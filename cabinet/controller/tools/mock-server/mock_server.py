#!/usr/bin/env python3
"""Drive a fixed return-then-receive cabinet flow over MQTT."""

from __future__ import annotations

import argparse
import json
import select
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class Publication:
    topic: str
    payload: dict[str, Any]


class MockWorkflow:
    """Pure state machine for one return/receive transaction."""

    def __init__(
        self,
        controller_id: str,
        return_cabinet: int,
        receive_cabinet: int,
        delay_seconds: float = 1.0,
    ):
        if not controller_id or "/" in controller_id:
            raise ValueError("controller_id must be a non-empty MQTT topic segment")
        if return_cabinet <= 0 or receive_cabinet <= 0:
            raise ValueError("cabinet numbers must be positive")
        if delay_seconds < 0:
            raise ValueError("delay_seconds cannot be negative")
        self.controller_id = controller_id
        self.return_cabinet = return_cabinet
        self.receive_cabinet = receive_cabinet
        self.delay_seconds = delay_seconds
        self.state = "idle"
        self.transaction_id: str | None = None
        self.last_transaction_id: str | None = None
        self.receive_due: float | None = None

    @property
    def card_topic(self) -> str:
        return f"/cabinet/{self.controller_id}/card"

    def status_topic(self, cabinet: int) -> str:
        return f"/cabinet/{self.controller_id}/{cabinet}/status"

    def open_topic(self, cabinet: int) -> str:
        return f"/cabinet/{self.controller_id}/{cabinet}/open"

    @property
    def status_topics(self) -> tuple[str, ...]:
        topics = {
            self.status_topic(self.return_cabinet),
            self.status_topic(self.receive_cabinet),
        }
        return tuple(sorted(topics))

    @property
    def complete_topic(self) -> str:
        return f"/cabinet/{self.controller_id}/complete"

    def _open(self, cabinet: int, step: int, mode: str) -> Publication:
        assert self.transaction_id is not None
        return Publication(
            self.open_topic(cabinet),
            {"transactionId": self.transaction_id, "step": step, "mode": mode},
        )

    def handle_message(self, topic: str, payload_text: str, now: float) -> list[Publication]:
        try:
            payload = json.loads(payload_text)
        except json.JSONDecodeError as error:
            raise ValueError(f"invalid JSON on {topic}: {error.msg}") from error
        if not isinstance(payload, dict):
            raise ValueError(f"payload on {topic} must be a JSON object")

        if topic == self.card_topic:
            return self._handle_card(payload)
        if topic in self.status_topics:
            return self._handle_status(topic, payload, now)
        return []

    def _handle_card(self, payload: dict[str, Any]) -> list[Publication]:
        transaction_id = payload.get("transactionId")
        card_uid = payload.get("cardUid")
        if not isinstance(transaction_id, str) or not transaction_id:
            raise ValueError("card event requires a non-empty transactionId")
        if not isinstance(card_uid, str) or not card_uid:
            raise ValueError("card event requires a non-empty cardUid")
        if transaction_id == self.last_transaction_id:
            return []
        if self.state != "idle":
            return []

        self.transaction_id = transaction_id
        self.state = "returning"
        return [self._open(self.return_cabinet, 1, "return")]

    def _handle_status(
        self,
        topic: str,
        payload: dict[str, Any],
        now: float,
    ) -> list[Publication]:
        if self.transaction_id is None:
            return []
        if payload.get("transactionId") != self.transaction_id:
            return []
        step = payload.get("step")
        status = payload.get("status")

        if (
            self.state == "returning"
            and topic == self.status_topic(self.return_cabinet)
            and step == 1
            and status == "closed"
        ):
            self.state = "waiting_receive"
            self.receive_due = now + self.delay_seconds
            return []
        if (
            self.state == "receiving"
            and topic == self.status_topic(self.receive_cabinet)
            and step == 2
            and status == "closed"
        ):
            publication = Publication(
                self.complete_topic,
                {"transactionId": self.transaction_id},
            )
            self.last_transaction_id = self.transaction_id
            self.transaction_id = None
            self.receive_due = None
            self.state = "idle"
            return [publication]
        return []

    def poll(self, now: float) -> list[Publication]:
        if (
            self.state == "waiting_receive"
            and self.receive_due is not None
            and now >= self.receive_due
        ):
            self.receive_due = None
            self.state = "receiving"
            return [self._open(self.receive_cabinet, 2, "receive")]
        return []

    def next_timeout(self, now: float) -> float | None:
        if self.receive_due is None:
            return None
        return max(0.0, self.receive_due - now)


def mqtt_connection_args(arguments: argparse.Namespace) -> list[str]:
    result = ["-h", arguments.host, "-p", str(arguments.port)]
    if arguments.username:
        result.extend(["-u", arguments.username])
    if arguments.password:
        result.extend(["-P", arguments.password])
    return result


def publish(arguments: argparse.Namespace, publication: Publication) -> None:
    command = [
        "mosquitto_pub",
        *mqtt_connection_args(arguments),
        "-q",
        "1",
        "-t",
        publication.topic,
        "-m",
        json.dumps(publication.payload, separators=(",", ":")),
    ]
    subprocess.run(command, check=True)
    print(f"published {publication.topic}: {publication.payload}", flush=True)


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=1883)
    parser.add_argument("--controller-id", default="rpi-01")
    parser.add_argument("--return-cabinet", type=int, default=1)
    parser.add_argument("--receive-cabinet", type=int, default=2)
    parser.add_argument("--delay-seconds", type=float, default=1.0)
    parser.add_argument("--username", default="")
    parser.add_argument("--password", default="")
    return parser.parse_args()


def run(arguments: argparse.Namespace) -> int:
    for executable in ("mosquitto_sub", "mosquitto_pub"):
        if shutil.which(executable) is None:
            raise RuntimeError(f"required executable is missing: {executable}")

    workflow = MockWorkflow(
        arguments.controller_id,
        arguments.return_cabinet,
        arguments.receive_cabinet,
        arguments.delay_seconds,
    )
    subscribe_command = [
        "mosquitto_sub",
        *mqtt_connection_args(arguments),
        "-q",
        "1",
        "-F",
        "%t\t%p",
        "-t",
        workflow.card_topic,
    ]
    for status_topic in workflow.status_topics:
        subscribe_command.extend(["-t", status_topic])
    subscriber = subprocess.Popen(
        subscribe_command,
        stdout=subprocess.PIPE,
        text=True,
        bufsize=1,
    )
    assert subscriber.stdout is not None
    print(
        f"mock server listening for controller {arguments.controller_id}, "
        f"return cabinet {arguments.return_cabinet}, "
        f"receive cabinet {arguments.receive_cabinet}",
        flush=True,
    )

    try:
        while subscriber.poll() is None:
            now = time.monotonic()
            for publication in workflow.poll(now):
                publish(arguments, publication)
            readable, _, _ = select.select(
                [subscriber.stdout],
                [],
                [],
                workflow.next_timeout(time.monotonic()),
            )
            if not readable:
                continue
            line = subscriber.stdout.readline()
            if not line:
                break
            try:
                topic, payload = line.rstrip("\n").split("\t", 1)
                publications = workflow.handle_message(topic, payload, time.monotonic())
            except ValueError as error:
                print(f"ignored message: {error}", file=sys.stderr, flush=True)
                continue
            for publication in publications:
                publish(arguments, publication)
    except KeyboardInterrupt:
        pass
    finally:
        subscriber.terminate()
        try:
            subscriber.wait(timeout=2)
        except subprocess.TimeoutExpired:
            subscriber.kill()
            subscriber.wait()
    if subscriber.returncode not in (None, 0, -15):
        raise RuntimeError(f"mosquitto_sub exited with status {subscriber.returncode}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(run(parse_arguments()))
    except (OSError, RuntimeError, subprocess.CalledProcessError) as error:
        print(f"mock server error: {error}", file=sys.stderr)
        raise SystemExit(1) from error
