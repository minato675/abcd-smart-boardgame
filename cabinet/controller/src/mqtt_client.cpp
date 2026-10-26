#include "mqtt_client.hpp"

#include <mosquitto.h>

#include <stdexcept>
#include <utility>

namespace cabinet {
namespace {

void check_result(int result, const std::string &operation)
{
    if (result != MOSQ_ERR_SUCCESS) {
        throw std::runtime_error(operation + ": " + mosquitto_strerror(result));
    }
}

} // namespace

MqttClient::MqttClient(MqttOptions options)
    : options_(std::move(options))
{
    if (options_.host.empty() || options_.client_id.empty() || options_.open_subscription.empty() ||
        options_.complete_subscription.empty()) {
        throw std::invalid_argument("MQTT host, client id, and subscriptions are required");
    }
    check_result(mosquitto_lib_init(), "initialize libmosquitto");
    library_initialized_ = true;
    client_ = mosquitto_new(options_.client_id.c_str(), true, this);
    if (client_ == nullptr) {
        mosquitto_lib_cleanup();
        library_initialized_ = false;
        throw std::runtime_error("create MQTT client: out of memory");
    }
    mosquitto_connect_callback_set(client_, &MqttClient::on_connect);
    mosquitto_disconnect_callback_set(client_, &MqttClient::on_disconnect);
    mosquitto_message_callback_set(client_, &MqttClient::on_message);
    check_result(mosquitto_reconnect_delay_set(client_, 1, 30, true), "set MQTT reconnect delay");
    if (!options_.username.empty()) {
        check_result(
            mosquitto_username_pw_set(client_, options_.username.c_str(), options_.password.c_str()),
            "set MQTT credentials");
    }
}

MqttClient::~MqttClient()
{
    stop();
    if (client_ != nullptr) {
        mosquitto_destroy(client_);
        client_ = nullptr;
    }
    if (library_initialized_) {
        mosquitto_lib_cleanup();
    }
}

void MqttClient::start()
{
    if (loop_started_) {
        throw std::logic_error("MQTT client already started");
    }
    check_result(
        mosquitto_connect_async(
            client_, options_.host.c_str(), options_.port, options_.keepalive_seconds),
        "start MQTT connection");
    check_result(mosquitto_loop_start(client_), "start MQTT network loop");
    loop_started_ = true;
}

void MqttClient::stop() noexcept
{
    if (!loop_started_) {
        return;
    }
    mosquitto_disconnect(client_);
    mosquitto_loop_stop(client_, true);
    loop_started_ = false;
    set_connected(false);
}

bool MqttClient::wait_until_connected(std::chrono::milliseconds timeout)
{
    std::unique_lock lock{mutex_};
    return condition_.wait_for(lock, timeout, [this] { return connected_.load(); });
}

bool MqttClient::connected() const noexcept
{
    return connected_.load();
}

std::vector<MqttMessage> MqttClient::drain_messages()
{
    std::scoped_lock lock{mutex_};
    std::vector<MqttMessage> result;
    result.swap(messages_);
    return result;
}

void MqttClient::publish(const std::string &topic, const std::string &payload)
{
    if (!connected()) {
        throw std::runtime_error("MQTT client is disconnected");
    }
    int message_id = 0;
    const int result = mosquitto_publish(
        client_,
        &message_id,
        topic.c_str(),
        static_cast<int>(payload.size()),
        payload.data(),
        1,
        false);
    check_result(result, "publish MQTT message");
}

void MqttClient::on_connect(struct mosquitto *client, void *context, int result)
{
    auto &self = *static_cast<MqttClient *>(context);
    if (result != 0) {
        self.set_connected(false);
        return;
    }
    int message_id = 0;
    if (mosquitto_subscribe(client, &message_id, self.options_.open_subscription.c_str(), 1) !=
        MOSQ_ERR_SUCCESS) {
        self.set_connected(false);
        return;
    }
    if (mosquitto_subscribe(client, &message_id, self.options_.complete_subscription.c_str(), 1) !=
        MOSQ_ERR_SUCCESS) {
        self.set_connected(false);
        return;
    }
    self.set_connected(true);
}

void MqttClient::on_disconnect(struct mosquitto *client, void *context, int result)
{
    (void)client;
    (void)result;
    auto &self = *static_cast<MqttClient *>(context);
    self.set_connected(false);
}

void MqttClient::on_message(
    struct mosquitto *client,
    void *context,
    const struct mosquitto_message *message)
{
    (void)client;
    if (message == nullptr || message->topic == nullptr || message->payloadlen < 0) {
        return;
    }
    auto &self = *static_cast<MqttClient *>(context);
    const auto *payload = static_cast<const char *>(message->payload);
    MqttMessage queued{
        message->topic,
        payload == nullptr ? std::string{} : std::string{payload, static_cast<std::size_t>(message->payloadlen)},
        message->retain};
    std::scoped_lock lock{self.mutex_};
    self.messages_.push_back(std::move(queued));
}

void MqttClient::set_connected(bool value)
{
    connected_ = value;
    condition_.notify_all();
}

} // namespace cabinet
