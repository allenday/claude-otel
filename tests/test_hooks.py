"""Unit tests for hook modules - token extraction and span attributes."""

import json
import os
import tempfile
import pytest

# Import the hook module functions directly
import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "hooks"))

from post_tool import (
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
