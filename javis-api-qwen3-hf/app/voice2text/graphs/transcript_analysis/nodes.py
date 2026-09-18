from langchain_core.runnables import RunnableConfig

from app.agent.nodes import BaseChatNode
from app.agent.utils.chat_request import build_chat_messages
from app.voice2text.graphs.transcript_analysis.helpers import (
    build_punctuate_prompt,
    build_summarize_prompt,
    parse_summary_and_actions,
)
from app.voice2text.graphs.transcript_analysis.state import TranscriptAnalysisState

DEFAULT_TRANSCRIPT_LANGUAGE: str = "Japanese"


class TranscriptAnalysisCleanPunctuateNode(BaseChatNode):
    """Class node that cleans, punctuates, and normalizes raw ASR transcript."""

    async def work(self, state: TranscriptAnalysisState, config: RunnableConfig) -> dict:
        """Clean and punctuate raw transcript text using ChatModel."""
        user_prompt = build_punctuate_prompt(
            raw_transcript=state["raw_transcript"],
            language=state.get("language", DEFAULT_TRANSCRIPT_LANGUAGE),
        )
        messages = build_chat_messages(
            system_prompt=self.system_prompt,
            user_message=user_prompt,
        )
        reply = await self.model.ainvoke(messages, config=config)
        cleaned_text = reply.content if hasattr(reply, "content") else str(reply)
        return {"cleaned_transcript": cleaned_text.strip()}


class TranscriptAnalysisSummarizeNode(BaseChatNode):
    """Class node that summarizes conversation and extracts action items."""

    async def work(self, state: TranscriptAnalysisState, config: RunnableConfig) -> dict:
        """Summarize conversation and extract action items from cleaned transcript."""
        user_prompt = build_summarize_prompt(
            cleaned_transcript=state.get("cleaned_transcript", state["raw_transcript"]),
            language=state.get("language", DEFAULT_TRANSCRIPT_LANGUAGE),
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
