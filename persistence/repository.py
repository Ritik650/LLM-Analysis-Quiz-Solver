"""
Repositories: the only place that reads/writes ORM models.

Every method takes an explicit ``Session`` so the same code works for a
request-scoped session (FastAPI dependency) and the agent's worker-thread
session (``session_scope``).
"""
from __future__ import annotations

import datetime as dt

from sqlalchemy import select
from sqlalchemy.orm import Session

from auth.security import generate_api_key, hash_api_key, hash_password, verify_password

from .models import ApiKey, Run, Step, User


def _utcnow() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


class UserRepository:
    @staticmethod
    def create_user(session: Session, email: str, password: str) -> User:
        user = User(email=email.lower().strip(), hashed_password=hash_password(password))
        session.add(user)
        session.commit()
        session.refresh(user)
        return user

    @staticmethod
    def get_by_email(session: Session, email: str) -> User | None:
        return session.scalar(select(User).where(User.email == email.lower().strip()))

    @staticmethod
    def get_by_id(session: Session, user_id: int) -> User | None:
        return session.get(User, user_id)

    @staticmethod
    def authenticate(session: Session, email: str, password: str) -> User | None:
        user = UserRepository.get_by_email(session, email)
        if user and verify_password(password, user.hashed_password):
            return user
        return None

    # --- API keys ------------------------------------------------------
    @staticmethod
    def create_api_key(session: Session, user: User, name: str = "default") -> tuple[ApiKey, str]:
        """Return the persisted record **and** the raw key (shown once)."""
        raw = generate_api_key()
        record = ApiKey(
            user_id=user.id,
            name=name or "default",
            hashed_key=hash_api_key(raw),
            prefix=raw[:11],  # "qk_" + 8 chars
        )
        session.add(record)
        session.commit()
        session.refresh(record)
        return record, raw

    @staticmethod
    def list_api_keys(session: Session, user: User) -> list[ApiKey]:
        return list(
            session.scalars(
                select(ApiKey).where(ApiKey.user_id == user.id).order_by(ApiKey.id)
            )
        )

    @staticmethod
    def revoke_api_key(session: Session, user: User, key_id: int) -> bool:
        key = session.get(ApiKey, key_id)
        if not key or key.user_id != user.id:
            return False
        key.revoked = True
        session.commit()
        return True

    @staticmethod
    def get_user_by_api_key(session: Session, raw_key: str) -> User | None:
        hashed = hash_api_key(raw_key)
        key = session.scalar(
            select(ApiKey).where(ApiKey.hashed_key == hashed, ApiKey.revoked.is_(False))
        )
        return key.user if key else None


class RunRepository:
    @staticmethod
    def create_run(session: Session, run_id: str, url: str, user_id: int | None) -> Run:
        run = Run(id=run_id, url=url, user_id=user_id, status="running")
        session.add(run)
        session.commit()
        session.refresh(run)
        return run

    @staticmethod
    def append_step(
        session: Session,
        run_id: str,
        seq: int,
        type: str,
        node: str | None = None,
        name: str | None = None,
        data: dict | None = None,
    ) -> Step:
        step = Step(
            run_id=run_id, seq=seq, type=type, node=node, name=name, data=data, ts=_utcnow()
        )
        session.add(step)
        session.commit()
        return step

    @staticmethod
    def finalize_run(
        session: Session,
        run_id: str,
        *,
        status: str,
        success: bool | None,
        prompt_tokens: int = 0,
        completion_tokens: int = 0,
        total_tokens: int = 0,
        est_cost_usd: float = 0.0,
        tool_call_count: int = 0,
        final_result: dict | None = None,
        error: str | None = None,
    ) -> Run | None:
        run = session.get(Run, run_id)
        if not run:
            return None
        run.status = status
        run.success = success
        run.finished_at = _utcnow()
        started = run.started_at
        if started is not None:
            if started.tzinfo is None:
                started = started.replace(tzinfo=dt.timezone.utc)
            run.duration_ms = int((run.finished_at - started).total_seconds() * 1000)
        run.prompt_tokens = prompt_tokens
        run.completion_tokens = completion_tokens
        run.total_tokens = total_tokens
        run.est_cost_usd = est_cost_usd
        run.tool_call_count = tool_call_count
        run.final_result = final_result
        run.error = error
        session.commit()
        session.refresh(run)
        return run

    @staticmethod
    def get_run(session: Session, run_id: str, user_id: int | None = None) -> Run | None:
        run = session.get(Run, run_id)
        if run is None:
            return None
        if user_id is not None and run.user_id != user_id:
            return None
        return run

    @staticmethod
    def list_runs(
        session: Session, user_id: int | None, limit: int = 50, offset: int = 0
    ) -> list[Run]:
        stmt = select(Run).order_by(Run.started_at.desc()).limit(limit).offset(offset)
        if user_id is not None:
            stmt = stmt.where(Run.user_id == user_id)
        return list(session.scalars(stmt))
