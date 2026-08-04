#!/usr/bin/env python3
"""Freeze and verify inputs for the R2Y material-signal diagnostic.

Requirement:
    REQ-BF3D-R2Y-MATERIAL-SIGNAL-VISIBILITY-DIAGNOSTIC-20260720

This command is read-only outside the owned R2Y stage directory.  It writes
the machine-readable input lock and gate report, then exits fail-closed when
any byte count or SHA-256 differs from the pre-registered contract.
"""

from __future__ import annotations

import hashlib
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo


REQUIREMENT_ID = (
    "REQ-BF3D-R2Y-MATERIAL-SIGNAL-VISIBILITY-DIAGNOSTIC-20260720"
)
STAGE_ID = "WEB_60_20260720_R2Y_MATERIAL_SIGNAL_VISIBILITY_DIAGNOSTIC"
ROOT = Path(__file__).resolve().parents[1]
STAGE = ROOT / "PT" / "高炉3D模型" / "work" / STAGE_ID
REPORTS = STAGE / "reports"
CONTRACT = STAGE / "WEB-60_R2Y_阶段预注册合同.md"
INPUT_LOCK = STAGE / "input_lock.json"
REPORT = REPORTS / "r2y_input_gate_report.json"


DIAGNOSTIC_INPUTS: dict[str, tuple[int, str]] = {
    "高炉前端数据/models/gl02_blast_furnace_material_review.v5.glb": (
        994_372,
        "652be1b2c9147d5a7392497c7ae4964d19bdd7095b5435b87c105f9eb3fb66bc",
    ),
    (
        "PT/高炉3D模型/work/"
        "WEB_60_20260720_R2X_R2J_AO_REBAKE_CANDIDATE/glb/"
        "gl02_blast_furnace_material_review.r2x-ao-smoke1k.v5payload.glb"
    ): (
        1_115_216,
        "bd074c23c237fe7ff3abac0f823bd9aef978021e4e829963b3f979e9b58f1c00",
    ),
    (
        "PT/高炉3D模型/work/"
        "WEB_60_20260720_R2X_R2J_AO_REBAKE_CANDIDATE/textures/"
        "GL02_R2J_LOCAL_CONTACT_AO_1K.png"
    ): (
        24_655,
        "c1362fa572e94e2b8f704ab9d3ec46aed6cc930d7616bb4ad14a38793abcf786",
    ),
    (
        "PT/高炉3D模型/work/"
        "WEB_60_20260720_R2X_R2J_AO_REBAKE_CANDIDATE/reports/"
        "bf3d_review_r2x_representative_report.json"
    ): (
        96_430,
        "3a70ec80dfd3f98fe15a4e69e35cbe086b906f91f72f9a2cd520c1d6bd01cdd8",
    ),
    "高炉前端数据/assets/bf3d-review-renderer-r2x.js": (
        43_968,
        "807b5697d8d74c640860e169b0c77ce8b1a06ca5653941a37d7953f53dc8edf2",
    ),
    "高炉前端数据/libs/three/three.module.js": (
        1_272_972,
        "76dea8151bc9352aef3528b4262e249b2604f62543828328db978d060d61a495",
    ),
    "高炉前端数据/libs/three/loaders/GLTFLoader.js": (
        108_522,
        "d073b438e6a07e1359741dd5d6c76c953420cc0d4fd84eb1bdde94315540e6a3",
    ),
}


PROTECTED_ASSETS: dict[str, tuple[int, str]] = {
    "高炉前端数据/models/gl02_blast_furnace_review.v5.blend": (
        37_121_148,
        "3e6df5fb02d3734d14923d4432739a5918ac8249d6a3c8ad1415395429b27e3a",
    ),
    "高炉前端数据/models/gl02_blast_furnace_review.v5.glb": (
        4_663_220,
        "0ac031e626c9eaa0b0cdd8192cf9fda712324af174a4285f563a97309451ed3c",
    ),
    "高炉前端数据/models/gl02_blast_furnace_structural_review.v5.glb": (
        3_945_984,
        "e5c77d3834c631e2513209a690f6328d1c63dba2c8d489b2d2dbe17645465f71",
    ),
    "高炉前端数据/models/gl02_blast_furnace.glb": (
        4_314_736,
        "808960f1b2703e7fb27df35f1b1b1a17063b9b10d2267acba593fc3872b62af6",
    ),
    "高炉前端数据/frontend_dashboard_v3.server.html": (
        852_156,
        "51118fc70d34cd28f32deac6039fbe81245b8cf196f46653696837a404dcdfbc",
    ),
    "高炉前端数据/assets/bf3d-structural-review.js": (
        66_839,
        "d99b6d8fc419d2c0d61f713af2343fe15b212f2c89f6f905ca27555dcb90b206",
    ),
    "高炉前端数据/bf3d_review_v5.server.html": (
        8_603,
        "bb0ddf0acf79f7ec81652b047e6295d90322fa15461f08d90473833ff5878565",
    ),
    "高炉前端数据/assets/bf3d-review-renderer-v5.js": (
        44_445,
        "9d01b31482abc7c09146f657ba402457d354890f74f76501ec45dcf7e50b589d",
    ),
}


def sha256_file(path: Path) -> str:
    """Return a lowercase SHA-256 for one file."""

    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def inspect_locked_set(
    expected: dict[str, tuple[int, str]],
) -> tuple[list[dict[str, Any]], bool]:
    """Inspect one immutable input set without changing it."""

    records: list[dict[str, Any]] = []
    for relative, (expected_bytes, expected_sha) in expected.items():
        path = ROOT / Path(relative)
        exists = path.is_file()
        actual_bytes = path.stat().st_size if exists else None
        actual_sha = sha256_file(path) if exists else None
        passed = (
            exists
            and actual_bytes == expected_bytes
            and actual_sha == expected_sha
        )
        records.append(
            {
                "path": relative,
                "expected_bytes": expected_bytes,
                "actual_bytes": actual_bytes,
                "expected_sha256": expected_sha,
                "actual_sha256": actual_sha,
                "exists": exists,
                "passed": passed,
            }
        )
    return records, all(record["passed"] for record in records)


def write_json(path: Path, payload: dict[str, Any]) -> None:
    """Write deterministic UTF-8 JSON inside the owned stage."""

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def main() -> int:
    """Verify locks and write the stage input gate evidence."""

    timestamp = datetime.now(ZoneInfo("Asia/Shanghai")).isoformat()
    diagnostic_records, diagnostic_passed = inspect_locked_set(
        DIAGNOSTIC_INPUTS
    )
    protected_records, protected_passed = inspect_locked_set(PROTECTED_ASSETS)
    contract_exists = CONTRACT.is_file()
    contract_record = {
        "path": CONTRACT.relative_to(ROOT).as_posix(),
        "exists": contract_exists,
        "bytes": CONTRACT.stat().st_size if contract_exists else None,
        "sha256": sha256_file(CONTRACT) if contract_exists else None,
    }
    passed = diagnostic_passed and protected_passed and contract_exists

    shared = {
        "schema_version": "bf3d.r2y.input_gate.v1",
        "requirement_id": REQUIREMENT_ID,
        "stage_id": STAGE_ID,
        "generated_at": timestamp,
        "contract": contract_record,
        "diagnostic_inputs": diagnostic_records,
        "protected_assets": protected_records,
        "checks": {
            "diagnostic_inputs_match": diagnostic_passed,
            "protected_assets_match": protected_passed,
            "preregistered_contract_exists": contract_exists,
        },
        "passed": passed,
    }
    input_lock = {
        **shared,
        "lock_status": "locked" if passed else "failed_closed",
        "execution_scope": [
            "read_only_cpu_uv_ao_raster_audit",
            "isolated_pbr_signal_visibility_fixture",
            "chromium_1440x900_representative_only",
        ],
        "stop_lines": {
            "asset_mutation_allowed": False,
            "full_matrix_allowed": False,
            "ao_rebake_allowed": False,
            "ao_2k_approved": False,
            "p50_approved": False,
            "p60_approved": False,
            "production_integration_allowed": False,
            "next_release_stage_allowed": False,
        },
    }
    report = {
        **shared,
        "status": "input_gate_passed" if passed else "input_gate_failed_closed",
        "written_outputs": [
            INPUT_LOCK.relative_to(ROOT).as_posix(),
            REPORT.relative_to(ROOT).as_posix(),
        ],
    }
    write_json(INPUT_LOCK, input_lock)
    write_json(REPORT, report)
    print(
        json.dumps(
            {
                "status": report["status"],
                "passed": passed,
                "input_lock": str(INPUT_LOCK),
                "report": str(REPORT),
            },
            ensure_ascii=False,
        )
    )
    return 0 if passed else 2


if __name__ == "__main__":
    sys.exit(main())
