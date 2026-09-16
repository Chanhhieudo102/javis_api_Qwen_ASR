"""Data response schemas."""

from enum import StrEnum
from typing import Any

from pydantic import BaseModel


class ResponseStatus(StrEnum):
    """Response status enum."""

    SUCCESS = "success"
    FAILURE = "failure"


class DataResponseAPI(BaseModel):
    """Standard API response wrapper."""

    status: ResponseStatus
    data: Any | None = None
    error: Any | None = None
    meta: Any | None = None

    model_config = {
        "json_schema_extra": {"exclude_none": True},
    }

    @staticmethod
    def success(data: Any = None, meta: Any = None) -> dict:
        """Return a success response with optional data and meta information."""
        return DataResponseAPI(
            status=ResponseStatus.SUCCESS, data=data, meta=meta
        ).model_dump(exclude_none=True)

    @staticmethod
    def success_without_meta(data: Any = None) -> dict:
        """Return a success response without meta information."""
        return DataResponseAPI(status=ResponseStatus.SUCCESS, data=data).model_dump(
            exclude_none=True
        )

    @staticmethod
    def success_without_meta_and_data() -> dict:
        """Return a success response without meta and data information."""
        return DataResponseAPI(status=ResponseStatus.SUCCESS).model_dump(exclude_none=True)

    @staticmethod
    def error_response(error: Any, data: Any = None) -> dict:
        """Return an error response with the provided error information."""
        return DataResponseAPI(status=ResponseStatus.FAILURE, error=error, data=data).model_dump(
            exclude_none=True
        )
