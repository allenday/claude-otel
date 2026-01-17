"""Command-line interface for Claude OTEL wrapper."""

import os
import sys
from typing import Annotated

import typer
from rich.console import Console
from rich.table import Table

from claude_otel.config import get_config

console = Console()

# Create Typer app with settings to allow unknown options (for Claude CLI passthrough)
app = typer.Typer(
    context_settings={"ignore_unknown_options": True, "allow_extra_args": True},
    add_completion=False,
    rich_markup_mode="rich",
    pretty_exceptions_enable=True,
)


def version_callback(value: bool) -> None:
    """Show version and exit."""
    if value:
        console.print("claude-otel version 0.1.0")
        raise typer.Exit


def config_callback(value: bool) -> None:
    """Show config and exit."""
    if value:
        show_config()
        raise typer.Exit


def show_config() -> None:
    """Show current configuration and environment."""
    config = get_config()

    table = Table(title="Configuration", show_header=True)
    table.add_column("Setting", style="cyan")
    table.add_column("Value", style="green")
    table.add_column("Source", style="dim")

    # OTEL configuration
    table.add_row("Service Name", config.service_name, "Environment")
    table.add_row("Service Namespace", config.service_namespace, "Environment")
    table.add_row("Endpoint", config.endpoint, "Environment")
    table.add_row("Protocol", config.protocol, "Environment")
    table.add_row("Traces Enabled", str(config.traces_enabled), "Environment")
    table.add_row("Logs Enabled", str(config.logs_enabled), "Environment")
    table.add_row("Metrics Enabled", str(config.metrics_enabled), "Environment")
    table.add_row("Sampler", config.traces_sampler, "Environment")

    if config.debug:
        table.add_row("Debug Mode", "Enabled", "Environment")

    console.print(table)


def show_startup_banner(extra_args: dict[str, str | None] | None = None) -> None:
    """Show startup banner for interactive mode.

    Args:
        extra_args: Extra arguments passed to Claude SDK (e.g., model, flags)
    """
    from rich.panel import Panel

    config = get_config()

    # Build banner text
    banner_lines = [
        "[bold cyan]Claude CLI with OpenTelemetry[/bold cyan]",
        "",
        f"Service: [green]{config.service_name}[/green]",
        f"Endpoint: [green]{config.endpoint}[/green]",
        f"Telemetry: [green]{'Enabled' if config.traces_enabled else 'Disabled'}[/green]",
    ]

    # Add model info if available
    if extra_args and "model" in extra_args:
        banner_lines.append(f"Model: [green]{extra_args['model']}[/green]")

    banner_lines.extend([
        "",
        "[dim]Type 'exit', 'quit', or 'bye' to end the session[/dim]",
        "[dim]Press Ctrl+C twice to exit immediately[/dim]",
    ])

    console.print(
        Panel(
            "\n".join(banner_lines),
            title="Interactive Mode",
            border_style="cyan",
        )
    )


def parse_claude_args(
    args: list[str] | None,
) -> tuple[str | None, dict[str, str | None]]:
    """
    Parse Claude CLI arguments into prompt and flags dict.

    Strategy:
    1. Last non-option argument is the prompt
    2. Parse flags:
       - `--flag=value` → {flag: value}
       - `--flag` followed by non-option → {flag: value}
       - `--flag` standalone → {flag: None}

    Args:
        args: Raw arguments from command line

    Returns:
        Tuple of (prompt, extra_args dict for Claude SDK)
    """
    if args is None or len(args) == 0:
        return None, {}

    # Find the last non-option argument (the prompt)
    prompt = None
    claude_args = list(args)

    for i in range(len(claude_args) - 1, -1, -1):
        if not claude_args[i].startswith("-"):
            prompt = claude_args.pop(i)
            break

    # Parse flags into dict for SDK
    extra_args = {}
    i = 0
    while i < len(claude_args):
        arg = claude_args[i]

        if "=" in arg:
            # --flag=value format
            key, value = arg.lstrip("-").split("=", 1)
            extra_args[key] = value
            i += 1
        elif i + 1 < len(claude_args) and not claude_args[i + 1].startswith("-"):
            # --flag value format (next arg is not a flag)
            extra_args[arg.lstrip("-")] = claude_args[i + 1]
            i += 2
        else:
            # --flag standalone (boolean flag)
            extra_args[arg.lstrip("-")] = None
            i += 1

    return prompt, extra_args


@app.command(
    context_settings={"ignore_unknown_options": True},
    help="""
    [bold]🔭 Claude CLI with OpenTelemetry instrumentation[/bold]

    claude-otel is a lightweight wrapper around Claude CLI that adds OTEL telemetry.
    All Claude CLI flags are supported - just pass them through.

    [bold]Examples:[/bold]

      # Single prompt (recommended: use = for flags)
      claude-otel --permission-mode=bypassPermissions "fix this bug"

      # With specific model
      claude-otel --model=opus "review my code"

      # Using SDK mode for richer telemetry
      claude-otel --use-sdk "analyze the codebase"

      # With debug output
      claude-otel --claude-otel-debug "what files handle routing?"

    [bold]Modes:[/bold]
      - Default: subprocess wrapper (lightweight, uses CLI hooks)
      - --use-sdk: SDK-based runner (richer telemetry with turn tracking)

    [bold]Note:[/bold] For flags that take values, the --flag=value format
    is recommended to avoid ambiguity with the prompt argument.
    """,
)
def main(
    args: Annotated[
        list[str],
        typer.Argument(help="Prompt and Claude CLI flags (all pass-through arguments)"),
    ] = None,
    use_sdk: Annotated[
        bool,
        typer.Option(
            "--use-sdk",
            help="Use SDK-based runner for richer telemetry (default: subprocess wrapper)",
        ),
    ] = False,
    claude_otel_debug: Annotated[
        bool,
        typer.Option(
            "--claude-otel-debug",
            help="Enable claude-otel debug output",
            envvar="CLAUDE_OTEL_DEBUG",
        ),
    ] = False,
    version: Annotated[
        bool | None,
        typer.Option(
            "--version",
            "-v",
            callback=version_callback,
            is_eager=True,
            help="Show version and exit",
        ),
    ] = None,
    config: Annotated[
        bool | None,
        typer.Option(
            "--config",
            callback=config_callback,
            is_eager=True,
            help="Show configuration and exit",
        ),
    ] = None,
) -> None:
    """Main CLI entry point."""
    # Set debug mode if requested
    if claude_otel_debug:
        os.environ["CLAUDE_OTEL_DEBUG"] = "1"

    # Get configuration (will pick up debug flag)
    otel_config = get_config()

    # Parse arguments into prompt and Claude CLI flags
    if otel_config.debug:
        print(f"[claude-otel] Debug: raw args = {args}", file=sys.stderr)

    prompt, extra_args = parse_claude_args(args)

    if otel_config.debug:
        print(f"[claude-otel] Debug: extra_args = {extra_args}", file=sys.stderr)
        print(f"[claude-otel] Debug: prompt = {prompt}", file=sys.stderr)
        print(f"[claude-otel] Debug: use_sdk = {use_sdk}", file=sys.stderr)

    # Determine if interactive mode (no prompt provided)
    use_interactive = prompt is None

    if otel_config.debug:
        print(f"[claude-otel] Debug: use_interactive = {use_interactive}", file=sys.stderr)

    # Interactive mode only supported with SDK
    if use_interactive and not use_sdk:
        console.print("[yellow]Interactive mode requires --use-sdk flag[/yellow]")
        console.print("[dim]Usage: claude-otel --use-sdk[/dim]")
        raise typer.Exit(1)

    if use_interactive:
        # Show startup banner
        show_startup_banner(extra_args)

        # Import SDK runner and run interactive mode
        from claude_otel.wrapper import setup_tracing, setup_logging
        from claude_otel.sdk_runner import run_agent_interactive_sync

        tracer = setup_tracing(otel_config)
        logger, logger_provider = setup_logging(otel_config)

        try:
            exit_code = run_agent_interactive_sync(
                extra_args=extra_args,
                config=otel_config,
                tracer=tracer,
                logger=logger,
            )
            raise typer.Exit(exit_code)
        finally:
            if logger_provider:
                logger_provider.shutdown()
    else:
        # Single-turn mode: use existing wrapper logic
        # Import wrapper main and invoke it
        from claude_otel.wrapper import main as wrapper_main

        # Reconstruct args for wrapper
        reconstructed_args = []

        # Add use-sdk flag if requested
        if use_sdk:
            reconstructed_args.append("--use-sdk")

        # Add extra args
        for key, value in extra_args.items():
            if value is None:
                reconstructed_args.append(f"--{key}")
            else:
                reconstructed_args.append(f"--{key}={value}")

        # Add prompt if present
        if prompt:
            reconstructed_args.append(prompt)

        # Update sys.argv for wrapper.main() to parse
        sys.argv[1:] = reconstructed_args

        # Call wrapper main
        exit_code = wrapper_main()
        raise typer.Exit(exit_code)


if __name__ == "__main__":
    app()
