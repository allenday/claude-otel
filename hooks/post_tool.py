#!/usr/bin/env python3
"""PostToolUse hook: create OTEL span for completed tool invocation.

Retrieves start time and input from PreToolUse context file, combines with
tool response data, and emits a complete span with all attributes.
"""

import json
import os
import sys
import time
import tempfile
from typing import Any, Optional

# Import OTEL after ensuring package is available
try:
    from opentelemetry import trace
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import BatchSpanProcessor
    from opentelemetry.sdk.resources import Resource, SERVICE_NAME, SERVICE_NAMESPACE
    from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
    from opentelemetry.trace import Status, StatusCode

    OTEL_AVAILABLE = True
except ImportError:
    OTEL_AVAILABLE = False


# Default configuration
DEFAULT_ENDPOINT = "http://100.91.20.46:4317"
DEFAULT_SERVICE_NAME = "claude-cli"
DEFAULT_SERVICE_NAMESPACE = "claude-otel"
DEFAULT_MAX_ATTR_LENGTH = 256
DEFAULT_MAX_PAYLOAD_BYTES = 1024

# Context directory matching pre_tool.py
CONTEXT_DIR = os.path.join(tempfile.gettempdir(), "claude-otel-spans")


def get_env(key: str, default: str) -> str:
    """Get environment variable with default."""
    return os.environ.get(key, default)


def truncate(value: str, max_len: int = DEFAULT_MAX_ATTR_LENGTH) -> tuple[str, bool]:
    """Truncate string to max length."""
    if len(value) <= max_len:
        return value, False
    return value[: max_len - 12] + "...[TRUNC]", True


def get_input_summary(tool_input: dict, tool_name: str) -> str:
    """Extract a summary of the tool input based on tool type."""
    if tool_name == "Bash":
        return tool_input.get("command", "")[:200]
    elif tool_name in ("Read", "Write", "Edit"):
        return tool_input.get("file_path", "")
    elif tool_name == "Glob":
        return tool_input.get("pattern", "")
    elif tool_name == "Grep":
        return tool_input.get("pattern", "")
    elif tool_name == "Task":
        return tool_input.get("description", "")[:100]
    else:
        # Generic: stringify and truncate
        try:
            return str(tool_input)[:200]
        except Exception:
            return "<unable to summarize>"


def calculate_payload_size(response: Any) -> int:
    """Calculate approximate size of response in bytes."""
    try:
        if isinstance(response, str):
            return len(response.encode("utf-8", errors="replace"))
        elif isinstance(response, bytes):
            return len(response)
        else:
            return len(json.dumps(response, default=str).encode("utf-8"))
    except Exception:
        return 0


def setup_tracer() -> Optional[trace.Tracer]:
    """Set up OTEL tracer with configured exporter."""
    if not OTEL_AVAILABLE:
        return None

    # Check if traces are enabled
    if get_env("OTEL_TRACES_EXPORTER", "otlp").lower() == "none":
        return None

    try:
        endpoint = get_env("OTEL_EXPORTER_OTLP_ENDPOINT", DEFAULT_ENDPOINT)
        service_name = get_env("OTEL_SERVICE_NAME", DEFAULT_SERVICE_NAME)
        service_namespace = get_env("OTEL_SERVICE_NAMESPACE", DEFAULT_SERVICE_NAMESPACE)

        resource = Resource.create(
            {
                SERVICE_NAME: service_name,
                SERVICE_NAMESPACE: service_namespace,
            }
        )

        provider = TracerProvider(resource=resource)
        exporter = OTLPSpanExporter(endpoint=endpoint, insecure=True)
        provider.add_span_processor(BatchSpanProcessor(exporter))

        trace.set_tracer_provider(provider)
        return trace.get_tracer("claude-otel-hooks", "0.1.0")

    except Exception as e:
        if get_env("CLAUDE_OTEL_DEBUG", "").lower() in ("1", "true"):
            print(f"[claude-otel] Tracer setup error: {e}", file=sys.stderr)
        return None


def load_pre_context(tool_use_id: str) -> Optional[dict]:
    """Load context saved by PreToolUse hook."""
    context_file = os.path.join(CONTEXT_DIR, f"{tool_use_id}.json")
    try:
        with open(context_file, "r") as f:
            context = json.load(f)
        # Clean up the context file
        os.unlink(context_file)
        return context
    except (FileNotFoundError, json.JSONDecodeError):
        return None


def main():
    try:
        # Parse input from Claude
        input_data = json.load(sys.stdin)

        tool_use_id = input_data.get("tool_use_id", "")
        if not tool_use_id:
            return

        # Load PreToolUse context
        pre_context = load_pre_context(tool_use_id)

        # Set up tracer
        tracer = setup_tracer()
        if not tracer:
            return

        # Extract data
        tool_name = input_data.get("tool_name", pre_context.get("tool_name", "unknown") if pre_context else "unknown")
        tool_input = input_data.get("tool_input", pre_context.get("tool_input", {}) if pre_context else {})
        tool_response = input_data.get("tool_response", "")
        session_id = input_data.get("session_id", pre_context.get("session_id", "") if pre_context else "")

        # Calculate timing
        end_time_ns = time.time_ns()
        if pre_context and "start_time_ns" in pre_context:
            start_time_ns = pre_context["start_time_ns"]
            duration_ms = (end_time_ns - start_time_ns) / 1_000_000
        else:
            # Fallback: use current time for both (duration = 0)
            start_time_ns = end_time_ns
            duration_ms = 0

        # Calculate payload sizes
        input_summary = get_input_summary(tool_input, tool_name)
        input_summary_truncated, was_input_truncated = truncate(input_summary)

        response_bytes = calculate_payload_size(tool_response)

        # Determine error status
        is_error = False
        error_message = ""
        exit_code = 0

        if isinstance(tool_response, dict):
            # Check for error indicators in response
            if tool_response.get("error"):
                is_error = True
                error_message = str(tool_response.get("error", ""))[:500]
            if "exit_code" in tool_response:
                exit_code = tool_response["exit_code"]
                if exit_code != 0:
                    is_error = True
        elif isinstance(tool_response, str):
            # Check for error patterns in string response
            if tool_response.startswith("Error:") or "error" in tool_response.lower()[:100]:
                is_error = True
                error_message = tool_response[:500]

        # Create span with all attributes
        with tracer.start_as_current_span(
            f"tool.{tool_name.lower()}",
            start_time=start_time_ns,
        ) as span:
            # Core attributes per PRD
            span.set_attribute("tool.name", tool_name)
            span.set_attribute("duration_ms", duration_ms)
            span.set_attribute("session.id", session_id)
            span.set_attribute("tool.use_id", tool_use_id)

            # Input summary (sanitized)
            span.set_attribute("input.summary", input_summary_truncated)
            span.set_attribute("input.truncated", was_input_truncated)

            # Output metrics
            span.set_attribute("response_bytes", response_bytes)
            span.set_attribute("response.truncated", response_bytes > DEFAULT_MAX_PAYLOAD_BYTES)

            # Exit code / error handling
            span.set_attribute("exit_code", exit_code)
            span.set_attribute("error", is_error)
            if error_message:
                span.set_attribute("error.message", error_message[:500])

            # Set span status
            if is_error:
                span.set_status(Status(StatusCode.ERROR, error_message[:100] if error_message else "Tool error"))
            else:
                span.set_status(Status(StatusCode.OK))

        # Force flush to ensure span is exported
        provider = trace.get_tracer_provider()
        if hasattr(provider, "force_flush"):
            provider.force_flush(timeout_millis=5000)

    except Exception as e:
        # Don't block tool execution on errors
        if os.environ.get("CLAUDE_OTEL_DEBUG", "").lower() in ("1", "true"):
            print(f"[claude-otel] PostToolUse error: {e}", file=sys.stderr)


if __name__ == "__main__":
    main()
