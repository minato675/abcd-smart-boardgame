#ifndef CR100EMUR_HPP
#define CR100EMUR_HPP

#include "cr100emur.h"

#include <array>
#include <atomic>
#include <cerrno>
#include <chrono>
#include <climits>
#include <cstddef>
#include <cstdint>
#include <cstring>
#include <exception>
#include <fcntl.h>
#include <functional>
#include <mutex>
#include <optional>
#include <poll.h>
#include <stdexcept>
#include <string>
#include <string_view>
#include <system_error>
#include <thread>
#include <utility>
#include <vector>
#include <unistd.h>

namespace cr100emur {

inline constexpr unsigned int default_baud = CR100EMUR_DEFAULT_BAUD;
inline constexpr std::size_t uid_size = CR100EMUR_UID_BYTES;
inline constexpr std::size_t uid_hex_length = CR100EMUR_UID_HEX_LENGTH;

class Error : public std::runtime_error {
public:
    Error(int status, std::string message)
        : std::runtime_error(std::move(message)), status_(status)
    {
    }

    [[nodiscard]] int status() const noexcept
    {
        return status_;
    }

private:
    int status_;
};

namespace detail {

[[noreturn]] inline void throw_error(int status,
                                     std::string_view operation = {})
{
    std::string message;

    if (!operation.empty()) {
        message.append(operation);
        message.append(": ");
    }
    message.append(cr100_strerror(status));
    if ((status == CR100_ERR_ACCESS || status == CR100_ERR_IO) &&
        errno != 0) {
        message.append(": ");
        message.append(std::strerror(errno));
    }
    throw Error(status, std::move(message));
}

inline int timeout_milliseconds(std::chrono::milliseconds timeout)
{
    const auto count = timeout.count();

    if (count < 0 || count > INT_MAX) {
        throw std::invalid_argument(
            "timeout must be between 0 and INT_MAX milliseconds");
    }
    return static_cast<int>(count);
}

} // namespace detail

struct Card {
    std::array<std::uint8_t, uid_size> uid{};
    std::string hex;
    std::uint64_t value = 0;

    [[nodiscard]] static Card from_hex(std::string_view text)
    {
        cr100_card native{};
        const std::string terminated{text};
        const int status = cr100_card_from_hex(terminated.c_str(), &native);

        if (status != CR100_OK) {
            detail::throw_error(status, "parse card UID");
        }
        return from_native(native);
    }

    [[nodiscard]] static Card from_native(const cr100_card &native)
    {
        Card card;

        for (std::size_t index = 0; index < card.uid.size(); ++index) {
            card.uid[index] = native.uid[index];
        }
        card.hex.assign(native.hex, uid_hex_length);
        card.value = native.value;
        return card;
    }
};

[[nodiscard]] inline std::string find_device()
{
    std::array<char, 512> path{};
    const int status = cr100_find_device(path.data(), path.size());

    if (status != CR100_OK) {
        detail::throw_error(status, "find CR-100EMUR");
    }
    return path.data();
}

class Parser {
public:
    Parser()
    {
        cr100_parser_init(&parser_);
    }

    [[nodiscard]] std::vector<Card> feed(const std::uint8_t *data,
                                         std::size_t size)
    {
        if (data == nullptr && size != 0) {
            throw std::invalid_argument("data cannot be null when size > 0");
        }

        const std::size_t capacity = size == 0 ? 0 : size + 1;
        std::vector<cr100_card> native_cards(capacity);
        std::size_t count = 0;
        const int status = cr100_parser_feed(
            &parser_,
            data,
            size,
            capacity == 0 ? nullptr : native_cards.data(),
            capacity,
            &count);

        if (status != CR100_OK) {
            detail::throw_error(status, "parse card stream");
        }

        std::vector<Card> cards;
        cards.reserve(count);
        for (std::size_t index = 0; index < count; ++index) {
            cards.push_back(Card::from_native(native_cards[index]));
        }
        return cards;
    }

    [[nodiscard]] std::vector<Card> feed(std::string_view data)
    {
        return feed(reinterpret_cast<const std::uint8_t *>(data.data()),
                    data.size());
    }

private:
    cr100_parser parser_{};
};

class Reader {
public:
    explicit Reader(std::string device = {},
                    unsigned int baud = default_baud)
    {
        const char *path = device.empty() ? nullptr : device.c_str();
        const int status = cr100_open(&handle_, path, baud);

        if (status != CR100_OK) {
            detail::throw_error(status, "open CR-100EMUR");
        }
    }

    ~Reader()
    {
        cr100_close(handle_);
    }

    Reader(const Reader &) = delete;
    Reader &operator=(const Reader &) = delete;

    Reader(Reader &&other) noexcept
        : handle_(std::exchange(other.handle_, nullptr))
    {
    }

    Reader &operator=(Reader &&other) noexcept
    {
        if (this != &other) {
            cr100_close(handle_);
            handle_ = std::exchange(other.handle_, nullptr);
        }
        return *this;
    }

    [[nodiscard]] bool is_open() const noexcept
    {
        return handle_ != nullptr;
    }

    void close() noexcept
    {
        cr100_close(handle_);
        handle_ = nullptr;
    }

    [[nodiscard]] std::string device_path() const
    {
        ensure_open();
        const char *path = cr100_device_path(handle_);
        return path == nullptr ? std::string{} : std::string{path};
    }

    [[nodiscard]] int file_descriptor() const
    {
        ensure_open();
        int fd = -1;
        const int status = cr100_get_fd(handle_, &fd);

        if (status != CR100_OK) {
            detail::throw_error(status, "get CR-100EMUR descriptor");
        }
        return fd;
    }

    [[nodiscard]] Card read()
    {
        return read_with_timeout(-1).value();
    }

    [[nodiscard]] std::optional<Card>
    read_for(std::chrono::milliseconds timeout)
    {
        return read_with_timeout(detail::timeout_milliseconds(timeout));
    }

    [[nodiscard]] std::vector<std::uint8_t>
    read_raw(std::size_t capacity = 256)
    {
        return read_raw_with_timeout(capacity, -1).value();
    }

    [[nodiscard]] std::optional<std::vector<std::uint8_t>>
    read_raw_for(std::chrono::milliseconds timeout,
                 std::size_t capacity = 256)
    {
        return read_raw_with_timeout(
            capacity, detail::timeout_milliseconds(timeout));
    }

    /*
     * Drain cards that are ready now and invoke handler synchronously.
     *
     * This is intended for an event loop after file_descriptor() reports
     * readable. It never waits for more serial input.
     */
    template <typename Handler>
    std::size_t dispatch(Handler &&handler)
    {
        std::size_t count = 0;
        auto &&callback = handler;

        for (;;) {
            auto card = read_with_timeout(0);
            if (!card.has_value()) {
                return count;
            }
            std::invoke(callback, *card);
            ++count;
        }
    }

private:
    void ensure_open() const
    {
        if (handle_ == nullptr) {
            throw std::logic_error("CR-100EMUR reader is closed");
        }
    }

    [[nodiscard]] std::optional<Card> read_with_timeout(int timeout_ms)
    {
        ensure_open();
        cr100_card native{};
        const int status = cr100_read_card(handle_, &native, timeout_ms);

        if (status == CR100_TIMEOUT) {
            return std::nullopt;
        }
        if (status != CR100_OK) {
            detail::throw_error(status, "read card");
        }
        return Card::from_native(native);
    }

    [[nodiscard]] std::optional<std::vector<std::uint8_t>>
    read_raw_with_timeout(std::size_t capacity, int timeout_ms)
    {
        ensure_open();
        if (capacity == 0) {
            throw std::invalid_argument("raw read capacity must be positive");
        }

        std::vector<std::uint8_t> data(capacity);
        std::size_t size = 0;
        const int status = cr100_read_raw(
            handle_, data.data(), data.size(), &size, timeout_ms);

        if (status == CR100_TIMEOUT) {
            return std::nullopt;
        }
        if (status != CR100_OK) {
            detail::throw_error(status, "read raw bytes");
        }
        data.resize(size);
        return data;
    }

    cr100_handle *handle_ = nullptr;
};

/*
 * Callback reader backed by poll(2), not a busy-wait loop.
 *
 * Card handlers execute on the worker thread. Keep them short and hand work
 * off to the application's own queue when necessary. ErrorHandler receives
 * an exception_ptr because native I/O failures and user callback failures are
 * both reported through the same channel.
 */
class EventReader final {
public:
    using CardHandler = std::function<void(const Card &)>;
    using ErrorHandler = std::function<void(std::exception_ptr)>;

    explicit EventReader(CardHandler on_card,
                         ErrorHandler on_error = {},
                         std::string device = {},
                         unsigned int baud = default_baud)
        : reader_(std::move(device), baud),
          on_card_(std::move(on_card)),
          on_error_(std::move(on_error))
    {
        int descriptors[2];

        if (!on_card_) {
            throw std::invalid_argument("card handler cannot be empty");
        }
        if (::pipe(descriptors) != 0) {
            throw std::system_error(
                errno, std::generic_category(), "create event-reader wake pipe");
        }
        wake_read_ = descriptors[0];
        wake_write_ = descriptors[1];

        try {
            configure_wake_descriptor(wake_read_);
            configure_wake_descriptor(wake_write_);
        } catch (...) {
            ::close(wake_read_);
            ::close(wake_write_);
            wake_read_ = -1;
            wake_write_ = -1;
            throw;
        }
    }

    ~EventReader()
    {
        stop();
        if (wake_read_ >= 0) {
            ::close(wake_read_);
        }
        if (wake_write_ >= 0) {
            ::close(wake_write_);
        }
    }

    EventReader(const EventReader &) = delete;
    EventReader &operator=(const EventReader &) = delete;
    EventReader(EventReader &&) = delete;
    EventReader &operator=(EventReader &&) = delete;

    void start()
    {
        if (worker_.joinable()) {
            throw std::logic_error("event reader is already started");
        }

        {
            std::lock_guard<std::mutex> lock(error_mutex_);
            last_error_ = nullptr;
        }
        stop_requested_.store(false);
        running_.store(true);
        try {
            worker_ = std::thread([this] { run(); });
        } catch (...) {
            running_.store(false);
            throw;
        }
    }

    void request_stop() noexcept
    {
        const std::uint8_t byte = 1;

        stop_requested_.store(true);
        if (wake_write_ < 0) {
            return;
        }

        ssize_t result;
        do {
            result = ::write(wake_write_, &byte, sizeof(byte));
        } while (result < 0 && errno == EINTR);
    }

    void stop() noexcept
    {
        request_stop();
        if (worker_.joinable() &&
            worker_.get_id() != std::this_thread::get_id()) {
            worker_.join();
        }
    }

    [[nodiscard]] bool running() const noexcept
    {
        return running_.load();
    }

    [[nodiscard]] std::string device_path() const
    {
        return reader_.device_path();
    }

    [[nodiscard]] std::exception_ptr last_error() const
    {
        std::lock_guard<std::mutex> lock(error_mutex_);
        return last_error_;
    }

private:
    static void configure_wake_descriptor(int fd)
    {
        const int status_flags = ::fcntl(fd, F_GETFL);
        const int descriptor_flags = ::fcntl(fd, F_GETFD);

        if (status_flags < 0 || descriptor_flags < 0 ||
            ::fcntl(fd, F_SETFL, status_flags | O_NONBLOCK) < 0 ||
            ::fcntl(fd, F_SETFD, descriptor_flags | FD_CLOEXEC) < 0) {
            throw std::system_error(
                errno, std::generic_category(), "configure event-reader pipe");
        }
    }

    void drain_wake_pipe() noexcept
    {
        std::array<std::uint8_t, 64> buffer{};

        for (;;) {
            const ssize_t result =
                ::read(wake_read_, buffer.data(), buffer.size());
            if (result > 0) {
                continue;
            }
            if (result < 0 && errno == EINTR) {
                continue;
            }
            return;
        }
    }

    void report_error(std::exception_ptr error) noexcept
    {
        {
            std::lock_guard<std::mutex> lock(error_mutex_);
            last_error_ = error;
        }
        if (on_error_) {
            try {
                on_error_(error);
            } catch (...) {
                // Error reporting must not terminate the worker thread.
            }
        }
    }

    void run() noexcept
    {
        try {
            const int reader_fd = reader_.file_descriptor();

            while (!stop_requested_.load()) {
                std::array<struct pollfd, 2> descriptors{{
                    {reader_fd, POLLIN, 0},
                    {wake_read_, POLLIN, 0},
                }};
                int result;

                do {
                    result = ::poll(
                        descriptors.data(), descriptors.size(), -1);
                } while (result < 0 && errno == EINTR);

                if (result < 0) {
                    throw std::system_error(
                        errno, std::generic_category(), "poll CR-100EMUR");
                }
                if (descriptors[1].revents != 0) {
                    drain_wake_pipe();
                    if (stop_requested_.load()) {
                        break;
                    }
                }
                if (descriptors[0].revents &
                    (POLLERR | POLLHUP | POLLNVAL)) {
                    throw Error(
                        CR100_ERR_DISCONNECTED,
                        "CR-100EMUR disconnected while waiting for a card");
                }
                if (descriptors[0].revents & POLLIN) {
                    reader_.dispatch(on_card_);
                }
            }
        } catch (...) {
            report_error(std::current_exception());
        }
        running_.store(false);
    }

    Reader reader_;
    CardHandler on_card_;
    ErrorHandler on_error_;
    int wake_read_ = -1;
    int wake_write_ = -1;
    std::atomic<bool> stop_requested_{false};
    std::atomic<bool> running_{false};
    std::thread worker_;
    mutable std::mutex error_mutex_;
    std::exception_ptr last_error_;
};

} // namespace cr100emur

#endif
