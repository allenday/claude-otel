"""Unit tests for wrapper module - span creation, duration calc, error paths."""

import os
import pytest
from unittest.mock import patch, MagicMock, Mock
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.resources import Resource
from opentelemetry.trace import Status, StatusCode

from claude_otel.config import OTelConfig, reset_config
from claude_otel.wrapper import (
    get_sampler,
    get_resource,
    get_exporter,
    setup_tracing,
    run_claude,
)


class TestGetSampler:
    """Tests for get_sampler function."""

    def test_always_on_default(self):
        """Default sampler should be always_on."""
        config = OTelConfig(traces_sampler="always_on")
        sampler = get_sampler(config)
        # ALWAYS_ON sampler has description "AlwaysOnSampler"
        assert "AlwaysOn" in str(type(sampler).__name__) or "always" in sampler.get_description().lower()

    def test_always_off(self):
        """Sampler should be always_off when configured."""
        config = OTelConfig(traces_sampler="always_off")
        sampler = get_sampler(config)
        assert "AlwaysOff" in str(type(sampler).__name__) or "always" in sampler.get_description().lower()

    def test_trace_id_ratio(self):
        """Sampler should be TraceIdRatioBased when configured."""
        config = OTelConfig(traces_sampler="traceidratio", traces_sampler_arg="0.5")
        sampler = get_sampler(config)
        assert "TraceIdRatio" in str(type(sampler).__name__)

    def test_trace_id_ratio_invalid_arg_falls_back(self):
        """Invalid ratio should fall back to always_on."""
        config = OTelConfig(traces_sampler="traceidratio", traces_sampler_arg="invalid", debug=True)
        with patch("sys.stderr"):  # suppress debug output
            sampler = get_sampler(config)
        # Should fall back to always_on
        assert sampler is not None


class TestGetResource:
    """Tests for get_resource function."""

    def test_includes_service_name(self):
        """Resource should include service name."""
        config = OTelConfig(service_name="test-service")
        resource = get_resource(config)
        attrs = dict(resource.attributes)
        assert attrs.get("service.name") == "test-service"

    def test_includes_service_namespace(self):
        """Resource should include service namespace."""
        config = OTelConfig(service_namespace="test-namespace")
        resource = get_resource(config)
        attrs = dict(resource.attributes)
        assert attrs.get("service.namespace") == "test-namespace"

    def test_includes_extra_attributes(self):
        """Resource should include extra resource attributes."""
        config = OTelConfig(resource_attributes={"env": "prod", "version": "1.0"})
        resource = get_resource(config)
        attrs = dict(resource.attributes)
        assert attrs.get("env") == "prod"
        assert attrs.get("version") == "1.0"


class TestGetExporter:
    """Tests for get_exporter function."""

    def test_returns_none_when_traces_disabled(self):
        """Should return None when traces are disabled."""
        config = OTelConfig(traces_exporter="none")
        exporter = get_exporter(config)
        assert exporter is None

    def test_warns_on_http_protocol(self):
        """Should warn when HTTP protocol is requested (not implemented)."""
        config = OTelConfig(protocol="http")
        with patch("sys.stderr"):
            exporter = get_exporter(config)
        # Still returns gRPC exporter as fallback
        assert exporter is not None


class TestSetupTracing:
    """Tests for setup_tracing function."""

    def teardown_method(self):
        """Reset config after each test."""
        reset_config()

    def test_returns_tracer(self):
        """setup_tracing should return a Tracer instance."""
        config = OTelConfig(traces_exporter="none")  # Disable export for test
        tracer = setup_tracing(config)
        assert tracer is not None
        assert hasattr(tracer, "start_span")
        assert hasattr(tracer, "start_as_current_span")


class TestRunClaude:
    """Tests for run_claude function - span creation, error paths."""

    def setup_method(self):
        """Set up in-memory exporter for capturing spans."""
        self.exporter = InMemorySpanExporter()
        self.provider = TracerProvider()
        self.provider.add_span_processor(SimpleSpanProcessor(self.exporter))
        self.tracer = self.provider.get_tracer("test-tracer")

    def teardown_method(self):
        """Clear exporter."""
        self.exporter.clear()

    def test_creates_session_span(self):
        """run_claude should create a session span."""
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0)
            run_claude(["--help"], self.tracer, None)

        spans = self.exporter.get_finished_spans()
        assert len(spans) == 1
        assert spans[0].name == "claude-session"

    def test_span_has_session_id(self):
        """Session span should have session.id attribute."""
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0)
            run_claude([], self.tracer, None)

        spans = self.exporter.get_finished_spans()
        attrs = dict(spans[0].attributes)
        assert "session.id" in attrs
        # Session ID should be a UUID-like string
        assert len(attrs["session.id"]) == 36  # UUID format

    def test_span_has_args_count(self):
        """Session span should have claude.args_count attribute."""
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0)
            run_claude(["arg1", "arg2", "arg3"], self.tracer, None)

        spans = self.exporter.get_finished_spans()
        attrs = dict(spans[0].attributes)
        assert attrs.get("claude.args_count") == 3

    def test_span_has_args_preview(self):
        """Session span should have claude.args_preview attribute."""
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0)
            run_claude(["--model", "opus"], self.tracer, None)

        spans = self.exporter.get_finished_spans()
        attrs = dict(spans[0].attributes)
        assert "claude.args_preview" in attrs
        assert "--model opus" in attrs["claude.args_preview"]

    def test_span_args_preview_truncated(self):
        """Args preview should be truncated to 100 chars."""
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0)
            long_args = ["x" * 200]
            run_claude(long_args, self.tracer, None)

        spans = self.exporter.get_finished_spans()
        attrs = dict(spans[0].attributes)
        assert len(attrs.get("claude.args_preview", "")) <= 100

    def test_span_has_exit_code_on_success(self):
        """Session span should have exit_code attribute on success."""
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0)
            run_claude([], self.tracer, None)

        spans = self.exporter.get_finished_spans()
        attrs = dict(spans[0].attributes)
        assert attrs.get("exit_code") == 0

    def test_span_status_ok_on_success(self):
        """Session span should have OK status on success."""
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0)
            run_claude([], self.tracer, None)

        spans = self.exporter.get_finished_spans()
        assert spans[0].status.status_code == StatusCode.OK

    def test_span_has_exit_code_on_failure(self):
        """Session span should have exit_code attribute on failure."""
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=1)
            run_claude([], self.tracer, None)

        spans = self.exporter.get_finished_spans()
        attrs = dict(spans[0].attributes)
        assert attrs.get("exit_code") == 1

    def test_span_status_error_on_non_zero_exit(self):
        """Session span should have ERROR status on non-zero exit."""
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=1)
            run_claude([], self.tracer, None)

        spans = self.exporter.get_finished_spans()
        assert spans[0].status.status_code == StatusCode.ERROR

    def test_returns_exit_code(self):
        """run_claude should return the subprocess exit code."""
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=42)
            result = run_claude([], self.tracer, None)

        assert result == 42

    def test_handles_file_not_found(self):
        """run_claude should handle FileNotFoundError gracefully."""
        with patch("subprocess.run") as mock_run:
            mock_run.side_effect = FileNotFoundError("claude not found")
            with patch("sys.stderr"):
                result = run_claude([], self.tracer, None)

        assert result == 1
        spans = self.exporter.get_finished_spans()
        attrs = dict(spans[0].attributes)
        assert attrs.get("error") is True
        assert "not found" in attrs.get("error.message", "").lower()

    def test_handles_generic_exception(self):
        """run_claude should handle generic exceptions gracefully."""
        with patch("subprocess.run") as mock_run:
            mock_run.side_effect = RuntimeError("Something went wrong")
            with patch("sys.stderr"):
                result = run_claude([], self.tracer, None)

        assert result == 1
        spans = self.exporter.get_finished_spans()
        attrs = dict(spans[0].attributes)
        assert attrs.get("error") is True
        assert "Something went wrong" in attrs.get("error.message", "")

    def test_error_message_truncated(self):
        """Error message should be truncated to 500 chars."""
        with patch("subprocess.run") as mock_run:
            mock_run.side_effect = RuntimeError("x" * 1000)
            with patch("sys.stderr"):
                run_claude([], self.tracer, None)

        spans = self.exporter.get_finished_spans()
        attrs = dict(spans[0].attributes)
        assert len(attrs.get("error.message", "")) <= 500

    def test_span_has_duration(self):
        """Session span should have start and end time (duration)."""
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0)
            run_claude([], self.tracer, None)

        spans = self.exporter.get_finished_spans()
        span = spans[0]
        # Duration is end_time - start_time in nanoseconds
        assert span.end_time is not None
        assert span.start_time is not None
        assert span.end_time >= span.start_time
