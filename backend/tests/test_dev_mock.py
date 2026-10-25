import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.db import notifications_repo as notif
from app.db.models import Base, Content, ContentRisk, RiskAssessment, WatchTarget
from app.services import dev_mock


@pytest.fixture
def session():
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    with Session(engine) as s:
        yield s


def test_seed_creates_full_mock(session):
    out = dev_mock.seed_mock(session)
    assert out["seeded"] and out["score"] > 0
    assert session.get(Content, dev_mock.MOCK_CONTENT_ID) is not None
    assert session.query(ContentRisk).filter_by(content_id=dev_mock.MOCK_CONTENT_ID).count() == 1
    assert session.query(RiskAssessment).filter_by(target=dev_mock.MOCK_AUTHOR).count() == 1
    assert session.query(WatchTarget).filter_by(value=dev_mock.MOCK_AUTHOR).count() == 1
    assert notif.unread_count(session) == 1   # alert fired for the watched account


def test_seed_is_idempotent(session):
    dev_mock.seed_mock(session)
    dev_mock.seed_mock(session)
    assert session.query(Content).filter_by(id=dev_mock.MOCK_CONTENT_ID).count() == 1
    assert session.query(WatchTarget).filter_by(value=dev_mock.MOCK_AUTHOR).count() == 1


def test_clear_removes_everything(session):
    dev_mock.seed_mock(session)
    dev_mock.clear_mock(session)
    assert session.get(Content, dev_mock.MOCK_CONTENT_ID) is None
    assert session.query(ContentRisk).filter_by(content_id=dev_mock.MOCK_CONTENT_ID).count() == 0
    assert session.query(RiskAssessment).filter_by(target=dev_mock.MOCK_AUTHOR).count() == 0
    assert session.query(WatchTarget).filter_by(value=dev_mock.MOCK_AUTHOR).count() == 0
