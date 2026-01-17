"""Unit tests for interactive mode functionality."""

import pytest
from unittest.mock import Mock, patch, AsyncMock, MagicMock, call
from rich.console import Console
import asyncio

from claude_otel.sdk_runner import run_agent_interactive
from claude_otel.config import OTelConfig


class TestInteractiveMode:
    """Tests for interactive mode functionality."""

    @pytest.fixture
    def mock_config(self):
        """Create mock OTel configuration."""
        config = Mock(spec=OTelConfig)
        config.debug = False
        config.service_name = "test-service"
        config.endpoint = "http://localhost:4317"
        config.traces_enabled = True
        return config

    @pytest.fixture
    def mock_tracer(self):
        """Create mock tracer."""
        tracer = Mock()
        # Mock span creation
        span = MagicMock()
        span.__enter__ = Mock(return_value=span)
        span.__exit__ = Mock(return_value=False)
        span.set_attribute = Mock()
        span.set_status = Mock()
        tracer.start_as_current_span = Mock(return_value=span)
        return tracer

    @pytest.fixture
    def mock_logger(self):
        """Create mock logger."""
        return Mock()

    @pytest.mark.asyncio
    async def test_interactive_mode_single_turn(self, mock_config, mock_tracer, mock_logger):
        """Test interactive mode with single turn and exit command."""
        with patch("claude_otel.sdk_runner.ClaudeSDKClient") as mock_client_class, \
             patch("builtins.input") as mock_input, \
             patch("claude_otel.sdk_runner.setup_sdk_hooks") as mock_setup_hooks, \
             patch("claude_otel.sdk_runner.Console") as mock_console_class:

            # Setup mock client
            mock_client = AsyncMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client.query = AsyncMock()

            # Mock message response
            async def mock_receive():
                mock_message = Mock()
                mock_message.content = [{"type": "text", "text": "Hello! How can I help?"}]
                yield mock_message

            mock_client.receive_response = mock_receive
            mock_client_class.return_value = mock_client

            # Setup mock hooks
            mock_hooks = Mock()
            mock_hooks.session_span = Mock()
            mock_hooks.complete_session = Mock()
            mock_hooks.metrics = {
                "input_tokens": 10,
                "output_tokens": 20,
                "cache_read_tokens": 0,
                "cache_creation_tokens": 0,
            }
            mock_hooks.tools_used = []
            mock_hook_config = Mock()
            mock_setup_hooks.return_value = (mock_hooks, mock_hook_config)

            # Setup mock console
            mock_console = Mock(spec=Console)
            mock_console_class.return_value = mock_console

            # Simulate user input: one prompt then exit
            mock_input.side_effect = ["What is 2+2?", "exit"]

            # Run interactive mode
            exit_code = await run_agent_interactive(
                extra_args={"model": "opus"},
                config=mock_config,
                tracer=mock_tracer,
                logger=mock_logger,
            )

            # Verify exit code
            assert exit_code == 0

            # Verify client.query was called with the prompt
            mock_client.query.assert_called_once_with(prompt="What is 2+2?")

            # Verify session was completed
            mock_hooks.complete_session.assert_called_once()

            # Verify logger was called
            assert mock_logger.info.called

    @pytest.mark.asyncio
    async def test_interactive_mode_multiple_turns(self, mock_config, mock_tracer, mock_logger):
        """Test interactive mode with multiple conversation turns."""
        with patch("claude_otel.sdk_runner.ClaudeSDKClient") as mock_client_class, \
             patch("builtins.input") as mock_input, \
             patch("claude_otel.sdk_runner.setup_sdk_hooks") as mock_setup_hooks, \
             patch("claude_otel.sdk_runner.Console"):

            # Setup mock client
            mock_client = AsyncMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client.query = AsyncMock()

            # Mock message responses
            responses = [
                [{"type": "text", "text": "Response 1"}],
                [{"type": "text", "text": "Response 2"}],
                [{"type": "text", "text": "Response 3"}],
            ]
            response_index = 0

            async def mock_receive():
                nonlocal response_index
                mock_message = Mock()
                mock_message.content = responses[response_index]
                response_index += 1
                yield mock_message

            mock_client.receive_response = mock_receive
            mock_client_class.return_value = mock_client

            # Setup mock hooks
            mock_hooks = Mock()
            mock_hooks.session_span = Mock()
            mock_hooks.complete_session = Mock()
            mock_hooks.metrics = {
                "input_tokens": 30,
                "output_tokens": 60,
                "cache_read_tokens": 5,
                "cache_creation_tokens": 2,
            }
            mock_hooks.tools_used = ["read_file", "edit_file"]
            mock_hook_config = Mock()
            mock_setup_hooks.return_value = (mock_hooks, mock_hook_config)

            # Simulate user input: three prompts then quit
            mock_input.side_effect = ["First question", "Second question", "Third question", "quit"]

            # Run interactive mode
            exit_code = await run_agent_interactive(
                extra_args={},
                config=mock_config,
                tracer=mock_tracer,
                logger=mock_logger,
            )

            # Verify exit code
            assert exit_code == 0

            # Verify client.query was called three times
            assert mock_client.query.call_count == 3
            mock_client.query.assert_has_calls([
                call(prompt="First question"),
                call(prompt="Second question"),
                call(prompt="Third question"),
            ])

    @pytest.mark.asyncio
    async def test_interactive_mode_empty_input_skipped(self, mock_config, mock_tracer, mock_logger):
        """Test that empty input is skipped in interactive mode."""
        with patch("claude_otel.sdk_runner.ClaudeSDKClient") as mock_client_class, \
             patch("builtins.input") as mock_input, \
             patch("claude_otel.sdk_runner.setup_sdk_hooks") as mock_setup_hooks, \
             patch("claude_otel.sdk_runner.Console"):

            # Setup mock client
            mock_client = AsyncMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client.query = AsyncMock()

            async def mock_receive():
                mock_message = Mock()
                mock_message.content = [{"type": "text", "text": "Response"}]
                yield mock_message

            mock_client.receive_response = mock_receive
            mock_client_class.return_value = mock_client

            # Setup mock hooks
            mock_hooks = Mock()
            mock_hooks.session_span = Mock()
            mock_hooks.complete_session = Mock()
            mock_hooks.metrics = {}
            mock_hooks.tools_used = []
            mock_hook_config = Mock()
            mock_setup_hooks.return_value = (mock_hooks, mock_hook_config)

            # Simulate input: empty strings and whitespace should be skipped
            mock_input.side_effect = ["", "  ", "\t", "actual question", "bye"]

            # Run interactive mode
            exit_code = await run_agent_interactive(
                extra_args={},
                config=mock_config,
                tracer=mock_tracer,
                logger=mock_logger,
            )

            # Verify exit code
            assert exit_code == 0

            # Verify client.query was called only once (empty inputs skipped)
            mock_client.query.assert_called_once_with(prompt="actual question")

    @pytest.mark.asyncio
    async def test_interactive_mode_exit_commands(self, mock_config, mock_tracer, mock_logger):
        """Test that all exit commands (exit, quit, bye) work correctly."""
        for exit_command in ["exit", "quit", "bye", "EXIT", "QUIT", "BYE"]:
            with patch("claude_otel.sdk_runner.ClaudeSDKClient") as mock_client_class, \
                 patch("builtins.input") as mock_input, \
                 patch("claude_otel.sdk_runner.setup_sdk_hooks") as mock_setup_hooks, \
                 patch("claude_otel.sdk_runner.Console"):

                # Setup mock client
                mock_client = AsyncMock()
                mock_client.__aenter__ = AsyncMock(return_value=mock_client)
                mock_client.__aexit__ = AsyncMock(return_value=False)
                mock_client_class.return_value = mock_client

                # Setup mock hooks
                mock_hooks = Mock()
                mock_hooks.session_span = Mock()
                mock_hooks.complete_session = Mock()
                mock_hooks.metrics = {}
                mock_hooks.tools_used = []
                mock_hook_config = Mock()
                mock_setup_hooks.return_value = (mock_hooks, mock_hook_config)

                # Simulate exit command
                mock_input.side_effect = [exit_command]

                # Run interactive mode
                exit_code = await run_agent_interactive(
                    extra_args={},
                    config=mock_config,
                    tracer=mock_tracer,
                    logger=mock_logger,
                )

                # Verify exit code
                assert exit_code == 0

                # Verify no queries were made
                assert not hasattr(mock_client, 'query') or not mock_client.query.called

    @pytest.mark.asyncio
    async def test_interactive_mode_keyboard_interrupt_single(self, mock_config, mock_tracer, mock_logger):
        """Test single Ctrl+C shows warning and continues."""
        with patch("claude_otel.sdk_runner.ClaudeSDKClient") as mock_client_class, \
             patch("builtins.input") as mock_input, \
             patch("claude_otel.sdk_runner.setup_sdk_hooks") as mock_setup_hooks, \
             patch("claude_otel.sdk_runner.Console") as mock_console_class:

            # Setup mock client
            mock_client = AsyncMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client.query = AsyncMock()

            async def mock_receive():
                mock_message = Mock()
                mock_message.content = [{"type": "text", "text": "Response"}]
                yield mock_message

            mock_client.receive_response = mock_receive
            mock_client_class.return_value = mock_client

            # Setup mock hooks
            mock_hooks = Mock()
            mock_hooks.session_span = Mock()
            mock_hooks.complete_session = Mock()
            mock_hooks.metrics = {}
            mock_hooks.tools_used = []
            mock_hook_config = Mock()
            mock_setup_hooks.return_value = (mock_hooks, mock_hook_config)

            # Setup mock console
            mock_console = Mock(spec=Console)
            mock_console_class.return_value = mock_console

            # Simulate: Ctrl+C, then normal exit
            mock_input.side_effect = [KeyboardInterrupt(), "exit"]

            # Run interactive mode
            exit_code = await run_agent_interactive(
                extra_args={},
                config=mock_config,
                tracer=mock_tracer,
                logger=mock_logger,
            )

            # Verify exit code
            assert exit_code == 0

            # Verify warning was printed
            assert mock_console.print.called
            # Check that warning message was shown
            print_calls = [str(call) for call in mock_console.print.call_args_list]
            assert any("Ctrl+C again" in str(call) or "exit" in str(call) for call in print_calls)

    @pytest.mark.asyncio
    async def test_interactive_mode_keyboard_interrupt_double(self, mock_config, mock_tracer, mock_logger):
        """Test double Ctrl+C exits immediately."""
        with patch("claude_otel.sdk_runner.ClaudeSDKClient") as mock_client_class, \
             patch("builtins.input") as mock_input, \
             patch("claude_otel.sdk_runner.setup_sdk_hooks") as mock_setup_hooks, \
             patch("claude_otel.sdk_runner.Console") as mock_console_class:

            # Setup mock client
            mock_client = AsyncMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client_class.return_value = mock_client

            # Setup mock hooks
            mock_hooks = Mock()
            mock_hooks.session_span = Mock()
            mock_hooks.complete_session = Mock()
            mock_hooks.metrics = {}
            mock_hooks.tools_used = []
            mock_hook_config = Mock()
            mock_setup_hooks.return_value = (mock_hooks, mock_hook_config)

            # Setup mock console
            mock_console = Mock(spec=Console)
            mock_console_class.return_value = mock_console

            # Simulate: two consecutive Ctrl+C
            mock_input.side_effect = [KeyboardInterrupt(), KeyboardInterrupt()]

            # Run interactive mode
            exit_code = await run_agent_interactive(
                extra_args={},
                config=mock_config,
                tracer=mock_tracer,
                logger=mock_logger,
            )

            # Verify exit code
            assert exit_code == 0

            # Verify console output
            assert mock_console.print.called

    @pytest.mark.asyncio
    async def test_interactive_mode_eof_handling(self, mock_config, mock_tracer, mock_logger):
        """Test EOF (piped input) handling."""
        with patch("claude_otel.sdk_runner.ClaudeSDKClient") as mock_client_class, \
             patch("builtins.input") as mock_input, \
             patch("claude_otel.sdk_runner.setup_sdk_hooks") as mock_setup_hooks, \
             patch("claude_otel.sdk_runner.Console") as mock_console_class:

            # Setup mock client
            mock_client = AsyncMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client_class.return_value = mock_client

            # Setup mock hooks
            mock_hooks = Mock()
            mock_hooks.session_span = Mock()
            mock_hooks.complete_session = Mock()
            mock_hooks.metrics = {}
            mock_hooks.tools_used = []
            mock_hook_config = Mock()
            mock_setup_hooks.return_value = (mock_hooks, mock_hook_config)

            # Setup mock console
            mock_console = Mock(spec=Console)
            mock_console_class.return_value = mock_console

            # Simulate EOF
            mock_input.side_effect = EOFError()

            # Run interactive mode
            exit_code = await run_agent_interactive(
                extra_args={},
                config=mock_config,
                tracer=mock_tracer,
                logger=mock_logger,
            )

            # Verify exit code
            assert exit_code == 0

            # Verify EOF message was shown
            assert mock_console.print.called
            print_calls = [str(call) for call in mock_console.print.call_args_list]
            assert any("EOF" in str(call) for call in print_calls)

    @pytest.mark.asyncio
    async def test_interactive_mode_error_continues_session(self, mock_config, mock_tracer, mock_logger):
        """Test that errors during query don't exit the session."""
        with patch("claude_otel.sdk_runner.ClaudeSDKClient") as mock_client_class, \
             patch("builtins.input") as mock_input, \
             patch("claude_otel.sdk_runner.setup_sdk_hooks") as mock_setup_hooks, \
             patch("claude_otel.sdk_runner.Console") as mock_console_class:

            # Setup mock client
            mock_client = AsyncMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)

            # First query raises error, second succeeds
            call_count = 0
            async def mock_query(prompt):
                nonlocal call_count
                call_count += 1
                if call_count == 1:
                    raise RuntimeError("API error")

            mock_client.query = mock_query

            async def mock_receive():
                mock_message = Mock()
                mock_message.content = [{"type": "text", "text": "Success"}]
                yield mock_message

            mock_client.receive_response = mock_receive
            mock_client_class.return_value = mock_client

            # Setup mock hooks
            mock_hooks = Mock()
            mock_hooks.session_span = Mock()
            mock_hooks.complete_session = Mock()
            mock_hooks.metrics = {}
            mock_hooks.tools_used = []
            mock_hook_config = Mock()
            mock_setup_hooks.return_value = (mock_hooks, mock_hook_config)

            # Setup mock console
            mock_console = Mock(spec=Console)
            mock_console_class.return_value = mock_console

            # Simulate: query with error, then successful query, then exit
            mock_input.side_effect = ["query 1", "query 2", "exit"]

            # Run interactive mode
            exit_code = await run_agent_interactive(
                extra_args={},
                config=mock_config,
                tracer=mock_tracer,
                logger=mock_logger,
            )

            # Verify exit code (should be 0, not error)
            assert exit_code == 0

            # Verify error was logged
            assert mock_logger.error.called
            error_calls = [str(call) for call in mock_logger.error.call_args_list]
            assert any("API error" in str(call) for call in error_calls)

            # Verify console showed error
            print_calls = [str(call) for call in mock_console.print.call_args_list]
            assert any("Error" in str(call) for call in print_calls)

    @pytest.mark.asyncio
    async def test_interactive_mode_session_metrics_tracking(self, mock_config, mock_tracer, mock_logger):
        """Test that session metrics are tracked and displayed."""
        with patch("claude_otel.sdk_runner.ClaudeSDKClient") as mock_client_class, \
             patch("builtins.input") as mock_input, \
             patch("claude_otel.sdk_runner.setup_sdk_hooks") as mock_setup_hooks, \
             patch("claude_otel.sdk_runner.Console") as mock_console_class:

            # Setup mock client
            mock_client = AsyncMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client.query = AsyncMock()

            async def mock_receive():
                mock_message = Mock()
                mock_message.content = [{"type": "text", "text": "Response"}]
                yield mock_message

            mock_client.receive_response = mock_receive
            mock_client_class.return_value = mock_client

            # Setup mock hooks with metrics
            mock_hooks = Mock()
            mock_hooks.session_span = Mock()
            mock_hooks.complete_session = Mock()
            mock_hooks.metrics = {
                "input_tokens": 150,
                "output_tokens": 300,
                "cache_read_tokens": 50,
                "cache_creation_tokens": 25,
            }
            mock_hooks.tools_used = ["read", "write", "search"]
            mock_hook_config = Mock()
            mock_setup_hooks.return_value = (mock_hooks, mock_hook_config)

            # Setup mock console
            mock_console = Mock(spec=Console)
            mock_console_class.return_value = mock_console

            # Simulate: two prompts then exit
            mock_input.side_effect = ["prompt 1", "prompt 2", "exit"]

            # Run interactive mode
            exit_code = await run_agent_interactive(
                extra_args={},
                config=mock_config,
                tracer=mock_tracer,
                logger=mock_logger,
            )

            # Verify exit code
            assert exit_code == 0

            # Verify session summary was printed
            print_calls = [str(call) for call in mock_console.print.call_args_list]

            # Check for session summary elements
            summary_text = " ".join(str(call) for call in print_calls)
            assert "Session Summary" in summary_text or "Prompts" in summary_text

            # Verify session completion
            mock_hooks.complete_session.assert_called_once()

    @pytest.mark.asyncio
    async def test_interactive_mode_with_extra_args(self, mock_config, mock_tracer, mock_logger):
        """Test interactive mode properly passes extra_args to SDK."""
        with patch("claude_otel.sdk_runner.ClaudeSDKClient") as mock_client_class, \
             patch("builtins.input") as mock_input, \
             patch("claude_otel.sdk_runner.setup_sdk_hooks") as mock_setup_hooks, \
             patch("claude_otel.sdk_runner.Console"), \
             patch("claude_otel.sdk_runner.ClaudeAgentOptions") as mock_options_class:

            # Setup mock client
            mock_client = AsyncMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client.query = AsyncMock()

            async def mock_receive():
                mock_message = Mock()
                mock_message.content = [{"type": "text", "text": "Response"}]
                yield mock_message

            mock_client.receive_response = mock_receive
            mock_client_class.return_value = mock_client

            # Setup mock hooks
            mock_hooks = Mock()
            mock_hooks.session_span = Mock()
            mock_hooks.complete_session = Mock()
            mock_hooks.metrics = {}
            mock_hooks.tools_used = []
            mock_hook_config = Mock()
            mock_setup_hooks.return_value = (mock_hooks, mock_hook_config)

            # Mock options
            mock_options = Mock()
            mock_options_class.return_value = mock_options

            # Simulate: one prompt then exit
            mock_input.side_effect = ["test", "exit"]

            # Run interactive mode with extra args
            extra_args = {
                "model": "opus",
                "permission-mode": "bypassPermissions",
            }
            exit_code = await run_agent_interactive(
                extra_args=extra_args,
                config=mock_config,
                tracer=mock_tracer,
                logger=mock_logger,
            )

            # Verify exit code
            assert exit_code == 0

            # Verify ClaudeAgentOptions was created with extra_args
            mock_options_class.assert_called_once()
            call_kwargs = mock_options_class.call_args.kwargs
            assert call_kwargs["extra_args"] == extra_args

    @pytest.mark.asyncio
    async def test_interactive_mode_keyboard_interrupt_from_outside(self, mock_config, mock_tracer, mock_logger):
        """Test KeyboardInterrupt raised from outside the loop (immediate exit)."""
        with patch("claude_otel.sdk_runner.ClaudeSDKClient") as mock_client_class, \
             patch("builtins.input") as mock_input, \
             patch("claude_otel.sdk_runner.setup_sdk_hooks") as mock_setup_hooks, \
             patch("claude_otel.sdk_runner.Console") as mock_console_class:

            # Setup mock client that raises KeyboardInterrupt on __aenter__
            mock_client = AsyncMock()
            mock_client.__aenter__ = AsyncMock(side_effect=KeyboardInterrupt())
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client_class.return_value = mock_client

            # Setup mock hooks
            mock_hooks = Mock()
            mock_hooks.session_span = Mock()
            mock_hooks.complete_session = Mock()
            mock_hooks.metrics = {}
            mock_hooks.tools_used = []
            mock_hook_config = Mock()
            mock_setup_hooks.return_value = (mock_hooks, mock_hook_config)

            # Setup mock console
            mock_console = Mock(spec=Console)
            mock_console_class.return_value = mock_console

            # Run interactive mode (should catch outer KeyboardInterrupt)
            exit_code = await run_agent_interactive(
                extra_args={},
                config=mock_config,
                tracer=mock_tracer,
                logger=mock_logger,
            )

            # Verify exit code is 130 (standard for SIGINT)
            assert exit_code == 130

            # Verify session completion was attempted
            mock_hooks.complete_session.assert_called_once()

            # Verify logger recorded interruption
            assert mock_logger.info.called
            info_calls = [str(call) for call in mock_logger.info.call_args_list]
            assert any("interrupt" in str(call).lower() for call in info_calls)
