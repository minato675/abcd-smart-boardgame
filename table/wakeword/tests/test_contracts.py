from __future__ import annotations

import json
import unittest
from uuid import uuid4

from wakeword_module.contracts import (
    ContractError,
    legacy_status_payload,
    parse_legacy_command,
    parse_v2_command,
    serialize_v2_status,
)


class ContractTests(unittest.TestCase):
    def test_legacy_empty_forms_only(self) -> None:
        for payload in (b"", b" \t\r\n", b"{}"):
            self.assertIsNone(parse_legacy_command(payload))
        for payload in (b"null", b"{\"x\":1}", b"[]", b"not-json"):
            with self.assertRaises(ContractError):
                parse_legacy_command(payload)

    def test_legacy_serializer_is_canonical(self) -> None:
        self.assertEqual(legacy_status_payload("listening"), b'{"status":"listening"}')

    def test_v2_rejects_duplicates_and_unknown_fields(self) -> None:
        value = str(uuid4())
        payload = (
            '{"contractVersion":2,"commandId":"%s","controllerEpoch":"%s",'
            '"commandSequence":1,"listenSessionId":"%s","issuedAt":"2026-08-03T00:00:00Z",'
            '"commandId":"%s"}' % (value, value, value, value)
        ).encode()
        with self.assertRaises(ContractError):
            parse_v2_command("start", payload)

    def test_v2_status_requires_fixed_invariants(self) -> None:
        with self.assertRaises(ContractError):
            serialize_v2_status({"status": "idle"})
        payload = serialize_v2_status({
            "contractVersion": 2,
            "deviceId": "wake-mic-01",
            "statusRevision": 1,
            "status": "idle",
            "listenSessionId": None,
            "eventId": None,
            "occurredAt": "2026-08-03T00:00:00Z",
            "modelId": None,
            "modelSha256": None,
            "confidence": None,
            "configRevision": "sha256:x",
            "commandId": str(uuid4()),
            "requestId": None,
            "outcome": "accepted",
            "reasonCode": None,
        })
        self.assertEqual(json.loads(payload), json.loads(payload))


if __name__ == "__main__":
    unittest.main()
