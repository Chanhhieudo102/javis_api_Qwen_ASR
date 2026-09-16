"""Auth dependencies for route protection."""

from typing import Callable

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.auth.services.auth_service import AuthService
from app.common.db import SessionDB
from app.users.enums.user_role import UserRole
from app.users.models.user import User

security = HTTPBearer()

# Service instantiated ONCE at module level
auth_service = AuthService()


def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: SessionDB = None,
) -> User:
    """Dependency to get current authenticated user."""
    token = credentials.credentials
    return auth_service.get_current_user(db, token)


# Role-based authorization dependencies
def require_role(allowed_roles: list[UserRole]) -> Callable:
    """Create a dependency that checks if user has one of the allowed roles.

    Usage:
        @router.get("/admin-only", dependencies=[Depends(require_role([UserRole.OWNER]))])
    """

    def role_checker(current_user: User = Depends(get_current_user)) -> User:
        if current_user.role not in allowed_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Access denied. Required roles: {[role.value for role in allowed_roles]}",
            )
        return current_user

    return role_checker


# Specific role checkers - simple is_<role> style
def is_owner(current_user: User = Depends(get_current_user)) -> User:
    """Check if user is owner."""
    if current_user.role != UserRole.OWNER:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied. Owner role required.",
        )
    return current_user
