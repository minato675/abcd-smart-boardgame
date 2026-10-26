#pragma once

#include "protocol.hpp"

#include <chrono>
#include <map>
#include <optional>
#include <set>
#include <string>
#include <vector>

namespace cabinet {

enum class ControllerState {
    Starting,
    Idle,
    WaitingServer,
    WaitingAccepted,
    WaitingOpened,
    WaitingClosed,
    Fault
};

[[nodiscard]] std::string to_string(ControllerState state);

enum class ActionType { Publish, SendCabinet, Log };
enum class LogLevel { Info, Warning, Error };

struct Action {
    ActionType type = ActionType::Log;
    int cabinet_number = 0;
    std::string topic;
    std::string payload;
    std::string line;
    LogLevel log_level = LogLevel::Info;
};

struct ControllerOptions {
    std::string controller_id;
    std::map<int, std::string> cabinet_devices;
    std::chrono::milliseconds command_ack_timeout{2000};
    std::chrono::milliseconds communication_timeout{5000};
    std::chrono::milliseconds server_timeout{10000};
    std::chrono::milliseconds startup_status_retry{1000};
};

class Controller {
public:
    using Clock = std::chrono::steady_clock;
    using TimePoint = Clock::time_point;

    explicit Controller(ControllerOptions options);

    void start(TimePoint now);
    void on_card(const std::string &card_uid, const std::string &transaction_id, TimePoint now);
    void on_server_command(const ServerCommand &command, TimePoint now);
    void on_arduino_message(int source_cabinet, const ArduinoMessage &message, TimePoint now);
    void on_transport_error(int cabinet_number, const std::string &message, TimePoint now);
    void on_mqtt_connection_changed(bool connected, TimePoint now);
    void on_mqtt_publish_error(const std::string &message, TimePoint now);
    void on_tick(TimePoint now);

    [[nodiscard]] ControllerState state() const noexcept;
    std::vector<Action> take_actions();

private:
    struct Transaction {
        std::string id;
        std::string card_uid;
        int last_executed_step = 0;
        int current_step = 0;
        int current_cabinet = 0;
        Mode current_mode = Mode::None;
        bool door_opened = false;
    };

    void handle_open(const OpenCommand &command, TimePoint now);
    void handle_complete(const CompleteCommand &command, TimePoint now);
    void set_state(ControllerState next, const std::string &reason);
    void enter_fault(const std::string &reason);
    void publish_status(const std::string &status);
    void publish_error(const std::string &detail, const std::optional<std::string> &reason = std::nullopt);
    void send_cabinet(int cabinet_number, const std::string &line);
    void log(LogLevel level, const std::string &message);
    [[nodiscard]] bool active_message_matches(int source_cabinet, const ArduinoMessage &message) const;
    void return_to_waiting_server(TimePoint now);

    ControllerOptions options_;
    ControllerState state_ = ControllerState::Starting;
    bool started_ = false;
    bool mqtt_connected_ = true;
    std::set<int> pending_startup_status_;
    std::optional<Transaction> transaction_;
    std::optional<TimePoint> deadline_;
    std::optional<TimePoint> startup_status_retry_at_;
    std::vector<Action> actions_;
};

} // namespace cabinet
