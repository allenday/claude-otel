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
- [ ] Emit session span and child spans for tool uses (attributes: tool.name, duration_ms, exit_code/error flag, stdout_bytes, stderr_bytes, truncated flags, input summary, prompt/session IDs).
- [x] Export traces and logs via OTLP to bastion (default gRPC 4317; HTTP optional).
- [ ] Export basic metrics (counters: tool_calls total/per tool; gauge: in-flight tools if applicable).
- [alpha] Config via env (OTEL_*), with a single coherent protocol/endpoint; default to gRPC 4317.
- [bravo] Apply lightweight PII safeguards: truncate tool inputs/outputs, avoid storing raw large payloads.
- [ ] Add unit tests for hook logic (span creation, duration calc, error paths) and a local integration test that sends a dummy span/log to bastion.

## Milestone 2: Deployment & Validation
- [ ] Add a small docs section in the repo (usage, env vars, troubleshooting).
- [ ] Run a manual smoke session; verify `service_name` appears in Loki and metrics counters increment on bastion.
- [ ] Optional: add a span-to-logs processor on collector if traces need to surface in Loki (only if requested).

## Milestone 3: Enhancements (Optional)
- [ ] Add per-tool metrics labels (tool.name) for Prometheus counters.
- [ ] Add configurable redaction rules (regex/allowlist) for inputs/outputs.
- [ ] Add token count capture if the CLI/SDK exposes usage.
- [ ] Add resilience features (bounded queues/drop policy, retries).
