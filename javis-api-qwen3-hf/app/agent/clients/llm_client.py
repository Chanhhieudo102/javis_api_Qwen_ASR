from langchain_core.language_models.chat_models import BaseChatModel
from langchain_openai import ChatOpenAI


def build_raw_chat_model(
    model_name: str,
    base_url: str,
    api_key: str,
    temperature: float = 0.0,
    timeout: float = 60.0,
    max_tokens: int | None = None,
) -> BaseChatModel:
    """Build a raw, single upstream ChatModel without failovers."""
    return ChatOpenAI(
        model=model_name,
        base_url=base_url,
        api_key=api_key,
        temperature=temperature,
        timeout=timeout,
        max_tokens=max_tokens,
    )
