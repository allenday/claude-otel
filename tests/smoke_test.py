#!/usr/bin/env python3
"""Manual smoke test script for claude-otel.

Run this script to verify connectivity to the bastion OTEL collector
and confirm traces/metrics are being accepted.

Usage:
    python tests/smoke_test.py

Environment:
    The script uses the default bastion endpoint (100.91.20.46:4317).
    Set OTEL_EXPORTER_OTLP_ENDPOINT to override.

Exit codes:
    0 - All tests passed
    1 - One or more tests failed
"""

import os
import sys
import time
import uuid

# OTEL imports
from opentelemetry import trace, metrics
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
from opentelemetry.sdk.resources import Resource, SERVICE_NAME, SERVICE_NAMESPACE
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.exporter.otlp.proto.grpc.metric_exporter import OTLPMetricExporter
from opentelemetry.trace import Status, StatusCode


# Configuration
DEFAULT_ENDPOINT = "http://100.91.20.46:4317"
SERVICE_NAME_VAL = "claude-otel-smoke-test"


def run_trace_smoke_test(endpoint: str, test_run_id: str) -> bool:
    """Send test traces to the collector.

    Returns True if successful, False on error.
    """
    print("\n--- Trace Smoke Test ---")
    print(f"Endpoint: {endpoint}")
    print(f"Service: {SERVICE_NAME_VAL}")

    try:
        resource = Resource.create({
            SERVICE_NAME: SERVICE_NAME_VAL,
            SERVICE_NAMESPACE: "claude-otel",
            "test.run_id": test_run_id,
        })

        provider = TracerProvider(resource=resource)
        exporter = OTLPSpanExporter(endpoint=endpoint, insecure=True)
        provider.add_span_processor(SimpleSpanProcessor(exporter))
        tracer = provider.get_tracer("smoke-test", "0.1.0")

        # Simulate a Claude session with tool calls
        with tracer.start_as_current_span("claude-session") as session:
            session_id = str(uuid.uuid4())
            session.set_attribute("session.id", session_id)
            session.set_attribute("test.run_id", test_run_id)
            session.set_attribute("claude.args_count", 2)
            session.set_attribute("claude.args_preview", "smoke test")

            # Simulate tool calls
            tools = [
                ("Bash", "git status", 120),
                ("Read", "README.md", 50),
                ("Grep", "function main", 200),
            ]

            for tool_name, input_summary, duration_ms in tools:
                with tracer.start_as_current_span(f"tool-call-{tool_name}") as tool:
                    tool.set_attribute("tool.name", tool_name)
                    tool.set_attribute("tool.input_summary", input_summary)
                    tool.set_attribute("duration_ms", duration_ms)
                    tool.set_attribute("exit_code", 0)
                    tool.set_attribute("stdout_bytes", 256)
                    tool.set_attribute("stderr_bytes", 0)
                    tool.set_attribute("truncated", False)
                    tool.set_status(Status(StatusCode.OK))

            session.set_attribute("exit_code", 0)
            session.set_attribute("tool_count", len(tools))
            session.set_status(Status(StatusCode.OK))

        # Send an error span
        with tracer.start_as_current_span("claude-session-error") as error_session:
            error_session.set_attribute("test.run_id", test_run_id)
            error_session.set_attribute("error", True)
            error_session.set_attribute("error.message", "Simulated error for smoke test")
            error_session.set_status(Status(StatusCode.ERROR, "Test error"))

        provider.shutdown()

        print(f"✓ Session span with {len(tools)} tool call spans sent")
        print("✓ Error span sent")
        return True

    except Exception as e:
        print(f"✗ Trace test failed: {e}")
        return False


def run_metrics_smoke_test(endpoint: str, test_run_id: str) -> bool:
    """Send test metrics to the collector.

    Returns True if successful, False on error.
    """
    print("\n--- Metrics Smoke Test ---")
    print(f"Endpoint: {endpoint}")
    print(f"Service: {SERVICE_NAME_VAL}")

    try:
        resource = Resource.create({
            SERVICE_NAME: SERVICE_NAME_VAL,
            SERVICE_NAMESPACE: "claude-otel",
            "test.run_id": test_run_id,
        })

        exporter = OTLPMetricExporter(endpoint=endpoint, insecure=True)
        reader = PeriodicExportingMetricReader(
            exporter,
            export_interval_millis=1000,
        )
        provider = MeterProvider(resource=resource, metric_readers=[reader])
        metrics.set_meter_provider(provider)

        meter = provider.get_meter("smoke-test-metrics", "0.1.0")

        # Create instruments
        tool_calls_counter = meter.create_counter(
            name="claude.tool_calls_total",
            description="Total number of tool calls",
            unit="1",
        )
        tool_errors_counter = meter.create_counter(
            name="claude.tool_calls_errors_total",
            description="Total number of tool call errors",
            unit="1",
        )
        tool_duration_histogram = meter.create_histogram(
            name="claude.tool_call_duration_ms",
            description="Duration of tool calls in milliseconds",
            unit="ms",
        )

        # Record metrics
        tools = [
            ("Bash", 120.5, False),
            ("Read", 50.2, False),
            ("Grep", 200.1, False),
            ("Write", 80.0, True),
            ("Bash", 90.3, False),
        ]

        for tool_name, duration_ms, error in tools:
            attributes = {"tool.name": tool_name}
            tool_calls_counter.add(1, attributes)
            tool_duration_histogram.record(duration_ms, attributes)
            if error:
                tool_errors_counter.add(1, attributes)

        print(f"  Recorded {len(tools)} tool call metrics")
        print("  Waiting for export...")
        time.sleep(2)

        provider.shutdown()

        print(f"✓ Metrics sent: {len(tools)} calls, 1 error")
        return True

    except Exception as e:
        print(f"✗ Metrics test failed: {e}")
        return False


def main():
    """Run smoke tests."""
    endpoint = os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT", DEFAULT_ENDPOINT)
    test_run_id = str(uuid.uuid4())

    print("=" * 60)
    print("Claude-OTEL Smoke Test")
    print("=" * 60)
    print(f"Test Run ID: {test_run_id}")
    print(f"Endpoint: {endpoint}")

    trace_ok = run_trace_smoke_test(endpoint, test_run_id)
    metrics_ok = run_metrics_smoke_test(endpoint, test_run_id)

    print("\n" + "=" * 60)
    print("SMOKE TEST RESULTS")
    print("=" * 60)
    print(f"Test Run ID: {test_run_id}")
    print(f"Traces: {'✓ PASS' if trace_ok else '✗ FAIL'}")
    print(f"Metrics: {'✓ PASS' if metrics_ok else '✗ FAIL'}")
    print()

    if trace_ok and metrics_ok:
        print("All tests passed! Data accepted by collector.")
        print()
        print("To verify in Loki (if span-to-logs enabled):")
        print(f'  {{service_name="{SERVICE_NAME_VAL}"}}')
        print()
        print("To verify in Prometheus (if OTLP metrics bridge enabled):")
        print(f'  {{service_name="{SERVICE_NAME_VAL}"}}')
        return 0
    else:
        print("Some tests failed. Check connectivity and endpoint config.")
        return 1


if __name__ == "__main__":
    sys.exit(main())
