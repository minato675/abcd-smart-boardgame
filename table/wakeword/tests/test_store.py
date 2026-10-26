from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from uuid import uuid4

from wakeword_module.store import DurableStateStore


class StoreTests(unittest.TestCase):
    def test_detection_latch_and_outbox_survive_restart(self) -> None:
        with TemporaryDirectory() as directory:
            path = Path(directory) / "state.sqlite"
            epoch = uuid4()
            event_id = uuid4()
            session_id = uuid4()
            store = DurableStateStore(path, device_id="wake-mic-01", controller_epoch=epoch)
            store.open()
            revision, payload = store.commit_detection(
                status="call",
                event_id=event_id,
                listen_session_id=session_id,
                model_id="ssafiya",
                model_sha256="a" * 64,
                confidence=0.9,
                occurred_at="2026-08-03T00:00:00Z",
                config_revision="sha256:test",
                payload=lambda rev: (f"revision={rev};event={event_id}").encode(),
            )
            store.close()
            store = DurableStateStore(path, device_id="wake-mic-01", controller_epoch=epoch)
            store.open()
            latch = store.restore_latch()
            self.assertEqual(latch.event_id, event_id)
            self.assertEqual(latch.status_revision, revision)
            self.assertEqual(latch.payload, payload)
            pending = store.pending_outbox()
            self.assertEqual(pending[0].payload, payload)
            self.assertFalse(pending[0].application_acked)
            store.mark_application_ack(event_id)
            self.assertTrue(store.restore_latch().application_acked)
            store.close()


if __name__ == "__main__":
    unittest.main()
