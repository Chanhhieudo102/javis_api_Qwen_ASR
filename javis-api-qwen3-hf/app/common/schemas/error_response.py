"""Error response schema."""

from pydantic import BaseModel


class ErrorResponse(BaseModel):
    """Error response model."""

    code: str
    message: str
