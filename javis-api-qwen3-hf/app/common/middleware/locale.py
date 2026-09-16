"""Locale middleware for request language detection."""

from fastapi import Request

from app.common.configs.settings import settings


def get_locale_from_request(request: Request) -> str:
    """Get the locale from the request headers.

    Args:
        request: The request object.

    Returns:
        The locale code.
    """
    accept_language = request.headers.get("accept-language", "")
    if accept_language:
        lang = accept_language.split(",")[0].split("-")[0].lower()
        if lang in settings.supported_locales:
            return lang
    return settings.default_locale


async def locale_middleware(request: Request, call_next):
    """Set the locale for the request.

    Args:
        request: The request object.
        call_next: The next middleware or route handler.

    Returns:
        The response from the next middleware or route handler.
    """
    request.state.locale = get_locale_from_request(request)
    response = await call_next(request)
    return response
