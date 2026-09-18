"""Unit tests for AudioDSPService and StreamingDSPProcessor."""

import numpy as np
import pytest

from app.voice2text.constants.dsp_constants import AudioDSPMode
from app.voice2text.services.audio_dsp_service import AudioDSPService, StreamingDSPProcessor


def test_smart_mono_single_channel():
    data = np.array([0.1, -0.2, 0.3], dtype=np.float32)
    mono = AudioDSPService.smart_mono(data, num_ch=1)
    assert mono.shape == (3,)
    assert np.allclose(mono, data)


def test_smart_mono_stereo_correlated():
    # Identical channels -> average
    ch0 = np.sin(np.linspace(0, 2 * np.pi, 100)).astype(np.float32)
    ch1 = ch0.copy()
    stereo = np.column_stack([ch0, ch1])
    mono = AudioDSPService.smart_mono(stereo, num_ch=2)
    assert mono.shape == (100,)
    assert np.allclose(mono, ch0)


def test_pre_limiter_and_soft_clip():
    # Values above 0.95 should be smoothly compressed, not hard clipped
    loud = np.array([1.5, -1.8, 0.5], dtype=np.float32)
    clipped = AudioDSPService.apply_pre_limiter(loud, threshold=0.95)
    assert np.max(np.abs(clipped)) <= 1.0
    assert 0.95 < clipped[0] <= 1.0
    assert -1.0 <= clipped[1] < -0.95
    assert clipped[2] == pytest.approx(0.5)


def test_resample_to_16k():
    sr_in = 8000
    signal = np.sin(np.linspace(0, 2 * np.pi * 10, sr_in)).astype(np.float32)
    resampled = AudioDSPService.resample_to_16k(signal, orig_sr=sr_in)
    assert len(resampled) == 16000
    assert resampled.dtype == np.float32


def test_hpf_attenuates_low_frequencies():
    # 20Hz signal (below 80Hz cutoff) vs 1000Hz signal
    sr = 16000
    t = np.linspace(0, 1, sr, endpoint=False)
    low_freq = np.sin(2 * np.pi * 20 * t).astype(np.float32)
    filtered_low, _ = AudioDSPService.apply_hpf(low_freq, sr, cutoff_hz=80.0)

    # Low frequency energy should be significantly attenuated (> 15 dB)
    energy_orig = np.mean(low_freq ** 2)
    energy_filt = np.mean(filtered_low ** 2)
    assert energy_filt < energy_orig * 0.1


def test_adaptive_rms_agc():
    # Test that AGC boosts quiet signal and keeps output well-behaved
    sr = 16000
    quiet = np.sin(np.linspace(0, 2 * np.pi * 50, sr * 2)).astype(np.float32) * 0.05
    out = AudioDSPService.adaptive_rms_agc(quiet, sr=sr, target_rms_db=-22.0)
    assert len(out) == len(quiet)
    # Output should have higher RMS than quiet input
    rms_in = np.sqrt(np.mean(quiet ** 2))
    rms_out = np.sqrt(np.mean(out ** 2))
    assert rms_out > rms_in


def test_streaming_dsp_processor_state():
    processor = StreamingDSPProcessor(mode=AudioDSPMode.MEETING, sample_rate=16000)
    chunk = (np.sin(np.linspace(0, 2 * np.pi * 20, 320)) * 0.5).astype(np.float32)

    out1 = processor.process_chunk(chunk)
    assert len(out1) == 320
    assert processor.zi is not None  # State preserved

    out2 = processor.process_chunk(chunk)
    assert len(out2) == 320


def test_process_full_audio():
    sr_in = 8000
    audio = np.random.uniform(-0.5, 0.5, sr_in * 2).astype(np.float32)
    pcm16 = AudioDSPService.process_full_audio(audio, orig_sr=sr_in, num_ch=1, mode=AudioDSPMode.MEETING)
    assert isinstance(pcm16, bytes)
    # 2 seconds @ 16kHz = 32,000 samples = 64,000 bytes
    assert len(pcm16) == 16000 * 2 * 2


def test_smart_mono_phase_inverted():
    # 180 degree out-of-phase channels (r = -1.0) -> (ch0 - ch1) * 0.5 avoids cancellation
    ch0 = np.sin(np.linspace(0, 2 * np.pi, 100)).astype(np.float32)
    ch1 = -ch0
    stereo = np.column_stack([ch0, ch1])
    mono = AudioDSPService.smart_mono(stereo, num_ch=2)
    assert mono.shape == (100,)
    # If simply averaged (ch0 + ch1)/2, result would be 0!
    # With phase flip (ch0 - ch1)*0.5 = ch0, signal is preserved.
    assert np.max(np.abs(mono)) > 0.5
    assert np.allclose(mono, ch0)


def test_smooth_compressor():
    sr = 16000
    # Loud audio above threshold (-24 dBFS)
    loud = np.sin(np.linspace(0, 2 * np.pi * 100, sr)).astype(np.float32) * 0.8
    compressed = AudioDSPService.smooth_compressor(
        loud,
        sample_rate=sr,
        threshold_db=-24.0,
        ratio=1.25,
        attack_ms=15.0,
        release_ms=500.0,
    )
    assert len(compressed) == len(loud)
    # Compressed peaks should be reduced compared to original
    assert np.max(np.abs(compressed)) < np.max(np.abs(loud))

