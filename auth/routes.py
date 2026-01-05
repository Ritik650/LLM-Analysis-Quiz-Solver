"""
/auth routes: register, login (→ JWT), and per-user API-key management.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy.orm import Session

from persistence.db import get_session
from persistence.models import User
from persistence.repository import UserRepository

from .dependencies import get_current_user
from .security import create_access_token

router = APIRouter(prefix="/auth", tags=["auth"])


# --------------------------------------------------------------------------
# Schemas
# --------------------------------------------------------------------------
class Credentials(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    email: EmailStr


class UserResponse(BaseModel):
    id: int
    email: EmailStr


class ApiKeyCreate(BaseModel):
    name: str = Field(default="default", max_length=120)


class ApiKeyResponse(BaseModel):
    id: int
    name: str
    prefix: str
    revoked: bool


class ApiKeyCreated(ApiKeyResponse):
    # The raw key is returned exactly once, at creation time.
    api_key: str


# --------------------------------------------------------------------------
# Routes
# --------------------------------------------------------------------------
@router.post("/register", response_model=TokenResponse, status_code=201)
def register(creds: Credentials, session: Session = Depends(get_session)):
    if UserRepository.get_by_email(session, creds.email):
        raise HTTPException(status_code=409, detail="Email already registered")
    user = UserRepository.create_user(session, creds.email, creds.password)
    token = create_access_token(user.id, user.email)
    return TokenResponse(access_token=token, email=user.email)


@router.post("/login", response_model=TokenResponse)
def login(creds: Credentials, session: Session = Depends(get_session)):
    user = UserRepository.authenticate(session, creds.email, creds.password)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials"
        )
    token = create_access_token(user.id, user.email)
    return TokenResponse(access_token=token, email=user.email)


@router.get("/me", response_model=UserResponse)
def me(user: User = Depends(get_current_user)):
    return UserResponse(id=user.id, email=user.email)


@router.post("/api-keys", response_model=ApiKeyCreated, status_code=201)
def create_api_key(
    body: ApiKeyCreate,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    record, raw = UserRepository.create_api_key(session, user, body.name)
    return ApiKeyCreated(
        id=record.id,
        name=record.name,
        prefix=record.prefix,
        revoked=record.revoked,
        api_key=raw,
    )


@router.get("/api-keys", response_model=list[ApiKeyResponse])
def list_api_keys(
    user: User = Depends(get_current_user), session: Session = Depends(get_session)
):
    keys = UserRepository.list_api_keys(session, user)
    return [
        ApiKeyResponse(id=k.id, name=k.name, prefix=k.prefix, revoked=k.revoked)
        for k in keys
    ]


@router.delete("/api-keys/{key_id}", status_code=204)
def revoke_api_key(
    key_id: int,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    if not UserRepository.revoke_api_key(session, user, key_id):
        raise HTTPException(status_code=404, detail="API key not found")
    return None
