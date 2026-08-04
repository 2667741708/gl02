#!/usr/bin/env python3
"""Validate and package the R2X 1K AO isolated Web representative.

Requirement:
    REQ-BF3D-R2X-R2J-AO-REBAKE-CONSUMPTION-20260720

This command does not edit the candidate GLB, V5 assets, production files,
materials, lights, camera parameters, textures, or the R2X contract. It only
validates the five owned Web sources and writes the R2X Web build report.

Exit codes:
    0: source, GLB, and immutable-input contracts passed.
    2: one or more fail-closed checks failed.
"""

from __future__ import annotations

import hashlib
import json
import struct
import sys
from pathlib import Path
from typing import Any


REQUIREMENT_ID = "REQ-BF3D-R2X-R2J-AO-REBAKE-CONSUMPTION-20260720"
STAGE_ID = "WEB_60_20260720_R2X_R2J_AO_REBAKE_CANDIDATE"
ROOT = Path(__file__).resolve().parents[1]
FRONTEND = ROOT / "高炉前端数据"
TOOLS = ROOT / "tools"
STAGE = ROOT / "PT" / "高炉3D模型" / "work" / STAGE_ID
REPORT = STAGE / "reports" / "r2x_web_candidate_build_report.json"

HTML = FRONTEND / "bf3d_review_r2x.server.html"
RENDERER = FRONTEND / "assets" / "bf3d-review-renderer-r2x.js"
SERVER = TOOLS / "serve_bf3d_review_r2x.py"
VERIFIER = TOOLS / "verify_bf3d_review_r2x_preview.cjs"
CANDIDATE = (
    STAGE
    / "glb"
    / "gl02_blast_furnace_material_review.r2x-ao-smoke1k.v5payload.glb"
)
CANDIDATE_BYTES = 1_115_216
CANDIDATE_SHA256 = (
    "bd074c23c237fe7ff3abac0f823bd9aef978021e4e829963b3f979e9b58f1c00"
)
PROTECTED_LOCKS = {
    FRONTEND / "models" / "gl02_blast_furnace_review.v5.blend": (
        "3e6df5fb02d3734d14923d4432739a5918ac8249d6a3c8ad1415395429b27e3a"
    ),
    FRONTEND / "models" / "gl02_blast_furnace_review.v5.glb": (
        "0ac031e626c9eaa0b0cdd8192cf9fda712324af174a4285f563a97309451ed3c"
    ),
    FRONTEND / "models" / "gl02_blast_furnace_material_review.v5.glb": (
        "652be1b2c9147d5a7392497c7ae4964d19bdd7095b5435b87c105f9eb3fb66bc"
    ),
    FRONTEND / "models" / "gl02_blast_furnace_structural_review.v5.glb": (
        "e5c77d3834c631e2513209a690f6328d1c63dba2c8d489b2d2dbe17645465f71"
    ),
    FRONTEND / "models" / "gl02_blast_furnace.glb": (
        "808960f1b2703e7fb27df35f1b1b1a17063b9b10d2267acba593fc3872b62af6"
    ),
}
PRODUCTION_FILES = (
    FRONTEND / "frontend_dashboard_v3.server.html",
    FRONTEND / "assets" / "bf3d-structural-review.js",
)


def sha256_file(path: Path) -> str:
    """Return a lowercase SHA-256 without modifying the file."""

    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def artifact(path: Path) -> dict[str, Any]:
    """Return one repository-relative immutable artifact record."""

    return {
        "path": path.resolve().relative_to(ROOT.resolve()).as_posix(),
        "bytes": path.stat().st_size,
        "sha256": sha256_file(path),
    }


def check(check_id: str, passed: bool, detail: Any = None) -> dict[str, Any]:
    """Build one machine-readable fail-closed check."""

    item: dict[str, Any] = {"id": check_id, "passed": bool(passed)}
    if detail is not None:
        item["detail"] = detail
    return item


def parse_glb_json(path: Path) -> dict[str, Any]:
    """Read and decode only the JSON chunk from a GLB 2.0 file."""

    payload = path.read_bytes()
    if len(payload) < 20:
        raise RuntimeError("R2X candidate is too small to be a GLB")
    magic, version, declared_length = struct.unpack_from("<4sII", payload, 0)
    if magic != b"glTF" or version != 2 or declared_length != len(payload):
        raise RuntimeError(
            "R2X GLB header mismatch: "
            f"magic={magic!r}, version={version}, "
            f"length={declared_length}/{len(payload)}"
        )
    json_length, json_type = struct.unpack_from("<I4s", payload, 12)
    if json_type != b"JSON":
        raise RuntimeError(f"R2X first GLB chunk is not JSON: {json_type!r}")
    start = 20
    end = start + json_length
    return json.loads(payload[start:end].decode("utf-8").rstrip(" \t\r\n\x00"))


def glb_contract(document: dict[str, Any]) -> dict[str, Any]:
    """Validate the five-shell AO/TEXCOORD contract directly from GLB JSON."""

    nodes = document.get("nodes", [])
    meshes = document.get("meshes", [])
    materials = document.get("materials", [])
    target_nodes = [
        node
        for node in nodes
        if str(node.get("name", "")).startswith("R2J_ASM_GL02_FURNACE_")
        and "_SHELL_" in str(node.get("name", ""))
    ]
    primitive_records: list[dict[str, Any]] = []
    for node in target_nodes:
        mesh_index = node.get("mesh")
        mesh = meshes[mesh_index] if isinstance(mesh_index, int) else {}
        for primitive_index, primitive in enumerate(mesh.get("primitives", [])):
            material_index = primitive.get("material")
            material = (
                materials[material_index]
                if isinstance(material_index, int)
                else {}
            )
            pbr = material.get("pbrMetallicRoughness", {})
            attributes = sorted(primitive.get("attributes", {}).keys())
            record = {
                "node": node.get("name"),
                "mesh": mesh.get("name"),
                "primitive_index": primitive_index,
                "material": material.get("name"),
                "attributes": attributes,
                "basecolor_texcoord": pbr.get("baseColorTexture", {}).get(
                    "texCoord", 0
                ),
                "metallic_roughness_texcoord": pbr.get(
                    "metallicRoughnessTexture", {}
                ).get("texCoord", 0),
                "normal_texcoord": material.get("normalTexture", {}).get(
                    "texCoord", 0
                ),
                "occlusion_texcoord": material.get(
                    "occlusionTexture", {}
                ).get("texCoord"),
                "occlusion_strength": material.get(
                    "occlusionTexture", {}
                ).get("strength", 1),
            }
            record["passed"] = (
                {"TEXCOORD_0", "TEXCOORD_1", "TEXCOORD_2"}.issubset(
                    set(attributes)
                )
                and record["basecolor_texcoord"] == 0
                and record["metallic_roughness_texcoord"] == 0
                and record["normal_texcoord"] == 0
                and record["occlusion_texcoord"] == 2
                and record["occlusion_strength"] == 1
            )
            primitive_records.append(record)
    checks = [
        check("five_target_nodes", len(target_nodes) == 5, len(target_nodes)),
        check("five_meshes", len(meshes) == 5, len(meshes)),
        check(
            "exact_v5_shared_material_baseline",
            len(materials) == 2
            and [material.get("name") for material in materials]
            == [
                "INT30_R2G_R1_LOCK_BAKED_PBR_STEEL",
                "INT30_R2G_R1_LOCK_BAKED_PBR_STEEL.001",
            ],
            {
                "material_count": len(materials),
                "material_names": [
                    material.get("name") for material in materials
                ],
            },
        ),
        check(
            "five_ao_primitives",
            len(primitive_records) == 5
            and all(record["passed"] for record in primitive_records),
            primitive_records,
        ),
        check(
            "all_resources_embedded",
            all(not image.get("uri") for image in document.get("images", [])),
            document.get("images", []),
        ),
    ]
    return {
        "asset": document.get("asset", {}),
        "extensions_used": document.get("extensionsUsed", []),
        "extensions_required": document.get("extensionsRequired", []),
        "node_count": len(nodes),
        "mesh_count": len(meshes),
        "material_count": len(materials),
        "primitive_records": primitive_records,
        "checks": checks,
        "passed": all(item["passed"] for item in checks),
    }


def main() -> int:
    """Validate R2X Web sources and emit the owned build report."""

    try:
        required = [HTML, RENDERER, SERVER, VERIFIER, CANDIDATE]
        required.extend(PROTECTED_LOCKS)
        required.extend(PRODUCTION_FILES)
        missing = [
            str(path.resolve().relative_to(ROOT.resolve()))
            for path in required
            if not path.is_file()
        ]
        if missing:
            raise RuntimeError(f"R2X Web required files missing: {missing}")

        candidate_artifact = artifact(CANDIDATE)
        protected = {str(path): artifact(path) for path in PROTECTED_LOCKS}
        production = {str(path): artifact(path) for path in PRODUCTION_FILES}
        html = HTML.read_text(encoding="utf-8")
        renderer = RENDERER.read_text(encoding="utf-8")
        server = SERVER.read_text(encoding="utf-8")
        verifier = VERIFIER.read_text(encoding="utf-8")
        document = parse_glb_json(CANDIDATE)
        candidate_glb_contract = glb_contract(document)

        checks = [
            check(
                "candidate_lock",
                candidate_artifact["bytes"] == CANDIDATE_BYTES
                and candidate_artifact["sha256"] == CANDIDATE_SHA256,
                candidate_artifact,
            ),
            check(
                "protected_v5_and_formal_locks",
                all(
                    protected[str(path)]["sha256"] == expected
                    for path, expected in PROTECTED_LOCKS.items()
                ),
                protected,
            ),
            check(
                "candidate_glb_contract",
                candidate_glb_contract["passed"],
                candidate_glb_contract,
            ),
            check(
                "page_scope_disclosure",
                all(
                    token in html
                    for token in (
                        "1K smoke",
                        "E/illustrative",
                        "not P50",
                        "not production",
                        'data-view-button="global"',
                        'data-view-button="detail"',
                        'data-ao-button="off"',
                        'data-ao-button="on"',
                    )
                ),
            ),
            check(
                "single_v5payload_url",
                (
                    "gl02_blast_furnace_material_review.r2x-ao-smoke1k.v5payload.glb"
                    in renderer
                    and 'r2x-ao-smoke1k.glb"' not in renderer
                ),
            ),
            check(
                "runtime_ao_contract",
                all(
                    token in renderer
                    for token in (
                        "aoMapChannel2",
                        'getAttribute?.("uv2")',
                        "nonAoTextureChannel0Count",
                        "entry.material.aoMapIntensity = value",
                        "entry.importedAoIntensity",
                        "onlyIntensityChangesAtRuntime",
                    )
                ),
            ),
            check(
                "locked_r2w_p40_color_camera_contract",
                all(
                    token in renderer
                    for token in (
                        "const FIXED_EXPOSURE = 1.0",
                        "[0.0864, 0.0864, 0.0864]",
                        "THREE.ACESFilmicToneMapping",
                        "[0.78, 0.18, 0.62]",
                        "exteriorGlobalHeightTarget: 0.86",
                        "exteriorDetailWidthTarget: 0.74",
                        "intensityAtK1: 1.3275510357953",
                    )
                ),
            ),
            check(
                "server_isolated_allow_list",
                all(
                    token in server
                    for token in (
                        "bf3d_review_r2x.server.html",
                        "bf3d-review-renderer-r2x.js",
                        "r2x-ao-smoke1k.v5payload.glb",
                        '"production_page_exposed": False',
                        '"formal_glb_exposed": False',
                        '"write_methods_supported": False',
                    )
                ),
            ),
            check(
                "representative_only_four_capture_verifier",
                all(
                    token in verifier
                    for token in (
                        'browserType: "chromium"',
                        "width: 1440",
                        "height: 900",
                        "global-off",
                        "global-on",
                        "detail-off",
                        "detail-on",
                        "full_matrix_executed: false",
                    )
                )
                and "firefox.launch" not in verifier
                and "webkit.launch" not in verifier,
            ),
        ]
        passed = all(item["passed"] for item in checks)
        report = {
            "schema_version": "bf3d.r2x.web_candidate_build.v1",
            "requirement_id": REQUIREMENT_ID,
            "stage_id": STAGE_ID,
            "candidate": candidate_artifact,
            "outputs": [artifact(path) for path in (HTML, RENDERER, SERVER, VERIFIER)],
            "protected_v5_and_formal": protected,
            "production_files_snapshot": production,
            "glb_contract": candidate_glb_contract,
            "checks": checks,
            "passed": passed,
            "scope": {
                "resolution": "1K smoke",
                "representative_only": True,
                "browser": "Chromium",
                "viewport": [1440, 900],
                "glb_modified": False,
                "material_modified": False,
                "lighting_modified": False,
                "exposure_modified": False,
                "environment_modified": False,
                "tone_mapping_modified": False,
                "camera_modified_from_r2w": False,
                "runtime_change": "five shell aoMapIntensity only",
                "p50_approved": False,
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
            "BF3D_R2X_WEB_CANDIDATE="
            + json.dumps(
                {
                    "passed": passed,
                    "candidate": candidate_artifact,
                    "report": REPORT.resolve()
                    .relative_to(ROOT.resolve())
                    .as_posix(),
                },
                ensure_ascii=False,
            )
        )
        return 0 if passed else 2
    except (OSError, RuntimeError, UnicodeError, json.JSONDecodeError) as error:
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
