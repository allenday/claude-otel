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

## Modes

`claude-otel` supports two execution modes:

### Subprocess Wrapper (Default)

The default mode wraps the `claude` CLI as a subprocess and uses CLI hooks for telemetry:

```bash
claude-otel "What is 2+2?"
```

**Features:**
- Lightweight and fast
- No SDK dependencies at runtime
- Basic telemetry: tool invocations, duration, token usage from transcript
- Works with all Claude CLI versions

### SDK Mode (Enhanced)

Use `--use-sdk` for richer telemetry via the `claude-agent-sdk`:

```bash
claude-otel --use-sdk "Analyze this codebase"
```

**Features:**
- Turn tracking with incremental token counts
- Gen AI semantic conventions (gen_ai.* attributes)
- Model metadata capture
- Context compaction events
- Interactive REPL mode support
- Per-turn metrics and cumulative totals

### Interactive Mode

Start an interactive session with `--use-sdk` and no prompt:

```bash
claude-otel --use-sdk
```

**Features:**
- Multi-turn conversations with shared context
- Session metrics tracking (total tokens, tools used)
- Rich console output with formatting
- Exit commands: `exit`, `quit`, `bye`, or Ctrl+C

## CLI Flags

### claude-otel Specific Flags

| Flag | Description |
|------|-------------|
| `--use-sdk` | Use SDK-based runner for enhanced telemetry |
| `--claude-otel-debug` | Enable debug output |
| `--version`, `-v` | Show version and exit |
| `--config` | Show configuration and exit |

### Claude CLI Passthrough

All other flags are passed directly to Claude CLI. Use `--flag=value` format for clarity:

```bash
# Permission mode
claude-otel --permission-mode=bypassPermissions "fix bug"

# Specific model
claude-otel --model=opus "review code"

# Multiple flags
claude-otel --model=sonnet --permission-mode=ask "analyze this"
```

### Quick Start

```bash
# Minimal setup - uses default collector
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
| `OTEL_EXPORTER_OTLP_ENDPOINT` | `http://localhost:4317` | OTLP collector endpoint |
| `OTEL_EXPORTER_OTLP_PROTOCOL` | `grpc` | Protocol: `grpc` or `http` |
| `OTEL_SERVICE_NAME` | `claude-otel` | Service name for traces/logs |
| `OTEL_SERVICE_NAMESPACE` | `infra` | Service namespace |
| `OTEL_RESOURCE_ATTRIBUTES` | (empty) | Additional attributes as `key=value,key2=value2` |
| `CLAUDE_BIN` | `claude` | Path/command for Claude CLI binary to exec |

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

### Resilience (Bounded Queues / Drop Policy)

| Variable | Default | Description |
|----------|---------|-------------|
| `OTEL_BSP_MAX_QUEUE_SIZE` | `2048` | Max spans to buffer before dropping |
| `OTEL_BSP_MAX_EXPORT_BATCH_SIZE` | `512` | Max spans per export batch |
| `OTEL_BSP_EXPORT_TIMEOUT` | `30000` | Export timeout in milliseconds |
| `OTEL_BSP_SCHEDULE_DELAY` | `5000` | Delay between exports in milliseconds |
| `OTEL_EXPORTER_OTLP_TIMEOUT` | `10000` | OTLP request timeout in milliseconds |

These settings ensure graceful degradation when the collector is unreachable:
- **Bounded queues**: Limits memory usage by capping buffered spans
- **Drop policy**: When the queue is full, oldest spans are dropped (non-blocking)
- **Timeouts**: Prevents indefinite blocking on network issues

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
export OTEL_SERVICE_NAME="claude-otel"
export OTEL_SERVICE_NAMESPACE="infra"
export OTEL_RESOURCE_ATTRIBUTES="environment=prod,team=platform"
claude-otel "Hello"
```

### Enable Metrics

```bash
export OTEL_METRICS_EXPORTER=otlp
claude-otel "Hello"
```

### Collector / Loki example

```bash
# Collector (gRPC 4317) with logs -> Loki
OTEL_EXPORTER_OTLP_ENDPOINT="http://collector:4317" \
OTEL_EXPORTER_OTLP_PROTOCOL=grpc \
OTEL_TRACES_EXPORTER=otlp \
OTEL_LOGS_EXPORTER=otlp \
OTEL_METRICS_EXPORTER=otlp \
OTEL_SERVICE_NAME="claude-otel" \
OTEL_RESOURCE_ATTRIBUTES="service.namespace=infra" \
CLAUDE_TELEMETRY_DEBUG=1 \
claude-otel -p "hello"
```

You should see logs in Loki under `service_name="infra/claude-otel"`. Ensure `/root/.claude/debug` (Claude CLI debug dir) is writable if running as root.

### SDK Mode Examples

#### Single-Turn with Enhanced Telemetry

```bash
# Use SDK mode for gen_ai.* attributes and turn tracking
export OTEL_METRICS_EXPORTER=otlp
claude-otel --use-sdk "Analyze the authentication flow"
```

This provides:
- Gen AI semantic conventions (gen_ai.system, gen_ai.request.model, etc.)
- Turn tracking and cumulative token counts
- Enhanced tool span attributes
- Model metadata capture

#### Interactive Session

```bash
# Start interactive REPL with SDK mode
export OTEL_EXPORTER_OTLP_ENDPOINT="http://localhost:4317"
export OTEL_METRICS_EXPORTER=otlp
claude-otel --use-sdk

# Now you can have multi-turn conversations:
# > What files handle routing?
# > Can you refactor the main handler?
# > Run the tests
# > exit
```

Interactive mode features:
- Persistent context across turns
- Session-level metrics (total tokens, tools used)
- Rich console output with formatting
- Type `exit`, `quit`, or `bye` to end session

#### SDK Mode with Custom Model

```bash
# Use specific model in SDK mode
claude-otel --use-sdk --model=opus "Review this pull request"

# With permission mode
claude-otel --use-sdk --permission-mode=bypassPermissions "Fix all linting errors"
```

#### Subprocess vs SDK Comparison

```bash
# Subprocess mode (default): lightweight, basic telemetry
claude-otel "What is 2+2?"
# ✓ Fast startup
# ✓ Tool metrics: duration, exit codes, payload sizes
# ✓ Token usage from transcript
# ✗ No turn tracking
# ✗ No gen_ai.* attributes

# SDK mode: rich telemetry
claude-otel --use-sdk "What is 2+2?"
# ✓ All subprocess mode features
# ✓ Turn tracking (turns counter)
# ✓ Gen AI semantic conventions
# ✓ Model metadata (gen_ai.request.model, gen_ai.response.model)
# ✓ Context compaction events
# ✓ Interactive mode support
# ✗ Slightly slower startup (SDK initialization)
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
   curl -v http://localhost:4317
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
   # Default service name is 'claude-otel'
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

If the collector is unreachable, the wrapper uses bounded queues and timeouts to prevent blocking. You can tune these settings or disable export entirely:

```bash
# Reduce timeouts for faster failure
export OTEL_EXPORTER_OTLP_TIMEOUT=1000  # 1 second
export OTEL_BSP_EXPORT_TIMEOUT=5000     # 5 seconds

# Reduce queue size to limit memory usage
export OTEL_BSP_MAX_QUEUE_SIZE=100

# Or disable for quick local testing
export OTEL_TRACES_EXPORTER=none
```

### SDK Mode Issues

#### "Interactive mode requires --use-sdk flag"

Interactive mode (running without a prompt) requires SDK mode:

```bash
# Wrong: subprocess mode doesn't support interactive
claude-otel
# Error: Interactive mode requires --use-sdk flag

# Correct: use --use-sdk for interactive sessions
claude-otel --use-sdk
```

#### SDK Import Errors

If you get import errors for `claude_agent_sdk`:

```bash
# Ensure SDK is installed
pip install claude-agent-sdk

# Or reinstall the package with SDK extras
pip install -e ".[sdk]"
```

#### Missing gen_ai.* Attributes

Gen AI semantic convention attributes are only available in SDK mode:

```bash
# Subprocess mode: only basic attributes
claude-otel "test"
# Has: tokens.*, tool.*, session.id
# Missing: gen_ai.*, turns

# SDK mode: includes gen_ai.* attributes
claude-otel --use-sdk "test"
# Has: All above + gen_ai.system, gen_ai.request.model, turns
```

#### Interactive Mode Not Responding

If interactive mode hangs or doesn't respond:

1. Check that Claude CLI is working:
   ```bash
   claude "test prompt"
   ```

2. Enable debug mode to see what's happening:
   ```bash
   claude-otel --use-sdk --claude-otel-debug
   ```

3. Try subprocess mode to isolate the issue:
   ```bash
   claude-otel "test prompt"
   ```

#### Turn Count Not Incrementing

Turn counting is only available in SDK mode via the MessageComplete hook:

```bash
# Enable metrics export to see turn counter
export OTEL_METRICS_EXPORTER=otlp
claude-otel --use-sdk "first prompt"

# Check collector/Prometheus for claude.turns_total metric
```

## Metrics

When `OTEL_METRICS_EXPORTER=otlp` is set, the following metrics are exported:

### Basic Metrics (All Modes)

| Metric | Type | Labels | Description |
|--------|------|--------|-------------|
| `claude.tool_calls_total` | Counter | `tool.name` | Total tool invocations |
| `claude.tool_calls_errors_total` | Counter | `tool.name` | Tool call errors |
| `claude.tool_call_duration_ms` | Histogram | `tool.name` | Tool call duration |

### SDK Mode Enhanced Metrics

When using `--use-sdk` mode, additional metrics are available:

| Metric | Type | Labels | Description |
|--------|------|--------|-------------|
| `claude.turns_total` | Counter | `model` | Total conversation turns |
| `claude.cache_hits_total` | Counter | `model` | Cache read operations |
| `claude.cache_creates_total` | Counter | `model` | Cache creation operations |
| `claude.compaction_total` | Counter | - | Context window compaction events |

## Token Usage Tracking

### Basic Mode (Subprocess Wrapper)

Tool spans include token usage attributes when available from the Claude transcript:

| Attribute | Type | Description |
|-----------|------|-------------|
| `tokens.input` | int | Input tokens for the API call |
| `tokens.output` | int | Output tokens generated |
| `tokens.cache_read` | int | Tokens read from cache |
| `tokens.cache_creation` | int | Tokens used for cache creation |
| `tokens.total` | int | Sum of all token counts |

Token usage is extracted from the Claude CLI transcript file which contains detailed usage metrics per API call.

### SDK Mode Enhanced Tracking

When using `--use-sdk`, additional semantic convention attributes are available following the OpenTelemetry Gen AI specification:

| Attribute | Type | Description |
|-----------|------|-------------|
| `gen_ai.system` | string | AI system (always "anthropic") |
| `gen_ai.request.model` | string | Model requested (e.g., "claude-sonnet-4") |
| `gen_ai.response.model` | string | Model used for response |
| `gen_ai.operation.name` | string | Operation type (e.g., "chat") |
| `gen_ai.usage.input_tokens` | int | Input tokens consumed |
| `gen_ai.usage.output_tokens` | int | Output tokens generated |
| `turns` | int | Conversation turn count |

The SDK mode also provides per-turn token tracking with cumulative totals updated after each message.

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

## Tool Hooks

For per-tool-invocation telemetry, the package provides hook commands that integrate with Claude CLI's hook system.

### Installation

After `pip install -e .`, the following commands are available on your PATH:

| Command | Description |
|---------|-------------|
| `claude-otel-pre-tool` | PreToolUse hook - records start time for duration calculation |
| `claude-otel-post-tool` | PostToolUse hook - creates OTEL span with full attributes |
| `claude-otel-pre-compact` | PreCompact hook - tracks context window compaction events |

### Configuration

Add these hooks to your Claude CLI settings (`~/.claude/settings.json`):

```json
{
  "hooks": {
    "PreToolUse": [
      {
        "matcher": "*",
        "hooks": ["claude-otel-pre-tool"]
      }
    ],
    "PostToolUse": [
      {
        "matcher": "*",
        "hooks": ["claude-otel-post-tool"]
      }
    ],
    "PreCompact": [
      {
        "matcher": "*",
        "hooks": ["claude-otel-pre-compact"]
      }
    ]
  }
}
```

### Span Attributes

#### Tool Invocation Spans

Each tool invocation span includes:

| Attribute | Type | Description |
|-----------|------|-------------|
| `tool.name` | string | Tool name (Bash, Read, Write, etc.) |
| `tool.use_id` | string | Unique tool invocation ID |
| `session.id` | string | Claude session ID |
| `duration_ms` | float | Tool execution time in milliseconds |
| `input.summary` | string | Sanitized summary of tool input |
| `input.truncated` | bool | Whether input was truncated |
| `response_bytes` | int | Size of tool response |
| `response.truncated` | bool | Whether response exceeds threshold |
| `exit_code` | int | Exit code for Bash commands |
| `error` | bool | Whether an error occurred |
| `error.message` | string | Error message (if error=true) |
| `tokens.*` | int | Token usage metrics (when available) |

#### Context Compaction Spans

Context window compaction spans (from PreCompact hook) include:

| Attribute | Type | Description |
|-----------|------|-------------|
| `compaction.trigger` | string | Why compaction occurred (e.g., "max_tokens", "user_request") |
| `compaction.has_custom_instructions` | bool | Whether custom instructions were provided |
| `session.id` | string | Claude session ID |

## License

MIT
