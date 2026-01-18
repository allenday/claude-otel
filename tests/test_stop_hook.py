"""Unit tests for Stop hook (token usage extraction from transcript)."""

import pytest
import json
import tempfile
from pathlib import Path
from unittest.mock import Mock, patch

from claude_otel.sdk_hooks import SDKTelemetryHooks


class TestStopHook:
    """Tests for on_stop hook that extracts token usage from transcript."""

    @pytest.fixture
    def hooks(self):
        """Create hooks instance for testing."""
        with patch("claude_otel.sdk_hooks.get_config") as mock_config:
            mock_config.return_value = Mock(debug=False)
            return SDKTelemetryHooks()

    @pytest.fixture
    def sample_transcript(self):
        """Create a sample transcript with token usage."""
        return {
            "messages": [
                {
                    "role": "user",
                    "content": "Hello",
                },
                {
                    "role": "assistant",
                    "content": "Hi there!",
                    "usage": {
                        "input_tokens": 100,
                        "output_tokens": 50,
                        "cache_read_input_tokens": 0,
                        "cache_creation_input_tokens": 0,
                    },
                },
                {
                    "role": "user",
                    "content": "How are you?",
                },
                {
                    "role": "assistant",
                    "content": "I'm doing well!",
                    "usage": {
                        "input_tokens": 150,
                        "output_tokens": 75,
                        "cache_read_input_tokens": 100,
                        "cache_creation_input_tokens": 50,
                    },
                },
            ]
        }

    @pytest.mark.asyncio
    async def test_on_stop_extracts_token_counts_from_transcript(self, hooks, sample_transcript):
        """Stop hook should parse transcript and extract token counts."""
        # Create a session span
        await hooks.on_user_prompt_submit(
            {"prompt": "test", "session_id": "s1"},
            None,
            {"options": {"model": "claude-opus-4"}},
        )

        # Create temporary transcript file
        with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".json") as f:
            json.dump(sample_transcript, f)
            transcript_path = f.name

        try:
            # Call the stop hook
            input_data = {
                "session_id": "s1",
                "transcript_path": transcript_path,
                "cwd": "/tmp",
            }

            result = await hooks.on_stop(input_data, None, None)

            # Should return empty dict
            assert result == {}

            # Should extract and accumulate token counts
            assert hooks.metrics["input_tokens"] == 250  # 100 + 150
            assert hooks.metrics["output_tokens"] == 125  # 50 + 75
            assert hooks.metrics["cache_read_input_tokens"] == 100
            assert hooks.metrics["cache_creation_input_tokens"] == 50
            assert hooks.metrics["turns"] == 2

        finally:
            # Clean up temp file
            Path(transcript_path).unlink()

    @pytest.mark.asyncio
    async def test_on_stop_updates_span_attributes(self, hooks, sample_transcript):
        """Stop hook should update span with token attributes."""
        # Create a session span
        await hooks.on_user_prompt_submit(
            {"prompt": "test", "session_id": "s1"},
            None,
            {"options": {"model": "claude-opus-4"}},
        )

        # Create temporary transcript file
        with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".json") as f:
            json.dump(sample_transcript, f)
            transcript_path = f.name

        try:
            # Mock the span's set_attribute method
            with patch.object(hooks.session_span, "set_attribute") as mock_set_attr:
                with patch.object(hooks.session_span, "add_event"):
                    input_data = {
                        "session_id": "s1",
                        "transcript_path": transcript_path,
                        "cwd": "/tmp",
                    }

                    await hooks.on_stop(input_data, None, None)

                    # Check that token attributes were set
                    calls = mock_set_attr.call_args_list
                    attr_dict = {call[0][0]: call[0][1] for call in calls}

                    assert attr_dict["gen_ai.usage.input_tokens"] == 250
                    assert attr_dict["gen_ai.usage.output_tokens"] == 125
                    assert attr_dict["tokens.cache_read"] == 100
                    assert attr_dict["tokens.cache_creation"] == 50
                    assert attr_dict["turns"] == 2

        finally:
            Path(transcript_path).unlink()

    @pytest.mark.asyncio
    async def test_on_stop_handles_missing_transcript_path(self, hooks):
        """Stop hook should handle missing transcript_path gracefully."""
        # Create a session span
        await hooks.on_user_prompt_submit(
            {"prompt": "test", "session_id": "s1"},
            None,
            {"options": {"model": "claude-opus-4"}},
        )

        # Call without transcript_path
        input_data = {
            "session_id": "s1",
            "cwd": "/tmp",
        }

        result = await hooks.on_stop(input_data, None, None)

        # Should return empty dict
        assert result == {}

        # Metrics should not be updated
        assert hooks.metrics["input_tokens"] == 0
        assert hooks.metrics["output_tokens"] == 0

    @pytest.mark.asyncio
    async def test_on_stop_handles_nonexistent_transcript_file(self, hooks):
        """Stop hook should handle nonexistent transcript file gracefully."""
        # Create a session span
        await hooks.on_user_prompt_submit(
            {"prompt": "test", "session_id": "s1"},
            None,
            {"options": {"model": "claude-opus-4"}},
        )

        # Call with nonexistent path
        input_data = {
            "session_id": "s1",
            "transcript_path": "/nonexistent/path/transcript.json",
            "cwd": "/tmp",
        }

        result = await hooks.on_stop(input_data, None, None)

        # Should return empty dict
        assert result == {}

        # Metrics should not be updated
        assert hooks.metrics["input_tokens"] == 0
        assert hooks.metrics["output_tokens"] == 0

    @pytest.mark.asyncio
    async def test_on_stop_handles_malformed_transcript(self, hooks):
        """Stop hook should handle malformed transcript gracefully."""
        # Create a session span
        await hooks.on_user_prompt_submit(
            {"prompt": "test", "session_id": "s1"},
            None,
            {"options": {"model": "claude-opus-4"}},
        )

        # Create temporary transcript file with invalid JSON
        with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".json") as f:
            f.write("{invalid json")
            transcript_path = f.name

        try:
            input_data = {
                "session_id": "s1",
                "transcript_path": transcript_path,
                "cwd": "/tmp",
            }

            result = await hooks.on_stop(input_data, None, None)

            # Should return empty dict
            assert result == {}

            # Metrics should not be updated
            assert hooks.metrics["input_tokens"] == 0
            assert hooks.metrics["output_tokens"] == 0

        finally:
            Path(transcript_path).unlink()

    @pytest.mark.asyncio
    async def test_on_stop_handles_list_transcript_format(self, hooks):
        """Stop hook should handle transcript as list (alternative format)."""
        # Create a session span
        await hooks.on_user_prompt_submit(
            {"prompt": "test", "session_id": "s1"},
            None,
            {"options": {"model": "claude-opus-4"}},
        )

        # Create transcript as list instead of dict
        transcript_list = [
            {
                "role": "assistant",
                "content": "Response",
                "usage": {
                    "input_tokens": 100,
                    "output_tokens": 50,
                    "cache_read_input_tokens": 0,
                    "cache_creation_input_tokens": 0,
                },
            }
        ]

        with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".json") as f:
            json.dump(transcript_list, f)
            transcript_path = f.name

        try:
            input_data = {
                "session_id": "s1",
                "transcript_path": transcript_path,
                "cwd": "/tmp",
            }

            result = await hooks.on_stop(input_data, None, None)

            # Should return empty dict
            assert result == {}

            # Should extract token counts from list format
            assert hooks.metrics["input_tokens"] == 100
            assert hooks.metrics["output_tokens"] == 50
            assert hooks.metrics["turns"] == 1

        finally:
            Path(transcript_path).unlink()

    @pytest.mark.asyncio
    async def test_on_stop_records_metrics(self, hooks, sample_transcript):
        """Stop hook should record metrics for turns and cache usage."""
        # Create a session span
        await hooks.on_user_prompt_submit(
            {"prompt": "test", "session_id": "s1"},
            None,
            {"options": {"model": "claude-opus-4"}},
        )

        # Create temporary transcript file
        with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".json") as f:
            json.dump(sample_transcript, f)
            transcript_path = f.name

        try:
            with patch("claude_otel.sdk_hooks.metrics") as mock_metrics:
                input_data = {
                    "session_id": "s1",
                    "transcript_path": transcript_path,
                    "cwd": "/tmp",
                }

                await hooks.on_stop(input_data, None, None)

                # Should record turn metric
                mock_metrics.record_turn.assert_called_once_with("claude-opus-4", count=2)

                # Should record cache usage metric
                mock_metrics.record_cache_usage.assert_called_once_with(100, 50, "claude-opus-4")

        finally:
            Path(transcript_path).unlink()
