from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.common.logging import get_logger
from app.voice2text.services.transcription_ws_service import NoDiarizationStreamSession

logger = get_logger(__name__)

router = APIRouter()

@router.get("/transcript/health", tags=["voice2text"])
async def health_check() -> dict:
    """HTTP Health check endpoint for STT API."""
    return {"status": "ok", "message": "Qwen3-ASR Realtime WebSocket Server is running!"}

@router.websocket("/transcript/ws/no-diarization")
async def websocket_no_diarization(websocket: WebSocket) -> None:
    session = NoDiarizationStreamSession(websocket)
    try:
        await session.handle()
    except WebSocketDisconnect:
        logger.info("Client disconnected from /no-diarization.")
    except Exception:
        logger.exception("Unhandled error in WebSocket route.")
