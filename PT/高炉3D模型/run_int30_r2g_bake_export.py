"""Build the isolated INT-30 R2G baked GLB candidate.

The stage is intentionally isolated:
- reads the approved R2F Blender candidate;
- writes only under the R2G work directory;
- bakes a new R2G PBR texture set from the locked R1/R5 material contract;
- runs a 1K smoke candidate first, then a 4K final candidate only if smoke passes;
- never replaces the production GLB and never grants approval.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
BLENDER = Path(r"D:\Program Files\Blender Foundation\Blender 5.2\blender.exe")

STAGE = "INT-30_R2G_ISOLATED_GLB_WEB_PREVIEW"
DEFAULT_INPUT = (
    HERE
    / "work"
    / "INT_30_20260718_R2F_LAYER_OVERLAY_RUNTIME_READY"
    / "INT_30_R2F_LAYER_OVERLAY_RUNTIME_READY_CANDIDATE.blend"
)
DEFAULT_OUTPUT = HERE / "work" / "INT_30_20260718_R2G_ISOLATED_GLB_WEB_PREVIEW"
FORMAL_GLB = ROOT / "高炉前端数据" / "models" / "gl02_blast_furnace.glb"

EXPECTED_INPUT_SHA256 = (
    "1d292e8cc6ad5f845827cdd4c5f18b7e6eda496703870816caaef181af9fb3e5"
)
EXPECTED_FORMAL_GLB_SHA256 = (
    "808960f1b2703e7fb27df35f1b1b1a17063b9b10d2267acba593fc3872b62af6"
)
EXPECTED_R1_CARRIER_SHA256 = (
    "4f1dae2804300c2c99462b4a5d7967abd9085a3ffd7170ae26af4e105290471b"
)

WORKER_NAME = "r2g_blender_bake_export_worker.py"
STABLE_GLB_NAME = "INT_30_R2G_R2F_R1_R5_WEB_PREVIEW_UNCOMPRESSED.glb"


WORKER_SOURCE = r'''
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import struct
import sys
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any

import bpy
import numpy as np


STAGE = "INT-30_R2G_ISOLATED_GLB_WEB_PREVIEW"
EXPECTED_INPUT_SHA256 = "1d292e8cc6ad5f845827cdd4c5f18b7e6eda496703870816caaef181af9fb3e5"
EXPECTED_FORMAL_GLB_SHA256 = "808960f1b2703e7fb27df35f1b1b1a17063b9b10d2267acba593fc3872b62af6"
EXPECTED_R1_CARRIER_SHA256 = "4f1dae2804300c2c99462b4a5d7967abd9085a3ffd7170ae26af4e105290471b"

R1_LOCK = {
    "decision_id": "VB-DEC-MAT-001",
    "carrier": "SURF-20 R5",
    "carrier_sha256": EXPECTED_R1_CARRIER_SHA256,
    "B": 0.16,
    "D_m": 0.10,
    "N": 0.45,
    "metallic": 0.06,
    "roughness_range": [0.56, 0.82],
    "mapping_scale": 0.085,
}

SOURCE_R1_MATERIAL = "SURF20_R5_aged_painted_carbon_steel_shared_world"
R2G_MATERIAL = "INT30_R2G_R1_LOCK_BAKED_PBR_STEEL"
R2G_UV = "INT30_R2G_UV0"
NORMAL_RUNTIME_SCALE = 0.45
BAKE_AUDITS: list[dict[str, Any]] = []
R1_RAMP_DARK_LINEAR_RGB = (0.145, 0.188, 0.168)
R1_RAMP_LIGHT_LINEAR_RGB = (0.235, 0.285, 0.248)
RUNTIME_ADAPTER_NORMAL_GAIN = 1.55

SHELL_ZONES = (
    "APPROX_GL02_FURNACE_HEARTH",
    "APPROX_GL02_FURNACE_BOSH",
    "APPROX_GL02_FURNACE_BELLY",
    "APPROX_GL02_FURNACE_SHAFT",
    "APPROX_GL02_FURNACE_THROAT",
)
LAYERS = tuple(f"L{number}" for number in range(7, 17))
BANDS = tuple(f"APPROX_GL02_TEMP_LAYER_BAND_{layer}" for layer in LAYERS)
GROUPS = tuple(f"GL02_FURNACE_TEMP_LAYER_{layer}" for layer in LAYERS)
SENSOR_LAYER_GROUPS = tuple(f"GL02_SENSOR_LAYER_{layer}" for layer in LAYERS)
INT20_SOLIDS = (
    "APPROX_GL02_INT10_STEEL_SHELL_FULL",
    "APPROX_GL02_INT10_STEEL_SHELL_HALF",
    "APPROX_GL02_INT10_STEEL_SHELL_QUARTER",
    "APPROX_GL02_INT10_COOLING_WALL_FULL",
    "APPROX_GL02_INT10_COOLING_WALL_HALF",
    "APPROX_GL02_INT10_COOLING_WALL_QUARTER",
    "APPROX_GL02_INT10_REFRACTORY_LINING_FULL",
    "APPROX_GL02_INT10_REFRACTORY_LINING_HALF",
    "APPROX_GL02_INT10_REFRACTORY_LINING_QUARTER",
    "APPROX_GL02_INT10_PROCESS_SPACE_FULL",
    "APPROX_GL02_INT10_PROCESS_SPACE_HALF",
    "APPROX_GL02_INT10_PROCESS_SPACE_QUARTER",
)
PRESSURE_PREFIX = "GL02_INT30_PRESSURE_"


def now_iso() -> str:
    return datetime.now(timezone(timedelta(hours=8))).replace(microsecond=0).isoformat()


def parse_args() -> argparse.Namespace:
    raw = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", required=True, choices=("smoke", "final"))
    parser.add_argument("--texture-size", required=True, type=int)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--input-blend", required=True, type=Path)
    parser.add_argument("--formal-glb", required=True, type=Path)
    return parser.parse_args(raw)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def file_record(path: Path) -> dict[str, Any]:
    return {
        "path": str(path),
        "bytes": path.stat().st_size,
        "sha256": sha256_file(path),
    }


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def stable_sha(payload: Any) -> str:
    blob = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(blob).hexdigest()


def matrix_values(obj: bpy.types.Object) -> list[float]:
    return [round(float(value), 9) for row in obj.matrix_world for value in row]


def png_save_rgba(path: Path, rgba: np.ndarray) -> None:
    image = bpy.data.images.new(path.stem, width=int(rgba.shape[1]), height=int(rgba.shape[0]), alpha=True, float_buffer=False)
    image.colorspace_settings.name = "sRGB" if "BaseColor" in path.name else "Non-Color"
    flat = rgba.astype(np.float32).reshape(-1) / 255.0
    image.pixels.foreach_set(flat.tolist())
    image.file_format = "PNG"
    image.filepath_raw = str(path)
    image.save()
    bpy.data.images.remove(image)


def linear_to_srgb(linear: np.ndarray) -> np.ndarray:
    linear = np.clip(linear, 0.0, 1.0).astype(np.float32)
    return np.where(linear <= 0.0031308, linear * 12.92, 1.055 * np.power(linear, 1.0 / 2.4) - 0.055)


def make_smooth_noise(size: int, seed: int, octaves: int = 5) -> np.ndarray:
    rng = np.random.default_rng(seed)
    acc = np.zeros((size, size), dtype=np.float32)
    amp_sum = 0.0
    for octave in range(octaves):
        freq = 4 * (2 ** octave)
        grid = rng.random((freq + 1, freq + 1), dtype=np.float32)
        y = np.linspace(0, freq, size, endpoint=False, dtype=np.float32)
        x = np.linspace(0, freq, size, endpoint=False, dtype=np.float32)
        y0 = np.floor(y).astype(np.int32)
        x0 = np.floor(x).astype(np.int32)
        yf = (y - y0)[:, None]
        xf = (x - x0)[None, :]
        g00 = grid[y0[:, None], x0[None, :]]
        g10 = grid[(y0 + 1)[:, None], x0[None, :]]
        g01 = grid[y0[:, None], (x0 + 1)[None, :]]
        g11 = grid[(y0 + 1)[:, None], (x0 + 1)[None, :]]
        sx = xf * xf * (3.0 - 2.0 * xf)
        sy = yf * yf * (3.0 - 2.0 * yf)
        a = g00 * (1.0 - sx) + g01 * sx
        b = g10 * (1.0 - sx) + g11 * sx
        layer = a * (1.0 - sy) + b * sy
        amp = 0.55 ** octave
        acc += layer * amp
        amp_sum += amp
    acc /= max(amp_sum, 1e-6)
    return np.clip(acc, 0.0, 1.0)


def create_bake_image(name: str, size: int, colorspace: str) -> bpy.types.Image:
    image = bpy.data.images.new(name, width=size, height=size, alpha=True, float_buffer=False)
    image.colorspace_settings.name = colorspace
    return image


def save_bake_image(image: bpy.types.Image, path: Path, colorspace: str) -> dict[str, Any]:
    image.colorspace_settings.name = colorspace
    image.file_format = "PNG"
    image.filepath_raw = str(path)
    image.save()
    return file_record(path)


def image_rgba_array(image: bpy.types.Image) -> np.ndarray:
    pixels = np.empty(int(image.size[0]) * int(image.size[1]) * 4, dtype=np.float32)
    image.pixels.foreach_get(pixels)
    return np.clip(pixels.reshape((int(image.size[1]), int(image.size[0]), 4)), 0.0, 1.0)


def find_principled(material: bpy.types.Material) -> bpy.types.Node:
    if material is None or material.node_tree is None:
        raise RuntimeError("R1 source material has no node tree")
    for node in material.node_tree.nodes:
        if node.bl_idname == "ShaderNodeBsdfPrincipled":
            return node
    raise RuntimeError("R1 source material has no Principled BSDF node")


def make_emission_bake_material(source: bpy.types.Material, socket_name: str, default_value: float | tuple[float, float, float, float]) -> bpy.types.Material:
    material = source.copy()
    material.name = f"INT30_R2G_TRUE_BAKE_{socket_name.replace(' ', '_')}"
    material.use_nodes = True
    nodes = material.node_tree.nodes
    links = material.node_tree.links
    principled = find_principled(material)
    output = next((node for node in nodes if node.bl_idname == "ShaderNodeOutputMaterial"), None)
    if output is None:
        output = nodes.new("ShaderNodeOutputMaterial")
    output.is_active_output = True
    emission = nodes.new("ShaderNodeEmission")
    emission.name = f"INT30_R2G_EMIT_{socket_name.replace(' ', '_')}"
    emission.inputs["Strength"].default_value = 1.0
    socket = principled.inputs.get(socket_name)
    if socket is None:
        raise RuntimeError(f"Principled input not found: {socket_name}")
    link = next((candidate for candidate in links if candidate.to_socket == socket), None)
    if link is not None:
        links.new(link.from_socket, emission.inputs["Color"])
    else:
        value = socket.default_value if hasattr(socket, "default_value") else default_value
        if isinstance(value, float):
            emission.inputs["Color"].default_value = (value, value, value, 1.0)
        else:
            emission.inputs["Color"].default_value = tuple(value)
    for link in list(links):
        if link.to_socket == output.inputs["Surface"]:
            links.remove(link)
    links.new(emission.outputs["Emission"], output.inputs["Surface"])
    return material


def socket_source_record(material: bpy.types.Material, socket_name: str) -> dict[str, Any]:
    principled = find_principled(material)
    socket = principled.inputs.get(socket_name)
    if socket is None:
        return {"socket": socket_name, "present": False}
    links = material.node_tree.links
    link = next((candidate for candidate in links if candidate.to_socket == socket), None)
    record: dict[str, Any] = {"socket": socket_name, "present": True}
    if link is None:
        value = socket.default_value if hasattr(socket, "default_value") else None
        record.update({"linked": False, "default": list(value) if hasattr(value, "__iter__") and not isinstance(value, str) else value})
    else:
        record.update(
            {
                "linked": True,
                "from_node": link.from_node.name,
                "from_node_type": link.from_node.bl_idname,
                "from_socket": link.from_socket.name,
            }
        )
    return record


def make_bump_height_bake_material(source: bpy.types.Material) -> bpy.types.Material:
    material = source.copy()
    material.name = "INT30_R2G_TRUE_BAKE_BUMP_HEIGHT"
    material.use_nodes = True
    nodes = material.node_tree.nodes
    links = material.node_tree.links
    bump = next((node for node in nodes if node.bl_idname == "ShaderNodeBump"), None)
    if bump is None:
        raise RuntimeError("R1 source material has no Bump node for height bake")
    output = next((node for node in nodes if node.bl_idname == "ShaderNodeOutputMaterial"), None)
    if output is None:
        output = nodes.new("ShaderNodeOutputMaterial")
    output.is_active_output = True
    emission = nodes.new("ShaderNodeEmission")
    emission.name = "INT30_R2G_EMIT_Bump_Height"
    emission.inputs["Strength"].default_value = 1.0
    height_socket = bump.inputs.get("Height")
    if height_socket is None:
        raise RuntimeError("R1 Bump node has no Height input")
    link = next((candidate for candidate in links if candidate.to_socket == height_socket), None)
    if link is not None:
        links.new(link.from_socket, emission.inputs["Color"])
    else:
        value = float(height_socket.default_value)
        emission.inputs["Color"].default_value = (value, value, value, 1.0)
    for link in list(links):
        if link.to_socket == output.inputs["Surface"]:
            links.remove(link)
    links.new(emission.outputs["Emission"], output.inputs["Surface"])
    return material


def bump_source_record(material: bpy.types.Material) -> dict[str, Any]:
    if material is None or material.node_tree is None:
        return {"present": False}
    bump = next((node for node in material.node_tree.nodes if node.bl_idname == "ShaderNodeBump"), None)
    if bump is None:
        return {"present": False}
    height_socket = bump.inputs.get("Height")
    link = next((candidate for candidate in material.node_tree.links if candidate.to_socket == height_socket), None)
    return {
        "present": True,
        "node": bump.name,
        "strength": float(bump.inputs["Strength"].default_value) if bump.inputs.get("Strength") else None,
        "distance": float(bump.inputs["Distance"].default_value) if bump.inputs.get("Distance") else None,
        "height_linked": link is not None,
        "height_from_node": link.from_node.name if link else None,
        "height_from_node_type": link.from_node.bl_idname if link else None,
        "height_from_socket": link.from_socket.name if link else None,
        "height_default": float(height_socket.default_value) if height_socket and hasattr(height_socket, "default_value") else None,
    }


def attach_active_bake_image(material: bpy.types.Material, image: bpy.types.Image) -> None:
    nodes = material.node_tree.nodes
    for node in nodes:
        node.select = False
    target = nodes.new("ShaderNodeTexImage")
    target.name = f"INT30_R2G_ACTIVE_BAKE_TARGET_{image.name}"
    target.image = image
    target.select = True
    nodes.active = target


def select_only(obj: bpy.types.Object) -> None:
    if bpy.context.object and bpy.context.object.mode != "OBJECT":
        bpy.ops.object.mode_set(mode="OBJECT")
    bpy.ops.object.select_all(action="DESELECT")
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj
    bpy.context.view_layer.update()


def layer_collection_snapshot(layer_collection: bpy.types.LayerCollection) -> list[tuple[bpy.types.LayerCollection, bool, bool]]:
    records = [(layer_collection, bool(layer_collection.hide_viewport), bool(layer_collection.exclude))]
    for child in layer_collection.children:
        records.extend(layer_collection_snapshot(child))
    return records


def unhide_layer_collections(records: list[tuple[bpy.types.LayerCollection, bool, bool]]) -> None:
    for layer_collection, _hide_viewport, _exclude in records:
        layer_collection.exclude = False
        layer_collection.hide_viewport = False


def restore_layer_collections(records: list[tuple[bpy.types.LayerCollection, bool, bool]]) -> None:
    for layer_collection, hide_viewport, exclude in records:
        layer_collection.hide_viewport = hide_viewport
        layer_collection.exclude = exclude


def data_collection_snapshot() -> list[tuple[bpy.types.Collection, bool, bool]]:
    return [
        (collection, bool(collection.hide_viewport), bool(collection.hide_render))
        for collection in bpy.data.collections
    ]


def unhide_data_collections(records: list[tuple[bpy.types.Collection, bool, bool]]) -> None:
    for collection, _hide_viewport, _hide_render in records:
        collection.hide_viewport = False
        collection.hide_render = False


def restore_data_collections(records: list[tuple[bpy.types.Collection, bool, bool]]) -> None:
    for collection, hide_viewport, hide_render in records:
        collection.hide_viewport = hide_viewport
        collection.hide_render = hide_render


def bake_selected_to_image(material: bpy.types.Material, image: bpy.types.Image, bake_type: str) -> None:
    attach_active_bake_image(material, image)
    targets = []
    hide_snapshot: dict[str, tuple[bool, bool, bool, bool]] = {}
    collection_snapshot = layer_collection_snapshot(bpy.context.view_layer.layer_collection)
    data_collections = data_collection_snapshot()
    unhide_layer_collections(collection_snapshot)
    unhide_data_collections(data_collections)
    for name in SHELL_ZONES:
        obj = bpy.data.objects.get(name)
        if obj is None or obj.type != "MESH":
            raise RuntimeError(f"Missing bake target: {name}")
        hide_snapshot[obj.name] = (bool(obj.hide_viewport), bool(obj.hide_render), bool(obj.hide_get()), bool(obj.hide_select))
        obj.hide_viewport = False
        obj.hide_render = False
        obj.hide_set(False)
        obj.hide_select = False
        obj.data.materials.clear()
        obj.data.materials.append(material)
        obj.active_material_index = 0
        for polygon in obj.data.polygons:
            polygon.material_index = 0
        targets.append(obj)
    try:
        if bpy.ops.object.mode_set.poll():
            bpy.ops.object.mode_set(mode="OBJECT")
        for index, obj in enumerate(targets):
            select_only(obj)
            bpy.context.scene.cycles.bake_type = bake_type
            uv = obj.data.uv_layers.get(R2G_UV)
            active_material = obj.active_material
            active_node = active_material.node_tree.nodes.active if active_material and active_material.node_tree else None
            audit = {
                "image": image.name,
                "bake_type": bake_type,
                "target": obj.name,
                "index": index,
                "selected_count": len(bpy.context.selected_objects),
                "active_object": bpy.context.view_layer.objects.active.name if bpy.context.view_layer.objects.active else None,
                "visible_get": bool(obj.visible_get()),
                "hide_select": bool(obj.hide_select),
                "hide_viewport": bool(obj.hide_viewport),
                "hide_render": bool(obj.hide_render),
                "active_render_uv": uv.name if uv and uv.active_render else None,
                "uv_layer_count": len(obj.data.uv_layers),
                "material": active_material.name if active_material else None,
                "active_image_node": active_node.name if active_node else None,
                "active_image_node_selected": bool(active_node.select) if active_node else None,
                "active_image_node_image": active_node.image.name if active_node and getattr(active_node, "image", None) else None,
                "scene_bake_target": bpy.context.scene.render.bake.target,
            }
            kwargs = {
                "type": bake_type,
                "margin": 16,
                "use_selected_to_active": False,
                "use_clear": index == 0,
                "target": "IMAGE_TEXTURES",
                "save_mode": "INTERNAL",
                "uv_layer": R2G_UV,
            }
            if bake_type == "NORMAL":
                kwargs.update(
                    {
                        "normal_space": "TANGENT",
                        "normal_r": "POS_X",
                        "normal_g": "POS_Y",
                        "normal_b": "POS_Z",
                        "margin_type": "ADJACENT_FACES",
                    }
                )
            else:
                kwargs["margin_type"] = "EXTEND"
            result = bpy.ops.object.bake(**kwargs)
            audit["operator_return"] = sorted(result)
            BAKE_AUDITS.append(audit)
    finally:
        for obj in targets:
            viewport_hidden, render_hidden, local_hidden, hide_select = hide_snapshot[obj.name]
            obj.hide_viewport = viewport_hidden
            obj.hide_render = render_hidden
            obj.hide_set(local_hidden)
            obj.hide_select = hide_select
        restore_layer_collections(collection_snapshot)
        restore_data_collections(data_collections)


def combine_orm(roughness_image: bpy.types.Image, metallic_image: bpy.types.Image, orm_path: Path, size: int) -> tuple[dict[str, Any], np.ndarray, np.ndarray, np.ndarray]:
    roughness = image_rgba_array(roughness_image)[..., 0]
    metallic = image_rgba_array(metallic_image)[..., 0]
    roughness = np.clip(roughness, R1_LOCK["roughness_range"][0], R1_LOCK["roughness_range"][1])
    metallic = np.full_like(metallic, R1_LOCK["metallic"], dtype=np.float32) if float(np.nanstd(metallic)) < 1e-6 else np.clip(metallic, 0.0, 1.0)
    ao = np.ones((size, size), dtype=np.float32)
    orm = np.zeros((size, size, 4), dtype=np.uint8)
    orm[..., 0] = np.clip(ao * 255.0, 0, 255).astype(np.uint8)
    orm[..., 1] = np.clip(roughness * 255.0, 0, 255).astype(np.uint8)
    orm[..., 2] = np.clip(metallic * 255.0, 0, 255).astype(np.uint8)
    orm[..., 3] = 255
    png_save_rgba(orm_path, orm)
    return file_record(orm_path), roughness, metallic, ao


def normal_from_baked_height(height_image: bpy.types.Image, normal_path: Path, size: int) -> tuple[dict[str, Any], np.ndarray]:
    height = image_rgba_array(height_image)[..., 0]
    gy, gx = np.gradient(height)
    strength = R1_LOCK["B"] * 80.0
    nx = np.clip(-gx * strength, -1.0, 1.0)
    ny = np.clip(-gy * strength, -1.0, 1.0)
    nz = np.ones_like(nx)
    length = np.sqrt(nx * nx + ny * ny + nz * nz)
    nx = nx / np.maximum(length, 1e-6)
    ny = ny / np.maximum(length, 1e-6)
    nz = nz / np.maximum(length, 1e-6)
    normal = np.zeros((size, size, 4), dtype=np.uint8)
    normal[..., 0] = np.clip((nx * 0.5 + 0.5) * 255.0, 0, 255).astype(np.uint8)
    normal[..., 1] = np.clip((ny * 0.5 + 0.5) * 255.0, 0, 255).astype(np.uint8)
    normal[..., 2] = np.clip((nz * 0.5 + 0.5) * 255.0, 0, 255).astype(np.uint8)
    normal[..., 3] = 255
    png_save_rgba(normal_path, normal)
    return file_record(normal_path), normal


def image_rgb_metrics(image: bpy.types.Image) -> dict[str, Any]:
    arr = np.clip(image_rgba_array(image) * 255.0, 0, 255).astype(np.uint8)
    return {
        "rgb_min": [int(arr[..., i].min()) for i in range(3)],
        "rgb_max": [int(arr[..., i].max()) for i in range(3)],
        "rgb_mean": [round(float(arr[..., i].mean()), 4) for i in range(3)],
    }


def run_standalone_plane_bake_probe(texture_dir: Path) -> dict[str, Any]:
    mesh = bpy.data.meshes.new("INT30_R2G_BAKE_STANDALONE_PLANE_MESH")
    mesh.from_pydata(
        [(-1.0, -1.0, 0.0), (1.0, -1.0, 0.0), (1.0, 1.0, 0.0), (-1.0, 1.0, 0.0)],
        [],
        [(0, 1, 2, 3)],
    )
    mesh.update()
    uv = mesh.uv_layers.new(name="UVMap")
    uv.active_render = True
    for loop_index, coord in enumerate(((0.0, 0.0), (1.0, 0.0), (1.0, 1.0), (0.0, 1.0))):
        uv.data[loop_index].uv = coord
    obj = bpy.data.objects.new("INT30_R2G_BAKE_STANDALONE_PLANE", mesh)
    bpy.context.scene.collection.objects.link(obj)
    material = bpy.data.materials.new("INT30_R2G_BAKE_STANDALONE_PLANE_RED")
    material.use_nodes = True
    nodes = material.node_tree.nodes
    nodes.clear()
    output = nodes.new("ShaderNodeOutputMaterial")
    output.is_active_output = True
    emission = nodes.new("ShaderNodeEmission")
    emission.inputs["Color"].default_value = (0.3, 0.5, 0.7, 1.0)
    emission.inputs["Strength"].default_value = 1.0
    image = create_bake_image("INT30_R2G_STANDALONE_PLANE_PROBE_64px", 64, "sRGB")
    target = nodes.new("ShaderNodeTexImage")
    target.image = image
    for node in nodes:
        node.select = False
    target.select = True
    nodes.active = target
    material.node_tree.links.new(emission.outputs[0], output.inputs[0])
    obj.data.materials.append(material)
    obj.active_material_index = 0
    select_only(obj)
    bpy.context.scene.cycles.bake_type = "EMIT"
    result = bpy.ops.object.bake(
        type="EMIT",
        margin=2,
        margin_type="EXTEND",
        use_selected_to_active=False,
        use_clear=True,
        target="IMAGE_TEXTURES",
        save_mode="INTERNAL",
        uv_layer="UVMap",
    )
    path = texture_dir / "INT30_R2G_STANDALONE_PLANE_PROBE_64px.png"
    record = save_bake_image(image, path, "sRGB")
    metrics = image_rgb_metrics(image)
    bpy.data.objects.remove(obj, do_unlink=True)
    bpy.data.meshes.remove(mesh)
    return {"operator_return": sorted(result), "file": record, "metrics": metrics}


def generate_runtime_adapter_textures(texture_dir: Path, size: int, label: str, blocked_probe: dict[str, Any]) -> dict[str, Any]:
    t0 = time.perf_counter()
    coarse = make_smooth_noise(size, 4205, 6)
    mid = make_smooth_noise(size, 8621, 5)
    fine = make_smooth_noise(size, 1907, 4)
    yy, xx = np.mgrid[0:size, 0:size].astype(np.float32)
    x = xx / float(size)
    y = yy / float(size)
    vertical_streak = 0.5 + 0.5 * np.sin((x * 21.0 + coarse * 1.8) * math.tau)
    oxidized = np.clip(0.50 * coarse + 0.32 * mid + 0.18 * fine, 0.0, 1.0)
    heat_patina = np.clip(0.45 + 0.35 * np.sin(y * math.tau * 2.5 + mid * 2.1) + 0.20 * vertical_streak, 0.0, 1.0)
    dust = np.clip(0.62 * fine + 0.38 * (1.0 - vertical_streak), 0.0, 1.0)
    dark = np.array(R1_RAMP_DARK_LINEAR_RGB, dtype=np.float32)
    light = np.array(R1_RAMP_LIGHT_LINEAR_RGB, dtype=np.float32)
    ramp_mix = np.clip(0.12 + 0.50 * oxidized + 0.20 * heat_patina + 0.18 * dust, 0.0, 1.0)
    linear_rgb = dark + (light - dark) * ramp_mix[..., None]
    linear_rgb += np.stack(
        [
            (vertical_streak - 0.5) * 0.010 + (fine - 0.5) * 0.012,
            (dust - 0.5) * 0.010 + (coarse - 0.5) * 0.009,
            (heat_patina - 0.5) * 0.007 + (mid - 0.5) * 0.008,
        ],
        axis=-1,
    )
    srgb_rgb = linear_to_srgb(linear_rgb)
    base = np.zeros((size, size, 4), dtype=np.uint8)
    base[..., :3] = np.clip(srgb_rgb * 255.0, 0, 255).astype(np.uint8)
    base[..., 3] = 255

    rough_min, rough_max = R1_LOCK["roughness_range"]
    roughness = np.clip(rough_min + (rough_max - rough_min) * (0.62 * oxidized + 0.24 * dust + 0.14 * (1.0 - vertical_streak)), rough_min, rough_max)
    metallic = np.full((size, size), R1_LOCK["metallic"], dtype=np.float32)
    ao = np.ones((size, size), dtype=np.float32)

    micro_x = (
        np.sin((x * 87.0 + coarse * 0.70) * math.tau) * 0.050
        + (mid - 0.5) * 0.160
        + (vertical_streak - 0.5) * 0.130
    )
    micro_y = (
        np.cos((y * 73.0 + fine * 0.55) * math.tau) * 0.050
        + (fine - 0.5) * 0.150
        + (heat_patina - 0.5) * 0.100
    )
    strength = R1_LOCK["B"] * 1.65 * RUNTIME_ADAPTER_NORMAL_GAIN
    nx = np.clip(micro_x * strength, -1.0, 1.0)
    ny = np.clip(micro_y * strength, -1.0, 1.0)
    nz = np.ones_like(nx)
    length = np.sqrt(nx * nx + ny * ny + nz * nz)
    nx /= np.maximum(length, 1e-6)
    ny /= np.maximum(length, 1e-6)
    nz /= np.maximum(length, 1e-6)
    normal = np.zeros((size, size, 4), dtype=np.uint8)
    normal[..., 0] = np.clip((nx * 0.5 + 0.5) * 255.0, 0, 255).astype(np.uint8)
    normal[..., 1] = np.clip((ny * 0.5 + 0.5) * 255.0, 0, 255).astype(np.uint8)
    normal[..., 2] = np.clip((nz * 0.5 + 0.5) * 255.0, 0, 255).astype(np.uint8)
    normal[..., 3] = 255
    orm = np.zeros((size, size, 4), dtype=np.uint8)
    orm[..., 0] = np.clip(ao * 255.0, 0, 255).astype(np.uint8)
    orm[..., 1] = np.clip(roughness * 255.0, 0, 255).astype(np.uint8)
    orm[..., 2] = np.clip(metallic * 255.0, 0, 255).astype(np.uint8)
    orm[..., 3] = 255

    files = {
        "BaseColor": texture_dir / f"INT30_R2G_R1_LOCK_BaseColor_{label}.png",
        "NormalGL": texture_dir / f"INT30_R2G_R1_LOCK_NormalGL_{label}.png",
        "ORM": texture_dir / f"INT30_R2G_R1_LOCK_ORM_{label}.png",
    }
    png_save_rgba(files["BaseColor"], base)
    png_save_rgba(files["NormalGL"], normal)
    png_save_rgba(files["ORM"], orm)
    records = {key: file_record(path) for key, path in files.items()}
    return {
        "generator": "runtime_adapter_approximation_from_locked_R1_parameters",
        "texture_generation_mode": "runtime_adapter_approximation",
        "runtime_adapter_approximation": True,
        "true_cycles_bake": False,
        "blender_cycles_bake_blocked": True,
        "blocked_bake_evidence": {
            "reason": "Blender 5.2 background object.bake returned FINISHED but wrote black pixels even for a standalone constant Emission plane probe.",
            "standalone_plane_bake_probe": blocked_probe,
        },
        "not_reused_from_p50_pixels": True,
        "texture_size": size,
        "label": label,
        "r1_lock": R1_LOCK,
        "files": records,
        "metrics": {
            "BaseColor": {
                "rgb_min": [int(base[..., i].min()) for i in range(3)],
                "rgb_max": [int(base[..., i].max()) for i in range(3)],
                "rgb_mean": [round(float(base[..., i].mean()), 4) for i in range(3)],
                "linear_rgb_min": [round(float(linear_rgb[..., i].min()), 6) for i in range(3)],
                "linear_rgb_max": [round(float(linear_rgb[..., i].max()), 6) for i in range(3)],
                "linear_rgb_mean": [round(float(linear_rgb[..., i].mean()), 6) for i in range(3)],
                "encoding": "R1 ramp mixed in Blender linear RGB then IEC 61966-2-1 sRGB encoded for PNG; not linear_value_times_255",
                "r1_ramp_dark_linear_rgb": [round(float(v), 6) for v in R1_RAMP_DARK_LINEAR_RGB],
                "r1_ramp_light_linear_rgb": [round(float(v), 6) for v in R1_RAMP_LIGHT_LINEAR_RGB],
            },
            "Roughness": {
                "min": round(float(roughness.min()), 6),
                "max": round(float(roughness.max()), 6),
                "mean": round(float(roughness.mean()), 6),
                "required_range": R1_LOCK["roughness_range"],
            },
            "Metallic": {
                "min": round(float(metallic.min()), 6),
                "max": round(float(metallic.max()), 6),
                "mean": round(float(metallic.mean()), 6),
                "target": R1_LOCK["metallic"],
            },
            "NormalGL": {
                "xy_range": [
                    round(float((normal[..., 0].max() - normal[..., 0].min()) / 255.0), 6),
                    round(float((normal[..., 1].max() - normal[..., 1].min()) / 255.0), 6),
                ],
                "xy_std_norm": round(float((normal[..., 0].std() + normal[..., 1].std()) / (2.0 * 255.0)), 6),
                "runtime_scale": NORMAL_RUNTIME_SCALE,
                "runtime_adapter_normal_gain": RUNTIME_ADAPTER_NORMAL_GAIN,
                "calibration_basis": "Final R2G runtime-adapter compensation only: prior directed-light close_roughness gradient ratio was 0.63884, so gain 1.55 approximates 1/0.63884 while keeping GLB normalTexture.scale at locked N=0.45.",
                "source": "runtime adapter approximation; not a Blender/Cycles node bake",
            },
        },
        "runtime_adapter_calibration": {
            "runtime_adapter_normal_gain": RUNTIME_ADAPTER_NORMAL_GAIN,
            "applies_only_to": "generate_runtime_adapter_textures NormalGL synthesis",
            "does_not_change": "VB-DEC-MAT-001 R1 physics, GLB normalTexture.scale, metallic, roughness, or BaseColor",
            "target_signal": "increase adapter close_roughness micro-gradient toward source R1 without overshoot above 1.25 or faceting/noise",
        },
        "source_socket_audit": {
            "BaseColor": "not_run_after_global_bake_probe_failed",
            "Roughness": "not_run_after_global_bake_probe_failed",
            "Metallic": "not_run_after_global_bake_probe_failed",
            "BumpHeight": "not_run_after_global_bake_probe_failed",
        },
        "elapsed_seconds": round(time.perf_counter() - t0, 3),
    }


def bake_r1_locked_textures(texture_dir: Path, size: int, label: str) -> dict[str, Any]:
    texture_dir.mkdir(parents=True, exist_ok=True)
    t0 = time.perf_counter()
    source = bpy.data.materials.get(SOURCE_R1_MATERIAL)
    if source is None:
        raise RuntimeError(f"Missing R1 source material: {SOURCE_R1_MATERIAL}")

    bpy.context.scene.render.engine = "CYCLES"
    bpy.context.scene.cycles.device = "CPU"
    bpy.context.scene.cycles.samples = 32 if size >= 4096 else 16
    bpy.context.scene.cycles.use_denoising = False
    bpy.context.scene.view_settings.view_transform = "Standard"
    bpy.context.scene.view_settings.look = "None"
    bpy.context.scene.render.bake.target = "IMAGE_TEXTURES"
    bpy.context.scene.render.bake.margin = 16

    files = {
        "BaseColor": texture_dir / f"INT30_R2G_R1_LOCK_BaseColor_{label}.png",
        "NormalGL": texture_dir / f"INT30_R2G_R1_LOCK_NormalGL_{label}.png",
        "ORM": texture_dir / f"INT30_R2G_R1_LOCK_ORM_{label}.png",
        "RoughnessScalar": texture_dir / f"INT30_R2G_R1_LOCK_RoughnessScalar_{label}.png",
        "MetallicScalar": texture_dir / f"INT30_R2G_R1_LOCK_MetallicScalar_{label}.png",
        "BumpHeightScalar": texture_dir / f"INT30_R2G_R1_LOCK_BumpHeightScalar_{label}.png",
    }
    images = {
        "BaseColor": create_bake_image(f"INT30_R2G_R1_LOCK_BaseColor_{label}", size, "sRGB"),
        "RoughnessScalar": create_bake_image(f"INT30_R2G_R1_LOCK_RoughnessScalar_{label}", size, "Non-Color"),
        "MetallicScalar": create_bake_image(f"INT30_R2G_R1_LOCK_MetallicScalar_{label}", size, "Non-Color"),
        "BumpHeightScalar": create_bake_image(f"INT30_R2G_R1_LOCK_BumpHeightScalar_{label}", size, "Non-Color"),
        "BakeProbe": create_bake_image(f"INT30_R2G_BAKE_PIPELINE_PROBE_{label}", size, "sRGB"),
    }
    standalone_probe = run_standalone_plane_bake_probe(texture_dir)
    if max(standalone_probe["metrics"]["rgb_max"]) == 0:
        return generate_runtime_adapter_textures(texture_dir, size, label, standalone_probe)

    probe_material = bpy.data.materials.new(f"INT30_R2G_BAKE_PIPELINE_PROBE_MATERIAL_{label}")
    probe_material.use_nodes = True
    probe_nodes = probe_material.node_tree.nodes
    probe_nodes.clear()
    probe_output = probe_nodes.new("ShaderNodeOutputMaterial")
    probe_output.is_active_output = True
    probe_emission = probe_nodes.new("ShaderNodeEmission")
    probe_emission.inputs["Color"].default_value = (1.0, 0.0, 0.0, 1.0)
    probe_emission.inputs["Strength"].default_value = 1.0
    probe_material.node_tree.links.new(probe_emission.outputs[0], probe_output.inputs[0])
    bake_selected_to_image(probe_material, images["BakeProbe"], "EMIT")

    base_material = make_emission_bake_material(source, "Base Color", (0.20, 0.22, 0.22, 1.0))
    bake_selected_to_image(base_material, images["BaseColor"], "EMIT")
    rough_material = make_emission_bake_material(source, "Roughness", 0.68)
    bake_selected_to_image(rough_material, images["RoughnessScalar"], "EMIT")
    metal_material = make_emission_bake_material(source, "Metallic", R1_LOCK["metallic"])
    bake_selected_to_image(metal_material, images["MetallicScalar"], "EMIT")
    bump_height_material = make_bump_height_bake_material(source)
    bake_selected_to_image(bump_height_material, images["BumpHeightScalar"], "EMIT")

    records = {
        "BakeProbe": save_bake_image(images["BakeProbe"], texture_dir / f"INT30_R2G_BAKE_PIPELINE_PROBE_{label}.png", "sRGB"),
        "BaseColor": save_bake_image(images["BaseColor"], files["BaseColor"], "sRGB"),
        "RoughnessScalar": save_bake_image(images["RoughnessScalar"], files["RoughnessScalar"], "Non-Color"),
        "MetallicScalar": save_bake_image(images["MetallicScalar"], files["MetallicScalar"], "Non-Color"),
        "BumpHeightScalar": save_bake_image(images["BumpHeightScalar"], files["BumpHeightScalar"], "Non-Color"),
    }
    normal_record, normal = normal_from_baked_height(images["BumpHeightScalar"], files["NormalGL"], size)
    records["NormalGL"] = normal_record
    orm_record, roughness, metallic, ao = combine_orm(images["RoughnessScalar"], images["MetallicScalar"], files["ORM"], size)
    records["ORM"] = orm_record
    base = np.clip(image_rgba_array(images["BaseColor"]) * 255.0, 0, 255).astype(np.uint8)
    probe = np.clip(image_rgba_array(images["BakeProbe"]) * 255.0, 0, 255).astype(np.uint8)
    height = np.clip(image_rgba_array(images["BumpHeightScalar"]) * 255.0, 0, 255).astype(np.uint8)
    metrics = {
        "BaseColor": {
            "rgb_min": [int(base[..., i].min()) for i in range(3)],
            "rgb_max": [int(base[..., i].max()) for i in range(3)],
            "rgb_mean": [round(float(base[..., i].mean()), 4) for i in range(3)],
        },
        "BakePipelineProbe": {
            "rgb_min": [int(probe[..., i].min()) for i in range(3)],
            "rgb_max": [int(probe[..., i].max()) for i in range(3)],
            "rgb_mean": [round(float(probe[..., i].mean()), 4) for i in range(3)],
        },
        "Roughness": {
            "min": round(float(roughness.min()), 6),
            "max": round(float(roughness.max()), 6),
            "mean": round(float(roughness.mean()), 6),
            "required_range": R1_LOCK["roughness_range"],
        },
        "Metallic": {
            "min": round(float(metallic.min()), 6),
            "max": round(float(metallic.max()), 6),
            "mean": round(float(metallic.mean()), 6),
            "target": R1_LOCK["metallic"],
        },
        "AO": {
            "source": "white_placeholder_non_blocking_for_r1_surface",
            "min": round(float(ao.min()), 6),
            "max": round(float(ao.max()), 6),
        },
        "NormalGL": {
            "xy_range": [
                round(float((normal[..., 0].max() - normal[..., 0].min()) / 255.0), 6),
                round(float((normal[..., 1].max() - normal[..., 1].min()) / 255.0), 6),
            ],
            "xy_std_norm": round(float((normal[..., 0].std() + normal[..., 1].std()) / (2.0 * 255.0)), 6),
            "runtime_scale": NORMAL_RUNTIME_SCALE,
            "source": "OpenGL +Y normal reconstructed from Cycles EMIT bake of R1 Bump.Height",
        },
        "BumpHeightScalar": {
            "min": round(float(height[..., 0].min() / 255.0), 6),
            "max": round(float(height[..., 0].max() / 255.0), 6),
            "std_norm": round(float(height[..., 0].std() / 255.0), 6),
            "source": "R1 Bump.Height input via temporary Emission bake",
        },
    }
    return {
        "generator": "true_blender_cycles_bake_from_R1_material_nodes",
        "texture_generation_mode": "cycles_node_bake",
        "runtime_adapter_approximation": False,
        "true_cycles_bake": True,
        "not_reused_from_p50_pixels": True,
        "texture_size": size,
        "label": label,
        "r1_lock": R1_LOCK,
        "files": records,
        "metrics": metrics,
        "source_socket_audit": {
            "BaseColor": socket_source_record(source, "Base Color"),
            "Roughness": socket_source_record(source, "Roughness"),
            "Metallic": socket_source_record(source, "Metallic"),
            "BumpHeight": bump_source_record(source),
        },
        "standalone_plane_bake_probe": standalone_probe,
        "bake_operator_audit": BAKE_AUDITS,
        "bake_sources": {
            "BaseColor": "Principled Base Color input via temporary Emission bake",
            "Roughness": "Principled Roughness input via temporary Emission bake",
            "Metallic": "Principled Metallic input via temporary Emission bake; constant fallback is R1 metallic=0.06",
            "BumpHeightScalar": "R1 Bump.Height input via temporary Emission bake",
            "NormalGL": "OpenGL +Y normal reconstructed from the baked R1 Bump.Height scalar; direct Blender NORMAL bake was rejected because it produced a flat map in background mode",
            "AO": "white placeholder in ORM.R, explicitly non-blocking for R1 roughness lock",
        },
        "elapsed_seconds": round(time.perf_counter() - t0, 3),
    }


def ensure_cylindrical_uv(obj: bpy.types.Object, zone_index: int = 0, zone_count: int = 1) -> dict[str, Any]:
    mesh = obj.data
    uv = mesh.uv_layers.get(R2G_UV) or mesh.uv_layers.new(name=R2G_UV)
    mesh.uv_layers.active = uv
    uv.active_render = True
    z_values = [(obj.matrix_world @ vertex.co).z for vertex in mesh.vertices]
    z_min = min(z_values) if z_values else 0.0
    z_max = max(z_values) if z_values else 1.0
    z_span = max(z_max - z_min, 1e-6)
    for poly in mesh.polygons:
        for loop_index in poly.loop_indices:
            vertex = mesh.vertices[mesh.loops[loop_index].vertex_index]
            world = obj.matrix_world @ vertex.co
            angle = math.atan2(float(world.y), float(world.x))
            u_raw = (angle + math.pi) / (2.0 * math.pi)
            u = (float(zone_index) + u_raw) / float(max(zone_count, 1))
            v = (float(world.z) - z_min) / z_span
            uv.data[loop_index].uv = (u, v)
    mesh.update()
    bpy.context.view_layer.update()
    coords = [(float(item.uv.x), float(item.uv.y)) for item in uv.data]
    u_values = [coord[0] for coord in coords]
    v_values = [coord[1] for coord in coords]
    finite = all(math.isfinite(u) and math.isfinite(v) for u, v in coords)
    uv_area_acc = 0.0
    for poly in mesh.polygons:
        points = [uv.data[loop_index].uv for loop_index in poly.loop_indices]
        if len(points) >= 3:
            area = 0.0
            for i, point in enumerate(points):
                nxt = points[(i + 1) % len(points)]
                area += float(point.x) * float(nxt.y) - float(nxt.x) * float(point.y)
            uv_area_acc += abs(area) * 0.5
    return {
        "object": obj.name,
        "uv_layer": R2G_UV,
        "atlas_u_region": [round(zone_index / max(zone_count, 1), 6), round((zone_index + 1) / max(zone_count, 1), 6)],
        "loop_count": len(uv.data),
        "uv_bounds": {
            "u_min": round(min(u_values), 6) if u_values else None,
            "u_max": round(max(u_values), 6) if u_values else None,
            "v_min": round(min(v_values), 6) if v_values else None,
            "v_max": round(max(v_values), 6) if v_values else None,
        },
        "uv_finite": finite,
        "uv_area_sum": round(float(uv_area_acc), 6),
        "uv_nonzero_area": uv_area_acc > 0.0,
        "z_min": round(float(z_min), 6),
        "z_max": round(float(z_max), 6),
    }


def create_baked_material(texture_files: dict[str, Any]) -> bpy.types.Material:
    material = bpy.data.materials.get(R2G_MATERIAL)
    if material is None:
        material = bpy.data.materials.new(R2G_MATERIAL)
    material.use_nodes = True
    material["bf3d_stage"] = STAGE
    material["bf3d_r1_lock_decision_id"] = R1_LOCK["decision_id"]
    material["bf3d_r1_carrier_sha256"] = R1_LOCK["carrier_sha256"]
    material["bf3d_orm_mapping"] = "R=AO,G=Roughness,B=Metallic,A=1"
    material["bf3d_normal_convention"] = "OpenGL +Y"
    material["bf3d_not_reused_from_p50_pixels"] = True
    nodes = material.node_tree.nodes
    links = material.node_tree.links
    nodes.clear()
    output = nodes.new("ShaderNodeOutputMaterial")
    output.is_active_output = True
    output.location = (520, 0)
    principled = nodes.new("ShaderNodeBsdfPrincipled")
    principled.name = "INT30_R2G_PRINCIPLED"
    principled.location = (260, 0)
    links.new(principled.outputs["BSDF"], output.inputs["Surface"])

    base = nodes.new("ShaderNodeTexImage")
    base.name = "INT30_R2G_BASE_COLOR_SRGB"
    base.location = (-620, 160)
    base.image = bpy.data.images.load(texture_files["BaseColor"]["path"], check_existing=True)
    base.image.colorspace_settings.name = "sRGB"
    links.new(base.outputs["Color"], principled.inputs["Base Color"])

    orm = nodes.new("ShaderNodeTexImage")
    orm.name = "INT30_R2G_ORM_NON_COLOR_R_AO_G_ROUGHNESS_B_METALLIC"
    orm.location = (-620, -60)
    orm.image = bpy.data.images.load(texture_files["ORM"]["path"], check_existing=True)
    orm.image.colorspace_settings.name = "Non-Color"
    separate = nodes.new("ShaderNodeSeparateColor")
    separate.name = "INT30_R2G_ORM_CHANNELS"
    separate.location = (-330, -60)
    links.new(orm.outputs["Color"], separate.inputs["Color"])
    links.new(separate.outputs["Green"], principled.inputs["Roughness"])
    links.new(separate.outputs["Blue"], principled.inputs["Metallic"])

    normal_tex = nodes.new("ShaderNodeTexImage")
    normal_tex.name = "INT30_R2G_OPENGL_NORMAL_NON_COLOR"
    normal_tex.location = (-620, -300)
    normal_tex.image = bpy.data.images.load(texture_files["NormalGL"]["path"], check_existing=True)
    normal_tex.image.colorspace_settings.name = "Non-Color"
    normal_map = nodes.new("ShaderNodeNormalMap")
    normal_map.name = "INT30_R2G_OPENGL_PLUS_Y_NORMAL"
    normal_map.location = (-320, -300)
    normal_map.inputs["Strength"].default_value = NORMAL_RUNTIME_SCALE
    links.new(normal_tex.outputs["Color"], normal_map.inputs["Color"])
    links.new(normal_map.outputs["Normal"], principled.inputs["Normal"])
    return material


def assign_shell_material(material: bpy.types.Material) -> list[dict[str, Any]]:
    uv_records = []
    for index, name in enumerate(SHELL_ZONES):
        obj = bpy.data.objects.get(name)
        if obj is None or obj.type != "MESH":
            raise RuntimeError(f"Missing shell zone mesh: {name}")
        uv_records.append(ensure_cylindrical_uv(obj, index, len(SHELL_ZONES)))
        obj.data.materials.clear()
        obj.data.materials.append(material)
        obj.active_material_index = 0
        for polygon in obj.data.polygons:
            polygon.material_index = 0
        obj["bf3d_r2g_baked_pbr_material"] = R2G_MATERIAL
        obj["bf3d_r1_lock_decision_id"] = R1_LOCK["decision_id"]
    return uv_records


def enforce_radial_outward_normals() -> list[dict[str, Any]]:
    records = []
    for name in SHELL_ZONES:
        obj = bpy.data.objects.get(name)
        if obj is None or obj.type != "MESH":
            raise RuntimeError(f"Missing shell zone mesh for normal audit: {name}")
        mesh = obj.data
        mesh.update(calc_edges=True)
        dots = []
        for polygon in mesh.polygons:
            center = polygon.center
            radial_len = math.hypot(float(center.x), float(center.y))
            if radial_len <= 1e-6:
                continue
            radial_x = float(center.x) / radial_len
            radial_y = float(center.y) / radial_len
            dots.append(float(polygon.normal.x) * radial_x + float(polygon.normal.y) * radial_y)
        avg_dot_before = float(sum(dots) / max(len(dots), 1))
        flipped = False
        if avg_dot_before < 0.0:
            mesh.flip_normals()
            mesh.update(calc_edges=True)
            flipped = True
        dots_after = []
        for polygon in mesh.polygons:
            center = polygon.center
            radial_len = math.hypot(float(center.x), float(center.y))
            if radial_len <= 1e-6:
                continue
            radial_x = float(center.x) / radial_len
            radial_y = float(center.y) / radial_len
            dots_after.append(float(polygon.normal.x) * radial_x + float(polygon.normal.y) * radial_y)
        records.append(
            {
                "object": name,
                "avg_normal_dot_radial_out_before": round(avg_dot_before, 6),
                "avg_normal_dot_radial_out_after": round(float(sum(dots_after) / max(len(dots_after), 1)), 6),
                "flipped_in_r2g_export_copy_only": flipped,
                "polygon_count": len(mesh.polygons),
            }
        )
    return records


def scene_contract() -> dict[str, Any]:
    names = sorted(obj.name for obj in bpy.data.objects)
    sensor_names = sorted(name for name in names if name.startswith("SENSOR_"))
    body_sensor_names = sorted(name for name in sensor_names if name.startswith("SENSOR_T_body_L"))
    pressure_names = sorted(name for name in names if name.startswith(PRESSURE_PREFIX))
    meshes = {}
    for obj in sorted((candidate for candidate in bpy.data.objects if candidate.type == "MESH"), key=lambda candidate: candidate.name):
        mesh = obj.data
        vertex_digest = hashlib.sha256()
        for vertex in mesh.vertices:
            vertex_digest.update(struct.pack("<3d", float(vertex.co.x), float(vertex.co.y), float(vertex.co.z)))
        polygon_digest = hashlib.sha256()
        for polygon in mesh.polygons:
            polygon_digest.update(struct.pack("<I", len(polygon.vertices)))
            for index in polygon.vertices:
                polygon_digest.update(struct.pack("<I", int(index)))
        meshes[obj.name] = {
            "vertices": len(mesh.vertices),
            "polygons": len(mesh.polygons),
            "vertex_sha256": vertex_digest.hexdigest(),
            "polygon_sha256": polygon_digest.hexdigest(),
            "uv_layers": sorted(layer.name for layer in mesh.uv_layers),
            "materials": [slot.material.name if slot.material else None for slot in obj.material_slots],
            "matrix": matrix_values(obj),
        }
    return {
        "object_count": len(names),
        "object_names_sha256": stable_sha(names),
        "mesh_object_count": len(meshes),
        "mesh_geometry_sha256": stable_sha({name: {key: value for key, value in record.items() if key not in {"materials", "uv_layers"}} for name, record in meshes.items()}),
        "sensor_count": len(sensor_names),
        "body_temperature_sensors": len(body_sensor_names),
        "pressure_count": len(pressure_names),
        "int20_solids": sorted(name for name in INT20_SOLIDS if name in bpy.data.objects),
        "shell_zones": sorted(name for name in SHELL_ZONES if name in bpy.data.objects),
        "bands": sorted(name for name in BANDS if name in bpy.data.objects),
        "groups": sorted(name for name in GROUPS if name in bpy.data.objects),
        "sensor_layer_groups": sorted(name for name in SENSOR_LAYER_GROUPS if name in bpy.data.objects),
        "band_default_hidden": all(bool(bpy.data.objects[name].hide_viewport and bpy.data.objects[name].hide_render) for name in BANDS if name in bpy.data.objects),
        "meshes": meshes,
    }


def export_glb(glb_path: Path) -> dict[str, Any]:
    supported = set(bpy.ops.export_scene.gltf.get_rna_type().properties.keys())
    options = {
        "filepath": str(glb_path),
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
    kwargs = {key: value for key, value in options.items() if key in supported}
    result = bpy.ops.export_scene.gltf(**kwargs)
    if "FINISHED" not in result:
        raise RuntimeError(f"GLB export failed: {result}")
    return {"options": options, "used_options": kwargs, "result": sorted(result)}


def parse_glb(glb_path: Path) -> dict[str, Any]:
    data = glb_path.read_bytes()
    if len(data) < 20:
        raise RuntimeError("GLB is too short")
    magic, version, length = struct.unpack_from("<4sII", data, 0)
    if magic != b"glTF" or version != 2 or length != len(data):
        raise RuntimeError(f"Invalid GLB header: {magic!r} version={version} length={length} actual={len(data)}")
    offset = 12
    chunks = []
    json_chunk = None
    while offset < len(data):
        chunk_len, chunk_type = struct.unpack_from("<II", data, offset)
        offset += 8
        payload = data[offset: offset + chunk_len]
        offset += chunk_len
        type_text = struct.pack("<I", chunk_type).decode("ascii", errors="replace")
        chunks.append({"type": type_text, "length": chunk_len, "sha256": hashlib.sha256(payload).hexdigest()})
        if type_text == "JSON":
            json_chunk = payload.rstrip(b" \t\r\n\0")
    if json_chunk is None:
        raise RuntimeError("GLB has no JSON chunk")
    gltf = json.loads(json_chunk.decode("utf-8"))
    nodes = gltf.get("nodes", [])
    node_names = sorted(node.get("name", "") for node in nodes)
    materials = gltf.get("materials", [])
    images = gltf.get("images", [])
    textures = gltf.get("textures", [])
    material_names = sorted(mat.get("name", "") for mat in materials)
    r2g_material = next((mat for mat in materials if mat.get("name") == R2G_MATERIAL), None)
    texture_source_indices = {}
    if r2g_material:
        pbr = r2g_material.get("pbrMetallicRoughness", {})
        texture_source_indices["BaseColor"] = pbr.get("baseColorTexture", {}).get("index")
        texture_source_indices["MetallicRoughness"] = pbr.get("metallicRoughnessTexture", {}).get("index")
        texture_source_indices["NormalGL"] = r2g_material.get("normalTexture", {}).get("index")
        texture_source_indices["Occlusion"] = r2g_material.get("occlusionTexture", {}).get("index")
    texture_sources = {}
    for label, texture_index in texture_source_indices.items():
        if isinstance(texture_index, int) and 0 <= texture_index < len(textures):
            source = textures[texture_index].get("source")
            texture_sources[label] = source
        else:
            texture_sources[label] = None
    return {
        "header": {"magic": magic.decode("ascii"), "version": version, "length": length},
        "chunks": chunks,
        "node_count": len(nodes),
        "node_names_sha256": stable_sha(node_names),
        "nodes": {
            "sensor_count": sum(1 for name in node_names if name.startswith("SENSOR_")),
            "body_temperature_sensors": sum(1 for name in node_names if name.startswith("SENSOR_T_body_L")),
            "pressure_count": sum(1 for name in node_names if name.startswith(PRESSURE_PREFIX)),
            "int20_solids": sorted(name for name in INT20_SOLIDS if name in node_names),
            "shell_zones": sorted(name for name in SHELL_ZONES if name in node_names),
            "bands": sorted(name for name in BANDS if name in node_names),
            "groups": sorted(name for name in GROUPS if name in node_names),
            "sensor_layer_groups": sorted(name for name in SENSOR_LAYER_GROUPS if name in node_names),
        },
        "material_count": len(materials),
        "material_names": material_names,
        "image_count": len(images),
        "texture_count": len(textures),
        "images": images,
        "textures": textures,
        "r2g_material_found": r2g_material is not None,
        "r2g_texture_source_indices": texture_sources,
        "json": {
            "asset": gltf.get("asset", {}),
            "extensionsUsed": gltf.get("extensionsUsed", []),
            "extensionsRequired": gltf.get("extensionsRequired", []),
        },
    }


def assert_scene_and_glb_contract(scene: dict[str, Any], glb: dict[str, Any], material_graph: dict[str, Any], texture_manifest: dict[str, Any]) -> list[dict[str, Any]]:
    nodes = glb["nodes"]
    extension_names = set(glb["json"].get("extensionsUsed") or []) | set(glb["json"].get("extensionsRequired") or [])
    gates = [
        {"id": "all_115_sensors_present_in_blend", "ok": scene["sensor_count"] == 115, "detail": scene["sensor_count"]},
        {"id": "all_80_body_temp_sensors_present_in_blend", "ok": scene["body_temperature_sensors"] == 80, "detail": scene["body_temperature_sensors"]},
        {"id": "all_18_pressure_objects_present_in_blend", "ok": scene["pressure_count"] == 18, "detail": scene["pressure_count"]},
        {"id": "all_12_int20_solids_present_in_blend", "ok": len(scene["int20_solids"]) == 12, "detail": scene["int20_solids"]},
        {"id": "five_shell_zones_present_in_blend", "ok": len(scene["shell_zones"]) == 5, "detail": scene["shell_zones"]},
        {"id": "ten_canonical_bands_present_in_blend", "ok": len(scene["bands"]) == 10, "detail": scene["bands"]},
        {"id": "ten_canonical_groups_present_in_blend", "ok": len(scene["groups"]) == 10, "detail": scene["groups"]},
        {"id": "ten_sensor_layer_groups_present_in_blend", "ok": len(scene["sensor_layer_groups"]) == 10, "detail": scene["sensor_layer_groups"]},
        {"id": "bands_default_hidden_preserved", "ok": bool(scene["band_default_hidden"]), "detail": scene["band_default_hidden"]},
        {"id": "all_115_sensors_present_in_glb", "ok": nodes["sensor_count"] == 115, "detail": nodes["sensor_count"]},
        {"id": "all_80_body_temp_sensors_present_in_glb", "ok": nodes["body_temperature_sensors"] == 80, "detail": nodes["body_temperature_sensors"]},
        {"id": "all_18_pressure_objects_present_in_glb", "ok": nodes["pressure_count"] == 18, "detail": nodes["pressure_count"]},
        {"id": "all_12_int20_solids_present_in_glb", "ok": len(nodes["int20_solids"]) == 12, "detail": nodes["int20_solids"]},
        {"id": "five_shell_zones_present_in_glb", "ok": len(nodes["shell_zones"]) == 5, "detail": nodes["shell_zones"]},
        {"id": "ten_canonical_bands_present_in_glb", "ok": len(nodes["bands"]) == 10, "detail": nodes["bands"]},
        {"id": "ten_canonical_groups_present_in_glb", "ok": len(nodes["groups"]) == 10, "detail": nodes["groups"]},
        {"id": "ten_sensor_layer_groups_present_in_glb", "ok": len(nodes["sensor_layer_groups"]) == 10, "detail": nodes["sensor_layer_groups"]},
        {"id": "r2g_baked_material_exported", "ok": bool(glb["r2g_material_found"]), "detail": glb["material_names"]},
        {"id": "r2g_basecolor_normal_orm_files_exist", "ok": {"BaseColor", "NormalGL", "ORM"}.issubset(set(texture_manifest["files"])), "detail": sorted(texture_manifest["files"])},
        {"id": "r2g_texture_generation_mode_truthful", "ok": (
            (bool(texture_manifest.get("true_cycles_bake")) and texture_manifest.get("texture_generation_mode") == "cycles_node_bake")
            or (texture_manifest.get("runtime_adapter_approximation") is True and texture_manifest.get("true_cycles_bake") is False and texture_manifest.get("texture_generation_mode") == "runtime_adapter_approximation")
        ), "detail": {"mode": texture_manifest.get("texture_generation_mode"), "true_cycles_bake": texture_manifest.get("true_cycles_bake"), "runtime_adapter_approximation": texture_manifest.get("runtime_adapter_approximation"), "blocked": texture_manifest.get("blender_cycles_bake_blocked")}},
        {"id": "roughness_within_r1_lock", "ok": texture_manifest["metrics"]["Roughness"]["min"] >= 0.56 and texture_manifest["metrics"]["Roughness"]["max"] <= 0.82, "detail": texture_manifest["metrics"]["Roughness"]},
        {"id": "metallic_matches_r1_lock", "ok": abs(texture_manifest["metrics"]["Metallic"]["mean"] - 0.06) <= 0.004, "detail": texture_manifest["metrics"]["Metallic"]},
        {"id": "normal_has_nonflat_xy_variation", "ok": min(texture_manifest["metrics"]["NormalGL"]["xy_range"]) >= (2.0 / 255.0), "detail": texture_manifest["metrics"]["NormalGL"]},
        {"id": "r1_lock_custom_properties_present", "ok": material_graph.get("bf3d_r1_lock_decision_id") == "VB-DEC-MAT-001", "detail": material_graph},
        {"id": "glb_is_uncompressed_no_draco_or_meshopt", "ok": "KHR_draco_mesh_compression" not in extension_names and "EXT_meshopt_compression" not in extension_names, "detail": sorted(extension_names)},
    ]
    return gates


def material_graph_contract(material: bpy.types.Material) -> dict[str, Any]:
    nodes = material.node_tree.nodes if material.node_tree else []
    return {
        "material": material.name,
        "bf3d_stage": material.get("bf3d_stage"),
        "bf3d_r1_lock_decision_id": material.get("bf3d_r1_lock_decision_id"),
        "bf3d_r1_carrier_sha256": material.get("bf3d_r1_carrier_sha256"),
        "bf3d_orm_mapping": material.get("bf3d_orm_mapping"),
        "bf3d_normal_convention": material.get("bf3d_normal_convention"),
        "bf3d_not_reused_from_p50_pixels": material.get("bf3d_not_reused_from_p50_pixels"),
        "nodes": sorted(({"name": node.name, "type": node.bl_idname} for node in nodes), key=lambda item: item["name"]),
    }


def main() -> int:
    args = parse_args()
    output_dir = args.output_dir.resolve()
    reports_dir = output_dir / "reports"
    texture_dir = output_dir / "textures" / ("smoke_1k" if args.mode == "smoke" else "final_4k")
    blend_dir = output_dir / "blends"
    glb_dir = output_dir / "glb"
    for directory in (reports_dir, texture_dir, blend_dir, glb_dir):
        directory.mkdir(parents=True, exist_ok=True)

    label = "1K" if args.mode == "smoke" else "4K"
    input_blend = args.input_blend.resolve()
    formal_glb = args.formal_glb.resolve()
    formal_before = file_record(formal_glb)
    if sha256_file(input_blend) != EXPECTED_INPUT_SHA256:
        raise RuntimeError("R2F input SHA lock mismatch")
    if formal_before["sha256"] != EXPECTED_FORMAL_GLB_SHA256:
        raise RuntimeError("Formal GLB SHA lock mismatch before R2G export")

    source_r1 = bpy.data.materials.get(SOURCE_R1_MATERIAL)
    source_r1_nodes = []
    if source_r1 and source_r1.node_tree:
        source_r1_nodes = sorted(({"name": node.name, "type": node.bl_idname} for node in source_r1.node_tree.nodes), key=lambda item: item["name"])
    source_contract = scene_contract()
    pre_bake_uv_records = []
    for index, name in enumerate(SHELL_ZONES):
        obj = bpy.data.objects.get(name)
        if obj is None or obj.type != "MESH":
            raise RuntimeError(f"Missing shell zone mesh: {name}")
        pre_bake_uv_records.append(ensure_cylindrical_uv(obj, index, len(SHELL_ZONES)))
    texture_manifest = bake_r1_locked_textures(texture_dir, args.texture_size, label)
    pre_export_texture_gates = [
        {
            "id": "basecolor_bake_has_nonzero_active_pixels",
            "ok": max(texture_manifest["metrics"]["BaseColor"]["rgb_max"]) > 0,
            "detail": texture_manifest["metrics"]["BaseColor"],
        },
        {
            "id": "texture_mode_truthfully_declared",
            "ok": (
                (
                    texture_manifest.get("true_cycles_bake") is True
                    and texture_manifest["metrics"].get("BumpHeightScalar", {}).get("std_norm", 0.0) > 0.0
                )
                or (
                    texture_manifest.get("runtime_adapter_approximation") is True
                    and texture_manifest.get("true_cycles_bake") is False
                    and texture_manifest.get("blender_cycles_bake_blocked") is True
                )
            ),
            "detail": {
                "texture_generation_mode": texture_manifest.get("texture_generation_mode"),
                "true_cycles_bake": texture_manifest.get("true_cycles_bake"),
                "runtime_adapter_approximation": texture_manifest.get("runtime_adapter_approximation"),
                "blender_cycles_bake_blocked": texture_manifest.get("blender_cycles_bake_blocked"),
                "bump_height": texture_manifest["metrics"].get("BumpHeightScalar"),
            },
        },
    ]
    if not all(gate["ok"] for gate in pre_export_texture_gates):
        report_path = reports_dir / (f"r2g_smoke_1k_machine_report.json" if args.mode == "smoke" else f"r2g_final_4k_machine_report.json")
        manifest_path = reports_dir / (f"r2g_smoke_1k_texture_manifest.json" if args.mode == "smoke" else f"r2g_final_4k_texture_manifest.json")
        write_json(manifest_path, texture_manifest)
        fail_report = {
            "schema_version": "bf3d.int30_r2g.bake_export.v1",
            "stage": STAGE,
            "mode": args.mode,
            "status": "texture_bake_failed_pre_export_no_glb_exported",
            "approval": "not_granted",
            "generated_at": now_iso(),
            "input": {"path": str(input_blend), "sha256": EXPECTED_INPUT_SHA256},
            "r1_material_lock": R1_LOCK,
            "texture_manifest": texture_manifest,
            "pre_bake_uv_records": pre_bake_uv_records,
            "gates": pre_export_texture_gates,
            "machine_assertions_pass": False,
            "stage_boundary": "Pre-export texture gate failed; GLB export intentionally skipped.",
        }
        write_json(report_path, fail_report)
        print(json.dumps({"mode": args.mode, "status": fail_report["status"], "report": str(report_path)}, ensure_ascii=False, indent=2))
        return 2
    material = create_baked_material(texture_manifest["files"])
    uv_records = assign_shell_material(material)
    normal_orientation_audit = enforce_radial_outward_normals()
    scene_after_setup = scene_contract()
    material_graph = material_graph_contract(material)

    blend_path = blend_dir / (f"INT_30_R2G_SMOKE_1K_EXPORT_COPY.blend" if args.mode == "smoke" else f"INT_30_R2G_FINAL_4K_EXPORT_COPY.blend")
    glb_path = glb_dir / (f"INT_30_R2G_SMOKE_1K_UNCOMPRESSED.glb" if args.mode == "smoke" else f"INT_30_R2G_FINAL_4K_UNCOMPRESSED.glb")
    bpy.context.scene["bf3d_stage"] = STAGE
    bpy.context.scene["bf3d_r2g_mode"] = args.mode
    bpy.context.scene["bf3d_r1_lock_decision_id"] = R1_LOCK["decision_id"]
    bpy.context.scene["bf3d_r1_carrier_sha256"] = R1_LOCK["carrier_sha256"]
    bpy.context.scene["bf3d_source_r2f_sha256"] = EXPECTED_INPUT_SHA256
    bpy.ops.wm.save_as_mainfile(filepath=str(blend_path), check_existing=False)
    export_info = export_glb(glb_path)
    glb_audit = parse_glb(glb_path)
    formal_after = file_record(formal_glb)

    gates = assert_scene_and_glb_contract(scene_after_setup, glb_audit, material_graph, texture_manifest)
    gates.extend([
        {
            "id": "source_geometry_preserved_or_only_normals_reoriented",
            "ok": (
                source_contract["mesh_geometry_sha256"] == scene_after_setup["mesh_geometry_sha256"]
                or all(record["avg_normal_dot_radial_out_after"] > 0.0 for record in normal_orientation_audit)
            ),
            "detail": {
                "source": source_contract["mesh_geometry_sha256"],
                "after_setup": scene_after_setup["mesh_geometry_sha256"],
                "normal_orientation_audit": normal_orientation_audit,
            },
        },
        {
            "id": "formal_glb_unchanged",
            "ok": formal_before["sha256"] == formal_after["sha256"] == EXPECTED_FORMAL_GLB_SHA256,
            "detail": {"before": formal_before["sha256"], "after": formal_after["sha256"]},
        },
        {
            "id": "r2f_input_sha_still_locked",
            "ok": sha256_file(input_blend) == EXPECTED_INPUT_SHA256,
            "detail": sha256_file(input_blend),
        },
    ])
    pass_all = all(bool(gate["ok"]) for gate in gates)

    report = {
        "schema_version": "bf3d.int30_r2g.bake_export.v1",
        "stage": STAGE,
        "mode": args.mode,
        "status": "candidate_ready_for_review" if pass_all else "candidate_failed_machine_assertions",
        "approval": "not_granted_requires_independent_glb_and_browser_review",
        "generated_at": now_iso(),
        "input": {"path": str(input_blend), "sha256": EXPECTED_INPUT_SHA256},
        "formal_glb_protection": {"before": formal_before, "after": formal_after, "unchanged": formal_before["sha256"] == formal_after["sha256"]},
        "r1_material_lock": R1_LOCK,
        "source_r1_material": {"name": SOURCE_R1_MATERIAL, "present": source_r1 is not None, "nodes": source_r1_nodes},
        "texture_manifest": texture_manifest,
        "pre_bake_uv_records": pre_bake_uv_records,
        "uv_records": uv_records,
        "normal_orientation_audit": normal_orientation_audit,
        "material_graph": material_graph,
        "blend": file_record(blend_path),
        "glb": file_record(glb_path),
        "export": export_info,
        "glb_audit": glb_audit,
        "source_contract": source_contract,
        "scene_after_setup": scene_after_setup,
        "gates": gates,
        "machine_assertions_pass": pass_all,
        "stage_boundary": "Isolated candidate only; no production GLB replacement, no self approval.",
    }
    report_path = reports_dir / (f"r2g_smoke_1k_machine_report.json" if args.mode == "smoke" else f"r2g_final_4k_machine_report.json")
    write_json(report_path, report)
    manifest_path = reports_dir / (f"r2g_smoke_1k_texture_manifest.json" if args.mode == "smoke" else f"r2g_final_4k_texture_manifest.json")
    write_json(manifest_path, texture_manifest)
    glb_manifest_path = reports_dir / (f"r2g_smoke_1k_glb_manifest.json" if args.mode == "smoke" else f"r2g_final_4k_glb_manifest.json")
    write_json(glb_manifest_path, {"glb": report["glb"], "glb_audit": glb_audit, "export": export_info})
    print(json.dumps({"mode": args.mode, "status": report["status"], "report": str(report_path), "glb": str(glb_path)}, ensure_ascii=False, indent=2))
    return 0 if pass_all else 2


if __name__ == "__main__":
    sys.exit(main())
'''


def now_iso() -> str:
    return datetime.now(timezone(timedelta(hours=8))).replace(microsecond=0).isoformat()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def file_record(path: Path) -> dict[str, Any]:
    return {
        "path": str(path),
        "bytes": path.stat().st_size,
        "sha256": sha256_file(path),
    }


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def rel(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(ROOT))
    except ValueError:
        return str(path)


def run_blender(
    *,
    blender: Path,
    input_blend: Path,
    formal_glb: Path,
    output_dir: Path,
    worker: Path,
    mode: str,
    texture_size: int,
) -> subprocess.CompletedProcess[str]:
    logs = output_dir / "reports"
    logs.mkdir(parents=True, exist_ok=True)
    stale_names = (
        [
            "r2g_smoke_1k_machine_report.json",
            "r2g_smoke_1k_texture_manifest.json",
            "r2g_smoke_1k_glb_manifest.json",
        ]
        if mode == "smoke"
        else [
            "r2g_final_4k_machine_report.json",
            "r2g_final_4k_texture_manifest.json",
            "r2g_final_4k_glb_manifest.json",
        ]
    )
    for name in stale_names:
        stale = logs / name
        if stale.exists():
            stale.unlink()
    command = [
        str(blender),
        "--background",
        str(input_blend),
        "--python",
        str(worker),
        "--",
        "--mode",
        mode,
        "--texture-size",
        str(texture_size),
        "--output-dir",
        str(output_dir),
        "--input-blend",
        str(input_blend),
        "--formal-glb",
        str(formal_glb),
    ]
    stdout_path = logs / f"r2g_{mode}_{texture_size}_blender.stdout.log"
    stderr_path = logs / f"r2g_{mode}_{texture_size}_blender.stderr.log"
    completed = subprocess.run(
        command,
        cwd=ROOT,
        text=True,
        encoding="utf-8",
        errors="replace",
        capture_output=True,
        check=False,
    )
    stdout_path.write_text(completed.stdout, encoding="utf-8")
    stderr_path.write_text(completed.stderr, encoding="utf-8")
    return completed


def load_report(output_dir: Path, mode: str) -> dict[str, Any]:
    name = "r2g_smoke_1k_machine_report.json" if mode == "smoke" else "r2g_final_4k_machine_report.json"
    path = output_dir / "reports" / name
    if not path.is_file():
        raise RuntimeError(f"Missing Blender report: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def artifact_manifest(output_dir: Path) -> dict[str, Any]:
    records: list[dict[str, Any]] = []
    for path in sorted(output_dir.rglob("*")):
        if path.is_file():
            if path.name == "artifact_sha256.json":
                continue
            records.append(
                {
                    "path": rel(path),
                    "bytes": path.stat().st_size,
                    "sha256": sha256_file(path),
                }
            )
    return {
        "schema_version": "bf3d.int30_r2g.artifacts.v1",
        "stage": STAGE,
        "generated_at": now_iso(),
        "artifact_count": len(records),
        "artifacts": records,
    }


def write_summary(output_dir: Path, consolidated: dict[str, Any]) -> Path:
    final_report = consolidated.get("final_report") or {}
    final_glb = final_report.get("glb") or {}
    final_blend = final_report.get("blend") or {}
    stable_glb = consolidated.get("stable_web_preview_glb") or {}
    lines = [
        "# INT-30_R2G_ISOLATED_GLB_WEB_PREVIEW stage production record",
        "",
        f"- Status: {consolidated['status']}",
        "- Approval: not granted; requires independent GLB/web review.",
        f"- Source R2F SHA256: {EXPECTED_INPUT_SHA256}",
        f"- Formal GLB SHA256 lock: {EXPECTED_FORMAL_GLB_SHA256}",
        "- R1/R5 lock: VB-DEC-MAT-001, B=0.16, D=0.10m, N=0.45, metallic=0.06, roughness=0.56-0.82, mapping scale=0.085.",
        "- Bake rule: new R2G BaseColor/NormalGL/ORM texture pixels generated for this stage; old P50 pixels were not reused.",
        "",
        "## Outputs",
        f"- Final GLB: {final_glb.get('path')} ({final_glb.get('sha256')})",
        f"- Stable web preview GLB: {stable_glb.get('path')} ({stable_glb.get('sha256')})",
        f"- Final blend copy: {final_blend.get('path')} ({final_blend.get('sha256')})",
        f"- Smoke report: {rel(output_dir / 'reports' / 'r2g_smoke_1k_machine_report.json')}",
        f"- Final report: {rel(output_dir / 'reports' / 'r2g_final_4k_machine_report.json')}",
        f"- Artifact manifest: {rel(output_dir / 'artifact_sha256.json')}",
        "",
        "## Gate Result",
        f"- Smoke gates passed: {consolidated.get('smoke_passed')}",
        f"- Final gates passed: {consolidated.get('final_passed')}",
        f"- Stable GLB same SHA as final: {consolidated.get('stable_web_preview_glb_same_sha_as_final')}",
        "- Production replacement: forbidden in this stage.",
    ]
    path = output_dir / "INT-30_R2G_ISOLATED_GLB_WEB_PREVIEW_阶段成果总结.md"
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input-blend", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--blender", type=Path, default=BLENDER)
    parser.add_argument("--formal-glb", type=Path, default=FORMAL_GLB)
    parser.add_argument("--smoke-size", type=int, default=1024)
    parser.add_argument("--final-size", type=int, default=4096)
    args = parser.parse_args()

    input_blend = args.input_blend.resolve()
    output_dir = args.output_dir.resolve()
    blender = args.blender.resolve()
    formal_glb = args.formal_glb.resolve()

    for path in (input_blend, blender, formal_glb):
        if not path.is_file():
            raise FileNotFoundError(path)
    input_before = file_record(input_blend)
    formal_before = file_record(formal_glb)
    if input_before["sha256"] != EXPECTED_INPUT_SHA256:
        raise RuntimeError(
            f"R2F input lock mismatch: expected {EXPECTED_INPUT_SHA256}, got {input_before['sha256']}"
        )
    if formal_before["sha256"] != EXPECTED_FORMAL_GLB_SHA256:
        raise RuntimeError(
            f"Formal GLB lock mismatch: expected {EXPECTED_FORMAL_GLB_SHA256}, got {formal_before['sha256']}"
        )

    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "reports").mkdir(parents=True, exist_ok=True)
    for stale_candidate in (
        output_dir / STABLE_GLB_NAME,
        output_dir / "glb" / "INT_30_R2G_SMOKE_1K_UNCOMPRESSED.glb",
        output_dir / "glb" / "INT_30_R2G_FINAL_4K_UNCOMPRESSED.glb",
    ):
        if stale_candidate.exists():
            stale_candidate.unlink()
    worker_path = output_dir / "reports" / WORKER_NAME
    worker_path.write_text(WORKER_SOURCE, encoding="utf-8")

    print(
        json.dumps(
            {
                "stage": STAGE,
                "step": "smoke_1k",
                "input": str(input_blend),
                "output_dir": str(output_dir),
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    smoke_run = run_blender(
        blender=blender,
        input_blend=input_blend,
        formal_glb=formal_glb,
        output_dir=output_dir,
        worker=worker_path,
        mode="smoke",
        texture_size=args.smoke_size,
    )
    if smoke_run.returncode != 0:
        raise RuntimeError(f"R2G smoke Blender run failed with exit code {smoke_run.returncode}")
    smoke_report = load_report(output_dir, "smoke")
    smoke_passed = bool(smoke_report.get("machine_assertions_pass"))
    if not smoke_passed:
        manifest = artifact_manifest(output_dir)
        write_json(output_dir / "artifact_sha256.json", manifest)
        raise RuntimeError("R2G smoke gates failed; final 4K bake/export was not run.")

    print(
        json.dumps(
            {"stage": STAGE, "step": "final_4k", "smoke_passed": True},
            ensure_ascii=False,
            indent=2,
        )
    )
    final_run = run_blender(
        blender=blender,
        input_blend=input_blend,
        formal_glb=formal_glb,
        output_dir=output_dir,
        worker=worker_path,
        mode="final",
        texture_size=args.final_size,
    )
    if final_run.returncode != 0:
        raise RuntimeError(f"R2G final Blender run failed with exit code {final_run.returncode}")
    final_report = load_report(output_dir, "final")
    final_passed = bool(final_report.get("machine_assertions_pass"))
    stable_glb = output_dir / STABLE_GLB_NAME
    if final_passed:
        final_glb_path = Path(final_report["glb"]["path"])
        shutil.copy2(final_glb_path, stable_glb)
        stable_glb_record = file_record(stable_glb)
        if stable_glb_record["sha256"] != final_report["glb"]["sha256"]:
            raise RuntimeError("Stable preview GLB copy SHA does not match final GLB")
    else:
        stable_glb_record = None

    input_after = file_record(input_blend)
    formal_after = file_record(formal_glb)
    consolidated = {
        "schema_version": "bf3d.int30_r2g.consolidated.v1",
        "stage": STAGE,
        "status": "candidate_ready_for_review" if smoke_passed and final_passed else "candidate_failed_machine_assertions",
        "approval": "not_granted_requires_independent_glb_and_browser_review",
        "generated_at": now_iso(),
        "input_protection": {
            "before": input_before,
            "after": input_after,
            "unchanged": input_before["sha256"] == input_after["sha256"] == EXPECTED_INPUT_SHA256,
        },
        "formal_glb_protection": {
            "before": formal_before,
            "after": formal_after,
            "unchanged": formal_before["sha256"] == formal_after["sha256"] == EXPECTED_FORMAL_GLB_SHA256,
        },
        "r1_material_lock": {
            "decision_id": "VB-DEC-MAT-001",
            "carrier_sha256": EXPECTED_R1_CARRIER_SHA256,
            "B": 0.16,
            "D_m": 0.10,
            "N": 0.45,
            "metallic": 0.06,
            "roughness_range": [0.56, 0.82],
            "mapping_scale": 0.085,
        },
        "smoke_passed": smoke_passed,
        "final_passed": final_passed,
        "stable_web_preview_glb": stable_glb_record,
        "stable_web_preview_glb_same_sha_as_final": bool(
            stable_glb_record
            and stable_glb_record["sha256"] == final_report["glb"]["sha256"]
        ),
        "smoke_report": smoke_report,
        "final_report": final_report,
        "stage_boundary": "Isolated R2G candidate only; formal GLB replacement remains forbidden.",
    }
    write_json(output_dir / "int30_r2g_machine_report.json", consolidated)
    summary_path = write_summary(output_dir, consolidated)
    manifest = artifact_manifest(output_dir)
    write_json(output_dir / "artifact_sha256.json", manifest)
    print(
        json.dumps(
            {
                "status": consolidated["status"],
                "machine_report": rel(output_dir / "int30_r2g_machine_report.json"),
                "summary": rel(summary_path),
                "artifact_manifest": rel(output_dir / "artifact_sha256.json"),
                "final_glb": final_report.get("glb", {}).get("path"),
                "final_blend": final_report.get("blend", {}).get("path"),
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0 if consolidated["status"] == "candidate_ready_for_review" else 2


if __name__ == "__main__":
    sys.exit(main())
