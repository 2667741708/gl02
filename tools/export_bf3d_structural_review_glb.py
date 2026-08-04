"""Build the controlled GL02 structural-review Web GLB.

Requirement:
    REQ-BF3D-STRUCTURAL-REVIEW-20260719

Inputs are immutable stage candidates:
    - R2G/R2H baked R5 Web GLB (base scene and 115 sensors)
    - R2K Blend (inherits the approved R2J five-zone shell entities)

The script is intended to run inside Blender:
    blender.exe --background --python tools/export_bf3d_structural_review_glb.py

It never overwrites the historical formal GLB. The output receives a versioned
name plus a manifest containing hashes, counts, provenance and rollback data.
"""

from __future__ import annotations

import hashlib
import json
import struct
from collections import Counter
from pathlib import Path

import bpy


ROOT = Path(r"D:\文件\冀南钢铁运行中第二版本")
BASE_GLB = (
    ROOT
    / "PT"
    / "高炉3D模型"
    / "work"
    / "INT_30_20260718_R2H_WEB_DETAIL_NORMAL"
    / "input"
    / "INT_30_R2G_BASE_R1_R5_UNCHANGED.glb"
)
R2K_BLEND = (
    ROOT
    / "PT"
    / "高炉3D模型"
    / "work"
    / "INT_30_20260719_R2K_WALL_INTERNAL_SOLIDS"
    / "blends"
    / "INT_30_R2K_WALL_INTERNAL_SOLIDS_CANDIDATE.blend"
)
FORMAL_GLB = ROOT / "高炉前端数据" / "models" / "gl02_blast_furnace.glb"
OUTPUT_GLB = (
    ROOT
    / "高炉前端数据"
    / "models"
    / "gl02_blast_furnace_structural_review.v1.glb"
)
OUTPUT_MANIFEST = OUTPUT_GLB.with_suffix(".manifest.json")
STAGE = (
    ROOT
    / "PT"
    / "高炉3D模型"
    / "work"
    / "WEB_60_20260719_R2O_STRUCTURAL_REVIEW"
)
STAGE_MANIFEST = STAGE / "structural_review_asset_manifest.json"

EXPECTED_BASE_SHA256 = (
    "9db82c83f2e3c8c78aff38c2b71810fcabb8394806f765d94280bedb0145f952"
)
EXPECTED_R2K_SHA256 = (
    "51fb6f57fe06ff923de5ea823aca8ba0fb51382d757b768a0669ce74b85bba68"
)
EXPECTED_FORMAL_SHA256 = (
    "808960f1b2703e7fb27df35f1b1b1a17063b9b10d2267acba593fc3872b62af6"
)

ZONES = ("HEARTH", "BOSH", "BELLY", "SHAFT", "THROAT")
STRUCTURAL_PREFIXES = (
    "R2J_ASM_GL02_FURNACE_",
    "R2K_L02_BACKFILL_40MM_CLOSED_ENTITY_E",
    "R2K_L04_HOTFACE_EMBED_40MM_CLOSED_ENTITY_E",
    "R2K_L05_RESIDUAL_REFRACTORY_CLOSED_ENTITY_E",
    "R2K_L06_IRREGULAR_SKULL_STATE_LAYER_MISSING_E",
    "SM_BF3D_GL02_CST_",
)
LEGACY_REVIEW_ARTIFACT_PREFIXES = (
    "APPROX_GL02_INT10_",
    "APPROX_GL02_INT20_",
    "GL02_INT30_PRESSURE_",
    "立方体",
    "球体",
)


def sha256(path: Path) -> str:
    """Return a lower-case SHA-256 digest for a file."""

    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def rel(path: Path) -> str:
    """Return a repository-relative POSIX path."""

    return path.relative_to(ROOT).as_posix()


def check_locked_input(path: Path, expected: str, label: str) -> None:
    """Reject missing or drifted controlled inputs."""

    if not path.is_file():
        raise RuntimeError(f"{label} is missing: {path}")
    actual = sha256(path)
    if actual != expected:
        raise RuntimeError(
            f"{label} SHA-256 drifted: expected={expected}, actual={actual}"
        )


def reset_scene() -> None:
    """Remove the Blender startup scene before importing the controlled base."""

    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete(use_global=False)
    for block in (bpy.data.meshes, bpy.data.curves, bpy.data.cameras, bpy.data.lights):
        for item in list(block):
            if item.users == 0:
                block.remove(item)


def import_r5_web_base() -> list[bpy.types.Object]:
    """Import the baked R5/R2G scene that already preserves Web PBR channels."""

    bpy.ops.import_scene.gltf(filepath=str(BASE_GLB))
    imported = list(bpy.context.scene.objects)
    if not imported:
        raise RuntimeError("R2G/R2H base GLB imported no objects")
    return imported


def is_structural_source(name: str) -> bool:
    """Return whether an R2K library object belongs in the Web review asset."""

    return any(name.startswith(prefix) for prefix in STRUCTURAL_PREFIXES)


def is_legacy_review_artifact(name: str) -> bool:
    """Exclude old section cards, guide lines and duplicate pressure markers."""

    return any(name.startswith(prefix) for prefix in LEGACY_REVIEW_ARTIFACT_PREFIXES)


def append_structural_objects() -> list[bpy.types.Object]:
    """Append only R2J assembly and R2K wall objects from the R2K candidate."""

    with bpy.data.libraries.load(str(R2K_BLEND), link=False) as (source, target):
        target.objects = [name for name in source.objects if is_structural_source(name)]
    appended = [obj for obj in target.objects if obj is not None]
    for obj in appended:
        if not obj.users_collection:
            bpy.context.scene.collection.objects.link(obj)
    if len([obj for obj in appended if obj.name.startswith("R2J_ASM_")]) != 5:
        raise RuntimeError("R2J five-zone assembly count is not 5")
    if len([obj for obj in appended if obj.name.startswith("SM_BF3D_GL02_CST_")]) != 560:
        raise RuntimeError("R2K cooling stave count is not 560")
    return appended


def find_base_shell(zone: str) -> bpy.types.Object:
    """Locate one exact R5 baked base shell mesh."""

    name = f"APPROX_GL02_FURNACE_{zone}"
    obj = bpy.data.objects.get(name)
    if obj is None or obj.type != "MESH" or not obj.material_slots:
        raise RuntimeError(f"missing baked R5 shell mesh/material: {name}")
    return obj


def bind_r5_to_r2j_shell_entities(appended: list[bpy.types.Object]) -> None:
    """Use the baked Web R5 material on each R2J entity's exterior slot."""

    for zone in ZONES:
        matches = [
            obj
            for obj in appended
            if obj.name.startswith(f"R2J_ASM_GL02_FURNACE_{zone}_SHELL_")
        ]
        if len(matches) != 1:
            raise RuntimeError(f"R2J entity mismatch for {zone}: {len(matches)}")
        entity = matches[0]
        base_material = find_base_shell(zone).material_slots[0].material
        if base_material is None:
            raise RuntimeError(f"baked R5 material is missing for {zone}")
        entity.data.materials[0] = base_material
        entity["bf3d_role"] = "r2j_five_zone_steel_shell_entity"
        entity["bf3d_zone"] = zone
        entity["bf3d_evidence"] = "illustrative"
        entity["bf3d_default_visible"] = False
        entity["bf3d_material_source"] = "R2G_R2H_baked_R5_Web_PBR"


def classify_structural_object(obj: bpy.types.Object) -> str:
    """Map an appended object to a stable Web structural role."""

    name = obj.name
    if name.startswith("R2J_ASM_"):
        return "steel_shell"
    if name.startswith("R2K_L02_"):
        return "backfill"
    if name.startswith("R2K_L04_"):
        return "hotface_embed"
    if name.startswith("R2K_L05_"):
        return "refractory"
    if name.startswith("R2K_L06_"):
        return "skull_optional_missing"
    if name.startswith("SM_BF3D_GL02_CST_"):
        return "cooling_stave"
    return "unknown"


def object_is_alive(obj: bpy.types.Object | None) -> bool:
    """Return whether a Blender object reference still points to live RNA."""

    if obj is None:
        return False
    try:
        return obj.name in bpy.context.scene.objects
    except ReferenceError:
        return False


def mark_structural_metadata(appended: list[bpy.types.Object]) -> None:
    """Attach glTF extras used by the Three.js visibility controller."""

    for obj in appended:
        obj["bf3d_asset"] = "GL02_STRUCTURAL_REVIEW_V1"
        obj["bf3d_structural_role"] = classify_structural_object(obj)
        obj["bf3d_default_visible"] = False
        obj["bf3d_not_for_construction"] = True
        obj["bf3d_evidence"] = "illustrative"
        obj.hide_set(False)
        obj.hide_viewport = False
        obj.hide_render = False


def join_stave_family(
    appended: list[bpy.types.Object], token: str, output_name: str
) -> bpy.types.Object:
    """Join one material family of R2K staves into a Web-efficient mesh."""

    staves = [
        obj
        for obj in appended
        if object_is_alive(obj)
        and obj.type == "MESH"
        and obj.name.startswith("SM_BF3D_GL02_CST_")
        and token in obj.name
    ]
    if not staves:
        raise RuntimeError(f"no cooling staves found for {token}")
    bpy.ops.object.select_all(action="DESELECT")
    for obj in staves:
        obj.hide_set(False)
        obj.select_set(True)
    bpy.context.view_layer.objects.active = staves[0]
    bpy.ops.object.join()
    joined = bpy.context.view_layer.objects.active
    joined.name = output_name
    joined.data.name = f"{output_name}_MESH"
    try:
        bpy.ops.object.material_slot_remove_unused()
    except RuntimeError:
        pass
    joined["bf3d_asset"] = "GL02_STRUCTURAL_REVIEW_V1"
    joined["bf3d_structural_role"] = "cooling_stave"
    joined["bf3d_cooling_family"] = token.lower()
    joined["bf3d_source_object_count"] = len(staves)
    joined["bf3d_default_visible"] = False
    joined["bf3d_not_for_construction"] = True
    return joined


def prepare_base_metadata(base_objects: list[bpy.types.Object]) -> None:
    """Mark base meshes and preserve all historical names/contracts."""

    for obj in base_objects:
        obj["bf3d_asset"] = "GL02_STRUCTURAL_REVIEW_V1"
        obj["bf3d_source"] = "R2G_R2H_baked_R5_Web_base"
        obj.hide_set(False)
        obj.hide_viewport = False
        obj.hide_render = False
        if obj.name.startswith("APPROX_GL02_FURNACE_"):
            obj["bf3d_review_role"] = "r5_exterior_shell"
        elif obj.name.startswith("SENSOR_"):
            obj["bf3d_review_role"] = "sensor"


def export_glb(objects: list[bpy.types.Object]) -> None:
    """Export selected base and structural objects as one embedded binary glTF."""

    OUTPUT_GLB.parent.mkdir(parents=True, exist_ok=True)
    bpy.ops.object.select_all(action="DESELECT")
    exportable = [
        obj
        for obj in objects
        if object_is_alive(obj)
        and not is_legacy_review_artifact(obj.name)
    ]
    for obj in exportable:
        obj.hide_set(False)
        obj.hide_viewport = False
        obj.hide_render = False
        obj.select_set(True)
    if not exportable:
        raise RuntimeError("no exportable objects selected")

    operator_properties = {
        prop.identifier for prop in bpy.ops.export_scene.gltf.get_rna_type().properties
    }
    requested = {
        "filepath": str(OUTPUT_GLB),
        "export_format": "GLB",
        "use_selection": True,
        "export_extras": True,
        "export_cameras": False,
        "export_lights": False,
        "export_apply": True,
        "export_yup": True,
        "export_materials": "EXPORT",
        "export_image_format": "AUTO",
        "export_texcoords": True,
        "export_normals": True,
        "export_tangents": True,
        "export_attributes": False,
        "export_skins": False,
        "export_animations": False,
    }
    kwargs = {
        key: value for key, value in requested.items() if key in operator_properties
    }
    result = bpy.ops.export_scene.gltf(**kwargs)
    if "FINISHED" not in result or not OUTPUT_GLB.is_file():
        raise RuntimeError(f"glTF export failed: {result}")


def read_glb_json(path: Path) -> dict:
    """Read the JSON chunk from a GLB without requiring third-party packages."""

    with path.open("rb") as stream:
        magic, version, total_length = struct.unpack("<4sII", stream.read(12))
        if magic != b"glTF" or version != 2:
            raise RuntimeError("output is not a GLB v2 file")
        if total_length != path.stat().st_size:
            raise RuntimeError("GLB header length does not match file size")
        chunk_length, chunk_type = struct.unpack("<I4s", stream.read(8))
        if chunk_type != b"JSON":
            raise RuntimeError("GLB first chunk is not JSON")
        return json.loads(stream.read(chunk_length).decode("utf-8").rstrip(" \t\r\n\x00"))


def build_manifest(glb_json: dict) -> dict:
    """Build a controlled delivery manifest from the final binary."""

    node_names = [node.get("name", "") for node in glb_json.get("nodes", [])]
    mesh_names = [mesh.get("name", "") for mesh in glb_json.get("meshes", [])]
    material_names = [
        material.get("name", "") for material in glb_json.get("materials", [])
    ]
    role_counts = Counter()
    for node in glb_json.get("nodes", []):
        role = (node.get("extras") or {}).get("bf3d_structural_role")
        if role:
            role_counts[role] += 1

    sensor_count = sum(name.startswith("SENSOR_") for name in node_names)
    body_sensor_count = sum(
        name.startswith("SENSOR_T_body_") for name in node_names
    )
    zones = {
        zone: {
            "r5_exterior": f"APPROX_GL02_FURNACE_{zone}" in node_names,
            "r2j_entity": any(
                name.startswith(f"R2J_ASM_GL02_FURNACE_{zone}_SHELL_")
                for name in node_names
            ),
        }
        for zone in ZONES
    }
    checks = {
        "sensor_count_115": sensor_count == 115,
        "body_sensor_count_80": body_sensor_count == 80,
        "five_r5_exterior_zones": all(item["r5_exterior"] for item in zones.values()),
        "five_r2j_entities": all(item["r2j_entity"] for item in zones.values()),
        "r2k_backfill_present": role_counts["backfill"] == 1,
        "r2k_hotface_present": role_counts["hotface_embed"] == 1,
        "r2k_refractory_present": role_counts["refractory"] == 1,
        "r2k_cooling_families_merged": all(
            name in node_names
            for name in (
                "R2K_WEB_L03_COOLING_COPPER_COMBINED",
                "R2K_WEB_L03_COOLING_CASTIRON_COMBINED",
            )
        ),
        "legacy_review_artifacts_removed": not any(
            is_legacy_review_artifact(name) for name in node_names
        ),
        "formal_glb_unchanged": sha256(FORMAL_GLB) == EXPECTED_FORMAL_SHA256,
    }
    return {
        "schema_version": "bf3d.web.structural_review_asset.v1",
        "requirement_id": "REQ-BF3D-STRUCTURAL-REVIEW-20260719",
        "asset_id": "GL02_STRUCTURAL_REVIEW_V1",
        "status": "controlled_local_web_asset",
        "evidence": "illustrative",
        "not_for_construction": True,
        "output": {
            "path": rel(OUTPUT_GLB),
            "bytes": OUTPUT_GLB.stat().st_size,
            "sha256": sha256(OUTPUT_GLB),
        },
        "provenance": {
            "r5_web_base": {
                "path": rel(BASE_GLB),
                "sha256": sha256(BASE_GLB),
                "decision": "R5 baked PBR from approved isolated R2G/R2H Web candidate",
            },
            "r2j_r2k_blend": {
                "path": rel(R2K_BLEND),
                "sha256": sha256(R2K_BLEND),
                "decision": "R2K inherits R2J five-zone closed shell entities",
            },
        },
        "rollback": {
            "formal_glb": rel(FORMAL_GLB),
            "formal_glb_sha256": sha256(FORMAL_GLB),
            "formal_file_overwritten": False,
        },
        "counts": {
            "nodes": len(glb_json.get("nodes", [])),
            "meshes": len(glb_json.get("meshes", [])),
            "materials": len(glb_json.get("materials", [])),
            "textures": len(glb_json.get("textures", [])),
            "images": len(glb_json.get("images", [])),
            "sensors": sensor_count,
            "body_temperature_sensors": body_sensor_count,
            "structural_roles": dict(sorted(role_counts.items())),
        },
        "zones": zones,
        "materials": material_names,
        "mesh_names": mesh_names,
        "checks": checks,
        "all_checks_pass": all(checks.values()),
    }


def main() -> None:
    """Build the asset and fail closed when any protected contract drifts."""

    STAGE.mkdir(parents=True, exist_ok=True)
    check_locked_input(BASE_GLB, EXPECTED_BASE_SHA256, "R5 Web base")
    check_locked_input(R2K_BLEND, EXPECTED_R2K_SHA256, "R2K candidate")
    check_locked_input(FORMAL_GLB, EXPECTED_FORMAL_SHA256, "formal rollback GLB")

    reset_scene()
    base_objects = import_r5_web_base()
    prepare_base_metadata(base_objects)
    appended = append_structural_objects()
    bind_r5_to_r2j_shell_entities(appended)
    mark_structural_metadata(appended)

    copper = join_stave_family(
        appended, "COPPER", "R2K_WEB_L03_COOLING_COPPER_COMBINED"
    )
    castiron = join_stave_family(
        appended, "CASTIRON", "R2K_WEB_L03_COOLING_CASTIRON_COMBINED"
    )
    appended = [
        obj
        for obj in appended
        if object_is_alive(obj)
        and not obj.name.startswith("SM_BF3D_GL02_CST_")
    ]
    appended.extend([copper, castiron])

    export_glb(base_objects + appended)
    manifest = build_manifest(read_glb_json(OUTPUT_GLB))
    if not manifest["all_checks_pass"]:
        raise RuntimeError(
            "structural-review GLB contract failed: "
            + json.dumps(manifest["checks"], ensure_ascii=False)
        )
    text = json.dumps(manifest, ensure_ascii=False, indent=2) + "\n"
    OUTPUT_MANIFEST.write_text(text, encoding="utf-8")
    STAGE_MANIFEST.write_text(text, encoding="utf-8")
    print("BF3D_STRUCTURAL_REVIEW_MANIFEST=" + json.dumps(manifest, ensure_ascii=False))


if __name__ == "__main__":
    main()
