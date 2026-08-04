#!/usr/bin/env python3
"""Build-time contract gate for the R2Y material-signal Web fixture.

This command does not build or mutate a GLB.  It verifies the preregistered
immutable inputs, inspects the V5 material GLB container, checks the isolated
page/renderer/server/verifier source contract, and writes one traceable report.

Exit codes:
    0: every build-time gate passed.
    1: one or more gates failed (report is still written).
    2: argument or report-write failure.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import struct
import sys
from datetime import datetime
from pathlib import Path
from typing import Any


REQUIREMENT_ID = (
    "REQ-BF3D-R2Y-MATERIAL-SIGNAL-VISIBILITY-DIAGNOSTIC-20260720"
)
STAGE_ID = "WEB_60_20260720_R2Y_MATERIAL_SIGNAL_VISIBILITY_DIAGNOSTIC"
WORKSPACE_ROOT = Path(__file__).resolve().parents[1]
STAGE_ROOT = (
    WORKSPACE_ROOT / "PT" / "高炉3D模型" / "work" / STAGE_ID
)
REPORT_PATH = (
    STAGE_ROOT / "reports" / "r2y_material_signal_web_build_report.json"
)

PAGE = WORKSPACE_ROOT / "高炉前端数据" / "bf3d_review_r2y.server.html"
RENDERER = (
    WORKSPACE_ROOT
    / "高炉前端数据"
    / "assets"
    / "bf3d-review-renderer-r2y.js"
)
SERVER = WORKSPACE_ROOT / "tools" / "serve_bf3d_review_r2y.py"
VERIFIER = (
    WORKSPACE_ROOT / "tools" / "verify_bf3d_review_r2y_preview.cjs"
)
MODEL = (
    WORKSPACE_ROOT
    / "高炉前端数据"
    / "models"
    / "gl02_blast_furnace_material_review.v5.glb"
)
INPUT_LOCK = STAGE_ROOT / "input_lock.json"
CONTRACT = STAGE_ROOT / "WEB-60_R2Y_阶段预注册合同.md"

LOCKED_INPUTS = {
    "高炉前端数据/models/gl02_blast_furnace_material_review.v5.glb": (
        994_372,
        "652be1b2c9147d5a7392497c7ae4964d19bdd7095b5435b87c105f9eb3fb66bc",
    ),
    (
        "PT/高炉3D模型/work/"
        "WEB_60_20260720_R2X_R2J_AO_REBAKE_CANDIDATE/glb/"
        "gl02_blast_furnace_material_review."
        "r2x-ao-smoke1k.v5payload.glb"
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

CAPTURE_IDS = [
    "00_contract",
    "01_p40_detail_ortho6p2",
    "02_macro_ortho3p1",
    "03_graze30",
    "04_graze75",
    "05_aniso1",
    "06_aniso8",
    "07_env0",
    "08_env1",
    "09_basecolor_raw",
    "10_normal_xy_fixed",
    "11_roughness_fixed",
    "12_contact_sheet",
]

EXPECTED_MATERIALS = {
    "INT30_R2G_R1_LOCK_BAKED_PBR_STEEL",
    "INT30_R2G_R1_LOCK_BAKED_PBR_STEEL.001",
}
EXPECTED_SHELLS = {
    "R2J_ASM_GL02_FURNACE_BELLY_SHELL_55MM_E",
    "R2J_ASM_GL02_FURNACE_BOSH_SHELL_55MM_E",
    "R2J_ASM_GL02_FURNACE_HEARTH_SHELL_65MM_E",
    "R2J_ASM_GL02_FURNACE_SHAFT_SHELL_45MM_E",
    "R2J_ASM_GL02_FURNACE_THROAT_SHELL_45MM_E",
}


def relative(path: Path) -> str:
    """Return a stable workspace-relative POSIX path."""

    return path.relative_to(WORKSPACE_ROOT).as_posix()


def sha256_file(path: Path) -> str:
    """Hash a file in bounded blocks."""

    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def file_snapshot(path: Path) -> dict[str, Any]:
    """Capture existence, bytes and SHA for audit output."""

    if not path.is_file():
        return {
            "path": relative(path),
            "exists": False,
            "bytes": None,
            "sha256": None,
        }
    return {
        "path": relative(path),
        "exists": True,
        "bytes": path.stat().st_size,
        "sha256": sha256_file(path),
    }


def check(
    checks: list[dict[str, Any]],
    name: str,
    passed: bool,
    actual: Any,
    expected: Any,
) -> None:
    """Append one serializable fail-closed check."""

    checks.append(
        {
            "name": name,
            "passed": bool(passed),
            "actual": actual,
            "expected": expected,
        }
    )


def read_glb_json(path: Path) -> dict[str, Any]:
    """Decode the JSON chunk from a GLB 2.0 container."""

    with path.open("rb") as stream:
        header = stream.read(12)
        if len(header) != 12:
            raise ValueError("GLB header truncated")
        magic, version, declared_length = struct.unpack("<4sII", header)
        if magic != b"glTF" or version != 2:
            raise ValueError(
                f"not GLB 2.0: magic={magic!r}, version={version}"
            )
        if declared_length != path.stat().st_size:
            raise ValueError(
                "GLB declared length mismatch: "
                f"{declared_length}/{path.stat().st_size}"
            )
        chunk_header = stream.read(8)
        if len(chunk_header) != 8:
            raise ValueError("GLB JSON chunk header truncated")
        chunk_length, chunk_type = struct.unpack("<I4s", chunk_header)
        if chunk_type != b"JSON":
            raise ValueError(f"first GLB chunk is not JSON: {chunk_type!r}")
        payload = stream.read(chunk_length)
        if len(payload) != chunk_length:
            raise ValueError("GLB JSON chunk truncated")
    return json.loads(payload.rstrip(b"\x00 \t\r\n").decode("utf-8"))


def inspect_model(checks: list[dict[str, Any]]) -> dict[str, Any]:
    """Inspect V5 shell/material/texture bindings without mutation."""

    document = read_glb_json(MODEL)
    materials = document.get("materials", [])
    material_names = {item.get("name", "") for item in materials}
    meshes = document.get("meshes", [])
    mesh_names = {item.get("name", "") for item in meshes}
    normalized_mesh_names = {
        name[:-5] if name.endswith("_MESH") else name
        for name in mesh_names
    }
    targeted = EXPECTED_SHELLS & normalized_mesh_names
    check(
        checks,
        "glb_two_locked_materials",
        material_names == EXPECTED_MATERIALS,
        sorted(material_names),
        sorted(EXPECTED_MATERIALS),
    )
    check(
        checks,
        "glb_five_r2j_shell_meshes",
        targeted == EXPECTED_SHELLS and len(meshes) == 5,
        {"mesh_count": len(meshes), "target_names": sorted(targeted)},
        {"mesh_count": 5, "target_names": sorted(EXPECTED_SHELLS)},
    )

    binding_rows = []
    for material in materials:
        pbr = material.get("pbrMetallicRoughness", {})
        base = pbr.get("baseColorTexture")
        orm = pbr.get("metallicRoughnessTexture")
        normal = material.get("normalTexture")
        row = {
            "name": material.get("name"),
            "base_color_texture": base,
            "normal_texture": normal,
            "metallic_roughness_texture": orm,
            "occlusion_texture": material.get("occlusionTexture"),
        }
        binding_rows.append(row)
        for channel_name, binding in (
            ("baseColor", base),
            ("normal", normal),
            ("metallicRoughness", orm),
        ):
            check(
                checks,
                f"glb_{material.get('name')}_{channel_name}_texcoord0",
                isinstance(binding, dict)
                and int(binding.get("texCoord", 0)) == 0
                and isinstance(binding.get("index"), int),
                binding,
                {"index": "integer", "texCoord": 0},
            )
        normal_scale = normal.get("scale") if isinstance(normal, dict) else None
        check(
            checks,
            f"glb_{material.get('name')}_normal_scale_0p45",
            isinstance(normal_scale, (int, float))
            and abs(float(normal_scale) - 0.45) <= 1e-6,
            normal_scale,
            0.45,
        )
        check(
            checks,
            f"glb_{material.get('name')}_ao_absent",
            "occlusionTexture" not in material,
            material.get("occlusionTexture"),
            None,
        )
    images = document.get("images", [])
    embedded_images = sum(
        1
        for image in images
        if isinstance(image.get("bufferView"), int) and "uri" not in image
    )
    check(
        checks,
        "glb_images_embedded",
        bool(images) and embedded_images == len(images),
        {"image_count": len(images), "embedded_count": embedded_images},
        "all images embedded in bufferViews",
    )
    return {
        "asset": document.get("asset", {}),
        "mesh_count": len(meshes),
        "mesh_names": sorted(mesh_names),
        "normalized_mesh_names": sorted(normalized_mesh_names),
        "material_count": len(materials),
        "material_names": sorted(material_names),
        "image_count": len(images),
        "embedded_image_count": embedded_images,
        "bindings": binding_rows,
    }


def contains_all(source: str, tokens: list[str]) -> list[str]:
    """Return missing literal contract tokens."""

    return [token for token in tokens if token not in source]


def inspect_sources(checks: list[dict[str, Any]]) -> dict[str, Any]:
    """Check static scope markers before browser execution."""

    paths = [PAGE, RENDERER, SERVER, VERIFIER]
    sources: dict[Path, str] = {}
    for path in paths:
        exists = path.is_file()
        check(
            checks,
            f"source_exists:{relative(path)}",
            exists,
            exists,
            True,
        )
        sources[path] = path.read_text(encoding="utf-8") if exists else ""

    page_tokens = CAPTURE_IDS + [
        "960",
        "540",
        "E/diagnostic",
        "NOT BEAUTY",
        "NOT PRODUCTION",
        "AO off",
        "不加载正式 GLB、生产控制器或 R2X 候选",
    ]
    renderer_tokens = [
        "models/gl02_blast_furnace_material_review.v5.glb",
        LOCKED_INPUTS[
            "高炉前端数据/models/"
            "gl02_blast_furnace_material_review.v5.glb"
        ][1],
        "P40_CAM_DETAIL_SHELL",
        "BASELINE_ORTHO_SCALE = 6.2",
        "MACRO_ORTHO_SCALE = 3.1",
        "grazingDegrees: 30",
        "grazingDegrees: 75",
        "anisotropy: 1",
        "anisotropy: 8",
        "ZERO_ENVIRONMENT",
        "BASELINE_ENVIRONMENT",
        "CHANNEL DIAGNOSTIC / NOT PBR",
        "THREE.ACESFilmicToneMapping",
        "setPixelRatio(1)",
        "pbrMutationCount",
        "aoEnabled: false",
        "roi: { ...ROI }",
    ]
    server_tokens = [
        "ROUTES = {",
        "r2x_candidate_exposed",
        "ao_webgl_probe_exposed",
        "do_GET",
        "do_HEAD",
        "do_POST",
        "do_PUT",
        "do_PATCH",
        "do_DELETE",
        "Content-Security-Policy",
        "bf3d_r2y_review_server_ready",
    ]
    verifier_tokens = [
        "playwright.chromium.launch",
        "width: 1440",
        "height: 900",
        "full_matrix_executed: false",
        "not_executed",
    ] + CAPTURE_IDS
    for name, source, tokens in (
        ("page_contract_tokens", sources[PAGE], page_tokens),
        ("renderer_contract_tokens", sources[RENDERER], renderer_tokens),
        ("server_contract_tokens", sources[SERVER], server_tokens),
        ("verifier_contract_tokens", sources[VERIFIER], verifier_tokens),
    ):
        missing = contains_all(source, tokens)
        check(checks, name, not missing, missing, [])

    renderer = sources[RENDERER]
    check(
        checks,
        "renderer_only_v5_model_url",
        ".r2x-ao-" not in renderer
        and "gl02_blast_furnace_review.v5.glb" not in renderer,
        {
            "has_r2x_url": ".r2x-ao-" in renderer,
            "has_formal_url": "gl02_blast_furnace_review.v5.glb" in renderer,
        },
        {"has_r2x_url": False, "has_formal_url": False},
    )
    verifier = sources[VERIFIER]
    check(
        checks,
        "verifier_chromium_representative_only",
        "playwright.firefox" not in verifier
        and "playwright.webkit" not in verifier
        and verifier.count("playwright.chromium.launch") == 1,
        {
            "chromium_launch_count": verifier.count(
                "playwright.chromium.launch"
            ),
            "firefox_reference": "playwright.firefox" in verifier,
            "webkit_reference": "playwright.webkit" in verifier,
        },
        {
            "chromium_launch_count": 1,
            "firefox_reference": False,
            "webkit_reference": False,
        },
    )
    return {
        relative(path): file_snapshot(path)
        for path in paths
    }


def inspect_locked_inputs(
    checks: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Enforce all seven preregistered immutable input locks."""

    rows = []
    for rel_path, (expected_bytes, expected_sha) in LOCKED_INPUTS.items():
        path = WORKSPACE_ROOT / Path(rel_path)
        snapshot = file_snapshot(path)
        passed = (
            snapshot["exists"]
            and snapshot["bytes"] == expected_bytes
            and snapshot["sha256"] == expected_sha
        )
        row = {
            **snapshot,
            "expected_bytes": expected_bytes,
            "expected_sha256": expected_sha,
            "passed": passed,
        }
        rows.append(row)
        check(
            checks,
            f"locked_input:{rel_path}",
            passed,
            {
                "exists": snapshot["exists"],
                "bytes": snapshot["bytes"],
                "sha256": snapshot["sha256"],
            },
            {
                "exists": True,
                "bytes": expected_bytes,
                "sha256": expected_sha,
            },
        )
    return rows


def protected_snapshots() -> list[dict[str, Any]]:
    """Read protected paths from the already locked stage input gate."""

    if not INPUT_LOCK.is_file():
        return []
    data = json.loads(INPUT_LOCK.read_text(encoding="utf-8"))
    rows = []
    for item in data.get("protected_assets", []):
        path = WORKSPACE_ROOT / Path(item["path"])
        snapshot = file_snapshot(path)
        rows.append(
            {
                **snapshot,
                "locked_bytes": item.get("expected_bytes"),
                "locked_sha256": item.get("expected_sha256"),
                "matches_input_lock": (
                    snapshot["exists"]
                    and snapshot["bytes"] == item.get("expected_bytes")
                    and snapshot["sha256"] == item.get("expected_sha256")
                ),
            }
        )
    return rows


def build_report() -> tuple[dict[str, Any], bool]:
    """Run build-time checks and return report plus overall result."""

    checks: list[dict[str, Any]] = []
    locked_inputs = inspect_locked_inputs(checks)
    check(
        checks,
        "preregistered_contract_exists",
        CONTRACT.is_file(),
        file_snapshot(CONTRACT),
        {"exists": True},
    )
    model_audit: dict[str, Any]
    try:
        model_audit = inspect_model(checks)
    except (OSError, ValueError, json.JSONDecodeError) as error:
        model_audit = {"error": str(error)}
        check(checks, "glb_parse", False, str(error), "valid GLB 2.0")
    source_audit = inspect_sources(checks)
    protected_before = protected_snapshots()
    protected_after = protected_snapshots()
    protected_unchanged = protected_before == protected_after
    check(
        checks,
        "protected_assets_unchanged_during_build",
        protected_unchanged,
        protected_after,
        protected_before,
    )
    all_passed = all(item["passed"] for item in checks)
    report = {
        "schema_version": "bf3d.r2y.material_signal_web_build_report.v1",
        "requirement_id": REQUIREMENT_ID,
        "stage_id": STAGE_ID,
        "generated_at": datetime.now().astimezone().isoformat(),
        "scope": {
            "evidence": "E/diagnostic",
            "beauty_approved": False,
            "production_approved": False,
            "representative_browser": "Chromium",
            "representative_viewport_css": [1440, 900],
            "full_matrix_executed": False,
            "asset_mutation_allowed": False,
            "ao_webgl_liveness": {
                "status": "not_executed",
                "reason": (
                    "This isolated PBR fixture does not expose or load the "
                    "locked R2X candidate; shader liveness cannot be inferred."
                ),
                "classification": "not_executed_fail_closed",
            },
        },
        "locked_inputs": locked_inputs,
        "model_audit": model_audit,
        "source_audit": source_audit,
        "protected_assets_before": protected_before,
        "protected_assets_after": protected_after,
        "checks": checks,
        "check_summary": {
            "total": len(checks),
            "passed": sum(1 for item in checks if item["passed"]),
            "failed": sum(1 for item in checks if not item["passed"]),
        },
        "artifacts": [
            relative(PAGE),
            relative(RENDERER),
            relative(SERVER),
            relative(VERIFIER),
            relative(REPORT_PATH),
        ],
        "passed": all_passed,
        "stop_lines": {
            "full_matrix_allowed": False,
            "ao_rebake_allowed": False,
            "ao_2k_approved": False,
            "p50_approved": False,
            "p60_approved": False,
            "production_integration_allowed": False,
            "next_release_stage_allowed": False,
        },
    }
    return report, all_passed


def build_parser() -> argparse.ArgumentParser:
    """Build CLI without any mutation options."""

    parser = argparse.ArgumentParser(
        description="核验 R2Y PBR 信号隔离页的构建时合同。",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "示例：\n"
            "  python tools/build_bf3d_review_r2y_web.py\n"
            "  python tools/build_bf3d_review_r2y_web.py --print-report\n"
            "  python tools/build_bf3d_review_r2y_web.py --check-only\n\n"
            "不修改任何 GLB/纹理；失败也写 fail-closed JSON 报告。"
        ),
    )
    parser.add_argument(
        "--check-only",
        action="store_true",
        help="执行全部检查但不写报告。",
    )
    parser.add_argument(
        "--print-report",
        action="store_true",
        help="把完整 JSON 报告输出到 stdout。",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    """Execute the fail-closed build gate."""

    args = build_parser().parse_args(argv)
    try:
        report, passed = build_report()
        if not args.check_only:
            REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
            REPORT_PATH.write_text(
                json.dumps(report, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
    except (OSError, ValueError, json.JSONDecodeError) as error:
        print(
            json.dumps(
                {
                    "ok": False,
                    "requirement_id": REQUIREMENT_ID,
                    "error": str(error),
                },
                ensure_ascii=False,
            ),
            file=sys.stderr,
        )
        return 2
    if args.print_report:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print(
            json.dumps(
                {
                    "ok": passed,
                    "report": relative(REPORT_PATH),
                    "checks": report["check_summary"],
                    "full_matrix_executed": False,
                    "ao_webgl_liveness": "not_executed",
                },
                ensure_ascii=False,
            )
        )
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
