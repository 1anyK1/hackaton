#!/usr/bin/env python3
"""Real-time walkie-talkie for ADALM-Pluto SDR.

Examples:
    python pluto_walkie_talkie.py tx --freq 915e6
    python pluto_walkie_talkie.py rx --freq 915e6
    python pluto_walkie_talkie.py trx --tx-freq 915e6 --rx-freq 916e6
"""

from __future__ import annotations

import argparse
import copy
import queue
import signal
import sys
import threading
import time

import adi
import numpy as np

from dsp import FmDemodulator, FmModulator, RadioConfig, rms_level


DEFAULT_URI = "ip:192.168.3.1"
DEFAULT_FREQ = int(915e6)
DEFAULT_RF_BW = int(200e3)
DEFAULT_AUDIO_BLOCK = 1_024
DEFAULT_RX_BUFFER = 20_480


def import_sounddevice():
    try:
        import sounddevice as sd
    except OSError as exc:
        raise RuntimeError(
            "sounddevice найден, но системная библиотека PortAudio отсутствует. "
            "Установите ее командой: sudo apt install libportaudio2 "
            "или запустите программу с --audio-backend soundcard."
        ) from exc
    return sd


def import_soundcard():
    try:
        import soundcard as sc
    except ImportError as exc:
        raise RuntimeError(
            "Аудиобэкенд soundcard не установлен. Выполните: "
            "pip install soundcard"
        ) from exc
    return sc


class StopFlag:
    def __init__(self) -> None:
        self.event = threading.Event()

    def install_signal_handlers(self) -> None:
        def _stop(_signum: int, _frame: object) -> None:
            self.event.set()

        signal.signal(signal.SIGINT, _stop)
        signal.signal(signal.SIGTERM, _stop)


def configure_tx_sdr(args: argparse.Namespace) -> adi.Pluto:
    sdr = adi.Pluto(args.uri)
    sdr.sample_rate = int(args.sdr_rate)
    sdr.tx_lo = int(args.tx_freq)
    sdr.tx_rf_bandwidth = int(args.rf_bandwidth)
    sdr.tx_hardwaregain_chan0 = float(args.tx_gain)
    sdr.tx_cyclic_buffer = False
    return sdr


def configure_rx_sdr(args: argparse.Namespace) -> adi.Pluto:
    sdr = adi.Pluto(args.uri)
    sdr.sample_rate = int(args.sdr_rate)
    sdr.rx_lo = int(args.rx_freq)
    sdr.rx_rf_bandwidth = int(args.rf_bandwidth)
    sdr.rx_buffer_size = int(args.rx_buffer)
    sdr.gain_control_mode_chan0 = args.gain_mode
    if args.gain_mode == "manual":
        sdr.rx_hardwaregain_chan0 = float(args.rx_gain)
    return sdr


def tx_worker(args: argparse.Namespace, stop: StopFlag) -> None:
    if resolve_audio_backend(args) == "soundcard":
        tx_worker_soundcard(args, stop)
        return

    sd = import_sounddevice()
    config = RadioConfig(
        audio_rate=args.audio_rate,
        sdr_rate=args.sdr_rate,
        fm_deviation_hz=args.deviation,
        tx_amplitude=args.tx_amplitude,
    )
    modulator = FmModulator(config)
    sdr = configure_tx_sdr(args)
    audio_queue: queue.Queue[np.ndarray] = queue.Queue(maxsize=args.queue_blocks)
    underruns = 0
    blocks_sent = 0

    def callback(indata: np.ndarray, _frames: int, _time: object, status: sd.CallbackFlags) -> None:
        if status:
            print(f"[audio-tx] {status}", file=sys.stderr)
        try:
            audio_queue.put_nowait(indata.copy())
        except queue.Full:
            try:
                audio_queue.get_nowait()
            except queue.Empty:
                pass
            audio_queue.put_nowait(indata.copy())

    print(
        f"TX: uri={args.uri}, lo={args.tx_freq/1e6:.3f} MHz, "
        f"sdr_rate={args.sdr_rate/1e6:.3f} MS/s, audio={args.audio_rate} Hz"
    )
    with sd.InputStream(
        samplerate=args.audio_rate,
        blocksize=args.audio_block,
        channels=1,
        dtype="float32",
        device=args.input_device,
        callback=callback,
    ):
        while not stop.event.is_set():
            try:
                audio = audio_queue.get(timeout=0.25)
            except queue.Empty:
                audio = np.zeros(args.audio_block, dtype=np.float32)
                underruns += 1

            iq = modulator.modulate(audio)
            sdr.tx(iq * (2**14))
            blocks_sent += 1
            if args.meter and blocks_sent % 25 == 0:
                print(f"\rTX audio rms={rms_level(audio):.3f} underruns={underruns}", end="")

    try:
        sdr.tx_destroy_buffer()
    except Exception:
        pass
    print("\nTX stopped")


def rx_worker(args: argparse.Namespace, stop: StopFlag) -> None:
    if resolve_audio_backend(args) == "soundcard":
        rx_worker_soundcard(args, stop)
        return

    sd = import_sounddevice()
    config = RadioConfig(
        audio_rate=args.audio_rate,
        sdr_rate=args.sdr_rate,
        fm_deviation_hz=args.deviation,
    )
    demodulator = FmDemodulator(config)
    sdr = configure_rx_sdr(args)
    audio_queue: queue.Queue[np.ndarray] = queue.Queue(maxsize=args.queue_blocks)

    def callback(outdata: np.ndarray, frames: int, _time: object, status: sd.CallbackFlags) -> None:
        if status:
            print(f"[audio-rx] {status}", file=sys.stderr)
        try:
            audio = audio_queue.get_nowait()
        except queue.Empty:
            audio = np.zeros(frames, dtype=np.float32)

        if len(audio) < frames:
            audio = np.pad(audio, (0, frames - len(audio)))
        outdata[:, 0] = audio[:frames] * args.volume

    print(
        f"RX: uri={args.uri}, lo={args.rx_freq/1e6:.3f} MHz, "
        f"sdr_rate={args.sdr_rate/1e6:.3f} MS/s, audio={args.audio_rate} Hz"
    )
    with sd.OutputStream(
        samplerate=args.audio_rate,
        blocksize=args.audio_block,
        channels=1,
        dtype="float32",
        device=args.output_device,
        callback=callback,
    ):
        while not stop.event.is_set():
            iq = sdr.rx()
            audio = demodulator.demodulate(iq)
            if args.squelch > 0 and rms_level(iq) < args.squelch:
                audio[:] = 0.0

            for start in range(0, len(audio), args.audio_block):
                chunk = audio[start : start + args.audio_block]
                try:
                    audio_queue.put_nowait(chunk)
                except queue.Full:
                    break

            if args.meter:
                print(f"\rRX iq rms={rms_level(iq):.3f} audio rms={rms_level(audio):.3f}", end="")

    print("\nRX stopped")


def tx_worker_soundcard(args: argparse.Namespace, stop: StopFlag) -> None:
    sc = import_soundcard()
    config = RadioConfig(
        audio_rate=args.audio_rate,
        sdr_rate=args.sdr_rate,
        fm_deviation_hz=args.deviation,
        tx_amplitude=args.tx_amplitude,
    )
    modulator = FmModulator(config)
    sdr = configure_tx_sdr(args)
    microphone = select_soundcard_microphone(sc, args.input_device)
    blocks_sent = 0

    print(
        f"TX(soundcard): uri={args.uri}, lo={args.tx_freq/1e6:.3f} MHz, "
        f"sdr_rate={args.sdr_rate/1e6:.3f} MS/s, audio={args.audio_rate} Hz"
    )
    print(f"Input: {microphone}")
    with microphone.recorder(
        samplerate=args.audio_rate,
        channels=1,
        blocksize=args.audio_block,
    ) as recorder:
        while not stop.event.is_set():
            audio = recorder.record(numframes=args.audio_block)
            iq = modulator.modulate(audio)
            sdr.tx(iq * (2**14))
            blocks_sent += 1
            if args.meter and blocks_sent % 25 == 0:
                print(f"\rTX audio rms={rms_level(audio):.3f}", end="")

    try:
        sdr.tx_destroy_buffer()
    except Exception:
        pass
    print("\nTX stopped")


def rx_worker_soundcard(args: argparse.Namespace, stop: StopFlag) -> None:
    sc = import_soundcard()
    config = RadioConfig(
        audio_rate=args.audio_rate,
        sdr_rate=args.sdr_rate,
        fm_deviation_hz=args.deviation,
    )
    demodulator = FmDemodulator(config)
    sdr = configure_rx_sdr(args)
    speaker = select_soundcard_speaker(sc, args.output_device)

    print(
        f"RX(soundcard): uri={args.uri}, lo={args.rx_freq/1e6:.3f} MHz, "
        f"sdr_rate={args.sdr_rate/1e6:.3f} MS/s, audio={args.audio_rate} Hz"
    )
    print(f"Output: {speaker}")
    with speaker.player(
        samplerate=args.audio_rate,
        channels=1,
        blocksize=args.audio_block,
    ) as player:
        while not stop.event.is_set():
            iq = sdr.rx()
            audio = demodulator.demodulate(iq)
            if args.squelch > 0 and rms_level(iq) < args.squelch:
                audio[:] = 0.0
            player.play((audio * args.volume).reshape(-1, 1))
            if args.meter:
                print(f"\rRX iq rms={rms_level(iq):.3f} audio rms={rms_level(audio):.3f}", end="")

    print("\nRX stopped")


def resolve_audio_backend(args: argparse.Namespace) -> str:
    if args.audio_backend != "auto":
        return args.audio_backend
    try:
        import_sounddevice()
        return "sounddevice"
    except RuntimeError:
        import_soundcard()
        return "soundcard"


def select_soundcard_microphone(sc, selector: str | None):
    if selector is None:
        return sc.default_microphone()
    microphones = sc.all_microphones(include_loopback=False)
    if selector.isdigit():
        return microphones[int(selector)]
    for microphone in microphones:
        if selector.lower() in str(microphone).lower():
            return microphone
    raise ValueError(f"Микрофон soundcard не найден: {selector}")


def select_soundcard_speaker(sc, selector: str | None):
    if selector is None:
        return sc.default_speaker()
    speakers = sc.all_speakers()
    if selector.isdigit():
        return speakers[int(selector)]
    for speaker in speakers:
        if selector.lower() in str(speaker).lower():
            return speaker
    raise ValueError(f"Динамик soundcard не найден: {selector}")


def list_audio_devices() -> None:
    print("soundcard devices:")
    try:
        sc = import_soundcard()
        print("Speakers:")
        for index, speaker in enumerate(sc.all_speakers()):
            print(f"  {index}: {speaker}")
        print("Microphones:")
        for index, microphone in enumerate(sc.all_microphones(include_loopback=False)):
            print(f"  {index}: {microphone}")
    except RuntimeError as exc:
        print(f"  unavailable: {exc}")

    print("\nsounddevice devices:")
    try:
        sd = import_sounddevice()
        print(sd.query_devices())
    except RuntimeError as exc:
        print(f"  unavailable: {exc}")


def parse_frequency(value: str) -> int:
    return int(float(value))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="ADALM-Pluto NBFM walkie-talkie")
    parser.add_argument("mode", choices=("tx", "rx", "trx", "devices"))
    parser.add_argument("--uri", default=DEFAULT_URI, help="Pluto URI, e.g. ip:192.168.3.1")
    parser.add_argument("--freq", type=parse_frequency, default=DEFAULT_FREQ)
    parser.add_argument("--tx-freq", type=parse_frequency)
    parser.add_argument("--rx-freq", type=parse_frequency)
    parser.add_argument("--sdr-rate", type=int, default=960_000)
    parser.add_argument("--audio-rate", type=int, default=48_000)
    parser.add_argument("--rf-bandwidth", type=int, default=DEFAULT_RF_BW)
    parser.add_argument("--deviation", type=float, default=5_000.0)
    parser.add_argument("--tx-gain", type=float, default=-20.0)
    parser.add_argument("--rx-gain", type=float, default=35.0)
    parser.add_argument("--gain-mode", choices=("slow_attack", "fast_attack", "manual"), default="slow_attack")
    parser.add_argument("--rx-buffer", type=int, default=DEFAULT_RX_BUFFER)
    parser.add_argument("--audio-block", type=int, default=DEFAULT_AUDIO_BLOCK)
    parser.add_argument("--queue-blocks", type=int, default=16)
    parser.add_argument("--input-device")
    parser.add_argument("--output-device")
    parser.add_argument("--audio-backend", choices=("auto", "soundcard", "sounddevice"), default="auto")
    parser.add_argument("--volume", type=float, default=0.6)
    parser.add_argument("--tx-amplitude", type=float, default=0.55)
    parser.add_argument("--squelch", type=float, default=0.0, help="Mute RX when IQ RMS is below this value")
    parser.add_argument("--meter", action="store_true", help="Print live level meters")
    return parser


def normalize_args(args: argparse.Namespace) -> argparse.Namespace:
    args.tx_freq = args.tx_freq if args.tx_freq is not None else args.freq
    args.rx_freq = args.rx_freq if args.rx_freq is not None else args.freq
    return args


def main(argv: list[str] | None = None) -> int:
    args = normalize_args(build_parser().parse_args(argv))
    if args.mode == "devices":
        list_audio_devices()
        return 0

    stop = StopFlag()
    stop.install_signal_handlers()

    if args.mode == "tx":
        tx_worker(args, stop)
    elif args.mode == "rx":
        rx_worker(args, stop)
    else:
        tx_args = copy.copy(args)
        rx_args = copy.copy(args)
        threads = [
            threading.Thread(target=tx_worker, args=(tx_args, stop), daemon=True),
            threading.Thread(target=rx_worker, args=(rx_args, stop), daemon=True),
        ]
        for thread in threads:
            thread.start()
        while not stop.event.is_set():
            time.sleep(0.2)
        for thread in threads:
            thread.join(timeout=2.0)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
