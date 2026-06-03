#include "protocol.h"

#include <algorithm>
#include <cmath>
#include <stdexcept>

namespace {

std::size_t samples_for_pulses(int pulses, const ProtocolConfig& cfg) {
    const double samples = cfg.sample_rate * cfg.pulse_us * 1e-6 * pulses;
    return std::max<std::size_t>(1, static_cast<std::size_t>(std::llround(samples)));
}

void append_level(std::vector<float>& out, float level, int pulses, const ProtocolConfig& cfg) {
    const std::size_t count = samples_for_pulses(pulses, cfg);
    out.insert(out.end(), count, level);
}

void append_bit(std::vector<float>& out, int bit, const ProtocolConfig& cfg) {
    if (bit) {
        append_level(out, 1.0f, cfg.one_high_pulses, cfg);
        append_level(out, 0.0f, cfg.one_low_pulses, cfg);
    } else {
        append_level(out, 1.0f, cfg.zero_high_pulses, cfg);
        append_level(out, 0.0f, cfg.zero_low_pulses, cfg);
    }
}

} // namespace

Command command_from_name(const std::string& name) {
    if (name == "stop") return Command::Stop;
    if (name == "forward") return Command::Forward;
    if (name == "backward") return Command::Backward;
    if (name == "left") return Command::Left;
    if (name == "right") return Command::Right;
    throw std::runtime_error("unknown command: " + name);
}

std::string command_name(Command command) {
    switch (command) {
        case Command::Stop: return "stop";
        case Command::Forward: return "forward";
        case Command::Backward: return "backward";
        case Command::Left: return "left";
        case Command::Right: return "right";
    }
    return "unknown";
}

uint32_t command_code(Command command) {
    switch (command) {
        case Command::Stop: return 0x0;
        case Command::Forward: return 0x1;
        case Command::Backward: return 0x2;
        case Command::Left: return 0x4;
        case Command::Right: return 0x8;
    }
    return 0;
}

std::vector<int> frame_bits(Command command, const ProtocolConfig& cfg) {
    const uint32_t frame = ((cfg.address & 0xFFFFF) << 4) | (command_code(command) & 0xF);
    std::vector<int> bits;
    bits.reserve(24);
    for (int i = 23; i >= 0; --i) {
        bits.push_back((frame >> i) & 1U);
    }
    return bits;
}

std::vector<float> sync_template(const ProtocolConfig& cfg) {
    std::vector<float> out;
    append_level(out, 1.0f, cfg.sync_high_pulses, cfg);
    append_level(out, 0.0f, cfg.sync_low_pulses, cfg);
    return out;
}

std::vector<float> ook_envelope_for_bits(const std::vector<int>& bits, const ProtocolConfig& cfg) {
    std::vector<float> one_frame;
    append_level(one_frame, 1.0f, cfg.sync_high_pulses, cfg);
    append_level(one_frame, 0.0f, cfg.sync_low_pulses, cfg);
    for (int bit : bits) {
        append_bit(one_frame, bit ? 1 : 0, cfg);
    }

    std::vector<float> out;
    out.reserve(one_frame.size() * static_cast<std::size_t>(std::max(1, cfg.repeats)));
    for (int r = 0; r < std::max(1, cfg.repeats); ++r) {
        out.insert(out.end(), one_frame.begin(), one_frame.end());
    }
    return out;
}

std::vector<float> iq_from_envelope(const std::vector<float>& envelope, float amplitude) {
    std::vector<float> iq;
    iq.reserve(envelope.size() * 2);
    for (float v : envelope) {
        iq.push_back(v * amplitude);
        iq.push_back(0.0f);
    }
    return iq;
}

std::vector<float> generate_command_iq(Command command, const ProtocolConfig& cfg) {
    const auto bits = frame_bits(command, cfg);
    const auto envelope = ook_envelope_for_bits(bits, cfg);
    return iq_from_envelope(envelope, cfg.amplitude);
}

std::vector<int> decode_pwm_bits_after_sync(
    const std::vector<float>& envelope,
    std::size_t sync_index,
    std::size_t bit_count,
    const ProtocolConfig& cfg) {

    const std::size_t sync_len = sync_template(cfg).size();
    const std::size_t pulse = samples_for_pulses(1, cfg);
    std::size_t pos = sync_index + sync_len;
    std::vector<int> bits;
    bits.reserve(bit_count);

    for (std::size_t b = 0; b < bit_count && pos + 4 * pulse <= envelope.size(); ++b) {
        double sum = 0.0;
        for (std::size_t i = 0; i < 4 * pulse; ++i) {
            sum += envelope[pos + i];
        }
        const double average = sum / static_cast<double>(4 * pulse);
        bits.push_back(average > 0.5 ? 1 : 0);
        pos += 4 * pulse;
    }
    return bits;
}
