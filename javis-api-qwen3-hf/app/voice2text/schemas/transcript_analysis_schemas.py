from pydantic import BaseModel, Field


class TranscriptAnalysisRequest(BaseModel):
    """Request payload to analyze an ASR transcript."""

    raw_transcript: str = Field(..., description="Raw unpunctuated ASR transcript", min_length=1)
    language: str = Field(default="Japanese", description="Language of transcript (Japanese, Vietnamese, English)")
    session_id: str | None = Field(default=None, description="Optional caller session or task ID for tracing")


class TranscriptAnalysisResponse(BaseModel):
    """Cleaned transcript, summary, and action items output."""

    cleaned_transcript: str = Field(..., description="Cleaned and punctuated transcript")
    summary: str = Field(..., description="Concise summary of the transcript")
    action_items: list[str] = Field(default_factory=list, description="Extracted action items or next steps")
