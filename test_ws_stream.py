import sys
import asyncio
import json
import wave
import numpy as np
import websockets
import pybase64 as base64

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

WS_URL = "wss://uydo8081--javis-api-qwen3-hf-serve-serve-dev.modal.run/api/v2/transcript/ws/no-diarization"
AUDIO_PATH = "d:/VJ/encode/all_audio_input/media_148280_1767762915627.mp3"

async def test_stream():
    import soundfile as sf
    data, sr = sf.read(AUDIO_PATH)
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

    # Take first 10 seconds for quick test
    audio_data = audio_data[:target_sr * 10]
    pcm16 = (np.clip(audio_data, -1.0, 1.0) * 32767).astype(np.int16).tobytes()
    print(f"Loaded Audio: {len(pcm16)} bytes (~{len(pcm16)/(target_sr*2):.2f}s audio)")

    print(f"Connecting to {WS_URL}...")
    async with websockets.connect(WS_URL, open_timeout=60) as ws:
        ready = await ws.recv()
        print(f"[RECV] Handshake: {ready}")

        # Send config
        await ws.send(json.dumps({"type": "session.update", "model": "qwen3"}))
        await ws.send(json.dumps({"type": "input_audio_buffer.commit"}))

        async def sender():
            chunk_size = 640 # 20ms = 320 samples = 640 bytes
            offset = 0
            while offset < len(pcm16):
                chunk = pcm16[offset:offset+chunk_size]
                b64 = base64.b64encode(chunk).decode("utf-8")
                await ws.send(json.dumps({
                    "type": "input_audio_buffer.append",
                    "audio": b64
                }))
                offset += chunk_size
                await asyncio.sleep(0.01) # Realtime rate
            
            print("[SEND] All chunks sent! Committing final...")
            await ws.send(json.dumps({"type": "input_audio_buffer.commit", "final": True}))

        async def receiver():
            try:
                while True:
                    msg = await asyncio.wait_for(ws.recv(), timeout=10.0)
                    data = json.loads(msg)
                    msg_type = data.get("type", "")
                    if msg_type in ("transcription.partial", "partial"):
                        print(f"[PARTIAL] {data.get('text', '')}")
                    elif msg_type in ("transcription.done", "final"):
                        text = data.get("text", "")
                        if "segments" in data:
                            text = " ".join([s.get("text", "") for s in data.get("segments", [])])
                        print(f"[DONE] Final transcript: {text}")
                        break
                    else:
                        print(f"[MSG] {data}")
            except asyncio.TimeoutError:
                print("[RECEIVER] Timeout waiting for more messages.")

        await asyncio.gather(sender(), receiver())

if __name__ == "__main__":
    asyncio.run(test_stream())
