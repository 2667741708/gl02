#!/usr/bin/env python3
"""Verify the immutable inputs for R2Z without rewriting the lock file."""

from __future__ import annotations

import hashlib
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo


REQUIREMENT_ID = "REQ-BF3D-R2Z-TRUE-PBR-BAKE-RECOVERY-20260720"
STAGE_ID = (
    "WEB_60_20260720_R2Z_TRUE_PBR_BAKE_RECOVERY_AND_CHANNEL_LIVENESS"
)
ROOT = Path(__file__).resolve().parents[1]
STAGE = ROOT / "PT" / "高炉3D模型" / "work" / STAGE_ID
CONTRACT = STAGE / "WEB-60_R2Z_阶段预注册合同.md"
INPUT_LOCK = STAGE / "input_lock.json"
REPORT = STAGE / "reports" / "r2z_input_gate_report.json"


def sha256_file(path: Path) -> str:
    """Return the lowercase SHA-256 of one file."""

    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def resolve_path(value: str) -> Path:
    """Resolve a lock path while preserving explicit Windows absolute paths."""

    path = Path(value)
    return path if path.is_absolute() else ROOT / path


def inspect_record(record: dict[str, Any]) -> dict[str, Any]:
    """Inspect one lock record without mutating it."""

    path = resolve_path(str(record["path"]))
    exists = path.is_file()
    actual_bytes = path.stat().st_size if exists else None
    actual_sha = sha256_file(path) if exists else None
    expected_bytes = int(record["bytes"])
    expected_sha = str(record["sha256"])
    return {
        "role": record.get("role"),
        "path": record["path"],
        "expected_bytes": expected_bytes,
        "actual_bytes": actual_bytes,
        "expected_sha256": expected_sha,
        "actual_sha256": actual_sha,
        "exists": exists,
        "passed": (
            exists
            and actual_bytes == expected_bytes
            and actual_sha == expected_sha
        ),
    }


def write_json(path: Path, payload: dict[str, Any]) -> None:
    """Write a deterministic UTF-8 report inside the owned stage."""

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def main() -> int:
    """Validate the pre-registered lock and emit the machine gate report."""

    if not INPUT_LOCK.is_file():
        raise FileNotFoundError(INPUT_LOCK)
    lock = json.loads(INPUT_LOCK.read_text(encoding="utf-8"))
    contract_record = inspect_record(lock["contract"])
    authoritative = [
        inspect_record(record) for record in lock["authoritative_inputs"]
    ]
    protected = [
        inspect_record(record) for record in lock["protected_assets"]
    ]
    unique_paths = [
        str(record["path"])
        for record in (
            [lock["contract"]]
            + lock["authoritative_inputs"]
            + lock["protected_assets"]
        )
    ]
    checks = {
        "schema_matches": lock.get("schema_version")
        == "bf3d.r2z.input_lock.v1",
        "requirement_matches": lock.get("requirement_id") == REQUIREMENT_ID,
        "stage_matches": lock.get("stage_id") == STAGE_ID,
        "phase_a_only": lock.get("phase")
        == "phase_a_bake_liveness_only",
        "contract_path_matches": resolve_path(
            str(lock["contract"]["path"])
        ).resolve()
        == CONTRACT.resolve(),
        "contract_matches": contract_record["passed"],
        "authoritative_inputs_match": all(
            record["passed"] for record in authoritative
        ),
        "protected_assets_match": all(
            record["passed"] for record in protected
        ),
        "paths_unique_within_each_role": (
            len(
                {
                    str(record["path"])
                    for record in lock["authoritative_inputs"]
                }
            )
            == len(lock["authoritative_inputs"])
            and len(
                {
                    str(record["path"])
                    for record in lock["protected_assets"]
                }
            )
            == len(lock["protected_assets"])
        ),
        "phase_b_still_locked": lock["stop_lines"].get(
            "phase_b_true_bake_allowed"
        )
        is False,
        "production_still_locked": lock["stop_lines"].get(
            "production_integration_allowed"
        )
        is False,
    }
    passed = all(checks.values())
    report = {
        "schema_version": "bf3d.r2z.input_gate_report.v1",
        "requirement_id": REQUIREMENT_ID,
        "stage_id": STAGE_ID,
        "generated_at": datetime.now(
            ZoneInfo("Asia/Shanghai")
        ).isoformat(),
        "scope": "phase_a_bake_liveness_only",
        "input_lock": {
            "path": INPUT_LOCK.relative_to(ROOT).as_posix(),
            "bytes": INPUT_LOCK.stat().st_size,
            "sha256": sha256_file(INPUT_LOCK),
        },
        "contract": contract_record,
        "authoritative_inputs": authoritative,
        "protected_assets": protected,
        "checks": checks,
        "path_count": len(unique_paths),
        "passed": passed,
        "status": "input_gate_passed"
        if passed
        else "input_gate_failed_closed",
        "stop_lines": lock["stop_lines"],
    }
    write_json(REPORT, report)
    print(
        json.dumps(
            {
                "ok": passed,
                "status": report["status"],
                "report": REPORT.relative_to(ROOT).as_posix(),
                "authoritative_inputs": len(authoritative),
                "protected_assets": len(protected),
            },
            ensure_ascii=False,
        )
    )
    return 0 if passed else 2


if __name__ == "__main__":
    sys.exit(main())
