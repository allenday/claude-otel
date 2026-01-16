"""Unit tests for configurable redaction rules."""

import json
import os
import tempfile
import pytest

from claude_otel.config import (
    RedactionConfig,
    load_redaction_config,
    _load_redaction_config_file,
    _parse_redaction_config_dict,
)
from claude_otel.pii import (
    redact,
    reset_redaction_cache,
    _get_redact_patterns,
    _get_allowlist_patterns,
    DEFAULT_REDACT_PATTERNS,
)


class TestRedactionConfig:
    """Tests for RedactionConfig dataclass."""

    def test_default_values(self):
        """Default config should have empty patterns and use_defaults=True."""
        config = RedactionConfig()
        assert config.patterns == []
        assert config.allowlist == []
        assert config.use_defaults is True
        assert config.pattern_groups == {}
        assert config.allowlist_groups == {}

    def test_get_all_patterns_flat(self):
        """get_all_patterns should return patterns list."""
        config = RedactionConfig(patterns=["pattern1", "pattern2"])
        assert config.get_all_patterns() == ["pattern1", "pattern2"]

    def test_get_all_patterns_with_groups(self):
        """get_all_patterns should include patterns from groups."""
        config = RedactionConfig(
            patterns=["base"],
            pattern_groups={"aws": ["aws1", "aws2"], "pii": ["pii1"]},
        )
        all_patterns = config.get_all_patterns()
        assert "base" in all_patterns
        assert "aws1" in all_patterns
        assert "aws2" in all_patterns
        assert "pii1" in all_patterns

    def test_get_all_allowlist_flat(self):
        """get_all_allowlist should return allowlist list."""
        config = RedactionConfig(allowlist=["allow1", "allow2"])
        assert config.get_all_allowlist() == ["allow1", "allow2"]

    def test_get_all_allowlist_with_groups(self):
        """get_all_allowlist should include patterns from groups."""
        config = RedactionConfig(
            allowlist=["base"],
            allowlist_groups={"safe": ["safe1", "safe2"]},
        )
        all_allowlist = config.get_all_allowlist()
        assert "base" in all_allowlist
        assert "safe1" in all_allowlist
        assert "safe2" in all_allowlist


class TestParseRedactionConfigDict:
    """Tests for _parse_redaction_config_dict function."""

    def test_empty_dict(self):
        """Empty dict should return config with defaults."""
        config = _parse_redaction_config_dict({})
        assert config.patterns == []
        assert config.allowlist == []
        assert config.use_defaults is True

    def test_patterns_list(self):
        """Should parse patterns list correctly."""
        config = _parse_redaction_config_dict({"patterns": ["p1", "p2"]})
        assert config.patterns == ["p1", "p2"]

    def test_allowlist_list(self):
        """Should parse allowlist list correctly."""
        config = _parse_redaction_config_dict({"allowlist": ["a1", "a2"]})
        assert config.allowlist == ["a1", "a2"]

    def test_use_defaults_false(self):
        """Should parse use_defaults=false correctly."""
        config = _parse_redaction_config_dict({"use_defaults": False})
        assert config.use_defaults is False

    def test_use_defaults_string(self):
        """Should parse use_defaults as string."""
        config = _parse_redaction_config_dict({"use_defaults": "false"})
        assert config.use_defaults is False

        config = _parse_redaction_config_dict({"use_defaults": "true"})
        assert config.use_defaults is True

    def test_pattern_groups(self):
        """Should parse pattern_groups correctly."""
        config = _parse_redaction_config_dict({
            "pattern_groups": {
                "aws": ["AKIA.*", "aws_secret.*"],
                "generic": ["password.*"],
            }
        })
        assert "aws" in config.pattern_groups
        assert config.pattern_groups["aws"] == ["AKIA.*", "aws_secret.*"]
        assert config.pattern_groups["generic"] == ["password.*"]

    def test_allowlist_groups(self):
        """Should parse allowlist_groups correctly."""
        config = _parse_redaction_config_dict({
            "allowlist_groups": {
                "safe": ["test_.*", "example_.*"],
            }
        })
        assert "safe" in config.allowlist_groups
        assert config.allowlist_groups["safe"] == ["test_.*", "example_.*"]

    def test_invalid_patterns_not_list(self):
        """Should handle non-list patterns gracefully."""
        config = _parse_redaction_config_dict({"patterns": "not a list"})
        assert config.patterns == []

    def test_filters_empty_patterns(self):
        """Should filter out empty patterns."""
        config = _parse_redaction_config_dict({"patterns": ["valid", "", None, "also_valid"]})
        assert config.patterns == ["valid", "also_valid"]


class TestLoadRedactionConfigFile:
    """Tests for _load_redaction_config_file function."""

    def test_nonexistent_file(self):
        """Should return None for nonexistent file."""
        config = _load_redaction_config_file("/nonexistent/path/config.json")
        assert config is None

    def test_valid_json_file(self):
        """Should load valid JSON config file."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump({
                "patterns": ["custom_secret.*"],
                "allowlist": ["safe_.*"],
                "use_defaults": False,
            }, f)
            temp_path = f.name

        try:
            config = _load_redaction_config_file(temp_path)
            assert config is not None
            assert config.patterns == ["custom_secret.*"]
            assert config.allowlist == ["safe_.*"]
            assert config.use_defaults is False
        finally:
            os.unlink(temp_path)

    def test_invalid_json_file(self):
        """Should return None for invalid JSON."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            f.write("not valid json {")
            temp_path = f.name

        try:
            config = _load_redaction_config_file(temp_path)
            assert config is None
        finally:
            os.unlink(temp_path)


class TestLoadRedactionConfig:
    """Tests for load_redaction_config function with environment variables."""

    def setup_method(self):
        """Clear environment before each test."""
        self._orig_env = os.environ.copy()
        for key in list(os.environ.keys()):
            if key.startswith("CLAUDE_OTEL_REDACT"):
                del os.environ[key]
        reset_redaction_cache()

    def teardown_method(self):
        """Restore environment after each test."""
        os.environ.clear()
        os.environ.update(self._orig_env)
        reset_redaction_cache()

    def test_default_config(self):
        """Should return default config when no env vars set."""
        config = load_redaction_config()
        assert config.patterns == []
        assert config.allowlist == []
        assert config.use_defaults is True

    def test_patterns_from_env(self):
        """Should load patterns from CLAUDE_OTEL_REDACT_PATTERNS."""
        os.environ["CLAUDE_OTEL_REDACT_PATTERNS"] = "custom1,custom2"
        config = load_redaction_config()
        assert "custom1" in config.patterns
        assert "custom2" in config.patterns

    def test_allowlist_from_env(self):
        """Should load allowlist from CLAUDE_OTEL_REDACT_ALLOWLIST."""
        os.environ["CLAUDE_OTEL_REDACT_ALLOWLIST"] = "safe1,safe2"
        config = load_redaction_config()
        assert "safe1" in config.allowlist
        assert "safe2" in config.allowlist

    def test_disable_defaults_from_env(self):
        """Should disable defaults when CLAUDE_OTEL_REDACT_DISABLE_DEFAULTS=true."""
        os.environ["CLAUDE_OTEL_REDACT_DISABLE_DEFAULTS"] = "true"
        config = load_redaction_config()
        assert config.use_defaults is False

    def test_config_file_with_env_override(self):
        """Env vars should append to config file patterns."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump({"patterns": ["file_pattern"]}, f)
            temp_path = f.name

        try:
            os.environ["CLAUDE_OTEL_REDACT_CONFIG"] = temp_path
            os.environ["CLAUDE_OTEL_REDACT_PATTERNS"] = "env_pattern"
            config = load_redaction_config()
            assert "file_pattern" in config.patterns
            assert "env_pattern" in config.patterns
        finally:
            os.unlink(temp_path)


class TestRedactWithAllowlist:
    """Tests for redact function with allowlist support."""

    def setup_method(self):
        """Clear environment and cache before each test."""
        self._orig_env = os.environ.copy()
        for key in list(os.environ.keys()):
            if key.startswith("CLAUDE_OTEL_REDACT"):
                del os.environ[key]
        reset_redaction_cache()

    def teardown_method(self):
        """Restore environment after each test."""
        os.environ.clear()
        os.environ.update(self._orig_env)
        reset_redaction_cache()

    def test_default_patterns_applied(self):
        """Default patterns should redact secrets."""
        text = "api_key=secret123 and password=mysecret"
        result = redact(text)
        assert "secret123" not in result
        assert "mysecret" not in result
        assert "[REDACTED]" in result

    def test_allowlist_prevents_redaction(self):
        """Allowlist patterns should prevent redaction."""
        os.environ["CLAUDE_OTEL_REDACT_PATTERNS"] = r"test_\w+"
        os.environ["CLAUDE_OTEL_REDACT_ALLOWLIST"] = r"test_allowed"
        reset_redaction_cache()

        # test_allowed should not be redacted
        text = "test_allowed and test_secret"
        result = redact(text)
        assert "test_allowed" in result
        assert "[REDACTED]" in result  # test_secret should be redacted

    def test_disable_defaults(self):
        """Disabling defaults should not redact with default patterns."""
        os.environ["CLAUDE_OTEL_REDACT_DISABLE_DEFAULTS"] = "true"
        reset_redaction_cache()

        # This would normally be redacted by default patterns
        text = "api_key=secret123"
        result = redact(text)
        # Without defaults, nothing should be redacted
        assert result == text

    def test_custom_pattern_only(self):
        """Custom patterns should work when defaults disabled."""
        os.environ["CLAUDE_OTEL_REDACT_DISABLE_DEFAULTS"] = "true"
        os.environ["CLAUDE_OTEL_REDACT_PATTERNS"] = r"my_secret_\w+"
        reset_redaction_cache()

        text = "my_secret_value should be redacted but api_key=123 not"
        result = redact(text)
        assert "my_secret_value" not in result
        assert "[REDACTED]" in result
        assert "api_key=123" in result  # Default pattern disabled

    def test_invalid_pattern_skipped(self):
        """Invalid regex patterns should be silently skipped."""
        os.environ["CLAUDE_OTEL_REDACT_PATTERNS"] = r"[invalid(regex,valid_pattern"
        reset_redaction_cache()

        # Should not crash
        patterns = _get_redact_patterns()
        # Default patterns should still be present
        assert len(patterns) >= len(DEFAULT_REDACT_PATTERNS)


class TestRedactionCacheReset:
    """Tests for cache reset functionality."""

    def setup_method(self):
        """Clear environment before each test."""
        self._orig_env = os.environ.copy()
        for key in list(os.environ.keys()):
            if key.startswith("CLAUDE_OTEL_REDACT"):
                del os.environ[key]
        reset_redaction_cache()

    def teardown_method(self):
        """Restore environment after each test."""
        os.environ.clear()
        os.environ.update(self._orig_env)
        reset_redaction_cache()

    def test_cache_reset_clears_patterns(self):
        """reset_redaction_cache should clear cached patterns."""
        # Load patterns
        _ = _get_redact_patterns()

        # Change env and reset
        os.environ["CLAUDE_OTEL_REDACT_PATTERNS"] = "new_pattern"
        reset_redaction_cache()

        # Patterns should now include new one
        patterns = _get_redact_patterns()
        pattern_strings = [p.pattern for p in patterns]
        assert "new_pattern" in pattern_strings

    def test_cache_reset_clears_allowlist(self):
        """reset_redaction_cache should clear cached allowlist."""
        # Load allowlist
        _ = _get_allowlist_patterns()

        # Change env and reset
        os.environ["CLAUDE_OTEL_REDACT_ALLOWLIST"] = "new_allow"
        reset_redaction_cache()

        # Allowlist should now include new one
        allowlist = _get_allowlist_patterns()
        pattern_strings = [p.pattern for p in allowlist]
        assert "new_allow" in pattern_strings
