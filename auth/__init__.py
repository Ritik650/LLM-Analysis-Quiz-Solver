"""Authentication package: JWT issue/verify, password + API-key hashing,
FastAPI dependencies, and the /auth routes."""

from .security import (
    create_access_token,
    decode_token,
    generate_api_key,
    hash_api_key,
    hash_password,
    verify_password,
)

__all__ = [
    "create_access_token",
    "decode_token",
    "generate_api_key",
    "hash_api_key",
    "hash_password",
    "verify_password",
]
