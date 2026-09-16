"""Global exception handlers."""

import traceback

from fastapi import Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.status import HTTP_400_BAD_REQUEST, HTTP_500_INTERNAL_SERVER_ERROR

from app.common.configs.settings import settings
from app.common.exceptions.http_exceptions import (
    AppHTTPException,
    BadRequestException,
    ForbiddenException,
    InternalServerException,
    NotFoundException,
    UnauthorizedException,
)
from app.common.i18n import MessageResolver
from app.common.logging import get_logger
from app.common.schemas import DataResponseAPI, ErrorResponse

logger = get_logger(__name__)


async def global_exception_handler(request: Request, exc: Exception):
    """Handle all application exceptions globally."""
    locale = getattr(request.state, "locale", settings.default_locale)

    if isinstance(
        exc,
        (
            BadRequestException,
            NotFoundException,
            ForbiddenException,
            UnauthorizedException,
            InternalServerException,
        ),
    ):
        error_dict = MessageResolver.get_message(locale, str(exc.detail))
        logger.error(f"Error occurred: {error_dict}")
        error = ErrorResponse(
            code=error_dict.get("code", "ERR.SER0101"),
            message=error_dict.get("message", "Unknown error"),
        )
        return JSONResponse(
            status_code=exc.status_code,
            content=DataResponseAPI.error_response(error),
        )

    elif isinstance(exc, RequestValidationError):
        errors = exc.errors()
        msgs = []
        for err in errors:
            field = err.get("loc")[-1]
            msg = err.get("msg")
            msgs.append(f"{field}: {msg}")

        full_msg = " | ".join(msgs)
        error = ErrorResponse(code="ERR.VAL0101", message=full_msg)
        return JSONResponse(
            status_code=HTTP_400_BAD_REQUEST,
            content=DataResponseAPI.error_response(error),
        )

    elif isinstance(exc, AppHTTPException):
        error = ErrorResponse(code="ERR.APP0101", message=str(exc.detail))
        return JSONResponse(
            status_code=exc.status_code,
            content=DataResponseAPI.error_response(error),
        )

    else:
        error_dict = MessageResolver.get_message(locale, "internal_server_error")
        error = ErrorResponse(
            code=error_dict.get("code", "ERR.SER0101"),
            message=error_dict.get("message", "Internal server error"),
        )
        logger.error("".join(traceback.format_exception(type(exc), exc, exc.__traceback__)))
        return JSONResponse(
            status_code=HTTP_500_INTERNAL_SERVER_ERROR,
            content=DataResponseAPI.error_response(error),
        )
