#pragma once

#include <atomic>
#include <chrono>
#include <condition_variable>
#include <mutex>
#include <string>
#include <vector>

struct mosquitto;
struct mosquitto_message;

namespace cabinet {

struct MqttMessage {
    std::string topic;
    std::string payload;
    bool retained = false;
};

struct MqttOptions {
    std::string host;
    int port = 1883;
    std::string username;
    std::string password;
    std::string client_id;
    std::string open_subscription;
    std::string complete_subscription;
    int keepalive_seconds = 30;
};

class MqttClient {
public:
    explicit MqttClient(MqttOptions options);
    ~MqttClient();

    MqttClient(const MqttClient &) = delete;
    MqttClient &operator=(const MqttClient &) = delete;

    void start();
    void stop() noexcept;
    [[nodiscard]] bool wait_until_connected(std::chrono::milliseconds timeout);
    [[nodiscard]] bool connected() const noexcept;
    [[nodiscard]] std::vector<MqttMessage> drain_messages();
    void publish(const std::string &topic, const std::string &payload);

private:
    static void on_connect(struct mosquitto *client, void *context, int result);
    static void on_disconnect(struct mosquitto *client, void *context, int result);
    static void on_message(struct mosquitto *client, void *context, const struct mosquitto_message *message);

    void set_connected(bool value);

    MqttOptions options_;
    struct mosquitto *client_ = nullptr;
    bool library_initialized_ = false;
    bool loop_started_ = false;
    std::atomic<bool> connected_{false};
    mutable std::mutex mutex_;
    std::condition_variable condition_;
    std::vector<MqttMessage> messages_;
};

} // namespace cabinet
