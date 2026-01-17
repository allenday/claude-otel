"""SDK-based runner for Claude agent with OpenTelemetry instrumentation.

This module provides an alternative to the subprocess wrapper, using the
claude-agent-sdk directly for richer telemetry via SDK hooks.
"""

import asyncio
import logging
from typing import Optional

from claude_agent_sdk import ClaudeAgentOptions, ClaudeSDKClient, HookMatcher
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider

from claude_otel.config import get_config, OTelConfig
from claude_otel.sdk_hooks import SDKTelemetryHooks


def setup_sdk_hooks(tracer: trace.Tracer) -> tuple[SDKTelemetryHooks, dict]:
    """Initialize SDK hooks and create hook configuration for ClaudeAgentOptions.

    Args:
        tracer: OpenTelemetry tracer to use for spans

    Returns:
        Tuple of (hooks instance, hook_config dict for SDK)
    """
    hooks = SDKTelemetryHooks(tracer=tracer)

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
        "MessageComplete": [
            HookMatcher(matcher=None, hooks=[hooks.on_message_complete])
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
    hooks, hook_config = setup_sdk_hooks(tracer)

    # Callback for stderr output from Claude CLI
    def log_claude_stderr(line: str) -> None:
        """Log Claude CLI stderr output for debugging."""
        if line.strip():
            if logger:
                logger.info(f"[Claude CLI] {line}")
            elif config.debug:
                print(f"[claude-otel-sdk] {line}")

    # Create agent options with hooks
    # IMPORTANT: Must explicitly set setting_sources to load user/project/local settings
    # SDK defaults to isolated environment (no settings) when None.
    # We want CLI-like behavior, so explicitly request all sources.
    options = ClaudeAgentOptions(
        hooks=hook_config,
        setting_sources=["user", "project", "local"],
        extra_args=extra_args,
        stderr=log_claude_stderr if config.debug else None,
    )

    try:
        async with ClaudeSDKClient(options=options) as client:
            # Send the query
            await client.query(prompt=prompt)

            # Receive and process responses
            async for message in client.receive_response():
                # Extract and display text content
                text = extract_message_text(message)
                if text:
                    print(text, end="", flush=True)

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
        # Extract text from list of blocks
        return "".join(block.text for block in content if hasattr(block, "text"))
    elif isinstance(content, str):
        return content
    else:
        # Fallback for other types
        return str(content)


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
    return asyncio.run(
        run_agent_with_sdk(
            prompt=prompt,
            extra_args=extra_args,
            config=config,
            tracer=tracer,
            logger=logger,
        )
    )
