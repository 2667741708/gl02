#!/usr/bin/env python3
"""Seal the R2Y diagnostic stage without promoting any release gate."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
STAGE_REL = Path(
    "PT/高炉3D模型/work/"
    "WEB_60_20260720_R2Y_MATERIAL_SIGNAL_VISIBILITY_DIAGNOSTIC"
)
STAGE = ROOT / STAGE_REL
MANIFEST = STAGE / "artifact_manifest.json"
EXPECTED_STATUS = (
    "r2y_cpu_hit_passed_pbr_visual_failed_ao_webgl_pending_fail_closed"
)

IMPLEMENTATION_FILES = (
    Path("tools/verify_bf3d_r2y_input_gate.py"),
    Path("tools/audit_bf3d_r2y_pbr_texture_signal.py"),
    Path("tools/audit_bf3d_r2y_ao_uv_hit.py"),
    Path("tools/build_bf3d_review_r2y_web.py"),
    Path("tools/serve_bf3d_review_r2y.py"),
    Path("tools/verify_bf3d_review_r2y_preview.cjs"),
    Path("tools/finalize_bf3d_r2y_stage.py"),
    Path("高炉前端数据/bf3d_review_r2y.server.html"),
    Path("高炉前端数据/assets/bf3d-review-renderer-r2y.js"),
)

TRACEABILITY_FILES = (
    Path("docs/automation_traceability.md"),
    Path("docs/question_traceability.md"),
    Path("docs/test_reference.md"),
    Path("PT/高炉3D模型/docs/WEB-60_炉内仿真运行时说明.md"),
    Path("PT/高炉3D模型/validation/Visual_Bible当前实现合规矩阵.md"),
    Path("PT/高炉3D模型/工业级高炉数字孪生视觉规范（Visual Bible）.md"),
    Path("PT/高炉3D模型/十阶段多智能体执行台账.md"),
    Path("PT/高炉3D模型/总设计详细规划.md"),
    Path("reports/pipeline_status.json"),
)


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def record(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise FileNotFoundError(path)
    return {
        "path": path.relative_to(ROOT).as_posix(),
        "bytes": path.stat().st_size,
        "sha256": sha256_file(path),
    }


def verify_stage_truth() -> dict[str, Any]:
    pipeline = load_json(STAGE / "pipeline_status.json")
    input_gate = load_json(STAGE / "reports/r2y_input_gate_report.json")
    pbr_audit = load_json(
        STAGE / "reports/r2y_pbr_texture_signal_audit.json"
    )
    cpu_audit = load_json(
        STAGE / "reports/r2y_ao_uv_hit_raster_audit.json"
    )
    web_build = load_json(
        STAGE / "reports/r2y_material_signal_web_build_report.json"
    )
    representative = load_json(
        STAGE / "reports/bf3d_review_r2y_representative_report.json"
    )
    review = load_json(
        STAGE / "reports/r2y_independent_review_decisions.json"
    )

    assertions = {
        "pipeline_status_is_fail_closed": pipeline["status"]
        == EXPECTED_STATUS,
        "input_gate_passed": input_gate["passed"] is True,
        "offline_pbr_data_gate_passed": pbr_audit["passed"] is True,
        "cpu_uv_ao_gate_passed": cpu_audit[
            "cpu_preregistered_gate_passed"
        ]
        is True,
        "full_ao_visibility_gate_passed": cpu_audit[
            "full_ao_visibility_gate_passed"
        ]
        is False,
        "web_build_passed": web_build["passed"] is True,
        "representative_pbr_fixture_failed": representative[
            "pbr_fixture_passed"
        ]
        is False,
        "representative_ao_gate_failed": representative["ao_gate_passed"]
        is False,
        "representative_stage_not_complete": representative[
            "stage_complete"
        ]
        is False,
        "ao_webgl_liveness_not_executed": representative[
            "ao_webgl_classification"
        ]["execution_status"]
        == "not_executed",
        "independent_review_failed_closed": review["status"]
        == (
            "fail_closed_material_signal_artifact_dominated_"
            "environment_nonobservable"
        ),
        "full_matrix_not_executed": representative["scope"][
            "full_matrix_executed"
        ]
        is False,
        "protected_inputs_unchanged": representative[
            "protected_inputs_unchanged"
        ]
        is True,
    }
    failed = [name for name, passed in assertions.items() if not passed]
    if failed:
        raise RuntimeError(
            "R2Y finalization truth assertions failed: " + ", ".join(failed)
        )
    return {
        "assertions": assertions,
        "pipeline": pipeline,
        "representative": representative,
        "review": review,
    }


def build_manifest() -> dict[str, Any]:
    truth = verify_stage_truth()
    stage_files = sorted(
        (
            path
            for path in STAGE.rglob("*")
            if path.is_file() and path != MANIFEST
        ),
        key=lambda path: path.relative_to(ROOT).as_posix(),
    )
    pipeline = truth["pipeline"]
    representative = truth["representative"]
    review = truth["review"]
    return {
        "schema_version": "bf3d.r2y.artifact_manifest.v1",
        "requirement_id": pipeline["requirement_id"],
        "stage_id": pipeline["stage_id"],
        "generated_at": pipeline["updated_at"],
        "evidence_class": "E/diagnostic",
        "status": EXPECTED_STATUS,
        "stage_truth_assertions": truth["assertions"],
        "decision": {
            "pbr_fixture_passed": representative["pbr_fixture_passed"],
            "ao_webgl_liveness_executed": False,
            "independent_review_status": review["status"],
            "full_matrix_executed": False,
            "beauty_approved": False,
            "production_integration_allowed": False,
        },
        "counts": {
            "stage_artifacts": len(stage_files),
            "implementation_artifacts": len(IMPLEMENTATION_FILES),
            "traceability_documents": len(TRACEABILITY_FILES),
        },
        "stage_artifacts": [record(path) for path in stage_files],
        "implementation_artifacts": [
            record(ROOT / relative) for relative in IMPLEMENTATION_FILES
        ],
        "traceability_documents": [
            record(ROOT / relative) for relative in TRACEABILITY_FILES
        ],
        "stop_lines": pipeline["stage_documents"]
        | {
            "beauty_approved": False,
            "golden_approved": False,
            "full_matrix_allowed": False,
            "ao_2k_approved": False,
            "p50_approved": False,
            "p60_approved": False,
            "production_integration_allowed": False,
            "next_release_stage_allowed": False,
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check",
        action="store_true",
        help="Verify stage truth and compare the current manifest.",
    )
    args = parser.parse_args()
    expected = build_manifest()
    if args.check:
        current = load_json(MANIFEST)
        if current != expected:
            raise RuntimeError("artifact_manifest.json is stale")
    else:
        MANIFEST.write_text(
            json.dumps(expected, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
    print(
        json.dumps(
            {
                "ok": True,
                "mode": "check" if args.check else "write",
                "manifest": MANIFEST.relative_to(ROOT).as_posix(),
                "status": EXPECTED_STATUS,
                "stage_artifacts": expected["counts"]["stage_artifacts"],
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
