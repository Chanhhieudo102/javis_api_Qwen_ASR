from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage


def build_chat_messages(
    system_prompt: str,
    user_message: str,
) -> list[BaseMessage]:
    """Render a single turn prompt with system instruction and user input for the model."""
    return [
        SystemMessage(content=system_prompt),
        HumanMessage(content=user_message),
    ]
