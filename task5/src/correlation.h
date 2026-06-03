#pragma once

#include <cstddef>
#include <vector>

struct CorrelationPeak {
    std::size_t index{};
    double score{};
};

std::vector<float> magnitude(const std::vector<float>& iq_interleaved);
std::vector<float> normalize_template(const std::vector<float>& pattern);
std::vector<CorrelationPeak> find_correlation_peaks(
    const std::vector<float>& samples,
    const std::vector<float>& pattern,
    double threshold,
    std::size_t min_distance);

