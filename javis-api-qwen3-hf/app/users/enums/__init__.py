"""User role enum."""

from enum import Enum


class UserRole(str, Enum):
    """User role enumeration."""

    OWNER = "owner"
    WAITER = "waiter"
    CHEF = "chef"
    BARTENDER = "bartender"
    CASHIER = "cashier"
