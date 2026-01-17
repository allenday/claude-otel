#!/usr/bin/env python3
"""PreCompact hook: record context window compaction events.

Receives compaction trigger data via stdin JSON and emits a span event
to track when and why context compaction occurs during a Claude session.
"""

import json
import os
import sys
from typing import Optional

# Import OTEL after ensuring package is available
try:
    from opentelemetry import trace
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import BatchSpanProcessor
    from opentelemetry.sdk.resources import Resource, SERVICE_NAME, SERVICE_NAMESPACE
    from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter

    OTEL_AVAILABLE = True
except ImportError:
    OTEL_AVAILABLE = False


# Default configuration
DEFAULT_ENDPOINT = "http://100.91.20.46:4317"
DEFAULT_SERVICE_NAME = "claude-cli"
DEFAULT_SERVICE_NAMESPACE = "claude-otel"


def get_env(key: str, default: str) -> str:
    """Get environment variable with default."""
    return os.environ.get(key, default)


def setup_tracer() -> Optional[trace.Tracer]:
    """Set up OTEL tracer with configured exporter."""
    if not OTEL_AVAILABLE:
        return None

    # Check if traces are enabled
    if get_env("OTEL_TRACES_EXPORTER", "otlp").lower() == "none":
        return None

    try:
        endpoint = get_env("OTEL_EXPORTER_OTLP_ENDPOINT", DEFAULT_ENDPOINT)
        service_name = get_env("OTEL_SERVICE_NAME", DEFAULT_SERVICE_NAME)
        service_namespace = get_env("OTEL_SERVICE_NAMESPACE", DEFAULT_SERVICE_NAMESPACE)

        resource = Resource.create(
            {
                SERVICE_NAME: service_name,
                SERVICE_NAMESPACE: service_namespace,
            }
        )

        provider = TracerProvider(resource=resource)
        exporter = OTLPSpanExporter(endpoint=endpoint, insecure=True)
        provider.add_span_processor(BatchSpanProcessor(exporter))

        trace.set_tracer_provider(provider)
        return trace.get_tracer("claude-otel-hooks", "0.1.0")

    except Exception as e:
        if get_env("CLAUDE_OTEL_DEBUG", "").lower() in ("1", "true"):
            print(f"[claude-otel] Tracer setup error: {e}", file=sys.stderr)
        return None


def main():
    """Entry point for pre-compact hook."""
    try:
        # Parse input from Claude
        input_data = json.load(sys.stdin)

        # Extract compaction metadata
        trigger = input_data.get("trigger", "unknown")
        custom_instructions = input_data.get("custom_instructions")
        session_id = input_data.get("session_id", "")

        # Set up tracer
        tracer = setup_tracer()
        if not tracer:
            return

        # Create a span event for the compaction
        # Since we don't have a session span context here, we create a standalone span
        with tracer.start_as_current_span("context.compaction") as span:
            # Set attributes
            span.set_attribute("compaction.trigger", trigger)
            span.set_attribute("compaction.has_custom_instructions", custom_instructions is not None)
            span.set_attribute("session.id", session_id)

            # Add event for timeline visibility
            span.add_event(
                "Context compaction triggered",
                {
                    "trigger": trigger,
                    "has_custom_instructions": custom_instructions is not None,
                },
            )

        # Force flush to ensure span is exported
        provider = trace.get_tracer_provider()
        if hasattr(provider, "force_flush"):
            provider.force_flush(timeout_millis=5000)

    except Exception as e:
        # Don't block compaction on errors
        if os.environ.get("CLAUDE_OTEL_DEBUG", "").lower() in ("1", "true"):
            print(f"[claude-otel] PreCompact error: {e}", file=sys.stderr)


if __name__ == "__main__":
    main()
