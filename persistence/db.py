"""
Database engine, session factory, and schema bootstrap.

The engine is chosen from ``DATABASE_URL``:
  * ``sqlite:///./data/runs.db`` (default) — no external service needed.
  * ``postgresql+psycopg2://...`` — Supabase / any Postgres in production.

SQLite needs ``check_same_thread=False`` because the agent writes ``Step`` rows
from a worker thread (FastAPI runs the sync background task in a threadpool)
while the request thread reads them.
"""
from __future__ import annotations

import os
from contextlib import contextmanager
from typing import Iterator

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from config import get_settings


class Base(DeclarativeBase):
    pass


def _make_engine():
    url = get_settings().database_url
    connect_args: dict = {}
    if url.startswith("sqlite"):
        connect_args["check_same_thread"] = False
        # Ensure the parent directory (e.g. ./data) exists for file-based DBs.
        if url.startswith("sqlite:///") and not url.startswith("sqlite:///:memory:"):
            path = url.replace("sqlite:///", "", 1)
            parent = os.path.dirname(path)
            if parent:
                os.makedirs(parent, exist_ok=True)
    return create_engine(url, connect_args=connect_args, future=True)


engine = _make_engine()
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def init_db() -> None:
    """Create all tables. Import models here so they register on ``Base``."""
    from . import models  # noqa: F401  (registers mappers)

    Base.metadata.create_all(bind=engine)


@contextmanager
def session_scope() -> Iterator[Session]:
    """Transactional session for use outside request handlers (agent thread)."""
    session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def get_session() -> Iterator[Session]:
    """FastAPI dependency yielding a request-scoped session."""
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()
