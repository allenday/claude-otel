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
- [charlie] Optional: add a span-to-logs processor on collector if traces need to surface in Loki (only if requested).

## Milestone 3: Enhancements (Optional)
- [x] Add per-tool metrics labels (tool.name) for Prometheus counters.
- [x] Add configurable redaction rules (regex/allowlist) for inputs/outputs.
- [x] Add token count capture if the CLI/SDK exposes usage.
  - Extracts token usage (input_tokens, output_tokens, cache_read, cache_creation) from Claude transcript
  - Adds tokens.* span attributes: tokens.input, tokens.output, tokens.cache_read, tokens.cache_creation, tokens.total
  - Tests added in `tests/test_hooks.py`
- [x] Add resilience features (bounded queues/drop policy, retries).
- [alpha] Refactor hooks into installable CLI entry points (move `hooks/*.py` to `src/claude_otel/hooks/`, add `claude-otel-pre-tool` and `claude-otel-post-tool` scripts to `pyproject.toml`).

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
- [ ] Add SDK-based hooks alongside CLI hooks for richer telemetry
  - [bravo] Implement UserPromptSubmit hook to capture prompt and model
  - [ ] Implement MessageComplete hook for turn tracking and usage
  - [ ] Implement PreCompact hook for context window tracking
  - [ ] Add `gen_ai.*` semantic convention attributes (gen_ai.system, gen_ai.request.model, gen_ai.response.model, gen_ai.operation.name)
- [ ] Add turn/conversation tracking to spans
  - [ ] Track turn count per session
  - [ ] Add turn events with incremental token counts
  - [ ] Store message history for session context
- [ ] Enhance tool span attributes
  - [ ] Add detailed `tool.input.*` and `tool.response.*` attributes
  - [ ] Add `tool.status` attribute (success/error)
  - [ ] Improve error detection and `tool.error` messaging

#### Phase 2: CLI & Args Enhancement
- [ ] Implement rich CLI with arg parsing (like `claudia`)
  - [ ] Add Typer-based CLI with `--help`, `--version`, `--config` flags
  - [ ] Implement `parse_claude_args()` to separate prompt from flags
  - [ ] Support both `--flag=value` and `--flag value` formats
  - [ ] Add debug mode (`--claude-otel-debug`)
- [ ] Add SDK-based runner alongside subprocess wrapper
  - [ ] Implement `run_agent_with_telemetry()` using claude-agent-sdk
  - [ ] Support `extra_args` dict for CLI flags passthrough
  - [ ] Add `ClaudeAgentOptions` configuration with setting_sources
  - [ ] Maintain backward compatibility with subprocess wrapper
- [ ] Add interactive mode
  - [ ] Implement multi-turn REPL with shared context
  - [ ] Add session metrics tracking (total tokens, tools used)
  - [ ] Show startup banner with configuration
  - [ ] Support exit commands (exit, quit, bye) and Ctrl+C handling

#### Phase 3: Enhanced Observability
- [ ] Add rich console output (like claude_telemetry)
  - [ ] Emoji indicators (🤖, 🔧, ✅, ❌, 🎉)
  - [ ] Smart truncation for tool inputs/outputs
  - [ ] Formatted panels for responses (Rich library)
  - [ ] Tool execution logging with structured display
- [ ] Improve metrics export
  - [ ] Add turn count metric
  - [ ] Add cache hit/miss metrics
  - [ ] Add model usage distribution
  - [ ] Add context compaction frequency
- [ ] Add backend-specific adapters (optional)
  - [ ] Logfire adapter with LLM UI formatting
  - [ ] Sentry adapter with AI monitoring attributes
  - [ ] Auto-detection via environment variables

#### Phase 4: Testing & Documentation
- [ ] Add tests for new features
  - [ ] SDK hook tests (UserPromptSubmit, MessageComplete, PreCompact)
  - [ ] CLI arg parsing tests
  - [ ] Turn tracking tests
  - [ ] Interactive mode tests
- [ ] Update documentation
  - [ ] Document new metrics (gen_ai.*, turns, model)
  - [ ] Document CLI flags and interactive mode
  - [ ] Add examples for SDK-based usage
  - [ ] Update troubleshooting guide
- [ ] Create migration guide
  - [ ] Document differences between subprocess and SDK modes
  - [ ] Provide migration path from simple to rich telemetry
  - [ ] Show side-by-side examples

### Implementation Notes

1. **Dual Architecture:** Maintain both subprocess wrapper (simple) and SDK-based runner (rich) for flexibility
2. **Backward Compatibility:** Existing `claude-otel` command continues to work unchanged
3. **Progressive Enhancement:** Users can opt into richer telemetry by using SDK mode
4. **Testing Strategy:** Test both architectures independently and in integration
5. **Documentation:** Clear guidance on when to use each approach

### Success Criteria
- [ ] All metrics from claude_telemetry available in claude-otel
- [ ] Full args passthrough via both subprocess and SDK modes
- [ ] Interactive mode functional with session tracking
- [ ] Rich console output with formatting
- [ ] Tests passing for all new features
- [ ] Documentation updated and examples provided
