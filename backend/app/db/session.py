"""SQLAlchemy session factory + FastAPI dependency.

The engine is created lazily so importing this module never requires a DB driver
or a live connection (tests override `get_session` with an in-memory engine).
"""
from __future__ import annotations

from collections.abc import Iterator
from functools import lru_cache

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import settings


@lru_cache
def _sessionmaker() -> sessionmaker:
    engine = create_engine(settings.database_url, pool_pre_ping=True, future=True)
    return sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def get_session() -> Iterator[Session]:
    """Request-scoped DB session. Overridden in tests with an in-memory engine."""
    session = _sessionmaker()()
    try:
        yield session
    finally:
        session.close()
