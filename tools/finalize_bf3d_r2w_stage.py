"""Fail-closed finalizer for the WEB-60 R2W material-readability stage.

This script does not modify any GLB, Blend, texture, light or renderer source.
It verifies the locked R2W evidence, records the diagnostic-only stage status,
and inventories the resulting artifacts.

Run:
    python tools/finalize_bf3d_r2w_stage.py
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
STAGE_ID = "WEB_60_20260720_R2W_MATERIAL_READABILITY_AO_EDGE"
REQUIREMENT_ID = "REQ-BF3D-R2W-MATERIAL-READABILITY-CAMERA-20260720"
STATUS = "r2w_camera_readability_passed_ao_and_structure_blocked"
STAGE = ROOT / "PT" / "高炉3D模型" / "work" / STAGE_ID
REPORTS = STAGE / "reports"
PREVIEW = STAGE / "preview"

FORMAL_GLB = ROOT / "高炉前端数据" / "models" / "gl02_blast_furnace.glb"
V5_GLB = (
    ROOT
    / "高炉前端数据"
    / "models"
    / "gl02_blast_furnace_review.v5.glb"
)
V5_BLEND = (
    ROOT
    / "高炉前端数据"
    / "models"
    / "gl02_blast_furnace_review.v5.blend"
)

FORMAL_SHA256 = (
    "808960f1b2703e7fb27df35f1b1b1a17063b9b10d2267acba593fc3872b62af6"
)
V5_GLB_SHA256 = (
    "0ac031e626c9eaa0b0cdd8192cf9fda712324af174a4285f563a97309451ed3c"
)
V5_BLEND_SHA256 = (
    "3e6df5fb02d3734d14923d4432739a5918ac8249d6a3c8ad1415395429b27e3a"
)

WEB_OUTPUTS = (
    ROOT / "高炉前端数据" / "bf3d_review_r2w.server.html",
    ROOT / "高炉前端数据" / "assets" / "bf3d-review-renderer-r2w.js",
    ROOT / "tools" / "serve_bf3d_review_r2w.py",
    ROOT / "tools" / "verify_bf3d_review_r2w_preview.cjs",
)


def now_iso() -> str:
    return datetime.now(timezone(timedelta(hours=8))).isoformat(timespec="seconds")


def require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def sha256(path: Path) -> str:
    require(path.is_file(), f"Required file is missing: {path}")
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def rel(path: Path) -> str:
    return path.resolve().relative_to(ROOT.resolve()).as_posix()


def artifact(path: Path) -> dict[str, Any]:
    require(path.is_file(), f"Required artifact is missing: {path}")
    return {
        "path": rel(path),
        "bytes": path.stat().st_size,
        "sha256": sha256(path),
    }


def load_json(path: Path) -> dict[str, Any]:
    require(path.is_file(), f"Required JSON is missing: {path}")
    value = json.loads(path.read_text(encoding="utf-8"))
    require(isinstance(value, dict), f"Expected a JSON object: {path}")
    return value


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def validate_locked_assets() -> dict[str, dict[str, Any]]:
    current = {
        "formal_glb": artifact(FORMAL_GLB),
        "v5_review_glb": artifact(V5_GLB),
        "v5_review_blend": artifact(V5_BLEND),
    }
    require(
        current["formal_glb"]["sha256"] == FORMAL_SHA256,
        "Formal GLB changed during R2W",
    )
    require(
        current["v5_review_glb"]["sha256"] == V5_GLB_SHA256,
        "Locked V5 review GLB changed during R2W",
    )
    require(
        current["v5_review_blend"]["sha256"] == V5_BLEND_SHA256,
        "Locked V5 review Blend changed during R2W",
    )
    return current


def validate_web_build() -> dict[str, Any]:
    report = load_json(REPORTS / "web_candidate_build_report.json")
    require(report.get("passed") is True, "R2W web build report did not pass")
    require(
        report.get("scope")
        == {
            "camera_only": True,
            "glb_modified": False,
            "material_modified": False,
            "lighting_modified": False,
            "exposure_modified": False,
            "environment_modified": False,
            "tone_mapping_modified": False,
            "ao_integrated": False,
            "reference_status": "REF-PENDING",
            "production_integration_allowed": False,
        },
        "R2W web build scope drifted from the camera-only contract",
    )
    expected = report.get("outputs", [])
    require(len(expected) == len(WEB_OUTPUTS), "Unexpected R2W web output count")
    current = [artifact(path) for path in WEB_OUTPUTS]
    require(expected == current, "R2W web outputs changed after the build report")
    require(
        all(check.get("passed") is True for check in report.get("checks", [])),
        "At least one R2W web build assertion failed",
    )
    return report


def validate_web_matrix() -> dict[str, Any]:
    report = load_json(REPORTS / "bf3d_review_r2w_preview_report.json")
    require(
        report.get("overall_status") == "full_matrix_passed_illustrative_only",
        "R2W full browser matrix did not pass",
    )
    require(report.get("stability_gate_passed") is True, "Stability gate failed")
    require(
        report.get("stability_iterations_required") == 2
        and report.get("stability_iterations_completed") == 2,
        "R2W must complete two stability iterations",
    )
    require(
        report.get("required_runs") == 17
        and report.get("total_viewport_runs") == 34
        and report.get("total_passed_runs") == 34
        and report.get("total_failed_runs") == 0,
        "R2W browser run count mismatch",
    )
    require(
        report.get("required_screenshots_per_run") == 4
        and report.get("total_screenshot_captures") == 136,
        "R2W screenshot-capture count mismatch",
    )
    require(
        report.get("protected_files_unchanged") is True
        and report.get("protected_files_before")
        == report.get("protected_files_after"),
        "R2W protected assets changed",
    )
    errors = report.get("error_totals", {})
    for name in ("console", "page", "http", "external", "request_failed"):
        require(errors.get(name) == 0, f"R2W {name} errors are not zero")
    require(not report.get("hard_failures"), "R2W matrix has hard failures")
    require(report.get("approval_granted") is False, "R2W over-approved itself")
    require(
        report.get("capture_eligible_for_numeric_ab") is False,
        "R2W cannot be eligible for numeric Blender/Three A/B",
    )
    require(
        len(list((PREVIEW / "screenshots").glob("*.png"))) == 68,
        "R2W must retain 68 unique matrix screenshot files",
    )
    return report


def validate_ao_audit() -> dict[str, Any]:
    report = load_json(REPORTS / "ao_consumption_audit.json")
    require(report.get("audit_passed") is True, "AO diagnostic audit failed")
    require(
        report.get("current_ao_signal_present") is False,
        "R2W unexpectedly found an AO signal",
    )
    require(
        report.get("current_glb_occlusion_bound") is False,
        "R2W unexpectedly found a GLB occlusion binding",
    )
    require(
        report.get("current_blend_orm_r_connected") is False,
        "R2W unexpectedly found a Blend ORM.R connection",
    )
    require(
        report.get("reuse_old_p50_atlas_allowed") is False,
        "R2W must forbid direct reuse of the old P50 atlas",
    )
    require(
        report.get("ao_consumption_ready") is False
        and report.get("release_or_production_approval_granted") is False,
        "R2W AO audit over-approved an absent AO path",
    )
    red = (
        report["current_r2g_orm_4k"]["decoded_statistics"]["channels"]["R"]
    )
    require(
        red.get("min_u8") == 255
        and red.get("max_u8") == 255
        and red.get("stddev_u8") == 0.0
        and red.get("nonwhite_sample_count") == 0,
        "R2W AO red-channel statistics changed",
    )
    return report


def validate_gap_audit() -> dict[str, Any]:
    report = load_json(REPORTS / "interface_gap_audit.json")
    require(
        report.get("result")
        == "fail_closed_missing_expected_L04_section_coverage",
        "R2W adjacent-layer audit did not fail closed as expected",
    )
    require(
        report.get("adjacent_layer_continuity_passed") is False,
        "R2W must not approve adjacent-layer continuity",
    )
    require(
        report.get("design_reference_required") is True,
        "R2W must require a design reference",
    )
    require(
        report.get("scene_saved_or_mutated") is False,
        "R2W gap audit mutated the locked scene",
    )
    checks = report.get("checks", {})
    require(
        checks.get("L04_coverage_ratio_over_copper_height_is_zero") is True
        and checks.get("L04_present_and_fills_radial_envelope") is False
        and checks.get("earlier_direct_L03_to_L05_gap_claim_valid") is False,
        "R2W L03/L04/L05 adjacency checks drifted",
    )
    diagnostic = report.get(
        "nonadjacent_L03_to_L05_cut_boundary_diagnostic", {}
    )
    require(
        diagnostic.get("eligible_as_adjacent_layer_gap") is False
        and diagnostic.get("prior_bilateral_maximum_mm") == 49.455908,
        "R2W non-adjacent direct-difference diagnostic drifted",
    )
    return report


def validate_independent_review() -> dict[str, Any]:
    review = load_json(REPORTS / "independent_review_decisions.json")
    require(
        review.get("decision")
        == "conditional_pass_r2w_camera_readability_candidate_only",
        "R2W independent visual decision is not the expected conditional pass",
    )
    require(
        review.get("camera_readability_candidate_approved") is True,
        "R2W camera readability was not approved",
    )
    for key in (
        "p50_approved",
        "p60_approved",
        "p70_approved",
        "qa70_approved",
        "production_integration_approved",
        "numeric_blender_three_equivalence_approved",
    ):
        require(review.get(key) is False, f"R2W review over-approved {key}")
    return review


def build_stage_status(
    locked: dict[str, dict[str, Any]],
    matrix: dict[str, Any],
) -> dict[str, Any]:
    return {
        "schema_version": "bf3d.r2w.pipeline_status.v1",
        "requirement_id": REQUIREMENT_ID,
        "stage_id": STAGE_ID,
        "updated_at": now_iso(),
        "status": STATUS,
        "approval": "isolated_camera_readability_passed_release_not_granted",
        "approval_boundary": (
            "E/illustrative R2W camera-readability candidate only; AO, "
            "adjacent-layer continuity, P50/P60/P70/QA70, production, field "
            "performance and numerical Blender/Three equivalence remain blocked."
        ),
        "camera_readability_scope_passed": True,
        "ao_consumption_ready": False,
        "adjacent_layer_continuity_passed": False,
        "design_reference_required": True,
        "production_integration_allowed": False,
        "next_release_stage_allowed": False,
        "locked_assets": locked,
        "web_matrix": {
            "status": matrix["overall_status"],
            "iterations": matrix["stability_iterations_completed"],
            "runs": matrix["total_viewport_runs"],
            "passed_runs": matrix["total_passed_runs"],
            "captures": matrix["total_screenshot_captures"],
            "unique_screenshot_files": 68,
            "error_totals": matrix["error_totals"],
        },
        "reports": {
            "ao": rel(REPORTS / "ao_consumption_audit.json"),
            "adjacent_layers": rel(REPORTS / "interface_gap_audit.json"),
            "web_matrix": rel(
                REPORTS / "bf3d_review_r2w_preview_report.json"
            ),
            "independent_review": rel(
                REPORTS / "independent_review_decisions.json"
            ),
        },
        "next_stop_line": (
            "Create a new, non-V5 current-R2J AO rebake candidate with an "
            "independent AO UV and explicit glTF/Three consumption; resolve "
            "L04 coverage only from a locked design reference."
        ),
    }


def write_input_lock(
    locked: dict[str, dict[str, Any]],
    matrix: dict[str, Any],
    ao: dict[str, Any],
) -> None:
    value = {
        "schema_version": "bf3d.r2w.input_lock.v1",
        "requirement_id": REQUIREMENT_ID,
        "stage_id": STAGE_ID,
        "generated_at": now_iso(),
        "locked_primary_assets": locked,
        "protected_files_before_matrix": matrix["protected_files_before"],
        "ao_audit_input_locks": ao["input_locks"],
        "mutation_policy": {
            "v5_assets_mutable": False,
            "formal_glb_mutable": False,
            "production_page_mutable": False,
            "camera_only_isolated_web_candidate": True,
        },
    }
    write_json(STAGE / "input_lock.json", value)


def update_root_pipeline(stage_status: dict[str, Any]) -> None:
    path = ROOT / "reports" / "pipeline_status.json"
    root_status = load_json(path)
    stages = root_status.get("stages")
    require(isinstance(stages, dict), "Root pipeline stages must be an object")
    stages[STAGE_ID] = {
        "status": STATUS,
        "camera_readability_scope_passed": True,
        "approval": "isolated_camera_readability_passed_release_not_granted",
        "approval_boundary": stage_status["approval_boundary"],
        "formal_glb_sha256": FORMAL_SHA256,
        "formal_glb_unchanged": True,
        "v5_review_glb": rel(V5_GLB),
        "v5_review_glb_sha256": V5_GLB_SHA256,
        "v5_review_blend": rel(V5_BLEND),
        "v5_review_blend_sha256": V5_BLEND_SHA256,
        "web_matrix_report": rel(
            REPORTS / "bf3d_review_r2w_preview_report.json"
        ),
        "ao_audit": rel(REPORTS / "ao_consumption_audit.json"),
        "adjacent_layer_audit": rel(REPORTS / "interface_gap_audit.json"),
        "independent_review": rel(
            REPORTS / "independent_review_decisions.json"
        ),
        "summary": rel(STAGE / "WEB-60_R2W_阶段成果总结.md"),
        "root_decision": rel(STAGE / "WEB-60_R2W_根审查结论.md"),
        "ao_consumption_ready": False,
        "adjacent_layer_continuity_passed": False,
        "production_integration_allowed": False,
        "next_release_stage_allowed": False,
        "next_stop_line": stage_status["next_stop_line"],
    }
    root_status["current_stage"] = STAGE_ID
    root_status["updated_at"] = now_iso()
    write_json(path, root_status)


def write_artifact_manifest() -> None:
    excluded = {
        (STAGE / "artifact_manifest.json").resolve(),
    }
    paths = [
        path
        for path in STAGE.rglob("*")
        if path.is_file() and path.resolve() not in excluded
    ]
    paths.extend(WEB_OUTPUTS)
    paths.append(ROOT / "tools" / "audit_bf3d_r2w_ao_consumption.py")
    paths.append(ROOT / "tools" / "audit_bf3d_r2w_interface_gap.py")
    paths.append(ROOT / "tools" / "build_bf3d_review_r2w_web.py")
    paths.append(ROOT / "tools" / "finalize_bf3d_r2w_stage.py")
    unique = sorted({path.resolve() for path in paths}, key=lambda p: str(p))
    manifest = {
        "schema_version": "bf3d.r2w.artifact_manifest.v1",
        "requirement_id": REQUIREMENT_ID,
        "stage_id": STAGE_ID,
        "generated_at": now_iso(),
        "artifact_count": len(unique),
        "artifacts": [artifact(path) for path in unique],
    }
    write_json(STAGE / "artifact_manifest.json", manifest)


def main() -> None:
    require(STAGE.is_dir(), f"R2W stage directory is missing: {STAGE}")
    locked = validate_locked_assets()
    validate_web_build()
    matrix = validate_web_matrix()
    ao = validate_ao_audit()
    validate_gap_audit()
    validate_independent_review()

    for required_doc in (
        STAGE / "WEB-60_R2W_阶段成果总结.md",
        STAGE / "WEB-60_R2W_根审查结论.md",
    ):
        require(
            required_doc.is_file(),
            f"Traceability document must exist before finalization: {required_doc}",
        )

    write_input_lock(locked, matrix, ao)
    status = build_stage_status(locked, matrix)
    write_json(STAGE / "pipeline_status.json", status)
    update_root_pipeline(status)
    write_artifact_manifest()

    print(
        json.dumps(
            {
                "stage_id": STAGE_ID,
                "status": STATUS,
                "camera_readability_scope_passed": True,
                "ao_consumption_ready": False,
                "adjacent_layer_continuity_passed": False,
                "production_integration_allowed": False,
                "next_release_stage_allowed": False,
                "matrix_runs": matrix["total_viewport_runs"],
                "matrix_captures": matrix["total_screenshot_captures"],
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
