from typing import List, Optional

from pydantic import BaseModel, ConfigDict

from app.voice2text.constants.events import TranscriptionWsServerEvent


class _WsBaseModel(BaseModel):
    """Base for all WebSocket response models — always serialize enums as raw values."""

    model_config = ConfigDict(use_enum_values=True)


class SonioxSegment(_WsBaseModel):
    text: str
    speaker_id: str
    offset: int
    duration: int


class WsReadyResponse(_WsBaseModel):
    type: TranscriptionWsServerEvent = TranscriptionWsServerEvent.READY
    message: str = "Ready to receive audio"


class WsPartialResponse(_WsBaseModel):
    type: TranscriptionWsServerEvent = TranscriptionWsServerEvent.PARTIAL
    text: str
    speaker_id: Optional[str] = None


class WsFinalResponse(_WsBaseModel):
    type: TranscriptionWsServerEvent = TranscriptionWsServerEvent.FINAL
    segments: List[SonioxSegment]


class WsErrorResponse(_WsBaseModel):
    type: TranscriptionWsServerEvent = TranscriptionWsServerEvent.ERROR
    code: str
    message: str


class WsTurnEndResponse(_WsBaseModel):
    type: TranscriptionWsServerEvent = TranscriptionWsServerEvent.TURN_END
    reason: str
    primary_speaker_id: Optional[str] = None
    detected_speaker_id: Optional[str] = None
    last_word_end_ms: Optional[int] = None
    silence_ms: Optional[int] = None


class WsSessionStoppedResponse(_WsBaseModel):
    type: TranscriptionWsServerEvent = TranscriptionWsServerEvent.SESSION_STOPPED
    message: str = "Session ended"
    title: Optional[str] = None
    title_source: Optional[str] = None


class WsPingResponse(_WsBaseModel):
    type: TranscriptionWsServerEvent = TranscriptionWsServerEvent.PING
    ts: int

