#pragma once

#include <cstdint>
#include <string>
#include <vector>

std::vector<float> read_iq_s8(const std::string& path);
void write_iq_s8(const std::string& path, const std::vector<float>& iq_interleaved);
void write_bits_text(const std::string& path, const std::vector<int>& bits);

