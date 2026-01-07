"""
Per-run metrics: token accounting, estimated cost, latency, tool-call count,
plus a structured-JSON logger.

Prices are USD per 1,000,000 tokens and are **estimates** — Gemini pricing
changes and free-tier usage is $0. They exist to give the dashboard a
ballpark cost story, not an invoice. Override any of them via env if needed.
"""
from __future__ import annotations

import json
import logging
import sys
import time
from dataclasses import dataclass, field

# model-substring -> (input_per_1M, output_per_1M) in USD
PRICING: dict[str, tuple[float, float]] = {
    "gemini-3-pro": (2.00, 12.00),      # estimate — official pricing TBD
    "gemini-2.5-pro": (1.25, 10.00),
    "gemini-2.5-flash": (0.30, 2.50),
    "gemini-2.0-flash": (0.10, 0.40),
    "gemini-1.5-pro": (1.25, 5.00),
    "gemini-1.5-flash": (0.075, 0.30),
}
_DEFAULT_PRICE = (0.30, 2.50)  # fall back to a flash-tier estimate


def _rate_for(model: str) -> tuple[float, float]:
    model = (model or "").lower()
    for key, price in PRICING.items():
        if key in model:
            return price
    return _DEFAULT_PRICE


def estimate_cost(prompt_tokens: int, completion_tokens: int, model: str) -> float:
    in_rate, out_rate = _rate_for(model)
    cost = (prompt_tokens / 1_000_000) * in_rate + (completion_tokens / 1_000_000) * out_rate
    return round(cost, 6)


@dataclass
class RunMetrics:
    """Mutable accumulator updated by the callback handler during a run."""

    model: str = ""
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    tool_call_count: int = 0
    llm_call_count: int = 0
    tool_calls_by_name: dict[str, int] = field(default_factory=dict)
    started_at: float = field(default_factory=time.time)
    finished_at: float | None = None

    def add_llm_usage(self, prompt: int, completion: int, total: int | None = None) -> None:
        self.llm_call_count += 1
        self.prompt_tokens += prompt
        self.completion_tokens += completion
        self.total_tokens += total if total is not None else (prompt + completion)

    def add_tool_call(self, name: str) -> None:
        self.tool_call_count += 1
        self.tool_calls_by_name[name] = self.tool_calls_by_name.get(name, 0) + 1

    @property
    def est_cost_usd(self) -> float:
        return estimate_cost(self.prompt_tokens, self.completion_tokens, self.model)

    @property
    def duration_ms(self) -> int:
        end = self.finished_at if self.finished_at is not None else time.time()
        return int((end - self.started_at) * 1000)

    def finish(self) -> None:
        self.finished_at = time.time()

    def snapshot(self) -> dict:
        return {
            "model": self.model,
            "prompt_tokens": self.prompt_tokens,
            "completion_tokens": self.completion_tokens,
            "total_tokens": self.total_tokens,
            "llm_call_count": self.llm_call_count,
            "tool_call_count": self.tool_call_count,
            "tool_calls_by_name": dict(self.tool_calls_by_name),
            "est_cost_usd": self.est_cost_usd,
            "duration_ms": self.duration_ms,
        }


class _JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "ts": time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime(record.created)),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
        }
        if isinstance(getattr(record, "extra_fields", None), dict):
            payload.update(record.extra_fields)
        return json.dumps(payload, default=str)


def get_json_logger(name: str = "agent") -> logging.Logger:
    """A logger that emits one JSON object per line to stdout."""
    logger = logging.getLogger(name)
    if not any(getattr(h, "_json", False) for h in logger.handlers):
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(_JsonFormatter())
        handler._json = True  # type: ignore[attr-defined]
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)
        logger.propagate = False
    return logger


def log_json(logger: logging.Logger, msg: str, **fields) -> None:
    logger.info(msg, extra={"extra_fields": fields})
