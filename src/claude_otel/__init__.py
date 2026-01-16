"""OTEL telemetry wrapper for Claude CLI."""

from claude_otel.exporter import (
    configure_exporters,
    get_tracer,
    get_logger_provider,
    shutdown_telemetry,
)
from claude_otel.pii import (
    truncate,
    truncate_bytes,
    redact,
    sanitize_attribute,
    sanitize_payload,
    safe_attributes,
)

__version__ = "0.1.0"
__all__ = [
    "configure_exporters",
    "get_tracer",
    "get_logger_provider",
    "shutdown_telemetry",
    "truncate",
    "truncate_bytes",
    "redact",
    "sanitize_attribute",
    "sanitize_payload",
    "safe_attributes",
]
