import os

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.config import settings
from app.db.licensed_repo import active_identifiers, import_rows, upsert_entity
from app.db.models import Base, LicensedEntity
from scripts.import_licensed_registry import parse_csv

SAMPLE = os.path.join(os.path.dirname(__file__), "..", "scripts", "licensed_registry.sample.csv")


@pytest.fixture
def session():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    with sessionmaker(bind=engine)() as s:
        yield s


def test_upsert_normalizes_and_is_idempotent(session):
    upsert_entity(session, "@LegalBroker", operator="AO")
    upsert_entity(session, "legalbroker", operator="AO updated")   # same normalized id
    session.commit()
    rows = session.query(LicensedEntity).all()
    assert len(rows) == 1 and rows[0].identifier == "legalbroker"
    assert rows[0].operator == "AO updated"


def test_blank_identifier_skipped(session):
    assert upsert_entity(session, "   ") is None


def test_active_identifiers_excludes_revoked_and_unions_env(session, monkeypatch):
    import_rows(session, [
        {"identifier": "profit-x.kz", "status": "active"},
        {"identifier": "scam-casino.io", "status": "revoked"},
        {"identifier": "broker.kz", "status": "suspended"},
    ])
    monkeypatch.setattr(settings, "licensed_registry", ["env-broker.kz"])
    ids = active_identifiers(session)
    assert "profit-x.kz" in ids                 # active DB row
    assert "env-broker.kz" in ids               # env allowlist union
    assert "scam-casino.io" not in ids          # revoked -> not licensed
    assert "broker.kz" not in ids               # suspended -> not licensed


def test_import_rows_counts(session):
    res = import_rows(session, [
        {"identifier": "a.kz"}, {"identifier": ""}, {"identifier": "@b"},
    ])
    assert res == {"imported": 2, "skipped": 1}


def test_parse_sample_csv_maps_columns():
    rows = parse_csv(SAMPLE)
    by_id = {r["identifier"]: r for r in rows}
    assert by_id["profit-x.kz"]["status"] == "active"
    assert by_id["scam-casino.io"]["status"] == "revoked"
    assert by_id["@legalbroker"]["kind"] == "handle"


def test_parse_csv_requires_identifier_column(tmp_path):
    bad = tmp_path / "bad.csv"
    bad.write_text("operator,status\nFoo,active\n", encoding="utf-8")
    with pytest.raises(ValueError):
        parse_csv(str(bad))
