# MessageComplete Hook Investigation

## Issue
Token counts showing "0 in, 0 out" despite successful tool executions in SDK-based sessions, particularly in ralph-loop contexts.

## Root Cause
**MessageComplete is NOT a supported hook in claude-agent-sdk.**

### Supported Hooks
The claude-agent-sdk (v0.1.20) only supports these hooks:
- `UserPromptSubmit` - Called when user submits a prompt
- `PreToolUse` - Called before tool execution
- `PostToolUse` - Called after tool execution
- `PreCompact` - Called before context compaction
- `Stop` - Called when session ends (provides transcript_path)
- `SubagentStop` - Called when subagent stops

### Evidence
Inspection of the SDK type hints shows:
```python
# From claude_agent_sdk.types
hooks: dict[
    Literal['PreToolUse']
    | Literal['PostToolUse']
    | Literal['UserPromptSubmit']
    | Literal['Stop']
    | Literal['SubagentStop']
    | Literal['PreCompact'],
    list[HookMatcher]
] | None
```

No `MessageComplete` hook type exists in the SDK's type system.

### Impact
Our code was registering `MessageComplete` in the hook configuration, which was silently ignored by the SDK. This meant:
- `on_message_complete()` was never called
- Token usage was never extracted from messages
- Metrics always showed 0 tokens despite successful sessions

## Solution

### Implementation
Replace `MessageComplete` hook registration with `Stop` hook, which provides access to the session transcript containing full token usage data.

#### Changes Made

1. **New Hook: `on_stop()` in `SDKTelemetryHooks`** (sdk_hooks.py:470)
   ```python
   async def on_stop(self, input_data: dict[str, Any], tool_use_id: Optional[str], ctx: Any):
       # Parse transcript_path from input_data
       # Extract token counts from transcript JSON
       # Update metrics and span attributes
   ```

2. **Updated Hook Registration** (sdk_runner.py:39-60)
   ```python
   hook_config = {
       "UserPromptSubmit": [...],
       "PreToolUse": [...],
       "PostToolUse": [...],
       "Stop": [HookMatcher(matcher=None, hooks=[hooks.on_stop])],  # Changed from MessageComplete
       "PreCompact": [...],
   }
   ```

3. **Enhanced Metrics Function** (metrics.py:251)
   ```python
   def record_turn(model: str = "unknown", count: int = 1):
       # Support recording multiple turns at once
   ```

### How Stop Hook Works

1. SDK calls `on_stop()` when session ends
2. Hook receives `input_data` containing:
   - `session_id` - Unique session identifier
   - `transcript_path` - Path to JSON transcript file
   - `cwd` - Working directory
3. Parse transcript JSON to extract usage data:
   ```json
   {
     "messages": [
       {
         "role": "assistant",
         "usage": {
           "input_tokens": 100,
           "output_tokens": 50,
           "cache_read_input_tokens": 0,
           "cache_creation_input_tokens": 0
         }
       }
     ]
   }
   ```
4. Accumulate token counts across all messages
5. Update span attributes and record metrics

### Testing

Comprehensive test suite added in `tests/test_stop_hook.py`:

- ✅ Extract token counts from transcript
- ✅ Update span attributes correctly
- ✅ Handle missing transcript_path gracefully
- ✅ Handle nonexistent transcript file
- ✅ Handle malformed JSON
- ✅ Support both dict and list transcript formats
- ✅ Record metrics correctly

All 7 tests passing.

## Backward Compatibility

The `on_message_complete()` method remains in `SDKTelemetryHooks` for:
- Programmatic usage where users manually call hooks
- Existing unit tests that exercise the method directly
- Potential future SDK versions that may add MessageComplete support

**Note added to docstring:** Clearly documents that this hook is not called by the SDK.

## Related Issues

This same bug exists in `claude_telemetry` reference implementation, which also registers `MessageComplete` hook. Both codebases were affected by the silent hook registration failure.

## Verification

To verify the fix works:

1. Run SDK session with `CLAUDE_OTEL_DEBUG=1`:
   ```bash
   CLAUDE_OTEL_DEBUG=1 claude-otel --use-sdk "test prompt"
   ```

2. Check for debug output:
   ```
   [claude-otel-sdk] Extracted from transcript: 1234 in, 567 out, 1 turns
   ```

3. Verify span attributes include token counts:
   - `gen_ai.usage.input_tokens`
   - `gen_ai.usage.output_tokens`
   - `tokens.cache_read`
   - `tokens.cache_creation`
   - `turns`

## Future Considerations

If a future version of `claude-agent-sdk` adds native `MessageComplete` hook support:

1. We can switch back to using it for per-turn token tracking
2. Keep `Stop` hook as fallback/verification
3. The `on_message_complete()` method is already implemented and ready

For now, `Stop` hook provides the complete session-level token data we need.
