#pragma once

#include <chrono>
#include <map>
#include <string>

namespace cabinet {

struct CabinetConfig {
    std::string device;
    std::string bluetooth_address;
    int rfcomm_channel = 1;
};

struct Config {
    std::string controller_id;

    std::string mqtt_host;
    int mqtt_port = 1883;
    std::string mqtt_username;
    std::string mqtt_password;
    int mqtt_keepalive_seconds = 30;

    std::string rfid_device;
    unsigned int rfid_baud = 9600;

    std::map<int, CabinetConfig> cabinets;

    std::chrono::milliseconds command_ack_timeout{2000};
    std::chrono::milliseconds communication_timeout{5000};
    std::chrono::milliseconds server_timeout{10000};

    [[nodiscard]] static Config load(const std::string &path);
    void validate() const;
};

} // namespace cabinet
