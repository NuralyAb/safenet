import secrets

import pyotp
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.config import Role
from app.core.security import (
    Principal,
    create_access_token,
    decode_token,
    hash_password,
    require_role,
)
from app.db.models import Base, User
from app.db.session import get_session
from app.main import app

LOGIN = "/api/v1/auth/login"
# Generated per run — no hardcoded literal (secret-scan gate). Tests only need
# the create-then-login values to match, not a fixed string.
PASSWORD = secrets.token_urlsafe(16)


@pytest.fixture
def client_and_secret():
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    TestingSession = sessionmaker(bind=engine, expire_on_commit=False)
    secret = pyotp.random_base32()
    with TestingSession() as s:
        s.add(User(username="analyst-1", role=Role.ANALYST.value,
                   password_hash=hash_password(PASSWORD), totp_secret=secret))
        s.commit()

    def override():
        s = TestingSession()
        try:
            yield s
        finally:
            s.close()

    from app.core.ratelimit import login_limiter
    login_limiter._hits.clear()   # isolate the shared limiter between tests

    app.dependency_overrides[get_session] = override
    # No `with` -> lifespan/startup is not triggered (no datastore connections in unit tests).
    yield TestClient(app), secret
    app.dependency_overrides.clear()


def _login(client, secret, password=PASSWORD, code=None):
    code = code if code is not None else pyotp.TOTP(secret).now()
    return client.post(LOGIN, data={
        "username": "analyst-1", "password": password, "client_secret": code,
    })


def test_login_success_returns_token(client_and_secret):
    client, secret = client_and_secret
    r = _login(client, secret)
    assert r.status_code == 200
    body = r.json()
    assert body["token_type"] == "bearer" and body["role"] == "analyst"
    assert body["access_token"]


def test_wrong_password_is_401(client_and_secret):
    client, secret = client_and_secret
    assert _login(client, secret, password="wrong").status_code == 401


def test_wrong_totp_is_401(client_and_secret, monkeypatch):
    from app.core.config import settings
    monkeypatch.setattr(settings, "require_mfa", True)      # independent of the local .env
    client, secret = client_and_secret
    assert _login(client, secret, code="000000").status_code == 401


def test_totp_not_checked_when_mfa_disabled(client_and_secret, monkeypatch):
    from app.core.config import settings
    monkeypatch.setattr(settings, "require_mfa", False)     # prototype login without TOTP
    client, secret = client_and_secret
    assert _login(client, secret, code="000000").status_code == 200


def test_unknown_user_is_401(client_and_secret):
    client, _ = client_and_secret
    r = client.post(LOGIN, data={"username": "ghost", "password": "x", "client_secret": "000000"})
    assert r.status_code == 401


# --- RBAC / token unit tests (no HTTP) ---------------------------------------
def test_token_round_trips_subject_and_role():
    token = create_access_token("analyst-1", Role.SUPERVISOR)
    p = decode_token(token)
    assert p.subject == "analyst-1" and p.role is Role.SUPERVISOR


def test_access_token_rejected_where_refresh_expected():
    from fastapi import HTTPException

    access = create_access_token("a", Role.ANALYST)
    with pytest.raises(HTTPException) as exc:
        decode_token(access, expected_type="refresh")    # type mismatch
    assert exc.value.status_code == 401


def test_login_returns_refresh_and_refresh_endpoint_issues_access(client_and_secret):
    client, secret = client_and_secret
    body = _login(client, secret).json()
    assert body["refresh_token"]
    r = client.post("/api/v1/auth/refresh", json={"refresh_token": body["refresh_token"]})
    assert r.status_code == 200 and r.json()["access_token"]


def test_refresh_rejects_an_access_token(client_and_secret):
    client, secret = client_and_secret
    body = _login(client, secret).json()
    r = client.post("/api/v1/auth/refresh", json={"refresh_token": body["access_token"]})
    assert r.status_code == 401                          # access token isn't a refresh token


def test_require_role_blocks_insufficient_privilege():
    guard = require_role(Role.SUPERVISOR)
    from fastapi import HTTPException

    with pytest.raises(HTTPException) as exc:
        guard(principal=Principal(subject="a", role=Role.ANALYST))
    assert exc.value.status_code == 403
    # supervisor passes its own gate
    assert guard(principal=Principal(subject="s", role=Role.SUPERVISOR)).role is Role.SUPERVISOR
