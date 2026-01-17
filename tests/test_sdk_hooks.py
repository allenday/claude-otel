"""Unit tests for SDK-based hooks."""

import pytest
from unittest.mock import Mock, patch
import time

from claude_otel.sdk_hooks import SDKTelemetryHooks


class TestSDKTelemetryHooks:
    """Tests for SDKTelemetryHooks class."""

    @pytest.fixture
    def hooks(self):
        """Create hooks instance for testing."""
        with patch("claude_otel.sdk_hooks.get_config") as mock_config:
            mock_config.return_value = Mock(debug=False)
            return SDKTelemetryHooks()

    @pytest.mark.asyncio
    async def test_on_user_prompt_submit_creates_session_span(self, hooks):
        """UserPromptSubmit hook should create a session span."""
        input_data = {
            "prompt": "Hello, Claude!",
            "session_id": "test-session-123",
        }
        ctx = {
            "options": {
                "model": "claude-opus-4",
            }
        }

        # Call the hook
        result = await hooks.on_user_prompt_submit(input_data, None, ctx)

        # Should return empty dict
        assert result == {}

        # Should create a session span
        assert hooks.session_span is not None

        # Should initialize metrics
        assert hooks.metrics["prompt"] == "Hello, Claude!"
        assert hooks.metrics["model"] == "claude-opus-4"
        assert hooks.metrics["input_tokens"] == 0
        assert hooks.metrics["output_tokens"] == 0
        assert hooks.metrics["tools_used"] == 0
        assert hooks.metrics["turns"] == 0
        assert hooks.metrics["start_time"] > 0

        # Should store message
        assert len(hooks.messages) == 1
        assert hooks.messages[0]["role"] == "user"
        assert hooks.messages[0]["content"] == "Hello, Claude!"

    @pytest.mark.asyncio
    async def test_on_user_prompt_submit_handles_dict_context(self, hooks):
        """UserPromptSubmit should handle dict context."""
        input_data = {
            "prompt": "Test prompt",
            "session_id": "test-session",
        }
        ctx = {
            "options": {
                "model": "claude-sonnet-4",
            }
        }

        await hooks.on_user_prompt_submit(input_data, None, ctx)

        assert hooks.metrics["model"] == "claude-sonnet-4"

    @pytest.mark.asyncio
    async def test_on_user_prompt_submit_handles_object_context(self, hooks):
        """UserPromptSubmit should handle object context."""
        input_data = {
            "prompt": "Test prompt",
            "session_id": "test-session",
        }

        # Create mock object context
        mock_options = Mock()
        mock_options.model = "claude-haiku-4"
        mock_ctx = Mock()
        mock_ctx.options = mock_options

        await hooks.on_user_prompt_submit(input_data, None, mock_ctx)

        assert hooks.metrics["model"] == "claude-haiku-4"

    @pytest.mark.asyncio
    async def test_on_user_prompt_submit_handles_missing_model(self, hooks):
        """UserPromptSubmit should default to 'unknown' if model not provided."""
        input_data = {
            "prompt": "Test prompt",
            "session_id": "test-session",
        }
        ctx = {}

        await hooks.on_user_prompt_submit(input_data, None, ctx)

        assert hooks.metrics["model"] == "unknown"

    @pytest.mark.asyncio
    async def test_on_user_prompt_submit_truncates_long_prompt_for_span_title(self, hooks):
        """UserPromptSubmit should truncate long prompts for span title."""
        long_prompt = "x" * 200
        input_data = {
            "prompt": long_prompt,
            "session_id": "test-session",
        }
        ctx = {"options": {"model": "claude-opus-4"}}

        await hooks.on_user_prompt_submit(input_data, None, ctx)

        # Metrics should store full prompt
        assert hooks.metrics["prompt"] == long_prompt

    @pytest.mark.asyncio
    async def test_on_user_prompt_submit_sets_gen_ai_attributes(self, hooks):
        """UserPromptSubmit should set gen_ai.* semantic convention attributes."""
        input_data = {
            "prompt": "Test prompt",
            "session_id": "test-session-123",
        }
        ctx = {"options": {"model": "claude-sonnet-4"}}

        with patch.object(hooks.tracer, "start_span") as mock_start_span:
            mock_span = Mock()
            mock_start_span.return_value = mock_span

            await hooks.on_user_prompt_submit(input_data, None, ctx)

            # Check span was created with correct attributes
            mock_start_span.assert_called_once()
            call_args = mock_start_span.call_args

            # Check attributes
            attrs = call_args.kwargs["attributes"]
            assert attrs["gen_ai.system"] == "anthropic"
            assert attrs["gen_ai.request.model"] == "claude-sonnet-4"
            assert attrs["model"] == "claude-sonnet-4"
            assert attrs["session.id"] == "test-session-123"
            assert "prompt" in attrs

    @pytest.mark.asyncio
    async def test_on_pre_tool_use_creates_child_span_when_enabled(self, hooks):
        """PreToolUse should create child span when create_tool_spans is True."""
        # Initialize session first
        await hooks.on_user_prompt_submit(
            {"prompt": "test", "session_id": "s1"},
            None,
            {"options": {"model": "claude-opus-4"}},
        )

        input_data = {
            "tool_name": "Bash",
            "tool_input": {"command": "ls -la"},
        }
        tool_use_id = "tool_123"

        with patch.object(hooks.tracer, "start_span") as mock_start_span:
            mock_span = Mock()
            mock_start_span.return_value = mock_span

            result = await hooks.on_pre_tool_use(input_data, tool_use_id, None)

            assert result == {}
            assert hooks.metrics["tools_used"] == 1
            assert "Bash" in hooks.tools_used

            # Should create child span
            assert tool_use_id in hooks.tool_spans

    @pytest.mark.asyncio
    async def test_on_pre_tool_use_adds_event_when_spans_disabled(self):
        """PreToolUse should add event when create_tool_spans is False."""
        with patch("claude_otel.sdk_hooks.get_config") as mock_config:
            mock_config.return_value = Mock(debug=False)
            hooks = SDKTelemetryHooks(create_tool_spans=False)

        # Initialize session
        await hooks.on_user_prompt_submit(
            {"prompt": "test", "session_id": "s1"},
            None,
            {"options": {"model": "claude-opus-4"}},
        )

        input_data = {
            "tool_name": "Read",
            "tool_input": {"file_path": "/test.txt"},
        }

        with patch.object(hooks.session_span, "add_event") as mock_add_event:
            await hooks.on_pre_tool_use(input_data, "tool_456", None)

            # Should add event instead of creating span
            mock_add_event.assert_called_once()
            assert "Read" in mock_add_event.call_args[0][0]

    @pytest.mark.asyncio
    async def test_on_message_complete_updates_token_counts(self, hooks):
        """MessageComplete should update cumulative token counts."""
        # Initialize session
        await hooks.on_user_prompt_submit(
            {"prompt": "test", "session_id": "s1"},
            None,
            {"options": {"model": "claude-opus-4"}},
        )

        # Create mock message with usage
        mock_usage = Mock()
        mock_usage.input_tokens = 100
        mock_usage.output_tokens = 50
        mock_usage.cache_read_input_tokens = 200
        mock_usage.cache_creation_input_tokens = 25

        mock_message = Mock()
        mock_message.usage = mock_usage
        mock_message.content = "Response text"

        # Call hook
        result = await hooks.on_message_complete(mock_message, None)

        assert result == {}
        assert hooks.metrics["input_tokens"] == 100
        assert hooks.metrics["output_tokens"] == 50
        assert hooks.metrics["cache_read_input_tokens"] == 200
        assert hooks.metrics["cache_creation_input_tokens"] == 25
        assert hooks.metrics["turns"] == 1

    @pytest.mark.asyncio
    async def test_on_message_complete_accumulates_tokens(self, hooks):
        """MessageComplete should accumulate token counts across turns."""
        # Initialize session
        await hooks.on_user_prompt_submit(
            {"prompt": "test", "session_id": "s1"},
            None,
            {"options": {"model": "claude-opus-4"}},
        )

        # First turn
        mock_usage1 = Mock()
        mock_usage1.input_tokens = 100
        mock_usage1.output_tokens = 50
        mock_usage1.cache_read_input_tokens = 0
        mock_usage1.cache_creation_input_tokens = 0
        mock_message1 = Mock()
        mock_message1.usage = mock_usage1
        mock_message1.content = "Response 1"

        await hooks.on_message_complete(mock_message1, None)

        # Second turn
        mock_usage2 = Mock()
        mock_usage2.input_tokens = 150
        mock_usage2.output_tokens = 75
        mock_usage2.cache_read_input_tokens = 100
        mock_usage2.cache_creation_input_tokens = 10
        mock_message2 = Mock()
        mock_message2.usage = mock_usage2
        mock_message2.content = "Response 2"

        await hooks.on_message_complete(mock_message2, None)

        # Should accumulate
        assert hooks.metrics["input_tokens"] == 250
        assert hooks.metrics["output_tokens"] == 125
        assert hooks.metrics["cache_read_input_tokens"] == 100
        assert hooks.metrics["cache_creation_input_tokens"] == 10
        assert hooks.metrics["turns"] == 2

    @pytest.mark.asyncio
    async def test_on_pre_compact_adds_event(self, hooks):
        """PreCompact should add compaction event to session span."""
        # Initialize session
        await hooks.on_user_prompt_submit(
            {"prompt": "test", "session_id": "s1"},
            None,
            {"options": {"model": "claude-opus-4"}},
        )

        input_data = {
            "trigger": "max_tokens",
            "custom_instructions": "Keep important context",
        }

        with patch.object(hooks.session_span, "add_event") as mock_add_event:
            result = await hooks.on_pre_compact(input_data, None, None)

            assert result == {}
            mock_add_event.assert_called_once()
            call_args = mock_add_event.call_args
            assert "compaction" in call_args[0][0]
            # Event data is in args[1], not kwargs
            event_data = call_args[0][1]
            assert event_data["trigger"] == "max_tokens"
            assert event_data["has_custom_instructions"] is True

    def test_complete_session_ends_span(self, hooks):
        """complete_session should end the session span."""
        # Set up mock span and initialized metrics
        mock_span = Mock()
        hooks.session_span = mock_span
        hooks.metrics = {
            "model": "claude-opus-4",
            "start_time": time.time(),
            "tools_used": 0,
        }
        hooks.tools_used = []

        hooks.complete_session()

        mock_span.end.assert_called_once()

    def test_complete_session_resets_state(self, hooks):
        """complete_session should reset internal state."""
        # Set up state with all required keys for complete_session
        hooks.session_span = Mock()
        hooks.metrics = {
            "prompt": "test",
            "model": "claude-opus-4",
            "start_time": time.time(),
            "tools_used": 1,
        }
        hooks.messages = [{"role": "user", "content": "test"}]
        hooks.tools_used = ["Bash"]

        hooks.complete_session()

        # Should reset
        assert hooks.session_span is None
        assert hooks.metrics == {}
        assert hooks.messages == []
        assert hooks.tools_used == []

    def test_complete_session_sets_duration_attribute(self, hooks):
        """complete_session should set session.duration_ms attribute."""
        # Set up mock span with initialized metrics
        mock_span = Mock()
        hooks.session_span = mock_span
        start_time = time.time()
        hooks.metrics = {
            "model": "claude-opus-4",
            "start_time": start_time,
            "tools_used": 0,
        }
        hooks.tools_used = []

        # Wait a bit to ensure duration > 0
        time.sleep(0.01)

        hooks.complete_session()

        # Should set session.duration_ms attribute
        set_attribute_calls = [call for call in mock_span.set_attribute.call_args_list
                               if call[0][0] == "session.duration_ms"]
        assert len(set_attribute_calls) == 1
        duration_ms = set_attribute_calls[0][0][1]
        # Duration should be > 0 and reasonable (less than 1 second for this test)
        assert duration_ms > 0
        assert duration_ms < 1000

    @pytest.mark.asyncio
    async def test_on_pre_tool_use_records_start_time(self, hooks):
        """PreToolUse should record start time for duration tracking."""
        # Initialize session
        await hooks.on_user_prompt_submit(
            {"prompt": "test", "session_id": "s1"},
            None,
            {"options": {"model": "claude-opus-4"}},
        )

        input_data = {
            "tool_name": "Bash",
            "tool_input": {"command": "ls"},
        }
        tool_use_id = "tool_123"

        result = await hooks.on_pre_tool_use(input_data, tool_use_id, None)

        assert result == {}
        # Should record start time
        assert tool_use_id in hooks.tool_start_times
        assert isinstance(hooks.tool_start_times[tool_use_id], float)

    @pytest.mark.asyncio
    async def test_on_post_tool_use_calculates_duration(self, hooks):
        """PostToolUse should calculate duration and add to span."""
        # Initialize session
        await hooks.on_user_prompt_submit(
            {"prompt": "test", "session_id": "s1"},
            None,
            {"options": {"model": "claude-opus-4"}},
        )

        # Start tool (records start time)
        tool_use_id = "tool_123"
        await hooks.on_pre_tool_use(
            {"tool_name": "Bash", "tool_input": {"command": "ls"}},
            tool_use_id,
            None,
        )

        # Simulate some delay
        time.sleep(0.01)  # 10ms

        # Complete tool
        input_data = {
            "tool_name": "Bash",
            "tool_response": {"stdout": "file1.txt\nfile2.txt"},
        }

        with patch.object(hooks.tool_spans[tool_use_id], "set_attribute") as mock_set_attr:
            result = await hooks.on_post_tool_use(input_data, tool_use_id, None)

            assert result == {}
            # Should have set duration attributes
            duration_calls = [
                call for call in mock_set_attr.call_args_list
                if "duration_ms" in str(call)
            ]
            assert len(duration_calls) >= 2  # tool.duration_ms and duration_ms

            # Duration should be > 0 (we slept for 10ms)
            for call in duration_calls:
                if call[0][0] in ("tool.duration_ms", "duration_ms"):
                    duration = call[0][1]
                    assert duration > 0

    @pytest.mark.asyncio
    async def test_on_post_tool_use_cleans_up_start_time(self, hooks):
        """PostToolUse should clean up start time after calculation."""
        # Initialize session
        await hooks.on_user_prompt_submit(
            {"prompt": "test", "session_id": "s1"},
            None,
            {"options": {"model": "claude-opus-4"}},
        )

        # Start and complete tool
        tool_use_id = "tool_123"
        await hooks.on_pre_tool_use(
            {"tool_name": "Bash", "tool_input": {"command": "ls"}},
            tool_use_id,
            None,
        )

        assert tool_use_id in hooks.tool_start_times

        await hooks.on_post_tool_use(
            {"tool_name": "Bash", "tool_response": {"stdout": "output"}},
            tool_use_id,
            None,
        )

        # Start time should be cleaned up
        assert tool_use_id not in hooks.tool_start_times

    @pytest.mark.asyncio
    async def test_on_post_tool_use_records_metric(self, hooks):
        """PostToolUse should record tool call metric with duration."""
        # Initialize session
        await hooks.on_user_prompt_submit(
            {"prompt": "test", "session_id": "s1"},
            None,
            {"options": {"model": "claude-opus-4"}},
        )

        # Start tool
        tool_use_id = "tool_123"
        await hooks.on_pre_tool_use(
            {"tool_name": "Read", "tool_input": {"file_path": "/test.txt"}},
            tool_use_id,
            None,
        )

        # Complete tool
        with patch("claude_otel.sdk_hooks.metrics.record_tool_call") as mock_record:
            await hooks.on_post_tool_use(
                {"tool_name": "Read", "tool_response": "file contents"},
                tool_use_id,
                None,
            )

            # Should record metric with tool name, duration, and error status
            mock_record.assert_called_once()
            args = mock_record.call_args[0]
            assert args[0] == "Read"  # tool_name
            assert isinstance(args[1], float)  # duration_ms
            assert args[1] >= 0  # duration should be non-negative
            assert args[2] is False  # has_error

    @pytest.mark.asyncio
    async def test_on_post_tool_use_records_error_metric(self, hooks):
        """PostToolUse should record error metric for failed tools."""
        # Initialize session
        await hooks.on_user_prompt_submit(
            {"prompt": "test", "session_id": "s1"},
            None,
            {"options": {"model": "claude-opus-4"}},
        )

        # Start tool
        tool_use_id = "tool_456"
        await hooks.on_pre_tool_use(
            {"tool_name": "Bash", "tool_input": {"command": "invalid"}},
            tool_use_id,
            None,
        )

        # Complete tool with error
        with patch("claude_otel.sdk_hooks.metrics.record_tool_call") as mock_record:
            await hooks.on_post_tool_use(
                {
                    "tool_name": "Bash",
                    "tool_response": {"error": "Command not found", "isError": True},
                },
                tool_use_id,
                None,
            )

            # Should record metric with error=True
            mock_record.assert_called_once()
            args = mock_record.call_args[0]
            assert args[0] == "Bash"
            assert args[2] is True  # has_error

    @pytest.mark.asyncio
    async def test_complete_session_resets_tool_start_times(self, hooks):
        """complete_session should reset tool start times."""
        # Set up state
        hooks.session_span = Mock()
        hooks.metrics = {"model": "test", "start_time": time.time(), "tools_used": 0}
        hooks.tools_used = []
        hooks.tool_start_times = {"tool_1": time.time(), "tool_2": time.time()}

        hooks.complete_session()

        # Should reset tool_start_times
        assert hooks.tool_start_times == {}

    @pytest.mark.asyncio
    async def test_on_post_tool_use_emits_log_when_logger_provided(self):
        """PostToolUse should emit a log entry when logger is provided."""
        # Create mock logger
        mock_logger = Mock()

        # Create hooks with logger
        with patch("claude_otel.sdk_hooks.get_config") as mock_config:
            mock_config.return_value = Mock(debug=False)
            hooks = SDKTelemetryHooks(logger=mock_logger)

        # Initialize session
        await hooks.on_user_prompt_submit(
            {"prompt": "test", "session_id": "s1"},
            None,
            {"options": {"model": "claude-opus-4"}},
        )

        # Start and complete tool
        tool_use_id = "tool_123"
        await hooks.on_pre_tool_use(
            {"tool_name": "Read", "tool_input": {"file_path": "/test.txt"}},
            tool_use_id,
            None,
        )

        await hooks.on_post_tool_use(
            {"tool_name": "Read", "tool_response": "file contents"},
            tool_use_id,
            None,
        )

        # Should emit info log with tool metadata
        mock_logger.info.assert_called_once()
        call_args = mock_logger.info.call_args
        assert "Tool call completed: Read" in call_args[0][0]
        assert "tool.name" in call_args[1]["extra"]
        assert call_args[1]["extra"]["tool.name"] == "Read"
        assert "tool.duration_ms" in call_args[1]["extra"]
        assert "tool.status" in call_args[1]["extra"]
        assert call_args[1]["extra"]["tool.status"] == "success"

    @pytest.mark.asyncio
    async def test_on_post_tool_use_emits_warning_log_for_errors(self):
        """PostToolUse should emit warning log for failed tools."""
        # Create mock logger
        mock_logger = Mock()

        # Create hooks with logger
        with patch("claude_otel.sdk_hooks.get_config") as mock_config:
            mock_config.return_value = Mock(debug=False)
            hooks = SDKTelemetryHooks(logger=mock_logger)

        # Initialize session
        await hooks.on_user_prompt_submit(
            {"prompt": "test", "session_id": "s1"},
            None,
            {"options": {"model": "claude-opus-4"}},
        )

        # Start and complete tool with error
        tool_use_id = "tool_123"
        await hooks.on_pre_tool_use(
            {"tool_name": "Bash", "tool_input": {"command": "fail"}},
            tool_use_id,
            None,
        )

        await hooks.on_post_tool_use(
            {"tool_name": "Bash", "tool_response": {"error": "Command failed", "isError": True}},
            tool_use_id,
            None,
        )

        # Should emit warning log with error metadata
        mock_logger.warning.assert_called_once()
        call_args = mock_logger.warning.call_args
        assert "Tool call failed: Bash" in call_args[0][0]
        assert "tool.name" in call_args[1]["extra"]
        assert call_args[1]["extra"]["tool.name"] == "Bash"
        assert "tool.status" in call_args[1]["extra"]
        assert call_args[1]["extra"]["tool.status"] == "error"
        assert "tool.error" in call_args[1]["extra"]

    @pytest.mark.asyncio
    async def test_on_post_tool_use_no_log_when_logger_not_provided(self, hooks):
        """PostToolUse should not emit logs when logger is not provided."""
        # hooks fixture has no logger
        assert hooks.logger is None

        # Initialize session
        await hooks.on_user_prompt_submit(
            {"prompt": "test", "session_id": "s1"},
            None,
            {"options": {"model": "claude-opus-4"}},
        )

        # Start and complete tool
        tool_use_id = "tool_123"
        await hooks.on_pre_tool_use(
            {"tool_name": "Read", "tool_input": {"file_path": "/test.txt"}},
            tool_use_id,
            None,
        )

        # Should not raise an error even without logger
        await hooks.on_post_tool_use(
            {"tool_name": "Read", "tool_response": "file contents"},
            tool_use_id,
            None,
        )
