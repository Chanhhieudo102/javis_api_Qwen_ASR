"""Database initialization."""

from app.common.db.base import Base
from app.common.db.session import engine


def init_db() -> None:
    """Initialize database by creating all tables."""
    # Import all models to register them with SQLAlchemy
    import app.common.db.models  # noqa: F401
    Base.metadata.create_all(bind=engine)
