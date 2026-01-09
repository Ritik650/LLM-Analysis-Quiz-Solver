"""
Evaluation runner / CLI.

Runs the agent against the mock quiz server and writes a success-rate report.

Usage:
    uv run python -m eval.run_eval            # full suite (FakeChatModel)
    uv run python -m eval.run_eval --smoke    # one chain (CI regression check)
    uv run python -m eval.run_eval --real     # use real Gemini (needs GOOGLE_API_KEY)

The default uses the deterministic FakeChatModel: numbers reflect the harness +
tooling pipeline, not Gemini's reasoning quality. Pass ``--real`` to measure the
actual model. Reports are written to eval/report.json and eval/report.md.
"""
from __future__ import annotations

import argparse
import json
import os
import time
import uuid
from pathlib import Path

from agent import build_app, build_llm, run_agent_instrumented
from eval.fake_llm import FakeChatModel
from eval.mock_quiz import DEFAULT_CHAINS, start_mock_quiz, stop_mock_quiz
from eval.suite import RunResult, summarize
from persistence.db import init_db, session_scope
from persistence.repository import RunRepository

_REPORT_DIR = Path(__file__).parent


def _run_one(app, base_url: str, chain: str, model: str) -> RunResult:
    run_id = str(uuid.uuid4())
    start_url = f"{base_url}/q/{chain}/1"
    with session_scope() as session:
        RunRepository.create_run(session, run_id, start_url, user_id=None)

        def persist(event):
            RunRepository.append_step(
                session, run_id, seq=event.seq, type=event.type,
                node=event.node, name=event.name, data=event.data,
            )

        outcome = run_agent_instrumented(
            start_url, run_id, app=app, persist=persist, model=model
        )
        m = outcome.metrics
        RunRepository.finalize_run(
            session, run_id,
            status="success" if outcome.success else "failed",
            success=outcome.success,
            prompt_tokens=m.prompt_tokens, completion_tokens=m.completion_tokens,
            total_tokens=m.total_tokens, est_cost_usd=m.est_cost_usd,
            tool_call_count=m.tool_call_count, final_result=outcome.result,
            error=outcome.error,
        )
    return RunResult(
        task=chain, success=outcome.success, duration_ms=m.duration_ms,
        total_tokens=m.total_tokens, est_cost_usd=m.est_cost_usd,
        tool_call_count=m.tool_call_count,
        tool_calls_by_name=dict(m.tool_calls_by_name), error=outcome.error,
    )


def run_suite(smoke: bool = False, real: bool = False) -> dict:
    init_db()
    chains = dict(DEFAULT_CHAINS)
    if smoke:
        chains = {"arith": DEFAULT_CHAINS["arith"]}

    if real:
        model = os.getenv("GEMINI_MODEL", "gemini-3-pro")
        app = build_app(build_llm(model))
    else:
        model = "fake-quiz-model"
        app = build_app(FakeChatModel())

    base_url, server = start_mock_quiz(chains)
    try:
        results = [_run_one(app, base_url, chain, model) for chain in chains]
    finally:
        stop_mock_quiz(server)

    report = summarize(results)
    report["config"] = {
        "model": model,
        "mode": "real-gemini" if real else "fake-chat-model (deterministic)",
        "generated_at": time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime()),
        "smoke": smoke,
    }
    _write_reports(report)
    return report


def _write_reports(report: dict) -> None:
    (_REPORT_DIR / "report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    (_REPORT_DIR / "report.md").write_text(_render_markdown(report), encoding="utf-8")


def _render_markdown(report: dict) -> str:
    cfg = report["config"]
    lat = report["latency_ms"]
    lines = [
        "# Eval Report",
        "",
        f"- **Mode:** {cfg['mode']}",
        f"- **Model:** `{cfg['model']}`",
        f"- **Generated:** {cfg['generated_at']}",
        "",
        "| Metric | Value |",
        "| --- | --- |",
        f"| Success rate | {report['success_rate_pct']}% ({report['solved']}/{report['total_tasks']}) |",
        f"| Median latency | {lat['median']} ms |",
        f"| p95 latency | {lat['p95']} ms |",
        f"| Avg tokens / run | {report['avg_tokens_per_run']} |",
        f"| Avg cost / run | ${report['avg_cost_per_run_usd']} |",
        "",
        "**Tool-call distribution:** "
        + ", ".join(f"`{k}`×{v}" for k, v in report["tool_call_distribution"].items()),
        "",
    ]
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the quiz-agent eval suite.")
    parser.add_argument("--smoke", action="store_true", help="Run one chain (CI check).")
    parser.add_argument("--real", action="store_true", help="Use real Gemini (needs key).")
    args = parser.parse_args()

    report = run_suite(smoke=args.smoke, real=args.real)
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
