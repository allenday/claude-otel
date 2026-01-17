"""OTEL exporter configuration for traces and logs.

Configures OTLP exporters to send telemetry to the configured collector.
Supports both gRPC (default, port 4317) and HTTP (port 4318) protocols.

Environment variables:
    OTEL_EXPORTER_OTLP_ENDPOINT: Collector endpoint (default: http://localhost:4317)
    OTEL_EXPORTER_OTLP_PROTOCOL: Protocol - 'grpc' (default) or 'http/protobuf'
    OTEL_SERVICE_NAME: Service name for resource attributes (default: claude-otel)
    OTEL_RESOURCE_ATTRIBUTES: Additional resource attributes as key=value,key2=value2
    OTEL_TRACES_EXPORTER: Trace exporter type - 'otlp' (default) or 'none'
    OTEL_LOGS_EXPORTER: Logs exporter type - 'otlp' (default) or 'none'

Resilience configuration:
    OTEL_BSP_MAX_QUEUE_SIZE: Max queue size for batch processor (default: 2048)
    OTEL_BSP_MAX_EXPORT_BATCH_SIZE: Max batch size for export (default: 512)
    OTEL_BSP_EXPORT_TIMEOUT: Export timeout in milliseconds (default: 30000)
    OTEL_BSP_SCHEDULE_DELAY: Delay between exports in milliseconds (default: 5000)
    OTEL_EXPORTER_OTLP_TIMEOUT: OTLP exporter timeout in milliseconds (default: 10000)
"""

import atexit
import logging
import os
from typing import Optional

from opentelemetry import trace
from opentelemetry.sdk.resources import Resource, SERVICE_NAME, SERVICE_NAMESPACE
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor

from opentelemetry.sdk._logs import LoggerProvider, LoggingHandler
from opentelemetry.sdk._logs.export import BatchLogRecordProcessor

# Default collector endpoint
DEFAULT_ENDPOINT = "http://localhost:4317"
DEFAULT_SERVICE_NAME = "claude-otel"
DEFAULT_PROTOCOL = "grpc"

# Resilience defaults
DEFAULT_BSP_MAX_QUEUE_SIZE = 2048
DEFAULT_BSP_MAX_EXPORT_BATCH_SIZE = 512
DEFAULT_BSP_EXPORT_TIMEOUT_MS = 30000
DEFAULT_BSP_SCHEDULE_DELAY_MS = 5000
DEFAULT_EXPORTER_TIMEOUT_MS = 10000

_tracer_provider: Optional[TracerProvider] = None
_logger_provider: Optional[LoggerProvider] = None
_configured = False


def _parse_resource_attributes(attrs_str: str) -> dict:
    """Parse OTEL_RESOURCE_ATTRIBUTES format: key=value,key2=value2."""
    if not attrs_str:
        return {}
    result = {}
    for pair in attrs_str.split(","):
        pair = pair.strip()
        if "=" in pair:
            key, value = pair.split("=", 1)
            result[key.strip()] = value.strip()
    return result


def _create_resource() -> Resource:
    """Create OTEL resource with service info and custom attributes."""
    service_name = os.environ.get("OTEL_SERVICE_NAME", DEFAULT_SERVICE_NAME)
    service_namespace = os.environ.get("OTEL_SERVICE_NAMESPACE", "claude")

    attrs = {
        SERVICE_NAME: service_name,
        SERVICE_NAMESPACE: service_namespace,
    }

    # Parse additional resource attributes from env
    extra_attrs = _parse_resource_attributes(
        os.environ.get("OTEL_RESOURCE_ATTRIBUTES", "")
    )
    attrs.update(extra_attrs)

    return Resource.create(attrs)


def _get_endpoint() -> str:
    """Get the OTLP endpoint from environment or use default."""
    return os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT", DEFAULT_ENDPOINT)


def _get_protocol() -> str:
    """Get the OTLP protocol from environment or use default (grpc)."""
    protocol = os.environ.get("OTEL_EXPORTER_OTLP_PROTOCOL", DEFAULT_PROTOCOL)
    # Normalize protocol names
    if protocol in ("http", "http/protobuf"):
        return "http"
    return "grpc"


def _get_int_env(name: str, default: int) -> int:
    """Get integer from environment variable with fallback."""
    val = os.environ.get(name, "")
    if not val:
        return default
    try:
        return int(val)
    except ValueError:
        return default


def _get_resilience_config() -> dict:
    """Get resilience configuration from environment variables."""
    return {
        "max_queue_size": _get_int_env("OTEL_BSP_MAX_QUEUE_SIZE", DEFAULT_BSP_MAX_QUEUE_SIZE),
        "max_export_batch_size": _get_int_env("OTEL_BSP_MAX_EXPORT_BATCH_SIZE", DEFAULT_BSP_MAX_EXPORT_BATCH_SIZE),
        "export_timeout_millis": _get_int_env("OTEL_BSP_EXPORT_TIMEOUT", DEFAULT_BSP_EXPORT_TIMEOUT_MS),
        "schedule_delay_millis": _get_int_env("OTEL_BSP_SCHEDULE_DELAY", DEFAULT_BSP_SCHEDULE_DELAY_MS),
    }


def _get_exporter_timeout() -> int:
    """Get OTLP exporter timeout in seconds."""
    timeout_ms = _get_int_env("OTEL_EXPORTER_OTLP_TIMEOUT", DEFAULT_EXPORTER_TIMEOUT_MS)
    return timeout_ms / 1000  # Convert to seconds


def _create_trace_exporter():
    """Create the appropriate trace exporter based on protocol.

    Uses OTEL_EXPORTER_OTLP_TIMEOUT for request timeouts.
    """
    endpoint = _get_endpoint()
    protocol = _get_protocol()
    timeout = _get_exporter_timeout()

    if protocol == "http":
        from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
        # HTTP endpoint typically uses /v1/traces path
        if not endpoint.endswith("/v1/traces"):
            traces_endpoint = endpoint.rstrip("/") + "/v1/traces"
        else:
            traces_endpoint = endpoint
        return OTLPSpanExporter(endpoint=traces_endpoint, timeout=timeout)
    else:
        from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
        return OTLPSpanExporter(endpoint=endpoint, insecure=True, timeout=timeout)


def _create_log_exporter():
    """Create the appropriate log exporter based on protocol.

    Uses OTEL_EXPORTER_OTLP_TIMEOUT for request timeouts.
    """
    endpoint = _get_endpoint()
    protocol = _get_protocol()
    timeout = _get_exporter_timeout()

    if protocol == "http":
        from opentelemetry.exporter.otlp.proto.http._log_exporter import OTLPLogExporter
        # HTTP endpoint typically uses /v1/logs path
        if not endpoint.endswith("/v1/logs"):
            logs_endpoint = endpoint.rstrip("/") + "/v1/logs"
        else:
            logs_endpoint = endpoint
        return OTLPLogExporter(endpoint=logs_endpoint, timeout=timeout)
    else:
        from opentelemetry.exporter.otlp.proto.grpc._log_exporter import OTLPLogExporter
        return OTLPLogExporter(endpoint=endpoint, insecure=True, timeout=timeout)


def configure_exporters() -> tuple[TracerProvider, LoggerProvider]:
    """Configure and return OTEL trace and log providers with OTLP exporters.

    Call this once at application startup to initialize telemetry.
    Uses environment variables for configuration.

    Resilience features:
    - Bounded queues: Limits memory usage when collector is unreachable
    - Drop policy: Drops oldest spans when queue is full (non-blocking)
    - Timeouts: Configurable export and request timeouts

    Returns:
        Tuple of (TracerProvider, LoggerProvider)

    Raises:
        RuntimeError: If exporters are already configured.
    """
    global _tracer_provider, _logger_provider, _configured

    if _configured:
        raise RuntimeError("OTEL exporters already configured. Call shutdown_telemetry() first.")

    resource = _create_resource()
    resilience = _get_resilience_config()

    # Check if traces export is enabled
    traces_exporter = os.environ.get("OTEL_TRACES_EXPORTER", "otlp")
    if traces_exporter != "none":
        _tracer_provider = TracerProvider(resource=resource)
        span_exporter = _create_trace_exporter()
        # Configure batch processor with resilience settings
        span_processor = BatchSpanProcessor(
            span_exporter,
            max_queue_size=resilience["max_queue_size"],
            max_export_batch_size=resilience["max_export_batch_size"],
            export_timeout_millis=resilience["export_timeout_millis"],
            schedule_delay_millis=resilience["schedule_delay_millis"],
        )
        _tracer_provider.add_span_processor(span_processor)
        trace.set_tracer_provider(_tracer_provider)

    # Check if logs export is enabled
    logs_exporter = os.environ.get("OTEL_LOGS_EXPORTER", "otlp")
    if logs_exporter != "none":
        _logger_provider = LoggerProvider(resource=resource)
        log_exporter = _create_log_exporter()
        # Configure batch processor with resilience settings
        log_processor = BatchLogRecordProcessor(
            log_exporter,
            max_queue_size=resilience["max_queue_size"],
            max_export_batch_size=resilience["max_export_batch_size"],
            export_timeout_millis=resilience["export_timeout_millis"],
            schedule_delay_millis=resilience["schedule_delay_millis"],
        )
        _logger_provider.add_log_record_processor(log_processor)

        # Attach OTEL logging handler to Python's root logger
        handler = LoggingHandler(level=logging.NOTSET, logger_provider=_logger_provider)
        logging.getLogger().addHandler(handler)

    _configured = True

    # Register shutdown handler
    atexit.register(shutdown_telemetry)

    return _tracer_provider, _logger_provider


def get_tracer(name: str = "claude-otel") -> trace.Tracer:
    """Get a tracer instance for creating spans.

    Args:
        name: Tracer name, typically the module name.

    Returns:
        A Tracer instance.
    """
    if _tracer_provider is None:
        # Return a no-op tracer if not configured
        return trace.get_tracer(name)
    return _tracer_provider.get_tracer(name)


def get_logger_provider() -> Optional[LoggerProvider]:
    """Get the configured logger provider.

    Returns:
        The LoggerProvider instance, or None if not configured.
    """
    return _logger_provider


def shutdown_telemetry() -> None:
    """Shutdown telemetry providers and flush pending data.

    Call this at application exit to ensure all data is exported.
    """
    global _tracer_provider, _logger_provider, _configured

    if _tracer_provider is not None:
        _tracer_provider.shutdown()
        _tracer_provider = None

    if _logger_provider is not None:
        _logger_provider.shutdown()
        _logger_provider = None

    _configured = False
