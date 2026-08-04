"""Reopen validation for the clean GL02 structural-review V2 Blend.

Run with Blender:
    blender.exe --background <review.blend> --python-exit-code 1 \
      --python tools/verify_bf3d_structural_review_v2_blender.py

Requirement:
    REQ-BF3D-CLEAN-STRUCTURAL-REVIEW-20260719
"""

from __future__ import annotations

import hashlib
import json
import struct
import sys
from collections import Counter
from pathlib import Path

import bpy


ROOT = Path(r"D:\文件\冀南钢铁运行中第二版本")
MODEL_DIR = ROOT / "高炉前端数据" / "models"
BLEND = MODEL_DIR / "gl02_blast_furnace_structural_review.v2.blend"
MATERIAL_GLB = MODEL_DIR / "gl02_blast_furnace_material_review.v2.glb"
STRUCTURAL_GLB = MODEL_DIR / "gl02_blast_furnace_structural_review.v2.glb"
MANIFEST = STRUCTURAL_GLB.with_suffix(".manifest.json")
REPORT = (
    ROOT
    / "PT"
    / "高炉3D模型"
    / "work"
    / "WEB_60_20260719_R2P_CLEAN_STRUCTURAL_REVIEW"
    / "reopen_validation.json"
)
IMPORT_REPORT = REPORT.with_name("glb_import_validation.json")
FULL_COLLECTION = "BF3D_V2_FULL_MATERIAL_REVIEW"
SECTION_COLLECTION = "BF3D_V2_STRUCTURAL_SECTION"
FORBIDDEN_TOKENS = (
    "SENSOR_",
    "PRESSURE",
    "FLOW",
    "STREAMLINE",
    "BURDEN",
    "TEMP_LAYER",
    "PARTICLE",
    "GUIDE",
    "REFERENCE_BAND",
    "STIFFENER_RING",
    "COOLING_BAND",
    "ACCESS_TOWER",
    "SUPPORT_FRAME",
    "SKULL_STATE_LAYER_MISSING",
)


def sha256(path: Path) -> str:
    """Return the lower-case SHA-256 digest for *path*."""

    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def read_glb_json(path: Path) -> dict:
    """Read a GLB v2 JSON chunk."""

    with path.open("rb") as stream:
        magic, version, total_length = struct.unpack("<4sII", stream.read(12))
        if magic != b"glTF" or version != 2 or total_length != path.stat().st_size:
            raise RuntimeError(f"invalid GLB v2 header: {path}")
        chunk_length, chunk_type = struct.unpack("<I4s", stream.read(8))
        if chunk_type != b"JSON":
            raise RuntimeError(f"missing GLB JSON chunk: {path}")
        return json.loads(
            stream.read(chunk_length).decode("utf-8").rstrip(" \t\r\n\x00")
        )


def glb_summary(path: Path) -> dict:
    """Return counts, roles and forbidden names for one GLB."""

    data = read_glb_json(path)
    roles = Counter()
    names: list[str] = []
    for key in ("nodes", "meshes", "materials"):
        names.extend(item.get("name", "") for item in data.get(key, []))
    for node in data.get("nodes", []):
        role = (node.get("extras") or {}).get("bf3d_structural_role")
        if role:
            roles[role] += 1
    return {
        "nodes": len(data.get("nodes", [])),
        "meshes": len(data.get("meshes", [])),
        "materials": len(data.get("materials", [])),
        "textures": len(data.get("textures", [])),
        "images": len(data.get("images", [])),
        "roles": dict(sorted(roles.items())),
        "forbidden_names": sorted(
            {
                name
                for name in names
                if any(token in name.upper() for token in FORBIDDEN_TOKENS)
            }
        ),
    }


def import_summary(path: Path) -> dict:
    """Factory-import one GLB and inspect the resulting Blender objects."""

    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete(use_global=False)
    bpy.ops.import_scene.gltf(filepath=str(path))
    meshes = [obj for obj in bpy.context.scene.objects if obj.type == "MESH"]
    roles = Counter(
        obj.get("bf3d_structural_role")
        for obj in meshes
        if obj.get("bf3d_structural_role")
    )
    forbidden = sorted(
        {
            obj.name
            for obj in meshes
            if any(token in obj.name.upper() for token in FORBIDDEN_TOKENS)
        }
    )
    return {
        "path": str(path),
        "mesh_objects": len(meshes),
        "roles": dict(sorted(roles.items())),
        "forbidden_objects": forbidden,
        "materials": len(
            {
                slot.material.name
                for obj in meshes
                for slot in obj.material_slots
                if slot.material is not None
            }
        ),
    }


def validate_glb_imports() -> None:
    """Prove both V2 GLBs import directly through Blender's glTF importer."""

    structural = import_summary(STRUCTURAL_GLB)
    material = import_summary(MATERIAL_GLB)
    checks = {
        "structural_import_10_meshes": structural["mesh_objects"] == 10,
        "structural_roles_preserved": structural["roles"]
        == {
            "backfill": 1,
            "cooling_stave": 2,
            "hotface_embed": 1,
            "refractory": 1,
            "steel_shell": 5,
        },
        "structural_forbidden_zero": not structural["forbidden_objects"],
        "material_import_5_meshes": material["mesh_objects"] == 5,
        "material_roles_preserved": material["roles"] == {"steel_shell": 5},
        "material_forbidden_zero": not material["forbidden_objects"],
    }
    report = {
        "requirement_id": "REQ-BF3D-CLEAN-STRUCTURAL-REVIEW-20260719",
        "structural": structural,
        "material": material,
        "checks": checks,
        "ok": all(checks.values()),
    }
    IMPORT_REPORT.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    if not report["ok"]:
        raise RuntimeError(
            "V2 direct GLB import validation failed: "
            + json.dumps(checks, ensure_ascii=False)
        )
    print("BF3D_V2_GLB_IMPORT_VALIDATION=" + json.dumps(report, ensure_ascii=False))


def main() -> None:
    """Validate the saved Blend and both V2 GLBs after a factory reopen."""

    if "--glb-import" in sys.argv:
        validate_glb_imports()
        return
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    full = bpy.data.collections.get(FULL_COLLECTION)
    section = bpy.data.collections.get(SECTION_COLLECTION)
    if full is None or section is None:
        raise RuntimeError("review collections are missing after reopen")

    full_meshes = [obj for obj in full.objects if obj.type == "MESH"]
    section_meshes = [obj for obj in section.objects if obj.type == "MESH"]
    scene_names = [obj.name for obj in bpy.context.scene.objects]
    packed_images = [
        image.name
        for image in bpy.data.images
        if image.packed_file is not None or bool(image.packed_files)
    ]
    material_ids = sorted(
        {
            material.get("bf3d_material_id")
            for material in bpy.data.materials
            if material.get("bf3d_material_id")
        }
    )
    material_summary = glb_summary(MATERIAL_GLB)
    structural_summary = glb_summary(STRUCTURAL_GLB)

    checks = {
        "opened_expected_blend": Path(bpy.data.filepath) == BLEND,
        "full_collection_has_10_meshes": len(full_meshes) == 10,
        "section_collection_has_10_meshes": len(section_meshes) == 10,
        "full_collection_hidden_by_default": full.hide_viewport and full.hide_render,
        "section_collection_visible_by_default": (
            not section.hide_viewport and not section.hide_render
        ),
        "camera_active": bpy.context.scene.camera is not None
        and bpy.context.scene.camera.name == "BF3D_V2_SECTION_CAMERA",
        "review_lights_present": len(
            [name for name in scene_names if name.startswith("BF3D_V2_") and "CAMERA" not in name]
        )
        >= 4,
        "no_forbidden_scene_objects": not any(
            any(token in name.upper() for token in FORBIDDEN_TOKENS)
            for name in scene_names
        ),
        "section_metadata_present": all(
            obj.get("bf3d_section_physical_cut") is True for obj in section_meshes
        ),
        "generated_textures_packed": len(packed_images) >= 24,
        "material_identity_count": len(material_ids) >= 12,
        "material_glb_contract": (
            material_summary["nodes"] == 5
            and material_summary["roles"] == {"steel_shell": 5}
            and not material_summary["forbidden_names"]
        ),
        "structural_glb_contract": (
            structural_summary["nodes"] == 10
            and structural_summary["roles"]
            == {
                "backfill": 1,
                "cooling_stave": 2,
                "hotface_embed": 1,
                "refractory": 1,
                "steel_shell": 5,
            }
            and not structural_summary["forbidden_names"]
        ),
        "manifest_hashes_match": (
            sha256(MATERIAL_GLB)
            == manifest["outputs"]["material_review_glb"]["sha256"]
            and sha256(STRUCTURAL_GLB)
            == manifest["outputs"]["structural_section_glb"]["sha256"]
            and sha256(BLEND)
            == manifest["outputs"]["direct_open_blend"]["sha256"]
        ),
        "manifest_all_checks_pass": manifest.get("all_checks_pass") is True,
    }
    report = {
        "requirement_id": "REQ-BF3D-CLEAN-STRUCTURAL-REVIEW-20260719",
        "blend": {
            "path": str(BLEND),
            "bytes": BLEND.stat().st_size,
            "sha256": sha256(BLEND),
            "full_meshes": len(full_meshes),
            "section_meshes": len(section_meshes),
            "packed_images": len(packed_images),
            "material_ids": material_ids,
        },
        "material_glb": material_summary,
        "structural_glb": structural_summary,
        "checks": checks,
        "ok": all(checks.values()),
    }
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    if not report["ok"]:
        raise RuntimeError(
            "V2 reopen validation failed: "
            + json.dumps(checks, ensure_ascii=False)
        )
    print("BF3D_V2_REOPEN_VALIDATION=" + json.dumps(report, ensure_ascii=False))


if __name__ == "__main__":
    main()
