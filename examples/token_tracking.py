#!/usr/bin/env python3
"""Token tracking example.

Demonstrates detailed token usage tracking including:
- Input/output tokens per turn
- Cache hits/misses
- Cumulative token usage
- Cost estimation

Run:
    python examples/token_tracking.py

Environment:
    OTEL_METRICS_EXPORTER=otlp - Enable metrics export
"""

import asyncio
import logging

from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.resources import Resource
from rich.console import Console
from rich.table import Table

from claude_otel.config import get_config
from claude_otel.exporter import setup_exporters
from claude_otel.sdk_runner import run_agent_with_sdk, setup_sdk_hooks

console = Console()
logging.basicConfig(level=logging.WARNING)
logger = logging.getLogger(__name__)


async def main():
    """Track token usage across multiple prompts."""

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

    # Initialize hooks to track state
    hooks_instance, _ = setup_sdk_hooks(tracer)

    console.print(Panel(
        "[bold cyan]Token Usage Tracking Example[/bold cyan]\n\n"
        "This example demonstrates detailed token tracking:\n"
        "• Per-turn input/output tokens\n"
        "• Cache read/creation tokens\n"
        "• Cumulative session totals\n"
        "• Cost estimation",
        border_style="cyan"
    ))

    # Test prompts
    prompts = [
        "What is the capital of France?",
        "What is the population of that city?",  # Should use context
        "Tell me about its history in 2 sentences.",  # More context usage
    ]

    # Track token usage
    token_records = []

    for i, prompt in enumerate(prompts, 1):
        console.print(f"\n[bold yellow]Prompt {i}:[/bold yellow] {prompt}")

        # Run agent
        with tracer.start_as_current_span(f"token_tracking.prompt_{i}") as span:
            exit_code = await run_agent_with_sdk(
                prompt=prompt,
                extra_args={"model": "sonnet"},
                config=config,
                tracer=tracer,
                logger=logger,
            )

            # Extract token usage from hooks
            if hooks_instance.session_state:
                state = hooks_instance.session_state
                record = {
                    "turn": i,
                    "input": state.get("last_input_tokens", 0),
                    "output": state.get("last_output_tokens", 0),
                    "cache_read": state.get("last_cache_read_tokens", 0),
                    "cache_creation": state.get("last_cache_creation_tokens", 0),
                    "total_cumulative": state.get("total_input_tokens", 0) + state.get("total_output_tokens", 0),
                }
                token_records.append(record)

                # Add to span
                span.set_attribute("tokens.input", record["input"])
                span.set_attribute("tokens.output", record["output"])
                span.set_attribute("tokens.cache_read", record["cache_read"])
                span.set_attribute("tokens.cache_creation", record["cache_creation"])

    # Display results
    console.print("\n[bold green]Token Usage Summary[/bold green]\n")

    table = Table(show_header=True, header_style="bold cyan")
    table.add_column("Turn", style="dim", width=6)
    table.add_column("Input", justify="right")
    table.add_column("Output", justify="right")
    table.add_column("Cache Read", justify="right")
    table.add_column("Cache Create", justify="right")
    table.add_column("Total (Turn)", justify="right")
    table.add_column("Cumulative", justify="right")

    for record in token_records:
        turn_total = record["input"] + record["output"]
        table.add_row(
            str(record["turn"]),
            str(record["input"]),
            str(record["output"]),
            str(record["cache_read"]) if record["cache_read"] > 0 else "-",
            str(record["cache_creation"]) if record["cache_creation"] > 0 else "-",
            str(turn_total),
            str(record["total_cumulative"]),
        )

    console.print(table)

    # Calculate totals
    total_input = sum(r["input"] for r in token_records)
    total_output = sum(r["output"] for r in token_records)
    total_cache_read = sum(r["cache_read"] for r in token_records)
    total_cache_creation = sum(r["cache_creation"] for r in token_records)

    # Cost estimation (example rates - adjust for actual pricing)
    SONNET_INPUT_COST_PER_1M = 3.00  # $3 per 1M input tokens
    SONNET_OUTPUT_COST_PER_1M = 15.00  # $15 per 1M output tokens
    CACHE_READ_COST_PER_1M = 0.30  # $0.30 per 1M cache read tokens

    input_cost = (total_input / 1_000_000) * SONNET_INPUT_COST_PER_1M
    output_cost = (total_output / 1_000_000) * SONNET_OUTPUT_COST_PER_1M
    cache_cost = (total_cache_read / 1_000_000) * CACHE_READ_COST_PER_1M
    total_cost = input_cost + output_cost + cache_cost

    console.print(f"\n[bold cyan]Totals:[/bold cyan]")
    console.print(f"  Input tokens: {total_input:,}")
    console.print(f"  Output tokens: {total_output:,}")
    console.print(f"  Cache read tokens: {total_cache_read:,}")
    console.print(f"  Cache creation tokens: {total_cache_creation:,}")

    console.print(f"\n[bold cyan]Estimated Cost:[/bold cyan]")
    console.print(f"  Input: ${input_cost:.6f}")
    console.print(f"  Output: ${output_cost:.6f}")
    console.print(f"  Cache reads: ${cache_cost:.6f}")
    console.print(f"  [bold]Total: ${total_cost:.6f}[/bold]")

    if total_cache_read > 0:
        savings = ((total_cache_read / 1_000_000) * (SONNET_INPUT_COST_PER_1M - CACHE_READ_COST_PER_1M))
        console.print(f"  [green]Cache savings: ${savings:.6f}[/green]")

    # Flush telemetry
    provider.force_flush()
    provider.shutdown()

    console.print("\n[dim]Token usage telemetry exported to collector[/dim]")


if __name__ == "__main__":
    asyncio.run(main())
