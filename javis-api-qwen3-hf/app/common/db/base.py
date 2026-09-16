"""Database base classes and metadata."""

import re

from sqlalchemy import MetaData
from sqlalchemy.orm import DeclarativeBase, declared_attr

# Constraint/index naming convention
POSTGRES_INDEXES_NAMING_CONVENTION = {
    "ix": "%(column_0_label)s_idx",
    "uq": "%(table_name)s_%(column_0_name)s_key",
    "ck": "%(table_name)s_%(constraint_name)s_check",
    "fk": "%(table_name)s_%(column_0_name)s_fkey",
    "pk": "%(table_name)s_pkey",
}
metadata = MetaData(naming_convention=POSTGRES_INDEXES_NAMING_CONVENTION)


def camel_to_snake(name: str) -> str:
    """Convert CamelCase to snake_case."""
    return re.sub(r"(?<!^)(?=[A-Z])", "_", name).lower()


class Base(DeclarativeBase):
    """Base class for all SQLAlchemy models."""

    metadata = metadata


class SnakeBase(Base):
    """Base class with automatic snake_case table naming."""

    __abstract__ = True

    @declared_attr.directive
    def __tablename__(self) -> str:
        """Get the table name for the model.

        Returns:
            str: The table name in snake_case.
        """
        return camel_to_snake(self.__name__)
