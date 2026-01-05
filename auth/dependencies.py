"""
FastAPI auth dependencies.

``get_current_user`` accepts EITHER:
  * ``Authorization: Bearer <jwt>``  — for the dashboard (login flow), or
  * ``X-API-Key: qk_...``            — for programmatic/API access.

``get_user_from_query_token`` exists because ``EventSource`` (the browser SSE
client) cannot set custom headers, so the stream endpoint reads the JWT/API key
from a ``?token=`` query parameter instead.
"""
from __future__ import annotations

from fastapi import Depends, Header, HTTPException, Query, status
from sqlalchemy.orm import Session

from persistence.db import get_session
from persistence.models import User
from persistence.repository import UserRepository

from .security import decode_token

_UNAUTH = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED,
    detail="Not authenticated",
    headers={"WWW-Authenticate": "Bearer"},
)


def _resolve_user(session: Session, token: str | None, api_key: str | None) -> User | None:
    """Shared resolution logic for both header- and query-based auth."""
    if token:
        payload = decode_token(token)
        if payload and payload.get("sub"):
            user = UserRepository.get_by_id(session, int(payload["sub"]))
            if user:
                return user
    if api_key:
        user = UserRepository.get_user_by_api_key(session, api_key)
        if user:
            return user
    return None


def get_current_user(
    authorization: str | None = Header(default=None),
    x_api_key: str | None = Header(default=None),
    session: Session = Depends(get_session),
) -> User:
    token = None
    if authorization and authorization.lower().startswith("bearer "):
        token = authorization[7:].strip()
    user = _resolve_user(session, token, x_api_key)
    if user is None:
        raise _UNAUTH
    return user


def get_user_from_query_token(
    token: str | None = Query(default=None),
    session: Session = Depends(get_session),
) -> User:
    """Auth for SSE: the token (JWT or API key) arrives as ?token=..."""
    user = _resolve_user(session, token, token)
    if user is None:
        raise _UNAUTH
    return user
