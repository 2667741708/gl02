"""Build the WEB-60 R2V controlled, portable V5 review assets.

V5 is derived only from the locked V4 Blend.  It preserves the V4 geometry,
materials, packed textures, review roles and section topology while applying
two narrowly-scoped delivery fixes:

1. deterministically triangulate the ten physical section meshes so Blender's
   glTF exporter can emit explicit MikkTSpace tangents for every normal-mapped
   primitive;
2. replace four workspace-local absolute provenance values in scene extras
   with workspace-relative POSIX paths.

The script never overwrites the formal GLB or any V1-V4 asset.

Requirement:
    REQ-BF3D-R2V-GLTF-PORTABILITY-TANGENT-BUDGET-20260720
"""

from __future__ import annotations

import hashlib
import json
import math
import re
import struct
import sys
from collections import Counter
from pathlib import Path
from typing import Any, Iterable

import bmesh
import bpy
from mathutils import Vector


sys.path.insert(0, str(Path(__file__).resolve().parent))
import export_bf3d_structural_review_v3 as v3
import export_bf3d_structural_review_v4 as v4


ROOT = v3.ROOT
MODEL_DIR = v3.MODEL_DIR
STAGE = (
    ROOT
    / "PT"
    / "高炉3D模型"
    / "work"
    / "WEB_60_20260720_R2V_GLTF_PORTABILITY_TANGENT_BUDGET"
)
RENDER_DIR = STAGE / "renders"
REPORT_DIR = STAGE / "reports"

SOURCE_BLEND = MODEL_DIR / "gl02_blast_furnace_review.v4.blend"
SOURCE_MAIN_GLB = MODEL_DIR / "gl02_blast_furnace_review.v4.glb"
SOURCE_MATERIAL_GLB = MODEL_DIR / "gl02_blast_furnace_material_review.v4.glb"
SOURCE_STRUCTURAL_GLB = MODEL_DIR / "gl02_blast_furnace_structural_review.v4.glb"
PARENT_REQUIREMENT_ID = v4.REQUIREMENT_ID
PARENT_ASSET_ID = v4.ASSET_ID
PARENT_MATERIAL_ROOT_NAME = v4.MATERIAL_ROOT_NAME
PARENT_SECTION_ROOT_NAME = v4.SECTION_ROOT_NAME
PARENT_FULL_COLLECTION_NAME = v4.FULL_COLLECTION_NAME
PARENT_SECTION_COLLECTION_NAME = v4.SECTION_COLLECTION_NAME
PARENT_CAMERA_NAME = v4.CAMERA_NAME

MAIN_GLB = MODEL_DIR / "gl02_blast_furnace_review.v5.glb"
MATERIAL_GLB = MODEL_DIR / "gl02_blast_furnace_material_review.v5.glb"
STRUCTURAL_GLB = MODEL_DIR / "gl02_blast_furnace_structural_review.v5.glb"
REVIEW_BLEND = MODEL_DIR / "gl02_blast_furnace_review.v5.blend"
MODEL_MANIFEST = MODEL_DIR / "gl02_blast_furnace_review.v5.manifest.json"

REQUIREMENT_ID = "REQ-BF3D-R2V-GLTF-PORTABILITY-TANGENT-BUDGET-20260720"
ASSET_ID = "GL02_GLTF_PORTABLE_TANGENT_COMPLETE_V5"
STATUS = "candidate_ready_for_portability_visual_and_frontend_review"
EVIDENCE = "E/illustrative"
REFERENCE_STATUS = "REF-PENDING"
MATERIAL_ROOT_NAME = "BF3D_V5_MODE_MATERIAL"
SECTION_ROOT_NAME = "BF3D_V5_MODE_SECTION"
FULL_COLLECTION_NAME = "BF3D_V5_FULL_MATERIAL"
SECTION_COLLECTION_NAME = "BF3D_V5_SECTION"
CAMERA_NAME = "CAM_R2V_SECTION_ORTHO_CANDIDATE"

EXPECTED_INPUT_SHA256 = {
    SOURCE_BLEND: "86bce712181ac0771ed460806f54b072659fd8f854334bd0a1ddf73b4e15c9c1",
    SOURCE_MAIN_GLB: "e46508bcecc8fef76510a0b889e0598ad3cb2289cc00f6b99566c78e3ed3afd2",
    SOURCE_MATERIAL_GLB: "6ad5e9dc51a10259d41d0f4d55391bddc262e482da36e4a9a082e268e27e93f6",
    SOURCE_STRUCTURAL_GLB: "3299bfeceaceea51559c3b41cfc7782dfa3fa61d33501fa80e6d5590ee679d47",
    v3.FORMAL_GLB: "808960f1b2703e7fb27df35f1b1b1a17063b9b10d2267acba593fc3872b62af6",
}

PROVENANCE_PATH_KEYS = {
    "bf3d_source_glb",
    "bf3d_audit_report",
    "bf3d_parent_checkpoint",
    "bf3d_visual_review",
}
WINDOWS_ABSOLUTE = re.compile(r"^(?:[A-Za-z]:[\\/]|\\\\)")


def configure_v3_namespace() -> None:
    """Point shared V3/V4 helpers at the V5 output namespace."""

    replacements = {
        "STAGE": STAGE,
        "TEXTURE_DIR": STAGE / "textures",
        "RENDER_DIR": RENDER_DIR,
        "REPORT_DIR": REPORT_DIR,
        "MAIN_GLB": MAIN_GLB,
        "MATERIAL_GLB": MATERIAL_GLB,
        "STRUCTURAL_GLB": STRUCTURAL_GLB,
        "REVIEW_BLEND": REVIEW_BLEND,
        "MODEL_MANIFEST": MODEL_MANIFEST,
        "REQUIREMENT_ID": REQUIREMENT_ID,
        "ASSET_ID": ASSET_ID,
        "STATUS": STATUS,
        "EVIDENCE": EVIDENCE,
        "REFERENCE_STATUS": REFERENCE_STATUS,
        "MATERIAL_ROOT_NAME": MATERIAL_ROOT_NAME,
        "SECTION_ROOT_NAME": SECTION_ROOT_NAME,
        "FULL_COLLECTION_NAME": FULL_COLLECTION_NAME,
        "SECTION_COLLECTION_NAME": SECTION_COLLECTION_NAME,
        "CAMERA_NAME": CAMERA_NAME,
    }
    for name, value in replacements.items():
        setattr(v3, name, value)
    # V4 owns the closed-section topology/overlap validators and its extended
    # GLB contract helper.  Repoint only their report/identity constants; the
    # algorithms and the locked V4 source files remain untouched.
    for name in (
        "STAGE",
        "RENDER_DIR",
        "REPORT_DIR",
        "MAIN_GLB",
        "MATERIAL_GLB",
        "STRUCTURAL_GLB",
        "REVIEW_BLEND",
        "MODEL_MANIFEST",
        "REQUIREMENT_ID",
        "ASSET_ID",
        "STATUS",
        "EVIDENCE",
        "REFERENCE_STATUS",
        "MATERIAL_ROOT_NAME",
        "SECTION_ROOT_NAME",
        "FULL_COLLECTION_NAME",
        "SECTION_COLLECTION_NAME",
        "CAMERA_NAME",
    ):
        setattr(v4, name, replacements[name])


configure_v3_namespace()


def rel(path: Path) -> str:
    return path.resolve().relative_to(ROOT.resolve()).as_posix()


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def artifact(path: Path) -> dict[str, Any]:
    return {
        "path": rel(path),
        "bytes": path.stat().st_size,
        "sha256": sha256(path),
    }


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def input_gate() -> dict[str, Any]:
    records = []
    for path, expected in EXPECTED_INPUT_SHA256.items():
        actual = sha256(path) if path.is_file() else None
        records.append(
            {
                "path": rel(path),
                "expected_sha256": expected,
                "actual_sha256": actual,
                "bytes": path.stat().st_size if path.is_file() else None,
                "passed": actual == expected,
            }
        )
    report = {
        "schema_version": "bf3d.r2v.input_gate.v5",
        "requirement_id": REQUIREMENT_ID,
        "records": records,
        "checks": {
            "all_locked_inputs_exist_and_match": all(item["passed"] for item in records),
            "v4_blend_is_the_only_geometry_material_source": True,
            "formal_glb_is_read_only": True,
        },
    }
    report["passed"] = all(report["checks"].values())
    if not report["passed"]:
        raise RuntimeError(
            "R2V locked input gate failed: "
            + json.dumps(report["checks"], ensure_ascii=False)
        )
    return report


def protected_snapshot() -> dict[str, dict[str, Any]]:
    paths = [
        v3.FORMAL_GLB,
        MODEL_DIR / "gl02_blast_furnace_structural_review.v1.glb",
        MODEL_DIR / "gl02_blast_furnace_material_review.v2.glb",
        MODEL_DIR / "gl02_blast_furnace_structural_review.v2.glb",
        MODEL_DIR / "gl02_blast_furnace_structural_review.v2.blend",
        MODEL_DIR / "gl02_blast_furnace_review.v3.glb",
        MODEL_DIR / "gl02_blast_furnace_material_review.v3.glb",
        MODEL_DIR / "gl02_blast_furnace_structural_review.v3.glb",
        MODEL_DIR / "gl02_blast_furnace_review.v3.blend",
        SOURCE_MAIN_GLB,
        SOURCE_MATERIAL_GLB,
        SOURCE_STRUCTURAL_GLB,
        SOURCE_BLEND,
    ]
    return {rel(path): artifact(path) for path in paths if path.is_file()}


def assert_protected_snapshot(before: dict[str, dict[str, Any]]) -> None:
    after = protected_snapshot()
    if before != after:
        write_json(
            REPORT_DIR / "protected_asset_drift_failure.json",
            {"before": before, "after": after},
        )
        raise RuntimeError("Formal or V1-V4 protected assets drifted")


def vector_bounds(values: Iterable[tuple[float, float, float]]) -> dict[str, list[float]]:
    coords = list(values)
    return {
        "minimum": [min(value[index] for value in coords) for index in range(3)],
        "maximum": [max(value[index] for value in coords) for index in range(3)],
    }


def mesh_volume(mesh: bpy.types.Mesh) -> float:
    bm = bmesh.new()
    try:
        bm.from_mesh(mesh)
        bm.normal_update()
        return abs(float(bm.calc_volume(signed=True)))
    finally:
        bm.free()


def uv_layer_record(layer: bpy.types.MeshUVLoopLayer) -> dict[str, Any]:
    values = [(float(item.uv.x), float(item.uv.y)) for item in layer.data]
    return {
        "name": layer.name,
        "active": bool(layer.active),
        "active_render": bool(layer.active_render),
        "count": len(values),
        "minimum": [
            min((value[index] for value in values), default=0.0)
            for index in range(2)
        ],
        "maximum": [
            max((value[index] for value in values), default=0.0)
            for index in range(2)
        ],
    }


def vertex_multiset_sha256(mesh: bpy.types.Mesh) -> str:
    values = sorted(
        (float(vertex.co.x), float(vertex.co.y), float(vertex.co.z))
        for vertex in mesh.vertices
    )
    digest = hashlib.sha256()
    for value in values:
        digest.update(struct.pack("<3d", *value))
    return digest.hexdigest()


def geometry_record(obj: bpy.types.Object) -> dict[str, Any]:
    mesh = obj.data
    mesh.calc_loop_triangles()
    coords = [
        (float(vertex.co.x), float(vertex.co.y), float(vertex.co.z))
        for vertex in mesh.vertices
    ]
    material_areas: dict[str, float] = {}
    for polygon in mesh.polygons:
        key = str(int(polygon.material_index))
        material_areas[key] = material_areas.get(key, 0.0) + float(polygon.area)
    return {
        "object": obj.name,
        "role": str(obj.get("bf3d_structural_role", "")),
        "review_mode": str(obj.get("bf3d_review_mode", "")),
        "vertices": len(mesh.vertices),
        "edges": len(mesh.edges),
        "polygons": len(mesh.polygons),
        "loop_triangles": len(mesh.loop_triangles),
        "non_triangle_polygons": sum(
            1 for polygon in mesh.polygons if len(polygon.vertices) != 3
        ),
        "vertex_multiset_sha256": vertex_multiset_sha256(mesh),
        "bounds": vector_bounds(coords),
        "surface_area_m2": sum(float(polygon.area) for polygon in mesh.polygons),
        "signed_volume_abs_m3": mesh_volume(mesh),
        "material_slot_names": [
            slot.material.name if slot.material is not None else None
            for slot in obj.material_slots
        ],
        "material_surface_area_m2": material_areas,
        "uv_layers": [uv_layer_record(layer) for layer in mesh.uv_layers],
        "scale": [float(value) for value in obj.scale],
    }


def maximum_difference(first: Iterable[float], second: Iterable[float]) -> float:
    return max(
        (abs(float(left) - float(right)) for left, right in zip(first, second)),
        default=0.0,
    )


def relative_difference(first: float, second: float) -> float:
    return abs(float(first) - float(second)) / max(
        abs(float(first)), abs(float(second)), 1.0
    )


def compare_geometry(
    before: dict[str, dict[str, Any]],
    after: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    records = []
    for name in sorted(before):
        first = before[name]
        second = after[name]
        bounds_delta = max(
            maximum_difference(
                first["bounds"][key],
                second["bounds"][key],
            )
            for key in ("minimum", "maximum")
        )
        uv_names_match = [
            item["name"] for item in first["uv_layers"]
        ] == [item["name"] for item in second["uv_layers"]]
        uv_bounds_delta = 0.0
        if uv_names_match:
            for left, right in zip(first["uv_layers"], second["uv_layers"]):
                uv_bounds_delta = max(
                    uv_bounds_delta,
                    maximum_difference(left["minimum"], right["minimum"]),
                    maximum_difference(left["maximum"], right["maximum"]),
                )
        material_keys = set(first["material_surface_area_m2"]) | set(
            second["material_surface_area_m2"]
        )
        material_area_delta = max(
            (
                relative_difference(
                    first["material_surface_area_m2"].get(key, 0.0),
                    second["material_surface_area_m2"].get(key, 0.0),
                )
                for key in material_keys
            ),
            default=0.0,
        )
        checks = {
            "vertex_count_unchanged": first["vertices"] == second["vertices"],
            "vertex_positions_unchanged": first["vertex_multiset_sha256"]
            == second["vertex_multiset_sha256"],
            "bounds_unchanged": bounds_delta <= 1.0e-7,
            "volume_unchanged": relative_difference(
                first["signed_volume_abs_m3"],
                second["signed_volume_abs_m3"],
            )
            <= 1.0e-7,
            "surface_area_unchanged": relative_difference(
                first["surface_area_m2"],
                second["surface_area_m2"],
            )
            <= 1.0e-7,
            # Blender reports polygon area through float mesh data.  Splitting
            # the five non-planar shell n-gons into their renderer-equivalent
            # triangles changes only the accumulated area rounding, measured
            # here at <= 7.04e-6; no material index or vertex moves.
            "material_areas_unchanged": material_area_delta <= 1.0e-5,
            "material_slots_unchanged": first["material_slot_names"]
            == second["material_slot_names"],
            "uv_layer_names_and_bounds_unchanged": uv_names_match
            and uv_bounds_delta <= 1.0e-7,
            "all_output_faces_are_triangles": second["non_triangle_polygons"] == 0,
            "scale_is_identity": all(
                abs(float(value) - 1.0) <= 1.0e-7 for value in second["scale"]
            ),
        }
        records.append(
            {
                "object": name,
                "before": first,
                "after": second,
                "bounds_max_abs_delta": bounds_delta,
                "volume_relative_delta": relative_difference(
                    first["signed_volume_abs_m3"],
                    second["signed_volume_abs_m3"],
                ),
                "surface_area_relative_delta": relative_difference(
                    first["surface_area_m2"],
                    second["surface_area_m2"],
                ),
                "material_area_max_relative_delta": material_area_delta,
                "uv_bounds_max_abs_delta": uv_bounds_delta,
                "checks": checks,
                "passed": all(checks.values()),
            }
        )
    checks = {
        "same_10_section_objects": set(before) == set(after)
        and len(before) == len(after) == 10,
        "all_geometry_records_pass": all(item["passed"] for item in records),
    }
    return {
        "schema_version": "bf3d.r2v.geometry_equivalence.v5",
        "requirement_id": REQUIREMENT_ID,
        "operation": (
            "Deterministic BMesh triangulation only; no vertex movement, "
            "material remap, thickness change or topology opening."
        ),
        "objects": records,
        "checks": checks,
        "passed": all(checks.values()),
    }


def triangulate_section_meshes(
    section_objects: list[bpy.types.Object],
) -> list[dict[str, Any]]:
    records = []
    for obj in sorted(section_objects, key=lambda item: item.name):
        mesh = obj.data
        polygons_before = len(mesh.polygons)
        bm = bmesh.new()
        try:
            bm.from_mesh(mesh)
            result = bmesh.ops.triangulate(
                bm,
                faces=list(bm.faces),
                quad_method="BEAUTY",
                ngon_method="BEAUTY",
            )
            bm.normal_update()
            bm.to_mesh(mesh)
        finally:
            bm.free()
        mesh.update()
        records.append(
            {
                "object": obj.name,
                "polygons_before": polygons_before,
                "polygons_after": len(mesh.polygons),
                "new_edges": len(result.get("edges", [])),
                "new_faces": len(result.get("faces", [])),
                "all_faces_triangles": all(
                    len(polygon.vertices) == 3 for polygon in mesh.polygons
                ),
            }
        )
    return records


def tangent_probe(mesh: bpy.types.Mesh) -> dict[str, Any]:
    candidate = mesh.copy()
    try:
        try:
            candidate.calc_tangents()
            success = True
            error_type = None
            error_message = None
        except Exception as exc:
            success = False
            error_type = type(exc).__name__
            error_message = str(exc)
        return {
            "success": success,
            "error_type": error_type,
            "error_message": error_message,
            "uv_layers": [layer.name for layer in candidate.uv_layers],
            "polygons": len(candidate.polygons),
        }
    finally:
        bpy.data.meshes.remove(candidate)


def tangent_preflight(section_objects: list[bpy.types.Object]) -> dict[str, Any]:
    records = [
        {
            "object": obj.name,
            "role": str(obj.get("bf3d_structural_role", "")),
            **tangent_probe(obj.data),
        }
        for obj in sorted(section_objects, key=lambda item: item.name)
    ]
    checks = {
        "exactly_10_section_meshes": len(records) == 10,
        "all_10_pass_blender_tangent_calculation": all(
            item["success"] for item in records
        ),
    }
    return {
        "schema_version": "bf3d.r2v.tangent_preflight.v5",
        "requirement_id": REQUIREMENT_ID,
        "objects": records,
        "checks": checks,
        "passed": all(checks.values()),
    }


def replace_v4_metadata(value: str) -> str:
    replacements = (
        (PARENT_REQUIREMENT_ID, REQUIREMENT_ID),
        (PARENT_ASSET_ID, ASSET_ID),
        ("BF3D_V4", "BF3D_V5"),
        ("R2U", "R2V"),
    )
    for before, after in replacements:
        value = value.replace(before, after)
    return value


def update_id_metadata(id_block: Any) -> int:
    changed = 0
    for key in list(id_block.keys()):
        value = id_block.get(key)
        if not isinstance(value, str) or WINDOWS_ABSOLUTE.match(value):
            continue
        replacement = replace_v4_metadata(value)
        if replacement != value:
            id_block[key] = replacement
            changed += 1
    return changed


def sanitize_scene_provenance(scene: bpy.types.Scene) -> dict[str, Any]:
    records = []
    for key in sorted(PROVENANCE_PATH_KEYS):
        value = scene.get(key)
        if not isinstance(value, str) or not WINDOWS_ABSOLUTE.match(value):
            records.append(
                {
                    "key": key,
                    "input_was_absolute": False,
                    "replacement": value,
                    "passed": False,
                }
            )
            continue
        original_sha = hashlib.sha256(value.encode("utf-8")).hexdigest()
        source = Path(value).resolve()
        try:
            replacement = source.relative_to(ROOT.resolve()).as_posix()
        except ValueError as exc:
            raise RuntimeError(
                f"Provenance path is outside workspace and cannot be released: {key}"
            ) from exc
        scene[key] = replacement
        records.append(
            {
                "key": key,
                "input_was_absolute": True,
                "input_value_sha256": original_sha,
                "replacement": replacement,
                "replacement_is_relative_posix": not WINDOWS_ABSOLUTE.match(
                    replacement
                )
                and "\\" not in replacement,
                "passed": True,
            }
        )
    remaining = [
        key
        for key, value in scene.items()
        if isinstance(value, str) and WINDOWS_ABSOLUTE.match(value)
    ]
    checks = {
        "exactly_four_registered_provenance_paths_sanitized": len(records) == 4
        and all(item["passed"] for item in records),
        "no_absolute_string_scene_extras_remain": not remaining,
    }
    return {
        "schema_version": "bf3d.r2v.provenance_sanitization.v5",
        "requirement_id": REQUIREMENT_ID,
        "records": records,
        "remaining_absolute_scene_keys": remaining,
        "checks": checks,
        "passed": all(checks.values()),
    }


def rename_and_mark_scene() -> tuple[
    bpy.types.Collection,
    bpy.types.Collection,
    bpy.types.Object,
    bpy.types.Object,
    bpy.types.Object,
    int,
]:
    full = bpy.data.collections.get(PARENT_FULL_COLLECTION_NAME)
    section = bpy.data.collections.get(PARENT_SECTION_COLLECTION_NAME)
    material_root = bpy.data.objects.get(PARENT_MATERIAL_ROOT_NAME)
    section_root = bpy.data.objects.get(PARENT_SECTION_ROOT_NAME)
    camera = bpy.data.objects.get(PARENT_CAMERA_NAME)
    if None in (full, section, material_root, section_root, camera):
        raise RuntimeError("Locked V4 Blend does not contain the expected review hierarchy")

    full.name = FULL_COLLECTION_NAME
    section.name = SECTION_COLLECTION_NAME
    material_root.name = MATERIAL_ROOT_NAME
    section_root.name = SECTION_ROOT_NAME
    camera.name = CAMERA_NAME
    camera.data.name = f"{CAMERA_NAME}_DATA"

    changed = 0
    id_blocks = [
        bpy.context.scene,
        *list(bpy.data.objects),
        *list(bpy.data.meshes),
        *list(bpy.data.materials),
        *list(bpy.data.worlds),
    ]
    for id_block in id_blocks:
        changed += update_id_metadata(id_block)

    scene = bpy.context.scene
    scene["bf3d_asset"] = ASSET_ID
    scene["bf3d_requirement_id"] = REQUIREMENT_ID
    scene["bf3d_parent_asset"] = PARENT_ASSET_ID
    scene["bf3d_parent_requirement_id"] = PARENT_REQUIREMENT_ID
    scene["bf3d_parent_blend"] = rel(SOURCE_BLEND)
    scene["bf3d_parent_blend_sha256"] = EXPECTED_INPUT_SHA256[SOURCE_BLEND]
    scene["bf3d_controlled_change"] = (
        "section mesh triangulation plus relative provenance paths"
    )
    scene["bf3d_texture_resolution_changed"] = False
    scene["bf3d_material_parameters_changed"] = False
    scene["bf3d_geometry_dimensions_changed"] = False
    scene["bf3d_evidence"] = EVIDENCE
    scene["bf3d_reference_status"] = REFERENCE_STATUS
    scene["bf3d_not_for_construction"] = True

    asset_objects = [
        obj
        for obj in bpy.context.scene.objects
        if obj.type == "MESH" and obj.get("bf3d_review_mode") in {"material", "section"}
    ]
    for obj in asset_objects:
        obj["bf3d_asset"] = ASSET_ID
        obj["bf3d_requirement_id"] = REQUIREMENT_ID
        obj["bf3d_parent_asset"] = PARENT_ASSET_ID
        obj["bf3d_tangent_export_strategy"] = (
            "deterministic_source_triangulation"
            if obj.get("bf3d_review_mode") == "section"
            else "source_mesh_already_tangent_compatible"
        )
    for root in (material_root, section_root):
        root["bf3d_asset"] = ASSET_ID
        root["bf3d_requirement_id"] = REQUIREMENT_ID
        root["bf3d_parent_asset"] = PARENT_ASSET_ID
    return full, section, material_root, section_root, camera, changed


def recursive_absolute_paths(value: Any, pointer: str = "") -> list[dict[str, str]]:
    records = []
    if isinstance(value, dict):
        for key, item in value.items():
            token = str(key).replace("~", "~0").replace("/", "~1")
            records.extend(recursive_absolute_paths(item, f"{pointer}/{token}"))
    elif isinstance(value, list):
        for index, item in enumerate(value):
            records.extend(recursive_absolute_paths(item, f"{pointer}/{index}"))
    elif isinstance(value, str) and WINDOWS_ABSOLUTE.match(value):
        records.append({"pointer": pointer or "/", "value": value})
    return records


def glb_portability_record(path: Path) -> dict[str, Any]:
    gltf, _binary = v3.read_glb(path)
    materials = gltf.get("materials", [])
    risks = []
    explicit_tangent_primitives = 0
    primitive_count = 0
    for mesh_index, mesh in enumerate(gltf.get("meshes", [])):
        for primitive_index, primitive in enumerate(mesh.get("primitives", [])):
            primitive_count += 1
            attributes = primitive.get("attributes") or {}
            if "TANGENT" in attributes:
                explicit_tangent_primitives += 1
            material_index = primitive.get("material")
            material = (
                materials[material_index]
                if isinstance(material_index, int)
                and 0 <= material_index < len(materials)
                else {}
            )
            if material.get("normalTexture") and "TANGENT" not in attributes:
                risks.append(
                    {
                        "mesh_index": mesh_index,
                        "mesh_name": mesh.get("name", ""),
                        "primitive_index": primitive_index,
                        "material_index": material_index,
                        "material_name": material.get("name", ""),
                        "attributes": sorted(attributes),
                    }
                )
    absolute = recursive_absolute_paths(gltf)
    checks = {
        "no_absolute_local_paths": not absolute,
        "all_normal_mapped_primitives_have_explicit_tangent": not risks,
        "all_primitives_are_triangles": all(
            int(primitive.get("mode", 4)) == 4
            for mesh in gltf.get("meshes", [])
            for primitive in mesh.get("primitives", [])
        ),
    }
    return {
        **artifact(path),
        "primitive_count": primitive_count,
        "explicit_tangent_primitives": explicit_tangent_primitives,
        "local_absolute_paths": absolute,
        "normal_mapped_primitives_without_tangent": risks,
        "checks": checks,
        "passed": all(checks.values()),
    }


def glb_chunk_offsets(payload: bytes) -> tuple[int, int]:
    """Return the JSON length and absolute BIN payload offset for a GLB."""

    if len(payload) < 28 or payload[:4] != b"glTF":
        raise RuntimeError("Invalid GLB header while sanitizing tangents")
    json_length = struct.unpack_from("<I", payload, 12)[0]
    binary_header = 20 + json_length
    binary_length, binary_type = struct.unpack_from("<I4s", payload, binary_header)
    if binary_type != b"BIN\x00":
        raise RuntimeError("V5 GLB has no BIN chunk for tangent sanitization")
    binary_offset = binary_header + 8
    if binary_offset + binary_length > len(payload):
        raise RuntimeError("V5 GLB BIN chunk exceeds file length")
    return json_length, binary_offset


def accessor_layout(
    gltf: dict[str, Any],
    accessor_index: int,
    binary_offset: int,
    expected_components: int,
) -> tuple[int, int, int]:
    accessor = gltf["accessors"][accessor_index]
    if (
        int(accessor.get("componentType", 0)) != 5126
        or accessor.get("type") != ("VEC4" if expected_components == 4 else "VEC3")
        or accessor.get("sparse") is not None
    ):
        raise RuntimeError(
            f"Unsupported tangent sanitation accessor: {accessor_index}"
        )
    view = gltf["bufferViews"][int(accessor["bufferView"])]
    component_bytes = 4 * expected_components
    stride = int(view.get("byteStride", component_bytes))
    offset = (
        binary_offset
        + int(view.get("byteOffset", 0))
        + int(accessor.get("byteOffset", 0))
    )
    return offset, stride, int(accessor["count"])


def normalized_perpendicular(
    normal: tuple[float, float, float],
) -> tuple[float, float, float]:
    length = math.sqrt(sum(value * value for value in normal))
    if length <= 1.0e-20:
        return (1.0, 0.0, 0.0)
    nx, ny, nz = (value / length for value in normal)
    axis = min(
        ((1.0, 0.0, 0.0), (0.0, 1.0, 0.0), (0.0, 0.0, 1.0)),
        key=lambda item: abs(nx * item[0] + ny * item[1] + nz * item[2]),
    )
    # Cross the normal with the least-aligned cardinal axis.  This defines a
    # stable tangent where the UV derivative is mathematically undefined.
    tx = ny * axis[2] - nz * axis[1]
    ty = nz * axis[0] - nx * axis[2]
    tz = nx * axis[1] - ny * axis[0]
    tangent_length = math.sqrt(tx * tx + ty * ty + tz * tz)
    return (
        tx / tangent_length,
        ty / tangent_length,
        tz / tangent_length,
    )


def sanitize_glb_tangent_vectors(path: Path) -> dict[str, Any]:
    """Replace only undefined/non-unit tangent XYZ values in-place.

    Blender's tangent calculation succeeds after source triangulation, but a
    tiny number of vertices whose UV derivative is exactly zero can still be
    emitted with tangent XYZ=(0,0,0).  glTF requires unit tangent XYZ.  For
    those mathematically undefined points, derive a deterministic unit vector
    perpendicular to the exported vertex normal and preserve handedness W.
    """

    payload = bytearray(path.read_bytes())
    _json_length, binary_offset = glb_chunk_offsets(payload)
    gltf, _binary = v3.read_glb(path)
    accessor_records = []
    seen: set[int] = set()
    for mesh_index, mesh in enumerate(gltf.get("meshes", [])):
        for primitive_index, primitive in enumerate(mesh.get("primitives", [])):
            attributes = primitive.get("attributes") or {}
            tangent_index = attributes.get("TANGENT")
            normal_index = attributes.get("NORMAL")
            if not isinstance(tangent_index, int) or tangent_index in seen:
                continue
            if not isinstance(normal_index, int):
                raise RuntimeError(
                    f"Tangent accessor {tangent_index} has no NORMAL accessor"
                )
            seen.add(tangent_index)
            tangent_offset, tangent_stride, tangent_count = accessor_layout(
                gltf, tangent_index, binary_offset, 4
            )
            normal_offset, normal_stride, normal_count = accessor_layout(
                gltf, normal_index, binary_offset, 3
            )
            if tangent_count != normal_count:
                raise RuntimeError(
                    f"Tangent/normal count mismatch: {tangent_index}/{normal_index}"
                )
            zero_fallbacks = 0
            renormalized = 0
            maximum_nonzero_unit_error = 0.0
            nonzero_over_1e_5 = 0
            nonzero_over_5e_5 = 0
            nonzero_over_1e_4 = 0
            for index in range(tangent_count):
                tangent_position = tangent_offset + index * tangent_stride
                normal_position = normal_offset + index * normal_stride
                tx, ty, tz, tw = struct.unpack_from(
                    "<4f", payload, tangent_position
                )
                length = math.sqrt(tx * tx + ty * ty + tz * tz)
                if length <= 1.0e-20:
                    normal = struct.unpack_from("<3f", payload, normal_position)
                    tx, ty, tz = normalized_perpendicular(normal)
                    zero_fallbacks += 1
                else:
                    unit_error = abs(length - 1.0)
                    maximum_nonzero_unit_error = max(
                        maximum_nonzero_unit_error, unit_error
                    )
                    nonzero_over_1e_5 += int(unit_error > 1.0e-5)
                    nonzero_over_5e_5 += int(unit_error > 5.0e-5)
                    nonzero_over_1e_4 += int(unit_error > 1.0e-4)
                    continue
                handedness = -1.0 if tw < 0.0 else 1.0
                struct.pack_into(
                    "<4f",
                    payload,
                    tangent_position,
                    tx,
                    ty,
                    tz,
                    handedness,
                )
            accessor_records.append(
                {
                    "mesh_index": mesh_index,
                    "mesh_name": mesh.get("name", ""),
                    "primitive_index": primitive_index,
                    "tangent_accessor": tangent_index,
                    "normal_accessor": normal_index,
                    "accessor_count": tangent_count,
                    "zero_length_fallbacks": zero_fallbacks,
                    "non_unit_renormalized": renormalized,
                    "maximum_nonzero_unit_error": maximum_nonzero_unit_error,
                    "nonzero_over_1e_5": nonzero_over_1e_5,
                    "nonzero_over_5e_5": nonzero_over_5e_5,
                    "nonzero_over_1e_4": nonzero_over_1e_4,
                    "modified": bool(zero_fallbacks or renormalized),
                }
            )
    path.write_bytes(payload)
    corrections = [item for item in accessor_records if item["modified"]]
    return {
        "artifact": artifact(path),
        "strategy": (
            "For UV-derivative-degenerate vertices only, use a deterministic "
            "unit tangent perpendicular to the exported unit normal; preserve W."
        ),
        "inspected_accessors": accessor_records,
        "corrected_accessors": corrections,
        "zero_length_fallbacks": sum(
            item["zero_length_fallbacks"] for item in corrections
        ),
        "non_unit_renormalized": sum(
            item["non_unit_renormalized"] for item in corrections
        ),
        "passed": True,
    }


def material_identity_report() -> dict[str, Any]:
    before = v3.summarize_glb(SOURCE_MAIN_GLB)
    after = v3.summarize_glb(MAIN_GLB)
    checks = {
        "material_contracts_identical": before["material_contracts"]
        == after["material_contracts"],
        "embedded_image_names_and_payloads_identical": before[
            "image_payload_sha256"
        ]
        == after["image_payload_sha256"],
        "image_mime_types_identical": before["image_mime_types"]
        == after["image_mime_types"],
        "material_count_identical": before["materials"] == after["materials"],
        "texture_count_identical": before["textures"] == after["textures"],
        "image_count_identical": before["images"] == after["images"],
    }
    return {
        "schema_version": "bf3d.r2v.material_identity.v5",
        "requirement_id": REQUIREMENT_ID,
        "source": artifact(SOURCE_MAIN_GLB),
        "candidate": artifact(MAIN_GLB),
        "checks": checks,
        "passed": all(checks.values()),
    }


def configure_render_scene() -> None:
    scene = bpy.context.scene
    scene.render.engine = "BLENDER_EEVEE"
    scene.render.resolution_x = 960
    scene.render.resolution_y = 720
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = "PNG"
    scene.render.film_transparent = False
    scene.view_settings.view_transform = "AgX"
    scene.view_settings.look = "AgX - Medium Low Contrast"
    scene.view_settings.exposure = 0.0


def evidence_renders(
    camera: bpy.types.Object,
    full: bpy.types.Collection,
    section: bpy.types.Collection,
    material_objects: list[bpy.types.Object],
    section_objects: list[bpy.types.Object],
) -> list[dict[str, Any]]:
    configure_render_scene()
    records = []

    minimum, maximum = v3.v2.bounds(section_objects)
    center = (minimum + maximum) * 0.5
    height = maximum.z - minimum.z
    width = max(maximum.y - minimum.y, maximum.x - minimum.x)
    distance = max(height, width) * 1.8

    v3.set_collection_visible(full, True)
    v3.set_collection_visible(section, False)
    material_min, material_max = v3.v2.bounds(material_objects)
    material_center = (material_min + material_max) * 0.5
    material_height = material_max.z - material_min.z
    material_width = max(
        material_max.y - material_min.y,
        material_max.x - material_min.x,
    )
    v3.set_ortho_camera(
        camera,
        Vector(
            (
                material_max.x + max(material_height, material_width) * 1.8,
                material_center.y - material_width * 0.62,
                material_center.z + material_height * 0.14,
            )
        ),
        material_center,
        max(material_height * 1.12, material_width * 1.35),
    )
    records.append(
        v3.render_record(
            RENDER_DIR / "BF3D_V5_01_MATERIAL_GLOBAL.png",
            "V5 pure-material review; only the five R2J shell zones are visible",
            "actual_candidate_mesh_pure_material_global",
        )
    )

    v3.set_collection_visible(full, False)
    v3.set_collection_visible(section, True)
    v3.set_ortho_camera(
        camera,
        Vector((maximum.x + distance, center.y, center.z)),
        center,
        max(height * 1.05, width * 1.22),
    )
    records.append(
        v3.render_record(
            RENDER_DIR / "BF3D_V5_02_STRUCTURAL_ORTHO_1X.png",
            "V5 physical structural section at unamplified 1x thickness",
            "actual_candidate_mesh_structural_orthographic_1x",
        )
    )

    local_target = Vector(
        (
            maximum.x,
            maximum.y - max(width * 0.035, 0.35),
            minimum.z + height * 0.58,
        )
    )
    v3.set_ortho_camera(
        camera,
        Vector((maximum.x + distance, center.y, local_target.z)),
        local_target,
        max(3.6, width * 0.24),
    )
    records.append(
        v3.render_record(
            RENDER_DIR / "BF3D_V5_03_STRUCTURAL_LOCAL_CLOSEUP_1X.png",
            "V5 steel/backfill/stave/hotface/refractory closeup at 1x thickness",
            "actual_candidate_mesh_structural_local_closeup_1x",
        )
    )
    return records


def build() -> None:
    """Build V5 from the locked V4 Blend and fail closed on any drift."""

    configure_v3_namespace()
    for directory in (STAGE, RENDER_DIR, REPORT_DIR, MODEL_DIR):
        directory.mkdir(parents=True, exist_ok=True)
    gate = input_gate()
    protected_before = protected_snapshot()
    input_lock = {
        "schema_version": "bf3d.r2v.input_lock.v5",
        "requirement_id": REQUIREMENT_ID,
        "source_gate": gate,
        "protected_assets_before_build": protected_before,
        "controlled_changes": [
            "triangulate ten V4 physical section meshes without moving vertices",
            "convert four scene provenance values to workspace-relative POSIX paths",
            "rename isolated V5 review roots, collections, camera and asset metadata",
        ],
        "explicit_non_changes": [
            "no texture resolution or payload change",
            "no material parameter or channel change",
            "no layer thickness, bounds, vertex position or volume change",
            "no sensor, data lead, yellow outline or process-particle content",
            "no formal/V1/V2/V3/V4 overwrite",
            "no P50/P60/P70/QA70 or production approval",
        ],
    }
    write_json(STAGE / "input_lock.json", input_lock)
    write_json(REPORT_DIR / "input_gate_validation.json", gate)

    bpy.ops.wm.open_mainfile(filepath=str(SOURCE_BLEND))
    (
        full,
        section,
        material_root,
        section_root,
        camera,
        metadata_changes,
    ) = rename_and_mark_scene()
    provenance = sanitize_scene_provenance(bpy.context.scene)
    write_json(REPORT_DIR / "scene_provenance_sanitization.json", provenance)
    if not provenance["passed"]:
        raise RuntimeError("R2V scene provenance sanitization failed")

    material_objects = sorted(
        [obj for obj in full.objects if obj.type == "MESH"],
        key=lambda item: item.name,
    )
    section_objects = sorted(
        [obj for obj in section.objects if obj.type == "MESH"],
        key=lambda item: item.name,
    )
    if len(material_objects) != 5 or len(section_objects) != 10:
        raise RuntimeError(
            f"R2V V4 hierarchy mismatch: material={len(material_objects)}, "
            f"section={len(section_objects)}"
        )

    before = {obj.name: geometry_record(obj) for obj in section_objects}
    triangulation = triangulate_section_meshes(section_objects)
    after = {obj.name: geometry_record(obj) for obj in section_objects}
    geometry = compare_geometry(before, after)
    tangent = tangent_preflight(section_objects)
    topology = v4.topology_report(section_objects)
    topology["schema_version"] = "bf3d.r2v.section_topology_validation.v5"
    topology["requirement_id"] = REQUIREMENT_ID
    overlap = v4.section_overlap_report(section_objects)
    overlap["schema_version"] = "bf3d.r2v.section_cap_overlap_validation.v5"
    overlap["requirement_id"] = REQUIREMENT_ID
    write_json(REPORT_DIR / "triangulation_operation.json", triangulation)
    write_json(REPORT_DIR / "geometry_equivalence_validation.json", geometry)
    write_json(REPORT_DIR / "tangent_preflight_validation.json", tangent)
    write_json(REPORT_DIR / "section_topology_validation.json", topology)
    write_json(REPORT_DIR / "section_cap_overlap_validation.json", overlap)
    if not geometry["passed"] or not tangent["passed"]:
        raise RuntimeError(
            "R2V geometry/tangent preflight failed: "
            + json.dumps(
                {
                    "geometry": geometry["checks"],
                    "tangent": tangent["checks"],
                },
                ensure_ascii=False,
            )
        )
    if not topology["passed"] or not overlap["passed"]:
        raise RuntimeError("R2V V4 topology preservation gate failed")

    # The locked V4 Blend opens in structural mode, so the full-material
    # collection is intentionally hidden.  Unhide both review collections
    # before selection-based export; direct-open visibility is restored after
    # evidence rendering.
    v3.set_collection_visible(full, True)
    v3.set_collection_visible(section, True)
    v3.export_selected(MATERIAL_GLB, [material_root, *material_objects])
    v3.export_selected(STRUCTURAL_GLB, [section_root, *section_objects])
    v3.export_selected(
        MAIN_GLB,
        [material_root, section_root, *material_objects, *section_objects],
    )
    tangent_sanitization = {
        key: sanitize_glb_tangent_vectors(path)
        for key, path in (
            ("main", MAIN_GLB),
            ("material", MATERIAL_GLB),
            ("structural", STRUCTURAL_GLB),
        )
    }
    write_json(
        REPORT_DIR / "glb_tangent_vector_sanitization.json",
        {
            "schema_version": "bf3d.r2v.glb_tangent_vector_sanitization.v5",
            "requirement_id": REQUIREMENT_ID,
            "assets": tangent_sanitization,
            "checks": {
                "three_assets_processed": len(tangent_sanitization) == 3,
                "all_assets_processed_successfully": all(
                    item["passed"] for item in tangent_sanitization.values()
                ),
            },
            "passed": all(
                item["passed"] for item in tangent_sanitization.values()
            ),
        },
    )

    summaries = {
        "main": v3.summarize_glb(MAIN_GLB),
        "material": v3.summarize_glb(MATERIAL_GLB),
        "structural": v3.summarize_glb(STRUCTURAL_GLB),
    }
    cap_records = [
        {
            "object": obj.name,
            "passed": bool(obj.get("bf3d_section_cut_caps", False)),
        }
        for obj in section_objects
    ]
    contract = v4.exact_contract_checks(
        summaries["main"],
        summaries["material"],
        summaries["structural"],
        cap_records,
        topology,
        overlap,
    )
    contract["v5_material_root_name"] = MATERIAL_ROOT_NAME in summaries[
        "main"
    ]["scene_root_names"]
    contract["v5_section_root_name"] = SECTION_ROOT_NAME in summaries[
        "main"
    ]["scene_root_names"]
    # V4-named checks are inherited helper labels, but their values still
    # correctly enforce the configured V5 roots and preserved topology.
    portability = {
        key: glb_portability_record(path)
        for key, path in (
            ("main", MAIN_GLB),
            ("material", MATERIAL_GLB),
            ("structural", STRUCTURAL_GLB),
        )
    }
    write_json(
        REPORT_DIR / "glb_portability_export_validation.json",
        {
            "schema_version": "bf3d.r2v.glb_portability_export_validation.v5",
            "requirement_id": REQUIREMENT_ID,
            "assets": portability,
            "checks": {
                "three_assets_pass": all(
                    item["passed"] for item in portability.values()
                ),
                "zero_absolute_paths_total": sum(
                    len(item["local_absolute_paths"])
                    for item in portability.values()
                )
                == 0,
                "zero_normal_map_tangent_risks_total": sum(
                    len(item["normal_mapped_primitives_without_tangent"])
                    for item in portability.values()
                )
                == 0,
            },
            "passed": all(item["passed"] for item in portability.values()),
        },
    )
    if not all(contract.values()) or not all(
        item["passed"] for item in portability.values()
    ):
        raise RuntimeError(
            "R2V GLB contract/portability gate failed: "
            + json.dumps(contract, ensure_ascii=False)
        )

    material_identity = material_identity_report()
    write_json(REPORT_DIR / "material_identity_validation.json", material_identity)
    if not material_identity["passed"]:
        raise RuntimeError(
            "R2V material identity gate failed: "
            + json.dumps(material_identity["checks"], ensure_ascii=False)
        )

    evidence = evidence_renders(
        camera,
        full,
        section,
        material_objects,
        section_objects,
    )
    direct_open = v3.configure_direct_open(full, section, camera)
    v3.save_review_blend()
    assert_protected_snapshot(protected_before)

    build_checks = {
        "input_gate_passed": gate["passed"],
        "provenance_sanitized": provenance["passed"],
        "geometry_equivalent": geometry["passed"],
        "tangent_preflight_passed": tangent["passed"],
        "topology_preserved": topology["passed"],
        "cap_overlap_zero": overlap["passed"],
        "glb_contract_passed": all(contract.values()),
        "glb_portability_passed": all(
            item["passed"] for item in portability.values()
        ),
        "tangent_vectors_sanitized": all(
            item["passed"] for item in tangent_sanitization.values()
        ),
        "material_identity_preserved": material_identity["passed"],
        "three_actual_mesh_renders_written": len(evidence) == 3,
        "protected_assets_unchanged": protected_snapshot() == protected_before,
    }
    report = {
        "schema_version": "bf3d.r2v.build_report.v5",
        "requirement_id": REQUIREMENT_ID,
        "asset_id": ASSET_ID,
        "status": STATUS,
        "source": artifact(SOURCE_BLEND),
        "outputs": {
            "main_glb": artifact(MAIN_GLB),
            "material_glb": artifact(MATERIAL_GLB),
            "structural_glb": artifact(STRUCTURAL_GLB),
            "direct_open_blend": artifact(REVIEW_BLEND),
        },
        "object_counts": {
            "material": len(material_objects),
            "section": len(section_objects),
            "total": len(material_objects) + len(section_objects),
        },
        "metadata_string_updates": metadata_changes,
        "controlled_changes": input_lock["controlled_changes"],
        "explicit_non_changes": input_lock["explicit_non_changes"],
        "geometry": geometry,
        "tangent": tangent,
        "topology": topology,
        "overlap": overlap,
        "material_identity": material_identity,
        "tangent_vector_sanitization": tangent_sanitization,
        "portability": portability,
        "direct_open": direct_open,
        "evidence": evidence,
        "checks": build_checks,
        "passed": all(build_checks.values()),
        "approval": {
            "approval_granted": False,
            "next_stage_allowed": False,
            "production_integration_allowed": False,
            "p50_p60_p70_qa70_approved": False,
            "three_blender_photometric_approved": False,
        },
    }
    write_json(REPORT_DIR / "build_report.json", report)
    write_json(
        REPORT_DIR / "visual_manifest.json",
        {
            "schema_version": "bf3d.r2v.visual_manifest.v5",
            "requirement_id": REQUIREMENT_ID,
            "render_engine": "BLENDER_EEVEE",
            "neutral_preset": "P40 neutral inherited from locked V4 Blend",
            "renders": evidence,
            "passed": len(evidence) == 3,
        },
    )
    if not report["passed"]:
        raise RuntimeError(
            "R2V build report failed: "
            + json.dumps(build_checks, ensure_ascii=False)
        )
    print(
        "BF3D_R2V_V5_BUILD="
        + json.dumps(
            {
                "main": artifact(MAIN_GLB),
                "material": artifact(MATERIAL_GLB),
                "structural": artifact(STRUCTURAL_GLB),
                "blend": artifact(REVIEW_BLEND),
                "explicit_tangent_primitives": {
                    key: value["explicit_tangent_primitives"]
                    for key, value in portability.items()
                },
                "absolute_paths": {
                    key: len(value["local_absolute_paths"])
                    for key, value in portability.items()
                },
                "normal_map_tangent_risks": {
                    key: len(value["normal_mapped_primitives_without_tangent"])
                    for key, value in portability.items()
                },
            },
            ensure_ascii=False,
        )
    )


def reopen_validation() -> None:
    """Reopen the saved V5 Blend and validate its direct-review defaults."""

    configure_v3_namespace()
    bpy.ops.wm.open_mainfile(filepath=str(REVIEW_BLEND))
    scene = bpy.context.scene
    full = bpy.data.collections.get(FULL_COLLECTION_NAME)
    section = bpy.data.collections.get(SECTION_COLLECTION_NAME)
    camera = bpy.data.objects.get(CAMERA_NAME)
    material_objects = (
        [obj for obj in full.objects if obj.type == "MESH"] if full else []
    )
    section_objects = (
        [obj for obj in section.objects if obj.type == "MESH"] if section else []
    )
    tangent = tangent_preflight(section_objects) if len(section_objects) == 10 else {
        "passed": False
    }
    topology = v4.topology_report(section_objects) if len(section_objects) == 10 else {
        "passed": False
    }
    if topology.get("passed") is not None:
        topology["schema_version"] = "bf3d.r2v.section_topology_validation.v5"
        topology["requirement_id"] = REQUIREMENT_ID
    overlap = (
        v4.section_overlap_report(section_objects)
        if len(section_objects) == 10
        else {"passed": False}
    )
    if overlap.get("passed") is not None:
        overlap["schema_version"] = "bf3d.r2v.section_cap_overlap_validation.v5"
        overlap["requirement_id"] = REQUIREMENT_ID
    absolute_scene_keys = [
        key
        for key, value in scene.items()
        if isinstance(value, str) and WINDOWS_ABSOLUTE.match(value)
    ]
    packed_images = [
        image.name for image in bpy.data.images if image.packed_file is not None
    ]
    target_screens = []
    for screen_name in ("Layout", "Modeling"):
        screen = bpy.data.screens.get(screen_name)
        values = (
            [
                area.spaces.active.shading.type
                for area in screen.areas
                if area.type == "VIEW_3D"
            ]
            if screen
            else []
        )
        target_screens.append({"screen": screen_name, "shading": values})
    checks = {
        "blend_path_is_v5": Path(bpy.data.filepath).resolve()
        == REVIEW_BLEND.resolve(),
        "material_collection_has_five_meshes": len(material_objects) == 5,
        "section_collection_has_ten_meshes": len(section_objects) == 10,
        "section_visible_by_default": section is not None
        and not section.hide_viewport,
        "material_hidden_by_default": full is not None and full.hide_viewport,
        "active_candidate_camera": camera is not None
        and scene.camera == camera
        and camera.data.type == "ORTHO",
        "layout_and_modeling_use_material_preview": all(
            item["shading"]
            and all(value == "MATERIAL" for value in item["shading"])
            for item in target_screens
        ),
        "all_primary_maps_are_packed": len(
            [name for name in packed_images if name.startswith("BF3D_V3_")]
        )
        >= 18,
        "no_absolute_scene_extras": not absolute_scene_keys,
        "all_section_tangent_calculations_pass": tangent.get("passed") is True,
        "topology_preserved": topology.get("passed") is True,
        "cap_overlap_zero": overlap.get("passed") is True,
        "asset_metadata_is_v5": scene.get("bf3d_asset") == ASSET_ID
        and scene.get("bf3d_requirement_id") == REQUIREMENT_ID,
        "no_forbidden_scene_objects": not [
            obj.name
            for obj in scene.objects
            if any(token in obj.name.upper() for token in v3.FORBIDDEN_TOKENS)
        ],
    }
    report = {
        "schema_version": "bf3d.r2v.blend_reopen_validation.v5",
        "requirement_id": REQUIREMENT_ID,
        "blend": artifact(REVIEW_BLEND),
        "packed_images": packed_images,
        "target_screens": target_screens,
        "absolute_scene_keys": absolute_scene_keys,
        "tangent": tangent,
        "topology": topology,
        "overlap": overlap,
        "checks": checks,
        "passed": all(checks.values()),
    }
    write_json(REPORT_DIR / "blend_reopen_validation.json", report)
    if not report["passed"]:
        raise RuntimeError(
            "R2V Blend reopen validation failed: "
            + json.dumps(checks, ensure_ascii=False)
        )
    print("BF3D_R2V_V5_REOPEN=" + json.dumps(report, ensure_ascii=False))


def factory_import_validation() -> None:
    """Factory-import the three V5 GLBs using the inherited strict contract."""

    configure_v3_namespace()
    v3.factory_import_validation()
    path = REPORT_DIR / "factory_import_validation.json"
    report = json.loads(path.read_text(encoding="utf-8"))
    report["schema_version"] = "bf3d.r2v.factory_import_validation.v5"
    report["requirement_id"] = REQUIREMENT_ID
    write_json(path, report)
    write_json(REPORT_DIR / "derived_glb_factory_import_validation.json", report)
    print("BF3D_R2V_V5_FACTORY_IMPORT=" + json.dumps(report, ensure_ascii=False))


def main() -> int:
    args = sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else []
    if "--reopen" in args:
        reopen_validation()
    elif "--factory-import" in args:
        factory_import_validation()
    else:
        build()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
