#include "controller.hpp"

#include <stdexcept>
#include <utility>

namespace cabinet {

std::string to_string(ControllerState state)
{
    switch (state) {
    case ControllerState::Starting:
        return "STARTING";
    case ControllerState::Idle:
        return "IDLE";
    case ControllerState::WaitingServer:
        return "WAITING_SERVER";
    case ControllerState::WaitingAccepted:
        return "WAITING_ACCEPTED";
    case ControllerState::WaitingOpened:
        return "WAITING_OPENED";
    case ControllerState::WaitingClosed:
        return "WAITING_CLOSED";
    case ControllerState::Fault:
        return "FAULT";
    }
    return "UNKNOWN";
}

Controller::Controller(ControllerOptions options)
    : options_(std::move(options))
{
    if (options_.controller_id.empty() || options_.cabinet_devices.empty()) {
        throw std::invalid_argument("controller id and cabinet mappings are required");
    }
    if (options_.startup_status_retry.count() <= 0) {
        throw std::invalid_argument("startup STATUS retry interval must be positive");
    }
}

void Controller::start(TimePoint now)
{
    if (started_) {
        throw std::logic_error("controller already started");
    }
    started_ = true;
    pending_startup_status_.clear();
    for (const auto &[number, device] : options_.cabinet_devices) {
        (void)device;
        pending_startup_status_.insert(number);
        send_cabinet(number, make_status_command(number));
    }
    deadline_ = now + options_.communication_timeout;
    startup_status_retry_at_ = now + options_.startup_status_retry;
    log(LogLevel::Info, "checking startup state for " + std::to_string(pending_startup_status_.size()) + " cabinet(s)");
}

void Controller::on_card(
    const std::string &card_uid,
    const std::string &transaction_id,
    TimePoint now)
{
    if (state_ != ControllerState::Idle || !mqtt_connected_) {
        log(LogLevel::Warning, "ignored RFID card while controller is " + to_string(state_));
        return;
    }
    if (card_uid.empty() || transaction_id.empty()) {
        log(LogLevel::Error, "ignored empty RFID UID or transaction id");
        return;
    }
    transaction_ = Transaction{transaction_id, card_uid};
    set_state(ControllerState::WaitingServer, "RFID card accepted");
    deadline_ = now + options_.server_timeout;
    actions_.push_back(Action{
        .type = ActionType::Publish,
        .cabinet_number = 0,
        .topic = card_topic(options_.controller_id),
        .payload = card_payload(transaction_id, card_uid),
        .line = {},
        .log_level = LogLevel::Info});
}

void Controller::on_server_command(const ServerCommand &command, TimePoint now)
{
    if (!transaction_.has_value()) {
        log(LogLevel::Warning, "ignored server command without an active transaction");
        return;
    }
    if (const auto *open = std::get_if<OpenCommand>(&command)) {
        handle_open(*open, now);
    } else {
        handle_complete(std::get<CompleteCommand>(command), now);
    }
}

void Controller::handle_open(const OpenCommand &command, TimePoint now)
{
    if (state_ != ControllerState::WaitingServer) {
        log(LogLevel::Warning, "ignored open command while controller is " + to_string(state_));
        return;
    }
    auto &transaction = *transaction_;
    if (command.transaction_id != transaction.id) {
        log(LogLevel::Warning, "ignored open command for another transaction");
        return;
    }
    if (!options_.cabinet_devices.contains(command.cabinet_number)) {
        transaction.current_step = command.step;
        transaction.current_cabinet = command.cabinet_number;
        transaction.current_mode = command.mode;
        publish_error("connection_failed");
        enter_fault("server selected an unmapped cabinet");
        return;
    }
    if (command.step <= transaction.last_executed_step) {
        log(LogLevel::Warning, "ignored duplicate or past open step " + std::to_string(command.step));
        return;
    }
    if (command.step != transaction.last_executed_step + 1) {
        log(LogLevel::Error, "ignored out-of-order open step " + std::to_string(command.step));
        return;
    }
    if (command.mode != Mode::Receive && command.mode != Mode::Return) {
        log(LogLevel::Error, "ignored open command with invalid mode");
        return;
    }

    transaction.current_step = command.step;
    transaction.last_executed_step = command.step;
    transaction.current_cabinet = command.cabinet_number;
    transaction.current_mode = command.mode;
    transaction.door_opened = false;
    set_state(ControllerState::WaitingAccepted, "cabinet command sent");
    deadline_ = now + options_.command_ack_timeout;
    send_cabinet(command.cabinet_number, make_arduino_command(command.cabinet_number, command.mode));
}

void Controller::handle_complete(const CompleteCommand &command, TimePoint now)
{
    (void)now;
    if (state_ != ControllerState::WaitingServer) {
        log(LogLevel::Warning, "ignored complete command while controller is " + to_string(state_));
        return;
    }
    if (command.transaction_id != transaction_->id) {
        log(LogLevel::Warning, "ignored complete command for another transaction");
        return;
    }
    transaction_.reset();
    deadline_.reset();
    set_state(ControllerState::Idle, "server completed transaction");
}

bool Controller::active_message_matches(
    int source_cabinet,
    const ArduinoMessage &message) const
{
    if (!transaction_.has_value() || source_cabinet != transaction_->current_cabinet) {
        return false;
    }
    return message.cabinet_number == source_cabinet;
}

void Controller::on_arduino_message(
    int source_cabinet,
    const ArduinoMessage &message,
    TimePoint now)
{
    if (!options_.cabinet_devices.contains(source_cabinet)) {
        log(LogLevel::Error, "ignored event from unknown cabinet source");
        return;
    }
    if (message.cabinet_number != source_cabinet) {
        enter_fault("cabinet mapping mismatch: port " + std::to_string(source_cabinet) +
                    " reported cabinet " + std::to_string(message.cabinet_number));
        return;
    }

    if (state_ == ControllerState::Starting && message.event == "STATUS") {
        if (!message.state.has_value()) {
            enter_fault("startup STATUS response omitted state");
            return;
        }
        if (*message.state == "OPEN") {
            enter_fault("cabinet " + std::to_string(source_cabinet) + " is open at startup");
            return;
        }
        pending_startup_status_.erase(source_cabinet);
        if (pending_startup_status_.empty()) {
            deadline_.reset();
            startup_status_retry_at_.reset();
            set_state(ControllerState::Idle, "all cabinets reported closed");
        }
        return;
    }
    if (state_ == ControllerState::Starting && message.event == "STARTUP_DOOR_OPEN") {
        enter_fault("cabinet reported an open door at startup");
        return;
    }
    if (state_ == ControllerState::Fault || message.event == "SYSTEM_STARTED" ||
        message.event == "STATUS") {
        return;
    }
    if (!active_message_matches(source_cabinet, message)) {
        log(LogLevel::Warning, "ignored event that does not match the active cabinet command");
        return;
    }
    const bool mode_may_be_none =
        message.event == "COMMAND_REJECTED" || message.event == "INVALID_COMMAND";
    if ((!mode_may_be_none && message.mode != transaction_->current_mode) ||
        (mode_may_be_none && message.mode != Mode::None &&
         message.mode != transaction_->current_mode)) {
        enter_fault("Arduino mode does not match active command");
        return;
    }

    if (state_ == ControllerState::WaitingAccepted) {
        if (message.event == "COMMAND_ACCEPTED") {
            set_state(ControllerState::WaitingOpened, "Arduino accepted command");
            deadline_ = now + options_.communication_timeout;
            return;
        }
        if (message.event == "COMMAND_REJECTED") {
            publish_error("device_error", message.reason.value_or("COMMAND_REJECTED"));
            if (message.reason == "BUSY" || message.reason == "DOOR_ALREADY_OPEN" ||
                message.reason == "WRONG_CABINET") {
                enter_fault("Arduino rejection indicates an unsafe physical state");
            } else {
                return_to_waiting_server(now);
            }
            return;
        }
        if (message.event == "INVALID_COMMAND") {
            publish_error("device_error", "INVALID_COMMAND");
            return_to_waiting_server(now);
            return;
        }
    }

    if (state_ == ControllerState::WaitingOpened) {
        if (message.event == "DOOR_OPENED") {
            transaction_->door_opened = true;
            publish_status("open");
            deadline_.reset();
            set_state(ControllerState::WaitingClosed, "door opened");
            return;
        }
        if (message.event == "OPEN_TIMEOUT") {
            publish_error("open_timeout");
            return_to_waiting_server(now);
            return;
        }
        if (message.event == "COMMAND_REJECTED" || message.event == "INVALID_COMMAND") {
            const std::string reason = message.event == "INVALID_COMMAND"
                ? "INVALID_COMMAND"
                : message.reason.value_or("COMMAND_REJECTED");
            publish_error("device_error", reason);
            return_to_waiting_server(now);
            return;
        }
    }

    if (state_ == ControllerState::WaitingClosed) {
        if (message.event == "DOOR_OPEN_TOO_LONG") {
            publish_error("close_timeout");
            return;
        }
        if (message.event == "DOOR_CLOSED") {
            publish_status("closed");
            transaction_->door_opened = false;
            return_to_waiting_server(now);
            return;
        }
    }

    log(LogLevel::Warning, "ignored unexpected Arduino event " + message.event +
        " while controller is " + to_string(state_));
}

void Controller::on_transport_error(
    int cabinet_number,
    const std::string &message,
    TimePoint now)
{
    (void)now;
    log(LogLevel::Error, "cabinet " + std::to_string(cabinet_number) + " transport error: " + message);
    if (state_ == ControllerState::Starting) {
        enter_fault("cabinet connection unavailable during startup");
        return;
    }
    if (state_ == ControllerState::Idle) {
        enter_fault("cabinet connection failed while idle; restart to verify every door");
        return;
    }
    if (transaction_.has_value() && cabinet_number == transaction_->current_cabinet &&
        (state_ == ControllerState::WaitingAccepted || state_ == ControllerState::WaitingOpened ||
         state_ == ControllerState::WaitingClosed)) {
        publish_error("connection_failed");
        enter_fault("active cabinet connection failed; physical state is unknown");
    }
}

void Controller::on_mqtt_connection_changed(bool connected, TimePoint now)
{
    (void)now;
    if (connected == mqtt_connected_) {
        return;
    }
    mqtt_connected_ = connected;
    if (connected) {
        log(LogLevel::Info, "MQTT connection restored");
        return;
    }
    log(LogLevel::Error, "MQTT connection lost");
    if (transaction_.has_value()) {
        enter_fault("MQTT disconnected during an active transaction");
    }
}

void Controller::on_mqtt_publish_error(const std::string &message, TimePoint now)
{
    (void)now;
    log(LogLevel::Error, "MQTT publish failed: " + message);
    if (transaction_.has_value()) {
        enter_fault("could not publish active transaction event");
    }
}

void Controller::on_tick(TimePoint now)
{
    if (state_ == ControllerState::Starting) {
        if (deadline_.has_value() && now >= *deadline_) {
            enter_fault("one or more cabinets did not answer startup STATUS");
            return;
        }
        if (startup_status_retry_at_.has_value() && now >= *startup_status_retry_at_) {
            for (const int cabinet_number : pending_startup_status_) {
                send_cabinet(cabinet_number, make_status_command(cabinet_number));
            }
            startup_status_retry_at_ = now + options_.startup_status_retry;
            log(LogLevel::Info, "retrying startup STATUS for " +
                    std::to_string(pending_startup_status_.size()) + " cabinet(s)");
        }
        return;
    }
    if (!deadline_.has_value() || now < *deadline_) {
        return;
    }
    if (state_ == ControllerState::WaitingAccepted || state_ == ControllerState::WaitingOpened) {
        publish_error("communication_timeout");
        enter_fault("Arduino response timeout left physical state unknown");
        return;
    }
    if (state_ == ControllerState::WaitingServer) {
        log(LogLevel::Warning, "server command timeout; transaction remains active");
        deadline_ = now + options_.server_timeout;
    }
}

void Controller::return_to_waiting_server(TimePoint now)
{
    set_state(ControllerState::WaitingServer, "cabinet step ended");
    deadline_ = now + options_.server_timeout;
}

void Controller::set_state(ControllerState next, const std::string &reason)
{
    const auto previous = state_;
    state_ = next;
    log(LogLevel::Info, to_string(previous) + " -> " + to_string(next) + ": " + reason);
}

void Controller::enter_fault(const std::string &reason)
{
    if (state_ == ControllerState::Fault) {
        return;
    }
    deadline_.reset();
    startup_status_retry_at_.reset();
    set_state(ControllerState::Fault, reason);
}

void Controller::publish_status(const std::string &status)
{
    if (!transaction_.has_value()) {
        return;
    }
    actions_.push_back(Action{
        .type = ActionType::Publish,
        .cabinet_number = transaction_->current_cabinet,
        .topic = cabinet_status_topic(options_.controller_id, transaction_->current_cabinet),
        .payload = status_payload(transaction_->id, transaction_->current_step, status, transaction_->current_mode),
        .line = {},
        .log_level = LogLevel::Info});
}

void Controller::publish_error(
    const std::string &detail,
    const std::optional<std::string> &reason)
{
    if (!transaction_.has_value() || transaction_->current_cabinet <= 0) {
        return;
    }
    actions_.push_back(Action{
        .type = ActionType::Publish,
        .cabinet_number = transaction_->current_cabinet,
        .topic = cabinet_status_topic(options_.controller_id, transaction_->current_cabinet),
        .payload = error_payload(transaction_->id, transaction_->current_step, detail, reason),
        .line = {},
        .log_level = LogLevel::Info});
}

void Controller::send_cabinet(int cabinet_number, const std::string &line)
{
    actions_.push_back(Action{
        .type = ActionType::SendCabinet,
        .cabinet_number = cabinet_number,
        .topic = {},
        .payload = {},
        .line = line,
        .log_level = LogLevel::Info});
}

void Controller::log(LogLevel level, const std::string &message)
{
    actions_.push_back(Action{
        .type = ActionType::Log,
        .cabinet_number = 0,
        .topic = {},
        .payload = {},
        .line = message,
        .log_level = level});
}

ControllerState Controller::state() const noexcept
{
    return state_;
}

std::vector<Action> Controller::take_actions()
{
    std::vector<Action> result;
    result.swap(actions_);
    return result;
}

} // namespace cabinet
