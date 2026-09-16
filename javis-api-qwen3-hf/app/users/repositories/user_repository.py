"""User repository."""

from typing import Literal

from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.users.models.user import User


class UserRepository:
    """Repository for user database operations."""

    def __init__(self):
        """Initialize repository without database session."""
        pass

    def get_by_id(self, db: Session, user_id: str) -> User | None:
        """Get user by ID."""
        return db.query(User).filter(User.id == user_id).first()

    def get_by_email(self, db: Session, email: str) -> User | None:
        """Get user by email."""
        return db.query(User).filter(User.email == email).first()

    def get_by_username(self, db: Session, username: str) -> User | None:
        """Get user by username."""
        return db.query(User).filter(User.username == username).first()

    def count_by_role(self, db: Session, role: str) -> int:
        """Count users by role."""
        return db.query(User).filter(User.role == role).count()

    def _apply_search_filter(self, query, search: str | None):
        """Apply search filter to query."""
        if search:
            search_pattern = f"%{search}%"
            query = query.filter(
                or_(
                    User.email.ilike(search_pattern),
                    User.full_name.ilike(search_pattern),
                    User.username.ilike(search_pattern),
                )
            )
        return query

    def _apply_sorting(
        self,
        query,
        sort_by: str = "created_at",
        sort_order: Literal["asc", "desc"] = "desc",
    ):
        """Apply sorting to query."""
        # Get the column to sort by, default to created_at
        sort_column = getattr(User, sort_by, User.created_at)
        if sort_order == "desc":
            query = query.order_by(sort_column.desc())
        else:
            query = query.order_by(sort_column.asc())
        return query

    def get_all(
        self,
        db: Session,
        skip: int = 0,
        limit: int = 100,
        search: str | None = None,
        sort_by: str = "created_at",
        sort_order: Literal["asc", "desc"] = "desc",
    ) -> list[User]:
        """Get all users with pagination, search, and sorting."""
        query = db.query(User)
        query = self._apply_search_filter(query, search)
        query = self._apply_sorting(query, sort_by, sort_order)
        return query.offset(skip).limit(limit).all()

    def count(self, db: Session, search: str | None = None) -> int:
        """Count total users with optional search filter."""
        query = db.query(User)
        query = self._apply_search_filter(query, search)
        return query.count()

    def create(self, db: Session, user: User) -> User:
        """Create a new user."""
        db.add(user)
        db.flush()
        db.refresh(user)
        return user

    def update(self, db: Session, user: User) -> User:
        """Update an existing user."""
        db.flush()
        db.refresh(user)
        return user

    def delete(self, db: Session, user: User) -> None:
        """Delete a user."""
        db.delete(user)
        db.flush()
