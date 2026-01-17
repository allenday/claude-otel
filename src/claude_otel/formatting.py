"""Console formatting utilities for rich output.

Provides emoji indicators, smart truncation, and formatted tool displays
for enhanced developer experience.
"""

from typing import Any


def truncate_for_display(text: str, max_length: int = 200) -> str:
    """Truncate text for display with ellipsis if needed.

    Args:
        text: Text to truncate
        max_length: Maximum length before truncation

    Returns:
        Original text or truncated version with ellipsis
    """
    if len(text) <= max_length:
        return text
    return text[:max_length] + "..."


def smart_truncate_value(value: Any, max_length: int = 150) -> str:
    """Truncate a value intelligently for display.

    Handles different types appropriately:
    - Strings: truncate with ellipsis
    - Lists: show first few items with count
    - Dicts: show truncated key-value pairs with count
    - Other types: convert to string

    Args:
        value: Value to truncate
        max_length: Maximum length for output

    Returns:
        Formatted and truncated string representation
    """
    if isinstance(value, str):
        if len(value) <= max_length:
            return value
        return value[:max_length] + "..."

    if isinstance(value, list):
        if len(value) == 0:
            return "[]"
        if len(value) <= 3:
            # Show all items if small list
            items_str = ", ".join(
                smart_truncate_value(item, max_length // 3) for item in value
            )
            if len(items_str) <= max_length:
                return f"[{items_str}]"
        # Show first few items with count
        first_items = ", ".join(
            smart_truncate_value(item, max_length // 4) for item in value[:2]
        )
        return f"[{first_items}, ... ({len(value)} items)]"

    if isinstance(value, dict):
        if len(value) == 0:
            return "{}"
        # Show first few keys
        items = []
        for i, (k, v) in enumerate(value.items()):
            if i >= 2:  # Show max 2 keys
                items.append(f"... ({len(value)} keys)")
                break
            v_str = smart_truncate_value(v, max_length // 3)
            items.append(f"{k}: {v_str}")
        return "{" + ", ".join(items) + "}"

    # For other types (int, bool, None, etc)
    return str(value)


def format_tool_input_for_console(tool_input: dict[str, Any]) -> str:
    """Format tool input for console display with smart truncation.

    Args:
        tool_input: Tool input parameters

    Returns:
        Nicely formatted, readable string showing structure
    """
    if not tool_input:
        return "{}"

    lines = []
    for key, value in tool_input.items():
        # Format value with smart truncation
        value_str = smart_truncate_value(value, max_length=200)
        lines.append(f'  "{key}": {value_str}')

    return "{\n" + ",\n".join(lines) + "\n}"


def format_tool_response_for_console(tool_response: Any) -> str:
    """Format tool response for console display with smart truncation.

    Provides useful information about what the tool returned without
    overwhelming the console.

    Args:
        tool_response: Response from tool execution

    Returns:
        Formatted response string with key information
    """
    if tool_response is None:
        return "None"

    response_type = type(tool_response).__name__

    if isinstance(tool_response, dict):
        keys = list(tool_response.keys())

        # If the whole dict is small, show it all
        full_str = str(tool_response)
        if len(full_str) <= 250:
            return f"dict with {len(keys)} key(s): {full_str}"

        # Dict is large - show structure and prioritize interesting fields
        result = f"dict with {len(keys)} key(s): {keys}\n"

        # Show interesting fields first (errors, results, content)
        interesting_keys = [
            "error",
            "stderr",
            "stdout",
            "result",
            "content",
            "message",
            "output",
        ]
        shown_keys = []
        for key in interesting_keys:
            if key in tool_response:
                value_str = smart_truncate_value(tool_response[key], max_length=300)
                result += f"   • {key}: {value_str}\n"
                shown_keys.append(key)

        # If no interesting fields found, show first few keys
        if not shown_keys:
            for key in keys[:3]:
                value_str = smart_truncate_value(tool_response[key], max_length=200)
                result += f"   • {key}: {value_str}\n"

        return result.rstrip()

    if isinstance(tool_response, list):
        count = len(tool_response)
        result = f"list with {count} item(s)"
        if count > 0:
            first_item = smart_truncate_value(tool_response[0], max_length=200)
            result += f"\n   • First item: {first_item}"
            if count > 1:
                result += f"\n   • ... and {count - 1} more"
        return result

    if isinstance(tool_response, str):
        if len(tool_response) <= 300:
            return f'"{tool_response}"'
        return f'"{tool_response[:300]}..."'

    # For other types
    return f"{response_type}: {smart_truncate_value(tool_response, max_length=300)}"


def create_tool_title(
    tool_name: str, tool_input: dict[str, Any] | None = None, max_length: int = 100
) -> str:
    """Create an informative title for a tool execution.

    Includes key arguments in the title for better DX when scanning logs.

    Args:
        tool_name: Name of the tool
        tool_input: Input arguments to the tool
        max_length: Maximum length for the title

    Returns:
        Title like "Bash - ls -l" or "Read - file_path=/path/to/file"
    """
    if not tool_input:
        return tool_name

    # Build summary of key args (max 3 params for brevity)
    summary_parts = []
    for key, value in tool_input.items():
        if len(summary_parts) >= 3:
            break

        if isinstance(value, str):
            if len(value) < 30:
                # Short string - show in quotes if it looks like a command/path
                if "/" in value or value.startswith("-") or " " in value:
                    summary_parts.append(f'"{value}"')
                else:
                    summary_parts.append(f"{key}={value}")
            else:
                # Long string - truncate
                summary_parts.append(f'{key}="{value[:30]}..."')
        elif isinstance(value, (int, bool, type(None))):
            summary_parts.append(f"{key}={value}")
        elif isinstance(value, dict):
            summary_parts.append(f"{key}={{...{len(value)}}}")
        elif isinstance(value, list):
            summary_parts.append(f"{key}=[...{len(value)}]")

    if not summary_parts:
        return tool_name

    summary = ", ".join(summary_parts)
    title = f"{tool_name} - {summary}"

    # Truncate if too long
    if len(title) > max_length:
        title = title[: max_length - 3] + "..."

    return title


def create_completion_title(
    tool_name: str, tool_response: Any, max_length: int = 100
) -> str:
    """Create an informative title for a tool completion.

    Includes key response info for better DX when scanning logs.

    Args:
        tool_name: Name of the tool
        tool_response: Response from the tool
        max_length: Maximum length for the title

    Returns:
        Title like "Bash → Success" or "Read → 1234 bytes"
    """
    if tool_response is None:
        return f"{tool_name} → None"

    # Build short response summary
    summary = None

    if isinstance(tool_response, dict):
        # Check for error first
        if "error" in tool_response and tool_response["error"]:
            error_msg = str(tool_response["error"])[:40]
            summary = f"Error: {error_msg}"
        elif "isError" in tool_response and tool_response["isError"]:
            summary = "Error"
        # Look for interesting result fields
        elif "result" in tool_response:
            result = str(tool_response["result"])[:40]
            summary = f"result={result}"
        elif "content" in tool_response:
            content = str(tool_response["content"])[:40]
            summary = f"{content}"
        elif "message" in tool_response:
            message = str(tool_response["message"])[:40]
            summary = f"{message}"
        else:
            # Just show count of keys
            summary = f"{len(tool_response)} fields"

    elif isinstance(tool_response, list):
        count = len(tool_response)
        summary = f"{count} item{'s' if count != 1 else ''}"

    elif isinstance(tool_response, str):
        if len(tool_response) < 50:
            summary = tool_response[:50]
        else:
            summary = f"{tool_response[:50]}..."

    else:
        summary = str(tool_response)[:50]

    title = f"{tool_name} → {summary}"

    # Truncate if too long
    if len(title) > max_length:
        title = title[: max_length - 3] + "..."

    return title
