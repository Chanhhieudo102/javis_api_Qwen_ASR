from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.common.logging import get_logger
from app.voice2text.services.transcription_ws_service import NoDiarizationStreamSession

from app.common.schemas.data_response import DataResponseAPI
from app.voice2text.schemas.transcript_analysis_schemas import TranscriptAnalysisRequest
from app.voice2text.services.transcript_analysis_graph_service import (
    TranscriptAnalysisGraphService,
)

logger = get_logger(__name__)

router = APIRouter()

@router.get("/transcript/health", tags=["voice2text"])
async def health_check() -> dict:
    """HTTP Health check endpoint for STT API."""
    return {"status": "ok", "message": "Qwen3-ASR Realtime WebSocket Server is running!"}

@router.post("/transcript/analyze", tags=["voice2text"])
async def analyze_transcript(
    request: TranscriptAnalysisRequest,
) -> dict:
    """Analyze, clean, and summarize an ASR transcript using LangGraph."""
    result = await TranscriptAnalysisGraphService.analyze(request)
    return DataResponseAPI.success(data=result.model_dump())

@router.websocket("/transcript/ws/no-diarization")
async def websocket_no_diarization(websocket: WebSocket) -> None:
    session = NoDiarizationStreamSession(websocket)
    try:
        await session.handle()
    except WebSocketDisconnect:
        logger.info("Client disconnected from /no-diarization.")
    except Exception:
        logger.exception("Unhandled error in WebSocket route.")
