"""OTEL metrics for Claude CLI instrumentation.

Provides counters and gauges for tool call telemetry:
- tool_calls_total: Counter of total tool invocations (with tool.name label)
- tool_calls_errors_total: Counter of tool call errors (with tool.name label)
- tool_calls_in_flight: Gauge of currently executing tools

Uses centralized config from claude_otel.config.
"""

from typing import Optional

from opentelemetry import metrics
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
from opentelemetry.sdk.resources import Resource, SERVICE_NAME, SERVICE_NAMESPACE

from claude_otel.config import get_config, OTelConfig


_meter_provider: Optional[MeterProvider] = None
_meter: Optional[metrics.Meter] = None

# Metric instruments (initialized lazily)
_tool_calls_counter: Optional[metrics.Counter] = None
_tool_errors_counter: Optional[metrics.Counter] = None
_tool_duration_histogram: Optional[metrics.Histogram] = None
_in_flight_gauge_value: int = 0

# New metrics for enhanced observability
_turn_counter: Optional[metrics.Counter] = None
_cache_hits_counter: Optional[metrics.Counter] = None
_cache_misses_counter: Optional[metrics.Counter] = None
_cache_creations_counter: Optional[metrics.Counter] = None
_model_requests_counter: Optional[metrics.Counter] = None
_compaction_counter: Optional[metrics.Counter] = None
_prompt_latency_histogram: Optional[metrics.Histogram] = None


def _create_metric_exporter(config: OTelConfig):
    """Create OTLP metric exporter based on protocol."""
    if config.is_grpc:
        from opentelemetry.exporter.otlp.proto.grpc.metric_exporter import OTLPMetricExporter
        return OTLPMetricExporter(endpoint=config.endpoint, insecure=True)
    else:
        from opentelemetry.exporter.otlp.proto.http.metric_exporter import OTLPMetricExporter
        # HTTP endpoint uses /v1/metrics path
        endpoint = config.http_endpoint
        if not endpoint.endswith("/v1/metrics"):
            endpoint = endpoint.rstrip("/") + "/v1/metrics"
        return OTLPMetricExporter(endpoint=endpoint)


def _create_resource(config: OTelConfig) -> Resource:
    """Create OTEL resource from config."""
    attrs = {
        SERVICE_NAME: config.service_name,
        SERVICE_NAMESPACE: config.service_namespace,
    }
    attrs.update(config.resource_attributes)
    return Resource.create(attrs)


def configure_metrics(config: Optional[OTelConfig] = None) -> Optional[MeterProvider]:
    """Configure OTEL metrics with OTLP exporter.

    Args:
        config: Optional OTelConfig. If None, loads from environment.

    Returns:
        MeterProvider if metrics enabled, None otherwise.
    """
    global _meter_provider, _meter

    if config is None:
        config = get_config()

    if not config.metrics_enabled:
        if config.debug:
            import sys
            print("[claude-otel] Metrics export disabled", file=sys.stderr)
        return None

    if _meter_provider is not None:
        return _meter_provider

    resource = _create_resource(config)

    try:
        exporter = _create_metric_exporter(config)
        reader = PeriodicExportingMetricReader(
            exporter,
            export_interval_millis=10000,  # 10 second export interval
        )
        _meter_provider = MeterProvider(resource=resource, metric_readers=[reader])
        metrics.set_meter_provider(_meter_provider)
        _meter = _meter_provider.get_meter("claude-otel", "0.1.0")

        if config.debug:
            import sys
            print(f"[claude-otel] Metrics configured: {config.endpoint}", file=sys.stderr)

    except Exception as e:
        import sys
        print(f"[claude-otel] Warning: failed to configure metrics: {e}", file=sys.stderr)
        return None

    return _meter_provider


def get_meter() -> Optional[metrics.Meter]:
    """Get the configured meter for creating instruments.

    Returns:
        Meter if configured, None otherwise.
    """
    return _meter


def _ensure_instruments():
    """Lazily initialize metric instruments."""
    global _tool_calls_counter, _tool_errors_counter, _tool_duration_histogram
    global _turn_counter, _cache_hits_counter, _cache_misses_counter
    global _cache_creations_counter, _model_requests_counter, _compaction_counter
    global _prompt_latency_histogram

    if _meter is None:
        return

    if _tool_calls_counter is None:
        _tool_calls_counter = _meter.create_counter(
            name="claude.tool_calls_total",
            description="Total number of tool calls",
            unit="1",
        )

    if _tool_errors_counter is None:
        _tool_errors_counter = _meter.create_counter(
            name="claude.tool_calls_errors_total",
            description="Total number of tool call errors",
            unit="1",
        )

    if _tool_duration_histogram is None:
        _tool_duration_histogram = _meter.create_histogram(
            name="claude.tool_call_duration_ms",
            description="Duration of tool calls in milliseconds",
            unit="ms",
        )

    # Enhanced observability metrics
    if _turn_counter is None:
        _turn_counter = _meter.create_counter(
            name="claude.turns_total",
            description="Total number of conversation turns",
            unit="1",
        )

    if _cache_hits_counter is None:
        _cache_hits_counter = _meter.create_counter(
            name="claude.cache_hits_total",
            description="Total number of cache hits (cache_read_input_tokens > 0)",
            unit="1",
        )

    if _cache_misses_counter is None:
        _cache_misses_counter = _meter.create_counter(
            name="claude.cache_misses_total",
            description="Total number of cache misses (cache_read_input_tokens == 0)",
            unit="1",
        )

    if _cache_creations_counter is None:
        _cache_creations_counter = _meter.create_counter(
            name="claude.cache_creations_total",
            description="Total number of cache creations (cache_creation_input_tokens > 0)",
            unit="1",
        )

    if _model_requests_counter is None:
        _model_requests_counter = _meter.create_counter(
            name="claude.model_requests_total",
            description="Total number of API requests by model",
            unit="1",
        )

    if _compaction_counter is None:
        _compaction_counter = _meter.create_counter(
            name="claude.context_compactions_total",
            description="Total number of context compaction events",
            unit="1",
        )

    if _prompt_latency_histogram is None:
        _prompt_latency_histogram = _meter.create_histogram(
            name="claude.prompt_latency_ms",
            description="Latency between prompts in interactive mode (human response time)",
            unit="ms",
        )


def record_tool_call(tool_name: str, duration_ms: float, error: bool = False):
    """Record a tool call metric.

    Args:
        tool_name: Name of the tool invoked.
        duration_ms: Duration of the call in milliseconds.
        error: Whether the call resulted in an error.
    """
    _ensure_instruments()

    if _tool_calls_counter is None:
        return

    attributes = {"tool.name": tool_name}

    _tool_calls_counter.add(1, attributes)
    _tool_duration_histogram.add(duration_ms, attributes)

    if error:
        _tool_errors_counter.add(1, attributes)


def record_session_start():
    """Record the start of a Claude session."""
    _ensure_instruments()

    if _meter is None:
        return

    # We use an UpDownCounter for in-flight since we can increment/decrement
    global _in_flight_gauge_value
    _in_flight_gauge_value += 1


def record_session_end():
    """Record the end of a Claude session."""
    global _in_flight_gauge_value
    _in_flight_gauge_value = max(0, _in_flight_gauge_value - 1)


def get_in_flight_count() -> int:
    """Get current in-flight session count.

    Returns:
        Number of sessions currently in progress.
    """
    return _in_flight_gauge_value


def record_turn(model: str = "unknown", count: int = 1):
    """Record a conversation turn completion.

    Args:
        model: Model used for the turn (default: "unknown").
        count: Number of turns to record (default: 1).
    """
    _ensure_instruments()

    if _turn_counter is None:
        return

    attributes = {"model": model}
    _turn_counter.add(count, attributes)


def record_cache_usage(
    cache_read_tokens: int = 0,
    cache_creation_tokens: int = 0,
    model: str = "unknown",
):
    """Record cache hit/miss and cache creation metrics.

    Args:
        cache_read_tokens: Number of tokens read from cache.
        cache_creation_tokens: Number of tokens created in cache.
        model: Model used (default: "unknown").
    """
    _ensure_instruments()

    if _cache_hits_counter is None:
        return

    attributes = {"model": model}

    # Record cache hit or miss
    if cache_read_tokens > 0:
        _cache_hits_counter.add(1, attributes)
    else:
        _cache_misses_counter.add(1, attributes)

    # Record cache creation
    if cache_creation_tokens > 0:
        _cache_creations_counter.add(1, attributes)


def record_model_request(model: str = "unknown"):
    """Record an API request to a specific model.

    Args:
        model: Model name (default: "unknown").
    """
    _ensure_instruments()

    if _model_requests_counter is None:
        return

    attributes = {"model": model}
    _model_requests_counter.add(1, attributes)


def record_context_compaction(trigger: str = "unknown", model: str = "unknown"):
    """Record a context compaction event.

    Args:
        trigger: What triggered the compaction (e.g., "token_limit", "user_request").
        model: Model being used (default: "unknown").
    """
    _ensure_instruments()

    if _compaction_counter is None:
        return

    attributes = {"trigger": trigger, "model": model}
    _compaction_counter.add(1, attributes)


def record_prompt_latency(latency_ms: float, model: str = "unknown"):
    """Record prompt latency (time between prompts in interactive mode).

    Args:
        latency_ms: Latency in milliseconds between prompt completion and next submission.
        model: Model being used (default: "unknown").
    """
    _ensure_instruments()

    if _prompt_latency_histogram is None:
        return

    attributes = {"model": model}
    _prompt_latency_histogram.add(latency_ms, attributes)


def shutdown_metrics():
    """Shutdown the meter provider and flush pending metrics."""
    global _meter_provider, _meter, _tool_calls_counter, _tool_errors_counter
    global _tool_duration_histogram, _in_flight_gauge_value
    global _turn_counter, _cache_hits_counter, _cache_misses_counter
    global _cache_creations_counter, _model_requests_counter, _compaction_counter
    global _prompt_latency_histogram

    if _meter_provider is not None:
        _meter_provider.shutdown()
        _meter_provider = None

    _meter = None
    _tool_calls_counter = None
    _tool_errors_counter = None
    _tool_duration_histogram = None
    _in_flight_gauge_value = 0
    _turn_counter = None
    _cache_hits_counter = None
    _cache_misses_counter = None
    _cache_creations_counter = None
    _model_requests_counter = None
    _compaction_counter = None
    _prompt_latency_histogram = None
