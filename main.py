#!/usr/bin/env python3
"""
Tool Monitor — monitoring agent for tool execution health and edge cases.

This agent monitors tools that agents build/run by analyzing ReasoningTraces.
It detects edge cases, tracks tool health metrics, and can receive spec updates.

Implements Agent Tool Interop Spec v0.1 primitives inline for self-containment.
"""

import argparse
import json
import sys
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum, StrEnum
from pathlib import Path
from typing import Any, Optional


# ── Agent Tool Interop Spec v0.1 Primitives (stdlib only) ───────────────────────

class StepType(StrEnum):
    """Type of a trace step."""
    REASONING = "reasoning"
    TOOL_CALL = "tool_call"
    TOOL_RESULT = "tool_result"
    HANDOFF = "handoff"
    MEMORY_READ = "memory_read"
    MEMORY_WRITE = "memory_write"


class TraceStatus(StrEnum):
    """Overall execution status."""
    SUCCESS = "success"
    ERROR = "error"
    LOOP_DETECTED = "loop_detected"
    CONTEXT_OVERFLOW = "context_overflow"
    TIMEOUT = "timeout"
    REFUSAL = "refusal"
    IN_PROGRESS = "in_progress"


@dataclass
class ToolCall:
    """A record of an agent invoking a tool."""
    name: str
    arguments: dict[str, Any]
    id: str = field(default_factory=lambda: f"call_{uuid.uuid4().hex[:8]}")
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "arguments": self.arguments,
            "timestamp": self.timestamp.isoformat(),
        }


@dataclass
class ToolResult:
    """The result of a tool call."""
    call_id: str
    output: Any
    error: str | None = None
    duration_ms: int = 0
    cost_tokens: int = 0

    @property
    def success(self) -> bool:
        return self.error is None

    def to_dict(self) -> dict:
        return {
            "call_id": self.call_id,
            "output": self.output,
            "error": self.error,
            "duration_ms": self.duration_ms,
            "cost_tokens": self.cost_tokens,
        }


@dataclass
class TraceStep:
    """One step in a reasoning trace."""
    type: StepType
    step_id: str = field(default_factory=lambda: f"step_{uuid.uuid4().hex[:6]}")
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    # reasoning step
    content: str | None = None
    context_tokens: int = 0

    # tool_call step
    tool_call: ToolCall | None = None

    # tool_result step
    tool_result: ToolResult | None = None

    # handoff step
    to_agent: str | None = None
    handoff_message: str | None = None

    # memory steps
    query: str | None = None
    results: list | None = None
    memory_key: str | None = None
    memory_content: str | None = None

    # catch-all extra
    extra: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        d: dict[str, Any] = {
            "step_id": self.step_id,
            "type": self.type.value,
            "timestamp": self.timestamp.isoformat(),
        }
        if self.content is not None:
            d["content"] = self.content
        if self.context_tokens:
            d["context_tokens"] = self.context_tokens
        if self.tool_call is not None:
            d["tool_call"] = self.tool_call.to_dict()
        if self.tool_result is not None:
            d["tool_result"] = self.tool_result.to_dict()
        if self.to_agent:
            d["to_agent"] = self.to_agent
            d["message"] = self.handoff_message
        if self.query:
            d["query"] = self.query
        if self.results is not None:
            d["results"] = self.results
        if self.memory_key:
            d["key"] = self.memory_key
        if self.memory_content:
            d["content"] = self.memory_content
        d.update(self.extra)
        return d


@dataclass
class TraceMetrics:
    """Aggregated metrics for a trace."""
    total_tokens: int = 0
    total_cost_usd: float = 0.0
    total_duration_ms: int = 0
    step_count: int = 0
    tool_call_count: int = 0

    def to_dict(self) -> dict:
        return {
            "total_tokens": self.total_tokens,
            "total_cost_usd": self.total_cost_usd,
            "total_duration_ms": self.total_duration_ms,
            "step_count": self.step_count,
            "tool_call_count": self.tool_call_count,
        }


@dataclass
class ReasoningTrace:
    """Full execution record for one agent invocation."""
    agent_id: str
    input: str
    trace_id: str = field(default_factory=lambda: f"tr_{uuid.uuid4().hex[:6]}")
    session_id: str | None = None
    started_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    finished_at: datetime | None = None
    output: str | None = None
    status: TraceStatus = TraceStatus.IN_PROGRESS
    steps: list[TraceStep] = field(default_factory=list)
    metrics: TraceMetrics = field(default_factory=TraceMetrics)
    metadata: dict[str, Any] = field(default_factory=dict)

    # Builder helpers
    def add_reasoning(self, content: str, context_tokens: int = 0) -> TraceStep:
        step = TraceStep(
            type=StepType.REASONING,
            content=content,
            context_tokens=context_tokens,
        )
        self.steps.append(step)
        self.metrics.step_count += 1
        return step

    def add_tool_call(self, call: ToolCall) -> TraceStep:
        step = TraceStep(type=StepType.TOOL_CALL, tool_call=call)
        self.steps.append(step)
        self.metrics.step_count += 1
        self.metrics.tool_call_count += 1
        return step

    def add_tool_result(self, result: ToolResult) -> TraceStep:
        step = TraceStep(type=StepType.TOOL_RESULT, tool_result=result)
        self.steps.append(step)
        self.metrics.step_count += 1
        if result.duration_ms:
            self.metrics.total_duration_ms += result.duration_ms
        return step

    def finish(
        self,
        output: str,
        status: TraceStatus = TraceStatus.SUCCESS,
        total_tokens: int = 0,
        total_cost_usd: float = 0.0,
    ) -> None:
        self.output = output
        self.status = status
        self.finished_at = datetime.now(timezone.utc)
        if total_tokens:
            self.metrics.total_tokens = total_tokens
        if total_cost_usd:
            self.metrics.total_cost_usd = total_cost_usd

    def to_dict(self) -> dict:
        return {
            "trace_id": self.trace_id,
            "agent_id": self.agent_id,
            "session_id": self.session_id,
            "started_at": self.started_at.isoformat(),
            "finished_at": self.finished_at.isoformat() if self.finished_at else None,
            "input": self.input,
            "output": self.output,
            "status": self.status.value,
            "steps": [s.to_dict() for s in self.steps],
            "metrics": self.metrics.to_dict(),
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "ReasoningTrace":
        """Rebuild a trace from a dict (JSON deserialization)."""
        trace = cls(
            trace_id=d.get("trace_id", f"tr_{uuid.uuid4().hex[:6]}"),
            agent_id=d["agent_id"],
            input=d["input"],
            session_id=d.get("session_id"),
            started_at=datetime.fromisoformat(d["started_at"]) if isinstance(d["started_at"], str) else d["started_at"],
            status=TraceStatus(d.get("status", "in_progress")),
            metadata=d.get("metadata", {}),
        )

        if d.get("finished_at"):
            trace.finished_at = datetime.fromisoformat(d["finished_at"]) if isinstance(d["finished_at"], str) else d["finished_at"]

        # deserialize steps
        for step_dict in d.get("steps", []):
            step_type = StepType(step_dict["type"])
            step = TraceStep(type=step_type, step_id=step_dict.get("step_id", f"step_{uuid.uuid4().hex[:6]}"))

            if isinstance(step_dict.get("timestamp"), str):
                step.timestamp = datetime.fromisoformat(step_dict["timestamp"])

            if step_type == StepType.REASONING:
                step.content = step_dict.get("content")
                step.context_tokens = step_dict.get("context_tokens", 0)
            elif step_type == StepType.TOOL_CALL:
                call_dict = step_dict.get("tool_call", {})
                step.tool_call = ToolCall(
                    name=call_dict.get("name", ""),
                    arguments=call_dict.get("arguments", {}),
                    id=call_dict.get("id", f"call_{uuid.uuid4().hex[:8]}"),
                )
            elif step_type == StepType.TOOL_RESULT:
                result_dict = step_dict.get("tool_result", {})
                step.tool_result = ToolResult(
                    call_id=result_dict.get("call_id", ""),
                    output=result_dict.get("output"),
                    error=result_dict.get("error"),
                    duration_ms=result_dict.get("duration_ms", 0),
                    cost_tokens=result_dict.get("cost_tokens", 0),
                )

            trace.steps.append(step)

        # rebuild metrics
        total_dur = 0
        tool_calls = 0
        for step in trace.steps:
            if step.tool_result and step.tool_result.duration_ms:
                total_dur += step.tool_result.duration_ms
            if step.tool_call:
                tool_calls += 1
        trace.metrics.total_duration_ms = total_dur
        trace.metrics.tool_call_count = tool_calls
        trace.metrics.step_count = len(trace.steps)

        return trace

    def tool_calls(self) -> list[ToolCall]:
        return [s.tool_call for s in self.steps if s.tool_call is not None]

    def reasoning_steps(self) -> list[str]:
        return [s.content for s in self.steps if s.type == StepType.REASONING and s.content]

    def has_loop(self, window: int = 3) -> bool:
        """Detect if the agent repeated the same tool call multiple times in a row."""
        calls = [s.tool_call.name for s in self.steps if s.tool_call]
        if len(calls) < window:
            return False
        for i in range(len(calls) - window + 1):
            if len(set(calls[i:i+window])) == 1:
                return True
        return False


class ToolHealth:
    """Health metrics for a monitored tool."""

    def __init__(self, name: str):
        self.name = name
        self.total_executions = 0
        self.success_count = 0
        self.error_count = 0
        self.timeout_count = 0
        self.loop_count = 0
        self.total_duration_ms = 0
        self.failure_patterns: list[str] = []
        self.edge_cases_detected: list[dict[str, Any]] = []
        self.last_execution: Optional[datetime] = None
        self.last_error: Optional[str] = None

    @property
    def success_rate(self) -> float:
        if self.total_executions == 0:
            return 0.0
        return self.success_count / self.total_executions

    @property
    def avg_duration_ms(self) -> float:
        if self.total_executions == 0:
            return 0.0
        return self.total_duration_ms / self.total_executions

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "total_executions": self.total_executions,
            "success_count": self.success_count,
            "error_count": self.error_count,
            "timeout_count": self.timeout_count,
            "loop_count": self.loop_count,
            "success_rate": round(self.success_rate, 3),
            "avg_duration_ms": round(self.avg_duration_ms, 2),
            "total_duration_ms": self.total_duration_ms,
            "failure_patterns": self.failure_patterns,
            "edge_cases_detected": self.edge_cases_detected,
            "last_execution": self.last_execution.isoformat() if self.last_execution else None,
            "last_error": self.last_error,
            "health_status": self._assess_health(),
        }

    def _assess_health(self) -> str:
        """Assess overall tool health."""
        if self.total_executions == 0:
            return "no_data"
        if self.success_rate >= 0.95:
            return "healthy"
        if self.success_rate >= 0.8:
            return "degraded"
        return "unhealthy"


class ToolMonitor:
    """
    Monitors tool executions and detects edge cases.

    Features:
    - Track execution health metrics per tool
    - Detect common edge cases (timeouts, loops, errors)
    - Identify failure patterns
    - Support for dynamic spec updates
    - Generate health reports
    """

    EDGE_CASE_THRESHOLDS = {
        "duration_warning_ms": 5000,
        "duration_critical_ms": 30000,
        "error_rate_warning": 0.1,
        "error_rate_critical": 0.3,
        "loop_detection_window": 3,
        "min_executions_for_pattern": 5,
    }

    def __init__(self):
        self.tools: dict[str, ToolHealth] = {}
        self.specs: dict[str, dict[str, Any]] = {}
        self.raw_traces: list[dict[str, Any]] = []

    def load_spec(self, name: str, spec_dict: dict[str, Any]) -> None:
        """Load or update a tool specification."""
        self.specs[name] = spec_dict

    def load_spec_from_file(self, filepath: Path) -> None:
        """Load tool specifications from a JSON file."""
        with open(filepath) as f:
            data = json.load(f)
            if isinstance(data, dict):
                for name, spec in data.items():
                    self.load_spec(name, spec)
            elif isinstance(data, list):
                for spec in data:
                    name = spec.get("name")
                    if name:
                        self.load_spec(name, spec)

    def process_trace(self, trace: ReasoningTrace) -> list[dict[str, Any]]:
        """
        Process a reasoning trace and detect edge cases.

        Returns list of detected edge cases.
        """
        edge_cases: list[dict[str, Any]] = []
        tool_name = trace.agent_id

        # Initialize tool health tracking
        if tool_name not in self.tools:
            self.tools[tool_name] = ToolHealth(tool_name)

        health = self.tools[tool_name]

        # Update execution count
        health.total_executions += 1
        health.last_execution = datetime.now(timezone.utc)

        # Check trace status
        if trace.status == TraceStatus.ERROR:
            health.error_count += 1
            edge_cases.append({
                "type": "trace_error",
                "tool": tool_name,
                "trace_id": trace.trace_id,
                "message": f"Trace ended with error status: {trace.status.value}",
                "severity": "high",
            })

        # Analyze tool calls within trace
        for step in trace.steps:
            if step.type == StepType.TOOL_RESULT and step.tool_result:
                result: ToolResult = step.tool_result
                if result.error:
                    health.error_count += 1
                    health.last_error = result.error
                    edge_cases.append({
                        "type": "tool_error",
                        "tool": tool_name,
                        "call_id": result.call_id,
                        "error": result.error,
                        "severity": "high",
                    })

                # Detect slow execution
                if result.duration_ms and result.duration_ms > self.EDGE_CASE_THRESHOLDS["duration_critical_ms"]:
                    edge_cases.append({
                        "type": "slow_execution",
                        "tool": tool_name,
                        "duration_ms": result.duration_ms,
                        "threshold_ms": self.EDGE_CASE_THRESHOLDS["duration_critical_ms"],
                        "severity": "medium" if result.duration_ms < self.EDGE_CASE_THRESHOLDS["duration_warning_ms"] else "high",
                    })

            if step.type == StepType.TOOL_CALL and step.tool_call:
                call = step.tool_call
                if call.name not in self.specs:
                    edge_cases.append({
                        "type": "unknown_tool",
                        "tool": call.name,
                        "trace_id": trace.trace_id,
                        "message": f"Tool '{call.name}' not in loaded specs",
                        "severity": "low",
                    })

        # Check for loops
        if trace.has_loop(window=self.EDGE_CASE_THRESHOLDS["loop_detection_window"]):
            health.loop_count += 1
            edge_cases.append({
                "type": "loop_detected",
                "tool": tool_name,
                "trace_id": trace.trace_id,
                "window": self.EDGE_CASE_THRESHOLDS["loop_detection_window"],
                "severity": "high",
            })

        # Track duration
        if trace.metrics.total_duration_ms:
            health.total_duration_ms += trace.metrics.total_duration_ms

        # Record edge cases
        health.edge_cases_detected.extend(edge_cases)

        # Assess if successful
        if trace.status == TraceStatus.SUCCESS:
            health.success_count += 1

        return edge_cases

    def process_trace_file(self, filepath: Path) -> list[dict[str, Any]]:
        """Process a trace from a JSON file."""
        with open(filepath) as f:
            data = json.load(f)
        trace = ReasoningTrace.from_dict(data)
        return self.process_trace(trace)

    def get_health_report(self) -> dict[str, Any]:
        """Generate a comprehensive health report for all monitored tools."""
        report = {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "total_tools_monitored": len(self.tools),
            "total_executions": sum(h.total_executions for h in self.tools.values()),
            "tools": {},
            "summary": {
                "healthy_tools": 0,
                "degraded_tools": 0,
                "unhealthy_tools": 0,
                "critical_edge_cases": 0,
            }
        }

        for name, health in sorted(self.tools.items(), key=lambda x: x[1].total_executions, reverse=True):
            health_dict = health.to_dict()
            report["tools"][name] = health_dict
            if health_dict["health_status"] == "healthy":
                report["summary"]["healthy_tools"] += 1
            elif health_dict["health_status"] == "degraded":
                report["summary"]["degraded_tools"] += 1
            else:
                report["summary"]["unhealthy_tools"] += 1

        return report

    def get_edge_case_summary(self) -> dict[str, Any]:
        """Summarize all detected edge cases."""
        all_edge_cases: list[dict[str, Any]] = []
        for health in self.tools.values():
            all_edge_cases.extend(health.edge_cases_detected)

        by_type: dict[str, int] = {}
        by_severity: dict[str, int] = {}
        for case in all_edge_cases:
            by_type[case["type"]] = by_type.get(case["type"], 0) + 1
            by_severity[case["severity"]] = by_severity.get(case["severity"], 0) + 1

        return {
            "total_edge_cases": len(all_edge_cases),
            "by_type": by_type,
            "by_severity": by_severity,
            "critical_cases": [c for c in all_edge_cases if c["severity"] == "high"],
        }

    def suggest_spec_updates(self) -> list[dict[str, Any]]:
        """
        Analyze patterns and suggest spec updates to handle edge cases.

        Returns a list of updates that could improve tool resilience.
        """
        suggestions: list[dict[str, Any]] = []

        for name, health in self.tools.items():
            # Check error rate
            if health.total_executions >= self.EDGE_CASE_THRESHOLDS["min_executions_for_pattern"]:
                error_rate = health.error_count / health.total_executions if health.total_executions > 0 else 0

                if error_rate >= self.EDGE_CASE_THRESHOLDS["error_rate_critical"]:
                    suggestions.append({
                        "tool": name,
                        "priority": "critical",
                        "issue": f"High error rate: {error_rate:.1%}",
                        "suggestion": "Add comprehensive error handling and retry logic",
                    })

                # Check for slow execution patterns
                if health.avg_duration_ms > 5000:
                    suggestions.append({
                        "tool": name,
                        "priority": "medium",
                        "issue": f"Slow average execution: {health.avg_duration_ms:.0f}ms",
                        "suggestion": "Consider adding timeout parameters or async processing",
                    })

        return suggestions


def main():
    parser = argparse.ArgumentParser(
        description="Tool Monitor — monitor tool executions and detect edge cases",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Monitor a directory of traces
  python3 main.py monitor traces/

  # Load tool specs and generate health report
  python3 main.py --specs tools.json report

  # Interactive monitoring (read traces from stdin)
  python3 main.py --specs tools.json monitor-stdin

  # Suggest spec updates based on patterns
  python3 main.py --specs tools.json suggest-updates
        """
    )

    parser.add_argument(
        "--specs", "-s",
        type=Path,
        help="Path to tool specs JSON file (loads before operation)"
    )

    subparsers = parser.add_subparsers(dest="command", help="Command to run")

    # Monitor command
    monitor_parser = subparsers.add_parser(
        "monitor",
        help="Monitor traces from a directory or file"
    )
    monitor_parser.add_argument(
        "path",
        type=Path,
        help="Directory or file containing trace JSON(s)"
    )

    # Report command
    report_parser = subparsers.add_parser(
        "report",
        help="Generate health report (requires --specs)"
    )

    # Suggest updates command
    suggest_parser = subparsers.add_parser(
        "suggest-updates",
        help="Suggest spec updates based on detected patterns (requires --specs)"
    )

    # Simulate command for testing
    sim_parser = subparsers.add_parser(
        "simulate",
        help="Simulate monitoring with sample data"
    )

    args = parser.parse_args()

    # Create monitor
    monitor = ToolMonitor()

    # Load specs if provided
    if args.specs and args.specs.exists():
        print(f"Loading specs from {args.specs}", file=sys.stderr)
        monitor.load_spec_from_file(args.specs)
    else:
        # Load built-in sample specs for demonstration
        _load_sample_specs(monitor)
        print("Loaded sample specs (use --specs to load real specs)", file=sys.stderr)

    # Execute command
    if args.command == "monitor":
        _cmd_monitor(monitor, args.path)
    elif args.command == "report":
        report = monitor.get_health_report()
        print(json.dumps(report, indent=2))
    elif args.command == "suggest-updates":
        suggestions = monitor.suggest_spec_updates()
        print(json.dumps({"suggestions": suggestions}, indent=2))
    elif args.command == "simulate":
        _cmd_simulate(monitor)
    else:
        parser.print_help()


def _load_sample_specs(monitor: ToolMonitor) -> None:
    """Load sample tool specs for demonstration."""
    sample_specs = {
        "search_web": {
            "name": "search_web",
            "description": "Search the web",
            "parameters": {
                "type": "object",
                "properties": {"query": {"type": "string"}},
                "required": ["query"],
            },
        },
        "read_file": {
            "name": "read_file",
            "description": "Read a file",
            "parameters": {
                "type": "object",
                "properties": {"path": {"type": "string"}},
                "required": ["path"],
            },
        },
    }
    for name, spec in sample_specs.items():
        monitor.load_spec(name, spec)


def _cmd_monitor(monitor: ToolMonitor, path: Path) -> None:
    """Handle monitor command."""
    if not path.exists():
        print(f"Error: Path does not exist: {path}", file=sys.stderr)
        sys.exit(1)

    trace_files: list[Path] = []
    if path.is_file():
        trace_files = [path]
    else:
        trace_files = sorted(path.glob("*.json"))

    if not trace_files:
        print(f"No trace JSON files found in {path}", file=sys.stderr)
        sys.exit(1)

    print(f"Processing {len(trace_files)} trace file(s)...", file=sys.stderr)
    all_edge_cases: list[dict[str, Any]] = []

    for trace_file in trace_files:
        try:
            cases = monitor.process_trace_file(trace_file)
            all_edge_cases.extend(cases)
        except Exception as e:
            print(f"Error processing {trace_file}: {e}", file=sys.stderr)

    # Output summary
    print(f"\nProcessed {len(trace_files)} trace(s)", file=sys.stderr)
    print(f"Edge cases detected: {len(all_edge_cases)}", file=sys.stderr)
    if all_edge_cases:
        print("\nTop edge cases:", file=sys.stderr)
        for case in all_edge_cases[:5]:
            print(f"  - [{case['severity']}] {case['type']}: {case.get('message', case.get('error', 'unknown'))}", file=sys.stderr)

    # Generate report
    report = monitor.get_health_report()
    print("\n" + json.dumps(report, indent=2))


def _cmd_simulate(monitor: ToolMonitor) -> None:
    """Simulate monitoring with sample traces."""
    print("Running simulation with sample traces...", file=sys.stderr)

    # Simulate some traces
    traces_data = [
        {
            "trace_id": "sim_001",
            "agent_id": "search_web",
            "input": "search for Python tutorials",
            "status": "success",
            "started_at": "2025-01-01T12:00:00Z",
            "finished_at": "2025-01-01T12:00:01Z",
            "metrics": {"total_duration_ms": 1000, "tool_call_count": 1},
            "steps": [
                {
                    "step_id": "s1",
                    "type": "reasoning",
                    "content": "I'll search for Python tutorials",
                    "timestamp": "2025-01-01T12:00:00Z",
                },
                {
                    "step_id": "s2",
                    "type": "tool_call",
                    "tool_call": {
                        "id": "call_001",
                        "name": "search_web",
                        "arguments": {"query": "Python tutorials"},
                        "timestamp": "2025-01-01T12:00:00.5Z",
                    },
                    "timestamp": "2025-01-01T12:00:00.5Z",
                },
                {
                    "step_id": "s3",
                    "type": "tool_result",
                    "tool_result": {
                        "call_id": "call_001",
                        "output": ["result1", "result2"],
                        "duration_ms": 500,
                        "success": True,
                    },
                    "timestamp": "2025-01-01T12:00:01Z",
                },
            ],
        },
        {
            "trace_id": "sim_002",
            "agent_id": "search_web",
            "input": "find documentation",
            "status": "success",
            "started_at": "2025-01-01T12:01:00Z",
            "finished_at": "2025-01-01T12:01:06Z",
            "metrics": {"total_duration_ms": 6000, "tool_call_count": 2},
            "steps": [
                {
                    "step_id": "t1",
                    "type": "tool_call",
                    "tool_call": {
                        "id": "call_002",
                        "name": "search_web",
                        "arguments": {"query": "docs"},
                        "timestamp": "2025-01-01T12:01:00Z",
                    },
                    "timestamp": "2025-01-01T12:01:00Z",
                },
                {
                    "step_id": "t2",
                    "type": "tool_result",
                    "tool_result": {
                        "call_id": "call_002",
                        "output": ["doc1"],
                        "duration_ms": 3000,
                    },
                    "timestamp": "2025-01-01T12:01:03Z",
                },
                {
                    "step_id": "t3",
                    "type": "tool_call",
                    "tool_call": {
                        "id": "call_003",
                        "name": "search_web",
                        "arguments": {"query": "Python documentation"},
                        "timestamp": "2025-01-01T12:01:03.1Z",
                    },
                    "timestamp": "2025-01-01T12:01:03.1Z",
                },
                {
                    "step_id": "t4",
                    "type": "tool_result",
                    "tool_result": {
                        "call_id": "call_003",
                        "output": ["doc2"],
                        "duration_ms": 3000,
                    },
                    "timestamp": "2025-01-01T12:01:06Z",
                },
            ],
        },
        {
            "trace_id": "sim_003",
            "agent_id": "read_file",
            "input": "read config.json",
            "status": "error",
            "started_at": "2025-01-01T12:02:00Z",
            "finished_at": "2025-01-01T12:02:00Z",
            "metrics": {"total_duration_ms": 0, "tool_call_count": 0},
            "steps": [],
        },
        {
            "trace_id": "sim_004",
            "agent_id": "unknown_tool",
            "input": "use missing tool",
            "status": "success",
            "started_at": "2025-01-01T12:03:00Z",
            "finished_at": "2025-01-01T12:03:01Z",
            "metrics": {"total_duration_ms": 1000, "tool_call_count": 1},
            "steps": [
                {
                    "step_id": "x1",
                    "type": "tool_call",
                    "tool_call": {
                        "id": "call_004",
                        "name": "nonexistent_tool",
                        "arguments": {"arg": "value"},
                        "timestamp": "2025-01-01T12:03:00Z",
                    },
                    "timestamp": "2025-01-01T12:03:00Z",
                },
            ],
        },
    ]

    for data in traces_data:
        trace = ReasoningTrace.from_dict(data)
        monitor.process_trace(trace)

    # Generate reports
    print("\nSimulation complete!", file=sys.stderr)
    print("\n=== Health Report ===", file=sys.stderr)
    report = monitor.get_health_report()
    print(json.dumps(report, indent=2), file=sys.stderr)

    print("\n=== Edge Case Summary ===", file=sys.stderr)
    edge_summary = monitor.get_edge_case_summary()
    print(json.dumps(edge_summary, indent=2), file=sys.stderr)

    print("\n=== Suggested Spec Updates ===", file=sys.stderr)
    suggestions = monitor.suggest_spec_updates()
    print(json.dumps({"suggestions": suggestions}, indent=2), file=sys.stderr)


if __name__ == "__main__":
    main()
