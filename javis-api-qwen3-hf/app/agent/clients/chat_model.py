from typing import Any, Protocol, runtime_checkable

from langchain_core.messages import BaseMessage
from langchain_core.runnables import RunnableConfig


@runtime_checkable
class ChatModel(Protocol):
    """Protocol for async chat models consumed by LangGraph nodes and services."""

    async def ainvoke(
        self,
        input: list[BaseMessage] | str,
        config: RunnableConfig | None = None,
        **kwargs: Any,
    ) -> BaseMessage:
        """Invoke chat model asynchronously."""
        ...
