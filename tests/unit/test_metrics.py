"""Unit tests for cost/latency metrics."""
from __future__ import annotations

from eval.suite import RunResult, summarize
from observability.metrics import RunMetrics, estimate_cost


def test_estimate_cost_uses_model_table():
    # 1M input + 1M output at flash rates (0.30 / 2.50).
    cost = estimate_cost(1_000_000, 1_000_000, "gemini-2.5-flash")
    assert round(cost, 2) == round(0.30 + 2.50, 2)


def test_estimate_cost_falls_back_for_unknown_model():
    assert estimate_cost(1000, 1000, "some-unknown-model") > 0


def test_run_metrics_accumulates():
    m = RunMetrics(model="gemini-2.5-flash")
    m.add_llm_usage(100, 50)
    m.add_llm_usage(200, 100)
    m.add_tool_call("run_code")
    m.add_tool_call("run_code")
    m.add_tool_call("post_request")
    assert m.prompt_tokens == 300
    assert m.completion_tokens == 150
    assert m.total_tokens == 450
    assert m.tool_call_count == 3
    assert m.tool_calls_by_name == {"run_code": 2, "post_request": 1}
    assert m.est_cost_usd > 0
    snap = m.snapshot()
    assert snap["total_tokens"] == 450


def test_summarize_computes_success_rate_and_percentiles():
    results = [
        RunResult("a", True, 100, 10, 0.0, 2, {"run_code": 2}),
        RunResult("b", True, 200, 20, 0.0, 1, {"post_request": 1}),
        RunResult("c", False, 300, 30, 0.0, 0, {}),
    ]
    report = summarize(results)
    assert report["total_tasks"] == 3
    assert report["solved"] == 2
    assert report["success_rate_pct"] == round(100 * 2 / 3, 1)
    assert report["latency_ms"]["median"] == 200
    assert report["tool_call_distribution"] == {"run_code": 2, "post_request": 1}
