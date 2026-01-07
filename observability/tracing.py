"""
Optional LangSmith tracing.

LangChain auto-exports traces when ``LANGCHAIN_TRACING_V2=true`` and
``LANGCHAIN_API_KEY`` are present in the environment — no code change is needed
at call sites. This helper just validates the config, sets a sane default
project name, and reports status, so the feature is discoverable and never a
hard dependency (the app runs fine with tracing off).
"""
from __future__ import annotations

import os

from config import get_settings

from .metrics import get_json_logger, log_json

_logger = get_json_logger("observability")


def configure_tracing() -> bool:
    """Return True if LangSmith tracing is active."""
    settings = get_settings()
    if not settings.langsmith_enabled:
        log_json(_logger, "langsmith tracing disabled", enabled=False)
        return False
    if not os.getenv("LANGCHAIN_API_KEY"):
        log_json(
            _logger,
            "LANGCHAIN_TRACING_V2 is set but LANGCHAIN_API_KEY is missing; tracing off",
            enabled=False,
        )
        return False
    os.environ.setdefault("LANGCHAIN_PROJECT", "quiz-solver-agent")
    log_json(
        _logger,
        "langsmith tracing enabled",
        enabled=True,
        project=os.environ["LANGCHAIN_PROJECT"],
    )
    return True
