# WakeWordModule Implementation Specification

Status: implementation-ready design, production deployment blocked by model quality  
Last evidence review: 2026-08-02 (Asia/Seoul)  
Audience: the agent implementing and testing `WakeWordModule`, reviewers, and the Spring/MQTT owner

## 1. Read this first

This document defines a robust Python service that listens to one room microphone, runs the two ONNX wake-word classifiers in this directory through the openWakeWord audio frontend, and publishes the result over MQTT.

The target phrases and wire results are:

| Spoken phrase | Model ID | MQTT result |
|---|---|---|
| `싸피야` | `ssafiya` | `call` |
| `내 턴 끝났어` | `nae_teon_kkeutnasseo` | `finish` |

The implementation MAY proceed through local and shadow testing with the current models. It MUST NOT be called production-ready and MUST NOT enable production event publishing yet. Both training reports say `quality_target_met: false`, the second model has no runtime verification report, and the final quality manifest is absent.

The implementation agent must follow these rules:

1. Do not feed PCM directly to either classifier ONNX file. They accept openWakeWord embeddings with shape `[batch, 16, 96]`, not raw audio.
2. Do not pass `patience`, `threshold`, or `debounce_time` to the vendored `openwakeword.Model.predict()` method. Consume raw scores and implement decision logic in this service.
3. Do not pass the WAV paths in `test_audio/` directly to `Model.predict_clip()`. Those files are 44.1 kHz stereo, while that helper assumes 16 kHz mono PCM16 and does not convert them.
4. One inference worker must exclusively own the stateful openWakeWord model, feature buffers, and optional VAD. Never call `predict()` or reset those objects concurrently.
5. Never log, publish, or persist raw microphone audio. Evaluation recordings require a separately approved consent and retention policy.
6. A code-complete module is not a quality-complete wake-word system. Production enablement is a separate, measurable release gate in Section 17.

`MUST`, `MUST NOT`, `SHOULD`, and `MAY` are normative in this document.

## 2. Source priority and adopted decisions

Use this precedence when sources disagree:

1. A later written decision approved by both the Spring owner and the Wake Word owner.
2. The completed [Server to Room MQTT Topic Reference](https://app.notion.com/p/3ae85e9160e68183af35cb110de062b5).
3. The completed [requirements definition](https://app.notion.com/p/39c85e9160e680589036fc082c59fa7e).
4. The explicit gap-filling decisions labeled **Adopted here** in this document.
5. The older, still-draft [Wake Word microservice MVP design](https://app.notion.com/p/3ad85e9160e6801ea0e6f594252f61d0), used only for historical guidance.

The completed MQTT page defines the four topics and a lower-case status field. It also uses upper-case states in prose, refers to the current-status topic as "No. 6" even though `status` is row 4, and does not define JSON encoding, command payloads, QoS, retain behavior, event identity, error reporting, or state transitions.

The following decisions remove those ambiguities without changing the four required topics:

| Question | Adopted here | Reason |
|---|---|---|
| Status encoding | A JSON object with one required `status` field | The Notion table strongly suggests an object but does not explicitly define JSON for Wake topics. Consumers compare parsed values, not byte serialization. |
| Wire casing | Lower-case `idle`, `listening`, `call`, `finish` | This matches the payload schema table. Upper-case names are internal enums only. |
| Detection behavior | Auto-stop capture and latch `call` or `finish` | Prevents repeated activations. A later legacy `stop-listen` is harmless; v2 first requires acknowledgement of the durable event. |
| Latch lifetime | Until the next accepted `start-listen` or `stop-listen`; v2 preserves it across graceful and crash restarts | Makes `request-status` meaningful and avoids overwriting an event with `idle`. Legacy cannot restore a latch after process exit and publishes `idle` during graceful shutdown as a documented compatibility limitation. |
| Command payload | Accept empty bytes, JSON-whitespace-only bytes, or `{}` in legacy mode | The source defines no command payload. This tolerates likely existing publishers. |
| MQTT delivery | QoS 1, `retain=false` on all four topics | At-least-once delivery is preferable; retained `call`/`finish` or commands could replay stale actions. |
| Retained commands | Ignore and warn | A retained start or stop is unsafe after process or broker restart. |
| One process | Exactly one room and one microphone | Matches the older design and prevents topic/device ownership races. Scale with one process per room. |
| Simultaneous crossings | Compare calibrated normalized threshold margins; reject near-ties | Raw scores from thresholds 0.8 and 0.99 are not directly comparable. Ambiguous audio should fail closed. |
| Broker disconnect | Stop capture and require a fresh start after reconnect | An offline stop cannot be recovered safely from the identifier-free legacy contract. Automatic re-arm is disabled unless an approved reconciliation protocol replaces this rule. |
| TTS ordering | Keep listening stopped through TTS and its measured echo tail | The completed page mentions re-enable and TTS together but does not order them. Re-enabling before playback ends can self-trigger. |
| Restart after `finish` | Stay latched until Spring explicitly sends the next `start-listen` or `stop-listen` | The MC flow starts turn analysis but does not define who rearms wake-word capture. The module must never guess that analysis is complete. |
| Runtime error | Close capture, enter internal `FAULT`, expose not-ready, and publish legacy `idle` if possible | The completed contract has no error state. Production also requires an approved monitored health channel so `FAULT` is not mistaken for healthy idle. |
| Model filenames | Use the hash-bound `ssafiya.onnx` and `nae_teon_kkeutnasseo.onnx` IDs | This deliberately supersedes the older draft's fixed `call.onnx`/`finish.onnx` slot convention. Logical wire mapping remains configuration-driven. |

These are compatibility decisions, not claims about what the Notion source already specifies. Section 6 proposes a reliable payload extension that still needs Spring approval.

## 3. Scope

### In scope

- One configured `roomNumber` and one microphone per process.
- Two openWakeWord-compatible classifier ONNX files from this directory.
- Exact audio framing, stateful inference, decision filtering, and collision handling.
- MQTT command handling and status publication.
- Reconnect, overflow, device-loss, and graceful-shutdown behavior.
- Offline fixture replay, live microphone tests, calibration tooling, metrics, and health checks.
- A strict development-versus-production model quality gate.

### Out of scope

- Performing QnA, STT, TTS, game analysis, or publishing QnA/MC topics directly.
- Saving microphone recordings in normal operation.
- Treating the eight supplied positive clips as an accuracy or precision benchmark.
- Training code inside `WakeWordModule`. Retraining remains in the existing OpenWakeWord pipeline.
- Supporting multiple rooms or microphones inside one process.
- Claiming exactly-once MQTT behavior with the current one-field status payload.

Spring, not this module, translates `call` into the QnA flow and `finish` into `/room/{roomNumber}/mc/cmd/analyze`.

## 4. Current artifact audit

### 4.1 Classifier models

| Artifact | Bytes | SHA-256 | Input | Output |
|---|---:|---|---|---|
| `ssafiya.onnx` | 203,855 | `af96d0d297eb6bbecbab43debe8af9fff2b914454f55b6ca123b2ba120711641` | `input`, float32 `[batch,16,96]` | `ssafiya`, float32 `[batch,1]` |
| `nae_teon_kkeutnasseo.onnx` | 203,881 | `95294f0a98464d3db9b19ad8a07a2d58ed485511757ce5d7583e478c43ae3473` | `input`, float32 `[batch,16,96]` | `nae_teon_kkeutnasseo`, float32 `[batch,1]` |

Both graphs are ONNX IR 8, opset 17, PyTorch 2.11 exports with a sigmoid output. Neither embeds useful model metadata. The service must therefore use a checked configuration/manifest rather than guessing phrase mapping from graph contents.

### 4.2 Required openWakeWord frontend

The two files above are small classifiers over speech embeddings. A runnable service also needs the pinned openWakeWord code and at least these frontend resources:

| Artifact | SHA-256 |
|---|---|
| `melspectrogram.onnx` | `ba2b0e0f8b7b875369a2c89cb13360ff53bac436f2895cced9f479fa65eb176f` |
| `embedding_model.onnx` | `70d164290c1d095d1d4ee149bc5e00543250a7316b59f31d056cff7bd3075c1f` |
| `silero_vad.onnx` (only if VAD is enabled) | `a35ebf52fd3ce5f1469b2a36158dba761bc47b973ea3382b3186ca15b1f5af28` |

These frontend files are not in `outputs/`; the audited copies are under `../vendor/openWakeWord/openwakeword/resources/models/`. The packaging step must copy those exact hash-checked files into the read-only deployment model bundle. Do not download models at service startup and do not rely on package-default resource discovery.

The local runtime is openWakeWord 0.6.0 at commit [`368c03716d1e92591906a84949bc477f3a834455`](https://github.com/dscripka/openWakeWord/tree/368c03716d1e92591906a84949bc477f3a834455). Pin this exact commit for the first implementation and treat an upgrade as a model-runtime compatibility change requiring the full replay suite.

Use CPU inference by default. Repeated local measurements with both classifiers were in the low single-digit milliseconds per frame, far below the 80 ms frame period, but they are not target-hardware acceptance evidence. Store a reproducible benchmark report for every deployment machine. CPU also avoids CUDA/cuDNN deployment coupling. Note that this pinned `Model` hardcodes classifier sessions to the CPU; `device="gpu"` only changes the mel/embedding sessions.

### 4.3 Quality evidence and hard production block

| Metric | `ssafiya` | `nae_teon_kkeutnasseo` |
|---|---:|---:|
| Metadata threshold | 0.8 | 0.99 |
| Feature-validation positive recall | 19.53% | 35.94% |
| Feature-validation hard-negative false rate | 2.08% | 4.69% |
| Feature-validation above-threshold frames/hour | 4.487 | 3.833 |
| Runtime clean recall | 68.75% (132/192) | not run |
| Runtime noisy recall | 36% (36/100) | not run |
| Runtime hard-negative false rate | 7.29% (14/192) | not run |
| `quality_target_met` | false | false |

Additional facts:

- `nae_teon_kkeutnasseo.verification.json` is absent.
- `manifest.json` is absent because the verification pipeline did not pass both models.
- The reported zero office-noise activations for `ssafiya` cover only 0.0667 hours and are not strong false-accept evidence.
- The metadata's suggested `vad_threshold=0.5` and `patience_frames=2` were not jointly evaluated by the runtime verification code. Verification used each clip's maximum raw score.
- Keyword-positive and phrase-specific hard-negative training clips are synthetic ElevenLabs audio, and targeted validation uses held-out synthetic voices. Generic negative features also draw on the local Zeroth-Korean, DEMAND, and ACAV sources, but `data/custom_noise` is absent and there is no labeled deployment-room/user-recorded real-negative evaluation corpus. The eight supplied smoke positives are not a substitute for that corpus.
- Training used the ACAV negative feature set identified in the project guide as CC BY-NC-SA 4.0. Commercial use needs legal review or a replacement negative corpus.

Production startup MUST require a valid, quality-passed deployment manifest whose model and frontend hashes match the loaded files. With the current directory, production startup must fail. Development or shadow startup requires an explicit `WAKEWORD_ALLOW_UNVERIFIED_MODELS=true` override and a prominent structured warning.

### 4.4 Supplied test audio

All eight files are 16-bit PCM, 44,100 Hz, stereo with byte-identical channels. Their RMS levels are low, approximately -35.9 to -42.3 dBFS. They are four positives for each phrase; there are no true negative, hard-negative, long-background, playback, or multi-speaker files.

After correct whole-file downmix/resampling to 16 kHz mono PCM16, raw single-phase maximum scores are:

| Clip | Expected model | Correct max | Threshold | Other model crosses? |
|---|---|---:|---:|---|
| `ssafiya_test1.wav` | `ssafiya` | 0.8065 | 0.8 | no |
| `ssafiya_test2.wav` | `ssafiya` | 0.8582 | 0.8 | no |
| `ssafiya_test3.wav` | `ssafiya` | 0.8544 | 0.8 | no |
| `ssafiya_test4.wav` | `ssafiya` | 0.8218 | 0.8 | no |
| `turn_test1.wav` | `nae_teon_kkeutnasseo` | 0.99850 | 0.99 | no |
| `turn_test2.wav` | `nae_teon_kkeutnasseo` | 0.99539 | 0.99 | no |
| `turn_test3.wav` | `nae_teon_kkeutnasseo` | 0.99744 | 0.99 | no |
| `turn_test4.wav` | `nae_teon_kkeutnasseo` | 0.99865 | 0.99 | no |

This is only an 8/8 functional smoke result. It does not establish precision, recall, or a false-activation rate.

The result is also fragile:

- A correct external two-consecutive-frame rule passes only 6/8; `ssafiya_test1` and `turn_test2` have only one qualifying frame.
- Sweeping phrase alignment through eight 10 ms offsets moved `ssafiya_test1` from about 0.783 to 0.846.
- The same sweep moved `turn_test2` from about 0.552 to 0.995; only one tested alignment crossed 0.99.

Frame-phase augmentation/retraining is therefore a production requirement. A staggered multi-phase inference ensemble MAY be evaluated later, but must not be enabled merely to make these fixtures pass; it can increase false activations and must be calibrated end to end.

## 5. Adopted MQTT legacy-compatible contract

For a configured room `A402`, the concrete topic prefix is `/room/A402/wake`. Build topics once from validated configuration. Do not subscribe with a room wildcard.

| Topic suffix | Full template | Direction | Module action |
|---|---|---|---|
| `start-listen` | `/room/{roomNumber}/wake/start-listen` | Spring to module | Arm both phrases and begin microphone inference. |
| `stop-listen` | `/room/{roomNumber}/wake/stop-listen` | Spring to module | Stop capture and inference decisions. |
| `request-status` | `/room/{roomNumber}/wake/request-status` | any to module | Publish the current latched wire status without changing state. |
| `status` | `/room/{roomNumber}/wake/status` | module to any | Publish `idle`, `listening`, `call`, or `finish`. |

### 5.1 Legacy command parsing

Until a command schema is approved, accept only:

```text
zero bytes
JSON whitespace bytes only: SP, TAB, LF, or CR
{}
```

Parsing requirements:

- Maximum payload size: 4 KiB. Reject larger payloads.
- If non-empty after trimming, decode strict UTF-8 and parse with a JSON parser.
- The parsed value must equal an empty object. Reject every other JSON value, including objects with keys, so different implementations cannot interpret the same command differently.
- Malformed input must not change state. Increment `wakeword_mqtt_invalid_command_total` and log topic, byte count, and reason, never raw payload contents.
- Ignore any command message with `retain=true`, log it, and increment a metric.
- MQTT callbacks must enqueue a small immutable command and return. They must not open/close audio, run inference, or wait for publication.

### 5.2 Status encoding

The module's legacy serializer emits one compact JSON object:

```json
{"status":"listening"}
```

Allowed values are lower-case only:

```text
idle
listening
call
finish
```

Publish at QoS 1 with `retain=false`. Consumers must parse JSON and compare the `status` value semantically; whitespace and key order are not part of the Notion contract. Tests SHOULD still assert the module's canonical compact serialization to catch accidental extra fields.

Duplicate QoS 1 delivery is legal. Spring should treat repeated receipt of the same latched state as idempotent in legacy development, but this is not sufficient for production: an old start or stop can arrive during a newer listening session, and a replayed latched result can retrigger work after a Spring restart. Production requires Section 6 or an equivalent persisted identity/deduplication protocol.

### 5.3 MQTT client behavior

- Use Paho MQTT's current callback API v2 and a unique, stable client ID such as `wakeword-{roomNumber}-{deviceId}`.
- Run the Paho network loop separately from audio and inference. Subscribe inside `on_connect` so reconnect renews subscriptions, as recommended by the [Paho client documentation](https://eclipse.dev/paho/files/paho.mqtt.python/html/client.html).
- Subscribe to the three exact command topics at QoS 1; v2 additionally subscribes to its exact acknowledgement topic from Section 6.
- In legacy mode, use a non-persistent broker session (`clean_session=true` for MQTT 3.1.1, or clean start with session expiry 0 for MQTT 5). This intentionally avoids queued identifier-free commands arriving after reconnect. Spring must send the current desired state again.
- In v2, use a stable client ID and a broker-persistent session (`clean_session=false` in MQTT 3.1.1, or a nonzero reviewed session expiry in MQTT 5). Sequence/session validation makes queued commands safe to classify, but the durable application outboxes remain authoritative if the broker loses session state.
- Do not declare the module ready until CONNACK and all expected SUBACKs have succeeded.
- Configure bounded exponential reconnect backoff with jitter.
- Use TLS and broker authentication in non-local environments. Load credentials from mounted secrets or environment references, never source control or logs.
- Do not use `idle` as a Last Will: it would falsely report a clean idle state after a crash. A separate health topic is preferable but requires a contract addition.
- In legacy mode, send publications through a bounded, nonblocking in-memory dispatcher queue. In v2, the coordinator first writes every logical status to the durable outbox and the dispatcher polls it in `statusRevision` order; any in-memory notification is only a wake hint and may be retried. The coordinator records PUBACK/application-ack events but never waits in the audio or MQTT callback.
- Keep a pending current-status snapshot in memory. A latched result may be retransmitted by MQTT or republished after reconnect/request-status and is therefore at-least-once. This is another reason v2 identity is mandatory for production.
- On graceful legacy shutdown, stop capture, publish `idle` at QoS 1, wait for PUBACK up to the deadline, then disconnect. On v2 shutdown, publish `idle` only when no latch exists. Preserve every v2 latch across shutdown, whether its event is acknowledged or pending; retry a pending outbox only within the deadline, disconnect without a later `idle`, and restore the latch on startup. Planned retirement must receive an accepted stop before shutdown if owners want the latch cleared.

MQTT QoS 1 is at-least-once, not exactly-once. The legacy payload contains no command/event IDs, so it cannot robustly distinguish all delayed duplicates or correlate an event with a listening session. Section 6 is required before claiming reliable deduplication.

## 6. Recommended MQTT v2 extension

This extension keeps the four existing topics, adds one application-acknowledgement topic, and is disabled until Spring accepts it. Add a `contract_version` setting so rollout can be coordinated. Production requires v2 or an equivalent protocol with durable ordering, command identity, session identity, event identity, and application acknowledgement on both sides.

V2 adds `/room/{roomNumber}/wake/ack`, Spring to module, QoS 1 and `retain=false`. It acknowledges durable application receipt of a detection; MQTT PUBACK alone acknowledges only the broker.

Example start command:

```json
{
  "contractVersion": 2,
  "commandId": "c5b1cfde-049c-48a6-8372-c76931154464",
  "controllerEpoch": "0ba78b9f-ab15-4643-8bd5-79a3796f04ab",
  "commandSequence": 1041,
  "listenSessionId": "df52ed10-499d-4ccd-ad72-2b91c3f8937e",
  "issuedAt": "2026-08-02T13:00:00Z"
}
```

Example stop command:

```json
{
  "contractVersion": 2,
  "commandId": "3d2913e5-b72c-420a-8a77-a2fa630bd1a3",
  "controllerEpoch": "0ba78b9f-ab15-4643-8bd5-79a3796f04ab",
  "commandSequence": 1042,
  "listenSessionId": "df52ed10-499d-4ccd-ad72-2b91c3f8937e",
  "issuedAt": "2026-08-02T13:00:10Z"
}
```

Example request-status command:

```json
{
  "contractVersion": 2,
  "requestId": "a4648968-0402-4bd1-b52f-55b1f3293b44",
  "issuedAt": "2026-08-02T13:00:12Z"
}
```

Every v2 status publication uses one fixed envelope. Fields that do not apply are present as JSON `null`; implementations must not improvise alternate shapes. An accepted start publishes:

```json
{
  "contractVersion": 2,
  "deviceId": "wake-mic-01",
  "statusRevision": 42,
  "status": "listening",
  "listenSessionId": "df52ed10-499d-4ccd-ad72-2b91c3f8937e",
  "eventId": null,
  "occurredAt": "2026-08-02T13:00:00.120Z",
  "modelId": null,
  "modelSha256": null,
  "confidence": null,
  "configRevision": "sha256:...",
  "commandId": "c5b1cfde-049c-48a6-8372-c76931154464",
  "requestId": null,
  "outcome": "accepted",
  "reasonCode": null
}
```

Example detection status:

```json
{
  "contractVersion": 2,
  "deviceId": "wake-mic-01",
  "statusRevision": 43,
  "status": "call",
  "eventId": "4add98d1-e87a-4f48-86f5-4e08eb24827b",
  "listenSessionId": "df52ed10-499d-4ccd-ad72-2b91c3f8937e",
  "occurredAt": "2026-08-02T13:00:03.241Z",
  "modelId": "ssafiya",
  "modelSha256": "af96d0d297eb6bbecbab43debe8af9fff2b914454f55b6ca123b2ba120711641",
  "confidence": 0.8421,
  "configRevision": "sha256:...",
  "commandId": null,
  "requestId": null,
  "outcome": null,
  "reasonCode": null
}
```

Example application acknowledgement:

```json
{
  "contractVersion": 2,
  "ackId": "dc48f30d-bb84-426a-9bb7-097998402031",
  "eventId": "4add98d1-e87a-4f48-86f5-4e08eb24827b",
  "listenSessionId": "df52ed10-499d-4ccd-ad72-2b91c3f8937e",
  "receivedAt": "2026-08-02T13:00:03.310Z"
}
```

V2 requirements:

- `contractVersion` is the JSON integer `2`. Command and acknowledgement JSON Schemas reject missing or unknown fields; adding fields requires a reviewed schema revision. Status consumers ignore unknown fields for forward compatibility.
- Apply the same 4 KiB inbound limit as legacy, decode strict UTF-8, require one top-level JSON object, reject duplicate member names and non-standard/non-finite numbers, then validate the topic-specific schema before any state or durable-sequence mutation.
- `commandId`, `requestId`, `ackId`, `eventId`, `controllerEpoch`, and `listenSessionId` are UUID strings where present/non-null. `occurredAt`, `issuedAt`, and `receivedAt` are UTC RFC 3339 timestamps with an explicit `Z` or offset.
- Spring provisions one durable `controllerEpoch` and a strictly increasing `commandSequence` in `[0, 2^63 - 1]` for every state-changing start/stop. It persists the next sequence before publish and does not create a new epoch on ordinary process restart. An epoch change is a coordinated reset allowed only while the module is confirmed idle.
- The module persists the expected epoch and the highest valid, in-window state-changing sequence. After exact command-ID duplicate handling, reject a lower sequence as `stale_command`, reuse of the same sequence with another ID/body as `sequence_conflict`, and another epoch as `controller_epoch_mismatch`. A fresh, authenticated, age-valid command advances the high-water mark transactionally even if its state/session outcome is rejected, so an older command cannot act later.
- A `listenSessionId` is globally single-use. A new start is accepted only with a never-seen session ID. During `ARMING_START`, only an exact retry of the processing command is valid and returns `in_progress`; a different command ID for that session is rejected as `invalid_state`. During `RECOVERING_AUDIO`, an exact retry of the original start replays its cached `accepted` response and a different-ID start is rejected. Once `LISTENING`, a different command ID/sequence for the same session is a semantic `duplicate`. A new start that reuses an ID after stop/detection is `session_reuse`; a matching stop may still refer to the active/latched session after its event is acknowledged. Retain closed-session tombstones for at least the maximum command age plus broker queued-message lifetime and clock-skew allowance. If that lifetime is unbounded, tombstones cannot be pruned in production.
- `statusRevision` is a durable, monotonically increasing integer in `[0, 2^63 - 1]`, scoped to `deviceId`. Allocate and persist it with the serialized status before queueing each new logical publication. MQTT retries/reconnect replay reuse the exact revision and payload; a new request-status snapshot or command response gets a new revision even when the state did not change. Exhaustion requires a coordinated idle reprovision rather than wraparound.
- `occurredAt` is the time the represented state transition/detection occurred, not send time. Duplicate responses, request-status snapshots, and retransmissions preserve the state's original occurrence time even when a snapshot receives a new `statusRevision`.
- Spring durably tracks the highest `statusRevision` per `deviceId`. A lower revision cannot replace its current-state projection, but an event payload is still deduplicated/re-acknowledged by `eventId`. Equal revisions with different canonical payload digests are a protocol fault.
- Every v2 status has all fields shown in the envelope. `idle` requires session/event/model/hash/confidence to be null. `listening` requires a session and null event/model/hash/confidence. `call`/`finish` require session, event, model, model hash, and confidence.
- A start/stop response echoes `commandId` and uses `outcome` equal to `accepted`, `duplicate`, `in_progress`, or `rejected`. A request-status response echoes `requestId` and uses `outcome` equal to `snapshot` or `rejected`. Asynchronous startup, recovery, and detection publications use null command/request/outcome. At most one of command ID and request ID is non-null.
- `reasonCode` is null except on `rejected`; define a closed, contract-tested enum including at least `invalid_schema`, `unsupported_version`, `expired`, `future_issued_at`, `stale_command`, `sequence_conflict`, `controller_epoch_mismatch`, `stale_session`, `session_reuse`, `event_unacknowledged`, `invalid_state`, `interrupted`, and `id_conflict`. Never put free-form error text on MQTT.
- Persist processed command/request/ack IDs and canonical request digests/outcomes, sequence/epoch state, session tombstones, the status-revision counter, current listen-session metadata, latched event metadata, and the serialized outbox in one transactional metadata-only store across process restart. Retain ID records at least as long as their maximum valid/replay lifetime. Never store audio.
- Enforce an approved maximum command age and clock-skew allowance using `issuedAt`. For a syntactically valid envelope with a valid ID, publish a `rejected` response when it is expired, materially future-dated, stale, or invalid in the current state. If no valid ID can be parsed, reject locally and emit only a sanitized metric/log because no safe correlation key exists.
- Compute request/status digests over RFC 8785 canonical JSON after schema validation. After a command finishes, an exact replay of the same `commandId` and digest republishes the exact cached terminal response bytes, including its original `statusRevision`, `outcome`, and `reasonCode`; it never substitutes `duplicate`. Reuse of an ID with a different digest returns `id_conflict` without replacing the original cached record. A stop whose `listenSessionId` does not equal the active/latched session is rejected as `stale_session`.
- Before executing a fresh start/stop, one transaction records its high-water sequence, ID/digest, session intent, and internal `PROCESSING` outcome. A start remains processing through `ARMING_START` and becomes `accepted` only when `listening` is durably queued; an exact retry meanwhile emits `in_progress` without restarting warm-up. `RECOVERING_AUDIO` is different: the start already has a cached terminal acceptance and must never be rewritten. On restart, an unfinished command/session is closed and receives a cached, correlated `rejected`/`interrupted` idle response. `duplicate` is reserved for a new command ID/sequence whose semantic intent is already satisfied, such as another start for the same active session. Spring keeps its command outbox until it receives `accepted`, `rejected`, or a `duplicate` response whose current state proves the requested intent; `in_progress` does not close it.
- For `request-status`, the first valid `requestId`/digest stores its exact `snapshot` response. An exact retry republishes those cached bytes/revision. A valid ID on an expired/invalid request stores and replays a correlated `rejected` response; the same ID with a different digest returns `rejected`/`id_conflict` without replacing the original. Request-status never changes lifecycle state or the state-changing command-sequence high-water mark.
- Use `listenSessionId` plus `eventId` for downstream deduplication.
- On a candidate detection, the coordinator immediately invalidates its local generation so later queued candidates are stale. It then atomically persists the latch, one newly generated `eventId`, `statusRevision`, and the exact serialized status payload in the outbox before issuing worker/audio stop and before queueing MQTT. Only that commit makes the detection accepted. If it fails, stop capture, enter `FAULT`, and publish no event.
- Keep a detection outbox item through broker PUBACK and across process restarts. Retry the identical payload/revision with bounded backoff after reconnect until a matching application acknowledgement arrives. A valid acknowledgement marks the outbox item delivered transactionally but does not clear the `call`/`finish` latch.
- Spring must transactionally record `eventId` and the downstream work intent before triggering QnA/turn analysis or publishing the acknowledgement. On duplicate event delivery, it performs no duplicate work but republishes an acknowledgement. The module deduplicates `ackId`, verifies event/session identity, and ignores stale/mismatched acknowledgements.
- While a latched detection is still unacknowledged, v2 rejects a start or stop with `event_unacknowledged`; the pending event must not be overwritten by a newer status. Spring acknowledges first, then issues a fresh command ID/sequence. Because a rejected command outcome is durable, retry after acknowledgement uses a new command ID/sequence rather than replaying the cached rejection.
- Spring also keeps each state-changing command in its own durable outbox and retries the identical command ID/epoch/sequence/body with bounded backoff until a correlated terminal response arrives. A broker PUBACK is not a command outcome. The module's exact cached terminal-response replay closes the loop if the first response was lost.
- Use UTC wall time only for observability. Use a monotonic clock for cooldowns, deadlines, and elapsed time.
- Confidence is diagnostic, not a probability guarantee.
- Spring must ignore unknown fields so the payload remains extensible.
- The module still latches the detection result and emits at most one event per listen session.

Do not silently add these fields or the acknowledgement subscription to a strict legacy consumer. Check in JSON Schemas for all three commands, the acknowledgement, and the fixed status envelope, then add producer/consumer contract tests on both sides before rollout.

## 7. State machine

### 7.1 Internal states

```python
class InternalState(Enum):
    STARTING = "starting"
    IDLE = "idle"
    ARMING_START = "arming_start"
    RECOVERING_AUDIO = "recovering_audio"
    LISTENING = "listening"
    LATCHED_CALL = "latched_call"
    LATCHED_FINISH = "latched_finish"
    PAUSED_DISCONNECTED = "paused_disconnected"
    FAULT = "fault"
    SHUTTING_DOWN = "shutting_down"
```

Wire mapping:

| Internal state | Legacy wire status |
|---|---|
| `IDLE`, `STARTING`, `ARMING_START`, `RECOVERING_AUDIO` | `idle` |
| `LISTENING` | `listening` |
| `LATCHED_CALL` | `call` |
| `LATCHED_FINISH` | `finish` |
| `PAUSED_DISCONNECTED` | Preserve the last externally visible status; no broker is available. |
| `FAULT` without a durable v2 latch, `SHUTTING_DOWN` | `idle` if publishing is possible. |
| `FAULT` with a durable v2 latch/outbox | Preserve the latched `call`/`finish`; expose failure only through health until recovery. |

Do not publish `listening` until the model is warmed, the capture stream is active, and inference can accept frames.

Broker connectivity/readiness is also tracked independently. `IDLE`, either latched state, and `FAULT` can all exist while disconnected without changing their domain meaning. `PAUSED_DISCONNECTED` is used only when an active, start-arming, or recovery generation is interrupted.

### 7.2 Transitions

The table below runs only after parsing/authentication and, in v2, durable ID/epoch/sequence/session validation from Section 6. A rejected command publishes the correlated v2 rejection snapshot and does not enter this lifecycle table.

**Pending-start invariant:** every v2 transition out of `ARMING_START` has exactly one terminal outcome for its persisted `PROCESSING` start. Success uses one transaction to store/cache the correlated `accepted` listening response and insert its exact bytes into the durable outbox; that commit is the semantic enqueue, and only a best-effort dispatcher wake hint follows. Before any non-success exit, one transaction changes the start to `rejected`/`interrupted`, allocates/stores its correlated idle response, and inserts it into the outbox; only then may lifecycle state leave `ARMING_START`. This applies to stop, broker disconnect, capture/open failure, model/warm failure, outbox-capacity/storage failure, signal shutdown, and recovery exhaustion. When a stop caused cancellation, the same transaction also records the stop outcome and orders the interrupted-start response before the accepted-stop response. If the store itself is unavailable, immediately invalidate the generation/stop capture, remain not-ready in `FAULT`, and complete terminalization before accepting commands during recovery or restart. Never return `in_progress` after the start has become incapable of reaching `LISTENING`. This invariant never runs in `RECOVERING_AUDIO`, which has no processing start command.

| Current | Input | Required behavior | Next |
|---|---|---|---|
| `STARTING` | checks pass with a restored v2 latch | Keep capture closed; retry the exact outbox payload if unacknowledged, otherwise publish a new correlated state snapshot. | matching latched state |
| `STARTING` | checks pass with no restored latch | Close/tombstone any crash-interrupted v2 active session, publish `idle`, and require a new session/start. | `IDLE` |
| `IDLE` | valid start | Reserve worker-control capacity and v2 outbox quota for the terminal start response plus one detection, then persist `PROCESSING`, increment generation, enqueue `ResetAndWarm`, and wait for acknowledgement. Reject/fault before arming if reservation fails. | `ARMING_START` |
| `IDLE` | valid stop | Republish `idle`; do not touch the engine. | `IDLE` |
| `ARMING_START` | legacy duplicate or exact v2 retry | Keep current warm-up; do not restart it. V2 exact retry reports `in_progress`. | `ARMING_START` |
| `ARMING_START` | different-ID v2 start | Reject `invalid_state`; do not register another waiter or restart warm-up. | `ARMING_START` |
| `ARMING_START` | matching `EngineReady` | Open capture with decisions disabled, atomically terminalize/queue the accepted `listening` response under the pending-start invariant, then enable decisions. | `LISTENING` |
| `ARMING_START` | valid stop | Apply the pending-start invariant, invalidate generation, cancel/discard worker acknowledgement, then publish the accepted stop's `idle`. | `IDLE` |
| `LISTENING` | legacy duplicate or same-session v2 start | Do not reset or create a gap. Legacy republishes `listening`; v2 exact-ID retries replay cached acceptance and new-ID semantic duplicates report `duplicate`. | `LISTENING` |
| `LISTENING` | valid stop | Stop capture, invalidate generation, reset decision state, publish `idle`. | `IDLE` |
| `LISTENING` | audio discontinuity/lag | Stop capture, invalidate/increment generation while preserving the accepted session, reserve recovery control/status capacity, publish `idle`, and enqueue `ResetAndWarm`; fault/close the session if reservation fails. | `RECOVERING_AUDIO` or `FAULT` |
| `RECOVERING_AUDIO` | exact original v2 start retry or legacy duplicate | Do not restart recovery. V2 replays the cached terminal `accepted` response; legacy republishes mapped `idle`. | `RECOVERING_AUDIO` |
| `RECOVERING_AUDIO` | different-ID v2 start | Reject `invalid_state`; do not restart recovery. | `RECOVERING_AUDIO` |
| `RECOVERING_AUDIO` | matching `EngineReady` | Open capture decision-disabled, durably queue an asynchronous `listening` snapshot, then consume the reserved control slot with `EnableDecisions`. | `LISTENING` |
| `RECOVERING_AUDIO` | valid stop | Invalidate generation, cancel recovery, close/tombstone the session, and publish the accepted stop's `idle`; do not rewrite the original start outcome. | `IDLE` |
| `LISTENING` | `ssafiya` candidate | Invalidate generation, transactionally persist the latch/outbox, stop worker/capture, then queue `call`; on persistence failure stop/fault without publishing. | `LATCHED_CALL` or `FAULT` |
| `LISTENING` | turn candidate | Invalidate generation, transactionally persist the latch/outbox, stop worker/capture, then queue `finish`; on persistence failure stop/fault without publishing. | `LATCHED_FINISH` or `FAULT` |
| latched | valid stop | Clear latch and publish `idle`. | `IDLE` |
| latched | valid start | Perform the same reservations/`PROCESSING` transaction as `IDLE + start`, create a new generation/session, and enqueue `ResetAndWarm`; do not open capture yet. | `ARMING_START` |
| any connected state | request-status | Publish current mapped status; make no transition. | unchanged |
| `ARMING_START`, `RECOVERING_AUDIO`, or `LISTENING` | broker disconnect | Apply the pending-start invariant only for `ARMING_START`; for recovery/listening preserve the original cached acceptance but close/tombstone the interrupted session. Stop capture, invalidate generation, and clear desired auto-resume. | `PAUSED_DISCONNECTED` |
| `PAUSED_DISCONNECTED` | broker ready | Publish `idle` and wait for a fresh Spring start. | `IDLE` |
| `IDLE` | broker disconnect/reconnect | Keep capture closed; on broker ready republish `idle`. | `IDLE` |
| latched | broker disconnect/reconnect | Keep capture closed and the same event ID; retransmit/report the latch at least once after broker ready. | unchanged |
| `FAULT` | broker disconnect/reconnect | Remain not-ready with capture closed. Preserve/retry a durable latched event if publishing is usable; with no latch publish legacy `idle` only when the approved health channel also exposes the fault. | `FAULT` |
| any active state | unrecoverable audio/model error | Apply the pending-start invariant only for `ARMING_START`; for recovery/listening close/tombstone the accepted session without rewriting its start. Stop capture, invalidate generation, expose not-ready, publish `idle` if possible. | `FAULT` |
| `FAULT` | start or stop command | V2 rejects `event_unacknowledged` when a pending event exists, otherwise `invalid_state`; legacy republishes `idle`. Do not touch capture/model. | `FAULT` |
| `FAULT` | successful bounded recovery with durable latch | Restore its latched state and resume pending event delivery or publish a current snapshot. | matching latched state |
| `FAULT` | successful bounded recovery without latch | Run all relevant self-checks and publish `idle`. Never auto-resume without a fresh start unless the approved policy says so. | `IDLE` |

Each accepted start creates a monotonically increasing in-process `generation` and a listen-session UUID. In v2, use the command's `listenSessionId`; in legacy mode, create the UUID locally for correlation even though it is not published. Every queued control, audio frame, score, and detection carries the generation. Every internal discontinuity recovery increments the generation but preserves the same listen-session UUID. The coordinator must ignore anything whose generation is not current. This closes races where a detection was already queued as `stop-listen` arrived.

Only the coordinator owns and mutates module state. Only the inference worker owns and mutates the model, assembler, VAD, and their histories. The coordinator sends typed control messages such as `ResetAndWarm(generation)` to the worker; it never calls model lifecycle methods directly. MQTT callbacks and the inference worker submit typed events to the coordinator's bounded queue.

The worker keeps decisions disabled throughout warm-up and initial stream opening. A start reserves a worker-control slot before `PROCESSING`; after the stream opens, the coordinator durably inserts the v2 `listening` response (or successfully offers the legacy status to its bounded FIFO) and only then consumes that reservation with `EnableDecisions(generation)`. Missing/invalid reservation is discovered and terminalized before the accepted-response transaction; after commit, consuming a valid reservation must be infallible by construction. This prevents a detection publication from overtaking the status that tells consumers listening is active. Never coalesce or drop `call`/`finish`; repeated legacy snapshots may be coalesced only when semantically identical, while v2 retries reuse their exact stored identity/revision.

The worker-control queue is FIFO and has priority over the independent audio queue before every audio dequeue. While a generation is decision-disabled, its audio blocks may wait in the bounded audio queue but must not advance the assembler/model; queue-age and overflow limits still apply. `ResetAndWarm` and `StopGeneration` drain all queued audio for the affected generation. Thus a successfully queued `EnableDecisions` is observed before any newly captured block can produce a score, while a queued stop/reset makes older blocks stale.

Legacy delayed commands can still cross listening-session boundaries because they carry no identity. In particular, an old start received while latched is indistinguishable from a legitimate new start, and an old stop can stop a new session. These transitions exist for local compatibility, not as a production reliability claim. V2 resolves them with `commandId` and `listenSessionId`.

Graceful legacy shutdown clears its non-durable latch to `idle`. V2 shutdown never changes a latched domain state: it preserves acknowledged latch metadata and any unacknowledged outbox, then restores them on restart. An ungraceful process crash also loses in-memory legacy latch state; production v2 restores and deduplicates transactional metadata in either restart path.

## 8. Component design

Use small components with explicit ownership. Do not put capture, inference, MQTT, and state mutation in one callback-heavy class.

```text
Paho network thread
  -> ControlEvent queue
                              +-------------------+
Inference worker              | WakeWordModule    | -> v2 durable outbox / bounded legacy queue
  -> WorkerEvent ------------>| coordinator       | -> health/metrics
                              +-------------------+             |
                                       |                        v
                                       +-> inference-control  Paho publisher/network loop

Audio callback -> bounded immutable AudioBlock queue -> inference-worker-owned
                                                        assembler -> engine -> detector
```

Suggested interfaces:

```python
@dataclass(frozen=True)
class AudioBlock:
    generation: int
    first_sample_index: int
    callback_monotonic_ns: int
    adc_time_seconds: float | None
    pcm_bytes: bytes

@dataclass(frozen=True)
class AudioFrame:
    generation: int
    sequence: int
    first_sample_index: int
    end_sample_index: int
    frame_end_monotonic_ns: int
    pcm: np.ndarray  # contiguous, read-only int16, shape (1280,)

@dataclass(frozen=True)
class RawScores:
    generation: int
    sequence: int
    frame_end_sample_index: int
    frame_end_monotonic_ns: int
    scores: Mapping[str, float]
    vad_score: float | None

@dataclass(frozen=True)
class WakeWordCandidate:  # returned by the pure detector; not yet an accepted event
    generation: int
    model_id: Literal["ssafiya", "nae_teon_kkeutnasseo"]
    wire_status: Literal["call", "finish"]
    raw_score: float
    threshold: float
    frame_end_sample_index: int
    frame_end_monotonic_ns: int
    occurred_at_utc: datetime  # timezone-aware; derived from the stream/sample anchor
    timestamp_uncertainty_ms: float

@dataclass(frozen=True)
class WakeWordDetection:  # created by the coordinator and accepted only after store commit
    event_id: UUID
    listen_session_id: UUID
    status_revision: int
    candidate: WakeWordCandidate
    model_sha256: str
    config_revision: str

class AudioSource(Protocol):
    def start(self, generation: int, sink: Callable[[AudioBlock], None]) -> None: ...
    def stop(self) -> None: ...
    def close(self) -> None: ...

class InferenceWorker(Protocol):
    def reserve_terminal_control(self, generation: int) -> ControlReservation | None: ...
    def submit_control(self, command: ResetAndWarm | EnableDecisions | StopGeneration | Shutdown,
                       reservation: ControlReservation | None = None) -> bool: ...
    def offer_audio(self, block: AudioBlock) -> bool: ...

class Publisher(Protocol):
    def offer_legacy_status(self, payload: bytes, qos: int = 1, retain: bool = False) -> bool: ...
    def wake_outbox_dispatcher(self) -> None: ...  # hint only; durable polling is authoritative
```

Required production classes:

- `WakeWordConfig`: immutable, fully validated settings and per-model policies.
- `PcmFrameAssembler`: inference-worker-owned converter from arbitrary immutable audio blocks into exact 1,280-sample frames.
- `SoundDeviceAudioSource`: production `RawInputStream` microphone adapter whose callback only copies/enqueues `AudioBlock`.
- `WaveFileAudioSource` or replay utility: deterministic tests only.
- `InferenceWorker`: sole owner of `PcmFrameAssembler`, one `OpenWakeWordEngine`, optional separate VAD state, warm-up, and discontinuity reset.
- `OpenWakeWordEngine`: thin synchronous wrapper around one `openwakeword.Model` containing both classifiers; it is never used outside the worker.
- `DetectionStateMachine`: pure, unit-tested application-side decision policy.
- `DurableStateStore`: coordinator-owned v2 command ordering/deduplication, session tombstones, latch, revision counter, and transactional outbox.
- `MqttAdapter`: connection, subscriptions, parsing, publishing, reconnect, PUBACK and application-acknowledgement tracking.
- `WakeWordModule`: serialized lifecycle/state coordinator.
- `HealthState` and metrics adapter.

Dependency injection is mandatory at the audio, clock, inference, and MQTT boundaries. Tests must not require a physical microphone or external broker unless specifically marked as system tests.

Resolve any `default`, name, or numeric device selector to the backend's canonical physical identity before locking or opening capture. Prefer a stable ALSA card/device, PipeWire node identity, or equivalent; a volatile PortAudio index alone is development-only. Acquire two independent OS-level exclusive locks, one keyed only by normalized room and one keyed only by canonical physical device identity, and hold both file descriptors for the process lifetime. This prevents both duplicate room ownership and reuse of one microphone under two room IDs. Failure to resolve unambiguously or acquire either lock is a startup error. MQTT client-ID contention is not a substitute: a broker may disconnect one client while both processes continue reading a shareable audio device.

Use a configured host-shared lock root such as `/run/lock/wakeword`, pre-created with least-privilege ownership. Derive separate `room-<sha256>` and `device-<sha256>` filenames from length-delimited canonical identities, not raw user text, and acquire them in that fixed order to avoid deadlock. Containers must mount the same host lock directory; production refuses a private per-container lock namespace that cannot exclude another replica.

Use SQLite for the first `DurableStateStore`: one coordinator-owned write connection, optional publisher read-only connection, explicit schema migrations, foreign keys enabled, WAL journaling, `synchronous=FULL`, bounded busy timeout, and explicit transactions. Put the database on a persistent local filesystem, not tmpfs or an unreliable network filesystem. Before marking a start `PROCESSING`, reserve bounded row/byte quota for its terminal response and one possible detection so ordinary backlog cannot consume them. The v2 publisher polls outstanding rows in revision order and permits at most one in-flight status per device; non-event rows complete on PUBACK, while detection rows remain until application acknowledgement. Production fails closed on reservation, migration, integrity-check, fsync/I/O, or corruption errors; never silently recreate a lost store because that would discard sequence, tombstone, and event identity.

## 9. Suggested project layout

The current `outputs/` directory is an artifact directory, not an application repository. Do not delete, rename, or overwrite the trained files. In the eventual service repository, use a layout equivalent to:

```text
wakeword-service/
├── pyproject.toml
├── lockfile
├── src/wakeword_module/
│   ├── __init__.py
│   ├── config.py
│   ├── contracts.py
│   ├── audio.py
│   ├── framing.py
│   ├── engine.py
│   ├── detector.py
│   ├── mqtt.py
│   ├── store.py
│   ├── coordinator.py
│   ├── health.py
│   └── main.py
├── config/
│   ├── development.yaml
│   └── production.yaml
├── models/
│   ├── deployment-manifest.json
│   ├── ssafiya.onnx
│   ├── nae_teon_kkeutnasseo.onnx
│   ├── melspectrogram.onnx
│   ├── embedding_model.onnx
│   ├── silero_vad.onnx
│   └── evaluation/
│       ├── ssafiya.final.json
│       └── nae_teon_kkeutnasseo.final.json
├── tests/
│   ├── unit/
│   ├── integration/
│   ├── contract/
│   └── fixtures/
├── schemas/
│   ├── mqtt-v2-start.schema.json
│   ├── mqtt-v2-stop.schema.json
│   ├── mqtt-v2-request-status.schema.json
│   ├── mqtt-v2-ack.schema.json
│   └── mqtt-v2-status.schema.json
└── tools/
    ├── replay.py
    ├── evaluate.py
    └── calibrate.py
```

Models SHOULD be mounted read-only in deployment. Resolve paths relative to the loaded config/manifest. Ignore the machine-specific absolute `model_path` values in the current training JSON files.

Use a supported Python release for the deployment image, install and lock every dependency of the pinned openWakeWord code, pin all resolved dependencies with hashes, and build reproducibly. At minimum the live service needs NumPy, SciPy, scikit-learn, ONNX Runtime CPU, `requests`, `tqdm`, the pinned openWakeWord package/code, Paho MQTT 2.x, and a PortAudio binding such as `sounddevice`. The pinned package imports SciPy/scikit-learn and requests/tqdm modules even when optional features are unused. Build/CI also needs `onnx` for the required checker; offline replay needs `soundfile`. The current virtual environment does not contain Paho MQTT, sounddevice, PyAudio, or Speex noise suppression.

Run exactly one service process/worker per microphone. Multiple Uvicorn/Gunicorn workers must not be used to wrap this hardware-owning module.

## 10. Startup and readiness

Perform these checks in order. Fail closed on any required check.

1. Parse config with unknown keys rejected.
2. Validate `roomNumber`: non-empty, no `/`, `+`, `#`, NUL, leading/trailing whitespace, or control characters. Apply the backend's exact regex once agreed.
3. Initialize the audio backend only far enough to enumerate devices. Resolve the configured selector to one canonical physical identity and reject ambiguity.
4. Acquire the independent room lock and canonical-device lock, in that order, from the configured host-shared lock root. Do not continue if another process owns either one.
5. Validate unique stable MQTT client/device IDs and topic lengths.
6. In v2, open the persistent state store, apply only known forward migrations, run its integrity/invariant checks, and verify the provisioned controller epoch. Never subscribe if this fails.
7. Check model/frontend files are regular, non-symlink files under the approved model root, unless symlinks are an explicit packaging choice.
8. Compute SHA-256 and compare with the deployment manifest. In explicitly unverified development mode only, compare with the typed config's pinned hashes when no manifest exists.
9. In production, require the trusted manifest's aggregate `qualityTargetMet=true`, every required per-model evaluation entry's `qualityTargetMet=true`, and every enumerated model/pipeline gate result to be passed. Verify the hashes of the referenced final evaluation reports. Do not read the training JSON's snake-case flag as the production source of truth. Reject the current artifacts because they have no such manifest/reports and their available training flags are false.
10. Run `onnx.checker.check_model` during build/CI. At runtime, inspect ONNX Runtime input/output name, dtype, and shape before accepting traffic.
11. Instantiate one openWakeWord model with both classifier paths, the explicit hash-checked mel/embedding paths, `inference_framework="onnx"`, `device="cpu"`, and `vad_threshold=0`. The wrapper must retain and expose the resolved loaded paths/providers for health and tests.
12. On the inference worker, feed at least 25 exact PCM16 silence frames to flush randomized feature history, initialized mel context, and the library's initial five suppressed predictions. Suppress all decisions during warm-up.
13. Run a finite-score and warm-up convergence self-test. Assert both expected keys exist, every score is finite and within `[0,1]` with a small numeric tolerance, and repeated reset/warm cycles produce equivalent post-warm silence scores within a tested tolerance.
14. Probe/open-close the same locked canonical microphone and confirm 16 kHz, mono, PCM16 capture; fail if re-resolution differs.
15. Connect to MQTT, subscribe to the three legacy command topics plus the v2 acknowledgement topic when enabled, and verify every SUBACK.
16. Restore durable v2 state. If any latch exists, enter its matching latched state and either queue the identical unacknowledged outbox payload or a new snapshot for an acknowledged latch. With no latch, transactionally close/tombstone any session interrupted by process death, enter `IDLE`, and queue a correlated `rejected`/`interrupted` idle response for an unfinished command (otherwise the ordinary contract-version-appropriate idle status). Mark readiness true only after the required initial/restore publication has been accepted by the dispatcher.

Liveness means the process/coordinator loop is running. Readiness means configuration, models, audio device, and broker subscriptions are usable. Keep them separate.

When `WAKEWORD_ALLOW_UNVERIFIED_MODELS=true`, readiness is allowed only in an explicitly non-production environment and must include `model_quality="unverified"` in health output and logs.

## 11. Audio pipeline

### 11.1 Live capture contract

Preferred capture format:

```text
sample rate: 16,000 Hz
channels: 1
sample format: signed little-endian PCM16
frame size: 1,280 samples
frame duration: 80 ms
```

Use `sounddevice.RawInputStream` or an equivalent raw callback stream. Let PortAudio choose its optimal callback block size (`blocksize=0`) unless target-hardware measurements justify a fixed size; correctness must not depend on callback block size. The callback must do only bounded work:

1. Read PortAudio status flags and increment overflow/underflow metrics.
2. Copy the callback bytes and enqueue one immutable `AudioBlock` with generation, first-sample index, ADC time when available, and callback monotonic time.
3. Return immediately.

It must not run model inference, MQTT operations, JSON encoding, logging I/O, resampling allocations, or locks with unbounded wait.

The queue limit is measured in callback blocks, while `max_callback_samples` independently bounds each block's memory and duration. The callback advances the sample clock even when enqueue fails. An oversized block, failed enqueue, or PortAudio overflow flag records the gap and forces the worker's discontinuity path; never truncate a block and pretend continuity.

Require native or audio-server-provided 16 kHz mono capture for the first production version. If a device cannot provide it, add a stateful streaming sample-rate converter with preserved filter state and explicit latency. Never call whole-array or stateless resampling independently on each callback chunk; that creates boundary artifacts and clock drift.

Reject odd byte counts, non-PCM16 formats, channel changes, or sample-rate changes while running. Treat them as discontinuities.

### 11.2 Framing

The inference worker's `PcmFrameAssembler` owns a byte/sample remainder and emits only contiguous `np.int16` arrays with shape `(1280,)`.

- Exact frame: emit once.
- Fragmented input: buffer until exact frames exist.
- Multiple frames: emit in original order with consecutive sequence numbers.
- Tail shorter than 1,280: retain, never call `predict()` with it.
- Stop/discontinuity: discard tail and increment a metric.
- Queue full: do not silently process stale audio. Drop/flush backlog, mark a discontinuity, reset the engine, and re-arm. Record dropped samples and outage duration.
- Frame too old: if its computed end time exceeds configured `max_frame_age_ms`, flush/reset before inference even when the queue is not full. Queue capacity is a memory bound, not permission to process seconds-old audio.

Calling openWakeWord with a shorter frame can repeat an earlier prediction; calling it with a longer frame max-pools multiple time steps and corrupts confirmation counts/timestamps. Exact framing is mandatory.

### 11.3 Sample clock and timestamps

Use a per-generation integer sample clock as the authoritative ordering and interval source:

- The first accepted sample has index 0; every callback advances by its exact sample count.
- Every assembled frame carries distinct first/end sample indexes, including when one callback produces several frames.
- Record UTC and Python monotonic anchors at stream start. Record PortAudio's `inputBufferAdcTime` separately; do not assume it shares Python's monotonic clock domain.
- Derive frame intervals from sample indexes and 16,000 Hz. Map to a monotonic estimate through a measured anchor/offset, and keep callback-arrival time for queue-age measurement.
- Derive v2 `occurredAt` from the UTC/sample anchor, not MQTT publication time, and expose timestamp uncertainty in diagnostics.
- Offline evaluation uses exact labeled sample indexes. Live phrase-end latency requires a synchronized playback/loopback test; ordinary logs cannot provide phrase ground truth.

### 11.4 Offline WAV conversion

The replay tool must inspect metadata and convert explicitly:

```python
audio, source_rate = soundfile.read(path, dtype="float32", always_2d=True)
mono = audio.mean(axis=1, dtype=np.float64).astype(np.float32)
mono_16k = scipy.signal.resample_poly(mono, 16000, source_rate)
pcm16 = np.clip(np.rint(mono_16k * 32768.0), -32768, 32767).astype(np.int16)
```

Reduce the resampling ratio by its greatest common divisor in the implementation. Record source metadata and conversion parameters in the replay report. The canonical smoke alignment used for the score table is exactly 16,000 zero samples before and after the converted clip, followed by every complete 1,280-sample frame; discard only the final incomplete tail. Warm the engine with 25 silence frames before that stream. Keep the full 0..1,279-sample phase sweep as a separate diagnostic/gate.

Do not use `Model.predict_clip(path)`: it assumes the file is already 16 kHz mono PCM16, reads interleaved stereo incorrectly, and its loop excludes a final exact-sized frame.

### 11.5 Gain and noise processing

- Do not normalize or apply per-frame AGC by default. Pumping changes the model distribution and the supplied quiet clips already cross in one alignment.
- Do not enable Speex noise suppression by default. It is not installed locally and must first win paired A/B validation on the frozen deployment dataset.
- Treat clipping ratio, RMS, and silence ratio as aggregate diagnostics only. Do not persist audio.
- Per the adopted integration decision in Section 2, stop listening before local TTS playback. Spring must send a new start only after playback plus a measured echo-tail guard. Add real TTS/echo audio to hard-negative evaluation.

## 12. Inference engine

Construct one model with both classifiers:

```python
model = openwakeword.Model(
    wakeword_models=[
        str(model_root / "ssafiya.onnx"),
        str(model_root / "nae_teon_kkeutnasseo.onnx"),
    ],
    inference_framework="onnx",
    device="cpu",
    vad_threshold=0,
    enable_speex_noise_suppression=False,
    ncpu=1,
    melspec_model_path=str(model_root / "melspectrogram.onnx"),
    embedding_model_path=str(model_root / "embedding_model.onnx"),
)
```

Those explicit frontend arguments are mandatory. Without them, the pinned library silently loads package-internal resources that may differ from the files checked by the deployment manifest. If a separate VAD is enabled, construct it with the explicit hash-checked `silero_vad.onnx` path as well.

For every exact frame:

```python
raw = model.predict(frame.pcm)  # no patience, threshold, or debounce arguments
scores = {
    "ssafiya": checked_float(raw["ssafiya"]),
    "nae_teon_kkeutnasseo": checked_float(raw["nae_teon_kkeutnasseo"]),
}
```

Reject missing, NaN, infinite, or materially out-of-range scores as inference faults. A tiny float tolerance may be clamped only after logging a metric.

The pinned library's `patience` code checks old prediction history, replaces an unconfirmed candidate with zero, and then appends that zero. It cannot bootstrap multi-frame patience from a cold sequence; `patience=2` produced zero detections for all eight supplied positives. Add a regression test ensuring the service calls `predict()` without these filtering arguments. The relevant pinned source is [`openwakeword/model.py`](https://raw.githubusercontent.com/dscripka/openWakeWord/368c03716d1e92591906a84949bc477f3a834455/openwakeword/model.py).

`Model.reset()` does not reset a built-in Silero VAD's recurrent state/deque or a Speex object's state. The baseline keeps `vad_threshold=0` and owns optional VAD separately. On an audio discontinuity, either rebuild the full engine or explicitly reset every stateful stage, clear all decision history, feed at least 25 exact silence frames, and suppress output until `EngineReady`. Never bridge feature context over lost audio.

## 13. Decision state machine

The detector is a pure class over `RawScores`, configuration, and an injected monotonic clock. It does not publish MQTT or mutate module lifecycle.

### 13.1 Policy fields per model

```text
trigger_threshold
evidence_window_frames
required_hits
vad_mode: off | observe | gate
vad_threshold                       # required only for gate
vad_context_oldest_lag_frames       # required only for gate
vad_context_newest_lag_frames       # required only for gate
vad_aggregate: max | mean           # required only for gate
```

Global arbitration fields:

```text
arbitration_frames                  # includes the first candidate frame
collision_margin                    # null means reject every dual candidate
ambiguous_suppression_frames
```

Optional release threshold/frames and cooldown exist only for shadow or a future continuously listening mode. They are not active in the one-detection-then-latch contract. Every active field must come from a hash-bound deployment profile produced by event-level calibration. Do not copy a generic 0.5 threshold from the older draft.

Development-only starting policy for the current artifacts:

| Field | `ssafiya` | `nae_teon_kkeutnasseo` |
|---|---:|---:|
| `trigger_threshold` | 0.8 | 0.99 |
| `evidence_window_frames` | 1 | 1 |
| `required_hits` | 1 | 1 |
| `vad_mode` | `observe` | `observe` |

The development global policy is `arbitration_frames=1`, `collision_margin=null`, and `ambiguous_suppression_frames=5`. Thus a single candidate fires, while same-frame dual candidates are rejected. These are smoke-test semantics, not production calibration.

### 13.2 Decision order

The exact baseline algorithm is:

1. Ignore it if generation is stale, module state is not `LISTENING`, or engine is warming.
2. Validate scores. If an ambiguity-suppression counter is active, advance the engine/VAD and metrics but do not append decision evidence; decrement the counter once for this frame, keep score histories empty, and return no candidate.
3. Otherwise append each score to that model's bounded raw history in frame order. A model has acoustic evidence when at least `required_hits` of the most recent, at most `evidence_window_frames`, scores are greater than or equal to `trigger_threshold`. Hits are k-of-n, not necessarily consecutive, and the history need not first contain a full window. Require `1 <= required_hits <= evidence_window_frames`.
4. If VAD mode is `gate`, the same model is a candidate only when its calibrated VAD context aggregate is greater than or equal to `vad_threshold`. `observe` records VAD but never blocks; `off` does not run VAD.
5. When the first candidate appears, open an arbitration window that includes the current frame and lasts exactly `arbitration_frames`. During that window, continue collecting both models' evidence and peak raw scores; do not emit early.
6. At the end of the window, if only one model ever became a candidate, emit that model.
7. If both became candidates, compute each peak's normalized exceedance:

   ```text
   margin = (peak_score - trigger_threshold) / (1 - trigger_threshold)
   ```

8. If `collision_margin` is non-null and the absolute margin difference is greater than or equal to it, select the larger margin. Otherwise classify the episode as ambiguous and emit nothing.
9. After ambiguity, clear evidence histories and set the suppression counter to exactly `ambiguous_suppression_frames`; Step 2 defines how those frames are consumed without accumulating latent evidence. After a selected event, the coordinator atomically latches it, closes capture, and makes all later queued candidates for that generation stale.

Comparisons are inclusive (`>=`). Reset all score, VAD, arbitration, release, and suppression histories on every new generation and discontinuity. Arbitration adds `(arbitration_frames - 1) * 80 ms` decision delay and must be included in latency calibration.

Never compare the raw 0.8-scale and 0.99-scale outputs directly. They are not calibrated probabilities.

### 13.3 VAD

VAD can reject non-speech noise but cannot distinguish confusable Korean phrases. It can also reject quiet/far-field speech. Keep it `observe` until a frozen dataset sweep proves a gate improves the required operating point.

When enabled, construct `openwakeword.vad.VAD(model_path=<hash-checked path>)` inside the inference worker. For each exact 1,280-sample frame call `vad.predict(frame.pcm, frame_size=640)` once; this advances recurrent state over two equal 40 ms chunks. Store the returned current-frame mean with the frame's end sample index in a bounded history. A gate aggregates the configured inclusive lag range, where lag 0 is the current frame. The manifest binds the lag range and `max`/`mean` aggregation. On reset, call `reset_states()`, clear the service-owned VAD history, and warm/suppress it with the engine.

Require `0 <= vad_context_newest_lag_frames <= vad_context_oldest_lag_frames < max_vad_history_frames`. Allocate exactly the configured bounded history capacity. Until every frame in the requested inclusive lag range exists after a reset, a gate fails closed and the model is not a candidate; never aggregate a partial or empty range.

Evaluate at least off, 0.2, 0.35, 0.5, and 0.65, including whispers, distance, overlapping speakers, music, impacts, and TTS echo. Do not rely on `Model.reset()` to clear VAD.

## 14. Configuration

Use a typed schema, reject unknown keys, validate ranges, and compute a canonical configuration SHA-256. Secrets are references, not values in YAML.

Illustrative development config:

```yaml
environment: development
room_number: A402
device_id: wake-mic-01
allow_unverified_models: true

audio:
  device: default
  sample_rate_hz: 16000
  channels: 1
  dtype: int16
  frame_samples: 1280
  queue_blocks: 8
  max_callback_samples: 4096  # development value; measure and bind on target hardware
  max_frame_age_ms: 160
  warmup_frames: 25

mqtt:
  host: localhost
  port: 1883
  protocol: "3.1.1"
  client_id: wakeword-A402-wake-mic-01
  clean_session: true
  keepalive_seconds: 30
  qos: 1
  retain: false
  connect_timeout_seconds: 10
  publish_ack_timeout_seconds: 3
  reconnect_min_seconds: 1
  reconnect_max_seconds: 30
  tls_enabled: false
  contract_version: legacy
  resume_listening_on_reconnect: false

runtime:
  inference_provider: cpu
  onnx_threads: 1
  max_consecutive_inference_errors: 3
  recovery_attempts: 3
  lock_root: /tmp/wakeword-locks  # development only; production requires a host-shared lock root
  state_store_path: /tmp/wakeword-state.sqlite3  # v2; production requires persistent local storage

artifacts:
  model_root: models
  manifest_path: null  # required and trusted in production; absent for current failed artifacts
  melspectrogram:
    path: melspectrogram.onnx
    sha256: ba2b0e0f8b7b875369a2c89cb13360ff53bac436f2895cced9f479fa65eb176f
  embedding:
    path: embedding_model.onnx
    sha256: 70d164290c1d095d1d4ee149bc5e00543250a7316b59f31d056cff7bd3075c1f
  vad:
    path: silero_vad.onnx
    sha256: a35ebf52fd3ce5f1469b2a36158dba761bc47b973ea3382b3186ca15b1f5af28

decision:
  arbitration_frames: 1
  collision_margin: null
  ambiguous_suppression_frames: 5
  max_vad_history_frames: 64

models:
  - id: ssafiya
    phrase: "싸피야"
    wire_status: call
    path: ssafiya.onnx
    sha256: af96d0d297eb6bbecbab43debe8af9fff2b914454f55b6ca123b2ba120711641
    trigger_threshold: 0.8
    evidence_window_frames: 1
    required_hits: 1
    vad_mode: observe
  - id: nae_teon_kkeutnasseo
    phrase: "내 턴 끝났어"
    wire_status: finish
    path: nae_teon_kkeutnasseo.onnx
    sha256: 95294f0a98464d3db9b19ad8a07a2d58ed485511757ce5d7583e478c43ae3473
    trigger_threshold: 0.99
    evidence_window_frames: 1
    required_hits: 1
    vad_mode: observe
```

The production config must set `allow_unverified_models: false` and load thresholds/policy from a passed deployment manifest, not duplicate them manually in YAML.

The v2 schema additionally requires a provisioned `controller_epoch`, positive maximum command age, nonnegative clock-skew allowance, finite broker queued-message lifetime, bounded event retry minimum/maximum, explicit outbox row/byte limits and reserved capacities, `clean_session: false` (or the MQTT 5 persistent-session equivalent), and a persistent local `state_store_path`. None may silently inherit a development default. The configured epoch must match the durable store; changing it requires the coordinated idle reset in Section 6.

Validate numeric bounds, including `0 < trigger_threshold < 1`, `1 <= required_hits <= evidence_window_frames`, `arbitration_frames >= 1`, nonnegative suppression values, positive queue/history/callback bounds, `frame_samples == 1280`, `sample_rate_hz == 16000`, and unique model IDs/wire statuses. A non-null collision margin must be in `[0,1]`. For gated VAD require `0 <= newest_lag <= oldest_lag < max_vad_history_frames`; reject incomplete ranges and reject inactive VAD fields in strict configs. Validate release/cooldown fields only when a non-latching shadow/continuous mode activates them. Production also rejects a lock root that is not shared by every possible replica on the host.

### 14.1 Production deployment manifest

Step 1 must add a checked-in `deployment-manifest.schema.json` with `additionalProperties: false` at every owned object. The generated production manifest must contain these required groups:

| Group | Required fields |
|---|---|
| Identity | `schemaVersion`, `manifestId`, `manifestRevision`, `createdAt`, `expiresAt`, `qualityTargetMet` |
| Provenance | training run/config/data revisions, source commit, CI/build run URL or immutable ID |
| Runtime | exact openWakeWord commit, ONNX Runtime version, Python ABI/platform, inference provider/thread policy |
| Artifacts | for every classifier/frontend/VAD/final-evaluation report/report schema: role, relative path, byte length, SHA-256, plus ONNX names/dtypes/shapes/opset where applicable |
| Mapping | model ID, exact phrase, wire status, classifier artifact ID |
| Per-model evaluation | for each mapped model: model ID, final evaluation-report artifact ID, `qualityTargetMet`, and every applicable gate ID/result |
| Decision profile | every active field from Section 13, arbitration fields, canonical profile SHA-256 |
| Evaluation | calibration/final-test dataset revisions, disjoint-split declaration, sample/speaker/session/device counts, negative hours, target hardware/microphone |
| Metrics | point values, numerator/denominator or hours/events, confidence method and bound for every release gate, latency/timing/drop/phase-sweep results |
| Pipeline gates | explicit pass/fail records for latency, timing, drops, phase sweep, cross-model arbitration, and every other non-model release gate |
| Approvals | MQTT contract revision, quality target revision, privacy approval ID, dataset-license approval ID |

Rules:

- Each classifier mapping must have exactly one final per-model evaluation record and a hash-bound report artifact. That record contains `modelId`, `evaluationReportArtifactId`, `qualityTargetMet`, and `gateResults[]`; each gate result includes the approved `gateId`, comparator/limit, measured value, applicable confidence bound, numerator/denominator or hours, and `passed`.
- Top-level `qualityTargetMet` must be the pipeline-computed conjunction of every per-model `qualityTargetMet` and every pipeline gate, never a hand-edited flag. Schema validation rejects missing, duplicate, unknown, or non-passing required gate IDs. Runtime recomputes this Boolean conjunction from the signed manifest records and verifies all referenced report hashes before readiness.
- The current `*.training.json` and `*.verification.json` files are audit inputs, not production authority. A release pipeline may transform their evidence into the required final reports, but production trusts only the signed/digest-pinned manifest and its hash-bound report artifacts.
- `expiresAt` is mandatory. Reject expired manifests and manifest IDs on the deployed revocation list.
- Paths are relative to the manifest directory and must resolve within the approved read-only model root.
- Runtime config may select environment/broker/device secrets, but may not override a manifest model hash, mapping, or detection policy in production.
- A manifest stored beside replaceable models provides integrity bookkeeping, not provenance. Production must either verify a release-system signature over RFC 8785 canonical JSON or receive the expected manifest SHA-256 from separately trusted immutable release metadata. Pinning a digest inside the same writable directory is insufficient.
- The service recomputes the canonical decision-profile hash and all artifact hashes before readiness, and exposes the manifest/profile IDs in health/logs.
- Any runtime, frontend, classifier, policy, sample-rate/framing, or preprocessing change invalidates the evaluation binding and requires a new manifest.

## 15. Failure handling

| Failure | Required response |
|---|---|
| Invalid config/model/hash | Fail startup; never subscribe or publish `listening`. |
| MQTT initially unavailable | Stay not-ready, retry with bounded backoff; do not capture. |
| MQTT disconnect while listening | Stop capture/decisions, invalidate queued generation, reconnect and publish `idle`; require a fresh start. Never auto-resume in the legacy profile. |
| Audio device unavailable on start | Apply the pending-start invariant, enter `FAULT`, publish `idle` if possible, expose reason without device secrets. |
| Audio overflow or sequence/timestamp gap | Flush queue and tail, reset/rebuild all state, warm, then resume; never infer across gap. |
| Inference exception/NaN | Drop current generation and apply the pending-start invariant only in `ARMING_START`; recovery/listening never rewrites an accepted start. Run bounded recovery and enter `FAULT` after configured consecutive failures. |
| Publish/PUBACK timeout | Keep the serialized logical status pending and retry with bounded backoff. A detection remains in the durable outbox until Spring's matching application acknowledgement, regardless of broker PUBACK; do not reopen capture. |
| Legacy publisher queue full or v2 outbox reservation/storage failure | In `ARMING_START`, apply the pending-start invariant when durable storage is usable; in `RECOVERING_AUDIO`, close/tombstone the accepted session without rewriting its start. Stop capture and enter `FAULT`. Never supersede an accepted detection. V2 refuses a new start before arming when reserved terminal/event quota is unavailable; physical store failure remains fail-closed until recovery. |
| Malformed/retained command | Ignore, metric, sanitized warning. |
| Coordinator or inference-control queue full | Apply the pending-start invariant only in `ARMING_START`; recovery never rewrites an accepted start. Then treat as a service fault. Control, lifecycle, or detection events must not be silently lost. |
| SIGTERM/SIGINT | Stop accepting commands, apply the pending-start invariant only in `ARMING_START`, close/tombstone any nonlatched `LISTENING`/`RECOVERING_AUDIO` session without rewriting its accepted start, and close audio. Legacy publishes `idle`; v2 publishes `idle` only with no latch. Preserve every v2 latch and retry any unacknowledged event within the deadline without publishing a later `idle`. Disconnect and join threads within the shutdown deadline. |

Recovery loops must be bounded and observable. Do not spin, allocate unbounded queues, or repeatedly reopen a failing device without backoff.

Mapping `FAULT` to legacy `idle` is only a fail-closed compatibility fallback and must never overwrite a durable v2 latched event. Production is blocked until Spring/operations monitor a separate authenticated readiness/health signal and distinguish unhealthy idle from healthy idle.

## 16. Observability, privacy, and security

### 16.1 Structured logs

Emit JSON logs containing only operational metadata:

```text
timestamp UTC
level
service/version/config revision
room number/device ID
event/command/listen-session ID when available
old state/new state/reason
model ID/hash prefix/score/threshold for accepted or ambiguous decisions
audio sequence and discontinuity counters
MQTT connection and PUBACK result
error type and sanitized message
```

Never include PCM, encoded audio, credentials, full command payloads, or arbitrary exception objects that may contain secret URLs.

### 16.2 Metrics

At minimum expose:

```text
wakeword_state{room,status} 0|1
wakeword_ready 0|1
wakeword_audio_frames_total
wakeword_audio_dropped_frames_total
wakeword_audio_discontinuities_total{reason}
wakeword_audio_callback_duration_seconds
wakeword_inference_duration_seconds{model_or_stage}
wakeword_score_histogram{model}             # optional, bounded labels
wakeword_candidate_total{model,outcome}
wakeword_detection_total{model,status}
wakeword_collision_total
wakeword_mqtt_connected 0|1
wakeword_mqtt_command_total{command,outcome}
wakeword_mqtt_publish_total{status,outcome}
wakeword_recovery_total{component,outcome}
```

Do not put event IDs, filenames, exception text, or other unbounded values in metric labels.

### 16.3 Privacy and security

- Normal operation processes transient audio/features in memory only and persists no raw or derived recoverable audio.
- Disable core dumps or ensure they cannot capture PCM buffers.
- Document microphone-active state to the user interface and align it with accepted `start-listen`/`stop-listen` commands.
- Evaluation capture requires explicit consent, access controls, purpose, retention duration, and deletion procedure before recording.
- Use least-privilege broker ACLs: subscribe only to this room's three command topics plus the v2 acknowledgement topic when enabled, and publish only its status topic.
- Use TLS certificate verification outside isolated local development.
- Run as a non-root user with access only to the required audio device and read-only models/secrets.

## 17. Testing and quality release gates

### 17.1 Unit tests

Unit tests must cover:

- Arbitrarily fragmented and batched PCM input emits exact 1,280-sample frames.
- Odd bytes, wrong dtype/channels/rate, and format changes are rejected.
- Tail clearing and sequence gaps cause a full discontinuity reset.
- The worker-owned reset/warm handshake reaches `EngineReady`; at least 25 warm-up frames emit nothing and produce repeatable steady-state silence scores.
- The callback enqueues immutable arbitrary-sized `AudioBlock` objects while only the inference worker mutates the assembler/model/VAD.
- Per-frame sample indexes/timestamps remain correct when one callback block yields zero, one, or several frames; stale-age handling resets rather than replaying backlog.
- Every state transition and every idempotent duplicate in Section 7.
- Stale generation detections are ignored.
- Threshold equality, below/above boundaries, release/rearm, cooldown, and fake monotonic time.
- Dual-candidate normalized-margin selection and ambiguous rejection.
- Sustained dual-candidate audio cannot accumulate hidden evidence or fire on the first frame after ambiguity suppression.
- A gated VAD range fails closed until every configured lag is populated; range ordering/capacity errors are rejected.
- NaN/infinite/missing/out-of-range score behavior.
- Bounded audio/control/publisher queue overflow behavior.
- MQTT empty/`{}`/malformed/oversized/retained command handling.
- V2 exact command retries during `PROCESSING` return `in_progress`; completed accepted/rejected retries replay the cached terminal bytes/revision/outcome/reason without executing again.
- Request-status exact retries replay the cached snapshot/rejection, while same-ID/different-body requests return `id_conflict` without changing state or the original cache.
- Parsed status JSON has exactly the adopted lower-case semantic field, and the module's canonical serializer remains compact/stable.
- MQTT callback and publisher exceptions never block the audio callback.
- The engine calls `model.predict(frame)` without built-in patience/debounce arguments.
- The engine loads the exact hash-checked explicit mel/embedding/VAD paths, not package defaults.
- Startup hash/tensor/manifest/schema/trust/provider checks, including expiry, per-model report/gate completeness, aggregate quality conjunction, and runtime/policy mismatch.
- Worker-control priority and `EnableDecisions` ordering prevent audio from advancing before enable; reset/stop drains stale queued generations.
- Transaction failures at each latch/outbox boundary never publish a non-durable detection; restart restores the same event ID, status revision, and bytes.
- Stop, disconnect, capture/model failure, legacy publisher failure, v2 store failure/recovery, and shutdown during `ARMING_START` never leave a start in `PROCESSING`; exact retries eventually replay cached `rejected`/`interrupted`. Stop-caused cancellation preserves the required two-response order.
- During `RECOVERING_AUDIO`, exact original-start retries replay cached `accepted`, and stop/disconnect/fault never rewrite that terminal response; recovery completion returns to `LISTENING` through a new asynchronous status revision.
- Worker-control and v2 outbox reservations prevent a start from becoming `accepted` unless `EnableDecisions` and terminal/event capacity are guaranteed.

### 17.2 Local ONNX integration tests

Run both models in one engine through the production framing path.

For every `test_audio/*.wav` file:

1. Inspect metadata.
2. Convert the whole clip to 16 kHz mono PCM16.
3. Reset and deterministically warm the engine.
4. Add the canonical 16,000-sample leading/trailing silence for the baseline report.
5. Stream through randomized input fragment sizes into `PcmFrameAssembler`.
6. Assert the expected model crosses its development threshold at least once.
7. Assert the other model never crosses its threshold.
8. Assert no duplicate module event is emitted for the listening generation.

Also run onset offsets from 0 through 1,279 samples, including at least 10 ms increments. Record min/max score and pass fraction; do not hide failures by choosing one padding alignment.

Do not assert exact scores across a runtime upgrade. Store model/frontend/runtime/config hashes with the report and use justified numeric ranges.

### 17.3 MQTT/system tests

Use a real local Mosquitto broker in a test container/process and a fake audio source. Verify:

- All four legacy topics, the v2 acknowledgement topic, and their exact versioned JSON Schemas.
- V2 exact command retries are no-ops that return `in_progress` only in `ARMING_START` and replay the exact cached terminal response afterward, including throughout audio recovery and after a lost rejection. New-ID semantic duplicates are reported as `duplicate`; ID/body conflicts, sequence conflicts, stale sequences, session reuse, and mismatched sessions are rejected after restart as well as in-process.
- Request-status snapshot/rejection replay, duplicate IDs, ID/body conflicts, expiry, and restart behavior follow the exact rules in Section 6.
- Legacy tests cover only immediate duplicate start while listening and stop while idle, and explicitly demonstrate that cross-session delayed duplicates cannot be made reliable without v2.
- Retained commands are ignored.
- Start while listening does not reset inference.
- Detection atomically stops audio and latches one result.
- `request-status` returns each stable state without changing it.
- Broker loss during listening stops decisions; reconnect resubscribes, publishes `idle`, and requires a fresh start.
- Interrupt `ARMING_START` separately with stop, broker loss, process signal, audio/model failure, control-capacity failure, and publisher/store-capacity failure; each pending start becomes a durable terminal rejection and never returns `in_progress` forever.
- Drive `LISTENING -> RECOVERING_AUDIO`, then test exact original-start retry, different-ID start, stop, disconnect, fault, and successful recovery; none may change the cached original acceptance.
- Kill the module before/after outbox commit, publisher enqueue, broker PUBACK, and application acknowledgement. Every committed detection eventually uses the same event ID/revision/payload; Spring performs downstream work once and re-acknowledges duplicates.
- Delayed duplicate start/stop commands from older sessions cannot alter a v2 current session; mismatched session IDs are rejected.
- Malformed traffic cannot crash or change state.
- Graceful legacy shutdown publishes `idle`. V2 shutdown preserves both acknowledged and unacknowledged latches, emits no later `idle`, and restores the same state/outbox after restart; an accepted stop before shutdown clears it.
- Separate room/device OS locks prevent two processes or containers from claiming the same room or aliases of the same physical device, including the same device configured under different room IDs.

### 17.4 Robustness corpus

The eight provided files are smoke fixtures only. Build a speaker/session/device-disjoint corpus representing actual rooms:

- At least 30 unseen Korean speakers and at least 20 independently recorded examples of each target phrase per speaker across conditions, unless a documented power/interval calculation requires more.
- Near-field and far-field distances, off-axis speech, sitting/standing, quiet and loud delivery.
- Multiple actual room/microphone units, reverberation, HVAC, table impacts, pieces/cards, music, and overlapping conversation.
- Every hard negative listed in `../configs/korean_office.json`, plus naturally mined confusions.
- Hours of ordinary Korean conversation, game play, silence, noise, and system TTS/playback with no target phrase.
- Gain, clipping, SNR, RIR, speed, codec, dropped-frame, and phase-offset perturbations, with real recordings weighted highest.
- At least 2,000 independently sourced hard-negative utterances and enough opposite-keyword trials to bound cross-keyword confusion; do not inflate counts with correlated augmentations.

Split by speaker, recording session, room/device, and source before tuning. No speaker or base recording may leak between train, calibration, and final test through augmented copies.

### 17.5 Calibration procedure

Calibrate the complete frozen streaming pipeline, not isolated classifier rows:

1. Freeze model/frontend hashes and runtime commit.
2. Freeze a calibration set and a final untouched test set.
3. Sweep per-model trigger/release thresholds, evidence window/hits, VAD policy/threshold, collision margin, cooldown, and any experimental phase ensemble.
4. Match emitted events to labeled phrase intervals. Count one acoustic episode once, not every above-threshold frame.
5. Constrain false activations/hour and hard-negative error first; among eligible policies maximize the worst speaker/room/noise recall, not only global average.
6. Report event recall, clean/noisy/far-field recall, hard-negative false-event rate, cross-keyword confusion, false activations/hour, duplicates, and phrase-end-to-event latency.
7. Report uncertainty for every rate gate: cluster-bootstrap by speaker/session/device for recall and precision, one-sided binomial bounds for hard-negative/confusion rates, and a one-sided Poisson bound for false activations/hour. Report effective independent units, not only augmented clip counts.
8. Write the selected policy and all hashes/metrics/dataset revision into `deployment-manifest.json`.
9. Evaluate exactly once on the untouched final test set. Any retuning makes it calibration data and requires a new final test set.

With zero observed false events, about 6 representative negative hours are needed merely to put the one-sided 95% Poisson upper bound below 0.5/hour; about 30 hours are needed to put it below 0.1/hour. More varied hours are preferable to repeating one quiet recording.

Pre-register scenario weights before computing mixed precision; precision without prevalence/weighting is not portable. Shadow-mode false negatives require explicit ground truth from scheduled prompted trials or a consented user-feedback mechanism. Absence of an activation in passive, unlabeled audio is not measurable as a false negative, and normal shadow mode must not retain raw audio merely to create labels.

### 17.6 Production acceptance targets

These proposed robust targets need product owner approval, but they are intentionally stricter than the failed training floor:

| Metric | Proposed gate |
|---|---:|
| Overall event recall per phrase | >= 95% |
| Noisy/far-field event recall per phrase | >= 90% |
| One-sided 95% lower bound for overall recall | >= 90% |
| Hard-negative false-event rate | <= 1% |
| Hard-negative one-sided 95% upper bound | <= 2% |
| Cross-keyword confusion | <= 0.5% |
| Cross-keyword one-sided 95% upper bound | <= 1% |
| False activations/hour point estimate | <= 0.1/hour |
| False activations/hour one-sided 95% upper bound | <= 0.5/hour |
| Scenario-mixed precision (report prevalence) | >= 98% |
| Scenario-mixed precision one-sided 95% lower bound | >= 95% |
| Phrase-end-to-event latency p95 | <= 400 ms |
| Per-frame pipeline time p99 on target hardware | < 40 ms |
| Dropped frames in an 8-hour target-hardware soak | 0 |
| Duplicate events per listen session | 0 at module boundary |

A product owner may change the numbers, but no agent may remove the concept of a frozen, event-level, confidence-bounded gate.

### 17.7 Current release verdict

```text
Code implementation: allowed
Offline/local integration: allowed
Shadow-mode room evaluation: allowed after privacy approval
Production MQTT detection publishing: BLOCKED
```

Unblock only when:

- both retrained model reports pass agreed targets;
- both runtime verification reports exist and pass;
- a final deployment manifest exists and matches every loaded hash;
- phase-offset and realistic room tests pass;
- MQTT v2 (or an equivalent persisted identity protocol) and the monitored health contract are approved and contract-tested on both sides;
- dataset licensing is acceptable for the intended use;
- privacy/retention and operational runbooks are approved.

## 18. Implementation sequence across turns

The implementation should be delivered in small steps. At the end of every step, the implementing agent must list changed files, commands run, exact test results, and remaining blockers. It must not mark a step complete when its exit test is skipped.

### Step 0: Contract and target repository freeze

Deliver:

- Confirm the service repository/location and packaging model.
- Confirm room identifier, broker protocol/version, authentication/TLS, microphone device, and legacy versus v2 payload.
- Record the adopted latching, auto-stop, post-`finish` restart owner, QoS, retain, reconnect, acknowledgement, and error policies.

Exit: Spring and Wake Word owners approve the externally visible contract, or implementation is explicitly limited to a legacy local harness.

### Step 1: Reproducible scaffold and artifact validator

Deliver:

- Typed config, dependency lock, model manifest schema, hash/ONNX contract validator.
- Manifest trust/digest verification, health model, exclusive device lock, and production quality gate.
- Unit tests for all validation failures.

Exit: current artifacts start only with the development override; production mode rejects them with a precise reason.

### Step 2: Offline framing, engine, and replay

Deliver:

- Worker-owned `PcmFrameAssembler`/engine, control handshake, explicit frontend paths, and deterministic 25-frame warm-up/reset.
- Correct WAV converter, canonical padding, sample-clock timestamps, and production-path replay CLI.
- Both-model smoke and full phase-offset reports for all eight clips.

Exit: fragmented replay equals contiguous replay, expected single-alignment smoke events pass, and phase fragility is reported rather than hidden.

### Step 3: Pure detector and coordinator

Deliver:

- Executable raw-score k-of-n FSM, cross-frame arbitration/collision policy, VAD context semantics, generation invalidation, and complete lifecycle state machine.
- Fake clock, fake engine/audio/publisher tests covering every transition and race.

Exit: no built-in patience/debounce is used; one listen generation can emit at most one accepted event.

### Step 4: Live audio adapter

Deliver:

- PortAudio/sounddevice adapter, device probe, bounded callback queue, overflow/discontinuity recovery.
- Live diagnostic command that reports aggregate levels, frame timing, drops, and scores without saving audio.

Exit: target microphone runs for at least one hour with p99 timing under budget and zero dropped frames in the test environment.

### Step 5: MQTT integration

Deliver:

- Paho adapter, exact topics/payload, QoS/PUBACK handling, fail-closed reconnect/resubscribe, v2 ordering/IDs/application acknowledgement, transactional outbox, and sanitized parsing.
- Mosquitto contract/system tests including cross-session/out-of-order commands, retained commands, disconnect/process kill during detection, pending-event replay/dedup/ack, and conditional graceful shutdown.

Exit: all state/MQTT scenarios in Sections 7 and 17.3 pass repeatedly.

### Step 6: Resilience, observability, and packaging

Deliver:

- Metrics, structured logging, liveness/readiness, bounded recovery, signal handling.
- Single-process container/systemd deployment, non-root audio permissions, TLS/secrets, read-only model mount.
- Operations runbook for device/broker/model failures and rollback.

Exit: fault injection and 8-hour soak pass on target hardware. This still does not unblock detection publishing with the current models.

### Step 7: Data, retraining, calibration, and shadow mode

Deliver:

- Approved recording/evaluation protocol and dataset manifests.
- New models trained with realistic noise, hard negatives, and frame-offset augmentation.
- Frozen event-level calibration/final-test reports and deployment manifest.
- Shadow deployment with false-positive/false-negative review and no raw-audio retention outside approved evaluation capture.

Exit: every approved production gate passes with confidence intervals and representative data.

### Step 8: Controlled production enablement

Deliver:

- Versioned manifest/config rollout, canary room, alert thresholds, rollback trigger.
- Spring end-to-end verification for `call` QnA and `finish` turn analysis.

Exit: canary remains within quality/SLO limits for the agreed observation period before wider rollout.

## 19. Definition of done

`WakeWordModule` is complete only when all applicable items are true:

- [ ] One process exclusively owns one configured microphone and room.
- [ ] The exact four legacy MQTT topics/lower-case status payload and the production v2 acknowledgement extension are contract-tested as applicable.
- [ ] Start, stop, request-status, latching, auto-stop, disconnect/fresh-start behavior, duplicates, and reconnect follow Section 7.
- [ ] Model/frontend hashes and tensor contracts are checked before readiness.
- [ ] Production refuses missing/failed/stale quality manifests.
- [ ] Audio is exact 16 kHz mono PCM16 and inference receives only 1,280-sample frames.
- [ ] One worker exclusively owns all stateful inference objects.
- [ ] No openWakeWord built-in patience/debounce filtering is used.
- [ ] Warm-up and every discontinuity suppress stale decisions.
- [ ] The supplied WAVs are converted correctly and replayed through the production path.
- [ ] Full frame-offset reports are retained as build artifacts.
- [ ] Bounded queues, broker loss, audio loss, inference error, and shutdown are tested.
- [ ] Raw audio and secrets never enter normal logs, MQTT, metrics, or persistent storage.
- [ ] Target hardware timing and soak gates pass.
- [ ] Real, deployment-representative event-level accuracy gates pass on an untouched test set.
- [ ] MQTT v2 ordering, IDs, transactional detection outbox, and application acknowledgement are approved and durably implemented on both sides, or an explicitly specified persisted protocol provides equivalent guarantees. Legacy state-transition idempotency and broker PUBACK alone are not sufficient.
- [ ] A monitored authenticated health/readiness contract distinguishes `FAULT` from healthy legacy `idle`.
- [ ] Dataset license and privacy reviews are complete for the intended deployment.

## 20. Decisions still required from the owners

These questions do not block Steps 1-3, but they block production integration:

1. What is the exact `roomNumber` format, and is deployment strictly one service instance per room?
2. Which broker/protocol/port, client authentication, CA, and ACLs apply in each environment?
3. Will Spring approve empty/whitespace/`{}`-only legacy commands, JSON status encoding, QoS 1, `retain=false`, lower-case payloads, auto-stop, and latched detection states?
4. Will Spring accept the v2 ordering/identity fields, acknowledgement topic, and durable processing/outbox responsibilities needed for reliable correlation and delivery?
5. Which exact microphone/device/audio server will production use, and can it deliver stable 16 kHz mono PCM16?
6. What distances, noise levels, rooms, speaker population, and false-activation budget define the real operating domain?
7. Who owns recording consent, dataset retention/deletion, and the ACAV non-commercial license decision?
8. Can Spring issue a fresh start after reconnect as the safe default, or will an authoritative reconciliation protocol be added before automatic resume?
9. Which authenticated health/readiness channel will let Spring/operations distinguish internal `FAULT` from legacy `idle`?
10. Will Spring/QnA guarantee that `start-listen` is sent only after TTS playback and the measured echo tail end?
11. After `finish`, which MC/Spring transition sends the next fresh `start-listen`, and what proves turn analysis is complete before it does so?

Until these are answered, preserve the adopted defaults in this document and label them as implementation decisions in code and tests.

## 21. References

- [Completed Server to Room MQTT Topic Reference](https://app.notion.com/p/3ae85e9160e68183af35cb110de062b5)
- [Draft Wake Word microservice MVP design](https://app.notion.com/p/3ad85e9160e6801ea0e6f594252f61d0)
- [Completed requirements definition](https://app.notion.com/p/39c85e9160e680589036fc082c59fa7e)
- [Pinned openWakeWord source](https://github.com/dscripka/openWakeWord/tree/368c03716d1e92591906a84949bc477f3a834455)
- [Pinned openWakeWord usage and evaluation guidance](https://raw.githubusercontent.com/dscripka/openWakeWord/368c03716d1e92591906a84949bc477f3a834455/README.md)
- [ONNX Runtime execution providers](https://onnxruntime.ai/docs/execution-providers/)
- [ONNX Runtime thread management](https://onnxruntime.ai/docs/performance/tune-performance/threading.html)
- [Eclipse Paho MQTT Python client](https://eclipse.dev/paho/files/paho.mqtt.python/html/client.html)
