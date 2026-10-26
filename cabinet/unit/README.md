# Arduino Cabinet Controller

This directory contains the Arduino firmware used to control each smart cabinet.

Each cabinet has one Arduino responsible for:

- Electronic lock control
- Magnetic door sensor
- Cabinet LED control
- Bluetooth communication with Raspberry Pi

---

# Firmware

Main firmware:

```text
main.ino
```

Each cabinet must have its own cabinet ID.

Example:

```cpp
const int CABINET_ID = 1;
```

Cabinet 2:

```cpp
const int CABINET_ID = 2;
```

---

# Process

## Default

- Cabinet locked
- White LED
- Waiting for Bluetooth command

## Receive

1. Blue LED
2. Unlock cabinet
3. Wait until door is opened
4. Send `DOOR_OPENED`
5. Wait until door is closed
6. Send `DOOR_CLOSED`
7. Return to default state

## Return

1. Red LED
2. Unlock cabinet
3. Wait until door is opened
4. Send `DOOR_OPENED`
5. Wait until door is closed
6. Send `DOOR_CLOSED`
7. Return to default state

---

# Bluetooth Command

Receive

```text
CABINET:1|COMMAND:RECEIVE
```

Return

```text
CABINET:1|COMMAND:RETURN
```

Commands should end with a newline (`\n`).

Status queries do not unlock the cabinet and are accepted even while a process
is active:

```text
CABINET:1|COMMAND:STATUS
```

The response reports the debounced physical door state:

```text
CABINET:1|MODE:NONE|EVENT:STATUS|STATE:CLOSED
CABINET:1|MODE:NONE|EVENT:STATUS|STATE:OPEN
```

---

# Callback

Example callbacks:

```text
CABINET:1|MODE:RECEIVE|EVENT:COMMAND_ACCEPTED
CABINET:1|MODE:RECEIVE|EVENT:DOOR_OPENED
CABINET:1|MODE:RECEIVE|EVENT:DOOR_CLOSED

CABINET:1|MODE:RETURN|EVENT:COMMAND_ACCEPTED
CABINET:1|MODE:RETURN|EVENT:DOOR_OPENED
CABINET:1|MODE:RETURN|EVENT:DOOR_CLOSED
```

Possible error callbacks:

```text
CABINET:1|MODE:RECEIVE|EVENT:OPEN_TIMEOUT
CABINET:1|MODE:RETURN|EVENT:DOOR_OPEN_TOO_LONG
CABINET:1|MODE:NONE|EVENT:COMMAND_REJECTED|REASON:BUSY
CABINET:1|MODE:NONE|EVENT:COMMAND_REJECTED|REASON:DOOR_ALREADY_OPEN
```

---

# Pin Assignment

| Device | Pin |
|---------|-----|
| Magnetic Sensor | D2 |
| Lock (MOSFET) | D3 |
| WS2812B LED | D6 |
| Bluetooth RX | D10 |
| Bluetooth TX | D11 |

---

# Required Library

This project uses the Adafruit NeoPixel library.

The following header is required:

```cpp
#include <Adafruit_NeoPixel.h>
```

## Arduino IDE

1. Open **Library Manager**
2. Search **Adafruit NeoPixel**
3. Install **Adafruit NeoPixel by Adafruit**

## Arduino CLI

```bash
arduino-cli lib install "Adafruit NeoPixel"
```

Without this library the firmware will not compile.

---

# Upload

1. Open `main.ino`
2. Select the correct Arduino board.
3. Select the correct COM port.
4. Upload the firmware.

Before uploading to another cabinet, change:

```cpp
const int CABINET_ID = X;
```

so that every cabinet has a unique ID.