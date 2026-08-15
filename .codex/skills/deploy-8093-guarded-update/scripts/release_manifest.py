"""Seal and verify immutable prepared releases for guarded 8093 deployment."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


SPEC_SCHEMA = "bf.deploy.release-spec.v1"
MANIFEST_SCHEMA = "bf.deploy.prepared-release.v1"
REMOTE_SCHEMA = "bf.deploy.remote-state.v1"
PLAN_SCHEMA = "bf.deploy.delta-plan.v1"
HASH_RE = re.compile(r"^[0-9A-Fa-f]{64}$")


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def canonical_bytes(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def object_hash(value: Any) -> str:
    return hashlib.sha256(canonical_bytes(value)).hexdigest().upper()


def file_hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest().upper()


def load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(value, dict):
        raise ValueError(f"JSON root must be an object: {path}")
    return value


def atomic_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.replace(temporary, path)


def normalize_hash(value: str, field: str) -> str:
    text = str(value or "").strip().upper()
    if not HASH_RE.fullmatch(text):
        raise ValueError(f"{field} must be a SHA-256 hex digest")
    return text


def required_text(value: Any, field: str) -> str:
    text = str(value or "").strip()
    if not text:
        raise ValueError(f"{field} is required")
    return text


def local_file(value: Any, base: Path, field: str) -> Path:
    raw = Path(required_text(value, field))
    path = raw if raw.is_absolute() else base / raw
    path = path.resolve()
    if not path.is_file():
        raise ValueError(f"{field} is not a file: {path}")
    return path


def seal_payload(payload: dict[str, Any]) -> dict[str, Any]:
    sealed = dict(payload)
    sealed["content_sha256"] = object_hash(payload)
    return sealed


def verify_seal(value: dict[str, Any], field: str) -> None:
    expected = normalize_hash(value.get("content_sha256", ""), f"{field}.content_sha256")
    payload = {key: item for key, item in value.items() if key != "content_sha256"}
    if object_hash(payload) != expected:
        raise ValueError(f"{field} content seal mismatch")


def check_markers(path: Path, markers: list[str]) -> None:
    if not markers:
        return
    try:
        text = path.read_text(encoding="utf-8-sig")
    except UnicodeDecodeError as exc:
        raise ValueError(f"markers require a UTF-8 text artifact: {path}") from exc
    for marker in markers:
        if marker not in text:
            raise ValueError(f"artifact marker missing: {marker}")


def prepare(spec_path: Path, output_path: Path) -> dict[str, Any]:
    spec = load_json(spec_path)
    if spec.get("schema") != SPEC_SCHEMA:
        raise ValueError(f"spec.schema must be {SPEC_SCHEMA}")
    requirement_id = required_text(spec.get("requirement_id"), "requirement_id")
    tier = required_text(spec.get("validation_tier"), "validation_tier")
    if tier not in {"quick", "standard", "full"}:
        raise ValueError("validation_tier must be quick, standard, or full")
    production_root = required_text(spec.get("production_root"), "production_root")
    base = spec_path.resolve().parent

    raw_sources = spec.get("sources")
    if not isinstance(raw_sources, list) or not raw_sources:
        raise ValueError("sources must contain at least one file")
    sources: list[dict[str, Any]] = []
    seen_sources: set[str] = set()
    for index, item in enumerate(raw_sources):
        path = local_file(item, base, f"sources[{index}]")
        key = str(path).casefold()
        if key in seen_sources:
            raise ValueError(f"duplicate source: {path}")
        seen_sources.add(key)
        sources.append({"path": str(path), "sha256": file_hash(path), "size": path.stat().st_size})

    raw_artifacts = spec.get("artifacts")
    if not isinstance(raw_artifacts, list) or not raw_artifacts:
        raise ValueError("artifacts must contain at least one file")
    artifacts: list[dict[str, Any]] = []
    seen_targets: set[str] = set()
    seen_stages: set[str] = set()
    for index, item in enumerate(raw_artifacts):
        if not isinstance(item, dict):
            raise ValueError(f"artifacts[{index}] must be an object")
        path = local_file(item.get("local_path"), base, f"artifacts[{index}].local_path")
        target = required_text(item.get("target"), f"artifacts[{index}].target")
        stage = required_text(item.get("stage"), f"artifacts[{index}].stage")
        target_key = target.casefold()
        stage_key = stage.casefold()
        if target_key in seen_targets:
            raise ValueError(f"duplicate target: {target}")
        if stage_key in seen_stages:
            raise ValueError(f"duplicate stage path: {stage}")
        seen_targets.add(target_key)
        seen_stages.add(stage_key)
        raw_baselines = item.get("baseline_sha256", [])
        if not isinstance(raw_baselines, list):
            raise ValueError(f"artifacts[{index}].baseline_sha256 must be a list")
        baselines = [normalize_hash(value, f"artifacts[{index}].baseline_sha256") for value in raw_baselines]
        allow_create = bool(item.get("allow_create", False))
        if not allow_create and not baselines:
            raise ValueError(f"artifacts[{index}] requires a baseline hash or allow_create=true")
        raw_markers = item.get("markers", [])
        if not isinstance(raw_markers, list):
            raise ValueError(f"artifacts[{index}].markers must be a list")
        markers = [required_text(value, f"artifacts[{index}].markers") for value in raw_markers]
        check_markers(path, markers)
        artifacts.append(
            {
                "local_path": str(path),
                "stage": stage,
                "target": target,
                "baseline_sha256": baselines,
                "allow_create": allow_create,
                "markers": markers,
                "desired_sha256": file_hash(path),
                "size": path.stat().st_size,
            }
        )

    validations = spec.get("validations")
    if not isinstance(validations, list) or not validations:
        raise ValueError("validations must contain at least one passed result")
    normalized_validations: list[dict[str, Any]] = []
    validation_ids: set[str] = set()
    for index, item in enumerate(validations):
        if not isinstance(item, dict):
            raise ValueError(f"validations[{index}] must be an object")
        validation_id = required_text(item.get("id"), f"validations[{index}].id")
        if validation_id in validation_ids:
            raise ValueError(f"duplicate validation id: {validation_id}")
        validation_ids.add(validation_id)
        if item.get("status") != "passed":
            raise ValueError(f"validation did not pass: {validation_id}")
        normalized_validations.append(dict(item))

    manifest = seal_payload(
        {
            "schema": MANIFEST_SCHEMA,
            "prepared_at": utc_now(),
            "requirement_id": requirement_id,
            "validation_tier": tier,
            "production_root": production_root,
            "sources": sources,
            "artifacts": artifacts,
            "validations": normalized_validations,
        }
    )
    atomic_json(output_path, manifest)
    return manifest


def verify_manifest(path: Path) -> dict[str, Any]:
    manifest = load_json(path)
    if manifest.get("schema") != MANIFEST_SCHEMA:
        raise ValueError(f"manifest.schema must be {MANIFEST_SCHEMA}")
    verify_seal(manifest, "manifest")
    for source in manifest.get("sources", []):
        local = Path(required_text(source.get("path"), "source.path"))
        if not local.is_file() or file_hash(local) != normalize_hash(source.get("sha256", ""), "source.sha256"):
            raise ValueError(f"prepared source changed or is missing: {local}")
    for artifact in manifest.get("artifacts", []):
        local = Path(required_text(artifact.get("local_path"), "artifact.local_path"))
        desired = normalize_hash(artifact.get("desired_sha256", ""), "artifact.desired_sha256")
        if not local.is_file() or file_hash(local) != desired:
            raise ValueError(f"prepared artifact changed or is missing: {local}")
        check_markers(local, list(artifact.get("markers", [])))
    validations = manifest.get("validations", [])
    if not validations or any(item.get("status") != "passed" for item in validations):
        raise ValueError("manifest contains missing or failed validation evidence")
    return manifest


def target_lookup(targets: dict[str, Any]) -> dict[str, tuple[str, Any]]:
    result: dict[str, tuple[str, Any]] = {}
    for key, value in targets.items():
        folded = str(key).casefold()
        if folded in result:
            raise ValueError(f"duplicate remote target ignoring case: {key}")
        result[folded] = (str(key), value)
    return result


def plan_delta(manifest_path: Path, remote_path: Path, output_path: Path) -> dict[str, Any]:
    manifest = verify_manifest(manifest_path)
    remote = load_json(remote_path)
    if remote.get("schema") != REMOTE_SCHEMA:
        raise ValueError(f"remote-state.schema must be {REMOTE_SCHEMA}")
    if remote.get("requirement_id") != manifest.get("requirement_id"):
        raise ValueError("remote-state requirement_id does not match manifest")
    targets = remote.get("targets")
    if not isinstance(targets, dict):
        raise ValueError("remote-state.targets must be an object")
    lookup = target_lookup(targets)
    changes: list[dict[str, Any]] = []
    unchanged: list[str] = []
    for artifact in manifest["artifacts"]:
        target = artifact["target"]
        pair = lookup.get(target.casefold())
        if pair is None or not isinstance(pair[1], dict):
            raise ValueError(f"remote state missing target: {target}")
        state = pair[1]
        exists = bool(state.get("exists", False))
        current = None
        if exists:
            current = normalize_hash(state.get("sha256", ""), f"remote target {target}")
        desired = artifact["desired_sha256"]
        if exists and current == desired:
            unchanged.append(target)
            continue
        if exists and current not in artifact["baseline_sha256"]:
            raise ValueError(f"unreviewed production baseline: {target} {current}")
        if not exists and not artifact["allow_create"]:
            raise ValueError(f"production target is absent but allow_create=false: {target}")
        changes.append({**artifact, "current_exists": exists, "current_sha256": current})
    plan = seal_payload(
        {
            "schema": PLAN_SCHEMA,
            "generated_at": utc_now(),
            "requirement_id": manifest["requirement_id"],
            "production_root": manifest["production_root"],
            "manifest_sha256": manifest["content_sha256"],
            "remote_state_sha256": object_hash(remote),
            "changes": changes,
            "unchanged": unchanged,
        }
    )
    atomic_json(output_path, plan)
    return plan


def self_test() -> dict[str, Any]:
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        source = root / "source.js"
        artifact = root / "artifact.js"
        source.write_text("const source = true;\n", encoding="utf-8")
        artifact.write_text("const marker = 'REQ-TEST';\n", encoding="utf-8")
        baseline = hashlib.sha256(b"old").hexdigest().upper()
        target = r"F:\production\artifact.js"
        spec = {
            "schema": SPEC_SCHEMA,
            "requirement_id": "REQ-TEST",
            "validation_tier": "quick",
            "production_root": r"F:\production",
            "sources": [str(source)],
            "artifacts": [
                {
                    "local_path": str(artifact),
                    "stage": r"C:\Temp\REQ-TEST\artifact.js",
                    "target": target,
                    "baseline_sha256": [baseline],
                    "markers": ["REQ-TEST"],
                }
            ],
            "validations": [{"id": "unit", "status": "passed", "kind": "deterministic"}],
        }
        spec_path = root / "spec.json"
        manifest_path = root / "manifest.json"
        remote_path = root / "remote.json"
        plan_path = root / "plan.json"
        atomic_json(spec_path, spec)
        manifest = prepare(spec_path, manifest_path)
        verify_manifest(manifest_path)
        remote = {
            "schema": REMOTE_SCHEMA,
            "requirement_id": "REQ-TEST",
            "targets": {target: {"exists": True, "sha256": baseline}},
        }
        atomic_json(remote_path, remote)
        plan = plan_delta(manifest_path, remote_path, plan_path)
        if len(plan["changes"]) != 1 or plan["manifest_sha256"] != manifest["content_sha256"]:
            raise AssertionError("delta plan self-test failed")
        artifact.write_text("tampered\n", encoding="utf-8")
        try:
            verify_manifest(manifest_path)
        except ValueError:
            pass
        else:
            raise AssertionError("tampered artifact was accepted")
    return {"ok": True, "schemas": [SPEC_SCHEMA, MANIFEST_SCHEMA, REMOTE_SCHEMA, PLAN_SCHEMA]}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--self-test", action="store_true")
    commands = parser.add_subparsers(dest="command")
    prepare_command = commands.add_parser("prepare")
    prepare_command.add_argument("--spec", type=Path, required=True)
    prepare_command.add_argument("--output", type=Path, required=True)
    verify_command = commands.add_parser("verify")
    verify_command.add_argument("--manifest", type=Path, required=True)
    plan_command = commands.add_parser("plan-delta")
    plan_command.add_argument("--manifest", type=Path, required=True)
    plan_command.add_argument("--remote-state", type=Path, required=True)
    plan_command.add_argument("--output", type=Path, required=True)
    return parser


def main() -> None:
    args = build_parser().parse_args()
    if args.self_test:
        result = self_test()
    elif args.command == "prepare":
        result = prepare(args.spec, args.output)
    elif args.command == "verify":
        result = verify_manifest(args.manifest)
    elif args.command == "plan-delta":
        result = plan_delta(args.manifest, args.remote_state, args.output)
    else:
        raise SystemExit("choose prepare, verify, or plan-delta")
    print(json.dumps({"ok": True, "result": result}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
