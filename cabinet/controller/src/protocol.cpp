#include "protocol.hpp"

#include <nlohmann/json.hpp>

#include <algorithm>
#include <cctype>
#include <charconv>
#include <ctime>
#include <iomanip>
#include <map>
#include <sstream>
#include <stdexcept>
#include <string_view>
#include <vector>

namespace cabinet {
namespace {

using Json = nlohmann::json;

std::string uppercase(std::string value)
{
    std::transform(value.begin(), value.end(), value.begin(), [](unsigned char character) {
        return static_cast<char>(std::toupper(character));
    });
    return value;
}

std::string lowercase(std::string value)
{
    std::transform(value.begin(), value.end(), value.begin(), [](unsigned char character) {
        return static_cast<char>(std::tolower(character));
    });
    return value;
}

int parse_positive_int(std::string_view text, std::string_view name)
{
    int result = 0;
    const auto [end, error] = std::from_chars(text.data(), text.data() + text.size(), result);
    if (error != std::errc{} || end != text.data() + text.size() || result <= 0) {
        throw std::runtime_error(std::string{name} + " must be a positive integer");
    }
    return result;
}

std::vector<std::string> split_topic(const std::string &topic)
{
    if (topic.empty() || topic.front() != '/') {
        throw std::runtime_error("MQTT topic must start with '/'");
    }
    std::vector<std::string> segments;
    std::size_t start = 1;
    while (start <= topic.size()) {
        const auto end = topic.find('/', start);
        segments.push_back(topic.substr(start, end - start));
        if (end == std::string::npos) {
            break;
        }
        start = end + 1;
    }
    if (std::ranges::any_of(segments, [](const std::string &segment) { return segment.empty(); })) {
        throw std::runtime_error("MQTT topic contains an empty segment");
    }
    return segments;
}

Json parse_json_object(const std::string &payload)
{
    Json json;
    try {
        json = Json::parse(payload);
    } catch (const Json::exception &error) {
        throw std::runtime_error(std::string{"invalid JSON payload: "} + error.what());
    }
    if (!json.is_object()) {
        throw std::runtime_error("JSON payload must be an object");
    }
    return json;
}

std::string required_string(const Json &json, const char *field)
{
    const auto iterator = json.find(field);
    if (iterator == json.end() || !iterator->is_string() || iterator->get_ref<const std::string &>().empty()) {
        throw std::runtime_error(std::string{"missing or invalid JSON field: "} + field);
    }
    return iterator->get<std::string>();
}

int required_positive_int(const Json &json, const char *field)
{
    const auto iterator = json.find(field);
    if (iterator == json.end() || !iterator->is_number_integer()) {
        throw std::runtime_error(std::string{"missing or invalid JSON field: "} + field);
    }
    const int value = iterator->get<int>();
    if (value <= 0) {
        throw std::runtime_error(std::string{"JSON field must be positive: "} + field);
    }
    return value;
}

void require_fields(const Json &json, std::initializer_list<std::string_view> allowed)
{
    for (const auto &[key, value] : json.items()) {
        (void)value;
        if (std::ranges::find(allowed, key) == allowed.end()) {
            throw std::runtime_error("unexpected JSON field: " + key);
        }
    }
}

} // namespace

std::string to_string(Mode mode)
{
    switch (mode) {
    case Mode::Receive:
        return "receive";
    case Mode::Return:
        return "return";
    case Mode::None:
        return "none";
    }
    throw std::runtime_error("unknown mode");
}

std::optional<Mode> parse_mode(const std::string &value)
{
    const auto normalized = lowercase(value);
    if (normalized == "receive") {
        return Mode::Receive;
    }
    if (normalized == "return") {
        return Mode::Return;
    }
    if (normalized == "none") {
        return Mode::None;
    }
    return std::nullopt;
}

ArduinoMessage parse_arduino_message(const std::string &line)
{
    if (line.empty() || line.size() > 128) {
        throw std::runtime_error("Arduino message length must be 1-128 characters");
    }
    std::map<std::string, std::string> fields;
    std::size_t start = 0;
    while (start <= line.size()) {
        const auto end = line.find('|', start);
        const auto field = std::string_view{line}.substr(start, end - start);
        const auto separator = field.find(':');
        if (separator == std::string_view::npos || separator == 0 || separator + 1 >= field.size()) {
            throw std::runtime_error("malformed Arduino field");
        }
        const std::string key = uppercase(std::string{field.substr(0, separator)});
        const std::string value = uppercase(std::string{field.substr(separator + 1)});
        if (!fields.emplace(key, value).second) {
            throw std::runtime_error("duplicate Arduino field: " + key);
        }
        if (end == std::string::npos) {
            break;
        }
        start = end + 1;
    }

    const auto cabinet = fields.find("CABINET");
    const auto mode_field = fields.find("MODE");
    const auto event = fields.find("EVENT");
    if (cabinet == fields.end() || mode_field == fields.end() || event == fields.end()) {
        throw std::runtime_error("Arduino message requires CABINET, MODE, and EVENT");
    }

    ArduinoMessage result;
    result.cabinet_number = parse_positive_int(cabinet->second, "CABINET");
    result.event = event->second;
    {
        const auto parsed = parse_mode(mode_field->second);
        if (!parsed.has_value()) {
            throw std::runtime_error("invalid Arduino MODE");
        }
        result.mode = *parsed;
    }
    if (const auto reason = fields.find("REASON"); reason != fields.end()) {
        result.reason = reason->second;
    }
    if (const auto state = fields.find("STATE"); state != fields.end()) {
        if (state->second != "OPEN" && state->second != "CLOSED") {
            throw std::runtime_error("invalid Arduino STATE");
        }
        result.state = state->second;
    }
    for (const auto &[key, value] : fields) {
        (void)value;
        if (key != "CABINET" && key != "MODE" && key != "EVENT" && key != "REASON" && key != "STATE") {
            throw std::runtime_error("unknown Arduino field: " + key);
        }
    }
    if (result.event == "STATUS" && !result.state.has_value()) {
        throw std::runtime_error("STATUS event requires STATE");
    }
    return result;
}

std::string make_arduino_command(int cabinet_number, Mode mode)
{
    if (cabinet_number <= 0 || (mode != Mode::Receive && mode != Mode::Return)) {
        throw std::invalid_argument("invalid cabinet command");
    }
    return "CABINET:" + std::to_string(cabinet_number) + "|COMMAND:" + uppercase(to_string(mode));
}

std::string make_status_command(int cabinet_number)
{
    if (cabinet_number <= 0) {
        throw std::invalid_argument("cabinet number must be positive");
    }
    return "CABINET:" + std::to_string(cabinet_number) + "|COMMAND:STATUS";
}

ServerCommand parse_server_command(
    const std::string &controller_id,
    const std::string &topic,
    const std::string &payload)
{
    const auto segments = split_topic(topic);
    const auto json = parse_json_object(payload);
    if (segments.size() == 3 && segments[0] == "cabinet" && segments[1] == controller_id &&
        segments[2] == "complete") {
        require_fields(json, {"transactionId"});
        return CompleteCommand{required_string(json, "transactionId")};
    }
    if (segments.size() == 4 && segments[0] == "cabinet" && segments[1] == controller_id &&
        segments[3] == "open") {
        require_fields(json, {"transactionId", "step", "mode"});
        const auto mode_text = required_string(json, "mode");
        const auto mode = parse_mode(mode_text);
        if (!mode.has_value() || *mode == Mode::None) {
            throw std::runtime_error("mode must be receive or return");
        }
        return OpenCommand{
            parse_positive_int(segments[2], "cabinet number"),
            required_string(json, "transactionId"),
            required_positive_int(json, "step"),
            *mode};
    }
    throw std::runtime_error("topic does not match this controller's command topics");
}

std::string card_topic(const std::string &controller_id)
{
    return "/cabinet/" + controller_id + "/card";
}

std::string cabinet_status_topic(const std::string &controller_id, int cabinet_number)
{
    return "/cabinet/" + controller_id + "/" + std::to_string(cabinet_number) + "/status";
}

std::string card_payload(const std::string &transaction_id, const std::string &card_uid)
{
    return Json{{"transactionId", transaction_id}, {"cardUid", card_uid}}.dump();
}

std::string status_payload(
    const std::string &transaction_id,
    int step,
    const std::string &status,
    Mode mode)
{
    return Json{{"transactionId", transaction_id}, {"step", step}, {"status", status}, {"mode", to_string(mode)}}.dump();
}

std::string error_payload(
    const std::string &transaction_id,
    int step,
    const std::string &detail,
    const std::optional<std::string> &reason)
{
    Json json{{"transactionId", transaction_id}, {"step", step}, {"status", "error"}, {"detail", detail}};
    if (reason.has_value()) {
        json["reason"] = *reason;
    }
    return json.dump();
}

std::string make_transaction_id(
    const std::string &controller_id,
    std::chrono::system_clock::time_point time,
    std::uint32_t sequence)
{
    const std::time_t raw = std::chrono::system_clock::to_time_t(time);
    std::tm broken_down{};
    localtime_r(&raw, &broken_down);
    std::ostringstream output;
    output << controller_id << '-' << std::put_time(&broken_down, "%Y%m%d-%H%M%S") << '-'
           << std::setw(6) << std::setfill('0') << (sequence % 1'000'000U);
    return output.str();
}

} // namespace cabinet
