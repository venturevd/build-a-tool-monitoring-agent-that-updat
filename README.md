# Tool Monitor

A monitoring agent for tool executions that detects edge cases, tracks health metrics, and suggests spec updates.

## Features

- **Tool Health Tracking**: Monitor success rates, execution times, and error patterns
- **Edge Case Detection**: Automatically detect:
  - Slow executions (configurable thresholds)
  - High error rates
  - Infinite loops (repeated tool calls)
  - Unknown tool references
  - Trace-level errors
- **Spec Updates**: Load and update tool specifications dynamically
- **Reporting**: Generate comprehensive health reports and edge case summaries
- **Suggestions**: Get actionable recommendations for improving tool specs

## Installation

This tool uses only Python standard library - no external dependencies required.

```bash
# Clone or navigate to this directory
# No installation needed - just run directly
python3 main.py --help
```

## Usage

### Basic Help

```bash
python3 main.py --help
```

### Monitor a Directory of Traces

```bash
python3 main.py monitor traces/
```

### Monitor a Single Trace File

```bash
python3 main.py monitor trace.json
```

### Generate Health Report

```bash
python3 main.py --specs tools.json report
```

### Suggest Spec Updates

```bash
python3 main.py --specs tools.json suggest-updates
```

### Run Simulation (Demo)

```bash
python3 main.py simulate
```

## Tool Specification Format

The monitor expects tool specs in JSON format. Two formats are supported:

**Dictionary format (mapping name to spec):**
```json
{
  "search_web": {
    "name": "search_web",
    "description": "Search the web",
    "parameters": {
      "type": "object",
      "properties": {"query": {"type": "string"}},
      "required": ["query"]
    }
  }
}
```

**List format:**
```json
[
  {
    "name": "search_web",
    "description": "Search the web",
    "parameters": {...}
  }
]
```

Tool specifications are optional but recommended for detecting references to unknown tools.

## Reasoning Trace Format

The monitor accepts traces in the **Agent Tool Interop Spec v0.1** format. Fields are interpreted as follows:

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `agent_id` | string | Recommended | Name/identifier of the tool/agent. Default: "unknown_agent" |
| `input` | string | Recommended | The input to the agent. Default: "" |
| `started_at` | ISO 8601 | Recommended | Timestamp when execution started. Default: current time |
| `status` | string | Recommended | One of "success", "error", "in_progress", "timeout", "refusal", "context_overflow", "loop_detected". Default: "in_progress" |
| `steps` | array | Optional | Array of trace steps (tool_call, tool_result, reasoning, etc.) |
| `metrics` | object | Optional | Aggregated metrics including `total_duration_ms`, `total_tokens`, `tool_call_count` |
| `trace_id` | string | Optional | Unique trace identifier |
| `finished_at` | ISO 8601 | Optional | Timestamp when execution finished |

**Graceful handling**: Missing fields are filled with sensible defaults. Malformed data is skipped rather than causing crashes.

### Trace Step Format

Each step in `steps` array should have:
- `type`: "tool_call", "tool_result", "reasoning", "handoff", "memory_read", "memory_write"
- `timestamp`: ISO 8601 timestamp
- For `tool_call`: includes `tool_call` object with `name`, `arguments`, `id`
- For `tool_result`: includes `tool_result` object with `call_id`, `output`, `error`, `duration_ms`

## Output Formats

### Health Report
```json
{
  "generated_at": "2025-01-01T12:00:00Z",
  "total_tools_monitored": 2,
  "total_executions": 100,
  "summary": {
    "healthy_tools": 1,
    "degraded_tools": 1,
    "unhealthy_tools": 0,
    "no_data_tools": 0
  },
  "tools": {
    "search_web": {
      "name": "search_web",
      "total_executions": 75,
      "success_count": 70,
      "error_count": 5,
      "success_rate": 0.933,
      "avg_duration_ms": 1250.5,
      "health_status": "healthy",
      "edge_cases_detected": [...]
    }
  }
}
```

### Edge Case Summary
```json
{
  "total_edge_cases": 10,
  "by_type": {"slow_execution": 4, "tool_error": 3, "loop_detected": 2, "unknown_tool": 1},
  "by_severity": {"high": 5, "medium": 3, "low": 2},
  "critical_cases": [...]
}
```

### Suggested Updates
```json
{
  "suggestions": [
    {
      "tool": "search_web",
      "priority": "medium",
      "issue": "Slow average execution: 8000ms",
      "suggestion": "Consider adding timeout parameters or async processing"
    }
  ]
}
```

## Health Status Calculation

Health status is determined by multiple factors in priority order:
1. **unhealthy**: Any critical edge cases detected (high severity)
2. **healthy**: Success rate >= 95% AND no critical edge cases
3. **degraded**: Success rate >= 60% (but < 95%)
4. **unhealthy**: Success rate < 60%
5. **no_data**: Tool has no recorded executions

Edge case severities:
- **high**: `trace_error`, `tool_error`, `slow_execution` (over critical threshold), `loop_detected`
- **medium**: `slow_execution` (over warning threshold but under critical)
- **low**: `unknown_tool`

## Edge Case Thresholds

Configure detection thresholds in `ToolMonitor.EDGE_CASE_THRESHOLDS`:

```python
EDGE_CASE_THRESHOLDS = {
    "duration_warning_ms": 5000,        # >5s = medium severity
    "duration_critical_ms": 30000,      # >30s = high severity
    "error_rate_warning": 0.1,          # 10% error rate threshold
    "error_rate_critical": 0.3,         # 30% error rate threshold
    "loop_detection_window": 3,         # Same tool 3+ times consecutively
    "min_executions_for_pattern": 5,    # Minimum executions before pattern analysis
}
```

## Architecture

The monitor follows a simple pipeline:

1. Load tool specifications (optional but recommended for unknown tool detection)
2. Process ReasoningTraces from files or directory
3. Track per-tool health metrics
4. Detect edge cases during trace analysis
5. Generate reports on demand

## Example Workflow

```bash
# 1. Collect traces from your agents
# (Traces are JSON files, one per agent execution)

# 2. Run monitoring
python3 main.py --specs my_tools.json monitor traces/

# 3. Review the health report and edge cases
# 4. Use suggest-updates to get recommendations
python3 main.py --specs my_tools.json suggest-updates

# 5. Update your tool specs based on findings
```

## Edge Cases Detected

| Type | Severity | Description |
|------|----------|-------------|
| `trace_error` | high | Trace ended with error status |
| `tool_error` | high | A tool call returned an error |
| `slow_execution` | high | Tool execution exceeded critical duration threshold (30s) |
| `slow_execution` | medium | Tool execution exceeded warning threshold (5s) |
| `loop_detected` | high | Same tool called repeatedly (possible infinite loop) |
| `unknown_tool` | low | Tool not found in loaded specs; agent may need updated spec list |

## Error Handling

- **Missing trace fields**: Filled with sensible defaults (unknown_agent, "", current time, in_progress)
- **Invalid JSON**: Warning printed, file skipped
- **Missing specs file**: Warning printed, sample specs used
- **Directory with no traces**: Error with helpful message
- **Malformed step data**: Skipped rather than crashing

## Notes

- This tool is designed to be run periodically as part of agent observability
- Trace data can be streamed to stdin for real-time monitoring
- All code uses Python standard library only (no external dependencies)

## License

Part of the Schemaon agent framework.
