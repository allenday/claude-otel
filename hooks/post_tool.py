#!/usr/bin/env python3
"""PostToolUse hook - thin wrapper for backward compatibility.

DEPRECATED: Use `claude-otel-post-tool` command instead (installed via pip).
This file is kept for backward compatibility with existing configurations.
"""

import sys
import os

# Add src to path so we can import the package
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from claude_otel.hooks.post_tool import main

if __name__ == "__main__":
    main()
