# Python SDK

The Python SDK is a typed, dependency-free `ctypes` binding to
`libcr100emur`. It uses the same native serial and parser implementation as
the C and C++ APIs.

## Repository virtual environment

This utility uses the cabinet controller's `.venv`. Run these
commands from the `cabinet/controller` directory:

```sh
make -C utils/cr100emur
.venv/bin/python -m pip install --upgrade setuptools wheel
.venv/bin/python -m pip install \
  --editable utils/cr100emur --no-build-isolation
```

Run the Python tests with the same interpreter:

```sh
.venv/bin/python -m unittest discover \
  -s utils/cr100emur/python/tests -v
```

Equivalent Make targets are available after the packaging tools are present:

```sh
make -C utils/cr100emur python-install
make -C utils/cr100emur python-test
make -C utils/cr100emur python-wheel
make -C utils/cr100emur test-all
```

The editable package resolves the native library from `build/`. A regular
installation resolves a system-installed `libcr100emur.so.0`. A custom path
can be supplied with `CR100EMUR_LIBRARY`.

## Reader API

```python
from cr100emur import Reader

with Reader() as reader:
    card = reader.read(timeout=5.0)
    if card is None:
        raise TimeoutError("No card within five seconds")

    print(card.hex)          # 680069DD2B
    print(card.uid.hex())    # 680069dd2b
    print(card.value)        # 446683536683
```

Timeouts are specified in seconds or with `datetime.timedelta`; `None` waits
indefinitely. `Reader.read_raw()` exposes unparsed bytes for diagnostics.
Readers are context managers and close automatically.

`Reader.fileno()` returns a borrowed serial descriptor for selector-based
frameworks. Do not close it directly.

## Asyncio event reader

`AsyncReader` uses the running loop's file-descriptor readiness API, with no
polling timer or executor thread:

```python
import asyncio
from cr100emur import AsyncReader

async def main() -> None:
    async with AsyncReader() as reader:
        card = await reader.read()
        print(card.hex)

asyncio.run(main())
```

An optional callback can be synchronous or asynchronous:

```python
async def on_card(card):
    await controller_queue.put(card)

async with AsyncReader(on_card=on_card) as reader:
    async for card in reader:
        print("audit", card.hex)
```

See [event-driven.md](event-driven.md) and
[`examples/read_async.py`](../examples/read_async.py).

`find_device()` returns the native SDK's stable path:

```python
from cr100emur import find_device

print(find_device())  # /dev/cr100emur
```

## Incremental parser

```python
from cr100emur import Parser

parser = Parser()
cards = []
for byte in b"\x02" + b"680069DD2B" + b"\r\n\x03":
    cards.extend(parser.feed(bytes([byte])))

assert cards[0].hex == "680069DD2B"
```

## CLI

The editable installation adds `cr100-python` to the repository venv:

```sh
.venv/bin/cr100-python --list
.venv/bin/cr100-python --count 1 --format json
```

The module form is equivalent:

```sh
.venv/bin/python -m cr100emur --count 1
```

## Wheel

Build the pure Python binding wheel with:

```sh
make python-wheel
```

The wheel intentionally does not bundle a platform-specific native library.
Install `libcr100emur` system-wide or set `CR100EMUR_LIBRARY` on the target
machine.
