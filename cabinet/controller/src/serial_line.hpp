#pragma once

#include <cstddef>
#include <stdexcept>
#include <string>
#include <vector>

namespace cabinet {

class SerialLineError : public std::runtime_error {
public:
    using std::runtime_error::runtime_error;
};

class LineTooLongError : public SerialLineError {
public:
    using SerialLineError::SerialLineError;
};

class SerialLine {
public:
    explicit SerialLine(std::string device, unsigned int baud = 9600, std::size_t max_line_length = 128);
    ~SerialLine();

    SerialLine(const SerialLine &) = delete;
    SerialLine &operator=(const SerialLine &) = delete;
    SerialLine(SerialLine &&other) noexcept;
    SerialLine &operator=(SerialLine &&other) noexcept;

    [[nodiscard]] int file_descriptor() const noexcept;
    [[nodiscard]] bool is_open() const noexcept;
    [[nodiscard]] const std::string &device() const noexcept;

    [[nodiscard]] std::vector<std::string> read_available();
    void write_line(const std::string &line);
    void close() noexcept;

private:
    static unsigned int speed_for_baud(unsigned int baud);
    void configure(unsigned int baud);

    int descriptor_ = -1;
    std::string device_;
    std::string input_buffer_;
    std::size_t max_line_length_ = 128;
    bool discarding_oversized_line_ = false;
};

} // namespace cabinet
