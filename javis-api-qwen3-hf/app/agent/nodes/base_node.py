from app.agent.clients.chat_model import ChatModel


class BaseChatNode:
    """Base class for LangGraph nodes invoking a chat model with system prompt."""

    def __init__(self, model: ChatModel, system_prompt: str) -> None:
        """Initialize node with ChatModel and system prompt configuration."""
        self.model = model
        self.system_prompt = system_prompt
