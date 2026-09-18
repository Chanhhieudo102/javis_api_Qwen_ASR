import asyncio
import base64
import json
import re
import time
from typing import ClassVar, Optional, Set

import numpy as np
import torch
from fastapi import WebSocket, WebSocketDisconnect
from starlette.websockets import WebSocketState

from app.common.logging import get_logger
from app.voice2text.constants.config import (
    DEFAULT_SPEAKER_ID,
    MAX_CONCURRENT_SESSIONS,
    SAMPLES_PER_MS,
)
from app.voice2text.constants.dsp_constants import DSPConstants
from app.voice2text.schemas.soniox_schemas import (
    SonioxSegment,
    WsFinalResponse,
    WsPartialResponse,
    WsPingResponse,
    WsReadyResponse,
    WsSessionStoppedResponse,
)
from app.voice2text.services.hf_engine import HFEngine
from app.voice2text.services.japanese_itn_service import JapaneseITNService

logger = get_logger(__name__)

# Global semaphore to cap concurrent sessions
_session_semaphore = asyncio.Semaphore(MAX_CONCURRENT_SESSIONS)

# Precompiled pattern for punctuation and whitespace removal
_PUNCTUATION_AND_WHITESPACE_PATTERN: re.Pattern = re.compile(
    r"[\s\u3000、。・！？!?,.\-—~～]+"
)

# Common short hallucination phrases triggered by non-speech noise
_SHORT_AUDIO_HALLUCINATIONS: Set[str] = frozenset({"釣り", "つり"})


def _pcm_to_float_array(pcm_bytes: bytes) -> np.ndarray:
    """Convert 16-bit PCM byte buffer to normalized float32 array [-1.0, 1.0]."""
    if not pcm_bytes:
        return np.empty(0, dtype=np.float32)
    return np.frombuffer(pcm_bytes, dtype=np.int16).astype(np.float32) / DSPConstants.PCM16_MAX_AMPLITUDE


def _calculate_rms(float_arr: np.ndarray) -> float:
    """Calculate Root Mean Square (RMS) energy of an audio sample array."""
    return float(np.sqrt(np.mean(float_arr ** 2))) if len(float_arr) > 0 else 0.0


def _bytes_to_duration_sec(byte_count: int) -> float:
    """Convert raw PCM16 byte length to duration in seconds at target sample rate."""
    return byte_count / (DSPConstants.TARGET_SAMPLE_RATE * DSPConstants.BYTES_PER_SAMPLE)


def _duration_sec_to_bytes(seconds: float) -> int:
    """Convert duration in seconds to raw PCM16 byte length at target sample rate."""
    return int(seconds * DSPConstants.TARGET_SAMPLE_RATE * DSPConstants.BYTES_PER_SAMPLE)


class NoDiarizationStreamSession:
    """Manages one WebSocket transcription session (no speaker diarization)."""

    def __init__(self, websocket: WebSocket) -> None:
        self.websocket: WebSocket = websocket
        self.engine: HFEngine = HFEngine.get_instance()
        self.vad_iterator = self.engine.create_vad_iterator()

        self.audio_buffer = bytearray()
        self.vad_buffer = bytearray()

        self.is_speaking: bool = False
        self.is_transcribing: bool = False
        self.last_transcribed_bytes: int = 0
        self.accumulated_offset_ms: int = 0
        self.segment_id: int = 1
        self.next_segment_to_send: int = 1
        self.transcribe_tasks: list[asyncio.Task] = []

        self.max_segment_bytes: int = _duration_sec_to_bytes(DSPConstants.MAX_SEGMENT_SECONDS)
        self.preroll_bytes: int = _duration_sec_to_bytes(DSPConstants.VAD_PREROLL_SEC)

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
                if self.websocket.client_state == WebSocketState.CONNECTED:
                    await self._send_model(WsSessionStoppedResponse())
                    try:
                        await self.websocket.close()
                    except Exception:
                        pass

    async def _process_audio(self, pcm_chunk: bytes) -> None:
        """Process incoming raw PCM 16kHz 16-bit bytes."""
        if not self.is_speaking and len(self.audio_buffer) >= self.preroll_bytes:
            # Keep VAD_PREROLL_SEC of audio context to avoid swallowing sentence-initial sounds
            self.audio_buffer = self.audio_buffer[-self.preroll_bytes:]

        self.audio_buffer.extend(pcm_chunk)
        self.vad_buffer.extend(pcm_chunk)

        # Safety cap: force-cut at max_segment_bytes regardless of VAD
        if len(self.audio_buffer) >= self.max_segment_bytes:
            duration = _bytes_to_duration_sec(len(self.audio_buffer))
            logger.info(f"[VAD] FORCE CUT at {duration:.1f}s (safety cap)")
            self._flush_buffer()
            return

        # Process VAD in fixed chunk size
        vad_frame_bytes = DSPConstants.VAD_FRAME_BYTES
        while len(self.vad_buffer) >= vad_frame_bytes:
            vad_chunk_bytes = self.vad_buffer[:vad_frame_bytes]
            self.vad_buffer = self.vad_buffer[vad_frame_bytes:]

            arr = _pcm_to_float_array(vad_chunk_bytes)
            tensor = torch.from_numpy(arr)

            speech_dict = self.vad_iterator(tensor, return_seconds=False)
            if speech_dict:
                if "start" in speech_dict:
                    self.is_speaking = True
                elif "end" in speech_dict:
                    duration = _bytes_to_duration_sec(len(self.audio_buffer))
                    logger.debug(f"[VAD] Speech END -> transcribing {duration:.1f}s")
                    self._flush_buffer()

        # Emit partial if speaking and buffer increased significantly
        bytes_threshold = DSPConstants.TARGET_SAMPLE_RATE  # ~0.5s of audio
        if self.is_speaking and (len(self.audio_buffer) - self.last_transcribed_bytes >= bytes_threshold):
            asyncio.create_task(self._do_partial())

    async def _do_partial(self) -> None:
        """Execute a partial speculative transcription pass."""
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

    def _is_speech_eligible(self, duration_sec: float, rms: float) -> bool:
        """Evaluate if the buffered audio meets minimum duration and energy thresholds."""
        has_min_duration = duration_sec >= DSPConstants.MIN_SPEECH_DURATION_SEC
        has_speech_energy = rms >= DSPConstants.MIN_SPEECH_RMS
        is_confirmed_or_loud = self.is_speaking or (rms >= DSPConstants.MIN_UNCONFIRMED_SPEECH_RMS)
        return has_min_duration and has_speech_energy and is_confirmed_or_loud

    def _flush_buffer(self) -> None:
        """Flush audio buffer and initiate final transcription if speech is confirmed."""
        if len(self.audio_buffer) > 0:
            buf = bytes(self.audio_buffer)
            float_arr = _pcm_to_float_array(buf)
            rms = _calculate_rms(float_arr)
            buf_duration_sec = _bytes_to_duration_sec(len(buf))

            if self._is_speech_eligible(buf_duration_sec, rms):
                current_seg = self.segment_id
                self.segment_id += 1
                task = asyncio.create_task(
                    self._transcribe_buffer(buf, is_final=True, target_segment_id=current_seg)
                )
                self.transcribe_tasks.append(task)
            else:
                logger.debug(
                    f"[VAD] Dropped silence/noise tail: {buf_duration_sec:.2f}s, RMS={rms:.4f}"
                )

        self.audio_buffer.clear()
        self.is_speaking = False
        self.last_transcribed_bytes = 0
        self.vad_iterator.reset_states()

    async def _transcribe_buffer(
        self, pcm_bytes: bytes, is_final: bool = False, target_segment_id: int = 0
    ) -> None:
        """Run ASR model inference, post-process text, and send responses."""
        text = await asyncio.to_thread(self.engine.generate_text, pcm_bytes)
        if text:
            text = JapaneseITNService.normalize(text)
            stripped = _PUNCTUATION_AND_WHITESPACE_PATTERN.sub("", text)
            duration_sec = _bytes_to_duration_sec(len(pcm_bytes))

            # Discard empty/punctuation-only segments or common short hallucination triggers
            if not stripped:
                text = ""
            elif (
                stripped in _SHORT_AUDIO_HALLUCINATIONS
                and duration_sec < DSPConstants.SHORT_AUDIO_HALLUCINATION_SEC
            ):
                text = ""

        duration_ms = int(len(pcm_bytes) / 2 / SAMPLES_PER_MS)

        if is_final:
            while self.next_segment_to_send < target_segment_id:
                await asyncio.sleep(DSPConstants.SEGMENT_ORDER_POLL_INTERVAL_SEC)

            if text:
                # Soniox protocol: emit empty partial first, then final segment
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
            if text and target_segment_id == self.segment_id and target_segment_id >= self.next_segment_to_send:
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
            is_final = msg.get("final", False)
            self._flush_buffer()
            if is_final:
                if self.transcribe_tasks:
                    await asyncio.gather(*self.transcribe_tasks, return_exceptions=True)
                if self.websocket.client_state == WebSocketState.CONNECTED:
                    await self._send_model(WsSessionStoppedResponse())
        elif msg_type == "input_audio_buffer.clear":
            self.audio_buffer.clear()
            self.vad_buffer.clear()
            self.is_speaking = False
            self.vad_iterator.reset_states()

    async def _ping_loop(self) -> None:
        """Send periodic pings to keep the connection alive."""
        try:
            while self._running:
                await asyncio.sleep(DSPConstants.PING_INTERVAL_SEC)
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
