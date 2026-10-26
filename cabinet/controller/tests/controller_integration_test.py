#!/usr/bin/env python3
"""End-to-end controller test using PTYs and a loopback MQTT broker."""

from __future__ import annotations

import json
import os
import pty
import select
import signal
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import BinaryIO


class TestFailure(RuntimeError):
    pass


class LineReader:
    def __init__(self) -> None:
        self._buffers: dict[int, bytearray] = {}

    def read_fd(self, descriptor: int, timeout: float = 3.0) -> str:
        buffer = self._buffers.setdefault(descriptor, bytearray())
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            for delimiter in (b"\n", b"\r"):
                if delimiter in buffer:
                    index = buffer.index(delimiter)
                    line = bytes(buffer[:index])
                    del buffer[: index + 1]
                    while buffer[:1] in (b"\n", b"\r"):
                        del buffer[:1]
                    if line:
                        return line.decode("ascii")
            ready, _, _ = select.select(
                [descriptor], [], [], max(0.0, deadline - time.monotonic())
            )
            if not ready:
                break
            try:
                chunk = os.read(descriptor, 4096)
            except OSError as error:
                raise TestFailure(f"PTY read failed: {error}") from error
            if not chunk:
                raise TestFailure("PTY closed before a complete line arrived")
            buffer.extend(chunk)
        raise TestFailure("timed out waiting for a PTY line")


class MqttSubscriber:
    def __init__(self, process: subprocess.Popen[bytes]) -> None:
        self.process = process
        self.pending: list[tuple[str, dict[str, object]]] = []

    def _read_one(self, timeout: float) -> tuple[str, dict[str, object]]:
        if self.process.stdout is None:
            raise TestFailure("subscriber stdout is unavailable")
        ready, _, _ = select.select([self.process.stdout], [], [], timeout)
        if not ready:
            raise TestFailure("timed out waiting for MQTT message")
        raw = self.process.stdout.readline()
        if not raw:
            raise TestFailure("MQTT subscriber exited unexpectedly")
        topic, separator, payload = raw.decode("utf-8").strip().partition(" ")
        if not separator:
            raise TestFailure(f"malformed subscriber output: {raw!r}")
        try:
            decoded = json.loads(payload)
        except json.JSONDecodeError as error:
            raise TestFailure(f"invalid JSON from controller: {payload}") from error
        if not isinstance(decoded, dict):
            raise TestFailure("controller MQTT payload was not an object")
        return topic, decoded

    def wait_for(
        self,
        topic: str,
        field: tuple[str, object] | None = None,
        timeout: float = 3.0,
    ) -> dict[str, object]:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            for index, (queued_topic, payload) in enumerate(self.pending):
                if queued_topic == topic and (
                    field is None or payload.get(field[0]) == field[1]
                ):
                    del self.pending[index]
                    return payload
            message = self._read_one(max(0.0, deadline - time.monotonic()))
            if message[0] == topic and (
                field is None or message[1].get(field[0]) == field[1]
            ):
                return message[1]
            self.pending.append(message)
        raise TestFailure(f"timed out waiting for MQTT topic {topic}")


def reserve_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
        listener.bind(("127.0.0.1", 0))
        return int(listener.getsockname()[1])


def wait_for_broker(process: subprocess.Popen[bytes], port: int) -> None:
    deadline = time.monotonic() + 3.0
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise TestFailure("MQTT broker exited during startup")
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.1):
                return
        except OSError:
            time.sleep(0.02)
    raise TestFailure("MQTT broker did not start")


def publish(
    executable: str, port: int, topic: str, payload: dict[str, object]
) -> None:
    subprocess.run(
        [
            executable,
            "-h",
            "127.0.0.1",
            "-p",
            str(port),
            "-q",
            "1",
            "-t",
            topic,
            "-m",
            json.dumps(payload, separators=(",", ":")),
        ],
        check=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
        timeout=3,
    )


def send_arduino(descriptor: int, cabinet: int, mode: str, event: str) -> None:
    message = f"CABINET:{cabinet}|MODE:{mode}|EVENT:{event}\r\n"
    os.write(descriptor, message.encode("ascii"))


def terminate(process: subprocess.Popen[bytes] | None) -> None:
    if process is None or process.poll() is not None:
        return
    process.terminate()
    try:
        process.wait(timeout=2)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=2)


def run_test(
    controller_executable: str,
    broker_executable: str,
    publisher_executable: str,
    subscriber_executable: str,
    log_file: BinaryIO,
    temporary_directory: str,
) -> None:
    port = reserve_port()
    broker: subprocess.Popen[bytes] | None = None
    subscriber_process: subprocess.Popen[bytes] | None = None
    controller: subprocess.Popen[bytes] | None = None
    descriptors: list[int] = []
    try:
        broker = subprocess.Popen(
            [broker_executable, "-p", str(port)],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        wait_for_broker(broker, port)

        subscriber_process = subprocess.Popen(
            [
                subscriber_executable,
                "-h",
                "127.0.0.1",
                "-p",
                str(port),
                "-q",
                "1",
                "-v",
                "-t",
                "/cabinet/integration/#",
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            bufsize=0,
        )
        subscriber = MqttSubscriber(subscriber_process)
        time.sleep(0.1)

        rfid_master, rfid_slave = pty.openpty()
        cabinet_one_master, cabinet_one_slave = pty.openpty()
        cabinet_two_master, cabinet_two_slave = pty.openpty()
        descriptors.extend(
            [
                rfid_master,
                rfid_slave,
                cabinet_one_master,
                cabinet_one_slave,
                cabinet_two_master,
                cabinet_two_slave,
            ]
        )
        config_path = Path(temporary_directory) / "controller.conf"
        config_path.write_text(
            "\n".join(
                [
                    "controller_id=integration",
                    "mqtt_host=127.0.0.1",
                    f"mqtt_port={port}",
                    f"rfid_device={os.ttyname(rfid_slave)}",
                    f"cabinet.1={os.ttyname(cabinet_one_slave)}",
                    f"cabinet.2={os.ttyname(cabinet_two_slave)}",
                    "command_ack_timeout_ms=1000",
                    "communication_timeout_ms=2000",
                    "server_timeout_ms=3000",
                    "",
                ]
            ),
            encoding="utf-8",
        )

        controller = subprocess.Popen(
            [controller_executable, "--config", str(config_path)],
            stdout=log_file,
            stderr=log_file,
        )
        reader = LineReader()
        if reader.read_fd(cabinet_one_master) != "CABINET:1|COMMAND:STATUS":
            raise TestFailure("cabinet 1 did not receive STATUS")
        if reader.read_fd(cabinet_two_master) != "CABINET:2|COMMAND:STATUS":
            raise TestFailure("cabinet 2 did not receive STATUS")
        send_arduino(cabinet_one_master, 1, "NONE", "STATUS|STATE:CLOSED")
        send_arduino(cabinet_two_master, 2, "NONE", "STATUS|STATE:CLOSED")

        time.sleep(0.1)
        os.write(rfid_master, b"04A12B34CD\r\n")
        card = subscriber.wait_for("/cabinet/integration/card")
        if card.get("cardUid") != "04A12B34CD":
            raise TestFailure("controller published the wrong card UID")
        transaction_id = card.get("transactionId")
        if not isinstance(transaction_id, str) or not transaction_id:
            raise TestFailure("controller did not publish a transaction id")

        publish(
            publisher_executable,
            port,
            "/cabinet/integration/1/open",
            {"transactionId": transaction_id, "step": 1, "mode": "receive"},
        )
        if reader.read_fd(cabinet_one_master) != "CABINET:1|COMMAND:RECEIVE":
            raise TestFailure("cabinet 1 did not receive RECEIVE")
        send_arduino(cabinet_one_master, 1, "RECEIVE", "COMMAND_ACCEPTED")
        send_arduino(cabinet_one_master, 1, "RECEIVE", "DOOR_OPENED")
        send_arduino(cabinet_one_master, 1, "RECEIVE", "DOOR_CLOSED")
        status_topic = "/cabinet/integration/1/status"
        subscriber.wait_for(status_topic, ("status", "open"))
        subscriber.wait_for(status_topic, ("status", "closed"))

        publish(
            publisher_executable,
            port,
            "/cabinet/integration/2/open",
            {"transactionId": transaction_id, "step": 2, "mode": "return"},
        )
        if reader.read_fd(cabinet_two_master) != "CABINET:2|COMMAND:RETURN":
            raise TestFailure("cabinet 2 did not receive RETURN")
        send_arduino(cabinet_two_master, 2, "RETURN", "COMMAND_ACCEPTED")
        send_arduino(cabinet_two_master, 2, "RETURN", "DOOR_OPENED")
        send_arduino(cabinet_two_master, 2, "RETURN", "DOOR_CLOSED")
        status_topic = "/cabinet/integration/2/status"
        subscriber.wait_for(status_topic, ("status", "open"))
        subscriber.wait_for(status_topic, ("status", "closed"))

        publish(
            publisher_executable,
            port,
            "/cabinet/integration/complete",
            {"transactionId": transaction_id},
        )
        time.sleep(0.1)
        os.write(rfid_master, b"0000000001\r\n")
        next_card = subscriber.wait_for("/cabinet/integration/card")
        if next_card.get("cardUid") != "0000000001":
            raise TestFailure("controller did not unlock RFID after complete")
        if next_card.get("transactionId") == transaction_id:
            raise TestFailure("controller reused a transaction id")
        if controller.poll() is not None:
            raise TestFailure("controller exited during the integration flow")
    finally:
        if controller is not None and controller.poll() is None:
            controller.send_signal(signal.SIGTERM)
            try:
                controller.wait(timeout=2)
            except subprocess.TimeoutExpired:
                controller.kill()
                controller.wait(timeout=2)
        terminate(subscriber_process)
        terminate(broker)
        for descriptor in descriptors:
            try:
                os.close(descriptor)
            except OSError:
                pass


def main() -> int:
    if len(sys.argv) != 5:
        print(
            "usage: controller_integration_test.py CONTROLLER MOSQUITTO PUB SUB",
            file=sys.stderr,
        )
        return 2
    with tempfile.TemporaryDirectory(prefix="cabinet-integration-") as directory:
        with tempfile.TemporaryFile(mode="w+b") as log_file:
            try:
                run_test(*sys.argv[1:], log_file, directory)
            except Exception as error:
                log_file.seek(0)
                logs = log_file.read().decode("utf-8", errors="replace")
                print(f"integration test failed: {error}", file=sys.stderr)
                if logs:
                    print("controller log:\n" + logs, file=sys.stderr)
                return 1
    print("controller integration test passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
