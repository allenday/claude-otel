"""Unit tests for enhanced metrics functionality."""

import pytest
from unittest.mock import Mock, patch

from claude_otel import metrics


@pytest.fixture(autouse=True)
def reset_metrics():
    """Reset metrics state before each test."""
    metrics.shutdown_metrics()
    yield
    metrics.shutdown_metrics()


@pytest.fixture
def mock_meter():
    """Create a mock meter with counter/histogram creation."""
    meter = Mock()
    counter = Mock()
    histogram = Mock()
    meter.create_counter.return_value = counter
    meter.create_histogram.return_value = histogram
    return meter, counter, histogram


class TestTurnMetrics:
    """Tests for turn count metrics."""

    def test_record_turn_increments_counter(self, mock_meter):
        """Should increment turn counter with model attribute."""
        meter, counter, _ = mock_meter

        with patch.object(metrics, '_meter', meter):
            with patch.object(metrics, '_turn_counter', counter):
                metrics.record_turn("claude-opus-4")
                counter.add.assert_called_once_with(1, {"model": "claude-opus-4"})

    def test_record_turn_defaults_to_unknown_model(self, mock_meter):
        """Should use 'unknown' model when not specified."""
        meter, counter, _ = mock_meter

        with patch.object(metrics, '_meter', meter):
            with patch.object(metrics, '_turn_counter', counter):
                metrics.record_turn()
                counter.add.assert_called_once_with(1, {"model": "unknown"})

    def test_record_turn_handles_missing_meter(self):
        """Should not fail when meter is not configured."""
        with patch.object(metrics, '_meter', None):
            metrics.record_turn("claude-sonnet-4")  # Should not raise


class TestCacheMetrics:
    """Tests for cache hit/miss and creation metrics."""

    def test_cache_hit_recorded_when_read_tokens_present(self, mock_meter):
        """Should record cache hit when cache_read_tokens > 0."""
        meter, counter, _ = mock_meter

        with patch.object(metrics, '_meter', meter):
            with patch.object(metrics, '_cache_hits_counter', counter):
                with patch.object(metrics, '_cache_misses_counter', Mock()):
                    with patch.object(metrics, '_cache_creations_counter', Mock()):
                        metrics.record_cache_usage(cache_read_tokens=100, model="opus")
                        counter.add.assert_called_once_with(1, {"model": "opus"})

    def test_cache_miss_recorded_when_no_read_tokens(self, mock_meter):
        """Should record cache miss when cache_read_tokens == 0."""
        meter, _, _ = mock_meter
        miss_counter = Mock()

        with patch.object(metrics, '_meter', meter):
            with patch.object(metrics, '_cache_hits_counter', Mock()):
                with patch.object(metrics, '_cache_misses_counter', miss_counter):
                    with patch.object(metrics, '_cache_creations_counter', Mock()):
                        metrics.record_cache_usage(cache_read_tokens=0, model="sonnet")
                        miss_counter.add.assert_called_once_with(1, {"model": "sonnet"})

    def test_cache_creation_recorded_when_creation_tokens_present(self, mock_meter):
        """Should record cache creation when cache_creation_tokens > 0."""
        meter, _, _ = mock_meter
        creation_counter = Mock()

        with patch.object(metrics, '_meter', meter):
            with patch.object(metrics, '_cache_hits_counter', Mock()):
                with patch.object(metrics, '_cache_misses_counter', Mock()):
                    with patch.object(metrics, '_cache_creations_counter', creation_counter):
                        metrics.record_cache_usage(cache_creation_tokens=50, model="haiku")
                        creation_counter.add.assert_called_once_with(1, {"model": "haiku"})

    def test_no_cache_creation_when_zero_tokens(self, mock_meter):
        """Should not record cache creation when cache_creation_tokens == 0."""
        meter, _, _ = mock_meter
        creation_counter = Mock()

        with patch.object(metrics, '_meter', meter):
            with patch.object(metrics, '_cache_hits_counter', Mock()):
                with patch.object(metrics, '_cache_misses_counter', Mock()):
                    with patch.object(metrics, '_cache_creations_counter', creation_counter):
                        metrics.record_cache_usage(cache_creation_tokens=0)
                        creation_counter.add.assert_not_called()

    def test_handles_missing_meter(self):
        """Should not fail when meter is not configured."""
        with patch.object(metrics, '_meter', None):
            metrics.record_cache_usage(100, 50, "opus")  # Should not raise


class TestModelRequestMetrics:
    """Tests for model request distribution metrics."""

    def test_record_model_request_increments_counter(self, mock_meter):
        """Should increment model request counter with model attribute."""
        meter, counter, _ = mock_meter

        with patch.object(metrics, '_meter', meter):
            with patch.object(metrics, '_model_requests_counter', counter):
                metrics.record_model_request("claude-3-5-sonnet")
                counter.add.assert_called_once_with(1, {"model": "claude-3-5-sonnet"})

    def test_record_model_request_defaults_to_unknown(self, mock_meter):
        """Should use 'unknown' model when not specified."""
        meter, counter, _ = mock_meter

        with patch.object(metrics, '_meter', meter):
            with patch.object(metrics, '_model_requests_counter', counter):
                metrics.record_model_request()
                counter.add.assert_called_once_with(1, {"model": "unknown"})

    def test_handles_missing_meter(self):
        """Should not fail when meter is not configured."""
        with patch.object(metrics, '_meter', None):
            metrics.record_model_request("opus")  # Should not raise


class TestContextCompactionMetrics:
    """Tests for context compaction frequency metrics."""

    def test_record_compaction_with_trigger(self, mock_meter):
        """Should record compaction with trigger and model attributes."""
        meter, counter, _ = mock_meter

        with patch.object(metrics, '_meter', meter):
            with patch.object(metrics, '_compaction_counter', counter):
                metrics.record_context_compaction("token_limit", "sonnet")
                counter.add.assert_called_once_with(
                    1, {"trigger": "token_limit", "model": "sonnet"}
                )

    def test_record_compaction_defaults(self, mock_meter):
        """Should use default values when not specified."""
        meter, counter, _ = mock_meter

        with patch.object(metrics, '_meter', meter):
            with patch.object(metrics, '_compaction_counter', counter):
                metrics.record_context_compaction()
                counter.add.assert_called_once_with(
                    1, {"trigger": "unknown", "model": "unknown"}
                )

    def test_handles_missing_meter(self):
        """Should not fail when meter is not configured."""
        with patch.object(metrics, '_meter', None):
            metrics.record_context_compaction("user_request", "opus")  # Should not raise


class TestMetricsInstrumentation:
    """Tests for metric instrument creation."""

    def test_ensure_instruments_creates_all_metrics(self, mock_meter):
        """Should create all metric instruments on first call."""
        meter, counter, histogram = mock_meter

        with patch.object(metrics, '_meter', meter):
            # Reset all instruments to None
            metrics._tool_calls_counter = None
            metrics._tool_errors_counter = None
            metrics._tool_duration_histogram = None
            metrics._turn_counter = None
            metrics._cache_hits_counter = None
            metrics._cache_misses_counter = None
            metrics._cache_creations_counter = None
            metrics._model_requests_counter = None
            metrics._compaction_counter = None

            metrics._ensure_instruments()

            # Verify all instruments were created
            assert meter.create_counter.call_count == 8  # 8 counters
            assert meter.create_histogram.call_count == 1  # 1 histogram

            # Verify specific metric names
            counter_names = [call[1]["name"] for call in meter.create_counter.call_args_list]
            assert "claude.tool_calls_total" in counter_names
            assert "claude.tool_calls_errors_total" in counter_names
            assert "claude.turns_total" in counter_names
            assert "claude.cache_hits_total" in counter_names
            assert "claude.cache_misses_total" in counter_names
            assert "claude.cache_creations_total" in counter_names
            assert "claude.model_requests_total" in counter_names
            assert "claude.context_compactions_total" in counter_names

    def test_ensure_instruments_idempotent(self, mock_meter):
        """Should not recreate instruments if already initialized."""
        meter, counter, histogram = mock_meter

        with patch.object(metrics, '_meter', meter):
            with patch.object(metrics, '_turn_counter', counter):
                # Call twice
                metrics._ensure_instruments()
                call_count_first = meter.create_counter.call_count

                metrics._ensure_instruments()
                call_count_second = meter.create_counter.call_count

                # Should not create more instruments
                assert call_count_second == call_count_first


class TestMetricsShutdown:
    """Tests for metrics shutdown and cleanup."""

    def test_shutdown_clears_all_instruments(self):
        """Should reset all instrument references to None."""
        # Set some instruments
        metrics._tool_calls_counter = Mock()
        metrics._turn_counter = Mock()
        metrics._cache_hits_counter = Mock()

        metrics.shutdown_metrics()

        # Verify all cleared
        assert metrics._tool_calls_counter is None
        assert metrics._tool_errors_counter is None
        assert metrics._tool_duration_histogram is None
        assert metrics._turn_counter is None
        assert metrics._cache_hits_counter is None
        assert metrics._cache_misses_counter is None
        assert metrics._cache_creations_counter is None
        assert metrics._model_requests_counter is None
        assert metrics._compaction_counter is None
        assert metrics._in_flight_gauge_value == 0
