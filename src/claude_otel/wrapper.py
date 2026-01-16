"""Lightweight wrapper that shells out to Claude CLI with OTEL instrumentation."""

import os
import sys
import subprocess
import uuid
from typing import Optional

from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.sdk.resources import Resource, SERVICE_NAME, SERVICE_NAMESPACE
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.trace import Status, StatusCode


def get_resource() -> Resource:
    """Build OTEL resource from environment."""
    service_name = os.environ.get("OTEL_SERVICE_NAME", "claude-cli")
    service_namespace = os.environ.get("OTEL_SERVICE_NAMESPACE", "claude-otel")

    attrs = {
        SERVICE_NAME: service_name,
        SERVICE_NAMESPACE: service_namespace,
    }

    # Parse additional resource attributes from OTEL_RESOURCE_ATTRIBUTES
    extra_attrs = os.environ.get("OTEL_RESOURCE_ATTRIBUTES", "")
    if extra_attrs:
        for pair in extra_attrs.split(","):
            if "=" in pair:
                key, value = pair.split("=", 1)
                attrs[key.strip()] = value.strip()

    return Resource.create(attrs)


def get_exporter() -> Optional[OTLPSpanExporter]:
    """Create OTLP exporter based on environment configuration."""
    endpoint = os.environ.get(
        "OTEL_EXPORTER_OTLP_ENDPOINT",
        "http://100.91.20.46:4317"
    )

    # Handle protocol preference (default gRPC)
    protocol = os.environ.get("OTEL_EXPORTER_OTLP_PROTOCOL", "grpc")
    if protocol != "grpc":
        # For now, only gRPC is implemented; HTTP is optional per PRD
        print(f"[claude-otel] Warning: protocol '{protocol}' not supported, using gRPC",
              file=sys.stderr)

    try:
        return OTLPSpanExporter(endpoint=endpoint, insecure=True)
    except Exception as e:
        print(f"[claude-otel] Warning: failed to create exporter: {e}", file=sys.stderr)
        return None


def setup_tracing() -> trace.Tracer:
    """Initialize OTEL tracing with configured exporter."""
    resource = get_resource()
    provider = TracerProvider(resource=resource)

    exporter = get_exporter()
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
        # (lightweight; don't capture full content for PII reasons)
        if args:
            # Truncate to avoid large payloads
            preview = " ".join(args)[:100]
            span.set_attribute("claude.args_preview", preview)

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
            span.set_attribute("error.message", str(e)[:500])  # Truncate for safety
            print(f"[claude-otel] Error: {e}", file=sys.stderr)
            return 1


def main() -> int:
    """CLI entry point."""
    # Check for debug mode
    debug = os.environ.get("CLAUDE_OTEL_DEBUG", "").lower() in ("1", "true", "yes")

    if debug:
        print("[claude-otel] Debug mode enabled", file=sys.stderr)
        print(f"[claude-otel] OTEL endpoint: {os.environ.get('OTEL_EXPORTER_OTLP_ENDPOINT', 'default')}",
              file=sys.stderr)

    tracer = setup_tracing()

    # Pass all CLI arguments to Claude
    args = sys.argv[1:]

    return run_claude(args, tracer)


if __name__ == "__main__":
    sys.exit(main())
