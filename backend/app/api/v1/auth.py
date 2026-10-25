"""Authentication endpoint: password + TOTP -> short-lived JWT.

User records (id, role, argon2 password hash, TOTP secret) live in Postgres; the
repository is injected so this flow stays testable. Failures return a generic 401
(no user enumeration).
"""
from __future__ import annotations

from dataclasses import dataclass

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session

from pydantic import BaseModel

from app.core.config import Role, settings
from app.core.ratelimit import rate_limit_login
from app.core.security import (
    create_access_token,
    create_refresh_token,
    decode_token,
    verify_password,
    verify_totp,
)
from app.db.models import User
from app.db.session import get_session

router = APIRouter()


@dataclass
class UserRecord:
    username: str
    role: Role
    password_hash: str
    totp_secret: str


class UserRepo:
    """Loads users from Postgres for authentication."""
    def __init__(self, session: Session):
        self.session = session

    def get(self, username: str) -> UserRecord | None:
        row = self.session.query(User).filter_by(username=username).one_or_none()
        if row is None:
            return None
        return UserRecord(
            username=row.username,
            role=Role(row.role),
            password_hash=row.password_hash,
            totp_secret=row.totp_secret,
        )


def get_user_repo(session: Session = Depends(get_session)) -> UserRepo:
    return UserRepo(session)


class TokenResponse(dict):
    pass


@router.post("/login")
def login(
    form: OAuth2PasswordRequestForm = Depends(),
    repo: UserRepo = Depends(get_user_repo),
    _: None = Depends(rate_limit_login),
) -> dict:
    # OAuth2 form: username, password, and TOTP passed via `client_secret` field.
    generic = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials"
    )
    user = repo.get(form.username)
    if user is None or not verify_password(user.password_hash, form.password):
        raise generic
    if settings.require_mfa:
        code = form.client_secret or ""
        if not verify_totp(user.totp_secret, code):
            raise generic

    return {
        "access_token": create_access_token(user.username, user.role),
        "refresh_token": create_refresh_token(user.username, user.role),
        "token_type": "bearer",
        "role": user.role.value,
    }


class RefreshRequest(BaseModel):
    refresh_token: str


@router.post("/refresh")
def refresh(body: RefreshRequest) -> dict:
    """Exchange a valid refresh token for a fresh access token."""
    principal = decode_token(body.refresh_token, expected_type="refresh")
    return {
        "access_token": create_access_token(principal.subject, principal.role),
        "token_type": "bearer",
    }
