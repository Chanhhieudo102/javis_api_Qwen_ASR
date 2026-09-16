from typing import TypedDict


class TranscriptAnalysisInput(TypedDict):
    """Input payload accepted by Transcript Analysis Graph."""

    raw_transcript: str
    language: str


class TranscriptAnalysisState(TypedDict):
    """Internal state maintained across graph nodes."""

    raw_transcript: str
    language: str
    cleaned_transcript: str
    summary: str
    action_items: list[str]


class TranscriptAnalysisOutput(TypedDict):
    """Public output schema returned to caller (scratch fields excluded)."""

    cleaned_transcript: str
    summary: str
    action_items: list[str]
