#include "controller.hpp"

#include <nlohmann/json.hpp>

#include <chrono>
#include <iostream>
#include <stdexcept>
#include <string>
#include <vector>

namespace {

using namespace std::chrono_literals;
using cabinet::Action;
using cabinet::ActionType;
using cabinet::ArduinoMessage;
using cabinet::Controller;
using cabinet::ControllerState;
using cabinet::Mode;

const auto start_time = Controller::TimePoint{};

void check(bool condition, const char *expression, int line)
{
    if (!condition) {
        throw std::runtime_error("check failed at line " + std::to_string(line) + ": " + expression);
    }
}

#define CHECK(expression) check((expression), #expression, __LINE__)

Controller make_controller()
{
    return Controller{{
        .controller_id = "rpi-01",
        .cabinet_devices = {{1, "/dev/rfcomm0"}, {2, "/dev/rfcomm1"}},
        .command_ack_timeout = 2s,
        .communication_timeout = 5s,
        .server_timeout = 10s,
        .startup_status_retry = 1s}};
}

ArduinoMessage event(int cabinet, Mode mode, std::string name)
{
    return ArduinoMessage{cabinet, mode, std::move(name), std::nullopt, std::nullopt};
}

ArduinoMessage status(int cabinet, std::string state)
{
    return ArduinoMessage{cabinet, Mode::None, "STATUS", std::nullopt, std::move(state)};
}

std::vector<Action> ready(Controller &controller)
{
    controller.start(start_time);
    auto startup = controller.take_actions();
    int status_requests = 0;
    for (const auto &action : startup) {
        if (action.type == ActionType::SendCabinet) {
            ++status_requests;
        }
    }
    CHECK(status_requests == 2);
    controller.on_arduino_message(1, status(1, "CLOSED"), start_time + 1ms);
    CHECK(controller.state() == ControllerState::Starting);
    controller.on_arduino_message(2, status(2, "CLOSED"), start_time + 2ms);
    CHECK(controller.state() == ControllerState::Idle);
    return controller.take_actions();
}

int count_actions(const std::vector<Action> &actions, ActionType type)
{
    int result = 0;
    for (const auto &action : actions) {
        result += action.type == type;
    }
    return result;
}

bool has_payload_value(
    const std::vector<Action> &actions,
    const std::string &field,
    const std::string &value)
{
    for (const auto &action : actions) {
        if (action.type != ActionType::Publish) {
            continue;
        }
        const auto json = nlohmann::json::parse(action.payload);
        if (json.contains(field) && json.at(field) == value) {
            return true;
        }
    }
    return false;
}

void scan(Controller &controller, std::string transaction = "tx-1")
{
    controller.on_card("04A12B34CD", transaction, start_time + 10ms);
    CHECK(controller.state() == ControllerState::WaitingServer);
    const auto actions = controller.take_actions();
    CHECK(count_actions(actions, ActionType::Publish) == 1);
    CHECK(has_payload_value(actions, "cardUid", "04A12B34CD"));
}

void open_step(Controller &controller, int cabinet, int step, Mode mode, std::string transaction = "tx-1")
{
    controller.on_server_command(
        cabinet::OpenCommand{cabinet, std::move(transaction), step, mode},
        start_time + std::chrono::milliseconds{20 + step});
}

void finish_step(Controller &controller, int cabinet, Mode mode, int offset)
{
    controller.on_arduino_message(cabinet, event(cabinet, mode, "COMMAND_ACCEPTED"), start_time + offset * 1ms);
    CHECK(controller.state() == ControllerState::WaitingOpened);
    controller.on_arduino_message(cabinet, event(cabinet, mode, "DOOR_OPENED"), start_time + (offset + 1) * 1ms);
    CHECK(controller.state() == ControllerState::WaitingClosed);
    CHECK(has_payload_value(controller.take_actions(), "status", "open"));
    controller.on_arduino_message(cabinet, event(cabinet, mode, "DOOR_CLOSED"), start_time + (offset + 2) * 1ms);
    CHECK(controller.state() == ControllerState::WaitingServer);
    CHECK(has_payload_value(controller.take_actions(), "status", "closed"));
}

void test_two_cabinet_transaction_and_complete()
{
    auto controller = make_controller();
    ready(controller);
    scan(controller);

    open_step(controller, 1, 1, Mode::Receive);
    auto actions = controller.take_actions();
    CHECK(count_actions(actions, ActionType::SendCabinet) == 1);
    CHECK(actions.back().line == "CABINET:1|COMMAND:RECEIVE");

    open_step(controller, 1, 1, Mode::Receive);
    CHECK(count_actions(controller.take_actions(), ActionType::SendCabinet) == 0);
    finish_step(controller, 1, Mode::Receive, 30);

    open_step(controller, 2, 2, Mode::Return);
    actions = controller.take_actions();
    CHECK(count_actions(actions, ActionType::SendCabinet) == 1);
    finish_step(controller, 2, Mode::Return, 50);

    controller.on_server_command(cabinet::CompleteCommand{"tx-1"}, start_time + 60ms);
    CHECK(controller.state() == ControllerState::Idle);
}

void test_cards_commands_and_steps_are_filtered()
{
    auto controller = make_controller();
    ready(controller);
    scan(controller);

    controller.on_card("SECOND", "tx-2", start_time + 11ms);
    CHECK(count_actions(controller.take_actions(), ActionType::Publish) == 0);

    open_step(controller, 1, 1, Mode::Receive, "wrong-tx");
    CHECK(controller.state() == ControllerState::WaitingServer);
    CHECK(count_actions(controller.take_actions(), ActionType::SendCabinet) == 0);

    open_step(controller, 1, 2, Mode::Receive);
    CHECK(controller.state() == ControllerState::WaitingServer);
    CHECK(count_actions(controller.take_actions(), ActionType::SendCabinet) == 0);

    open_step(controller, 1, 1, Mode::Receive);
    controller.take_actions();
    controller.on_arduino_message(1, event(1, Mode::Receive, "COMMAND_ACCEPTED"), start_time + 30ms);
    controller.on_arduino_message(1, event(1, Mode::Receive, "DOOR_OPENED"), start_time + 31ms);
    controller.take_actions();

    open_step(controller, 2, 2, Mode::Return);
    CHECK(controller.state() == ControllerState::WaitingClosed);
    CHECK(count_actions(controller.take_actions(), ActionType::SendCabinet) == 0);

    controller.on_server_command(cabinet::CompleteCommand{"tx-1"}, start_time + 32ms);
    CHECK(controller.state() == ControllerState::WaitingClosed);

    controller.on_arduino_message(1, event(1, Mode::Receive, "DOOR_CLOSED"), start_time + 33ms);
    controller.take_actions();
    open_step(controller, 1, 1, Mode::Receive);
    CHECK(count_actions(controller.take_actions(), ActionType::SendCabinet) == 0);
}

void test_open_too_long_stays_locked_until_close()
{
    auto controller = make_controller();
    ready(controller);
    scan(controller);
    open_step(controller, 1, 1, Mode::Return);
    controller.take_actions();
    controller.on_arduino_message(1, event(1, Mode::Return, "COMMAND_ACCEPTED"), start_time + 30ms);
    controller.on_arduino_message(1, event(1, Mode::Return, "DOOR_OPENED"), start_time + 31ms);
    controller.take_actions();

    controller.on_arduino_message(1, event(1, Mode::Return, "DOOR_OPEN_TOO_LONG"), start_time + 60s);
    CHECK(controller.state() == ControllerState::WaitingClosed);
    CHECK(has_payload_value(controller.take_actions(), "detail", "close_timeout"));
    controller.on_card("SECOND", "tx-2", start_time + 61s);
    CHECK(count_actions(controller.take_actions(), ActionType::Publish) == 0);

    controller.on_arduino_message(1, event(1, Mode::Return, "DOOR_CLOSED"), start_time + 62s);
    CHECK(controller.state() == ControllerState::WaitingServer);
    CHECK(has_payload_value(controller.take_actions(), "status", "closed"));
}

void test_transport_failure_and_timeouts_fault_safely()
{
    auto controller = make_controller();
    ready(controller);
    scan(controller);
    open_step(controller, 1, 1, Mode::Receive);
    controller.take_actions();
    controller.on_transport_error(1, "open failed", start_time + 30ms);
    CHECK(controller.state() == ControllerState::Fault);
    CHECK(has_payload_value(controller.take_actions(), "detail", "connection_failed"));

    auto timeout_controller = make_controller();
    ready(timeout_controller);
    scan(timeout_controller);
    open_step(timeout_controller, 1, 1, Mode::Receive);
    timeout_controller.take_actions();
    timeout_controller.on_tick(start_time + 3s);
    CHECK(timeout_controller.state() == ControllerState::Fault);
    CHECK(has_payload_value(timeout_controller.take_actions(), "detail", "communication_timeout"));
}

void test_startup_requires_every_closed_cabinet()
{
    auto open_controller = make_controller();
    open_controller.start(start_time);
    open_controller.take_actions();
    open_controller.on_arduino_message(1, status(1, "OPEN"), start_time + 1ms);
    CHECK(open_controller.state() == ControllerState::Fault);

    auto missing_controller = make_controller();
    missing_controller.start(start_time);
    missing_controller.take_actions();
    missing_controller.on_arduino_message(1, status(1, "CLOSED"), start_time + 1ms);
    CHECK(missing_controller.state() == ControllerState::Starting);
    missing_controller.take_actions();
    missing_controller.on_tick(start_time + 1s);
    const auto retry_actions = missing_controller.take_actions();
    CHECK(count_actions(retry_actions, ActionType::SendCabinet) == 1);
    for (const auto &action : retry_actions) {
        if (action.type == ActionType::SendCabinet) {
            CHECK(action.cabinet_number == 2);
        }
    }
    missing_controller.on_tick(start_time + 6s);
    CHECK(missing_controller.state() == ControllerState::Fault);
}

void test_rejections_open_timeout_and_complete_rules()
{
    auto unsafe_controller = make_controller();
    ready(unsafe_controller);
    scan(unsafe_controller);
    open_step(unsafe_controller, 1, 1, Mode::Receive);
    unsafe_controller.take_actions();
    unsafe_controller.on_arduino_message(
        1,
        ArduinoMessage{1, Mode::None, "COMMAND_REJECTED", "DOOR_ALREADY_OPEN", std::nullopt},
        start_time + 30ms);
    CHECK(unsafe_controller.state() == ControllerState::Fault);
    auto actions = unsafe_controller.take_actions();
    CHECK(has_payload_value(actions, "detail", "device_error"));
    CHECK(has_payload_value(actions, "reason", "DOOR_ALREADY_OPEN"));

    auto controller = make_controller();
    ready(controller);
    scan(controller);
    controller.on_server_command(cabinet::CompleteCommand{"wrong"}, start_time + 11ms);
    CHECK(controller.state() == ControllerState::WaitingServer);
    open_step(controller, 1, 1, Mode::Receive);
    controller.take_actions();
    controller.on_arduino_message(
        1,
        ArduinoMessage{1, Mode::None, "COMMAND_REJECTED", "UNSUPPORTED_OPERATION", std::nullopt},
        start_time + 30ms);
    CHECK(controller.state() == ControllerState::WaitingServer);
    actions = controller.take_actions();
    CHECK(has_payload_value(actions, "detail", "device_error"));
    CHECK(has_payload_value(actions, "reason", "UNSUPPORTED_OPERATION"));

    open_step(controller, 2, 2, Mode::Return);
    controller.take_actions();
    controller.on_arduino_message(2, event(2, Mode::Return, "COMMAND_ACCEPTED"), start_time + 40ms);
    controller.on_arduino_message(2, event(2, Mode::Return, "OPEN_TIMEOUT"), start_time + 41ms);
    CHECK(controller.state() == ControllerState::WaitingServer);
    CHECK(has_payload_value(controller.take_actions(), "detail", "open_timeout"));

    controller.on_server_command(cabinet::CompleteCommand{"tx-1"}, start_time + 50ms);
    CHECK(controller.state() == ControllerState::Idle);
}

void test_mapping_mismatch_faults()
{
    auto controller = make_controller();
    ready(controller);
    controller.on_arduino_message(1, status(2, "CLOSED"), start_time + 10ms);
    CHECK(controller.state() == ControllerState::Fault);
}

void test_mode_mismatch_and_idle_disconnect_fault()
{
    auto controller = make_controller();
    ready(controller);
    scan(controller);
    open_step(controller, 1, 1, Mode::Receive);
    controller.take_actions();
    controller.on_arduino_message(1, event(1, Mode::None, "COMMAND_ACCEPTED"), start_time + 30ms);
    CHECK(controller.state() == ControllerState::Fault);

    auto wrong_mode_controller = make_controller();
    ready(wrong_mode_controller);
    scan(wrong_mode_controller);
    open_step(wrong_mode_controller, 1, 1, Mode::Receive);
    wrong_mode_controller.take_actions();
    wrong_mode_controller.on_arduino_message(1, event(1, Mode::Return, "COMMAND_ACCEPTED"), start_time + 30ms);
    CHECK(wrong_mode_controller.state() == ControllerState::Fault);

    auto idle_controller = make_controller();
    ready(idle_controller);
    idle_controller.on_transport_error(2, "disconnected", start_time + 30ms);
    CHECK(idle_controller.state() == ControllerState::Fault);
}

void test_three_cabinet_steps_repeat_sequentially()
{
    Controller controller{{
        .controller_id = "rpi-01",
        .cabinet_devices = {
            {1, "/dev/rfcomm0"},
            {2, "/dev/rfcomm1"},
            {3, "/dev/rfcomm2"}},
        .command_ack_timeout = 2s,
        .communication_timeout = 5s,
        .server_timeout = 10s}};
    controller.start(start_time);
    auto actions = controller.take_actions();
    CHECK(count_actions(actions, ActionType::SendCabinet) == 3);
    controller.on_arduino_message(1, status(1, "CLOSED"), start_time + 1ms);
    controller.on_arduino_message(2, status(2, "CLOSED"), start_time + 2ms);
    controller.on_arduino_message(3, status(3, "CLOSED"), start_time + 3ms);
    CHECK(controller.state() == ControllerState::Idle);
    controller.take_actions();
    scan(controller);

    for (int step = 1; step <= 3; ++step) {
        const Mode mode = step == 2 ? Mode::Return : Mode::Receive;
        open_step(controller, step, step, mode);
        actions = controller.take_actions();
        CHECK(count_actions(actions, ActionType::SendCabinet) == 1);
        CHECK(actions.back().cabinet_number == step);
        finish_step(controller, step, mode, 40 + step * 10);
    }
    controller.on_server_command(cabinet::CompleteCommand{"tx-1"}, start_time + 100ms);
    CHECK(controller.state() == ControllerState::Idle);
}

} // namespace

int main()
{
    try {
        test_two_cabinet_transaction_and_complete();
        test_cards_commands_and_steps_are_filtered();
        test_open_too_long_stays_locked_until_close();
        test_transport_failure_and_timeouts_fault_safely();
        test_startup_requires_every_closed_cabinet();
        test_rejections_open_timeout_and_complete_rules();
        test_mapping_mismatch_faults();
        test_mode_mismatch_and_idle_disconnect_fault();
        test_three_cabinet_steps_repeat_sequentially();
        std::cout << "controller tests passed\n";
        return 0;
    } catch (const std::exception &error) {
        std::cerr << error.what() << '\n';
        return 1;
    }
}
