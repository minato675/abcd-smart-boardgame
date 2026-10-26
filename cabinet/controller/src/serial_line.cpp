#include "serial_line.hpp"

#include <cerrno>
#include <cstring>
#include <fcntl.h>
#include <poll.h>
#include <stdexcept>
#include <system_error>
#include <termios.h>
#include <unistd.h>
#include <utility>

namespace cabinet {
namespace {

std::string error_message(const std::string &operation, const std::string &device)
{
    return operation + " " + device + ": " + std::strerror(errno);
}

} // namespace

SerialLine::SerialLine(std::string device, unsigned int baud, std::size_t max_line_length)
    : device_(std::move(device)), max_line_length_(max_line_length)
{
    if (device_.empty() || max_line_length_ == 0) {
        throw std::invalid_argument("serial device and positive line limit are required");
    }
    descriptor_ = ::open(device_.c_str(), O_RDWR | O_NOCTTY | O_NONBLOCK | O_CLOEXEC);
    if (descriptor_ < 0) {
        throw SerialLineError(error_message("open", device_));
    }
    try {
        configure(baud);
        if (::tcflush(descriptor_, TCIOFLUSH) < 0) {
            throw SerialLineError(error_message("flush", device_));
        }
    } catch (...) {
        close();
        throw;
    }
}

SerialLine::~SerialLine()
{
    close();
}

SerialLine::SerialLine(SerialLine &&other) noexcept
    : descriptor_(std::exchange(other.descriptor_, -1)),
      device_(std::move(other.device_)),
      input_buffer_(std::move(other.input_buffer_)),
      max_line_length_(other.max_line_length_),
      discarding_oversized_line_(other.discarding_oversized_line_)
{
}

SerialLine &SerialLine::operator=(SerialLine &&other) noexcept
{
    if (this != &other) {
        close();
        descriptor_ = std::exchange(other.descriptor_, -1);
        device_ = std::move(other.device_);
        input_buffer_ = std::move(other.input_buffer_);
        max_line_length_ = other.max_line_length_;
        discarding_oversized_line_ = other.discarding_oversized_line_;
    }
    return *this;
}

unsigned int SerialLine::speed_for_baud(unsigned int baud)
{
    switch (baud) {
    case 9600:
        return B9600;
    case 19200:
        return B19200;
    case 38400:
        return B38400;
    case 57600:
        return B57600;
    case 115200:
        return B115200;
    default:
        throw std::invalid_argument("unsupported serial baud rate: " + std::to_string(baud));
    }
}

void SerialLine::configure(unsigned int baud)
{
    termios settings{};
    if (::tcgetattr(descriptor_, &settings) < 0) {
        throw SerialLineError(error_message("read termios for", device_));
    }
    ::cfmakeraw(&settings);
    const auto speed = static_cast<speed_t>(speed_for_baud(baud));
    if (::cfsetispeed(&settings, speed) < 0 || ::cfsetospeed(&settings, speed) < 0) {
        throw SerialLineError(error_message("set baud for", device_));
    }
    settings.c_cflag |= CLOCAL | CREAD;
    settings.c_cflag &= ~CSTOPB;
    settings.c_cflag &= ~PARENB;
    settings.c_cflag &= ~CSIZE;
    settings.c_cflag |= CS8;
    settings.c_cc[VMIN] = 0;
    settings.c_cc[VTIME] = 0;
    if (::tcsetattr(descriptor_, TCSANOW, &settings) < 0) {
        throw SerialLineError(error_message("configure", device_));
    }
}

std::vector<std::string> SerialLine::read_available()
{
    if (!is_open()) {
        throw SerialLineError("read from closed serial device");
    }
    std::vector<std::string> lines;
    bool line_too_long = false;
    char buffer[256];
    for (;;) {
        const auto count = ::read(descriptor_, buffer, sizeof(buffer));
        if (count < 0) {
            if (errno == EINTR) {
                continue;
            }
            if (errno == EAGAIN || errno == EWOULDBLOCK) {
                break;
            }
            throw SerialLineError(error_message("read", device_));
        }
        if (count == 0) {
            break;
        }
        for (ssize_t index = 0; index < count; ++index) {
            const char character = buffer[index];
            if (character == '\r' || character == '\n') {
                if (discarding_oversized_line_) {
                    discarding_oversized_line_ = false;
                    input_buffer_.clear();
                } else if (!input_buffer_.empty()) {
                    lines.push_back(std::move(input_buffer_));
                    input_buffer_.clear();
                }
                continue;
            }
            if (discarding_oversized_line_) {
                continue;
            }
            input_buffer_.push_back(character);
            if (input_buffer_.size() > max_line_length_) {
                input_buffer_.clear();
                discarding_oversized_line_ = true;
                line_too_long = true;
            }
        }
    }
    if (line_too_long && lines.empty()) {
        throw LineTooLongError("discarded oversized line from " + device_);
    }
    return lines;
}

void SerialLine::write_line(const std::string &line)
{
    if (!is_open()) {
        throw SerialLineError("write to closed serial device");
    }
    if (line.find('\r') != std::string::npos || line.find('\n') != std::string::npos) {
        throw std::invalid_argument("serial line cannot contain a newline");
    }
    const std::string output = line + '\n';
    std::size_t offset = 0;
    while (offset < output.size()) {
        const auto count = ::write(descriptor_, output.data() + offset, output.size() - offset);
        if (count > 0) {
            offset += static_cast<std::size_t>(count);
            continue;
        }
        if (count < 0 && errno == EINTR) {
            continue;
        }
        if (count < 0 && (errno == EAGAIN || errno == EWOULDBLOCK)) {
            pollfd descriptor{descriptor_, POLLOUT, 0};
            const int result = ::poll(&descriptor, 1, 500);
            if (result > 0) {
                continue;
            }
            if (result < 0 && errno == EINTR) {
                continue;
            }
            if (result == 0) {
                throw SerialLineError("timed out writing " + device_);
            }
        }
        throw SerialLineError(error_message("write", device_));
    }
}

int SerialLine::file_descriptor() const noexcept
{
    return descriptor_;
}

bool SerialLine::is_open() const noexcept
{
    return descriptor_ >= 0;
}

const std::string &SerialLine::device() const noexcept
{
    return device_;
}

void SerialLine::close() noexcept
{
    if (descriptor_ >= 0) {
        ::close(descriptor_);
        descriptor_ = -1;
    }
}

} // namespace cabinet
