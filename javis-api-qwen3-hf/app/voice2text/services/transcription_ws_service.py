import asyncio
import base64
import json
import time
from typing import Optional

import numpy as np
import torch
from fastapi import WebSocket, WebSocketDisconnect

from app.common.logging import get_logger
from app.voice2text.constants.config import (
    DEFAULT_SPEAKER_ID,
    MAX_CONCURRENT_SESSIONS,
    SAMPLES_PER_MS,
)
from app.voice2text.schemas.soniox_schemas import (
    SonioxSegment,
    WsFinalResponse,
    WsPartialResponse,
    WsPingResponse,
    WsReadyResponse,
    WsSessionStoppedResponse,
)
from app.voice2text.services.hf_engine import HFEngine

logger = get_logger(__name__)

# Global semaphore to cap concurrent sessions
_session_semaphore = asyncio.Semaphore(MAX_CONCURRENT_SESSIONS)


class NoDiarizationStreamSession:
    """Manages one WebSocket transcription session (no speaker diarization)."""

    def __init__(self, websocket: WebSocket) -> None:
        self.websocket: WebSocket = websocket
        self.engine: HFEngine = HFEngine.get_instance()
        self.vad_iterator = self.engine.create_vad_iterator()
        
        self.audio_buffer = bytearray()
        self.vad_buffer = bytearray()
        self.is_speaking = False
        self.is_transcribing = False
        self.last_transcribed_bytes = 0
        self.segment_id = 1
        self.next_segment_to_send = 1
        self.accumulated_offset_ms = 0
        self.transcribe_tasks = []
        
        # Max segment ~ 29s
        self.MAX_SEGMENT_BYTES = 16000 * 2 * 29

        self._running: bool = True
        self._ping_task: Optional[asyncio.Task] = None

    async def handle(self) -> None:
        """Full lifecycle: accept -> ready -> stream -> session_stopped -> close."""
        if _session_semaphore._value <= 0:
            await self.websocket.accept()
            await self._send_json(
                {"type": "error", "code": "WS_ERR_CAPACITY_FULL", "message": "Server at capacity"}
            )
            await self.websocket.close(code=1013)
            return

        async with _session_semaphore:
            await self.websocket.accept()
            await self._send_model(WsReadyResponse())
            self._ping_task = asyncio.create_task(self._ping_loop())

            try:
                while self._running:
                    message = await self.websocket.receive()
                    if message.get("type") == "websocket.disconnect":
                        break
                    if "bytes" in message and message["bytes"]:
                        await self._process_audio(message["bytes"])
                    elif "text" in message and message["text"]:
                        await self._handle_text_message(message["text"])
            except WebSocketDisconnect:
                logger.info("Client disconnected.")
            except Exception:
                logger.exception("Unexpected error in WebSocket session")
            finally:
                self._running = False
                if self._ping_task:
                    self._ping_task.cancel()
                self._flush_buffer()
                if self.transcribe_tasks:
                    await asyncio.gather(*self.transcribe_tasks, return_exceptions=True)
                await self._send_model(WsSessionStoppedResponse())
                try:
                    await self.websocket.close()
                except Exception:
                    pass

    async def _process_audio(self, pcm_chunk: bytes) -> None:
        """Process incoming raw PCM 16kHz 16-bit bytes."""
        if not self.is_speaking and len(self.audio_buffer) >= 16000 * 2:
            # Keep only the last 0.5s to provide context when speech starts
            self.audio_buffer = self.audio_buffer[-(16000):]

        self.audio_buffer.extend(pcm_chunk)
        self.vad_buffer.extend(pcm_chunk)

        # Safety cap: force-cut at MAX_SEGMENT_BYTES regardless of VAD
        if len(self.audio_buffer) >= self.MAX_SEGMENT_BYTES:
            logger.info(f"[VAD] FORCE CUT at {len(self.audio_buffer)/(16000*2):.1f}s (safety cap)")
            self._flush_buffer()
            return

        # Process VAD in 512-sample chunks (1024 bytes)
        while len(self.vad_buffer) >= 1024:
            vad_chunk_bytes = self.vad_buffer[:1024]
            self.vad_buffer = self.vad_buffer[1024:]

            arr = np.frombuffer(vad_chunk_bytes, dtype=np.int16).astype(np.float32) / 32768.0
            tensor = torch.from_numpy(arr)

            speech_dict = self.vad_iterator(tensor, return_seconds=False)
            if speech_dict:
                if 'start' in speech_dict:
                    self.is_speaking = True
                elif 'end' in speech_dict:
                    logger.debug(f"[VAD] Speech END -> transcribing {len(self.audio_buffer)/(16000*2):.1f}s")
                    self._flush_buffer()

        if self.is_speaking and (len(self.audio_buffer) - self.last_transcribed_bytes >= 16000):
            asyncio.create_task(self._do_partial())

    async def _do_partial(self):
        if self.is_transcribing or len(self.audio_buffer) == 0:
            return
        self.is_transcribing = True
        buf = bytes(self.audio_buffer)
        self.last_transcribed_bytes = len(buf)
        current_seg = self.segment_id
        try:
            await self._transcribe_buffer(buf, is_final=False, target_segment_id=current_seg)
        finally:
            self.is_transcribing = False

    def _flush_buffer(self):
        if len(self.audio_buffer) > 0:
            buf = bytes(self.audio_buffer)
            current_seg = self.segment_id
            self.segment_id += 1
            task = asyncio.create_task(self._transcribe_buffer(buf, is_final=True, target_segment_id=current_seg))
            self.transcribe_tasks.append(task)
            
        self.audio_buffer.clear()
        self.is_speaking = False
        self.last_transcribed_bytes = 0
        self.vad_iterator.reset_states()

    async def _transcribe_buffer(self, pcm_bytes: bytes, is_final: bool = False, target_segment_id: int = 0):
        # Run inference in a background thread to unblock event loop
        text = await asyncio.to_thread(self.engine.generate_text, pcm_bytes)
        
        duration_ms = int(len(pcm_bytes) / 2 / SAMPLES_PER_MS)

        if is_final:
            while self.next_segment_to_send < target_segment_id:
                await asyncio.sleep(0.05)
            
            if text:
                # Soniox logic: emit empty partial first, then emit final
                await self._send_model(WsPartialResponse(text=""))
                
                segment = SonioxSegment(
                    text=text,
                    speaker_id=DEFAULT_SPEAKER_ID,
                    offset=self.accumulated_offset_ms,
                    duration=duration_ms,
                )
                await self._send_model(WsFinalResponse(segments=[segment]))
                
                # Accumulate offset only on valid final segments
                self.accumulated_offset_ms += duration_ms

            self.next_segment_to_send += 1
        else:
            if text:
                if target_segment_id == self.segment_id and target_segment_id >= self.next_segment_to_send:
                    await self._send_model(WsPartialResponse(text=text))

    async def _handle_text_message(self, text: str) -> None:
        """Handle client JSON messages (e.g. pong, time_start)."""
        try:
            msg = json.loads(text)
        except json.JSONDecodeError:
            return

        msg_type = msg.get("type")
        if msg_type == "pong":
            return
        if msg_type == "ping":
            ts = msg.get("ts", int(time.time() * 1000))
            await self._send_json({"type": "pong", "ts": ts})
        elif msg_type == "input_audio_buffer.append":
            b64_audio = msg.get("audio", "")
            if b64_audio:
                pcm_chunk = base64.b64decode(b64_audio)
                await self._process_audio(pcm_chunk)
        elif msg_type == "input_audio_buffer.commit":
            self._flush_buffer()
        elif msg_type == "input_audio_buffer.clear":
            self.audio_buffer.clear()
            self.vad_buffer.clear()
            self.is_speaking = False
            self.vad_iterator.reset_states()

    async def _ping_loop(self) -> None:
        """Send periodic pings to keep the connection alive."""
        try:
            while self._running:
                await asyncio.sleep(30)
                ts = int(time.time() * 1000)
                await self._send_model(WsPingResponse(ts=ts))
        except asyncio.CancelledError:
            pass

    async def _send_model(self, model) -> None:
        """Send a Pydantic model as JSON text, swallowing errors on closed sockets."""
        try:
            await self.websocket.send_text(model.model_dump_json(exclude_none=True))
        except Exception:
            self._running = False

    async def _send_json(self, obj: dict) -> None:
        """Send a raw dict as JSON text."""
        try:
            await self.websocket.send_text(json.dumps(obj, ensure_ascii=False))
        except Exception:
            self._running = False
