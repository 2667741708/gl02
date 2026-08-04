"""Create non-destructive GL02 temperature-layer overlay meshes for L7-L16.

This Blender 5.2 script does not split or edit the five production shell meshes.
It adds ten lightweight parametric overlay bands that follow the locked
approximate furnace profile.  Each band is an independent object/material under
an independent layer group so Three.js can select, recolor, and radially scale
one layer without opening cracks in the production shell.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import sys
from pathlib import Path
from typing import Any

import bpy
from mathutils import Vector


AUDIT_DIR = Path(__file__).resolve().parent
UV_DIR = Path(__file__).resolve().parents[2] / "bf3d-uv-bake" / "scripts"
MATERIAL_DIR = Path(__file__).resolve().parents[2] / "bf3d-industrial-materials" / "scripts"
sys.path[:0] = [str(AUDIT_DIR), str(UV_DIR), str(MATERIAL_DIR)]
import p00_import_audit as p00  # noqa: E402
import p21_shaft_bake_test as p21  # noqa: E402
import p30_shell_material_candidate as p30  # noqa: E402


EXPECTED_PROFILE_SHA256 = "39e3739d7a73563b48eab5a5e75aa51826b45e9dff258d65cab50342de215172"
EXPECTED_SENSOR_LAYOUT_SHA256 = "ff65f0ffc328f96548a1a3a0be517ada9030b2f47207fb995c8e27d91dc661ef"
EXPECTED_LAYERS = tuple(f"L{number}" for number in range(7, 17))
EXPECTED_SECTORS = tuple("ABCDEFGH")
ROOT_NAME = "BF3D_TEMPERATURE_LAYER_SEGMENTS"
COLLECTION_NAME = "BF3D_TEMPERATURE_LAYER_OVERLAYS"
GROUP_PREFIX = "GL02_FURNACE_TEMP_LAYER_"
BAND_PREFIX = "APPROX_GL02_TEMP_LAYER_BAND_"
MATERIAL_PREFIX = "BF3D_TEMP_LAYER_HIGHLIGHT_"
ALLOWED_PARENT_STAGES = {
    "P30_MATERIAL_APPROVED",
    "P32_EQUIPMENT_MATERIAL_CANDIDATE",
    "P32_EQUIPMENT_MATERIAL_APPROVED",
    "P35_DETAIL_GEOMETRY_CANDIDATE",
    "P35_DETAIL_GEOMETRY_APPROVED",
    "P40_FIXED_LOOKDEV_CANDIDATE",
    "P40_LOOKDEV_APPROVED",
}
APPROVED_PARENT_STAGES = {
    "P30_MATERIAL_APPROVED",
    "P32_EQUIPMENT_MATERIAL_APPROVED",
    "P35_DETAIL_GEOMETRY_APPROVED",
    "P40_LOOKDEV_APPROVED",
}
PROFILE_POINT_RE = re.compile(
    r"\{\s*h_m:\s*([-+]?[0-9]*\.?[0-9]+)\s*,\s*r_m:\s*([-+]?[0-9]*\.?[0-9]+)"
)
LAYER_RE = re.compile(
    r"\{\s*layer:\s*(L(?:[7-9]|1[0-6]))\s*,\s*height_m:\s*([-+]?[0-9]*\.?[0-9]+)"
    r"\s*,\s*area:\s*\"([^\"]+)\""
)
PREVIEW_COLORS = (
    "#1C8D78",
    "#38A899",
    "#5BB7A3",
    "#D09A35",
    "#DAAE4F",
    "#D47E35",
    "#C55D42",
    "#A64C54",
    "#826086",
    "#6277A2",
)


def parse_args() -> argparse.Namespace:
    argv = sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else []
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-glb", required=True, type=Path)
    parser.add_argument("--profile-yaml", required=True, type=Path)
    parser.add_argument("--sensor-layout-yaml", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--segments", type=int, default=64)
    parser.add_argument("--offset-m", type=float, default=0.06)
    parser.add_argument("--preview-resolution", type=int, default=960)
    parser.add_argument("--skip-preview", action="store_true")
    return parser.parse_args(argv)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def round_floats(values: list[float] | tuple[float, ...], digits: int = 6) -> list[float]:
    return [round(float(value), digits) for value in values]


def parse_profile(path: Path) -> list[tuple[float, float]]:
    points = [
        (float(height), float(radius))
        for height, radius in PROFILE_POINT_RE.findall(path.read_text(encoding="utf-8"))
    ]
    if len(points) < 2 or points != sorted(points):
        raise RuntimeError(f"Could not parse a monotonic furnace profile from {path}")
    return points


def parse_layers(path: Path) -> list[dict[str, Any]]:
    layers = [
        {"layer_id": layer, "height_m": float(height), "area": area}
        for layer, height, area in LAYER_RE.findall(path.read_text(encoding="utf-8"))
    ]
    if tuple(item["layer_id"] for item in layers) != EXPECTED_LAYERS:
        raise RuntimeError(f"Expected L7-L16 in order, got {[item['layer_id'] for item in layers]}")
    return layers


def radius_at(height_m: float, profile: list[tuple[float, float]]) -> float:
    if not profile[0][0] <= height_m <= profile[-1][0]:
        raise ValueError(f"Height {height_m} is outside the furnace profile")
    for (h0, r0), (h1, r1) in zip(profile, profile[1:]):
        if h0 <= height_m <= h1:
            factor = 0.0 if h1 == h0 else (height_m - h0) / (h1 - h0)
            return r0 + factor * (r1 - r0)
    return profile[-1][1]


def layer_boundaries(layers: list[dict[str, Any]]) -> list[dict[str, Any]]:
    heights = [float(item["height_m"]) for item in layers]
    boundaries = [(heights[index] + heights[index + 1]) * 0.5 for index in range(len(heights) - 1)]
    lower = heights[0] - (heights[1] - heights[0]) * 0.5
    upper = heights[-1] + (heights[-1] - heights[-2]) * 0.5
    result = []
    for index, layer in enumerate(layers):
        item = dict(layer)
        item["lower_m"] = lower if index == 0 else boundaries[index - 1]
        item["upper_m"] = upper if index == len(layers) - 1 else boundaries[index]
        item["thickness_m"] = item["upper_m"] - item["lower_m"]
        result.append(item)
    return result


def matrix_values(obj: bpy.types.Object) -> list[float]:
    return [round(float(obj.matrix_world[row][column]), 9) for row in range(4) for column in range(4)]


def original_snapshot() -> dict[str, Any]:
    objects = {}
    for obj in sorted(bpy.data.objects, key=lambda item: item.name):
        record: dict[str, Any] = {
            "type": obj.type,
            "parent": obj.parent.name if obj.parent else None,
            "matrix": matrix_values(obj),
        }
        if obj.type == "MESH":
            record["mesh"] = obj.data.name
            record["geometry_sha256"] = p21.geometry_sha256(obj.data)
            record["uv_sha256"] = p21.uv_sha256(obj.data)
            record["materials"] = [slot.material.name if slot.material else None for slot in obj.material_slots]
        objects[obj.name] = record
    return {
        "objects": objects,
        "materials": {material.name: p30.material_hash(material) for material in bpy.data.materials},
    }


def compare_original_snapshot(before: dict[str, Any]) -> dict[str, Any]:
    after = original_snapshot()
    changed_objects = []
    missing_objects = []
    for name, record in before["objects"].items():
        if name not in after["objects"]:
            missing_objects.append(name)
        elif after["objects"][name] != record:
            changed_objects.append({"name": name, "before": record, "after": after["objects"][name]})
    changed_materials = [
        name
        for name, digest in before["materials"].items()
        if name not in after["materials"] or after["materials"][name] != digest
    ]
    return {
        "missing_objects": missing_objects,
        "changed_objects": changed_objects,
        "changed_materials": changed_materials,
    }


def set_property_block(target: Any, values: dict[str, Any]) -> None:
    for key, value in values.items():
        target[key] = value


def create_collection() -> bpy.types.Collection:
    if COLLECTION_NAME in bpy.data.collections:
        raise RuntimeError(f"Reserved collection already exists: {COLLECTION_NAME}")
    collection = bpy.data.collections.new(COLLECTION_NAME)
    bpy.context.scene.collection.children.link(collection)
    return collection


def create_empty(name: str, collection: bpy.types.Collection, parent: bpy.types.Object | None = None) -> bpy.types.Object:
    if name in bpy.data.objects:
        raise RuntimeError(f"Reserved object already exists: {name}")
    obj = bpy.data.objects.new(name, None)
    collection.objects.link(obj)
    obj.parent = parent
    obj.empty_display_type = "PLAIN_AXES"
    obj.empty_display_size = 0.35
    return obj


def create_layer_material(layer_id: str) -> bpy.types.Material:
    name = f"{MATERIAL_PREFIX}{layer_id}"
    if name in bpy.data.materials:
        raise RuntimeError(f"Reserved material already exists: {name}")
    material = bpy.data.materials.new(name)
    material.use_nodes = True
    nodes = material.node_tree.nodes
    links = material.node_tree.links
    nodes.clear()
    output = nodes.new("ShaderNodeOutputMaterial")
    output.name = "P36_OUTPUT"
    principled = nodes.new("ShaderNodeBsdfPrincipled")
    principled.name = "P36_PRINCIPLED"
    principled.inputs["Base Color"].default_value = (0.158, 0.350, 0.410, 1.0)
    principled.inputs["Metallic"].default_value = 0.12
    principled.inputs["Roughness"].default_value = 0.38
    principled.inputs["Alpha"].default_value = 0.42
    emission = principled.inputs.get("Emission Color") or principled.inputs.get("Emission")
    if emission is not None:
        emission.default_value = (0.035, 0.150, 0.175, 1.0)
    if "Emission Strength" in principled.inputs:
        principled.inputs["Emission Strength"].default_value = 0.45
    links.new(principled.outputs["BSDF"], output.inputs["Surface"])
    material.diffuse_color = (0.158, 0.350, 0.410, 0.42)
    set_property_block(
        material,
        {
            "bf3d_role": "temperature_layer_independent_highlight_material",
            "layer_id": layer_id,
            "default_state": "off",
            "runtime_tones": "normal:#32D6A0,warn:#F2B84B,bad:#E5534B,nodata:#6F8790",
        },
    )
    return material


def band_ring_heights(
    layer: dict[str, Any], profile: list[tuple[float, float]]
) -> list[float]:
    values = {float(layer["lower_m"]), float(layer["height_m"]), float(layer["upper_m"])}
    values.update(height for height, _ in profile if layer["lower_m"] < height < layer["upper_m"])
    return sorted(values)


def create_band_mesh(
    layer: dict[str, Any],
    profile: list[tuple[float, float]],
    segments: int,
    offset_m: float,
) -> tuple[bpy.types.Mesh, dict[str, Any]]:
    layer_id = str(layer["layer_id"])
    ring_heights = band_ring_heights(layer, profile)
    vertices: list[tuple[float, float, float]] = []
    faces: list[tuple[int, int, int, int]] = []
    for height_m in ring_heights:
        radius = radius_at(height_m, profile) + offset_m
        z = height_m - 20.0
        for sector in range(segments):
            angle = math.tau * sector / segments
            vertices.append((radius * math.cos(angle), radius * math.sin(angle), z))
    for ring in range(len(ring_heights) - 1):
        lower_start = ring * segments
        upper_start = (ring + 1) * segments
        for sector in range(segments):
            next_sector = (sector + 1) % segments
            faces.append(
                (
                    lower_start + sector,
                    lower_start + next_sector,
                    upper_start + next_sector,
                    upper_start + sector,
                )
            )
    mesh = bpy.data.meshes.new(f"{BAND_PREFIX}{layer_id}_MESH")
    mesh.from_pydata(vertices, [], faces)
    mesh.update(calc_edges=True)
    uv_layer = mesh.uv_layers.new(name="P36_LAYER_UV", do_init=False)
    band_height = float(layer["upper_m"]) - float(layer["lower_m"])
    for ring in range(len(ring_heights) - 1):
        v0 = (ring_heights[ring] - float(layer["lower_m"])) / band_height
        v1 = (ring_heights[ring + 1] - float(layer["lower_m"])) / band_height
        for sector in range(segments):
            polygon = mesh.polygons[ring * segments + sector]
            u0 = sector / segments
            u1 = (sector + 1) / segments
            for loop_index, uv in zip(polygon.loop_indices, ((u0, v0), (u1, v0), (u1, v1), (u0, v1))):
                uv_layer.uv[loop_index].vector = uv
            polygon.use_smooth = True
    mesh.validate(verbose=False, clean_customdata=False)
    mesh.update(calc_edges=True)
    metadata = {
        "ring_heights_m": round_floats(ring_heights),
        "ring_radii_m": round_floats([radius_at(height, profile) + offset_m for height in ring_heights]),
        "vertices": len(mesh.vertices),
        "edges": len(mesh.edges),
        "faces": len(mesh.polygons),
        "triangles": len(mesh.polygons) * 2,
        "uv_layers": [uv.name for uv in mesh.uv_layers],
        "geometry_sha256": p21.geometry_sha256(mesh),
        "uv_sha256": p21.uv_sha256(mesh),
    }
    return mesh, metadata


def create_layers(
    collection: bpy.types.Collection,
    profile: list[tuple[float, float]],
    layers: list[dict[str, Any]],
    segments: int,
    offset_m: float,
    profile_sha: str,
    sensor_layout_sha: str,
) -> tuple[bpy.types.Object, list[dict[str, Any]]]:
    root = create_empty(ROOT_NAME, collection)
    set_property_block(
        root,
        {
            "bf3d_role": "temperature_layer_segmentation_root",
            "furnace_id": "GL02",
            "coordinate_confidence": "approximate_until_real_cad_dimensions",
            "geometry_mode": "non_destructive_overlay_not_shell_split",
            "layer_range": "L7-L16",
            "layer_count": 10,
            "default_visible": False,
            "profile_sha256": profile_sha,
            "sensor_layout_sha256": sensor_layout_sha,
            "blender_radial_axes": "XY",
            "threejs_radial_axes": "XZ",
            "interpretation": "diagnostic_overlay_not_physical_shell_motion",
        },
    )
    records = []
    for layer in layers:
        layer_id = str(layer["layer_id"])
        group_name = f"{GROUP_PREFIX}{layer_id}"
        band_name = f"{BAND_PREFIX}{layer_id}"
        sensor_group_name = f"GL02_SENSOR_LAYER_{layer_id}"
        group = create_empty(group_name, collection, root)
        material = create_layer_material(layer_id)
        mesh, mesh_info = create_band_mesh(layer, profile, segments, offset_m)
        band = bpy.data.objects.new(band_name, mesh)
        collection.objects.link(band)
        band.parent = group
        band.data.materials.append(material)
        band.hide_render = True
        band.hide_viewport = True
        common = {
            "layer_id": layer_id,
            "height_m": float(layer["height_m"]),
            "frontend_y_m": float(layer["height_m"]) - 20.0,
            "area": str(layer["area"]),
            "band_lower_m": float(layer["lower_m"]),
            "band_upper_m": float(layer["upper_m"]),
            "band_thickness_m": float(layer["thickness_m"]),
            "shell_offset_m": offset_m,
            "source_sensor_group": sensor_group_name,
            "expected_sensor_count": 8,
            "default_visible": False,
        }
        set_property_block(
            group,
            {
                **common,
                "bf3d_role": "temperature_layer_group",
                "interaction_target": band_name,
            },
        )
        set_property_block(
            band,
            {
                **common,
                "bf3d_role": "temperature_layer_overlay_mesh",
                "interaction_mode": "radial_scale_and_state_color",
                "recommended_enter_scale": 1.12,
                "recommended_settled_scale": 1.04,
                "recommended_pulse_min": 1.025,
                "recommended_pulse_max": 1.055,
                "blender_radial_axes": "XY",
                "threejs_radial_axes": "XZ",
                "interpretation": "diagnostic_overlay_not_physical_shell_motion",
            },
        )
        records.append(
            {
                **common,
                "group": group_name,
                "band_object": band_name,
                "mesh": mesh.name,
                "material": material.name,
                **mesh_info,
            }
        )
    bpy.context.view_layer.update()
    return root, records


def color_from_hex(value: str) -> tuple[float, float, float, float]:
    value = value.lstrip("#")
    return tuple(int(value[index : index + 2], 16) / 255.0 for index in (0, 2, 4)) + (1.0,)


def look_at(obj: bpy.types.Object, target: Vector) -> None:
    obj.rotation_euler = (target - obj.location).to_track_quat("-Z", "Y").to_euler()


def add_area(
    collection: bpy.types.Collection,
    name: str,
    location: tuple[float, float, float],
    energy: float,
    size: float,
    color: tuple[float, float, float],
    target: Vector,
) -> bpy.types.Object:
    data = bpy.data.lights.new(name, "AREA")
    data.energy = energy
    data.shape = "DISK"
    data.size = size
    data.color = color
    obj = bpy.data.objects.new(name, data)
    collection.objects.link(obj)
    obj.location = location
    look_at(obj, target)
    return obj


def create_review_artifacts(
    output_dir: Path,
    collection: bpy.types.Collection,
    layer_records: list[dict[str, Any]],
    resolution: int,
) -> dict[str, Any]:
    for index, record in enumerate(layer_records):
        band = bpy.data.objects[record["band_object"]]
        band.hide_viewport = False
        band.hide_render = False
        material = bpy.data.materials[record["material"]]
        color = color_from_hex(PREVIEW_COLORS[index])
        principled = material.node_tree.nodes["P36_PRINCIPLED"]
        principled.inputs["Base Color"].default_value = color
        principled.inputs["Alpha"].default_value = 0.82
        emission = principled.inputs.get("Emission Color") or principled.inputs.get("Emission")
        if emission is not None:
            emission.default_value = color
        if "Emission Strength" in principled.inputs:
            principled.inputs["Emission Strength"].default_value = 0.26
        material.diffuse_color = (*color[:3], 0.82)

    review_collection = bpy.data.collections.new("P36_REVIEW_RIG")
    bpy.context.scene.collection.children.link(review_collection)
    target = Vector((0.0, 0.0, 4.6))
    camera_data = bpy.data.cameras.new("P36_REVIEW_CAMERA")
    camera = bpy.data.objects.new("P36_REVIEW_CAMERA", camera_data)
    review_collection.objects.link(camera)
    camera.data.type = "ORTHO"
    camera.data.ortho_scale = 25.0
    add_area(review_collection, "P36_REVIEW_KEY", (12.0, -16.0, 18.0), 1700.0, 9.0, (1.0, 0.87, 0.72), target)
    add_area(review_collection, "P36_REVIEW_FILL", (-13.0, -7.0, 9.0), 1100.0, 8.0, (0.58, 0.75, 1.0), target)
    add_area(review_collection, "P36_REVIEW_RIM", (7.0, 12.0, 13.0), 1250.0, 7.0, (0.46, 0.78, 1.0), target)
    scene = bpy.context.scene
    scene.camera = camera
    scene.render.engine = "BLENDER_EEVEE"
    scene.render.resolution_x = resolution
    scene.render.resolution_y = resolution
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = "PNG"
    scene.render.film_transparent = False
    scene.view_settings.view_transform = "AgX"
    scene.view_settings.look = "AgX - Medium High Contrast"
    world = scene.world or bpy.data.worlds.new("P36_REVIEW_WORLD")
    scene.world = world
    world.use_nodes = True
    background = world.node_tree.nodes.get("Background")
    if background:
        background.inputs["Color"].default_value = (0.008, 0.012, 0.016, 1.0)
        background.inputs["Strength"].default_value = 0.18
    render_dir = output_dir / "review"
    render_dir.mkdir(parents=True, exist_ok=True)
    renders = []
    for label, location in (
        ("front", (0.0, -31.0, 5.2)),
        ("oblique", (21.0, -24.0, 8.8)),
    ):
        camera.location = location
        look_at(camera, target)
        scene.render.filepath = str(render_dir / f"P36_L7_L16_{label}.png")
        bpy.ops.render.render(write_still=True)
        path = Path(scene.render.filepath)
        renders.append({"view": label, "path": str(path), "bytes": path.stat().st_size, "sha256": sha256_file(path)})
    scene["bf3d_review_only"] = True
    review_path = output_dir / "P36_LAYER_SEGMENTATION_REVIEW.blend"
    bpy.ops.wm.save_as_mainfile(filepath=str(review_path), check_existing=False)
    return {
        "path": str(review_path),
        "bytes": review_path.stat().st_size,
        "sha256": sha256_file(review_path),
        "renders": renders,
        "warning": "Review blend has all bands visible with diagnostic colors; it is not an export checkpoint.",
    }


def export_structural_smoke_glb(output_dir: Path) -> dict[str, Any]:
    """Export a non-production GLB to prove hidden layer nodes survive handoff."""
    path = output_dir / "P36_LAYER_SEGMENTATION_STRUCTURAL_SMOKE.glb"
    supported = set(bpy.ops.export_scene.gltf.get_rna_type().properties.keys())
    requested: dict[str, Any] = {
        "filepath": str(path),
        "check_existing": False,
        "export_format": "GLB",
        "use_selection": False,
        "use_visible": False,
        "use_renderable": False,
        "use_active_collection": False,
        "use_active_scene": True,
        "export_cameras": False,
        "export_lights": False,
        "export_extras": True,
        "export_yup": True,
        "export_apply": False,
        "export_animations": False,
        "export_texcoords": True,
        "export_normals": True,
        "export_materials": "EXPORT",
        "export_image_format": "AUTO",
        "export_unused_images": False,
        "export_unused_textures": False,
        "export_draco_mesh_compression_enable": False,
        "export_meshopt_compression_enable": False,
    }
    kwargs = {key: value for key, value in requested.items() if key in supported}
    result = bpy.ops.export_scene.gltf(**kwargs)
    if "FINISHED" not in result or not path.is_file():
        raise RuntimeError(f"P36 structural smoke GLB export failed: {result}")
    gltf = p00.read_glb_json(path)
    nodes = gltf.get("nodes", [])
    node_by_name = {node.get("name", ""): node for node in nodes}
    material_by_name = {material.get("name", ""): material for material in gltf.get("materials", [])}
    band_names = [f"{BAND_PREFIX}{layer}" for layer in EXPECTED_LAYERS]
    group_names = [f"{GROUP_PREFIX}{layer}" for layer in EXPECTED_LAYERS]
    material_names = [f"{MATERIAL_PREFIX}{layer}" for layer in EXPECTED_LAYERS]
    sensor_names = [name for name in node_by_name if name.startswith("SENSOR_")]
    checks = [
        {"id": "root_node_exported", "ok": ROOT_NAME in node_by_name},
        {"id": "ten_group_nodes_exported", "ok": all(name in node_by_name for name in group_names)},
        {
            "id": "ten_band_mesh_nodes_exported",
            "ok": all(name in node_by_name and "mesh" in node_by_name[name] for name in band_names),
        },
        {
            "id": "band_extras_exported",
            "ok": all(
                node_by_name[name].get("extras", {}).get("bf3d_role") == "temperature_layer_overlay_mesh"
                and node_by_name[name].get("extras", {}).get("layer_id") == layer
                and node_by_name[name].get("extras", {}).get("default_visible") is False
                for name, layer in zip(band_names, EXPECTED_LAYERS)
            ),
        },
        {
            "id": "ten_independent_blended_double_sided_materials_exported",
            "ok": all(
                name in material_by_name
                and material_by_name[name].get("alphaMode") == "BLEND"
                and material_by_name[name].get("doubleSided") is True
                for name in material_names
            ),
        },
        {"id": "all_115_sensor_nodes_exported", "ok": len(sensor_names) == 115, "detail": len(sensor_names)},
        {
            "id": "five_process_zone_nodes_exported",
            "ok": all(name in node_by_name for name in p00.PROCESS_ZONES),
        },
        {
            "id": "original_sensor_layer_groups_exported",
            "ok": all(f"GL02_SENSOR_LAYER_{layer}" in node_by_name for layer in EXPECTED_LAYERS),
        },
    ]
    return {
        "purpose": "structural_smoke_only_not_production_handoff",
        "path": str(path),
        "bytes": path.stat().st_size,
        "sha256": sha256_file(path),
        "node_count": len(nodes),
        "mesh_count": len(gltf.get("meshes", [])),
        "material_count": len(gltf.get("materials", [])),
        "checks": checks,
        "ok": all(bool(item["ok"]) for item in checks),
        "export_options": kwargs,
        "warning": "P30/P32 procedural materials are not yet baked; this file validates hierarchy/extras only.",
    }


def main() -> int:
    args = parse_args()
    source_glb = args.source_glb.resolve()
    profile_yaml = args.profile_yaml.resolve()
    sensor_layout_yaml = args.sensor_layout_yaml.resolve()
    output_dir = args.output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    input_blend = Path(bpy.data.filepath).resolve()
    if args.segments < 48 or args.segments > 128 or args.segments % 8:
        raise ValueError("--segments must be a multiple of 8 between 48 and 128")
    if not 0.02 <= args.offset_m <= 0.12:
        raise ValueError("--offset-m must be between 0.02 and 0.12 metres")
    for path in (source_glb, profile_yaml, sensor_layout_yaml, input_blend):
        if not path.is_file():
            raise FileNotFoundError(path)

    parent_stage = str(bpy.context.scene.get("bf3d_stage", ""))
    source_sha = sha256_file(source_glb)
    profile_sha = sha256_file(profile_yaml)
    sensor_layout_sha = sha256_file(sensor_layout_yaml)
    source_contract = p00.source_node_contract(p00.read_glb_json(source_glb))
    sensor_before = p00.imported_contract(source_contract)
    before = original_snapshot()
    profile = parse_profile(profile_yaml)
    layers = layer_boundaries(parse_layers(sensor_layout_yaml))
    reserved_names = {
        ROOT_NAME,
        *(f"{GROUP_PREFIX}{layer}" for layer in EXPECTED_LAYERS),
        *(f"{BAND_PREFIX}{layer}" for layer in EXPECTED_LAYERS),
    }
    collisions = sorted(reserved_names & set(bpy.data.objects))
    if collisions:
        raise RuntimeError(f"P36 reserved object names already exist: {collisions}")

    collection = create_collection()
    root, records = create_layers(
        collection,
        profile,
        layers,
        args.segments,
        args.offset_m,
        profile_sha,
        sensor_layout_sha,
    )
    sensor_after = p00.imported_contract(source_contract)
    original_diff = compare_original_snapshot(before)
    new_object_names = sorted({obj.name for obj in bpy.data.objects} - set(before["objects"]))
    expected_new_objects = sorted(
        [ROOT_NAME]
        + [f"{GROUP_PREFIX}{layer}" for layer in EXPECTED_LAYERS]
        + [f"{BAND_PREFIX}{layer}" for layer in EXPECTED_LAYERS]
    )
    total_vertices = sum(int(record["vertices"]) for record in records)
    total_triangles = sum(int(record["triangles"]) for record in records)
    sensor_group_checks = {}
    for layer_id in EXPECTED_LAYERS:
        group = bpy.data.objects.get(f"GL02_SENSOR_LAYER_{layer_id}")
        actual = sorted(child.name for child in group.children) if group else []
        expected = sorted(f"SENSOR_T_body_{layer_id}_{sector}" for sector in EXPECTED_SECTORS)
        sensor_group_checks[layer_id] = {"actual": actual, "expected": expected, "ok": actual == expected}
    continuous = all(
        abs(float(records[index]["band_upper_m"]) - float(records[index + 1]["band_lower_m"])) <= 1e-9
        for index in range(len(records) - 1)
    )
    transforms_identity = all(
        matrix_values(bpy.data.objects[record["band_object"]])
        == [1.0, 0.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 0.0, 1.0]
        for record in records
    )
    metadata_ok = all(
        bpy.data.objects[record["band_object"]].get("layer_id") == record["layer_id"]
        and bpy.data.objects[record["band_object"]].get("source_sensor_group")
        == f"GL02_SENSOR_LAYER_{record['layer_id']}"
        and bpy.data.objects[record["band_object"]].get("bf3d_role") == "temperature_layer_overlay_mesh"
        for record in records
    )
    assertions = [
        {"id": "input_stage_allowed", "ok": parent_stage in ALLOWED_PARENT_STAGES, "detail": parent_stage},
        {"id": "source_glb_matches_lock", "ok": source_sha == p00.EXPECTED_SOURCE_SHA256, "detail": source_sha},
        {"id": "profile_matches_lock", "ok": profile_sha == EXPECTED_PROFILE_SHA256, "detail": profile_sha},
        {"id": "sensor_layout_matches_lock", "ok": sensor_layout_sha == EXPECTED_SENSOR_LAYOUT_SHA256, "detail": sensor_layout_sha},
        {
            "id": "sensor_contract_unchanged",
            "ok": sensor_before["sensor_records"] == sensor_after["sensor_records"]
            and sensor_after["sensor_count"] == 115
            and sensor_after["body_sensor_count"] == 80,
        },
        {"id": "all_original_objects_unchanged", "ok": not original_diff["missing_objects"] and not original_diff["changed_objects"], "detail": original_diff},
        {"id": "all_original_materials_unchanged", "ok": not original_diff["changed_materials"], "detail": original_diff["changed_materials"]},
        {"id": "only_expected_objects_added", "ok": new_object_names == expected_new_objects, "detail": new_object_names},
        {"id": "ten_independent_layer_meshes", "ok": len(records) == 10 and len({record["mesh"] for record in records}) == 10},
        {"id": "ten_independent_layer_materials", "ok": len({record["material"] for record in records}) == 10},
        {"id": "layer_sensor_groups_are_exact_A_to_H", "ok": all(item["ok"] for item in sensor_group_checks.values()), "detail": sensor_group_checks},
        {"id": "bands_are_continuous_at_midpoint_boundaries", "ok": continuous},
        {
            "id": "each_sensor_height_is_inside_its_band",
            "ok": all(record["band_lower_m"] < record["height_m"] < record["band_upper_m"] for record in records),
        },
        {"id": "band_objects_have_identity_world_transforms", "ok": transforms_identity},
        {"id": "band_metadata_is_complete", "ok": metadata_ok},
        {
            "id": "web_performance_budget",
            "ok": total_vertices <= 3000 and total_triangles <= 4000 and len(records) == 10,
            "detail": {"vertices": total_vertices, "triangles": total_triangles, "draw_calls": 10, "materials": 10},
        },
        {
            "id": "default_visibility_is_off",
            "ok": all(
                bpy.data.objects[record["band_object"]].hide_render
                and bpy.data.objects[record["band_object"]].hide_viewport
                and bpy.data.objects[record["band_object"]].get("default_visible") is False
                for record in records
            ),
        },
        {
            "id": "profile_offset_is_exact",
            "ok": all(
                all(
                    abs(
                        radius
                        - (radius_at(height, profile) + args.offset_m)
                    )
                    <= 1e-6
                    for height, radius in zip(record["ring_heights_m"], record["ring_radii_m"])
                )
                for record in records
            ),
        },
    ]
    ok = all(bool(item["ok"]) for item in assertions)
    candidate = None
    review = None
    structural_smoke = None
    if ok:
        scene = bpy.context.scene
        scene["bf3d_stage"] = "P36_LAYER_SEGMENTATION_CANDIDATE"
        scene["bf3d_parent_stage"] = parent_stage
        scene["bf3d_parent_checkpoint"] = str(input_blend)
        scene["bf3d_change_dimension"] = "non_destructive_temperature_layer_overlays_L7_L16"
        scene["bf3d_layer_segmentation_root"] = root.name
        scene["bf3d_layer_count"] = 10
        scene["bf3d_layer_default_visibility"] = "off"
        scene["bf3d_approval_dependency"] = (
            "parent_checkpoint_approved" if parent_stage in APPROVED_PARENT_STAGES else "rerun_after_parent_stage_approval"
        )
        candidate_path = output_dir / "P36_LAYER_SEGMENTATION_CANDIDATE.blend"
        bpy.ops.wm.save_as_mainfile(filepath=str(candidate_path), check_existing=False)
        candidate = {
            "path": str(candidate_path),
            "bytes": candidate_path.stat().st_size,
            "sha256": sha256_file(candidate_path),
        }
        structural_smoke = export_structural_smoke_glb(output_dir)
        assertions.append(
            {
                "id": "structural_smoke_glb_preserves_layers_extras_and_sensors",
                "ok": bool(structural_smoke["ok"]),
                "detail": structural_smoke["checks"],
            }
        )
        ok = all(bool(item["ok"]) for item in assertions)
        if ok and not args.skip_preview:
            review = create_review_artifacts(output_dir, collection, records, args.preview_resolution)

    report = {
        "schema_version": 1,
        "stage": "P36_LAYER_SEGMENTATION_CANDIDATE",
        "status": "candidate_ready_for_visual_review" if ok else "fail",
        "input_checkpoint": {
            "path": str(input_blend),
            "sha256": sha256_file(input_blend),
            "stage": parent_stage,
            "approved_parent": parent_stage in APPROVED_PARENT_STAGES,
        },
        "candidate": candidate,
        "structural_smoke_glb": structural_smoke,
        "review": review,
        "source_assets": {
            "source_glb": {"path": str(source_glb), "sha256": source_sha},
            "profile_yaml": {"path": str(profile_yaml), "sha256": profile_sha},
            "sensor_layout_yaml": {"path": str(sensor_layout_yaml), "sha256": sensor_layout_sha},
        },
        "design": {
            "mode": "non_destructive_parametric_overlay",
            "original_shell_split": False,
            "segments_per_ring": args.segments,
            "shell_offset_m": args.offset_m,
            "boundary_rule": "midpoint_between_adjacent_sensor_heights; extrapolated_half_spacing_at_L7_and_L16",
            "radial_scale_rule": "Blender XY only; Three.js XZ only; never scale vertical axis",
            "default_visibility": "off",
            "interaction": "select one mesh, clone/use its independent material, show, recolor by state, animate radial scale",
            "interpretation": "diagnostic overlay, not real mechanical expansion",
        },
        "layers": records,
        "performance": {
            "added_vertices": total_vertices,
            "added_triangles": total_triangles,
            "added_mesh_objects": 10,
            "added_materials": 10,
            "maximum_active_runtime_draw_calls": 1,
            "all_layers_visible_review_draw_calls": 10,
        },
        "assertions": assertions,
        "approval": (
            "pending_fixed_camera_visual_review_and_parent_checkpoint_approval"
            if parent_stage not in APPROVED_PARENT_STAGES
            else "pending_fixed_camera_visual_review"
        ),
        "integration_note": (
            "This run is technical validation only; rerun the same script on P32/P35 APPROVED before GLB handoff."
            if parent_stage not in APPROVED_PARENT_STAGES
            else "Parent checkpoint is approved; candidate still requires P36 visual approval before GLB handoff."
        ),
    }
    report_path = output_dir / "p36_layer_segmentation_candidate.json"
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(
        json.dumps(
            {
                "status": report["status"],
                "candidate": candidate,
                "review": review,
                "report": str(report_path),
                "performance": report["performance"],
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0 if ok else 2


if __name__ == "__main__":
    raise SystemExit(main())
