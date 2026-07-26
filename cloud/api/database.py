"""Database connection and session management."""
from __future__ import annotations

import os

from models import Base
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

DATABASE_URL = os.environ.get(
    "DATABASE_URL",
    "postgresql://boat:boat@localhost:5432/boatdata",
)

engine = create_engine(
    DATABASE_URL,
    pool_size=10,
    max_overflow=20,
    # Managed/cloud Postgres (Railway, Fly.io, etc.) will silently drop idle
    # connections; without these, a pooled connection handed to a request can
    # be dead on arrival and raise mid-request instead of being replaced.
    pool_pre_ping=True,
    pool_recycle=1800,
)
SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)


def init_db() -> None:
    """Create required extensions, then all tables, if they don't exist."""
    with engine.begin() as conn:
        # postgis: backs the Geometry columns. btree_gist: required for the
        # composite GiST index on (timestamp, geom) in models.py — a GiST
        # index mixing a scalar (timestamp) column with geometry needs the
        # btree_gist opclasses, or table creation fails on a fresh database.
        conn.execute(text("CREATE EXTENSION IF NOT EXISTS postgis"))
        conn.execute(text("CREATE EXTENSION IF NOT EXISTS btree_gist"))
    Base.metadata.create_all(bind=engine)


def get_db():
    """FastAPI dependency — yields a database session, rolling back on error."""
    db = SessionLocal()
    try:
        yield db
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
