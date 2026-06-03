#include "correlation.h"
#include "iq_io.h"
#include "protocol.h"

#include <cstdlib>
#include <filesystem>
#include <iomanip>
#include <iostream>
#include <sstream>
#include <stdexcept>
#include <string>

namespace {

void print_usage() {
    std::cout
        << "Usage:\n"
        << "  rc_car_tool generate <command> <out.iq> [sample_rate]\n"
        << "  rc_car_tool analyze <capture.iq> [threshold]\n"
        << "  rc_car_tool tx <command> <frequency_hz> [sample_rate] [hackrf_transfer]\n"
        << "  rc_car_tool keyboard <frequency_hz> [sample_rate] [hackrf_transfer]\n\n"
        << "Commands: stop, forward, backward, left, right\n";
}

double parse_double(const std::string& value) {
    std::size_t consumed = 0;
    const double out = std::stod(value, &consumed);
    if (consumed != value.size()) {
        throw std::runtime_error("bad numeric value: " + value);
    }
    return out;
}

std::string bundled_hackrf_transfer() {
    const std::string from_repo = "task5/linux/2024.02.01/x86_64/bin/hackrf_transfer";
    const std::string from_task = "linux/2024.02.01/x86_64/bin/hackrf_transfer";
    if (std::filesystem::exists(from_repo)) {
        return from_repo;
    }
    if (std::filesystem::exists(from_task)) {
        return from_task;
    }
    return "hackrf_transfer";
}

void run_hackrf_transfer(const std::string& iq_path,
                         double frequency,
                         double sample_rate,
                         const std::string& hackrf_transfer_path) {
    std::ostringstream cmd;
    cmd << hackrf_transfer_path
        << " -t " << iq_path
        << " -f " << std::fixed << std::setprecision(0) << frequency
        << " -s " << std::fixed << std::setprecision(0) << sample_rate
        << " -x 0"
        << " -a 1";

    std::cout << "TX: " << cmd.str() << "\n";
    const int rc = std::system(cmd.str().c_str());
    if (rc != 0) {
        throw std::runtime_error("hackrf_transfer returned non-zero status");
    }
}

void generate_file(Command command, const std::string& out_path, const ProtocolConfig& cfg) {
    const auto parent = std::filesystem::path(out_path).parent_path();
    if (!parent.empty()) {
        std::filesystem::create_directories(parent);
    }
    const auto iq = generate_command_iq(command, cfg);
    write_iq_s8(out_path, iq);

    const auto bits = frame_bits(command, cfg);
    const std::string bits_path = out_path + ".bits.txt";
    write_bits_text(bits_path, bits);

    std::cout << "Generated " << command_name(command) << " frame: " << out_path << "\n";
    std::cout << "Bits saved to " << bits_path << "\n";
}

int main_impl(int argc, char** argv) {
    if (argc < 2) {
        print_usage();
        return 1;
    }

    ProtocolConfig cfg;
    const std::string mode = argv[1];

    if (mode == "generate") {
        if (argc < 4) {
            print_usage();
            return 1;
        }
        if (argc >= 5) cfg.sample_rate = parse_double(argv[4]);
        generate_file(command_from_name(argv[2]), argv[3], cfg);
        return 0;
    }

    if (mode == "analyze") {
        if (argc < 3) {
            print_usage();
            return 1;
        }
        const double threshold = argc >= 4 ? parse_double(argv[3]) : 0.78;
        const auto iq = read_iq_s8(argv[2]);
        const auto env = magnitude(iq);
        const auto pattern = sync_template(cfg);
        const auto peaks = find_correlation_peaks(env, pattern, threshold, pattern.size());

        std::cout << "Samples: " << env.size() << "\n";
        std::cout << "Sync peaks: " << peaks.size() << "\n";
        for (const auto& peak : peaks) {
            std::cout << "  index=" << peak.index << " score=" << std::fixed
                      << std::setprecision(3) << peak.score;
            const auto bits = decode_pwm_bits_after_sync(env, peak.index, 24, cfg);
            if (!bits.empty()) {
                std::cout << " bits=";
                for (int bit : bits) std::cout << bit;
            }
            std::cout << "\n";
        }
        return 0;
    }

    if (mode == "tx") {
        if (argc < 4) {
            print_usage();
            return 1;
        }
        const Command command = command_from_name(argv[2]);
        const double frequency = parse_double(argv[3]);
        if (argc >= 5) cfg.sample_rate = parse_double(argv[4]);
        const std::string hackrf_path = argc >= 6 ? argv[5] : bundled_hackrf_transfer();
        const std::string out_path = "generated/" + command_name(command) + ".iq";
        generate_file(command, out_path, cfg);
        run_hackrf_transfer(out_path, frequency, cfg.sample_rate, hackrf_path);
        return 0;
    }

    if (mode == "keyboard") {
        if (argc < 3) {
            print_usage();
            return 1;
        }
        const double frequency = parse_double(argv[2]);
        if (argc >= 4) cfg.sample_rate = parse_double(argv[3]);
        const std::string hackrf_path = argc >= 5 ? argv[4] : bundled_hackrf_transfer();

        std::cout << "Keys: w=forward, s=backward, a=left, d=right, space=stop, q=quit\n";
        for (;;) {
            const int ch = std::cin.get();
            if (ch == 'q') break;
            Command command = Command::Stop;
            bool known = true;
            if (ch == 'w') command = Command::Forward;
            else if (ch == 's') command = Command::Backward;
            else if (ch == 'a') command = Command::Left;
            else if (ch == 'd') command = Command::Right;
            else if (ch == ' ') command = Command::Stop;
            else known = false;

            if (known) {
                const std::string out_path = "generated/" + command_name(command) + ".iq";
                generate_file(command, out_path, cfg);
                run_hackrf_transfer(out_path, frequency, cfg.sample_rate, hackrf_path);
            }
        }
        return 0;
    }

    print_usage();
    return 1;
}

} // namespace

int main(int argc, char** argv) {
    try {
        return main_impl(argc, argv);
    } catch (const std::exception& ex) {
        std::cerr << "error: " << ex.what() << "\n";
        return 2;
    }
}
