"""Bake a seam-safe 4K PBR test set for the representative GL02 shaft only."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import struct
import sys
import time
from pathlib import Path

import bpy
import numpy as np
from mathutils import Vector

AUDIT_SCRIPT_DIR = Path(__file__).resolve().parents[2] / "bf3d-geometry-audit" / "scripts"
sys.path.insert(0, str(AUDIT_SCRIPT_DIR))
import p00_import_audit as p00  # noqa: E402

TARGET = "APPROX_GL02_FURNACE_SHAFT"
UV_NAME = "BF3D_UV0"
SEED = 20260716
CHANNELS = ("BaseColor", "Roughness", "Metallic", "AO", "NormalGL", "SeamGrid")


def parse_args() -> argparse.Namespace:
    argv = sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else []
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-glb", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--texture-size", type=int, default=4096)
    parser.add_argument("--margin", type=int, default=16)
    parser.add_argument("--render-size", type=int, default=768)
    return parser.parse_args(argv)


def srgb(hex_value: str) -> tuple[float, float, float, float]:
    value = hex_value.lstrip("#")
    channels = [int(value[index : index + 2], 16) / 255.0 for index in (0, 2, 4)]

    def linear(channel: float) -> float:
        return channel / 12.92 if channel <= 0.04045 else ((channel + 0.055) / 1.055) ** 2.4

    return tuple(linear(channel) for channel in channels) + (1.0,)


def geometry_sha256(mesh: bpy.types.Mesh) -> str:
    digest = hashlib.sha256()
    for vertex in mesh.vertices:
        digest.update(struct.pack("<3d", *(float(value) for value in vertex.co)))
    for polygon in mesh.polygons:
        digest.update(struct.pack("<I", len(polygon.vertices)))
        for index in polygon.vertices:
            digest.update(struct.pack("<I", int(index)))
    return digest.hexdigest()


def uv_sha256(mesh: bpy.types.Mesh) -> str:
    digest = hashlib.sha256()
    for layer in mesh.uv_layers:
        digest.update(layer.name.encode("utf-8"))
        for index in range(len(mesh.loops)):
            uv = layer.uv[index].vector
            digest.update(struct.pack("<2d", float(uv.x), float(uv.y)))
    return digest.hexdigest()


def scene_matrix_sha256() -> str:
    digest = hashlib.sha256()
    for obj in sorted(bpy.data.objects, key=lambda item: item.name):
        digest.update(obj.name.encode("utf-8"))
        digest.update(struct.pack("<16d", *(float(value) for row in obj.matrix_world for value in row)))
    return digest.hexdigest()


def material_slots() -> dict[str, list[str | None]]:
    return {
        obj.name: [material.name if material else None for material in obj.data.materials]
        for obj in bpy.data.objects
        if obj.type == "MESH"
    }


def new_node(nodes: bpy.types.Nodes, node_type: str, name: str) -> bpy.types.Node:
    node = nodes.new(node_type)
    node.name = name
    node.label = name
    return node


def color_ramp(nodes: bpy.types.Nodes, name: str, low: float, high: float) -> bpy.types.Node:
    node = new_node(nodes, "ShaderNodeValToRGB", name)
    ramp = node.color_ramp
    ramp.interpolation = "EASE"
    ramp.elements[0].position = low
    ramp.elements[0].color = (0.0, 0.0, 0.0, 1.0)
    ramp.elements[1].position = high
    ramp.elements[1].color = (1.0, 1.0, 1.0, 1.0)
    return node


def build_procedural_material() -> tuple[bpy.types.Material, bpy.types.Object, dict[str, object]]:
    empty = bpy.data.objects.new("BF3D_WORLD_TEXCOORD", None)
    bpy.context.scene.collection.objects.link(empty)
    material = bpy.data.materials.new("P21_SHAFT_WORLDSPACE_SOURCE")
    material.use_nodes = True
    nodes = material.node_tree.nodes
    links = material.node_tree.links
    nodes.clear()

    output = new_node(nodes, "ShaderNodeOutputMaterial", "P21_OUTPUT")
    principled = new_node(nodes, "ShaderNodeBsdfPrincipled", "P21_PRINCIPLED")
    emission = new_node(nodes, "ShaderNodeEmission", "P21_BAKE_EMISSION")
    image_target = new_node(nodes, "ShaderNodeTexImage", "P21_ACTIVE_BAKE_TARGET")
    texcoord = new_node(nodes, "ShaderNodeTexCoord", "P21_WORLD_COORDINATE")
    texcoord.object = empty
    offset = new_node(nodes, "ShaderNodeVectorMath", "P21_FIXED_SEED_OFFSET")
    offset.operation = "ADD"
    offset.inputs[1].default_value = (2.60716, -1.60716, 0.716)
    links.new(texcoord.outputs["Object"], offset.inputs[0])

    def noise(name: str, scale: float, detail: float, roughness: float, vector_socket=None) -> bpy.types.Node:
        node = new_node(nodes, "ShaderNodeTexNoise", name)
        node.noise_dimensions = "4D"
        node.inputs["Scale"].default_value = scale
        node.inputs["Detail"].default_value = detail
        node.inputs["Roughness"].default_value = roughness
        node.inputs["W"].default_value = float(SEED % 997) / 997.0
        links.new(vector_socket or offset.outputs["Vector"], node.inputs["Vector"])
        return node

    macro = noise("P21_MACRO_NOISE", 0.23, 2.0, 0.58)
    meso = noise("P21_MESO_NOISE", 1.25, 3.0, 0.62)
    micro = noise("P21_MICRO_NOISE", 18.0, 2.0, 0.45)
    streak_scale = new_node(nodes, "ShaderNodeVectorMath", "P21_GRAVITY_STREAK_SCALE")
    streak_scale.operation = "MULTIPLY"
    streak_scale.inputs[1].default_value = (1.6, 1.6, 0.10)
    links.new(offset.outputs["Vector"], streak_scale.inputs[0])
    streak = noise("P21_VERTICAL_STREAK_NOISE", 1.0, 3.0, 0.60, streak_scale.outputs["Vector"])

    exposed = color_ramp(nodes, "P21_EXPOSED_STEEL_MASK", 0.44, 0.60)
    links.new(meso.outputs["Fac"], exposed.inputs["Fac"])
    rust_product = new_node(nodes, "ShaderNodeMath", "P21_RUST_PRODUCT")
    rust_product.operation = "MULTIPLY"
    links.new(macro.outputs["Fac"], rust_product.inputs[0])
    links.new(streak.outputs["Fac"], rust_product.inputs[1])
    rust = color_ramp(nodes, "P21_OXIDATION_MASK", 0.45, 0.61)
    links.new(rust_product.outputs[0], rust.inputs["Fac"])
    water = color_ramp(nodes, "P21_WATER_STREAK_MASK", 0.58, 0.75)
    links.new(streak.outputs["Fac"], water.inputs["Fac"])
    water_strength = new_node(nodes, "ShaderNodeMath", "P21_WATER_STREAK_STRENGTH")
    water_strength.operation = "MULTIPLY"
    water_strength.inputs[1].default_value = 0.28
    links.new(water.outputs["Color"], water_strength.inputs[0])

    coat_steel = new_node(nodes, "ShaderNodeMixRGB", "P21_COAT_TO_STEEL")
    coat_steel.blend_type = "MIX"
    coat_steel.inputs[1].default_value = srgb("#48534F")
    coat_steel.inputs[2].default_value = srgb("#59615E")
    links.new(exposed.outputs["Color"], coat_steel.inputs[0])
    add_rust = new_node(nodes, "ShaderNodeMixRGB", "P21_ADD_OXIDATION")
    add_rust.blend_type = "MIX"
    add_rust.inputs[2].default_value = srgb("#5B4032")
    links.new(rust.outputs["Color"], add_rust.inputs[0])
    links.new(coat_steel.outputs["Color"], add_rust.inputs[1])
    add_water = new_node(nodes, "ShaderNodeMixRGB", "P21_ADD_WATER_STREAK")
    add_water.blend_type = "MIX"
    add_water.inputs[2].default_value = srgb("#37423E")
    links.new(water_strength.outputs[0], add_water.inputs[0])
    links.new(add_rust.outputs["Color"], add_water.inputs[1])

    rough_steel = new_node(nodes, "ShaderNodeMix", "P21_ROUGH_COAT_STEEL")
    rough_steel.data_type = "FLOAT"
    rough_steel.inputs[2].default_value = 0.74
    rough_steel.inputs[3].default_value = 0.56
    links.new(exposed.outputs["Color"], rough_steel.inputs[0])
    rough_rust = new_node(nodes, "ShaderNodeMix", "P21_ROUGH_OXIDATION")
    rough_rust.data_type = "FLOAT"
    rough_rust.inputs[3].default_value = 0.85
    links.new(rust.outputs["Color"], rough_rust.inputs[0])
    links.new(rough_steel.outputs["Result"], rough_rust.inputs[2])
    micro_center = new_node(nodes, "ShaderNodeMapRange", "P21_MICRO_ROUGHNESS")
    micro_center.inputs["From Min"].default_value = 0.0
    micro_center.inputs["From Max"].default_value = 1.0
    micro_center.inputs["To Min"].default_value = -0.025
    micro_center.inputs["To Max"].default_value = 0.025
    micro_center.clamp = True
    links.new(micro.outputs["Fac"], micro_center.inputs["Value"])
    rough_add = new_node(nodes, "ShaderNodeMath", "P21_ROUGHNESS_FINAL")
    rough_add.operation = "ADD"
    rough_add.use_clamp = True
    links.new(rough_rust.outputs["Result"], rough_add.inputs[0])
    links.new(micro_center.outputs["Result"], rough_add.inputs[1])

    metal_steel = new_node(nodes, "ShaderNodeMix", "P21_METAL_COAT_STEEL")
    metal_steel.data_type = "FLOAT"
    metal_steel.inputs[2].default_value = 0.04
    metal_steel.inputs[3].default_value = 0.90
    links.new(exposed.outputs["Color"], metal_steel.inputs[0])
    metal_rust = new_node(nodes, "ShaderNodeMix", "P21_METAL_OXIDATION")
    metal_rust.data_type = "FLOAT"
    metal_rust.inputs[3].default_value = 0.03
    links.new(rust.outputs["Color"], metal_rust.inputs[0])
    links.new(metal_steel.outputs["Result"], metal_rust.inputs[2])

    bump = new_node(nodes, "ShaderNodeBump", "P21_MICRO_BUMP")
    bump.inputs["Strength"].default_value = 0.10
    bump.inputs["Distance"].default_value = 0.012
    links.new(micro.outputs["Fac"], bump.inputs["Height"])

    grid = new_node(nodes, "ShaderNodeTexChecker", "P21_WORLD_SEAM_GRID")
    grid.inputs["Color1"].default_value = srgb("#0A5963")
    grid.inputs["Color2"].default_value = srgb("#B6C8C4")
    grid.inputs["Scale"].default_value = 1.25
    links.new(offset.outputs["Vector"], grid.inputs["Vector"])
    neutral_ao = new_node(nodes, "ShaderNodeValue", "P21_NEUTRAL_OPEN_SHELL_AO")
    neutral_ao.outputs["Value"].default_value = 1.0

    links.new(add_water.outputs["Color"], principled.inputs["Base Color"])
    links.new(rough_add.outputs[0], principled.inputs["Roughness"])
    links.new(metal_rust.outputs["Result"], principled.inputs["Metallic"])
    links.new(bump.outputs["Normal"], principled.inputs["Normal"])
    links.new(principled.outputs["BSDF"], output.inputs["Surface"])
    return material, empty, {
        "nodes": nodes,
        "links": links,
        "output": output,
        "principled": principled,
        "emission": emission,
        "image_target": image_target,
        "BaseColor": add_water.outputs["Color"],
        "Roughness": rough_add.outputs[0],
        "Metallic": metal_rust.outputs["Result"],
        "AO": neutral_ao.outputs["Value"],
        "SeamGrid": grid.outputs["Color"],
    }


def configure_cycles(prefer_gpu: bool) -> dict[str, object]:
    scene = bpy.context.scene
    scene.render.engine = "CYCLES"
    scene.cycles.samples = 32
    result: dict[str, object] = {"requested": "OPTIX" if prefer_gpu else "CPU", "used": "CPU", "devices": []}
    if not prefer_gpu:
        scene.cycles.device = "CPU"
        return result
    try:
        preferences = bpy.context.preferences.addons["cycles"].preferences
        preferences.compute_device_type = "OPTIX"
        preferences.get_devices()
        for device in preferences.devices:
            device.use = device.type == "OPTIX"
            result["devices"].append({"name": device.name, "type": device.type, "use": bool(device.use)})
        if not any(item["type"] == "OPTIX" and item["use"] for item in result["devices"]):
            raise RuntimeError("No active OptiX device")
        scene.cycles.device = "GPU"
        result["used"] = "OPTIX"
    except Exception as exc:  # pragma: no cover - Blender/device dependent
        scene.cycles.device = "CPU"
        result["fallback_reason"] = str(exc)
    return result


def create_image(name: str, size: int, color_space: str) -> bpy.types.Image:
    existing = bpy.data.images.get(name)
    if existing:
        bpy.data.images.remove(existing)
    image = bpy.data.images.new(name, width=size, height=size, alpha=True, float_buffer=False, is_data=color_space != "sRGB")
    image.generated_color = (0.0, 0.0, 0.0, 0.0)
    image.colorspace_settings.name = color_space
    return image


def activate_target(nodes: bpy.types.Nodes, image_node: bpy.types.Node, image: bpy.types.Image) -> None:
    for node in nodes:
        node.select = False
    image_node.image = image
    image_node.select = True
    nodes.active = image_node


def select_only(obj: bpy.types.Object) -> None:
    if bpy.context.object and bpy.context.object.mode != "OBJECT":
        bpy.ops.object.mode_set(mode="OBJECT")
    bpy.ops.object.select_all(action="DESELECT")
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj


def save_image(image: bpy.types.Image, path: Path) -> dict[str, object]:
    image.filepath_raw = str(path)
    image.file_format = "PNG"
    image.save()
    return {"path": str(path), "bytes": path.stat().st_size, "sha256": p00.sha256_file(path)}


def bake_channels(
    shaft: bpy.types.Object,
    material: bpy.types.Material,
    graph: dict[str, object],
    texture_dir: Path,
    size: int,
    margin: int,
) -> tuple[dict[str, bpy.types.Image], dict[str, dict[str, object]], dict[str, float]]:
    shaft.data.materials.clear()
    shaft.data.materials.append(material)
    select_only(shaft)
    nodes = graph["nodes"]
    links = graph["links"]
    output = graph["output"]
    emission = graph["emission"]
    image_node = graph["image_target"]
    images: dict[str, bpy.types.Image] = {}
    files: dict[str, dict[str, object]] = {}
    timings: dict[str, float] = {}

    for channel in ("BaseColor", "Roughness", "Metallic", "AO", "SeamGrid"):
        color_space = "sRGB" if channel in {"BaseColor", "SeamGrid"} else "Non-Color"
        image = create_image(f"P21_SHAFT_{channel}_{size}", size, color_space)
        images[channel] = image
        activate_target(nodes, image_node, image)
        for link in list(output.inputs["Surface"].links):
            links.remove(link)
        for link in list(emission.inputs["Color"].links):
            links.remove(link)
        links.new(graph[channel], emission.inputs["Color"])
        links.new(emission.outputs["Emission"], output.inputs["Surface"])
        started = time.perf_counter()
        bpy.ops.object.bake(
            type="EMIT",
            margin=margin,
            margin_type="EXTEND",
            use_selected_to_active=False,
            use_clear=True,
            target="IMAGE_TEXTURES",
            save_mode="INTERNAL",
            uv_layer=UV_NAME,
        )
        timings[channel] = time.perf_counter() - started
        files[channel] = save_image(image, texture_dir / f"P21_SHAFT_{channel}_{size // 1024}K.png")

    for link in list(output.inputs["Surface"].links):
        links.remove(link)
    links.new(graph["principled"].outputs["BSDF"], output.inputs["Surface"])

    normal = create_image(f"P21_SHAFT_NormalGL_{size}", size, "Non-Color")
    images["NormalGL"] = normal
    activate_target(nodes, image_node, normal)
    started = time.perf_counter()
    bpy.ops.object.bake(
        type="NORMAL",
        normal_space="TANGENT",
        normal_r="POS_X",
        normal_g="POS_Y",
        normal_b="POS_Z",
        margin=margin,
        margin_type="ADJACENT_FACES",
        use_selected_to_active=False,
        use_clear=True,
        target="IMAGE_TEXTURES",
        save_mode="INTERNAL",
        uv_layer=UV_NAME,
    )
    timings["NormalGL"] = time.perf_counter() - started
    files["NormalGL"] = save_image(normal, texture_dir / f"P21_SHAFT_NormalGL_{size // 1024}K.png")

    return images, files, timings


def image_array(image: bpy.types.Image) -> np.ndarray:
    values = np.empty(len(image.pixels), dtype=np.float32)
    image.pixels.foreach_get(values)
    return values.reshape((-1, 4))


def image_metrics(image: bpy.types.Image, active: np.ndarray) -> dict[str, object]:
    values = image_array(image)
    finite = bool(np.isfinite(values).all())
    rgb = values[active, :3] if np.any(active) else values[:, :3]
    return {
        "width": int(image.size[0]),
        "height": int(image.size[1]),
        "colorspace": image.colorspace_settings.name,
        "finite": finite,
        "active_pixel_ratio": float(np.mean(active)),
        "rgb_min": [float(value) for value in np.min(rgb, axis=0)],
        "rgb_max": [float(value) for value in np.max(rgb, axis=0)],
        "rgb_mean": [float(value) for value in np.mean(rgb, axis=0)],
        "first_channel_p05": float(np.quantile(rgb[:, 0], 0.05)),
        "first_channel_p95": float(np.quantile(rgb[:, 0], 0.95)),
        "first_channel_above_0_5_ratio": float(np.mean(rgb[:, 0] > 0.5)),
    }


def pack_orm(images: dict[str, bpy.types.Image], texture_dir: Path, size: int) -> tuple[bpy.types.Image, dict[str, object]]:
    ao = image_array(images["AO"])
    roughness = image_array(images["Roughness"])
    metallic = image_array(images["Metallic"])
    packed = np.empty_like(ao)
    packed[:, 0] = ao[:, 0]
    packed[:, 1] = roughness[:, 0]
    packed[:, 2] = metallic[:, 0]
    packed[:, 3] = 1.0
    orm = create_image(f"P21_SHAFT_ORM_{size}", size, "Non-Color")
    orm.alpha_mode = "CHANNEL_PACKED"
    orm.pixels.foreach_set(packed.reshape(-1))
    orm.update()
    path = texture_dir / f"P21_SHAFT_ORM_{size // 1024}K.png"
    file_info = save_image(orm, path)
    max_error = max(
        float(np.max(np.abs(packed[:, 0] - ao[:, 0]))),
        float(np.max(np.abs(packed[:, 1] - roughness[:, 0]))),
        float(np.max(np.abs(packed[:, 2] - metallic[:, 0]))),
    )
    return orm, {**file_info, "channel_mapping": "R=AO,G=Roughness,B=Metallic,A=1", "in_memory_max_channel_error": max_error}


def build_baked_material(images: dict[str, bpy.types.Image]) -> bpy.types.Material:
    material = bpy.data.materials.new("P21_SHAFT_BAKED_STEEL")
    material.use_nodes = True
    nodes = material.node_tree.nodes
    links = material.node_tree.links
    nodes.clear()
    output = new_node(nodes, "ShaderNodeOutputMaterial", "P21_BAKED_OUTPUT")
    principled = new_node(nodes, "ShaderNodeBsdfPrincipled", "P21_BAKED_PRINCIPLED")
    links.new(principled.outputs["BSDF"], output.inputs["Surface"])
    for name in ("BaseColor", "Roughness", "Metallic", "NormalGL", "AO", "ORM"):
        node = new_node(nodes, "ShaderNodeTexImage", f"P21_BAKED_{name}")
        node.image = images[name]
        if name == "BaseColor":
            links.new(node.outputs["Color"], principled.inputs["Base Color"])
        elif name == "Roughness":
            links.new(node.outputs["Color"], principled.inputs["Roughness"])
        elif name == "Metallic":
            links.new(node.outputs["Color"], principled.inputs["Metallic"])
        elif name == "NormalGL":
            normal_map = new_node(nodes, "ShaderNodeNormalMap", "P21_OPENGL_NORMAL")
            normal_map.space = "TANGENT"
            links.new(node.outputs["Color"], normal_map.inputs["Color"])
            links.new(normal_map.outputs["Normal"], principled.inputs["Normal"])
    return material


def build_grid_material(image: bpy.types.Image) -> bpy.types.Material:
    material = bpy.data.materials.new("P21_SHAFT_BAKED_SEAM_GRID")
    material.use_nodes = True
    nodes = material.node_tree.nodes
    links = material.node_tree.links
    nodes.clear()
    output = new_node(nodes, "ShaderNodeOutputMaterial", "P21_GRID_OUTPUT")
    principled = new_node(nodes, "ShaderNodeBsdfPrincipled", "P21_GRID_PRINCIPLED")
    texture = new_node(nodes, "ShaderNodeTexImage", "P21_GRID_TEXTURE")
    texture.image = image
    principled.inputs["Metallic"].default_value = 0.0
    principled.inputs["Roughness"].default_value = 1.0
    links.new(texture.outputs["Color"], principled.inputs["Base Color"])
    links.new(principled.outputs["BSDF"], output.inputs["Surface"])
    return material


def look_at(obj: bpy.types.Object, target: Vector) -> None:
    obj.rotation_euler = (target - obj.location).to_track_quat("-Z", "Y").to_euler()


def render_material_matrix(output_dir: Path, resolution: int, shaft: bpy.types.Object, material: bpy.types.Material, prefix: str) -> list[dict[str, object]]:
    scene = bpy.context.scene
    for obj in bpy.data.objects:
        if obj.type == "MESH":
            obj.hide_render = obj != shaft
    shaft.data.materials.clear()
    shaft.data.materials.append(material)
    scene.render.engine = "BLENDER_EEVEE"
    scene.render.resolution_x = resolution
    scene.render.resolution_y = resolution
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = "PNG"
    scene.render.film_transparent = False
    scene.view_settings.view_transform = "AgX"
    scene.view_settings.exposure = 0.0
    scene.world.use_nodes = True
    background = scene.world.node_tree.nodes.get("Background")
    background.inputs["Color"].default_value = (0.025, 0.03, 0.035, 1.0)
    background.inputs["Strength"].default_value = 0.55
    minimum, maximum = p00.object_bounds([shaft])
    center = (minimum + maximum) * 0.5
    size = maximum - minimum
    span = max(float(size.x), float(size.y), float(size.z), 1.0)
    distance = span * 2.2
    p00.add_sun_light(f"{prefix}_KEY", center + Vector((span, -span, span)), center, 2.2, (1.0, 0.96, 0.92))
    p00.add_sun_light(f"{prefix}_FILL", center + Vector((-span, -span * 0.3, span * 0.4)), center, 1.1, (0.88, 0.94, 1.0))
    p00.add_sun_light(f"{prefix}_RIM", center + Vector((0.3 * span, span, span)), center, 1.4, (0.78, 0.86, 1.0))
    camera_data = bpy.data.cameras.new(f"{prefix}_CAMERA")
    camera_data.type = "ORTHO"
    camera = bpy.data.objects.new(f"{prefix}_CAMERA", camera_data)
    scene.collection.objects.link(camera)
    scene.camera = camera
    camera_data.ortho_scale = max(float(size.z), float(size.x), float(size.y)) * 1.16
    views = {
        "front": center + Vector((0.0, -distance, 0.0)),
        "back": center + Vector((0.0, distance, 0.0)),
        "left": center + Vector((-distance, 0.0, 0.0)),
        "right": center + Vector((distance, 0.0, 0.0)),
        "iso": center + Vector((distance * 0.75, -distance * 0.75, distance * 0.28)),
    }
    render_dir = output_dir / "renders" / prefix.lower()
    render_dir.mkdir(parents=True, exist_ok=True)
    results = []
    for name, location in views.items():
        camera.location = location
        look_at(camera, center)
        path = render_dir / f"P21_SHAFT_{prefix}_{name}.png"
        scene.render.filepath = str(path)
        bpy.ops.render.render(write_still=True)
        results.append({"view": name, "path": str(path), "sha256": p00.sha256_file(path)})
    return results


def main() -> int:
    args = parse_args()
    output_dir = args.output_dir.resolve()
    texture_dir = output_dir / "textures"
    texture_dir.mkdir(parents=True, exist_ok=True)
    source_glb = args.source_glb.resolve()
    input_blend = Path(bpy.data.filepath).resolve()
    if bpy.context.scene.get("bf3d_stage") != "P20_SHAFT_UV_CANDIDATE":
        raise RuntimeError(f"Expected P20_SHAFT_UV_CANDIDATE, got {bpy.context.scene.get('bf3d_stage')!r}")
    shaft = bpy.data.objects.get(TARGET)
    if shaft is None or shaft.type != "MESH":
        raise RuntimeError(f"Missing target mesh: {TARGET}")
    if [layer.name for layer in shaft.data.uv_layers] != [UV_NAME]:
        raise RuntimeError(f"Unexpected UV layers: {[layer.name for layer in shaft.data.uv_layers]}")
    source = p00.source_node_contract(p00.read_glb_json(source_glb))
    sensor_before = p00.imported_contract(source)["sensor_records"]
    geometry_before = geometry_sha256(shaft.data)
    uv_before = uv_sha256(shaft.data)
    matrices_before = scene_matrix_sha256()
    slots_before = material_slots()
    source_material, coordinate_empty, graph = build_procedural_material()
    gpu = configure_cycles(True)
    try:
        images, files, timings = bake_channels(shaft, source_material, graph, texture_dir, args.texture_size, args.margin)
    except RuntimeError as gpu_error:
        if gpu.get("used") != "OPTIX":
            raise
        for image in list(bpy.data.images):
            if image.name.startswith("P21_SHAFT_"):
                bpy.data.images.remove(image)
        gpu["bake_fallback_reason"] = str(gpu_error)
        gpu = {**gpu, **configure_cycles(False), "fallback_from": "OPTIX"}
        images, files, timings = bake_channels(shaft, source_material, graph, texture_dir, args.texture_size, args.margin)
    orm, orm_file = pack_orm(images, texture_dir, args.texture_size)
    images["ORM"] = orm
    files["ORM"] = orm_file
    # Neutral AO is baked as 1 on UV-covered pixels and remains 0 outside the islands.
    active_uv = image_array(images["AO"])[:, 0] > 0.5
    metrics = {name: image_metrics(image, active_uv) for name, image in images.items()}
    baked_material = build_baked_material(images)
    shaft.data.materials.clear()
    shaft.data.materials.append(baked_material)
    if coordinate_empty.name in bpy.data.objects:
        bpy.data.objects.remove(coordinate_empty, do_unlink=True)
    bpy.data.materials.remove(source_material)
    geometry_after = geometry_sha256(shaft.data)
    uv_after = uv_sha256(shaft.data)
    matrices_after = scene_matrix_sha256()
    sensor_after = p00.imported_contract(source)["sensor_records"]
    slots_after = material_slots()
    changed_slot_objects = sorted(name for name in slots_before if slots_before[name] != slots_after[name])
    assertions = [
        {"id": "input_stage_is_p20", "ok": bpy.context.scene.get("bf3d_stage") == "P20_SHAFT_UV_CANDIDATE"},
        {"id": "source_glb_matches_lock", "ok": p00.sha256_file(source_glb) == p00.EXPECTED_SOURCE_SHA256},
        {"id": "shaft_geometry_unchanged", "ok": geometry_before == geometry_after, "detail": {"before": geometry_before, "after": geometry_after}},
        {"id": "shaft_uv_unchanged", "ok": uv_before == uv_after, "detail": {"before": uv_before, "after": uv_after}},
        {"id": "object_matrices_unchanged", "ok": matrices_before == matrices_after, "detail": {"before": matrices_before, "after": matrices_after}},
        {"id": "sensors_unchanged", "ok": sensor_before == sensor_after and len(sensor_after) == 115},
        {"id": "only_shaft_material_slot_changed", "ok": changed_slot_objects == [TARGET], "detail": changed_slot_objects},
        {"id": "all_images_expected_size", "ok": all(value["width"] == args.texture_size and value["height"] == args.texture_size for value in metrics.values()), "detail": {name: [value["width"], value["height"]] for name, value in metrics.items()}},
        {"id": "all_images_finite_and_nonempty", "ok": all(value["finite"] and value["active_pixel_ratio"] > 0.05 for value in metrics.values()), "detail": {name: {"finite": value["finite"], "active": value["active_pixel_ratio"]} for name, value in metrics.items()}},
        {"id": "roughness_range_is_matte", "ok": metrics["Roughness"]["rgb_min"][0] >= 0.50 and metrics["Roughness"]["rgb_max"][0] <= 0.90, "detail": metrics["Roughness"]},
        {"id": "metallic_is_mask_driven", "ok": metrics["Metallic"]["rgb_min"][0] <= 0.10 and metrics["Metallic"]["rgb_max"][0] >= 0.75 and 0.20 <= metrics["Metallic"]["rgb_mean"][0] <= 0.50 and 0.20 <= metrics["Metallic"]["first_channel_above_0_5_ratio"] <= 0.55, "detail": metrics["Metallic"]},
        {"id": "normal_is_opengl_oriented", "ok": 0.35 <= metrics["NormalGL"]["rgb_mean"][0] <= 0.65 and 0.35 <= metrics["NormalGL"]["rgb_mean"][1] <= 0.65 and metrics["NormalGL"]["rgb_mean"][2] >= 0.80, "detail": metrics["NormalGL"]},
        {"id": "ao_does_not_crush_shell", "ok": metrics["AO"]["rgb_mean"][0] >= 0.60, "detail": metrics["AO"]},
        {"id": "orm_channels_exact_in_memory", "ok": orm_file["in_memory_max_channel_error"] <= 1e-8, "detail": orm_file},
    ]
    ok = all(bool(item["ok"]) for item in assertions)
    candidate = None
    if ok:
        scene = bpy.context.scene
        scene["bf3d_stage"] = "P21_BAKE_TEST"
        scene["bf3d_parent_checkpoint"] = str(input_blend)
        scene["bf3d_change_dimension"] = "shaft_seam_safe_pbr_bake_only"
        scene["bf3d_bake_resolution"] = args.texture_size
        bpy.ops.file.pack_all()
        candidate_path = output_dir / "P21_BAKE_TEST.blend"
        bpy.ops.wm.save_as_mainfile(filepath=str(candidate_path), check_existing=False)
        candidate = {"path": str(candidate_path), "bytes": candidate_path.stat().st_size, "sha256": p00.sha256_file(candidate_path)}
    renders = {"seam_grid": [], "baked_steel": []}
    if ok:
        grid_material = build_grid_material(images["SeamGrid"])
        renders["seam_grid"] = render_material_matrix(output_dir, args.render_size, shaft, grid_material, "SEAM_GRID")
        renders["baked_steel"] = render_material_matrix(output_dir, args.render_size, shaft, baked_material, "BAKED_STEEL")
    status = "candidate_ready_for_visual_review" if ok and all(len(value) == 5 for value in renders.values()) else "fail"
    report = {
        "schema_version": 1,
        "stage": "P21_BAKE_TEST",
        "status": status,
        "input_checkpoint": {"path": str(input_blend), "sha256": p00.sha256_file(input_blend)},
        "candidate": candidate,
        "target": TARGET,
        "uv_layer": UV_NAME,
        "texture_size": args.texture_size,
        "margin_px": args.margin,
        "seed": SEED,
        "device": gpu,
        "timings_seconds": timings,
        "textures": files,
        "image_metrics": metrics,
        "assertions": assertions,
        "renders": renders,
        "approval": "pending_seam_and_material_visual_review",
    }
    report_path = output_dir / "p21_bake_test.json"
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    manifest_path = output_dir / "p21_texture_manifest.json"
    manifest_path.write_text(json.dumps({"schema_version": 1, "textures": files, "metrics": metrics}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": status, "report": str(report_path), "candidate": candidate, "device": gpu, "timings_seconds": timings}, ensure_ascii=False, indent=2))
    return 0 if status == "candidate_ready_for_visual_review" else 2


if __name__ == "__main__":
    raise SystemExit(main())
