try:
    import adi
except (ImportError, AttributeError) as error:
    raise RuntimeError(
        "Cannot import Analog Devices pyadi-iio module. "
        "Run the chat from the project virtualenv, not with plain 'sudo python3'. "
        "Install Python dependencies with 'python3 -m pip install -r requirements.txt' "
        "and system IIO libraries with 'sudo apt install libiio0 libiio-utils'. "
        "If sudo is still required, run 'sudo ../venv/bin/python pluto_chat.py'."
    ) from error
import time

MHZ = int(1e6)


class MyRadio(adi.Pluto):

    def __init__(self, uri: str, user_name: str, tx_length: int = int(2**18),ongoing_transmission = False):
        super().__init__(f'ip:{uri}')
        self._user_name = user_name
        self._tx_length = tx_length
        self._ongoing_transmission = ongoing_transmission
        self.configure_chat_defaults()

    def configure_chat_defaults(self):
        self.tx_lo = int(900 * MHZ)
        self.rx_lo = int(900 * MHZ)
        self.sample_rate = int(10 * MHZ)
        self.tx_rf_bandwidth = int(10 * MHZ)
        self.rx_rf_bandwidth = int(10 * MHZ)
        self.tx_hardwaregain_chan0 = -10
        self.gain_control_mode_chan0 = 'slow_attack'
        self.rx_buffer_size = int(2**16)

    def __repr__(self):
        retstr = f"""Pluto(uri="{self.uri}") object for user "{self._user_name}" with following key properties:

rx_lo:                   {self.rx_lo / 1000000:<12} MHz, Carrier frequency of RX path
rx_hardwaregain_chan0    {self.rx_hardwaregain_chan0:<12} dB, Gain applied to RX path. Only applicable when gain_control_mode is set to 'manual'
rx_rf_bandwidth:         {self.rx_rf_bandwidth / 1000000:<12} MHz, Bandwidth of front-end analog filter of RX path
gain_control_mode_chan0: {self.gain_control_mode_chan0:<12} Receive path AGC Options: slow_attack, fast_attack, manual
rx_buffer_size:          {self.rx_buffer_size} Samples for receive

tx_lo:                   {self.tx_lo / 1000000:<12} MHz, Carrier frequency of TX path
tx_hardwaregain_chan0:   {self.tx_hardwaregain_chan0:<12} dB, Attenuation applied to TX path
tx_rf_bandwidth:         {self.tx_rf_bandwidth / 1000000:<12} MHz, Bandwidth of front-end analog filter of TX path
tx_cyclic_buffer:        {self.tx_cyclic_buffer:<12} Toggles cyclic buffer
tx_length                {self._tx_length} Samples for transmission

filter:                  {str(self.filter):<12} FIR filter file
sample_rate:             {self.sample_rate / 1000000:<12} MSPS, Sample rate RX and TX paths
loopback:                {self.loopback:<12} 0=Disabled, 1=Digital, 2=RF

"""
        return retstr

    @property
    def user_name(self):
        return self._user_name

    @user_name.setter
    def user_name(self, value):
        self._user_name = value

    @property
    def tx_length(self):
        return self._tx_length

    @tx_length.setter
    def tx_length(self, value):
        self._tx_length = value

    @property
    def ongoing_transmission(self):
        return self._ongoing_transmission
    
    @ongoing_transmission.setter
    def ongoing_transmission(self,value):
        self._ongoing_transmission = value

    def transmit_samples(self, samples, duration=2.0):
        if self.tx_cyclic_buffer and self._ongoing_transmission:
            self.kill_tranmission()
        self.tx_cyclic_buffer = True
        tx_samples = (samples) * (2**14)
        self.tx(tx_samples)
        self._ongoing_transmission = True
        time.sleep(duration)
        self.kill_tranmission()

    def kill_tranmission(self):
        self.tx_destroy_buffer()
        self._ongoing_transmission = False

    def kill_transmission(self):
        self.kill_tranmission()

    def receive_samples(self):
        for i in range(5):
            samples = self.rx()
        return samples / (2**11)
