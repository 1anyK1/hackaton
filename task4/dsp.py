"""DSP primitives for the Pluto walkie-talkie.

The radio path uses narrow-band FM:
microphone audio -> resample to SDR rate -> phase integration -> complex IQ.
The receiver performs the inverse operation with phase-difference FM demodulation.
"""

from __future__ import annotations

from dataclasses import dataclass
from math import gcd

import numpy as np
from scipy import signal


@dataclass(frozen=True)
class RadioConfig:
    audio_rate: int = 48_000
    sdr_rate: int = 960_000
    fm_deviation_hz: float = 5_000.0
    tx_amplitude: float = 0.55
    preemphasis_tau: float = 75e-6
    deemphasis_tau: float = 75e-6


def _resample_ratio(src_rate: int, dst_rate: int) -> tuple[int, int]:
    divisor = gcd(src_rate, dst_rate)
    return dst_rate // divisor, src_rate // divisor


def audio_to_mono_float32(block: np.ndarray) -> np.ndarray:
    """Convert a PortAudio input block to normalized mono float32 samples."""
    audio = np.asarray(block, dtype=np.float32)
    if audio.ndim == 2:
        audio = np.mean(audio, axis=1)
    return np.clip(audio.reshape(-1), -1.0, 1.0).astype(np.float32)


def resample_audio(audio: np.ndarray, src_rate: int, dst_rate: int) -> np.ndarray:
    if src_rate == dst_rate:
        return np.asarray(audio, dtype=np.float32)

    up, down = _resample_ratio(src_rate, dst_rate)
    return signal.resample_poly(audio, up, down).astype(np.float32)


def preemphasis(audio: np.ndarray, sample_rate: int, tau: float = 75e-6) -> np.ndarray:
    """Apply a single-pole high-pass preemphasis filter."""
    if tau <= 0:
        return np.asarray(audio, dtype=np.float32)

    alpha = tau / (tau + 1.0 / sample_rate)
    emphasized = signal.lfilter([1.0, -1.0], [1.0, -alpha], audio)
    return np.clip(emphasized, -1.0, 1.0).astype(np.float32)


def deemphasis(audio: np.ndarray, sample_rate: int, tau: float = 75e-6) -> np.ndarray:
    """Apply a single-pole low-pass deemphasis filter."""
    if tau <= 0:
        return np.asarray(audio, dtype=np.float32)

    alpha = np.exp(-1.0 / (sample_rate * tau))
    filtered = signal.lfilter([1.0 - alpha], [1.0, -alpha], audio)
    return filtered.astype(np.float32)


class FmModulator:
    def __init__(self, config: RadioConfig):
        self.config = config
        self._phase = 0.0

    def modulate(self, audio_block: np.ndarray) -> np.ndarray:
        audio = audio_to_mono_float32(audio_block)
        audio = preemphasis(audio, self.config.audio_rate, self.config.preemphasis_tau)
        baseband = resample_audio(audio, self.config.audio_rate, self.config.sdr_rate)
        baseband = np.clip(baseband, -1.0, 1.0)

        phase_step = 2.0 * np.pi * self.config.fm_deviation_hz / self.config.sdr_rate
        phase = self._phase + np.cumsum(baseband, dtype=np.float64) * phase_step
        self._phase = float(np.mod(phase[-1], 2.0 * np.pi)) if len(phase) else self._phase

        iq = self.config.tx_amplitude * np.exp(1j * phase)
        return iq.astype(np.complex64)


class FmDemodulator:
    def __init__(self, config: RadioConfig):
        self.config = config
        self._last_sample = np.complex64(1.0 + 0.0j)

    def demodulate(self, iq_block: np.ndarray) -> np.ndarray:
        iq = np.asarray(iq_block, dtype=np.complex64).reshape(-1)
        if len(iq) == 0:
            return np.empty(0, dtype=np.float32)

        previous = np.concatenate(([self._last_sample], iq[:-1]))
        self._last_sample = iq[-1]
        phase_diff = np.angle(iq * np.conj(previous)).astype(np.float32)
        audio_sdr = phase_diff * self.config.sdr_rate / (
            2.0 * np.pi * self.config.fm_deviation_hz
        )
        audio = resample_audio(audio_sdr, self.config.sdr_rate, self.config.audio_rate)
        audio = deemphasis(audio, self.config.audio_rate, self.config.deemphasis_tau)
        return np.clip(audio, -1.0, 1.0).astype(np.float32)


def rms_level(samples: np.ndarray) -> float:
    data = np.asarray(samples)
    if len(data) == 0:
        return 0.0
    if np.iscomplexobj(data):
        data = np.abs(data)
    data = data.astype(np.float32)
    return float(np.sqrt(np.mean(np.square(data))))
