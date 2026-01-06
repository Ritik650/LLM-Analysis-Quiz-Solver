"""
ORM models: users, API keys, runs, and per-run step traces.

``Run`` captures one quiz-solving invocation end to end (input URL, timing,
token + cost totals, success flag, final result). ``Step`` is the append-only
trace — one row per agent event (llm call, tool call, node transition) — which
powers both the persisted history and the live SSE replay.
"""
from __future__ import annotations

import datetime as dt

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base


def _utcnow() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    email: Mapped[str] = mapped_column(String(320), unique=True, index=True)
    hashed_password: Mapped[str] = mapped_column(String(255))
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=_utcnow)

    api_keys: Mapped[list["ApiKey"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )
    runs: Mapped[list["Run"]] = relationship(back_populates="user")


class ApiKey(Base):
    __tablename__ = "api_keys"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    name: Mapped[str] = mapped_column(String(120), default="default")
    # Only the SHA-256 hash is stored; the raw key is shown once at creation.
    hashed_key: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    # Non-secret prefix kept for display ("qk_abcd…") so users can tell keys apart.
    prefix: Mapped[str] = mapped_column(String(16))
    revoked: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=_utcnow)

    user: Mapped["User"] = relationship(back_populates="api_keys")


class Run(Base):
    __tablename__ = "runs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id"), nullable=True, index=True
    )
    url: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(20), default="running", index=True)
    success: Mapped[bool | None] = mapped_column(Boolean, nullable=True)

    started_at: Mapped[dt.datetime] = mapped_column(DateTime, default=_utcnow)
    finished_at: Mapped[dt.datetime | None] = mapped_column(DateTime, nullable=True)
    duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)

    prompt_tokens: Mapped[int] = mapped_column(Integer, default=0)
    completion_tokens: Mapped[int] = mapped_column(Integer, default=0)
    total_tokens: Mapped[int] = mapped_column(Integer, default=0)
    est_cost_usd: Mapped[float] = mapped_column(Float, default=0.0)
    tool_call_count: Mapped[int] = mapped_column(Integer, default=0)

    final_result: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)

    user: Mapped["User | None"] = relationship(back_populates="runs")
    steps: Mapped[list["Step"]] = relationship(
        back_populates="run",
        cascade="all, delete-orphan",
        order_by="Step.seq",
    )


class Step(Base):
    __tablename__ = "steps"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    run_id: Mapped[str] = mapped_column(ForeignKey("runs.id"), index=True)
    seq: Mapped[int] = mapped_column(Integer)
    ts: Mapped[dt.datetime] = mapped_column(DateTime, default=_utcnow)
    type: Mapped[str] = mapped_column(String(40))  # llm | tool | node | error | final
    node: Mapped[str | None] = mapped_column(String(60), nullable=True)
    name: Mapped[str | None] = mapped_column(String(120), nullable=True)
    data: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    run: Mapped["Run"] = relationship(back_populates="steps")
