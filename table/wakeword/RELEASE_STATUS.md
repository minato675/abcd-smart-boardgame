# Release status

The implementation is development/shadow-capable and production-blocked by
design.

- `ssafiya` and `nae_teon_kkeutnasseo` are loaded through the pinned
  openWakeWord frontend with explicit hash-checked ONNX paths.
- The current training evidence marks `quality_target_met: false`; the second
  runtime verification report and final deployment manifest are absent.
- `reports/replay-smoke-2026-08-03.json` is an eight-clip functional smoke and
  full 1,280-phase-offset report, not a representative quality evaluation.
  The aligned smoke pass is true, but phase stability is false: the supplied
  fixtures measure 83.67% (`ssafiya_test1`), 98.28% (`ssafiya_test4`), and
  10.78% (`turn_test2`) above threshold across the phase sweep.
- Production startup requires a trusted quality-passed manifest and refuses
  the current model bundle before MQTT subscription/publication.
- Live microphone timing/soak, representative event-level calibration,
  privacy/dataset approvals, Spring v2 approval, and an authenticated health
  channel remain release gates outside this artifact-only workspace.
