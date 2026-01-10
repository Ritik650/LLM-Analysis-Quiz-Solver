"""Unit tests for auth primitives: passwords, JWTs, API keys."""
from __future__ import annotations

import time

from auth.security import (
    create_access_token,
    decode_token,
    generate_api_key,
    hash_api_key,
    hash_password,
    verify_password,
)


def test_password_hash_roundtrip():
    hashed = hash_password("s3cret-pass")
    assert hashed != "s3cret-pass"
    assert verify_password("s3cret-pass", hashed)
    assert not verify_password("wrong", hashed)


def test_password_verify_handles_garbage():
    assert not verify_password("x", "not-a-real-hash")


def test_jwt_roundtrip():
    token = create_access_token(user_id=7, email="a@b.com")
    payload = decode_token(token)
    assert payload is not None
    assert payload["sub"] == "7"
    assert payload["email"] == "a@b.com"


def test_jwt_expired_is_rejected():
    token = create_access_token(user_id=1, email="a@b.com", expires_minutes=-1)
    time.sleep(0.01)
    assert decode_token(token) is None


def test_jwt_tampered_is_rejected():
    token = create_access_token(user_id=1, email="a@b.com")
    assert decode_token(token + "tamper") is None


def test_api_key_generation_and_hash():
    raw = generate_api_key()
    assert raw.startswith("qk_")
    h = hash_api_key(raw)
    assert len(h) == 64  # sha256 hex
    assert hash_api_key(raw) == h  # deterministic
    assert hash_api_key(generate_api_key()) != h  # unique keys differ
