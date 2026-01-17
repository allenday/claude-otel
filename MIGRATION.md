# Migration Guide: Subprocess to SDK Mode

This guide helps you understand the differences between `claude-otel`'s two operation modes and migrate from simple subprocess mode to rich SDK-based telemetry.

## Overview

`claude-otel` supports two architectures for instrumenting Claude CLI:

1. **Subprocess Mode (Default)** - External wrapper that executes `claude` CLI as a subprocess
2. **SDK Mode (Opt-in)** - Uses `claude-agent-sdk` directly for richer telemetry and interactive features

## Quick Comparison

| Feature | Subprocess Mode | SDK Mode |
|---------|----------------|----------|
| **Setup** | Install `claude-otel` only | Install `claude-otel` + `claude-agent-sdk` |
| **Command** | `claude-otel [args]` | `claude-otel --use-sdk [args]` or `claude-otel --interactive` |
| **Execution** | Shells out to `claude` binary | Uses SDK directly (no subprocess) |
| **Hooks** | CLI hooks (PreToolUse, PostToolUse) | SDK hooks (UserPromptSubmit, MessageComplete, PreCompact, etc.) |
| **Telemetry** | Basic tool metrics, session spans | Rich conversation tracking, turn metrics, model info |
| **Token Tracking** | From transcript files (post-execution) | From `message.usage` (real-time) |
| **Interactive Mode** | No | Yes (multi-turn REPL) |
| **Console Output** | Passthrough from CLI | Rich formatting with emoji indicators |
| **Performance** | Subprocess overhead | Direct SDK calls |

## When to Use Each Mode

### Use Subprocess Mode When:
- You want drop-in replacement for `claude` command
- You need minimal setup and dependencies
- You prefer the standard Claude CLI experience
- You're wrapping existing CLI scripts or automation

### Use SDK Mode When:
- You want detailed conversation and turn tracking
- You need interactive/REPL mode for multi-turn sessions
- You want rich console output with formatted panels
- You need real-time token usage metrics
- You're building custom Claude integrations

## Migration Steps

### Step 1: Verify Current Setup

Check your current installation and verify it works:

```bash
# Should show version
claude-otel --version

# Test basic execution
OTEL_TRACES_EXPORTER=none claude-otel "Hello"
```

### Step 2: Install SDK Dependencies

The SDK mode requires the Claude Agent SDK:

```bash
# Already included if you installed from requirements
pip install claude-agent-sdk

# Or reinstall to ensure dependencies are updated
pip install -e .
```

### Step 3: Test SDK Mode

Try SDK mode with a simple command:

```bash
# SDK mode with same command-line interface
claude-otel --use-sdk "What is 2+2?"

# Or use interactive mode (SDK only)
claude-otel --interactive
```

### Step 4: Compare Telemetry Output

Run the same prompt in both modes and compare:

```bash
# Subprocess mode - basic telemetry
CLAUDE_OTEL_DEBUG=1 claude-otel "Explain Python decorators"

# SDK mode - rich telemetry
CLAUDE_OTEL_DEBUG=1 claude-otel --use-sdk "Explain Python decorators"
```

**Subprocess mode provides:**
- Session span with `session.id`
- Tool spans with duration, exit codes, payload sizes
- Token usage from transcript (after execution)

**SDK mode adds:**
- User prompt events with `gen_ai.request.model`
- Turn tracking with incremental token counts
- Message completion events with `gen_ai.usage.*` attributes
- Context compaction events
- Richer console output with structured formatting

### Step 5: Update Your Scripts

If you're using `claude-otel` in scripts or automation:

```bash
# Before (subprocess mode - still works)
claude-otel "Generate test data"

# After (SDK mode - opt-in)
claude-otel --use-sdk "Generate test data"
```

### Step 6: Environment Variables

Both modes use the same OTEL environment variables. No changes needed:

```bash
export OTEL_EXPORTER_OTLP_ENDPOINT="http://collector:4317"
export OTEL_SERVICE_NAME="claude-otel"
export OTEL_METRICS_EXPORTER=otlp

# Works with both modes
claude-otel "Hello"
claude-otel --use-sdk "Hello"
```

## Telemetry Differences

### Span Attributes

#### Subprocess Mode
```
Session Span:
  - session.id: <uuid>
  - tool_count: <int>

Tool Span:
  - tool.name: "Bash"
  - duration_ms: 123.45
  - exit_code: 0
  - response_bytes: 1024
  - tokens.input: 100 (from transcript)
  - tokens.output: 50 (from transcript)
```

#### SDK Mode
```
Session Span:
  - session.id: <uuid>
  - gen_ai.system: "claude"
  - gen_ai.request.model: "claude-sonnet-4"
  - turns: 3
  - gen_ai.usage.input_tokens: 500 (cumulative)
  - gen_ai.usage.output_tokens: 200 (cumulative)

Tool Span:
  - tool.name: "Bash"
  - tool.status: "success"
  - duration_ms: 123.45
  - tool.input.command: "ls -la"
  - tool.response.stdout: "..." (truncated)

Turn Event (per message):
  - turn: 1
  - gen_ai.usage.input_tokens: 150 (incremental)
  - gen_ai.usage.output_tokens: 50 (incremental)
```

### Metrics

Both modes export the same base metrics when `OTEL_METRICS_EXPORTER=otlp`:

```
claude.tool_calls_total{tool.name="Bash"}
claude.tool_calls_errors_total{tool.name="Bash"}
claude.tool_call_duration_ms{tool.name="Bash"}
```

SDK mode adds turn tracking metrics:
```
claude.turns_total
claude.cache_hits_total
claude.cache_misses_total
```

## Interactive Mode (SDK Only)

SDK mode supports an interactive REPL for multi-turn conversations:

```bash
# Start interactive session
claude-otel --interactive

# Or with custom model
claude-otel --interactive --model opus
```

**Features:**
- Maintains conversation context across turns
- Shows cumulative session metrics (tokens, tools used)
- Rich console output with formatted responses
- Exit with `exit`, `quit`, `bye`, or Ctrl+C

**Example session:**
```
🚀 Claude OTEL Interactive Mode
Service: claude-otel | Endpoint: http://localhost:4317

You: What files are in the current directory?
🤖 Claude is thinking...
🔧 Tool: Bash - ls -la
✅ Completed in 45ms

[Claude's response with file listing]

Session: 1 turns | 250 tokens (150 in, 100 out) | 1 tools used

You: What is the largest file?
[Continues with shared context...]
```

## CLI Arguments

### Subprocess Mode
```bash
# All args passed directly to `claude` command
claude-otel --model opus --permission-mode allow "Hello"
claude-otel -p "Hello"  # Short form
```

### SDK Mode
```bash
# Args parsed and converted to SDK options
claude-otel --use-sdk --model opus --permission-mode allow "Hello"
claude-otel --interactive  # Enables SDK mode automatically
claude-otel --claude-otel-debug  # Debug flag (recognized by wrapper)
```

**Supported SDK-specific flags:**
- `--use-sdk` - Enable SDK mode
- `--interactive` - Start interactive REPL (enables SDK mode)
- `--claude-otel-debug` - Enable debug output
- All standard `claude` CLI flags are passed through via `extra_args`

## Troubleshooting

### "claude-agent-sdk not found"

SDK mode requires the SDK package:
```bash
pip install claude-agent-sdk
# Or
pip install -e .  # Installs all dependencies from pyproject.toml
```

### SDK Mode Shows Different Token Counts

This is expected:
- **Subprocess mode**: Reads tokens from transcript files after execution (includes all API calls)
- **SDK mode**: Reads tokens from `message.usage` in real-time (per-message)

Both are accurate but measured at different points in the execution.

### Interactive Mode Not Responding

Check that you're using SDK mode:
```bash
# Wrong - interactive requires SDK mode
claude-otel --interactive  # ✓ Works (SDK mode auto-enabled)

# If issues persist, try explicit flag
claude-otel --use-sdk --interactive
```

### Rich Console Output Missing

Rich console output requires the `rich` library and SDK mode:
```bash
pip install rich
claude-otel --use-sdk "Hello"
```

## Side-by-Side Examples

### Simple Command

**Subprocess mode:**
```bash
$ claude-otel "What is 2+2?"
4

# Telemetry: Session span, tool spans (if any), basic attributes
```

**SDK mode:**
```bash
$ claude-otel --use-sdk "What is 2+2?"
🤖 Claude is thinking...
4

# Telemetry: Session span, turn events, gen_ai.* attributes, message events
```

### With Tool Usage

**Subprocess mode:**
```bash
$ claude-otel "List files in /tmp"
[Files listed]

# Telemetry:
# - Session span
# - Tool span (Bash: ls /tmp) with exit_code, duration_ms, response_bytes
```

**SDK mode:**
```bash
$ claude-otel --use-sdk "List files in /tmp"
🤖 Claude is thinking...
🔧 Tool: Bash - ls /tmp
✅ Completed in 23ms
[Formatted file listing]

# Telemetry:
# - Session span with gen_ai.request.model
# - Turn event with incremental tokens
# - Tool span with tool.input.command, tool.status, tool.response.*
# - Message complete event
```

### Multi-Turn Conversation

**Subprocess mode (not supported):**
```bash
$ claude-otel "What is Python?"
[Answer]

$ claude-otel "Show me an example"
# ⚠️  New session, no context from previous command
[Generic example without context]
```

**SDK mode:**
```bash
$ claude-otel --interactive
You: What is Python?
🤖 Claude: [Explanation of Python]

You: Show me an example
🤖 Claude: [Python example, aware of previous context]
# ✓ Maintains conversation context
```

## Best Practices

### 1. Start with Subprocess Mode
For most use cases, subprocess mode is sufficient and has less overhead.

### 2. Use SDK Mode for Development
When building or debugging, SDK mode provides better visibility:
```bash
# Development
CLAUDE_OTEL_DEBUG=1 claude-otel --use-sdk --interactive

# Production/Scripts
claude-otel "Automated task"
```

### 3. Keep Both Options Available
Your environment can support both modes seamlessly:
```bash
# Script determines mode based on need
if [ "$INTERACTIVE" = "true" ]; then
  claude-otel --interactive  # SDK mode
else
  claude-otel "$PROMPT"  # Subprocess mode
fi
```

### 4. Monitor Telemetry Differences
Set up queries to track metrics from both modes:
```promql
# Subprocess mode sessions
rate(claude_session_total{mode="subprocess"}[5m])

# SDK mode sessions
rate(claude_session_total{mode="sdk"}[5m])

# Turn metrics (SDK only)
sum(claude_turns_total)
```

## Rollback Strategy

If you encounter issues with SDK mode:

1. **Immediate fallback** - Remove `--use-sdk` flag:
   ```bash
   # From
   claude-otel --use-sdk "Hello"
   # To
   claude-otel "Hello"
   ```

2. **Scripts** - Update wrapper to detect and handle:
   ```bash
   if ! claude-otel --use-sdk --version 2>/dev/null; then
     echo "SDK mode unavailable, falling back to subprocess"
     claude-otel "$@"
   fi
   ```

3. **No data loss** - Both modes export to same OTLP endpoint, just with different attribute schemas

## Summary

| Aspect | Subprocess Mode | SDK Mode |
|--------|----------------|----------|
| **Default** | Yes | No (opt-in) |
| **Dependencies** | `claude` CLI | `claude-agent-sdk` |
| **Command** | `claude-otel` | `claude-otel --use-sdk` |
| **Use Case** | Drop-in CLI wrapper | Rich telemetry & interactive |
| **Telemetry** | Tool-focused | Conversation-focused |
| **Context** | Single command | Multi-turn sessions |
| **Output** | CLI passthrough | Rich formatting |
| **Migration** | N/A | Add `--use-sdk` flag |

Both modes are fully supported and can coexist. Choose based on your needs:
- **Subprocess mode** for simple, reliable CLI wrapping
- **SDK mode** for detailed telemetry, interactive use, and development workflows
