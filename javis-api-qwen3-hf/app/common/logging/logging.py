"""Logging configuration and utilities."""

import logging
import sys
from pprint import pformat

from pydantic import BaseModel

from app.common.configs.settings import settings


def pretty_repr(obj) -> str:
    """Pretty print an object for logging."""
    if isinstance(obj, BaseModel):
        return pformat(obj.model_dump() if hasattr(obj, "model_dump") else obj.dict())
    elif isinstance(obj, list | tuple):
        return pformat([pretty_repr(x) for x in obj])
    elif isinstance(obj, dict):
        return pformat(obj)
    return str(obj)


def get_logger(name: str = __name__) -> logging.Logger:
    """Get a logger instance.

    Args:
        name: The name of the logger.

    Returns:
        logging.Logger: A logger instance.
    """
    return logging.getLogger(name)


def setup_logging() -> None:
    """Setup logging configuration."""
    log_level = logging.INFO

    # Remove existing handlers
    for handler in logging.root.handlers[:]:
        logging.root.removeHandler(handler)

    # Console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(
        logging.Formatter(
            "%(asctime)s | %(levelname)s | %(name)s | %(funcName)s | %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
    )

    handlers = [console_handler]

    logging.basicConfig(level=log_level, handlers=handlers)

    # Reduce noise from uvicorn in production
    if settings.app_env != "dev":
        logging.getLogger("uvicorn.access").setLevel(logging.ERROR)
        logging.getLogger("uvicorn.error").setLevel(logging.ERROR)


# System logger instance
system_logger = get_logger("system")
