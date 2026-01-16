"""Unit tests for config module."""

import os
import pytest

from claude_otel.config import (
    OTelConfig,
    parse_resource_attributes,
    load_config,
    get_config,
    reset_config,
    DEFAULT_ENDPOINT,
    DEFAULT_PROTOCOL,
    DEFAULT_SERVICE_NAME,
    DEFAULT_SERVICE_NAMESPACE,
)


class TestParseResourceAttributes:
    """Tests for parse_resource_attributes function."""

    def test_empty_string(self):
        """Empty string should return empty dict."""
        assert parse_resource_attributes("") == {}

    def test_none_like_empty(self):
        """None-ish values should return empty dict."""
        assert parse_resource_attributes(None) == {}

    def test_single_pair(self):
        """Single key=value pair should parse correctly."""
        result = parse_resource_attributes("key1=value1")
        assert result == {"key1": "value1"}

    def test_multiple_pairs(self):
        """Multiple comma-separated pairs should parse correctly."""
        result = parse_resource_attributes("key1=value1,key2=value2")
        assert result == {"key1": "value1", "key2": "value2"}

    def test_whitespace_handling(self):
        """Whitespace around keys/values should be stripped."""
        result = parse_resource_attributes("  key1 = value1 , key2=value2  ")
        assert result == {"key1": "value1", "key2": "value2"}

    def test_value_with_equals(self):
        """Value containing equals sign should be preserved."""
        result = parse_resource_attributes("key1=val=ue")
        assert result == {"key1": "val=ue"}

    def test_missing_value(self):
        """Pair without equals sign should be ignored."""
        result = parse_resource_attributes("key1=value1,badpair,key2=value2")
        assert result == {"key1": "value1", "key2": "value2"}


class TestOTelConfigProperties:
    """Tests for OTelConfig dataclass properties."""

    def test_traces_enabled_default(self):
        """Traces should be enabled by default (otlp exporter)."""
        config = OTelConfig()
        assert config.traces_enabled is True

    def test_traces_disabled(self):
        """Traces should be disabled when exporter is 'none'."""
        config = OTelConfig(traces_exporter="none")
        assert config.traces_enabled is False

    def test_traces_disabled_case_insensitive(self):
        """Exporter check should be case insensitive."""
        config = OTelConfig(traces_exporter="NONE")
        assert config.traces_enabled is False

    def test_logs_enabled_default(self):
        """Logs should be enabled by default."""
        config = OTelConfig()
        assert config.logs_enabled is True

    def test_logs_disabled(self):
        """Logs should be disabled when exporter is 'none'."""
        config = OTelConfig(logs_exporter="none")
        assert config.logs_enabled is False

    def test_metrics_disabled_default(self):
        """Metrics should be disabled by default."""
        config = OTelConfig()
        assert config.metrics_enabled is False

    def test_metrics_enabled(self):
        """Metrics should be enabled when exporter is 'otlp'."""
        config = OTelConfig(metrics_exporter="otlp")
        assert config.metrics_enabled is True

    def test_is_grpc_default(self):
        """Default protocol should be grpc."""
        config = OTelConfig()
        assert config.is_grpc is True

    def test_is_grpc_false_for_http(self):
        """is_grpc should be False for http protocol."""
        config = OTelConfig(protocol="http")
        assert config.is_grpc is False

    def test_grpc_endpoint_strips_http(self):
        """grpc_endpoint should strip http:// prefix."""
        config = OTelConfig(endpoint="http://localhost:4317")
        assert config.grpc_endpoint == "localhost:4317"

    def test_grpc_endpoint_strips_https(self):
        """grpc_endpoint should strip https:// prefix."""
        config = OTelConfig(endpoint="https://localhost:4317")
        assert config.grpc_endpoint == "localhost:4317"

    def test_grpc_endpoint_no_prefix(self):
        """grpc_endpoint should pass through endpoint without prefix."""
        config = OTelConfig(endpoint="localhost:4317")
        assert config.grpc_endpoint == "localhost:4317"

    def test_http_endpoint_adds_prefix(self):
        """http_endpoint should add http:// prefix if missing."""
        config = OTelConfig(endpoint="localhost:4318")
        assert config.http_endpoint == "http://localhost:4318"

    def test_http_endpoint_preserves_http(self):
        """http_endpoint should preserve existing http:// prefix."""
        config = OTelConfig(endpoint="http://localhost:4318")
        assert config.http_endpoint == "http://localhost:4318"

    def test_http_endpoint_preserves_https(self):
        """http_endpoint should preserve existing https:// prefix."""
        config = OTelConfig(endpoint="https://localhost:4318")
        assert config.http_endpoint == "https://localhost:4318"


class TestLoadConfig:
    """Tests for load_config function."""

    def setup_method(self):
        """Clear environment before each test."""
        self._orig_env = os.environ.copy()
        # Clear all OTEL vars
        for key in list(os.environ.keys()):
            if key.startswith("OTEL_") or key == "CLAUDE_OTEL_DEBUG":
                del os.environ[key]
        reset_config()

    def teardown_method(self):
        """Restore environment after each test."""
        os.environ.clear()
        os.environ.update(self._orig_env)
        reset_config()

    def test_default_values(self):
        """Config should have correct defaults when no env vars set."""
        config = load_config()
        assert config.endpoint == DEFAULT_ENDPOINT
        assert config.protocol == DEFAULT_PROTOCOL
        assert config.service_name == DEFAULT_SERVICE_NAME
        assert config.service_namespace == DEFAULT_SERVICE_NAMESPACE
        assert config.traces_exporter == "otlp"
        assert config.logs_exporter == "otlp"
        assert config.metrics_exporter == "none"
        assert config.traces_sampler == "always_on"
        assert config.traces_sampler_arg is None
        assert config.debug is False

    def test_endpoint_from_env(self):
        """Endpoint should be loaded from OTEL_EXPORTER_OTLP_ENDPOINT."""
        os.environ["OTEL_EXPORTER_OTLP_ENDPOINT"] = "http://custom:9999"
        config = load_config()
        assert config.endpoint == "http://custom:9999"

    def test_protocol_from_env(self):
        """Protocol should be loaded from OTEL_EXPORTER_OTLP_PROTOCOL."""
        os.environ["OTEL_EXPORTER_OTLP_PROTOCOL"] = "http"
        config = load_config()
        assert config.protocol == "http"

    def test_service_name_from_env(self):
        """Service name should be loaded from OTEL_SERVICE_NAME."""
        os.environ["OTEL_SERVICE_NAME"] = "my-service"
        config = load_config()
        assert config.service_name == "my-service"

    def test_resource_attributes_from_env(self):
        """Resource attributes should be parsed from OTEL_RESOURCE_ATTRIBUTES."""
        os.environ["OTEL_RESOURCE_ATTRIBUTES"] = "env=prod,version=1.0"
        config = load_config()
        assert config.resource_attributes == {"env": "prod", "version": "1.0"}

    def test_traces_sampler_from_env(self):
        """Traces sampler should be loaded from OTEL_TRACES_SAMPLER."""
        os.environ["OTEL_TRACES_SAMPLER"] = "always_off"
        config = load_config()
        assert config.traces_sampler == "always_off"

    def test_traces_sampler_arg_from_env(self):
        """Sampler arg should be loaded from OTEL_TRACES_SAMPLER_ARG."""
        os.environ["OTEL_TRACES_SAMPLER_ARG"] = "0.5"
        config = load_config()
        assert config.traces_sampler_arg == "0.5"

    def test_debug_true_values(self):
        """Debug should be True for '1', 'true', 'yes'."""
        for val in ("1", "true", "yes", "TRUE", "Yes"):
            os.environ["CLAUDE_OTEL_DEBUG"] = val
            reset_config()
            config = load_config()
            assert config.debug is True, f"Failed for value: {val}"

    def test_debug_false_values(self):
        """Debug should be False for other values."""
        for val in ("0", "false", "no", ""):
            os.environ["CLAUDE_OTEL_DEBUG"] = val
            reset_config()
            config = load_config()
            assert config.debug is False, f"Failed for value: {val}"


class TestGetConfigSingleton:
    """Tests for get_config singleton behavior."""

    def setup_method(self):
        """Clear environment and reset singleton before each test."""
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

    def test_returns_same_instance(self):
        """get_config should return the same instance on repeated calls."""
        config1 = get_config()
        config2 = get_config()
        assert config1 is config2

    def test_reset_clears_singleton(self):
        """reset_config should allow a new instance to be created."""
        config1 = get_config()
        reset_config()
        os.environ["OTEL_SERVICE_NAME"] = "new-service"
        config2 = get_config()
        assert config1 is not config2
        assert config2.service_name == "new-service"
