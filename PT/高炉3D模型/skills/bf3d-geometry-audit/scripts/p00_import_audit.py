"""Import the GL02 GLB into Blender and create a non-destructive P00 audit.

This script runs inside Blender 5.2 in background mode. It never writes to the
input GLB. It saves a new P00 blend checkpoint, a machine-readable scene audit,
and five fixed clay renders for visual baseline review.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import struct
import sys
import traceback
from collections import Counter
from pathlib import Path
from typing import Any

import bmesh
import bpy
from mathutils import Matrix, Quaternion, Vector


PROCESS_ZONES = {
    "APPROX_GL02_FURNACE_HEARTH",
    "APPROX_GL02_FURNACE_BOSH",
    "APPROX_GL02_FURNACE_BELLY",
    "APPROX_GL02_FURNACE_SHAFT",
    "APPROX_GL02_FURNACE_THROAT",
}
LAYER_GROUPS = {f"GL02_SENSOR_LAYER_L{layer}" for layer in range(7, 17)}
EXPECTED_SENSOR_COUNT = 115
EXPECTED_BODY_SENSOR_COUNT = 80
EXPECTED_SOURCE_SHA256 = "808960f1b2703e7fb27df35f1b1b1a17063b9b10d2267acba593fc3872b62af6"
POSITION_TOLERANCE_M = 1e-5
MATRIX_TOLERANCE = 1e-5
SCALE_TOLERANCE = 1e-6
GLTF_TO_BLENDER = Matrix(
    (
        (1.0, 0.0, 0.0, 0.0),
        (0.0, 0.0, -1.0, 0.0),
        (0.0, 1.0, 0.0, 0.0),
        (0.0, 0.0, 0.0, 1.0),
    )
)
INTERNAL_RENDER_PREFIXES = (
    "SENSOR_",
    "APPROX_GL02_internal_",
    "APPROX_GL02_burden_",
    "APPROX_GL02_cohesive_",
    "APPROX_GL02_hearth_molten_",
    "APPROX_GL02_hearth_slag_",
    "APPROX_GL02_hot_metal_dripping_",
    "APPROX_GL02_countercurrent_",
    "APPROX_GL02_hot_blast_raceway_",
    "APPROX_GL02_cold_blast_supply_",
    "APPROX_GL02_shell_ash_",
    "APPROX_GL02_shell_local_heat_",
)


def parse_args() -> argparse.Namespace:
    argv = sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else []
    parser = argparse.ArgumentParser(description="Create a GL02 Blender P00 audit checkpoint.")
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--resolution", type=int, default=768)
    return parser.parse_args(argv)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def read_glb_json(path: Path) -> dict[str, Any]:
    blob = path.read_bytes()
    if len(blob) < 20:
        raise ValueError(f"GLB is too small: {path}")
    magic, version, total_length = struct.unpack("<4sII", blob[:12])
    if magic != b"glTF" or version != 2 or total_length != len(blob):
        raise ValueError(f"Invalid glTF 2.0 GLB: {path}")
    json_length, chunk_type = struct.unpack("<II", blob[12:20])
    if chunk_type != 0x4E4F534A:
        raise ValueError("The first GLB chunk is not JSON")
    return json.loads(blob[20 : 20 + json_length].decode("utf-8"))


def json_value(value: Any) -> Any:
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    if isinstance(value, dict):
        return {str(key): json_value(item) for key, item in value.items()}
    if hasattr(value, "to_list"):
        return json_value(value.to_list())
    try:
        return [json_value(item) for item in value]
    except TypeError:
        return str(value)


def node_local_matrix(node: dict[str, Any]) -> Matrix:
    if "matrix" in node:
        values = [float(value) for value in node["matrix"]]
        return Matrix(tuple(tuple(values[column * 4 + row] for column in range(4)) for row in range(4)))
    translation = Vector(tuple(float(value) for value in node.get("translation", (0.0, 0.0, 0.0))))
    rotation_values = [float(value) for value in node.get("rotation", (0.0, 0.0, 0.0, 1.0))]
    rotation = Quaternion((rotation_values[3], rotation_values[0], rotation_values[1], rotation_values[2]))
    scale_values = tuple(float(value) for value in node.get("scale", (1.0, 1.0, 1.0)))
    scale = Matrix.Diagonal((*scale_values, 1.0))
    return Matrix.Translation(translation) @ rotation.to_matrix().to_4x4() @ scale


def source_node_contract(gltf: dict[str, Any]) -> dict[str, Any]:
    nodes = gltf.get("nodes", [])
    parents: dict[int, int] = {}
    for parent_index, node in enumerate(nodes):
        for child_index in node.get("children", []):
            parents[int(child_index)] = parent_index
    world_cache: dict[int, Matrix] = {}

    def world_matrix(index: int) -> Matrix:
        if index not in world_cache:
            local = node_local_matrix(nodes[index])
            world_cache[index] = world_matrix(parents[index]) @ local if index in parents else local
        return world_cache[index]

    name_counts = Counter(node.get("name", "") for node in nodes)
    by_name = {node.get("name", ""): (index, node) for index, node in enumerate(nodes)}
    sensors: dict[str, Any] = {}
    for index, node in enumerate(nodes):
        name = node.get("name", "")
        if not name.startswith("SENSOR_"):
            continue
        gltf_world = world_matrix(index)
        source_origin = gltf_world @ Vector((0.0, 0.0, 0.0, 1.0))
        expected_blender = GLTF_TO_BLENDER @ source_origin
        expected_blender_matrix = GLTF_TO_BLENDER @ gltf_world @ GLTF_TO_BLENDER.inverted()
        parent_index = parents.get(index)
        sensors[name] = {
            "parent": nodes[parent_index].get("name", "") if parent_index is not None else None,
            "local_scale": [float(value) for value in node.get("scale", (1.0, 1.0, 1.0))],
            "extras": node.get("extras", {}),
            "gltf_world_position": [round(float(source_origin[i]), 9) for i in range(3)],
            "expected_blender_world_position": [round(float(expected_blender[i]), 9) for i in range(3)],
            "expected_blender_world_matrix_row_major": [
                round(float(expected_blender_matrix[row][column]), 9)
                for row in range(4)
                for column in range(4)
            ],
        }
    primitive_attributes = [
        primitive.get("attributes", {})
        for mesh in gltf.get("meshes", [])
        for primitive in mesh.get("primitives", [])
    ]
    return {
        "nodes": len(nodes),
        "meshes": len(gltf.get("meshes", [])),
        "materials": len(gltf.get("materials", [])),
        "textures": len(gltf.get("textures", [])),
        "images": len(gltf.get("images", [])),
        "duplicate_node_names": sorted(name for name, count in name_counts.items() if name and count > 1),
        "sensors": sensors,
        "process_zones": sorted(name for name in PROCESS_ZONES if name in by_name),
        "layer_groups": {
            name: len(by_name[name][1].get("children", []))
            for name in sorted(LAYER_GROUPS, key=lambda item: int(item.rsplit("L", 1)[1]))
            if name in by_name
        },
        "primitive_count": len(primitive_attributes),
        "primitives_with_texcoord_0": sum("TEXCOORD_0" in attributes for attributes in primitive_attributes),
    }


def clear_factory_scene() -> None:
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete(use_global=False)
    for datablocks in (bpy.data.meshes, bpy.data.curves, bpy.data.cameras, bpy.data.lights):
        for datablock in list(datablocks):
            if datablock.users == 0:
                datablocks.remove(datablock)


def import_glb(path: Path) -> None:
    supported = set(bpy.ops.import_scene.gltf.get_rna_type().properties.keys())
    required = {"filepath", "import_pack_images", "merge_vertices", "import_shading"}
    missing = sorted(required - supported)
    if missing:
        raise RuntimeError(f"Blender glTF operator is missing required properties: {missing}")
    requested: dict[str, Any] = {
        "filepath": str(path),
        "import_pack_images": True,
        "import_scene_as_collection": False,
        "import_scene_extras": True,
        "import_select_created_objects": True,
        "import_merge_material_slots": False,
        "import_shading": "NORMALS",
        "merge_vertices": False,
    }
    kwargs = {key: value for key, value in requested.items() if key in supported}
    result = bpy.ops.import_scene.gltf(**kwargs)
    if "FINISHED" not in result:
        raise RuntimeError(f"glTF import did not finish: {result}")
    bpy.context.view_layer.update()


def object_bounds(objects: list[bpy.types.Object]) -> tuple[Vector, Vector]:
    points = [obj.matrix_world @ Vector(corner) for obj in objects if obj.type == "MESH" for corner in obj.bound_box]
    if not points:
        raise ValueError("No mesh bounds were available after import")
    minimum = Vector(tuple(min(point[axis] for point in points) for axis in range(3)))
    maximum = Vector(tuple(max(point[axis] for point in points) for axis in range(3)))
    return minimum, maximum


def mesh_topology() -> dict[str, Any]:
    results: list[dict[str, Any]] = []
    totals = Counter()
    for mesh in sorted(bpy.data.meshes, key=lambda item: item.name):
        bm = bmesh.new()
        bm.from_mesh(mesh)
        boundary_edges = sum(1 for edge in bm.edges if edge.is_boundary)
        non_manifold_edges = sum(1 for edge in bm.edges if not edge.is_manifold)
        zero_area_faces = sum(1 for face in bm.faces if face.calc_area() <= 1e-12)
        item = {
            "mesh": mesh.name,
            "users": mesh.users,
            "vertices": len(bm.verts),
            "edges": len(bm.edges),
            "faces": len(bm.faces),
            "boundary_edges": boundary_edges,
            "non_manifold_edges": non_manifold_edges,
            "zero_area_faces": zero_area_faces,
            "uv_layers": [layer.name for layer in mesh.uv_layers],
        }
        results.append(item)
        for key in ("vertices", "edges", "faces", "boundary_edges", "non_manifold_edges", "zero_area_faces"):
            totals[key] += item[key]
        bm.free()
    return {"totals": dict(totals), "meshes": results}


def imported_contract(source: dict[str, Any]) -> dict[str, Any]:
    objects = list(bpy.data.objects)
    by_name = {obj.name: obj for obj in objects}
    object_name_counts = Counter(obj.name for obj in objects)
    sensors = {name: obj for name, obj in by_name.items() if name.startswith("SENSOR_")}
    source_sensors = source["sensors"]
    missing_sensor_names = sorted(set(source_sensors) - set(sensors))
    unexpected_sensor_names = sorted(set(sensors) - set(source_sensors))
    parent_mismatches: list[dict[str, Any]] = []
    scale_mismatches: list[dict[str, Any]] = []
    extras_mismatches: list[dict[str, Any]] = []
    position_mismatches: list[dict[str, Any]] = []
    matrix_mismatches: list[dict[str, Any]] = []
    sensor_records: list[dict[str, Any]] = []
    max_position_error = 0.0
    for name in sorted(set(source_sensors) & set(sensors)):
        obj = sensors[name]
        expected = source_sensors[name]
        actual_parent = obj.parent.name if obj.parent else None
        if actual_parent != expected["parent"]:
            parent_mismatches.append({"name": name, "expected": expected["parent"], "actual": actual_parent})
        actual_scale = [float(value) for value in obj.scale]
        scale_error = max(abs(actual_scale[index] - expected["local_scale"][index]) for index in range(3))
        if scale_error > SCALE_TOLERANCE:
            scale_mismatches.append({"name": name, "expected": expected["local_scale"], "actual": actual_scale})
        expected_extras = expected.get("extras", {})
        actual_extras = {key: json_value(obj.get(key)) for key in expected_extras}
        extras_diff = {
            key: {"expected": expected_extras.get(key), "actual": actual_extras.get(key)}
            for key in expected_extras
            if actual_extras.get(key) != expected_extras.get(key)
        }
        if extras_diff:
            extras_mismatches.append({"name": name, "fields": extras_diff})
        actual_position = obj.matrix_world.translation
        expected_position = Vector(expected["expected_blender_world_position"])
        position_error = float((actual_position - expected_position).length)
        max_position_error = max(max_position_error, position_error)
        if position_error > POSITION_TOLERANCE_M:
            position_mismatches.append(
                {
                    "name": name,
                    "expected": [round(float(value), 9) for value in expected_position],
                    "actual": [round(float(value), 9) for value in actual_position],
                    "error_m": position_error,
                }
            )
        actual_matrix = [float(obj.matrix_world[row][column]) for row in range(4) for column in range(4)]
        expected_matrix = expected["expected_blender_world_matrix_row_major"]
        matrix_error = max(abs(actual_matrix[index] - expected_matrix[index]) for index in range(16))
        if matrix_error > MATRIX_TOLERANCE:
            matrix_mismatches.append({"name": name, "max_abs_error": matrix_error})
        sensor_records.append(
            {
                "name": name,
                "parent": actual_parent,
                "location": [round(float(value), 9) for value in obj.location],
                "world_position": [round(float(value), 9) for value in actual_position],
                "scale": [round(float(value), 9) for value in obj.scale],
                "world_matrix_row_major": [round(float(obj.matrix_world[row][column]), 9) for row in range(4) for column in range(4)],
                "custom_properties": {key: json_value(value) for key, value in obj.items() if not key.startswith("_")},
            }
        )
    layer_groups = {
        name: {
            "exists": name in by_name,
            "children": sorted(child.name for child in by_name[name].children) if name in by_name else [],
        }
        for name in sorted(LAYER_GROUPS, key=lambda item: int(item.rsplit("L", 1)[1]))
    }
    body_sensors = [record for record in sensor_records if record["custom_properties"].get("group") == "BODY_TEMP"]
    return {
        "objects": len(objects),
        "mesh_objects": sum(obj.type == "MESH" for obj in objects),
        "mesh_datablocks": len(bpy.data.meshes),
        "materials": len(bpy.data.materials),
        "duplicate_object_names": sorted(name for name, count in object_name_counts.items() if count > 1),
        "sensor_count": len(sensors),
        "body_sensor_count": len(body_sensors),
        "missing_sensor_names": missing_sensor_names,
        "unexpected_sensor_names": unexpected_sensor_names,
        "parent_mismatches": parent_mismatches,
        "scale_mismatches": scale_mismatches,
        "extras_mismatches": extras_mismatches,
        "position_mismatches": position_mismatches,
        "matrix_mismatches": matrix_mismatches,
        "max_sensor_position_error_m": max_position_error,
        "process_zones": {name: name in by_name for name in sorted(PROCESS_ZONES)},
        "layer_groups": layer_groups,
        "sensor_records": sensor_records,
    }


def look_at(obj: bpy.types.Object, target: Vector) -> None:
    obj.rotation_euler = (target - obj.location).to_track_quat("-Z", "Y").to_euler()


def add_sun_light(name: str, location: Vector, target: Vector, energy: float, color: tuple[float, float, float]) -> bpy.types.Object:
    data = bpy.data.lights.new(name=name, type="SUN")
    data.energy = energy
    data.angle = math.radians(9.0)
    data.color = color
    obj = bpy.data.objects.new(name, data)
    bpy.context.scene.collection.objects.link(obj)
    obj.location = location
    look_at(obj, target)
    return obj


def render_clay_views(output_dir: Path, resolution: int, prefix: str = "P00") -> list[dict[str, Any]]:
    scene = bpy.context.scene
    structural_objects = [
        obj
        for obj in bpy.data.objects
        if obj.type == "MESH" and not obj.name.startswith(INTERNAL_RENDER_PREFIXES)
    ]
    minimum, maximum = object_bounds(structural_objects)
    center = (minimum + maximum) * 0.5
    size = maximum - minimum
    span = max(float(size.x), float(size.y), float(size.z), 1.0)
    hidden_state = {obj.name: bool(obj.hide_render) for obj in bpy.data.objects}
    for obj in bpy.data.objects:
        if obj.name.startswith(INTERNAL_RENDER_PREFIXES):
            obj.hide_render = True

    scene.render.engine = "BLENDER_EEVEE"
    scene.render.resolution_x = resolution
    scene.render.resolution_y = resolution
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = "PNG"
    scene.render.film_transparent = False
    try:
        scene.view_settings.view_transform = "AgX"
    except TypeError:
        pass
    scene.view_settings.exposure = 0.7
    scene.view_settings.gamma = 1.0
    scene.world.use_nodes = True
    background = scene.world.node_tree.nodes.get("Background")
    if background:
        background.inputs["Color"].default_value = (0.018, 0.026, 0.034, 1.0)
        background.inputs["Strength"].default_value = 0.5

    clay = bpy.data.materials.new("P00_CLAY_OVERRIDE")
    clay.diffuse_color = (0.42, 0.45, 0.44, 1.0)
    clay.use_nodes = True
    principled = clay.node_tree.nodes.get("Principled BSDF")
    principled.inputs["Base Color"].default_value = (0.42, 0.45, 0.44, 1.0)
    principled.inputs["Metallic"].default_value = 0.08
    principled.inputs["Roughness"].default_value = 0.72
    scene.view_layers[0].material_override = clay

    camera_data = bpy.data.cameras.new("P00_FIXED_CAMERA")
    camera_data.type = "ORTHO"
    camera = bpy.data.objects.new("P00_FIXED_CAMERA", camera_data)
    scene.collection.objects.link(camera)
    scene.camera = camera
    distance = span * 2.2
    add_sun_light("P00_KEY", center + Vector((span * 0.75, -span * 1.10, span * 0.90)), center, 3.0, (1.0, 0.89, 0.78))
    add_sun_light("P00_FILL", center + Vector((-span * 0.90, -span * 0.35, span * 0.30)), center, 1.25, (0.76, 0.86, 1.0))
    add_sun_light("P00_RIM", center + Vector((span * 0.20, span * 1.10, span * 1.00)), center, 2.1, (0.55, 0.72, 1.0))

    views = {
        "front": (center + Vector((0.0, -distance, 0.0)), max(float(size.x), float(size.z)) * 1.16),
        "back": (center + Vector((0.0, distance, 0.0)), max(float(size.x), float(size.z)) * 1.16),
        "left": (center + Vector((-distance, 0.0, 0.0)), max(float(size.y), float(size.z)) * 1.16),
        "right": (center + Vector((distance, 0.0, 0.0)), max(float(size.y), float(size.z)) * 1.16),
        "top": (center + Vector((0.0, 0.0, distance)), max(float(size.x), float(size.y)) * 1.18),
    }
    render_dir = output_dir / "renders"
    render_dir.mkdir(parents=True, exist_ok=True)
    results: list[dict[str, Any]] = []
    for name, (location, ortho_scale) in views.items():
        camera.location = location
        camera_data.ortho_scale = max(ortho_scale, 1.0)
        camera_data.lens = 50.0
        look_at(camera, center)
        output_path = render_dir / f"{prefix}_{name}.png"
        scene.render.filepath = str(output_path)
        bpy.ops.render.render(write_still=True)
        results.append(
            {
                "view": name,
                "path": str(output_path),
                "camera_location": [round(float(value), 6) for value in camera.location],
                "camera_rotation_euler": [round(float(value), 9) for value in camera.rotation_euler],
                "orthographic_scale": float(camera_data.ortho_scale),
                "sha256": sha256_file(output_path),
            }
        )
    scene.view_layers[0].material_override = None
    for name, hidden in hidden_state.items():
        if name in bpy.data.objects:
            bpy.data.objects[name].hide_render = hidden
    return results


def build_assertions(source: dict[str, Any], imported: dict[str, Any]) -> list[dict[str, Any]]:
    layers_ok = all(
        item["exists"] and len(item["children"]) == 8
        for item in imported["layer_groups"].values()
    )
    checks = [
        ("source_has_unique_node_names", not source["duplicate_node_names"], source["duplicate_node_names"]),
        ("source_sensor_count_115", len(source["sensors"]) == EXPECTED_SENSOR_COUNT, len(source["sensors"])),
        ("source_has_no_texcoord_0", source["primitives_with_texcoord_0"] == 0, source["primitives_with_texcoord_0"]),
        ("import_sensor_count_115", imported["sensor_count"] == EXPECTED_SENSOR_COUNT, imported["sensor_count"]),
        ("import_body_sensor_count_80", imported["body_sensor_count"] == EXPECTED_BODY_SENSOR_COUNT, imported["body_sensor_count"]),
        ("import_object_count_matches_source", imported["objects"] == source["nodes"], {"expected": source["nodes"], "actual": imported["objects"]}),
        ("import_mesh_datablocks_match_source", imported["mesh_datablocks"] == source["meshes"], {"expected": source["meshes"], "actual": imported["mesh_datablocks"]}),
        ("import_materials_match_source", imported["materials"] == source["materials"], {"expected": source["materials"], "actual": imported["materials"]}),
        ("sensor_names_preserved", not imported["missing_sensor_names"] and not imported["unexpected_sensor_names"], {"missing": imported["missing_sensor_names"], "unexpected": imported["unexpected_sensor_names"]}),
        ("sensor_parents_preserved", not imported["parent_mismatches"], imported["parent_mismatches"][:8]),
        ("sensor_scales_preserved", not imported["scale_mismatches"], imported["scale_mismatches"][:8]),
        ("sensor_extras_preserved", not imported["extras_mismatches"], imported["extras_mismatches"][:8]),
        ("sensor_positions_preserved", not imported["position_mismatches"], {"max_error_m": imported["max_sensor_position_error_m"], "examples": imported["position_mismatches"][:8]}),
        ("sensor_world_matrices_preserved", not imported["matrix_mismatches"], imported["matrix_mismatches"][:8]),
        ("five_process_zones_preserved", all(imported["process_zones"].values()), imported["process_zones"]),
        ("ten_layer_groups_with_eight_children", layers_ok, {name: len(item["children"]) for name, item in imported["layer_groups"].items()}),
        ("no_duplicate_blender_object_names", not imported["duplicate_object_names"], imported["duplicate_object_names"]),
    ]
    return [{"id": check_id, "ok": bool(ok), "detail": detail} for check_id, ok, detail in checks]


def main() -> int:
    args = parse_args()
    input_path = args.input.resolve()
    output_dir = args.output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    if not input_path.is_file():
        raise FileNotFoundError(input_path)
    source_hash = sha256_file(input_path)
    gltf = read_glb_json(input_path)
    source = source_node_contract(gltf)

    if abs(float(bpy.context.scene.unit_settings.scale_length) - 1.0) > 1e-12:
        raise RuntimeError(f"Factory scene scale_length must be 1.0 before glTF import, got {bpy.context.scene.unit_settings.scale_length}")
    clear_factory_scene()
    import_glb(input_path)
    scene = bpy.context.scene
    scene.unit_settings.system = "METRIC"
    scene.unit_settings.length_unit = "METERS"
    scene.unit_settings.scale_length = 1.0
    imported = imported_contract(source)
    minimum, maximum = object_bounds(list(bpy.data.objects))
    topology = mesh_topology()
    assertions = build_assertions(source, imported)
    assertions.insert(0, {"id": "input_sha_matches_locked_glb", "ok": source_hash == EXPECTED_SOURCE_SHA256, "detail": {"expected": EXPECTED_SOURCE_SHA256, "actual": source_hash}})
    source_hash_after_import = sha256_file(input_path)
    assertions.insert(1, {"id": "source_glb_unchanged_after_import", "ok": source_hash_after_import == source_hash, "detail": {"before": source_hash, "after": source_hash_after_import}})
    status = "pass" if all(item["ok"] for item in assertions) else "fail"

    report_path = output_dir / "p00_scene_audit.json"
    checkpoint_path = output_dir / "P00_SOURCE_LOCKED.blend"
    scene["bf3d_stage"] = "P00_SOURCE_LOCKED"
    scene["bf3d_source_glb"] = str(input_path)
    scene["bf3d_source_sha256"] = source_hash
    scene["bf3d_audit_status"] = status
    scene["bf3d_audit_report"] = str(report_path)
    checkpoint = None
    if status == "pass":
        bpy.ops.wm.save_as_mainfile(filepath=str(checkpoint_path), check_existing=False)
        checkpoint = {"path": str(checkpoint_path), "bytes": checkpoint_path.stat().st_size, "sha256": sha256_file(checkpoint_path)}

    renders: list[dict[str, Any]] = []
    render_error = None
    try:
        renders = render_clay_views(output_dir, max(256, min(args.resolution, 2048)))
    except Exception as exc:  # noqa: BLE001 - preserve the audit even if rendering fails
        render_error = {"type": type(exc).__name__, "message": str(exc), "traceback": traceback.format_exc()}
        status = "fail"

    report = {
        "schema_version": 1,
        "stage": "P00_SOURCE_LOCKED",
        "status": status,
        "input": {"path": str(input_path), "bytes": input_path.stat().st_size, "sha256": source_hash},
        "checkpoint": checkpoint,
        "blender": {
            "version": bpy.app.version_string,
            "build_hash": bpy.app.build_hash.decode("ascii", "replace") if isinstance(bpy.app.build_hash, bytes) else str(bpy.app.build_hash),
            "binary_path": bpy.app.binary_path,
            "background": bool(bpy.app.background),
        },
        "coordinates": {
            "scene_unit_system": scene.unit_settings.system,
            "scene_length_unit": scene.unit_settings.length_unit,
            "scale_length": scene.unit_settings.scale_length,
            "gltf_to_blender_position": "(x, y, z) -> (x, -z, y)",
            "aabb_min": [round(float(value), 9) for value in minimum],
            "aabb_max": [round(float(value), 9) for value in maximum],
            "aabb_size": [round(float(value), 9) for value in maximum - minimum],
        },
        "source_contract": {key: value for key, value in source.items() if key != "sensors"},
        "import_contract": imported,
        "topology": topology,
        "assertions": assertions,
        "renders": renders,
        "render_error": render_error,
        "notes": [
            "P00 is an imported audit checkpoint, not an optimized or production-exported model.",
            "Boundary/non-manifold counts are recorded as a baseline and are not automatically treated as defects.",
            "The source GLB has no TEXCOORD_0; no professional texture claim is permitted at P00.",
        ],
    }
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": status, "report": str(report_path), "checkpoint": str(checkpoint_path), "renders": len(renders)}, ensure_ascii=False, indent=2))
    return 0 if status == "pass" else 2


if __name__ == "__main__":
    raise SystemExit(main())
