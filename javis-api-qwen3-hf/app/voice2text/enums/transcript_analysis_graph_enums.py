from enum import StrEnum


class TranscriptAnalysisNodeName(StrEnum):
    """Node names for the Transcript Analysis LangGraph."""

    CLEAN_PUNCTUATE = "clean_punctuate"
    SUMMARIZE_ACTIONS = "summarize_actions"
