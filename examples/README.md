# Claude OTEL SDK Examples

This directory contains examples demonstrating SDK-based usage of `claude-otel` for rich telemetry and advanced use cases.

## Overview

`claude-otel` supports two modes:
- **CLI Mode (default)**: Subprocess wrapper around `claude` CLI
- **SDK Mode**: Direct integration with `claude-agent-sdk` for richer telemetry

These examples focus on SDK mode, which provides:
- Rich semantic conventions (`gen_ai.*` attributes)
- Turn tracking with per-turn token counts
- Interactive REPL mode
- Real-time metrics and structured console output
- Backend-specific adapters (Logfire, Sentry)

## Examples

### 1. Basic SDK Usage (`basic_sdk.py`)

Simplest SDK usage - run a single prompt with enhanced telemetry.

```bash
python examples/basic_sdk.py
```

**Use when:**
- You want richer telemetry than CLI mode
- Need semantic conventions for LLM observability tools
- Want to capture model and turn information

### 2. Interactive REPL (`interactive_repl.py`)

Multi-turn conversational interface with shared context.

```bash
python examples/interactive_repl.py
```

**Use when:**
- Building conversational applications
- Testing multi-turn workflows
- Debugging context management

### 3. Custom Metrics (`custom_metrics.py`)

Add application-specific metrics alongside OTEL metrics.

```bash
python examples/custom_metrics.py
```

**Use when:**
- Tracking custom KPIs (cost, latency, quality)
- Implementing business logic metrics
- Building dashboards with combined telemetry

### 4. Backend Integration (`backend_integration.py`)

Using Logfire and Sentry adapters for specialized LLM monitoring.

```bash
# With Logfire
LOGFIRE_TOKEN=your_token python examples/backend_integration.py --backend logfire

# With Sentry
SENTRY_DSN=your_dsn python examples/backend_integration.py --backend sentry
```

**Use when:**
- Using Logfire for LLM-specific UI
- Monitoring AI errors with Sentry AI
- Need specialized AI observability features

### 5. Programmatic SDK (`programmatic_sdk.py`)

Direct SDK integration without CLI wrapper for embedding in applications.

```bash
python examples/programmatic_sdk.py
```

**Use when:**
- Embedding Claude in larger applications
- Need full control over SDK configuration
- Building custom integrations

### 6. Token Tracking (`token_tracking.py`)

Monitor and optimize token usage with detailed tracking.

```bash
python examples/token_tracking.py
```

**Use when:**
- Optimizing costs
- Tracking cache hit rates
- Analyzing token usage patterns

## Environment Variables

All examples support standard OTEL environment variables:

```bash
# OTLP endpoint (default: http://localhost:4317)
export OTEL_EXPORTER_OTLP_ENDPOINT="http://collector:4317"

# Service identity
export OTEL_SERVICE_NAME="my-claude-app"
export OTEL_SERVICE_NAMESPACE="production"

# Enable metrics (default: none)
export OTEL_METRICS_EXPORTER=otlp

# Debug output
export CLAUDE_OTEL_DEBUG=1
```

## Running Examples

### Prerequisites

```bash
# Install claude-otel with SDK dependencies
pip install -e .

# Or install dependencies manually
pip install claude-agent-sdk opentelemetry-api opentelemetry-sdk rich
```

### Quick Start

```bash
# 1. Start OTLP collector (optional, for telemetry)
docker run -p 4317:4317 -p 4318:4318 otel/opentelemetry-collector

# 2. Run an example
python examples/basic_sdk.py

# 3. View telemetry in your collector/backend
```

### Running Without Collector

For local testing without telemetry export:

```bash
OTEL_TRACES_EXPORTER=none python examples/basic_sdk.py
```

## Comparison: CLI vs SDK Mode

| Feature | CLI Mode | SDK Mode (Examples) |
|---------|----------|---------------------|
| **Setup** | `claude-otel "prompt"` | `python examples/basic_sdk.py` |
| **Subprocess** | Yes (shells out to `claude`) | No (SDK direct) |
| **Telemetry** | Basic tool metrics | Rich conversation tracking |
| **Attributes** | `tool.*`, `tokens.*` | `gen_ai.*`, `tool.*`, `tokens.*`, `turns` |
| **Interactive** | No | Yes |
| **Customization** | Limited | Full SDK control |
| **Integration** | CLI wrapper | Programmatic |

## Common Patterns

### Pattern 1: One-Shot with Telemetry

```python
from claude_otel.sdk_runner import run_agent_with_sdk
import asyncio

async def main():
    await run_agent_with_sdk(
        prompt="What is 2+2?",
        extra_args={"model": "opus"}
    )

asyncio.run(main())
```

### Pattern 2: Interactive Session

```bash
# Command line
claude-otel --interactive

# Or programmatically (see interactive_repl.py)
```

### Pattern 3: Custom Hooks

```python
from claude_otel.sdk_hooks import SDKTelemetryHooks

class CustomHooks(SDKTelemetryHooks):
    def on_message_complete(self, message, ...):
        super().on_message_complete(message, ...)
        # Add custom logic
        self.record_cost(message.usage)
```

## Troubleshooting

### "claude-agent-sdk not found"

```bash
pip install claude-agent-sdk
```

### "No telemetry appearing"

Check environment variables:
```bash
export OTEL_TRACES_EXPORTER=otlp
export OTEL_EXPORTER_OTLP_ENDPOINT="http://localhost:4317"
export CLAUDE_OTEL_DEBUG=1
```

### "Import errors"

Ensure all dependencies are installed:
```bash
pip install -e .  # From repository root
```

## Next Steps

1. **Start Simple**: Try `basic_sdk.py` to understand SDK mode
2. **Add Metrics**: Use `custom_metrics.py` to track KPIs
3. **Go Interactive**: Explore `interactive_repl.py` for conversational AI
4. **Integrate Backend**: Connect to Logfire/Sentry with `backend_integration.py`
5. **Customize**: Use `programmatic_sdk.py` as a template for your app

## Resources

- [Migration Guide](../MIGRATION.md) - CLI vs SDK mode comparison
- [README](../README.md) - Configuration and environment variables
- [OpenTelemetry Semantic Conventions](https://opentelemetry.io/docs/specs/semconv/gen-ai/)
- [Claude Agent SDK Docs](https://github.com/anthropics/claude-agent-sdk)

## Contributing

Have an interesting SDK usage pattern? Add it to this directory with:
1. A standalone `.py` file demonstrating the pattern
2. Update this README with a description and use case
3. Add inline comments explaining key concepts
