#!/usr/bin/env python3
"""PreToolUse hook: record start time and tool input for span creation.

Receives tool invocation data via stdin JSON and stores it in a temp file
for the PostToolUse hook to retrieve and create a complete span.
"""

import json
import os
import sys
import time
import tempfile

# Use a dedicated directory for tool context files
CONTEXT_DIR = os.path.join(tempfile.gettempdir(), "claude-otel-spans")


def main():
    """Entry point for pre-tool hook."""
    try:
        # Parse input from Claude
        input_data = json.load(sys.stdin)

        tool_use_id = input_data.get("tool_use_id", "")
        if not tool_use_id:
            return  # Can't track without an ID

        # Store context for PostToolUse
        context = {
            "start_time_ns": time.time_ns(),
            "tool_name": input_data.get("tool_name", "unknown"),
            "tool_input": input_data.get("tool_input", {}),
            "session_id": input_data.get("session_id", ""),
            "cwd": input_data.get("cwd", ""),
        }

        # Ensure context directory exists
        os.makedirs(CONTEXT_DIR, exist_ok=True)

        # Write context file
        context_file = os.path.join(CONTEXT_DIR, f"{tool_use_id}.json")
        with open(context_file, "w") as f:
            json.dump(context, f)

    except Exception as e:
        # Don't block tool execution on errors
        print(f"[claude-otel] PreToolUse error: {e}", file=sys.stderr)


if __name__ == "__main__":
    main()
