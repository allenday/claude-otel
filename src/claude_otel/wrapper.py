"""Lightweight wrapper that shells out to Claude CLI with OTEL instrumentation."""

import logging
import sys
import subprocess
import uuid
from typing import Optional

from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider, SpanProcessor
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.sdk.resources import Resource, SERVICE_NAME, SERVICE_NAMESPACE
from opentelemetry.sdk.trace.sampling import (
    ALWAYS_ON,
    ALWAYS_OFF,
    TraceIdRatioBased,
    Sampler,
)
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.trace import Status, StatusCode
from opentelemetry.sdk.trace.export import SpanExporter

from opentelemetry.exporter.otlp.proto.grpc._log_exporter import OTLPLogExporter
from opentelemetry.sdk._logs import LoggerProvider, LoggingHandler
from opentelemetry.sdk._logs.export import BatchLogRecordProcessor

from claude_otel.config import get_config, OTelConfig
from claude_otel.pii import sanitize_attribute, safe_attributes


def get_sampler(config: OTelConfig) -> Sampler:
    """Create sampler based on configuration."""
    sampler_name = config.traces_sampler.lower()

    if sampler_name == "always_off":
        return ALWAYS_OFF

    if sampler_name == "traceidratio":
        try:
            ratio = float(config.traces_sampler_arg or "1.0")
            return TraceIdRatioBased(ratio)
        except (ValueError, TypeError):
            if config.debug:
                print(f"[claude-otel] Invalid sampler ratio, using always_on", file=sys.stderr)
            return ALWAYS_ON

    # Default: always_on
    return ALWAYS_ON


def get_resource(config: OTelConfig) -> Resource:
    """Build OTEL resource from configuration."""
    attrs = {
        SERVICE_NAME: config.service_name,
        SERVICE_NAMESPACE: config.service_namespace,
    }

    # Merge additional resource attributes
    attrs.update(config.resource_attributes)

    return Resource.create(attrs)


def get_exporter(config: OTelConfig) -> Optional[OTLPSpanExporter]:
    """Create OTLP exporter based on configuration.

    Uses exporter_timeout_ms from config for network request timeouts.
    """
    if not config.traces_enabled:
        if config.debug:
            print("[claude-otel] Traces export disabled", file=sys.stderr)
        return None

    if not config.is_grpc:
        # For now, only gRPC is implemented; HTTP is optional per PRD
        print(f"[claude-otel] Warning: protocol '{config.protocol}' not supported, using gRPC",
              file=sys.stderr)

    try:
        return OTLPSpanExporter(
            endpoint=config.endpoint,
            insecure=True,
            timeout=config.exporter_timeout_ms / 1000,  # Convert ms to seconds
        )
    except Exception as e:
        print(f"[claude-otel] Warning: failed to create exporter: {e}", file=sys.stderr)
        return None


def create_batch_processor(exporter: SpanExporter, config: OTelConfig) -> BatchSpanProcessor:
    """Create BatchSpanProcessor with resilience configuration.

    Configures bounded queues and drop policy for graceful degradation:
    - max_queue_size: Maximum spans to buffer (drops oldest when full)
    - max_export_batch_size: Maximum spans per export batch
    - export_timeout_millis: Timeout for each export attempt
    - schedule_delay_millis: Delay between scheduled exports

    When the queue is full, new spans are dropped rather than blocking.
    This ensures the application remains responsive even when the
    collector is unreachable.
    """
    return BatchSpanProcessor(
        exporter,
        max_queue_size=config.bsp_max_queue_size,
        max_export_batch_size=config.bsp_max_export_batch_size,
        export_timeout_millis=config.bsp_export_timeout_ms,
        schedule_delay_millis=config.bsp_schedule_delay_ms,
    )


def setup_tracing(config: OTelConfig) -> trace.Tracer:
    """Initialize OTEL tracing with configured exporter and sampler.

    Uses resilience configuration for bounded queues and drop policy.
    """
    resource = get_resource(config)
    sampler = get_sampler(config)

    provider = TracerProvider(resource=resource, sampler=sampler)

    exporter = get_exporter(config)
    if exporter:
        processor = create_batch_processor(exporter, config)
        provider.add_span_processor(processor)

        if config.debug:
            print(f"[claude-otel] BatchSpanProcessor configured:", file=sys.stderr)
            print(f"[claude-otel]   max_queue_size: {config.bsp_max_queue_size}", file=sys.stderr)
            print(f"[claude-otel]   max_export_batch_size: {config.bsp_max_export_batch_size}", file=sys.stderr)
            print(f"[claude-otel]   export_timeout_ms: {config.bsp_export_timeout_ms}", file=sys.stderr)
            print(f"[claude-otel]   schedule_delay_ms: {config.bsp_schedule_delay_ms}", file=sys.stderr)

    trace.set_tracer_provider(provider)
    return trace.get_tracer("claude-otel", "0.1.0")


def setup_logging(config: OTelConfig) -> tuple[Optional[logging.Logger], Optional[LoggerProvider]]:
    """Initialize OTEL logging and return a logger hooked to the OTLP exporter."""
    if not config.logs_enabled:
        return None, None

    resource = get_resource(config)
    provider = LoggerProvider(resource=resource)
    exporter = OTLPLogExporter(endpoint=config.endpoint, insecure=True)
    provider.add_log_record_processor(BatchLogRecordProcessor(exporter))

    handler = LoggingHandler(level=logging.INFO, logger_provider=provider)
    logger = logging.getLogger("claude-otel")
    logger.setLevel(logging.INFO)
    logger.addHandler(handler)
    logger.propagate = False

    return logger, provider


def run_claude(args: list[str], tracer: trace.Tracer, logger: Optional[logging.Logger]) -> int:
    """Run Claude CLI within a session span."""
    session_id = str(uuid.uuid4())
    preview = None

    with tracer.start_as_current_span("claude-session") as span:
        span.set_attribute("session.id", session_id)
        span.set_attribute("claude.args_count", len(args))

        # Capture a preview of the prompt if provided via stdin or args
        # Apply PII safeguards: sanitize and truncate
        if args:
            preview = " ".join(args)
            sanitized_preview, _ = sanitize_attribute(preview, max_length=100)
            span.set_attribute("claude.args_preview", sanitized_preview)

        if logger:
            logger.info(
                "claude session start",
                extra={
                    "session_id": session_id,
                    "args_preview": preview[:100] if preview else "",
                },
            )

        try:
            # Shell out to Claude CLI, passing through all arguments
            result = subprocess.run(
                ["claude"] + args,
                stdin=sys.stdin if sys.stdin.isatty() else None,
                stdout=sys.stdout,
                stderr=sys.stderr,
            )

            span.set_attribute("exit_code", result.returncode)

            if result.returncode != 0:
                span.set_status(Status(StatusCode.ERROR, f"Exit code: {result.returncode}"))
            else:
                span.set_status(Status(StatusCode.OK))

            if logger:
                logger.info(
                    "claude session end",
                    extra={
                        "session_id": session_id,
                        "exit_code": result.returncode,
                    },
                )

            return result.returncode

        except FileNotFoundError:
            span.set_status(Status(StatusCode.ERROR, "Claude CLI not found"))
            span.set_attribute("error", True)
            span.set_attribute("error.message", "Claude CLI not found in PATH")
            if logger:
                logger.error(
                    "claude CLI not found",
                    extra={"session_id": session_id},
                )
            print("[claude-otel] Error: 'claude' command not found in PATH", file=sys.stderr)
            return 1

        except Exception as e:
            span.set_status(Status(StatusCode.ERROR, str(e)))
            span.set_attribute("error", True)
            error_msg, _ = sanitize_attribute(str(e), max_length=500)
            span.set_attribute("error.message", error_msg)
            if logger:
                logger.error(
                    "claude CLI error",
                    extra={
                        "session_id": session_id,
                        "error_message": error_msg,
                    },
                )
            print(f"[claude-otel] Error: {e}", file=sys.stderr)
            return 1


def main() -> int:
    """CLI entry point."""
    config = get_config()

    if config.debug:
        print("[claude-otel] Debug mode enabled", file=sys.stderr)
        print(f"[claude-otel] Endpoint: {config.endpoint}", file=sys.stderr)
        print(f"[claude-otel] Protocol: {config.protocol}", file=sys.stderr)
        print(f"[claude-otel] Service: {config.service_name}", file=sys.stderr)
        print(f"[claude-otel] Traces: {config.traces_exporter}", file=sys.stderr)
        print(f"[claude-otel] Logs: {config.logs_exporter}", file=sys.stderr)
        print(f"[claude-otel] Metrics: {config.metrics_exporter}", file=sys.stderr)
        print(f"[claude-otel] Sampler: {config.traces_sampler}", file=sys.stderr)

    tracer = setup_tracing(config)
    logger, logger_provider = setup_logging(config)

    # Pass all CLI arguments to Claude
    args = sys.argv[1:]

    try:
        return run_claude(args, tracer, logger)
    finally:
        if logger_provider:
            logger_provider.shutdown()


if __name__ == "__main__":
    sys.exit(main())
