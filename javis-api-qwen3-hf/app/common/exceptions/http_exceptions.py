"""HTTP exception classes."""

from fastapi import HTTPException, status


class AppHTTPException(HTTPException):
    """Base class for all application HTTP exceptions."""

    pass


class BadRequestException(AppHTTPException):
    """Exception for 400 Bad Request errors."""

    def __init__(self, detail: str = "Bad request"):
        super().__init__(status_code=status.HTTP_400_BAD_REQUEST, detail=detail)


class UnauthorizedException(AppHTTPException):
    """Exception for 401 Unauthorized errors."""

    def __init__(self, detail: str = "Unauthorized"):
        super().__init__(status_code=status.HTTP_401_UNAUTHORIZED, detail=detail)


class ForbiddenException(AppHTTPException):
    """Exception for 403 Forbidden errors."""

    def __init__(self, detail: str = "Forbidden"):
        super().__init__(status_code=status.HTTP_403_FORBIDDEN, detail=detail)


class NotFoundException(AppHTTPException):
    """Exception for 404 Not Found errors."""

    def __init__(self, detail: str = "Not Found"):
        super().__init__(status_code=status.HTTP_404_NOT_FOUND, detail=detail)


class InternalServerException(AppHTTPException):
    """Exception for 500 Internal Server errors."""

    def __init__(self, detail: str = "Internal server error"):
        super().__init__(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=detail)
