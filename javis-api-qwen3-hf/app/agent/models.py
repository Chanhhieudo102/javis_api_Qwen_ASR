import os

from app.agent.clients.chat_model import ChatModel
from app.agent.clients.llm_client import build_raw_chat_model
from app.agent.clients.runnable_chat_model import RunnableChatModel
from app.agent.schemas.model_profile import ModelProfile


def build_pair(profile: ModelProfile) -> tuple[ChatModel, ChatModel | None]:
    """Build primary and optional fallback ChatModel instances.

    This is the ONLY place specifying LLM providers.
    """
    base_url = os.getenv("LLM_BASE_URL", "https://api.openai.com/v1")
    api_key = os.getenv("LLM_API_KEY", "dummy-api-key")
    x_api_key = os.getenv("LLM_X_API_KEY")

    primary = build_raw_chat_model(
        model_name=profile.primary_model,
        base_url=base_url,
        api_key=api_key,
        x_api_key=x_api_key,
        temperature=profile.temperature,
        timeout=profile.timeout_seconds,
        max_tokens=profile.max_tokens,
    )

    fallback: ChatModel | None = None
    if profile.fallback_model:
        fallback_base_url = os.getenv("LLM_BASE_URL_FALLBACK", base_url)
        fallback_api_key = os.getenv("LLM_API_KEY_FALLBACK", api_key)
        fallback_x_api_key = os.getenv("LLM_X_API_KEY_FALLBACK", x_api_key)
        fallback = build_raw_chat_model(
            model_name=profile.fallback_model,
            base_url=fallback_base_url,
            api_key=fallback_api_key,
            x_api_key=fallback_x_api_key,
            temperature=profile.temperature,
            timeout=profile.timeout_seconds,
            max_tokens=profile.max_tokens,
        )

    return primary, fallback


def build_chat_model(profile: ModelProfile) -> ChatModel:
    """Build a complete ChatModel with failover logging and failure boundary wrapping."""
    primary, fallback = build_pair(profile)
    return RunnableChatModel(
        profile=profile,
        primary_model=primary,
        fallback_model=fallback,
    )
