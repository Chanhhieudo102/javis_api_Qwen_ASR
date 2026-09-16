"""Authentication service."""

from datetime import datetime, timedelta, timezone

from jose import JWTError, jwt
from passlib.context import CryptContext
from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.auth.models.token import Token
from app.auth.schemas.auth_schema import LoginResponse
from app.common.configs.settings import settings
from app.common.constants.error_constants import ErrorConstants
from app.common.exceptions import BadRequestException, UnauthorizedException
from app.users.models.user import User

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


class AuthService:
    """Service for authentication operations."""

    def __init__(self):
        """Initialize service without database session."""
        pass

    def verify_password(self, plain_password: str, hashed_password: str) -> bool:
        """Verify a password against a hash."""
        return pwd_context.verify(plain_password, hashed_password)

    def get_password_hash(self, password: str) -> str:
        """Generate password hash."""
        return pwd_context.hash(password)

    def create_access_token(self, token_id: str) -> str:
        """Create access token with subject as Token ID."""
        expire = datetime.now(timezone.utc) + timedelta(
            minutes=settings.access_token_expire_minutes
        )
        to_encode = {
            "sub": str(token_id),
            "exp": expire,
            "type": "access",
        }
        return jwt.encode(to_encode, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)

    def create_refresh_token(self, refresh_token_uuid: str) -> str:
        """Create refresh token encoded as JWT."""
        expire = datetime.now(timezone.utc) + timedelta(days=settings.refresh_token_expire_days)
        to_encode = {
            "sub": str(refresh_token_uuid),
            "exp": expire,
            "type": "refresh",
        }
        return jwt.encode(to_encode, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)

    def create_token_record(self, db: Session, user_id: str) -> Token:
        """Create a new token record in database."""
        token_record = Token(user_id=user_id)  # ID and refresh_token are auto-generated UUIDs
        db.add(token_record)
        db.flush()
        db.refresh(token_record)
        return token_record

    def decode_token(self, token: str) -> dict:
        """Decode and validate token."""
        try:
            payload = jwt.decode(
                token, settings.jwt_secret_key, algorithms=[settings.jwt_algorithm]
            )
            return payload
        except JWTError as e:
            raise UnauthorizedException(detail=ErrorConstants.Auth.TOKEN_INVALID) from e

    def login(self, db: Session, email: str, password: str) -> LoginResponse:
        """Authenticate user and return access token + encoded refresh token."""
        # STRICT EMAIL LOGIN
        user = db.query(User).filter(User.email == email).first()

        if not user:
            raise BadRequestException(detail=ErrorConstants.Auth.INVALID_CREDENTIALS)

        if not self.verify_password(password, user.password):
            raise BadRequestException(detail=ErrorConstants.Auth.INVALID_CREDENTIALS)

        # Create Token Record
        token_record = self.create_token_record(db, user.id)

        # Access token sub = Token ID as requested
        access_token = self.create_access_token(token_record.id)

        # Refresh token is encoded JWT containing the UUID from the record
        refresh_token = self.create_refresh_token(token_record.refresh_token)

        return LoginResponse(
            access_token=access_token,
            refresh_token=refresh_token,
        )

    def refresh_access_token(self, db: Session, refresh_token_jwt: str) -> LoginResponse:
        """Refresh access token using encoded refresh token."""
        # 1. Decode JWT to get the UUID
        payload = self.decode_token(refresh_token_jwt)

        if payload.get("type") != "refresh":
            raise UnauthorizedException(detail=ErrorConstants.Auth.TOKEN_INVALID)

        refresh_token_uuid = payload.get("sub")

        # 2. Lookup Token by refresh_token UUID
        try:
            token_record = (
                db.query(Token)
                .filter(
                    Token.refresh_token == refresh_token_uuid,
                    or_(Token.revoked_at.is_(None), Token.revoked_at > datetime.utcnow()),
                )
                .first()
            )
        except Exception:
            raise UnauthorizedException(detail=ErrorConstants.Auth.TOKEN_INVALID)

        if not token_record:
            raise UnauthorizedException(detail=ErrorConstants.Auth.TOKEN_INVALID)

        # Check explicit revocation if revoked_at is not NULL (handled in filter roughly, but be precise)
        if token_record.revoked_at:
            raise UnauthorizedException(detail=ErrorConstants.Auth.TOKEN_INVALID)

        # 3. Revoke OLD token (Rotation)
        token_record.revoked_at = datetime.utcnow()
        db.add(token_record)

        # 4. Create NEW token record (Same flow as login)
        new_token_record = self.create_token_record(db, token_record.user_id)

        new_access_token = self.create_access_token(new_token_record.id)
        new_refresh_token = self.create_refresh_token(new_token_record.refresh_token)

        return LoginResponse(
            access_token=new_access_token,
            refresh_token=new_refresh_token,
        )

    def revoke_token_by_id(self, db: Session, token_id: str) -> None:
        """Revoke a token by its ID (from access token sub)."""
        token_record = db.query(Token).filter(Token.id == token_id).first()
        if token_record:
            token_record.revoked_at = datetime.utcnow()
            db.add(token_record)
            db.flush()

    def get_current_user(self, db: Session, token: str) -> User:
        """Get current user from token."""
        payload = self.decode_token(token)

        if payload.get("type") != "access":
            raise UnauthorizedException(detail=ErrorConstants.Auth.TOKEN_INVALID)

        # 'sub' is Token ID now
        token_id = payload.get("sub")

        token_record = db.query(Token).filter(Token.id == token_id).first()

        if not token_record or token_record.revoked_at:
            raise UnauthorizedException(detail=ErrorConstants.Auth.TOKEN_INVALID)

        # Resolve User from Token
        user = token_record.user  # Via relationship

        # Or explicit query if relationship issue
        if not user:
            user = db.query(User).filter(User.id == token_record.user_id).first()

        if not user:
            raise UnauthorizedException(detail=ErrorConstants.User.USER_NOT_FOUND)

        return user
