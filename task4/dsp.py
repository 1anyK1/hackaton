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
    tx_voice_low_hz: float = 120.0
    tx_voice_high_hz: float = 3_400.0
    rx_voice_low_hz: float = 250.0
    rx_voice_high_hz: float = 3_400.0
    channel_filter_hz: float = 55_000.0
    mic_gate_threshold: float = 0.006
    mic_target_rms: float = 0.16
    mic_max_gain: float = 8.0


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


class StatefulIirFilter:
    def __init__(self, b: np.ndarray, a: np.ndarray):
        self.b = np.asarray(b, dtype=np.float64)
        self.a = np.asarray(a, dtype=np.float64)
        self.zi = signal.lfilter_zi(self.b, self.a) * 0.0

    def process(self, samples: np.ndarray) -> np.ndarray:
        filtered, self.zi = signal.lfilter(self.b, self.a, samples, zi=self.zi)
        return filtered.astype(samples.dtype, copy=False)


def butter_filter(
    sample_rate: int,
    low_hz: float | None = None,
    high_hz: float | None = None,
    order: int = 4,
) -> StatefulIirFilter | None:
    nyquist = sample_rate / 2.0
    low = None if low_hz is None or low_hz <= 0 else max(1.0, low_hz) / nyquist
    high = None if high_hz is None or high_hz <= 0 else min(high_hz, nyquist * 0.95) / nyquist

    if low is None and high is None:
        return None
    if low is not None and high is not None:
        if low >= high:
            low = None
        else:
            b, a = signal.butter(order, [low, high], btype="bandpass")
            return StatefulIirFilter(b, a)
    if low is None:
        b, a = signal.butter(order, high, btype="lowpass")
    else:
        b, a = signal.butter(order, low, btype="highpass")
    return StatefulIirFilter(b, a)


class SmoothNoiseGate:
    def __init__(
        self,
        threshold: float,
        close_threshold: float | None = None,
        attack: float = 0.35,
        release: float = 0.08,
    ):
        self.threshold = max(0.0, threshold)
        self.close_threshold = (
            max(0.0, close_threshold)
            if close_threshold is not None
            else self.threshold * 0.65
        )
        self.attack = np.clip(attack, 0.0, 1.0)
        self.release = np.clip(release, 0.0, 1.0)
        self.gain = 1.0 if self.threshold <= 0 else 0.0
        self.is_open = self.threshold <= 0

    def process(self, samples: np.ndarray) -> np.ndarray:
        if self.threshold <= 0 or len(samples) == 0:
            return samples

        level = rms_level(samples)
        if self.is_open and level < self.close_threshold:
            self.is_open = False
        elif not self.is_open and level > self.threshold:
            self.is_open = True

        target = 1.0 if self.is_open else 0.0
        smoothing = self.attack if target > self.gain else self.release
        self.gain = (1.0 - smoothing) * self.gain + smoothing * target
        return (samples * self.gain).astype(np.float32)


class MicProcessor:
    """Clean microphone audio before FM modulation."""

    def __init__(self, config: RadioConfig):
        self.config = config
        self.voice_filter = butter_filter(
            config.audio_rate,
            low_hz=config.tx_voice_low_hz,
            high_hz=config.tx_voice_high_hz,
            order=4,
        )
        self.gate = SmoothNoiseGate(config.mic_gate_threshold, release=0.04)
        self.agc_gain = 1.0

    def process(self, audio_block: np.ndarray) -> np.ndarray:
        audio = audio_to_mono_float32(audio_block)
        if self.voice_filter is not None:
            audio = self.voice_filter.process(audio)
        audio = self.gate.process(audio)

        level = rms_level(audio)
        if level > 1e-4:
            desired = np.clip(
                self.config.mic_target_rms / level,
                1.0 / self.config.mic_max_gain,
                self.config.mic_max_gain,
            )
            self.agc_gain = 0.97 * self.agc_gain + 0.03 * desired

        audio = audio * self.agc_gain
        return np.tanh(audio * 1.15).astype(np.float32)


class FmModulator:
    def __init__(self, config: RadioConfig):
        self.config = config
        self._phase = 0.0
        self._mic_processor = MicProcessor(config)

    def modulate(self, audio_block: np.ndarray) -> np.ndarray:
        audio = self._mic_processor.process(audio_block)
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
        self._channel_filter = butter_filter(
            config.sdr_rate,
            high_hz=config.channel_filter_hz,
            order=5,
        )
        self._deemphasis = self._build_deemphasis_filter()
        self._voice_filter = butter_filter(
            config.audio_rate,
            low_hz=config.rx_voice_low_hz,
            high_hz=config.rx_voice_high_hz,
            order=4,
        )

    def _build_deemphasis_filter(self) -> StatefulIirFilter | None:
        if self.config.deemphasis_tau <= 0:
            return None
        alpha = np.exp(-1.0 / (self.config.audio_rate * self.config.deemphasis_tau))
        return StatefulIirFilter(
            np.array([1.0 - alpha], dtype=np.float64),
            np.array([1.0, -alpha], dtype=np.float64),
        )

    def demodulate(self, iq_block: np.ndarray) -> np.ndarray:
        iq = np.asarray(iq_block, dtype=np.complex64).reshape(-1)
        if len(iq) == 0:
            return np.empty(0, dtype=np.float32)

        if self._channel_filter is not None:
            iq = self._channel_filter.process(iq)

        previous = np.concatenate(([self._last_sample], iq[:-1]))
        self._last_sample = iq[-1]
        phase_diff = np.angle(iq * np.conj(previous)).astype(np.float32)
        audio_sdr = phase_diff * self.config.sdr_rate / (
            2.0 * np.pi * self.config.fm_deviation_hz
        )
        audio = resample_audio(audio_sdr, self.config.sdr_rate, self.config.audio_rate)
        if self._deemphasis is not None:
            audio = self._deemphasis.process(audio)
        if self._voice_filter is not None:
            audio = self._voice_filter.process(audio)
        return np.clip(audio, -1.0, 1.0).astype(np.float32)


class AudioSquelch:
    """Smooth noise gate for demodulated receive audio."""

    def __init__(self, open_threshold: float, close_threshold: float | None = None):
        self.gate = SmoothNoiseGate(
            open_threshold,
            close_threshold=close_threshold,
            attack=0.45,
            release=0.06,
        )

    @property
    def is_open(self) -> bool:
        return self.gate.is_open

    def process(self, audio: np.ndarray) -> np.ndarray:
        return self.gate.process(audio)


def rms_level(samples: np.ndarray) -> float:
    data = np.asarray(samples)
    if len(data) == 0:
        return 0.0
    if np.iscomplexobj(data):
        data = np.abs(data)
    data = data.astype(np.float32)
    return float(np.sqrt(np.mean(np.square(data))))
