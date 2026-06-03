#include "iq_io.h"

#include <algorithm>
#include <cmath>
#include <fstream>
#include <stdexcept>

std::vector<float> read_iq_s8(const std::string& path) {
    std::ifstream in(path, std::ios::binary);
    if (!in) {
        throw std::runtime_error("cannot open input file: " + path);
    }

    std::vector<char> bytes((std::istreambuf_iterator<char>(in)),
                            std::istreambuf_iterator<char>());
    std::vector<float> out;
    out.reserve(bytes.size());
    for (char b : bytes) {
        const auto s = static_cast<int8_t>(b);
        out.push_back(static_cast<float>(s) / 127.0f);
    }
    return out;
}

void write_iq_s8(const std::string& path, const std::vector<float>& iq_interleaved) {
    std::ofstream out(path, std::ios::binary);
    if (!out) {
        throw std::runtime_error("cannot open output file: " + path);
    }

    for (float v : iq_interleaved) {
        v = std::clamp(v, -1.0f, 1.0f);
        const auto s = static_cast<int8_t>(std::lround(v * 100.0f));
        out.write(reinterpret_cast<const char*>(&s), sizeof(s));
    }
}

void write_bits_text(const std::string& path, const std::vector<int>& bits) {
    std::ofstream out(path);
    if (!out) {
        throw std::runtime_error("cannot open output file: " + path);
    }
    for (int bit : bits) {
        out << (bit ? '1' : '0');
    }
    out << '\n';
}
