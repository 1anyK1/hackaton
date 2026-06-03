#include "correlation.h"

#include <algorithm>
#include <cmath>
#include <numeric>

std::vector<float> magnitude(const std::vector<float>& iq_interleaved) {
    std::vector<float> out;
    out.reserve(iq_interleaved.size() / 2);
    for (std::size_t i = 0; i + 1 < iq_interleaved.size(); i += 2) {
        const float re = iq_interleaved[i];
        const float im = iq_interleaved[i + 1];
        out.push_back(std::sqrt(re * re + im * im));
    }
    return out;
}

std::vector<float> normalize_template(const std::vector<float>& pattern) {
    if (pattern.empty()) {
        return {};
    }

    const double mean = std::accumulate(pattern.begin(), pattern.end(), 0.0) /
                        static_cast<double>(pattern.size());

    std::vector<float> out(pattern.size());
    double energy = 0.0;
    for (std::size_t i = 0; i < pattern.size(); ++i) {
        out[i] = static_cast<float>(pattern[i] - mean);
        energy += static_cast<double>(out[i]) * out[i];
    }

    const double scale = std::sqrt(std::max(energy, 1e-12));
    for (float& v : out) {
        v = static_cast<float>(v / scale);
    }
    return out;
}

std::vector<CorrelationPeak> find_correlation_peaks(
    const std::vector<float>& samples,
    const std::vector<float>& pattern,
    double threshold,
    std::size_t min_distance) {

    std::vector<CorrelationPeak> peaks;
    if (samples.size() < pattern.size() || pattern.empty()) {
        return peaks;
    }

    const std::vector<float> tpl = normalize_template(pattern);
    const std::size_t n = pattern.size();

    for (std::size_t pos = 0; pos + n <= samples.size(); ++pos) {
        double mean = 0.0;
        for (std::size_t i = 0; i < n; ++i) {
            mean += samples[pos + i];
        }
        mean /= static_cast<double>(n);

        double energy = 0.0;
        double dot = 0.0;
        for (std::size_t i = 0; i < n; ++i) {
            const double centered = samples[pos + i] - mean;
            dot += centered * tpl[i];
            energy += centered * centered;
        }

        const double score = dot / std::sqrt(std::max(energy, 1e-12));
        if (score >= threshold) {
            if (!peaks.empty() && pos - peaks.back().index < min_distance) {
                if (score > peaks.back().score) {
                    peaks.back() = {pos, score};
                }
            } else {
                peaks.push_back({pos, score});
            }
        }
    }

    return peaks;
}
