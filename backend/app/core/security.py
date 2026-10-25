"""Authentication & authorization primitives.

- Passwords: argon2id (never store plaintext / fast hashes).
- Tokens: short-lived JWT carrying subject + role.
- MFA: TOTP, required for analysts (law-enforcement access).
- RBAC: role hierarchy enforced server-side on every protected endpoint.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer

from app.core.config import Role, settings

# Higher number = more privilege. require_role checks the caller meets the minimum.
_ROLE_RANK = {Role.ANALYST: 1, Role.SUPERVISOR: 2, Role.ADMIN: 3}

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login")


# --- passwords ---------------------------------------------------------------
def hash_password(plain: str) -> str:
    from argon2 import PasswordHasher

    return PasswordHasher().hash(plain)


def verify_password(hashed: str, plain: str) -> bool:
    from argon2 import PasswordHasher
    from argon2.exceptions import VerifyMismatchError

    try:
        return PasswordHasher().verify(hashed, plain)
    except VerifyMismatchError:
        return False


# --- MFA (TOTP) --------------------------------------------------------------
def verify_totp(secret: str, code: str) -> bool:
    import pyotp

    return pyotp.TOTP(secret).verify(code, valid_window=1)


# --- tokens ------------------------------------------------------------------
@dataclass
class Principal:
    subject: str
    role: Role


def _encode(subject: str, role: Role, token_type: str, ttl_minutes: int) -> str:
    from jose import jwt

    now = datetime.now(timezone.utc)
    claims = {
        "sub": subject,
        "role": role.value,
        "type": token_type,
        "iat": now,
        "exp": now + timedelta(minutes=ttl_minutes),
    }
    return jwt.encode(claims, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def create_access_token(subject: str, role: Role) -> str:
    return _encode(subject, role, "access", settings.access_token_ttl_minutes)


def create_refresh_token(subject: str, role: Role) -> str:
    return _encode(subject, role, "refresh", settings.refresh_token_ttl_minutes)


def decode_token(token: str, expected_type: str = "access") -> Principal:
    from jose import JWTError, jwt

    try:
        payload = jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
        if payload.get("type") != expected_type:
            raise ValueError("wrong token type")
        return Principal(subject=payload["sub"], role=Role(payload["role"]))
    except (JWTError, KeyError, ValueError) as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired token"
        ) from exc


# --- dependencies ------------------------------------------------------------
def get_current_principal(token: str = Depends(oauth2_scheme)) -> Principal:
    return decode_token(token, expected_type="access")


def require_role(minimum: Role):
    """Dependency factory: caller must hold `minimum` or higher."""
    def _guard(principal: Principal = Depends(get_current_principal)) -> Principal:
        if _ROLE_RANK[principal.role] < _ROLE_RANK[minimum]:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Requires role >= {minimum.value}",
            )
        return principal
    return _guard
