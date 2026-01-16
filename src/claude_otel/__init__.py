"""OTEL telemetry wrapper for Claude CLI."""

from claude_otel.exporter import (
    configure_exporters,
    get_tracer,
    get_logger_provider,
    shutdown_telemetry,
)
from claude_otel.metrics import (
    configure_metrics,
    get_meter,
    record_tool_call,
    record_session_start,
    record_session_end,
    shutdown_metrics,
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
    "configure_metrics",
    "get_meter",
    "record_tool_call",
    "record_session_start",
    "record_session_end",
    "shutdown_metrics",
    "truncate",
    "truncate_bytes",
    "redact",
    "sanitize_attribute",
    "sanitize_payload",
    "safe_attributes",
]
