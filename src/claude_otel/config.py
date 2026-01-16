"""Centralized OTEL configuration via environment variables.

Supported environment variables (per PRD):
  OTEL_EXPORTER_OTLP_ENDPOINT   - Collector endpoint (default: http://localhost:4317)
  OTEL_EXPORTER_OTLP_PROTOCOL   - Protocol: grpc or http (default: grpc)
  OTEL_SERVICE_NAME             - Service name (default: claude-cli)
  OTEL_SERVICE_NAMESPACE        - Service namespace (default: claude-otel)
  OTEL_RESOURCE_ATTRIBUTES      - Comma-separated key=value pairs
  OTEL_TRACES_EXPORTER          - Exporter type: otlp or none (default: otlp)
  OTEL_LOGS_EXPORTER            - Exporter type: otlp or none (default: otlp)
  OTEL_METRICS_EXPORTER         - Exporter type: otlp or none (default: none)
  OTEL_TRACES_SAMPLER           - Sampler: always_on, always_off, traceidratio (default: always_on)
  OTEL_TRACES_SAMPLER_ARG       - Sampler argument (e.g., ratio for traceidratio)
  CLAUDE_OTEL_DEBUG             - Enable debug logging (default: false)

Redaction configuration:
  CLAUDE_OTEL_REDACT_CONFIG     - Path to JSON config file for redaction rules
  CLAUDE_OTEL_REDACT_PATTERNS   - Comma-separated regex patterns to redact (legacy)
  CLAUDE_OTEL_REDACT_ALLOWLIST  - Comma-separated regex patterns to never redact
  CLAUDE_OTEL_REDACT_DISABLE_DEFAULTS - Set to 'true' to disable built-in patterns

Resilience configuration:
  OTEL_BSP_MAX_QUEUE_SIZE       - Max queue size for batch processor (default: 2048)
  OTEL_BSP_MAX_EXPORT_BATCH_SIZE - Max batch size for export (default: 512)
  OTEL_BSP_EXPORT_TIMEOUT       - Export timeout in milliseconds (default: 30000)
  OTEL_BSP_SCHEDULE_DELAY       - Delay between exports in milliseconds (default: 5000)
  OTEL_EXPORTER_OTLP_TIMEOUT    - OTLP exporter timeout in milliseconds (default: 10000)
"""

import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional


# Default collector endpoint (override in env per deployment)
DEFAULT_ENDPOINT = "http://localhost:4317"
DEFAULT_PROTOCOL = "grpc"
DEFAULT_SERVICE_NAME = "claude-cli"
DEFAULT_SERVICE_NAMESPACE = "claude-otel"

# Resilience defaults - tuned for graceful degradation when collector is unreachable
DEFAULT_BSP_MAX_QUEUE_SIZE = 2048       # Max spans to buffer before dropping
DEFAULT_BSP_MAX_EXPORT_BATCH_SIZE = 512  # Max spans per export batch
DEFAULT_BSP_EXPORT_TIMEOUT_MS = 30000    # Export timeout (30s)
DEFAULT_BSP_SCHEDULE_DELAY_MS = 5000     # Delay between exports (5s)
DEFAULT_EXPORTER_TIMEOUT_MS = 10000      # OTLP request timeout (10s)


@dataclass
class RedactionConfig:
    """Configuration for PII redaction rules.

    Supports:
    - Regex patterns for redaction (things to redact)
    - Allowlist patterns (things to never redact, even if matched)
    - Named pattern groups for organization
    - Disabling default built-in patterns
    """

    # Patterns to redact (regex strings)
    patterns: list[str] = field(default_factory=list)

    # Patterns to allow (never redact even if matched by patterns)
    allowlist: list[str] = field(default_factory=list)

    # Whether to include default built-in patterns
    use_defaults: bool = True

    # Named pattern groups for organization (e.g., {"aws": [...], "pii": [...]})
    pattern_groups: dict[str, list[str]] = field(default_factory=dict)

    # Named allowlist groups
    allowlist_groups: dict[str, list[str]] = field(default_factory=dict)

    def get_all_patterns(self) -> list[str]:
        """Get all redaction patterns including from groups."""
        all_patterns = list(self.patterns)
        for group_patterns in self.pattern_groups.values():
            all_patterns.extend(group_patterns)
        return all_patterns

    def get_all_allowlist(self) -> list[str]:
        """Get all allowlist patterns including from groups."""
        all_allowlist = list(self.allowlist)
        for group_patterns in self.allowlist_groups.values():
            all_allowlist.extend(group_patterns)
        return all_allowlist


def load_redaction_config() -> RedactionConfig:
    """Load redaction configuration from environment and optional config file.

    Precedence (later overrides earlier):
    1. Default values
    2. Config file (CLAUDE_OTEL_REDACT_CONFIG)
    3. Environment variables (CLAUDE_OTEL_REDACT_*)

    Returns:
        RedactionConfig instance
    """
    config = RedactionConfig()

    # Load from config file if specified
    config_path = os.environ.get("CLAUDE_OTEL_REDACT_CONFIG")
    if config_path:
        file_config = _load_redaction_config_file(config_path)
        if file_config:
            config = file_config

    # Override with environment variables
    # Additional patterns from env (appended to file config)
    env_patterns = os.environ.get("CLAUDE_OTEL_REDACT_PATTERNS", "")
    if env_patterns:
        for p in env_patterns.split(","):
            p = p.strip()
            if p and p not in config.patterns:
                config.patterns.append(p)

    # Allowlist from env (appended to file config)
    env_allowlist = os.environ.get("CLAUDE_OTEL_REDACT_ALLOWLIST", "")
    if env_allowlist:
        for p in env_allowlist.split(","):
            p = p.strip()
            if p and p not in config.allowlist:
                config.allowlist.append(p)

    # Disable defaults from env
    disable_defaults = os.environ.get("CLAUDE_OTEL_REDACT_DISABLE_DEFAULTS", "").lower()
    if disable_defaults in ("1", "true", "yes"):
        config.use_defaults = False

    return config


def _load_redaction_config_file(path: str) -> Optional[RedactionConfig]:
    """Load redaction config from a JSON file.

    Expected JSON format:
    {
        "patterns": ["regex1", "regex2"],
        "allowlist": ["safe_pattern1"],
        "use_defaults": true,
        "pattern_groups": {
            "aws": ["AKIA...", "aws_secret..."],
            "pii": ["\\b\\d{3}-\\d{2}-\\d{4}\\b"]
        },
        "allowlist_groups": {
            "safe": ["test_.*", "example_.*"]
        }
    }

    Args:
        path: Path to the JSON config file

    Returns:
        RedactionConfig if file loads successfully, None otherwise
    """
    try:
        config_path = Path(path).expanduser()
        if not config_path.exists():
            return None

        with open(config_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        return _parse_redaction_config_dict(data)

    except (json.JSONDecodeError, OSError, TypeError):
        # Silently ignore invalid config files - use defaults
        return None


def _parse_redaction_config_dict(data: dict[str, Any]) -> RedactionConfig:
    """Parse a dictionary into RedactionConfig.

    Args:
        data: Dictionary with config values

    Returns:
        RedactionConfig instance
    """
    patterns = data.get("patterns", [])
    if not isinstance(patterns, list):
        patterns = []
    patterns = [str(p) for p in patterns if p]

    allowlist = data.get("allowlist", [])
    if not isinstance(allowlist, list):
        allowlist = []
    allowlist = [str(p) for p in allowlist if p]

    use_defaults = data.get("use_defaults", True)
    if not isinstance(use_defaults, bool):
        use_defaults = str(use_defaults).lower() in ("true", "1", "yes")

    pattern_groups = {}
    raw_groups = data.get("pattern_groups", {})
    if isinstance(raw_groups, dict):
        for name, group_patterns in raw_groups.items():
            if isinstance(group_patterns, list):
                pattern_groups[str(name)] = [str(p) for p in group_patterns if p]

    allowlist_groups = {}
    raw_allowlist_groups = data.get("allowlist_groups", {})
    if isinstance(raw_allowlist_groups, dict):
        for name, group_patterns in raw_allowlist_groups.items():
            if isinstance(group_patterns, list):
                allowlist_groups[str(name)] = [str(p) for p in group_patterns if p]

    return RedactionConfig(
        patterns=patterns,
        allowlist=allowlist,
        use_defaults=use_defaults,
        pattern_groups=pattern_groups,
        allowlist_groups=allowlist_groups,
    )


@dataclass
class OTelConfig:
    """Parsed OTEL configuration from environment."""

    # Endpoint configuration
    endpoint: str = DEFAULT_ENDPOINT
    protocol: str = DEFAULT_PROTOCOL

    # Resource attributes
    service_name: str = DEFAULT_SERVICE_NAME
    service_namespace: str = DEFAULT_SERVICE_NAMESPACE
    resource_attributes: dict = field(default_factory=dict)

    # Exporter toggles
    traces_exporter: str = "otlp"
    logs_exporter: str = "otlp"
    metrics_exporter: str = "none"

    # Sampler configuration
    traces_sampler: str = "always_on"
    traces_sampler_arg: Optional[str] = None

    # Debug mode
    debug: bool = False

    # Resilience configuration (bounded queues/drop policy)
    bsp_max_queue_size: int = DEFAULT_BSP_MAX_QUEUE_SIZE
    bsp_max_export_batch_size: int = DEFAULT_BSP_MAX_EXPORT_BATCH_SIZE
    bsp_export_timeout_ms: int = DEFAULT_BSP_EXPORT_TIMEOUT_MS
    bsp_schedule_delay_ms: int = DEFAULT_BSP_SCHEDULE_DELAY_MS
    exporter_timeout_ms: int = DEFAULT_EXPORTER_TIMEOUT_MS

    @property
    def traces_enabled(self) -> bool:
        """Check if trace export is enabled."""
        return self.traces_exporter.lower() != "none"

    @property
    def logs_enabled(self) -> bool:
        """Check if log export is enabled."""
        return self.logs_exporter.lower() != "none"

    @property
    def metrics_enabled(self) -> bool:
        """Check if metrics export is enabled."""
        return self.metrics_exporter.lower() != "none"

    @property
    def is_grpc(self) -> bool:
        """Check if using gRPC protocol."""
        return self.protocol.lower() == "grpc"

    @property
    def grpc_endpoint(self) -> str:
        """Get endpoint formatted for gRPC (strips http:// prefix if present)."""
        ep = self.endpoint
        if ep.startswith("http://"):
            ep = ep[7:]
        elif ep.startswith("https://"):
            ep = ep[8:]
        return ep

    @property
    def http_endpoint(self) -> str:
        """Get endpoint formatted for HTTP (ensures http:// prefix)."""
        if not self.endpoint.startswith(("http://", "https://")):
            return f"http://{self.endpoint}"
        return self.endpoint


def parse_resource_attributes(attr_string: str) -> dict:
    """Parse OTEL_RESOURCE_ATTRIBUTES format: key1=val1,key2=val2."""
    attrs = {}
    if not attr_string:
        return attrs

    for pair in attr_string.split(","):
        pair = pair.strip()
        if "=" in pair:
            key, value = pair.split("=", 1)
            attrs[key.strip()] = value.strip()

    return attrs


def _parse_int_env(name: str, default: int) -> int:
    """Parse integer from environment variable with fallback to default."""
    val = os.environ.get(name, "")
    if not val:
        return default
    try:
        return int(val)
    except ValueError:
        return default


def load_config() -> OTelConfig:
    """Load OTEL configuration from environment variables."""
    debug_val = os.environ.get("CLAUDE_OTEL_DEBUG", "").lower()

    return OTelConfig(
        endpoint=os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT", DEFAULT_ENDPOINT),
        protocol=os.environ.get("OTEL_EXPORTER_OTLP_PROTOCOL", DEFAULT_PROTOCOL),
        service_name=os.environ.get("OTEL_SERVICE_NAME", DEFAULT_SERVICE_NAME),
        service_namespace=os.environ.get("OTEL_SERVICE_NAMESPACE", DEFAULT_SERVICE_NAMESPACE),
        resource_attributes=parse_resource_attributes(
            os.environ.get("OTEL_RESOURCE_ATTRIBUTES", "")
        ),
        traces_exporter=os.environ.get("OTEL_TRACES_EXPORTER", "otlp"),
        logs_exporter=os.environ.get("OTEL_LOGS_EXPORTER", "otlp"),
        metrics_exporter=os.environ.get("OTEL_METRICS_EXPORTER", "none"),
        traces_sampler=os.environ.get("OTEL_TRACES_SAMPLER", "always_on"),
        traces_sampler_arg=os.environ.get("OTEL_TRACES_SAMPLER_ARG"),
        debug=debug_val in ("1", "true", "yes"),
        # Resilience configuration
        bsp_max_queue_size=_parse_int_env("OTEL_BSP_MAX_QUEUE_SIZE", DEFAULT_BSP_MAX_QUEUE_SIZE),
        bsp_max_export_batch_size=_parse_int_env("OTEL_BSP_MAX_EXPORT_BATCH_SIZE", DEFAULT_BSP_MAX_EXPORT_BATCH_SIZE),
        bsp_export_timeout_ms=_parse_int_env("OTEL_BSP_EXPORT_TIMEOUT", DEFAULT_BSP_EXPORT_TIMEOUT_MS),
        bsp_schedule_delay_ms=_parse_int_env("OTEL_BSP_SCHEDULE_DELAY", DEFAULT_BSP_SCHEDULE_DELAY_MS),
        exporter_timeout_ms=_parse_int_env("OTEL_EXPORTER_OTLP_TIMEOUT", DEFAULT_EXPORTER_TIMEOUT_MS),
    )


# Singleton config instance (lazy-loaded)
_config: Optional[OTelConfig] = None


def get_config() -> OTelConfig:
    """Get the current OTEL configuration (singleton)."""
    global _config
    if _config is None:
        _config = load_config()
    return _config


def reset_config() -> None:
    """Reset config singleton (useful for testing)."""
    global _config
    _config = None
