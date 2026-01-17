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

## CLI Flags

### claude-otel Flags

These flags control `claude-otel` behavior and are not passed to Claude:

| Flag | Short | Default | Description |
|------|-------|---------|-------------|
| `--use-sdk` | - | `false` | Use SDK-based runner for richer telemetry (enables gen_ai.* attributes, turn tracking, interactive mode support) |
| `--claude-otel-debug` | - | `false` | Enable debug output to stderr (also set via `CLAUDE_OTEL_DEBUG=1`) |
| `--version` | `-v` | - | Show version and exit |
| `--config` | - | - | Show current configuration (OTEL endpoint, service name, enabled exporters) and exit |

### Interactive Mode

When invoked without a prompt, `claude-otel --use-sdk` enters interactive mode:

```bash
# Start interactive REPL
claude-otel --use-sdk

# Interactive mode with custom model
claude-otel --use-sdk --model=opus
```

**Interactive mode features:**
- Multi-turn conversations with shared context
- Session metrics display (tokens, tools used)
- Rich console output with emoji indicators (🤖, 🔧, ✅, ❌)
- Exit commands: `exit`, `quit`, `bye`, or press Ctrl+C twice

**Note:** Interactive mode requires `--use-sdk` flag and is not available in subprocess mode.

### Claude CLI Flags (Pass-through)

All standard Claude CLI flags are supported and passed through. Use the `--flag=value` format (with `=`) to avoid ambiguity:

```bash
# Recommended: use = for flags with values
claude-otel --model=opus --permission-mode=bypassPermissions "review my code"

# Also works: space-separated (but prompt must be last)
claude-otel --model opus "review my code"

# Boolean flags (no value needed)
claude-otel --bypass-permissions "fix this bug"
```

**Common Claude flags:**
- `--model=<name>` - Select model (e.g., `opus`, `sonnet`, `haiku`)
- `--permission-mode=<mode>` - Permission mode (`allow`, `deny`, `bypassPermissions`)
- `--bypass-permissions` - Bypass permission prompts (boolean flag)
- `--setting-sources=<sources>` - Comma-separated list of setting sources
- All other `claude` CLI flags - see `claude --help` for full list

### Quick Start

```bash
# Minimal setup - uses default collector
claude-otel "Hello, Claude"

# With custom endpoint
OTEL_EXPORTER_OTLP_ENDPOINT="http://localhost:4317" claude-otel "Hello"

# Enable debug output
CLAUDE_OTEL_DEBUG=1 claude-otel "Hello"

# SDK mode with richer telemetry
claude-otel --use-sdk "Analyze this codebase"

# Interactive multi-turn session
claude-otel --use-sdk
```

## Interactive Mode Guide

Interactive mode provides a multi-turn REPL (Read-Eval-Print Loop) for conversational sessions with Claude, maintaining full context across turns.

### Starting Interactive Mode

```bash
# Basic interactive session (automatically enters REPL when no prompt provided)
claude-otel --use-sdk

# With specific model
claude-otel --use-sdk --model=opus

# With custom permissions
claude-otel --use-sdk --permission-mode=bypassPermissions

# With debug output
claude-otel --use-sdk --claude-otel-debug
```

**Requirements:**
- `--use-sdk` flag must be provided (interactive mode uses SDK-based runner)
- Claude Agent SDK installed (`pip install claude-agent-sdk`)

### Features

**Conversation Context:**
- All turns share the same session context
- Claude remembers previous messages and tool interactions
- Context window managed automatically with compaction when needed

**Session Metrics:**
After each turn, see cumulative session statistics:
```
Session: 3 turns | 1,250 tokens (750 in, 500 out) | 5 tools used
```

**Rich Console Output:**
- 🤖 Claude thinking indicator
- 🔧 Tool execution notifications with duration
- ✅ Success indicators
- ❌ Error indicators
- Formatted response panels using Rich library

**Startup Banner:**
```
┌─ Interactive Mode ───────────────────────────────────┐
│ Claude CLI with OpenTelemetry                        │
│                                                      │
│ Service: claude-otel                                │
│ Endpoint: http://localhost:4317                     │
│ Telemetry: Enabled                                  │
│ Model: claude-sonnet-4                              │
│                                                      │
│ Type 'exit', 'quit', or 'bye' to end the session   │
│ Press Ctrl+C twice to exit immediately              │
└──────────────────────────────────────────────────────┘
```

### Exiting Interactive Mode

**Exit commands:**
- Type `exit`, `quit`, or `bye` at any prompt

**Keyboard shortcuts:**
- Press `Ctrl+C` once to cancel current input
- Press `Ctrl+C` twice quickly to force exit immediately

### Example Session

```bash
$ claude-otel --use-sdk

┌─ Interactive Mode ───────────────────────────────────┐
│ Claude CLI with OpenTelemetry                        │
│ Service: claude-otel                                │
│ Endpoint: http://localhost:4317                     │
│ Telemetry: Enabled                                  │
└──────────────────────────────────────────────────────┘

You: What files are in the current directory?

🤖 Claude is thinking...
🔧 Tool: Bash - ls -la
✅ Completed in 45ms

The current directory contains:
- README.md (documentation)
- src/ (source code)
- tests/ (test files)
[... Claude's formatted response ...]

Session: 1 turns | 250 tokens (150 in, 100 out) | 1 tools used

You: What is the largest file?

🤖 Claude is thinking...
🔧 Tool: Bash - du -sh * | sort -rh | head -5
✅ Completed in 32ms

Based on the previous listing, the largest file is...
[... Claude's response with context awareness ...]

Session: 2 turns | 480 tokens (280 in, 200 out) | 2 tools used

You: exit

Session complete! Total: 2 turns, 480 tokens, 2 tools used.
```

### Interactive Mode vs Single-Turn Mode

| Feature | Single-Turn | Interactive |
|---------|-------------|-------------|
| **Command** | `claude-otel "prompt"` | `claude-otel --use-sdk` (no prompt) |
| **Context** | One-off command | Persistent across turns |
| **Exit** | Automatic after response | Manual (`exit`/`quit`/`bye` or Ctrl+C) |
| **Metrics** | Per-command | Cumulative per session |
| **Use Case** | Automation, scripts | Development, exploration, debugging |

### Telemetry in Interactive Mode

Interactive sessions generate rich telemetry with full conversation tracking:

**Session Span Attributes:**
- `turns`: Total conversation turns
- `gen_ai.usage.input_tokens`: Cumulative input tokens
- `gen_ai.usage.output_tokens`: Cumulative output tokens
- `tokens.cache_read`: Cumulative cache read tokens
- `tokens.cache_creation`: Cumulative cache creation tokens
- `tools_used`: Total tool invocations
- `tool_names`: Comma-separated list of unique tools used
- `model`: Model name (e.g., `claude-sonnet-4`)

**Turn Events:**
Each turn generates a `turn.completed` event with incremental token counts:
```
Event: turn.completed
  turn: 2
  gen_ai.usage.input_tokens: 130 (this turn only)
  gen_ai.usage.output_tokens: 50 (this turn only)
  tokens.cache_read: 20 (this turn only)
```

**Tool Spans:**
Each tool invocation creates a span with full attributes (same as single-turn mode).

**Context Compaction Events:**
When the context window is compacted, a `compaction` event is logged with the trigger reason.

### Tips for Interactive Mode

1. **Use for exploration:** Interactive mode excels at iterative tasks where context matters
   ```
   You: Show me the database schema
   You: Find all tables with user data
   You: Generate a migration to add email validation
   ```

2. **Monitor session metrics:** Keep an eye on token usage to avoid context window limits
   - The session metrics line shows cumulative token counts after each turn
   - Watch for context compaction events if approaching limits

3. **Enable debug mode:** See detailed telemetry export information
   ```bash
   claude-otel --use-sdk --claude-otel-debug
   ```

4. **Check configuration first:** Verify your OTEL setup before starting a session
   ```bash
   claude-otel --config
   claude-otel --use-sdk  # Start with verified config
   ```

5. **Use with specific models:** Test different models in the same interactive session
   ```bash
   claude-otel --use-sdk --model=haiku  # Fast iterations
   claude-otel --use-sdk --model=opus   # Complex reasoning
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

## Metrics

When `OTEL_METRICS_EXPORTER=otlp` is set, the following metrics are exported:

### Tool Metrics

| Metric | Type | Labels | Description |
|--------|------|--------|-------------|
| `claude.tool_calls_total` | Counter | `tool.name` | Total tool invocations |
| `claude.tool_calls_errors_total` | Counter | `tool.name` | Tool call errors |
| `claude.tool_call_duration_ms` | Histogram | `tool.name` | Tool call duration in milliseconds |

### Conversation Metrics

| Metric | Type | Labels | Description |
|--------|------|--------|-------------|
| `claude.turns_total` | Counter | `model` | Total conversation turns completed |
| `claude.model_requests_total` | Counter | `model` | Total API requests by model type |

### Cache Metrics

| Metric | Type | Labels | Description |
|--------|------|--------|-------------|
| `claude.cache_hits_total` | Counter | `model` | Cache hits (cache_read_input_tokens > 0) |
| `claude.cache_misses_total` | Counter | `model` | Cache misses (cache_read_input_tokens == 0) |
| `claude.cache_creations_total` | Counter | `model` | Cache creations (cache_creation_input_tokens > 0) |

### Context Management Metrics

| Metric | Type | Labels | Description |
|--------|------|--------|-------------|
| `claude.context_compactions_total` | Counter | `trigger`, `model` | Context compaction events with trigger reason |

## Semantic Conventions

This wrapper follows [OpenTelemetry Semantic Conventions for Generative AI](https://opentelemetry.io/docs/specs/semconv/gen-ai/) to ensure compatibility with LLM observability tools.

### gen_ai.* Attributes (SDK Mode)

When using SDK-based hooks (`--use-sdk` flag), the following semantic convention attributes are included:

| Attribute | Type | Example | Description |
|-----------|------|---------|-------------|
| `gen_ai.system` | string | `anthropic` | The AI system/provider |
| `gen_ai.request.model` | string | `claude-sonnet-4` | Model requested |
| `gen_ai.response.model` | string | `claude-sonnet-4` | Model that responded |
| `gen_ai.operation.name` | string | `execute_tool` | Operation type |
| `gen_ai.usage.input_tokens` | int | `1234` | Cumulative input tokens for session |
| `gen_ai.usage.output_tokens` | int | `567` | Cumulative output tokens for session |

### Session & Turn Tracking (SDK Mode)

SDK-based hooks provide rich conversation tracking:

| Attribute | Type | Description |
|-----------|------|-------------|
| `model` | string | Model name (e.g., `claude-sonnet-4`) |
| `prompt` | string | Initial user prompt (truncated to 1000 chars) |
| `session.id` | string | Unique Claude session identifier |
| `turns` | int | Total conversation turns in this session |
| `tools_used` | int | Number of tools invoked |
| `tool_names` | string | Comma-separated list of unique tools used |

**Turn Events:** Each completed turn adds a `turn.completed` event with incremental token counts for that specific turn.

## Token Usage Tracking

Token usage attributes are available in both CLI and SDK modes:

### Cumulative Token Attributes (Session Span)

| Attribute | Type | Description |
|-----------|------|-------------|
| `gen_ai.usage.input_tokens` | int | Total input tokens for the session |
| `gen_ai.usage.output_tokens` | int | Total output tokens for the session |
| `tokens.cache_read` | int | Total tokens read from cache |
| `tokens.cache_creation` | int | Total tokens used for cache creation |
| `tokens.input` | int | Legacy attribute (same as gen_ai.usage.input_tokens) |
| `tokens.output` | int | Legacy attribute (same as gen_ai.usage.output_tokens) |
| `tokens.total` | int | Sum of all token counts |

### Token Sources

- **CLI Mode:** Extracted from Claude CLI transcript file (per-API-call usage)
- **SDK Mode:** Extracted from `message.usage` object (per-turn usage with cumulative totals)

SDK mode provides richer tracking with per-turn granularity via turn events.

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

### CLI Mode vs SDK Mode

`claude-otel` supports two execution modes with different telemetry capabilities:

#### CLI Mode (Default)

**Usage:** `claude-otel "your prompt"`

- Wraps the Claude CLI as a subprocess
- Uses CLI hooks (PreToolUse, PostToolUse, PreCompact) via settings.json
- Lightweight and simple
- Token usage extracted from transcript files
- Basic session span with tool invocations

**Best for:**
- Quick setup and simple use cases
- Drop-in replacement for `claude` command
- Minimal dependencies

#### SDK Mode (Enhanced Telemetry)

**Usage:** `claude-otel --use-sdk "your prompt"`

- Uses `claude-agent-sdk` directly (no subprocess)
- Uses SDK hooks (UserPromptSubmit, MessageComplete, PreToolUse, PostToolUse, PreCompact)
- Rich semantic conventions (`gen_ai.*` attributes)
- Turn tracking with per-turn token counts
- Model information capture
- Interactive mode support
- Context compaction tracking

**Best for:**
- Production observability with full context
- LLM-specific monitoring tools (Logfire, Sentry AI)
- Multi-turn conversations and interactive sessions
- Detailed performance analysis

**Comparison:**

| Feature | CLI Mode | SDK Mode |
|---------|----------|----------|
| gen_ai.* attributes | ❌ | ✅ |
| Model tracking | ❌ | ✅ |
| Turn tracking | ❌ | ✅ |
| Per-turn tokens | ❌ | ✅ |
| Interactive mode | ❌ | ✅ |
| Prompt capture | ❌ | ✅ |
| Tool spans | ✅ | ✅ |
| Cache metrics | ✅ | ✅ |
| Compaction events | ✅ | ✅ |

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
