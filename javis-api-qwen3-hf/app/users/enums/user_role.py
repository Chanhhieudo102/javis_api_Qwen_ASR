"""User role enum."""

from enum import Enum


class UserRole(str, Enum):
    """User role enumeration."""

    OWNER = "owner"
    USER = "user"
