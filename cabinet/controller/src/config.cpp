#include "config.hpp"

#include <algorithm>
#include <cctype>
#include <charconv>
#include <fstream>
#include <stdexcept>
#include <string_view>

namespace cabinet {
namespace {

std::string trim(std::string_view input)
{
    const auto is_space = [](unsigned char value) { return std::isspace(value) != 0; };
    auto first = input.begin();
    while (first != input.end() && is_space(static_cast<unsigned char>(*first))) {
        ++first;
    }
    auto last = input.end();
    while (last != first && is_space(static_cast<unsigned char>(*(last - 1)))) {
        --last;
    }
    return {first, last};
}

int parse_int(std::string_view text, std::string_view name)
{
    int result = 0;
    const auto [end, error] = std::from_chars(text.data(), text.data() + text.size(), result);
    if (error != std::errc{} || end != text.data() + text.size()) {
        throw std::runtime_error("invalid integer for " + std::string{name});
    }
    return result;
}

unsigned int parse_unsigned(std::string_view text, std::string_view name)
{
    unsigned int result = 0;
    const auto [end, error] = std::from_chars(text.data(), text.data() + text.size(), result);
    if (error != std::errc{} || end != text.data() + text.size()) {
        throw std::runtime_error("invalid unsigned integer for " + std::string{name});
    }
    return result;
}

struct CabinetKey {
    int number;
    std::string suffix;
};

CabinetKey parse_cabinet_key(std::string_view key)
{
    constexpr std::string_view prefix = "cabinet.";
    const auto remainder = key.substr(prefix.size());
    const auto dot = remainder.find('.');
    const auto number_text = remainder.substr(0, dot);
    const int number = parse_int(number_text, "cabinet number");
    if (number <= 0) {
        throw std::runtime_error("cabinet number must be positive");
    }
    return {number, dot == std::string_view::npos ? std::string{} : std::string{remainder.substr(dot)}};
}

} // namespace

Config Config::load(const std::string &path)
{
    std::ifstream input{path};
    if (!input) {
        throw std::runtime_error("cannot open config file: " + path);
    }

    Config config;
    std::string line;
    std::size_t line_number = 0;
    while (std::getline(input, line)) {
        ++line_number;
        const auto comment = line.find('#');
        if (comment != std::string::npos) {
            line.erase(comment);
        }
        const std::string cleaned = trim(line);
        if (cleaned.empty()) {
            continue;
        }
        const auto separator = cleaned.find('=');
        if (separator == std::string::npos) {
            throw std::runtime_error("missing '=' at config line " + std::to_string(line_number));
        }
        const std::string key = trim(std::string_view{cleaned}.substr(0, separator));
        const std::string value = trim(std::string_view{cleaned}.substr(separator + 1));
        if (key.empty()) {
            throw std::runtime_error("empty key at config line " + std::to_string(line_number));
        }

        try {
            if (key == "controller_id") {
                config.controller_id = value;
            } else if (key == "mqtt_host") {
                config.mqtt_host = value;
            } else if (key == "mqtt_port") {
                config.mqtt_port = parse_int(value, key);
            } else if (key == "mqtt_username") {
                config.mqtt_username = value;
            } else if (key == "mqtt_password") {
                config.mqtt_password = value;
            } else if (key == "mqtt_keepalive_seconds") {
                config.mqtt_keepalive_seconds = parse_int(value, key);
            } else if (key == "rfid_device") {
                config.rfid_device = value;
            } else if (key == "rfid_baud") {
                config.rfid_baud = parse_unsigned(value, key);
            } else if (key == "command_ack_timeout_ms") {
                config.command_ack_timeout = std::chrono::milliseconds{parse_int(value, key)};
            } else if (key == "communication_timeout_ms") {
                config.communication_timeout = std::chrono::milliseconds{parse_int(value, key)};
            } else if (key == "server_timeout_ms") {
                config.server_timeout = std::chrono::milliseconds{parse_int(value, key)};
            } else if (key.starts_with("cabinet.")) {
                const auto parsed = parse_cabinet_key(key);
                auto &cabinet = config.cabinets[parsed.number];
                if (parsed.suffix.empty()) {
                    cabinet.device = value;
                } else if (parsed.suffix == ".address") {
                    cabinet.bluetooth_address = value;
                } else if (parsed.suffix == ".channel") {
                    cabinet.rfcomm_channel = parse_int(value, key);
                } else {
                    throw std::runtime_error("unknown cabinet setting: " + key);
                }
            } else {
                throw std::runtime_error("unknown config key: " + key);
            }
        } catch (const std::exception &error) {
            throw std::runtime_error("config line " + std::to_string(line_number) + ": " + error.what());
        }
    }

    config.validate();
    return config;
}

void Config::validate() const
{
    if (controller_id.empty()) {
        throw std::runtime_error("controller_id is required");
    }
    if (controller_id.find('/') != std::string::npos) {
        throw std::runtime_error("controller_id cannot contain '/'");
    }
    if (mqtt_host.empty()) {
        throw std::runtime_error("mqtt_host is required");
    }
    if (mqtt_port <= 0 || mqtt_port > 65535) {
        throw std::runtime_error("mqtt_port must be between 1 and 65535");
    }
    if (mqtt_keepalive_seconds <= 0) {
        throw std::runtime_error("mqtt_keepalive_seconds must be positive");
    }
    if (mqtt_username.empty() != mqtt_password.empty()) {
        throw std::runtime_error("mqtt_username and mqtt_password must be set together");
    }
    if (rfid_device.empty()) {
        throw std::runtime_error("rfid_device is required");
    }
    if (rfid_baud == 0) {
        throw std::runtime_error("rfid_baud must be positive");
    }
    if (cabinets.empty()) {
        throw std::runtime_error("at least one cabinet mapping is required");
    }
    for (const auto &[number, cabinet] : cabinets) {
        if (cabinet.device.empty()) {
            throw std::runtime_error("cabinet." + std::to_string(number) + " device is required");
        }
        if (cabinet.rfcomm_channel <= 0 || cabinet.rfcomm_channel > 30) {
            throw std::runtime_error("cabinet." + std::to_string(number) + ".channel must be 1-30");
        }
    }
    if (command_ack_timeout.count() <= 0 || communication_timeout.count() <= 0 ||
        server_timeout.count() <= 0) {
        throw std::runtime_error("all timeouts must be positive");
    }
}

} // namespace cabinet
