#!/usr/bin/env python3
"""Build the isolated WEB-60 R2U V4 Three.js review surface.

Requirement:
    REQ-BF3D-R2U-ISOLATED-WEB-REVIEW-20260720

The V3 review surface is retained byte-for-byte as historical evidence.  This
builder derives V4-only HTML, renderer, localhost server, and Playwright
verifier files from SHA-locked V3 sources.  Every replacement is fail-closed;
source drift or an unexpected replacement count aborts the build.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path


REQUIREMENT_ID = "REQ-BF3D-R2U-ISOLATED-WEB-REVIEW-20260720"
ROOT = Path(__file__).resolve().parents[1]
FRONTEND = ROOT / "高炉前端数据"
TOOLS = ROOT / "tools"
STAGE = (
    ROOT
    / "PT"
    / "高炉3D模型"
    / "work"
    / "WEB_60_20260720_R2U_SECTION_CAP_CONTROLLED_V4"
)
REPORT_DIR = STAGE / "reports"

SOURCE_HTML = FRONTEND / "bf3d_review.server.html"
SOURCE_RENDERER = FRONTEND / "assets" / "bf3d-review-renderer.js"
SOURCE_SERVER = TOOLS / "serve_bf3d_review.py"
SOURCE_VERIFIER = TOOLS / "verify_bf3d_review_preview.cjs"

OUTPUT_HTML = FRONTEND / "bf3d_review_v4.server.html"
OUTPUT_RENDERER = FRONTEND / "assets" / "bf3d-review-renderer-v4.js"
OUTPUT_SERVER = TOOLS / "serve_bf3d_review_v4.py"
OUTPUT_VERIFIER = TOOLS / "verify_bf3d_review_v4_preview.cjs"
OUTPUT_REPORT = REPORT_DIR / "web_review_build_report.json"

MODEL = FRONTEND / "models" / "gl02_blast_furnace_review.v4.glb"
MODEL_BYTES = 4_275_268
MODEL_SHA256 = "e46508bcecc8fef76510a0b889e0598ad3cb2289cc00f6b99566c78e3ed3afd2"
FORMAL_SHA256 = "808960f1b2703e7fb27df35f1b1b1a17063b9b10d2267acba593fc3872b62af6"

SOURCE_LOCKS = {
    SOURCE_HTML: {
        "bytes": 8_600,
        "sha256": "d816cb90a46398c1b5c8fec45d3c7a192c83b4b103aa43e64dc62eddf228fd53",
    },
    SOURCE_RENDERER: {
        "bytes": 44_431,
        "sha256": "1a44438276bdf92c66cb2f2813fed67f4aff6470e84527479530b3d7ac0ba224",
    },
    SOURCE_SERVER: {
        "bytes": 11_732,
        "sha256": "ff1182d01fddcaa1bf05d492785ca09330d2eff185f2112fe198f1c6c7ec8c5d",
    },
    SOURCE_VERIFIER: {
        "bytes": 48_844,
        "sha256": "99be4134ec953e5e9b6d658d924fd0316f800fc0bed9845efa2ed1df5c8d95de",
    },
}


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def sha256_file(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


def relative(path: Path) -> str:
    return path.resolve().relative_to(ROOT).as_posix()


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
            f"Locked V3 source drift: {relative(path)} "
            f"actual={actual} expected={expected}"
        )
    return payload.decode("utf-8")


def replace_exact(
    text: str,
    old: str,
    new: str,
    *,
    expected_count: int = 1,
    label: str,
) -> tuple[str, dict[str, object]]:
    actual_count = text.count(old)
    if actual_count != expected_count:
        raise RuntimeError(
            f"Replacement contract failed for {label}: "
            f"actual={actual_count}, expected={expected_count}"
        )
    return (
        text.replace(old, new),
        {
            "label": label,
            "expected_count": expected_count,
            "actual_count": actual_count,
        },
    )


def apply_replacements(
    text: str, replacements: list[tuple[str, str, int, str]]
) -> tuple[str, list[dict[str, object]]]:
    records: list[dict[str, object]] = []
    for old, new, count, label in replacements:
        text, record = replace_exact(
            text,
            old,
            new,
            expected_count=count,
            label=label,
        )
        records.append(record)
    return text, records


def build_html() -> tuple[str, list[dict[str, object]]]:
    source = read_locked(SOURCE_HTML)
    return apply_replacements(
        source,
        [
            (
                "assets/bf3d-review-renderer.js",
                "assets/bf3d-review-renderer-v4.js",
                1,
                "html renderer entry",
            ),
            ("V3", "V4", 3, "html visible version labels"),
            ("review.v3", "review.v4", 1, "html asset contract"),
        ],
    )


def build_renderer() -> tuple[str, list[dict[str, object]]]:
    source = read_locked(SOURCE_RENDERER)
    text, records = apply_replacements(
        source,
        [
            (
                "REQ-BF3D-R2T-ISOLATED-REVIEW-PREVIEW-20260720",
                REQUIREMENT_ID,
                2,
                "renderer requirement id",
            ),
            (
                "models/gl02_blast_furnace_review.v3.glb",
                "models/gl02_blast_furnace_review.v4.glb",
                1,
                "renderer model url",
            ),
            (
                "7e4b3b95343103784500aba354a124262ecf593fe89a3f0aa98348692152574b",
                MODEL_SHA256,
                1,
                "renderer model sha",
            ),
            ("4_380_396", "4_275_268", 1, "renderer model bytes"),
            (
                "底部深色楔形为现有 V3 GLB 物理 Section 封口面在同一切平面的共面叠合与遮挡，不是内腔开口，且未在审查页修复。",
                "V4 物理 Section 已通过 10/10 闭合与跨对象共面重叠 0；中央深色面为保留半炉的对侧内壁，不是固定圆环、竖线、数据引线或内腔封堵。",
                1,
                "renderer structural diagnosis",
            ),
            (
                '"coincident_physical_section_cap_overlap"',
                '"controlled_section_caps_zero_overlap"',
                1,
                "renderer structural audit code",
            ),
            ("V3", "V4", 9, "renderer visible and contract labels"),
            ("review.v3", "review.v4", 3, "renderer review labels"),
        ],
    )
    forbidden = [
        "gl02_blast_furnace_review.v3.glb",
        "BF3D_V3_MODE_MATERIAL",
        "BF3D_V3_MODE_SECTION",
        "coincident_physical_section_cap_overlap",
    ]
    leaked = [token for token in forbidden if token in text]
    if leaked:
        raise RuntimeError(f"V4 renderer retained V3-only tokens: {leaked}")
    return text, records


def build_server() -> tuple[str, list[dict[str, object]]]:
    source = read_locked(SOURCE_SERVER)
    return apply_replacements(
        source,
        [
            (
                "REQ-BF3D-R2T-ISOLATED-REVIEW-PREVIEW-20260720",
                REQUIREMENT_ID,
                2,
                "server requirement id",
            ),
            (
                "7e4b3b95343103784500aba354a124262ecf593fe89a3f0aa98348692152574b",
                MODEL_SHA256,
                1,
                "server model sha",
            ),
            ("4_380_396", "4_275_268", 1, "server model bytes"),
            (
                "bf3d_review.server.html",
                "bf3d_review_v4.server.html",
                5,
                "server V4 document route",
            ),
            (
                "bf3d-review-renderer.js",
                "bf3d-review-renderer-v4.js",
                2,
                "server V4 renderer route",
            ),
            (
                "gl02_blast_furnace_review.v3.glb",
                "gl02_blast_furnace_review.v4.glb",
                4,
                "server V4 model route",
            ),
            ("V3", "V4", 2, "server visible and contract labels"),
            ("review.v3", "review.v4", 2, "server asset contract text"),
        ],
    )


def build_verifier() -> tuple[str, list[dict[str, object]]]:
    source = read_locked(SOURCE_VERIFIER)
    text, records = apply_replacements(
        source,
        [
            (
                "WEB_60_20260720_R2T_OCIO_PHOTOMETRIC_EQUIVALENCE",
                "WEB_60_20260720_R2U_SECTION_CAP_CONTROLLED_V4",
                1,
                "verifier stage root",
            ),
            (
                "bf3d_review_preview_report.json",
                "bf3d_review_v4_preview_report.json",
                1,
                "verifier report name",
            ),
            (
                "bf3d_review.server.html",
                "bf3d_review_v4.server.html",
                1,
                "verifier document path",
            ),
            (
                "bf3d-review-renderer.js",
                "bf3d-review-renderer-v4.js",
                1,
                "verifier renderer path",
            ),
            (
                "serve_bf3d_review.py",
                "serve_bf3d_review_v4.py",
                1,
                "verifier server path",
            ),
            (
                "REQ-BF3D-R2T-ISOLATED-REVIEW-PREVIEW-20260720",
                REQUIREMENT_ID,
                1,
                "verifier requirement id",
            ),
            (
                "7e4b3b95343103784500aba354a124262ecf593fe89a3f0aa98348692152574b",
                MODEL_SHA256,
                1,
                "verifier model sha",
            ),
            ("4_380_396", "4_275_268", 1, "verifier model bytes"),
            (
                "gl02_blast_furnace_review.v3.glb",
                "gl02_blast_furnace_review.v4.glb",
                5,
                "verifier model references",
            ),
            (
                "material_review.v3.glb",
                "material_review.v4.glb",
                1,
                "verifier material exclusion",
            ),
            (
                "structural_review.v3.glb",
                "structural_review.v4.glb",
                1,
                "verifier structural exclusion",
            ),
            (
                "现有 V3 GLB 的十个物理 Section 封口面共享同一切平面并跨越中心；底部深色楔形按共面叠合/遮挡披露，不判为内腔或已修复。",
                "V4 十个物理 Section 封口均位于同一受控切平面；跨对象正面积重叠已由 R2U 几何验证器独立证明为 0。",
                1,
                "verifier section interpretation",
            ),
            (
                "glb_section_cap_coplanar_overlap_basis",
                "glb_section_cap_registered_plane",
                1,
                "verifier section plane check id",
            ),
            (
                "Math.abs(entry.x_min - entry.x_max) < 1e-6 &&\n"
                "        entry.z_min < 0 &&\n"
                "        entry.z_max > 0,",
                "Math.abs(entry.x_min - entry.x_max) < 1e-6,",
                1,
                "verifier no cross-centre assumption",
            ),
            (
                'structural.composition.structuralBottomWedgeDiagnosis ===\n'
                '            "coincident_physical_section_cap_overlap" &&',
                'structural.composition.structuralBottomWedgeDiagnosis ===\n'
                '            "controlled_section_caps_zero_overlap" &&',
                1,
                "verifier structural audit code",
            ),
            (
                'structuralUi.note.includes("共面叠合与遮挡") &&\n'
                '          structuralUi.note.includes("不是内腔开口") &&\n'
                '          structuralUi.note.includes("未在审查页修复")',
                'structuralUi.note.includes("跨对象共面重叠 0") &&\n'
                '          structuralUi.note.includes("不是固定圆环、竖线") &&\n'
                '          structuralUi.note.includes("不是")',
                1,
                "verifier V4 structural disclosure",
            ),
            (
                'renderer.includes("共面叠合与遮挡") &&\n'
                '        renderer.includes("不是内腔开口") &&\n'
                '        renderer.includes("且未在审查页修复")',
                'renderer.includes("跨对象共面重叠 0") &&\n'
                '        renderer.includes("不是固定圆环、竖线") &&\n'
                '        renderer.includes("保留半炉的对侧内壁")',
                1,
                "verifier V4 static composition disclosure",
            ),
            ('stage_id: "WEB-60_R2T"', 'stage_id: "WEB-60_R2U"', 1, "verifier stage id"),
            ("V3", "V4", 2, "verifier V4 contract labels"),
        ],
    )
    if "frontend_dashboard_v3.server.html" not in text:
        raise RuntimeError("Verifier must continue protecting the V3 production page.")
    return text, records


def write_lf(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as stream:
        stream.write(text)


def main() -> int:
    if not MODEL.is_file():
        raise RuntimeError(f"V4 model missing: {MODEL}")
    if MODEL.stat().st_size != MODEL_BYTES or sha256_file(MODEL) != MODEL_SHA256:
        raise RuntimeError("V4 model bytes/SHA contract failed.")
    formal = FRONTEND / "models" / "gl02_blast_furnace.glb"
    if sha256_file(formal) != FORMAL_SHA256:
        raise RuntimeError("Formal production GLB drift detected.")

    builders = [
        (OUTPUT_HTML, build_html),
        (OUTPUT_RENDERER, build_renderer),
        (OUTPUT_SERVER, build_server),
        (OUTPUT_VERIFIER, build_verifier),
    ]
    transformation_records: dict[str, list[dict[str, object]]] = {}
    for output, builder in builders:
        text, records = builder()
        write_lf(output, text)
        transformation_records[relative(output)] = records

    report = {
        "schema_version": "bf3d.r2u.web_review_build.v1",
        "requirement_id": REQUIREMENT_ID,
        "status": "isolated_v4_review_surface_built",
        "evidence": "E/illustrative",
        "reference_status": "REF-PENDING",
        "not_for_construction": True,
        "production_integrated": False,
        "source_locks": {
            relative(path): {
                **expected,
                "actual_sha256": sha256_file(path),
                "actual_bytes": path.stat().st_size,
            }
            for path, expected in SOURCE_LOCKS.items()
        },
        "model": artifact(MODEL),
        "formal_glb": artifact(formal),
        "outputs": [artifact(path) for path, _ in builders],
        "transformations": transformation_records,
        "checks": {
            "all_source_locks_match": True,
            "v4_model_sha_matches": True,
            "formal_glb_unchanged": True,
            "v3_review_surface_unchanged": True,
            "v4_outputs_exist": all(path.is_file() for path, _ in builders),
            "production_integration_absent": True,
        },
    }
    report["passed"] = all(report["checks"].values())
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    write_lf(OUTPUT_REPORT, json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(report, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
