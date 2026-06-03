#include <algorithm>
#include <atomic>
#include <csignal>
#include <cmath>
#include <complex>
#include <cstddef>
#include <cstdint>
#include <cstdlib>
#include <cstring>
#include <dlfcn.h>
#include <iostream>
#include <stdexcept>
#include <string>
#include <thread>
#include <vector>

namespace {

std::atomic_bool g_stop{false};

void on_signal(int) {
    g_stop = true;
}

class SharedLibrary {
public:
    explicit SharedLibrary(const char* name) : handle_(dlopen(name, RTLD_NOW)) {
        if (!handle_) {
            throw std::runtime_error(std::string("cannot load ") + name + ": " + dlerror());
        }
    }

    ~SharedLibrary() {
        if (handle_) {
            dlclose(handle_);
        }
    }

    template <typename T>
    T load(const char* symbol) {
        dlerror();
        void* ptr = dlsym(handle_, symbol);
        const char* err = dlerror();
        if (err || !ptr) {
            throw std::runtime_error(std::string("cannot load symbol ") + symbol);
        }
        return reinterpret_cast<T>(ptr);
    }

private:
    void* handle_{};
};

struct PaStream;
using PaError = int;
constexpr unsigned long paFloat32 = 0x00000001UL;

struct PaDeviceInfo {
    int structVersion;
    const char* name;
    int hostApi;
    int maxInputChannels;
    int maxOutputChannels;
    double defaultLowInputLatency;
    double defaultLowOutputLatency;
    double defaultHighInputLatency;
    double defaultHighOutputLatency;
    double defaultSampleRate;
};

struct PortAudioApi {
    SharedLibrary lib{"libportaudio.so.2"};
    PaError (*Initialize)() = lib.load<PaError (*)()>("Pa_Initialize");
    PaError (*Terminate)() = lib.load<PaError (*)()>("Pa_Terminate");
    const char* (*GetErrorText)(PaError) = lib.load<const char* (*)(PaError)>("Pa_GetErrorText");
    int (*GetDeviceCount)() = lib.load<int (*)()>("Pa_GetDeviceCount");
    int (*GetDefaultInputDevice)() = lib.load<int (*)()>("Pa_GetDefaultInputDevice");
    int (*GetDefaultOutputDevice)() = lib.load<int (*)()>("Pa_GetDefaultOutputDevice");
    const PaDeviceInfo* (*GetDeviceInfo)(int) =
        lib.load<const PaDeviceInfo* (*)(int)>("Pa_GetDeviceInfo");
    PaError (*OpenDefaultStream)(PaStream**, int, int, unsigned long, double,
                                 unsigned long, void*, void*) =
        lib.load<PaError (*)(PaStream**, int, int, unsigned long, double,
                             unsigned long, void*, void*)>("Pa_OpenDefaultStream");
    PaError (*StartStream)(PaStream*) = lib.load<PaError (*)(PaStream*)>("Pa_StartStream");
    PaError (*StopStream)(PaStream*) = lib.load<PaError (*)(PaStream*)>("Pa_StopStream");
    PaError (*CloseStream)(PaStream*) = lib.load<PaError (*)(PaStream*)>("Pa_CloseStream");
    PaError (*ReadStream)(PaStream*, void*, unsigned long) =
        lib.load<PaError (*)(PaStream*, void*, unsigned long)>("Pa_ReadStream");
    PaError (*WriteStream)(PaStream*, const void*, unsigned long) =
        lib.load<PaError (*)(PaStream*, const void*, unsigned long)>("Pa_WriteStream");
};

void check_pa(PortAudioApi& pa, PaError err, const char* what) {
    if (err < 0) {
        throw std::runtime_error(std::string(what) + ": " + pa.GetErrorText(err));
    }
}

struct iio_context;
struct iio_device;
struct iio_channel;
struct iio_buffer;

struct IioApi {
    SharedLibrary lib{"libiio.so.0"};
    iio_context* (*create_context_from_uri)(const char*) =
        lib.load<iio_context* (*)(const char*)>("iio_create_context_from_uri");
    void (*context_destroy)(iio_context*) =
        lib.load<void (*)(iio_context*)>("iio_context_destroy");
    iio_device* (*context_find_device)(iio_context*, const char*) =
        lib.load<iio_device* (*)(iio_context*, const char*)>("iio_context_find_device");
    iio_channel* (*device_find_channel)(iio_device*, const char*, bool) =
        lib.load<iio_channel* (*)(iio_device*, const char*, bool)>("iio_device_find_channel");
    int (*channel_attr_write)(iio_channel*, const char*, const char*) =
        lib.load<int (*)(iio_channel*, const char*, const char*)>("iio_channel_attr_write");
    int (*channel_attr_write_longlong)(iio_channel*, const char*, long long) =
        lib.load<int (*)(iio_channel*, const char*, long long)>("iio_channel_attr_write_longlong");
    void (*channel_enable)(iio_channel*) =
        lib.load<void (*)(iio_channel*)>("iio_channel_enable");
    iio_buffer* (*device_create_buffer)(iio_device*, std::size_t, bool) =
        lib.load<iio_buffer* (*)(iio_device*, std::size_t, bool)>("iio_device_create_buffer");
    void (*buffer_destroy)(iio_buffer*) =
        lib.load<void (*)(iio_buffer*)>("iio_buffer_destroy");
    std::ptrdiff_t (*buffer_push)(iio_buffer*) =
        lib.load<std::ptrdiff_t (*)(iio_buffer*)>("iio_buffer_push");
    std::ptrdiff_t (*buffer_refill)(iio_buffer*) =
        lib.load<std::ptrdiff_t (*)(iio_buffer*)>("iio_buffer_refill");
    void* (*buffer_first)(iio_buffer*, iio_channel*) =
        lib.load<void* (*)(iio_buffer*, iio_channel*)>("iio_buffer_first");
    std::ptrdiff_t (*buffer_step)(iio_buffer*) =
        lib.load<std::ptrdiff_t (*)(iio_buffer*)>("iio_buffer_step");
    void* (*buffer_end)(iio_buffer*) =
        lib.load<void* (*)(iio_buffer*)>("iio_buffer_end");
};

void check_iio(int err, const char* what) {
    if (err < 0) {
        throw std::runtime_error(std::string(what) + " failed, libiio error " + std::to_string(err));
    }
}

float rms(const std::vector<float>& x) {
    if (x.empty()) {
        return 0.0f;
    }
    double sum = 0.0;
    for (float v : x) {
        sum += static_cast<double>(v) * v;
    }
    return static_cast<float>(std::sqrt(sum / x.size()));
}

float rms_sum(double sum, std::size_t count) {
    if (count == 0) {
        return 0.0f;
    }
    return static_cast<float>(std::sqrt(sum / static_cast<double>(count)));
}

float clamp1(float x) {
    return std::clamp(x, -1.0f, 1.0f);
}

class OnePoleLowpass {
public:
    OnePoleLowpass(double sample_rate, double cutoff_hz) {
        if (cutoff_hz <= 0.0) {
            alpha_ = 1.0;
        } else {
            const double rc = 1.0 / (2.0 * M_PI * cutoff_hz);
            const double dt = 1.0 / sample_rate;
            alpha_ = dt / (rc + dt);
        }
    }

    float process(float x) {
        y_ += static_cast<float>(alpha_) * (x - y_);
        return y_;
    }

    std::complex<float> process(std::complex<float> x) {
        yi_ += static_cast<float>(alpha_) * (x - yi_);
        return yi_;
    }

private:
    double alpha_{1.0};
    float y_{0.0f};
    std::complex<float> yi_{0.0f, 0.0f};
};

class CascadedLowpass {
public:
    CascadedLowpass(double sample_rate, double cutoff_hz, int stages)
        : stages_(static_cast<std::size_t>(std::max(1, stages)), OnePoleLowpass(sample_rate, cutoff_hz)) {}

    float process(float x) {
        for (auto& stage : stages_) {
            x = stage.process(x);
        }
        return x;
    }

    std::complex<float> process(std::complex<float> x) {
        for (auto& stage : stages_) {
            x = stage.process(x);
        }
        return x;
    }

private:
    std::vector<OnePoleLowpass> stages_;
};

class DcBlocker {
public:
    explicit DcBlocker(float r = 0.995f) : r_(r) {}

    float process(float x) {
        const float y = x - x1_ + r_ * y1_;
        x1_ = x;
        y1_ = y;
        return y;
    }

private:
    float r_;
    float x1_{0.0f};
    float y1_{0.0f};
};

class MicProcessor {
public:
    MicProcessor(double audio_rate, double audio_cutoff)
        : hp_(), lp_(audio_rate, audio_cutoff, 3) {}

    std::vector<float> process(const std::vector<float>& in, float gate, float target_rms) {
        std::vector<float> out;
        out.reserve(in.size());
        for (float v : in) {
            float y = hp_.process(clamp1(v));
            y = lp_.process(y);
            out.push_back(y);
        }

        const float level = rms(out);
        const bool open = level > gate;
        gate_gain_ = 0.93f * gate_gain_ + 0.07f * (open ? 1.0f : 0.0f);
        if (level > 1e-4f) {
            const float desired = std::clamp(target_rms / level, 0.2f, 8.0f);
            agc_gain_ = 0.97f * agc_gain_ + 0.03f * desired;
        }
        for (float& v : out) {
            v = std::tanh(v * gate_gain_ * agc_gain_ * 1.15f);
        }
        const float processed_level = rms(out);
        const float max_level = std::max(0.02f, target_rms * 1.15f);
        if (processed_level > max_level) {
            const float scale = max_level / processed_level;
            for (float& v : out) {
                v *= scale;
            }
        }
        return out;
    }

private:
    DcBlocker hp_{0.995f};
    CascadedLowpass lp_;
    float gate_gain_{0.0f};
    float agc_gain_{1.0f};
};

class FmModulator {
public:
    FmModulator(double audio_rate, double sdr_rate, double deviation)
        : audio_rate_(audio_rate), sdr_rate_(sdr_rate), deviation_(deviation) {}

    std::vector<std::complex<float>> modulate(const std::vector<float>& audio) {
        const int up = static_cast<int>(std::llround(sdr_rate_ / audio_rate_));
        std::vector<std::complex<float>> iq;
        iq.reserve(audio.size() * up);
        const double k = 2.0 * M_PI * deviation_ / sdr_rate_;
        for (float sample : audio) {
            sample = clamp1(sample);
            for (int i = 0; i < up; ++i) {
                phase_ += k * sample;
                if (phase_ > 2.0 * M_PI) {
                    phase_ -= 2.0 * M_PI;
                } else if (phase_ < -2.0 * M_PI) {
                    phase_ += 2.0 * M_PI;
                }
                iq.emplace_back(std::cos(phase_), std::sin(phase_));
            }
        }
        return iq;
    }

private:
    double audio_rate_;
    double sdr_rate_;
    double deviation_;
    double phase_{0.0};
};

class AmModulator {
public:
    AmModulator(double audio_rate, double sdr_rate)
        : audio_rate_(audio_rate), sdr_rate_(sdr_rate) {}

    std::vector<std::complex<float>> modulate(const std::vector<float>& audio,
                                              float carrier,
                                              float depth) const {
        const int up = static_cast<int>(std::llround(sdr_rate_ / audio_rate_));
        std::vector<std::complex<float>> iq;
        iq.reserve(audio.size() * up);
        for (float sample : audio) {
            const float amplitude = std::clamp(carrier + depth * clamp1(sample), -1.0f, 1.0f);
            for (int i = 0; i < up; ++i) {
                iq.emplace_back(amplitude, 0.0f);
            }
        }
        return iq;
    }

private:
    double audio_rate_;
    double sdr_rate_;
};

class FmDemodulator {
public:
    FmDemodulator(double audio_rate, double sdr_rate, double deviation,
                  double channel_filter, double audio_cutoff)
        : audio_rate_(audio_rate),
          sdr_rate_(sdr_rate),
          deviation_(deviation),
          channel_lpf_(sdr_rate, channel_filter, 4),
          voice_lpf_(audio_rate, audio_cutoff, 6),
          noise_lpf_(audio_rate, audio_cutoff * 1.25, 4) {}

    struct Result {
        std::vector<float> audio;
        float voice_rms{};
        float noise_rms{};
        float iq_rms{};
    };

    Result demodulate(const std::vector<std::complex<float>>& iq) {
        const int down = static_cast<int>(std::llround(sdr_rate_ / audio_rate_));
        Result result;
        result.audio.reserve(iq.size() / down + 1);

        float acc = 0.0f;
        int count = 0;
        double voice_sum = 0.0;
        double noise_sum = 0.0;
        double iq_sum = 0.0;
        std::size_t audio_count = 0;
        for (auto x : iq) {
            iq_sum += std::norm(x);
            x = channel_lpf_.process(x);
            const float mag = std::max(1e-6f, std::abs(x));
            x /= mag;
            const float dphi = std::arg(x * std::conj(last_));
            last_ = x;
            const float demod = dphi * static_cast<float>(sdr_rate_ / (2.0 * M_PI * deviation_));
            acc += demod;
            ++count;
            if (count == down) {
                float y = acc / static_cast<float>(down);
                y = dc_.process(y);
                const float voice = voice_lpf_.process(y);
                const float noise_band = y - noise_lpf_.process(y);
                const float shaped = std::tanh(voice * 1.15f);
                result.audio.push_back(clamp1(shaped));
                voice_sum += static_cast<double>(voice) * voice;
                noise_sum += static_cast<double>(noise_band) * noise_band;
                ++audio_count;
                acc = 0.0f;
                count = 0;
            }
        }
        result.voice_rms = rms_sum(voice_sum, audio_count);
        result.noise_rms = rms_sum(noise_sum, audio_count);
        result.iq_rms = rms_sum(iq_sum, iq.size());
        return result;
    }

private:
    double audio_rate_;
    double sdr_rate_;
    double deviation_;
    CascadedLowpass channel_lpf_;
    CascadedLowpass voice_lpf_;
    CascadedLowpass noise_lpf_;
    DcBlocker dc_{0.995f};
    std::complex<float> last_{1.0f, 0.0f};
};

class AmDemodulator {
public:
    AmDemodulator(double audio_rate, double sdr_rate, double channel_filter, double audio_cutoff)
        : audio_rate_(audio_rate),
          sdr_rate_(sdr_rate),
          channel_lpf_(sdr_rate, channel_filter, 4),
          carrier_lpf_(audio_rate, 20.0, 2),
          voice_lpf_(audio_rate, audio_cutoff, 6),
          noise_lpf_(audio_rate, audio_cutoff * 1.25, 4) {}

    FmDemodulator::Result demodulate(const std::vector<std::complex<float>>& iq) {
        const int down = static_cast<int>(std::llround(sdr_rate_ / audio_rate_));
        FmDemodulator::Result result;
        result.audio.reserve(iq.size() / down + 1);

        float acc = 0.0f;
        int count = 0;
        double voice_sum = 0.0;
        double noise_sum = 0.0;
        double iq_sum = 0.0;
        std::size_t audio_count = 0;

        for (auto x : iq) {
            iq_sum += std::norm(x);
            x = channel_lpf_.process(x);
            acc += std::abs(x);
            ++count;
            if (count == down) {
                const float envelope = acc / static_cast<float>(down);
                const float carrier = std::max(1e-4f, carrier_lpf_.process(envelope));
                float y = (envelope - carrier) / carrier;
                const float voice = voice_lpf_.process(y);
                const float noise_band = y - noise_lpf_.process(y);
                const float shaped = std::tanh(voice * 1.4f);
                result.audio.push_back(clamp1(shaped));
                voice_sum += static_cast<double>(voice) * voice;
                noise_sum += static_cast<double>(noise_band) * noise_band;
                ++audio_count;
                acc = 0.0f;
                count = 0;
            }
        }

        result.voice_rms = rms_sum(voice_sum, audio_count);
        result.noise_rms = rms_sum(noise_sum, audio_count);
        result.iq_rms = rms_sum(iq_sum, iq.size());
        return result;
    }

private:
    double audio_rate_;
    double sdr_rate_;
    CascadedLowpass channel_lpf_;
    CascadedLowpass carrier_lpf_;
    CascadedLowpass voice_lpf_;
    CascadedLowpass noise_lpf_;
};

struct Config {
    std::string mode = "rx";
    std::string modulation = "fm";
    std::string uri = "ip:192.168.3.1";
    long long freq = 915000000;
    long long sdr_rate = 2400000;
    long long rf_bw = 200000;
    int audio_rate = 48000;
    int audio_block = 1024;
    float tx_gain = -10.0f;
    float rx_gain = 12.0f;
    bool manual_gain = false;
    float volume = 0.22f;
    float deviation = 5000.0f;
    float tx_amp = 0.85f;
    float am_carrier = 0.65f;
    float am_depth = 0.22f;
    float mic_gate = 0.003f;
    float mic_target = 0.16f;
    float squelch = 0.035f;
    float noise_ratio = 1.15f;
    float channel_filter = 30000.0f;
    float tx_audio_cutoff = 2600.0f;
    float rx_audio_cutoff = 2200.0f;
    float tone = 0.0f;
    float tone_level = 0.35f;
    bool meter = false;
};

long long parse_freq(const std::string& s) {
    return static_cast<long long>(std::stod(s));
}

Config parse_args(int argc, char** argv) {
    Config c;
    if (argc > 1 && (std::string(argv[1]) == "--help" || std::string(argv[1]) == "-h")) {
        std::cout
            << "usage: pluto_walkie_cpp {tx|rx|devices} [options]\n"
            << "  --uri ip:192.168.3.1 --freq 915e6 --tx-gain -10 --rx-gain 12\n"
            << "  --mod fm|am --am-carrier 0.65 --am-depth 0.22\n"
            << "  --tx-tone 1000 --volume 0.22 --squelch 0.035 --noise-ratio 1.15\n"
            << "  --channel-filter 30000 --rx-audio-cutoff 2200 --tx-audio-cutoff 2600 --meter\n";
        std::exit(0);
    }
    if (argc > 1) {
        c.mode = argv[1];
    }
    for (int i = 2; i < argc; ++i) {
        std::string a = argv[i];
        auto need = [&](const char* name) {
            if (i + 1 >= argc) {
                throw std::runtime_error(std::string("missing value for ") + name);
            }
            return std::string(argv[++i]);
        };
        if (a == "--uri") c.uri = need("--uri");
        else if (a == "--mod") c.modulation = need("--mod");
        else if (a == "--freq") c.freq = parse_freq(need("--freq"));
        else if (a == "--sdr-rate") c.sdr_rate = parse_freq(need("--sdr-rate"));
        else if (a == "--rf-bandwidth") c.rf_bw = parse_freq(need("--rf-bandwidth"));
        else if (a == "--audio-rate") c.audio_rate = static_cast<int>(parse_freq(need("--audio-rate")));
        else if (a == "--audio-block") c.audio_block = static_cast<int>(parse_freq(need("--audio-block")));
        else if (a == "--tx-gain") c.tx_gain = std::stof(need("--tx-gain"));
        else if (a == "--rx-gain") c.rx_gain = std::stof(need("--rx-gain"));
        else if (a == "--gain-mode") c.manual_gain = (need("--gain-mode") == "manual");
        else if (a == "--volume") c.volume = std::stof(need("--volume"));
        else if (a == "--deviation") c.deviation = std::stof(need("--deviation"));
        else if (a == "--tx-amplitude") c.tx_amp = std::stof(need("--tx-amplitude"));
        else if (a == "--am-carrier") c.am_carrier = std::stof(need("--am-carrier"));
        else if (a == "--am-depth") c.am_depth = std::stof(need("--am-depth"));
        else if (a == "--mic-gate") c.mic_gate = std::stof(need("--mic-gate"));
        else if (a == "--mic-target-rms") c.mic_target = std::stof(need("--mic-target-rms"));
        else if (a == "--squelch") c.squelch = std::stof(need("--squelch"));
        else if (a == "--noise-ratio") c.noise_ratio = std::stof(need("--noise-ratio"));
        else if (a == "--channel-filter") c.channel_filter = std::stof(need("--channel-filter"));
        else if (a == "--tx-audio-cutoff") c.tx_audio_cutoff = std::stof(need("--tx-audio-cutoff"));
        else if (a == "--rx-audio-cutoff") c.rx_audio_cutoff = std::stof(need("--rx-audio-cutoff"));
        else if (a == "--tx-tone") c.tone = std::stof(need("--tx-tone"));
        else if (a == "--tx-tone-level") c.tone_level = std::stof(need("--tx-tone-level"));
        else if (a == "--meter") c.meter = true;
        else if (a == "--help" || a == "-h") {
            std::cout
                << "usage: pluto_walkie_cpp {tx|rx|devices} [options]\n"
                << "  --uri ip:192.168.3.1 --freq 915e6 --tx-gain -10 --rx-gain 12\n"
                << "  --mod fm|am --am-carrier 0.65 --am-depth 0.22\n"
                << "  --tx-tone 1000 --volume 0.22 --squelch 0.035 --noise-ratio 1.15\n"
                << "  --channel-filter 30000 --rx-audio-cutoff 2200 --tx-audio-cutoff 2600 --meter\n";
            std::exit(0);
        }
    }
    return c;
}

class Pluto {
public:
    Pluto(IioApi& api, const Config& c) : io_(api) {
        ctx_ = io_.create_context_from_uri(c.uri.c_str());
        if (!ctx_) {
            throw std::runtime_error("cannot connect to Pluto at " + c.uri);
        }
        phy_ = need_device("ad9361-phy");
    }

    ~Pluto() {
        if (tx_buf_) io_.buffer_destroy(tx_buf_);
        if (rx_buf_) io_.buffer_destroy(rx_buf_);
        if (ctx_) io_.context_destroy(ctx_);
    }

    void setup_tx(const Config& c, std::size_t samples) {
        tx_dev_ = need_device("cf-ad9361-dds-core-lpc");
        tx_i_ = need_channel(tx_dev_, "voltage0", true);
        tx_q_ = need_channel(tx_dev_, "voltage1", true);
        io_.channel_enable(tx_i_);
        io_.channel_enable(tx_q_);

        auto* phy_tx = need_channel(phy_, "voltage0", true);
        auto* lo = need_channel(phy_, "altvoltage1", true);
        check_iio(io_.channel_attr_write_longlong(phy_tx, "sampling_frequency", c.sdr_rate), "tx sampling_frequency");
        check_iio(io_.channel_attr_write_longlong(phy_tx, "rf_bandwidth", c.rf_bw), "tx rf_bandwidth");
        check_iio(io_.channel_attr_write_longlong(lo, "frequency", c.freq), "tx lo frequency");
        check_iio(io_.channel_attr_write(phy_tx, "hardwaregain", std::to_string(c.tx_gain).c_str()), "tx gain");

        tx_buf_ = io_.device_create_buffer(tx_dev_, samples, false);
        if (!tx_buf_) throw std::runtime_error("cannot create TX buffer");
    }

    void setup_rx(const Config& c, std::size_t samples) {
        rx_dev_ = need_device("cf-ad9361-lpc");
        rx_i_ = need_channel(rx_dev_, "voltage0", false);
        rx_q_ = need_channel(rx_dev_, "voltage1", false);
        io_.channel_enable(rx_i_);
        io_.channel_enable(rx_q_);

        auto* phy_rx = need_channel(phy_, "voltage0", false);
        auto* lo = need_channel(phy_, "altvoltage0", true);
        check_iio(io_.channel_attr_write_longlong(phy_rx, "sampling_frequency", c.sdr_rate), "rx sampling_frequency");
        check_iio(io_.channel_attr_write_longlong(phy_rx, "rf_bandwidth", c.rf_bw), "rx rf_bandwidth");
        check_iio(io_.channel_attr_write_longlong(lo, "frequency", c.freq), "rx lo frequency");
        if (c.manual_gain) {
            check_iio(io_.channel_attr_write(phy_rx, "gain_control_mode", "manual"), "rx gain mode");
            check_iio(io_.channel_attr_write(phy_rx, "hardwaregain", std::to_string(c.rx_gain).c_str()), "rx gain");
        } else {
            check_iio(io_.channel_attr_write(phy_rx, "gain_control_mode", "slow_attack"), "rx agc");
        }

        rx_buf_ = io_.device_create_buffer(rx_dev_, samples, false);
        if (!rx_buf_) throw std::runtime_error("cannot create RX buffer");
    }

    void tx(const std::vector<std::complex<float>>& iq, float amp) {
        auto* pi = static_cast<char*>(io_.buffer_first(tx_buf_, tx_i_));
        auto* pq = static_cast<char*>(io_.buffer_first(tx_buf_, tx_q_));
        const auto step = io_.buffer_step(tx_buf_);
        auto* end = static_cast<char*>(io_.buffer_end(tx_buf_));
        std::size_t idx = 0;
        for (; pi < end && idx < iq.size(); pi += step, pq += step, ++idx) {
            const int16_t i = static_cast<int16_t>(std::clamp(iq[idx].real() * amp, -1.0f, 1.0f) * 32760.0f);
            const int16_t q = static_cast<int16_t>(std::clamp(iq[idx].imag() * amp, -1.0f, 1.0f) * 32760.0f);
            std::memcpy(pi, &i, sizeof(i));
            std::memcpy(pq, &q, sizeof(q));
        }
        check_iio(static_cast<int>(io_.buffer_push(tx_buf_)), "tx buffer push");
    }

    std::vector<std::complex<float>> rx() {
        check_iio(static_cast<int>(io_.buffer_refill(rx_buf_)), "rx buffer refill");
        std::vector<std::complex<float>> iq;
        auto* pi = static_cast<char*>(io_.buffer_first(rx_buf_, rx_i_));
        auto* pq = static_cast<char*>(io_.buffer_first(rx_buf_, rx_q_));
        const auto step = io_.buffer_step(rx_buf_);
        auto* end = static_cast<char*>(io_.buffer_end(rx_buf_));
        for (; pi < end; pi += step, pq += step) {
            int16_t i = 0;
            int16_t q = 0;
            std::memcpy(&i, pi, sizeof(i));
            std::memcpy(&q, pq, sizeof(q));
            iq.emplace_back(static_cast<float>(i) / 2048.0f, static_cast<float>(q) / 2048.0f);
        }
        return iq;
    }

private:
    iio_device* need_device(const char* name) {
        auto* d = io_.context_find_device(ctx_, name);
        if (!d) throw std::runtime_error(std::string("missing IIO device ") + name);
        return d;
    }

    iio_channel* need_channel(iio_device* dev, const char* name, bool output) {
        auto* ch = io_.device_find_channel(dev, name, output);
        if (!ch) throw std::runtime_error(std::string("missing IIO channel ") + name);
        return ch;
    }

    IioApi& io_;
    iio_context* ctx_{};
    iio_device* phy_{};
    iio_device* tx_dev_{};
    iio_device* rx_dev_{};
    iio_channel* tx_i_{};
    iio_channel* tx_q_{};
    iio_channel* rx_i_{};
    iio_channel* rx_q_{};
    iio_buffer* tx_buf_{};
    iio_buffer* rx_buf_{};
};

void list_devices(PortAudioApi& pa) {
    check_pa(pa, pa.Initialize(), "Pa_Initialize");
    const int n = pa.GetDeviceCount();
    for (int i = 0; i < n; ++i) {
        const PaDeviceInfo* info = pa.GetDeviceInfo(i);
        if (!info) continue;
        std::cout << i << ": " << info->name
                  << " in=" << info->maxInputChannels
                  << " out=" << info->maxOutputChannels << "\n";
    }
    pa.Terminate();
}

void run_tx(const Config& c, IioApi& iio, PortAudioApi& pa) {
    const int ratio = static_cast<int>(std::llround(static_cast<double>(c.sdr_rate) / c.audio_rate));
    Pluto pluto(iio, c);
    pluto.setup_tx(c, static_cast<std::size_t>(c.audio_block * ratio));
    FmModulator fm(c.audio_rate, c.sdr_rate, c.deviation);
    AmModulator am(c.audio_rate, c.sdr_rate);
    MicProcessor mic(c.audio_rate, c.tx_audio_cutoff);

    check_pa(pa, pa.Initialize(), "Pa_Initialize");
    PaStream* stream = nullptr;
    if (c.tone <= 0.0f) {
        check_pa(pa, pa.OpenDefaultStream(&stream, 1, 0, paFloat32, c.audio_rate, c.audio_block, nullptr, nullptr),
                 "Pa_OpenDefaultStream input");
        check_pa(pa, pa.StartStream(stream), "Pa_StartStream input");
    }

    std::vector<float> audio(c.audio_block);
    double tone_phase = 0.0;
    const double tone_step = 2.0 * M_PI * c.tone / c.audio_rate;
    std::size_t blocks = 0;
    std::cout << "TX C++ uri=" << c.uri << " freq=" << c.freq / 1e6
              << " MHz mod=" << c.modulation
              << " gain=" << c.tx_gain << " dB\n";
    while (!g_stop) {
        if (c.tone > 0.0f) {
            for (int i = 0; i < c.audio_block; ++i) {
                audio[i] = c.tone_level * std::sin(tone_phase);
                tone_phase += tone_step;
                if (tone_phase > 2.0 * M_PI) tone_phase -= 2.0 * M_PI;
            }
        } else {
            const PaError err = pa.ReadStream(stream, audio.data(), c.audio_block);
            if (err < 0) std::fill(audio.begin(), audio.end(), 0.0f);
            audio = mic.process(audio, c.mic_gate, c.mic_target);
        }
        std::vector<std::complex<float>> iq;
        if (c.modulation == "am") {
            iq = am.modulate(audio, c.am_carrier, c.am_depth);
        } else {
            iq = fm.modulate(audio);
        }
        pluto.tx(iq, c.tx_amp);
        if (c.meter && (++blocks % 25 == 0)) {
            std::cout << "\rTX audio rms=" << rms(audio) << std::flush;
        }
    }

    if (stream) {
        pa.StopStream(stream);
        pa.CloseStream(stream);
    }
    pa.Terminate();
    std::cout << "\nTX stopped\n";
}

void run_rx(const Config& c, IioApi& iio, PortAudioApi& pa) {
    const int ratio = static_cast<int>(std::llround(static_cast<double>(c.sdr_rate) / c.audio_rate));
    Pluto pluto(iio, c);
    pluto.setup_rx(c, static_cast<std::size_t>(c.audio_block * ratio));
    FmDemodulator fm(c.audio_rate, c.sdr_rate, c.deviation, c.channel_filter, c.rx_audio_cutoff);
    AmDemodulator am(c.audio_rate, c.sdr_rate, c.channel_filter, c.rx_audio_cutoff);

    check_pa(pa, pa.Initialize(), "Pa_Initialize");
    PaStream* stream = nullptr;
    check_pa(pa, pa.OpenDefaultStream(&stream, 0, 1, paFloat32, c.audio_rate, c.audio_block, nullptr, nullptr),
             "Pa_OpenDefaultStream output");
    check_pa(pa, pa.StartStream(stream), "Pa_StartStream output");

    float gate_gain = 0.0f;
    std::size_t blocks = 0;
    std::cout << "RX C++ uri=" << c.uri << " freq=" << c.freq / 1e6
              << " MHz mod=" << c.modulation
              << " volume=" << c.volume << "\n";
    while (!g_stop) {
        auto iq = pluto.rx();
        auto demod = (c.modulation == "am") ? am.demodulate(iq) : fm.demodulate(iq);
        const float quality = demod.voice_rms / std::max(1e-4f, demod.noise_rms);
        const bool force_open = c.squelch <= 0.0f;
        const bool voice_present =
            force_open || (demod.voice_rms > c.squelch && quality > c.noise_ratio);
        const float target = voice_present ? 1.0f : 0.0f;
        gate_gain = 0.90f * gate_gain + 0.10f * target;
        auto& audio = demod.audio;
        for (float& v : audio) {
            v = clamp1(v * c.volume * gate_gain);
        }
        if (audio.size() < static_cast<std::size_t>(c.audio_block)) {
            audio.resize(c.audio_block, 0.0f);
        }
        check_pa(pa, pa.WriteStream(stream, audio.data(), c.audio_block), "Pa_WriteStream");
        if (c.meter && (++blocks % 10 == 0)) {
            std::cout << "\rRX iq_rms=" << demod.iq_rms
                      << " voice=" << demod.voice_rms
                      << " noise=" << demod.noise_rms
                      << " q=" << quality
                      << " gate=" << gate_gain
                      << " out=" << rms(audio) << std::flush;
        }
    }

    pa.StopStream(stream);
    pa.CloseStream(stream);
    pa.Terminate();
    std::cout << "\nRX stopped\n";
}

}  // namespace

int main(int argc, char** argv) {
    try {
        std::signal(SIGINT, on_signal);
        std::signal(SIGTERM, on_signal);
        Config c = parse_args(argc, argv);
        PortAudioApi pa;
        if (c.mode == "devices") {
            list_devices(pa);
            return 0;
        }
        IioApi iio;
        if (c.mode == "tx") {
            run_tx(c, iio, pa);
        } else if (c.mode == "rx") {
            run_rx(c, iio, pa);
        } else {
            throw std::runtime_error("mode must be tx, rx, or devices");
        }
    } catch (const std::exception& e) {
        std::cerr << "error: " << e.what() << "\n";
        return 1;
    }
    return 0;
}
