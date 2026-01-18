# Telemetry Wrapper for Claude CLI — Backlog

## Working Convention
When claiming a task, place your worker ID inside the brackets: `[ ]` → `[alpha]`.
When complete, change to `[x]` and remove your ID.

## Build & Install
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
```
Package configuration lives in `pyproject.toml`.

## Milestone 1: MVP OTEL Wrapper
- [x] Implement a lightweight wrapper script (e.g., `bin/claude-otel`) that shells out to Claude CLI/SDK with OTEL hooks.
- [x] Emit session span and child spans for tool uses (attributes: tool.name, duration_ms, exit_code/error flag, stdout_bytes, stderr_bytes, truncated flags, input summary, prompt/session IDs).
- [x] Export traces and logs via OTLP to the collector (default gRPC 4317; HTTP optional).
- [x] Export basic metrics (counters: tool_calls total/per tool; gauge: in-flight tools if applicable).
- [x] Config via env (OTEL_*), with a single coherent protocol/endpoint; default to gRPC 4317.
- [x] Apply lightweight PII safeguards: truncate tool inputs/outputs, avoid storing raw large payloads.
- [x] Add unit tests for hook logic (span creation, duration calc, error paths) and a local integration test that sends a dummy span/log to the collector.

## Milestone 2: Deployment & Validation
- [x] Add a small docs section in the repo (usage, env vars, troubleshooting).
- [x] Run a manual smoke session; verify `service_name` appears in Loki and metrics counters increment on the collector.
  - Smoke test script added: `tests/smoke_test.py`
  - Traces and metrics accepted by OTLP collector at 4317 ✓
  - Note: Loki shows only promtail (span-to-logs processor not configured); Prometheus doesn't expose OTLP metrics directly. Both require collector config changes (see optional task below).
- [~] Optional: add a span-to-logs processor on collector if traces need to surface in Loki (only if requested). *Note: This is infrastructure work outside the codebase scope. Won't-do - requires collector config changes, not code changes.*

## Milestone 3: Enhancements (Optional)
- [x] Add per-tool metrics labels (tool.name) for Prometheus counters.
- [x] Add configurable redaction rules (regex/allowlist) for inputs/outputs.
- [x] Add token count capture if the CLI/SDK exposes usage.
  - Extracts token usage (input_tokens, output_tokens, cache_read, cache_creation) from Claude transcript
  - Adds tokens.* span attributes: tokens.input, tokens.output, tokens.cache_read, tokens.cache_creation, tokens.total
  - Tests added in `tests/test_hooks.py`
- [x] Add resilience features (bounded queues/drop policy, retries).
- [x] Refactor hooks into installable CLI entry points (move `hooks/*.py` to `src/claude_otel/hooks/`, add `claude-otel-pre-tool` and `claude-otel-post-tool` scripts to `pyproject.toml`).

---

## Milestone 4: Feature Parity with claude_telemetry

### Context
The `claude_telemetry` repo (in `/claude_telemetry/`) provides a reference implementation with complementary features. This milestone establishes feature parity by identifying gaps in both directions and implementing missing functionality.

### Architecture Comparison

**claude-otel (current):**
- External wrapper script that execs `claude` CLI
- Uses Claude Code CLI hooks (PostToolUse, PreToolUse scripts)
- Metrics: tool invocations, token usage from transcript, payload sizes
- Args passthrough: All args passed directly to `claude` command via subprocess
- Configuration: OTEL_* environment variables

**claude_telemetry (reference):**
- Python wrapper using `claude-agent-sdk` directly
- Uses SDK hooks (UserPromptSubmit, PreToolUse, PostToolUse, MessageComplete, PreCompact)
- Metrics: tool invocations, token usage from `message.usage`, turn tracking, model info
- Args passthrough: Converts `extra_args` dict to CLI flags for SDK
- Configuration: OTEL_* + backend-specific (LOGFIRE_TOKEN, SENTRY_DSN)
- CLI: `claudia` command with full arg parsing and interactive mode

### Metrics & Telemetry Comparison

#### Token Usage
**claude-otel** (from transcript):
- `tokens.input` - Input tokens
- `tokens.output` - Output tokens
- `tokens.cache_read` - Cache read tokens
- `tokens.cache_creation` - Cache creation tokens
- `tokens.total` - Total tokens

**claude_telemetry** (from message.usage):
- `gen_ai.usage.input_tokens` - Input tokens
- `gen_ai.usage.output_tokens` - Output tokens
- `turns` - Turn count

**Gap:** claude_telemetry missing cache metrics; claude-otel missing gen_ai.* semantic conventions and turn tracking.

#### Tool Metrics
**claude-otel:**
- `tool.name`, `duration_ms`, `exit_code`, `error`, `error.message`
- `input.summary`, `input.truncated`
- `response_bytes`, `response.truncated`
- `session.id`, `tool.use_id`
- Metrics: `claude.tool_calls_total`, `claude.tool_calls_errors_total`, `claude.tool_call_duration_ms`

**claude_telemetry:**
- `tool.name`, duration (as span)
- `gen_ai.operation.name`, `gen_ai.system`
- `tool.input.*`, `tool.response.*`, `tool.status`, `tool.error`
- Detailed tool events with structured data
- Console logging with emoji indicators
- Tool input/output formatting

**Gap:** claude-otel missing detailed tool I/O attributes and gen_ai.* conventions; claude_telemetry missing explicit metrics export.

#### Session/Conversation Tracking
**claude-otel:**
- Basic session span with `session.id`
- Single command execution model

**claude_telemetry:**
- Session span with prompt, model, session_id
- `gen_ai.request.model`, `gen_ai.response.model`
- Turn tracking (`turns` counter)
- Context compaction events (PreCompact hook)
- Interactive mode support
- Message history tracking

**Gap:** claude-otel missing conversation/turn tracking, model metadata, and compaction events.

### Args Passthrough Comparison

**claude-otel:**
```python
# Direct passthrough to subprocess
subprocess.run([claude_bin] + args, ...)
```
- All args passed unchanged to `claude` command
- No interpretation or validation
- Simple and direct

**claude_telemetry:**
```python
# SDK-based passthrough via extra_args dict
options = ClaudeAgentOptions(
    setting_sources=["user", "project", "local"],
    extra_args={"model": "opus", "permission-mode": "bypassPermissions"},
    stderr=log_handler,
    hooks=hook_config,
)
```
- Converts dict to CLI flags for SDK
- Supports all Claude CLI flags through `extra_args`
- CLI parsing: `parse_claude_args()` splits prompt from flags
- Future-proof: new Claude flags work without code changes

**Gap:** claude-otel lacks rich CLI parsing and dict-based arg handling.

### Feature Gap Tasks

#### Phase 1: SDK Integration & Hook Enhancement

**Note:** SDK-based hooks implemented in `src/claude_otel/sdk_hooks.py`. SDK runner integration pending in Phase 2.

- [x] Add `claude-agent-sdk` dependency to pyproject.toml
- [x] Add SDK-based hooks alongside CLI hooks for richer telemetry
  - [x] Implement UserPromptSubmit hook to capture prompt and model
  - [x] Implement MessageComplete hook for turn tracking and usage
  - [x] Implement PreCompact hook for context window tracking
  - [x] Add `gen_ai.*` semantic convention attributes (gen_ai.system, gen_ai.request.model, gen_ai.response.model, gen_ai.operation.name)
- [x] MessageComplete hook features (all implemented)
  - [x] Extract token usage from `message.usage` (input_tokens, output_tokens, cache_read, cache_creation)
  - [x] Track turn count per session (increment on each message)
  - [x] Update span with cumulative token usage
  - [x] Add turn events with incremental token counts
  - [x] Add `gen_ai.usage.input_tokens` and `gen_ai.usage.output_tokens` attributes
  - [x] Store message history for session context
- [x] Add SDK-based runner alongside subprocess wrapper
  - [x] Implement SDK-based runner in `src/claude_otel/sdk_runner.py`
  - [x] Create SDK hook manager to bridge SDK callbacks to OTEL spans
  - [x] Add `--use-sdk` flag to `claude-otel` CLI for opt-in SDK mode
  - [x] Maintain backward compatibility with subprocess wrapper (default)
- [x] Enhance tool span attributes
  - [x] Add detailed `tool.input.*` and `tool.response.*` attributes
  - [x] Add `tool.status` attribute (success/error)
  - [x] Improve error detection and `tool.error` messaging

#### Phase 2: CLI & Args Enhancement
- [x] Implement rich CLI with arg parsing (like `claudia`)
  - [x] Add Typer-based CLI with `--help`, `--version`, `--config` flags
  - [x] Implement `parse_claude_args()` to separate prompt from flags
  - [x] Support both `--flag=value` and `--flag value` formats
  - [x] Add debug mode (`--claude-otel-debug`)
- [x] Add interactive mode
  - [x] Implement multi-turn REPL with shared context
  - [x] Add session metrics tracking (total tokens, tools used)
  - [x] Show startup banner with configuration
  - [x] Support exit commands (exit, quit, bye) and Ctrl+C handling

#### Phase 3: Enhanced Observability
- [x] Add rich console output (like claude_telemetry)
  - [x] Emoji indicators (🤖, 🔧, ✅, ❌, 🎉)
  - [x] Smart truncation for tool inputs/outputs
  - [x] Formatted panels for responses (Rich library)
  - [x] Tool execution logging with structured display
- [x] Improve metrics export
  - [x] Add turn count metric
  - [x] Add cache hit/miss metrics
  - [x] Add model usage distribution
  - [x] Add context compaction frequency
- [x] Add backend-specific adapters (optional)
  - [x] Logfire adapter with LLM UI formatting
  - [x] Sentry adapter with AI monitoring attributes
  - [x] Auto-detection via environment variables

#### Phase 4: Testing & Documentation
- [x] Add tests for new features
  - [x] SDK hook tests (UserPromptSubmit, MessageComplete, PreCompact)
  - [x] CLI arg parsing tests
  - [x] Turn tracking tests
  - [x] Interactive mode tests
  - [x] SDK runner integration tests
  - [x] Fix failing wrapper tests (run_claude signature change)
- [x] Update documentation
  - [x] Document new metrics (gen_ai.*, turns, model)
  - [x] Document CLI flags and interactive mode
  - [x] Add examples for SDK-based usage
  - [x] Update troubleshooting guide
- [x] Create migration guide
  - [x] Document differences between subprocess and SDK modes
  - [x] Provide migration path from simple to rich telemetry
  - [x] Show side-by-side examples

### Implementation Notes

1. **Dual Architecture:** Maintain both subprocess wrapper (simple) and SDK-based runner (rich) for flexibility
2. **Backward Compatibility:** Existing `claude-otel` command continues to work unchanged
3. **Progressive Enhancement:** Users can opt into richer telemetry by using SDK mode
4. **Testing Strategy:** Test both architectures independently and in integration
5. **Documentation:** Clear guidance on when to use each approach

### Success Criteria
- [x] All metrics from claude_telemetry available in claude-otel
- [x] Full args passthrough via both subprocess and SDK modes
- [x] Interactive mode functional with session tracking
- [x] Rich console output with formatting
- [x] Tests passing for all new features
- [x] Documentation updated and examples provided

---

## Post-MVP: Bug Fixes & Improvements
- [x] Fix interactive mode output formatting to match claude_telemetry (accumulate response, display in Panel)
- [x] Improve interactive mode input prompting
  - Add clear "Waiting for your input..." or similar indicator before prompt
  - Show context (e.g., turn number, session info) in prompt
  - Make it obvious when Claude is waiting vs. processing
  - Consider using Rich's styled prompt or status indicators

## Telemetry Enhancements
- [x] Add session duration tracking
  - Record session start/end times
  - Add session.duration_ms span attribute
  - Log session duration on completion
- [x] Add tool-call duration tracking
  - Record tool start/end times in SDK hooks
  - Add tool.duration_ms attribute to tool spans
  - Include in tool metrics
- [x] Add interactive prompt latency tracking
  - Track time between prompts in interactive mode
  - Record human response time (prompt-to-prompt latency)
  - Add prompt.latency_ms metric
  - Useful for understanding user interaction patterns
- [x] Add per-tool-call logging
  - Emit a log per tool call from SDK hooks PostToolUse path
  - Include tool.name, duration, exit_code, tokens, and other tool metadata
  - Currently tool names aren't in any logs (SDK only logs session summary)
  - Needed for charting tools per session in Loki/Grafana
- [x] Fix failing test: test_sdk_runner_creates_spans
  - Test expects setup_sdk_hooks to be called with (tracer) but it's called with (tracer, None)
  - Update test mock assertion to match actual function signature

## Ralph Loop Integration Issues (2026-01-18)

These bugs were discovered during ralph-loop testing with `--max-iterations 1`.

### Installation Issues
- [ ] claude-otel binary using old entry point (wrapper:main instead of cli:app)
  - pyproject.toml defines entry point as "claude_otel.cli:app" (new Typer-based CLI)
  - Installed binary at /opt/homebrew/bin/claude-otel uses "claude_otel.wrapper:main" (old CLI)
  - Cause: Package needs to be reinstalled after pyproject.toml was updated
  - Fix: `pip install -e .` to update the console_scripts entry point
  - Impact: Interactive mode not available, old CLI doesn't support Typer features
  - Priority: HIGH - blocks interactive mode functionality

### Critical Bugs
- [ ] Fix PreToolUse/PostToolUse hook errors
  - Hooks are failing for Grep, Read, TodoWrite tools with "hook error" messages
  - Tools still execute successfully (hooks don't block execution)
  - Need to investigate what's causing the hooks to error
  - Likely mismatch between expected hook signature/context and what Claude Code provides
  - Check src/claude_otel/sdk_hooks.py on_pre_tool_use/on_post_tool_use implementations
  - Priority: HIGH - hooks are core telemetry functionality

- [charlie] Fix KeyError in complete_session() when metrics keys missing
  - Bug location: src/claude_otel/sdk_hooks.py:534-537
  - Root cause: Code accesses self.metrics['input_tokens'] and self.metrics['output_tokens'] directly
  - Failing test: test_complete_session_ends_span_and_flushes (tests/test_hooks.py:998-1002)
  - Test sets up metrics dict without input_tokens/output_tokens keys
  - Fix: Use .get() with default values: self.metrics.get('input_tokens', 0)
  - Priority: MEDIUM - causes test failure, defensive coding needed

### Token Count Issues
- [ ] Investigate why MessageComplete hook not firing in ralph-loop
  - Symptom: Token counts show "0 in, 0 out" despite 35 tools used over 544.9s
  - PreToolUse/PostToolUse hooks ARE working (tool count = 35)
  - MessageComplete hook NOT working (token counts = 0)
  - Check if SDK fires MessageComplete in ralph-loop context
  - Check if message.usage attribute is present
  - May need fallback token counting mechanism
  - Priority: MEDIUM - affects telemetry completeness

### Output Formatting Issues
- [ ] Fix missing line breaks in SDK output
  - Symptom: Output compressed like "manually:Now let me analyze" without line breaks
  - Location: src/claude_otel/sdk_runner.py:188 extract_message_text()
  - Root cause: "".join() concatenates text blocks without separators
  - Fix: Add newline between text blocks or preserve original spacing
  - Priority: LOW - cosmetic issue, doesn't affect functionality

### Workflow Issues (Not Code Bugs)
- [ ] Document file permission workflow for ralph-loop
  - Issue: Agent attempted file edits but permissions not requested/granted
  - This is expected behavior - Edit/Write tools should prompt for permissions
  - In ralph-loop with --max-iterations 1, permission prompts may be bypassed
  - Not a bug, but needs documentation for ralph-loop users
  - Consider: Should EnterPlanMode be required before file edits in automated contexts?
  - Priority: LOW - documentation task
