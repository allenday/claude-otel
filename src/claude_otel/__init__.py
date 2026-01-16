"""OTEL telemetry wrapper for Claude CLI."""

from claude_otel.exporter import (
    configure_exporters,
    get_tracer,
    get_logger_provider,
    shutdown_telemetry,
)

__version__ = "0.1.0"
__all__ = [
    "configure_exporters",
    "get_tracer",
    "get_logger_provider",
    "shutdown_telemetry",
]
