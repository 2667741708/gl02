"""Fail-closed stage-local finalizer for the WEB-60 R2X 1K AO smoke stage.

Requirement:
    REQ-BF3D-R2X-R2J-AO-REBAKE-CONSUMPTION-20260720

The finalizer is deliberately stage-local.  It reads locked V5/formal inputs,
the Blender build/reopen evidence, the V5-payload repack evidence, the
independent read-only audit, and the representative Three.js/visual report.
It never modifies GLB, Blend, texture, Web, root pipeline, or cross-stage
documentation.

No seal is written until
``reports/bf3d_review_r2x_representative_report.json`` exists and carries a
schema-valid explicit pass/fail conclusion.

Commands:
    python tools/finalize_bf3d_r2x_stage.py --preflight
    python tools/finalize_bf3d_r2x_stage.py
    python tools/finalize_bf3d_r2x_stage.py --print-json

Exit codes:
    0: preflight/finalization succeeded
    1: evidence validation failed closed
    2: representative Web report is not ready
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import sys
import traceback
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable


ROOT = Path(__file__).resolve().parents[1]
STAGE_ID = "WEB_60_20260720_R2X_R2J_AO_REBAKE_CANDIDATE"
REQUIREMENT_ID = "REQ-BF3D-R2X-R2J-AO-REBAKE-CONSUMPTION-20260720"
STAGE = ROOT / "PT" / "高炉3D模型" / "work" / STAGE_ID
REPORTS = STAGE / "reports"

CONTRACT = STAGE / "WEB-60_R2X_阶段预注册合同.md"
BUILD_REPORT = REPORTS / "r2x_ao_smoke1k_build_report.json"
REOPEN_REPORT = REPORTS / "r2x_ao_smoke1k_reopen_report.json"
REPACK_REPORT = REPORTS / "r2x_ao_v5_payload_repack_report.json"
INDEPENDENT_AUDIT = REPORTS / "r2x_ao_smoke1k_v5payload_audit.json"
KHRONOS_REPORT = REPORTS / "khronos_gltf_validator_r2x_ao_v5payload.json"
WEB_BUILD_REPORT = REPORTS / "r2x_web_candidate_build_report.json"
REPRESENTATIVE_REPORT = (
    REPORTS / "bf3d_review_r2x_representative_report.json"
)
INDEPENDENT_VISUAL_REVIEW = (
    REPORTS / "r2x_independent_visual_review.json"
)

SUMMARY_DOC = STAGE / "WEB-60_R2X_阶段成果总结.md"
ROOT_DECISION_DOC = STAGE / "WEB-60_R2X_根审查结论.md"
INPUT_LOCK = STAGE / "input_lock.json"
PIPELINE_STATUS = STAGE / "pipeline_status.json"
ARTIFACT_MANIFEST = STAGE / "artifact_manifest.json"
AUTHORIZED_SEAL_OUTPUTS = (
    SUMMARY_DOC,
    ROOT_DECISION_DOC,
    INPUT_LOCK,
    PIPELINE_STATUS,
    ARTIFACT_MANIFEST,
)

V5_BLEND = (
    ROOT
    / "高炉前端数据"
    / "models"
    / "gl02_blast_furnace_review.v5.blend"
)
V5_UNIFIED_GLB = (
    ROOT
    / "高炉前端数据"
    / "models"
    / "gl02_blast_furnace_review.v5.glb"
)
V5_MATERIAL_GLB = (
    ROOT
    / "高炉前端数据"
    / "models"
    / "gl02_blast_furnace_material_review.v5.glb"
)
V5_STRUCTURAL_GLB = (
    ROOT
    / "高炉前端数据"
    / "models"
    / "gl02_blast_furnace_structural_review.v5.glb"
)
FORMAL_GLB = (
    ROOT / "高炉前端数据" / "models" / "gl02_blast_furnace.glb"
)
CURRENT_ORM = (
    ROOT
    / "PT"
    / "高炉3D模型"
    / "work"
    / "INT_30_20260718_R2G_ISOLATED_GLB_WEB_PREVIEW"
    / "textures"
    / "final_4k"
    / "INT30_R2G_R1_LOCK_ORM_4K.png"
)

CANDIDATE_BLEND = (
    STAGE
    / "blends"
    / "gl02_blast_furnace_review.r2x-ao-smoke1k.blend"
)
AO_PNG = STAGE / "textures" / "GL02_R2J_LOCAL_CONTACT_AO_1K.png"
SOURCE_CANDIDATE_GLB = (
    STAGE
    / "glb"
    / "gl02_blast_furnace_material_review.r2x-ao-smoke1k.glb"
)
FINAL_CANDIDATE_GLB = (
    STAGE
    / "glb"
    / "gl02_blast_furnace_material_review.r2x-ao-smoke1k.v5payload.glb"
)
WEB_PAGE = ROOT / "高炉前端数据" / "bf3d_review_r2x.server.html"
WEB_RENDERER = (
    ROOT / "高炉前端数据" / "assets" / "bf3d-review-renderer-r2x.js"
)
WEB_SERVE_SCRIPT = ROOT / "tools" / "serve_bf3d_review_r2x.py"
WEB_VERIFY_SCRIPT = ROOT / "tools" / "verify_bf3d_review_r2x_preview.cjs"
WEB_BUILD_SCRIPT = ROOT / "tools" / "build_bf3d_review_r2x_web.py"
WEB_RUNTIME_PATHS = (WEB_PAGE, WEB_RENDERER)
WEB_BUILD_OUTPUT_PATHS = (
    WEB_PAGE,
    WEB_RENDERER,
    WEB_SERVE_SCRIPT,
    WEB_VERIFY_SCRIPT,
)
PRODUCTION_GUARD_PATHS = (
    ROOT / "高炉前端数据" / "frontend_dashboard_v3.server.html",
    ROOT / "高炉前端数据" / "assets" / "bf3d-structural-review.js",
)

STATUS_REPRESENTATIVE_PASS = (
    "r2x_smoke1k_representative_passed_full_matrix_pending"
)
STATUS_REPRESENTATIVE_FAIL = (
    "r2x_machine_passed_three_visual_failed_closed"
)
WEB_STATUS_PASS = "representative_passed_pending_root_visual_review"
WEB_STATUS_FAIL = "representative_fail_closed"

EXPECTED_CANDIDATE_SHA256 = (
    "bd074c23c237fe7ff3abac0f823bd9aef978021e4e829963b3f979e9b58f1c00"
)
EXPECTED_CANDIDATE_BYTES = 1_115_216
FIRST_FAILED_CANDIDATE_SHA256 = (
    "c8b748ef03b516a78de658a3b25a5f2265fef9bd34cea334a3490fba1fbab139"
)

PRIMARY_LOCKS: dict[str, tuple[Path, str]] = {
    "v5_blend": (
        V5_BLEND,
        "3e6df5fb02d3734d14923d4432739a5918ac8249d6a3c8ad1415395429b27e3a",
    ),
    "v5_unified_glb": (
        V5_UNIFIED_GLB,
        "0ac031e626c9eaa0b0cdd8192cf9fda712324af174a4285f563a97309451ed3c",
    ),
    "v5_material_glb": (
        V5_MATERIAL_GLB,
        "652be1b2c9147d5a7392497c7ae4964d19bdd7095b5435b87c105f9eb3fb66bc",
    ),
    "v5_structural_glb": (
        V5_STRUCTURAL_GLB,
        "e5c77d3834c631e2513209a690f6328d1c63dba2c8d489b2d2dbe17645465f71",
    ),
    "formal_glb": (
        FORMAL_GLB,
        "808960f1b2703e7fb27df35f1b1b1a17063b9b10d2267acba593fc3872b62af6",
    ),
    "current_orm_4k": (
        CURRENT_ORM,
        "e3354cc5d793807ebb4f6b0d74593a7b6f09f18fcece8f9102e867f2c8570e17",
    ),
    "stage_contract": (
        CONTRACT,
        "14432e1cc140b29bff216df470018f028b579ad9ddc413446b07f47369847639",
    ),
}

MACHINE_EVIDENCE_LOCKS: dict[str, tuple[Path, str]] = {
    "candidate_blend": (
        CANDIDATE_BLEND,
        "4b1976f7c2c4fcbdc54fbfe881a223d42ddbe35a56e5f2a91529476cb23d71f0",
    ),
    "ao_png": (
        AO_PNG,
        "c1362fa572e94e2b8f704ab9d3ec46aed6cc930d7616bb4ad14a38793abcf786",
    ),
    "source_candidate_glb": (
        SOURCE_CANDIDATE_GLB,
        "a7c9842331a3bae69d7555ac31c3310daec8d883f7b1afcbbf0d5f67c494c6ab",
    ),
    "v5payload_candidate_glb": (
        FINAL_CANDIDATE_GLB,
        EXPECTED_CANDIDATE_SHA256,
    ),
    "build_report": (
        BUILD_REPORT,
        "c10828270c83e11fc7d44f3ae24ab4ce2663d9252d3fce105241135493521589",
    ),
    "reopen_report": (
        REOPEN_REPORT,
        "f5de845f6fb56825e4f0baa18974c003196925f3ef96a21153dd9b1af69f8157",
    ),
    "repack_report": (
        REPACK_REPORT,
        "79017487f5868c72db02931cccc9b666715ed98065287b28ef29fbba445f2c05",
    ),
    "independent_audit": (
        INDEPENDENT_AUDIT,
        "c579477603f6c6a8775ac5bf6c61142be1b447a216df74976061091842a8ab4a",
    ),
    "khronos_report": (
        KHRONOS_REPORT,
        "bdc0b4e9fe9e9acf55f7b52703e6257d09ff1c9b294eb6fd2a9ef58d10aeb422",
    ),
}

STOP_LINES = {
    "approval_granted": False,
    "ao_2k_approved": False,
    "p50_approved": False,
    "p60_approved": False,
    "production_integration_allowed": False,
    "next_release_stage_allowed": False,
}

IMPLEMENTATION_PATHS = (
    ROOT / "tools" / "build_bf3d_r2x_r2j_ao_candidate.py",
    ROOT / "tools" / "repack_bf3d_r2x_ao_v5_payload.py",
    ROOT / "tools" / "audit_bf3d_r2x_ao_candidate.py",
    WEB_BUILD_SCRIPT,
    WEB_SERVE_SCRIPT,
    WEB_VERIFY_SCRIPT,
    ROOT / "tools" / "finalize_bf3d_r2x_stage.py",
)


class FinalizationError(RuntimeError):
    """Raised when stage evidence is inconsistent or over-approves scope."""


class FinalizationBlocked(FinalizationError):
    """Raised when the representative Web report is not ready."""


def now_iso() -> str:
    """Return an ISO timestamp in the project timezone."""

    return datetime.now(timezone(timedelta(hours=8))).isoformat(
        timespec="seconds"
    )


def require(condition: bool, message: str) -> None:
    """Raise a fail-closed validation error when a condition is false."""

    if not condition:
        raise FinalizationError(message)


def sha256_bytes(payload: bytes) -> str:
    """Return the SHA-256 digest of bytes."""

    return hashlib.sha256(payload).hexdigest()


def sha256_file(path: Path) -> str:
    """Return the SHA-256 digest of a file."""

    require(path.is_file(), f"Required file is missing: {path}")
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def rel(path: Path) -> str:
    """Return a repository-relative POSIX path."""

    return path.resolve().relative_to(ROOT.resolve()).as_posix()


def artifact(
    path: Path,
    expected_sha256: str | None = None,
) -> dict[str, Any]:
    """Describe one file and optionally enforce a known digest."""

    require(path.is_file(), f"Required artifact is missing: {path}")
    actual = sha256_file(path)
    record: dict[str, Any] = {
        "path": rel(path),
        "bytes": path.stat().st_size,
        "sha256": actual,
    }
    if expected_sha256 is not None:
        record["expected_sha256"] = expected_sha256
        record["matches_expected"] = actual == expected_sha256
        require(
            actual == expected_sha256,
            f"Artifact hash drifted: {rel(path)}: "
            f"expected={expected_sha256}, actual={actual}",
        )
    return record


def artifact_from_bytes(path: Path, payload: bytes) -> dict[str, Any]:
    """Describe bytes read from a repository file in one immutable snapshot."""

    return {
        "path": rel(path),
        "bytes": len(payload),
        "sha256": sha256_bytes(payload),
    }


def load_json(path: Path) -> dict[str, Any]:
    """Load one required UTF-8 JSON object."""

    require(path.is_file(), f"Required JSON is missing: {path}")
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise FinalizationError(f"Invalid JSON {path}: {exc}") from exc
    require(isinstance(value, dict), f"Expected JSON object: {path}")
    return value


def load_json_snapshot(
    path: Path,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Load JSON and bind validation to the exact bytes that were parsed."""

    require(path.is_file(), f"Required JSON is missing: {path}")
    try:
        payload = path.read_bytes()
        value = json.loads(payload.decode("utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise FinalizationError(f"Invalid JSON {path}: {exc}") from exc
    require(isinstance(value, dict), f"Expected JSON object: {path}")
    return value, artifact_from_bytes(path, payload)


def repo_path_from_record(
    record: Any,
    label: str,
    *,
    allowed_parent: Path | None = None,
) -> Path:
    """Resolve a reported repository-relative path without allowing escape."""

    require(isinstance(record, dict), f"{label} artifact record is missing")
    raw = record.get("path")
    require(
        isinstance(raw, str) and bool(raw.strip()),
        f"{label} artifact path is invalid",
    )
    candidate = Path(raw)
    require(not candidate.is_absolute(), f"{label} path must be relative")
    resolved = (ROOT / candidate).resolve()
    try:
        resolved.relative_to(ROOT.resolve())
    except ValueError as exc:
        raise FinalizationError(
            f"{label} path escapes the repository: {raw}"
        ) from exc
    require(
        rel(resolved) == raw.replace("\\", "/"),
        f"{label} path is not normalized: {raw}",
    )
    if allowed_parent is not None:
        try:
            resolved.relative_to(allowed_parent.resolve())
        except ValueError as exc:
            raise FinalizationError(
                f"{label} path is outside {rel(allowed_parent)}: {raw}"
            ) from exc
    return resolved


def validate_reported_artifact(
    record: Any,
    label: str,
    *,
    expected_path: Path | None = None,
    allowed_parent: Path | None = None,
) -> dict[str, Any]:
    """Validate one path/bytes/SHA record against the current file."""

    path = repo_path_from_record(
        record,
        label,
        allowed_parent=allowed_parent,
    )
    if expected_path is not None:
        require(
            path == expected_path.resolve(),
            f"{label} path mismatch: {rel(path)}",
        )
    actual = artifact(path)
    require(
        record.get("bytes") == actual["bytes"]
        and record.get("sha256") == actual["sha256"],
        f"{label} bytes/SHA-256 do not match the file",
    )
    return actual


def all_false(value: Any, keys: Iterable[str]) -> bool:
    """Return true only when every named key is explicitly false."""

    return isinstance(value, dict) and all(
        key in value and value[key] is False for key in keys
    )


def all_true_dict(value: Any) -> bool:
    """Return true only for a non-empty dictionary of literal true values."""

    return (
        isinstance(value, dict)
        and bool(value)
        and all(item is True for item in value.values())
    )


def validate_lock_set(
    locks: dict[str, tuple[Path, str]],
) -> dict[str, dict[str, Any]]:
    """Validate and record a named immutable artifact set."""

    return {
        name: artifact(path, expected)
        for name, (path, expected) in locks.items()
    }


def validate_build_report() -> dict[str, Any]:
    """Validate the Blender 1K build report without granting Web approval."""

    report = load_json(BUILD_REPORT)
    require(
        report.get("schema_version")
        == "bf3d.r2x.r2j_ao_smoke1k.build.v1",
        "Unexpected R2X build report schema",
    )
    require(
        report.get("stage_id") == STAGE_ID
        and report.get("requirement_id") == REQUIREMENT_ID,
        "R2X build report identity mismatch",
    )
    require(
        report.get("status")
        == "smoke1k_machine_gates_passed_pending_three_visual_and_independent_review",
        "R2X build report status drifted",
    )
    require(
        report.get("all_machine_gates_passed") is True
        and all_true_dict(report.get("machine_gates")),
        "R2X Blender build machine gates did not all pass",
    )
    require(report.get("errors") == [], "R2X build report has errors")
    scope = report.get("scope")
    require(
        isinstance(scope, dict)
        and scope.get("resolution") == "1K smoke only"
        and {"2K", "4K"}.issubset(set(scope.get("not_generated") or [])),
        "R2X build scope does not preserve the 1K-only stop line",
    )
    boundary = report.get("evidence_boundary")
    require(
        isinstance(boundary, dict)
        and boundary.get("candidate_only") is True
        and boundary.get("three_runtime_check")
        == "not_in_this_blender_build"
        and boundary.get("visual_review") == "pending_independent_review",
        "R2X build evidence boundary drifted",
    )
    require(
        all_false(
            report.get("approval_stop_lines"),
            (
                "approval_granted",
                "p50_approved",
                "production_integration_allowed",
                "next_release_stage_allowed",
            ),
        ),
        "R2X build report over-approved its scope",
    )
    return report


def validate_reopen_report() -> dict[str, Any]:
    """Validate the Blender reopen persistence report."""

    report = load_json(REOPEN_REPORT)
    require(
        report.get("schema_version")
        == "bf3d.r2x.r2j_ao_smoke1k.reopen.v1",
        "Unexpected R2X reopen report schema",
    )
    require(
        report.get("stage_id") == STAGE_ID
        and report.get("requirement_id") == REQUIREMENT_ID
        and report.get("status") == "reopen_passed"
        and report.get("passed") is True,
        "R2X reopen report did not pass",
    )
    require(
        all_true_dict(report.get("checks")),
        "At least one R2X reopen check failed",
    )
    require(report.get("errors") == [], "R2X reopen report has errors")
    return report


def validate_repack_report() -> dict[str, Any]:
    """Validate the surgical V5-payload repack report."""

    report = load_json(REPACK_REPORT)
    require(
        report.get("schema")
        == "bf3d.r2x.r2j_ao_v5_payload_repack.v1",
        "Unexpected R2X V5-payload repack schema",
    )
    require(
        report.get("stage_id") == STAGE_ID
        and report.get("requirement_id") == REQUIREMENT_ID
        and report.get("status") == "passed_smoke_only"
        and report.get("passed") is True,
        "R2X V5-payload repack did not pass",
    )
    require(
        all_true_dict(report.get("machine_gates")),
        "At least one V5-payload repack machine gate failed",
    )
    require(report.get("errors") == [], "R2X repack report has errors")
    output = report.get("output")
    require(
        isinstance(output, dict)
        and output.get("sha256") == EXPECTED_CANDIDATE_SHA256
        and output.get("bytes") == EXPECTED_CANDIDATE_BYTES,
        "R2X repack output identity mismatch",
    )
    validator = report.get("khronos_validator")
    require(
        isinstance(validator, dict)
        and validator.get("passed") is True
        and validator.get("errors") == 0
        and validator.get("warnings") == 0
        and validator.get("version_matches_expected") is True,
        "R2X repack Khronos gate did not pass at 0/0",
    )
    protected = report.get("protected_hashes_before_after")
    require(
        isinstance(protected, dict)
        and protected.get("all_unchanged") is True
        and protected.get("all_match_expected") is True,
        "R2X protected inputs changed during repack",
    )
    sampler_identity = (
        report.get("baseline_identity", {})
        .get("array_prefix_identity", {})
        .get("samplers", {})
    )
    require(
        sampler_identity.get("exact") is True
        and sampler_identity.get("v5_count") == 1
        and sampler_identity.get("output_count") == 1,
        "R2X final candidate did not preserve the V5 sampler array",
    )
    require(
        all_false(report.get("approval_stop_lines"), STOP_LINES),
        "R2X repack report over-approved 2K/P50/P60/production",
    )
    return report


def validate_khronos_report() -> dict[str, Any]:
    """Validate the native Khronos report used by the repack audit."""

    report = load_json(KHRONOS_REPORT)
    issues = report.get("issues")
    require(
        report.get("validatorVersion") == "2.0.0-dev.3.10"
        and isinstance(issues, dict)
        and issues.get("numErrors") == 0
        and issues.get("numWarnings") == 0,
        "Native Khronos Validator result is not 0 errors / 0 warnings",
    )
    return report


def validate_attempt_history(value: Any) -> list[dict[str, Any]]:
    """Require preservation of the first unauthorized-sampler failure."""

    require(
        isinstance(value, list) and bool(value),
        "Independent audit attempt_history is missing",
    )
    first = value[0]
    require(
        isinstance(first, dict)
        and first.get("attempt") == 1
        and first.get("candidate_glb_sha256")
        == FIRST_FAILED_CANDIDATE_SHA256
        and first.get("result") == "fail_closed"
        and first.get("finding_code")
        == "UNAUTHORIZED_EXTRA_AO_CLAMP_SAMPLER"
        and first.get("p50_approved") is False
        and first.get("production_integration_allowed") is False,
        "First unauthorized-sampler failure history was lost or changed",
    )
    return value


def validate_independent_audit() -> dict[str, Any]:
    """Validate the final independent read-only machine audit."""

    report = load_json(INDEPENDENT_AUDIT)
    require(
        report.get("schema_version")
        == "bf3d.r2x.ao_smoke1k_v5payload_audit.v2",
        "Unexpected R2X independent audit schema",
    )
    require(
        report.get("stage_id") == STAGE_ID
        and report.get("requirement_id") == REQUIREMENT_ID,
        "R2X independent audit identity mismatch",
    )
    require(
        report.get("audit_completed") is True
        and report.get("audit_passed") is True
        and report.get("contract_machine_gate_passed") is True,
        "R2X independent machine audit did not pass",
    )
    require(
        all_true_dict(report.get("assertions")),
        "At least one independent audit assertion failed",
    )
    require(
        report.get("smoke1k_upgrade_gate_passed") is False
        and report.get("three_runtime_gate_passed") is False
        and report.get("visual_whitelist_gate_passed") is False,
        "Independent machine audit over-claimed later gates",
    )
    require(
        all_false(
            report,
            (
                "approval_granted",
                "ao_2k_approved",
                "p50_approved",
                "production_integration_allowed",
                "next_release_stage_allowed",
            ),
        ),
        "Independent audit over-approved the candidate",
    )
    candidate = report.get("candidate_material_glb", {}).get("artifact", {})
    require(
        candidate.get("sha256") == EXPECTED_CANDIDATE_SHA256
        and candidate.get("bytes") == EXPECTED_CANDIDATE_BYTES,
        "Independent audit is not bound to the final candidate GLB",
    )
    require(
        report.get("candidate_artifacts_before")
        == report.get("candidate_artifacts_after"),
        "Candidate artifacts changed during the independent audit",
    )
    validate_attempt_history(report.get("attempt_history"))
    return report


def validate_web_build_report(
    primary_locks: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    """Validate the isolated representative Web build and its live outputs."""

    report, report_artifact = load_json_snapshot(WEB_BUILD_REPORT)
    require(
        report.get("schema_version")
        == "bf3d.r2x.web_candidate_build.v1",
        "Unexpected R2X Web build report schema",
    )
    require(
        report.get("stage_id") == STAGE_ID
        and report.get("requirement_id") == REQUIREMENT_ID
        and report.get("passed") is True,
        "R2X Web candidate build did not pass",
    )
    candidate = report.get("candidate")
    require(
        isinstance(candidate, dict)
        and candidate.get("path") == rel(FINAL_CANDIDATE_GLB)
        and candidate.get("bytes") == EXPECTED_CANDIDATE_BYTES
        and candidate.get("sha256") == EXPECTED_CANDIDATE_SHA256,
        "R2X Web build is not bound to the final candidate",
    )
    scope = report.get("scope")
    require(
        isinstance(scope, dict)
        and scope.get("resolution") == "1K smoke"
        and scope.get("representative_only") is True
        and scope.get("browser") == "Chromium"
        and scope.get("viewport") == [1440, 900]
        and scope.get("runtime_change")
        == "five shell aoMapIntensity only"
        and scope.get("glb_modified") is False
        and scope.get("material_modified") is False
        and scope.get("lighting_modified") is False
        and scope.get("exposure_modified") is False
        and scope.get("environment_modified") is False
        and scope.get("tone_mapping_modified") is False
        and scope.get("camera_modified_from_r2w") is False
        and scope.get("p50_approved") is False
        and scope.get("production_integration_allowed") is False,
        "R2X Web build scope or mutation boundary drifted",
    )
    checks = report.get("checks")
    expected_check_ids = {
        "candidate_lock",
        "protected_v5_and_formal_locks",
        "candidate_glb_contract",
        "page_scope_disclosure",
        "single_v5payload_url",
        "runtime_ao_contract",
        "locked_r2w_p40_color_camera_contract",
        "server_isolated_allow_list",
        "representative_only_four_capture_verifier",
    }
    require(
        isinstance(checks, list)
        and len(checks) == len(expected_check_ids)
        and {
            item.get("id")
            for item in checks
            if isinstance(item, dict)
        }
        == expected_check_ids
        and all(
            isinstance(item, dict) and item.get("passed") is True
            for item in checks
        ),
        "R2X Web build checks are incomplete or failed",
    )
    glb_contract = report.get("glb_contract")
    require(
        isinstance(glb_contract, dict)
        and glb_contract.get("passed") is True,
        "R2X Web build GLB contract did not pass",
    )

    outputs = report.get("outputs")
    require(
        isinstance(outputs, list)
        and len(outputs) == len(WEB_BUILD_OUTPUT_PATHS),
        "R2X Web build output list is incomplete",
    )
    output_records: dict[str, dict[str, Any]] = {}
    expected_output_by_rel = {
        rel(path): path for path in WEB_BUILD_OUTPUT_PATHS
    }
    for item in outputs:
        require(
            isinstance(item, dict)
            and item.get("path") in expected_output_by_rel,
            "R2X Web build reports an unauthorized output",
        )
        key = item["path"]
        require(key not in output_records, f"Duplicate Web output: {key}")
        output_records[key] = validate_reported_artifact(
            item,
            f"Web build output {key}",
            expected_path=expected_output_by_rel[key],
        )
    require(
        set(output_records) == set(expected_output_by_rel),
        "R2X Web build output paths differ from the isolated allow-list",
    )

    protected = report.get("protected_v5_and_formal")
    require(
        isinstance(protected, dict) and len(protected) == 5,
        "R2X Web build protected V5/formal snapshot is incomplete",
    )
    expected_protected = {
        primary_locks[name]["path"]: {
            key: primary_locks[name][key]
            for key in ("path", "bytes", "sha256")
        }
        for name in (
            "v5_blend",
            "v5_unified_glb",
            "v5_material_glb",
            "v5_structural_glb",
            "formal_glb",
        )
    }
    actual_protected: dict[str, dict[str, Any]] = {}
    for item in protected.values():
        actual = validate_reported_artifact(
            item,
            "Web build protected V5/formal input",
        )
        require(
            actual["path"] not in actual_protected,
            f"Duplicate protected Web-build input: {actual['path']}",
        )
        actual_protected[actual["path"]] = actual
    require(
        actual_protected == expected_protected,
        "R2X Web build protected V5/formal snapshot drifted",
    )

    production = report.get("production_files_snapshot")
    require(
        isinstance(production, dict)
        and len(production) == len(PRODUCTION_GUARD_PATHS),
        "R2X Web build production guard snapshot is incomplete",
    )
    expected_production = {
        rel(path): path for path in PRODUCTION_GUARD_PATHS
    }
    production_records: dict[str, dict[str, Any]] = {}
    for item in production.values():
        actual = validate_reported_artifact(
            item,
            "Web build protected production file",
        )
        require(
            actual["path"] in expected_production,
            f"Unexpected production guard: {actual['path']}",
        )
        require(
            actual["path"] not in production_records,
            f"Duplicate production guard: {actual['path']}",
        )
        production_records[actual["path"]] = actual
    require(
        set(production_records) == set(expected_production),
        "R2X Web build production guard paths drifted",
    )

    return {
        "report": report,
        "report_artifact": report_artifact,
        "output_artifacts": [
            output_records[key] for key in sorted(output_records)
        ],
        "production_guard_artifacts": [
            production_records[key] for key in sorted(production_records)
        ],
    }


def validate_pair_metrics(name: str, value: Any) -> dict[str, Any]:
    """Validate one representative AO off/on pixel-difference record."""

    require(isinstance(value, dict), f"Missing {name} AO pair metrics")
    require(
        value.get("pair") == name,
        f"Representative pair identity mismatch: {name}",
    )
    for field in (
        "passed",
        "ao_difference_too_weak",
        "false_ring_detected",
        "overall_darkening_detected",
        "unexpected_brightening_detected",
    ):
        require(
            isinstance(value.get(field), bool),
            f"Representative pair {name}.{field} must be boolean",
        )
    for field in ("width", "height", "pixel_count", "changed_pixels"):
        require(
            isinstance(value.get(field), int)
            and not isinstance(value.get(field), bool)
            and value[field] >= 0,
            f"Representative pair {name}.{field} must be non-negative int",
        )
    require(
        value["width"] > 0
        and value["height"] > 0
        and value["pixel_count"] == value["width"] * value["height"]
        and value["changed_pixels"] <= value["pixel_count"],
        f"Representative pair {name} pixel dimensions are inconsistent",
    )
    numeric_fields = (
        "changed_ratio",
        "mean_abs_diff_all_rgb_u8",
        "mean_abs_diff_changed_rgb_u8",
        "max_abs_diff_u8",
        "full_frame_mean_luma_drop_fraction",
        "foreground_mean_luma_drop_fraction",
        "brightened_share_of_changed",
    )
    for field in numeric_fields:
        number = value.get(field)
        require(
            isinstance(number, (int, float))
            and not isinstance(number, bool),
            f"Representative pair {name}.{field} is not numeric",
        )
    require(
        value["changed_pixels"] >= 0
        and 0.0 <= value["changed_ratio"] <= 1.0
        and value["mean_abs_diff_all_rgb_u8"] >= 0.0
        and value["mean_abs_diff_changed_rgb_u8"] >= 0.0
        and 0.0 <= value["max_abs_diff_u8"] <= 255.0
        and -1.0
        <= value["full_frame_mean_luma_drop_fraction"]
        <= 1.0
        and -1.0
        <= value["foreground_mean_luma_drop_fraction"]
        <= 1.0
        and 0.0 <= value["brightened_share_of_changed"] <= 1.0,
        f"Representative pair {name} metrics are out of range",
    )
    expected_ratio = value["changed_pixels"] / value["pixel_count"]
    require(
        math.isclose(
            float(value["changed_ratio"]),
            expected_ratio,
            rel_tol=1e-12,
            abs_tol=1e-12,
        ),
        f"Representative pair {name} changed ratio is inconsistent",
    )
    pair_failure = any(
        value[field]
        for field in (
            "ao_difference_too_weak",
            "false_ring_detected",
            "overall_darkening_detected",
            "unexpected_brightening_detected",
        )
    )
    require(
        value["passed"] is (not pair_failure),
        f"Representative pair {name} pass flag contradicts its failures",
    )
    return value


def validate_capture_records(
    captures: Any,
    error_keys: tuple[str, ...],
) -> list[dict[str, Any]]:
    """Bind the four representative states to actual screenshot artifacts."""

    require(
        isinstance(captures, list) and len(captures) == 4,
        "Final representative report requires exactly four actual captures",
    )
    expected = {
        "global-off": ("global", False),
        "global-on": ("global", True),
        "detail-off": ("detail", False),
        "detail-on": ("detail", True),
    }
    records: dict[str, dict[str, Any]] = {}
    capture_parent = STAGE / "preview" / "screenshots"
    for capture in captures:
        require(
            isinstance(capture, dict)
            and capture.get("id") in expected,
            "Representative capture has an invalid id",
        )
        capture_id = capture["id"]
        require(
            capture_id not in records,
            f"Duplicate representative capture id: {capture_id}",
        )
        view, ao_enabled = expected[capture_id]
        require(
            capture.get("view") == view
            and capture.get("ao_enabled") is ao_enabled,
            f"Representative capture state mismatch: {capture_id}",
        )
        error_totals = capture.get("error_totals_after_capture")
        require(
            isinstance(error_totals, dict)
            and set(error_totals) == set(error_keys)
            and all(error_totals[key] == 0 for key in error_keys),
            f"Representative capture has runtime errors: {capture_id}",
        )
        actual = validate_reported_artifact(
            capture,
            f"Representative capture {capture_id}",
            allowed_parent=capture_parent,
        )
        require(
            Path(actual["path"]).suffix.lower() == ".png",
            f"Representative capture is not PNG: {capture_id}",
        )
        records[capture_id] = actual
    require(
        set(records) == set(expected),
        "Representative captures do not cover the four fixed states",
    )
    return [records[key] for key in sorted(records)]


def validate_independent_visual_review(
    web: dict[str, Any],
    web_evidence: dict[str, Any],
) -> dict[str, Any]:
    """Validate the independent read-only visual review against Web evidence."""

    report, report_artifact = load_json_snapshot(
        INDEPENDENT_VISUAL_REVIEW
    )
    require(
        report.get("schema_version")
        == "bf3d.r2x.independent_visual_review.v1",
        "Unexpected R2X independent visual review schema",
    )
    require(
        report.get("stage_id") == STAGE_ID
        and report.get("requirement_id") == REQUIREMENT_ID
        and report.get("review_mode")
        == "independent_read_only_sha_byte_pixel_and_visual_inspection",
        "Independent visual review identity/mode mismatch",
    )
    require(
        all_false(report.get("approval_stop_lines"), STOP_LINES),
        "Independent visual review over-approved the R2X candidate",
    )
    scope = report.get("scope")
    require(
        isinstance(scope, dict)
        and scope.get("browser_engine") == "Chromium"
        and scope.get("css_viewport") == {"width": 1440, "height": 900}
        and scope.get("views") == ["global", "detail"]
        and scope.get("ao_states") == ["off", "on"]
        and scope.get("capture_count") == 4
        and scope.get("full_matrix_executed") is False
        and isinstance(scope.get("limitations"), list)
        and bool(scope["limitations"]),
        "Independent visual review scope drifted",
    )
    evidence = report.get("evidence")
    require(
        isinstance(evidence, dict),
        "Independent visual review evidence is missing",
    )
    require(
        evidence.get("representative_web_report")
        == web_evidence["report_artifact"],
        "Independent visual review is not bound to the final Web report",
    )
    candidate = evidence.get("final_candidate_glb")
    require(
        isinstance(candidate, dict)
        and candidate.get("path") == rel(FINAL_CANDIDATE_GLB)
        and candidate.get("bytes") == EXPECTED_CANDIDATE_BYTES
        and candidate.get("sha256") == EXPECTED_CANDIDATE_SHA256,
        "Independent visual review candidate identity mismatch",
    )
    ao_png = evidence.get("ao_png")
    require(
        isinstance(ao_png, dict)
        and ao_png.get("path") == rel(AO_PNG)
        and ao_png.get("bytes") == AO_PNG.stat().st_size
        and ao_png.get("sha256")
        == MACHINE_EVIDENCE_LOCKS["ao_png"][1],
        "Independent visual review AO artifact identity mismatch",
    )
    capture_values = evidence.get("captures")
    require(
        isinstance(capture_values, list) and len(capture_values) == 4,
        "Independent visual review must bind all four captures",
    )
    review_captures: dict[str, dict[str, Any]] = {}
    expected_capture_records = {
        record["path"]: record
        for record in web_evidence["capture_artifacts"]
    }
    for capture in capture_values:
        require(
            isinstance(capture, dict)
            and capture.get("id")
            in {"global-off", "global-on", "detail-off", "detail-on"}
            and capture.get("reported_sha_and_bytes_match") is True
            and capture.get("dimensions") == [1038, 631]
            and capture.get("mode") == "RGB",
            "Independent visual review capture metadata is invalid",
        )
        actual = validate_reported_artifact(
            capture,
            f"Independent visual capture {capture['id']}",
            allowed_parent=STAGE / "preview" / "screenshots",
        )
        require(
            actual["path"] in expected_capture_records
            and actual == expected_capture_records[actual["path"]]
            and capture["id"] not in review_captures,
            "Independent visual capture does not match Web evidence",
        )
        review_captures[capture["id"]] = actual
    require(
        set(review_captures)
        == {"global-off", "global-on", "detail-off", "detail-on"},
        "Independent visual review capture ids are incomplete",
    )

    runtime = report.get("machine_runtime_evidence")
    require(
        isinstance(runtime, dict)
        and runtime.get("representative_report_status")
        == web["overall_status"]
        and runtime.get("runtime_contract_passed")
        is web["machine_three_passed"]
        and runtime.get("machine_three_passed")
        is web["machine_three_passed"]
        and runtime.get("runtime_failed") is web["runtime_failed"]
        and runtime.get("protected_files_unchanged")
        is web["protected_files_unchanged"]
        and runtime.get("error_totals") == web["error_totals"],
        "Independent visual machine-runtime evidence contradicts Web report",
    )
    independent_pairs = report.get("pairwise_independent_checks")
    require(
        isinstance(independent_pairs, dict)
        and set(independent_pairs) == {"global", "detail"},
        "Independent visual pair checks are incomplete",
    )
    capture_by_id = {
        item["id"]: item for item in capture_values
    }
    for pair_name in ("global", "detail"):
        pair = independent_pairs[pair_name]
        web_pair = web["pairs"][pair_name]
        require(
            isinstance(pair, dict)
            and pair.get("off_sha256")
            == capture_by_id[f"{pair_name}-off"]["sha256"]
            and pair.get("on_sha256")
            == capture_by_id[f"{pair_name}-on"]["sha256"]
            and pair.get("changed_pixels")
            == web_pair["changed_pixels"]
            and pair.get("max_abs_channel_diff_u8")
            == web_pair["max_abs_diff_u8"]
            and pair.get("mean_abs_channel_diff_u8")
            == web_pair["mean_abs_diff_all_rgb_u8"]
            and pair.get("byte_identical")
            is (
                pair["off_sha256"] == pair["on_sha256"]
            )
            and pair.get("decoded_pixel_identical")
            is (web_pair["changed_pixels"] == 0),
            f"Independent visual {pair_name} pair contradicts Web metrics",
        )

    conclusion = report.get("conclusion")
    decision = report.get("decision")
    require(
        isinstance(conclusion, dict)
        and isinstance(decision, dict)
        and report.get("status") == conclusion.get("decision")
        == decision.get("result")
        and conclusion.get("machine_runtime_passed")
        is web["machine_three_passed"]
        and conclusion.get("visual_review_passed")
        is web["visual_gate_passed"]
        and conclusion.get("ao_visual_signal_present")
        is (not web["ao_difference_too_weak"])
        and decision.get("machine_runtime_result")
        == ("pass" if web["machine_three_passed"] else "fail")
        and decision.get("visual_result")
        == ("pass" if web["visual_gate_passed"] else "fail")
        and decision.get("full_matrix_result") == "not_executed"
        and all_false(
            decision,
            (
                "ao_2k_approved",
                "p50_approved",
                "p60_approved",
                "production_integration_allowed",
                "next_release_stage_allowed",
            ),
        ),
        "Independent visual conclusion/decision contradicts Web evidence",
    )
    verification = report.get("verification")
    require(
        isinstance(verification, dict)
        and verification.get(
            "all_capture_artifacts_match_reported_sha_and_bytes"
        )
        is True
        and verification.get(
            "all_pairwise_byte_and_pixel_checks_match_web_report"
        )
        is True
        and verification.get("source_mutation_performed") is False
        and verification.get("only_new_file_written")
        == rel(INDEPENDENT_VISUAL_REVIEW),
        "Independent visual verification claims are incomplete",
    )
    return {
        "report": report,
        "report_artifact": report_artifact,
    }


def validate_representative_report(
) -> tuple[dict[str, Any], str, dict[str, Any]]:
    """Validate the representative Three.js/visual report and derive status."""

    if not REPRESENTATIVE_REPORT.is_file():
        raise FinalizationBlocked(
            "Representative Web report is not ready: "
            f"{rel(REPRESENTATIVE_REPORT)}"
        )
    report, report_artifact = load_json_snapshot(REPRESENTATIVE_REPORT)
    require(
        report.get("schema_version")
        == "bf3d.r2x.representative_preview.v1",
        "Unexpected R2X representative report schema",
    )
    require(
        report.get("stage_id") == STAGE_ID
        and report.get("requirement_id") == REQUIREMENT_ID,
        "Representative report identity mismatch",
    )
    require(
        report.get("execution_scope")
        == "chromium_1440x900_representative_only"
        and report.get("full_matrix_executed") is False,
        "Representative report over-claims the full browser matrix",
    )
    require(
        report.get("candidate_glb_sha256") == EXPECTED_CANDIDATE_SHA256
        and report.get("candidate_glb_bytes") == EXPECTED_CANDIDATE_BYTES,
        "Representative report is not bound to the final candidate GLB",
    )
    require(
        report.get("protected_files_unchanged") is True,
        "Protected files changed during representative Web validation",
    )
    require(
        all_false(report.get("approval_stop_lines"), STOP_LINES),
        "Representative report over-approved 2K/P50/P60/production",
    )

    boolean_fields = (
        "machine_three_passed",
        "visual_gate_passed",
        "ao_difference_too_weak",
        "false_ring_detected",
        "overall_darkening_detected",
        "unexpected_brightening_detected",
        "runtime_failed",
    )
    for field in boolean_fields:
        require(
            isinstance(report.get(field), bool),
            f"Representative report must explicitly set {field}",
        )
    error_totals = report.get("error_totals")
    require(
        isinstance(error_totals, dict),
        "Representative error_totals is missing",
    )
    error_keys = ("console", "page", "http", "external", "request_failed")
    require(
        set(error_totals) == set(error_keys),
        "Representative error_totals must contain exactly five classes",
    )
    for key in error_keys:
        require(
            isinstance(error_totals.get(key), int)
            and error_totals[key] >= 0,
            f"Representative error total is invalid: {key}",
        )
    runtime_contract = report.get("runtime_contract")
    require(
        isinstance(runtime_contract, dict),
        "Final representative runtime_contract must be an object",
    )
    require(
        isinstance(report.get("hard_failures"), list),
        "Representative hard_failures must be a list",
    )
    require(
        isinstance(report.get("limitations"), list)
        and bool(report.get("limitations")),
        "Representative limitations must explicitly preserve pending scope",
    )
    require(
        isinstance(report.get("pairs"), dict),
        "Representative AO comparison pairs are missing",
    )
    require(
        isinstance(report.get("representative_visual_conclusion"), str)
        and bool(report["representative_visual_conclusion"].strip()),
        "Representative visual conclusion is not explicit",
    )
    require(
        report.get("protected_files_before")
        == report.get("protected_files_after"),
        "Representative protected-file snapshots differ",
    )

    capture_artifacts = validate_capture_records(
        report.get("captures"),
        error_keys,
    )
    pairs = report["pairs"]
    require(
        set(pairs) == {"global", "detail"},
        "Final representative report requires exactly global/detail pairs",
    )
    global_pair = validate_pair_metrics("global", pairs["global"])
    detail_pair = validate_pair_metrics("detail", pairs["detail"])
    require(
        runtime_contract.get("passed") is report["machine_three_passed"],
        "runtime_contract.passed contradicts machine_three_passed",
    )
    state_machine_checks = runtime_contract.get("state_machine_checks")
    require(
        isinstance(state_machine_checks, dict)
        and bool(state_machine_checks)
        and all(
            isinstance(value, bool)
            for value in state_machine_checks.values()
        )
        and all(state_machine_checks.values())
        is report["machine_three_passed"],
        "Runtime state-machine checks contradict machine_three_passed",
    )
    runtime_states = runtime_contract.get("states")
    require(
        isinstance(runtime_states, dict)
        and set(runtime_states)
        == {"global-off", "global-on", "detail-off", "detail-on"},
        "Runtime contract states do not cover the four captures",
    )
    for state_id, (view, ao_enabled) in {
        "global-off": ("global", False),
        "global-on": ("global", True),
        "detail-off": ("detail", False),
        "detail-on": ("detail", True),
    }.items():
        state = runtime_states[state_id]
        require(
            isinstance(state, dict)
            and state.get("requirementId") == REQUIREMENT_ID
            and state.get("loadState") == "ready"
            and state.get("view") == view
            and state.get("aoEnabled") is ao_enabled
            and state.get("smokeResolution") == "1K"
            and state.get("p50Approved") is False
            and state.get("productionApproved") is False,
            f"Runtime state contract mismatch: {state_id}",
        )
    for key in ("global_off_on", "detail_off_on"):
        pair_runtime = runtime_contract.get(key)
        require(
            isinstance(pair_runtime, dict)
            and isinstance(pair_runtime.get("passed"), bool),
            f"Runtime intensity-only contract is missing: {key}",
        )
    require(
        (
            runtime_contract["global_off_on"]["passed"]
            and runtime_contract["detail_off_on"]["passed"]
        )
        is report["machine_three_passed"],
        "Runtime off/on pair checks contradict machine_three_passed",
    )

    overall_status = report.get("overall_status")
    require(
        overall_status in {WEB_STATUS_PASS, WEB_STATUS_FAIL},
        "Representative overall_status is not a supported final Web status",
    )
    no_errors = all(error_totals[key] == 0 for key in error_keys)
    require(
        report["runtime_failed"]
        is (not report["machine_three_passed"] or not no_errors),
        "runtime_failed contradicts Three.js machine/error evidence",
    )
    pair_flags = {
        "ao_difference_too_weak": (
            global_pair["ao_difference_too_weak"]
            or detail_pair["ao_difference_too_weak"]
        ),
        "false_ring_detected": (
            global_pair["false_ring_detected"]
            or detail_pair["false_ring_detected"]
        ),
        "overall_darkening_detected": (
            global_pair["overall_darkening_detected"]
            or detail_pair["overall_darkening_detected"]
        ),
        "unexpected_brightening_detected": (
            global_pair["unexpected_brightening_detected"]
            or detail_pair["unexpected_brightening_detected"]
        ),
    }
    for field, expected_value in pair_flags.items():
        require(
            report[field] is expected_value,
            f"Top-level {field} contradicts global/detail pairs",
        )
    require(
        report["visual_gate_passed"]
        is (global_pair["passed"] and detail_pair["passed"]),
        "visual_gate_passed contradicts global/detail pair gates",
    )
    visual_failure_flags = {
        "ao_difference_too_weak": report["ao_difference_too_weak"],
        "false_ring_detected": report["false_ring_detected"],
        "overall_darkening_detected": report[
            "overall_darkening_detected"
        ],
        "unexpected_brightening_detected": report[
            "unexpected_brightening_detected"
        ],
        "runtime_failed": report["runtime_failed"],
    }
    derived_pass = (
        report["machine_three_passed"]
        and report["visual_gate_passed"]
        and not any(visual_failure_flags.values())
        and no_errors
        and report["hard_failures"] == []
    )
    web_evidence = {
        "report_artifact": report_artifact,
        "capture_artifacts": capture_artifacts,
    }
    web_evidence["independent_visual_review"] = (
        validate_independent_visual_review(report, web_evidence)
    )
    if overall_status == WEB_STATUS_PASS:
        require(
            derived_pass,
            "Representative pass contradicts machine/visual/error evidence",
        )
        require(
            global_pair["changed_pixels"] > 0
            and detail_pair["changed_pixels"] > 0
            and global_pair["changed_ratio"] > 0.0
            and detail_pair["changed_ratio"] > 0.0,
            "Representative pass has no measurable AO off/on difference",
        )
        return (
            report,
            STATUS_REPRESENTATIVE_PASS,
            web_evidence,
        )

    require(
        not derived_pass,
        "Representative fail_closed contradicts fully passing evidence",
    )
    failure_is_explicit = (
        not report["machine_three_passed"]
        or not report["visual_gate_passed"]
        or any(visual_failure_flags.values())
        or not no_errors
        or bool(report["hard_failures"])
    )
    require(
        failure_is_explicit,
        "Representative fail_closed has no explicit failure reason",
    )
    return (
        report,
        STATUS_REPRESENTATIVE_FAIL,
        web_evidence,
    )


def validate_all_machine_evidence() -> dict[str, Any]:
    """Validate every pre-Web locked input and machine report."""

    require(STAGE.is_dir(), f"R2X stage directory is missing: {STAGE}")
    primary = validate_lock_set(PRIMARY_LOCKS)
    machine_locks = validate_lock_set(MACHINE_EVIDENCE_LOCKS)
    require(
        machine_locks["v5payload_candidate_glb"]["bytes"]
        == EXPECTED_CANDIDATE_BYTES,
        "Final candidate GLB byte length drifted",
    )
    build = validate_build_report()
    reopen = validate_reopen_report()
    repack = validate_repack_report()
    khronos = validate_khronos_report()
    independent = validate_independent_audit()
    web_build = validate_web_build_report(primary)
    return {
        "primary_locks": primary,
        "machine_evidence_locks": machine_locks,
        "build": build,
        "reopen": reopen,
        "repack": repack,
        "khronos": khronos,
        "independent": independent,
        "web_build": web_build,
    }


def markdown_value(value: Any) -> str:
    """Render a compact Markdown-safe evidence value."""

    if isinstance(value, bool):
        return "`true`" if value else "`false`"
    if value is None:
        return "`null`"
    if isinstance(value, (dict, list)):
        return "`" + json.dumps(value, ensure_ascii=False) + "`"
    return f"`{value}`"


def render_pair_rows(report: dict[str, Any]) -> str:
    """Render available representative AO off/on metric rows."""

    rows: list[str] = []
    pairs = report.get("pairs") or {}
    for key, label in (("global", "全景"), ("detail", "炉腰近景")):
        value = pairs.get(key)
        if not isinstance(value, dict):
            rows.append(f"| {label} | 未形成 | — | — | — |")
            continue
        rows.append(
            "| {label} | {changed_pixels} | {changed_ratio} | "
            "{mean_abs_diff} | {luma_drop_fraction} |".format(
                label=label,
                changed_pixels=value.get("changed_pixels", "—"),
                changed_ratio=value.get("changed_ratio", "—"),
                mean_abs_diff=value.get(
                    "mean_abs_diff_all_rgb_u8", "—"
                ),
                luma_drop_fraction=value.get(
                    "foreground_mean_luma_drop_fraction", "—"
                ),
            )
        )
    return "\n".join(rows)


def render_lock_rows(locks: dict[str, dict[str, Any]]) -> str:
    """Render immutable input rows for stage Markdown."""

    rows = []
    for name, record in locks.items():
        rows.append(
            f"| `{name}` | `{record['path']}` | "
            f"`{record['sha256']}` | 保持锁定 |"
        )
    return "\n".join(rows)


def render_failure_history(
    attempts: list[dict[str, Any]],
) -> str:
    """Render immutable failed-attempt history."""

    rows = []
    for item in attempts:
        rows.append(
            "| {attempt} | `{sha}` | `{result}` | `{code}` | {finding} |".format(
                attempt=item.get("attempt"),
                sha=item.get("candidate_glb_sha256"),
                result=item.get("result"),
                code=item.get("finding_code"),
                finding=item.get("finding"),
            )
        )
    return "\n".join(rows)


def render_hard_failures(value: list[Any]) -> str:
    """Render concise failures without copying local stacks into Markdown."""

    if not value:
        return "- 无"
    rows: list[str] = []
    for item in value:
        if isinstance(item, dict):
            phase = item.get("phase") or "unknown_phase"
            name = item.get("name") or item.get("type") or "Error"
            message = item.get("message") or "未提供错误消息"
            rows.append(f"- `{phase}` / `{name}`：{message}")
        else:
            rows.append(f"- {item}")
    return "\n".join(rows)


def build_summary_markdown(
    evidence: dict[str, Any],
    web: dict[str, Any],
    status: str,
) -> str:
    """Build the stage results summary from validated evidence only."""

    passed = status == STATUS_REPRESENTATIVE_PASS
    decision_text = (
        "代表 Chromium 1440×900 的 Three.js 消费和视觉门通过；完整跨引擎/"
        "跨视口矩阵尚未执行，因此只保留 1K 代表候选结论。"
        if passed
        else "Blender/repack/独立机器证据通过，但代表 Three.js 或视觉门失败关闭；"
        "不得进入完整矩阵或 2K。"
    )
    limitations = "\n".join(
        f"- {item}" for item in web.get("limitations") or []
    )
    hard_failures = render_hard_failures(web.get("hard_failures") or [])
    attempts = evidence["independent"]["attempt_history"]
    return f"""# WEB-60 R2X 当前 R2J 独立 AO 1K 冒烟阶段成果总结

## 1. 阶段结论

阶段 ID：`{STAGE_ID}`。  
需求 ID：`{REQUIREMENT_ID}`。

本阶段状态为：

`{status}`

{decision_text}

本结论不批准 2K、P50、P60、生产集成、正式 GLB 替换或下一发布阶段。
`full_matrix_executed=false`，代表视口结果不得表述为跨浏览器/响应式完成。

## 2. 受保护输入

| 输入键 | 路径 | SHA-256 | 结果 |
|---|---|---|---|
{render_lock_rows(evidence["primary_locks"])}

所有 V5、正式 GLB 与当前 ORM 在构建、重打包、独立审计及代表 Web 验证期间保持只读。

## 3. 1K Blender 与 GLB 机器证据

| 证据 | 结论 |
|---|---|
| [Blender 构建报告](reports/r2x_ao_smoke1k_build_report.json) | 1K 烘焙、五壳 UV2、事务恢复和初始 GLB 机器门通过；Three/视觉当时明确待审 |
| [Blender reopen 报告](reports/r2x_ao_smoke1k_reopen_report.json) | 候选 reopen 后 UV、几何、材质与 AO 图片合同保持 |
| [V5 payload 重打包报告](reports/r2x_ao_v5_payload_repack_report.json) | 只追加五壳 TEXCOORD_2 与单一 AO PNG/texture；V5 sampler 0 复用，V5 WebP/PBR/节点/其它属性保持 |
| [Khronos 原始报告](reports/khronos_gltf_validator_r2x_ao_v5payload.json) | `2.0.0-dev.3.10`，`0 errors / 0 warnings` |
| [独立只读审计](reports/r2x_ao_smoke1k_v5payload_audit.json) | `audit_passed=true`，最终候选绑定 SHA `{EXPECTED_CANDIDATE_SHA256}` |
| [隔离 Web 构建报告](reports/r2x_web_candidate_build_report.json) | 仅生成 R2X 代表页、渲染器、隔离服务与四截图验证器；生产页面保持只读 |
| [独立视觉复核](reports/r2x_independent_visual_review.json) | 只读复核确认机器运行链通过，但 AO 开/关两对截图字节与像素均相同，视觉信号缺失 |

最终 V5-payload 候选为
[gl02_blast_furnace_material_review.r2x-ao-smoke1k.v5payload.glb](glb/gl02_blast_furnace_material_review.r2x-ao-smoke1k.v5payload.glb)，
大小 `{EXPECTED_CANDIDATE_BYTES}` bytes，SHA-256
`{EXPECTED_CANDIDATE_SHA256}`。

## 4. 首次失败尝试保留

| 尝试 | 候选 SHA-256 | 结果 | finding code | 说明 |
|---:|---|---|---|---|
{render_failure_history(attempts)}

首次候选因越权追加第二个 clamp sampler 被失败关闭。最终候选没有删除这段历史，
并改为复用锁定 V5 sampler 0；不得把首次失败从阶段证据中抹除。

## 5. 代表 Three.js 与视觉门

[代表报告](reports/bf3d_review_r2x_representative_report.json)仅覆盖
`{web["execution_scope"]}`：

| 项目 | 结果 |
|---|---|
| Three.js 机器门 | {markdown_value(web["machine_three_passed"])} |
| 代表视觉门 | {markdown_value(web["visual_gate_passed"])} |
| AO 差异过弱 | {markdown_value(web["ao_difference_too_weak"])} |
| 虚假粗黑圆环 | {markdown_value(web["false_ring_detected"])} |
| 整体压暗 | {markdown_value(web["overall_darkening_detected"])} |
| 异常增亮 | {markdown_value(web["unexpected_brightening_detected"])} |
| 运行失败 | {markdown_value(web["runtime_failed"])} |
| 完整矩阵已执行 | {markdown_value(web["full_matrix_executed"])} |

| 对照 | changed pixels | changed ratio | mean abs diff (all RGB u8) | foreground luma drop fraction |
|---|---:|---:|---:|---:|
{render_pair_rows(web)}

代表运行硬失败：

{hard_failures}

限制：

{limitations}

## 6. 批准边界

| 门禁 | R2X 判定 |
|---|---|
| Blender/UV2/AO PNG 机器证据 | `PASS` |
| V5 payload 外科式保持与 Khronos 0/0 | `PASS` |
| 独立只读机器审计 | `PASS` |
| 代表 Three.js/视觉 | `{"PASS_REPRESENTATIVE_ONLY" if passed else "FAIL_CLOSED"}` |
| 完整 17 组跨引擎/视口矩阵 | `NOT_EXECUTED` |
| 2K / P50 / P60 | `NOT_APPROVED` |
| 正式 GLB / 生产集成 | `NOT_APPROVED` |

停止线固定为：

- `approval_granted=false`
- `ao_2k_approved=false`
- `p50_approved=false`
- `p60_approved=false`
- `production_integration_allowed=false`
- `next_release_stage_allowed=false`

## 7. 复验入口

```powershell
python tools\\finalize_bf3d_r2x_stage.py --preflight
python tools\\repack_bf3d_r2x_ao_v5_payload.py
python tools\\audit_bf3d_r2x_ao_candidate.py
```

以上命令复验机器证据或封存前提；不得据此推导完整 Web 矩阵、2K、P50、P60 或生产
批准。
"""


def build_root_decision_markdown(
    evidence: dict[str, Any],
    web: dict[str, Any],
    status: str,
) -> str:
    """Build the stage-local root-review decision from validated evidence."""

    passed = status == STATUS_REPRESENTATIVE_PASS
    root_decision = (
        "pass_representative_only_full_matrix_pending"
        if passed
        else "fail_closed_representative_three_visual"
    )
    decision = (
        "批准范围仅为 1K AO 候选在单一代表 Chromium 1440×900 下的 Three.js "
        "消费与视觉证据；完整矩阵仍是强制停止线。"
        if passed
        else "不批准代表 Three.js/视觉候选；机器资产证据虽通过，当前 1K 参数或"
        "运行链必须在同阶段重新标定/修复后复验。"
    )
    attempts = evidence["independent"]["attempt_history"]
    return f"""# WEB-60 R2X 根审查结论

审查日期：`{now_iso()}`  
阶段：`{STAGE_ID}`  
根判定：`{root_decision}`

## 1. 最终判定

阶段状态固定为：

`{status}`

{decision}

本判定不批准 2K、P50、P60、生产集成、正式 GLB 替换或下一发布阶段。

## 2. 证据门

| 证据 | 根审查结论 |
|---|---|
| [1K 构建报告](reports/r2x_ao_smoke1k_build_report.json) | Blender 机器门通过，范围固定为五个完整 R2J 炉壳 |
| [V5 payload 重打包](reports/r2x_ao_v5_payload_repack_report.json) | 最终 GLB SHA `{EXPECTED_CANDIDATE_SHA256}`；sampler `1→1`，V5 payload 保持 |
| [独立机器审计](reports/r2x_ao_smoke1k_v5payload_audit.json) | `audit_passed=true`；首次越权 sampler 失败历史保留 |
| [隔离 Web 构建报告](reports/r2x_web_candidate_build_report.json) | `passed=true`；仅允许 R2X 代表页/脚本，生产页面与正式资产未改 |
| [代表 Three/视觉报告](reports/bf3d_review_r2x_representative_report.json) | `overall_status={web["overall_status"]}`，仅 `chromium_1440x900_representative_only` |
| [独立视觉复核](reports/r2x_independent_visual_review.json) | `status=fail_closed_ao_visual_signal_absent`；确认无可见 AO 信号且不批准升级 |

## 3. 首次失败与最终修正

| 尝试 | 候选 SHA-256 | 结果 | finding code | 说明 |
|---:|---|---|---|---|
{render_failure_history(attempts)}

第一次重打包越权新增 AO clamp sampler，已失败关闭。最终候选复用 V5 sampler 0，
sampler 数量与完整数组保持不变。该修正不扩展授权范围。

## 4. Three.js 与视觉根判定

- `machine_three_passed={str(web["machine_three_passed"]).lower()}`
- `visual_gate_passed={str(web["visual_gate_passed"]).lower()}`
- `ao_difference_too_weak={str(web["ao_difference_too_weak"]).lower()}`
- `false_ring_detected={str(web["false_ring_detected"]).lower()}`
- `overall_darkening_detected={str(web["overall_darkening_detected"]).lower()}`
- `unexpected_brightening_detected={str(web["unexpected_brightening_detected"]).lower()}`
- `runtime_failed={str(web["runtime_failed"]).lower()}`
- `full_matrix_executed=false`

若 AO 差异过弱、出现虚假粗黑圆环、整体压暗或运行失败，状态必须保持
`{STATUS_REPRESENTATIVE_FAIL}`。只有代表 Three 与视觉均通过时，才允许记录
`{STATUS_REPRESENTATIVE_PASS}`，且仍不得生成 2K。

## 5. 批准矩阵

| 审查项 | 判定 |
|---|---|
| 五壳 UV2 / 1K AO PNG / GLB 绑定 | `PASS_MACHINE` |
| V5 PBR/WebP/节点/其它属性保持 | `PASS_MACHINE` |
| Khronos Validator | `PASS_0_ERRORS_0_WARNINGS` |
| 代表 Three.js/视觉 | `{"PASS_REPRESENTATIVE_ONLY" if passed else "FAIL_CLOSED"}` |
| 完整跨引擎/视口矩阵 | `NOT_EXECUTED` |
| 2K | `NOT_APPROVED` |
| P50 / P60 | `NOT_APPROVED` |
| 正式 GLB / 生产 | `NOT_APPROVED` |

## 6. 停止线与下一步

`approval_granted=false`  
`ao_2k_approved=false`  
`p50_approved=false`  
`p60_approved=false`  
`production_integration_allowed=false`  
`next_release_stage_allowed=false`

下一步：

{
    "保持 1K，不生成 2K；先完成合同规定的两轮 17 组跨引擎/视口矩阵，再决定是否具备提出 2K 申请的前提。"
    if passed
    else "保持 1K 和失败关闭；根据代表报告修复运行链或重新标定 AO，重新执行代表 Three/视觉门。"
}
"""


def build_input_lock(
    evidence: dict[str, Any],
    web_evidence: dict[str, Any],
) -> dict[str, Any]:
    """Build the stage-local immutable input lock document."""

    return {
        "schema_version": "bf3d.r2x.input_lock.v1",
        "requirement_id": REQUIREMENT_ID,
        "stage_id": STAGE_ID,
        "generated_at": now_iso(),
        "locked_primary_assets": evidence["primary_locks"],
        "locked_machine_evidence": evidence["machine_evidence_locks"],
        "locked_web_build_evidence": {
            "report": evidence["web_build"]["report_artifact"],
            "outputs": evidence["web_build"]["output_artifacts"],
            "production_guards": evidence["web_build"][
                "production_guard_artifacts"
            ],
        },
        "representative_report": web_evidence["report_artifact"],
        "representative_captures": web_evidence["capture_artifacts"],
        "independent_visual_review": web_evidence[
            "independent_visual_review"
        ]["report_artifact"],
        "final_candidate": evidence["machine_evidence_locks"][
            "v5payload_candidate_glb"
        ],
        "first_failed_attempt": evidence["independent"][
            "attempt_history"
        ][0],
        "mutation_policy": {
            "v5_assets_mutable": False,
            "formal_glb_mutable": False,
            "current_orm_mutable": False,
            "candidate_glb_mutable_during_finalization": False,
            "web_assets_mutable_during_finalization": False,
            "root_pipeline_mutable": False,
            "stage_local_seal_files_only": True,
        },
        "approval_stop_lines": dict(STOP_LINES),
    }


def build_pipeline_status(
    evidence: dict[str, Any],
    web: dict[str, Any],
    status: str,
    web_evidence: dict[str, Any],
) -> dict[str, Any]:
    """Build the stage-local status record."""

    passed = status == STATUS_REPRESENTATIVE_PASS
    return {
        "schema_version": "bf3d.r2x.pipeline_status.v1",
        "requirement_id": REQUIREMENT_ID,
        "stage_id": STAGE_ID,
        "updated_at": now_iso(),
        "status": status,
        "approval": (
            "representative_1k_only_full_matrix_pending_release_not_granted"
            if passed
            else "failed_closed_release_not_granted"
        ),
        "approval_boundary": (
            "At most one Chromium 1440x900 representative Three/visual "
            "result; full cross-engine/viewport matrix, 2K, P50, P60, "
            "production and next release remain blocked."
        ),
        "blender_machine_gates_passed": True,
        "v5_payload_repack_passed": True,
        "independent_machine_audit_passed": True,
        "representative_three_passed": web["machine_three_passed"],
        "representative_visual_passed": web["visual_gate_passed"],
        "representative_overall_status": web["overall_status"],
        "representative_failure_flags": {
            "ao_difference_too_weak": web["ao_difference_too_weak"],
            "false_ring_detected": web["false_ring_detected"],
            "overall_darkening_detected": web[
                "overall_darkening_detected"
            ],
            "unexpected_brightening_detected": web[
                "unexpected_brightening_detected"
            ],
            "runtime_failed": web["runtime_failed"],
        },
        "full_matrix_executed": False,
        "full_matrix_pending": True,
        "smoke1k_upgrade_gate_passed": False,
        "approval_granted": False,
        "ao_2k_approved": False,
        "p50_approved": False,
        "p60_approved": False,
        "production_integration_allowed": False,
        "next_release_stage_allowed": False,
        "final_candidate": evidence["machine_evidence_locks"][
            "v5payload_candidate_glb"
        ],
        "first_failed_attempt": evidence["independent"][
            "attempt_history"
        ][0],
        "attempt_history": evidence["independent"]["attempt_history"],
        "web_build_report": evidence["web_build"]["report_artifact"],
        "web_build_outputs": evidence["web_build"]["output_artifacts"],
        "representative_report": web_evidence["report_artifact"],
        "representative_captures": web_evidence["capture_artifacts"],
        "independent_visual_review": web_evidence[
            "independent_visual_review"
        ]["report_artifact"],
        "reports": {
            "build": rel(BUILD_REPORT),
            "reopen": rel(REOPEN_REPORT),
            "repack": rel(REPACK_REPORT),
            "khronos": rel(KHRONOS_REPORT),
            "independent_audit": rel(INDEPENDENT_AUDIT),
            "web_build": rel(WEB_BUILD_REPORT),
            "representative": rel(REPRESENTATIVE_REPORT),
            "independent_visual_review": rel(
                INDEPENDENT_VISUAL_REVIEW
            ),
        },
        "stage_documents": {
            "summary": rel(SUMMARY_DOC),
            "root_decision": rel(ROOT_DECISION_DOC),
        },
        "next_stop_line": (
            "Run the contract-required two-round 17-case cross-engine/"
            "viewport matrix while retaining 1K and all approval stops."
            if passed
            else "Keep 1K failed closed; repair runtime or recalibrate AO "
            "from the representative failure evidence, then rerun the "
            "representative Three/visual gate."
        ),
    }


def json_bytes(value: Any) -> bytes:
    """Encode deterministic human-readable JSON."""

    return (
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=False)
        + "\n"
    ).encode("utf-8")


def text_bytes(value: str) -> bytes:
    """Encode normalized UTF-8 Markdown."""

    return (value.rstrip() + "\n").encode("utf-8")


def artifact_from_payload(path: Path, payload: bytes) -> dict[str, Any]:
    """Describe not-yet-written output bytes using their final path."""

    return {
        "path": rel(path),
        "bytes": len(payload),
        "sha256": sha256_bytes(payload),
    }


def build_artifact_manifest(
    generated_payloads: dict[Path, bytes],
) -> dict[str, Any]:
    """Inventory stage artifacts and implementation files, excluding itself."""

    excluded = {ARTIFACT_MANIFEST.resolve()}
    stage_records: dict[str, dict[str, Any]] = {}
    for path in STAGE.rglob("*"):
        if not path.is_file() or path.resolve() in excluded:
            continue
        if path in generated_payloads:
            record = artifact_from_payload(path, generated_payloads[path])
        else:
            record = artifact(path)
        stage_records[record["path"]] = record
    for path, payload in generated_payloads.items():
        if path.resolve() == ARTIFACT_MANIFEST.resolve():
            continue
        record = artifact_from_payload(path, payload)
        stage_records[record["path"]] = record

    implementation = [
        artifact(path) for path in IMPLEMENTATION_PATHS
    ]
    web_runtime = [artifact(path) for path in WEB_RUNTIME_PATHS]
    stage_artifacts = [
        stage_records[key] for key in sorted(stage_records)
    ]
    return {
        "schema_version": "bf3d.r2x.artifact_manifest.v1",
        "requirement_id": REQUIREMENT_ID,
        "stage_id": STAGE_ID,
        "generated_at": now_iso(),
        "manifest_self_excluded": True,
        "stage_artifact_count": len(stage_artifacts),
        "implementation_artifact_count": len(implementation),
        "web_runtime_artifact_count": len(web_runtime),
        "artifact_count": (
            len(stage_artifacts) + len(implementation) + len(web_runtime)
        ),
        "stage_artifacts": stage_artifacts,
        "implementation_artifacts": implementation,
        "web_runtime_artifacts": web_runtime,
        "approval_stop_lines": dict(STOP_LINES),
    }


def verify_written_outputs(
    expected_payloads: dict[Path, bytes],
) -> dict[str, dict[str, Any]]:
    """Reopen final seal files and verify exact written bytes."""

    records: dict[str, dict[str, Any]] = {}
    for path, payload in expected_payloads.items():
        require(path.is_file(), f"Final seal output is missing: {path}")
        actual = path.read_bytes()
        require(
            actual == payload,
            f"Final seal output differs after write: {path}",
        )
        records[path.name] = artifact(path)
    return records


def write_output_transaction(
    payloads: dict[Path, bytes],
    post_write_validator: Any,
) -> dict[str, dict[str, Any]]:
    """Write only the five authorized paths and roll back on any exception."""

    require(
        set(payloads) == set(AUTHORIZED_SEAL_OUTPUTS),
        "Stage seal payload paths differ from the five-file whitelist",
    )
    backups = {
        path: path.read_bytes() if path.is_file() else None
        for path in payloads
    }
    try:
        for path, payload in payloads.items():
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(payload)
        records = verify_written_outputs(payloads)
        post_write_validator()
        return records
    except BaseException as original:
        rollback_errors: list[str] = []
        for path, previous in backups.items():
            try:
                if previous is None:
                    try:
                        path.unlink()
                    except FileNotFoundError:
                        pass
                else:
                    path.write_bytes(previous)
                if previous is None and path.exists():
                    raise FinalizationError(
                        "Rollback did not remove new output"
                    )
                if previous is not None and path.read_bytes() != previous:
                    raise FinalizationError(
                        "Rollback did not restore original bytes"
                    )
            except Exception as rollback_error:
                rollback_errors.append(
                    f"{path}: {type(rollback_error).__name__}: "
                    f"{rollback_error}"
                )
        if rollback_errors:
            raise FinalizationError(
                "Stage seal write failed and rollback was incomplete: "
                f"original={type(original).__name__}: {original}; "
                f"rollback={rollback_errors}"
            ) from original
        raise


def finalize_stage(
    evidence: dict[str, Any],
    web: dict[str, Any],
    status: str,
    web_evidence: dict[str, Any],
) -> dict[str, Any]:
    """Generate exactly the five authorized stage-local seal files."""

    summary_payload = text_bytes(
        build_summary_markdown(evidence, web, status)
    )
    root_decision_payload = text_bytes(
        build_root_decision_markdown(evidence, web, status)
    )
    input_lock_payload = json_bytes(
        build_input_lock(evidence, web_evidence)
    )
    pipeline_payload = json_bytes(
        build_pipeline_status(evidence, web, status, web_evidence)
    )
    payloads: dict[Path, bytes] = {
        SUMMARY_DOC: summary_payload,
        ROOT_DECISION_DOC: root_decision_payload,
        INPUT_LOCK: input_lock_payload,
        PIPELINE_STATUS: pipeline_payload,
    }
    manifest = build_artifact_manifest(payloads)
    manifest_payload = json_bytes(manifest)
    payloads[ARTIFACT_MANIFEST] = manifest_payload

    def validate_after_write() -> None:
        """Verify that sealing did not mutate any input or evidence."""

        primary_after = validate_lock_set(PRIMARY_LOCKS)
        machine_after = validate_lock_set(MACHINE_EVIDENCE_LOCKS)
        require(
            primary_after == evidence["primary_locks"]
            and machine_after == evidence["machine_evidence_locks"],
            "A locked input changed while writing the stage seal",
        )
        require(
            artifact(REPRESENTATIVE_REPORT)
            == web_evidence["report_artifact"],
            "Representative report changed while writing the stage seal",
        )
        require(
            artifact(INDEPENDENT_VISUAL_REVIEW)
            == web_evidence["independent_visual_review"][
                "report_artifact"
            ],
            "Independent visual review changed while sealing the stage",
        )
        capture_after = [
            artifact(ROOT / record["path"])
            for record in web_evidence["capture_artifacts"]
        ]
        require(
            capture_after == web_evidence["capture_artifacts"],
            "Representative screenshot changed while writing the stage seal",
        )
        require(
            artifact(WEB_BUILD_REPORT)
            == evidence["web_build"]["report_artifact"],
            "Web build report changed while writing the stage seal",
        )
        web_outputs_after = [
            artifact(ROOT / record["path"])
            for record in evidence["web_build"]["output_artifacts"]
        ]
        require(
            web_outputs_after == evidence["web_build"]["output_artifacts"],
            "Web build output changed while writing the stage seal",
        )
        production_after = [
            artifact(ROOT / record["path"])
            for record in evidence["web_build"][
                "production_guard_artifacts"
            ]
        ]
        require(
            production_after
            == evidence["web_build"]["production_guard_artifacts"],
            "A protected production file changed while sealing the stage",
        )

    written = write_output_transaction(payloads, validate_after_write)
    return {
        "stage_id": STAGE_ID,
        "requirement_id": REQUIREMENT_ID,
        "status": status,
        "finalized": True,
        "representative_report": web_evidence["report_artifact"],
        "representative_captures": web_evidence["capture_artifacts"],
        "independent_visual_review": web_evidence[
            "independent_visual_review"
        ]["report_artifact"],
        "written_outputs": written,
        "full_matrix_executed": False,
        "smoke1k_upgrade_gate_passed": False,
        **STOP_LINES,
    }


def preflight() -> dict[str, Any]:
    """Validate machine evidence and optionally the representative report."""

    validate_all_machine_evidence()
    if not REPRESENTATIVE_REPORT.is_file():
        return {
            "stage_id": STAGE_ID,
            "requirement_id": REQUIREMENT_ID,
            "status": "waiting_for_representative_web_report",
            "machine_evidence_passed": True,
            "representative_report": {
                "path": rel(REPRESENTATIVE_REPORT),
                "exists": False,
            },
            "seal_outputs_written": False,
            **STOP_LINES,
        }
    web, status, web_evidence = validate_representative_report()
    return {
        "stage_id": STAGE_ID,
        "requirement_id": REQUIREMENT_ID,
        "status": status,
        "machine_evidence_passed": True,
        "representative_report": web_evidence["report_artifact"],
        "representative_captures": web_evidence["capture_artifacts"],
        "independent_visual_review": web_evidence[
            "independent_visual_review"
        ]["report_artifact"],
        "representative_overall_status": web["overall_status"],
        "seal_outputs_written": False,
        **STOP_LINES,
    }


def parse_args(argv: list[str]) -> argparse.Namespace:
    """Parse the stage-finalizer command line."""

    parser = argparse.ArgumentParser(
        description=(
            "Validate and seal the WEB-60 R2X 1K AO stage locally. "
            "The command never changes Web, GLB, Blend, texture, or root docs."
        ),
        epilog=(
            "Examples: "
            "python tools/finalize_bf3d_r2x_stage.py --preflight; "
            "python tools/finalize_bf3d_r2x_stage.py; "
            "python tools/finalize_bf3d_r2x_stage.py --print-json"
        ),
    )
    parser.add_argument(
        "--preflight",
        action="store_true",
        help=(
            "Validate available evidence without writing seal outputs; "
            "missing representative Web evidence is reported as waiting."
        ),
    )
    parser.add_argument(
        "--print-json",
        action="store_true",
        help="Pretty-print the complete finalization result.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    """Run preflight or finalization with explicit fail-closed exit codes."""

    args = parse_args(sys.argv[1:] if argv is None else argv)
    try:
        if args.preflight:
            result = preflight()
        else:
            evidence = validate_all_machine_evidence()
            web, status, web_evidence = validate_representative_report()
            result = finalize_stage(
                evidence,
                web,
                status,
                web_evidence,
            )
    except FinalizationBlocked as exc:
        print(
            json.dumps(
                {
                    "status": "blocked_waiting_for_representative_report",
                    "error": str(exc),
                    "seal_outputs_written": False,
                    **STOP_LINES,
                },
                ensure_ascii=False,
            ),
            file=sys.stderr,
        )
        return 2
    except Exception as exc:
        print(
            json.dumps(
                {
                    "status": "failed_closed",
                    "error_type": type(exc).__name__,
                    "error": str(exc),
                    "traceback": traceback.format_exc(),
                    "seal_outputs_written": False,
                    **STOP_LINES,
                },
                ensure_ascii=False,
            ),
            file=sys.stderr,
        )
        return 1

    print(
        json.dumps(
            result,
            ensure_ascii=False,
            indent=2 if args.print_json else None,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
