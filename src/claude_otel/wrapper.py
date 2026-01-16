"""Lightweight wrapper that shells out to Claude CLI with OTEL instrumentation."""

import sys
import subprocess
import uuid
from typing import Optional

from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
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
    """Create OTLP exporter based on configuration."""
    if not config.traces_enabled:
        if config.debug:
            print("[claude-otel] Traces export disabled", file=sys.stderr)
        return None

    if not config.is_grpc:
        # For now, only gRPC is implemented; HTTP is optional per PRD
        print(f"[claude-otel] Warning: protocol '{config.protocol}' not supported, using gRPC",
              file=sys.stderr)

    try:
        return OTLPSpanExporter(endpoint=config.endpoint, insecure=True)
    except Exception as e:
        print(f"[claude-otel] Warning: failed to create exporter: {e}", file=sys.stderr)
        return None


def setup_tracing(config: OTelConfig) -> trace.Tracer:
    """Initialize OTEL tracing with configured exporter and sampler."""
    resource = get_resource(config)
    sampler = get_sampler(config)

    provider = TracerProvider(resource=resource, sampler=sampler)

    exporter = get_exporter(config)
    if exporter:
        processor = BatchSpanProcessor(exporter)
        provider.add_span_processor(processor)

    trace.set_tracer_provider(provider)
    return trace.get_tracer("claude-otel", "0.1.0")


def run_claude(args: list[str], tracer: trace.Tracer) -> int:
    """Run Claude CLI within a session span."""
    session_id = str(uuid.uuid4())

    with tracer.start_as_current_span("claude-session") as span:
        span.set_attribute("session.id", session_id)
        span.set_attribute("claude.args_count", len(args))

        # Capture a preview of the prompt if provided via stdin or args
        # Apply PII safeguards: sanitize and truncate
        if args:
            preview = " ".join(args)
            sanitized_preview, _ = sanitize_attribute(preview, max_length=100)
            span.set_attribute("claude.args_preview", sanitized_preview)

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

            return result.returncode

        except FileNotFoundError:
            span.set_status(Status(StatusCode.ERROR, "Claude CLI not found"))
            span.set_attribute("error", True)
            span.set_attribute("error.message", "Claude CLI not found in PATH")
            print("[claude-otel] Error: 'claude' command not found in PATH", file=sys.stderr)
            return 1

        except Exception as e:
            span.set_status(Status(StatusCode.ERROR, str(e)))
            span.set_attribute("error", True)
            error_msg, _ = sanitize_attribute(str(e), max_length=500)
            span.set_attribute("error.message", error_msg)
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

    # Pass all CLI arguments to Claude
    args = sys.argv[1:]

    return run_claude(args, tracer)


if __name__ == "__main__":
    sys.exit(main())
