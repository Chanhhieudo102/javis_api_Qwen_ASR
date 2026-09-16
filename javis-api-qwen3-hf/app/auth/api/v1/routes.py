"""Auth API v1 routes."""

from fastapi import APIRouter, Depends, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer, OAuth2PasswordBearer

from app.auth.schemas.auth_schema import LoginRequest, TokenRefreshRequest
from app.auth.services.auth_service import AuthService
from app.common.db import SessionDB
from app.common.schemas import DataResponseAPI
from app.users.schemas.user_schema import UserRegister
from app.users.services.user_service import UserService

router = APIRouter(prefix="/auth", tags=["Auth"])

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login")

# Services instantiated ONCE at module level
auth_service = AuthService()
user_service = UserService()


@router.post(
    "/register",
    response_model=dict,
    status_code=status.HTTP_201_CREATED,
    summary="Register user",
    description="Register a new user.",
)
async def register(user_data: UserRegister, db: SessionDB = None):
    """Register a new user."""
    result = user_service.create_user(db, user_data)
    return DataResponseAPI.success_without_meta(data=result)


@router.post("/login", response_model=dict)
async def login(request: LoginRequest, db: SessionDB = None):
    """Login with email and password."""
    result = auth_service.login(db, request.email, request.password)
    return DataResponseAPI.success_without_meta(data=result)


@router.post("/refresh", response_model=dict)
async def refresh_token(request: TokenRefreshRequest, db: SessionDB = None):
    """Refresh access token using refresh token."""
    result = auth_service.refresh_access_token(db, request.refresh_token)
    return DataResponseAPI.success_without_meta(data=result)


@router.post("/logout", response_model=dict)
@router.post("/logout", response_model=dict)
async def logout(
    credentials: HTTPAuthorizationCredentials = Depends(HTTPBearer()), db: SessionDB = None
):
    """Logout user (revoke access token)."""
    token = credentials.credentials
    payload = auth_service.decode_token(token)
    token_id = payload.get("sub")
    auth_service.revoke_token_by_id(db, token_id)

    return DataResponseAPI.success_without_meta_and_data()
