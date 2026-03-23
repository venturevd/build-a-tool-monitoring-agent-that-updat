# Tool Monitor

A monitoring agent for tool executions that detects edge cases, tracks health metrics, and suggests spec updates.

## Features

- **Tool Health Tracking**: Monitor success rates, execution times, and error patterns
- **Edge Case Detection**: Automatically detect:
  - Slow executions (configurable thresholds)
  - High error rates
  - Infinite loops
  - Unknown tool references
  - Trace-level errors
- **Spec Updates**: Load and update tool specifications dynamically
- **Reporting**: Generate comprehensive health reports and edge case summaries
- **Suggestions**: Get actionable recommendations for improving tool specs

## Installation Requirements

This tool depends on the `agentool` package (agent-tool-spec reference implementation).

```bash
# Install agentool from local path
cd ~/agents/artifacts/agent-tool-spec
pip install -e . --break-system-packages
```

Or use git installation:
```bash
pip install git+https://github.com/venturevd/agent-tool-spec --break-system-packages
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
    "critical_edge_cases": 3
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

## Edge Case Thresholds

Configure detection thresholds in `ToolMonitor.EDGE_CASE_THRESHOLDS`:

```python
EDGE_CASE_THRESHOLDS = {
    "duration_warning_ms": 5000,
    "duration_critical_ms": 30000,
    "error_rate_warning": 0.1,
    "error_rate_critical": 0.3,
    "loop_detection_window": 3,
    "min_executions_for_pattern": 5,
}
```

## Architecture

The monitor follows a simple pipeline:

1. Load tool specifications (optional but recommended)
2. Process ReasoningTraces from files or stdin
3. Track per-tool health metrics
4. Detect edge cases during trace analysis
5. Generate reports on demand

## Example Workflow

```bash
# 1. Collect traces from your agents
# (Traces are JSON files in agentool ReasoningTrace format)

# 2. Run monitoring
python3 main.py --specs my_tools.json monitor traces/

# 3. Review the health report and edge cases
# 4. Use suggest-updates to get recommendations
python3 main.py --specs my_tools.json suggest-updates

# 5. Update your tool specs based on findings
```

## License

Part of the Schemaon agent framework.
