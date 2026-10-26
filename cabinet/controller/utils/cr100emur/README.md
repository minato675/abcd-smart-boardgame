# CR-100EMUR Linux driver integration and SDK

Linux support for the S-RFID/Hyunseung `CR-100EMUR`, also sold as
`CR100-EM(232)`. The reader is a read-only 125 kHz EM/EM4100 device.

The important discovery is that this reader does **not** need a new kernel
driver. It contains a standard Silicon Labs CP2102 USB-to-UART bridge
(`10c4:ea60`), supported by Linux's in-tree `cp210x` driver. This project adds
the missing pieces:

- a narrowly matched udev rule for a stable `/dev/cr100emur` node and
  desktop-session access;
- `libcr100emur`, a dependency-free C SDK;
- an idiomatic header-only C++17 SDK;
- a typed Python SDK installed through the repository `.venv`;
- readiness-driven C dispatch, C++ callbacks, and Python asyncio support;
- `cr100-read`, a command-line reader and diagnostic utility;
- `cr100-dump`, a raw-byte protocol and baud diagnostic;
- an incremental parser for the reader's 10-character ASCII hexadecimal UID;
- tests based on the UID shown in the vendor's own terminal screenshot.

See [docs/protocol.md](docs/protocol.md) for the hardware and protocol
evidence and UID representation details. The successful live test is recorded
in [docs/hardware-validation.md](docs/hardware-validation.md).

## Build and test

Requirements are a C11 compiler, a C++17 compiler, GNU Make, Linux/POSIX
termios, and the in-tree `cp210x` module. This utility uses the cabinet
controller repository's `../../.venv/bin/python`.

```sh
make
make test
make examples
make python-install
make python-test
```

The outputs are under `build/`:

```text
build/cr100-read
build/cr100-dump
build/libcr100emur.a
build/libcr100emur.so
build/read-once
build/read-once-cpp
```

## Give the current user access

Without a rule, many distributions expose `/dev/ttyUSB0` only to a serial
device group. Install the supplied rule and reconnect the reader:

```sh
sudo make install-udev
sudo udevadm control --reload-rules
```

Unplug and reconnect the reader after reloading. Confirm detection and access:

```sh
build/cr100-read --list
```

Expected output:

```text
/dev/cr100emur	access=yes
```

On a headless system without a logind-managed active session, add the service
account to the distribution's serial group (`dialout` on Debian/Ubuntu,
`uucp` on Arch Linux) and log in again:

```sh
sudo usermod -aG uucp "$USER"       # Arch Linux
sudo usermod -aG dialout "$USER"    # Debian/Ubuntu
```

## Read cards

Read continuously as uppercase UID hex:

```sh
build/cr100-read
```

Read one card and return:

```sh
build/cr100-read --count 1
```

Other lossless views:

```sh
build/cr100-read --format bytes
build/cr100-read --format decimal
build/cr100-read --format json
```

The live-validated serial setting is 9600 baud, 8 data bits, no parity, one
stop bit, and no flow control. A different hardware revision can be tested
without recompiling:

```sh
build/cr100-read --baud 19200 --count 1
```

Use `--device /dev/ttyUSB0` to bypass auto-discovery or the udev symlink.

## Capture raw protocol bytes

For hardware validation or an unfamiliar revision, present one card while
this command is listening:

```sh
build/cr100-dump --baud 9600
```

It waits up to ten seconds for the first byte, prints the hexadecimal and
ASCII stream, and exits after 100 ms of silence. For example, an STX/ETX
framed UID would look similar to:

```text
00000000  02 33 46 30 30 32 33 38  34 39 33 0d 0a 03        |.3F00238493...|
```

If the ASCII is garbled or no valid scan appears, remove and present the card
again while trying `--baud 19200` or `--baud 38400`.

## Native C SDK

```c
#include <cr100emur.h>
#include <stdio.h>

int main(void)
{
    cr100_handle *reader;
    cr100_card card;
    int result = cr100_open(&reader, NULL, 0);

    if (result != CR100_OK) {
        fprintf(stderr, "%s\n", cr100_strerror(result));
        return 1;
    }

    result = cr100_read_card(reader, &card, -1);
    if (result == CR100_OK)
        printf("UID: %s\n", card.hex);

    cr100_close(reader);
    return result == CR100_OK ? 0 : 1;
}
```

Build against the local static library:

```sh
cc -Iinclude app.c build/libcr100emur.a -o app
```

Or install the header, library, and CLI:

```sh
sudo make install
sudo ldconfig
```

For event-loop integration, `cr100_get_fd()` returns the borrowed serial
descriptor and `cr100_dispatch()` drains all complete cards after a readiness
notification. The SDK API also exposes `cr100_parser_feed()` for applications
that want to parse captured bytes or integrate a different transport.

## C++ SDK

The header-only C++17 wrapper in `include/cr100emur.hpp` provides:

- RAII ownership through `cr100emur::Reader`;
- `std::optional` timeout results;
- `std::chrono` timeouts;
- move-only reader semantics;
- typed `Card`, `Parser`, and exception APIs.
- `EventReader`, a stoppable callback reader backed by `poll(2)`.

Quick build:

```sh
g++ -std=c++17 -Iinclude app.cpp build/libcr100emur.a -o app
```

See [docs/cpp-sdk.md](docs/cpp-sdk.md) and
[examples/read_once.cpp](examples/read_once.cpp). For callback usage, see
[examples/read_events.cpp](examples/read_events.cpp).

## Python SDK

From the `cabinet/controller` directory, install the Python binding into this
repository's virtual environment:

```sh
.venv/bin/python -m pip install --upgrade setuptools wheel
.venv/bin/python -m pip install --editable utils/cr100emur --no-build-isolation
.venv/bin/python -m unittest discover \
  -s utils/cr100emur/python/tests -v
```

Example:

```python
from cr100emur import Reader

with Reader() as reader:
    card = reader.read(timeout=5.0)
    if card is not None:
        print(card.hex, card.uid, card.value)
```

The binding loads the repository's `build/libcr100emur.so` during editable
development, so `make` must run first. See
[docs/python-sdk.md](docs/python-sdk.md) and
[examples/read_once.py](examples/read_once.py).

## Interrupt/event-driven reading

The USB reader does not deliver a hardware interrupt directly to a userspace
program. Linux's `cp210x` driver handles USB/UART interrupts and marks the
serial descriptor readable. These SDK APIs sleep until that kernel readiness
notification, so they do not busy-poll:

- C: register the descriptor from `cr100_get_fd()` with `poll`, `epoll`, or
  the controller's event loop, then call `cr100_dispatch()`;
- C++: use `cr100emur::EventReader` for worker-thread callbacks, or register
  `Reader::file_descriptor()` with an existing loop and call
  `Reader::dispatch()`;
- Python: use `AsyncReader`, which calls `asyncio.add_reader()` internally.

Python callback example:

```python
import asyncio
from cr100emur import AsyncReader

async def main() -> None:
    async with AsyncReader(on_card=lambda card: print(card.hex)):
        await asyncio.Event().wait()

asyncio.run(main())
```

See [docs/event-driven.md](docs/event-driven.md) for lifecycle, threading, and
controller-integration details.

## Current hardware check

Useful commands when diagnosing a connection:

```sh
lsusb -d 10c4:ea60
lsusb -t
udevadm info --query=property --name=/dev/ttyUSB0
modinfo cp210x
```

`lsusb -t` should show `Driver=cp210x`. If the CP2102 is absent entirely,
check the cable/port. If it is present but no `ttyUSB` node appears, load the
in-tree module with `sudo modprobe cp210x`.

## Scope

This reader exposes only the fixed ID of a read-only EM card. It cannot write,
clone, authenticate, or retrieve protected card memory. The SDK deliberately
never transmits bytes to the device.

## Validated hardware result

On the connected `10c4:ea60` reader, `cr100-dump` captured:

```text
02 36 38 30 30 36 39 44 44 32 42 0D 0A 03
```

`cr100-read --count 1 --format json` decoded the same scan as:

```json
{"uid":"680069DD2B","value":446683536683,"bytes":[104,0,105,221,43]}
```

License: MIT.
