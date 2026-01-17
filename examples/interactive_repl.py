#!/usr/bin/env python3
"""Interactive REPL example.

Demonstrates multi-turn conversational interface with shared context and
session metrics tracking.

Run:
    python examples/interactive_repl.py

Features:
    - Multi-turn conversations with context preservation
    - Session metrics (total tokens, tools used)
    - Rich console output
    - Exit commands: exit, quit, bye, Ctrl+C
"""

import asyncio
import logging
import sys

from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.resources import Resource
from rich.console import Console
from rich.panel import Panel
from rich.prompt import Prompt

from claude_otel.config import get_config
from claude_otel.exporter import setup_exporters
from claude_otel.sdk_runner import setup_sdk_hooks
from claude_otel.cli import show_startup_banner

# Import SDK client
from claude_agent_sdk import ClaudeAgentOptions, ClaudeSDKClient

console = Console()
logging.basicConfig(level=logging.WARNING)
logger = logging.getLogger(__name__)


async def interactive_session():
    """Run an interactive REPL session with Claude."""

    # Load configuration
    config = get_config()

    # Setup OTEL
    resource = Resource.create({
        "service.name": config.service_name,
        "service.namespace": config.service_namespace,
    })
    provider = TracerProvider(resource=resource)
    trace.set_tracer_provider(provider)
    setup_exporters(provider, config, logger)

    tracer = trace.get_tracer(__name__)

    # Setup SDK hooks
    hooks_instance, hook_config = setup_sdk_hooks(tracer)

    # Create SDK options
    extra_args = {"model": "sonnet"}  # Can be customized
    options = ClaudeAgentOptions(
        hooks=hook_config,
        setting_sources=["user", "project", "local"],
        extra_args=extra_args,
    )

    # Show startup banner
    show_startup_banner(extra_args)

    # Session metrics
    total_turns = 0
    total_input_tokens = 0
    total_output_tokens = 0
    tools_used = set()

    # Start tracer span for the entire session
    with tracer.start_as_current_span("claude.interactive_session") as session_span:
        session_span.set_attribute("gen_ai.system", "anthropic")
        session_span.set_attribute("mode", "interactive")

        # Create SDK client
        client = ClaudeSDKClient(options)

        console.print("\n[bold cyan]Interactive Mode Ready[/bold cyan]")
        console.print("[dim]Type your message and press Enter. Use 'exit', 'quit', or 'bye' to end.[/dim]\n")

        try:
            while True:
                # Get user input
                try:
                    user_input = Prompt.ask("\n[bold green]You[/bold green]")
                except (EOFError, KeyboardInterrupt):
                    console.print("\n[yellow]Session interrupted[/yellow]")
                    break

                # Check for exit commands
                if user_input.strip().lower() in ["exit", "quit", "bye"]:
                    console.print("[cyan]Goodbye![/cyan]")
                    break

                if not user_input.strip():
                    continue

                # Send prompt to Claude
                console.print("\n[dim]Claude is thinking...[/dim]")

                try:
                    # Run the agent with current prompt
                    result = await client.run(user_input)

                    # Extract metrics from hooks
                    if hooks_instance.session_state:
                        state = hooks_instance.session_state
                        total_turns = state.get("turns", 0)
                        total_input_tokens = state.get("total_input_tokens", 0)
                        total_output_tokens = state.get("total_output_tokens", 0)
                        if "tools_used" in state:
                            tools_used.update(state["tools_used"])

                    # Display response
                    console.print(Panel(
                        result,
                        title="[bold blue]Claude[/bold blue]",
                        border_style="blue"
                    ))

                    # Show session metrics
                    metrics_text = (
                        f"[dim]Session: {total_turns} turns | "
                        f"{total_input_tokens + total_output_tokens} tokens "
                        f"({total_input_tokens} in, {total_output_tokens} out)"
                    )
                    if tools_used:
                        metrics_text += f" | {len(tools_used)} tools used"
                    metrics_text += "[/dim]"

                    console.print(metrics_text)

                except Exception as e:
                    console.print(f"[red]Error: {e}[/red]")
                    logger.exception("Error during agent run")

        except KeyboardInterrupt:
            console.print("\n[yellow]Session ended[/yellow]")

        # Update final session metrics
        session_span.set_attribute("turns", total_turns)
        session_span.set_attribute("total_input_tokens", total_input_tokens)
        session_span.set_attribute("total_output_tokens", total_output_tokens)
        if tools_used:
            session_span.set_attribute("tools_used", len(tools_used))
            session_span.set_attribute("tool_names", ",".join(sorted(tools_used)))

    # Shutdown
    provider.force_flush()
    provider.shutdown()

    console.print("\n[green]Session telemetry exported to collector[/green]")


if __name__ == "__main__":
    try:
        asyncio.run(interactive_session())
    except KeyboardInterrupt:
        console.print("\n[yellow]Interrupted[/yellow]")
        sys.exit(0)
