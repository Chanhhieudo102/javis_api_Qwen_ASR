"""Database session management."""

import os
from collections.abc import Generator
from typing import Annotated

from fastapi import Depends
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.common.configs.settings import settings
from app.common.logging import get_logger

logger = get_logger(__name__)

# Lazy-load DB engine: chỉ tạo kết nối khi thực sự gọi, tránh crash lúc import
_engine = None
_SessionLocal = None


def get_engine():
    """Get or create the SQLAlchemy engine (lazy initialization)."""
    global _engine
    if _engine is None:
        _engine = create_engine(
            settings.database_url,
            pool_pre_ping=True,
            pool_size=10,
            max_overflow=20,
            pool_recycle=1800,
            pool_timeout=30,
            connect_args={
                "options": "-c timezone=utc",
                "keepalives": 1,
                "keepalives_idle": 300,
                "keepalives_interval": 30,
                "keepalives_count": 5,
                "connect_timeout": 10,
            },
        )
    return _engine


def get_session_local():
    """Get or create the SessionLocal factory (lazy initialization)."""
    global _SessionLocal
    if _SessionLocal is None:
        _SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=get_engine())
    return _SessionLocal


# Backward-compatible properties for existing code that imports `engine` and `SessionLocal`
class _LazyEngine:
    """Proxy object that lazily initializes the engine on first attribute access."""
    def __getattr__(self, name):
        return getattr(get_engine(), name)

class _LazySessionLocal:
    """Proxy object that lazily initializes SessionLocal on first call."""
    def __call__(self, *args, **kwargs):
        return get_session_local()(*args, **kwargs)
    def __getattr__(self, name):
        return getattr(get_session_local(), name)

engine = _LazyEngine()
SessionLocal = _LazySessionLocal()


def get_db() -> Generator[Session, None, None]:
    """Get database session.

    Yields:
        Session: SQLAlchemy database session.
    """
    db = get_session_local()()
    try:
        yield db
        db.commit()
    except Exception as e:
        logger.error(f"Database session error: {e}")
        db.rollback()
        raise
    finally:
        db.close()

SessionDB = Annotated[Session, Depends(get_db)]
