#!/usr/bin/env python3
"""Derive the isolated V5 Three.js review surface from locked V4 sources.

The V4 page, renderer, server and Playwright verifier are immutable parent
evidence.  This builder changes only the review version, R2V traceability ID
and SHA/byte contract for the controlled V5 main GLB.

Requirement:
    REQ-BF3D-R2V-ISOLATED-WEB-REVIEW-20260720
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path


REQUIREMENT_ID = "REQ-BF3D-R2V-ISOLATED-WEB-REVIEW-20260720"
ROOT = Path(__file__).resolve().parents[1]
FRONTEND = ROOT / "高炉前端数据"
TOOLS = ROOT / "tools"
STAGE = (
    ROOT
    / "PT"
    / "高炉3D模型"
    / "work"
    / "WEB_60_20260720_R2V_GLTF_PORTABILITY_TANGENT_BUDGET"
)
REPORT_DIR = STAGE / "reports"

SOURCE_HTML = FRONTEND / "bf3d_review_v4.server.html"
SOURCE_RENDERER = FRONTEND / "assets" / "bf3d-review-renderer-v4.js"
SOURCE_SERVER = TOOLS / "serve_bf3d_review_v4.py"
SOURCE_VERIFIER = TOOLS / "verify_bf3d_review_v4_preview.cjs"

OUTPUT_HTML = FRONTEND / "bf3d_review_v5.server.html"
OUTPUT_RENDERER = FRONTEND / "assets" / "bf3d-review-renderer-v5.js"
OUTPUT_SERVER = TOOLS / "serve_bf3d_review_v5.py"
OUTPUT_VERIFIER = TOOLS / "verify_bf3d_review_v5_preview.cjs"
OUTPUT_REPORT = REPORT_DIR / "web_review_build_report.json"

MODEL = FRONTEND / "models" / "gl02_blast_furnace_review.v5.glb"
MODEL_BYTES = 4_663_220
MODEL_SHA256 = "0ac031e626c9eaa0b0cdd8192cf9fda712324af174a4285f563a97309451ed3c"
FORMAL = FRONTEND / "models" / "gl02_blast_furnace.glb"
FORMAL_SHA256 = "808960f1b2703e7fb27df35f1b1b1a17063b9b10d2267acba593fc3872b62af6"

SOURCE_LOCKS = {
    SOURCE_HTML: {
        "bytes": 8_603,
        "sha256": "c5bfd57ccd6d78cbf03d2b1da22c60f26445cce7cf1dac61593490d8ce4999a9",
    },
    SOURCE_RENDERER: {
        "bytes": 44_445,
        "sha256": "ad11d8b67f7d91f15ed83fead7977af393cccbf23c1c224de5590a59175743f6",
    },
    SOURCE_SERVER: {
        "bytes": 11_745,
        "sha256": "279959018e5cf6dff03a6ae3166baa75a0e5f78b6f9b40ab6470add1e10bbcc2",
    },
    SOURCE_VERIFIER: {
        "bytes": 48_764,
        "sha256": "548f598c1134a528b02ab24802eb9b6d044a80918f0d39532466efd5b9322d0c",
    },
}


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def sha256_file(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


def relative(path: Path) -> str:
    return path.resolve().relative_to(ROOT.resolve()).as_posix()


def artifact(path: Path) -> dict[str, object]:
    payload = path.read_bytes()
    return {
        "path": relative(path),
        "bytes": len(payload),
        "sha256": sha256_bytes(payload),
    }


def read_locked(path: Path) -> str:
    expected = SOURCE_LOCKS[path]
    payload = path.read_bytes()
    actual = {"bytes": len(payload), "sha256": sha256_bytes(payload)}
    if actual != expected:
        raise RuntimeError(
            f"Locked V4 web source drift: {relative(path)} "
            f"actual={actual} expected={expected}"
        )
    return payload.decode("utf-8")


def replace_all(
    text: str,
    old: str,
    new: str,
    *,
    label: str,
) -> tuple[str, dict[str, object]]:
    count = text.count(old)
    if count < 1:
        raise RuntimeError(f"Required V5 replacement is absent: {label}")
    return (
        text.replace(old, new),
        {
            "label": label,
            "source": old,
            "replacement": new,
            "count": count,
        },
    )


def transform(
    path: Path,
    replacements: list[tuple[str, str, str]],
) -> tuple[str, list[dict[str, object]]]:
    text = read_locked(path)
    records = []
    for old, new, label in replacements:
        text, record = replace_all(text, old, new, label=label)
        records.append(record)
    return text, records


def build_html() -> tuple[str, list[dict[str, object]]]:
    return transform(
        SOURCE_HTML,
        [
            (
                "bf3d-review-renderer-v4.js",
                "bf3d-review-renderer-v5.js",
                "HTML renderer entry",
            ),
            ("review.v4", "review.v5", "HTML asset contract"),
            ("V4", "V5", "HTML visible version"),
        ],
    )


def build_renderer() -> tuple[str, list[dict[str, object]]]:
    return transform(
        SOURCE_RENDERER,
        [
            (
                "REQ-BF3D-R2U-ISOLATED-WEB-REVIEW-20260720",
                REQUIREMENT_ID,
                "renderer requirement",
            ),
            (
                "gl02_blast_furnace_review.v4.glb",
                "gl02_blast_furnace_review.v5.glb",
                "renderer GLB URL",
            ),
            (
                "e46508bcecc8fef76510a0b889e0598ad3cb2289cc00f6b99566c78e3ed3afd2",
                MODEL_SHA256,
                "renderer GLB SHA",
            ),
            ("4_275_268", "4_663_220", "renderer GLB bytes"),
            ("review.v4", "review.v5", "renderer asset contract"),
            ("BF3D_V4", "BF3D_V5", "renderer root names"),
            ("V4", "V5", "renderer visible version"),
        ],
    )


def build_server() -> tuple[str, list[dict[str, object]]]:
    return transform(
        SOURCE_SERVER,
        [
            (
                "REQ-BF3D-R2U-ISOLATED-WEB-REVIEW-20260720",
                REQUIREMENT_ID,
                "server requirement",
            ),
            (
                "e46508bcecc8fef76510a0b889e0598ad3cb2289cc00f6b99566c78e3ed3afd2",
                MODEL_SHA256,
                "server GLB SHA",
            ),
            ("4_275_268", "4_663_220", "server GLB bytes"),
            ("review.v4", "review.v5", "server asset contract"),
            (
                "bf3d-review-renderer-v4.js",
                "bf3d-review-renderer-v5.js",
                "server renderer route",
            ),
            ("_v4", "_v5", "server document/script suffixes"),
            ("V4", "V5", "server visible version"),
        ],
    )


def build_verifier() -> tuple[str, list[dict[str, object]]]:
    return transform(
        SOURCE_VERIFIER,
        [
            (
                "REQ-BF3D-R2U-ISOLATED-WEB-REVIEW-20260720",
                REQUIREMENT_ID,
                "verifier requirement",
            ),
            (
                "e46508bcecc8fef76510a0b889e0598ad3cb2289cc00f6b99566c78e3ed3afd2",
                MODEL_SHA256,
                "verifier GLB SHA",
            ),
            ("4_275_268", "4_663_220", "verifier GLB bytes"),
            (
                "WEB_60_20260720_R2U_SECTION_CAP_CONTROLLED_V4",
                "WEB_60_20260720_R2V_GLTF_PORTABILITY_TANGENT_BUDGET",
                "verifier stage root",
            ),
            ("WEB-60_R2U", "WEB-60_R2V", "verifier stage id"),
            ("review.v4", "review.v5", "verifier asset contract"),
            (
                "bf3d-review-renderer-v4.js",
                "bf3d-review-renderer-v5.js",
                "verifier renderer path",
            ),
            ("_v4", "_v5", "verifier document/script/report suffixes"),
            ("BF3D_V4", "BF3D_V5", "verifier root names"),
            ("V4", "V5", "verifier visible version"),
        ],
    )


def write_lf(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as stream:
        stream.write(text)


def validate_output_texts(outputs: dict[Path, str]) -> dict[str, bool]:
    combined = "\n".join(outputs.values())
    return {
        "v5_model_url_present": "gl02_blast_furnace_review.v5.glb" in combined,
        "v5_review_contract_present": "review.v5" in combined,
        "v5_root_names_present": "BF3D_V5_MODE_MATERIAL" in combined
        and "BF3D_V5_MODE_SECTION" in combined,
        "v5_requirement_present": REQUIREMENT_ID in combined,
        "v4_model_not_referenced": "gl02_blast_furnace_review.v4.glb"
        not in combined,
        "v4_root_names_not_referenced": "BF3D_V4_MODE_MATERIAL" not in combined
        and "BF3D_V4_MODE_SECTION" not in combined,
        "production_page_remains_excluded": (
            "frontend_dashboard_v3.server.html"
            in outputs[OUTPUT_VERIFIER]
        ),
        "two_review_modes_retained": (
            'data-mode-button="material"' in outputs[OUTPUT_HTML]
            and 'data-mode-button="structural"' in outputs[OUTPUT_HTML]
        ),
    }


def main() -> int:
    if not MODEL.is_file() or MODEL.stat().st_size != MODEL_BYTES:
        raise RuntimeError("V5 main GLB is missing or has an unexpected byte count")
    if sha256_file(MODEL) != MODEL_SHA256:
        raise RuntimeError("V5 main GLB SHA-256 does not match the locked contract")
    if not FORMAL.is_file() or sha256_file(FORMAL) != FORMAL_SHA256:
        raise RuntimeError("Formal GLB drifted before V5 web derivation")

    html, html_records = build_html()
    renderer, renderer_records = build_renderer()
    server, server_records = build_server()
    verifier, verifier_records = build_verifier()
    outputs = {
        OUTPUT_HTML: html,
        OUTPUT_RENDERER: renderer,
        OUTPUT_SERVER: server,
        OUTPUT_VERIFIER: verifier,
    }
    checks = validate_output_texts(outputs)
    if not all(checks.values()):
        raise RuntimeError(
            "V5 web output contract failed: "
            + json.dumps(checks, ensure_ascii=False)
        )
    for path, text in outputs.items():
        write_lf(path, text)

    report = {
        "schema_version": "bf3d.r2v.web_review_build.v5",
        "requirement_id": REQUIREMENT_ID,
        "source_locks": {
            relative(path): expected for path, expected in SOURCE_LOCKS.items()
        },
        "model": artifact(MODEL),
        "formal_glb": artifact(FORMAL),
        "replacement_records": {
            "html": html_records,
            "renderer": renderer_records,
            "server": server_records,
            "verifier": verifier_records,
        },
        "outputs": [artifact(path) for path in outputs],
        "checks": checks,
        "passed": all(checks.values()),
        "approval": {
            "isolated_review_only": True,
            "production_integration_allowed": False,
            "p60_approved": False,
        },
    }
    write_lf(OUTPUT_REPORT, json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    print(
        "BF3D_R2V_V5_WEB_BUILD="
        + json.dumps(
            {
                "passed": report["passed"],
                "model": report["model"],
                "outputs": report["outputs"],
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
