"""PII safeguards for telemetry data.

Provides truncation and lightweight redaction to avoid storing sensitive data
in spans and logs. Designed to be conservative - prefer truncation over complex
pattern matching to minimize false negatives.

Configuration via environment:
    CLAUDE_OTEL_MAX_ATTR_LENGTH: Max attribute string length (default: 256)
    CLAUDE_OTEL_MAX_PAYLOAD_BYTES: Max payload size to capture (default: 1024)

Redaction configuration (see config.py for full details):
    CLAUDE_OTEL_REDACT_CONFIG: Path to JSON config file for redaction rules
    CLAUDE_OTEL_REDACT_PATTERNS: Comma-separated regex patterns to redact
    CLAUDE_OTEL_REDACT_ALLOWLIST: Comma-separated regex patterns to never redact
    CLAUDE_OTEL_REDACT_DISABLE_DEFAULTS: Set to 'true' to disable built-in patterns
"""

import os
import re
from typing import Any, Optional

from claude_otel.config import load_redaction_config, RedactionConfig

# Default limits - conservative to avoid storing large/sensitive data
DEFAULT_MAX_ATTR_LENGTH = 256
DEFAULT_MAX_PAYLOAD_BYTES = 1024

# Common patterns that likely contain secrets (case-insensitive)
# These are intentionally broad to catch variations
DEFAULT_REDACT_PATTERNS = [
    r"(?i)(api[_-]?key|apikey)\s*[=:]\s*\S+",
    r"(?i)(secret|password|passwd|pwd)\s*[=:]\s*\S+",
    r"(?i)(token|bearer)\s*[=:]\s*\S+",
    r"(?i)(auth|authorization)\s*[=:]\s*\S+",
    r"(?i)(private[_-]?key)\s*[=:]\s*\S+",
    # AWS-style keys
    r"(?i)AKIA[0-9A-Z]{16}",
    r"(?i)aws[_-]?(secret|access)[_-]?key\s*[=:]\s*\S+",
    # Generic long base64-ish strings that look like secrets (40+ chars)
    r"(?<![A-Za-z0-9])[A-Za-z0-9+/]{40,}={0,2}(?![A-Za-z0-9])",
]

_cached_patterns: Optional[list[re.Pattern]] = None
_cached_allowlist: Optional[list[re.Pattern]] = None
_cached_config: Optional[RedactionConfig] = None


def _get_max_attr_length() -> int:
    """Get max attribute length from env or default."""
    try:
        return int(os.environ.get("CLAUDE_OTEL_MAX_ATTR_LENGTH", DEFAULT_MAX_ATTR_LENGTH))
    except ValueError:
        return DEFAULT_MAX_ATTR_LENGTH


def _get_max_payload_bytes() -> int:
    """Get max payload bytes from env or default."""
    try:
        return int(os.environ.get("CLAUDE_OTEL_MAX_PAYLOAD_BYTES", DEFAULT_MAX_PAYLOAD_BYTES))
    except ValueError:
        return DEFAULT_MAX_PAYLOAD_BYTES


def _get_redaction_config() -> RedactionConfig:
    """Get the redaction configuration, using cache for efficiency."""
    global _cached_config
    if _cached_config is not None:
        return _cached_config
    _cached_config = load_redaction_config()
    return _cached_config


def _get_redact_patterns() -> list[re.Pattern]:
    """Get compiled redaction patterns, using cache for efficiency."""
    global _cached_patterns
    if _cached_patterns is not None:
        return _cached_patterns

    config = _get_redaction_config()
    patterns: list[str] = []

    # Add default patterns if not disabled
    if config.use_defaults:
        patterns.extend(DEFAULT_REDACT_PATTERNS)

    # Add custom patterns from config
    patterns.extend(config.get_all_patterns())

    # Compile all patterns
    compiled = []
    for p in patterns:
        try:
            compiled.append(re.compile(p))
        except re.error:
            # Skip invalid patterns silently
            pass

    _cached_patterns = compiled
    return _cached_patterns


def _get_allowlist_patterns() -> list[re.Pattern]:
    """Get compiled allowlist patterns, using cache for efficiency."""
    global _cached_allowlist
    if _cached_allowlist is not None:
        return _cached_allowlist

    config = _get_redaction_config()
    allowlist = config.get_all_allowlist()

    # Compile all patterns
    compiled = []
    for p in allowlist:
        try:
            compiled.append(re.compile(p))
        except re.error:
            # Skip invalid patterns silently
            pass

    _cached_allowlist = compiled
    return _cached_allowlist


def _is_allowlisted(text: str) -> bool:
    """Check if text matches any allowlist pattern.

    Args:
        text: Text to check

    Returns:
        True if text matches any allowlist pattern
    """
    allowlist = _get_allowlist_patterns()
    for pattern in allowlist:
        if pattern.search(text):
            return True
    return False


def truncate(value: str, max_length: Optional[int] = None) -> tuple[str, bool]:
    """Truncate a string to max length.

    Args:
        value: String to truncate.
        max_length: Maximum length (uses env/default if None).

    Returns:
        Tuple of (truncated_string, was_truncated).
    """
    if max_length is None:
        max_length = _get_max_attr_length()

    if len(value) <= max_length:
        return value, False

    # Truncate and add indicator
    truncated = value[:max_length - 12] + "...[TRUNC]"
    return truncated, True


def truncate_bytes(data: bytes, max_bytes: Optional[int] = None) -> tuple[bytes, bool]:
    """Truncate bytes to max size.

    Args:
        data: Bytes to truncate.
        max_bytes: Maximum size (uses env/default if None).

    Returns:
        Tuple of (truncated_bytes, was_truncated).
    """
    if max_bytes is None:
        max_bytes = _get_max_payload_bytes()

    if len(data) <= max_bytes:
        return data, False

    return data[:max_bytes], True


def redact(value: str) -> str:
    """Apply redaction patterns to a string.

    Replaces matches with [REDACTED] to remove potential secrets.
    Respects allowlist patterns - matched text won't be redacted.

    Args:
        value: String to redact.

    Returns:
        String with sensitive patterns replaced.
    """
    patterns = _get_redact_patterns()
    allowlist = _get_allowlist_patterns()
    result = value

    for pattern in patterns:
        # Use a replacement function that checks allowlist
        def replace_if_not_allowed(match: re.Match) -> str:
            matched_text = match.group(0)
            # Check if the matched text is in the allowlist
            for allow_pattern in allowlist:
                if allow_pattern.search(matched_text):
                    return matched_text  # Keep original text
            return "[REDACTED]"

        result = pattern.sub(replace_if_not_allowed, result)

    return result


def sanitize_attribute(value: Any, max_length: Optional[int] = None) -> tuple[Any, bool]:
    """Sanitize a value for use as a span attribute.

    Applies redaction, then truncation. Non-strings are converted to strings first.

    Args:
        value: Value to sanitize.
        max_length: Maximum string length (uses env/default if None).

    Returns:
        Tuple of (sanitized_value, was_modified).
    """
    if value is None:
        return None, False

    # Convert to string if needed
    if not isinstance(value, str):
        value = str(value)

    # First redact, then truncate
    redacted = redact(value)
    was_redacted = redacted != value

    truncated, was_truncated = truncate(redacted, max_length)

    return truncated, was_redacted or was_truncated


def sanitize_payload(
    data: bytes,
    max_bytes: Optional[int] = None,
    encoding: str = "utf-8"
) -> tuple[str, int, bool]:
    """Sanitize a payload (stdout/stderr) for logging.

    Args:
        data: Raw bytes to sanitize.
        max_bytes: Maximum bytes to keep (uses env/default if None).
        encoding: Text encoding to decode as.

    Returns:
        Tuple of (sanitized_string, original_size, was_truncated).
    """
    original_size = len(data)

    # Truncate first (before decoding to avoid splitting multi-byte chars)
    truncated_data, was_truncated = truncate_bytes(data, max_bytes)

    # Decode with error handling
    try:
        text = truncated_data.decode(encoding, errors="replace")
    except Exception:
        # Fallback to latin-1 which accepts any byte
        text = truncated_data.decode("latin-1", errors="replace")

    # Apply redaction
    sanitized = redact(text)

    return sanitized, original_size, was_truncated or (sanitized != text)


def safe_attributes(attrs: dict[str, Any]) -> dict[str, Any]:
    """Sanitize a dictionary of attributes for span/log use.

    Args:
        attrs: Dictionary of attribute name -> value.

    Returns:
        New dictionary with all values sanitized.
        Also adds *_truncated flags for any truncated values.
    """
    result = {}
    for key, value in attrs.items():
        if value is None:
            result[key] = None
            continue

        sanitized, was_modified = sanitize_attribute(value)
        result[key] = sanitized

        if was_modified:
            result[f"{key}_sanitized"] = True

    return result


def reset_redaction_cache() -> None:
    """Reset the redaction cache (useful for testing)."""
    global _cached_patterns, _cached_allowlist, _cached_config
    _cached_patterns = None
    _cached_allowlist = None
    _cached_config = None
