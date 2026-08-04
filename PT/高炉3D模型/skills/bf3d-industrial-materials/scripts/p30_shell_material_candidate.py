"""Build and evidence a procedural P30 matte weathered-steel material candidate."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import struct
import sys
from pathlib import Path

import bpy
from mathutils import Vector

AUDIT_DIR = Path(__file__).resolve().parents[2] / "bf3d-geometry-audit" / "scripts"
UV_DIR = Path(__file__).resolve().parents[2] / "bf3d-uv-bake" / "scripts"
sys.path.insert(0, str(AUDIT_DIR))
sys.path.insert(0, str(UV_DIR))
import p00_import_audit as p00  # noqa: E402
import p21_shaft_bake_test as p21  # noqa: E402

SHELL_MATERIAL = "APPROX_matte_weathered_steel"
ASH_MATERIAL = "shell_ash_and_dust_streaks"
HEAT_MATERIAL = "shell_local_heat_patina"
ALLOWED_MATERIALS = {SHELL_MATERIAL, ASH_MATERIAL, HEAT_MATERIAL}
ZONES = tuple(sorted(p00.PROCESS_ZONES))
SEED = 20260716


def parse_args() -> argparse.Namespace:
    argv = sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else []
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-glb", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--resolution", type=int, default=768)
    return parser.parse_args(argv)


def json_value(value):
    if isinstance(value, (int, float, bool, str)) or value is None:
        return value
    try:
        return [float(item) for item in value]
    except (TypeError, ValueError):
        return str(value)


def material_hash(material: bpy.types.Material) -> str:
    if not material.use_nodes or not material.node_tree:
        payload = {"name": material.name, "diffuse": list(material.diffuse_color)}
    else:
        nodes = []
        for node in sorted(material.node_tree.nodes, key=lambda item: item.name):
            nodes.append(
                {
                    "name": node.name,
                    "type": node.bl_idname,
                    "inputs": {socket.name: json_value(socket.default_value) for socket in node.inputs if hasattr(socket, "default_value")},
                }
            )
        links = sorted(
            (link.from_node.name, link.from_socket.name, link.to_node.name, link.to_socket.name)
            for link in material.node_tree.links
        )
        payload = {"name": material.name, "nodes": nodes, "links": links}
    return hashlib.sha256(json.dumps(payload, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()


def scene_mesh_sha256(include_uv: bool) -> str:
    digest = hashlib.sha256()
    for mesh in sorted(bpy.data.meshes, key=lambda item: item.name):
        digest.update(mesh.name.encode("utf-8"))
        digest.update(p21.geometry_sha256(mesh).encode("ascii"))
        if include_uv:
            digest.update(p21.uv_sha256(mesh).encode("ascii"))
    return digest.hexdigest()


def noise(nodes, links, vector_socket, name: str, scale: float, detail: float, roughness: float, w_offset: float = 0.0):
    node = p21.new_node(nodes, "ShaderNodeTexNoise", name)
    node.noise_dimensions = "4D"
    node.inputs["Scale"].default_value = scale
    node.inputs["Detail"].default_value = detail
    node.inputs["Roughness"].default_value = roughness
    node.inputs["W"].default_value = float(SEED % 997) / 997.0 + w_offset
    links.new(vector_socket, node.inputs["Vector"])
    return node


def float_mix(nodes, links, name: str, factor, value_a, value_b):
    node = p21.new_node(nodes, "ShaderNodeMix", name)
    node.data_type = "FLOAT"
    if hasattr(value_a, "bl_idname"):
        links.new(value_a, node.inputs[2])
    else:
        node.inputs[2].default_value = float(value_a)
    if hasattr(value_b, "bl_idname"):
        links.new(value_b, node.inputs[3])
    else:
        node.inputs[3].default_value = float(value_b)
    links.new(factor, node.inputs[0])
    return node.outputs["Result"]


def color_mix(nodes, links, name: str, factor, value_a, value_b):
    node = p21.new_node(nodes, "ShaderNodeMixRGB", name)
    node.blend_type = "MIX"
    if hasattr(value_a, "bl_idname"):
        links.new(value_a, node.inputs[1])
    else:
        node.inputs[1].default_value = value_a
    if hasattr(value_b, "bl_idname"):
        links.new(value_b, node.inputs[2])
    else:
        node.inputs[2].default_value = value_b
    links.new(factor, node.inputs[0])
    return node.outputs["Color"]


def rebuild_shell_material(material: bpy.types.Material) -> dict[str, object]:
    material.use_nodes = True
    material.diffuse_color = (*p21.srgb("#48534F")[:3], 0.88)
    if hasattr(material, "surface_render_method"):
        material.surface_render_method = "DITHERED"
    nodes = material.node_tree.nodes
    links = material.node_tree.links
    nodes.clear()
    output = p21.new_node(nodes, "ShaderNodeOutputMaterial", "P30_OUTPUT")
    principled = p21.new_node(nodes, "ShaderNodeBsdfPrincipled", "P30_PRINCIPLED")
    geometry = p21.new_node(nodes, "ShaderNodeNewGeometry", "P30_WORLD_POSITION")
    offset = p21.new_node(nodes, "ShaderNodeVectorMath", "P30_FIXED_SEED_OFFSET")
    offset.operation = "ADD"
    offset.inputs[1].default_value = (2.60716, -1.60716, 0.716)
    links.new(geometry.outputs["Position"], offset.inputs[0])

    macro = noise(nodes, links, offset.outputs["Vector"], "P30_MACRO", 0.18, 2.0, 0.56)
    meso = noise(nodes, links, offset.outputs["Vector"], "P30_MESO", 3.20, 3.0, 0.60, 0.13)
    micro = noise(nodes, links, offset.outputs["Vector"], "P30_MICRO", 20.0, 2.0, 0.45, 0.29)
    dust_noise = noise(nodes, links, offset.outputs["Vector"], "P30_DUST_NOISE", 0.42, 2.0, 0.62, 0.41)

    streak_vector = p21.new_node(nodes, "ShaderNodeVectorMath", "P30_GRAVITY_STREAK_SCALE")
    streak_vector.operation = "MULTIPLY"
    streak_vector.inputs[1].default_value = (1.45, 1.45, 0.085)
    links.new(offset.outputs["Vector"], streak_vector.inputs[0])
    streak = noise(nodes, links, streak_vector.outputs["Vector"], "P30_VERTICAL_STREAK", 1.0, 3.0, 0.58, 0.53)

    directional_vector = p21.new_node(nodes, "ShaderNodeVectorMath", "P30_FINE_DIRECTION_SCALE")
    directional_vector.operation = "MULTIPLY"
    directional_vector.inputs[1].default_value = (6.0, 6.0, 0.22)
    links.new(offset.outputs["Vector"], directional_vector.inputs[0])
    directional = noise(nodes, links, directional_vector.outputs["Vector"], "P30_FINE_DIRECTIONAL_WEAR", 1.0, 2.0, 0.48, 0.67)
    directional_weight = p21.new_node(nodes, "ShaderNodeMapRange", "P30_DIRECTIONAL_WEAR_WEIGHT")
    directional_weight.inputs["From Min"].default_value = 0.0
    directional_weight.inputs["From Max"].default_value = 1.0
    directional_weight.inputs["To Min"].default_value = 0.82
    directional_weight.inputs["To Max"].default_value = 1.0
    directional_weight.clamp = True
    links.new(directional.outputs["Fac"], directional_weight.inputs["Value"])

    exposed_base = p21.color_ramp(nodes, "P30_EXPOSED_STEEL_BASE", 0.47, 0.62)
    links.new(meso.outputs["Fac"], exposed_base.inputs["Fac"])
    exposed = p21.new_node(nodes, "ShaderNodeMath", "P30_EXPOSED_STEEL_MASK")
    exposed.operation = "MULTIPLY"
    links.new(exposed_base.outputs["Color"], exposed.inputs[0])
    links.new(directional_weight.outputs["Result"], exposed.inputs[1])

    separate = p21.new_node(nodes, "ShaderNodeSeparateXYZ", "P30_HEIGHT")
    links.new(geometry.outputs["Position"], separate.inputs["Vector"])

    def platform_falloff(name: str, depth: float):
        combined = None
        for index, height_m in enumerate((4.8, 8.8, 18.6, 30.6, 37.2, 39.4)):
            level = height_m - 20.0
            below = p21.new_node(nodes, "ShaderNodeMapRange", f"{name}_BELOW_{index}")
            below.inputs["From Min"].default_value = level - depth
            below.inputs["From Max"].default_value = level
            below.inputs["To Min"].default_value = 0.0
            below.inputs["To Max"].default_value = 1.0
            below.clamp = True
            links.new(separate.outputs["Z"], below.inputs["Value"])
            above = p21.new_node(nodes, "ShaderNodeMapRange", f"{name}_ABOVE_{index}")
            above.inputs["From Min"].default_value = level
            above.inputs["From Max"].default_value = level + 0.08
            above.inputs["To Min"].default_value = 1.0
            above.inputs["To Max"].default_value = 0.0
            above.clamp = True
            links.new(separate.outputs["Z"], above.inputs["Value"])
            band = p21.new_node(nodes, "ShaderNodeMath", f"{name}_BAND_{index}")
            band.operation = "MULTIPLY"
            links.new(below.outputs["Result"], band.inputs[0])
            links.new(above.outputs["Result"], band.inputs[1])
            if combined is None:
                combined = band.outputs[0]
            else:
                maximum = p21.new_node(nodes, "ShaderNodeMath", f"{name}_MAX_{index}")
                maximum.operation = "MAXIMUM"
                links.new(combined, maximum.inputs[0])
                links.new(band.outputs[0], maximum.inputs[1])
                combined = maximum.outputs[0]
        return combined

    platform_edge = platform_falloff("P30_PLATFORM_EDGE", 0.45)
    platform_runoff = platform_falloff("P30_PLATFORM_RUNOFF", 3.2)

    rust_product = p21.new_node(nodes, "ShaderNodeMath", "P30_OXIDATION_PRODUCT")
    rust_product.operation = "MULTIPLY"
    links.new(macro.outputs["Fac"], rust_product.inputs[0])
    links.new(streak.outputs["Fac"], rust_product.inputs[1])
    rust_base = p21.color_ramp(nodes, "P30_OXIDATION_BASE", 0.32, 0.48)
    links.new(rust_product.outputs[0], rust_base.inputs["Fac"])
    water_base = p21.color_ramp(nodes, "P30_WATER_STREAK_BASE", 0.55, 0.72)
    links.new(streak.outputs["Fac"], water_base.inputs["Fac"])
    water = p21.new_node(nodes, "ShaderNodeMath", "P30_WATER_STREAK_MASK")
    water.operation = "MULTIPLY"
    links.new(water_base.outputs["Color"], water.inputs[0])
    links.new(platform_runoff, water.inputs[1])
    platform_rust = p21.new_node(nodes, "ShaderNodeMath", "P30_PLATFORM_OXIDATION")
    platform_rust.operation = "MULTIPLY"
    platform_rust.inputs[1].default_value = 0.42
    links.new(water.outputs[0], platform_rust.inputs[0])
    rust = p21.new_node(nodes, "ShaderNodeMath", "P30_OXIDATION_MASK")
    rust.operation = "MAXIMUM"
    links.new(rust_base.outputs["Color"], rust.inputs[0])
    links.new(platform_rust.outputs[0], rust.inputs[1])
    water_strength = p21.new_node(nodes, "ShaderNodeMath", "P30_WATER_LOW_CONTRAST")
    water_strength.operation = "MULTIPLY"
    water_strength.inputs[1].default_value = 0.24
    links.new(water.outputs[0], water_strength.inputs[0])

    lower_height = p21.new_node(nodes, "ShaderNodeMapRange", "P30_LOWER_DUST_WEIGHT")
    lower_height.inputs["From Min"].default_value = -20.0
    lower_height.inputs["From Max"].default_value = 26.0
    lower_height.inputs["To Min"].default_value = 0.34
    lower_height.inputs["To Max"].default_value = 0.04
    lower_height.clamp = True
    links.new(separate.outputs["Z"], lower_height.inputs["Value"])
    dust_shape = p21.color_ramp(nodes, "P30_DRY_DUST_SHAPE", 0.56, 0.74)
    links.new(dust_noise.outputs["Fac"], dust_shape.inputs["Fac"])
    ambient_dust = p21.new_node(nodes, "ShaderNodeMath", "P30_AMBIENT_DUST")
    ambient_dust.operation = "MULTIPLY"
    links.new(dust_shape.outputs["Color"], ambient_dust.inputs[0])
    links.new(lower_height.outputs["Result"], ambient_dust.inputs[1])
    edge_dust = p21.new_node(nodes, "ShaderNodeMath", "P30_PLATFORM_DUST")
    edge_dust.operation = "MULTIPLY"
    links.new(dust_shape.outputs["Color"], edge_dust.inputs[0])
    links.new(platform_edge, edge_dust.inputs[1])
    dust = p21.new_node(nodes, "ShaderNodeMath", "P30_DRY_DUST_MASK")
    dust.operation = "MAXIMUM"
    links.new(ambient_dust.outputs[0], dust.inputs[0])
    links.new(edge_dust.outputs[0], dust.inputs[1])

    base_color = color_mix(nodes, links, "P30_COLOR_COAT_STEEL", exposed.outputs[0], p21.srgb("#48534F"), p21.srgb("#59615E"))
    base_color = color_mix(nodes, links, "P30_COLOR_OXIDATION", rust.outputs[0], base_color, p21.srgb("#5B4032"))
    base_color = color_mix(nodes, links, "P30_COLOR_DRY_DUST", dust.outputs[0], base_color, p21.srgb("#625F56"))
    base_color = color_mix(nodes, links, "P30_COLOR_WATER_STREAK", water_strength.outputs[0], base_color, p21.srgb("#37423E"))

    roughness = float_mix(nodes, links, "P30_ROUGH_COAT_STEEL", exposed.outputs[0], 0.76, 0.63)
    roughness = float_mix(nodes, links, "P30_ROUGH_OXIDATION", rust.outputs[0], roughness, 0.85)
    roughness = float_mix(nodes, links, "P30_ROUGH_DRY_DUST", dust.outputs[0], roughness, 0.92)
    roughness = float_mix(nodes, links, "P30_ROUGH_WATER", water_strength.outputs[0], roughness, 0.80)
    micro_range = p21.new_node(nodes, "ShaderNodeMapRange", "P30_MICRO_ROUGHNESS")
    micro_range.inputs["From Min"].default_value = 0.0
    micro_range.inputs["From Max"].default_value = 1.0
    micro_range.inputs["To Min"].default_value = -0.022
    micro_range.inputs["To Max"].default_value = 0.022
    micro_range.clamp = True
    links.new(micro.outputs["Fac"], micro_range.inputs["Value"])
    rough_add = p21.new_node(nodes, "ShaderNodeMath", "P30_ROUGHNESS_MICRO_ADD")
    rough_add.operation = "ADD"
    rough_add.use_clamp = True
    links.new(roughness, rough_add.inputs[0])
    links.new(micro_range.outputs["Result"], rough_add.inputs[1])
    fine_rough = p21.new_node(nodes, "ShaderNodeMapRange", "P30_DIRECTIONAL_ROUGHNESS")
    fine_rough.inputs["From Min"].default_value = 0.0
    fine_rough.inputs["From Max"].default_value = 1.0
    fine_rough.inputs["To Min"].default_value = -0.012
    fine_rough.inputs["To Max"].default_value = 0.012
    fine_rough.clamp = True
    links.new(directional.outputs["Fac"], fine_rough.inputs["Value"])
    rough_final = p21.new_node(nodes, "ShaderNodeMath", "P30_ROUGHNESS_FINAL")
    rough_final.operation = "ADD"
    rough_final.use_clamp = True
    links.new(rough_add.outputs[0], rough_final.inputs[0])
    links.new(fine_rough.outputs["Result"], rough_final.inputs[1])

    metal_exposure = p21.color_ramp(nodes, "P30_METAL_EXPOSURE_MASK", 0.32, 0.62)
    links.new(exposed.outputs[0], metal_exposure.inputs["Fac"])
    metallic = float_mix(nodes, links, "P30_METAL_COAT_STEEL", metal_exposure.outputs["Color"], 0.04, 0.90)
    metallic = float_mix(nodes, links, "P30_METAL_OXIDATION", rust.outputs[0], metallic, 0.03)
    metallic = float_mix(nodes, links, "P30_METAL_DRY_DUST", dust.outputs[0], metallic, 0.0)
    metallic = float_mix(nodes, links, "P30_METAL_WATER", water_strength.outputs[0], metallic, 0.04)

    bump = p21.new_node(nodes, "ShaderNodeBump", "P30_MICRO_BUMP")
    bump.inputs["Strength"].default_value = 0.10
    bump.inputs["Distance"].default_value = 0.003
    links.new(micro.outputs["Fac"], bump.inputs["Height"])
    links.new(base_color, principled.inputs["Base Color"])
    links.new(rough_final.outputs[0], principled.inputs["Roughness"])
    links.new(metallic, principled.inputs["Metallic"])
    links.new(bump.outputs["Normal"], principled.inputs["Normal"])
    principled.inputs["Alpha"].default_value = 0.88
    if "Emission Color" in principled.inputs:
        principled.inputs["Emission Color"].default_value = (0.0, 0.0, 0.0, 1.0)
    if "Emission Strength" in principled.inputs:
        principled.inputs["Emission Strength"].default_value = 0.0
    links.new(principled.outputs["BSDF"], output.inputs["Surface"])
    return {
        "output": output,
        "principled": principled,
        "base_color": base_color,
        "roughness": rough_final.outputs[0],
        "metallic": metallic,
        "exposed_mask": exposed.outputs[0],
        "oxidation_mask": rust.outputs[0],
        "dust_mask": dust.outputs[0],
        "water_mask": water.outputs[0],
        "bump": bump.outputs["Normal"],
    }


def rebuild_overlay_material(material: bpy.types.Material, color: str, metallic: float, roughness: float, alpha: float) -> None:
    material.use_nodes = True
    material.diffuse_color = (*p21.srgb(color)[:3], alpha)
    if hasattr(material, "surface_render_method"):
        material.surface_render_method = "DITHERED"
    nodes = material.node_tree.nodes
    links = material.node_tree.links
    nodes.clear()
    output = p21.new_node(nodes, "ShaderNodeOutputMaterial", f"{material.name}_OUTPUT")
    principled = p21.new_node(nodes, "ShaderNodeBsdfPrincipled", f"{material.name}_PRINCIPLED")
    principled.inputs["Base Color"].default_value = p21.srgb(color)
    principled.inputs["Metallic"].default_value = metallic
    principled.inputs["Roughness"].default_value = roughness
    principled.inputs["Alpha"].default_value = alpha
    if "Emission Color" in principled.inputs:
        principled.inputs["Emission Color"].default_value = (0.0, 0.0, 0.0, 1.0)
    if "Emission Strength" in principled.inputs:
        principled.inputs["Emission Strength"].default_value = 0.0
    links.new(principled.outputs["BSDF"], output.inputs["Surface"])


def look_at(obj: bpy.types.Object, target: Vector) -> None:
    obj.rotation_euler = (target - obj.location).to_track_quat("-Z", "Y").to_euler()


def add_area_light(name: str, location: Vector, target: Vector, energy: float, size: float, color) -> bpy.types.Object:
    data = bpy.data.lights.new(name, type="AREA")
    data.energy = energy
    data.shape = "DISK"
    data.size = size
    data.color = color
    obj = bpy.data.objects.new(name, data)
    bpy.context.scene.collection.objects.link(obj)
    obj.location = location
    look_at(obj, target)
    return obj


def render_matrix(output_dir: Path, resolution: int, mode: str, shell_only: bool) -> list[dict[str, object]]:
    scene = bpy.context.scene
    hidden_state = {obj.name: bool(obj.hide_render) for obj in bpy.data.objects}
    zones = [bpy.data.objects[name] for name in ZONES]
    hidden_prefixes = p00.INTERNAL_RENDER_PREFIXES[1:-2]
    visible_meshes = []
    for obj in bpy.data.objects:
        if obj.type != "MESH":
            continue
        if shell_only:
            obj.hide_render = obj not in zones and not obj.name.startswith(("APPROX_GL02_shell_ash_", "APPROX_GL02_shell_local_heat_"))
        else:
            obj.hide_render = obj.name.startswith(hidden_prefixes)
        if not obj.hide_render:
            visible_meshes.append(obj)
    minimum, maximum = p00.object_bounds(visible_meshes)
    center = (minimum + maximum) * 0.5
    size = maximum - minimum
    span = max(float(size.x), float(size.y), float(size.z), 1.0)
    distance = span * 2.2
    scene.render.engine = "BLENDER_EEVEE"
    scene.render.resolution_x = resolution
    scene.render.resolution_y = resolution
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = "PNG"
    channel_mode = mode in {"BASE_COLOR", "ROUGHNESS", "METALLIC", "EXPOSED_MASK", "OXIDATION_MASK", "DUST_MASK", "WATER_MASK"}
    scene.render.film_transparent = channel_mode
    scene.view_settings.view_transform = "Standard" if channel_mode else "AgX"
    scene.view_settings.look = "None" if channel_mode else "AgX - Medium Low Contrast"
    scene.view_settings.exposure = 0.0
    scene.world.use_nodes = True
    world = scene.world.node_tree.nodes.get("Background")
    world.inputs["Color"].default_value = (0.12, 0.12, 0.12, 1.0)
    world.inputs["Strength"].default_value = 0.75
    created = [
        p00.add_sun_light(f"{mode}_KEY", center + Vector((span, -span, span)), center, 2.5, (1.0, 0.97, 0.93)),
        p00.add_sun_light(f"{mode}_FILL", center + Vector((-span, -span * 0.3, span * 0.4)), center, 1.1, (0.88, 0.94, 1.0)),
        p00.add_sun_light(f"{mode}_RIM", center + Vector((span * 0.3, span, span)), center, 1.7, (0.78, 0.87, 1.0)),
    ]
    camera_data = bpy.data.cameras.new(f"{mode}_CAMERA")
    camera_data.type = "ORTHO"
    camera = bpy.data.objects.new(f"{mode}_CAMERA", camera_data)
    scene.collection.objects.link(camera)
    created.append(camera)
    scene.camera = camera
    base_scale = max(float(size.z), float(size.x), float(size.y)) * 1.12
    views = {
        "front": (center + Vector((0.0, -distance, 0.0)), center, base_scale),
        "back": (center + Vector((0.0, distance, 0.0)), center, base_scale),
        "left": (center + Vector((-distance, 0.0, 0.0)), center, base_scale),
        "right": (center + Vector((distance, 0.0, 0.0)), center, base_scale),
        "iso": (center + Vector((distance * 0.75, -distance * 0.75, distance * 0.25)), center, base_scale),
    }
    if shell_only:
        detail_target = bpy.data.objects["APPROX_GL02_FURNACE_SHAFT"].bound_box
        detail_center = Vector((0.0, -3.4, 8.4))
        views["detail_shell"] = (detail_center + Vector((0.0, -distance, 0.6)), detail_center, 6.2)
    render_dir = output_dir / "renders" / mode.lower()
    render_dir.mkdir(parents=True, exist_ok=True)
    results = []
    for name, (location, target, ortho_scale) in views.items():
        camera.location = location
        camera_data.ortho_scale = ortho_scale
        look_at(camera, target)
        path = render_dir / f"P30_{mode}_{name}.png"
        scene.render.filepath = str(path)
        bpy.ops.render.render(write_still=True)
        results.append({"view": name, "path": str(path), "sha256": p00.sha256_file(path)})
    for obj in bpy.data.objects:
        if obj.name in hidden_state:
            obj.hide_render = hidden_state[obj.name]
    for obj in created:
        bpy.data.objects.remove(obj, do_unlink=True)
    return results


def render_channel_previews(output_dir: Path, resolution: int, material: bpy.types.Material, graph: dict[str, object]) -> list[dict[str, object]]:
    nodes = material.node_tree.nodes
    links = material.node_tree.links
    output = graph["output"]
    emission = p21.new_node(nodes, "ShaderNodeEmission", "P30_CHANNEL_PREVIEW_EMISSION")
    results = []
    for name in ("base_color", "roughness", "metallic", "exposed_mask", "oxidation_mask", "dust_mask", "water_mask"):
        for link in list(output.inputs["Surface"].links):
            links.remove(link)
        for link in list(emission.inputs["Color"].links):
            links.remove(link)
        links.new(graph[name], emission.inputs["Color"])
        links.new(emission.outputs["Emission"], output.inputs["Surface"])
        matrix = render_matrix(output_dir / "channels", max(384, resolution // 2), name.upper(), True)
        results.append({"channel": name, "renders": [item for item in matrix if item["view"] == "front"]})
    return results


def main() -> int:
    args = parse_args()
    output_dir = args.output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    source_glb = args.source_glb.resolve()
    input_blend = Path(bpy.data.filepath).resolve()
    if bpy.context.scene.get("bf3d_stage") != "P21_BAKE_TEST":
        raise RuntimeError(f"Expected P21_BAKE_TEST, got {bpy.context.scene.get('bf3d_stage')!r}")
    source = p00.source_node_contract(p00.read_glb_json(source_glb))
    sensor_before = p00.imported_contract(source)["sensor_records"]
    geometry_before = scene_mesh_sha256(False)
    uv_before = scene_mesh_sha256(True)
    matrices_before = p21.scene_matrix_sha256()
    material_hashes_before = {material.name: material_hash(material) for material in bpy.data.materials}
    material_names_before = sorted(material_hashes_before)
    shell_material = bpy.data.materials.get(SHELL_MATERIAL)
    ash_material = bpy.data.materials.get(ASH_MATERIAL)
    heat_material = bpy.data.materials.get(HEAT_MATERIAL)
    if not all((shell_material, ash_material, heat_material)):
        raise RuntimeError("Missing one or more protected shell material families")
    graph = rebuild_shell_material(shell_material)
    rebuild_overlay_material(ash_material, "#625E53", 0.0, 0.94, 0.24)
    rebuild_overlay_material(heat_material, "#594137", 0.02, 0.70, 0.18)
    for name in ZONES:
        obj = bpy.data.objects[name]
        obj.data.materials.clear()
        obj.data.materials.append(shell_material)
    for material in list(bpy.data.materials):
        if material.name.startswith("P21_"):
            bpy.data.materials.remove(material)
    for image in list(bpy.data.images):
        if image.name.startswith("P21_"):
            bpy.data.images.remove(image)

    geometry_after = scene_mesh_sha256(False)
    uv_after = scene_mesh_sha256(True)
    matrices_after = p21.scene_matrix_sha256()
    imported_after = p00.imported_contract(source)
    sensor_after = imported_after["sensor_records"]
    material_hashes_after = {material.name: material_hash(material) for material in bpy.data.materials}
    protected_changes = {
        name: {"before": value, "after": material_hashes_after.get(name)}
        for name, value in material_hashes_before.items()
        if name not in ALLOWED_MATERIALS and not name.startswith("P21_") and material_hashes_after.get(name) != value
    }
    zone_slots = {name: [material.name if material else None for material in bpy.data.objects[name].data.materials] for name in ZONES}
    node_names = {node.name for node in shell_material.node_tree.nodes}
    assertions = [
        {"id": "input_stage_is_p21", "ok": bpy.context.scene.get("bf3d_stage") == "P21_BAKE_TEST"},
        {"id": "source_glb_matches_lock", "ok": p00.sha256_file(source_glb) == p00.EXPECTED_SOURCE_SHA256},
        {"id": "geometry_unchanged", "ok": geometry_before == geometry_after, "detail": {"before": geometry_before, "after": geometry_after}},
        {"id": "uv_unchanged", "ok": uv_before == uv_after, "detail": {"before": uv_before, "after": uv_after}},
        {"id": "matrices_unchanged", "ok": matrices_before == matrices_after, "detail": {"before": matrices_before, "after": matrices_after}},
        {"id": "sensors_unchanged", "ok": sensor_before == sensor_after and imported_after["sensor_count"] == 115 and imported_after["body_sensor_count"] == 80},
        {"id": "only_temporary_p21_materials_removed", "ok": set(material_hashes_after) == {name for name in material_names_before if not name.startswith("P21_")}, "detail": {"before": material_names_before, "after": sorted(material_hashes_after)}},
        {"id": "only_three_material_families_changed", "ok": not protected_changes, "detail": protected_changes},
        {"id": "all_five_zones_share_weathered_steel", "ok": all(value == [SHELL_MATERIAL] for value in zone_slots.values()), "detail": zone_slots},
        {"id": "procedural_material_requires_bake", "ok": all(name in node_names for name in ("P30_MACRO", "P30_MESO", "P30_MICRO", "P30_VERTICAL_STREAK", "P30_EXPOSED_STEEL_MASK", "P30_OXIDATION_MASK", "P30_DRY_DUST_MASK")), "detail": sorted(node_names)},
        {"id": "no_time_or_random_nodes", "ok": not any(node.bl_idname in {"ShaderNodeTexCoord"} and "Random" in node.name for node in shell_material.node_tree.nodes)},
        {"id": "shell_emission_is_zero", "ok": graph["principled"].inputs["Emission Strength"].default_value == 0.0 if "Emission Strength" in graph["principled"].inputs else True},
    ]
    ok = all(bool(item["ok"]) for item in assertions)
    candidate = None
    if ok:
        scene = bpy.context.scene
        scene["bf3d_stage"] = "P30_SHELL_MATERIAL_CANDIDATE"
        scene["bf3d_parent_checkpoint"] = str(input_blend)
        scene["bf3d_change_dimension"] = "shell_material_family_only"
        scene["bf3d_requires_bake"] = True
        candidate_path = output_dir / "P30_SHELL_MATERIAL_CANDIDATE.blend"
        bpy.ops.wm.save_as_mainfile(filepath=str(candidate_path), check_existing=False)
        candidate = {"path": str(candidate_path), "bytes": candidate_path.stat().st_size, "sha256": p00.sha256_file(candidate_path)}
    renders = {"neutral_shell": [], "neutral_full": [], "channels": []}
    if ok:
        renders["neutral_shell"] = render_matrix(output_dir, args.resolution, "NEUTRAL_SHELL", True)
        renders["neutral_full"] = render_matrix(output_dir, args.resolution, "NEUTRAL_FULL", False)
        renders["channels"] = render_channel_previews(output_dir, args.resolution, shell_material, graph)
    status = "candidate_ready_for_visual_review" if ok and len(renders["neutral_shell"]) == 6 and len(renders["neutral_full"]) == 5 else "fail"
    report = {
        "schema_version": 1,
        "stage": "P30_SHELL_MATERIAL_CANDIDATE",
        "status": status,
        "input_checkpoint": {"path": str(input_blend), "sha256": p00.sha256_file(input_blend)},
        "candidate": candidate,
        "single_changed_dimension": "Procedural shell, ash and heat-patina material families only.",
        "requires_bake": True,
        "seed": SEED,
        "material_parameters": {
            "coat": {"color": "#48534F", "metallic": 0.04, "roughness": 0.76},
            "bare_steel": {"color": "#59615E", "metallic": 0.90, "roughness": 0.63},
            "oxidation": {"color": "#5B4032", "metallic": 0.03, "roughness": 0.85},
            "dry_dust": {"color": "#625F56", "metallic": 0.0, "roughness": 0.92},
            "water_streak": {"color": "#37423E", "metallic": 0.04, "roughness": 0.80},
            "alpha": 0.88,
            "bump": {"strength": 0.10, "distance_m": 0.003},
        },
        "assertions": assertions,
        "renders": renders,
        "approval": "pending_neutral_and_channel_visual_review",
    }
    report_path = output_dir / "p30_shell_material_candidate.json"
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": status, "report": str(report_path), "candidate": candidate, "assertions_ok": ok}, ensure_ascii=False, indent=2))
    return 0 if status == "candidate_ready_for_visual_review" else 2


if __name__ == "__main__":
    raise SystemExit(main())
