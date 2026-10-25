import pyotp
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.db.models import Base, User
from scripts.seed_demo import DEMO_USER, seed_user


@pytest.fixture
def session():
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    with Session(engine) as s:
        yield s


def test_seed_user_creates_with_valid_totp(session):
    info = seed_user(session)
    assert info["created"] is True
    # TOTP secret is valid base32 and produces 6-digit codes
    code = pyotp.TOTP(info["totp_secret"]).now()
    assert len(code) == 6 and code.isdigit()
    assert "otpauth://" in info["otpauth"]
    assert session.query(User).filter_by(username=DEMO_USER).count() == 1


def test_seed_user_is_idempotent(session):
    seed_user(session)
    info2 = seed_user(session)
    assert info2["created"] is False
    assert session.query(User).filter_by(username=DEMO_USER).count() == 1


@pytest.mark.integration
def test_seed_graph_and_fingerprints_against_live_services():
    # Requires live Neo4j + Qdrant (docker compose up). Skipped in the default unit run.
    from app.db.clients import neo4j_driver, qdrant_client
    from scripts.seed_demo import seed_fingerprints, seed_graph

    seed_graph(neo4j_driver())
    seed_fingerprints(qdrant_client())
