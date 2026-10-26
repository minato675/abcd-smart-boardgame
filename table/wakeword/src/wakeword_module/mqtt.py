"""MQTT topics, bounded callback parsing, and the Paho network boundary."""

from __future__ import annotations

from dataclasses import dataclass
import queue
import os
import threading
import time
from typing import Any, Callable, Protocol

from .config import MqttConfig
from .contracts import (
    ContractError,
    MAX_MQTT_PAYLOAD_BYTES,
    parse_legacy_command,
    parse_v2_ack,
    parse_v2_command,
)


class MqttError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class WakeTopics:
    room_number: str

    def __post_init__(self) -> None:
        if not self.room_number or any(char in self.room_number for char in "/+#\x00") or any(ord(char) < 32 for char in self.room_number):
            raise ValueError("room number cannot be used in MQTT topics")
        if len(self.room_number.encode("utf-8")) > 65500:
            raise ValueError("room number produces oversized MQTT topics")

    @property
    def prefix(self) -> str:
        return f"/room/{self.room_number}/wake"

    @property
    def start_listen(self) -> str:
        return f"{self.prefix}/start-listen"

    @property
    def stop_listen(self) -> str:
        return f"{self.prefix}/stop-listen"

    @property
    def request_status(self) -> str:
        return f"{self.prefix}/request-status"

    @property
    def status(self) -> str:
        return f"{self.prefix}/status"

    @property
    def ack(self) -> str:
        return f"{self.prefix}/ack"

    def command_topics(self, *, contract_version: str = "legacy") -> tuple[str, ...]:
        values = (self.start_listen, self.stop_listen, self.request_status)
        return values + ((self.ack,) if contract_version == "v2" else ())


@dataclass(frozen=True, slots=True)
class CommandMessage:
    topic: str
    payload: bytes
    retained: bool
    qos: int


@dataclass(frozen=True, slots=True)
class Publication:
    topic: str
    payload: bytes
    qos: int = 1
    retain: bool = False
    logical_key: str | None = None


class Publisher(Protocol):
    def offer(self, publication: Publication) -> bool: ...
    def wake_outbox_dispatcher(self) -> None: ...


class MqttAdapter:
    """Paho adapter; callbacks only validate/enqueue immutable small messages."""

    def __init__(
        self,
        *,
        config: MqttConfig,
        topics: WakeTopics,
        contract_version: str = "legacy",
        client: Any | None = None,
        command_queue_size: int = 128,
        publish_queue_size: int = 128,
        logger: Callable[[str, dict[str, Any]], None] | None = None,
    ) -> None:
        self.config = config
        self.topics = topics
        self.contract_version = contract_version
        self._client = client
        self._commands: queue.Queue[CommandMessage] = queue.Queue(maxsize=command_queue_size)
        self._publications: queue.Queue[Publication] = queue.Queue(maxsize=publish_queue_size)
        self._logger = logger
        self._publisher_thread: threading.Thread | None = None
        self._stop_publisher = threading.Event()
        self._connected = False
        self._subscribed = False
        self._puback_lock = threading.Lock()
        self._pending_pubacks: dict[int, str] = {}
        self._puback_listener: Callable[[str], None] | None = None
        self.metrics: dict[str, int] = {
            "invalid_command": 0,
            "retained_command": 0,
            "command_queue_full": 0,
            "publish_queue_full": 0,
            "publish_error": 0,
        }
        if self._client is None:
            try:
                import paho.mqtt.client as mqtt
            except ImportError as exc:
                raise MqttError("paho-mqtt is not installed") from exc
            callback_api = getattr(mqtt, "CallbackAPIVersion", None)
            protocol = getattr(mqtt, "MQTTv311", 4)
            if callback_api is not None:
                self._client = mqtt.Client(
                    callback_api.VERSION2,
                    client_id=config.client_id,
                    protocol=protocol,
                    clean_session=config.clean_session,
                )
            else:
                self._client = mqtt.Client(
                    client_id=config.client_id,
                    protocol=protocol,
                    clean_session=config.clean_session,
                )
        self._client.on_connect = self._on_connect
        self._client.on_message = self._on_message
        self._client.on_disconnect = self._on_disconnect
        self._client.on_subscribe = self._on_subscribe
        self._client.on_publish = self._on_publish

    @property
    def connected(self) -> bool:
        return self._connected and self._subscribed

    @property
    def client(self) -> Any:
        return self._client

    def _log(self, event: str, **fields: Any) -> None:
        if self._logger is not None:
            try:
                self._logger(event, fields)
            except Exception:
                pass

    def _on_connect(self, client: Any, userdata: Any, flags: Any, reason_code: Any, properties: Any = None) -> None:
        failed = bool(getattr(reason_code, "is_failure", False)) or (isinstance(reason_code, int) and reason_code != 0)
        if failed:
            self._connected = False
            self._subscribed = False
            self._log("mqtt_connect_failed")
            return
        self._connected = True
        self._subscribed = False
        self._log("mqtt_connected", mqtt_host=self.config.host, mqtt_port=self.config.port)
        topics = [(topic, 1) for topic in self.topics.command_topics(contract_version=self.contract_version)]
        result, _mid = client.subscribe(topics)
        if isinstance(result, int) and result != 0:
            self._connected = False
            self._log("mqtt_subscribe_failed", result=result)

    def _on_subscribe(self, client: Any, userdata: Any, mid: int, reason_codes: Any, properties: Any = None) -> None:
        codes = reason_codes if isinstance(reason_codes, (list, tuple)) else [reason_codes]
        failed = any(getattr(code, "is_failure", False) or (isinstance(code, int) and code >= 128) for code in codes)
        self._subscribed = not failed
        if failed:
            self._connected = False
            self._log("mqtt_subscribe_failed")
        else:
            self._log("mqtt_subscribed", result=len(codes))

    def _on_disconnect(self, client: Any, userdata: Any, disconnect_flags: Any = None, reason_code: Any = None, properties: Any = None) -> None:
        self._connected = False
        self._subscribed = False
        self._log("mqtt_disconnected")

    def register_puback_listener(self, listener: Callable[[str], None]) -> None:
        self._puback_listener = listener

    def _on_publish(self, client: Any, userdata: Any, mid: int, reason_code: Any = None, properties: Any = None) -> None:
        with self._puback_lock:
            logical_key = self._pending_pubacks.pop(int(mid), None)
        if logical_key is not None and self._puback_listener is not None:
            try:
                failed = bool(getattr(reason_code, "is_failure", False)) or (
                    isinstance(reason_code, int) and reason_code >= 128
                )
                self._puback_listener(("failed:" if failed else "") + logical_key)
            except Exception:
                pass

    def _topic_kind(self, topic: str) -> str | None:
        if topic == self.topics.start_listen:
            return "start"
        if topic == self.topics.stop_listen:
            return "stop"
        if topic == self.topics.request_status:
            return "request-status"
        if topic == self.topics.ack and self.contract_version == "v2":
            return "ack"
        return None

    def _on_message(self, client: Any, userdata: Any, message: Any) -> None:
        topic = str(message.topic)
        kind = self._topic_kind(topic)
        if kind is None:
            return
        payload = bytes(message.payload)
        retained = bool(getattr(message, "retain", False))
        qos = int(getattr(message, "qos", 0))
        if retained:
            self.metrics["retained_command"] += 1
            self._log("mqtt_retained_message_ignored", topic=topic, byte_count=len(payload))
            return
        if len(payload) > MAX_MQTT_PAYLOAD_BYTES:
            self.metrics["invalid_command"] += 1
            self._log("mqtt_invalid_command", topic=topic, byte_count=len(payload), reason="too_large")
            return
        try:
            if kind == "ack":
                if self.contract_version != "v2":
                    return
                parse_v2_ack(payload)
            elif self.contract_version == "legacy":
                parse_legacy_command(payload)
            else:
                parse_v2_command(kind, payload)
        except (ContractError, ValueError) as exc:
            self.metrics["invalid_command"] += 1
            self._log("mqtt_invalid_command", topic=topic, byte_count=len(payload), reason=str(exc))
            return
        try:
            self._commands.put_nowait(CommandMessage(topic, payload, retained, qos))
        except queue.Full:
            self.metrics["command_queue_full"] += 1
            self._log("mqtt_command_queue_full", topic=topic, byte_count=len(payload))

    def poll_commands(self, max_items: int = 32) -> list[CommandMessage]:
        messages: list[CommandMessage] = []
        for _ in range(max_items):
            try:
                messages.append(self._commands.get_nowait())
            except queue.Empty:
                break
        return messages

    def offer(self, publication: Publication) -> bool:
        if publication.qos != 1 or publication.retain:
            raise ValueError("wake status publications require QoS 1 and retain=false")
        if len(publication.payload) > MAX_MQTT_PAYLOAD_BYTES:
            raise ValueError("status payload exceeds MQTT limit")
        try:
            self._publications.put_nowait(publication)
            return True
        except queue.Full:
            self.metrics["publish_queue_full"] += 1
            return False

    def offer_legacy_status(self, payload: bytes, qos: int = 1, retain: bool = False) -> bool:
        return self.offer(Publication(self.topics.status, bytes(payload), qos=qos, retain=retain))

    def wake_outbox_dispatcher(self) -> None:
        # The durable store is authoritative; the network loop is only nudged
        # by this bounded queue in legacy mode.
        return None

    def start(self) -> None:
        try:
            reconnect_delay_set = getattr(self._client, "reconnect_delay_set", None)
            if reconnect_delay_set is not None:
                reconnect_delay_set(
                    min_delay=self.config.reconnect_min_seconds,
                    max_delay=self.config.reconnect_max_seconds,
                )
            if self.config.tls_enabled:
                self._client.tls_set(ca_certs=str(self.config.ca_cert_path) if self.config.ca_cert_path else None)
            if self.config.username_env:
                username = os.environ.get(self.config.username_env)
                password = os.environ.get(self.config.password_env) if self.config.password_env else None
                if not username:
                    raise MqttError("configured MQTT username secret is unavailable")
                self._client.username_pw_set(username, password)
            self._client.connect(self.config.host, self.config.port, self.config.keepalive_seconds)
            self._client.loop_start()
        except Exception as exc:
            raise MqttError("cannot connect to MQTT broker") from exc
        self._stop_publisher.clear()
        self._publisher_thread = threading.Thread(target=self._publish_loop, name="wakeword-mqtt-publisher", daemon=True)
        self._publisher_thread.start()

    def _publish_loop(self) -> None:
        while not self._stop_publisher.is_set():
            try:
                publication = self._publications.get(timeout=0.1)
            except queue.Empty:
                continue
            try:
                info = self._client.publish(
                    publication.topic,
                    payload=publication.payload,
                    qos=publication.qos,
                    retain=publication.retain,
                )
                result_code = getattr(info, "rc", 0) if info is not None else 0
                if isinstance(result_code, int) and result_code != 0:
                    self.metrics["publish_error"] += 1
                    self._log("mqtt_publish_error", topic=publication.topic, byte_count=len(publication.payload))
                    continue
                if publication.logical_key is not None and info is not None and hasattr(info, "mid"):
                    with self._puback_lock:
                        self._pending_pubacks[int(info.mid)] = publication.logical_key
            except Exception:
                self.metrics["publish_error"] += 1
                self._log("mqtt_publish_error", topic=publication.topic, byte_count=len(publication.payload))

    def flush(self, timeout: float = 3.0) -> bool:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            with self._puback_lock:
                pubacks_pending = bool(self._pending_pubacks)
            if self._publications.empty() and not pubacks_pending:
                return True
            time.sleep(0.01)
        return self._publications.empty()

    def stop(self, timeout: float = 3.0) -> None:
        self.flush(timeout)
        self._stop_publisher.set()
        if self._publisher_thread is not None:
            self._publisher_thread.join(timeout=timeout)
            self._publisher_thread = None
        try:
            self._client.loop_stop()
            self._client.disconnect()
        except Exception:
            pass
        self._connected = False
        self._subscribed = False


class MemoryPublisher:
    """Bounded deterministic publisher used by coordinator tests."""

    def __init__(self, maxsize: int = 128) -> None:
        self.queue: queue.Queue[Publication] = queue.Queue(maxsize=maxsize)
        self.published: list[Publication] = []
        self.connected = True
        self._puback_listener: Callable[[str], None] | None = None

    def offer(self, publication: Publication) -> bool:
        try:
            self.queue.put_nowait(publication)
        except queue.Full:
            return False
        self.published.append(publication)
        if self._puback_listener is not None and publication.logical_key is not None:
            self._puback_listener(publication.logical_key)
        return True

    def offer_legacy_status(self, payload: bytes, qos: int = 1, retain: bool = False) -> bool:
        return self.offer(Publication("/wake/status", bytes(payload), qos=qos, retain=retain))

    def wake_outbox_dispatcher(self) -> None:
        return None

    def register_puback_listener(self, listener: Callable[[str], None]) -> None:
        self._puback_listener = listener

    def clear(self) -> None:
        self.published.clear()
        while True:
            try:
                self.queue.get_nowait()
            except queue.Empty:
                break


class DurableOutboxDispatcher:
    """Poll v2 SQLite outbox rows in revision order and retry exact bytes."""

    def __init__(
        self,
        store: Any,
        publisher: Publisher,
        status_topic: str,
        *,
        publish_ack_timeout_seconds: float = 3.0,
        monotonic: Callable[[], float] = time.monotonic,
    ) -> None:
        self.store = store
        self.publisher = publisher
        self.status_topic = status_topic
        if publish_ack_timeout_seconds <= 0:
            raise ValueError("publish_ack_timeout_seconds must be positive")
        self.publish_ack_timeout_seconds = publish_ack_timeout_seconds
        self.monotonic = monotonic
        self._in_flight: dict[int, float] = {}
        # Startup is a reconnect boundary: a committed detection is retried
        # even if the previous process observed a broker PUBACK but never
        # received Spring's application acknowledgement.
        self._retry_events = True
        register = getattr(publisher, "register_puback_listener", None)
        if register is not None:
            register(self.on_puback)

    def on_puback(self, logical_key: str) -> None:
        failed = logical_key.startswith("failed:")
        if failed:
            logical_key = logical_key[len("failed:"):]
        if not logical_key.startswith("outbox:"):
            return
        try:
            outbox_id = int(logical_key.split(":", 1)[1])
        except ValueError:
            return
        self._in_flight.pop(outbox_id, None)
        if failed:
            return
        try:
            self.store.mark_broker_ack(outbox_id)
        except Exception:
            # The durable row remains pending and will be retried after store
            # recovery; no exception crosses the network callback.
            pass

    def on_reconnect(self) -> None:
        self._in_flight.clear()
        self._retry_events = True

    def dispatch(self, limit: int = 32) -> int:
        offered = 0
        now = self.monotonic()
        for item in self.store.pending_outbox(limit=limit):
            sent_at = self._in_flight.get(item.outbox_id)
            if sent_at is not None:
                if now - sent_at < self.publish_ack_timeout_seconds:
                    continue
                self._in_flight.pop(item.outbox_id, None)
            if item.broker_acked and not (self._retry_events and item.kind == "detection"):
                continue
            self._in_flight[item.outbox_id] = now
            publication = Publication(
                self.status_topic,
                item.payload,
                qos=1,
                retain=False,
                logical_key=f"outbox:{item.outbox_id}",
            )
            try:
                accepted = self.publisher.offer(publication)
            except Exception:
                accepted = False
            if accepted:
                offered += 1
            else:
                self._in_flight.pop(item.outbox_id, None)
        self._retry_events = False
        return offered
