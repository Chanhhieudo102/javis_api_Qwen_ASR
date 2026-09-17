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
    VAD_THRESHOLD: float = 0.18          # conservative: 0.15 caused false triggers
    VAD_MIN_SILENCE_MS: int = 750        # balance: 650 too aggressive, 800 too slow
    VAD_PREROLL_SEC: float = 1.5         # audio pre-roll buffer before speech start
