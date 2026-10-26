#include "cr100emur.hpp"

#include <condition_variable>
#include <exception>
#include <iostream>
#include <mutex>

int main()
{
    std::mutex mutex;
    std::condition_variable condition;
    bool finished = false;
    std::exception_ptr failure;

    try {
        cr100emur::EventReader reader{
            [&](const cr100emur::Card &card) {
                std::cout << "UID: " << card.hex << '\n';
                {
                    std::lock_guard<std::mutex> lock(mutex);
                    finished = true;
                }
                condition.notify_one();
            },
            [&](std::exception_ptr error) {
                {
                    std::lock_guard<std::mutex> lock(mutex);
                    failure = error;
                    finished = true;
                }
                condition.notify_one();
            }};

        std::cout << "Waiting for one event on " << reader.device_path()
                  << "...\n";
        reader.start();
        {
            std::unique_lock<std::mutex> lock(mutex);
            condition.wait(lock, [&] { return finished; });
        }
        reader.stop();
    } catch (...) {
        failure = std::current_exception();
    }

    if (failure) {
        try {
            std::rethrow_exception(failure);
        } catch (const std::exception &error) {
            std::cerr << error.what() << '\n';
        }
        return 1;
    }
    return 0;
}
