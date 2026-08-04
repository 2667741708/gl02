#!/usr/bin/env python3
"""Lock and package the R2W camera-only material-readability candidate.

This entry point does not rewrite V5, the GLB, the shared stylesheet, or any
production file.  It validates the authored R2W isolated-page sources against
their locked V5 parent and emits one deterministic build/audit report.

Requirement:
    REQ-BF3D-R2W-MATERIAL-READABILITY-CAMERA-20260720

Exit codes:
    0: candidate and parent locks passed.
    2: a parent hash, protected asset, numeric renderer contract, or R2W
       semantic contract failed.
"""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path


REQUIREMENT_ID = "REQ-BF3D-R2W-MATERIAL-READABILITY-CAMERA-20260720"
ROOT = Path(__file__).resolve().parents[1]
FRONTEND = ROOT / "高炉前端数据"
TOOLS = ROOT / "tools"
STAGE = (
    ROOT
    / "PT"
    / "高炉3D模型"
    / "work"
    / "WEB_60_20260720_R2W_MATERIAL_READABILITY_AO_EDGE"
)
REPORT = STAGE / "reports" / "web_candidate_build_report.json"

V5_HTML = FRONTEND / "bf3d_review_v5.server.html"
V5_RENDERER = FRONTEND / "assets" / "bf3d-review-renderer-v5.js"
V5_SERVER = TOOLS / "serve_bf3d_review_v5.py"
V5_VERIFIER = TOOLS / "verify_bf3d_review_v5_preview.cjs"
R2W_HTML = FRONTEND / "bf3d_review_r2w.server.html"
R2W_RENDERER = FRONTEND / "assets" / "bf3d-review-renderer-r2w.js"
R2W_SERVER = TOOLS / "serve_bf3d_review_r2w.py"
R2W_VERIFIER = TOOLS / "verify_bf3d_review_r2w_preview.cjs"
MODEL = FRONTEND / "models" / "gl02_blast_furnace_review.v5.glb"
FORMAL = FRONTEND / "models" / "gl02_blast_furnace.glb"

V5_LOCKS = {
    V5_HTML: {
        "bytes": 8_603,
        "sha256": "bb0ddf0acf79f7ec81652b047e6295d90322fa15461f08d90473833ff5878565",
    },
    V5_RENDERER: {
        "bytes": 44_445,
        "sha256": "9d01b31482abc7c09146f657ba402457d354890f74f76501ec45dcf7e50b589d",
    },
    V5_SERVER: {
        "bytes": 11_745,
        "sha256": "69adc5ed12b3e41767ce85a34da395aee335b523861116099339faae8efbb855",
    },
    V5_VERIFIER: {
        "bytes": 48_770,
        "sha256": "e73c78753d6a0e86fb31a469bf007980a22e6585b0613e9f886adb2f4a71f9c9",
    },
}
MODEL_LOCK = {
    "bytes": 4_663_220,
    "sha256": "0ac031e626c9eaa0b0cdd8192cf9fda712324af174a4285f563a97309451ed3c",
}
FORMAL_SHA256 = (
    "808960f1b2703e7fb27df35f1b1b1a17063b9b10d2267acba593fc3872b62af6"
)


def sha256_bytes(payload: bytes) -> str:
    """Return a lowercase SHA-256 digest for one in-memory payload."""

    return hashlib.sha256(payload).hexdigest()


def inspect(path: Path) -> dict[str, object]:
    """Return repository-relative path, byte count, and SHA-256."""

    payload = path.read_bytes()
    return {
        "path": path.resolve().relative_to(ROOT.resolve()).as_posix(),
        "bytes": len(payload),
        "sha256": sha256_bytes(payload),
    }


def read_text(path: Path) -> str:
    """Read one required UTF-8 source or fail closed."""

    return path.read_text(encoding="utf-8")


def between(text: str, start: str, end: str) -> str:
    """Extract a deterministic source interval including its start marker."""

    start_index = text.find(start)
    if start_index < 0:
        raise RuntimeError(f"Missing numeric-contract start marker: {start}")
    end_index = text.find(end, start_index)
    if end_index < 0:
        raise RuntimeError(f"Missing numeric-contract end marker: {end}")
    return text[start_index:end_index]


def make_check(check_id: str, passed: bool, detail: object = None) -> dict[str, object]:
    """Create one serializable fail-closed check record."""

    return {
        "id": check_id,
        "passed": bool(passed),
        **({} if detail is None else {"detail": detail}),
    }


def main() -> int:
    """Validate the R2W candidate and emit its traceable build report."""

    try:
        required = [
            *V5_LOCKS,
            R2W_HTML,
            R2W_RENDERER,
            R2W_SERVER,
            R2W_VERIFIER,
            MODEL,
            FORMAL,
        ]
        missing = [
            path.resolve().relative_to(ROOT.resolve()).as_posix()
            for path in required
            if not path.is_file()
        ]
        if missing:
            raise RuntimeError(f"Missing required R2W/V5 files: {missing}")

        v5_artifacts = {path: inspect(path) for path in V5_LOCKS}
        r2w_artifacts = [
            inspect(path)
            for path in [R2W_HTML, R2W_RENDERER, R2W_SERVER, R2W_VERIFIER]
        ]
        model_artifact = inspect(MODEL)
        formal_artifact = inspect(FORMAL)
        v5_lock_checks = [
            make_check(
                f"v5_parent_lock_{path.name}",
                v5_artifacts[path]["bytes"] == expected["bytes"]
                and v5_artifacts[path]["sha256"] == expected["sha256"],
                {
                    "actual": v5_artifacts[path],
                    "expected": expected,
                },
            )
            for path, expected in V5_LOCKS.items()
        ]

        v5_renderer = read_text(V5_RENDERER)
        r2w_renderer = read_text(R2W_RENDERER)
        r2w_html = read_text(R2W_HTML)
        r2w_server = read_text(R2W_SERVER)
        r2w_verifier = read_text(R2W_VERIFIER)

        numeric_intervals = [
            ("P40_LIGHT_CONSTANTS", "const P40_DIRECTIONAL_LIGHTS", "const ROLE_LABELS"),
            (
                "RENDERER_COLOR_PIPELINE",
                "this.renderer = new THREE.WebGLRenderer",
                "this.controls = new OrbitControls",
            ),
            (
                "P40_LIGHT_IMPLEMENTATION",
                "  createP40CandidateLights()",
                "  createFixedLinearEnvironment()",
            ),
            (
                "ENVIRONMENT_IMPLEMENTATION",
                "  createFixedLinearEnvironment()",
                "  resize()",
            ),
        ]
        numeric_checks = [
            make_check(
                f"numeric_contract_{name}",
                between(v5_renderer, start, end)
                == between(r2w_renderer, start, end),
                {"source_start": start, "source_end": end},
            )
            for name, start, end in numeric_intervals
        ]

        checks = [
            *v5_lock_checks,
            make_check(
                "v5_review_glb_lock",
                model_artifact["bytes"] == MODEL_LOCK["bytes"]
                and model_artifact["sha256"] == MODEL_LOCK["sha256"],
                {"actual": model_artifact, "expected": MODEL_LOCK},
            ),
            make_check(
                "formal_glb_lock",
                formal_artifact["sha256"] == FORMAL_SHA256,
                {"actual": formal_artifact, "expected_sha256": FORMAL_SHA256},
            ),
            *numeric_checks,
            make_check(
                "single_v5_model_contract",
                'const MODEL_URL = "models/gl02_blast_furnace_review.v5.glb"'
                in r2w_renderer
                and MODEL_LOCK["sha256"] in r2w_renderer
                and "gl02_blast_furnace.glb" not in r2w_renderer,
            ),
            make_check(
                "four_view_contract",
                all(
                    token in r2w_html
                    for token in [
                        'data-material-view-button="exterior"',
                        'data-material-view-button="exterior-detail"',
                        'data-material-view-button="interior"',
                        'data-mode-button="structural"',
                    ]
                ),
            ),
            make_check(
                "belly_camera_only_contract",
                all(
                    token in r2w_renderer
                    for token in [
                        'exteriorDetailZone: "BELLY"',
                        "projectObjectToCanvas",
                        "fitProjectionFraction",
                        "cameraOnly: true",
                        "materialOrGeometryModified: false",
                        "lightingOrColorPathModified: false",
                    ]
                )
                and "仅新增确定性相机近景" in r2w_html,
            ),
            make_check(
                "projection_threshold_contract",
                all(
                    token in r2w_renderer
                    for token in [
                        "exteriorGlobalHeightMinimum: 0.8",
                        "exteriorGlobalHeightMaximum: 0.93",
                        "exteriorDetailWidthMinimum: 0.6",
                        "exteriorDetailHeightMinimum: 0.25",
                        "exteriorDetailCenterOffsetMaximum: 0.15",
                    ]
                ),
            ),
            make_check(
                "neutral_user_disclosure_contract",
                "AO 未接入 / REF-PENDING" in r2w_html
                and "内部层边界 REF-PENDING，非数据竖线" in r2w_html
                and "聚焦炉腰区" in r2w_renderer
                and "聚焦 bf3d_zone" not in r2w_renderer,
            ),
            make_check(
                "server_isolation_contract",
                "bf3d_review_r2w.server.html" in r2w_server
                and "bf3d-review-renderer-r2w.js" in r2w_server
                and '"production_page_exposed": False' in r2w_server
                and '"production_controller_exposed": False' in r2w_server
                and '"formal_glb_exposed": False' in r2w_server,
            ),
            make_check(
                "representative_four_capture_contract",
                'required_screenshots_per_run: 4' in r2w_verifier
                and "material-exterior-global" in r2w_verifier
                and "material-exterior-detail" in r2w_verifier
                and "material-interior" in r2w_verifier
                and "structural-section" in r2w_verifier,
            ),
        ]
        passed = all(check["passed"] for check in checks)
        report = {
            "schema_version": "bf3d.r2w.web_candidate_build.v1",
            "requirement_id": REQUIREMENT_ID,
            "stage_id": "WEB-60_R2W",
            "source_parent": "locked V5 isolated review",
            "outputs": r2w_artifacts,
            "model": model_artifact,
            "formal_glb": formal_artifact,
            "checks": checks,
            "passed": passed,
            "scope": {
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
        }
        REPORT.parent.mkdir(parents=True, exist_ok=True)
        REPORT.write_text(
            json.dumps(report, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
            newline="\n",
        )
        print(
            "BF3D_R2W_WEB_CANDIDATE="
            + json.dumps(
                {
                    "passed": passed,
                    "outputs": r2w_artifacts,
                    "report": REPORT.resolve()
                    .relative_to(ROOT.resolve())
                    .as_posix(),
                },
                ensure_ascii=False,
            )
        )
        return 0 if passed else 2
    except (OSError, RuntimeError, UnicodeError) as error:
        print(
            json.dumps(
                {
                    "passed": False,
                    "requirement_id": REQUIREMENT_ID,
                    "error": str(error),
                },
                ensure_ascii=False,
            ),
            file=sys.stderr,
        )
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
