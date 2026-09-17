# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: Copyright contributors to the vLLM project
import sys
import time
import argparse
import asyncio
import json
import queue
import re
import threading
import logging
from typing import Optional

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding='utf-8')
        sys.stderr.reconfigure(encoding='utf-8')
    except Exception:
        pass
    # Sử dụng SelectorEventLoopPolicy trên Windows để tránh lỗi Proactor crash [WinError 10054] khi remote host ngắt kết nối
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

import gradio as gr
import gradio.processing_utils as gpu
import numpy as np
import os
import pybase64 as base64
import websockets

# Tự động nạp ffmpeg từ imageio_ffmpeg vào PATH để hỗ trợ đọc mọi định dạng audio (.mp3, .wav, .m4a, .flac, .ogg, v.v.)
try:
    import imageio_ffmpeg
    ffmpeg_bin_dir = os.path.dirname(imageio_ffmpeg.get_ffmpeg_exe())
    if ffmpeg_bin_dir not in os.environ.get("PATH", ""):
        os.environ["PATH"] = ffmpeg_bin_dir + os.pathsep + os.environ.get("PATH", "")
except Exception:
    pass

def load_any_audio(file_path: str) -> np.ndarray:
    """Load any audio format (.mp3, .wav, .m4a, .flac, .ogg, .aac, .webm, etc.) and convert to 16kHz mono float32."""
    try:
        import soundfile as sf
        data, sr = sf.read(file_path)
        audio_data = data.astype(np.float32)
        if len(audio_data.shape) > 1:
            audio_data = audio_data.mean(axis=1)

        target_sr = 16000
        if sr != target_sr:
            num_target_samples = int(len(audio_data) * target_sr / sr)
            audio_data = np.interp(
                np.linspace(0, len(audio_data) - 1, num_target_samples),
                np.arange(len(audio_data)),
                audio_data
            )
        return np.clip(audio_data, -1.0, 1.0)
    except Exception as sf_err:
        import subprocess
        try:
            import imageio_ffmpeg
            ffmpeg_exe = imageio_ffmpeg.get_ffmpeg_exe()
            cmd = [
                ffmpeg_exe, "-i", file_path,
                "-f", "s16le", "-ac", "1", "-ar", "16000",
                "-loglevel", "error", "-"
            ]
            proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            out, _ = proc.communicate()
            if proc.returncode == 0 and len(out) > 0:
                audio_data = np.frombuffer(out, dtype=np.int16).astype(np.float32) / 32767.0
                return np.clip(audio_data, -1.0, 1.0)
        except Exception:
            pass
        raise RuntimeError(f"Không thể đọc file âm thanh {file_path}: {sf_err}")

# Monkey-patch Gradio & pydub để hỗ trợ mọi định dạng audio và microphone streaming không bị crash do thiếu ffprobe trên Windows
_orig_audio_is_playable = gpu.audio_is_playable
def _safe_audio_is_playable(audio_filepath: str) -> bool:
    try:
        return _orig_audio_is_playable(audio_filepath)
    except Exception:
        suffix = os.path.splitext(str(audio_filepath))[1].lower()
        return suffix in ('.mp3', '.wav', '.ogg', '.m4a', '.aac', '.flac', '.wma', '.webm')
gpu.audio_is_playable = _safe_audio_is_playable

_orig_audio_from_file = getattr(gpu, "audio_from_file", None)
def _safe_audio_from_file(filename: str, crop_min: float = 0, crop_max: float = 100):
    try:
        data = load_any_audio(filename)
        pcm16 = (data * 32767).astype(np.int16)
        return 16000, pcm16
    except Exception:
        if _orig_audio_from_file is not None:
            return _orig_audio_from_file(filename, crop_min, crop_max)
        raise
gpu.audio_from_file = _safe_audio_from_file

try:
    import pydub.utils
    pydub.utils.get_prober_name = lambda: imageio_ffmpeg.get_ffmpeg_exe()
    pydub.AudioSegment.converter = imageio_ffmpeg.get_ffmpeg_exe()
except Exception:
    pass

try:
    from audio_enhancement_04 import get_pipeline, EnhancementPipeline
except ImportError:
    class EnhancementPipeline:
        def run(self, chunk, sr=16000):
            return chunk

    def get_pipeline(name="none"):
        return None

# ==========================================
# 0. CẤU HÌNH LOGGING GHI RA FILE JSON
# ==========================================
class JsonFormatter(logging.Formatter):
    """Custom Formatter để parse log record thành định dạng JSON."""
    def format(self, record):
        log_record = {
            "timestamp": self.formatTime(record, self.datefmt) + f".{int(record.msecs):03d}",
            "level": record.levelname.strip(),
            "thread": record.threadName,
            "message": record.getMessage()
        }
        if record.exc_info:
            log_record["exception"] = self.formatException(record.exc_info)
        return json.dumps(log_record, ensure_ascii=False)

# Khởi tạo Logger
logger = logging.getLogger("MicClient")
logger.setLevel(logging.INFO)
logger.propagate = False     

file_handler = logging.FileHandler("client_logs.jsonl", mode='a', encoding="utf-8")
file_handler.setFormatter(JsonFormatter(datefmt="%Y-%m-%d %H:%M:%S"))
logger.addHandler(file_handler)

SAMPLE_RATE = 16_000
TARGET_CHUNK_SAMPLES = 320
internal_audio_buffer = np.array([], dtype=np.float32)

CHOUON_PATTERN = re.compile(r'ー{2,}')

def normalize_chouon(text: str) -> str:
    """Collapse redundant long vowel marks (e.g. バール→バル)."""
    return CHOUON_PATTERN.sub('ー', text)

# Global state
audio_queue: queue.Queue = queue.Queue()
transcription_text = ""
partial_text = ""
is_running = False
ws_url = ""
model = ""
connection_status = "⚪ Sẵn sàng. Nhấn Start để bắt đầu."

chosen_pipeline_strategy = "none"
dsp_pipeline: Optional[EnhancementPipeline] = None
transport_thread: Optional[threading.Thread] = None

def wait_for_session_close(timeout=4.0):
    """Ensure any previous WebSocket transport thread is completely stopped and closed."""
    global transport_thread, is_running
    is_running = False
    if transport_thread is not None and transport_thread.is_alive():
        logger.info("Đang chờ phiên WebSocket cũ đóng hoàn toàn...")
        transport_thread.join(timeout=timeout)
        if transport_thread.is_alive():
            logger.warning("Phiên WebSocket cũ đóng quá thời gian chờ!")
    transport_thread = None
    time.sleep(0.3)

async def websocket_handler():
    """Connect to WebSocket and handle audio streaming + transcription."""
    global transcription_text, partial_text, is_running, connection_status
    
    stop_event = asyncio.Event()
    max_retries = 6

    for attempt in range(max_retries):
        if not is_running:
            return

        connection_status = f"🟡 Đang kết nối tới server (thử lần {attempt + 1}/{max_retries})..."
        logger.info(f"Đang kết nối WebSocket tới: {ws_url} (lần {attempt + 1}/{max_retries})")

        try:
            async with websockets.connect(
                ws_url, 
                ping_interval=20, 
                ping_timeout=20, 
                open_timeout=30
            ) as ws:
                # 1. Handshake & Config
                init_msg = await ws.recv()
                logger.info(f"[RECV] Server Initial: {init_msg}")

                try:
                    init_data = json.loads(init_msg)
                    if init_data.get("type") == "error" and init_data.get("code") == "WS_ERR_CAPACITY_FULL":
                        if attempt < max_retries - 1:
                            logger.warning(f"Server đang bận giải phóng phiên cũ (Capacity full). Đợi 1.0s và thử lại ({attempt + 1}/{max_retries})...")
                            connection_status = f"🟡 Server đang bận giải phóng phiên cũ. Đợi thử lại ({attempt + 1}/{max_retries})..."
                            await asyncio.sleep(1.0)
                            continue
                        else:
                            connection_status = "🔴 Server đang bận phục vụ phiên khác (Capacity full)."
                            return
                except json.JSONDecodeError:
                    pass

                connection_status = "🟢 Đã kết nối WebSocket thành công! Đang lắng nghe âm thanh..."
                logger.info("Kết nối WebSocket thành công!")

                logger.info(f"[SEND] Gửi cấu hình Model: {model}")
                await ws.send(json.dumps({
                    "type": "session.update",
                    "model": model
                }))

                await ws.send(json.dumps({"type": "input_audio_buffer.commit"}))

                last_msg_time = time.time()

                async def send_audio():
                    nonlocal last_msg_time
                    chunk_count = 0
                    logger.info("[SEND] Bắt đầu luồng đẩy âm thanh liên tục...")
                    
                    while is_running or not audio_queue.empty():
                        try:
                            item = await asyncio.get_event_loop().run_in_executor(
                                None, lambda: audio_queue.get(timeout=0.1)
                            )
                            if isinstance(item, tuple):
                                chunk, is_silent = item
                            else:
                                chunk, is_silent = item, False

                            await ws.send(
                                json.dumps({"type": "input_audio_buffer.append", "audio": chunk})
                            )
                            chunk_count += 1
                            
                            if chunk_count % 50 == 0:
                                logger.debug(f"[SEND] Đang đẩy audio... (Đã gửi {chunk_count} chunks)")

                            await asyncio.sleep(0.005)
                        except queue.Empty:
                            continue
                            
                    logger.info("Phiên kết thúc hoặc Queue đã cạn. Gửi tín hiệu COMMIT (final=True) lên server...")
                    try:
                        await ws.send(json.dumps({"type": "input_audio_buffer.commit", "final": True}))
                    except Exception as e:
                        logger.warning(f"Không thể gửi commit: {e}")
                    
                    logger.info("Đang chờ server hoàn thành nhận diện toàn bộ các đoạn âm thanh...")
                    while not stop_event.is_set():
                        try:
                            await asyncio.wait_for(stop_event.wait(), timeout=2.5)
                            break
                        except asyncio.TimeoutError:
                            if time.time() - last_msg_time >= 4.0:
                                logger.info("Server đã nhận diện xong toàn bộ các đoạn âm thanh (hết dữ liệu).")
                                break

                    logger.info("[SEND] Đóng phiên WebSocket sạch sẽ để giải phóng GPU cho lần chạy tiếp theo.")
                    try:
                        await ws.close()
                    except Exception:
                        pass
                    logger.info("[SEND] Luồng đẩy âm thanh đã đóng.")

                async def receive_transcription():
                    nonlocal last_msg_time
                    global transcription_text, partial_text, connection_status
                    logger.info("[RECV] Bắt đầu luồng lắng nghe kết quả từ Server...")
                    
                    try:
                        async for message in ws:
                            last_msg_time = time.time()
                            data = json.loads(message)
                            msg_type = data.get("type", "unknown")

                            if msg_type in ("transcription.partial", "partial"):
                                partial_text = data.get("text", "")
                                logger.info(f"[PARTIAL] {partial_text}")
                                
                            elif msg_type in ("transcription.done", "final"):
                                text = ""
                                if msg_type == "final" and "segments" in data:
                                    text = " ".join([seg.get("text", "") for seg in data.get("segments", [])])
                                else:
                                    text = data.get("text", "")
                                    
                                if text:
                                    transcription_text += text + "\n"
                                    transcription_text = normalize_chouon(transcription_text)
                                partial_text = ""
                                logger.info(f"[DONE] Server chốt câu: {text}")
                                
                            elif msg_type == "error":
                                logger.error(f"[ERROR] Lỗi từ Server: {data.get('error', data)}")
                                stop_event.set()
                            elif msg_type in ("session_stopped", "stopped"):
                                logger.info("[EVENT] Server thông báo hoàn tất phiên.")
                                stop_event.set()
                    except (websockets.exceptions.ConnectionClosed, asyncio.CancelledError) as e:
                        logger.info(f"[RECV] WebSocket đóng: {e}")
                    except Exception as e:
                        logger.error(f"[RECV] Lỗi nhận tin nhắn: {e}")

                await asyncio.gather(send_audio(), receive_transcription(), return_exceptions=True)
                break  # Phiên hoàn thành thành công

        except websockets.exceptions.ConnectionClosed as cc:
            if getattr(cc, 'code', None) == 1013 and attempt < max_retries - 1:
                logger.warning(f"Server trả về code 1013 (Capacity Full). Đợi 1.0s và thử lại ({attempt + 1}/{max_retries})...")
                connection_status = f"🟡 Server đang bận giải phóng phiên cũ, đợi thử lại ({attempt + 1}/{max_retries})..."
                await asyncio.sleep(1.0)
                continue
            connection_status = f"🔴 Lỗi kết nối WebSocket: {cc}"
            logger.error(f"WebSocket closed: {cc}")
            break
        except Exception as e:
            if attempt < max_retries - 1 and is_running:
                logger.warning(f"Lỗi kết nối ({e}), đang thử lại ({attempt + 1}/{max_retries})...")
                await asyncio.sleep(1.0)
                continue
            connection_status = f"🔴 Lỗi kết nối WebSocket: {e}"
            logger.error(f"Bị lỗi ở WebSocket Handler: {e}", exc_info=True)
            break

    is_running = False
    if "🔴" not in connection_status:
        connection_status = "⚪ Đã ngắt kết nối. Bấm Start hoặc chọn file để bắt đầu lại."

def start_websocket():
    """Start WebSocket connection in background thread."""
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        loop.run_until_complete(websocket_handler())
    except (ConnectionResetError, websockets.exceptions.ConnectionClosed) as e:
        logger.warning(f"Kết nối WebSocket bị ngắt: {e}")
    except Exception as e:
        logger.error(f"Thread Error: {e}")
    finally:
        try:
            loop.close()
        except Exception:
            pass

def start_recording():
    """Start audio recording and streaming session."""
    global transcription_text, partial_text, dsp_pipeline, internal_audio_buffer, connection_status, is_running, transport_thread
    
    # Đảm bảo phiên cũ đã kết thúc và đóng kết nối hoàn toàn trước khi mở phiên mới
    wait_for_session_close(timeout=4.0)

    logger.info("NÚT START ĐƯỢC NHẤN. Đang khởi tạo...")
    connection_status = "🟡 Đang kết nối tới server Modal..."
    
    transcription_text = ""
    partial_text = ""
    internal_audio_buffer = np.array([], dtype=np.float32)

    while not audio_queue.empty():
        try:
            audio_queue.get_nowait()
        except Exception:
            break
        
    dsp_pipeline = get_pipeline(chosen_pipeline_strategy)
    logger.info(f"DSP Pipeline được chọn: {chosen_pipeline_strategy}")
    
    is_running = True
    transport_thread = threading.Thread(target=start_websocket, daemon=True, name="WSTransportThread")
    transport_thread.start()
    return gr.update(interactive=False), gr.update(interactive=True), ""

def stop_recording():
    """Stop the transcription service and flush remaining buffer."""
    global is_running, internal_audio_buffer, dsp_pipeline, connection_status
    if not is_running:
        logger.info("stop_recording được gọi nhưng phiên chưa chạy hoặc đã dừng.")
        return gr.update(interactive=True), gr.update(interactive=False), transcription_text

    logger.info("NÚT STOP ĐƯỢC NHẤN. Đang tiến hành xả (flush) buffer kẹt...")
    connection_status = "⏳ Đang xả buffer âm thanh và chờ kết quả từ server..."

    # 1. Bơm 150ms khoảng lặng (silence) vào để ép LookaheadBuffer nhả đoạn đuôi
    if dsp_pipeline is not None:
        lookahead_samples = int(150.0 / 1000.0 * SAMPLE_RATE) # 2400 samples
        silence_padding = np.zeros(lookahead_samples, dtype=np.float32)
        internal_audio_buffer = np.concatenate((internal_audio_buffer, silence_padding))

    # 2. Rút cạn toàn bộ buffer thành các chunk 512 mẫu để đẩy qua DSP và Queue
    while len(internal_audio_buffer) >= TARGET_CHUNK_SAMPLES:
        chunk_to_process = internal_audio_buffer[:TARGET_CHUNK_SAMPLES]
        internal_audio_buffer = internal_audio_buffer[TARGET_CHUNK_SAMPLES:]

        if dsp_pipeline is not None:
            chunk_to_process = dsp_pipeline.run(chunk_to_process, sr=SAMPLE_RATE)
            chunk_to_process = np.clip(chunk_to_process, -1.0, 1.0)

        if len(chunk_to_process) == 0:
            continue

        pcm16 = (chunk_to_process * 32767).astype(np.int16)
        b64_chunk = base64.b64encode(pcm16.tobytes()).decode("utf-8")
        audio_queue.put((b64_chunk, True))

    # 3. Gửi thẳng phần dư lẻ cuối (không qua DSP vì chunk < 512 không tương thích Silero VAD)
    if len(internal_audio_buffer) > 0:
        chunk_to_process = internal_audio_buffer
        pcm16 = (chunk_to_process * 32767).astype(np.int16)
        b64_chunk = base64.b64encode(pcm16.tobytes()).decode("utf-8")
        audio_queue.put((b64_chunk, True))

    # Reset lại buffer
    internal_audio_buffer = np.array([], dtype=np.float32)

    logger.info("Đã xả xong buffer vào Queue. Đang ra lệnh ngắt luồng WebSocket...")
    is_running = False
    
    return gr.update(interactive=True), gr.update(interactive=False), transcription_text

def process_audio(audio):
    """Process incoming audio from microphone, apply DSP, and queue for streaming."""
    global transcription_text, partial_text, dsp_pipeline, internal_audio_buffer, is_running

    if audio is None or not is_running:
        return transcription_text + ("\n⏳ Đang dịch: " + partial_text if partial_text else "")

    sample_rate, audio_data = audio

    # Chuẩn hóa về mono và float32
    if len(audio_data.shape) > 1:
        audio_data = audio_data.mean(axis=1)

    if audio_data.dtype == np.int16:
        audio_float = audio_data.astype(np.float32) / 32767.0
    else:
        max_abs = float(np.max(np.abs(audio_data))) if len(audio_data) > 0 else 0.0
        if max_abs > 1.5:
            audio_float = audio_data.astype(np.float32) / 32767.0
        else:
            audio_float = audio_data.astype(np.float32)

    # Resample về 16000Hz nếu cần
    if sample_rate != SAMPLE_RATE:
        num_samples = int(len(audio_float) * SAMPLE_RATE / sample_rate)
        audio_float = np.interp(
            np.linspace(0, len(audio_float) - 1, num_samples),
            np.arange(len(audio_float)),
            audio_float,
        )

    audio_float = np.clip(audio_float, -1.0, 1.0)

    # 1. BỎ TOÀN BỘ ÂM THANH MỚI VÀO "THÙNG CHỨA"
    internal_audio_buffer = np.concatenate((internal_audio_buffer, audio_float))

    # 2. RÚT TỪNG CHUNK ĐÚNG 320 MẪU (20ms) RA ĐỂ XỬ LÝ VÀ GỬI
    chunks_sent = 0
    while len(internal_audio_buffer) >= TARGET_CHUNK_SAMPLES:
        chunk_to_process = internal_audio_buffer[:TARGET_CHUNK_SAMPLES]
        internal_audio_buffer = internal_audio_buffer[TARGET_CHUNK_SAMPLES:]

        # 3. Chạy DSP trên chunk chuẩn 20ms
        if dsp_pipeline is not None:
            chunk_to_process = dsp_pipeline.run(chunk_to_process, sr=SAMPLE_RATE)
            
        chunk_to_process = np.clip(chunk_to_process, -1.0, 1.0)

        # Chặn mảng rỗng (khi LookaheadBuffer đang ngậm dữ liệu)
        if len(chunk_to_process) == 0:
            continue
        
        # 4. Mã hóa và đẩy vào hàng đợi WebSocket
        pcm16 = (chunk_to_process * 32767).astype(np.int16)
        b64_chunk = base64.b64encode(pcm16.tobytes()).decode("utf-8")
        chunk_rms = np.sqrt(np.mean(chunk_to_process**2) + 1e-9)
        is_silent = bool(chunk_rms < 0.015)
        
        audio_queue.put((b64_chunk, is_silent))
        chunks_sent += 1

    return transcription_text + ("\n⏳ Đang dịch: " + partial_text if partial_text else "")

file_stream_cancel = threading.Event()

def stream_file_test(file_input_val, audio_dropdown_val):
    """Stream an uploaded audio file directly through WebSocket to test ASR."""
    global transcription_text, partial_text, is_running, connection_status, file_stream_cancel
    
    target_path = file_input_val
    if not target_path and audio_dropdown_val:
        target_path = os.path.join(AUDIO_DIR, audio_dropdown_val)

    if not target_path or not os.path.exists(target_path):
        return "⚠️ Vui lòng chọn hoặc nạp file âm thanh hợp lệ trước!"

    file_name = os.path.basename(target_path)

    # 1. Hủy bất kỳ worker stream nào đang chạy dở
    file_stream_cancel.set()

    # 2. Ngắt phiên kết nối cũ và đợi đóng hoàn toàn
    stop_recording()
    wait_for_session_close(timeout=4.0)

    # 3. Đọc dữ liệu audio
    try:
        audio_data = load_any_audio(target_path)
    except Exception as e:
        logger.error(f"Lỗi khi đọc file {file_name}: {e}")
        return f"❌ Lỗi đọc file {file_name}: {e}"

    # 4. Khởi tạo phiên kết nối mới
    start_recording()

    # 5. Tạo cờ hủy riêng cho worker file hiện tại
    current_cancel = threading.Event()
    file_stream_cancel = current_cancel

    def worker():
        # Chờ WebSocket kết nối thành công (tối đa 12s, hỗ trợ retry)
        for _ in range(120):
            if current_cancel.is_set():
                logger.info(f"Hủy worker file `{file_name}` do có file mới được yêu cầu.")
                return
            if is_running and "🟢" in connection_status:
                break
            time.sleep(0.1)

        if not is_running or "🟢" not in connection_status:
            logger.error(f"Không thể kết nối WebSocket để stream file `{file_name}`.")
            return

        logger.info(f"Bắt đầu truyền stream file âm thanh `{file_name}` ({len(audio_data)/SAMPLE_RATE:.1f}s) lên server...")
        pcm16 = (np.clip(audio_data, -1.0, 1.0) * 32767).astype(np.int16).tobytes()
        chunk_size = 1600  # 50ms chunk (800 samples @ 16kHz)
        offset = 0
        while offset < len(pcm16) and is_running and not current_cancel.is_set():
            chunk = pcm16[offset:offset + chunk_size]
            b64_chunk = base64.b64encode(chunk).decode("utf-8")
            audio_queue.put((b64_chunk, False))
            offset += chunk_size
            time.sleep(0.012)
        
        if current_cancel.is_set():
            logger.info(f"Đã hủy stream `{file_name}` giữa chừng.")
            return

        logger.info(f"Đã nạp toàn bộ audio `{file_name}` vào hàng đợi. Đang chờ truyền hết lên server...")
        while not audio_queue.empty() and is_running and not current_cancel.is_set():
            time.sleep(0.05)

        if not current_cancel.is_set():
            logger.info(f"Đã truyền xong 100% audio `{file_name}` lên server. Đang chờ chốt kết quả...")
            stop_recording()

    threading.Thread(target=worker, daemon=True, name="FileStreamWorker").start()
    return f"🚀 Đang truyền luồng âm thanh từ file `{file_name}` ({len(audio_data)/SAMPLE_RATE:.1f}s) lên server..."

# ==========================================
# EVALUATION INTEGRATION
# ==========================================
import csv
import glob
from datetime import datetime

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
GT_DIR = os.path.join(BASE_DIR, "ground_truth")
AUDIO_DIR = os.path.join(BASE_DIR, "all_audio_input")

def get_available_gt_files():
    if not os.path.exists(GT_DIR):
        return []
    files = sorted([
        os.path.basename(f)
        for f in glob.glob(os.path.join(GT_DIR, "*.txt"))
        if not os.path.basename(f).lower().startswith("readme")
    ])
    return files

def get_available_audio_files():
    if not os.path.exists(AUDIO_DIR):
        return []
    exts = ("*.mp3", "*.wav", "*.m4a", "*.flac", "*.ogg")
    files = []
    for ext in exts:
        files.extend(glob.glob(os.path.join(AUDIO_DIR, ext)))
    return sorted([os.path.basename(f) for f in files])

# Load JapaneseASREvaluator from cer.py
try:
    from cer import JapaneseASREvaluator
    asr_evaluator = JapaneseASREvaluator()
except Exception as e:
    logger.error(f"Cannot load JapaneseASREvaluator from cer.py: {e}")
    asr_evaluator = None

def run_evaluation(current_transcript: str, selected_gt: str):
    """Calculate 3 CER metrics against selected Ground Truth file."""
    if not current_transcript or not current_transcript.strip():
        return "⚠️ **Chưa có nội dung transcript để đánh giá!**", "-", "-", "-"
    
    if asr_evaluator is None:
        return "❌ Lỗi: Không khởi tạo được module đánh giá cer.py", "-", "-", "-"

    gt_file_path = os.path.join(GT_DIR, selected_gt)
    if not os.path.exists(gt_file_path):
        return f"❌ **Không tìm thấy file Ground Truth:** `{selected_gt}`", "-", "-", "-"
    
    try:
        with open(gt_file_path, 'r', encoding='utf-8') as f:
            ground_truth = f.read()

        gt_strict = asr_evaluator.normalize_strict(ground_truth)
        gt_std = asr_evaluator.normalize_standard(ground_truth)
        gt_loose = asr_evaluator.normalize_loose(ground_truth)

        hyp_strict = asr_evaluator.normalize_strict(current_transcript)
        hyp_std = asr_evaluator.normalize_standard(current_transcript)
        hyp_loose = asr_evaluator.normalize_loose(current_transcript)

        cer_strict = asr_evaluator.calc_cer(gt_strict, hyp_strict)
        cer_std = asr_evaluator.calc_cer(gt_std, hyp_std)
        cer_loose = asr_evaluator.calc_cer(gt_loose, hyp_loose)

        # Save to history CSV & txt
        results_dir = os.path.join(BASE_DIR, "results")
        os.makedirs(results_dir, exist_ok=True)
        csv_path = os.path.join(results_dir, "cer_results.csv")
        file_exists = os.path.exists(csv_path) and os.path.getsize(csv_path) > 0
        existing_run_count = 0
        if file_exists:
            with open(csv_path, mode='r', encoding='utf-8-sig') as f:
                existing_run_count = max(0, len(list(csv.reader(f))) - 1)
        
        timestamp_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with open(csv_path, mode='a', newline='', encoding='utf-8-sig') as f:
            writer = csv.writer(f)
            if not file_exists:
                writer.writerow(["Run", "GT File", "CER Strict", "CER Standard", "CER Loose", "Accuracy Loose", "Transcript", "Timestamp"])
            writer.writerow([
                existing_run_count + 1,
                selected_gt,
                f"{cer_strict * 100:.2f}%",
                f"{cer_std * 100:.2f}%",
                f"{cer_loose * 100:.2f}%",
                f"{max(0.0, (1.0 - cer_loose) * 100):.2f}%",
                current_transcript.strip(),
                timestamp_str
            ])

        status_msg = f"✅ **Đánh giá thành công với `{selected_gt}`** | Độ chính xác (Loose): **{max(0.0, (1.0 - cer_loose) * 100):.2f}%** | Đã lưu vào `results/cer_results.csv`"
        return status_msg, f"{cer_strict * 100:.2f}%", f"{cer_std * 100:.2f}%", f"{cer_loose * 100:.2f}%"
    except Exception as e:
        logger.error(f"Error during evaluation: {e}")
        return f"❌ Lỗi khi tính CER: {e}", "-", "-", "-"

# ==========================================
# GIAO DIỆN GRADIO
# ==========================================
gt_choices = get_available_gt_files()
audio_choices = get_available_audio_files()

def select_audio_file(selected_audio: str):
    if not selected_audio:
        return None, gt_choices[0] if gt_choices else None
    audio_path = os.path.join(AUDIO_DIR, selected_audio)
    stem = os.path.splitext(selected_audio)[0]
    matching_gt = f"{stem}.txt"
    if matching_gt not in gt_choices:
        matching_gt = gt_choices[0] if gt_choices else None
    return audio_path, matching_gt

default_audio = os.path.join(AUDIO_DIR, audio_choices[0]) if audio_choices else None
default_gt = gt_choices[0] if gt_choices else None

with gr.Blocks(title="Qwen3-ASR Real-time Speech Transcription") as demo:
    gr.Markdown("# 🎙️ Qwen3-ASR Real-time Speech Transcription")
    status_indicator = gr.Markdown(f"**Trạng thái:** {connection_status}")

    with gr.Tabs():
        with gr.Tab("🎙️ Thu âm Microphone Trực tiếp"):
            gr.Markdown("👉 **Bước 1:** Bấm nút **Start** để khởi tạo kết nối. Sau đó bấm biểu tượng **Microphone** ở khung bên dưới để bắt đầu nói:")
            with gr.Row():
                start_btn = gr.Button("▶️ Start (Bắt đầu)", variant="primary")
                stop_btn = gr.Button("⏹️ Stop (Dừng)", variant="stop", interactive=False)
            audio_input = gr.Audio(sources=["microphone"], streaming=True, type="numpy", label="Microphone Stream")

        with gr.Tab("📁 Test nhanh bằng File Âm thanh (.mp3, .wav, .m4a, ...)"):
            gr.Markdown("👉 Bạn có thể chọn file có sẵn từ thư mục `all_audio_input` hoặc tải lên file tùy ý:")
            with gr.Row():
                audio_dropdown = gr.Dropdown(
                    label="Chọn File Audio từ all_audio_input",
                    choices=audio_choices,
                    value=audio_choices[0] if audio_choices else None,
                    interactive=True,
                    scale=2
                )
                load_audio_btn = gr.Button("📂 Nạp File vào Trình phát", variant="secondary", scale=1)
            file_input = gr.Audio(value=default_audio, sources=["upload"], type="filepath", label="Trình phát & Kéo thả file âm thanh")
            file_stream_btn = gr.Button("🚀 Bắt đầu Stream File lên Server", variant="primary")
            file_status = gr.Markdown("")

    def clear_transcription():
        """Clear all accumulated and partial transcription text."""
        global transcription_text, partial_text
        transcription_text = ""
        partial_text = ""
        return ""

    transcription_output = gr.Textbox(label="Kết quả Transcription (Streaming Real-time)", lines=6)
    with gr.Row():
        copy_btn = gr.Button("📋 Copy Transcription", variant="secondary", scale=2)
        clear_btn = gr.Button("🗑️ Xóa Transcription", variant="stop", scale=1)

    with gr.Accordion("🔍 Đánh Giá Độ Chính Xác (ASR CER Evaluation)", open=False):
        with gr.Row():
            gt_dropdown = gr.Dropdown(
                label="Chọn File Ground Truth (GT)",
                choices=gt_choices,
                value=default_gt,
                interactive=True,
                scale=2
            )
            eval_btn = gr.Button("📊 So Sánh & Tính CER", variant="primary", scale=1)
        
        with gr.Row():
            cer_strict_out = gr.Textbox(label="1️⃣ CER Strict (Giữ nguyên)", interactive=False)
            cer_std_out = gr.Textbox(label="2️⃣ CER Standard (Bỏ dấu câu)", interactive=False)
            cer_loose_out = gr.Textbox(label="3️⃣ CER Loose (Bỏ từ thừa & chuẩn hóa)", interactive=False)
        
        eval_status = gr.Markdown("")

    def poll_updates():
        global transcription_text, partial_text, connection_status
        display_str = transcription_text
        if partial_text:
            display_str += ("\n" if display_str and not display_str.endswith("\n") else "") + "⏳ Đang dịch: " + partial_text
        return display_str, f"**Trạng thái:** {connection_status}"

    timer = gr.Timer(value=0.5)
    timer.tick(poll_updates, outputs=[transcription_output, status_indicator])

    start_btn.click(start_recording, outputs=[start_btn, stop_btn, transcription_output])
    stop_btn.click(stop_recording, outputs=[start_btn, stop_btn, transcription_output])
    clear_btn.click(clear_transcription, outputs=[transcription_output])
    audio_input.stream(process_audio, inputs=[audio_input], outputs=[transcription_output])
    audio_dropdown.change(fn=select_audio_file, inputs=[audio_dropdown], outputs=[file_input, gt_dropdown])
    load_audio_btn.click(fn=select_audio_file, inputs=[audio_dropdown], outputs=[file_input, gt_dropdown])
    file_stream_btn.click(stream_file_test, inputs=[file_input, audio_dropdown], outputs=[file_status])
    copy_btn.click(
        fn=None,
        inputs=[transcription_output],
        js="(text) => { navigator.clipboard.writeText(text); }"
    )
    eval_btn.click(
        fn=run_evaluation,
        inputs=[transcription_output, gt_dropdown],
        outputs=[eval_status, cer_strict_out, cer_std_out, cer_loose_out]
    )

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Realtime WebSocket Transcription Client")
    parser.add_argument("--ws-url", type=str, default="", help="Direct WebSocket URL (e.g. wss://.../v1/realtime)")
    parser.add_argument("--model", type=str, default="qwen3")
    parser.add_argument("--host", type=str, default="localhost")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--share", action="store_true")
    
    parser.add_argument(
        "--pipeline",
        type=str,
        choices=["none", "qwen3", "qwen3_dsp", "voxtral_core", "voxtral_pro", "core", "ultra", "optimal", "ehanc_v1", "adaptive_v2", "adaptive_v3"],
        default="none",
        help="Chọn DSP Pipeline để xử lý âm thanh (mặc định: none cho Qwen3-ASR)"
    )
    
    args = parser.parse_args()

    if args.ws_url:
        ws_url = args.ws_url
    elif args.host.startswith("ws://") or args.host.startswith("wss://"):
        ws_url = args.host
    elif args.host.endswith(".modal.run"):
        ws_url = f"wss://{args.host}/v1/realtime"
    else:
        ws_url = f"ws://{args.host}:{args.port}/v1/realtime"
    
    model = args.model
    chosen_pipeline_strategy = args.pipeline
    
    print("🚀 Khởi động ứng dụng Gradio Client... Log đang được ghi vào file 'client_logs.jsonl'")
    demo.launch(theme=gr.themes.Soft(), share=args.share)