#!/usr/bin/env python3
"""Programmatic SDK usage example.

Demonstrates embedding Claude SDK directly in your application with
full control over configuration, hooks, and telemetry.

Use this as a template for integrating Claude into larger applications
where you need fine-grained control over the SDK behavior.

Run:
    python examples/programmatic_sdk.py
"""

import asyncio
import logging
from typing import Optional

from claude_agent_sdk import ClaudeAgentOptions, ClaudeSDKClient, HookMatcher
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.resources import Resource
from rich.console import Console

from claude_otel.config import get_config
from claude_otel.exporter import setup_exporters
from claude_otel.sdk_hooks import SDKTelemetryHooks

console = Console()
logging.basicConfig(level=logging.INFO, format="[%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)


class ClaudeAgent:
    """Wrapper class for Claude SDK with OpenTelemetry instrumentation.

    This class demonstrates how to integrate Claude SDK into your application
    with full telemetry support.
    """

    def __init__(
        self,
        model: str = "sonnet",
        service_name: Optional[str] = None,
        debug: bool = False,
    ):
        """Initialize Claude agent with OTEL instrumentation.

        Args:
            model: Claude model to use (sonnet, opus, haiku)
            service_name: Override default service name
            debug: Enable debug logging
        """
        self.model = model
        self.debug = debug

        # Load configuration
        self.config = get_config()
        if service_name:
            self.config.service_name = service_name

        # Setup OTEL
        self._setup_telemetry()

        # Setup SDK client
        self._setup_client()

        logger.info(f"Initialized Claude agent: {self.model}")
        logger.info(f"Service: {self.config.service_name}")
        logger.info(f"Telemetry: {self.config.endpoint}")

    def _setup_telemetry(self):
        """Setup OpenTelemetry tracer and exporters."""
        resource = Resource.create({
            "service.name": self.config.service_name,
            "service.namespace": self.config.service_namespace,
            "model": self.model,
        })

        self.trace_provider = TracerProvider(resource=resource)
        trace.set_tracer_provider(self.trace_provider)

        setup_exporters(self.trace_provider, self.config, logger)

        self.tracer = trace.get_tracer(__name__)

    def _setup_client(self):
        """Setup Claude SDK client with hooks."""
        # Initialize telemetry hooks
        self.hooks = SDKTelemetryHooks(tracer=self.tracer)

        # Configure hook matchers
        hook_config = {
            "UserPromptSubmit": [
                HookMatcher(matcher=None, hooks=[self.hooks.on_user_prompt_submit])
            ],
            "PreToolUse": [
                HookMatcher(matcher=None, hooks=[self.hooks.on_pre_tool_use])
            ],
            "PostToolUse": [
                HookMatcher(matcher=None, hooks=[self.hooks.on_post_tool_use])
            ],
            "MessageComplete": [
                HookMatcher(matcher=None, hooks=[self.hooks.on_message_complete])
            ],
            "PreCompact": [
                HookMatcher(matcher=None, hooks=[self.hooks.on_pre_compact])
            ],
        }

        # Create SDK options
        options = ClaudeAgentOptions(
            hooks=hook_config,
            setting_sources=["user", "project", "local"],
            extra_args={"model": self.model},
            stderr=lambda line: logger.debug(f"[Claude] {line}") if self.debug else None,
        )

        # Create client
        self.client = ClaudeSDKClient(options)

    async def run(self, prompt: str) -> str:
        """Run a prompt with Claude and return the response.

        Args:
            prompt: User prompt to send to Claude

        Returns:
            Claude's response as a string
        """
        with self.tracer.start_as_current_span("claude_agent.run") as span:
            span.set_attribute("prompt", prompt[:100])  # Truncate for privacy
            span.set_attribute("model", self.model)

            try:
                result = await self.client.run(prompt)
                span.set_attribute("success", True)
                return result

            except Exception as e:
                span.set_attribute("success", False)
                span.set_attribute("error", str(e))
                logger.error(f"Error running prompt: {e}")
                raise

    async def run_batch(self, prompts: list[str]) -> list[str]:
        """Run multiple prompts in sequence.

        Args:
            prompts: List of prompts to run

        Returns:
            List of responses
        """
        with self.tracer.start_as_current_span("claude_agent.run_batch") as span:
            span.set_attribute("batch_size", len(prompts))

            results = []
            for i, prompt in enumerate(prompts):
                logger.info(f"Processing prompt {i+1}/{len(prompts)}")
                result = await self.run(prompt)
                results.append(result)

            return results

    def shutdown(self):
        """Flush and shutdown telemetry."""
        self.trace_provider.force_flush()
        self.trace_provider.shutdown()
        logger.info("Claude agent shutdown complete")


async def main():
    """Example application using programmatic Claude SDK integration."""

    console.print(Panel(
        "[bold cyan]Programmatic SDK Integration Example[/bold cyan]\n\n"
        "This example shows how to embed Claude SDK in your application\n"
        "with full OpenTelemetry instrumentation.",
        border_style="cyan"
    ))

    # Create Claude agent instance
    agent = ClaudeAgent(
        model="sonnet",
        service_name="my-claude-app",
        debug=True,
    )

    try:
        # Example 1: Single prompt
        console.print("\n[bold]Example 1: Single Prompt[/bold]")
        response = await agent.run("What is 2+2? Be concise.")
        console.print(f"Response: {response}\n")

        # Example 2: Batch processing
        console.print("[bold]Example 2: Batch Processing[/bold]")
        prompts = [
            "What is the capital of France?",
            "What is the capital of Germany?",
            "What is the capital of Italy?",
        ]

        responses = await agent.run_batch(prompts)
        for i, (prompt, response) in enumerate(zip(prompts, responses), 1):
            console.print(f"{i}. {prompt}")
            console.print(f"   → {response}\n")

        # Example 3: Access session state
        console.print("[bold]Example 3: Session Metrics[/bold]")
        if agent.hooks.session_state:
            state = agent.hooks.session_state
            console.print(f"Turns: {state.get('turns', 0)}")
            console.print(f"Total tokens: {state.get('total_input_tokens', 0) + state.get('total_output_tokens', 0)}")
            if "tools_used" in state:
                console.print(f"Tools used: {', '.join(state['tools_used'])}")

    finally:
        # Cleanup
        agent.shutdown()

    console.print("\n[green]✓ Telemetry exported to collector[/green]")
    console.print("[dim]Check your OTLP collector for traces and metrics[/dim]")


if __name__ == "__main__":
    asyncio.run(main())
