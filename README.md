# claude-otel

OTEL telemetry wrapper for Claude CLI. Instruments Claude CLI sessions with OpenTelemetry traces, logs, and metrics, exporting to an OTLP-compatible collector.

## Installation

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
```

## Usage

Use `claude-otel` as a drop-in replacement for the `claude` CLI:

```bash
# Instead of:
claude "What is 2+2?"

# Use:
claude-otel "What is 2+2?"
```

All arguments are passed through to the underlying `claude` command. The wrapper creates an OTEL session span and exports telemetry to the configured collector.

### Quick Start

```bash
# Minimal setup - uses default bastion collector
claude-otel "Hello, Claude"

# With custom endpoint
OTEL_EXPORTER_OTLP_ENDPOINT="http://localhost:4317" claude-otel "Hello"

# Enable debug output
CLAUDE_OTEL_DEBUG=1 claude-otel "Hello"
```

## Environment Variables

### Core OTEL Configuration

| Variable | Default | Description |
|----------|---------|-------------|
| `OTEL_EXPORTER_OTLP_ENDPOINT` | `http://100.91.20.46:4317` | OTLP collector endpoint |
| `OTEL_EXPORTER_OTLP_PROTOCOL` | `grpc` | Protocol: `grpc` or `http` |
| `OTEL_SERVICE_NAME` | `claude-cli` | Service name for traces/logs |
| `OTEL_SERVICE_NAMESPACE` | `claude-otel` | Service namespace |
| `OTEL_RESOURCE_ATTRIBUTES` | (empty) | Additional attributes as `key=value,key2=value2` |

### Exporter Toggles

| Variable | Default | Description |
|----------|---------|-------------|
| `OTEL_TRACES_EXPORTER` | `otlp` | Trace exporter: `otlp` or `none` |
| `OTEL_LOGS_EXPORTER` | `otlp` | Log exporter: `otlp` or `none` |
| `OTEL_METRICS_EXPORTER` | `none` | Metrics exporter: `otlp` or `none` |

### Sampling

| Variable | Default | Description |
|----------|---------|-------------|
| `OTEL_TRACES_SAMPLER` | `always_on` | Sampler: `always_on`, `always_off`, `traceidratio` |
| `OTEL_TRACES_SAMPLER_ARG` | (none) | Sampler argument (e.g., ratio for `traceidratio`) |

### PII Safeguards

| Variable | Default | Description |
|----------|---------|-------------|
| `CLAUDE_OTEL_MAX_ATTR_LENGTH` | `256` | Max attribute string length before truncation |
| `CLAUDE_OTEL_MAX_PAYLOAD_BYTES` | `1024` | Max payload (stdout/stderr) bytes to capture |
| `CLAUDE_OTEL_REDACT_PATTERNS` | (built-in) | Additional regex patterns to redact (comma-separated) |
| `CLAUDE_OTEL_REDACT_ALLOWLIST` | (none) | Regex patterns to never redact (comma-separated) |
| `CLAUDE_OTEL_REDACT_CONFIG` | (none) | Path to JSON config file for redaction rules |
| `CLAUDE_OTEL_REDACT_DISABLE_DEFAULTS` | `false` | Set to `true` to disable built-in redaction patterns |

### Debug

| Variable | Default | Description |
|----------|---------|-------------|
| `CLAUDE_OTEL_DEBUG` | `false` | Enable debug output (`1`, `true`, or `yes`) |

## Example Configurations

### Local Development (no export)

```bash
export OTEL_TRACES_EXPORTER=none
export OTEL_LOGS_EXPORTER=none
export CLAUDE_OTEL_DEBUG=1
claude-otel "Test"
```

### Production with Sampling

```bash
export OTEL_EXPORTER_OTLP_ENDPOINT="http://collector.example.com:4317"
export OTEL_TRACES_SAMPLER=traceidratio
export OTEL_TRACES_SAMPLER_ARG=0.1  # Sample 10% of traces
claude-otel "Hello"
```

### Custom Service Identity

```bash
export OTEL_SERVICE_NAME="my-app-claude"
export OTEL_SERVICE_NAMESPACE="production"
export OTEL_RESOURCE_ATTRIBUTES="environment=prod,team=platform"
claude-otel "Hello"
```

### Enable Metrics

```bash
export OTEL_METRICS_EXPORTER=otlp
claude-otel "Hello"
```

## Troubleshooting

### "claude command not found"

The wrapper shells out to the `claude` CLI. Ensure it's installed and in your PATH:

```bash
which claude
# If not found, install Claude CLI first
```

### Connection Refused / Network Errors

1. Verify the collector endpoint is reachable:
   ```bash
   curl -v http://100.91.20.46:4317
   ```

2. Check protocol consistency - don't mix gRPC endpoint with HTTP protocol:
   ```bash
   # gRPC uses port 4317
   OTEL_EXPORTER_OTLP_ENDPOINT="http://host:4317" OTEL_EXPORTER_OTLP_PROTOCOL=grpc

   # HTTP uses port 4318
   OTEL_EXPORTER_OTLP_ENDPOINT="http://host:4318" OTEL_EXPORTER_OTLP_PROTOCOL=http
   ```

3. Enable debug mode to see configuration:
   ```bash
   CLAUDE_OTEL_DEBUG=1 claude-otel "test"
   ```

### Traces Not Appearing in Collector

1. Confirm tracing is enabled:
   ```bash
   CLAUDE_OTEL_DEBUG=1 claude-otel "test"
   # Should show: [claude-otel] Traces: otlp
   ```

2. Check sampler configuration - `always_off` disables all traces:
   ```bash
   # Ensure this is NOT set
   unset OTEL_TRACES_SAMPLER
   # Or set explicitly
   export OTEL_TRACES_SAMPLER=always_on
   ```

3. Verify service name in collector query:
   ```bash
   # Default service name is 'claude-cli'
   # Check your OTEL_SERVICE_NAME if customized
   ```

### PII Showing in Traces

The wrapper applies automatic redaction for common secret patterns. To add custom patterns:

```bash
export CLAUDE_OTEL_REDACT_PATTERNS="(?i)my_secret_\w+,(?i)internal_token=\S+"
```

To prevent certain patterns from being redacted (allowlist):

```bash
export CLAUDE_OTEL_REDACT_ALLOWLIST="test_api_key,example_token"
```

To disable all built-in redaction patterns (use only custom patterns):

```bash
export CLAUDE_OTEL_REDACT_DISABLE_DEFAULTS=true
export CLAUDE_OTEL_REDACT_PATTERNS="my_custom_secret_\w+"
```

For complex redaction rules, use a JSON config file:

```bash
export CLAUDE_OTEL_REDACT_CONFIG=~/.claude-otel-redact.json
```

Example config file:
```json
{
  "patterns": ["custom_secret_\\w+"],
  "allowlist": ["test_.*", "example_.*"],
  "use_defaults": true,
  "pattern_groups": {
    "aws": ["AKIA[0-9A-Z]{16}", "aws_secret_\\w+"],
    "internal": ["internal_token=\\S+"]
  },
  "allowlist_groups": {
    "safe": ["dev_api_key", "staging_token"]
  }
}
```

To reduce captured payload sizes:

```bash
export CLAUDE_OTEL_MAX_ATTR_LENGTH=100
export CLAUDE_OTEL_MAX_PAYLOAD_BYTES=512
```

### High Latency / Slow Startup

If the collector is unreachable, the wrapper may block briefly on span export. Use batching defaults or disable export for testing:

```bash
# Disable for quick local testing
export OTEL_TRACES_EXPORTER=none
```

## Metrics

When `OTEL_METRICS_EXPORTER=otlp` is set, the following metrics are exported:

| Metric | Type | Labels | Description |
|--------|------|--------|-------------|
| `claude.tool_calls_total` | Counter | `tool.name` | Total tool invocations |
| `claude.tool_calls_errors_total` | Counter | `tool.name` | Tool call errors |
| `claude.tool_call_duration_ms` | Histogram | `tool.name` | Tool call duration |

## Architecture

```
┌─────────────┐     ┌──────────────┐     ┌──────────────┐
│ claude-otel │────▶│  Claude CLI  │     │ OTLP         │
│   wrapper   │     │              │     │ Collector    │
└──────┬──────┘     └──────────────┘     └──────▲───────┘
       │                                        │
       │         OTLP (gRPC/HTTP)               │
       └────────────────────────────────────────┘
       (traces, logs, metrics)
```

## License

MIT
