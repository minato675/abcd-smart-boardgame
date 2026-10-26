from __future__ import annotations

import json
import time
import unittest
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from uuid import uuid4

import numpy as np

from wakeword_module.audio import FakeAudioSource
from wakeword_module.audio import ExclusiveResourceLocks, ResourceBusyError
from wakeword_module.config import load_config
from wakeword_module.coordinator import WakeWordModule
from wakeword_module.detector import DetectionStateMachine
from wakeword_module.engine import EnginePrediction
from wakeword_module.mqtt import CommandMessage, MemoryPublisher, MqttAdapter, WakeTopics
from wakeword_module.worker import InferenceWorker


class FakeMqttClient:
    def __init__(self):
        self.subscriptions = []
        self.publications = []
        self.mid = 0
        self.on_connect = None
        self.on_message = None
        self.on_disconnect = None
        self.on_subscribe = None
        self.on_publish = None

    def subscribe(self, values):
        self.subscriptions.append(values)
        return 0, 1

    def publish(self, topic, payload, qos, retain):
        self.mid += 1
        self.publications.append((topic, payload, qos, retain))
        return SimpleNamespace(mid=self.mid)


class FakeEngine:
    def reset_and_warm(self, frames):
        pass

    def reset(self):
        pass

    def predict(self, frame):
        return EnginePrediction({"ssafiya": 0.9, "nae_teon_kkeutnasseo": 0.0})


class MqttTests(unittest.TestCase):
    def test_exact_topics_and_callback_queue(self):
        config = load_config("config/development.yaml")
        client = FakeMqttClient()
        adapter = MqttAdapter(config=config.mqtt, topics=WakeTopics(config.room_number), client=client)
        adapter._on_connect(client, None, {}, 0, None)
        adapter._on_subscribe(client, None, 1, [0], None)
        self.assertTrue(adapter.connected)
        subscribed = [topic for topic, qos in client.subscriptions[0]]
        self.assertEqual(subscribed, [
            "/room/A402/wake/start-listen",
            "/room/A402/wake/stop-listen",
            "/room/A402/wake/request-status",
        ])
        message = SimpleNamespace(topic=subscribed[0], payload=b"{}", retain=False, qos=1)
        adapter._on_message(client, None, message)
        self.assertEqual(len(adapter.poll_commands()), 1)
        adapter._on_message(client, None, SimpleNamespace(topic=subscribed[0], payload=b"{}", retain=True, qos=1))
        self.assertEqual(adapter.metrics["retained_command"], 1)

    def test_room_and_device_locks_are_independent(self):
        with TemporaryDirectory() as directory:
            first = ExclusiveResourceLocks(directory, "A402", "physical-device")
            second = ExclusiveResourceLocks(directory, "A402", "physical-device")
            first.acquire()
            with self.assertRaises(ResourceBusyError):
                second.acquire()
            first.release()


class CoordinatorTests(unittest.TestCase):
    def test_legacy_detection_rearms_when_configured(self):
        base = load_config("config/development.yaml")
        config = replace(base, continue_listening_after_detection=True)
        worker = InferenceWorker(FakeEngine(), DetectionStateMachine(config.model_by_id), warmup_frames=25)
        audio = FakeAudioSource()
        publisher = MemoryPublisher()
        module = WakeWordModule(config, worker=worker, audio_source=audio, publisher=publisher)
        module.start()
        module.handle_message(CommandMessage(module.topics.start_listen, b"{}", False, 1))
        for _ in range(100):
            module.process_pending()
            if module.state.value == "listening":
                break
            time.sleep(0.002)
        self.assertEqual(module.state.value, "listening")

        self.assertTrue(audio.push(np.zeros(1280, dtype=np.int16).tobytes(), first_sample_index=0, callback_monotonic_ns=time.monotonic_ns()))
        for _ in range(200):
            time.sleep(0.002)
            module.process_pending()
            statuses = [json.loads(item.payload)["status"] for item in publisher.published]
            if "call" in statuses and module.state.value == "listening":
                break
        statuses = [json.loads(item.payload)["status"] for item in publisher.published]
        self.assertIn("call", statuses)
        self.assertEqual(statuses[-1], "listening")
        self.assertEqual(module.state.value, "listening")

        module.handle_message(CommandMessage(module.topics.stop_listen, b"\n", False, 1))
        self.assertEqual(module.state.value, "idle")
        module.shutdown()

    def test_legacy_start_detect_latch_and_stop(self):
        config = load_config("config/development.yaml")
        worker = InferenceWorker(FakeEngine(), DetectionStateMachine(config.model_by_id), warmup_frames=25)
        audio = FakeAudioSource()
        publisher = MemoryPublisher()
        module = WakeWordModule(config, worker=worker, audio_source=audio, publisher=publisher)
        module.start()
        module.handle_message(CommandMessage(module.topics.start_listen, b"{}", False, 1))
        for _ in range(100):
            module.process_pending()
            if module.state.value == "listening":
                break
            time.sleep(0.002)
        self.assertEqual(module.state.value, "listening")
        self.assertTrue(audio.push(np.zeros(1280, dtype=np.int16).tobytes(), first_sample_index=0, callback_monotonic_ns=time.monotonic_ns()))
        for _ in range(100):
            time.sleep(0.002)
            module.process_pending()
            if module.state.value == "latched_call":
                break
        self.assertEqual(module.state.value, "latched_call")
        self.assertEqual([json.loads(item.payload)["status"] for item in publisher.published], ["idle", "listening", "call"])
        module.handle_message(CommandMessage(module.topics.stop_listen, b"\n", False, 1))
        self.assertEqual(module.state.value, "idle")
        self.assertEqual(json.loads(publisher.published[-1].payload)["status"], "idle")
        module.shutdown()

    def test_broker_loss_requires_fresh_start(self):
        config = load_config("config/development.yaml")
        worker = InferenceWorker(FakeEngine(), DetectionStateMachine(config.model_by_id))
        audio = FakeAudioSource()
        module = WakeWordModule(config, worker=worker, audio_source=audio, publisher=MemoryPublisher())
        module.start()
        module.handle_message(CommandMessage(module.topics.start_listen, b"{}", False, 1))
        for _ in range(100):
            module.process_pending()
            if module.state.value == "listening":
                break
            time.sleep(0.002)
        module.set_broker_connected(False)
        self.assertEqual(module.state.value, "paused_disconnected")
        module.set_broker_connected(True)
        self.assertEqual(module.state.value, "idle")
        module.shutdown()

    def test_v2_identity_latch_ack_and_cached_conflict(self):
        base = load_config("config/development.yaml")
        with TemporaryDirectory() as directory:
            epoch = uuid4()
            state_path = Path(directory) / "state.sqlite"
            config = replace(
                base,
                mqtt=replace(base.mqtt, contract_version="v2", clean_session=False),
                runtime=replace(base.runtime, controller_epoch=epoch, state_store_path=state_path),
            )
            worker = InferenceWorker(FakeEngine(), DetectionStateMachine(config.model_by_id), warmup_frames=25)
            audio = FakeAudioSource()
            publisher = MemoryPublisher()
            from wakeword_module.store import DurableStateStore

            store = DurableStateStore(state_path, device_id=config.device_id, controller_epoch=epoch)
            module = WakeWordModule(config, worker=worker, audio_source=audio, publisher=publisher, store=store)
            module.start()

            now = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
            session_id = uuid4()
            start_id = uuid4()
            start_body = json.dumps(
                {
                    "contractVersion": 2,
                    "commandId": str(start_id),
                    "controllerEpoch": str(epoch),
                    "commandSequence": 0,
                    "listenSessionId": str(session_id),
                    "issuedAt": now,
                },
                separators=(",", ":"),
            ).encode()
            module.handle_message(CommandMessage(module.topics.start_listen, start_body, False, 1))
            for _ in range(100):
                module.process_pending()
                if module.state.value == "listening":
                    break
                time.sleep(0.002)
            self.assertEqual(module.state.value, "listening")

            accepted = [
                json.loads(publication.payload)
                for publication in publisher.published
                if json.loads(publication.payload).get("commandId") == str(start_id)
            ]
            self.assertEqual(accepted[-1]["outcome"], "accepted")
            accepted_payload = publisher.published[[
                json.loads(publication.payload).get("commandId") == str(start_id)
                for publication in publisher.published
            ].index(True)].payload

            # An exact retry is an exact byte replay, while a body mutation
            # under the same command ID gets a new correlated id_conflict.
            module.handle_message(CommandMessage(module.topics.start_listen, start_body, False, 1))
            self.assertIn(accepted_payload, [publication.payload for publication in publisher.published])
            conflict = json.loads(start_body.decode().replace(str(session_id), str(uuid4())))
            conflict_body = json.dumps(conflict, separators=(",", ":")).encode()
            module.handle_message(CommandMessage(module.topics.start_listen, conflict_body, False, 1))
            self.assertEqual(json.loads(publisher.published[-1].payload)["reasonCode"], "id_conflict")

            self.assertTrue(audio.push(np.zeros(1280, dtype=np.int16).tobytes(), first_sample_index=0, callback_monotonic_ns=time.monotonic_ns()))
            for _ in range(100):
                time.sleep(0.002)
                module.process_pending()
                if module.state.value == "latched_call":
                    break
            self.assertEqual(module.state.value, "latched_call")
            latch = store.restore_latch()
            self.assertIsNotNone(latch)
            detection_payloads = [
                publication.payload
                for publication in publisher.published
                if json.loads(publication.payload).get("status") == "call"
            ]
            self.assertEqual(len(detection_payloads), 1)
            self.assertFalse(latch.application_acked)

            blocked_id = uuid4()
            blocked_session = uuid4()
            blocked_body = json.dumps(
                {
                    "contractVersion": 2,
                    "commandId": str(blocked_id),
                    "controllerEpoch": str(epoch),
                    "commandSequence": 1,
                    "listenSessionId": str(blocked_session),
                    "issuedAt": now,
                },
                separators=(",", ":"),
            ).encode()
            module.handle_message(CommandMessage(module.topics.start_listen, blocked_body, False, 1))
            self.assertEqual(json.loads(publisher.published[-1].payload)["reasonCode"], "event_unacknowledged")

            ack_body = json.dumps(
                {
                    "contractVersion": 2,
                    "ackId": str(uuid4()),
                    "eventId": str(latch.event_id),
                    "listenSessionId": str(latch.listen_session_id),
                    "receivedAt": now,
                },
                separators=(",", ":"),
            ).encode()
            module.handle_message(CommandMessage(module.topics.ack, ack_body, False, 1))
            self.assertTrue(store.restore_latch().application_acked)

            stop_id = uuid4()
            stop_body = json.dumps(
                {
                    "contractVersion": 2,
                    "commandId": str(stop_id),
                    "controllerEpoch": str(epoch),
                    "commandSequence": 2,
                    "listenSessionId": str(latch.listen_session_id),
                    "issuedAt": now,
                },
                separators=(",", ":"),
            ).encode()
            module.handle_message(CommandMessage(module.topics.stop_listen, stop_body, False, 1))
            self.assertEqual(module.state.value, "idle")
            self.assertIsNone(store.restore_latch())
            self.assertEqual(json.loads(publisher.published[-1].payload)["outcome"], "accepted")
            module.shutdown()


if __name__ == "__main__":
    unittest.main()
