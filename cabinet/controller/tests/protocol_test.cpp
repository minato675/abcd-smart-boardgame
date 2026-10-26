#include "protocol.hpp"

#include <nlohmann/json.hpp>

#include <chrono>
#include <iostream>
#include <stdexcept>
#include <string>

namespace {

void check(bool condition, const char *expression, int line)
{
    if (!condition) {
        throw std::runtime_error("check failed at line " + std::to_string(line) + ": " + expression);
    }
}

#define CHECK(expression) check((expression), #expression, __LINE__)

template <typename Function>
void expect_failure(Function function)
{
    try {
        function();
    } catch (const std::exception &) {
        return;
    }
    throw std::runtime_error("expected operation to fail");
}

void test_arduino_protocol()
{
    const auto opened = cabinet::parse_arduino_message(
        "CABINET:3|MODE:RECEIVE|EVENT:DOOR_OPENED");
    CHECK(opened.cabinet_number == 3);
    CHECK(opened.mode == cabinet::Mode::Receive);
    CHECK(opened.event == "DOOR_OPENED");

    const auto rejected = cabinet::parse_arduino_message(
        "cabinet:2|mode:none|event:command_rejected|reason:busy");
    CHECK(rejected.reason == "BUSY");

    const auto status = cabinet::parse_arduino_message(
        "CABINET:1|MODE:NONE|EVENT:STATUS|STATE:CLOSED");
    CHECK(status.state == "CLOSED");
    CHECK(cabinet::make_status_command(1) == "CABINET:1|COMMAND:STATUS");
    CHECK(cabinet::make_arduino_command(3, cabinet::Mode::Return) ==
          "CABINET:3|COMMAND:RETURN");

    expect_failure([] {
        (void)cabinet::parse_arduino_message("CABINET:1|EVENT:DOOR_OPENED");
    });
    expect_failure([] {
        (void)cabinet::parse_arduino_message("CABINET:1|EVENT:STATUS");
    });
    expect_failure([] {
        (void)cabinet::parse_arduino_message("CABINET:1|EVENT:STATUS|STATE:UNKNOWN");
    });
    expect_failure([] {
        (void)cabinet::parse_arduino_message("CABINET:1|CABINET:2|EVENT:STATUS|STATE:CLOSED");
    });
}

void test_mqtt_protocol()
{
    const auto command = cabinet::parse_server_command(
        "rpi-01",
        "/cabinet/rpi-01/3/open",
        R"({"transactionId":"tx-1","step":2,"mode":"receive"})");
    const auto &open = std::get<cabinet::OpenCommand>(command);
    CHECK(open.cabinet_number == 3);
    CHECK(open.transaction_id == "tx-1");
    CHECK(open.step == 2);
    CHECK(open.mode == cabinet::Mode::Receive);

    const auto complete = cabinet::parse_server_command(
        "rpi-01",
        "/cabinet/rpi-01/complete",
        R"({"transactionId":"tx-1"})");
    CHECK(std::get<cabinet::CompleteCommand>(complete).transaction_id == "tx-1");

    expect_failure([] {
        (void)cabinet::parse_server_command(
            "rpi-01", "/cabinet/other/1/open",
            R"({"transactionId":"tx","step":1,"mode":"receive"})");
    });
    expect_failure([] {
        (void)cabinet::parse_server_command(
            "rpi-01", "/cabinet/rpi-01/1/open",
            R"({"transactionId":"tx","step":1,"mode":"invalid"})");
    });
    expect_failure([] {
        (void)cabinet::parse_server_command(
            "rpi-01", "/cabinet/rpi-01/1/open",
            R"({"transactionId":"tx","step":1,"mode":"return","extra":true})");
    });

    const auto card = nlohmann::json::parse(cabinet::card_payload("tx", "04A12B34CD"));
    CHECK(card.at("transactionId") == "tx");
    CHECK(card.at("cardUid") == "04A12B34CD");
    const auto status = nlohmann::json::parse(
        cabinet::status_payload("tx", 1, "closed", cabinet::Mode::Return));
    CHECK(status.at("status") == "closed");
    CHECK(status.at("mode") == "return");
    const auto error = nlohmann::json::parse(
        cabinet::error_payload("tx", 1, "device_error", "BUSY"));
    CHECK(error.at("detail") == "device_error");
    CHECK(error.at("reason") == "BUSY");
}

void test_transaction_id()
{
    using namespace std::chrono;
    const auto id = cabinet::make_transaction_id(
        "rpi-01", system_clock::from_time_t(1'786'000'000), 42);
    CHECK(id.starts_with("rpi-01-"));
    CHECK(id.ends_with("-000042"));
}

} // namespace

int main()
{
    try {
        test_arduino_protocol();
        test_mqtt_protocol();
        test_transaction_id();
        std::cout << "protocol tests passed\n";
        return 0;
    } catch (const std::exception &error) {
        std::cerr << error.what() << '\n';
        return 1;
    }
}
