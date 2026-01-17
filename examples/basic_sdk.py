#!/usr/bin/env python3
"""Basic SDK usage example.

This example demonstrates the simplest way to use claude-otel with SDK mode
for enhanced telemetry including semantic conventions and turn tracking.

Run:
    python examples/basic_sdk.py

Environment:
    OTEL_EXPORTER_OTLP_ENDPOINT - OTLP collector endpoint (default: http://localhost:4317)
    OTEL_METRICS_EXPORTER - Set to 'otlp' to enable metrics
    CLAUDE_OTEL_DEBUG - Set to '1' for debug output
"""

import asyncio
import logging

from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.resources import Resource

from claude_otel.config import get_config
from claude_otel.exporter import setup_exporters
from claude_otel.sdk_runner import run_agent_with_sdk

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="[%(levelname)s] %(message)s"
)
logger = logging.getLogger(__name__)


async def main():
    """Run a simple SDK-based Claude session with OTEL instrumentation."""

    # Load configuration from environment
    config = get_config()

    logger.info("Starting Claude OTEL SDK Example")
    logger.info(f"Service: {config.service_name}")
    logger.info(f"Endpoint: {config.endpoint}")
    logger.info(f"Traces: {'enabled' if config.traces_enabled else 'disabled'}")
    logger.info(f"Metrics: {'enabled' if config.metrics_enabled else 'disabled'}")

    # Setup OTEL exporters and tracer provider
    resource = Resource.create({
        "service.name": config.service_name,
        "service.namespace": config.service_namespace,
    })

    provider = TracerProvider(resource=resource)
    trace.set_tracer_provider(provider)

    # Setup exporters for traces/logs/metrics
    setup_exporters(provider, config, logger)

    # Get tracer
    tracer = trace.get_tracer(__name__)

    # Run a simple prompt with SDK mode
    # This will:
    # 1. Create a session span with gen_ai.* attributes
    # 2. Track turns and token usage
    # 3. Create tool spans for any tool usage
    # 4. Export metrics (if enabled)
    prompt = "What is the capital of France? Be concise."

    logger.info(f"\nSending prompt: {prompt}")

    exit_code = await run_agent_with_sdk(
        prompt=prompt,
        extra_args={"model": "sonnet"},  # Optional: specify model
        config=config,
        tracer=tracer,
        logger=logger,
    )

    # Flush and shutdown exporters
    provider.force_flush()
    provider.shutdown()

    logger.info(f"\nCompleted with exit code: {exit_code}")

    if config.traces_enabled:
        logger.info("\nCheck your OTLP collector for traces with:")
        logger.info(f"  - service.name: {config.service_name}")
        logger.info("  - gen_ai.system: anthropic")
        logger.info("  - gen_ai.request.model: claude-sonnet-4")
        logger.info("  - Span attributes: turns, tokens, tool usage")


if __name__ == "__main__":
    asyncio.run(main())
