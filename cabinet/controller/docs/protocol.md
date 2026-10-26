# Controller protocol

This is the authoritative controller protocol. Older forms such as
`/cabinet/{cabinetNumber}/open`, `/reset`, or an `open` payload without
`controllerId`, `transactionId`, `step`, and `mode` are deprecated.

All MQTT messages use JSON, QoS 1, and `retain=false`. The server must also
publish commands with `retain=false`; the controller rejects retained commands.

## Card

Topic: `/cabinet/{controllerId}/card`

```json
{"transactionId":"rpi-01-20260729-120000-000001","cardUid":"04A12B34CD"}
```

## Open command

Topic: `/cabinet/{controllerId}/{cabinetNumber}/open`

```json
{"transactionId":"rpi-01-20260729-120000-000001","step":1,"mode":"receive"}
```

`mode` is exactly `receive` or `return`. The controller translates it to one
of these newline-terminated 9600-baud RFCOMM commands:

```text
CABINET:3|COMMAND:RECEIVE
CABINET:3|COMMAND:RETURN
```

## Status

Topic: `/cabinet/{controllerId}/{cabinetNumber}/status`

The controller publishes `open` only after `DOOR_OPENED`, not after
`COMMAND_ACCEPTED`.

```json
{"transactionId":"rpi-01-20260729-120000-000001","step":1,"status":"open","mode":"receive"}
```

```json
{"transactionId":"rpi-01-20260729-120000-000001","step":1,"status":"closed","mode":"receive"}
```

Errors use the same status topic:

```json
{"transactionId":"rpi-01-20260729-120000-000001","step":1,"status":"error","detail":"device_error","reason":"DOOR_ALREADY_OPEN"}
```

| Source | `detail` | `reason` |
| --- | --- | --- |
| RFCOMM open/write/disconnect failure | `connection_failed` | omitted |
| No Arduino response | `communication_timeout` | omitted |
| `OPEN_TIMEOUT` | `open_timeout` | omitted |
| `DOOR_OPEN_TOO_LONG` | `close_timeout` | omitted |
| `COMMAND_REJECTED` | `device_error` | Arduino reason |
| `INVALID_COMMAND` | `device_error` | `INVALID_COMMAND` |

A `BUSY`, `DOOR_ALREADY_OPEN`, or wrong-cabinet rejection indicates that the
controller cannot prove a safe physical state and therefore enters `FAULT`.

A close timeout does not release the RFID input. The controller remains in
`WAITING_CLOSED` until a real `DOOR_CLOSED` arrives.

## Complete

Topic: `/cabinet/{controllerId}/complete`

```json
{"transactionId":"rpi-01-20260729-120000-000001"}
```

The controller accepts this only in `WAITING_SERVER`. It ignores `complete`
while a cabinet is accepting, opening, or waiting to close.

## Startup status check

The controller sends this command to every configured cabinet at startup:

```text
CABINET:3|COMMAND:STATUS
```

A cabinet replies with its current physical state:

```text
CABINET:3|MODE:NONE|EVENT:STATUS|STATE:CLOSED
CABINET:3|MODE:NONE|EVENT:STATUS|STATE:OPEN
```

RFID input is enabled only after every cabinet reports `CLOSED`. An open door,
missing response, transport failure, or a cabinet number that does not match
the RFCOMM mapping moves the controller to `FAULT`.

## State and duplicate rules

```text
STARTING
  -> IDLE
  -> WAITING_SERVER
  -> WAITING_ACCEPTED
  -> WAITING_OPENED
  -> WAITING_CLOSED
  -> WAITING_SERVER (repeat for each cabinet)
  -> IDLE (only after complete)
```

Only one transaction and one cabinet operation can be active. While a
transaction is active, all additional RFID scans are read and discarded.

For a matching transaction:

- `step <= lastExecutedStep` is a past or duplicate command and is ignored.
- `step == lastExecutedStep + 1` is the only executable command.
- a larger step is out of order and is ignored.
- all commands for another `transactionId` are ignored.
- all open commands received outside `WAITING_SERVER` are ignored.

The controller never automatically leaves `FAULT`. Inspect the cabinet,
ensure every door is closed, correct the connection or configuration problem,
and restart the service.
