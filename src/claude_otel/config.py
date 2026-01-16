"""Centralized OTEL configuration via environment variables.

Supported environment variables (per PRD):
  OTEL_EXPORTER_OTLP_ENDPOINT   - Collector endpoint (default: http://100.91.20.46:4317)
  OTEL_EXPORTER_OTLP_PROTOCOL   - Protocol: grpc or http (default: grpc)
  OTEL_SERVICE_NAME             - Service name (default: claude-cli)
  OTEL_SERVICE_NAMESPACE        - Service namespace (default: claude-otel)
  OTEL_RESOURCE_ATTRIBUTES      - Comma-separated key=value pairs
  OTEL_TRACES_EXPORTER          - Exporter type: otlp or none (default: otlp)
  OTEL_LOGS_EXPORTER            - Exporter type: otlp or none (default: otlp)
  OTEL_METRICS_EXPORTER         - Exporter type: otlp or none (default: none)
  OTEL_TRACES_SAMPLER           - Sampler: always_on, always_off, traceidratio (default: always_on)
  OTEL_TRACES_SAMPLER_ARG       - Sampler argument (e.g., ratio for traceidratio)
  CLAUDE_OTEL_DEBUG             - Enable debug logging (default: false)
"""

import os
from dataclasses import dataclass, field
from typing import Optional


# Default bastion collector endpoint
DEFAULT_ENDPOINT = "http://100.91.20.46:4317"
DEFAULT_PROTOCOL = "grpc"
DEFAULT_SERVICE_NAME = "claude-cli"
DEFAULT_SERVICE_NAMESPACE = "claude-otel"


@dataclass
class OTelConfig:
    """Parsed OTEL configuration from environment."""

    # Endpoint configuration
    endpoint: str = DEFAULT_ENDPOINT
    protocol: str = DEFAULT_PROTOCOL

    # Resource attributes
    service_name: str = DEFAULT_SERVICE_NAME
    service_namespace: str = DEFAULT_SERVICE_NAMESPACE
    resource_attributes: dict = field(default_factory=dict)

    # Exporter toggles
    traces_exporter: str = "otlp"
    logs_exporter: str = "otlp"
    metrics_exporter: str = "none"

    # Sampler configuration
    traces_sampler: str = "always_on"
    traces_sampler_arg: Optional[str] = None

    # Debug mode
    debug: bool = False

    @property
    def traces_enabled(self) -> bool:
        """Check if trace export is enabled."""
        return self.traces_exporter.lower() != "none"

    @property
    def logs_enabled(self) -> bool:
        """Check if log export is enabled."""
        return self.logs_exporter.lower() != "none"

    @property
    def metrics_enabled(self) -> bool:
        """Check if metrics export is enabled."""
        return self.metrics_exporter.lower() != "none"

    @property
    def is_grpc(self) -> bool:
        """Check if using gRPC protocol."""
        return self.protocol.lower() == "grpc"

    @property
    def grpc_endpoint(self) -> str:
        """Get endpoint formatted for gRPC (strips http:// prefix if present)."""
        ep = self.endpoint
        if ep.startswith("http://"):
            ep = ep[7:]
        elif ep.startswith("https://"):
            ep = ep[8:]
        return ep

    @property
    def http_endpoint(self) -> str:
        """Get endpoint formatted for HTTP (ensures http:// prefix)."""
        if not self.endpoint.startswith(("http://", "https://")):
            return f"http://{self.endpoint}"
        return self.endpoint


def parse_resource_attributes(attr_string: str) -> dict:
    """Parse OTEL_RESOURCE_ATTRIBUTES format: key1=val1,key2=val2."""
    attrs = {}
    if not attr_string:
        return attrs

    for pair in attr_string.split(","):
        pair = pair.strip()
        if "=" in pair:
            key, value = pair.split("=", 1)
            attrs[key.strip()] = value.strip()

    return attrs


def load_config() -> OTelConfig:
    """Load OTEL configuration from environment variables."""
    debug_val = os.environ.get("CLAUDE_OTEL_DEBUG", "").lower()

    return OTelConfig(
        endpoint=os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT", DEFAULT_ENDPOINT),
        protocol=os.environ.get("OTEL_EXPORTER_OTLP_PROTOCOL", DEFAULT_PROTOCOL),
        service_name=os.environ.get("OTEL_SERVICE_NAME", DEFAULT_SERVICE_NAME),
        service_namespace=os.environ.get("OTEL_SERVICE_NAMESPACE", DEFAULT_SERVICE_NAMESPACE),
        resource_attributes=parse_resource_attributes(
            os.environ.get("OTEL_RESOURCE_ATTRIBUTES", "")
        ),
        traces_exporter=os.environ.get("OTEL_TRACES_EXPORTER", "otlp"),
        logs_exporter=os.environ.get("OTEL_LOGS_EXPORTER", "otlp"),
        metrics_exporter=os.environ.get("OTEL_METRICS_EXPORTER", "none"),
        traces_sampler=os.environ.get("OTEL_TRACES_SAMPLER", "always_on"),
        traces_sampler_arg=os.environ.get("OTEL_TRACES_SAMPLER_ARG"),
        debug=debug_val in ("1", "true", "yes"),
    )


# Singleton config instance (lazy-loaded)
_config: Optional[OTelConfig] = None


def get_config() -> OTelConfig:
    """Get the current OTEL configuration (singleton)."""
    global _config
    if _config is None:
        _config = load_config()
    return _config


def reset_config() -> None:
    """Reset config singleton (useful for testing)."""
    global _config
    _config = None
