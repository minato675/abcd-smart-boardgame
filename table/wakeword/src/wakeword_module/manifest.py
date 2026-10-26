"""Artifact integrity, ONNX tensor, and production quality-gate validation."""

from __future__ import annotations

import argparse
from dataclasses import dataclass, replace
from hashlib import sha256
import json
from pathlib import Path
import os
import re
from typing import Any
from datetime import datetime, timezone

from .config import ConfigError, WakeWordConfig, load_config
from .contracts import ContractError, parse_uuid, parse_utc_timestamp, strict_json_loads


class ArtifactValidationError(RuntimeError):
    pass


PINNED_OPENWAKEWORD_COMMIT = "368c03716d1e92591906a84949bc477f3a834455"
_MANIFEST_KEYS = {
    "schemaVersion", "manifestId", "manifestRevision", "createdAt", "expiresAt",
    "qualityTargetMet", "provenance", "runtime", "artifacts", "mapping",
    "perModelEvaluation", "decisionProfile", "evaluation", "metrics", "pipelineGates",
    "approvals",
}


@dataclass(frozen=True, slots=True)
class ArtifactValidationReport:
    production_ready: bool
    model_quality: str
    config_revision: str
    artifact_hashes: dict[str, str]
    warnings: tuple[str, ...]


def sha256_file(path: Path, *, chunk_size: int = 1024 * 1024) -> str:
    digest = sha256()
    try:
        with path.open("rb") as handle:
            while chunk := handle.read(chunk_size):
                digest.update(chunk)
    except OSError as exc:
        raise ArtifactValidationError(f"cannot read artifact: {path}") from exc
    return digest.hexdigest()


def _regular_file(path: Path, *, allow_symlink: bool = False) -> None:
    if path.is_symlink() and not allow_symlink:
        raise ArtifactValidationError(f"artifact must not be a symlink: {path}")
    if not path.is_file():
        raise ArtifactValidationError(f"artifact is not a regular file: {path}")


def _check_hash(path: Path, expected: str) -> str:
    if len(expected) != 64 or any(char not in "0123456789abcdef" for char in expected.lower()):
        raise ArtifactValidationError(f"invalid SHA-256 for {path}")
    actual = sha256_file(path)
    if actual != expected.lower():
        raise ArtifactValidationError(f"SHA-256 mismatch for {path}: expected {expected}, got {actual}")
    return actual


def _onnx_contract(path: Path, *, classifier_id: str | None = None) -> dict[str, Any]:
    try:
        import onnx
    except ImportError as exc:
        raise ArtifactValidationError("onnx is required for artifact validation") from exc
    try:
        model = onnx.load(str(path), load_external_data=False)
        onnx.checker.check_model(model)
    except Exception as exc:  # ONNX checker exceptions are sanitized below.
        raise ArtifactValidationError(f"ONNX checker rejected {path}") from exc
    if not model.graph.input or not model.graph.output:
        raise ArtifactValidationError(f"ONNX graph has no input/output: {path}")
    input_value = model.graph.input[0]
    output_value = model.graph.output[0]
    input_shape = [dim.dim_value if dim.dim_value else dim.dim_param for dim in input_value.type.tensor_type.shape.dim]
    output_shape = [dim.dim_value if dim.dim_value else dim.dim_param for dim in output_value.type.tensor_type.shape.dim]
    result = {
        "irVersion": model.ir_version,
        "opset": next((item.version for item in model.opset_import if item.domain == ""), None),
        "inputName": input_value.name,
        "inputShape": input_shape,
        "inputDtype": input_value.type.tensor_type.elem_type,
        "outputName": output_value.name,
        "outputShape": output_shape,
        "outputDtype": output_value.type.tensor_type.elem_type,
    }
    if classifier_id is not None:
        if input_value.name != "input" or output_value.name != classifier_id:
            raise ArtifactValidationError(f"{path} has unexpected classifier tensor names")
        if len(input_shape) != 3 or input_shape[1:] != [16, 96]:
            raise ArtifactValidationError(f"{path} must accept [batch,16,96]")
        if len(output_shape) != 2 or output_shape[1] != 1:
            raise ArtifactValidationError(f"{path} must produce [batch,1]")
        if result["inputDtype"] != 1 or result["outputDtype"] != 1:
            raise ArtifactValidationError(f"{path} must use float32 tensors")
    return result


def _manifest_quality_check(config: WakeWordConfig, manifest_path: Path) -> None:
    _regular_file(manifest_path)
    try:
        manifest = strict_json_loads(manifest_path.read_bytes(), max_bytes=16 * 1024 * 1024)
    except (OSError, ContractError) as exc:
        raise ArtifactValidationError("production deployment manifest is not valid JSON") from exc
    if not isinstance(manifest, dict):
        raise ArtifactValidationError("production deployment manifest must be an object")
    missing = _MANIFEST_KEYS - set(manifest)
    unknown = set(manifest) - _MANIFEST_KEYS
    if missing or unknown:
        raise ArtifactValidationError(
            "deployment manifest schema fields are invalid"
            + (f"; missing={','.join(sorted(missing))}" if missing else "")
            + (f"; unknown={','.join(sorted(unknown))}" if unknown else "")
        )
    trusted_digest = os.environ.get("WAKEWORD_TRUSTED_MANIFEST_SHA256")
    if not trusted_digest:
        raise ArtifactValidationError("production requires an externally trusted manifest digest")
    actual_digest = sha256_file(manifest_path)
    if actual_digest != trusted_digest.lower():
        raise ArtifactValidationError("deployment manifest does not match trusted digest")
    if manifest.get("qualityTargetMet") is not True:
        raise ArtifactValidationError("deployment manifest qualityTargetMet is not true")
    if (
        isinstance(manifest.get("schemaVersion"), bool)
        or not isinstance(manifest.get("schemaVersion"), int)
        or manifest["schemaVersion"] < 1
        or isinstance(manifest.get("manifestRevision"), bool)
        or not isinstance(manifest.get("manifestRevision"), int)
        or manifest["manifestRevision"] < 1
    ):
        raise ArtifactValidationError("deployment manifest version fields are invalid")
    try:
        parse_uuid(manifest["manifestId"], "manifestId")
        created_at = parse_utc_timestamp(manifest["createdAt"], "createdAt")
        expires_at = parse_utc_timestamp(manifest["expiresAt"], "expiresAt")
    except ContractError as exc:
        raise ArtifactValidationError("deployment manifest identity or timestamps are invalid") from exc
    if expires_at <= datetime.now(timezone.utc) or expires_at <= created_at:
        raise ArtifactValidationError("deployment manifest is expired or has an invalid lifetime")
    revoked = {item.strip() for item in os.environ.get("WAKEWORD_REVOKED_MANIFEST_IDS", "").split(",") if item.strip()}
    if str(manifest["manifestId"]) in revoked:
        raise ArtifactValidationError("deployment manifest is revoked")
    for required in ("expiresAt", "artifacts", "mapping", "perModelEvaluation", "pipelineGates"):
        if required not in manifest:
            raise ArtifactValidationError(f"deployment manifest missing {required}")
    provenance = manifest.get("provenance")
    runtime = manifest.get("runtime")
    decision_profile = manifest.get("decisionProfile")
    approvals = manifest.get("approvals")
    if not isinstance(provenance, dict) or provenance.get("configRevision") != config.config_revision:
        raise ArtifactValidationError("deployment manifest config revision does not match runtime config")
    if not isinstance(runtime, dict) or (
        runtime.get("openWakeWordCommit") != PINNED_OPENWAKEWORD_COMMIT
        or runtime.get("provider") != "CPUExecutionProvider"
        or runtime.get("threads") != config.runtime.onnx_threads
    ):
        raise ArtifactValidationError("deployment manifest runtime does not match the pinned CPU runtime")
    if not isinstance(approvals, dict) or any(
        not isinstance(approvals.get(field), str) or not approvals[field]
        for field in ("mqttContractRevision", "qualityTargetRevision", "privacyApprovalId", "datasetLicenseApprovalId")
    ):
        raise ArtifactValidationError("deployment manifest approvals are incomplete")
    if not isinstance(decision_profile, dict):
        raise ArtifactValidationError("deployment manifest decision profile is invalid")
    if (
        decision_profile.get("arbitrationFrames") != config.decision.arbitration_frames
        or decision_profile.get("collisionMargin") != config.decision.collision_margin
        or decision_profile.get("ambiguousSuppressionFrames") != config.decision.ambiguous_suppression_frames
        or not isinstance(decision_profile.get("models"), list)
        or len(decision_profile["models"]) != len(config.models)
    ):
        raise ArtifactValidationError("deployment manifest decision policy does not match runtime config")
    profile_by_model = {
        item.get("modelId"): item for item in decision_profile["models"] if isinstance(item, dict)
    }
    if len(profile_by_model) != len(decision_profile["models"]):
        raise ArtifactValidationError("deployment manifest decision profile IDs are duplicated or invalid")
    for model in config.models:
        profile = profile_by_model.get(model.id)
        if not profile or any(
            profile.get(field) != expected
            for field, expected in (
                ("triggerThreshold", model.trigger_threshold),
                ("evidenceWindowFrames", model.evidence_window_frames),
                ("requiredHits", model.required_hits),
                ("vadMode", model.vad_mode),
            )
        ):
            raise ArtifactValidationError(f"deployment manifest decision policy mismatch for {model.id}")
        if model.vad_mode == "gate" and any(
            profile.get(field) != expected
            for field, expected in (
                ("vadThreshold", model.vad_threshold),
                ("vadContextOldestLagFrames", model.vad_context_oldest_lag_frames),
                ("vadContextNewestLagFrames", model.vad_context_newest_lag_frames),
                ("vadAggregate", model.vad_aggregate),
            )
        ):
            raise ArtifactValidationError(f"deployment manifest VAD policy mismatch for {model.id}")
    if not isinstance(manifest.get("evaluation"), dict) or not isinstance(manifest.get("metrics"), dict):
        raise ArtifactValidationError("deployment manifest evaluation sections are invalid")
    # A top-level true flag is not sufficient: the conjunction is recomputed.
    evaluations = manifest["perModelEvaluation"]
    if not isinstance(evaluations, list) or len(evaluations) != len(config.models):
        raise ArtifactValidationError("deployment manifest per-model evaluation set is incomplete")
    by_model = {item.get("modelId"): item for item in evaluations if isinstance(item, dict)}
    if len(by_model) != len(evaluations):
        raise ArtifactValidationError("deployment manifest per-model evaluation IDs are duplicated or invalid")

    def require_passed_gates(gates: Any, label: str) -> None:
        if not isinstance(gates, list) or not gates:
            raise ArtifactValidationError(f"{label} gate set is empty")
        for gate in gates:
            if not isinstance(gate, dict) or any(
                field not in gate for field in ("gateId", "comparator", "limit", "measured", "passed")
            ) or not isinstance(gate["gateId"], str) or not gate["gateId"] or gate["passed"] is not True:
                raise ArtifactValidationError(f"{label} gate set failed")

    for model in config.models:
        record = by_model.get(model.id)
        if not record or record.get("qualityTargetMet") is not True:
            raise ArtifactValidationError(f"quality gate failed for {model.id}")
        if not isinstance(record.get("evaluationReportArtifactId"), str) or not record["evaluationReportArtifactId"]:
            raise ArtifactValidationError(f"evaluation report is missing for {model.id}")
        require_passed_gates(record.get("gateResults"), f"per-model {model.id}")
    mappings = manifest.get("mapping")
    if not isinstance(mappings, list) or len(mappings) != len(config.models):
        raise ArtifactValidationError("deployment manifest model mapping is incomplete")
    mapping_by_model = {item.get("modelId"): item for item in mappings if isinstance(item, dict)}
    if len(mapping_by_model) != len(mappings):
        raise ArtifactValidationError("deployment manifest model mappings are duplicated or invalid")
    artifact_records = manifest.get("artifacts")
    if not isinstance(artifact_records, list) or not artifact_records:
        raise ArtifactValidationError("deployment manifest artifact records are invalid")
    artifact_by_id: dict[str, dict[str, Any]] = {}
    artifact_by_path: dict[str, dict[str, Any]] = {}
    approved_root = config.artifacts.model_root.resolve()
    for artifact in artifact_records:
        if not isinstance(artifact, dict):
            raise ArtifactValidationError("deployment manifest contains an invalid artifact record")
        artifact_id = artifact.get("artifactId")
        relative_path = artifact.get("relativePath")
        byte_length = artifact.get("byteLength")
        digest = artifact.get("sha256")
        if (
            not isinstance(artifact_id, str) or not artifact_id or artifact_id in artifact_by_id
            or not isinstance(artifact.get("role"), str) or not artifact["role"]
            or not isinstance(relative_path, str) or Path(relative_path).is_absolute()
            or ".." in Path(relative_path).parts
            or not isinstance(byte_length, int) or isinstance(byte_length, bool) or byte_length < 1
            or not isinstance(digest, str) or not re.fullmatch(r"[0-9a-f]{64}", digest)
        ):
            raise ArtifactValidationError("deployment manifest artifact record fields are invalid")
        path = config.artifacts.model_root / relative_path
        try:
            path.resolve().relative_to(approved_root)
        except ValueError as exc:
            raise ArtifactValidationError("deployment manifest artifact escapes approved model root") from exc
        if relative_path in artifact_by_path:
            raise ArtifactValidationError("deployment manifest artifact paths are duplicated")
        _regular_file(path)
        actual_length = path.stat().st_size
        actual_digest = sha256_file(path)
        if byte_length != actual_length or digest != actual_digest:
            raise ArtifactValidationError(f"deployment manifest artifact digest mismatch: {relative_path}")
        artifact_by_id[artifact_id] = artifact
        artifact_by_path[relative_path] = artifact

    for model in config.models:
        mapping = mapping_by_model.get(model.id)
        if not mapping or mapping.get("phrase") != model.phrase or mapping.get("wireStatus") != model.wire_status:
            raise ArtifactValidationError(f"deployment manifest mapping mismatch for {model.id}")
        artifact = artifact_by_id.get(mapping.get("classifierArtifactId"))
        if not artifact or artifact.get("sha256") != model.sha256:
            raise ArtifactValidationError(f"deployment manifest classifier hash mismatch for {model.id}")
        if artifact.get("relativePath") != model.path.resolve().relative_to(approved_root).as_posix():
            raise ArtifactValidationError(f"deployment manifest classifier path mismatch for {model.id}")
    expected_paths = {
        model.path.resolve().relative_to(approved_root).as_posix(): model.sha256 for model in config.models
    }
    expected_paths.update({
        config.artifacts.melspectrogram.path.resolve().relative_to(approved_root).as_posix(): config.artifacts.melspectrogram.sha256,
        config.artifacts.embedding.path.resolve().relative_to(approved_root).as_posix(): config.artifacts.embedding.sha256,
    })
    if config.artifacts.vad is not None:
        expected_paths[config.artifacts.vad.path.resolve().relative_to(approved_root).as_posix()] = config.artifacts.vad.sha256
    for relative_path, digest in expected_paths.items():
        artifact = artifact_by_path.get(relative_path)
        if artifact is None or artifact.get("sha256") != digest:
            raise ArtifactValidationError(f"deployment manifest is missing loaded artifact {relative_path}")
    for model in config.models:
        report_id = by_model[model.id]["evaluationReportArtifactId"]
        if report_id not in artifact_by_id:
            raise ArtifactValidationError(f"evaluation report artifact is missing for {model.id}")
    pipeline_gates = manifest["pipelineGates"]
    require_passed_gates(pipeline_gates, "pipeline")


def validate_artifacts(config: WakeWordConfig) -> ArtifactValidationReport:
    warnings: list[str] = []
    hashes: dict[str, str] = {}
    model_root = config.artifacts.model_root.resolve()
    if model_root.is_symlink() or not model_root.is_dir():
        raise ArtifactValidationError(f"approved model root is not a directory: {model_root}")

    def enforce_root(path: Path) -> None:
        if config.environment != "production":
            return
        try:
            path.resolve().relative_to(model_root)
        except ValueError as exc:
            raise ArtifactValidationError(f"production artifact escapes approved model root: {path}") from exc

    for model in config.models:
        enforce_root(model.path)
        _regular_file(model.path)
        hashes[model.id] = _check_hash(model.path, model.sha256)
        _onnx_contract(model.path, classifier_id=model.id)
    for name, reference in (
        ("melspectrogram", config.artifacts.melspectrogram),
        ("embedding", config.artifacts.embedding),
    ):
        enforce_root(reference.path)
        _regular_file(reference.path)
        hashes[name] = _check_hash(reference.path, reference.sha256)
        _onnx_contract(reference.path)
    if config.artifacts.vad is not None:
        reference = config.artifacts.vad
        enforce_root(reference.path)
        _regular_file(reference.path)
        hashes["vad"] = _check_hash(reference.path, reference.sha256)
        _onnx_contract(reference.path)

    if config.environment == "production":
        if config.artifacts.manifest_path is None:
            raise ArtifactValidationError("production requires a deployment manifest")
        _manifest_quality_check(config, config.artifacts.manifest_path)
        quality = "verified"
        production_ready = True
    elif config.artifacts.manifest_path is not None:
        # A development manifest is still required to pass the same integrity
        # checks before its quality flag can be reported as verified.
        try:
            _manifest_quality_check(config, config.artifacts.manifest_path)
        except ArtifactValidationError as exc:
            if not config.allow_unverified_models:
                raise
            warnings.append(f"unverified development manifest: {exc}")
            quality = "unverified"
            production_ready = False
        else:
            quality = "verified"
            production_ready = True
    else:
        if not config.allow_unverified_models:
            raise ArtifactValidationError(
                "no deployment manifest; set WAKEWORD_ALLOW_UNVERIFIED_MODELS=true only for development/shadow"
            )
        warnings.append("model_quality=unverified: no trusted deployment manifest")
        quality = "unverified"
        production_ready = False
    return ArtifactValidationReport(production_ready, quality, config.config_revision, hashes, tuple(warnings))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate WakeWordModule artifacts")
    parser.add_argument("--config", required=True, type=Path)
    parser.add_argument("--allow-unverified", action="store_true")
    args = parser.parse_args(argv)
    try:
        config = load_config(args.config)
        if args.allow_unverified and config.environment != "production":
            config = replace(config, allow_unverified_models=True)
        report = validate_artifacts(config)
    except (ConfigError, ArtifactValidationError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False))
        return 2
    print(json.dumps({
        "ok": True,
        "production_ready": report.production_ready,
        "model_quality": report.model_quality,
        "config_revision": report.config_revision,
        "artifact_hashes": report.artifact_hashes,
        "warnings": report.warnings,
    }, ensure_ascii=False, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
