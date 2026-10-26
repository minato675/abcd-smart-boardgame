#include "serial_line.hpp"

#include <fcntl.h>
#include <pty.h>
#include <unistd.h>

#include <chrono>
#include <cstring>
#include <iostream>
#include <stdexcept>
#include <string>
#include <thread>

namespace {

using namespace std::chrono_literals;

void check(bool condition, const char *expression, int line)
{
    if (!condition) {
        throw std::runtime_error("check failed at line " + std::to_string(line) + ": " + expression);
    }
}

#define CHECK(expression) check((expression), #expression, __LINE__)

class PseudoTerminal {
public:
    PseudoTerminal()
    {
        int slave = -1;
        char name[256]{};
        if (::openpty(&master_, &slave, name, nullptr, nullptr) < 0) {
            throw std::runtime_error(std::string{"openpty: "} + std::strerror(errno));
        }
        slave_path_ = name;
        ::close(slave);
        const int flags = ::fcntl(master_, F_GETFL);
        ::fcntl(master_, F_SETFL, flags | O_NONBLOCK);
    }

    ~PseudoTerminal() { ::close(master_); }

    const std::string &slave_path() const { return slave_path_; }

    void send(const std::string &data)
    {
        CHECK(::write(master_, data.data(), data.size()) == static_cast<ssize_t>(data.size()));
        std::this_thread::sleep_for(10ms);
    }

    std::string receive()
    {
        char buffer[256]{};
        for (int attempt = 0; attempt < 20; ++attempt) {
            const auto count = ::read(master_, buffer, sizeof(buffer));
            if (count > 0) {
                return {buffer, static_cast<std::size_t>(count)};
            }
            std::this_thread::sleep_for(5ms);
        }
        return {};
    }

private:
    int master_ = -1;
    std::string slave_path_;
};

void test_line_endings_and_writes()
{
    PseudoTerminal terminal;
    cabinet::SerialLine serial{terminal.slave_path()};
    terminal.send("FIRST\r\nSECOND\nTHIRD\r");
    const auto lines = serial.read_available();
    CHECK(lines.size() == 3);
    CHECK(lines[0] == "FIRST");
    CHECK(lines[1] == "SECOND");
    CHECK(lines[2] == "THIRD");

    serial.write_line("CABINET:1|COMMAND:STATUS");
    CHECK(terminal.receive() == "CABINET:1|COMMAND:STATUS\n");
}

void test_fragmentation_and_limit()
{
    PseudoTerminal terminal;
    cabinet::SerialLine serial{terminal.slave_path(), 9600, 4};
    terminal.send("AB");
    CHECK(serial.read_available().empty());
    terminal.send("CD\n");
    const auto complete = serial.read_available();
    CHECK(complete.size() == 1);
    CHECK(complete.front() == "ABCD");

    terminal.send("TOO-LONG\n");
    try {
        (void)serial.read_available();
        throw std::runtime_error("expected oversized line failure");
    } catch (const cabinet::LineTooLongError &) {
    }
    terminal.send("OK\n");
    const auto recovered = serial.read_available();
    CHECK(recovered.size() == 1);
    CHECK(recovered.front() == "OK");
}

} // namespace

int main()
{
    try {
        test_line_endings_and_writes();
        test_fragmentation_and_limit();
        std::cout << "serial line tests passed\n";
        return 0;
    } catch (const std::exception &error) {
        std::cerr << error.what() << '\n';
        return 1;
    }
}
