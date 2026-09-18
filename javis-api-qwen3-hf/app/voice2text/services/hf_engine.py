import asyncio
import io
import os
import re
import tempfile
import wave
from typing import Optional

import torch
from transformers import AutoModelForMultimodalLM, AutoProcessor

from app.common.logging import get_logger
from app.voice2text.constants.config import MODEL_NAME
from app.voice2text.constants.dsp_constants import DSPConstants


logger = get_logger(__name__)


class HFEngine:
    """Singleton for HuggingFace Transformers logic (Qwen3-ASR).

    This mimics the logic from 03_09_02_modal_qwen3_serve.py but integrated via Clean Architecture.
    """

    _instance = None
    _lock = asyncio.Lock()

    # Audio padding constants
    LEADING_PADDING_SEC: float = 0.20

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

    def create_vad_iterator(self, threshold: float = DSPConstants.VAD_THRESHOLD, min_silence_duration_ms: int = DSPConstants.VAD_MIN_SILENCE_MS):
        """Create a new VAD iterator instance for a session (params from DSPConstants)."""
        return self.VADIteratorClass(self.silero_model, threshold=threshold, min_silence_duration_ms=min_silence_duration_ms)

    def generate_text(self, pcm_bytes: bytes, language: str = "Japanese") -> str:
        """
        Pad 300ms of silence, save to wav, run generation.
        Matches pipeline "none" from v3.
        """
        wav_io = io.BytesIO()
        with wave.open(wav_io, 'wb') as wf:
            wf.setnchannels(1)
            wf.setsampwidth(DSPConstants.BYTES_PER_SAMPLE)
            wf.setframerate(DSPConstants.TARGET_SAMPLE_RATE)
            
            # Leading silence protects onset phonemes against CNN filter edge effects;
            # no trailing padding ensures the model stops cleanly without hallucination
            padding_bytes_count = int(
                DSPConstants.TARGET_SAMPLE_RATE * DSPConstants.BYTES_PER_SAMPLE * self.LEADING_PADDING_SEC
            )
            leading_padding = b'\x00' * padding_bytes_count
            wf.writeframes(leading_padding + pcm_bytes)


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
                    max_new_tokens=384,
                    do_sample=False,
                    num_beams=2,
                    length_penalty=1.0,
                    repetition_penalty=1.0,
                    pad_token_id=self.processor.tokenizer.pad_token_id,
                    eos_token_id=self.processor.tokenizer.eos_token_id,
                )


            prompt_len = inputs["input_ids"].shape[1]
            generated_ids = output_ids[:, prompt_len:] if output_ids.shape[1] > prompt_len else output_ids
            
            try:
                raw = self.processor.decode(generated_ids, return_format="transcription_only")[0]
                return self._postprocess(raw.strip())
            except TypeError:
                raw_text = self.processor.decode(generated_ids[0], skip_special_tokens=True)
                raw_text = re.sub(r"^.*?<asr_text>\s*", "", raw_text, flags=re.DOTALL)
                raw_text = re.sub(r"^language\s+[A-Za-z0-9_]+\s*", "", raw_text)
                return self._postprocess(raw_text.strip())
        except Exception as e:
            logger.error(f"[ASR Error] {e}")
            return ""
        finally:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)

    # -----------------------------------------------------------------------
    # Post-processing: Remove hallucination tails
    # -----------------------------------------------------------------------
    # Qwen3-ASR sometimes appends off-topic prose after the real speech ends,
    # especially when the audio tail contains silence.  We detect common
    # hallucination markers (narrative starters, ellipsis-like patterns) and
    # truncate the output at the first such occurrence.
    # Patterns are kept general – no hard-coded transcription content.
    _HALLUCINATION_PATTERNS = re.compile(
        r"(?:"
        # Narrative / story starters (Japanese)
        r"この(?:作品|物語|小説|映画|番組|曲|歌|本|記事|内容|テキスト|サービス|システム|ページ|サイト)"
        r"|以下は.{0,10}(?:です|ます|である)"
        r"|次の.{0,10}(?:文章|テキスト|内容|会話|音声)"
        r"|訳文[:：]"
        r"|字幕[:：]"
        # Generic connective prose Qwen generates after silence
        r"|このように(?:して)?[、。]"
        r"|このため[、。]"
        r"|したがって[、。]"
        r"|なお[、。].{0,5}(?:です|ます|でした|ました)"
        # Off-topic personal narrative starters
        r"|その時[、,]?(?:私|俺|僕|彼|彼女|我々)"
        r"|そして[、,]?(?:私|俺|僕|彼|彼女)は"
        # Instruction/translation artifacts
        r"|^(?:翻訳|要約|まとめ|解説)[：:]"
        # Broken/repeated character artifacts (4+ repeated chars)
        r"|(?P<rep_char>.)(?P=rep_char){4,}"
        # English narrative starters
        r"|The following is"
        r"|In this (?:video|audio|recording|episode)"
        r")",
        re.UNICODE | re.MULTILINE,
    )

    # Regex to split text into sentences for repeat detection
    _SENTENCE_SPLIT = re.compile(r'(?<=[。！？\n])\s*')

    def _remove_hallucination_tail(self, text: str) -> str:
        """Strip hallucinated prose appended after real speech."""
        if not text:
            return text
        m = self._HALLUCINATION_PATTERNS.search(text)
        if m:
            truncated = text[:m.start()].rstrip("。、!！?？\n ")
            logger.debug(
                f"[Hallucination] Stripped tail at pos {m.start()}: ...{text[max(0,m.start()-20):m.start()]!r}"
                f" | removed: {text[m.start():m.start()+40]!r}"
            )
            return truncated
        return text

    def _remove_consecutive_repeats(self, text: str) -> str:
        """Remove model hallucination loops where a phrase repeats 3+ times in a row.

        Preserves legitimate 2-turn conversational exchanges (e.g. both speakers saying
        'お世話になります。' or '失礼いたします。') while safely dropping unnatural 3+
        consecutive repetitions generated during audio pauses.
        """
        if not text:
            return text
        # Split on sentence-ending punctuation, keeping the delimiter
        parts = self._SENTENCE_SPLIT.split(text)
        deduped = []
        prev = None
        repeat_count = 0
        for part in parts:
            stripped = part.strip()
            if not stripped:
                continue
            if stripped == prev:
                repeat_count += 1
                if repeat_count >= 2:  # Already present twice; 3rd+ is a repetition loop
                    logger.debug(f"[RepeatRemoval] Dropped 3+ repeat: {stripped!r}")
                    continue
            else:
                prev = stripped
                repeat_count = 0
            deduped.append(part)
        return "".join(deduped)


    def _postprocess(self, text: str) -> str:
        """Full post-processing pipeline: hallucination removal then deduplication."""
        text = self._remove_hallucination_tail(text)
        text = self._remove_consecutive_repeats(text)
        return text.strip()
