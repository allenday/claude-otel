#!/usr/bin/env python3
"""PostToolUse hook: create OTEL span for completed tool invocation.

Retrieves start time and input from PreToolUse context file, combines with
tool response data, and emits a complete span with all attributes.

Token usage is extracted from the Claude transcript file (if available).
"""

import json
import os
import sys
import time
import tempfile
from typing import Any, Optional, Dict

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


def extract_token_usage(transcript_path: str, tool_use_id: str) -> Optional[Dict[str, int]]:
    """Extract token usage from the Claude transcript for the tool invocation.

    The transcript is a JSONL file where each line is a message. We look for
    the assistant message that contains the tool_use with matching ID, then
    extract the usage metrics from that entry.

    Args:
        transcript_path: Path to the session transcript JSONL file.
        tool_use_id: The tool_use_id to find usage for.

    Returns:
        Dict with token counts if found, None otherwise.
        Keys: input_tokens, output_tokens, cache_read_input_tokens,
              cache_creation_input_tokens
    """
    if not transcript_path or not os.path.exists(transcript_path):
        return None

    try:
        # Read the last N lines efficiently (tool use should be recent)
        # We use a tail-like approach to avoid reading the entire file
        with open(transcript_path, "rb") as f:
            # Seek to end and read backwards to find last ~50KB
            f.seek(0, 2)  # End of file
            file_size = f.tell()
            read_size = min(file_size, 50 * 1024)  # Last 50KB
            f.seek(max(0, file_size - read_size))
            data = f.read().decode("utf-8", errors="replace")

        # Split into lines and parse from the end
        lines = data.strip().split("\n")

        for line in reversed(lines):
            if not line.strip():
                continue
            try:
                entry = json.loads(line)

                # Check if this is an assistant message with our tool_use_id
                message = entry.get("message", {})
                if message.get("role") != "assistant":
                    continue

                # Check content for matching tool_use
                content = message.get("content", [])
                if not isinstance(content, list):
                    continue

                for item in content:
                    if (
                        isinstance(item, dict)
                        and item.get("type") == "tool_use"
                        and item.get("id") == tool_use_id
                    ):
                        # Found the message, extract usage
                        usage = message.get("usage", {})
                        if usage:
                            return {
                                "input_tokens": usage.get("input_tokens", 0),
                                "output_tokens": usage.get("output_tokens", 0),
                                "cache_read_input_tokens": usage.get(
                                    "cache_read_input_tokens", 0
                                ),
                                "cache_creation_input_tokens": usage.get(
                                    "cache_creation_input_tokens", 0
                                ),
                            }
                        return None

            except json.JSONDecodeError:
                continue

    except Exception as e:
        if get_env("CLAUDE_OTEL_DEBUG", "").lower() in ("1", "true"):
            print(f"[claude-otel] Token extraction error: {e}", file=sys.stderr)

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
        transcript_path = input_data.get("transcript_path", "")

        # Extract token usage from transcript (if available)
        token_usage = extract_token_usage(transcript_path, tool_use_id)

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

            # Token usage (if available from transcript)
            if token_usage:
                span.set_attribute("tokens.input", token_usage.get("input_tokens", 0))
                span.set_attribute("tokens.output", token_usage.get("output_tokens", 0))
                span.set_attribute(
                    "tokens.cache_read", token_usage.get("cache_read_input_tokens", 0)
                )
                span.set_attribute(
                    "tokens.cache_creation",
                    token_usage.get("cache_creation_input_tokens", 0),
                )
                # Total tokens for easy querying
                total_tokens = (
                    token_usage.get("input_tokens", 0)
                    + token_usage.get("output_tokens", 0)
                    + token_usage.get("cache_read_input_tokens", 0)
                    + token_usage.get("cache_creation_input_tokens", 0)
                )
                span.set_attribute("tokens.total", total_tokens)

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
