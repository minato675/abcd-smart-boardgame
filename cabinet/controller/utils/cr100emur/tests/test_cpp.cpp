#include "cr100emur.hpp"

#include <array>
#include <chrono>
#include <condition_variable>
#include <cstdint>
#include <cstring>
#include <exception>
#include <fcntl.h>
#include <iostream>
#include <mutex>
#include <string>
#include <unistd.h>
#include <utility>

#define EXPECT(condition)                                                     \
    do {                                                                      \
        if (!(condition)) {                                                   \
            std::cerr << __FILE__ << ':' << __LINE__                          \
                      << ": expectation failed: " #condition << '\n';         \
            result = 1;                                                       \
            goto cleanup;                                                     \
        }                                                                     \
    } while (false)

int main()
{
    using namespace std::chrono_literals;

    const std::string frame{"\x02" "680069DD2B" "\r\n\x03", 14};
    int master = -1;
    int result = 0;

    {
        const auto card = cr100emur::Card::from_hex("680069dd2b");
        EXPECT(card.hex == "680069DD2B");
        EXPECT(card.value == UINT64_C(0x680069DD2B));
        EXPECT((card.uid == std::array<std::uint8_t, 5>{
                                0x68, 0x00, 0x69, 0xdd, 0x2b}));
    }

    {
        cr100emur::Parser parser;
        std::vector<cr100emur::Card> cards;

        for (const char byte : frame) {
            auto parsed = parser.feed(
                reinterpret_cast<const std::uint8_t *>(&byte), 1);
            cards.insert(cards.end(), parsed.begin(), parsed.end());
        }
        EXPECT(cards.size() == 1);
        EXPECT(cards.front().hex == "680069DD2B");
    }

    master = posix_openpt(O_RDWR | O_NOCTTY);
    EXPECT(master >= 0);
    EXPECT(grantpt(master) == 0);
    EXPECT(unlockpt(master) == 0);

    {
        const char *slave_path = ptsname(master);
        EXPECT(slave_path != nullptr);

        cr100emur::Reader reader{slave_path};
        EXPECT(reader.is_open());
        EXPECT(reader.file_descriptor() >= 0);
        EXPECT(reader.device_path() == slave_path);
        EXPECT(write(master, frame.data(), frame.size()) ==
               static_cast<ssize_t>(frame.size()));

        const auto card = reader.read_for(500ms);
        EXPECT(card.has_value());
        EXPECT(card->hex == "680069DD2B");
        EXPECT(!reader.read_for(10ms).has_value());

        EXPECT(write(master, frame.data(), frame.size()) ==
               static_cast<ssize_t>(frame.size()));
        struct pollfd ready_descriptor {
            reader.file_descriptor(), POLLIN, 0
        };
        EXPECT(poll(&ready_descriptor, 1, 500) == 1);
        std::size_t dispatched = 0;
        bool dispatched_card_valid = true;
        EXPECT(reader.dispatch(
                   [&dispatched, &dispatched_card_valid](
                       const cr100emur::Card &event_card) {
                       dispatched_card_valid =
                           dispatched_card_valid &&
                           event_card.hex == "680069DD2B";
                       ++dispatched;
                   }) == 1);
        EXPECT(dispatched == 1);
        EXPECT(dispatched_card_valid);

        cr100emur::Reader moved{std::move(reader)};
        EXPECT(!reader.is_open());
        EXPECT(moved.is_open());
        moved.close();
        EXPECT(!moved.is_open());
    }

    {
        const char *slave_path = ptsname(master);
        EXPECT(slave_path != nullptr);

        cr100emur::Reader reader{slave_path};
        EXPECT(write(master, frame.data(), frame.size()) ==
               static_cast<ssize_t>(frame.size()));
        const auto raw = reader.read_raw_for(500ms);
        EXPECT(raw.has_value());
        EXPECT(std::string(raw->begin(), raw->end()) == frame);
        EXPECT(!reader.read_raw_for(10ms).has_value());
    }

    {
        const char *slave_path = ptsname(master);
        bool caught_expected_error = false;
        EXPECT(slave_path != nullptr);

        try {
            cr100emur::Reader invalid_baud{slave_path, 12345};
        } catch (const cr100emur::Error &error) {
            caught_expected_error = error.status() == CR100_ERR_BAUD;
        }
        EXPECT(caught_expected_error);
    }

    {
        const char *slave_path = ptsname(master);
        std::mutex mutex;
        std::condition_variable condition;
        std::vector<std::string> cards;
        std::exception_ptr callback_error;
        EXPECT(slave_path != nullptr);

        cr100emur::EventReader reader{
            [&](const cr100emur::Card &card) {
                {
                    std::lock_guard<std::mutex> lock(mutex);
                    cards.push_back(card.hex);
                }
                condition.notify_one();
            },
            [&](std::exception_ptr error) {
                {
                    std::lock_guard<std::mutex> lock(mutex);
                    callback_error = error;
                }
                condition.notify_one();
            },
            slave_path};

        reader.start();
        EXPECT(reader.running());
        const std::string two_frames = frame + frame;
        EXPECT(write(master, two_frames.data(), two_frames.size()) ==
               static_cast<ssize_t>(two_frames.size()));

        bool received;
        {
            std::unique_lock<std::mutex> lock(mutex);
            received = condition.wait_for(lock, 1s, [&] {
                return cards.size() == 2 || callback_error != nullptr;
            });
        }
        reader.stop();
        EXPECT(received);
        EXPECT(callback_error == nullptr);
        EXPECT(cards.size() == 2);
        EXPECT(cards[0] == "680069DD2B");
        EXPECT(cards[1] == "680069DD2B");
        EXPECT(!reader.running());
        EXPECT(reader.last_error() == nullptr);
    }

cleanup:
    if (master >= 0) {
        close(master);
    }
    if (result == 0) {
        std::cout << "All C++ SDK tests passed.\n";
    }
    return result;
}
