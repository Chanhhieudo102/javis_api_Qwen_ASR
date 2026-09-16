"""Message resolver for internationalization."""

from pathlib import Path
from typing import Any

import yaml

from app.common.configs.settings import settings


class MessageResolver:
    """Utility class to resolve localized messages from YAML files."""

    _cache: dict[str, dict[str, Any]] = {}
    DEFAULT_ERROR = {"code": "UNKNOWN", "message": "Message not found"}

    @classmethod
    def get_message(cls, lang: str, *path: str) -> dict[str, str]:
        """Retrieve a localized error message by language and path.

        Args:
            lang: Language code (e.g., "en", "vi", "ja").
            *path: Path to the message in YAML, e.g., ("validation_error",).

        Returns:
            A dictionary containing 'code' and 'message'.
        """
        messages = cls._cache.setdefault(lang, cls._load_yaml(lang))
        if not messages:
            return {"code": "UNKNOWN", "message": f"Language '{lang}' not found"}

        message_entry = cls._get_from_path(messages, path)

        if message_entry is None:
            return {
                "code": cls.DEFAULT_ERROR["code"],
                "message": " / ".join(path),
            }

        if isinstance(message_entry, dict):
            return {
                "code": message_entry.get("code", cls.DEFAULT_ERROR["code"]),
                "message": message_entry.get("message", cls.DEFAULT_ERROR["message"]),
            }

        return {
            "code": cls.DEFAULT_ERROR["code"],
            "message": str(message_entry) or cls.DEFAULT_ERROR["message"],
        }

    @classmethod
    def _get_from_path(cls, data: dict[str, Any], path: tuple) -> Any:
        """Traverse nested dict using the provided path."""
        current = data
        for key in path:
            if not isinstance(current, dict):
                return None
            current = current.get(key)
            if current is None:
                return None
        return current

    @classmethod
    def _load_yaml(cls, lang: str) -> dict[str, Any]:
        """Load the YAML file for the given language."""
        file_path = Path(settings.error_dir) / f"error_{lang}.yml"
        if not file_path.exists():
            return {}

        try:
            with file_path.open("r", encoding="utf-8") as f:
                return yaml.safe_load(f) or {}
        except Exception:
            return {}
