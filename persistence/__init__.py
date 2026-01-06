"""Persistence package: SQLAlchemy engine/session, ORM models, and repositories.

Runs on SQLite locally (zero setup) and on Postgres/Supabase in production by
pointing ``DATABASE_URL`` at the managed database.
"""

from .db import Base, SessionLocal, engine, get_session, init_db, session_scope
from .repository import RunRepository, UserRepository

__all__ = [
    "Base",
    "SessionLocal",
    "engine",
    "get_session",
    "init_db",
    "session_scope",
    "RunRepository",
    "UserRepository",
]
