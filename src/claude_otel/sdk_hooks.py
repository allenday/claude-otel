"""SDK-based hooks for Claude agent telemetry.

This module provides OpenTelemetry instrumentation for Claude agent sessions
using the claude-agent-sdk hooks (UserPromptSubmit, PreToolUse, PostToolUse,
MessageComplete, PreCompact).

These hooks provide richer telemetry than CLI hooks alone, including:
- Prompt and model capture
- Turn tracking with incremental token counts
- gen_ai.* semantic conventions
- Context compaction events
"""

from typing import Any, Optional
import logging
import time
import uuid

from opentelemetry import trace
from opentelemetry.trace import Status, StatusCode

from claude_otel.config import get_config
from claude_otel.formatting import (
    create_tool_title,
    create_completion_title,
    truncate_for_display,
)
from claude_otel import metrics


class SDKTelemetryHooks:
    """SDK-based hooks for capturing Claude agent telemetry.

    Implements the hook interface expected by claude-agent-sdk:
    - on_user_prompt_submit: Called when user submits a prompt
    - on_pre_tool_use: Called before tool execution
    - on_post_tool_use: Called after tool execution
    - on_message_complete: Called when assistant message is complete
    - on_pre_compact: Called before context compaction
    """

    def __init__(
        self,
        tracer: Optional[trace.Tracer] = None,
        tracer_name: str = "claude-otel-sdk",
        create_tool_spans: bool = True,
        logger: Optional[logging.Logger] = None,
    ):
        """Initialize SDK hooks with a tracer.

        Args:
            tracer: Optional OpenTelemetry tracer; if None, creates one with tracer_name
            tracer_name: Name for the OpenTelemetry tracer (used if tracer is None)
            create_tool_spans: If True, create child spans for each tool.
                              If False, add tool data as events only.
            logger: Optional logger for OTEL logging (emits per-tool logs to Loki)
        """
        self.config = get_config()
        self.tracer = tracer if tracer is not None else trace.get_tracer(tracer_name, "0.1.0")
        self.logger = logger
        self.session_span: Optional[trace.Span] = None
        self.tool_spans: dict[str, trace.Span] = {}
        self.tool_start_times: dict[str, float] = {}

        # Initialize metrics tracking
        self.metrics = {
            "prompt": "",
            "model": "unknown",
            "input_tokens": 0,
            "output_tokens": 0,
            "cache_read_input_tokens": 0,
            "cache_creation_input_tokens": 0,
            "tools_used": 0,
            "turns": 0,
            "start_time": 0.0,
        }

        self.messages = []
        self.tools_used = []
        self.create_tool_spans = create_tool_spans

    async def on_user_prompt_submit(
        self,
        input_data: dict[str, Any],
        tool_use_id: Optional[str],
        ctx: Any,
    ) -> dict[str, Any]:
        """Hook called when user submits a prompt.

        Opens the parent session span and captures the initial prompt and model.
        Implements gen_ai.* semantic conventions for LLM observability.

        Args:
            input_data: Dict containing 'prompt' and 'session_id'
            tool_use_id: Not used for this hook (always None)
            ctx: Context dict with 'options' containing 'model'

        Returns:
            Empty dict (no modifications to input)
        """
        # Extract prompt from input
        prompt = input_data.get("prompt", "")
        raw_session_id = input_data.get("session_id", "")
        session_id = str(raw_session_id) if raw_session_id else uuid.uuid4().hex

        # Extract model from context - handle both dict and object contexts
        model = "unknown"
        if isinstance(ctx, dict):
            if "options" in ctx and "model" in ctx["options"]:
                model = ctx["options"]["model"]
        else:
            # Handle object context
            if hasattr(ctx, "options") and hasattr(ctx.options, "model"):
                model = ctx.options.model

        # Initialize metrics
        self.metrics = {
            "prompt": prompt,
            "model": model,
            "input_tokens": 0,
            "output_tokens": 0,
            "cache_read_input_tokens": 0,
            "cache_creation_input_tokens": 0,
            "tools_used": 0,
            "turns": 0,
            "start_time": time.time(),
        }

        # Create span title with prompt preview
        prompt_preview = prompt[:60] + "..." if len(prompt) > 60 else prompt

        # Start session span with semantic conventions
        self.session_span = self.tracer.start_span(
            f"claude.session: {prompt_preview}",
            attributes={
                "prompt": prompt[:1000],  # Truncate for attribute size limits
                "model": model,
                "session.id": session_id,
                # gen_ai.* semantic conventions for LLM observability
                "gen_ai.system": "anthropic",
                "gen_ai.request.model": model,
            },
        )

        # Add user prompt event
        if self.session_span:
            self.session_span.add_event(
                "user.prompt.submitted",
                {"prompt": prompt[:500]},
            )

        # Store message
        self.messages.append({"role": "user", "content": prompt})

        # Record model request metric
        metrics.record_model_request(model)

        # Rich console output
        if self.config.debug:
            print(f"🤖 {prompt_preview}")

        return {}

    async def on_pre_tool_use(
        self,
        input_data: dict[str, Any],
        tool_use_id: Optional[str],
        ctx: Any,
    ) -> dict[str, Any]:
        """Hook called before tool execution.

        Args:
            input_data: Dict with 'tool_name' and 'tool_input'
            tool_use_id: Unique ID for this tool invocation
            ctx: Context object

        Returns:
            Empty dict (no modifications to input)
        """
        tool_name = input_data.get("tool_name", "unknown")
        tool_input = input_data.get("tool_input", {})

        if not self.session_span:
            if self.config.debug:
                print("[claude-otel-sdk] Warning: No active session span")
            return {}

        # Track usage
        self.tools_used.append(tool_name)
        self.metrics["tools_used"] += 1

        # Record start time for duration tracking
        span_id = tool_use_id or f"{tool_name}_{time.time_ns()}"
        self.tool_start_times[span_id] = time.time()

        # Rich console output
        tool_title = create_tool_title(tool_name, tool_input)
        if self.config.debug:
            print(f"🔧 {tool_title}")

        if self.create_tool_spans:
            # Create child span for tool
            ctx_token = trace.set_span_in_context(self.session_span)
            tool_span = self.tracer.start_span(
                f"tool.{tool_name}",
                attributes={
                    "tool.name": tool_name,
                    "gen_ai.operation.name": "execute_tool",
                },
                context=ctx_token,
            )

            # Add tool input as attributes (truncated)
            if tool_input:
                input_str = str(tool_input)[:500]
                tool_span.set_attribute("tool.input", input_str)
                tool_span.add_event("tool.started", {"input": input_str})

            # Store span (reuse span_id from above)
            self.tool_spans[span_id] = tool_span
        else:
            # Just add event to session span
            self.session_span.add_event(
                f"tool.started: {tool_name}",
                {"tool.name": tool_name, "tool.input": str(tool_input)[:500]},
            )

        return {}

    async def on_post_tool_use(
        self,
        input_data: dict[str, Any],
        tool_use_id: Optional[str],
        ctx: Any,
    ) -> dict[str, Any]:
        """Hook called after tool execution.

        Args:
            input_data: Dict with 'tool_name' and 'tool_response'
            tool_use_id: Unique ID for this tool invocation
            ctx: Context object

        Returns:
            Empty dict (no modifications to input)
        """
        tool_name = input_data.get("tool_name", "unknown")
        tool_response = input_data.get("tool_response")

        if not self.create_tool_spans:
            # No child spans - add response data as event to session span
            if self.session_span:
                # Calculate duration for event
                span_id = tool_use_id or f"{tool_name}_{time.time_ns()}"
                duration_ms = 0.0
                if span_id in self.tool_start_times:
                    start_time = self.tool_start_times[span_id]
                    duration_ms = (time.time() - start_time) * 1000
                    del self.tool_start_times[span_id]

                # Determine error status for metrics
                has_error = False
                if isinstance(tool_response, dict):
                    if "error" in tool_response and tool_response["error"]:
                        has_error = True
                    elif "isError" in tool_response and tool_response["isError"]:
                        has_error = True

                # Record metric
                metrics.record_tool_call(tool_name, duration_ms, has_error)

                self.session_span.add_event(
                    f"tool.completed: {tool_name}",
                    {
                        "tool.name": tool_name,
                        "tool.response": str(tool_response)[:500],
                        "duration_ms": duration_ms,
                    },
                )
            return {}

        # Find and close the tool span
        span = None
        span_id = None

        if tool_use_id and tool_use_id in self.tool_spans:
            span = self.tool_spans[tool_use_id]
            span_id = tool_use_id
        else:
            # Fall back to name matching for most recent
            for tid, s in reversed(list(self.tool_spans.items())):
                if tid.startswith(f"{tool_name}_"):
                    span = s
                    span_id = tid
                    break

        if not span:
            if self.config.debug:
                print(f"[claude-otel-sdk] Warning: No span found for tool: {tool_name}")
            return {}

        # Calculate duration
        duration_ms = 0.0
        if span_id and span_id in self.tool_start_times:
            start_time = self.tool_start_times[span_id]
            duration_ms = (time.time() - start_time) * 1000  # Convert to milliseconds
            span.set_attribute("tool.duration_ms", duration_ms)
            span.set_attribute("duration_ms", duration_ms)
            # Clean up start time
            del self.tool_start_times[span_id]

        # Determine error status
        has_error = False
        if isinstance(tool_response, dict):
            if "error" in tool_response and tool_response["error"]:
                has_error = True
            elif "isError" in tool_response and tool_response["isError"]:
                has_error = True

        # Record metric
        metrics.record_tool_call(tool_name, duration_ms, has_error)

        # Emit per-tool-call log for Loki/Grafana charting
        if self.logger:
            # Extract additional metadata for logging
            log_extra = {
                "tool.name": tool_name,
                "tool.duration_ms": duration_ms,
                "tool.status": "error" if has_error else "success",
            }

            # Add session ID if available
            if self.session_span and hasattr(self.session_span, "context"):
                log_extra["session.id"] = str(self.session_span.context.span_id)

            # Add error information if present
            if has_error and isinstance(tool_response, dict):
                if "error" in tool_response:
                    log_extra["tool.error"] = str(tool_response["error"])[:200]
                elif "isError" in tool_response:
                    log_extra["tool.error"] = "Tool execution failed"

            # Log with info level for success, warning for errors
            if has_error:
                self.logger.warning(
                    f"Tool call failed: {tool_name}",
                    extra=log_extra,
                )
            else:
                self.logger.info(
                    f"Tool call completed: {tool_name}",
                    extra=log_extra,
                )

        # Rich console output
        completion_title = create_completion_title(tool_name, tool_response)
        if self.config.debug:
            if has_error:
                print(f"❌ {completion_title}")
            else:
                print(f"✅ {completion_title}")

        # Add response attributes and close span
        try:
            if tool_response is not None:
                response_str = str(tool_response)
                span.set_attribute("tool.response", response_str[:1000])

                # Check for errors
                if isinstance(tool_response, dict):
                    if "error" in tool_response and tool_response["error"]:
                        error_msg = str(tool_response["error"])[:500]
                        span.set_attribute("tool.error", error_msg)
                        span.set_attribute("tool.status", "error")
                        span.set_status(Status(StatusCode.ERROR, error_msg[:100]))
                    elif "isError" in tool_response and tool_response["isError"]:
                        span.set_attribute("tool.status", "error")
                        span.set_status(Status(StatusCode.ERROR, "Tool failed"))
                    else:
                        span.set_attribute("tool.status", "success")
                        span.set_status(Status(StatusCode.OK))
                else:
                    span.set_attribute("tool.status", "success")
                    span.set_status(Status(StatusCode.OK))

                span.add_event("tool.completed", {"response": response_str[:500]})
        finally:
            # Always end the span
            span.end()
            if span_id and span_id in self.tool_spans:
                del self.tool_spans[span_id]

        return {}

    async def on_message_complete(
        self,
        message: Any,
        ctx: Any,
    ) -> dict[str, Any]:
        """Hook called when assistant message is complete.

        Updates cumulative token counts and turn tracking with gen_ai.* conventions.

        Args:
            message: Message object with 'usage' attribute containing token counts
            ctx: Context object

        Returns:
            Empty dict (no modifications)
        """
        # Extract token usage
        if hasattr(message, "usage"):
            input_tokens = getattr(message.usage, "input_tokens", 0)
            output_tokens = getattr(message.usage, "output_tokens", 0)
            cache_read = getattr(message.usage, "cache_read_input_tokens", 0)
            cache_creation = getattr(message.usage, "cache_creation_input_tokens", 0)

            # Update cumulative metrics
            self.metrics["input_tokens"] += input_tokens
            self.metrics["output_tokens"] += output_tokens
            self.metrics["cache_read_input_tokens"] += cache_read
            self.metrics["cache_creation_input_tokens"] += cache_creation
            self.metrics["turns"] += 1

            # Record metrics
            model = self.metrics.get("model", "unknown")
            metrics.record_turn(model)
            metrics.record_cache_usage(cache_read, cache_creation, model)

            # Update span with cumulative token usage using semantic conventions
            if self.session_span:
                # gen_ai.* semantic conventions for token usage
                self.session_span.set_attribute(
                    "gen_ai.usage.input_tokens", self.metrics["input_tokens"]
                )
                self.session_span.set_attribute(
                    "gen_ai.usage.output_tokens", self.metrics["output_tokens"]
                )

                # Additional token metrics
                self.session_span.set_attribute(
                    "tokens.cache_read", self.metrics["cache_read_input_tokens"]
                )
                self.session_span.set_attribute(
                    "tokens.cache_creation", self.metrics["cache_creation_input_tokens"]
                )
                self.session_span.set_attribute("turns", self.metrics["turns"])

                # Add event for this turn with incremental tokens
                self.session_span.add_event(
                    "turn.completed",
                    {
                        "turn": self.metrics["turns"],
                        "input_tokens": input_tokens,
                        "output_tokens": output_tokens,
                        "cache_read_tokens": cache_read,
                        "cache_creation_tokens": cache_creation,
                    },
                )

        # Store message
        if hasattr(message, "content"):
            self.messages.append({"role": "assistant", "content": message.content})

        return {}

    async def on_pre_compact(
        self,
        input_data: dict[str, Any],
        tool_use_id: Optional[str],
        ctx: Any,
    ) -> dict[str, Any]:
        """Hook called before context window compaction.

        Args:
            input_data: Dict with 'trigger' and optional 'custom_instructions'
            tool_use_id: Not used for this hook
            ctx: Context object

        Returns:
            Empty dict (no modifications)
        """
        trigger = input_data.get("trigger", "unknown")
        custom_instructions = input_data.get("custom_instructions")

        # Record compaction metric
        model = self.metrics.get("model", "unknown")
        metrics.record_context_compaction(trigger, model)

        if self.session_span:
            self.session_span.add_event(
                "context.compaction",
                {
                    "trigger": trigger,
                    "has_custom_instructions": custom_instructions is not None,
                },
            )

        return {}

    def complete_session(self) -> None:
        """Complete and flush the telemetry session."""
        if not self.session_span:
            if self.config.debug:
                print("[claude-otel-sdk] Warning: No active session span")
            return

        # Calculate and record session duration
        session_duration_ms = (time.time() - self.metrics.get("start_time", 0)) * 1000
        self.session_span.set_attribute("session.duration_ms", session_duration_ms)

        # Set final attributes with semantic conventions
        self.session_span.set_attribute("gen_ai.response.model", self.metrics["model"])
        self.session_span.set_attribute("tools_used", self.metrics["tools_used"])

        if self.tools_used:
            self.session_span.set_attribute(
                "tool_names", ",".join(set(self.tools_used))
            )

        # Add completion event
        self.session_span.add_event("session.completed")

        # End span
        self.session_span.end()

        # Flush telemetry to backend
        tracer_provider = trace.get_tracer_provider()
        if hasattr(tracer_provider, "force_flush"):
            tracer_provider.force_flush()

        # Log summary if debug enabled
        if self.config.debug:
            duration = time.time() - self.metrics["start_time"]
            print(
                f"🎉 Session completed | "
                f"{self.metrics['input_tokens']} in, "
                f"{self.metrics['output_tokens']} out | "
                f"{self.metrics['tools_used']} tools | "
                f"{duration:.1f}s"
            )

        # Reset state
        self.session_span = None
        self.tool_spans = {}
        self.tool_start_times = {}
        self.metrics = {}
        self.messages = []
        self.tools_used = []
