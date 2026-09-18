"""Audio DSP constants and enums for voice2text module."""

from enum import Enum


class AudioDSPMode(str, Enum):
    """Audio DSP preprocessing mode."""

    NONE = "none"
    IDEAL = "ideal"
    MEETING = "meeting"


class DSPConstants:
    """DSP constants matching audio_processing_VAD.js and encode audio_dsp_service."""

    TARGET_SAMPLE_RATE: int = 16000
    BYTES_PER_SAMPLE: int = 2  # PCM16
    HPF_CUTOFF_HZ: float = 80.0    # encode/audio_bridge.py uses 80Hz HPF
    SOFT_CLIP_THRESHOLD: float = 0.95
    PEAK_TARGET_DBFS: float = -1.0
    AGC_TARGET_RMS_DB: float = -22.0   # encode/audio_bridge.py uses -22.0
    AGC_NOISE_FLOOR_DB: float = -38.0
    AGC_WINDOW_SEC: float = 1.5
    AGC_HOP_SEC: float = 0.05
    AGC_MAX_BOOST_DB: float = 5.0      # same as encode folder StatefulAGCProcessor
    AGC_MAX_CUT_DB: float = -3.0
    AGC_ATTACK_MS: float = 30.0
    AGC_RELEASE_MS: float = 350.0

    # Smooth Compressor constants matching COMP_MEETING in audio_processing_VAD.js
    COMP_THRESHOLD_DB: float = -24.0
    COMP_RATIO: float = 1.25
    COMP_ATTACK_MS: float = 15.0
    COMP_RELEASE_MS: float = 500.0
    COMP_MAKEUP_GAIN_DB: float = 0.0

    # VAD parameters for Silero VAD (used in transcription_ws_service)
    VAD_THRESHOLD: float = 0.35          # Balanced threshold: avoids breath/line hum triggers on telephony audio
    VAD_MIN_SILENCE_MS: int = 950        # 950ms prevents mid-clause premature cuts while keeping latency low
    VAD_PREROLL_SEC: float = 1.2         # 1.2s pre-roll ensures onset phonemes (consonants/vowels) are not clipped

    # Streaming WebSocket & VAD buffer thresholds
    PCM16_MAX_AMPLITUDE: float = 32768.0
    VAD_FRAME_SAMPLES: int = 512
    VAD_FRAME_BYTES: int = 1024          # 512 samples * 2 bytes (PCM16)
    MIN_SPEECH_DURATION_SEC: float = 0.55 # 550ms minimum for meaningful Japanese utterance
    MIN_SPEECH_RMS: float = 0.010        # ~ -40 dBFS threshold for speech presence
    SHORT_SEGMENT_ENERGY_THRESHOLD: float = 0.015 # Extra energy threshold for short chunks (<0.8s) to suppress breaths
    MIN_UNCONFIRMED_SPEECH_RMS: float = 0.012
    MAX_SEGMENT_SECONDS: float = 29.0
    SHORT_AUDIO_HALLUCINATION_SEC: float = 1.5
    PING_INTERVAL_SEC: float = 30.0
    SEGMENT_ORDER_POLL_INTERVAL_SEC: float = 0.05
