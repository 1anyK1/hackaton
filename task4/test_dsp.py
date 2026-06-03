import numpy as np
import unittest

from dsp import FmDemodulator, FmModulator, RadioConfig, rms_level


class DspTest(unittest.TestCase):
    def test_fm_round_trip_preserves_audio_tone(self):
        config = RadioConfig(
            audio_rate=48_000,
            sdr_rate=960_000,
            fm_deviation_hz=5_000,
            preemphasis_tau=0.0,
            deemphasis_tau=0.0,
            tx_voice_low_hz=0.0,
            tx_voice_high_hz=0.0,
            rx_voice_low_hz=0.0,
            rx_voice_high_hz=0.0,
            channel_filter_hz=0.0,
            mic_gate_threshold=0.0,
            mic_target_rms=0.35,
            mic_max_gain=1.0,
        )
        modulator = FmModulator(config)
        demodulator = FmDemodulator(config)

        t = np.arange(config.audio_rate, dtype=np.float32) / config.audio_rate
        audio = 0.35 * np.sin(2.0 * np.pi * 1_000.0 * t)

        iq = modulator.modulate(audio)
        recovered = demodulator.demodulate(iq)

        recovered = recovered[: len(audio) // 2]
        reference = audio[: len(recovered)]
        correlation = np.corrcoef(reference, recovered)[0, 1]

        self.assertGreater(correlation, 0.92)
        self.assertGreater(rms_level(recovered), 0.05)
        self.assertLess(rms_level(recovered), 0.6)

    def test_empty_blocks_are_supported(self):
        config = RadioConfig()
        self.assertEqual(len(FmModulator(config).modulate(np.empty(0, dtype=np.float32))), 0)
        self.assertEqual(
            len(FmDemodulator(config).demodulate(np.empty(0, dtype=np.complex64))),
            0,
        )


if __name__ == "__main__":
    unittest.main()
