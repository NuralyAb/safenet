"""Lazily-constructed datastore clients (one place to wire connections)."""
from __future__ import annotations

from functools import lru_cache

from app.core.config import settings


@lru_cache
def neo4j_driver():
    from neo4j import GraphDatabase

    return GraphDatabase.driver(
        settings.neo4j_uri, auth=(settings.neo4j_user, settings.neo4j_password)
    )


@lru_cache
def qdrant_client():
    from qdrant_client import QdrantClient

    return QdrantClient(url=settings.qdrant_url)


@lru_cache
def minio_client():
    from minio import Minio

    host = settings.minio_endpoint
    return Minio(
        host,
        access_key=settings.minio_user,
        secret_key=settings.minio_password,
        secure=False,  # internal network; terminate TLS at the perimeter
    )


@lru_cache
def sqlalchemy_engine():
    from sqlalchemy import create_engine

    return create_engine(settings.database_url, pool_pre_ping=True)
