"""
Low-level auth primitives: password hashing, JWT tokens, and API keys.

- Passwords are hashed with bcrypt (per-hash salt, slow by design).
- Access tokens are signed JWTs (HS256) carrying the user id + email + expiry.
- API keys are random tokens shown to the user exactly once; only their
  SHA-256 hash is persisted, so a database leak does not expose usable keys.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import secrets

import bcrypt
import jwt

from config import get_settings

_API_KEY_PREFIX = "qk_"  # "quiz key" — makes leaked keys easy to grep/rotate


# --------------------------------------------------------------------------
# Passwords
# --------------------------------------------------------------------------
def hash_password(password: str) -> str:
    # bcrypt only considers the first 72 bytes; encode + truncate explicitly so
    # long passphrases behave predictably instead of raising.
    pw = password.encode("utf-8")[:72]
    return bcrypt.hashpw(pw, bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode("utf-8")[:72], hashed.encode("utf-8"))
    except (ValueError, TypeError):
        return False


# --------------------------------------------------------------------------
# JWT access tokens
# --------------------------------------------------------------------------
def create_access_token(
    user_id: int, email: str, expires_minutes: int | None = None
) -> str:
    settings = get_settings()
    minutes = expires_minutes if expires_minutes is not None else settings.jwt_expire_minutes
    now = dt.datetime.now(dt.timezone.utc)
    payload = {
        "sub": str(user_id),
        "email": email,
        "iat": now,
        "exp": now + dt.timedelta(minutes=minutes),
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def decode_token(token: str) -> dict | None:
    """Return the JWT payload, or ``None`` if the token is invalid/expired."""
    settings = get_settings()
    try:
        return jwt.decode(
            token, settings.jwt_secret, algorithms=[settings.jwt_algorithm]
        )
    except jwt.PyJWTError:
        return None


# --------------------------------------------------------------------------
# API keys
# --------------------------------------------------------------------------
def generate_api_key() -> str:
    """Return a fresh raw API key. Show it once — it is never recoverable."""
    return _API_KEY_PREFIX + secrets.token_urlsafe(32)


def hash_api_key(raw_key: str) -> str:
    """Deterministic SHA-256 so lookups are an indexed equality check."""
    return hashlib.sha256(raw_key.encode("utf-8")).hexdigest()
