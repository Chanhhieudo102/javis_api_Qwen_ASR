# -*- coding: utf-8 -*-
"""
evaluate_batch.py
=================
Công cụ tự động hóa đánh giá toàn bộ audio trong all_audio_input với ground_truth:
1. Áp dụng Pipeline tiền xử lý âm thanh số 16kHz DSP (Smart Mono, HPF 80Hz, Resample soxr, AGC Meeting / Peak Normalization, SoftClip).
2. Kết nối WebSocket tới Qwen3 / Voxtral ASR Server và stream audio thời gian thực.
3. Nhận transcript hoàn chỉnh từ WebSocket.
4. Tính toán CER Strict, CER Standard, CER Loose (Janome phonetic normalization) và Accuracy.
5. Xuất báo cáo đối soát chi tiết so sánh với Baseline v1 ra console, file TXT và file JSON.

Sử dụng:
    py -3.11 evaluate_batch.py
    py -3.11 evaluate_batch.py --mode meeting
    py -3.11 evaluate_batch.py --mode ideal
    py -3.11 evaluate_batch.py --mode none
    py -3.11 evaluate_batch.py --file media_148393_1767860211615.mp3
"""

import os
import sys
import re
import json
import time
import glob
import asyncio
import argparse
import unicodedata
from pathlib import Path
from collections import Counter
from typing import Dict, List, Tuple, Optional

import numpy as np

# Force UTF-8 và unbuffered stdout trên Windows terminal
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace", line_buffering=True)
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace", line_buffering=True)

import websockets
import pybase64 as base64

# Thêm đường dẫn javis-api-qwen3-hf để import AudioDSPService
BASE_DIR = Path(__file__).parent.resolve()
BACKEND_DIR = BASE_DIR / "javis-api-qwen3-hf"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

try:
    import sounddevice as sd
except ImportError:
    sd = None

try:
    from app.voice2text.services.audio_dsp_service import AudioDSPService, StreamingDSPProcessor
    from app.voice2text.constants.dsp_constants import AudioDSPMode
    from app.voice2text.services.japanese_itn_service import JapaneseITNService
except ImportError:
    AudioDSPService = None
    StreamingDSPProcessor = None
    AudioDSPMode = None
    JapaneseITNService = None

from cer import JapaneseASREvaluator, clean_text, levenshtein_distance, get_alignment

DEFAULT_WS_URL = "wss://uydo8081--javis-api-qwen3-hf-serve-serve-dev.modal.run/api/v2/transcript/ws/no-diarization"
AUDIO_DIR = BASE_DIR / "all_audio_input"
GT_DIR = BASE_DIR / "ground_truth"
RESULTS_DIR = BASE_DIR / "results"

# Bảng baseline v1 của người dùng để so sánh đối chiếu
BASELINE_V1 = {
    "media_148280_1767762915627.mp3": {"gt_chars": 369, "errors": 59, "cer": 24.18, "acc": 75.82},
    "media_148284_1767766514646.mp3": {"gt_chars": 260, "errors": 21, "cer": 11.28, "acc": 88.72},
    "media_148393_1767860211615.mp3": {"gt_chars": 188, "errors": 18, "cer": 13.90, "acc": 86.10},
    "media_148394_1767860189485.mp3": {"gt_chars": 199, "errors": 28, "cer": 20.30, "acc": 79.70},
    "media_148414_1767922241264.mp3": {"gt_chars": 393, "errors": 56, "cer": 25.13, "acc": 74.87},
    "media_148439_1767926711644.mp3": {"gt_chars": 191, "errors": 22, "cer": 27.93, "acc": 72.07},
    "media_148954_1768789819598.mp3": {"gt_chars": 565, "errors": 125, "cer": 24.60, "acc": 75.40},
    "media_149291_1769069811005.mp3": {"gt_chars": 954, "errors": 107, "cer": 16.09, "acc": 83.91},
    "media_149733_1769589919400.mp3": {"gt_chars": 327, "errors": 88, "cer": 36.51, "acc": 63.49},
}


def load_audio_pcm16_with_dsp(file_path: Path, mode: str = "meeting") -> bytes:
    """Nạp file audio và chạy qua pipeline DSP 16kHz."""
    try:
        import soundfile as sf
        raw_data, orig_sr = sf.read(str(file_path))
        data = raw_data.astype(np.float32)
        sr = orig_sr
    except Exception as sf_err:
        import subprocess
        try:
            import imageio_ffmpeg
            ffmpeg_exe = imageio_ffmpeg.get_ffmpeg_exe()
            cmd = [
                ffmpeg_exe, "-i", str(file_path),
                "-f", "f32le", "-ac", "1", "-ar", "16000",
                "-loglevel", "error", "-"
            ]
            proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            out, _ = proc.communicate()
            if proc.returncode == 0 and len(out) > 0:
                data = np.frombuffer(out, dtype=np.float32)
                sr = 16000
            else:
                raise RuntimeError(f"FFmpeg decode error: {proc.returncode}")
        except Exception:
            raise RuntimeError(f"Không thể đọc file {file_path}: {sf_err}")

    num_ch = 1 if data.ndim == 1 else data.shape[1]
    if AudioDSPService is not None:
        return AudioDSPService.process_full_audio(data, orig_sr=sr, num_ch=num_ch, mode=mode)

    # Fallback
    if len(data.shape) > 1:
        data = data.mean(axis=1)
    if sr != 16000:
        try:
            import soxr
            data = soxr.resample(data, sr, 16000).astype(np.float32)
        except Exception:
            num_samples = int(len(data) * 16000 / sr)
            data = np.interp(np.linspace(0, len(data) - 1, num_samples), np.arange(len(data)), data)
    clipped = np.clip(data, -1.0, 1.0)
    return (clipped * 32767.0).astype(np.int16).tobytes()


# Bộ lọc ảo giác phụ đề chuẩn của các mô hình ASR huấn luyện trên web (Whisper / Qwen)
STANDARD_ASR_HALLUCINATIONS = [
    re.compile(r"ご視聴ありがとう.*?", re.IGNORECASE),
    re.compile(r"チャンネル登録.*?", re.IGNORECASE),
    re.compile(r"字幕.*?制作.*?", re.IGNORECASE),
    re.compile(r"その時、.*?(学びました|ようになる|なった|知る|生きる).*?", re.DOTALL),
]

def filter_hallucinations(text: str) -> str:
    cleaned = text
    for pat in STANDARD_ASR_HALLUCINATIONS:
        cleaned = pat.sub("", cleaned)
    return cleaned.strip()


async def transcribe_stream_websocket(
    pcm16: bytes,
    ws_url: str,
    model: str = "qwen3",
    chunk_size: int = 5120,  # 160ms chunk (2560 samples * 2 bytes) @ 16kHz matching encode/audio_processing_VAD.js
    rate_delay: float = 0.020,
    timeout_seconds: float = 40.0
) -> str:
    """Stream PCM16 qua WebSocket với cơ chế drift-free pacing và silence tail 1.5s."""
    max_retries = 5
    for attempt in range(max_retries):
        accumulated_texts = []
        try:
            async with websockets.connect(
                ws_url,
                open_timeout=60,
                ping_interval=20,
                ping_timeout=20,
            ) as ws:
                # 1. Nhận thông điệp khởi tạo
                init_msg = await ws.recv()
                try:
                    init_data = json.loads(init_msg)
                    if init_data.get("type") == "error" and init_data.get("code") == "WS_ERR_CAPACITY_FULL":
                        if attempt < max_retries - 1:
                            print(f"  ⏳ Server đang bận giải phóng phiên cũ. Đợi 2s thử lại ({attempt + 1}/{max_retries})...")
                            await asyncio.sleep(2.0)
                            continue
                except Exception:
                    pass

                # 2. Gửi session.update
                await ws.send(json.dumps({
                    "type": "session.update",
                    "model": model
                }))

                sender_done = asyncio.Event()
                stop_event = asyncio.Event()
                commit_time: Optional[float] = None

                async def sender():
                    nonlocal commit_time
                    offset = 0
                    start_stream_time = time.perf_counter()
                    chunk_idx = 0
                    step_delay = rate_delay

                    try:
                        # 3. Bơm audio chính theo chunk 160ms với drift-free pacing
                        while offset < len(pcm16) and not stop_event.is_set():
                            chunk = pcm16[offset:offset + chunk_size]
                            b64_chunk = base64.b64encode(chunk).decode("utf-8")
                            await ws.send(json.dumps({
                                "type": "input_audio_buffer.append",
                                "audio": b64_chunk
                            }))
                            offset += chunk_size
                            chunk_idx += 1
                            target_time = start_stream_time + chunk_idx * step_delay
                            now = time.perf_counter()
                            if target_time > now:
                                await asyncio.sleep(target_time - now)

                        # 4. Gửi đệm khoảng lặng (silence tail) 400ms để server chốt VAD và phát hết từ cuối
                        silence_len = int(16000 * 2 * 0.4)  # 400ms silence tail (vừa đủ VAD, không gây ảo giác)
                        silence_bytes = b'\x00' * silence_len
                        for sil_offset in range(0, silence_len, chunk_size):
                            if stop_event.is_set():
                                break
                            chunk = silence_bytes[sil_offset:sil_offset + chunk_size]
                            b64_chunk = base64.b64encode(chunk).decode("utf-8")
                            await ws.send(json.dumps({
                                "type": "input_audio_buffer.append",
                                "audio": b64_chunk
                            }))
                            chunk_idx += 1
                            target_time = start_stream_time + chunk_idx * step_delay
                            now = time.perf_counter()
                            if target_time > now:
                                await asyncio.sleep(target_time - now)

                        # 5. Gửi commit final sau khi đệm xong silence tail
                        if not stop_event.is_set():
                            await ws.send(json.dumps({"type": "input_audio_buffer.commit", "final": True}))
                            commit_time = time.time()
                    except Exception as send_err:
                        print(f"  ⚠️ Lỗi trong sender: {send_err}")
                    finally:
                        sender_done.set()


                async def receiver():
                    nonlocal commit_time
                    last_recv_time = time.time()
                    try:
                        while not stop_event.is_set():
                            try:
                                msg = await asyncio.wait_for(ws.recv(), timeout=2.0)
                                last_recv_time = time.time()
                                data = json.loads(msg)
                                msg_type = data.get("type", "")

                                if msg_type in ("transcription.done", "final"):
                                    if "segments" in data:
                                        text = " ".join([seg.get("text", "") for seg in data.get("segments", []) if seg.get("text")])
                                    else:
                                        text = data.get("text", "")
                                    text = filter_hallucinations(text)
                                    if text:
                                        accumulated_texts.append(text)
                                elif msg_type in ("session_stopped", "stopped"):
                                    stop_event.set()
                                    break
                                elif msg_type == "error":
                                    err_code = data.get("code", "")
                                    err_msg = data.get("message", data)
                                    print(f"  ❌ Lỗi từ server: {err_code} - {err_msg}")
                                    stop_event.set()
                                    break
                            except asyncio.TimeoutError:
                                # Chỉ ngắt kết nối nếu sender đã gửi commit xong VÀ server không phản hồi gì trong 35s
                                if sender_done.is_set():
                                    if (time.time() - last_recv_time) >= 35.0:
                                        print("  ⏳ Quá thời gian chờ server phản hồi (35s không có dữ liệu mới). Kết thúc phiên.")
                                        stop_event.set()
                                        break
                                # Nếu sender vẫn đang đẩy âm thanh, tiếp tục lắng nghe bình thường
                    except Exception as recv_err:
                        pass

                await asyncio.gather(sender(), receiver(), return_exceptions=True)
                try:
                    await ws.close()
                except Exception:
                    pass

                full_transcript = "\n".join(accumulated_texts).strip()
                if full_transcript:
                    return full_transcript
                elif attempt < max_retries - 1:
                    print(f"  ⚠️ Chưa nhận được transcript (lần {attempt + 1}/{max_retries}). Thử lại sau 2s...")
                    await asyncio.sleep(2.0)
                    continue

        except (asyncio.TimeoutError, websockets.exceptions.ConnectionClosed, Exception) as e:
            if attempt < max_retries - 1:
                print(f"  ⚠️ Lỗi kết nối ({e}). Đang thử lại lần {attempt + 2}/{max_retries} sau 2.5s...")
                await asyncio.sleep(2.5)
                continue
            raise

    return "\n".join(accumulated_texts).strip()


def find_virtual_cable_devices():
    """Tự động quét và phát hiện cặp thiết bị CABLE Output (Mic) và CABLE Input (Playback)."""
    if sd is None:
        return None, None, "Chưa cài thư viện sounddevice. Hãy chạy: pip install sounddevice"

    devs = sd.query_devices()
    in_dev = None   # CABLE Output (Microphone / Recording)
    out_dev = None  # CABLE Input (Speaker / Playback)
    for host_pref in ['Windows DirectSound', 'MME', 'Windows WASAPI']:
        for i, d in enumerate(devs):
            host_name = sd.query_hostapis(d['hostapi'])['name']
            if host_name == host_pref:
                if 'CABLE Output' in d['name'] and d['max_input_channels'] > 0 and in_dev is None:
                    in_dev = i
                if 'CABLE Input' in d['name'] and d['max_output_channels'] > 0 and out_dev is None:
                    out_dev = i
        if in_dev is not None and out_dev is not None:
            break
    if in_dev is None or out_dev is None:
        for i, d in enumerate(devs):
            if 'CABLE Output' in d['name'] and d['max_input_channels'] > 0 and in_dev is None:
                in_dev = i
            if 'CABLE Input' in d['name'] and d['max_output_channels'] > 0 and out_dev is None:
                out_dev = i

    if in_dev is None or out_dev is None:
        return None, None, "Không tìm thấy driver VB-Audio Virtual Cable (CABLE Input / CABLE Output)!"
    return in_dev, out_dev, None


async def transcribe_virtual_mic_stream_ws(
    audio_path: Path,
    in_dev: int,
    out_dev: int,
    ws_url: str,
    model: str = "qwen3",
    mode: str = "meeting",
    chunk_size_samples: int = 2560,
) -> str:
    """
    Phát audio vào CABLE Input, đồng thời thu âm thời gian thực từ CABLE Output (Micro ảo),
    tiền xử lý DSP StreamingDSPProcessor qua từng chunk và stream lên WebSocket backend.
    """
    if sd is None:
        raise RuntimeError("sounddevice chưa được cài đặt.")

    try:
        import soundfile as sf
        raw_data, orig_sr = sf.read(str(audio_path), dtype='float32')
    except Exception:
        import librosa
        raw_data, orig_sr = librosa.load(str(audio_path), sr=None, mono=False)
        if raw_data.ndim > 1:
            raw_data = raw_data.T

    num_ch = 1 if raw_data.ndim == 1 else raw_data.shape[1]
    audio_play = np.column_stack([raw_data, raw_data]) if num_ch == 1 else raw_data
    audio_duration = len(raw_data) / float(orig_sr)

    accumulated_texts = []
    stop_event = asyncio.Event()
    processor = StreamingDSPProcessor(mode=mode, sample_rate=16000) if StreamingDSPProcessor else None
    audio_queue = asyncio.Queue()
    loop = asyncio.get_running_loop()

    def record_callback(indata, frames, time_info, status):
        chunk = indata[:, 0].copy()
        loop.call_soon_threadsafe(audio_queue.put_nowait, chunk)

    async with websockets.connect(
        ws_url,
        open_timeout=60,
        ping_interval=20,
        ping_timeout=20,
    ) as ws:
        # 1. Nhận thông điệp khởi tạo
        await ws.recv()

        # 2. Gửi session.update
        await ws.send(json.dumps({
            "type": "session.update",
            "model": model
        }))

        last_rx_time = time.time()
        sender_done = asyncio.Event()

        async def receiver():
            nonlocal last_rx_time
            try:
                while not stop_event.is_set():
                    try:
                        msg = await asyncio.wait_for(ws.recv(), timeout=2.0)
                        data = json.loads(msg)
                        msg_type = data.get("type", "")

                        if msg_type in ("transcription.done", "final"):
                            last_rx_time = time.time()
                            if "segments" in data:
                                text = " ".join([seg.get("text", "") for seg in data.get("segments", []) if seg.get("text")])
                            else:
                                text = data.get("text", "")
                            text = filter_hallucinations(text)
                            if text:
                                accumulated_texts.append(text)
                        elif msg_type in ("session_stopped", "stopped"):
                            stop_event.set()
                            break
                        elif msg_type == "error":
                            err_code = data.get("code", "")
                            err_msg = data.get("message", data)
                            print(f"  ❌ Lỗi từ server: {err_code} - {err_msg}")
                            stop_event.set()
                            break
                    except asyncio.TimeoutError:
                        if stop_event.is_set():
                            break
            except Exception:
                pass

        recv_task = asyncio.create_task(receiver())

        # Khởi tạo Stream thu âm từ Micro ảo (CABLE Output)
        stream = sd.InputStream(
            device=in_dev,
            channels=1,
            samplerate=16000,
            blocksize=chunk_size_samples,
            callback=record_callback
        )

        with stream:
            # Phát âm thanh vào cổng CABLE Input
            sd.play(audio_play, samplerate=orig_sr, device=out_dev)
            start_time = time.time()
            total_wait = audio_duration + 0.3  # Đệm 0.3s margin cho DAC flush sạch buffer

            while time.time() - start_time < total_wait and not stop_event.is_set():
                try:
                    chunk = await asyncio.wait_for(audio_queue.get(), timeout=0.5)
                    if processor:
                        proc = processor.process_chunk(chunk)
                    else:
                        proc = chunk
                    pcm16 = (np.clip(proc, -1.0, 1.0) * 32767.0).astype(np.int16).tobytes()
                    b64_chunk = base64.b64encode(pcm16).decode("utf-8")
                    await ws.send(json.dumps({
                        "type": "input_audio_buffer.append",
                        "audio": b64_chunk
                    }))
                except asyncio.TimeoutError:
                    continue

        # Chờ dừng phát âm thanh
        sd.stop()

        # Dọn sạch các chunk còn tồn trong hàng đợi âm thanh
        while not audio_queue.empty():
            try:
                chunk = audio_queue.get_nowait()
                if processor:
                    proc = processor.process_chunk(chunk)
                else:
                    proc = chunk
                pcm16 = (np.clip(proc, -1.0, 1.0) * 32767.0).astype(np.int16).tobytes()
                b64_chunk = base64.b64encode(pcm16).decode("utf-8")
                await ws.send(json.dumps({
                    "type": "input_audio_buffer.append",
                    "audio": b64_chunk
                }))
            except Exception:
                break

        # Gửi commit final sau khi kết thúc phát
        await ws.send(json.dumps({"type": "input_audio_buffer.commit", "final": True}))
        commit_time = time.time()

        # Chờ server WebSocket trả về hết transcript (chờ session_stopped hoặc tối đa 35 giây)
        wait_start = time.time()
        while time.time() < wait_start + 35.0 and not stop_event.is_set():
            await asyncio.sleep(0.5)
            # Chỉ dừng nếu server đã gửi segment sau khi commit VÀ đã im lặng 4 giây liên tục
            if (last_rx_time >= wait_start) and (time.time() - last_rx_time >= 4.0):
                break

        stop_event.set()
        await ws.close()
        recv_task.cancel()
        await asyncio.gather(recv_task, return_exceptions=True)

    return "\n".join(accumulated_texts).strip()


def evaluate_single_file(
    audio_path: Path,
    gt_path: Path,
    ws_url: str,
    model: str = "qwen3",
    mode: str = "meeting",
    rate_delay: float = 0.020,
    vmic_in: Optional[int] = None,
    vmic_out: Optional[int] = None,
) -> dict:
    """Đánh giá 1 file: Nạp DSP -> Stream WebSocket (hoặc phát qua Virtual Mic) -> Chuẩn hóa ITN -> Tính CER Loose & Standard."""
    file_name = audio_path.name
    print(f"\n▶ Đang xử lý: {file_name} [DSP Mode: {mode}]...")

    t0 = time.time()
    if vmic_in is not None and vmic_out is not None:
        print(f"  └─ 🎤 Phát qua CABLE Input (#{vmic_out}) & thu âm thời gian thực từ CABLE Output (#{vmic_in})...")
        try:
            transcript = asyncio.run(
                transcribe_virtual_mic_stream_ws(
                    audio_path=audio_path,
                    in_dev=vmic_in,
                    out_dev=vmic_out,
                    ws_url=ws_url,
                    model=model,
                    mode=mode,
                )
            )
        except Exception as e:
            print(f"  ❌ Lỗi Virtual Mic: {e}")
            transcript = ""
    else:
        pcm16 = load_audio_pcm16_with_dsp(audio_path, mode=mode)
        audio_dur_sec = len(pcm16) / (16000 * 2)
        print(f"  └─ Audio duration: {audio_dur_sec:.2f}s | PCM16: {len(pcm16):,} bytes")

        # Stream WebSocket
        try:
            transcript = asyncio.run(
                transcribe_stream_websocket(pcm16, ws_url, model=model, rate_delay=rate_delay)
            )
        except Exception as e:
            print(f"  ❌ Lỗi WebSocket: {e}")
            transcript = ""

    # Áp dụng Japanese ITN Normalization (Inverse Text Normalization)
    if JapaneseITNService is not None and transcript:
        transcript = JapaneseITNService.normalize(transcript)

    elapsed = time.time() - t0
    print(f"  └─ Nhận diện xong trong {elapsed:.2f}s")


    # Đọc Ground Truth
    with open(gt_path, "r", encoding="utf-8") as f:
        ref_raw = f.read().strip()

    # Tính toán chỉ số theo CER Loose (Phonetic Janome reading) và CER Standard
    evaluator = JapaneseASREvaluator()

    ref_loose = clean_text(ref_raw)
    hyp_loose = clean_text(transcript)

    dist_loose, dp_loose = levenshtein_distance(ref_loose, hyp_loose)
    align_ref, align_hyp, ops = get_alignment(ref_loose, hyp_loose, dp_loose)

    del_c = ops.count("del")
    ins_c = ops.count("ins")
    sub_c = ops.count("sub")
    matches = ops.count("match")

    gt_len_loose = len(ref_loose)
    cer_loose = (dist_loose / gt_len_loose * 100) if gt_len_loose > 0 else 0.0
    acc_loose = max(0.0, 100.0 - cer_loose)

    # Thống kê tần suất ký tự
    ref_counts = Counter(ref_loose)
    hyp_counts = Counter(hyp_loose)
    common_counts = ref_counts & hyp_counts
    match_rate = (sum(common_counts.values()) / gt_len_loose * 100) if gt_len_loose > 0 else 0.0

    # Tính thêm CER Standard (Unicode NFKC, bỏ dấu câu)
    ref_std = evaluator.normalize_standard(ref_raw)
    hyp_std = evaluator.normalize_standard(transcript)
    dist_std, _ = levenshtein_distance(ref_std, hyp_std)
    cer_std = (dist_std / len(ref_std) * 100) if len(ref_std) > 0 else 0.0

    # Lấy đối chứng v1
    v1_info = BASELINE_V1.get(file_name, {})
    cer_v1 = v1_info.get("cer", 0.0)

    delta_cer = cer_loose - cer_v1 if cer_v1 > 0 else 0.0
    print(f"  └─ CER Loose: {cer_loose:.2f}% | Độ chính xác: {acc_loose:.2f}% | Độ trùng khớp: {match_rate:.2f}%")
    print(f"  └─ So với Baseline v1 ({cer_v1:.2f}%): {'Cải thiện ' if delta_cer < 0 else 'Tăng '}{abs(delta_cer):.2f}%")

    return {
        "file": file_name,
        "gt_chars": gt_len_loose,
        "errors": dist_loose,
        "cer_loose": cer_loose,
        "cer_std": cer_std,
        "cer_v1": cer_v1,
        "accuracy": acc_loose,
        "match_rate": match_rate,
        "deletions": del_c,
        "insertions": ins_c,
        "substitutions": sub_c,
        "matches": matches,
        "ref_raw": ref_raw,
        "hyp_raw": transcript,
        "ref_clean": ref_loose,
        "hyp_clean": hyp_loose,
    }


def main():
    parser = argparse.ArgumentParser(description="Batch Audio Evaluation with DSP and CER Benchmarking")
    parser.add_argument("--ws-url", type=str, default=DEFAULT_WS_URL, help="WebSocket URL of ASR backend")
    parser.add_argument("--mode", type=str, choices=["meeting", "ideal", "none"], default="meeting", help="Audio DSP mode")
    parser.add_argument("--model", type=str, default="qwen3", help="Model name (e.g. qwen3, voxtral-realtime)")
    parser.add_argument("--file", type=str, default=None, help="Specific audio file name to test")
    parser.add_argument("--realtime", action="store_true", help="Chạy ở tốc độ chuẩn 1.0x Realtime (160ms audio nghỉ đúng 160ms)")
    parser.add_argument("--virtual-mic", action="store_true", help="Thu âm và phát âm thanh qua driver micro ảo (VB-Audio Virtual Cable) chuẩn 1.0x Realtime")
    args = parser.parse_args()

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    rate_delay = 0.160 if args.realtime else 0.020

    vmic_in, vmic_out = None, None
    if args.virtual_mic:
        vmic_in, vmic_out, err = find_virtual_cable_devices()
        if err:
            print(f"❌ {err}")
            sys.exit(1)
        devs = sd.query_devices()
        in_name = devs[vmic_in]['name']
        out_name = devs[vmic_out]['name']

    # Tìm danh sách file audio
    if args.file:
        audio_files = [AUDIO_DIR / args.file]
        if not audio_files[0].exists():
            print(f"❌ File không tồn tại: {audio_files[0]}")
            sys.exit(1)
    else:
        audio_files = sorted(list(AUDIO_DIR.glob("*.mp3")) + list(AUDIO_DIR.glob("*.wav")))

    if not audio_files:
        print(f"❌ Không tìm thấy file audio nào trong {AUDIO_DIR}")
        sys.exit(1)

    print("=" * 90)
    print("🚀 BẮT ĐẦU CHẠY BENCHMARK TOÀN BỘ FILE VỚI PIPELINE DSP & ITN")
    print(f"• WebSocket: {args.ws_url}")
    print(f"• DSP Mode : {args.mode.upper()} (Adaptive RMS AGC, HPF 80Hz, 16kHz soxr)")
    if args.virtual_mic:
        print(f"• Phương thức: 🎤 Thu âm REAL-TIME qua Micro ảo (VB-Audio Virtual Cable)")
        print(f"• Micro ảo (In) : Device #{vmic_in} [{in_name}]")
        print(f"• Phát nhạc(Out): Device #{vmic_out} [{out_name}]")
    else:
        print(f"• Stream   : {'1.0x REALTIME (Mô phỏng người nói trực tiếp)' if args.realtime else 'FAST STREAM (~4.0x tốc độ cao)'}")
    print(f"• Model    : {args.model}")
    print(f"• Tổng số  : {len(audio_files)} files")
    print("=" * 90)

    results = []
    for audio_path in audio_files:
        stem = audio_path.stem
        gt_path = GT_DIR / f"{stem}.txt"
        if not gt_path.exists():
            print(f"⚠️ Bỏ qua {audio_path.name}: không tìm thấy file GT {gt_path.name}")
            continue

        res = evaluate_single_file(
            audio_path=audio_path,
            gt_path=gt_path,
            ws_url=args.ws_url,
            model=args.model,
            mode=args.mode,
            rate_delay=rate_delay,
            vmic_in=vmic_in,
            vmic_out=vmic_out,
        )
        results.append(res)
        time.sleep(1.0)  # Giãn cách 1s giữa các file để server giải phóng bộ nhớ


    if not results:
        print("❌ Không có kết quả nào được thu thập!")
        return

    # Tổng kết bảng điểm
    total_gt = sum(r["gt_chars"] for r in results)
    total_err = sum(r["errors"] for r in results)
    avg_cer = (total_err / total_gt * 100) if total_gt > 0 else 0.0
    avg_acc = max(0.0, 100.0 - avg_cer)
    avg_match = np.mean([r["match_rate"] for r in results])

    v1_total_err = sum(BASELINE_V1.get(r["file"], {}).get("errors", 0) for r in results)
    v1_total_gt = sum(BASELINE_V1.get(r["file"], {}).get("gt_chars", 0) for r in results)
    v1_avg_cer = (v1_total_err / v1_total_gt * 100) if v1_total_gt > 0 else 22.213

    # Định dạng bảng markdown và text
    timestamp_str = time.strftime("%Y-%m-%d %H:%M:%S")
    header = (
        "==========================================================================================================================\n"
        "BẢNG TỔNG HỢP KẾT QUẢ ĐÁNH GIÁ (CER BENCHMARK VỚI DSP CẢI TIẾN)\n"
        f"Thời gian: {timestamp_str}\n"
        f"WebSocket: {args.ws_url}\n"
        f"DSP Mode : {args.mode} (Smart Mono, HPF 80Hz, 16kHz soxr, Adaptive AGC -22dBFS)\n"
        "==========================================================================================================================\n"
        f"{'File Audio':<32} | {'Ký tự GT':>9} | {'Lỗi v1':>7} | {'Lỗi DSP':>8} | {'CER v1 (%)':>10} | {'CER DSP (%)':>11} | {'Độ chính xác (%)':>16}\n"
        "--------------------------------------------------------------------------------------------------------------------------\n"
    )

    rows = []
    for r in results:
        v1_info = BASELINE_V1.get(r["file"], {})
        err_v1 = v1_info.get("errors", "-")
        cer_v1_str = f"{v1_info.get('cer', 0.0):.2f}%" if "cer" in v1_info else "-"
        row_str = (
            f"{r['file']:<32} | {r['gt_chars']:>9} | {str(err_v1):>7} | {r['errors']:>8} | "
            f"{cer_v1_str:>10} | {r['cer_loose']:>10.2f}% | {r['accuracy']:>15.2f}%\n"
        )
        rows.append(row_str)

    footer = (
        "--------------------------------------------------------------------------------------------------------------------------\n"
        f"{'Tổng thể trung bình':<32} | {total_gt:>9} | {v1_total_err:>7} | {total_err:>8} | "
        f"{v1_avg_cer:>9.2f}% | {avg_cer:>10.2f}% | {avg_acc:>15.2f}%\n"
        "==========================================================================================================================\n"
    )

    full_report = header + "".join(rows) + footer
    print("\n" + full_report)

    # Lưu ra file results/eval_results.txt
    txt_path = RESULTS_DIR / "eval_results.txt"
    with open(txt_path, "w", encoding="utf-8") as f:
        f.write(full_report)
        f.write("\n\nCHI TIẾT SAI SỐ TỪNG FILE:\n" + "=" * 80 + "\n")
        for r in results:
            f.write(f"\n--- [File: {r['file']}] ---\n")
            f.write(f"Errors: {r['errors']} (Del: {r['deletions']}, Ins: {r['insertions']}, Sub: {r['substitutions']}) | CER Loose: {r['cer_loose']:.2f}% | CER Std: {r['cer_std']:.2f}%\n")
            f.write(f"Ref (Gốc)      : {r['ref_raw']}\n")
            f.write(f"Hyp (Gốc)      : {r['hyp_raw']}\n")
            f.write(f"Ref (Chuẩn hóa): {r['ref_clean']}\n")
            f.write(f"Hyp (Chuẩn hóa): {r['hyp_clean']}\n")

    # Lưu ra file results/eval_results.json
    json_path = RESULTS_DIR / "eval_results.json"
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump({
            "timestamp": timestamp_str,
            "dsp_mode": args.mode,
            "ws_url": args.ws_url,
            "summary": {
                "total_gt_chars": total_gt,
                "total_errors": total_err,
                "cer_v1_avg": v1_avg_cer,
                "cer_dsp_avg": avg_cer,
                "accuracy_avg": avg_acc,
                "match_rate_avg": avg_match,
            },
            "details": results
        }, f, ensure_ascii=False, indent=2)

    print(f"✅ Đã lưu báo cáo chi tiết vào:\n  • {txt_path}\n  • {json_path}")


if __name__ == "__main__":
    main()
