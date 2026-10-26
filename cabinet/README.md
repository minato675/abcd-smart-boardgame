# Cabinet

The cabinet code is split by runtime target:

- [`unit/`](unit): Arduino firmware for individual cabinet units.
- [`controller/`](controller): Raspberry Pi controller code, utilities, and test tools.

## Raspberry Pi controller

### CR-100EMUR

The Raspberry Pi service and its tests live in [`controller/`](controller).
Build and test them on the Raspberry Pi with:

```sh
cd controller
cmake -S . -B build -DCMAKE_BUILD_TYPE=Debug
cmake --build build --parallel
ctest --test-dir build --output-on-failure
```

The CR-100EMUR Linux driver integration and C, C++, and Python SDK live in
[`controller/utils/cr100emur`](controller/utils/cr100emur). Its native tests
can also be run independently:

```sh
make -C controller/utils/cr100emur test
```

The controller CTest suite includes a loopback Mosquitto test and a full
RFID/MQTT/two-cabinet pseudo-terminal integration flow.

## Arduino cabinet unit

The Arduino firmware for each smart cabinet unit is located in
[`unit/`](unit).

Each cabinet uses one Arduino to control:

- Electronic solenoid lock
- Magnetic door sensor
- Cabinet LED
- Bluetooth communication with Raspberry Pi
- Receive and return processes
- Door open and close callbacks

The main firmware file is:

```text
unit/main.ino
```

The firmware requires the **Adafruit NeoPixel** library.

For wiring, commands, callbacks, library installation, and upload instructions,
see [`unit/README.md`](unit/README.md).
