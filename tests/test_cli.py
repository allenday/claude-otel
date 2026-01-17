"""Unit tests for CLI module."""

import pytest

from claude_otel.cli import parse_claude_args


class TestParseClaudeArgs:
    """Tests for parse_claude_args function."""

    def test_none_args(self):
        """None args should return None prompt and empty dict."""
        prompt, extra_args = parse_claude_args(None)
        assert prompt is None
        assert extra_args == {}

    def test_empty_list(self):
        """Empty list should return None prompt and empty dict."""
        prompt, extra_args = parse_claude_args([])
        assert prompt is None
        assert extra_args == {}

    def test_prompt_only(self):
        """Single non-flag argument should be treated as prompt."""
        prompt, extra_args = parse_claude_args(["fix this bug"])
        assert prompt == "fix this bug"
        assert extra_args == {}

    def test_flag_with_equals_no_prompt(self):
        """Flag with equals format and no prompt."""
        prompt, extra_args = parse_claude_args(["--model=opus"])
        assert prompt is None
        assert extra_args == {"model": "opus"}

    def test_flag_with_equals_and_prompt(self):
        """Flag with equals format followed by prompt."""
        prompt, extra_args = parse_claude_args(["--model=opus", "fix the bug"])
        assert prompt == "fix the bug"
        assert extra_args == {"model": "opus"}

    def test_multiple_flags_with_equals(self):
        """Multiple flags with equals format."""
        prompt, extra_args = parse_claude_args([
            "--model=opus",
            "--permission-mode=bypassPermissions",
            "analyze this"
        ])
        assert prompt == "analyze this"
        assert extra_args == {
            "model": "opus",
            "permission-mode": "bypassPermissions"
        }

    def test_flag_with_value_space_separated(self):
        """Flag followed by value (space-separated format)."""
        prompt, extra_args = parse_claude_args(["--model", "opus", "review code"])
        assert prompt == "review code"
        assert extra_args == {"model": "opus"}

    def test_multiple_flags_space_separated(self):
        """Multiple flags with space-separated values."""
        prompt, extra_args = parse_claude_args([
            "--model", "opus",
            "--permission-mode", "bypassPermissions",
            "check this"
        ])
        assert prompt == "check this"
        assert extra_args == {
            "model": "opus",
            "permission-mode": "bypassPermissions"
        }

    def test_boolean_flag_standalone(self):
        """Standalone flag without value (boolean flag)."""
        prompt, extra_args = parse_claude_args(["--verbose", "test prompt"])
        assert prompt == "test prompt"
        assert extra_args == {"verbose": None}

    def test_multiple_boolean_flags(self):
        """Multiple boolean flags."""
        prompt, extra_args = parse_claude_args([
            "--verbose",
            "--debug",
            "run this"
        ])
        assert prompt == "run this"
        assert extra_args == {"verbose": None, "debug": None}

    def test_mixed_flag_formats(self):
        """Mix of equals, space-separated, and boolean flags."""
        prompt, extra_args = parse_claude_args([
            "--model=opus",
            "--verbose",
            "--permission-mode", "bypassPermissions",
            "complex command"
        ])
        assert prompt == "complex command"
        assert extra_args == {
            "model": "opus",
            "verbose": None,
            "permission-mode": "bypassPermissions"
        }

    def test_flag_value_with_equals_sign(self):
        """Flag value containing equals sign should be preserved."""
        prompt, extra_args = parse_claude_args([
            "--config=key=value",
            "test"
        ])
        assert prompt == "test"
        assert extra_args == {"config": "key=value"}

    def test_flag_before_prompt(self):
        """Flag before prompt in various positions."""
        prompt, extra_args = parse_claude_args([
            "--model=opus",
            "my prompt",
            "--verbose"
        ])
        # Last non-flag argument is the prompt
        assert prompt == "my prompt"
        assert extra_args == {"model": "opus", "verbose": None}

    def test_prompt_with_dashes(self):
        """Prompt that happens to contain dashes but isn't a flag."""
        # The function finds the last non-flag argument
        # "test-string" would be treated as prompt
        prompt, extra_args = parse_claude_args([
            "--model=opus",
            "test-string"
        ])
        assert prompt == "test-string"
        assert extra_args == {"model": "opus"}

    def test_single_dash_flag(self):
        """Single dash flags should be handled."""
        prompt, extra_args = parse_claude_args([
            "-m=opus",
            "prompt here"
        ])
        assert prompt == "prompt here"
        assert extra_args == {"m": "opus"}

    def test_multiple_single_dash_flags(self):
        """Multiple single dash flags."""
        prompt, extra_args = parse_claude_args([
            "-v",
            "-m", "opus",
            "test"
        ])
        assert prompt == "test"
        assert extra_args == {"v": None, "m": "opus"}

    def test_flag_at_end_with_no_value(self):
        """Boolean flag at the end of args."""
        prompt, extra_args = parse_claude_args([
            "my prompt",
            "--verbose"
        ])
        assert prompt == "my prompt"
        assert extra_args == {"verbose": None}

    def test_consecutive_flags_no_prompt(self):
        """Multiple consecutive flags with no prompt."""
        prompt, extra_args = parse_claude_args([
            "--model=opus",
            "--verbose",
            "--debug"
        ])
        assert prompt is None
        assert extra_args == {
            "model": "opus",
            "verbose": None,
            "debug": None
        }

    def test_empty_flag_value(self):
        """Flag with empty value after equals."""
        prompt, extra_args = parse_claude_args([
            "--config=",
            "prompt"
        ])
        assert prompt == "prompt"
        assert extra_args == {"config": ""}

    def test_flag_with_spaces_in_value(self):
        """Flag value with spaces (in equals format)."""
        prompt, extra_args = parse_claude_args([
            "--message=hello world",
            "test"
        ])
        assert prompt == "test"
        assert extra_args == {"message": "hello world"}

    def test_complex_real_world_example(self):
        """Real-world example with multiple flag types."""
        prompt, extra_args = parse_claude_args([
            "--model=sonnet",
            "--permission-mode=bypassPermissions",
            "--verbose",
            "--timeout", "30",
            "analyze the codebase and find bugs"
        ])
        assert prompt == "analyze the codebase and find bugs"
        assert extra_args == {
            "model": "sonnet",
            "permission-mode": "bypassPermissions",
            "verbose": None,
            "timeout": "30"
        }

    def test_double_dash_only(self):
        """Only flags, no prompt."""
        prompt, extra_args = parse_claude_args([
            "--model=opus",
            "--permission-mode=bypassPermissions"
        ])
        assert prompt is None
        assert extra_args == {
            "model": "opus",
            "permission-mode": "bypassPermissions"
        }

    def test_prompt_detection_last_non_flag(self):
        """Prompt is always the last non-flag argument."""
        prompt, extra_args = parse_claude_args([
            "not-a-flag",
            "--model=opus",
            "actual prompt"
        ])
        # "not-a-flag" would appear first but "actual prompt" is last non-flag
        assert prompt == "actual prompt"
        # "not-a-flag" gets treated as a flag somehow? Let's verify behavior
        # Looking at the code: it pops from end backwards, so "actual prompt" is found first
        # Then "not-a-flag" would be in claude_args and parsed as... part of flags?
        # Actually, re-reading code: it finds LAST non-flag and pops it
        # So "actual prompt" is the prompt, and "not-a-flag" stays in args
        # Then "not-a-flag" doesn't start with - so... it would be skipped in flag parsing

    def test_flags_after_prompt_in_middle(self):
        """Test case where prompt is in the middle but last non-flag wins."""
        # Based on code: finds last non-flag argument going backwards
        prompt, extra_args = parse_claude_args([
            "early-arg",
            "--model=opus",
            "--verbose"
        ])
        # "early-arg" is the last (only) non-flag argument
        assert prompt == "early-arg"
        assert extra_args == {"model": "opus", "verbose": None}

    def test_value_that_looks_like_flag(self):
        """Value for a flag that looks like another flag."""
        # This is ambiguous: --config --verbose
        # Code would treat --verbose as standalone boolean flag
        # since it starts with -
        prompt, extra_args = parse_claude_args([
            "--config", "--verbose",
            "test"
        ])
        assert prompt == "test"
        # --config has no value (next arg is a flag)
        # So --config is standalone, --verbose is standalone
        assert extra_args == {"config": None, "verbose": None}
