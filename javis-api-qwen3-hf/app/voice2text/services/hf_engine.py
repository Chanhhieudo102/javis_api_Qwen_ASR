import asyncio
import io
import os
import re
import tempfile
import wave

import torch
from transformers import AutoModelForMultimodalLM, AutoProcessor

from app.common.logging import get_logger
from app.voice2text.constants.config import MODEL_NAME

logger = get_logger(__name__)


class HFEngine:
    """
    Singleton for HuggingFace Transformers logic (Qwen3-ASR).
    This mimics the logic from 03_09_02_modal_qwen3_serve.py but integrated via Clean Architecture.
    """

    _instance = None
    _lock = asyncio.Lock()

    def __init__(self):
        if HFEngine._instance is not None:
            raise Exception("This class is a singleton!")
        self.processor = None
        self.tokenizer = None
        self.model = None
        self.silero_model = None
        self.VADIteratorClass = None

    @classmethod
    def get_instance(cls) -> "HFEngine":
        if cls._instance is None:
            cls._instance = HFEngine()
            cls._instance.load_model()
        return cls._instance

    def load_model(self) -> None:
        """Load the HF Model, Processor, and Silero VAD into memory."""
        logger.info(f"Loading Qwen3-ASR model from {MODEL_NAME}...")
        self.processor = AutoProcessor.from_pretrained(MODEL_NAME)
        
        self.model = AutoModelForMultimodalLM.from_pretrained(
            MODEL_NAME,
            torch_dtype=torch.bfloat16 if torch.cuda.is_bf16_supported() else torch.float16,
            device_map="auto"
        )
        self.model.eval()
        logger.info("Qwen3-ASR Model loaded successfully!")

        logger.info("[INIT] Loading Silero VAD...")
        self.silero_model, utils = torch.hub.load(
            repo_or_dir='snakers4/silero-vad',
            model='silero_vad',
            force_reload=False,
            onnx=False,
            trust_repo=True
        )
        self.VADIteratorClass = utils[3]
        logger.info("[INIT] Silero VAD loaded!")

        self._warmup()

    def _warmup(self) -> None:
        """Warmup the model to prevent 20-30s delay on first request."""
        logger.info("[INIT] Warming up model...")
        try:
            with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
                with wave.open(tmp.name, 'wb') as wf:
                    wf.setnchannels(1)
                    wf.setsampwidth(2)
                    wf.setframerate(16000)
                    wf.writeframes(b'\x00' * 32000)  # 1 sec silence
                inputs = self.processor.apply_transcription_request(audio=tmp.name, language="Japanese").to(self.model.device, self.model.dtype)
                with torch.no_grad():
                    self.model.generate(**inputs, max_new_tokens=10)
                os.remove(tmp.name)
            logger.info("[INIT] Warmup complete!")
        except Exception as e:
            logger.error(f"[INIT] Warmup failed: {e}")

    def create_vad_iterator(self, threshold: float = 0.3, min_silence_duration_ms: int = 1000):
        """Create a new VAD iterator instance for a session."""
        return self.VADIteratorClass(self.silero_model, threshold=threshold, min_silence_duration_ms=min_silence_duration_ms)

    def generate_text(self, pcm_bytes: bytes, language: str = "Japanese") -> str:
        """
        Pad 300ms of silence, save to wav, run generation.
        Matches pipeline "none" from v3.
        """
        wav_io = io.BytesIO()
        with wave.open(wav_io, 'wb') as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(16000)
            
            # Audio Padding: Thêm 300ms khoảng lặng vào đầu và cuối để khắc phục CNN Edge Effects
            padding_bytes = b'\x00' * int(16000 * 2 * 0.3)
            padded_pcm_bytes = padding_bytes + pcm_bytes + padding_bytes
            wf.writeframes(padded_pcm_bytes)

        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
            tmp.write(wav_io.getvalue())
            tmp_path = tmp.name

        try:
            inputs = self.processor.apply_transcription_request(
                audio=tmp_path,
                language=language
            ).to(self.model.device, self.model.dtype)

            with torch.no_grad():
                output_ids = self.model.generate(
                    **inputs,
                    max_new_tokens=256,
                    do_sample=False,
                    num_beams=1,
                    repetition_penalty=1.02,
                    pad_token_id=self.processor.tokenizer.pad_token_id,
                    eos_token_id=self.processor.tokenizer.eos_token_id,
                )

            prompt_len = inputs["input_ids"].shape[1]
            generated_ids = output_ids[:, prompt_len:] if output_ids.shape[1] > prompt_len else output_ids
            
            try:
                clean_text = self.processor.decode(generated_ids, return_format="transcription_only")[0]
                return clean_text.strip()
            except TypeError:
                raw_text = self.processor.decode(generated_ids[0], skip_special_tokens=True)
                clean_text = re.sub(r"^.*?<asr_text>\s*", "", raw_text, flags=re.DOTALL)
                clean_text = re.sub(r"^language\s+[A-Za-z0-9_]+\s*", "", clean_text)
                return clean_text.strip()
        except Exception as e:
            logger.error(f"[ASR Error] {e}")
            return ""
        finally:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)
