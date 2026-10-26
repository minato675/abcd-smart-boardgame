# Raspberry Pi RFID cabinet controller

This service connects a CR-100EMUR RFID reader, an MQTT server, and one or more
Arduino cabinets over Bluetooth Classic RFCOMM. One card starts one transaction.
Cabinets are opened sequentially, and a transaction ends only when the server
publishes `complete` after the last door has closed.

The controller is intentionally small:

- `controller.cpp` is a hardware-independent single-transaction state machine.
- `protocol.cpp` validates MQTT JSON and Arduino key/value messages.
- `serial_line.cpp` provides bounded, non-blocking RFCOMM line I/O.
- `mqtt_client.cpp` queues libmosquitto callbacks for the controller loop.
- the existing `utils/cr100emur` SDK provides event-driven RFID input.

The exact MQTT and Arduino messages are in [docs/protocol.md](docs/protocol.md).

## Dependencies

Debian packages:

```sh
sudo apt install build-essential cmake pkg-config libmosquitto-dev nlohmann-json3-dev bluez
```

The project uses only libmosquitto and nlohmann/json beyond the existing
dependency-free CR-100EMUR SDK and Linux/POSIX APIs.

## Build and test

Run from `cabinet/controller`:

```sh
cmake -S . -B build -DCMAKE_BUILD_TYPE=Debug
cmake --build build --parallel
ctest --test-dir build --output-on-failure
```

The test suite covers strict protocol parsing, configuration validation,
fragmented CR/LF/CRLF serial input, the line-length limit, and the required
single- and multi-cabinet state-machine scenarios. It uses pseudo-terminals and
does not require physical cabinet hardware or an MQTT broker.

## Configure

```sh
cp config/controller.conf.example config/controller.conf
editor config/controller.conf
./build/rpi-cabinet-controller --config config/controller.conf --check-config
```

Required settings are the controller ID, MQTT broker, RFID device, and at least
one cabinet-to-RFCOMM mapping:

```ini
controller_id=rpi-01
mqtt_host=192.168.0.10
mqtt_port=1883
mqtt_username=cabinet-controller
mqtt_password=secret
rfid_device=/dev/cr100emur
cabinet.1=/dev/rfcomm0
cabinet.2=/dev/rfcomm1
```

The CR-100EMUR udev rule creates `/dev/cr100emur`. Build and validate that SDK
independently when bringing up new hardware:

```sh
make -C utils/cr100emur test
# Optional Python SDK checks when no repository virtualenv is installed:
PYTHONPATH=utils/cr100emur/python/src \
  python3 -m unittest discover -s utils/cr100emur/python/tests -v
utils/cr100emur/build/cr100-read --list
```

## Bluetooth setup

Pair each BT04-A/HC-05-style module once using the normal BlueZ workflow.
Automatic pairing is outside the MVP. Either bind RFCOMM units separately or
add the already-paired address to the config:

```ini
cabinet.1=/dev/rfcomm0
cabinet.1.address=00:11:22:33:44:55
cabinet.1.channel=1
```

Then run:

```sh
sudo scripts/setup-rfcomm.sh config/controller.conf
```

Each Arduino must have the same cabinet number as its mapping and must support
the `STATUS` command in the sibling `cabinet/unit` firmware. A mismatch causes
`FAULT` instead of opening a potentially wrong cabinet.

## Local mock server

For a two-cabinet development cycle, start the included MQTT mock in a separate
terminal before running the controller:

```sh
python3 tools/mock-server/mock_server.py \
  --host 127.0.0.1 \
  --controller-id rpi-01 \
  --return-cabinet 1 \
  --receive-cabinet 2
```

For each new RFID transaction, the mock publishes these commands with MQTT QoS
1 and retain disabled:

1. Open cabinet 1 in `return` mode (`step: 1`).
2. Wait for its matching `closed` status.
3. Wait one second, then open cabinet 2 in `receive` mode (`step: 2`).
4. Wait for its matching `closed` status, then publish `complete`.

The mock permits one active transaction at a time and ignores duplicate or
unrelated events. Return and receive cabinet numbers are configurable and may
also be the same. It requires the `mosquitto_pub` and `mosquitto_sub` commands.

## Run

For foreground diagnostics:

```sh
./build/rpi-cabinet-controller --config config/controller.conf
```

Logs go to standard output/error, so systemd captures them in journald.

Production installation builds and reruns the tests before installing. It
creates a dedicated service account and preserves an existing production
configuration:

```sh
sudo scripts/install.sh
sudo editor /etc/rpi-cabinet-controller/controller.conf
sudo -u cabinet-controller /usr/local/bin/rpi-cabinet-controller \
  --config /etc/rpi-cabinet-controller/controller.conf --check-config
sudo systemctl start rpi-cabinet-controller
journalctl -u rpi-cabinet-controller -f
```

## Safety behavior

RFID is accepted only in `IDLE`. At startup, every configured Arduino must
answer `STATUS` with `CLOSED`. STATUS is retried once per second until the
communication timeout so a command lost while RFCOMM settles can recover. An open door, missing response, bad mapping, or
unavailable RFCOMM port leaves the controller in `FAULT`.

During a transaction:

- other card scans are discarded;
- QoS 1 duplicates, old steps, wrong transaction IDs, and out-of-order steps
  are ignored;
- only one cabinet command can execute at a time;
- `DOOR_OPEN_TOO_LONG` publishes `close_timeout` but retains the transaction;
- only a real `DOOR_CLOSED` permits the next server step;
- only `complete` in `WAITING_SERVER` returns to `IDLE`;
- `BUSY`, `DOOR_ALREADY_OPEN`, and wrong-cabinet rejections enter `FAULT`
  after publishing the device error;
- an ambiguous transport, response, or MQTT failure enters `FAULT`.

`FAULT` is deliberately not self-clearing. Confirm every door is closed, fix
the reported cause, and restart the service.

## Hardware acceptance

The automated tests prove controller logic without activating real locks. On
the installed Raspberry Pi, complete these checks before production use:

1. `STATUS` reports `CLOSED` for every closed cabinet and `OPEN` for an open one.
2. A receive command produces `COMMAND_ACCEPTED`, `DOOR_OPENED`, then
   `DOOR_CLOSED` on its mapped RFCOMM port.
3. Repeat for return mode and every cabinet number.
4. Run a two-cabinet MQTT transaction and confirm only one lock is active.
5. Repeat the duplicate, wrong transaction, old/out-of-order step, early next
   cabinet, long-open, disconnect, and restart-with-open-door cases from the
   project protocol plan.
6. Confirm published MQTT messages use QoS 1 and are not retained.

These physical lock, Bluetooth radio, broker ACL, and systemd boot checks cannot
be established by the unit tests alone and must be recorded during site
commissioning.
