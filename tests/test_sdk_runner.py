"""Integration tests for SDK-based runner.

These tests verify the SDK runner's end-to-end functionality including:
- Span creation and management
- Hook integration
- Error handling
- Interactive mode
- Sync/async wrapper functionality
"""

import pytest
from unittest.mock import Mock, AsyncMock, patch, MagicMock
import asyncio

from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.trace import Status, StatusCode

from claude_otel.sdk_runner import (
    setup_sdk_hooks,
    run_agent_with_sdk,
    run_agent_with_sdk_sync,
    run_agent_interactive,
    run_agent_interactive_sync,
    extract_message_text,
)
from claude_otel.config import OTelConfig


@pytest.fixture
def mock_tracer():
    """Create a mock tracer for testing."""
    provider = TracerProvider()
    return provider.get_tracer("test-tracer", "0.1.0")


@pytest.fixture
def test_config():
    """Create a test configuration."""
    return OTelConfig(
        endpoint="http://localhost:4317",
        protocol="grpc",
        service_name="claude-otel-test",
        debug=False,
    )


class TestSetupSDKHooks:
    """Tests for setup_sdk_hooks function."""

    def test_setup_sdk_hooks_returns_hooks_and_config(self, mock_tracer):
        """setup_sdk_hooks should return hooks instance and hook config dict."""
        hooks, hook_config = setup_sdk_hooks(mock_tracer)

        # Should return hooks instance
        assert hooks is not None
        assert hasattr(hooks, "on_user_prompt_submit")
        assert hasattr(hooks, "on_pre_tool_use")
        assert hasattr(hooks, "on_post_tool_use")
        assert hasattr(hooks, "on_message_complete")
        assert hasattr(hooks, "on_pre_compact")

        # Should return hook config dict
        assert isinstance(hook_config, dict)
        assert "UserPromptSubmit" in hook_config
        assert "PreToolUse" in hook_config
        assert "PostToolUse" in hook_config
        assert "MessageComplete" in hook_config
        assert "PreCompact" in hook_config

    def test_setup_sdk_hooks_creates_valid_hook_matchers(self, mock_tracer):
        """Hook config should contain valid HookMatcher objects."""
        hooks, hook_config = setup_sdk_hooks(mock_tracer)

        # Each hook type should have a list of HookMatchers
        for hook_type, matchers in hook_config.items():
            assert isinstance(matchers, list)
            assert len(matchers) == 1
            # HookMatcher has matcher and hooks attributes
            matcher = matchers[0]
            assert hasattr(matcher, "matcher")
            assert hasattr(matcher, "hooks")
            assert matcher.matcher is None  # Match all
            assert len(matcher.hooks) == 1


class TestExtractMessageText:
    """Tests for extract_message_text helper function."""

    def test_extract_text_from_list_content(self):
        """Should extract text from list of content blocks."""
        mock_block1 = Mock()
        mock_block1.text = "Hello, "
        mock_block2 = Mock()
        mock_block2.text = "world!"

        message = Mock()
        message.content = [mock_block1, mock_block2]

        result = extract_message_text(message)
        assert result == "Hello, world!"

    def test_extract_text_from_string_content(self):
        """Should handle string content directly."""
        message = Mock()
        message.content = "Direct string content"

        result = extract_message_text(message)
        assert result == "Direct string content"

    def test_extract_text_from_other_content_type(self):
        """Should convert other types to string."""
        message = Mock()
        message.content = 12345

        result = extract_message_text(message)
        assert result == "12345"

    def test_extract_text_from_message_without_content(self):
        """Should return empty string for message without content."""
        message = Mock(spec=[])  # No content attribute

        result = extract_message_text(message)
        assert result == ""

    def test_extract_text_handles_mixed_blocks(self):
        """Should handle blocks with and without text attribute."""
        mock_block_with_text = Mock()
        mock_block_with_text.text = "Hello"
        mock_block_without_text = Mock(spec=[])  # No text attribute

        message = Mock()
        message.content = [mock_block_with_text, mock_block_without_text]

        result = extract_message_text(message)
        assert result == "Hello"


class TestRunAgentWithSDK:
    """Tests for run_agent_with_sdk async function."""

    @pytest.mark.asyncio
    async def test_run_agent_with_sdk_requires_tracer(self, test_config):
        """Should raise ValueError if no tracer provided."""
        with pytest.raises(ValueError, match="Tracer is required"):
            await run_agent_with_sdk(
                prompt="Test prompt",
                config=test_config,
                tracer=None,
            )

    @pytest.mark.asyncio
    async def test_run_agent_with_sdk_success(self, mock_tracer, test_config):
        """Should successfully run agent and return exit code 0."""
        # Mock ClaudeSDKClient
        mock_message = Mock()
        mock_message.content = "Test response"

        async def mock_receive():
            yield mock_message

        mock_client = AsyncMock()
        mock_client.query = AsyncMock()
        mock_client.receive_response = mock_receive
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock()

        with patch("claude_otel.sdk_runner.ClaudeSDKClient", return_value=mock_client):
            exit_code = await run_agent_with_sdk(
                prompt="Test prompt",
                config=test_config,
                tracer=mock_tracer,
            )

        assert exit_code == 0
        mock_client.query.assert_called_once_with(prompt="Test prompt")

    @pytest.mark.asyncio
    async def test_run_agent_with_sdk_keyboard_interrupt(self, mock_tracer, test_config):
        """Should return 130 on KeyboardInterrupt."""
        # Mock the entire async context manager to raise on entry
        mock_client_cm = AsyncMock()
        mock_client_cm.__aenter__ = AsyncMock(side_effect=KeyboardInterrupt())
        mock_client_cm.__aexit__ = AsyncMock()

        with patch("claude_otel.sdk_runner.ClaudeSDKClient", return_value=mock_client_cm):
            exit_code = await run_agent_with_sdk(
                prompt="Test prompt",
                config=test_config,
                tracer=mock_tracer,
            )

        assert exit_code == 130

    @pytest.mark.asyncio
    async def test_run_agent_with_sdk_error(self, mock_tracer, test_config):
        """Should return 1 on exception."""
        # Mock the entire async context manager to raise on entry
        mock_client_cm = AsyncMock()
        mock_client_cm.__aenter__ = AsyncMock(side_effect=RuntimeError("Test error"))
        mock_client_cm.__aexit__ = AsyncMock()

        with patch("claude_otel.sdk_runner.ClaudeSDKClient", return_value=mock_client_cm):
            exit_code = await run_agent_with_sdk(
                prompt="Test prompt",
                config=test_config,
                tracer=mock_tracer,
            )

        assert exit_code == 1

    @pytest.mark.asyncio
    async def test_run_agent_with_sdk_passes_extra_args(self, mock_tracer, test_config):
        """Should pass extra_args to ClaudeAgentOptions."""
        mock_message = Mock()
        mock_message.content = "Response"

        async def mock_receive():
            yield mock_message

        mock_client = AsyncMock()
        mock_client.query = AsyncMock()
        mock_client.receive_response = mock_receive
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock()

        with patch("claude_otel.sdk_runner.ClaudeSDKClient", return_value=mock_client) as mock_sdk:
            with patch("claude_otel.sdk_runner.ClaudeAgentOptions") as mock_options:
                await run_agent_with_sdk(
                    prompt="Test",
                    extra_args={"model": "opus", "permission-mode": "bypassPermissions"},
                    config=test_config,
                    tracer=mock_tracer,
                )

                # Check that ClaudeAgentOptions was called with extra_args
                call_kwargs = mock_options.call_args.kwargs
                assert call_kwargs["extra_args"] == {
                    "model": "opus",
                    "permission-mode": "bypassPermissions"
                }

    @pytest.mark.asyncio
    async def test_run_agent_with_sdk_sets_setting_sources(self, mock_tracer, test_config):
        """Should set setting_sources to load user/project/local settings."""
        mock_message = Mock()
        mock_message.content = "Response"

        async def mock_receive():
            yield mock_message

        mock_client = AsyncMock()
        mock_client.query = AsyncMock()
        mock_client.receive_response = mock_receive
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock()

        with patch("claude_otel.sdk_runner.ClaudeSDKClient", return_value=mock_client):
            with patch("claude_otel.sdk_runner.ClaudeAgentOptions") as mock_options:
                await run_agent_with_sdk(
                    prompt="Test",
                    config=test_config,
                    tracer=mock_tracer,
                )

                # Check that setting_sources includes all required sources
                call_kwargs = mock_options.call_args.kwargs
                assert call_kwargs["setting_sources"] == ["user", "project", "local"]

    @pytest.mark.asyncio
    async def test_run_agent_with_sdk_completes_session_span(self, mock_tracer, test_config):
        """Should complete session span after agent finishes."""
        mock_message = Mock()
        mock_message.content = "Response"

        async def mock_receive():
            yield mock_message

        mock_client = AsyncMock()
        mock_client.query = AsyncMock()
        mock_client.receive_response = mock_receive
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock()

        with patch("claude_otel.sdk_runner.ClaudeSDKClient", return_value=mock_client):
            with patch("claude_otel.sdk_runner.setup_sdk_hooks") as mock_setup:
                mock_hooks = Mock()
                mock_hooks.session_span = Mock()
                mock_hooks.complete_session = Mock()
                mock_setup.return_value = (mock_hooks, {})

                await run_agent_with_sdk(
                    prompt="Test",
                    config=test_config,
                    tracer=mock_tracer,
                )

                # Should complete session
                mock_hooks.complete_session.assert_called_once()

    @pytest.mark.asyncio
    async def test_run_agent_with_sdk_marks_error_on_exception(self, mock_tracer, test_config):
        """Should mark session span with error status on exception."""
        # Mock the entire async context manager to raise on entry
        mock_client_cm = AsyncMock()
        mock_client_cm.__aenter__ = AsyncMock(side_effect=RuntimeError("Test error"))
        mock_client_cm.__aexit__ = AsyncMock()

        with patch("claude_otel.sdk_runner.ClaudeSDKClient", return_value=mock_client_cm):
            with patch("claude_otel.sdk_runner.setup_sdk_hooks") as mock_setup:
                mock_span = Mock()
                mock_hooks = Mock()
                mock_hooks.session_span = mock_span
                mock_hooks.complete_session = Mock()
                mock_setup.return_value = (mock_hooks, {})

                await run_agent_with_sdk(
                    prompt="Test",
                    config=test_config,
                    tracer=mock_tracer,
                )

                # Should set error status
                mock_span.set_status.assert_called_once()
                call_args = mock_span.set_status.call_args[0][0]
                assert call_args.status_code == StatusCode.ERROR
                assert "Test error" in call_args.description


class TestRunAgentWithSDKSync:
    """Tests for synchronous wrapper run_agent_with_sdk_sync."""

    def test_run_agent_with_sdk_sync_calls_async_version(self, mock_tracer, test_config):
        """Sync wrapper should call async version via asyncio.run."""
        with patch("claude_otel.sdk_runner.asyncio.run") as mock_run:
            mock_run.return_value = 0

            result = run_agent_with_sdk_sync(
                prompt="Test",
                extra_args={"model": "opus"},
                config=test_config,
                tracer=mock_tracer,
            )

            assert result == 0
            mock_run.assert_called_once()

    def test_run_agent_with_sdk_sync_passes_arguments(self, mock_tracer, test_config):
        """Sync wrapper should pass all arguments to async version."""
        with patch("claude_otel.sdk_runner.asyncio.run") as mock_run:
            mock_run.return_value = 0

            run_agent_with_sdk_sync(
                prompt="Test prompt",
                extra_args={"model": "sonnet"},
                config=test_config,
                tracer=mock_tracer,
                logger=None,
            )

            # Check the coroutine passed to asyncio.run
            assert mock_run.called
            # The first arg to asyncio.run is the coroutine
            coro = mock_run.call_args[0][0]
            assert asyncio.iscoroutine(coro)


class TestRunAgentInteractive:
    """Tests for run_agent_interactive async function."""

    @pytest.mark.asyncio
    async def test_run_agent_interactive_requires_tracer(self, test_config):
        """Should raise ValueError if no tracer provided."""
        with pytest.raises(ValueError, match="Tracer is required"):
            await run_agent_interactive(
                config=test_config,
                tracer=None,
            )

    @pytest.mark.asyncio
    async def test_run_agent_interactive_multi_turn(self, mock_tracer, test_config):
        """Should handle multiple turns in interactive mode."""
        # Mock user inputs: two prompts then exit
        user_inputs = ["First prompt", "Second prompt", "exit"]
        input_iter = iter(user_inputs)

        mock_message = Mock()
        mock_message.content = "Response"

        async def mock_receive():
            yield mock_message

        mock_client = AsyncMock()
        mock_client.query = AsyncMock()
        mock_client.receive_response = mock_receive
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock()

        with patch("claude_otel.sdk_runner.ClaudeSDKClient", return_value=mock_client):
            with patch("builtins.input", side_effect=lambda _: next(input_iter)):
                exit_code = await run_agent_interactive(
                    config=test_config,
                    tracer=mock_tracer,
                )

        assert exit_code == 0
        # Should have called query twice (for two prompts before exit)
        assert mock_client.query.call_count == 2

    @pytest.mark.asyncio
    async def test_run_agent_interactive_handles_ctrl_c(self, mock_tracer, test_config):
        """Should handle Ctrl+C with double-press to exit."""
        # First Ctrl+C shows warning, second Ctrl+C exits
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock()

        with patch("claude_otel.sdk_runner.ClaudeSDKClient", return_value=mock_client):
            with patch("builtins.input", side_effect=[KeyboardInterrupt(), KeyboardInterrupt()]):
                exit_code = await run_agent_interactive(
                    config=test_config,
                    tracer=mock_tracer,
                )

        assert exit_code == 0  # Normal exit after two Ctrl+C

    @pytest.mark.asyncio
    async def test_run_agent_interactive_handles_eof(self, mock_tracer, test_config):
        """Should handle EOF gracefully."""
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock()

        with patch("claude_otel.sdk_runner.ClaudeSDKClient", return_value=mock_client):
            with patch("builtins.input", side_effect=EOFError()):
                exit_code = await run_agent_interactive(
                    config=test_config,
                    tracer=mock_tracer,
                )

        assert exit_code == 0

    @pytest.mark.asyncio
    async def test_run_agent_interactive_skips_empty_input(self, mock_tracer, test_config):
        """Should skip empty input and continue."""
        user_inputs = ["", "  ", "actual prompt", "exit"]
        input_iter = iter(user_inputs)

        mock_message = Mock()
        mock_message.content = "Response"

        async def mock_receive():
            yield mock_message

        mock_client = AsyncMock()
        mock_client.query = AsyncMock()
        mock_client.receive_response = mock_receive
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock()

        with patch("claude_otel.sdk_runner.ClaudeSDKClient", return_value=mock_client):
            with patch("builtins.input", side_effect=lambda _: next(input_iter)):
                await run_agent_interactive(
                    config=test_config,
                    tracer=mock_tracer,
                )

        # Should only query once (for "actual prompt")
        assert mock_client.query.call_count == 1

    @pytest.mark.asyncio
    async def test_run_agent_interactive_continues_on_error(self, mock_tracer, test_config):
        """Should continue session after individual query error."""
        user_inputs = ["First prompt", "exit"]
        input_iter = iter(user_inputs)

        mock_client = AsyncMock()
        # First query raises error, second should work
        mock_client.query = AsyncMock(side_effect=[RuntimeError("Test error"), None])
        mock_client.receive_response = AsyncMock(return_value=iter([]))
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock()

        with patch("claude_otel.sdk_runner.ClaudeSDKClient", return_value=mock_client):
            with patch("builtins.input", side_effect=lambda _: next(input_iter)):
                exit_code = await run_agent_interactive(
                    config=test_config,
                    tracer=mock_tracer,
                )

        # Should exit normally, not crash
        assert exit_code == 0

    @pytest.mark.asyncio
    async def test_run_agent_interactive_exit_commands(self, mock_tracer, test_config):
        """Should recognize various exit commands."""
        for exit_cmd in ["exit", "quit", "bye", "EXIT", "QUIT", "BYE"]:
            mock_client = AsyncMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock()

            with patch("claude_otel.sdk_runner.ClaudeSDKClient", return_value=mock_client):
                with patch("builtins.input", return_value=exit_cmd):
                    exit_code = await run_agent_interactive(
                        config=test_config,
                        tracer=mock_tracer,
                    )

            assert exit_code == 0

    @pytest.mark.asyncio
    async def test_run_agent_interactive_tracks_prompt_latency(self, mock_tracer, test_config):
        """Should track latency between prompts in interactive mode."""
        import time

        user_inputs = ["First prompt", "Second prompt", "exit"]
        input_iter = iter(user_inputs)

        mock_message = Mock()
        mock_message.content = "Response"

        async def mock_receive():
            yield mock_message

        mock_client = AsyncMock()
        mock_client.query = AsyncMock()
        mock_client.receive_response = mock_receive
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock()

        with patch("claude_otel.sdk_runner.ClaudeSDKClient", return_value=mock_client):
            with patch("builtins.input", side_effect=lambda _: next(input_iter)):
                with patch("claude_otel.sdk_runner.setup_sdk_hooks") as mock_setup:
                    mock_hooks = Mock()
                    mock_hooks.session_span = Mock()
                    mock_hooks.complete_session = Mock()
                    mock_hooks.metrics = {"model": "sonnet"}
                    mock_hooks.tools_used = []  # Must be a list for len() check
                    mock_setup.return_value = (mock_hooks, {})

                    with patch("claude_otel.sdk_runner.otel_metrics.record_prompt_latency") as mock_record:
                        exit_code = await run_agent_interactive(
                            config=test_config,
                            tracer=mock_tracer,
                        )

                        # Should have recorded latency for the second and third prompts
                        # (first prompt has no prior completion time, but "exit" counts as a prompt input)
                        assert mock_record.call_count == 2

                        # Verify the latency was recorded with model info
                        call_args = mock_record.call_args
                        latency_ms = call_args[0][0]
                        model = call_args[0][1]

                        assert latency_ms >= 0  # Should be non-negative
                        assert model == "sonnet"

        assert exit_code == 0

    @pytest.mark.asyncio
    async def test_run_agent_interactive_adds_latency_to_span(self, mock_tracer, test_config):
        """Should add prompt latency statistics to session span."""
        user_inputs = ["First prompt", "Second prompt", "Third prompt", "exit"]
        input_iter = iter(user_inputs)

        mock_message = Mock()
        mock_message.content = "Response"

        async def mock_receive():
            yield mock_message

        mock_client = AsyncMock()
        mock_client.query = AsyncMock()
        mock_client.receive_response = mock_receive
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock()

        with patch("claude_otel.sdk_runner.ClaudeSDKClient", return_value=mock_client):
            with patch("builtins.input", side_effect=lambda _: next(input_iter)):
                with patch("claude_otel.sdk_runner.setup_sdk_hooks") as mock_setup:
                    mock_span = Mock()
                    mock_hooks = Mock()
                    mock_hooks.session_span = mock_span
                    mock_hooks.complete_session = Mock()
                    mock_hooks.metrics = {"model": "sonnet"}
                    mock_hooks.tools_used = []  # Must be a list for len() check
                    mock_setup.return_value = (mock_hooks, {})

                    exit_code = await run_agent_interactive(
                        config=test_config,
                        tracer=mock_tracer,
                    )

                    # Should have set latency attributes on span
                    # (3 prompts total, so 2 latencies: prompt 2 and prompt 3)
                    set_attribute_calls = [
                        call for call in mock_span.set_attribute.call_args_list
                        if "prompt.latency" in str(call)
                    ]

                    # Should have avg, min, max, and count attributes
                    attribute_names = {call[0][0] for call in set_attribute_calls}
                    assert "prompt.latency_avg_ms" in attribute_names
                    assert "prompt.latency_min_ms" in attribute_names
                    assert "prompt.latency_max_ms" in attribute_names
                    assert "prompt.latency_count" in attribute_names

        assert exit_code == 0


class TestRunAgentInteractiveSync:
    """Tests for synchronous wrapper run_agent_interactive_sync."""

    def test_run_agent_interactive_sync_calls_async_version(self, mock_tracer, test_config):
        """Sync wrapper should call async version via asyncio.run."""
        with patch("claude_otel.sdk_runner.asyncio.run") as mock_run:
            mock_run.return_value = 0

            result = run_agent_interactive_sync(
                extra_args={"model": "opus"},
                config=test_config,
                tracer=mock_tracer,
            )

            assert result == 0
            mock_run.assert_called_once()


class TestSDKRunnerIntegration:
    """End-to-end integration tests for SDK runner."""

    @pytest.mark.asyncio
    async def test_sdk_runner_creates_spans(self, mock_tracer, test_config):
        """SDK runner should create proper span hierarchy."""
        mock_message = Mock()
        mock_message.content = "Test response"

        async def mock_receive():
            yield mock_message

        mock_client = AsyncMock()
        mock_client.query = AsyncMock()
        mock_client.receive_response = mock_receive
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock()

        with patch("claude_otel.sdk_runner.ClaudeSDKClient", return_value=mock_client):
            with patch("claude_otel.sdk_runner.setup_sdk_hooks") as mock_setup:
                mock_hooks = Mock()
                mock_hooks.session_span = Mock()
                mock_hooks.complete_session = Mock()
                mock_setup.return_value = (mock_hooks, {})

                exit_code = await run_agent_with_sdk(
                    prompt="Test prompt",
                    config=test_config,
                    tracer=mock_tracer,
                )

                assert exit_code == 0
                # Should have created hooks and completed the session
                mock_setup.assert_called_once_with(mock_tracer, None)
                mock_hooks.complete_session.assert_called_once()

    @pytest.mark.asyncio
    async def test_sdk_runner_with_hooks_integration(self, mock_tracer, test_config):
        """SDK runner should integrate properly with SDK hooks."""
        mock_message = Mock()
        mock_message.content = "Response"
        mock_message.usage = Mock(
            input_tokens=100,
            output_tokens=50,
            cache_read_input_tokens=0,
            cache_creation_input_tokens=0,
        )

        async def mock_receive():
            yield mock_message

        mock_client = AsyncMock()
        mock_client.query = AsyncMock()
        mock_client.receive_response = mock_receive
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock()

        with patch("claude_otel.sdk_runner.ClaudeSDKClient", return_value=mock_client):
            exit_code = await run_agent_with_sdk(
                prompt="Test",
                config=test_config,
                tracer=mock_tracer,
            )

            assert exit_code == 0
