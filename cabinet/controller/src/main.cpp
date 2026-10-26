#include "config.hpp"
#include "controller.hpp"
#include "mqtt_client.hpp"
#include "protocol.hpp"
#include "serial_line.hpp"

#include <cr100emur.hpp>

#include <atomic>
#include <chrono>
#include <cerrno>
#include <csignal>
#include <cstdint>
#include <exception>
#include <iostream>
#include <map>
#include <memory>
#include <poll.h>
#include <set>
#include <stdexcept>
#include <string>
#include <thread>
#include <vector>

namespace {

using cabinet::Controller;

volatile std::sig_atomic_t stop_requested = 0;

std::uint32_t initial_transaction_sequence()
{
    const auto micros = std::chrono::duration_cast<std::chrono::microseconds>(
        std::chrono::system_clock::now().time_since_epoch());
    return static_cast<std::uint32_t>(micros.count() % 1'000'000);
}

std::atomic<std::uint32_t> transaction_sequence{initial_transaction_sequence()};

void handle_signal(int signal)
{
    (void)signal;
    stop_requested = 1;
}

cabinet::LogLevel action_level(const cabinet::Action &action)
{
    return action.log_level;
}

const char *log_prefix(cabinet::LogLevel level)
{
    switch (level) {
    case cabinet::LogLevel::Info:
        return "INFO";
    case cabinet::LogLevel::Warning:
        return "WARN";
    case cabinet::LogLevel::Error:
        return "ERROR";
    }
    return "INFO";
}

void log(cabinet::LogLevel level, const std::string &message)
{
    std::clog << log_prefix(level) << ": " << message << '\n';
}

using PortMap = std::map<int, std::unique_ptr<cabinet::SerialLine>>;

void dispatch_actions(
    Controller &controller,
    cabinet::MqttClient &mqtt,
    PortMap &ports)
{
    for (;;) {
        controller.on_mqtt_connection_changed(mqtt.connected(), Controller::Clock::now());
        auto actions = controller.take_actions();
        if (actions.empty()) {
            return;
        }
        for (const auto &action : actions) {
            if (action.type == cabinet::ActionType::Log) {
                log(action_level(action), action.line);
                continue;
            }
            if (action.type == cabinet::ActionType::Publish) {
                try {
                    mqtt.publish(action.topic, action.payload);
                } catch (const std::exception &error) {
                    controller.on_mqtt_publish_error(error.what(), Controller::Clock::now());
                }
                continue;
            }
            if (controller.state() == cabinet::ControllerState::Fault) {
                log(cabinet::LogLevel::Warning, "skipped cabinet command because controller is in FAULT");
                continue;
            }
            const auto port = ports.find(action.cabinet_number);
            if (port == ports.end() || !port->second || !port->second->is_open()) {
                controller.on_transport_error(
                    action.cabinet_number,
                    "device is not open",
                    Controller::Clock::now());
                continue;
            }
            try {
                port->second->write_line(action.line);
            } catch (const std::exception &error) {
                port->second->close();
                controller.on_transport_error(
                    action.cabinet_number,
                    error.what(),
                    Controller::Clock::now());
            }
        }
    }
}

struct Arguments {
    std::string config_path = "/etc/rpi-cabinet-controller/controller.conf";
    bool check_config = false;
};

Arguments parse_arguments(int argc, char **argv)
{
    Arguments arguments;
    for (int index = 1; index < argc; ++index) {
        const std::string argument = argv[index];
        if (argument == "--config" && index + 1 < argc) {
            arguments.config_path = argv[++index];
        } else if (argument == "--check-config") {
            arguments.check_config = true;
        } else if (argument == "--help") {
            std::cout << "Usage: rpi-cabinet-controller [--config PATH] [--check-config]\n";
            std::exit(0);
        } else {
            throw std::runtime_error("unknown or incomplete argument: " + argument);
        }
    }
    return arguments;
}

int run(const Arguments &arguments)
{
    const auto config = cabinet::Config::load(arguments.config_path);
    if (arguments.check_config) {
        std::cout << "Configuration is valid for controller " << config.controller_id << '\n';
        return 0;
    }

    cabinet::MqttClient mqtt{{
        .host = config.mqtt_host,
        .port = config.mqtt_port,
        .username = config.mqtt_username,
        .password = config.mqtt_password,
        .client_id = config.controller_id,
        .open_subscription = "/cabinet/" + config.controller_id + "/+/open",
        .complete_subscription = "/cabinet/" + config.controller_id + "/complete",
        .keepalive_seconds = config.mqtt_keepalive_seconds}};
    mqtt.start();
    if (!mqtt.wait_until_connected(config.communication_timeout)) {
        throw std::runtime_error("MQTT connection timed out during startup");
    }
    log(cabinet::LogLevel::Info, "connected to MQTT broker");

    cr100emur::Reader rfid{config.rfid_device, config.rfid_baud};
    log(cabinet::LogLevel::Info, "opened RFID reader " + rfid.device_path());

    PortMap ports;
    std::map<int, std::string> cabinet_devices;
    for (const auto &[number, cabinet_config] : config.cabinets) {
        cabinet_devices.emplace(number, cabinet_config.device);
        try {
            ports.emplace(
                number,
                std::make_unique<cabinet::SerialLine>(cabinet_config.device, 9600, 128));
            log(cabinet::LogLevel::Info, "opened cabinet " + std::to_string(number) + " at " + cabinet_config.device);
        } catch (const std::exception &error) {
            log(cabinet::LogLevel::Error, "could not open cabinet " + std::to_string(number) + ": " + error.what());
            ports.emplace(number, nullptr);
        }
    }

    Controller controller{{
        .controller_id = config.controller_id,
        .cabinet_devices = std::move(cabinet_devices),
        .command_ack_timeout = config.command_ack_timeout,
        .communication_timeout = config.communication_timeout,
        .server_timeout = config.server_timeout}};
    controller.start(Controller::Clock::now());
    dispatch_actions(controller, mqtt, ports);

    bool last_mqtt_state = mqtt.connected();
    while (stop_requested == 0) {
        struct PollTarget {
            enum class Type { Rfid, Cabinet } type;
            int cabinet_number = 0;
        };
        std::vector<pollfd> descriptors;
        std::vector<PollTarget> targets;
        descriptors.push_back({rfid.file_descriptor(), POLLIN, 0});
        targets.push_back({PollTarget::Type::Rfid, 0});
        for (const auto &[number, port] : ports) {
            if (port && port->is_open()) {
                descriptors.push_back({port->file_descriptor(), POLLIN, 0});
                targets.push_back({PollTarget::Type::Cabinet, number});
            }
        }

        const int poll_result = ::poll(descriptors.data(), descriptors.size(), 100);
        if (poll_result < 0 && errno != EINTR) {
            throw std::runtime_error("poll failed");
        }
        if (poll_result > 0) {
            for (std::size_t index = 0; index < descriptors.size(); ++index) {
                const short events = descriptors[index].revents;
                if (events == 0) {
                    continue;
                }
                if ((events & (POLLERR | POLLHUP | POLLNVAL)) != 0) {
                    if (targets[index].type == PollTarget::Type::Rfid) {
                        throw std::runtime_error("RFID reader disconnected");
                    }
                    auto &port = ports.at(targets[index].cabinet_number);
                    port->close();
                    controller.on_transport_error(
                        targets[index].cabinet_number,
                        "device disconnected",
                        Controller::Clock::now());
                    continue;
                }
                if ((events & POLLIN) == 0) {
                    continue;
                }
                if (targets[index].type == PollTarget::Type::Rfid) {
                    rfid.dispatch([&](const cr100emur::Card &card) {
                        const auto transaction_id = cabinet::make_transaction_id(
                            config.controller_id,
                            std::chrono::system_clock::now(),
                            transaction_sequence.fetch_add(1));
                        controller.on_card(card.hex, transaction_id, Controller::Clock::now());
                    });
                    continue;
                }
                const int cabinet_number = targets[index].cabinet_number;
                try {
                    for (const auto &line : ports.at(cabinet_number)->read_available()) {
                        try {
                            controller.on_arduino_message(
                                cabinet_number,
                                cabinet::parse_arduino_message(line),
                                Controller::Clock::now());
                        } catch (const std::exception &error) {
                            log(cabinet::LogLevel::Warning, "invalid Arduino message: " + std::string{error.what()});
                        }
                    }
                } catch (const cabinet::LineTooLongError &error) {
                    log(cabinet::LogLevel::Warning, error.what());
                } catch (const std::exception &error) {
                    ports.at(cabinet_number)->close();
                    controller.on_transport_error(cabinet_number, error.what(), Controller::Clock::now());
                }
            }
        }

        for (const auto &message : mqtt.drain_messages()) {
            if (message.retained) {
                log(cabinet::LogLevel::Warning, "ignored retained MQTT command on " + message.topic);
                continue;
            }
            try {
                controller.on_server_command(
                    cabinet::parse_server_command(config.controller_id, message.topic, message.payload),
                    Controller::Clock::now());
            } catch (const std::exception &error) {
                log(cabinet::LogLevel::Warning, "ignored invalid MQTT command: " + std::string{error.what()});
            }
        }

        const bool mqtt_state = mqtt.connected();
        if (mqtt_state != last_mqtt_state) {
            controller.on_mqtt_connection_changed(mqtt_state, Controller::Clock::now());
            last_mqtt_state = mqtt_state;
        }
        controller.on_tick(Controller::Clock::now());
        dispatch_actions(controller, mqtt, ports);
    }

    log(cabinet::LogLevel::Info, "shutdown requested");
    return 0;
}

} // namespace

int main(int argc, char **argv)
{
    std::signal(SIGINT, handle_signal);
    std::signal(SIGTERM, handle_signal);
    try {
        return run(parse_arguments(argc, argv));
    } catch (const std::exception &error) {
        std::cerr << "ERROR: " << error.what() << '\n';
        return 1;
    }
}
