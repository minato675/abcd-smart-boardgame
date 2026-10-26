# C++ SDK

The C++17 SDK is a header-only, type-safe wrapper over the live-validated C
library. It does not duplicate serial or protocol logic.

## Build

```sh
make
make test
make examples
```

The C++ test is `build/test-cpp` and the example is
`build/read-once-cpp`.

Build an application against the repository:

```sh
g++ -std=c++17 -Iinclude app.cpp build/libcr100emur.a -pthread -o app
```

After `sudo make install && sudo ldconfig`:

```sh
g++ -std=c++17 app.cpp -lcr100emur -pthread -o app
```

## Reader API

```cpp
#include <cr100emur.hpp>

#include <chrono>
#include <iostream>

int main()
{
    using namespace std::chrono_literals;

    try {
        cr100emur::Reader reader; // auto-discovers /dev/cr100emur
        auto card = reader.read_for(5s);

        if (!card) {
            std::cerr << "No card within five seconds\n";
            return 2;
        }
        std::cout << card->hex << ' ' << card->value << '\n';
    } catch (const cr100emur::Error &error) {
        std::cerr << error.what() << '\n';
        return 1;
    }
}
```

`Reader` owns and closes the native handle, is non-copyable, and supports
move construction and move assignment. Its main operations are:

- `read()` — wait indefinitely and return a `Card`;
- `read_for(milliseconds)` — return `std::optional<Card>`;
- `read_raw()` and `read_raw_for()` — protocol diagnostics;
- `device_path()` — selected stable device path;
- `close()` — explicit early close.
- `file_descriptor()` — borrowed descriptor for an existing event loop;
- `dispatch(handler)` — synchronously drain ready cards without blocking.

`Card` contains:

- `std::array<std::uint8_t, 5> uid`;
- uppercase `std::string hex`;
- lossless 40-bit value stored in `std::uint64_t value`.

## Incremental parser

`cr100emur::Parser` handles arbitrary serial fragmentation independently of a
device:

```cpp
cr100emur::Parser parser;
auto cards = parser.feed("\x02" "680069DD2B" "\r\n\x03");
```

The parser can also accept a byte pointer and length.

## Event callbacks

`EventReader` waits on descriptor readiness and invokes a callback from its
worker thread:

```cpp
cr100emur::EventReader reader{
    [](const cr100emur::Card &card) {
        controller_queue.push(card);
    },
    [](std::exception_ptr error) {
        report_reader_error(error);
    }};

reader.start();
run_controller();
reader.stop();
```

Callbacks should be short and thread-safe. `request_stop()` can be called by
a handler; call `stop()` from the owning thread to join. Compile callback
users with `-pthread`. See [event-driven.md](event-driven.md) and
[`examples/read_events.cpp`](../examples/read_events.cpp).
