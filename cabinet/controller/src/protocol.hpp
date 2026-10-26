#pragma once

#include <chrono>
#include <cstdint>
#include <optional>
#include <string>
#include <variant>

namespace cabinet {

enum class Mode { None, Receive, Return };

[[nodiscard]] std::string to_string(Mode mode);
[[nodiscard]] std::optional<Mode> parse_mode(const std::string &value);

struct ArduinoMessage {
    int cabinet_number = 0;
    Mode mode = Mode::None;
    std::string event;
    std::optional<std::string> reason;
    std::optional<std::string> state;
};

struct OpenCommand {
    int cabinet_number = 0;
    std::string transaction_id;
    int step = 0;
    Mode mode = Mode::None;
};

struct CompleteCommand {
    std::string transaction_id;
};

using ServerCommand = std::variant<OpenCommand, CompleteCommand>;

[[nodiscard]] ArduinoMessage parse_arduino_message(const std::string &line);
[[nodiscard]] std::string make_arduino_command(int cabinet_number, Mode mode);
[[nodiscard]] std::string make_status_command(int cabinet_number);

[[nodiscard]] ServerCommand parse_server_command(
    const std::string &controller_id,
    const std::string &topic,
    const std::string &payload);

[[nodiscard]] std::string card_topic(const std::string &controller_id);
[[nodiscard]] std::string cabinet_status_topic(const std::string &controller_id, int cabinet_number);
[[nodiscard]] std::string card_payload(const std::string &transaction_id, const std::string &card_uid);
[[nodiscard]] std::string status_payload(
    const std::string &transaction_id,
    int step,
    const std::string &status,
    Mode mode);
[[nodiscard]] std::string error_payload(
    const std::string &transaction_id,
    int step,
    const std::string &detail,
    const std::optional<std::string> &reason = std::nullopt);

[[nodiscard]] std::string make_transaction_id(
    const std::string &controller_id,
    std::chrono::system_clock::time_point time,
    std::uint32_t sequence);

} // namespace cabinet
