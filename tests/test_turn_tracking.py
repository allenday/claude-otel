"""Integration tests for turn tracking across multi-turn conversations.

Turn tracking is a key feature that counts conversation rounds and accumulates
token usage across multiple user-assistant exchanges. These tests verify that:
- Turn count increments correctly across multiple messages
- Token counts accumulate properly
- Turn events are recorded with correct incremental data
- Span attributes reflect cumulative state
- Metrics are recorded for each turn
"""

import pytest
from unittest.mock import Mock, patch, call
import time

from claude_otel.sdk_hooks import SDKTelemetryHooks


class TestTurnTrackingIntegration:
    """Integration tests for turn tracking across conversations."""

    @pytest.fixture
    def hooks(self):
        """Create hooks instance for testing."""
        with patch("claude_otel.sdk_hooks.get_config") as mock_config:
            mock_config.return_value = Mock(debug=False)
            return SDKTelemetryHooks()

    @pytest.mark.asyncio
    async def test_single_turn_increments_count(self, hooks):
        """Single user-assistant exchange should increment turn count to 1."""
        # Start session
        await hooks.on_user_prompt_submit(
            {"prompt": "Hello", "session_id": "s1"},
            None,
            {"options": {"model": "claude-opus-4"}},
        )

        # Create mock message
        mock_usage = Mock()
        mock_usage.input_tokens = 10
        mock_usage.output_tokens = 20
        mock_usage.cache_read_input_tokens = 0
        mock_usage.cache_creation_input_tokens = 0

        mock_message = Mock()
        mock_message.usage = mock_usage
        mock_message.content = "Hi there!"

        # Complete turn
        await hooks.on_message_complete(mock_message, None)

        # Verify turn count
        assert hooks.metrics["turns"] == 1

    @pytest.mark.asyncio
    async def test_multi_turn_conversation_increments_correctly(self, hooks):
        """Multiple turns should increment count sequentially."""
        # Start session
        await hooks.on_user_prompt_submit(
            {"prompt": "First prompt", "session_id": "s1"},
            None,
            {"options": {"model": "claude-sonnet-4"}},
        )

        # Turn 1
        mock_usage1 = Mock()
        mock_usage1.input_tokens = 10
        mock_usage1.output_tokens = 20
        mock_usage1.cache_read_input_tokens = 0
        mock_usage1.cache_creation_input_tokens = 0
        mock_message1 = Mock()
        mock_message1.usage = mock_usage1
        mock_message1.content = "Response 1"

        await hooks.on_message_complete(mock_message1, None)
        assert hooks.metrics["turns"] == 1

        # Turn 2
        mock_usage2 = Mock()
        mock_usage2.input_tokens = 15
        mock_usage2.output_tokens = 25
        mock_usage2.cache_read_input_tokens = 0
        mock_usage2.cache_creation_input_tokens = 0
        mock_message2 = Mock()
        mock_message2.usage = mock_usage2
        mock_message2.content = "Response 2"

        await hooks.on_message_complete(mock_message2, None)
        assert hooks.metrics["turns"] == 2

        # Turn 3
        mock_usage3 = Mock()
        mock_usage3.input_tokens = 20
        mock_usage3.output_tokens = 30
        mock_usage3.cache_read_input_tokens = 0
        mock_usage3.cache_creation_input_tokens = 0
        mock_message3 = Mock()
        mock_message3.usage = mock_usage3
        mock_message3.content = "Response 3"

        await hooks.on_message_complete(mock_message3, None)
        assert hooks.metrics["turns"] == 3

    @pytest.mark.asyncio
    async def test_cumulative_token_tracking_across_turns(self, hooks):
        """Token counts should accumulate across multiple turns."""
        # Start session
        await hooks.on_user_prompt_submit(
            {"prompt": "Start", "session_id": "s1"},
            None,
            {"options": {"model": "claude-opus-4"}},
        )

        # Turn 1: 100 in, 50 out
        mock_usage1 = Mock()
        mock_usage1.input_tokens = 100
        mock_usage1.output_tokens = 50
        mock_usage1.cache_read_input_tokens = 0
        mock_usage1.cache_creation_input_tokens = 0
        mock_message1 = Mock()
        mock_message1.usage = mock_usage1
        mock_message1.content = "Response 1"

        await hooks.on_message_complete(mock_message1, None)

        assert hooks.metrics["input_tokens"] == 100
        assert hooks.metrics["output_tokens"] == 50
        assert hooks.metrics["turns"] == 1

        # Turn 2: 150 in, 75 out (cumulative: 250 in, 125 out)
        mock_usage2 = Mock()
        mock_usage2.input_tokens = 150
        mock_usage2.output_tokens = 75
        mock_usage2.cache_read_input_tokens = 0
        mock_usage2.cache_creation_input_tokens = 0
        mock_message2 = Mock()
        mock_message2.usage = mock_usage2
        mock_message2.content = "Response 2"

        await hooks.on_message_complete(mock_message2, None)

        assert hooks.metrics["input_tokens"] == 250
        assert hooks.metrics["output_tokens"] == 125
        assert hooks.metrics["turns"] == 2

        # Turn 3: 200 in, 100 out (cumulative: 450 in, 225 out)
        mock_usage3 = Mock()
        mock_usage3.input_tokens = 200
        mock_usage3.output_tokens = 100
        mock_usage3.cache_read_input_tokens = 0
        mock_usage3.cache_creation_input_tokens = 0
        mock_message3 = Mock()
        mock_message3.usage = mock_usage3
        mock_message3.content = "Response 3"

        await hooks.on_message_complete(mock_message3, None)

        assert hooks.metrics["input_tokens"] == 450
        assert hooks.metrics["output_tokens"] == 225
        assert hooks.metrics["turns"] == 3

    @pytest.mark.asyncio
    async def test_cache_tokens_accumulate_across_turns(self, hooks):
        """Cache read and creation tokens should accumulate separately."""
        # Start session
        await hooks.on_user_prompt_submit(
            {"prompt": "Test", "session_id": "s1"},
            None,
            {"options": {"model": "claude-haiku-4"}},
        )

        # Turn 1: 200 cache read, 25 cache creation
        mock_usage1 = Mock()
        mock_usage1.input_tokens = 100
        mock_usage1.output_tokens = 50
        mock_usage1.cache_read_input_tokens = 200
        mock_usage1.cache_creation_input_tokens = 25
        mock_message1 = Mock()
        mock_message1.usage = mock_usage1
        mock_message1.content = "Response 1"

        await hooks.on_message_complete(mock_message1, None)

        assert hooks.metrics["cache_read_input_tokens"] == 200
        assert hooks.metrics["cache_creation_input_tokens"] == 25

        # Turn 2: 300 cache read, 50 cache creation
        mock_usage2 = Mock()
        mock_usage2.input_tokens = 150
        mock_usage2.output_tokens = 75
        mock_usage2.cache_read_input_tokens = 300
        mock_usage2.cache_creation_input_tokens = 50
        mock_message2 = Mock()
        mock_message2.usage = mock_usage2
        mock_message2.content = "Response 2"

        await hooks.on_message_complete(mock_message2, None)

        # Should accumulate
        assert hooks.metrics["cache_read_input_tokens"] == 500
        assert hooks.metrics["cache_creation_input_tokens"] == 75

    @pytest.mark.asyncio
    async def test_turn_events_recorded_with_incremental_tokens(self, hooks):
        """Each turn should record an event with that turn's token counts."""
        # Start session
        await hooks.on_user_prompt_submit(
            {"prompt": "Test", "session_id": "s1"},
            None,
            {"options": {"model": "claude-opus-4"}},
        )

        with patch.object(hooks.session_span, "add_event") as mock_add_event:
            # Turn 1
            mock_usage = Mock()
            mock_usage.input_tokens = 100
            mock_usage.output_tokens = 50
            mock_usage.cache_read_input_tokens = 200
            mock_usage.cache_creation_input_tokens = 25
            mock_message = Mock()
            mock_message.usage = mock_usage
            mock_message.content = "Response"

            await hooks.on_message_complete(mock_message, None)

            # Should record turn.completed event with incremental tokens
            mock_add_event.assert_called_with(
                "turn.completed",
                {
                    "turn": 1,
                    "input_tokens": 100,
                    "output_tokens": 50,
                    "cache_read_tokens": 200,
                    "cache_creation_tokens": 25,
                },
            )

    @pytest.mark.asyncio
    async def test_span_attributes_updated_with_cumulative_tokens(self, hooks):
        """Span attributes should reflect cumulative token counts."""
        # Start session
        await hooks.on_user_prompt_submit(
            {"prompt": "Test", "session_id": "s1"},
            None,
            {"options": {"model": "claude-sonnet-4"}},
        )

        with patch.object(hooks.session_span, "set_attribute") as mock_set_attr:
            # Turn 1
            mock_usage1 = Mock()
            mock_usage1.input_tokens = 100
            mock_usage1.output_tokens = 50
            mock_usage1.cache_read_input_tokens = 200
            mock_usage1.cache_creation_input_tokens = 25
            mock_message1 = Mock()
            mock_message1.usage = mock_usage1
            mock_message1.content = "Response 1"

            await hooks.on_message_complete(mock_message1, None)

            # Check cumulative attributes after turn 1
            expected_calls = [
                call("gen_ai.usage.input_tokens", 100),
                call("gen_ai.usage.output_tokens", 50),
                call("tokens.cache_read", 200),
                call("tokens.cache_creation", 25),
                call("turns", 1),
            ]
            for expected_call in expected_calls:
                assert expected_call in mock_set_attr.call_args_list

            mock_set_attr.reset_mock()

            # Turn 2 - should update with cumulative totals
            mock_usage2 = Mock()
            mock_usage2.input_tokens = 150
            mock_usage2.output_tokens = 75
            mock_usage2.cache_read_input_tokens = 100
            mock_usage2.cache_creation_input_tokens = 10
            mock_message2 = Mock()
            mock_message2.usage = mock_usage2
            mock_message2.content = "Response 2"

            await hooks.on_message_complete(mock_message2, None)

            # Check cumulative attributes after turn 2
            expected_calls_turn2 = [
                call("gen_ai.usage.input_tokens", 250),  # 100 + 150
                call("gen_ai.usage.output_tokens", 125),  # 50 + 75
                call("tokens.cache_read", 300),  # 200 + 100
                call("tokens.cache_creation", 35),  # 25 + 10
                call("turns", 2),
            ]
            for expected_call in expected_calls_turn2:
                assert expected_call in mock_set_attr.call_args_list

    @pytest.mark.asyncio
    async def test_metrics_recorded_for_each_turn(self, hooks):
        """Each turn should record a turn metric."""
        # Start session
        await hooks.on_user_prompt_submit(
            {"prompt": "Test", "session_id": "s1"},
            None,
            {"options": {"model": "claude-opus-4"}},
        )

        with patch("claude_otel.sdk_hooks.metrics.record_turn") as mock_record_turn:
            # Turn 1
            mock_usage1 = Mock()
            mock_usage1.input_tokens = 100
            mock_usage1.output_tokens = 50
            mock_usage1.cache_read_input_tokens = 0
            mock_usage1.cache_creation_input_tokens = 0
            mock_message1 = Mock()
            mock_message1.usage = mock_usage1
            mock_message1.content = "Response 1"

            await hooks.on_message_complete(mock_message1, None)
            mock_record_turn.assert_called_once_with("claude-opus-4")

            mock_record_turn.reset_mock()

            # Turn 2
            mock_usage2 = Mock()
            mock_usage2.input_tokens = 150
            mock_usage2.output_tokens = 75
            mock_usage2.cache_read_input_tokens = 0
            mock_usage2.cache_creation_input_tokens = 0
            mock_message2 = Mock()
            mock_message2.usage = mock_usage2
            mock_message2.content = "Response 2"

            await hooks.on_message_complete(mock_message2, None)
            mock_record_turn.assert_called_once_with("claude-opus-4")

    @pytest.mark.asyncio
    async def test_turn_tracking_with_tools(self, hooks):
        """Turn count should increment even when tools are used."""
        # Start session
        await hooks.on_user_prompt_submit(
            {"prompt": "Run a command", "session_id": "s1"},
            None,
            {"options": {"model": "claude-sonnet-4"}},
        )

        # Execute a tool
        await hooks.on_pre_tool_use(
            {"tool_name": "Bash", "tool_input": {"command": "ls"}},
            "tool_1",
            None,
        )
        await hooks.on_post_tool_use(
            {"tool_name": "Bash", "tool_response": {"output": "file1.txt"}},
            "tool_1",
            None,
        )

        # Complete message (turn 1)
        mock_usage1 = Mock()
        mock_usage1.input_tokens = 100
        mock_usage1.output_tokens = 50
        mock_usage1.cache_read_input_tokens = 0
        mock_usage1.cache_creation_input_tokens = 0
        mock_message1 = Mock()
        mock_message1.usage = mock_usage1
        mock_message1.content = "Here's the output"

        await hooks.on_message_complete(mock_message1, None)

        assert hooks.metrics["turns"] == 1
        assert hooks.metrics["tools_used"] == 1

        # Turn 2 - user follows up
        mock_usage2 = Mock()
        mock_usage2.input_tokens = 120
        mock_usage2.output_tokens = 60
        mock_usage2.cache_read_input_tokens = 0
        mock_usage2.cache_creation_input_tokens = 0
        mock_message2 = Mock()
        mock_message2.usage = mock_usage2
        mock_message2.content = "Follow up response"

        await hooks.on_message_complete(mock_message2, None)

        assert hooks.metrics["turns"] == 2
        assert hooks.metrics["tools_used"] == 1  # Tools counter doesn't reset

    @pytest.mark.asyncio
    async def test_turn_tracking_persists_until_session_complete(self, hooks):
        """Turn tracking should persist throughout the session."""
        # Start session
        await hooks.on_user_prompt_submit(
            {"prompt": "Start", "session_id": "s1"},
            None,
            {"options": {"model": "claude-opus-4"}},
        )

        # Multiple turns
        for i in range(5):
            mock_usage = Mock()
            mock_usage.input_tokens = 100
            mock_usage.output_tokens = 50
            mock_usage.cache_read_input_tokens = 0
            mock_usage.cache_creation_input_tokens = 0
            mock_message = Mock()
            mock_message.usage = mock_usage
            mock_message.content = f"Response {i+1}"

            await hooks.on_message_complete(mock_message, None)

        # After 5 turns
        assert hooks.metrics["turns"] == 5
        assert hooks.metrics["input_tokens"] == 500
        assert hooks.metrics["output_tokens"] == 250

        # Complete session
        hooks.complete_session()

        # After session complete, state should reset
        assert hooks.metrics == {}

    @pytest.mark.asyncio
    async def test_message_history_tracking(self, hooks):
        """Messages should be stored for session context."""
        # Start session
        await hooks.on_user_prompt_submit(
            {"prompt": "Hello", "session_id": "s1"},
            None,
            {"options": {"model": "claude-opus-4"}},
        )

        # Should have user message
        assert len(hooks.messages) == 1
        assert hooks.messages[0]["role"] == "user"
        assert hooks.messages[0]["content"] == "Hello"

        # Turn 1
        mock_usage = Mock()
        mock_usage.input_tokens = 10
        mock_usage.output_tokens = 20
        mock_usage.cache_read_input_tokens = 0
        mock_usage.cache_creation_input_tokens = 0
        mock_message = Mock()
        mock_message.usage = mock_usage
        mock_message.content = "Hi there!"

        await hooks.on_message_complete(mock_message, None)

        # Should now have 2 messages
        assert len(hooks.messages) == 2
        assert hooks.messages[1]["role"] == "assistant"
        assert hooks.messages[1]["content"] == "Hi there!"

    @pytest.mark.asyncio
    async def test_gen_ai_semantic_conventions_for_turns(self, hooks):
        """Turn tracking should use gen_ai.* semantic conventions."""
        # Start session
        await hooks.on_user_prompt_submit(
            {"prompt": "Test", "session_id": "s1"},
            None,
            {"options": {"model": "claude-sonnet-4"}},
        )

        # Verify session span has gen_ai attributes
        with patch.object(hooks.session_span, "set_attribute") as mock_set_attr:
            mock_usage = Mock()
            mock_usage.input_tokens = 100
            mock_usage.output_tokens = 50
            mock_usage.cache_read_input_tokens = 0
            mock_usage.cache_creation_input_tokens = 0
            mock_message = Mock()
            mock_message.usage = mock_usage
            mock_message.content = "Response"

            await hooks.on_message_complete(mock_message, None)

            # Check that gen_ai.* attributes are set
            gen_ai_calls = [
                c for c in mock_set_attr.call_args_list
                if c[0][0].startswith("gen_ai.usage.")
            ]
            assert len(gen_ai_calls) >= 2  # At least input and output tokens

            # Verify specific gen_ai attributes
            attr_dict = {c[0][0]: c[0][1] for c in mock_set_attr.call_args_list}
            assert attr_dict.get("gen_ai.usage.input_tokens") == 100
            assert attr_dict.get("gen_ai.usage.output_tokens") == 50
