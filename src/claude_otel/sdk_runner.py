"""SDK-based runner for Claude agent with OpenTelemetry instrumentation.

This module provides an alternative to the subprocess wrapper, using the
claude-agent-sdk directly for richer telemetry via SDK hooks.
"""

import asyncio
import logging
import time
from typing import Optional

from claude_agent_sdk import ClaudeAgentOptions, ClaudeSDKClient, HookMatcher
from claude_agent_sdk.types import PermissionResultAllow, PermissionResultDeny, ToolPermissionContext
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel
from rich.prompt import Confirm

from claude_otel.config import get_config, OTelConfig
from claude_otel.sdk_hooks import SDKTelemetryHooks
from claude_otel import metrics as otel_metrics


async def permission_callback(
    tool_name: str,
    tool_input: dict,
    context: ToolPermissionContext,
) -> PermissionResultAllow | PermissionResultDeny:
    """Interactive permission callback for tool use.

    Prompts the user in the terminal for permission to use a tool.

    Args:
        tool_name: Name of the tool to use
        tool_input: Tool input parameters
        context: Permission context with signal and suggestions

    Returns:
        PermissionResultAllow or PermissionResultDeny
    """
    console = Console()

    # Show tool info
    console.print(f"\n[yellow]Permission request for tool:[/yellow] [bold]{tool_name}[/bold]")

    # Show truncated input
    input_preview = str(tool_input)[:200]
    if len(str(tool_input)) > 200:
        input_preview += "..."
    console.print(f"[dim]Input: {input_preview}[/dim]")

    # Prompt for permission
    try:
        if Confirm.ask("[cyan]Allow this tool use?[/cyan]", default=True):
            return PermissionResultAllow()
        else:
            return PermissionResultDeny(message="User denied permission")
    except (EOFError, KeyboardInterrupt):
        # If user interrupts, deny by default
        return PermissionResultDeny(message="Permission prompt interrupted", interrupt=True)


def setup_sdk_hooks(
    tracer: trace.Tracer,
    logger: Optional[logging.Logger] = None,
) -> tuple[SDKTelemetryHooks, dict]:
    """Initialize SDK hooks and create hook configuration for ClaudeAgentOptions.

    Args:
        tracer: OpenTelemetry tracer to use for spans
        logger: Optional logger for OTEL logging (emits per-tool logs)

    Returns:
        Tuple of (hooks instance, hook_config dict for SDK)
    """
    hooks = SDKTelemetryHooks(tracer=tracer, logger=logger)

    hook_config = {
        "UserPromptSubmit": [
            HookMatcher(matcher=None, hooks=[hooks.on_user_prompt_submit])
        ],
        "PreToolUse": [
            HookMatcher(matcher=None, hooks=[hooks.on_pre_tool_use])
        ],
        "PostToolUse": [
            HookMatcher(matcher=None, hooks=[hooks.on_post_tool_use])
        ],
        # Note: MessageComplete is not a supported hook in claude-agent-sdk
        # The SDK supports: UserPromptSubmit, PreToolUse, PostToolUse, PreCompact, Stop, SubagentStop
        # We use the Stop hook instead to get final session data including token counts
        "Stop": [
            HookMatcher(matcher=None, hooks=[hooks.on_stop])
        ],
        "PreCompact": [
            HookMatcher(matcher=None, hooks=[hooks.on_pre_compact])
        ],
    }

    return hooks, hook_config


async def run_agent_with_sdk(
    prompt: str,
    extra_args: Optional[dict[str, Optional[str]]] = None,
    config: Optional[OTelConfig] = None,
    tracer: Optional[trace.Tracer] = None,
    logger: Optional[logging.Logger] = None,
) -> int:
    """Run Claude agent via SDK with OpenTelemetry instrumentation.

    Args:
        prompt: User prompt to send to Claude
        extra_args: Extra arguments to pass to Claude SDK (e.g., {"model": "opus"})
        config: Optional OTelConfig; uses get_config() if not provided
        tracer: Optional tracer; required for telemetry
        logger: Optional logger for OTEL logging

    Returns:
        Exit code (0 for success, 1 for error)
    """
    if extra_args is None:
        extra_args = {}

    if config is None:
        config = get_config()

    if tracer is None:
        raise ValueError("Tracer is required for SDK runner")

    # Initialize SDK hooks
    hooks, hook_config = setup_sdk_hooks(tracer, logger)

    # Callback for stderr output from Claude CLI
    def log_claude_stderr(line: str) -> None:
        """Log Claude CLI stderr output for debugging."""
        if line.strip():
            if logger:
                logger.info(f"[Claude CLI] {line}")
            elif config.debug:
                print(f"[claude-otel-sdk] {line}")

    # Extract permission_mode from extra_args if present
    # SDK requires it as a direct parameter, not via extra_args
    permission_mode = extra_args.get("permission-mode") if extra_args else None

    # Use interactive permission callback if no permission mode specified
    # This ensures users see permission prompts in SDK mode
    can_use_tool_callback = permission_callback if permission_mode is None else None

    # Create agent options with hooks
    # IMPORTANT: Must explicitly set setting_sources to load user/project/local settings
    # SDK defaults to isolated environment (no settings) when None.
    # We want CLI-like behavior, so explicitly request all sources.
    options = ClaudeAgentOptions(
        hooks=hook_config,
        setting_sources=["user", "project", "local"],
        extra_args=extra_args,
        stderr=log_claude_stderr if config.debug else None,
        permission_mode=permission_mode,
        can_use_tool=can_use_tool_callback,
    )

    # Use Rich Console for formatted output
    console = Console()
    response_text = ""

    try:
        async with ClaudeSDKClient(options=options) as client:
            # Send the query
            await client.query(prompt=prompt)

            # Receive and process responses
            async for message in client.receive_response():
                # Extract and accumulate text content
                text = extract_message_text(message)
                if text:
                    response_text += text

            # Display response with formatting
            if response_text:
                console.print(
                    Panel(
                        Markdown(response_text),
                        title="Claude",
                        border_style="cyan",
                    )
                )

        # Complete the session span
        if hooks.session_span:
            hooks.complete_session()

        if logger:
            logger.info("claude SDK session completed successfully")

        return 0

    except KeyboardInterrupt:
        if logger:
            logger.info("claude SDK session interrupted by user")
        return 130  # Standard exit code for SIGINT

    except Exception as e:
        error_msg = str(e)
        if logger:
            logger.error(f"claude SDK error: {error_msg}")
        else:
            print(f"[claude-otel-sdk] Error: {error_msg}")

        # Mark session span as error if it exists
        if hooks.session_span:
            from opentelemetry.trace import Status, StatusCode
            hooks.session_span.set_status(Status(StatusCode.ERROR, error_msg))
            hooks.complete_session()

        return 1


def extract_message_text(message) -> str:
    """Extract text content from Claude SDK message.

    Handles different message content types:
    - List of text blocks
    - String content
    - Other content types (converted to string)

    Args:
        message: Claude SDK message object

    Returns:
        Extracted text content or empty string
    """
    if not hasattr(message, "content"):
        return ""

    content = message.content

    if isinstance(content, list):
        # Extract text from list of blocks with proper spacing
        return "\n".join(block.text for block in content if hasattr(block, "text"))
    elif isinstance(content, str):
        return content
    else:
        # Fallback for other types
        return str(content)


def get_interactive_prompt(turn_number: int, console: Console) -> str:
    """Get user input with a styled prompt showing context.

    Supports multiline input with Meta+Enter (Alt+Enter) to submit.

    Args:
        turn_number: Current turn number (1-indexed)
        console: Rich console for styled output

    Returns:
        User input string
    """
    from prompt_toolkit import PromptSession
    from prompt_toolkit.formatted_text import HTML
    from prompt_toolkit.key_binding import KeyBindings

    # Create key bindings for multiline support
    bindings = KeyBindings()

    @bindings.add("escape", "enter")  # Alt/Meta + Enter
    def _(event):
        """Submit input on Meta+Enter."""
        event.current_buffer.validate_and_handle()

    # Create styled prompt text
    prompt_text = HTML(f'<ansibrightcyan><b>Turn {turn_number}</b></ansibrightcyan> <ansi-dim>›</ansi-dim> ')

    # Create prompt session with multiline support
    session = PromptSession(
        message=prompt_text,
        multiline=True,
        key_bindings=bindings,
    )

    try:
        # Get input (plain Enter for newline, Meta+Enter to submit)
        return session.prompt()
    except (EOFError, KeyboardInterrupt):
        # Re-raise these for proper handling
        raise


async def run_agent_interactive(
    extra_args: Optional[dict[str, Optional[str]]] = None,
    config: Optional[OTelConfig] = None,
    tracer: Optional[trace.Tracer] = None,
    logger: Optional[logging.Logger] = None,
) -> int:
    """Run Claude agent in interactive mode (multi-turn conversation).

    Args:
        extra_args: Extra arguments to pass to Claude SDK (e.g., {"model": "opus"})
        config: Optional OTelConfig; uses get_config() if not provided
        tracer: Optional tracer; required for telemetry
        logger: Optional logger for OTEL logging

    Returns:
        Exit code (0 for success, 130 for Ctrl+C)
    """
    if extra_args is None:
        extra_args = {}

    if config is None:
        config = get_config()

    if tracer is None:
        raise ValueError("Tracer is required for SDK runner")

    # Initialize SDK hooks (shared across all turns)
    hooks, hook_config = setup_sdk_hooks(tracer, logger)

    # Session metrics tracking
    session_metrics = {
        "total_input_tokens": 0,
        "total_output_tokens": 0,
        "total_cache_read_tokens": 0,
        "total_cache_creation_tokens": 0,
        "total_tools_used": 0,
        "prompts_count": 0,
    }

    # Prompt latency tracking
    last_prompt_completion_time: Optional[float] = None
    prompt_latencies: list[float] = []

    # Callback for stderr output from Claude CLI
    def log_claude_stderr(line: str) -> None:
        """Log Claude CLI stderr output for debugging."""
        if line.strip():
            if logger:
                logger.info(f"[Claude CLI] {line}")
            elif config.debug:
                print(f"[claude-otel-sdk] {line}")

    # Extract permission_mode from extra_args if present
    # SDK requires it as a direct parameter, not via extra_args
    permission_mode = extra_args.get("permission-mode") if extra_args else None

    # Use interactive permission callback if no permission mode specified
    # This ensures users see permission prompts in SDK mode
    can_use_tool_callback = permission_callback if permission_mode is None else None

    # Create agent options with hooks
    options = ClaudeAgentOptions(
        hooks=hook_config,
        setting_sources=["user", "project", "local"],
        extra_args=extra_args,
        stderr=log_claude_stderr if config.debug else None,
        permission_mode=permission_mode,
        can_use_tool=can_use_tool_callback,
    )

    # Use Rich Console for formatted output
    console = Console()

    # Ctrl+C handling
    ctrl_c_count = 0

    try:
        # Create a single persistent client for the entire session
        async with ClaudeSDKClient(options=options) as client:
            # Multi-turn loop
            while True:
                try:
                    # Track prompt submission time for latency calculation
                    prompt_submit_time = time.time()

                    # Calculate latency from last prompt completion (if any)
                    if last_prompt_completion_time is not None:
                        prompt_latency_ms = (prompt_submit_time - last_prompt_completion_time) * 1000
                        prompt_latencies.append(prompt_latency_ms)

                        # Get model from hooks for metrics attribution
                        model = hooks.metrics.get("model", "unknown") if hasattr(hooks, "metrics") else "unknown"

                        # Record latency metric
                        otel_metrics.record_prompt_latency(prompt_latency_ms, model)

                        # Log latency metric
                        if logger:
                            logger.info(
                                "prompt.latency",
                                extra={
                                    "prompt.latency_ms": prompt_latency_ms,
                                    "turn": session_metrics["prompts_count"] + 1,
                                },
                            )

                        # Add latency event to session span
                        if hooks.session_span:
                            hooks.session_span.add_event(
                                "prompt.latency",
                                {
                                    "latency_ms": prompt_latency_ms,
                                    "turn": session_metrics["prompts_count"] + 1,
                                },
                            )

                    # Get user input with styled prompt
                    console.print()  # Empty line before prompt
                    user_input = get_interactive_prompt(
                        turn_number=session_metrics["prompts_count"] + 1,
                        console=console,
                    )
                    ctrl_c_count = 0  # Reset on successful input

                    # Check for exit commands
                    if user_input.strip().lower() in ["exit", "quit", "bye"]:
                        console.print("\n[dim]Goodbye![/dim]")
                        break

                    # Skip empty input
                    if not user_input.strip():
                        continue

                    # Show processing indicator
                    console.print("\n[dim]Processing...[/dim]")

                    # Send the query
                    await client.query(prompt=user_input)
                    session_metrics["prompts_count"] += 1

                    # Receive and process responses
                    response_text = ""
                    async for message in client.receive_response():
                        # Extract and accumulate text content
                        text = extract_message_text(message)
                        if text:
                            response_text += text

                    # Display response with formatting
                    if response_text:
                        console.print(
                            Panel(
                                Markdown(response_text),
                                title="Claude",
                                border_style="cyan",
                            )
                        )

                    # Record prompt completion time for next latency calculation
                    last_prompt_completion_time = time.time()

                    # Update session metrics from hooks
                    if hasattr(hooks, "metrics"):
                        session_metrics["total_input_tokens"] = hooks.metrics.get("input_tokens", 0)
                        session_metrics["total_output_tokens"] = hooks.metrics.get("output_tokens", 0)
                        session_metrics["total_cache_read_tokens"] = hooks.metrics.get("cache_read_tokens", 0)
                        session_metrics["total_cache_creation_tokens"] = hooks.metrics.get("cache_creation_tokens", 0)
                        session_metrics["total_tools_used"] = len(hooks.tools_used) if hasattr(hooks, "tools_used") else 0

                except KeyboardInterrupt:
                    ctrl_c_count += 1
                    if ctrl_c_count == 1:
                        console.print("\n[yellow]Press Ctrl+C again to exit, or type 'exit'[/yellow]")
                    else:
                        console.print("\n[dim]Exiting...[/dim]")
                        break

                except EOFError:
                    # Handle EOF (e.g., piped input)
                    console.print("\n[dim]EOF received, exiting...[/dim]")
                    break

                except Exception as e:
                    # Don't exit on error; continue session
                    error_msg = str(e)
                    console.print(f"\n[red]Error: {error_msg}[/red]")
                    if logger:
                        logger.error(f"Error in interactive session: {error_msg}")
                    # Continue to next prompt

        # Complete the session span
        if hooks.session_span:
            # Add latency statistics to session span
            if prompt_latencies:
                avg_latency = sum(prompt_latencies) / len(prompt_latencies)
                min_latency = min(prompt_latencies)
                max_latency = max(prompt_latencies)
                hooks.session_span.set_attribute("prompt.latency_avg_ms", avg_latency)
                hooks.session_span.set_attribute("prompt.latency_min_ms", min_latency)
                hooks.session_span.set_attribute("prompt.latency_max_ms", max_latency)
                hooks.session_span.set_attribute("prompt.latency_count", len(prompt_latencies))

            hooks.complete_session()

        # Show session summary
        console.print("\n[bold cyan]Session Summary[/bold cyan]")
        console.print(f"  Prompts: {session_metrics['prompts_count']}")
        console.print(f"  Total input tokens: {session_metrics['total_input_tokens']}")
        console.print(f"  Total output tokens: {session_metrics['total_output_tokens']}")
        if session_metrics['total_cache_read_tokens'] > 0:
            console.print(f"  Cache read tokens: {session_metrics['total_cache_read_tokens']}")
        if session_metrics['total_cache_creation_tokens'] > 0:
            console.print(f"  Cache creation tokens: {session_metrics['total_cache_creation_tokens']}")
        console.print(f"  Tools used: {session_metrics['total_tools_used']}")

        # Show prompt latency statistics
        if prompt_latencies:
            avg_latency = sum(prompt_latencies) / len(prompt_latencies)
            min_latency = min(prompt_latencies)
            max_latency = max(prompt_latencies)
            console.print(f"  Prompt latencies:")
            console.print(f"    Average: {avg_latency:.1f}ms")
            console.print(f"    Min: {min_latency:.1f}ms")
            console.print(f"    Max: {max_latency:.1f}ms")

        if logger:
            log_extra = {
                "tokens.input": session_metrics["total_input_tokens"],
                "tokens.output": session_metrics["total_output_tokens"],
                "tokens.cache_read": session_metrics["total_cache_read_tokens"],
                "tokens.cache_creation": session_metrics["total_cache_creation_tokens"],
                "tools.total": session_metrics["total_tools_used"],
                "prompts.count": session_metrics["prompts_count"],
            }

            # Add latency statistics if available
            if prompt_latencies:
                log_extra["prompt.latency_avg_ms"] = sum(prompt_latencies) / len(prompt_latencies)
                log_extra["prompt.latency_min_ms"] = min(prompt_latencies)
                log_extra["prompt.latency_max_ms"] = max(prompt_latencies)
                log_extra["prompt.latency_count"] = len(prompt_latencies)

            logger.info(
                "claude SDK interactive session completed",
                extra=log_extra,
            )

        return 0

    except KeyboardInterrupt:
        # Final Ctrl+C to exit immediately
        console.print("\n[dim]Interrupted[/dim]")
        if hooks.session_span:
            hooks.complete_session()
        if logger:
            logger.info("claude SDK interactive session interrupted")
        return 130


def run_agent_with_sdk_sync(
    prompt: str,
    extra_args: Optional[dict[str, Optional[str]]] = None,
    config: Optional[OTelConfig] = None,
    tracer: Optional[trace.Tracer] = None,
    logger: Optional[logging.Logger] = None,
) -> int:
    """Synchronous wrapper for run_agent_with_sdk.

    Args:
        prompt: User prompt to send to Claude
        extra_args: Extra arguments to pass to Claude SDK (e.g., {"model": "opus"})
        config: Optional OTelConfig; uses get_config() if not provided
        tracer: Optional tracer; required for telemetry
        logger: Optional logger for OTEL logging

    Returns:
        Exit code (0 for success, 1 for error)
    """
    result = asyncio.run(
        run_agent_with_sdk(
            prompt=prompt,
            extra_args=extra_args,
            config=config,
            tracer=tracer,
            logger=logger,
        )
    )

    # Emit a session summary log so Loki can show SDK runs even if spans/logs are sampled
    if logger:
        logger.info(
            "claude sdk session",
            extra={
                "session.prompt": (prompt[:100] + "…") if prompt and len(prompt) > 100 else (prompt or ""),
            },
        )

    return result


def run_agent_interactive_sync(
    extra_args: Optional[dict[str, Optional[str]]] = None,
    config: Optional[OTelConfig] = None,
    tracer: Optional[trace.Tracer] = None,
    logger: Optional[logging.Logger] = None,
) -> int:
    """Synchronous wrapper for run_agent_interactive.

    Args:
        extra_args: Extra arguments to pass to Claude SDK (e.g., {"model": "opus"})
        config: Optional OTelConfig; uses get_config() if not provided
        tracer: Optional tracer; required for telemetry
        logger: Optional logger for OTEL logging

    Returns:
        Exit code (0 for success, 130 for Ctrl+C)
    """
    return asyncio.run(
        run_agent_interactive(
            extra_args=extra_args,
            config=config,
            tracer=tracer,
            logger=logger,
        )
    )
