"""Backend-specific adapters for Logfire and Sentry.

This module provides auto-detection and configuration for specialized observability backends
based on environment variables. Backends are configured automatically if their credentials are
present, falling back to standard OTLP export if no backend is detected.

Supported Backends:
    - Logfire: Pydantic's observability platform with LLM-optimized UI
    - Sentry: Error monitoring and AI monitoring platform

Environment Variables:
    LOGFIRE_TOKEN: Enable Logfire backend
    SENTRY_DSN: Enable Sentry backend
    SENTRY_ENVIRONMENT: Sentry environment (default: "production")
    SENTRY_TRACES_SAMPLE_RATE: Trace sampling rate 0.0-1.0 (default: "1.0")

Priority: If multiple backends are configured, Logfire takes precedence over Sentry,
which takes precedence over standard OTLP.
"""

import logging
import os
import sys
from typing import Optional

from opentelemetry import trace
from opentelemetry.sdk.resources import Resource, SERVICE_NAME, SERVICE_NAMESPACE
from opentelemetry.sdk.trace import TracerProvider

logger = logging.getLogger(__name__)


def detect_backend() -> Optional[str]:
    """Auto-detect which backend to use based on environment variables.

    Returns:
        Backend name ('logfire', 'sentry', or None for standard OTLP)
    """
    if os.getenv("LOGFIRE_TOKEN"):
        return "logfire"
    if os.getenv("SENTRY_DSN"):
        return "sentry"
    return None


def configure_logfire(service_name: str = "claude-otel") -> TracerProvider:
    """Configure Logfire for telemetry.

    Logfire provides a rich UI optimized for LLM observability with automatic
    formatting of tool calls, prompts, and responses.

    Args:
        service_name: Service name for traces

    Returns:
        Configured TracerProvider with Logfire

    Raises:
        ValueError: If LOGFIRE_TOKEN is not set
        ImportError: If logfire package is not installed
        RuntimeError: If Logfire configuration fails
    """
    # Check token is present first
    token = os.getenv("LOGFIRE_TOKEN")
    if not token:
        raise ValueError("LOGFIRE_TOKEN environment variable is not set")

    try:
        import logfire  # type: ignore
    except ImportError as e:
        logger.error("❌ LOGFIRE_TOKEN set but logfire not installed!")
        logger.error("   Run: pip install logfire")
        raise RuntimeError(
            "Logfire token provided but logfire package not installed"
        ) from e

    try:
        # Configure Logfire with service name
        logfire.configure(
            service_name=service_name,
            send_to_logfire=True,
        )

        # Get the configured tracer provider
        provider = trace.get_tracer_provider()

        logger.info(f"✅ Logfire configured with service name: {service_name}")
        logger.info("   Note: Token validation happens on first span export")
        logger.info("   View traces at: https://logfire.pydantic.dev/")

        return provider

    except Exception as e:
        logger.exception("Failed to configure Logfire")
        raise RuntimeError("Logfire configuration failed") from e


def configure_sentry(service_name: str = "claude-otel") -> TracerProvider:
    """Configure Sentry for LLM telemetry.

    Uses Sentry's native SDK for initialization and OpenTelemetry API for
    span creation. This provides full access to Sentry's LLM monitoring UI
    while maintaining consistency with other backends.

    Args:
        service_name: Service name for traces

    Returns:
        Configured TracerProvider with Sentry integration

    Raises:
        ValueError: If SENTRY_DSN is not set
        ImportError: If sentry-sdk package is not installed
        RuntimeError: If Sentry configuration fails

    Environment Variables:
        SENTRY_DSN: Sentry project DSN (required)
        SENTRY_ENVIRONMENT: Environment name (default: "production")
        SENTRY_TRACES_SAMPLE_RATE: Trace sampling rate 0.0-1.0 (default: "1.0")
    """
    # Check DSN is present first
    dsn = os.getenv("SENTRY_DSN")
    if not dsn:
        raise ValueError("SENTRY_DSN environment variable is not set")

    try:
        import sentry_sdk  # type: ignore
        from sentry_sdk.integrations.logging import LoggingIntegration  # type: ignore
        from sentry_sdk.integrations.opentelemetry import SentrySpanProcessor  # type: ignore
    except ImportError as e:
        logger.error("❌ SENTRY_DSN set but sentry-sdk not installed!")
        logger.error("   Run: pip install sentry-sdk")
        raise RuntimeError(
            "Sentry DSN provided but sentry-sdk package not installed"
        ) from e

    try:
        # Parse configuration from environment
        environment = os.getenv("SENTRY_ENVIRONMENT", "production")
        traces_sample_rate = float(os.getenv("SENTRY_TRACES_SAMPLE_RATE", "1.0"))

        # Initialize Sentry SDK with LLM monitoring optimizations
        sentry_sdk.init(
            dsn=dsn,
            traces_sample_rate=traces_sample_rate,
            environment=environment,
            send_default_pii=False,  # Privacy: don't send PII by default
            enable_tracing=True,
            integrations=[
                LoggingIntegration(
                    level=None,  # Capture no logs by default
                    event_level=None,  # Only capture errors via spans
                ),
            ],
        )

        # Create OpenTelemetry provider with Sentry processor
        resource = Resource.create({
            SERVICE_NAME: service_name,
            SERVICE_NAMESPACE: os.environ.get("OTEL_SERVICE_NAMESPACE", "claude"),
        })
        provider = TracerProvider(resource=resource)

        # Add Sentry span processor to bridge OTEL spans to Sentry
        provider.add_span_processor(SentrySpanProcessor())

        # Set as global tracer provider
        trace.set_tracer_provider(provider)

        logger.info(f"✅ Sentry configured with service name: {service_name}")
        logger.info(f"   Environment: {environment}")
        logger.info("   Note: Traces will appear in Sentry's AI Monitoring section")

        return provider

    except ValueError as e:
        logger.error(f"Invalid Sentry configuration: {e}")
        raise
    except Exception as e:
        logger.exception("Failed to configure Sentry")
        raise RuntimeError("Sentry configuration failed") from e


def get_logfire():
    """Get the configured logfire instance.

    Returns:
        The logfire module if it's been imported, None otherwise.
        This avoids global state by checking sys.modules.
    """
    return sys.modules.get("logfire")


def get_sentry():
    """Get the configured Sentry SDK instance.

    Returns:
        The sentry_sdk module if it's been imported, None otherwise.
        This avoids global state by checking sys.modules.
    """
    return sys.modules.get("sentry_sdk")
