"""Capture the pre-registered R2R Eevee/Cycles renderer A/B evidence.

This module is executed by Blender against the locked R2Q V3 ``.blend``.
It changes render state only in memory, never saves the source file, and
fails closed before capture when an input lock or strict OptiX requirement
is not satisfied.

Requirement:
    REQ-BF3D-R2R-BLENDER-RENDERER-NUMERIC-AB-20260719
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import sys
import time
import traceback
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import bpy
import numpy as np
from bpy_extras.object_utils import world_to_camera_view
from mathutils import Matrix, Vector


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_STAGE = (
    ROOT
    / "PT"
    / "高炉3D模型"
    / "work"
    / "WEB_60_20260719_R2R_RENDERER_NUMERIC_AB_GATE"
)
DEFAULT_CONTRACT = DEFAULT_STAGE / "capture_contract.json"
CAPTURE_SCHEMA = "bf3d.r2r.capture_manifest.v1"
RUN_SCHEMA = "bf3d.r2r.capture_run_manifest.v1"
BLOCKED_SCHEMA = "bf3d.r2r.blocked_report.v1"
REQUIREMENT_ID = "REQ-BF3D-R2R-BLENDER-RENDERER-NUMERIC-AB-20260719"

SHOT_IDS = (
    "standard_ortho_section_1x",
    "local_layer_closeup_1x",
    "six_family_material_board_with_midgray",
)
ENGINE_IDS = ("eevee", "cycles")
PRIMARY_FAMILIES = (
    "steel_inner",
    "backfill",
    "cast_iron",
    "copper",
    "hotface",
    "refractory",
)
MATERIAL_NAMES = {
    family: f"BF3D_V3_{family.upper()}_PBR_E_REF_PENDING"
    for family in PRIMARY_FAMILIES
}
UV_NAMES = {
    "steel_inner": "BF3D_INTERNAL_UV_1M",
    "backfill": "BF3D_PHYSICAL_UV_1M",
    "cast_iron": "BF3D_PHYSICAL_UV_1M",
    "copper": "BF3D_PHYSICAL_UV_1M",
    "hotface": "BF3D_PHYSICAL_UV_1M",
    "refractory": "BF3D_PHYSICAL_UV_1M",
}


class GateError(RuntimeError):
    """A fail-closed contract, input, scene, or output validation error."""


class GateBlocked(RuntimeError):
    """A machine capability block, currently reserved for strict OptiX."""


def utc_now() -> str:
    """Return a stable UTC timestamp for machine-readable evidence."""

    return datetime.now(timezone.utc).isoformat()


def sha256(path: Path) -> str:
    """Hash a file without loading it into memory."""

    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def rel(path: Path) -> str:
    """Return a repository-relative POSIX path."""

    return path.resolve().relative_to(ROOT.resolve()).as_posix()


def artifact(path: Path) -> dict[str, Any]:
    """Describe an existing evidence artifact."""

    return {
        "path": rel(path),
        "bytes": path.stat().st_size,
        "sha256": sha256(path),
    }


def write_json(path: Path, value: Any) -> None:
    """Write deterministic UTF-8 JSON evidence."""

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def parse_args() -> argparse.Namespace:
    """Parse Blender arguments following ``--``."""

    argv = sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else []
    parser = argparse.ArgumentParser(
        description="Capture locked R2Q Blender Eevee/strict-OptiX numeric A/B evidence."
    )
    parser.add_argument("--contract", type=Path, default=DEFAULT_CONTRACT)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_STAGE)
    return parser.parse_args(argv)


def require(condition: bool, message: str) -> None:
    """Raise a fail-closed gate error when ``condition`` is false."""

    if not condition:
        raise GateError(message)


def load_contract(path: Path, output_dir: Path) -> tuple[dict[str, Any], str]:
    """Load and validate the immutable, pre-registered capture contract."""

    require(path.is_file(), f"capture contract missing: {path}")
    require(
        path.resolve().parent == output_dir.resolve(),
        "capture contract and output directory must be the same registered stage",
    )
    require(
        output_dir.resolve().is_relative_to(ROOT.resolve()),
        "output directory must remain inside the repository",
    )
    contract_hash = sha256(path)
    contract = json.loads(path.read_text(encoding="utf-8"))
    require(
        contract.get("schema_version") == "bf3d.r2r.capture_contract.v1",
        "unsupported capture contract schema",
    )
    require(contract.get("requirement_id") == REQUIREMENT_ID, "requirement id drift")
    require(
        contract.get("status") == "pre_registered_before_capture",
        "contract was not pre-registered before capture",
    )
    require(contract.get("source_mutation_forbidden") is True, "source mutation lock missing")
    capture = contract.get("capture_contract") or {}
    require(capture.get("repeat_count") == 2, "repeat_count must remain exactly 2")
    require(
        tuple(shot.get("id") for shot in capture.get("shots", [])) == SHOT_IDS,
        "registered shot order or ids drifted",
    )
    engines = capture.get("engines") or {}
    require(
        engines.get("eevee", {}).get("blender_engine") == "BLENDER_EEVEE"
        and engines.get("eevee", {}).get("taa_render_samples") == 64,
        "Eevee64 contract drifted",
    )
    cycles = engines.get("cycles") or {}
    require(
        cycles.get("blender_engine") == "CYCLES"
        and cycles.get("samples") == 48
        and cycles.get("adaptive_sampling") is False
        and cycles.get("denoise") is True
        and cycles.get("denoiser") == "OPTIX"
        and cycles.get("device") == "OPTIX"
        and cycles.get("strict_no_cpu_fallback") is True,
        "strict OptiX Cycles48 contract drifted",
    )
    scene = contract.get("scene_contract") or {}
    require(tuple(scene.get("resolution", [])) == (1920, 1080), "resolution drifted")
    require(scene.get("color_mode") == "RGBA", "RGBA capture is required")
    require(scene.get("transparent_film") is True, "transparent film is required")
    require(scene.get("compositor_effects") is False, "compositor effects must remain off")
    return contract, contract_hash


def lock_snapshot(contract: dict[str, Any]) -> dict[str, Any]:
    """Verify every pre-registered input lock against bytes and SHA-256."""

    records: list[dict[str, Any]] = []
    for item in contract.get("input_locks", []):
        path = ROOT / str(item.get("path", ""))
        exists = path.is_file()
        actual_bytes = path.stat().st_size if exists else None
        actual_sha = sha256(path) if exists else None
        passed = (
            exists
            and actual_bytes == item.get("bytes")
            and actual_sha == item.get("sha256")
        )
        records.append(
            {
                "id": item.get("id"),
                "path": item.get("path"),
                "required": item.get("required") is True,
                "expected_bytes": item.get("bytes"),
                "actual_bytes": actual_bytes,
                "expected_sha256": item.get("sha256"),
                "actual_sha256": actual_sha,
                "passed": passed,
            }
        )
    required_records = [record for record in records if record["required"]]
    return {
        "records": records,
        "required_count": len(required_records),
        "passed": bool(required_records) and all(record["passed"] for record in required_records),
    }


def simple_value(value: Any) -> Any:
    """Convert Blender custom-property values into JSON-compatible data."""

    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    if hasattr(value, "to_list"):
        return value.to_list()
    try:
        return list(value)
    except TypeError:
        return str(value)


def collection_meshes(collection: bpy.types.Collection) -> list[bpy.types.Object]:
    """Return all mesh objects visible through a collection hierarchy."""

    return sorted(
        [obj for obj in collection.all_objects if obj.type == "MESH"],
        key=lambda obj: obj.name,
    )


def object_material_contract(objects: list[bpy.types.Object]) -> list[dict[str, Any]]:
    """Capture the locked R2Q object-to-material and role mapping."""

    role_keys = (
        "bf3d_asset",
        "bf3d_role",
        "bf3d_review_mode",
        "bf3d_material_family",
        "bf3d_section_cap_family",
        "bf3d_body_material_id",
    )
    records: list[dict[str, Any]] = []
    for obj in sorted(objects, key=lambda item: item.name):
        records.append(
            {
                "object": obj.name,
                "mesh": obj.data.name,
                "materials": [slot.name if slot is not None else None for slot in obj.data.materials],
                "roles": {
                    key: simple_value(obj.get(key))
                    for key in role_keys
                    if obj.get(key) is not None
                },
            }
        )
    return records


def flatten_matrix(matrix: Matrix) -> list[float]:
    """Flatten a Blender matrix in row-major order."""

    return [float(value) for row in matrix for value in row]


def light_record(light: bpy.types.Object) -> dict[str, Any]:
    """Record position, direction, color, and energy for a locked light."""

    direction = light.matrix_world.to_quaternion() @ Vector((0.0, 0.0, -1.0))
    data = light.data
    record = {
        "name": light.name,
        "type": data.type,
        "location": [float(value) for value in light.matrix_world.translation],
        "direction": [float(value) for value in direction],
        "color": [float(value) for value in data.color],
        "energy": float(data.energy),
        "matrix_world": flatten_matrix(light.matrix_world),
    }
    if hasattr(data, "angle"):
        record["angle"] = float(data.angle)
    if hasattr(data, "size"):
        record["size"] = float(data.size)
    if hasattr(data, "shape"):
        record["shape"] = str(data.shape)
    return record


def set_collection_visible(collection: bpy.types.Collection, visible: bool) -> None:
    """Set render and viewport visibility for an in-memory collection."""

    # Blender 5.2 can invalidate ``all_objects`` iteration after toggling the
    # collection itself.  Snapshot valid objects first; source mesh counts are
    # still checked independently and exactly by ``scene_setup``.
    objects = [obj for obj in collection.all_objects if obj is not None]
    collection.hide_render = not visible
    collection.hide_viewport = not visible
    for obj in objects:
        obj.hide_render = not visible


def scene_setup(
    contract: dict[str, Any],
) -> tuple[
    bpy.types.Object,
    bpy.types.Collection,
    bpy.types.Collection,
    list[bpy.types.Object],
    list[dict[str, Any]],
]:
    """Apply and validate the pre-registered scene contract in memory."""

    scene_contract = contract["scene_contract"]
    scene = bpy.context.scene
    width, height = scene_contract["resolution"]
    scene.render.resolution_x = int(width)
    scene.render.resolution_y = int(height)
    scene.render.resolution_percentage = int(scene_contract["resolution_percentage"])
    scene.render.image_settings.file_format = scene_contract["file_format"]
    scene.render.image_settings.color_mode = scene_contract["color_mode"]
    scene.render.image_settings.color_depth = scene_contract["color_depth"]
    scene.render.film_transparent = bool(scene_contract["transparent_film"])
    scene.view_settings.view_transform = scene_contract["view_transform"]
    scene.view_settings.look = scene_contract["look"]
    scene.view_settings.exposure = float(scene_contract["exposure"])
    # Blender 5.2 keeps the deprecated ``Scene.use_nodes`` flag true even
    # when no compositor exists.  The authoritative no-effects signal is the
    # new compositing node-group pointer, which must remain absent.
    require(
        scene.compositing_node_group is None,
        "compositor node group exists but compositor effects are forbidden",
    )

    world = scene.world
    require(world is not None, "locked Blend has no world")
    world.use_nodes = True
    background = world.node_tree.nodes.get("Background")
    require(background is not None, "world Background node missing")
    background.inputs["Color"].default_value = scene_contract["world_color"]
    background.inputs["Strength"].default_value = float(scene_contract["world_strength"])

    full = bpy.data.collections.get(scene_contract["hidden_collection"])
    section = bpy.data.collections.get(scene_contract["visible_collection"])
    require(full is not None, "locked full-material collection missing")
    require(section is not None, "locked section collection missing")
    full_meshes = collection_meshes(full)
    section_meshes = collection_meshes(section)
    require(
        len(full_meshes) == scene_contract["expected_hidden_meshes"],
        f"hidden mesh count drift: {len(full_meshes)}",
    )
    require(
        len(section_meshes) == scene_contract["expected_visible_meshes"],
        f"visible mesh count drift: {len(section_meshes)}",
    )
    set_collection_visible(full, False)
    set_collection_visible(section, True)

    camera = bpy.data.objects.get(scene_contract["camera_object"])
    require(camera is not None and camera.type == "CAMERA", "registered camera missing")
    require(camera.data.type == scene_contract["camera_type"], "camera projection drift")
    scene.camera = camera

    light_collection = bpy.data.collections.get(scene_contract["light_collection"])
    require(light_collection is not None, "P40 neutral light collection missing")
    set_collection_visible(light_collection, True)
    light_records: list[dict[str, Any]] = []
    expected_types = scene_contract["required_light_types"]
    for name in scene_contract["required_lights"]:
        light = bpy.data.objects.get(name)
        require(light is not None and light.type == "LIGHT", f"required light missing: {name}")
        require(light.data.type == expected_types[name], f"required light type drift: {name}")
        light.hide_render = False
        light_records.append(light_record(light))
    return camera, full, section, section_meshes, light_records


def bounds(objects: list[bpy.types.Object]) -> tuple[Vector, Vector]:
    """Compute world-space bounds for the locked section objects."""

    points = [
        obj.matrix_world @ Vector(corner)
        for obj in objects
        for corner in obj.bound_box
    ]
    require(bool(points), "cannot compute bounds for an empty object set")
    minimum = Vector(tuple(min(point[index] for point in points) for index in range(3)))
    maximum = Vector(tuple(max(point[index] for point in points) for index in range(3)))
    return minimum, maximum


def look_at(camera: bpy.types.Object, target: Vector) -> None:
    """Aim a Blender camera's local -Z axis at ``target``."""

    direction = target - camera.location
    require(direction.length > 1.0e-9, "camera target equals camera location")
    camera.rotation_euler = direction.to_track_quat("-Z", "Y").to_euler()


def set_ortho_camera(
    camera: bpy.types.Object,
    location: Vector,
    target: Vector,
    ortho_scale: float,
) -> None:
    """Set the registered camera without creating or saving a replacement."""

    camera.data.type = "ORTHO"
    camera.location = location
    camera.data.ortho_scale = float(ortho_scale)
    look_at(camera, target)
    bpy.context.scene.camera = camera
    bpy.context.view_layer.update()


def move_exact(obj: bpy.types.Object, collection: bpy.types.Collection) -> None:
    """Move an in-memory diagnostic object into exactly one collection."""

    for source in list(obj.users_collection):
        source.objects.unlink(obj)
    collection.objects.link(obj)


def fill_spherical_uv(obj: bpy.types.Object, layer: Any) -> None:
    """Fill a deterministic local-space spherical UV layer."""

    for loop in obj.data.loops:
        point = obj.data.vertices[loop.vertex_index].co.normalized()
        u = math.atan2(float(point.y), float(point.x)) / (2.0 * math.pi) + 0.5
        v = math.acos(max(-1.0, min(1.0, float(point.z)))) / math.pi
        layer.data[loop.index].uv = (u, 1.0 - v)


def create_midgray_material() -> bpy.types.Material:
    """Create an in-memory neutral 18 percent reflectance reference material."""

    name = "R2R_DIAGNOSTIC_MIDGRAY_18_PERCENT"
    existing = bpy.data.materials.get(name)
    if existing is not None:
        bpy.data.materials.remove(existing)
    material = bpy.data.materials.new(name)
    material.use_nodes = True
    material.use_backface_culling = True
    nodes = material.node_tree.nodes
    links = material.node_tree.links
    nodes.clear()
    output = nodes.new("ShaderNodeOutputMaterial")
    bsdf = nodes.new("ShaderNodeBsdfPrincipled")
    links.new(bsdf.outputs["BSDF"], output.inputs["Surface"])
    bsdf.inputs["Base Color"].default_value = (0.18, 0.18, 0.18, 1.0)
    bsdf.inputs["Metallic"].default_value = 0.0
    bsdf.inputs["Roughness"].default_value = 0.8
    bsdf.inputs["Alpha"].default_value = 1.0
    if bsdf.inputs.get("Emission Color") is not None:
        bsdf.inputs["Emission Color"].default_value = (0.0, 0.0, 0.0, 1.0)
    if bsdf.inputs.get("Emission Strength") is not None:
        bsdf.inputs["Emission Strength"].default_value = 0.0
    material["bf3d_reference_reflectance"] = 0.18
    material["bf3d_diagnostic_only"] = True
    return material


def create_material_board() -> tuple[bpy.types.Collection, dict[str, bpy.types.Object]]:
    """Create the registered six-family board and centered midgray block in memory."""

    name = "R2R_DIAGNOSTIC_MATERIAL_BOARD_TEMP"
    existing = bpy.data.collections.get(name)
    if existing is not None:
        raise GateError("stale diagnostic material-board collection already exists")
    board = bpy.data.collections.new(name)
    bpy.context.scene.collection.children.link(board)
    positions = {
        "steel_inner": (-3.125, 1.05),
        "backfill": (-0.625, 1.05),
        "cast_iron": (1.875, 1.05),
        "copper": (-1.875, -1.115),
        "hotface": (0.625, -1.115),
        "refractory": (3.125, -1.115),
    }
    objects: dict[str, bpy.types.Object] = {}
    for family in PRIMARY_FAMILIES:
        material = bpy.data.materials.get(MATERIAL_NAMES[family])
        require(material is not None, f"locked material datablock missing: {family}")
        y, z = positions[family]
        bpy.ops.mesh.primitive_ico_sphere_add(
            subdivisions=5,
            radius=1.25,
            location=(0.0, y, z),
        )
        sphere = bpy.context.object
        sphere.name = f"R2R_SWATCH_{family.upper()}"
        move_exact(sphere, board)
        sphere.data.materials.append(material)
        if family == "steel_inner":
            sphere.data.uv_layers.new(name="UV0_DUMMY")
        uv_layer = sphere.data.uv_layers.new(name=UV_NAMES[family])
        fill_spherical_uv(sphere, uv_layer)
        if family == "steel_inner":
            sphere.data.uv_layers.active_index = 1
            uv_layer.active_render = True
        sphere["bf3d_material_family"] = family
        sphere["bf3d_diagnostic_only"] = True
        objects[family] = sphere

    bpy.ops.mesh.primitive_cube_add(size=1.0, location=(0.0, 0.0, -2.55))
    midgray = bpy.context.object
    midgray.name = "R2R_MIDGRAY_18_PERCENT"
    midgray.scale = (0.55, 0.75, 0.08)
    move_exact(midgray, board)
    midgray.data.materials.append(create_midgray_material())
    midgray["bf3d_material_family"] = "midgray_18_percent"
    midgray["bf3d_diagnostic_only"] = True
    objects["midgray"] = midgray
    set_collection_visible(board, False)
    return board, objects


def configure_shot(
    shot_id: str,
    camera: bpy.types.Object,
    full: bpy.types.Collection,
    section: bpy.types.Collection,
    section_objects: list[bpy.types.Object],
    board: bpy.types.Collection,
) -> dict[str, Any]:
    """Apply one registered camera formula and visibility state."""

    minimum, maximum = bounds(section_objects)
    center = (minimum + maximum) * 0.5
    height = float(maximum.z - minimum.z)
    width = float(max(maximum.y - minimum.y, maximum.x - minimum.x))
    distance = 1.8 * max(height, width)
    if shot_id == "standard_ortho_section_1x":
        location = Vector((maximum.x + distance, center.y, center.z))
        target = center
        ortho_scale = max(1.05 * height, 1.22 * width)
        set_collection_visible(full, False)
        set_collection_visible(section, True)
        set_collection_visible(board, False)
        actual_asset_geometry = True
    elif shot_id == "local_layer_closeup_1x":
        target = Vector(
            (
                maximum.x,
                maximum.y - max(0.035 * width, 0.35),
                minimum.z + 0.58 * height,
            )
        )
        location = Vector((maximum.x + distance, center.y, target.z))
        ortho_scale = max(3.6, 0.24 * width)
        set_collection_visible(full, False)
        set_collection_visible(section, True)
        set_collection_visible(board, False)
        actual_asset_geometry = True
    elif shot_id == "six_family_material_board_with_midgray":
        location = Vector((12.0, 0.0, 0.0))
        target = Vector((0.0, 0.0, 0.0))
        ortho_scale = 9.6
        set_collection_visible(full, False)
        set_collection_visible(section, False)
        set_collection_visible(board, True)
        actual_asset_geometry = False
    else:
        raise GateError(f"unregistered shot: {shot_id}")
    set_ortho_camera(camera, location, target, ortho_scale)
    return {
        "camera_formula_applied": True,
        "location": [float(value) for value in location],
        "target": [float(value) for value in target],
        "ortho_scale": float(ortho_scale),
        "actual_asset_geometry": actual_asset_geometry,
        "thickness_scale": 1.0 if actual_asset_geometry else None,
        "bounds": {
            "minimum": [float(value) for value in minimum],
            "maximum": [float(value) for value in maximum],
            "height": height,
            "width": width,
        },
    }


def project_point(camera: bpy.types.Object, point: Vector) -> list[float]:
    """Project a world point to top-left-origin CSS-like pixel coordinates."""

    scene = bpy.context.scene
    coordinate = world_to_camera_view(scene, camera, point)
    return [
        float(coordinate.x * scene.render.resolution_x),
        float((1.0 - coordinate.y) * scene.render.resolution_y),
        float(coordinate.z),
    ]


def object_projected_bbox(camera: bpy.types.Object, obj: bpy.types.Object) -> list[int]:
    """Project an object's world bounding box and clamp it to the frame."""

    width = bpy.context.scene.render.resolution_x
    height = bpy.context.scene.render.resolution_y
    points = [
        project_point(camera, obj.matrix_world @ Vector(corner))
        for corner in obj.bound_box
    ]
    raw = [
        int(math.floor(min(point[0] for point in points))),
        int(math.floor(min(point[1] for point in points))),
        int(math.ceil(max(point[0] for point in points))) + 1,
        int(math.ceil(max(point[1] for point in points))) + 1,
    ]
    x0 = max(0, raw[0])
    y0 = max(0, raw[1])
    x1 = min(width, raw[2])
    y1 = min(height, raw[3])
    require(
        x1 > x0 and y1 > y0,
        f"empty projected bbox for {obj.name}: raw={raw}, frame={[width, height]}",
    )
    return [x0, y0, x1, y1]


def camera_record(
    camera: bpy.types.Object,
    control_objects: list[bpy.types.Object],
    board_objects: dict[str, bpy.types.Object],
    shot_id: str,
) -> dict[str, Any]:
    """Record fixed camera matrices, projection, controls, and material ROIs."""

    scene = bpy.context.scene
    depsgraph = bpy.context.evaluated_depsgraph_get()
    projection = camera.calc_matrix_camera(
        depsgraph,
        x=scene.render.resolution_x,
        y=scene.render.resolution_y,
        scale_x=1.0,
        scale_y=1.0,
    )
    controls: dict[str, list[float]] = {}
    if shot_id == "six_family_material_board_with_midgray":
        active_objects = [board_objects[key] for key in (*PRIMARY_FAMILIES, "midgray")]
    else:
        active_objects = control_objects
    for obj in active_objects:
        controls[f"{obj.name}:center"] = project_point(
            camera, obj.matrix_world.translation
        )
        for index, corner in enumerate(obj.bound_box):
            controls[f"{obj.name}:bbox:{index}"] = project_point(
                camera, obj.matrix_world @ Vector(corner)
            )
    material_rois = None
    midgray_roi = None
    if shot_id == "six_family_material_board_with_midgray":
        material_rois = {
            family: object_projected_bbox(camera, board_objects[family])
            for family in PRIMARY_FAMILIES
        }
        midgray_roi = object_projected_bbox(camera, board_objects["midgray"])
    return {
        "object": camera.name,
        "type": camera.data.type,
        "location": [float(value) for value in camera.matrix_world.translation],
        "rotation_quaternion": [
            float(value) for value in camera.matrix_world.to_quaternion()
        ],
        "ortho_scale": float(camera.data.ortho_scale),
        "clip_start": float(camera.data.clip_start),
        "clip_end": float(camera.data.clip_end),
        "matrix_world": flatten_matrix(camera.matrix_world),
        "view_matrix": flatten_matrix(camera.matrix_world.inverted()),
        "projection_matrix": flatten_matrix(projection),
        "control_points_px": controls,
        "material_rois_px": material_rois,
        "midgray_roi_px": midgray_roi,
    }


def optix_preflight() -> dict[str, Any]:
    """Enable only OptiX devices and prove that CPU/CUDA fallback is disabled."""

    addon = bpy.context.preferences.addons.get("cycles")
    if addon is None:
        raise GateBlocked("Cycles add-on is unavailable")
    preferences = addon.preferences
    try:
        preferences.compute_device_type = "OPTIX"
        preferences.get_devices()
    except Exception as exc:
        raise GateBlocked(f"OptiX device discovery failed: {exc}") from exc
    records: list[dict[str, Any]] = []
    for device in preferences.devices:
        device.use = device.type == "OPTIX"
        records.append(
            {
                "name": device.name,
                "type": device.type,
                "enabled": bool(device.use),
            }
        )
    enabled_optix = [
        record for record in records if record["type"] == "OPTIX" and record["enabled"]
    ]
    enabled_non_optix = [
        record for record in records if record["type"] != "OPTIX" and record["enabled"]
    ]
    if not enabled_optix:
        raise GateBlocked("no enabled OptiX device; CPU fallback is forbidden")
    if enabled_non_optix:
        raise GateBlocked("a non-OptiX device remained enabled")
    return {
        "compute_device_type": preferences.compute_device_type,
        "devices": records,
        "enabled_optix_count": len(enabled_optix),
        "enabled_non_optix_count": len(enabled_non_optix),
        "strict_no_cpu_fallback": True,
        "passed": True,
    }


def configure_engine(engine_id: str, contract: dict[str, Any]) -> dict[str, Any]:
    """Apply the exact registered Eevee64 or strict OptiX Cycles48 settings."""

    scene = bpy.context.scene
    settings = contract["capture_contract"]["engines"][engine_id]
    if engine_id == "eevee":
        scene.render.engine = settings["blender_engine"]
        scene.eevee.taa_render_samples = int(settings["taa_render_samples"])
        scene.eevee.taa_samples = int(settings["taa_render_samples"])
        return {
            "engine_id": engine_id,
            "blender_engine": scene.render.engine,
            "taa_render_samples": int(scene.eevee.taa_render_samples),
            "fixed_seed": contract["capture_contract"]["fixed_seed"],
        }
    if engine_id == "cycles":
        scene.render.engine = settings["blender_engine"]
        scene.cycles.samples = int(settings["samples"])
        scene.cycles.use_adaptive_sampling = bool(settings["adaptive_sampling"])
        scene.cycles.use_denoising = bool(settings["denoise"])
        scene.cycles.denoiser = settings["denoiser"]
        scene.cycles.device = "GPU"
        scene.cycles.seed = int(contract["capture_contract"]["fixed_seed"])
        if hasattr(scene.cycles, "use_animated_seed"):
            scene.cycles.use_animated_seed = False
        return {
            "engine_id": engine_id,
            "blender_engine": scene.render.engine,
            "samples": int(scene.cycles.samples),
            "adaptive_sampling": bool(scene.cycles.use_adaptive_sampling),
            "denoise": bool(scene.cycles.use_denoising),
            "denoiser": scene.cycles.denoiser,
            "cycles_device": scene.cycles.device,
            "requested_backend": settings["device"],
            "strict_no_cpu_fallback": settings["strict_no_cpu_fallback"],
            "fixed_seed": int(scene.cycles.seed),
        }
    raise GateError(f"unsupported engine id: {engine_id}")


def save_binary_mask(path: Path, alpha: np.ndarray, threshold: float) -> dict[str, Any]:
    """Save a binary PNG mask derived directly from the beauty render alpha."""

    height, width = alpha.shape
    binary = alpha >= threshold
    rgba = np.empty((height, width, 4), dtype=np.float32)
    rgba[..., 0] = binary
    rgba[..., 1] = binary
    rgba[..., 2] = binary
    rgba[..., 3] = 1.0
    image = bpy.data.images.new(
        f"R2R_MASK_{path.stem}_{time.time_ns()}",
        width=width,
        height=height,
        alpha=True,
        float_buffer=False,
    )
    try:
        image.colorspace_settings.name = "Non-Color"
        image.pixels.foreach_set(rgba.ravel())
        image.filepath_raw = str(path)
        image.file_format = "PNG"
        image.save()
    finally:
        bpy.data.images.remove(image)
    require(path.is_file(), f"mask output missing: {path}")
    return {
        **artifact(path),
        "threshold": float(threshold),
        "foreground_pixels": int(np.count_nonzero(binary)),
        "foreground_ratio": float(np.mean(binary)),
        "derived_from_beauty_alpha": True,
    }


def render_capture(
    beauty_path: Path,
    mask_path: Path,
    mask_threshold: float,
) -> tuple[dict[str, Any], dict[str, Any], float]:
    """Render one RGBA beauty and derive its required alpha mask."""

    scene = bpy.context.scene
    beauty_path.parent.mkdir(parents=True, exist_ok=True)
    scene.render.filepath = str(beauty_path)
    start = time.perf_counter()
    bpy.ops.render.render(write_still=True)
    duration = time.perf_counter() - start
    require(beauty_path.is_file(), f"beauty output missing: {beauty_path}")
    # Blender 5.2 background mode may release ``Render Result`` pixels after
    # ``write_still=True``.  Reload the just-written RGBA PNG so the mask is
    # provably derived from the persisted beauty evidence.
    result = bpy.data.images.load(str(beauty_path), check_existing=False)
    try:
        width, height = result.size
        require(
            (width, height) == (scene.render.resolution_x, scene.render.resolution_y),
            f"persisted beauty size drift: {(width, height)}",
        )
        pixels = np.empty(width * height * 4, dtype=np.float32)
        result.pixels.foreach_get(pixels)
        require(
            pixels.size == width * height * 4 and np.all(np.isfinite(pixels)),
            "persisted beauty RGBA pixels are invalid",
        )
    finally:
        bpy.data.images.remove(result)
    alpha = pixels.reshape((height, width, 4))[..., 3]
    beauty = {
        **artifact(beauty_path),
        "width": int(width),
        "height": int(height),
        "color_mode": scene.render.image_settings.color_mode,
        "color_depth": scene.render.image_settings.color_depth,
        "transparent_film": bool(scene.render.film_transparent),
        "alpha_min": float(np.min(alpha)),
        "alpha_max": float(np.max(alpha)),
    }
    mask = save_binary_mask(mask_path, alpha, mask_threshold)
    return beauty, mask, duration


def scene_contract_record(
    contract: dict[str, Any],
    full: bpy.types.Collection,
    section: bpy.types.Collection,
    light_records: list[dict[str, Any]],
    material_contract: list[dict[str, Any]],
) -> dict[str, Any]:
    """Record the scene settings that must be invariant across captures."""

    scene = bpy.context.scene
    background = scene.world.node_tree.nodes.get("Background")
    checks = {
        "resolution": [scene.render.resolution_x, scene.render.resolution_y]
        == contract["scene_contract"]["resolution"],
        "resolution_percentage": scene.render.resolution_percentage
        == contract["scene_contract"]["resolution_percentage"],
        "file_format": scene.render.image_settings.file_format
        == contract["scene_contract"]["file_format"],
        "color_mode": scene.render.image_settings.color_mode
        == contract["scene_contract"]["color_mode"],
        "color_depth": scene.render.image_settings.color_depth
        == contract["scene_contract"]["color_depth"],
        "transparent_film": bool(scene.render.film_transparent)
        == contract["scene_contract"]["transparent_film"],
        "view_transform": scene.view_settings.view_transform
        == contract["scene_contract"]["view_transform"],
        "look": scene.view_settings.look == contract["scene_contract"]["look"],
        "exposure": abs(
            float(scene.view_settings.exposure)
            - float(contract["scene_contract"]["exposure"])
        )
        <= 1.0e-12,
        "compositor_effects": (scene.compositing_node_group is not None)
        == contract["scene_contract"]["compositor_effects"],
    }
    return {
        "resolution": [scene.render.resolution_x, scene.render.resolution_y],
        "resolution_percentage": scene.render.resolution_percentage,
        "file_format": scene.render.image_settings.file_format,
        "color_mode": scene.render.image_settings.color_mode,
        "color_depth": scene.render.image_settings.color_depth,
        "transparent_film": bool(scene.render.film_transparent),
        "view_transform": scene.view_settings.view_transform,
        "look": scene.view_settings.look,
        "exposure": float(scene.view_settings.exposure),
        "world_color": [float(value) for value in background.inputs["Color"].default_value],
        "world_strength": float(background.inputs["Strength"].default_value),
        "compositor_effects": scene.compositing_node_group is not None,
        "legacy_scene_use_nodes_deprecated": bool(scene.use_nodes),
        "full_collection": full.name,
        "section_collection": section.name,
        "full_mesh_count": len(collection_meshes(full)),
        "section_mesh_count": len(collection_meshes(section)),
        "lights": light_records,
        "object_material_roles": material_contract,
        "checks": checks,
        "matches_registered_static_contract": all(checks.values()),
    }


def capture_all(
    contract: dict[str, Any],
    contract_path: Path,
    contract_hash: str,
    output_dir: Path,
    state: dict[str, Any],
) -> None:
    """Execute all 12 registered captures and write incremental manifests."""

    initial_locks = lock_snapshot(contract)
    state["input_locks_before"] = initial_locks
    require(initial_locks["passed"], "one or more required input locks failed")
    source_lock = next(
        item for item in contract["input_locks"] if item["id"] == "r2q_direct_open_blend"
    )
    open_blend = Path(bpy.data.filepath).resolve()
    expected_blend = (ROOT / source_lock["path"]).resolve()
    require(open_blend == expected_blend, "Blender did not directly open the locked R2Q Blend")

    optix = optix_preflight()
    state["optix_preflight"] = optix
    camera, full, section, section_objects, lights = scene_setup(contract)
    material_contract = object_material_contract(section_objects)
    board, board_objects = create_material_board()
    static_scene = scene_contract_record(
        contract, full, section, lights, material_contract
    )
    state["scene_contract"] = static_scene
    write_json(output_dir / "capture_manifest.json", state)
    require(
        static_scene["matches_registered_static_contract"],
        "scene settings do not match the registered static contract",
    )
    state["source_blend_opened"] = rel(open_blend)
    state["source_blend_saved"] = False
    state["captures"] = []
    state["run_manifests"] = []
    state["status"] = "capturing"
    write_json(output_dir / "capture_manifest.json", state)

    repeat_count = int(contract["capture_contract"]["repeat_count"])
    mask_threshold = float(contract["comparison_contract"]["mask_threshold"])
    for engine_id in ENGINE_IDS:
        engine_settings = configure_engine(engine_id, contract)
        for repeat_index in range(1, repeat_count + 1):
            run_records: list[dict[str, Any]] = []
            for shot_id in SHOT_IDS:
                formula = configure_shot(
                    shot_id,
                    camera,
                    full,
                    section,
                    section_objects,
                    board,
                )
                current_material_contract = object_material_contract(section_objects)
                require(
                    current_material_contract == material_contract,
                    "locked object/material role mapping drifted in memory",
                )
                current_lights = [
                    light_record(bpy.data.objects[item["name"]]) for item in lights
                ]
                camera_data = camera_record(
                    camera,
                    section_objects,
                    board_objects,
                    shot_id,
                )
                capture_dir = (
                    output_dir
                    / "captures"
                    / engine_id
                    / f"repeat_{repeat_index:02d}"
                )
                beauty_path = capture_dir / f"{shot_id}_beauty.png"
                mask_path = capture_dir / f"{shot_id}_mask.png"
                beauty, mask, duration = render_capture(
                    beauty_path,
                    mask_path,
                    mask_threshold,
                )
                record = {
                    "id": f"{engine_id}.repeat_{repeat_index:02d}.{shot_id}",
                    "engine_id": engine_id,
                    "repeat_index": repeat_index,
                    "shot_id": shot_id,
                    "captured_at": utc_now(),
                    "duration_seconds": duration,
                    "engine_settings": engine_settings,
                    "shot_formula": formula,
                    "camera": camera_data,
                    "lights": current_lights,
                    "object_material_roles": current_material_contract,
                    "beauty": beauty,
                    "mask": mask,
                }
                run_records.append(record)
                state["captures"].append(record)
                write_json(output_dir / "capture_manifest.json", state)
                print(
                    "BF3D_R2R_CAPTURE="
                    + json.dumps(
                        {
                            "id": record["id"],
                            "duration_seconds": duration,
                            "beauty": beauty["path"],
                            "mask": mask["path"],
                        },
                        ensure_ascii=False,
                    ),
                    flush=True,
                )
            run_path = (
                output_dir
                / "manifests"
                / f"{engine_id}_repeat_{repeat_index:02d}.json"
            )
            run_manifest = {
                "schema_version": RUN_SCHEMA,
                "requirement_id": REQUIREMENT_ID,
                "contract": {
                    "path": rel(contract_path),
                    "sha256": contract_hash,
                },
                "engine_id": engine_id,
                "repeat_index": repeat_index,
                "engine_settings": engine_settings,
                "optix_preflight": optix if engine_id == "cycles" else None,
                "captures": run_records,
                "passed": len(run_records) == len(SHOT_IDS),
            }
            write_json(run_path, run_manifest)
            state["run_manifests"].append(artifact(run_path))
            write_json(output_dir / "capture_manifest.json", state)

    final_locks = lock_snapshot(contract)
    state["input_locks_after"] = final_locks
    require(final_locks["passed"], "an input lock changed during capture")
    require(
        initial_locks == final_locks,
        "input lock snapshot changed during capture",
    )
    require(
        len(state["captures"]) == len(ENGINE_IDS) * repeat_count * len(SHOT_IDS),
        "capture count is incomplete",
    )
    state["status"] = "captured"
    state["completed_at"] = utc_now()
    state["capture_count"] = len(state["captures"])
    state["source_mutation_detected"] = False
    write_json(output_dir / "capture_manifest.json", state)


def blocked_markdown(report: dict[str, Any]) -> str:
    """Render a concise capability-block report."""

    return "\n".join(
        [
            "# R2R Blender renderer A/B BLOCKED",
            "",
            f"- Requirement: `{report['requirement_id']}`",
            f"- Reason: {report['reason']}",
            "- Cycles policy: strict OptiX only; CPU/CUDA fallback was not used.",
            "- Numeric A/B PASS: unavailable because required captures/metrics are missing.",
            "",
        ]
    )


def main() -> int:
    """Run the fail-closed registered capture workflow."""

    args = parse_args()
    contract_path = args.contract.resolve()
    output_dir = args.output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    state: dict[str, Any] = {
        "schema_version": CAPTURE_SCHEMA,
        "requirement_id": REQUIREMENT_ID,
        "stage_id": "WEB-60_R2R",
        "status": "initializing",
        "started_at": utc_now(),
        "blender": {
            "version": bpy.app.version_string,
            "version_tuple": list(bpy.app.version),
            "binary_path": bpy.app.binary_path,
            "build_hash": bpy.app.build_hash.decode("ascii", errors="replace")
            if isinstance(bpy.app.build_hash, bytes)
            else str(bpy.app.build_hash),
            "background": bool(bpy.app.background),
        },
        "command": {
            "source_blend": bpy.data.filepath,
            "python_script": str(Path(__file__).resolve()),
            "contract": str(contract_path),
            "output_dir": str(output_dir),
        },
        "source_mutation_forbidden": True,
        "source_blend_saved": False,
    }
    try:
        contract, contract_hash = load_contract(contract_path, output_dir)
        state["contract"] = {
            "path": rel(contract_path),
            "bytes": contract_path.stat().st_size,
            "sha256": contract_hash,
            "status": contract["status"],
        }
        state["evidence_class"] = contract["evidence_class"]
        state["reference_status"] = contract["reference_status"]
        state["not_for_construction"] = contract["not_for_construction"]
        state["approval_granted"] = contract["approval_granted"]
        capture_all(
            contract,
            contract_path,
            contract_hash,
            output_dir,
            state,
        )
        print(
            "BF3D_R2R_CAPTURE_COMPLETE="
            + json.dumps(
                {
                    "status": state["status"],
                    "capture_count": state["capture_count"],
                    "manifest": rel(output_dir / "capture_manifest.json"),
                },
                ensure_ascii=False,
            ),
            flush=True,
        )
        return 0
    except GateBlocked as exc:
        state["status"] = "blocked"
        state["completed_at"] = utc_now()
        state["reason"] = str(exc)
        state["traceback"] = traceback.format_exc()
        write_json(output_dir / "capture_manifest.json", state)
        report = {
            "schema_version": BLOCKED_SCHEMA,
            "requirement_id": REQUIREMENT_ID,
            "status": "BLOCKED",
            "reason": str(exc),
            "strict_no_cpu_fallback": True,
            "capture_manifest": artifact(output_dir / "capture_manifest.json"),
            "numeric_ab_pass": False,
        }
        write_json(output_dir / "blocked_report.json", report)
        (output_dir / "blocked_report.md").write_text(
            blocked_markdown(report),
            encoding="utf-8",
        )
        print("BF3D_R2R_BLOCKED=" + str(exc), flush=True)
        return 2
    except Exception as exc:
        state["status"] = "failed"
        state["completed_at"] = utc_now()
        state["reason"] = str(exc)
        state["traceback"] = traceback.format_exc()
        write_json(output_dir / "capture_manifest.json", state)
        print("BF3D_R2R_FAILED=" + str(exc), flush=True)
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
