#pragma once

#include <cstdint>
#include <string>
#include <vector>

enum class Command {
    Stop,
    Forward,
    Backward,
    Left,
    Right,
};

struct ProtocolConfig {
    double sample_rate = 2'000'000.0;
    double pulse_us = 350.0;
    int sync_high_pulses = 1;
    int sync_low_pulses = 31;
    int zero_high_pulses = 1;
    int zero_low_pulses = 3;
    int one_high_pulses = 3;
    int one_low_pulses = 1;
    int repeats = 12;
    float amplitude = 0.70f;
    uint32_t address = 0xA55A5;
};

Command command_from_name(const std::string& name);
std::string command_name(Command command);
uint32_t command_code(Command command);
std::vector<int> frame_bits(Command command, const ProtocolConfig& cfg);
std::vector<float> sync_template(const ProtocolConfig& cfg);
std::vector<float> ook_envelope_for_bits(const std::vector<int>& bits, const ProtocolConfig& cfg);
std::vector<float> iq_from_envelope(const std::vector<float>& envelope, float amplitude);
std::vector<float> generate_command_iq(Command command, const ProtocolConfig& cfg);
std::vector<int> decode_pwm_bits_after_sync(
    const std::vector<float>& envelope,
    std::size_t sync_index,
    std::size_t bit_count,
    const ProtocolConfig& cfg);

