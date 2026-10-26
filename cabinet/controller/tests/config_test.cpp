#include "config.hpp"

#include <fcntl.h>
#include <unistd.h>

#include <chrono>
#include <iostream>
#include <stdexcept>
#include <string>

namespace {

using namespace std::chrono_literals;

void check(bool condition, const char *expression, int line)
{
    if (!condition) {
        throw std::runtime_error("check failed at line " + std::to_string(line) + ": " + expression);
    }
}

#define CHECK(expression) check((expression), #expression, __LINE__)

class TemporaryFile {
public:
    explicit TemporaryFile(const std::string &contents)
    {
        char pattern[] = "/tmp/cabinet-config-test-XXXXXX";
        const int descriptor = ::mkstemp(pattern);
        if (descriptor < 0) {
            throw std::runtime_error("mkstemp failed");
        }
        path_ = pattern;
        std::size_t offset = 0;
        while (offset < contents.size()) {
            const auto count = ::write(descriptor, contents.data() + offset, contents.size() - offset);
            if (count <= 0) {
                ::close(descriptor);
                throw std::runtime_error("write temporary config failed");
            }
            offset += static_cast<std::size_t>(count);
        }
        ::close(descriptor);
    }

    ~TemporaryFile()
    {
        ::unlink(path_.c_str());
    }

    const std::string &path() const { return path_; }

private:
    std::string path_;
};

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

void test_valid_config()
{
    TemporaryFile file{R"(
controller_id = rpi-01
mqtt_host=192.168.0.10
mqtt_port=1884
mqtt_username=user
mqtt_password=pass
rfid_device=/dev/cr100emur
cabinet.1=/dev/rfcomm0
cabinet.1.address=00:11:22:33:44:55
cabinet.1.channel=2
cabinet.3=/dev/rfcomm2
command_ack_timeout_ms=2100
communication_timeout_ms=5100
server_timeout_ms=10100
)"};
    const auto config = cabinet::Config::load(file.path());
    CHECK(config.controller_id == "rpi-01");
    CHECK(config.mqtt_port == 1884);
    CHECK(config.cabinets.size() == 2);
    CHECK(config.cabinets.at(1).device == "/dev/rfcomm0");
    CHECK(config.cabinets.at(1).bluetooth_address == "00:11:22:33:44:55");
    CHECK(config.cabinets.at(1).rfcomm_channel == 2);
    CHECK(config.command_ack_timeout == 2100ms);
}

void test_invalid_configs()
{
    TemporaryFile missing{"controller_id=rpi-01\n"};
    expect_failure([&] { (void)cabinet::Config::load(missing.path()); });

    TemporaryFile typo{R"(
controller_id=rpi-01
mqtt_host=localhost
rfid_device=/dev/cr100emur
cabinet.1=/dev/rfcomm0
mqtt_por=1883
)"};
    expect_failure([&] { (void)cabinet::Config::load(typo.path()); });
}

} // namespace

int main()
{
    try {
        test_valid_config();
        test_invalid_configs();
        std::cout << "config tests passed\n";
        return 0;
    } catch (const std::exception &error) {
        std::cerr << error.what() << '\n';
        return 1;
    }
}
