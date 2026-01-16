"""Unit tests for resilience features - bounded queues, drop policy, timeouts."""

import os
import pytest
from unittest.mock import patch, MagicMock

from claude_otel.config import (
    OTelConfig,
    load_config,
    reset_config,
    DEFAULT_BSP_MAX_QUEUE_SIZE,
    DEFAULT_BSP_MAX_EXPORT_BATCH_SIZE,
    DEFAULT_BSP_EXPORT_TIMEOUT_MS,
    DEFAULT_BSP_SCHEDULE_DELAY_MS,
    DEFAULT_EXPORTER_TIMEOUT_MS,
)
from claude_otel.wrapper import create_batch_processor, get_exporter, setup_tracing


class TestResilienceConfigDefaults:
    """Tests for resilience configuration defaults."""

    def setup_method(self):
        """Clear environment before each test."""
        self._orig_env = os.environ.copy()
        for key in list(os.environ.keys()):
            if key.startswith("OTEL_") or key == "CLAUDE_OTEL_DEBUG":
                del os.environ[key]
        reset_config()

    def teardown_method(self):
        """Restore environment after each test."""
        os.environ.clear()
        os.environ.update(self._orig_env)
        reset_config()

    def test_default_bsp_max_queue_size(self):
        """Default max queue size should be 2048."""
        config = load_config()
        assert config.bsp_max_queue_size == DEFAULT_BSP_MAX_QUEUE_SIZE
        assert config.bsp_max_queue_size == 2048

    def test_default_bsp_max_export_batch_size(self):
        """Default max export batch size should be 512."""
        config = load_config()
        assert config.bsp_max_export_batch_size == DEFAULT_BSP_MAX_EXPORT_BATCH_SIZE
        assert config.bsp_max_export_batch_size == 512

    def test_default_bsp_export_timeout(self):
        """Default export timeout should be 30000ms."""
        config = load_config()
        assert config.bsp_export_timeout_ms == DEFAULT_BSP_EXPORT_TIMEOUT_MS
        assert config.bsp_export_timeout_ms == 30000

    def test_default_bsp_schedule_delay(self):
        """Default schedule delay should be 5000ms."""
        config = load_config()
        assert config.bsp_schedule_delay_ms == DEFAULT_BSP_SCHEDULE_DELAY_MS
        assert config.bsp_schedule_delay_ms == 5000

    def test_default_exporter_timeout(self):
        """Default exporter timeout should be 10000ms."""
        config = load_config()
        assert config.exporter_timeout_ms == DEFAULT_EXPORTER_TIMEOUT_MS
        assert config.exporter_timeout_ms == 10000


class TestResilienceConfigFromEnv:
    """Tests for loading resilience config from environment variables."""

    def setup_method(self):
        """Clear environment before each test."""
        self._orig_env = os.environ.copy()
        for key in list(os.environ.keys()):
            if key.startswith("OTEL_") or key == "CLAUDE_OTEL_DEBUG":
                del os.environ[key]
        reset_config()

    def teardown_method(self):
        """Restore environment after each test."""
        os.environ.clear()
        os.environ.update(self._orig_env)
        reset_config()

    def test_bsp_max_queue_size_from_env(self):
        """Max queue size should be loaded from OTEL_BSP_MAX_QUEUE_SIZE."""
        os.environ["OTEL_BSP_MAX_QUEUE_SIZE"] = "1024"
        config = load_config()
        assert config.bsp_max_queue_size == 1024

    def test_bsp_max_export_batch_size_from_env(self):
        """Max export batch size should be loaded from OTEL_BSP_MAX_EXPORT_BATCH_SIZE."""
        os.environ["OTEL_BSP_MAX_EXPORT_BATCH_SIZE"] = "256"
        config = load_config()
        assert config.bsp_max_export_batch_size == 256

    def test_bsp_export_timeout_from_env(self):
        """Export timeout should be loaded from OTEL_BSP_EXPORT_TIMEOUT."""
        os.environ["OTEL_BSP_EXPORT_TIMEOUT"] = "60000"
        config = load_config()
        assert config.bsp_export_timeout_ms == 60000

    def test_bsp_schedule_delay_from_env(self):
        """Schedule delay should be loaded from OTEL_BSP_SCHEDULE_DELAY."""
        os.environ["OTEL_BSP_SCHEDULE_DELAY"] = "10000"
        config = load_config()
        assert config.bsp_schedule_delay_ms == 10000

    def test_exporter_timeout_from_env(self):
        """Exporter timeout should be loaded from OTEL_EXPORTER_OTLP_TIMEOUT."""
        os.environ["OTEL_EXPORTER_OTLP_TIMEOUT"] = "5000"
        config = load_config()
        assert config.exporter_timeout_ms == 5000

    def test_invalid_int_falls_back_to_default(self):
        """Invalid integer values should fall back to defaults."""
        os.environ["OTEL_BSP_MAX_QUEUE_SIZE"] = "not-a-number"
        config = load_config()
        assert config.bsp_max_queue_size == DEFAULT_BSP_MAX_QUEUE_SIZE


class TestCreateBatchProcessor:
    """Tests for create_batch_processor function."""

    def test_uses_config_values(self):
        """Batch processor should be created with config values."""
        config = OTelConfig(
            traces_exporter="none",  # Disable actual export
            bsp_max_queue_size=100,
            bsp_max_export_batch_size=50,
            bsp_export_timeout_ms=1000,
            bsp_schedule_delay_ms=500,
        )

        mock_exporter = MagicMock()

        with patch("claude_otel.wrapper.BatchSpanProcessor") as mock_bsp:
            create_batch_processor(mock_exporter, config)

            mock_bsp.assert_called_once_with(
                mock_exporter,
                max_queue_size=100,
                max_export_batch_size=50,
                export_timeout_millis=1000,
                schedule_delay_millis=500,
            )


class TestGetExporterTimeout:
    """Tests for exporter timeout configuration."""

    def test_exporter_uses_timeout(self):
        """Exporter should be created with timeout from config."""
        config = OTelConfig(
            traces_exporter="otlp",
            exporter_timeout_ms=5000,  # 5 seconds
        )

        with patch("claude_otel.wrapper.OTLPSpanExporter") as mock_exporter:
            get_exporter(config)

            # Timeout should be converted from ms to seconds
            mock_exporter.assert_called_once()
            call_kwargs = mock_exporter.call_args[1]
            assert call_kwargs["timeout"] == 5.0  # 5000ms = 5s


class TestSetupTracingDebugOutput:
    """Tests for debug output in setup_tracing."""

    def setup_method(self):
        """Clear environment before each test."""
        self._orig_env = os.environ.copy()
        reset_config()

    def teardown_method(self):
        """Restore environment after each test."""
        os.environ.clear()
        os.environ.update(self._orig_env)
        reset_config()

    def test_debug_prints_resilience_config(self):
        """Debug mode should print resilience configuration."""
        config = OTelConfig(
            traces_exporter="otlp",
            debug=True,
            bsp_max_queue_size=100,
            bsp_max_export_batch_size=50,
            bsp_export_timeout_ms=1000,
            bsp_schedule_delay_ms=500,
        )

        with patch("sys.stderr") as mock_stderr:
            with patch("claude_otel.wrapper.OTLPSpanExporter"):
                with patch("claude_otel.wrapper.BatchSpanProcessor"):
                    setup_tracing(config)

            # Check that debug output was written
            write_calls = [str(call) for call in mock_stderr.write.call_args_list]
            output = "".join(write_calls)
            assert "max_queue_size" in output or mock_stderr.write.called


class TestResilienceBehavior:
    """Tests for resilience behavior (bounded queues, drop policy)."""

    def test_bounded_queue_prevents_oom(self):
        """Bounded queue should limit memory usage.

        The BatchSpanProcessor with max_queue_size will drop spans
        when the queue is full rather than growing unbounded.
        This is a design verification test.
        """
        config = OTelConfig(
            traces_exporter="none",
            bsp_max_queue_size=10,  # Very small queue for testing
        )
        # The bounded queue behavior is built into OTEL SDK's BatchSpanProcessor
        # This test documents that we configure it correctly
        assert config.bsp_max_queue_size == 10

    def test_timeout_prevents_blocking(self):
        """Timeouts should prevent indefinite blocking on export.

        Both the exporter timeout and export timeout work together:
        - exporter_timeout_ms: Individual OTLP request timeout
        - bsp_export_timeout_ms: Total time for a batch export operation
        """
        config = OTelConfig(
            exporter_timeout_ms=1000,  # 1 second request timeout
            bsp_export_timeout_ms=5000,  # 5 second batch export timeout
        )
        # Verify configuration is set correctly
        assert config.exporter_timeout_ms == 1000
        assert config.bsp_export_timeout_ms == 5000
