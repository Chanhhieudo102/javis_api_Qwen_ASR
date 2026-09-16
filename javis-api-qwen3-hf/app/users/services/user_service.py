"""User service."""

import secrets
import string

from passlib.context import CryptContext
from sqlalchemy.orm import Session

from app.common.constants.error_constants import ErrorConstants
from app.common.exceptions import BadRequestException, NotFoundException
from app.users.enums.user_role import UserRole
from app.users.models.user import User
from app.users.repositories.user_repository import UserRepository
from app.users.schemas.user_schema import (
    UserRegister,
    UserResponse,
)

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


class UserService:
    """Service for user operations."""

    def __init__(self):
        """Initialize service without database session."""
        self.repository = UserRepository()

    @staticmethod
    def _generate_password(length: int = 12) -> str:
        """Generate a secure random password."""
        alphabet = string.ascii_letters + string.digits + "!@#$%^&*"
        return "".join(secrets.choice(alphabet) for _ in range(length))

    def get_user(self, db: Session, user_id: str) -> UserResponse:
        """Get user by ID."""
        user = self.repository.get_by_id(db, user_id)
        if not user:
            raise NotFoundException(detail=ErrorConstants.User.USER_NOT_FOUND)
        return UserResponse.model_validate(user)

    def create_user(self, db: Session, user_data: UserRegister) -> UserResponse:
        """Create a normal user."""
        if self.repository.get_by_email(db, user_data.email):
            raise BadRequestException(detail=ErrorConstants.User.EMAIL_ALREADY_EXISTS)

        hashed_password = pwd_context.hash(user_data.password)
        db_user = User(
            email=user_data.email,
            username=user_data.username,
            password=hashed_password,
            role=UserRole.USER,
            is_active=True,
        )

        user = self.repository.create(db, db_user)
        return UserResponse.model_validate(user)

    # Keeping create_owner if it was supposedly there, or identifying it's removal is fine because user removed the route.
    # I will NOT add create_owner back if it wasn't validly visible, but I'll add create_owner placeholder if I want to be safe?
    # No, I'll stick to what I see.
