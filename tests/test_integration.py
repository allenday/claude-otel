"""Integration tests - send dummy span/log to the OTLP endpoint.

These tests verify that the OTEL exporters can successfully connect
and send data to the collector (default localhost:4317).

To run these tests, ensure you have network connectivity to the collector.
Tests are marked with @pytest.mark.integration for selective running.

Usage:
    # Run only integration tests
    pytest tests/test_integration.py -v -m integration

    # Skip integration tests in normal runs
    pytest tests/ -v -m "not integration"
"""

import os
import time
import uuid
import logging
import pytest

from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor, SimpleSpanProcessor
from opentelemetry.sdk.resources import Resource, SERVICE_NAME, SERVICE_NAMESPACE
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.trace import Status, StatusCode

from claude_otel.config import get_config, reset_config, load_config


# Mark all tests in this module as integration tests
pytestmark = pytest.mark.integration


# Collector endpoint from PRD (override via env for real runs)
COLLECTOR_ENDPOINT = os.environ.get("OTEL_TEST_COLLECTOR", "http://localhost:4317")


@pytest.fixture
def integration_tracer():
    """Create a tracer configured to send to the collector."""
    resource = Resource.create({
        SERVICE_NAME: "claude-otel-test",
        SERVICE_NAMESPACE: "claude-otel-integration",
        "test.run_id": str(uuid.uuid4()),
    })

    provider = TracerProvider(resource=resource)

    try:
        exporter = OTLPSpanExporter(endpoint=COLLECTOR_ENDPOINT, insecure=True)
        # Use SimpleSpanProcessor for immediate export in tests
        provider.add_span_processor(SimpleSpanProcessor(exporter))
    except Exception as e:
        pytest.skip(f"Could not connect to collector: {e}")

    tracer = provider.get_tracer("integration-test", "0.1.0")

    yield tracer

    # Shutdown provider to flush spans
    provider.shutdown()


class TestCollectorConnectivity:
    """Tests for connectivity to OTLP endpoint."""

    def test_can_send_simple_span(self, integration_tracer):
        """Verify we can send a simple span to the collector."""
        test_id = str(uuid.uuid4())

        with integration_tracer.start_as_current_span("integration-test-span") as span:
            span.set_attribute("test.id", test_id)
            span.set_attribute("test.type", "simple_span")
            span.set_status(Status(StatusCode.OK))

        # If we get here without exception, the span was accepted
        # (actual verification in Loki would require querying the collector)

    def test_can_send_span_with_attributes(self, integration_tracer):
        """Verify we can send a span with various attribute types."""
        test_id = str(uuid.uuid4())

        with integration_tracer.start_as_current_span("integration-test-attributes") as span:
            span.set_attribute("test.id", test_id)
            span.set_attribute("test.string", "hello world")
            span.set_attribute("test.int", 42)
            span.set_attribute("test.float", 3.14)
            span.set_attribute("test.bool", True)
            span.set_status(Status(StatusCode.OK))

    def test_can_send_span_with_error(self, integration_tracer):
        """Verify we can send a span with error status."""
        test_id = str(uuid.uuid4())

        with integration_tracer.start_as_current_span("integration-test-error") as span:
            span.set_attribute("test.id", test_id)
            span.set_attribute("error", True)
            span.set_attribute("error.message", "Test error for integration")
            span.set_status(Status(StatusCode.ERROR, "Simulated error"))

    def test_can_send_nested_spans(self, integration_tracer):
        """Verify we can send nested spans (parent-child relationship)."""
        test_id = str(uuid.uuid4())

        with integration_tracer.start_as_current_span("integration-parent") as parent:
            parent.set_attribute("test.id", test_id)
            parent.set_attribute("test.type", "parent")

            with integration_tracer.start_as_current_span("integration-child") as child:
                child.set_attribute("test.id", test_id)
                child.set_attribute("test.type", "child")
                child.set_status(Status(StatusCode.OK))

            parent.set_status(Status(StatusCode.OK))

    def test_can_send_span_simulating_tool_call(self, integration_tracer):
        """Verify we can send a span simulating a Claude tool call."""
        test_id = str(uuid.uuid4())
        session_id = str(uuid.uuid4())

        with integration_tracer.start_as_current_span("claude-session") as session:
            session.set_attribute("test.id", test_id)
            session.set_attribute("session.id", session_id)
            session.set_attribute("claude.args_count", 2)
            session.set_attribute("claude.args_preview", "--model opus")

            # Simulate a tool call span (child of session)
            with integration_tracer.start_as_current_span("tool-call") as tool:
                tool.set_attribute("tool.name", "Bash")
                tool.set_attribute("tool.input_summary", "git status")
                tool.set_attribute("duration_ms", 150)
                tool.set_attribute("exit_code", 0)
                tool.set_attribute("stdout_bytes", 256)
                tool.set_attribute("stderr_bytes", 0)
                tool.set_attribute("truncated", False)
                tool.set_status(Status(StatusCode.OK))

            session.set_attribute("exit_code", 0)
            session.set_status(Status(StatusCode.OK))


class TestConfigIntegration:
    """Tests that config correctly targets the collector endpoint."""

    def setup_method(self):
        """Reset config before each test."""
        reset_config()

    def teardown_method(self):
        """Reset config after each test."""
        reset_config()

    def test_default_endpoint_is_localhost(self):
        """Default endpoint should be the localhost collector."""
        config = load_config()
        assert "localhost" in config.endpoint
        assert "4317" in config.endpoint

    def test_default_protocol_is_grpc(self):
        """Default protocol should be gRPC."""
        config = load_config()
        assert config.is_grpc is True
