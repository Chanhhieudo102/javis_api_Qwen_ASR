"""Audio DSP preprocessing service matching encode/app/encode/services/audio_dsp_service.py

Pipeline:
1. Smart Mono (Correlation-based stereo downmix)
2. Pre-limiter / De-clipping (tanh knee > 0.95)
3. Butterworth High-Pass Filter (HPF 80Hz) with state persistence
4. Resampling to 16,000 Hz (soxr / polyphase / librosa)
5. Level Processing (Peak Normalization for 'ideal', Adaptive RMS AGC for 'meeting')
6. SoftClip Limiter (tanh knee > 0.95)
7. PCM16 Conversion (16-bit linear PCM Little Endian)
"""

import logging
from typing import Optional, Tuple

import numpy as np

from app.voice2text.constants.dsp_constants import AudioDSPMode, DSPConstants

logger = logging.getLogger(__name__)


class AudioDSPService:
    """Service providing high-fidelity audio conditioning and DSP algorithms."""

    @staticmethod
    def smart_mono(data: np.ndarray, num_ch: int = 1) -> np.ndarray:
        """Intelligently combine channels to mono based on Pearson correlation."""
        if num_ch == 1 or data.ndim == 1:
            return data.flatten()

        ch0 = data[:, 0]
        ch1 = data[:, 1]
        c0 = float(np.std(ch0))
        c1 = float(np.std(ch1))

        if c0 > 1e-6 and c1 > 1e-6:
            r = float(np.corrcoef(ch0, ch1)[0, 1])
            if r >= 0.85:
                return (ch0 + ch1) * 0.5
            elif r < -0.3:
                return (ch0 - ch1) * 0.5
            else:
                return ch0 if c0 >= c1 else ch1

        return ch0 if c0 >= c1 else ch1

    @staticmethod
    def apply_pre_limiter(mono: np.ndarray, threshold: float = DSPConstants.SOFT_CLIP_THRESHOLD) -> np.ndarray:
        """De-clip and compress overdriven peaks above threshold using tanh knee."""
        abs_m = np.abs(mono)
        over_m = abs_m > threshold
        if np.any(over_m):
            return np.sign(mono) * np.where(
                over_m,
                threshold + (1.0 - threshold) * np.tanh((abs_m - threshold) / (1.0 - threshold)),
                abs_m,
            )
        return mono

    @staticmethod
    def apply_hpf(
        mono: np.ndarray,
        sample_rate: int,
        cutoff_hz: float = DSPConstants.HPF_CUTOFF_HZ,
        zi: Optional[np.ndarray] = None,
    ) -> Tuple[np.ndarray, Optional[np.ndarray]]:
        """Apply Butterworth 2nd-order high-pass filter with optional state persistence."""
        try:
            from scipy.signal import butter, sosfilt, sosfilt_zi

            nyq = sample_rate / 2.0
            cutoff = min(cutoff_hz, nyq * 0.9)
            sos = butter(2, cutoff / nyq, btype="highpass", output="sos")
            if zi is None:
                zi = sosfilt_zi(sos) * mono[0] if len(mono) > 0 else sosfilt_zi(sos)
                filtered, new_zi = sosfilt(sos, mono, zi=zi)
            else:
                filtered, new_zi = sosfilt(sos, mono, zi=zi)
            return filtered.astype(np.float32), new_zi
        except Exception:
            return mono.astype(np.float32), zi

    @staticmethod
    def resample_to_16k(signal: np.ndarray, orig_sr: int) -> np.ndarray:
        """High-fidelity resampling to 16,000 Hz using soxr / librosa / scipy."""
        target_sr = DSPConstants.TARGET_SAMPLE_RATE
        if orig_sr == target_sr:
            return signal.astype(np.float32)

        # 1. Try soxr (best quality & performance)
        try:
            import soxr
            return soxr.resample(signal, orig_sr, target_sr).astype(np.float32)
        except Exception:
            pass

        # 2. Try librosa (soxr or polyphase backend)
        try:
            import librosa
            return librosa.resample(signal, orig_sr=orig_sr, target_sr=target_sr).astype(np.float32)
        except Exception:
            pass

        # 3. Try scipy.signal.resample_poly
        try:
            from math import gcd

            from scipy.signal import resample_poly
            g = gcd(orig_sr, target_sr)
            up = target_sr // g
            down = orig_sr // g
            return resample_poly(signal, up, down).astype(np.float32)
        except Exception:
            pass

        # Fallback to linear interpolation if no DSP library is installed
        out_len = max(1, int(round(len(signal) * target_sr / orig_sr)))
        xp = np.linspace(0, len(signal) - 1, len(signal))
        x_new = np.linspace(0, len(signal) - 1, out_len)
        return np.interp(x_new, xp, signal).astype(np.float32)

    @staticmethod
    def apply_telephony_cleaner(signal: np.ndarray, orig_sr: int) -> np.ndarray:
        """Filter out codec quantization hiss above 3800Hz for narrowband 8kHz audio."""
        if orig_sr <= 8000:
            try:
                from scipy.signal import butter, sosfilt
                nyq = DSPConstants.TARGET_SAMPLE_RATE / 2.0
                sos = butter(2, 3800.0 / nyq, btype="lowpass", output="sos")
                return sosfilt(sos, signal).astype(np.float32)
            except Exception:
                pass
        return signal

    @staticmethod
    def smooth_compressor(
        data: np.ndarray,
        sample_rate: int = 16000,
        threshold_db: float = DSPConstants.COMP_THRESHOLD_DB,
        ratio: float = DSPConstants.COMP_RATIO,
        attack_ms: float = DSPConstants.COMP_ATTACK_MS,
        release_ms: float = DSPConstants.COMP_RELEASE_MS,
        makeup_gain_db: float = DSPConstants.COMP_MAKEUP_GAIN_DB,
    ) -> np.ndarray:
        """Sample-by-sample envelope follower compressor matching COMP_MEETING in audio_processing_VAD.js.

        Smooths sudden acoustic level variations and protects against distortion prior to AGC.
        """
        if len(data) == 0:
            return data

        alpha_attack = float(np.exp(-1.0 / (sample_rate * (attack_ms / 1000.0))))
        alpha_release = float(np.exp(-1.0 / (sample_rate * (release_ms / 1000.0))))
        threshold_linear = float(10.0 ** (threshold_db / 20.0))
        makeup = float(10.0 ** (makeup_gain_db / 20.0))
        exponent = float(1.0 - 1.0 / ratio)

        result = np.empty_like(data, dtype=np.float32)
        env = 0.0
        abs_data = np.abs(data)
        for i in range(len(data)):
            level = float(abs_data[i])
            if level > env:
                env = alpha_attack * env + (1.0 - alpha_attack) * level
            else:
                env = alpha_release * env + (1.0 - alpha_release) * level

            if env > threshold_linear:
                gain = (threshold_linear / env) ** exponent
            else:
                gain = 1.0
            result[i] = data[i] * gain * makeup
        return result

    @staticmethod
    def adaptive_rms_agc(
        data: np.ndarray,
        sr: int = 16000,
        target_rms_db: float = DSPConstants.AGC_TARGET_RMS_DB,
        window_sec: float = DSPConstants.AGC_WINDOW_SEC,
        hop_sec: float = DSPConstants.AGC_HOP_SEC,
        noise_floor_db: float = DSPConstants.AGC_NOISE_FLOOR_DB,
        max_boost_db: float = DSPConstants.AGC_MAX_BOOST_DB,
        max_cut_db: float = DSPConstants.AGC_MAX_CUT_DB,
        attack_ms: float = DSPConstants.AGC_ATTACK_MS,
        release_ms: float = DSPConstants.AGC_RELEASE_MS,
    ) -> np.ndarray:
        """Adaptive RMS AGC with sliding window, matching encode/audio_processing_VAD.js."""
        if len(data) == 0:
            return data

        total_samples = len(data)
        hop_samples = max(1, int(round(sr * hop_sec)))
        window_samples = max(hop_samples, int(round(sr * window_sec)))
        num_frames = int(np.ceil(total_samples / hop_samples))

        frame_energies = np.zeros(num_frames, dtype=np.float32)
        for f in range(num_frames):
            start = f * hop_samples
            end = min(total_samples, start + hop_samples)
            frame_energies[f] = np.mean(data[start:end] ** 2) if end > start else 0.0

        window_frames = max(1, int(round(window_samples / hop_samples)))
        window_energies = np.zeros(num_frames, dtype=np.float32)
        running_sum = 0.0
        for f in range(num_frames):
            running_sum += frame_energies[f]
            if f >= window_frames:
                running_sum -= frame_energies[f - window_frames]
            count = min(f + 1, window_frames)
            window_energies[f] = running_sum / count

        alpha_attack = np.exp(-hop_samples / (sr * (attack_ms / 1000.0)))
        alpha_release = np.exp(-hop_samples / (sr * (release_ms / 1000.0)))

        frame_gains = np.zeros(num_frames, dtype=np.float32)
        curr_gain = 1.0
        last_active_gain = 1.0

        for f in range(num_frames):
            rms = np.sqrt(window_energies[f] + 1e-12)
            rms_db = 20.0 * np.log10(rms)
            if rms_db >= noise_floor_db:
                raw_gain_db = target_rms_db - rms_db
                target_gain_db = max(max_cut_db, min(max_boost_db, raw_gain_db))
                last_active_gain = 10.0 ** (target_gain_db / 20.0)
            else:
                target_gain_db = 20.0 * np.log10(max(1e-4, last_active_gain))

            target_gain = 10.0 ** (target_gain_db / 20.0)
            if target_gain < curr_gain:
                curr_gain = alpha_attack * curr_gain + (1.0 - alpha_attack) * target_gain
            else:
                curr_gain = alpha_release * curr_gain + (1.0 - alpha_release) * target_gain
            frame_gains[f] = curr_gain

        output = np.zeros(total_samples, dtype=np.float32)
        prev_gain = frame_gains[0]
        for f in range(num_frames):
            start = f * hop_samples
            end = min(total_samples, start + hop_samples)
            span = end - start
            next_gain = frame_gains[f]
            if span > 0:
                frac = np.linspace(0.0, 1.0, span, endpoint=False)
                interp_gain = prev_gain + frac * (next_gain - prev_gain)
                s = data[start:end] * interp_gain
                abs_s = np.abs(s)
                over = abs_s > DSPConstants.SOFT_CLIP_THRESHOLD
                if np.any(over):
                    s[over] = np.sign(s[over]) * (
                        DSPConstants.SOFT_CLIP_THRESHOLD
                        + (1.0 - DSPConstants.SOFT_CLIP_THRESHOLD)
                        * np.tanh((abs_s[over] - DSPConstants.SOFT_CLIP_THRESHOLD) / (1.0 - DSPConstants.SOFT_CLIP_THRESHOLD))
                    )
                output[start:end] = np.clip(s, -1.0, 1.0)
            prev_gain = next_gain

        return output

    @staticmethod
    def peak_normalize(data: np.ndarray, target_db: float = DSPConstants.PEAK_TARGET_DBFS) -> np.ndarray:
        """Normalize signal peak to target dBFS."""
        peak = float(np.max(np.abs(data))) if len(data) > 0 else 0.0
        if peak > 1e-6:
            target_amp = 10.0 ** (target_db / 20.0)
            gain = min(target_amp / peak, 10.0)
            return data * gain
        return data

    @staticmethod
    def soft_clip(data: np.ndarray, threshold: float = DSPConstants.SOFT_CLIP_THRESHOLD) -> np.ndarray:
        """Apply smooth tanh soft-clipping for values exceeding threshold."""
        abs_s = np.abs(data)
        over = abs_s > threshold
        if np.any(over):
            result = data.copy()
            result[over] = np.sign(result[over]) * (
                threshold + (1.0 - threshold) * np.tanh((abs_s[over] - threshold) / (1.0 - threshold))
            )
            return np.clip(result, -1.0, 1.0)
        return np.clip(data, -1.0, 1.0)

    @classmethod
    def process_full_audio(
        cls,
        data: np.ndarray,
        orig_sr: int,
        num_ch: int = 1,
        mode: str = AudioDSPMode.MEETING,
    ) -> bytes:
        """Execute full batch DSP conditioning pipeline and return PCM16 bytes."""
        mono = cls.smart_mono(data, num_ch)
        mono = cls.apply_pre_limiter(mono)
        mono, _ = cls.apply_hpf(mono, orig_sr, cutoff_hz=DSPConstants.HPF_CUTOFF_HZ)
        resampled = cls.resample_to_16k(mono, orig_sr)

        if orig_sr <= 8000:
            resampled = cls.apply_telephony_cleaner(resampled, orig_sr)

        mode_str = str(mode).lower()
        if mode_str in ("meeting", AudioDSPMode.MEETING.value):
            compressed = cls.smooth_compressor(
                resampled,
                sample_rate=DSPConstants.TARGET_SAMPLE_RATE,
                threshold_db=DSPConstants.COMP_THRESHOLD_DB,
                ratio=DSPConstants.COMP_RATIO,
                attack_ms=DSPConstants.COMP_ATTACK_MS,
                release_ms=DSPConstants.COMP_RELEASE_MS,
                makeup_gain_db=DSPConstants.COMP_MAKEUP_GAIN_DB,
            )
            processed = cls.adaptive_rms_agc(compressed, sr=DSPConstants.TARGET_SAMPLE_RATE)
        elif mode_str in ("ideal", AudioDSPMode.IDEAL.value):
            processed = cls.peak_normalize(resampled, target_db=DSPConstants.PEAK_TARGET_DBFS)
        else:
            processed = resampled

        processed = cls.soft_clip(processed)
        pcm16 = (processed * 32767.0).astype(np.int16)
        return pcm16.tobytes()


class StreamingDSPProcessor:
    """Stateful streaming DSP processor for continuous real-time audio chunks."""

    def __init__(
        self,
        mode: str = AudioDSPMode.MEETING,
        sample_rate: int = 16000,
        window_sec: float = DSPConstants.AGC_WINDOW_SEC,
    ):
        """Initialize streaming processor with specified DSP mode and sample rate."""
        self.mode = str(mode).lower()
        self.sample_rate = sample_rate
        self.window_sec = window_sec
        self.zi: Optional[np.ndarray] = None
        self.prev_gain: float = 1.0
        self.last_active_gain: float = 1.0
        self.recent_energies: list[float] = []

    def reset(self):
        """Reset internal filter states."""
        self.zi = None
        self.prev_gain = 1.0
        self.last_active_gain = 1.0
        self.recent_energies.clear()

    def process_chunk(self, chunk: np.ndarray) -> np.ndarray:
        """Process a 16kHz mono float32 chunk with persistent filter state."""
        if len(chunk) == 0 or self.mode in ("none", AudioDSPMode.NONE.value):
            return np.clip(chunk, -1.0, 1.0)

        # 1. Pre-limiter
        out = AudioDSPService.apply_pre_limiter(chunk)

        # 2. HPF 80Hz with continuous state
        out, self.zi = AudioDSPService.apply_hpf(out, self.sample_rate, zi=self.zi)

        # 3. Dynamic Level Processing
        if self.mode in ("meeting", AudioDSPMode.MEETING.value):
            chunk_samples = len(out)
            chunk_energy = float(np.mean(out ** 2)) if chunk_samples > 0 else 0.0
            self.recent_energies.append(chunk_energy)
            max_stored = max(1, int(round(self.sample_rate * self.window_sec / max(1, chunk_samples))))
            while len(self.recent_energies) > max_stored:
                self.recent_energies.pop(0)

            avg_energy = float(np.mean(self.recent_energies))
            rms = float(np.sqrt(avg_energy + 1e-12))
            rms_db = 20.0 * np.log10(rms)

            if rms_db >= DSPConstants.AGC_NOISE_FLOOR_DB:
                raw_gain_db = DSPConstants.AGC_TARGET_RMS_DB - rms_db
                target_gain_db = max(DSPConstants.AGC_MAX_CUT_DB, min(DSPConstants.AGC_MAX_BOOST_DB, raw_gain_db))
                self.last_active_gain = 10.0 ** (target_gain_db / 20.0)
            else:
                target_gain_db = 20.0 * np.log10(max(1e-4, self.last_active_gain))

            target_gain = 10.0 ** (target_gain_db / 20.0)
            alpha = (
                np.exp(-chunk_samples / (self.sample_rate * (DSPConstants.AGC_ATTACK_MS / 1000.0)))
                if target_gain < self.prev_gain
                else np.exp(-chunk_samples / (self.sample_rate * (DSPConstants.AGC_RELEASE_MS / 1000.0)))
            )
            curr_gain = alpha * self.prev_gain + (1.0 - alpha) * target_gain

            span = chunk_samples
            if span > 0:
                frac = np.linspace(0.0, 1.0, span, endpoint=False)
                gain_ramp = self.prev_gain + frac * (curr_gain - self.prev_gain)
                out = out * gain_ramp
            self.prev_gain = curr_gain
        elif self.mode in ("ideal", AudioDSPMode.IDEAL.value):
            peak = float(np.max(np.abs(out))) if len(out) > 0 else 0.0
            if peak > 0.891:
                out = out * (0.891 / peak)

        # 4. SoftClip Limiter
        return AudioDSPService.soft_clip(out)
