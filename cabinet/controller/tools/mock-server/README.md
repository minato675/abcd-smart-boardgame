# Cabinet MQTT mock server

This development-only process turns each RFID card transaction into a fixed
two-step cabinet flow:

```text
card -> cabinet 1 return -> closed -> wait 1 second -> cabinet 2 receive -> closed -> complete
```

It uses the local `mosquitto_sub` and `mosquitto_pub` command-line clients, so
no Python packages are required. Start it with:

```sh
python3 mock_server.py \
  --host 127.0.0.1 \
  --controller-id rpi-01 \
  --return-cabinet 1 \
  --receive-cabinet 2
```

The two cabinet numbers may be equal when testing with a single physical unit.

Optional `--username` and `--password` arguments are available for a broker
that requires authentication. Published commands use QoS 1 and do not set the
retain flag.

Run its focused test directly with:

```sh
python3 test_mock_server.py
```

This mock is intentionally single-transaction and is not a production server.
