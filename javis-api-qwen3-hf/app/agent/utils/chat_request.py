from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage


def build_chat_messages(
    system_prompt: str,
    user_message: str,
    history: list[BaseMessage] | None = None,
) -> list[BaseMessage]:
    """Render a conversation turn with system prompt and history for the model."""
    messages: list[BaseMessage] = [SystemMessage(content=system_prompt)]
    if history:
        messages.extend(history)
    messages.append(HumanMessage(content=user_message))
    return messages


def format_ai_message(content: str) -> AIMessage:
    """Helper to wrap string as an AIMessage."""
    return AIMessage(content=content)
