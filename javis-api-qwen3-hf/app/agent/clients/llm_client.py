from langchain_core.language_models.chat_models import BaseChatModel
from langchain_openai import ChatOpenAI


def build_raw_chat_model(
    model_name: str,
    base_url: str,
    api_key: str,
    x_api_key: str | None = None,
    temperature: float = 0.0,
    timeout: float = 60.0,
    max_tokens: int | None = None,
) -> BaseChatModel:
    """Build a raw, single upstream ChatModel without failovers."""
    default_headers: dict[str, str] | None = None
    if x_api_key:
        default_headers = {"x-api-key": x_api_key}

    return ChatOpenAI(
        model=model_name,
        base_url=base_url,
        api_key=api_key,
        default_headers=default_headers,
        temperature=temperature,
        timeout=timeout,
        max_tokens=max_tokens,
    )
