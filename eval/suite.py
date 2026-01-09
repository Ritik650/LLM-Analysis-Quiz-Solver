"""
Suite definition + metric aggregation.

A "task" is one quiz chain from the mock server. ``summarize`` turns a list of
per-run results into the headline metrics the JD asks for: success rate,
median + p95 latency, avg tokens/run, avg cost/run, and the tool-call
distribution.
"""
from __future__ import annotations

import statistics
from dataclasses import dataclass, field


@dataclass
class RunResult:
    task: str
    success: bool
    duration_ms: int
    total_tokens: int
    est_cost_usd: float
    tool_call_count: int
    tool_calls_by_name: dict[str, int] = field(default_factory=dict)
    error: str | None = None


def _percentile(values: list[float], pct: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    k = (len(ordered) - 1) * pct
    lo = int(k)
    hi = min(lo + 1, len(ordered) - 1)
    return ordered[lo] + (ordered[hi] - ordered[lo]) * (k - lo)


def summarize(results: list[RunResult]) -> dict:
    total = len(results)
    solved = sum(1 for r in results if r.success)
    latencies = [r.duration_ms for r in results]
    tokens = [r.total_tokens for r in results]
    costs = [r.est_cost_usd for r in results]

    tool_dist: dict[str, int] = {}
    for r in results:
        for name, count in r.tool_calls_by_name.items():
            tool_dist[name] = tool_dist.get(name, 0) + count

    return {
        "total_tasks": total,
        "solved": solved,
        "success_rate_pct": round(100 * solved / total, 1) if total else 0.0,
        "latency_ms": {
            "median": round(statistics.median(latencies), 1) if latencies else 0.0,
            "p95": round(_percentile(latencies, 0.95), 1) if latencies else 0.0,
            "max": max(latencies) if latencies else 0,
        },
        "avg_tokens_per_run": round(statistics.mean(tokens), 1) if tokens else 0.0,
        "avg_cost_per_run_usd": round(statistics.mean(costs), 6) if costs else 0.0,
        "tool_call_distribution": tool_dist,
        "per_task": [
            {
                "task": r.task,
                "success": r.success,
                "duration_ms": r.duration_ms,
                "total_tokens": r.total_tokens,
                "tool_call_count": r.tool_call_count,
                "error": r.error,
            }
            for r in results
        ],
    }
