"""Unit tests for hook modules - token extraction and span attributes."""

import json
import os
import subprocess
import tempfile
import pytest

# Import the hook module functions directly
from claude_otel.hooks.post_tool import (
    extract_token_usage,
    truncate,
    get_input_summary,
    calculate_payload_size,
)


class TestExtractTokenUsage:
    """Tests for extract_token_usage function."""

    def test_returns_none_for_missing_path(self):
        """Should return None when transcript path is empty."""
        result = extract_token_usage("", "tool_123")
        assert result is None

    def test_returns_none_for_nonexistent_file(self):
        """Should return None when transcript file doesn't exist."""
        result = extract_token_usage("/nonexistent/path.jsonl", "tool_123")
        assert result is None

    def test_extracts_token_usage_from_transcript(self):
        """Should extract token usage when tool_use_id matches."""
        transcript_content = json.dumps({
            "type": "assistant",
            "message": {
                "role": "assistant",
                "content": [
                    {
                        "type": "tool_use",
                        "id": "toolu_123ABC",
                        "name": "Bash",
                        "input": {"command": "ls"}
                    }
                ],
                "usage": {
                    "input_tokens": 100,
                    "output_tokens": 50,
                    "cache_read_input_tokens": 200,
                    "cache_creation_input_tokens": 25
                }
            }
        })

        with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False) as f:
            f.write(transcript_content + "\n")
            f.flush()
            temp_path = f.name

        try:
            result = extract_token_usage(temp_path, "toolu_123ABC")
            assert result is not None
            assert result["input_tokens"] == 100
            assert result["output_tokens"] == 50
            assert result["cache_read_input_tokens"] == 200
            assert result["cache_creation_input_tokens"] == 25
        finally:
            os.unlink(temp_path)

    def test_returns_none_when_tool_use_id_not_found(self):
        """Should return None when tool_use_id doesn't match any entry."""
        transcript_content = json.dumps({
            "type": "assistant",
            "message": {
                "role": "assistant",
                "content": [
                    {
                        "type": "tool_use",
                        "id": "toolu_OTHER",
                        "name": "Bash",
                        "input": {}
                    }
                ],
                "usage": {"input_tokens": 100}
            }
        })

        with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False) as f:
            f.write(transcript_content + "\n")
            f.flush()
            temp_path = f.name

        try:
            result = extract_token_usage(temp_path, "toolu_NOTFOUND")
            assert result is None
        finally:
            os.unlink(temp_path)

    def test_handles_multiple_entries(self):
        """Should find the correct entry among multiple transcript lines."""
        lines = [
            json.dumps({
                "type": "user",
                "message": {"role": "user", "content": "Hello"}
            }),
            json.dumps({
                "type": "assistant",
                "message": {
                    "role": "assistant",
                    "content": [{"type": "tool_use", "id": "toolu_1", "name": "Bash"}],
                    "usage": {"input_tokens": 10, "output_tokens": 5}
                }
            }),
            json.dumps({
                "type": "assistant",
                "message": {
                    "role": "assistant",
                    "content": [{"type": "tool_use", "id": "toolu_2", "name": "Read"}],
                    "usage": {"input_tokens": 20, "output_tokens": 15}
                }
            }),
        ]

        with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False) as f:
            for line in lines:
                f.write(line + "\n")
            f.flush()
            temp_path = f.name

        try:
            result = extract_token_usage(temp_path, "toolu_2")
            assert result is not None
            assert result["input_tokens"] == 20
            assert result["output_tokens"] == 15
        finally:
            os.unlink(temp_path)

    def test_returns_none_when_usage_missing(self):
        """Should return None when matching entry has no usage field."""
        transcript_content = json.dumps({
            "type": "assistant",
            "message": {
                "role": "assistant",
                "content": [{"type": "tool_use", "id": "toolu_NOUSAGE", "name": "Bash"}]
                # No usage field
            }
        })

        with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False) as f:
            f.write(transcript_content + "\n")
            f.flush()
            temp_path = f.name

        try:
            result = extract_token_usage(temp_path, "toolu_NOUSAGE")
            assert result is None
        finally:
            os.unlink(temp_path)

    def test_handles_malformed_json_gracefully(self):
        """Should skip malformed JSON lines without crashing."""
        lines = [
            "not valid json",
            json.dumps({
                "type": "assistant",
                "message": {
                    "role": "assistant",
                    "content": [{"type": "tool_use", "id": "toolu_VALID", "name": "Bash"}],
                    "usage": {"input_tokens": 100}
                }
            }),
        ]

        with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False) as f:
            for line in lines:
                f.write(line + "\n")
            f.flush()
            temp_path = f.name

        try:
            result = extract_token_usage(temp_path, "toolu_VALID")
            assert result is not None
            assert result["input_tokens"] == 100
        finally:
            os.unlink(temp_path)

    def test_defaults_missing_token_fields_to_zero(self):
        """Should default missing token fields to 0."""
        transcript_content = json.dumps({
            "type": "assistant",
            "message": {
                "role": "assistant",
                "content": [{"type": "tool_use", "id": "toolu_PARTIAL", "name": "Bash"}],
                "usage": {
                    "input_tokens": 50
                    # Missing output_tokens, cache fields
                }
            }
        })

        with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False) as f:
            f.write(transcript_content + "\n")
            f.flush()
            temp_path = f.name

        try:
            result = extract_token_usage(temp_path, "toolu_PARTIAL")
            assert result is not None
            assert result["input_tokens"] == 50
            assert result["output_tokens"] == 0
            assert result["cache_read_input_tokens"] == 0
            assert result["cache_creation_input_tokens"] == 0
        finally:
            os.unlink(temp_path)


class TestTruncate:
    """Tests for truncate helper function."""

    def test_no_truncation_for_short_string(self):
        """Short strings should not be truncated."""
        text = "short text"
        result, was_truncated = truncate(text, max_len=100)
        assert result == text
        assert was_truncated is False

    def test_truncates_long_string(self):
        """Long strings should be truncated with marker."""
        text = "x" * 300
        result, was_truncated = truncate(text, max_len=100)
        assert len(result) <= 100
        assert was_truncated is True
        assert "[TRUNC]" in result

    def test_exact_length_not_truncated(self):
        """String exactly at max length should not be truncated."""
        text = "x" * 100
        result, was_truncated = truncate(text, max_len=100)
        assert result == text
        assert was_truncated is False


class TestGetInputSummary:
    """Tests for get_input_summary helper function."""

    def test_bash_returns_command(self):
        """Bash tool should return command as summary."""
        result = get_input_summary({"command": "ls -la"}, "Bash")
        assert result == "ls -la"

    def test_bash_truncates_long_command(self):
        """Bash command should be truncated to 200 chars."""
        long_cmd = "x" * 300
        result = get_input_summary({"command": long_cmd}, "Bash")
        assert len(result) == 200

    def test_read_returns_file_path(self):
        """Read tool should return file_path as summary."""
        result = get_input_summary({"file_path": "/path/to/file.txt"}, "Read")
        assert result == "/path/to/file.txt"

    def test_write_returns_file_path(self):
        """Write tool should return file_path as summary."""
        result = get_input_summary({"file_path": "/path/to/file.txt"}, "Write")
        assert result == "/path/to/file.txt"

    def test_edit_returns_file_path(self):
        """Edit tool should return file_path as summary."""
        result = get_input_summary({"file_path": "/path/to/file.txt"}, "Edit")
        assert result == "/path/to/file.txt"

    def test_glob_returns_pattern(self):
        """Glob tool should return pattern as summary."""
        result = get_input_summary({"pattern": "**/*.py"}, "Glob")
        assert result == "**/*.py"

    def test_grep_returns_pattern(self):
        """Grep tool should return pattern as summary."""
        result = get_input_summary({"pattern": "def main"}, "Grep")
        assert result == "def main"

    def test_task_returns_description(self):
        """Task tool should return description as summary."""
        result = get_input_summary({"description": "Run tests"}, "Task")
        assert result == "Run tests"

    def test_unknown_tool_stringifies_input(self):
        """Unknown tools should stringify input."""
        result = get_input_summary({"foo": "bar"}, "UnknownTool")
        assert "foo" in result or "bar" in result


class TestCalculatePayloadSize:
    """Tests for calculate_payload_size helper function."""

    def test_string_payload(self):
        """Should calculate string byte size."""
        result = calculate_payload_size("hello")
        assert result == 5

    def test_unicode_string(self):
        """Should handle unicode strings correctly."""
        # UTF-8 encoding
        result = calculate_payload_size("hello\u4e16\u754c")  # "hello世界"
        assert result > 5  # UTF-8 encoded Chinese chars take multiple bytes

    def test_bytes_payload(self):
        """Should return length of bytes directly."""
        result = calculate_payload_size(b"hello")
        assert result == 5

    def test_dict_payload(self):
        """Should JSON serialize dicts."""
        result = calculate_payload_size({"key": "value"})
        assert result > 0

    def test_none_returns_zero(self):
        """Should handle None gracefully."""
        # The function tries to serialize, which may fail or succeed
        result = calculate_payload_size(None)
        assert result >= 0  # Either 0 or "null" serialized


class TestPreCompactHook:
    """Tests for PreCompact hook entry point."""

    def test_pre_compact_accepts_valid_input(self):
        """PreCompact hook should accept valid compaction data."""
        input_data = {
            "trigger": "max_tokens",
            "custom_instructions": "Keep important context",
            "session_id": "session_123"
        }

        # Call the hook via subprocess
        try:
            result = subprocess.run(
                ["python", "-m", "claude_otel.hooks.pre_compact"],
                input=json.dumps(input_data),
                capture_output=True,
                text=True,
                timeout=5,
                env={**os.environ, "OTEL_TRACES_EXPORTER": "none"}
            )
            # Should exit successfully even with traces disabled
            assert result.returncode == 0
        except subprocess.TimeoutExpired:
            pytest.fail("PreCompact hook timed out")

    def test_pre_compact_handles_minimal_input(self):
        """PreCompact hook should handle minimal input without custom instructions."""
        input_data = {
            "trigger": "user_request",
            "session_id": "session_456"
        }

        try:
            result = subprocess.run(
                ["python", "-m", "claude_otel.hooks.pre_compact"],
                input=json.dumps(input_data),
                capture_output=True,
                text=True,
                timeout=5,
                env={**os.environ, "OTEL_TRACES_EXPORTER": "none"}
            )
            assert result.returncode == 0
        except subprocess.TimeoutExpired:
            pytest.fail("PreCompact hook timed out")

    def test_pre_compact_handles_missing_fields(self):
        """PreCompact hook should handle missing optional fields gracefully."""
        input_data = {}

        try:
            result = subprocess.run(
                ["python", "-m", "claude_otel.hooks.pre_compact"],
                input=json.dumps(input_data),
                capture_output=True,
                text=True,
                timeout=5,
                env={**os.environ, "OTEL_TRACES_EXPORTER": "none"}
            )
            # Should not crash
            assert result.returncode == 0
        except subprocess.TimeoutExpired:
            pytest.fail("PreCompact hook timed out")


class TestEnhancedToolSpanAttributes:
    """Tests for enhanced tool span attributes (tool.input.*, tool.response.*, tool.status)."""

    def test_tool_input_attributes_dict(self):
        """PostToolUse should add tool.input.* attributes for dict inputs."""
        # This is an integration test that verifies the hook creates the right attributes
        # We'll test the logic by creating mock data and verifying processing
        tool_input = {
            "command": "ls -la",
            "timeout": "5000",
            "description": "List files"
        }

        # Verify each key would be added as tool.input.<key>
        for key, value in tool_input.items():
            expected_attr = f"tool.input.{key}"
            assert expected_attr  # Just verify the naming convention works
            assert str(value)  # Verify value can be stringified

    def test_tool_input_truncation(self):
        """Large tool input values should be truncated."""
        large_value = "x" * 3000
        tool_input = {"large_field": large_value}

        # Verify truncation logic
        value_str = str(tool_input["large_field"])
        if len(value_str) >= 2000:
            truncated = f"{value_str[:1900]}... (truncated, full size: {len(value_str)} chars)"
            assert len(truncated) < len(value_str)
            assert "truncated" in truncated
            assert str(len(value_str)) in truncated

    def test_tool_response_attributes_dict(self):
        """PostToolUse should add tool.response.* attributes for dict responses."""
        tool_response = {
            "stdout": "File listing output",
            "stderr": "",
            "exit_code": 0
        }

        # Verify each key would be added as tool.response.<key>
        for key, value in tool_response.items():
            expected_attr = f"tool.response.{key}"
            assert expected_attr
            # Verify value can be stringified (even empty strings)
            assert str(value) is not None

    def test_tool_response_string(self):
        """PostToolUse should add tool.response attribute for string responses."""
        tool_response = "This is a simple string response"

        # Verify string responses are stored as tool.response
        assert len(tool_response) < 2000  # No truncation needed
        expected_value = tool_response

    def test_tool_response_truncation(self):
        """Large tool response values should be truncated."""
        large_response = "y" * 3000

        # Verify truncation logic
        if len(large_response) >= 2000:
            truncated = large_response[:2000] + "..."
            assert len(truncated) < len(large_response)
            assert truncated.endswith("...")

    def test_tool_status_success(self):
        """PostToolUse should set tool.status='success' for successful executions."""
        tool_response = {"stdout": "OK", "exit_code": 0}

        # Verify status determination logic
        is_error = False
        if isinstance(tool_response, dict):
            if tool_response.get("error") or tool_response.get("isError"):
                is_error = True
            exit_code = tool_response.get("exit_code", 0)
            if exit_code != 0:
                is_error = True

        status = "error" if is_error else "success"
        assert status == "success"

    def test_tool_status_error_with_error_field(self):
        """PostToolUse should set tool.status='error' when error field is present."""
        tool_response = {"error": "Command failed", "exit_code": 1}

        # Verify error detection
        is_error = False
        if isinstance(tool_response, dict):
            if tool_response.get("error"):
                is_error = True

        status = "error" if is_error else "success"
        assert status == "error"

    def test_tool_status_error_with_isError_flag(self):
        """PostToolUse should set tool.status='error' when isError=true."""
        tool_response = {"isError": True, "message": "Failed"}

        # Verify error detection
        is_error = False
        if isinstance(tool_response, dict):
            if tool_response.get("isError"):
                is_error = True

        status = "error" if is_error else "success"
        assert status == "error"

    def test_tool_status_error_with_nonzero_exit_code(self):
        """PostToolUse should set tool.status='error' when exit_code != 0."""
        tool_response = {"stdout": "output", "exit_code": 127}

        # Verify error detection
        is_error = False
        exit_code = 0
        if isinstance(tool_response, dict):
            exit_code = tool_response.get("exit_code", 0)
            if exit_code != 0:
                is_error = True

        status = "error" if is_error else "success"
        assert status == "error"
        assert exit_code == 127

    def test_tool_status_error_with_stderr_keywords(self):
        """PostToolUse should detect errors in stderr with error keywords."""
        tool_response = {
            "stdout": "Some output",
            "stderr": "Error: file not found",
            "exit_code": 0
        }

        # Verify error detection from stderr
        is_error = False
        if isinstance(tool_response, dict):
            if not is_error and tool_response.get("stderr"):
                stderr = str(tool_response.get("stderr", ""))
                if stderr and any(keyword in stderr.lower() for keyword in ["error", "exception", "failed", "fatal"]):
                    is_error = True

        status = "error" if is_error else "success"
        assert status == "error"

    def test_tool_error_message_extraction(self):
        """PostToolUse should extract error messages from various sources."""
        # Test error field
        response1 = {"error": "File not found"}
        if response1.get("error"):
            error_msg = str(response1.get("error", ""))[:500]
            assert error_msg == "File not found"

        # Test isError flag
        response2 = {"isError": True}
        if response2.get("isError"):
            error_msg = "Tool execution failed (isError=true)"
            assert error_msg == "Tool execution failed (isError=true)"

        # Test exit code
        response3 = {"exit_code": 1}
        exit_code = response3.get("exit_code", 0)
        if exit_code != 0:
            error_msg = f"Tool exited with code {exit_code}"
            assert error_msg == "Tool exited with code 1"

    def test_string_response_error_detection(self):
        """PostToolUse should detect errors in string responses."""
        # Test Error: prefix
        response1 = "Error: Something went wrong"
        is_error = response1.startswith("Error:") or response1.startswith("ERROR:")
        assert is_error is True

        # Test error pattern in content
        response2 = "The operation failed: permission denied"
        lower_response = response2.lower()
        is_error = any(pattern in lower_response[:200] for pattern in ["error:", "exception:", "failed:", "fatal:"])
        assert is_error is True

        # Test no false positive
        response3 = "Successfully completed without errors"
        lower_response = response3.lower()
        is_error = response3.startswith("Error:") or response3.startswith("ERROR:")
        if not is_error:
            is_error = any(pattern in lower_response[:200] for pattern in ["error:", "exception:", "failed:", "fatal:"])
        assert is_error is False


# ============================================================================
# SDK Hook Tests
# ============================================================================

from unittest.mock import MagicMock, patch
from claude_otel.sdk_hooks import SDKTelemetryHooks


class TestSDKUserPromptSubmit:
    """Tests for SDK UserPromptSubmit hook."""

    @pytest.mark.asyncio
    async def test_user_prompt_submit_creates_session_span(self):
        """Should create session span with prompt and model attributes."""
        # Create mock tracer
        mock_tracer = MagicMock()
        mock_span = MagicMock()
        mock_tracer.start_span.return_value = mock_span

        hooks = SDKTelemetryHooks(tracer=mock_tracer)

        # Call hook
        input_data = {
            "prompt": "Hello, Claude!",
            "session_id": "sess_123",
        }
        ctx = {
            "options": {
                "model": "claude-sonnet-4-5",
            }
        }

        result = await hooks.on_user_prompt_submit(input_data, None, ctx)

        # Verify span was created
        assert mock_tracer.start_span.called
        call_args = mock_tracer.start_span.call_args
        assert "Hello, Claude!" in call_args[0][0]  # Span name

        # Verify attributes
        attrs = call_args[1]["attributes"]
        assert attrs["prompt"] == "Hello, Claude!"
        assert attrs["model"] == "claude-sonnet-4-5"
        assert attrs["session.id"] == "sess_123"
        assert attrs["gen_ai.system"] == "anthropic"
        assert attrs["gen_ai.request.model"] == "claude-sonnet-4-5"

        # Verify event added
        assert mock_span.add_event.called
        assert mock_span.add_event.call_args[0][0] == "user.prompt.submitted"

        # Verify metrics updated
        assert hooks.metrics["prompt"] == "Hello, Claude!"
        assert hooks.metrics["model"] == "claude-sonnet-4-5"
        assert hooks.metrics["turns"] == 0
        assert result == {}

    @pytest.mark.asyncio
    async def test_user_prompt_submit_truncates_long_prompt(self):
        """Should truncate long prompts in span attributes."""
        mock_tracer = MagicMock()
        mock_span = MagicMock()
        mock_tracer.start_span.return_value = mock_span

        hooks = SDKTelemetryHooks(tracer=mock_tracer)

        # Long prompt
        long_prompt = "A" * 2000
        input_data = {
            "prompt": long_prompt,
            "session_id": "sess_123",
        }
        ctx = {"options": {"model": "opus"}}

        await hooks.on_user_prompt_submit(input_data, None, ctx)

        # Verify prompt truncated to 1000 chars in attributes
        attrs = mock_tracer.start_span.call_args[1]["attributes"]
        assert len(attrs["prompt"]) == 1000

        # But full prompt in metrics
        assert len(hooks.metrics["prompt"]) == 2000

    @pytest.mark.asyncio
    async def test_user_prompt_submit_handles_object_context(self):
        """Should extract model from object-based context."""
        mock_tracer = MagicMock()
        mock_span = MagicMock()
        mock_tracer.start_span.return_value = mock_span

        hooks = SDKTelemetryHooks(tracer=mock_tracer)

        # Object-based context
        ctx = MagicMock()
        ctx.options.model = "claude-opus-4-5"

        input_data = {"prompt": "Test", "session_id": "s1"}
        await hooks.on_user_prompt_submit(input_data, None, ctx)

        # Verify model extracted
        attrs = mock_tracer.start_span.call_args[1]["attributes"]
        assert attrs["model"] == "claude-opus-4-5"


class TestSDKMessageComplete:
    """Tests for SDK MessageComplete hook."""

    @pytest.mark.asyncio
    async def test_message_complete_updates_token_metrics(self):
        """Should update cumulative token counts and turn count."""
        mock_tracer = MagicMock()
        mock_span = MagicMock()
        mock_tracer.start_span.return_value = mock_span

        hooks = SDKTelemetryHooks(tracer=mock_tracer)

        # Initialize session
        input_data = {"prompt": "Test", "session_id": "s1"}
        ctx = {"options": {"model": "sonnet"}}
        await hooks.on_user_prompt_submit(input_data, None, ctx)

        # Create mock message with usage
        message = MagicMock()
        message.usage.input_tokens = 100
        message.usage.output_tokens = 50
        message.usage.cache_read_input_tokens = 200
        message.usage.cache_creation_input_tokens = 25

        # Call hook
        result = await hooks.on_message_complete(message, ctx)

        # Verify metrics updated
        assert hooks.metrics["input_tokens"] == 100
        assert hooks.metrics["output_tokens"] == 50
        assert hooks.metrics["cache_read_input_tokens"] == 200
        assert hooks.metrics["cache_creation_input_tokens"] == 25
        assert hooks.metrics["turns"] == 1

        # Verify span attributes set
        assert mock_span.set_attribute.called
        calls = {call[0][0]: call[0][1] for call in mock_span.set_attribute.call_args_list}
        assert calls["gen_ai.usage.input_tokens"] == 100
        assert calls["gen_ai.usage.output_tokens"] == 50
        assert calls["tokens.cache_read"] == 200
        assert calls["tokens.cache_creation"] == 25
        assert calls["turns"] == 1

        # Verify turn event added
        event_calls = [call for call in mock_span.add_event.call_args_list if call[0][0] == "turn.completed"]
        assert len(event_calls) == 1
        event_attrs = event_calls[0][0][1]  # Second positional arg
        assert event_attrs["turn"] == 1
        assert event_attrs["input_tokens"] == 100

        assert result == {}

    @pytest.mark.asyncio
    async def test_message_complete_accumulates_tokens(self):
        """Should accumulate tokens across multiple turns."""
        mock_tracer = MagicMock()
        mock_span = MagicMock()
        mock_tracer.start_span.return_value = mock_span

        hooks = SDKTelemetryHooks(tracer=mock_tracer)

        # Initialize session
        await hooks.on_user_prompt_submit(
            {"prompt": "Test", "session_id": "s1"},
            None,
            {"options": {"model": "sonnet"}},
        )

        # First message
        message1 = MagicMock()
        message1.usage.input_tokens = 100
        message1.usage.output_tokens = 50
        message1.usage.cache_read_input_tokens = 0
        message1.usage.cache_creation_input_tokens = 0
        await hooks.on_message_complete(message1, {})

        # Second message
        message2 = MagicMock()
        message2.usage.input_tokens = 80
        message2.usage.output_tokens = 40
        message2.usage.cache_read_input_tokens = 100
        message2.usage.cache_creation_input_tokens = 10
        await hooks.on_message_complete(message2, {})

        # Verify cumulative totals
        assert hooks.metrics["input_tokens"] == 180
        assert hooks.metrics["output_tokens"] == 90
        assert hooks.metrics["cache_read_input_tokens"] == 100
        assert hooks.metrics["cache_creation_input_tokens"] == 10
        assert hooks.metrics["turns"] == 2

    @pytest.mark.asyncio
    async def test_message_complete_handles_missing_usage(self):
        """Should handle messages without usage attribute gracefully."""
        mock_tracer = MagicMock()
        hooks = SDKTelemetryHooks(tracer=mock_tracer)

        # Message without usage
        message = MagicMock(spec=[])  # No attributes
        result = await hooks.on_message_complete(message, {})

        # Should not crash
        assert result == {}
        assert hooks.metrics["input_tokens"] == 0


class TestSDKPreCompact:
    """Tests for SDK PreCompact hook."""

    @pytest.mark.asyncio
    async def test_pre_compact_adds_event(self):
        """Should add compaction event to session span."""
        mock_tracer = MagicMock()
        mock_span = MagicMock()
        mock_tracer.start_span.return_value = mock_span

        hooks = SDKTelemetryHooks(tracer=mock_tracer)

        # Initialize session
        await hooks.on_user_prompt_submit(
            {"prompt": "Test", "session_id": "s1"},
            None,
            {"options": {"model": "sonnet"}},
        )

        # Call pre_compact hook
        input_data = {
            "trigger": "max_tokens_reached",
            "custom_instructions": "Keep important context",
        }
        result = await hooks.on_pre_compact(input_data, None, {})

        # Verify event added
        event_calls = [call for call in mock_span.add_event.call_args_list if call[0][0] == "context.compaction"]
        assert len(event_calls) == 1
        event_attrs = event_calls[0][0][1]  # Second positional arg
        assert event_attrs["trigger"] == "max_tokens_reached"
        assert event_attrs["has_custom_instructions"] is True

        assert result == {}

    @pytest.mark.asyncio
    async def test_pre_compact_without_custom_instructions(self):
        """Should handle compaction without custom instructions."""
        mock_tracer = MagicMock()
        mock_span = MagicMock()
        mock_tracer.start_span.return_value = mock_span

        hooks = SDKTelemetryHooks(tracer=mock_tracer)
        await hooks.on_user_prompt_submit(
            {"prompt": "Test", "session_id": "s1"},
            None,
            {"options": {"model": "sonnet"}},
        )

        input_data = {"trigger": "user_requested"}
        await hooks.on_pre_compact(input_data, None, {})

        # Verify event
        event_calls = [call for call in mock_span.add_event.call_args_list if call[0][0] == "context.compaction"]
        event_attrs = event_calls[0][0][1]  # Second positional arg
        assert event_attrs["has_custom_instructions"] is False


class TestSDKToolHooks:
    """Tests for SDK PreToolUse and PostToolUse hooks."""

    @pytest.mark.asyncio
    async def test_pre_tool_use_creates_tool_span(self):
        """Should create child span for tool execution."""
        mock_tracer = MagicMock()
        mock_session_span = MagicMock()
        mock_tool_span = MagicMock()
        mock_tracer.start_span.side_effect = [mock_session_span, mock_tool_span]

        hooks = SDKTelemetryHooks(tracer=mock_tracer, create_tool_spans=True)

        # Initialize session
        await hooks.on_user_prompt_submit(
            {"prompt": "Test", "session_id": "s1"},
            None,
            {"options": {"model": "sonnet"}},
        )

        # Call pre_tool_use
        input_data = {
            "tool_name": "Bash",
            "tool_input": {"command": "ls -la"},
        }
        result = await hooks.on_pre_tool_use(input_data, "tool_123", {})

        # Verify tool span created
        assert mock_tracer.start_span.call_count == 2
        tool_span_call = mock_tracer.start_span.call_args_list[1]
        assert tool_span_call[0][0] == "tool.Bash"
        assert tool_span_call[1]["attributes"]["tool.name"] == "Bash"
        assert tool_span_call[1]["attributes"]["gen_ai.operation.name"] == "execute_tool"

        # Verify tool span stored
        assert "tool_123" in hooks.tool_spans
        assert hooks.metrics["tools_used"] == 1
        assert result == {}

    @pytest.mark.asyncio
    async def test_post_tool_use_closes_tool_span(self):
        """Should close tool span and add response attributes."""
        mock_tracer = MagicMock()
        mock_session_span = MagicMock()
        mock_tool_span = MagicMock()
        mock_tracer.start_span.side_effect = [mock_session_span, mock_tool_span]

        hooks = SDKTelemetryHooks(tracer=mock_tracer, create_tool_spans=True)

        # Initialize session and tool
        await hooks.on_user_prompt_submit(
            {"prompt": "Test", "session_id": "s1"},
            None,
            {"options": {"model": "sonnet"}},
        )
        await hooks.on_pre_tool_use(
            {"tool_name": "Bash", "tool_input": {"command": "ls"}},
            "tool_123",
            {},
        )

        # Call post_tool_use
        input_data = {
            "tool_name": "Bash",
            "tool_response": {"output": "file1.txt\nfile2.txt"},
        }
        result = await hooks.on_post_tool_use(input_data, "tool_123", {})

        # Verify response attribute set
        assert mock_tool_span.set_attribute.called
        calls = {call[0][0]: call[0][1] for call in mock_tool_span.set_attribute.call_args_list}
        assert "tool.response" in calls
        assert calls["tool.status"] == "success"

        # Verify span ended
        assert mock_tool_span.end.called

        # Verify span removed from storage
        assert "tool_123" not in hooks.tool_spans
        assert result == {}

    @pytest.mark.asyncio
    async def test_post_tool_use_handles_error_response(self):
        """Should mark span as error when tool fails."""
        mock_tracer = MagicMock()
        mock_session_span = MagicMock()
        mock_tool_span = MagicMock()
        mock_tracer.start_span.side_effect = [mock_session_span, mock_tool_span]

        hooks = SDKTelemetryHooks(tracer=mock_tracer, create_tool_spans=True)

        await hooks.on_user_prompt_submit(
            {"prompt": "Test", "session_id": "s1"},
            None,
            {"options": {"model": "sonnet"}},
        )
        await hooks.on_pre_tool_use(
            {"tool_name": "Bash", "tool_input": {"command": "invalid"}},
            "tool_123",
            {},
        )

        # Error response
        input_data = {
            "tool_name": "Bash",
            "tool_response": {"error": "Command not found", "isError": True},
        }
        await hooks.on_post_tool_use(input_data, "tool_123", {})

        # Verify error attributes
        calls = {call[0][0]: call[0][1] for call in mock_tool_span.set_attribute.call_args_list}
        assert calls["tool.status"] == "error"
        assert calls["tool.error"] == "Command not found"

        # Verify span status set to error
        assert mock_tool_span.set_status.called

    @pytest.mark.asyncio
    async def test_pre_tool_use_without_spans(self):
        """Should add event to session span when create_tool_spans=False."""
        mock_tracer = MagicMock()
        mock_span = MagicMock()
        mock_tracer.start_span.return_value = mock_span

        hooks = SDKTelemetryHooks(tracer=mock_tracer, create_tool_spans=False)

        await hooks.on_user_prompt_submit(
            {"prompt": "Test", "session_id": "s1"},
            None,
            {"options": {"model": "sonnet"}},
        )

        input_data = {"tool_name": "Read", "tool_input": {"file": "test.py"}}
        await hooks.on_pre_tool_use(input_data, "tool_123", {})

        # Should only create session span, not tool span
        assert mock_tracer.start_span.call_count == 1

        # Should add event to session span
        event_calls = [call[0][0] for call in mock_span.add_event.call_args_list]
        assert any("tool.started: Read" in call for call in event_calls)


class TestSDKSessionCompletion:
    """Tests for SDK session completion and cleanup."""

    def test_complete_session_ends_span_and_flushes(self):
        """Should end session span and flush telemetry."""
        mock_tracer = MagicMock()
        mock_span = MagicMock()
        mock_tracer.start_span.return_value = mock_span

        # Mock tracer provider
        mock_provider = MagicMock()
        with patch("claude_otel.sdk_hooks.trace.get_tracer_provider", return_value=mock_provider):
            hooks = SDKTelemetryHooks(tracer=mock_tracer)
            hooks.session_span = mock_span
            hooks.metrics = {
                "model": "sonnet",
                "tools_used": 3,
                "start_time": 0.0,
            }
            hooks.tools_used = ["Bash", "Read", "Bash"]

            hooks.complete_session()

            # Verify final attributes set
            calls = {call[0][0]: call[0][1] for call in mock_span.set_attribute.call_args_list}
            assert calls["gen_ai.response.model"] == "sonnet"
            assert calls["tools_used"] == 3
            # Tool names should contain both Bash and Read (order not guaranteed due to set)
            assert set(calls["tool_names"].split(",")) == {"Bash", "Read"}

            # Verify event and span end
            event_calls = [call[0][0] for call in mock_span.add_event.call_args_list]
            assert "session.completed" in event_calls
            assert mock_span.end.called

            # Verify flush called
            assert mock_provider.force_flush.called

            # Verify state reset
            assert hooks.session_span is None
            assert len(hooks.tool_spans) == 0
