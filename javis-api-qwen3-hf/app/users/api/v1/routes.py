"""Users API v1 routes."""

from fastapi import APIRouter, Depends

from app.auth.dependencies import get_current_user
from app.common.schemas import DataResponseAPI
from app.users.models.user import User
from app.users.schemas.user_schema import (
    UserResponse,
)
from app.users.services.user_service import UserService

router = APIRouter(prefix="/users", tags=["Users"])

# Service instantiated ONCE at module level
user_service = UserService()


@router.get("/me", response_model=dict)
async def get_current_user_info(current_user: User = Depends(get_current_user)):
    """Get current user information."""
    return DataResponseAPI.success_without_meta(data=UserResponse.model_validate(current_user))
