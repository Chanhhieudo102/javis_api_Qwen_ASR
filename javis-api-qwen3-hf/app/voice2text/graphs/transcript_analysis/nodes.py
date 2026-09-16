from langchain_core.runnables import RunnableConfig

from app.agent.clients.chat_model import ChatModel
from app.agent.utils.chat_request import build_chat_messages
from app.voice2text.graphs.transcript_analysis.helpers import (
    build_punctuate_prompt,
    build_summarize_prompt,
    parse_summary_and_actions,
)
from app.voice2text.graphs.transcript_analysis.state import TranscriptAnalysisState


class TranscriptAnalysisCleanPunctuateNode:
    """Class node that cleans, punctuates, and normalizes raw ASR transcript."""

    def __init__(self, model: ChatModel, system_prompt: str) -> None:
        self.model = model
        self.system_prompt = system_prompt

    async def work(self, state: TranscriptAnalysisState, config: RunnableConfig) -> dict:
        user_prompt = build_punctuate_prompt(
            raw_transcript=state["raw_transcript"],
            language=state.get("language", "Japanese"),
        )
        messages = build_chat_messages(
            system_prompt=self.system_prompt,
            user_message=user_prompt,
        )
        reply = await self.model.ainvoke(messages, config=config)
        cleaned_text = reply.content if hasattr(reply, "content") else str(reply)
        return {"cleaned_transcript": cleaned_text.strip()}


class TranscriptAnalysisSummarizeNode:
    """Class node that summarizes conversation and extracts action items."""

    def __init__(self, model: ChatModel, system_prompt: str) -> None:
        self.model = model
        self.system_prompt = system_prompt

    async def work(self, state: TranscriptAnalysisState, config: RunnableConfig) -> dict:
        user_prompt = build_summarize_prompt(
            cleaned_transcript=state.get("cleaned_transcript", state["raw_transcript"]),
            language=state.get("language", "Japanese"),
        )
        messages = build_chat_messages(
            system_prompt=self.system_prompt,
            user_message=user_prompt,
        )
        reply = await self.model.ainvoke(messages, config=config)
        raw_text = reply.content if hasattr(reply, "content") else str(reply)
        summary, action_items = parse_summary_and_actions(raw_text)
        return {
            "summary": summary,
            "action_items": action_items,
        }
