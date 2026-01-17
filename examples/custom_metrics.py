#!/usr/bin/env python3
"""Custom metrics example.

Demonstrates how to add application-specific metrics alongside built-in
OTEL metrics for tracking costs, quality scores, or other business KPIs.

Run:
    OTEL_METRICS_EXPORTER=otlp python examples/custom_metrics.py

Metrics exported:
    - Built-in: claude.tool_calls_total, claude.turns_total, etc.
    - Custom: claude.estimated_cost, claude.response_quality, claude.session_duration
"""

import asyncio
import logging
import time

from opentelemetry import trace, metrics
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.resources import Resource

from claude_otel.config import get_config
from claude_otel.exporter import setup_exporters
from claude_otel.sdk_runner import run_agent_with_sdk

logging.basicConfig(level=logging.INFO, format="[%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)


# Cost estimation (simplified - adjust for actual pricing)
COST_PER_1K_INPUT_TOKENS = 0.003  # Example: Sonnet pricing
COST_PER_1K_OUTPUT_TOKENS = 0.015


def estimate_cost(input_tokens: int, output_tokens: int) -> float:
    """Estimate cost based on token usage."""
    return (
        (input_tokens / 1000) * COST_PER_1K_INPUT_TOKENS +
        (output_tokens / 1000) * COST_PER_1K_OUTPUT_TOKENS
    )


async def main():
    """Run Claude with custom metrics tracking."""

    config = get_config()

    logger.info("Custom Metrics Example")
    logger.info(f"Service: {config.service_name}")
    logger.info(f"Metrics: {'enabled' if config.metrics_enabled else 'disabled'}")

    # Setup OTEL
    resource = Resource.create({
        "service.name": config.service_name,
        "service.namespace": config.service_namespace,
    })

    # Setup trace provider
    trace_provider = TracerProvider(resource=resource)
    trace.set_tracer_provider(trace_provider)

    # Setup meter provider for custom metrics
    meter_provider = MeterProvider(resource=resource)
    metrics.set_meter_provider(meter_provider)

    # Setup exporters
    setup_exporters(trace_provider, config, logger)

    # Create custom meter
    meter = metrics.get_meter(__name__)

    # Define custom metrics
    cost_counter = meter.create_counter(
        name="claude.estimated_cost",
        description="Estimated cost of Claude API calls in USD",
        unit="USD"
    )

    quality_histogram = meter.create_histogram(
        name="claude.response_quality",
        description="Quality score of responses (1-10)",
        unit="1"
    )

    duration_histogram = meter.create_histogram(
        name="claude.session_duration",
        description="Duration of Claude sessions",
        unit="ms"
    )

    # Get tracer
    tracer = trace.get_tracer(__name__)

    # Run multiple prompts and track custom metrics
    prompts = [
        "What is Python? Be very brief.",
        "Write a haiku about coding.",
        "Explain recursion in one sentence.",
    ]

    session_start = time.time()

    for i, prompt in enumerate(prompts, 1):
        logger.info(f"\n[{i}/{len(prompts)}] Prompt: {prompt}")

        # Track prompt-level span
        with tracer.start_as_current_span("custom_metrics.prompt") as span:
            span.set_attribute("prompt.index", i)
            span.set_attribute("prompt.text", prompt[:100])

            prompt_start = time.time()

            # Run agent
            exit_code = await run_agent_with_sdk(
                prompt=prompt,
                extra_args={"model": "sonnet"},
                config=config,
                tracer=tracer,
                logger=logger,
            )

            prompt_duration = (time.time() - prompt_start) * 1000

            # Record duration
            duration_histogram.record(prompt_duration, {"model": "sonnet"})

            # Simulate extracting token usage (in real app, get from hooks)
            # For this example, estimate based on prompt/response length
            estimated_input_tokens = len(prompt.split()) * 1.3  # Rough estimate
            estimated_output_tokens = 50  # Assume short response

            # Calculate and record cost
            cost = estimate_cost(estimated_input_tokens, estimated_output_tokens)
            cost_counter.add(cost, {"model": "sonnet", "prompt_type": "question"})

            logger.info(f"  Duration: {prompt_duration:.2f}ms")
            logger.info(f"  Estimated cost: ${cost:.6f}")

            # Simulate quality scoring (in real app, could use actual scoring)
            quality_score = 8.5 if exit_code == 0 else 3.0
            quality_histogram.record(quality_score, {"model": "sonnet"})

            span.set_attribute("quality_score", quality_score)
            span.set_attribute("estimated_cost_usd", cost)

    session_duration = (time.time() - session_start) * 1000
    duration_histogram.record(session_duration, {"model": "sonnet", "type": "full_session"})

    # Flush and shutdown
    trace_provider.force_flush()
    meter_provider.force_flush()
    trace_provider.shutdown()
    meter_provider.shutdown()

    logger.info(f"\n✓ Session completed in {session_duration:.2f}ms")
    logger.info("\nCustom metrics exported:")
    logger.info("  - claude.estimated_cost (counter)")
    logger.info("  - claude.response_quality (histogram)")
    logger.info("  - claude.session_duration (histogram)")

    if config.metrics_enabled:
        logger.info(f"\nQuery metrics in your collector at: {config.endpoint}")
        logger.info("Example Prometheus queries:")
        logger.info("  - sum(claude_estimated_cost_total)")
        logger.info("  - histogram_quantile(0.95, claude_response_quality)")
        logger.info("  - histogram_quantile(0.99, claude_session_duration)")


if __name__ == "__main__":
    asyncio.run(main())
