"""Tests for backend-specific adapters."""

import os
import pytest
from unittest.mock import MagicMock, patch

from claude_otel.backends import (
    detect_backend,
    configure_logfire,
    configure_sentry,
    get_logfire,
    get_sentry,
)


class TestBackendDetection:
    """Test backend auto-detection logic."""

    def test_detect_logfire(self, monkeypatch):
        """Test Logfire detection when LOGFIRE_TOKEN is set."""
        monkeypatch.setenv("LOGFIRE_TOKEN", "test-token")
        assert detect_backend() == "logfire"

    def test_detect_sentry(self, monkeypatch):
        """Test Sentry detection when SENTRY_DSN is set."""
        monkeypatch.setenv("SENTRY_DSN", "https://test@sentry.io/123")
        assert detect_backend() == "sentry"

    def test_detect_logfire_priority(self, monkeypatch):
        """Test Logfire takes priority over Sentry when both are set."""
        monkeypatch.setenv("LOGFIRE_TOKEN", "test-token")
        monkeypatch.setenv("SENTRY_DSN", "https://test@sentry.io/123")
        assert detect_backend() == "logfire"

    def test_detect_none(self):
        """Test no backend detected when neither is set."""
        # Ensure env vars are not set
        os.environ.pop("LOGFIRE_TOKEN", None)
        os.environ.pop("SENTRY_DSN", None)
        assert detect_backend() is None


class TestLogfireAdapter:
    """Test Logfire backend adapter."""

    def test_configure_logfire_missing_token(self):
        """Test Logfire configuration fails without token."""
        os.environ.pop("LOGFIRE_TOKEN", None)
        with pytest.raises(ValueError, match="LOGFIRE_TOKEN"):
            configure_logfire()

    def test_configure_logfire_missing_package(self, monkeypatch):
        """Test Logfire configuration fails without package installed."""
        monkeypatch.setenv("LOGFIRE_TOKEN", "test-token")

        # Mock builtins.__import__ to raise ImportError for logfire
        import builtins
        real_import = builtins.__import__

        def mock_import(name, *args, **kwargs):
            if name == "logfire":
                raise ImportError("No module named 'logfire'")
            return real_import(name, *args, **kwargs)

        with patch("builtins.__import__", side_effect=mock_import):
            with pytest.raises(RuntimeError, match="logfire package not installed"):
                configure_logfire()

    @patch("claude_otel.backends.trace.get_tracer_provider")
    def test_configure_logfire_success(self, mock_get_provider, monkeypatch):
        """Test successful Logfire configuration."""
        monkeypatch.setenv("LOGFIRE_TOKEN", "test-token")
        mock_provider = MagicMock()
        mock_get_provider.return_value = mock_provider

        # Mock the logfire module
        mock_logfire = MagicMock()
        with patch.dict("sys.modules", {"logfire": mock_logfire}):
            result = configure_logfire("test-service")

            mock_logfire.configure.assert_called_once_with(
                service_name="test-service",
                send_to_logfire=True,
            )
            assert result == mock_provider

    def test_get_logfire_not_imported(self):
        """Test get_logfire returns None when not imported."""
        # Ensure logfire is not in sys.modules
        import sys
        sys.modules.pop("logfire", None)
        assert get_logfire() is None


class TestSentryAdapter:
    """Test Sentry backend adapter."""

    def test_configure_sentry_missing_dsn(self):
        """Test Sentry configuration fails without DSN."""
        os.environ.pop("SENTRY_DSN", None)
        with pytest.raises(ValueError, match="SENTRY_DSN"):
            configure_sentry()

    def test_configure_sentry_missing_package(self, monkeypatch):
        """Test Sentry configuration fails without package installed."""
        monkeypatch.setenv("SENTRY_DSN", "https://test@sentry.io/123")

        # Mock builtins.__import__ to raise ImportError for sentry_sdk
        import builtins
        real_import = builtins.__import__

        def mock_import(name, *args, **kwargs):
            if name == "sentry_sdk":
                raise ImportError("No module named 'sentry_sdk'")
            return real_import(name, *args, **kwargs)

        with patch("builtins.__import__", side_effect=mock_import):
            with pytest.raises(RuntimeError, match="sentry-sdk package not installed"):
                configure_sentry()

    @patch("claude_otel.backends.trace.set_tracer_provider")
    def test_configure_sentry_success(self, mock_set_provider, monkeypatch):
        """Test successful Sentry configuration."""
        monkeypatch.setenv("SENTRY_DSN", "https://test@sentry.io/123")
        monkeypatch.setenv("SENTRY_ENVIRONMENT", "test")
        monkeypatch.setenv("SENTRY_TRACES_SAMPLE_RATE", "0.5")

        # Mock the sentry_sdk module and its integrations
        mock_sentry_sdk = MagicMock()
        mock_span_processor = MagicMock()
        mock_logging_integration = MagicMock()

        with patch.dict(
            "sys.modules",
            {
                "sentry_sdk": mock_sentry_sdk,
                "sentry_sdk.integrations.opentelemetry": MagicMock(
                    SentrySpanProcessor=mock_span_processor
                ),
                "sentry_sdk.integrations.logging": MagicMock(
                    LoggingIntegration=mock_logging_integration
                ),
            },
        ):
            result = configure_sentry("test-service")

            # Verify Sentry SDK initialized
            mock_sentry_sdk.init.assert_called_once()
            init_kwargs = mock_sentry_sdk.init.call_args[1]
            assert init_kwargs["dsn"] == "https://test@sentry.io/123"
            assert init_kwargs["environment"] == "test"
            assert init_kwargs["traces_sample_rate"] == 0.5
            assert init_kwargs["send_default_pii"] is False
            assert init_kwargs["enable_tracing"] is True

            # Verify TracerProvider created and configured
            assert result is not None
            mock_set_provider.assert_called_once()

    @patch("claude_otel.backends.trace.set_tracer_provider")
    def test_configure_sentry_defaults(self, mock_set_provider, monkeypatch):
        """Test Sentry configuration with default values."""
        monkeypatch.setenv("SENTRY_DSN", "https://test@sentry.io/123")

        # Mock the sentry_sdk module and its integrations
        mock_sentry_sdk = MagicMock()
        mock_span_processor = MagicMock()
        mock_logging_integration = MagicMock()

        with patch.dict(
            "sys.modules",
            {
                "sentry_sdk": mock_sentry_sdk,
                "sentry_sdk.integrations.opentelemetry": MagicMock(
                    SentrySpanProcessor=mock_span_processor
                ),
                "sentry_sdk.integrations.logging": MagicMock(
                    LoggingIntegration=mock_logging_integration
                ),
            },
        ):
            result = configure_sentry()

            init_kwargs = mock_sentry_sdk.init.call_args[1]
            assert init_kwargs["environment"] == "production"
            assert init_kwargs["traces_sample_rate"] == 1.0

    def test_get_sentry_not_imported(self):
        """Test get_sentry returns None when not imported."""
        import sys
        sys.modules.pop("sentry_sdk", None)
        assert get_sentry() is None


class TestBackendIntegration:
    """Test backend integration with exporter."""

    @patch("claude_otel.backends.configure_logfire")
    @patch("claude_otel.backends.detect_backend")
    def test_exporter_uses_logfire(self, mock_detect, mock_configure, monkeypatch):
        """Test exporter uses Logfire when detected."""
        from claude_otel.exporter import configure_exporters, shutdown_telemetry

        # Clean up any existing config
        shutdown_telemetry()

        mock_detect.return_value = "logfire"
        mock_provider = MagicMock()
        mock_configure.return_value = mock_provider

        monkeypatch.setenv("OTEL_SERVICE_NAME", "test-service")

        tracer_provider, logger_provider = configure_exporters()

        mock_configure.assert_called_once_with("test-service")
        assert tracer_provider == mock_provider

        # Clean up
        shutdown_telemetry()

    @patch("claude_otel.backends.configure_sentry")
    @patch("claude_otel.backends.detect_backend")
    def test_exporter_uses_sentry(self, mock_detect, mock_configure, monkeypatch):
        """Test exporter uses Sentry when detected."""
        from claude_otel.exporter import configure_exporters, shutdown_telemetry

        # Clean up any existing config
        shutdown_telemetry()

        mock_detect.return_value = "sentry"
        mock_provider = MagicMock()
        mock_configure.return_value = mock_provider

        monkeypatch.setenv("OTEL_SERVICE_NAME", "test-service")

        tracer_provider, logger_provider = configure_exporters()

        mock_configure.assert_called_once_with("test-service")
        assert tracer_provider == mock_provider

        # Clean up
        shutdown_telemetry()

    @patch("claude_otel.backends.detect_backend")
    def test_exporter_fallback_to_otlp(self, mock_detect, monkeypatch):
        """Test exporter falls back to OTLP when no backend detected."""
        from claude_otel.exporter import configure_exporters, shutdown_telemetry

        # Clean up any existing config
        shutdown_telemetry()

        mock_detect.return_value = None
        monkeypatch.setenv("OTEL_TRACES_EXPORTER", "otlp")

        tracer_provider, logger_provider = configure_exporters()

        # Should get standard OTLP providers
        assert tracer_provider is not None

        # Clean up
        shutdown_telemetry()

    @patch("claude_otel.backends.configure_logfire")
    @patch("claude_otel.backends.detect_backend")
    def test_exporter_fallback_on_backend_error(
        self, mock_detect, mock_configure, monkeypatch
    ):
        """Test exporter falls back to OTLP if backend configuration fails."""
        from claude_otel.exporter import configure_exporters, shutdown_telemetry

        # Clean up any existing config
        shutdown_telemetry()

        mock_detect.return_value = "logfire"
        mock_configure.side_effect = RuntimeError("Backend config failed")

        monkeypatch.setenv("OTEL_TRACES_EXPORTER", "otlp")

        tracer_provider, logger_provider = configure_exporters()

        # Should fall back to standard OTLP
        assert tracer_provider is not None

        # Clean up
        shutdown_telemetry()
