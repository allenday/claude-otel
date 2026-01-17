"""OTEL hooks for Claude CLI tool invocations."""

from claude_otel.hooks.pre_tool import main as pre_tool_main
from claude_otel.hooks.post_tool import main as post_tool_main

__all__ = ["pre_tool_main", "post_tool_main"]
