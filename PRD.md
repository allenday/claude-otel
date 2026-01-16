# OTEL Telemetry Wrapper for Claude CLI

## Context
- Current `third-party/claude_telemetry` integration is brittle (session span required, inconsistent error handling) and not reliably delivering logs to our OTEL collector/Loki.
- We want reliable telemetry (traces + logs) from local Claude CLI sessions, with richer tool-call metrics than Claude’s built-in telemetry.

## Goals
- Emit OTEL traces and logs for every Claude CLI session and tool use.
- Capture tool-level metrics: duration, exit status/errors, stdout/stderr size, tool name, input summary, prompt/session IDs.
- Deliver data to our OTEL collector on bastion (`100.91.20.46:4317` gRPC, 4318 HTTP) and store logs in Loki.
- Keep client-side setup minimal (env-based configuration).

## Non-Goals
- Building a UI or analytics layer (Grafana/Loki queries suffice for now).
- Replacing Claude CLI functionality; we wrap/instrument it.
- Persisting traces long-term (unless we add Tempo later).

## Functional Requirements
- Start a session span per CLI session; child spans per tool use.
- Log events for user prompts, assistant responses, and tool lifecycle (pre/post, errors).
- Attach attributes:
  - Session: service.name, service.namespace, session_id, prompt preview/model, total tool count, token counts if exposed.
  - Tool span: tool.name, duration_ms, exit_code (if subprocess), error flag/message, stdout_bytes, stderr_bytes, truncated flags, input summary (truncated), interrupted/timeout indicators.
- Exporters:
  - Traces: OTLP to `100.91.20.46:4317` (gRPC) or `:4318` HTTP.
  - Logs: OTLP logs to same endpoint; Loki receives via collector.
- Config via env:
  - `OTEL_EXPORTER_OTLP_ENDPOINT`, `OTEL_EXPORTER_OTLP_PROTOCOL` (grpc/http), `OTEL_SERVICE_NAME`, `OTEL_RESOURCE_ATTRIBUTES`, `OTEL_TRACES_EXPORTER`, `OTEL_LOGS_EXPORTER`, `OTEL_METRICS_EXPORTER` (default none), `OTEL_TRACES_SAMPLER`.
- Fallback behavior: tolerate missing spans (no hard crashes), buffer small batches, and drop gracefully on network errors.

## Collector/Infra Considerations
- Optionally add span-to-logs processor so traces also surface in Loki.
- Keep current Loki/OTLP endpoints; no new infra required for MVP.

## UX/CLI
- Provide a lightweight wrapper script (e.g., `bin/claude-otel`) that shells out to Claude CLI/SDK with hooks.
- Debug flag to emit local logs if export fails.
- Minimal setup instructions (env vars + pip install).

## Testing/Validation
- Unit tests for hook logic (span creation, attributes, duration calc, error paths).
- Local integration test: send a dummy span/log to bastion OTLP and confirm it appears in Loki.
- Manual smoke: run a Claude session with a few tool calls, verify `service_name` appears in Loki and attributes include tool metrics.

## Risks/Watchouts
- Mixing HTTP vs gRPC endpoints leads to connection resets; enforce coherent config.
- Large stdout/stderr may need truncation limits.
- Token counts only available if the CLI/SDK exposes them.
- Backpressure if collector unreachable—use bounded queues/drop policy.

## Open Questions
1) Which attributes are mandatory vs nice-to-have (e.g., full tool input, stdout/stderr hashes, token counts)? → Start lightweight; YAGNI but keep extensible.
2) Preferred protocol for clients (gRPC vs HTTP) and whether to support both. → Default gRPC; HTTP optional but low priority.
3) Should we add a span-to-logs processor on the collector by default? → Not required unless needed later.
4) Do we need metrics export (counters) in addition to traces/logs? → Yes, include basic counters/gauges.
5) Retention/PII: any fields to redact or avoid logging? → Likely; trim/redact inputs/outputs and limit payload sizes; be ready to tighten redaction.
