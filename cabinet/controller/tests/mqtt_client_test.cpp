#include "mqtt_client.hpp"

#include <fcntl.h>
#include <signal.h>
#include <sys/wait.h>
#include <unistd.h>

#include <chrono>
#include <cstdlib>
#include <iostream>
#include <stdexcept>
#include <string>
#include <thread>
#include <vector>

namespace {

using namespace std::chrono_literals;

void check(bool condition, const char *expression, int line)
{
    if (!condition) {
        throw std::runtime_error("check failed at line " + std::to_string(line) + ": " + expression);
    }
}

#define CHECK(expression) check((expression), #expression, __LINE__)

class BrokerProcess {
public:
    explicit BrokerProcess(int port)
    {
        const std::string port_text = std::to_string(port);
        process_ = ::fork();
        if (process_ < 0) {
            throw std::runtime_error("could not fork MQTT broker");
        }
        if (process_ == 0) {
            const int null_device = ::open("/dev/null", O_RDWR);
            if (null_device >= 0) {
                ::dup2(null_device, STDOUT_FILENO);
                ::dup2(null_device, STDERR_FILENO);
                ::close(null_device);
            }
            ::execl(
                MOSQUITTO_BROKER_EXECUTABLE,
                MOSQUITTO_BROKER_EXECUTABLE,
                "-p",
                port_text.c_str(),
                static_cast<char *>(nullptr));
            _exit(127);
        }
        std::this_thread::sleep_for(150ms);
        int status = 0;
        const pid_t result = ::waitpid(process_, &status, WNOHANG);
        if (result == process_) {
            process_ = -1;
            throw std::runtime_error("MQTT test broker exited during startup");
        }
    }

    ~BrokerProcess()
    {
        if (process_ > 0) {
            ::kill(process_, SIGTERM);
            ::waitpid(process_, nullptr, 0);
        }
    }

    BrokerProcess(const BrokerProcess &) = delete;
    BrokerProcess &operator=(const BrokerProcess &) = delete;

private:
    pid_t process_ = -1;
};

std::vector<cabinet::MqttMessage> wait_for_messages(
    cabinet::MqttClient &client,
    std::size_t expected)
{
    std::vector<cabinet::MqttMessage> messages;
    const auto deadline = std::chrono::steady_clock::now() + 2s;
    while (std::chrono::steady_clock::now() < deadline && messages.size() < expected) {
        auto received = client.drain_messages();
        messages.insert(
            messages.end(),
            std::make_move_iterator(received.begin()),
            std::make_move_iterator(received.end()));
        if (messages.size() < expected) {
            std::this_thread::sleep_for(10ms);
        }
    }
    return messages;
}

void test_publish_subscribe()
{
    const int port = 20'000 + static_cast<int>(::getpid() % 20'000);
    BrokerProcess broker{port};
    const std::string suffix = std::to_string(::getpid());
    cabinet::MqttClient client{{
        .host = "127.0.0.1",
        .port = port,
        .username = {},
        .password = {},
        .client_id = "cabinet-mqtt-test-" + suffix,
        .open_subscription = "/cabinet/test/+/open",
        .complete_subscription = "/cabinet/test/complete",
        .keepalive_seconds = 5}};
    client.start();
    CHECK(client.wait_until_connected(2s));
    std::this_thread::sleep_for(100ms);

    const std::string open_topic = "/cabinet/test/1/open";
    const std::string open_payload =
        R"({"transactionId":"tx","step":1,"mode":"receive"})";
    client.publish(open_topic, open_payload);
    auto messages = wait_for_messages(client, 1);
    CHECK(messages.size() == 1);
    CHECK(messages[0].topic == open_topic);
    CHECK(messages[0].payload == open_payload);
    CHECK(!messages[0].retained);

    const std::string complete_topic = "/cabinet/test/complete";
    const std::string complete_payload = R"({"transactionId":"tx"})";
    client.publish(complete_topic, complete_payload);
    messages = wait_for_messages(client, 1);
    CHECK(messages.size() == 1);
    CHECK(messages[0].topic == complete_topic);
    CHECK(messages[0].payload == complete_payload);
    CHECK(!messages[0].retained);

    client.stop();
    CHECK(!client.connected());
}

} // namespace

int main()
{
    try {
        test_publish_subscribe();
        std::cout << "MQTT client tests passed\n";
        return 0;
    } catch (const std::exception &error) {
        std::cerr << error.what() << '\n';
        return 1;
    }
}
