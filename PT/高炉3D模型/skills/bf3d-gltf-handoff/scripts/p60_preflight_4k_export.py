"""Build an isolated, uncompressed P60 glTF preflight from the P50 4K blend.

This script intentionally does not replace the production GLB and cannot grant
P50/P60 approval.  It adds the glTF-specific occlusion hookup to a copy of the
P50 material, exports a baseline GLB, reloads it in Blender, and writes
machine-readable contract evidence.

Run with Blender 5.2 or newer, for example:

    blender --background P50_FULL_FURNACE_BAKE_CANDIDATE.blend \
      --python p60_preflight_4k_export.py -- \
      --input-blend P50_FULL_FURNACE_BAKE_CANDIDATE.blend \
      --output-dir P60_PREFLIGHT_4K_20260717_R1
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import re
import shutil
import struct
import subprocess
import sys
import time
from pathlib import Path, PureWindowsPath
from typing import Any, Iterable

import bpy


SCRIPT_PATH = Path(__file__).resolve()
REPO_ROOT = SCRIPT_PATH.parents[5]
DEFAULT_INPUT = (
    REPO_ROOT
    / "PT"
    / "高炉3D模型"
    / "work"
    / "P50_MASTER_4K_20260717_R1"
    / "P50_FULL_FURNACE_BAKE_CANDIDATE.blend"
)
DEFAULT_OUTPUT = (
    REPO_ROOT
    / "PT"
    / "高炉3D模型"
    / "work"
    / "P60_PREFLIGHT_4K_20260717_R1"
)
DEFAULT_FORMAL_GLB = (
    REPO_ROOT / "高炉前端数据" / "models" / "gl02_blast_furnace.glb"
)

EXPECTED_FORMAL_GLB_SHA256 = (
    "808960f1b2703e7fb27df35f1b1b1a17063b9b10d2267acba593fc3872b62af6"
)
P50_MATERIAL_NAME = "P50_GL02_FULL_FURNACE_BAKED_STEEL"
P50_BASE_IMAGE = "P50_GL02_BaseColor_4K"
P50_ORM_IMAGE = "P50_GL02_ORM_4K"
P50_NORMAL_IMAGE = "P50_GL02_NormalGL_4K"
P50_UV_NAME = "P50_UV0"
NORMAL_SCALE = 0.25

PROCESS_ZONES = (
    "APPROX_GL02_FURNACE_HEARTH",
    "APPROX_GL02_FURNACE_BOSH",
    "APPROX_GL02_FURNACE_BELLY",
    "APPROX_GL02_FURNACE_SHAFT",
    "APPROX_GL02_FURNACE_THROAT",
)
LAYERS = tuple(f"L{number}" for number in range(7, 17))
SECTORS = tuple("ABCDEFGH")
P36_GROUPS = tuple(f"GL02_FURNACE_TEMP_LAYER_{layer}" for layer in LAYERS)
P36_BANDS = tuple(f"APPROX_GL02_TEMP_LAYER_BAND_{layer}" for layer in LAYERS)
SENSOR_LAYER_GROUPS = tuple(f"GL02_SENSOR_LAYER_{layer}" for layer in LAYERS)
INTERNAL_PROCESS_OBJECTS = (
    "APPROX_GL02_burden_column_layered_charge_coke",
    "APPROX_GL02_burden_column_layered_charge_ore",
    "APPROX_GL02_cohesive_zone_softening_melting_band",
    "APPROX_GL02_countercurrent_gas_flow_streamlines",
    "APPROX_GL02_internal_burden_reference_bands",
    "APPROX_GL02_hearth_molten_iron_pool",
    "APPROX_GL02_hearth_slag_layer",
    "APPROX_GL02_hot_blast_raceway_plumes",
    "APPROX_GL02_cold_blast_supply_flow",
)
INTERNAL_PROCESS_PREFIXES = ("APPROX_GL02_hot_metal_dripping_droplet_",)

EXPORT_COPY_NAME = "P60_PREFLIGHT_EXPORT_COPY.blend"
GLB_NAME = "P60_PREFLIGHT_4K_UNCOMPRESSED.glb"
REPORT_NAME = "p60_preflight_report.json"
MANIFEST_NAME = "p60_preflight_manifest.json"
CHECKSUM_NAME = "p60_preflight_sha256.json"
VALIDATOR_STATUS_NAME = "gltf_validator_status.json"


def parse_args() -> argparse.Namespace:
    raw = sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else []
    parser = argparse.ArgumentParser(
        description="Isolated P60 4K uncompressed GLB export and contract preflight."
    )
    parser.add_argument("--input-blend", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--formal-glb", type=Path, default=DEFAULT_FORMAL_GLB)
    return parser.parse_args(raw)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def file_record(path: Path) -> dict[str, Any]:
    return {
        "path": str(path),
        "bytes": path.stat().st_size,
        "sha256": sha256_file(path),
    }


def write_json(path: Path, payload: Any) -> None:
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def stable_json_sha(payload: Any) -> str:
    data = json.dumps(
        payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(data).hexdigest()


def matrix_values(obj: bpy.types.Object) -> list[float]:
    return [round(float(value), 9) for row in obj.matrix_world for value in row]


def scene_contract() -> dict[str, Any]:
    names = sorted(obj.name for obj in bpy.data.objects)
    sensor_names = sorted(name for name in names if name.startswith("SENSOR_"))
    body_sensor_names = sorted(
        name for name in sensor_names if name.startswith("SENSOR_T_body_L")
    )
    sensor_matrices = {
        name: matrix_values(bpy.data.objects[name]) for name in sensor_names
    }
    mesh_contract: dict[str, Any] = {}
    for obj in sorted(
        (candidate for candidate in bpy.data.objects if candidate.type == "MESH"),
        key=lambda candidate: candidate.name,
    ):
        mesh = obj.data
        vertex_digest = hashlib.sha256()
        for vertex in mesh.vertices:
            vertex_digest.update(
                struct.pack(
                    "<3d",
                    float(vertex.co.x),
                    float(vertex.co.y),
                    float(vertex.co.z),
                )
            )
        polygon_digest = hashlib.sha256()
        for polygon in mesh.polygons:
            polygon_digest.update(struct.pack("<I", len(polygon.vertices)))
            for index in polygon.vertices:
                polygon_digest.update(struct.pack("<I", int(index)))
        mesh_contract[obj.name] = {
            "vertices": len(mesh.vertices),
            "edges": len(mesh.edges),
            "polygons": len(mesh.polygons),
            "vertex_sha256": vertex_digest.hexdigest(),
            "polygon_sha256": polygon_digest.hexdigest(),
            "matrix": matrix_values(obj),
            "uv_layers": sorted(layer.name for layer in mesh.uv_layers),
            "materials": [slot.material.name if slot.material else None for slot in obj.material_slots],
        }
    internal_names = sorted(
        name
        for name in names
        if name in INTERNAL_PROCESS_OBJECTS
        or any(name.startswith(prefix) for prefix in INTERNAL_PROCESS_PREFIXES)
    )
    payload = {
        "object_count": len(names),
        "object_names_sha256": stable_json_sha(names),
        "mesh_object_count": len(mesh_contract),
        "mesh_geometry_sha256": stable_json_sha(
            {
                name: {
                    key: value
                    for key, value in record.items()
                    if key != "materials"
                }
                for name, record in mesh_contract.items()
            }
        ),
        "sensor_count": len(sensor_names),
        "body_sensor_count": len(body_sensor_names),
        "sensor_names": sensor_names,
        "sensor_matrices_sha256": stable_json_sha(sensor_matrices),
        "process_zones": sorted(name for name in PROCESS_ZONES if name in names),
        "p36_groups": sorted(name for name in P36_GROUPS if name in names),
        "p36_bands": sorted(name for name in P36_BANDS if name in names),
        "sensor_layer_groups": sorted(
            name for name in SENSOR_LAYER_GROUPS if name in names
        ),
        "internal_process_objects": internal_names,
        "meshes": mesh_contract,
    }
    return payload


def image_contract(image: bpy.types.Image) -> dict[str, Any]:
    path = Path(bpy.path.abspath(image.filepath)) if image.filepath else None
    return {
        "name": image.name,
        "width": int(image.size[0]),
        "height": int(image.size[1]),
        "colorspace": image.colorspace_settings.name,
        "packed": bool(image.packed_file),
        "source_path": str(path) if path else None,
        "source_file": file_record(path) if path and path.is_file() else None,
    }


def configure_p50_material_for_gltf() -> dict[str, Any]:
    material = bpy.data.materials.get(P50_MATERIAL_NAME)
    if material is None or material.node_tree is None:
        raise RuntimeError(f"Missing standard P50 material: {P50_MATERIAL_NAME}")
    nodes = material.node_tree.nodes
    links = material.node_tree.links
    base_node = nodes.get("P50_BASE_COLOR_SRGB")
    orm_node = nodes.get("P50_ORM_NON_COLOR_R_AO_G_ROUGHNESS_B_METALLIC")
    separate = nodes.get("P50_ORM_CHANNELS")
    normal_node = nodes.get("P50_OPENGL_NORMAL_NON_COLOR")
    normal_map = nodes.get("P50_OPENGL_PLUS_Y_NORMAL")
    principled = nodes.get("P50_PRINCIPLED")
    required = {
        "base_node": base_node,
        "orm_node": orm_node,
        "separate": separate,
        "normal_node": normal_node,
        "normal_map": normal_map,
        "principled": principled,
    }
    missing = sorted(name for name, node in required.items() if node is None)
    if missing:
        raise RuntimeError(f"P50 material graph missing nodes: {missing}")
    if base_node.image is None or base_node.image.name != P50_BASE_IMAGE:
        raise RuntimeError("P50 BaseColor node is not bound to the 4K master image")
    if orm_node.image is None or orm_node.image.name != P50_ORM_IMAGE:
        raise RuntimeError("P50 ORM node is not bound to the 4K master image")
    if normal_node.image is None or normal_node.image.name != P50_NORMAL_IMAGE:
        raise RuntimeError("P50 Normal node is not bound to the 4K OpenGL image")

    base_node.image.colorspace_settings.name = "sRGB"
    orm_node.image.colorspace_settings.name = "Non-Color"
    normal_node.image.colorspace_settings.name = "Non-Color"
    normal_map.inputs["Strength"].default_value = NORMAL_SCALE
    principled.inputs["Alpha"].default_value = 1.0
    material.diffuse_color = (
        float(material.diffuse_color[0]),
        float(material.diffuse_color[1]),
        float(material.diffuse_color[2]),
        1.0,
    )

    for node in list(nodes):
        if (
            node.type == "GROUP"
            and node.node_tree is not None
            and node.node_tree.name.lower().startswith("gltf material output")
        ):
            nodes.remove(node)
    group_name = "glTF Material Output P60"
    old_group = bpy.data.node_groups.get(group_name)
    if old_group is not None:
        bpy.data.node_groups.remove(old_group, do_unlink=True)
    group = bpy.data.node_groups.new(group_name, "ShaderNodeTree")
    group.interface.new_socket(
        "Occlusion", in_out="INPUT", socket_type="NodeSocketFloat"
    )
    group.nodes.new("NodeGroupOutput")
    group_input = group.nodes.new("NodeGroupInput")
    group_input.location = (-180, 0)
    gltf_output = nodes.new("ShaderNodeGroup")
    gltf_output.name = "P60_GLTF_MATERIAL_OUTPUT"
    gltf_output.label = "P60 glTF Occlusion (ORM R)"
    gltf_output.node_tree = group
    gltf_output.location = (520, -560)
    links.new(separate.outputs["Red"], gltf_output.inputs["Occlusion"])

    previous_assignments: dict[str, list[str | None]] = {}
    for name in PROCESS_ZONES:
        obj = bpy.data.objects.get(name)
        if obj is None or obj.type != "MESH":
            raise RuntimeError(f"Missing shell-zone mesh: {name}")
        previous_assignments[name] = [
            slot.material.name if slot.material else None for slot in obj.material_slots
        ]
        if len(obj.data.materials) != 1 or obj.data.materials[0] != material:
            obj.data.materials.clear()
            obj.data.materials.append(material)
        if P50_UV_NAME not in obj.data.uv_layers:
            raise RuntimeError(f"{name} is missing {P50_UV_NAME}")
        obj.data.uv_layers.active = obj.data.uv_layers[P50_UV_NAME]
        obj.data.uv_layers.active_render = obj.data.uv_layers[P50_UV_NAME]

    material["bf3d_gltf_occlusion_binding"] = "ORM.R via glTF Material Output"
    material["bf3d_delivery_alpha_mode"] = "OPAQUE"
    material["bf3d_cutaway_mode"] = "viewer_clipping_plane_not_shell_transparency"
    material["bf3d_p60_preflight_only"] = True
    bpy.context.scene["bf3d_stage"] = "P60_PREFLIGHT_4K_UNCOMPRESSED"
    bpy.context.scene["bf3d_approval"] = "not_granted_preflight_only"
    bpy.context.scene["bf3d_source_p50_material"] = P50_MATERIAL_NAME
    bpy.context.scene["bf3d_formal_asset_replaced"] = False

    return {
        "material": material.name,
        "previous_shell_assignments": previous_assignments,
        "final_shell_assignments": {
            name: [
                slot.material.name if slot.material else None
                for slot in bpy.data.objects[name].material_slots
            ]
            for name in PROCESS_ZONES
        },
        "gltf_output_node": gltf_output.name,
        "gltf_output_group": group.name,
        "occlusion_source": "P50_ORM_CHANNELS.Red",
        "normal_map_strength": float(normal_map.inputs["Strength"].default_value),
        "principled_alpha": float(principled.inputs["Alpha"].default_value),
        "diffuse_color_alpha": float(material.diffuse_color[3]),
        "delivery_alpha_mode": "OPAQUE",
        "images": {
            "BaseColor": image_contract(base_node.image),
            "ORM": image_contract(orm_node.image),
            "NormalGL": image_contract(normal_node.image),
        },
    }


def sanitize_export_extras() -> list[dict[str, str]]:
    """Keep custom-property keys while removing path/credential payloads."""
    changes: list[dict[str, str]] = []
    datablocks: list[tuple[str, Any]] = [
        ("scene", bpy.context.scene),
        *[(f"object:{obj.name}", obj) for obj in bpy.data.objects],
        *[(f"material:{material.name}", material) for material in bpy.data.materials],
    ]
    sensitive_tokens = ("password", "token", "credential", "secret")
    for owner, datablock in datablocks:
        for key in list(datablock.keys()):
            value = datablock.get(key)
            if any(token in key.lower() for token in sensitive_tokens):
                del datablock[key]
                changes.append(
                    {
                        "owner": owner,
                        "key": key,
                        "action": "removed_sensitive_key",
                    }
                )
                continue
            if not isinstance(value, str):
                continue
            is_windows_absolute = bool(
                re.match(r"(?i)^[a-z]:[\\/]", value)
            ) or value.startswith("\\\\")
            if not is_windows_absolute:
                continue
            basename = PureWindowsPath(value).name
            datablock[key] = basename
            changes.append(
                {
                    "owner": owner,
                    "key": key,
                    "action": "absolute_path_reduced_to_basename",
                    "replacement": basename,
                }
            )
    return changes


def export_glb(path: Path) -> dict[str, Any]:
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
        "export_tangents": True,
        "export_attributes": True,
        "export_materials": "EXPORT",
        "export_image_format": "AUTO",
        "export_unused_images": False,
        "export_unused_textures": False,
        "export_draco_mesh_compression_enable": False,
        "export_meshopt_compression_enable": False,
    }
    kwargs = {key: value for key, value in requested.items() if key in supported}
    started = time.perf_counter()
    result = bpy.ops.export_scene.gltf(**kwargs)
    elapsed = time.perf_counter() - started
    if "FINISHED" not in result or not path.is_file():
        raise RuntimeError(f"glTF export failed: {result}")
    return {
        "operator_result": sorted(result),
        "seconds": elapsed,
        "supported_option_count": len(supported),
        "options": kwargs,
        "unsupported_requested_options": sorted(set(requested) - supported),
    }


def read_glb(path: Path) -> tuple[dict[str, Any], bytes, list[dict[str, Any]]]:
    raw = path.read_bytes()
    if len(raw) < 20:
        raise RuntimeError("GLB is too short")
    magic, version, declared_length = struct.unpack_from("<4sII", raw, 0)
    if magic != b"glTF" or version != 2 or declared_length != len(raw):
        raise RuntimeError(
            f"Invalid GLB header: magic={magic!r} version={version} "
            f"declared={declared_length} actual={len(raw)}"
        )
    offset = 12
    chunks: list[dict[str, Any]] = []
    json_payload: dict[str, Any] | None = None
    binary = b""
    while offset < len(raw):
        chunk_length, chunk_type = struct.unpack_from("<II", raw, offset)
        offset += 8
        data = raw[offset : offset + chunk_length]
        if len(data) != chunk_length:
            raise RuntimeError("Truncated GLB chunk")
        offset += chunk_length
        chunks.append(
            {
                "type_hex": f"0x{chunk_type:08x}",
                "bytes": chunk_length,
                "sha256": hashlib.sha256(data).hexdigest(),
            }
        )
        if chunk_type == 0x4E4F534A:
            json_payload = json.loads(data.decode("utf-8").rstrip(" \t\r\n\0"))
        elif chunk_type == 0x004E4942:
            binary = data
    if json_payload is None:
        raise RuntimeError("GLB has no JSON chunk")
    return json_payload, binary, chunks


def node_descendants(
    index: int, nodes: list[dict[str, Any]]
) -> set[int]:
    result: set[int] = set()
    stack = list(nodes[index].get("children", []))
    while stack:
        child = int(stack.pop())
        if child in result:
            continue
        result.add(child)
        stack.extend(nodes[child].get("children", []))
    return result


def texture_source(
    texture_info: dict[str, Any] | None,
    textures: list[dict[str, Any]],
) -> int | None:
    if not texture_info or "index" not in texture_info:
        return None
    texture_index = int(texture_info["index"])
    if not 0 <= texture_index < len(textures):
        return None
    source = textures[texture_index].get("source")
    return int(source) if source is not None else None


def extract_embedded_images(
    gltf: dict[str, Any], binary: bytes
) -> list[dict[str, Any]]:
    buffer_views = gltf.get("bufferViews", [])
    result: list[dict[str, Any]] = []
    for index, image in enumerate(gltf.get("images", [])):
        record: dict[str, Any] = {
            "index": index,
            "name": image.get("name"),
            "mimeType": image.get("mimeType"),
            "uri": image.get("uri"),
            "bufferView": image.get("bufferView"),
        }
        if "bufferView" in image:
            view = buffer_views[int(image["bufferView"])]
            start = int(view.get("byteOffset", 0))
            length = int(view["byteLength"])
            payload = binary[start : start + length]
            record.update(
                {
                    "bytes": len(payload),
                    "sha256": hashlib.sha256(payload).hexdigest(),
                }
            )
        result.append(record)
    return result


def collect_sensitive_strings(value: Any, path: str = "$") -> list[dict[str, str]]:
    findings: list[dict[str, str]] = []
    if isinstance(value, dict):
        for key, item in value.items():
            child_path = f"{path}.{key}"
            if (
                isinstance(item, (str, int, float, bool))
                and any(token in key.lower() for token in ("password", "token", "credential", "secret"))
                and str(item)
            ):
                findings.append({"path": child_path, "reason": "sensitive_key"})
            findings.extend(collect_sensitive_strings(item, child_path))
    elif isinstance(value, list):
        for index, item in enumerate(value):
            findings.extend(collect_sensitive_strings(item, f"{path}[{index}]"))
    elif isinstance(value, str):
        if re.search(r"(?i)(?:^|[\s\"'])[a-z]:[\\/]", value) or value.startswith("\\\\"):
            findings.append({"path": path, "reason": "absolute_path"})
    return findings


def audit_glb(gltf: dict[str, Any], binary: bytes) -> dict[str, Any]:
    nodes = gltf.get("nodes", [])
    meshes = gltf.get("meshes", [])
    materials = gltf.get("materials", [])
    textures = gltf.get("textures", [])
    images = gltf.get("images", [])
    node_indices = {
        node.get("name", ""): index
        for index, node in enumerate(nodes)
        if node.get("name")
    }
    material_indices = {
        material.get("name", ""): index
        for index, material in enumerate(materials)
        if material.get("name")
    }
    sensor_names = sorted(
        name for name in node_indices if name.startswith("SENSOR_")
    )
    body_names = sorted(
        name for name in sensor_names if name.startswith("SENSOR_T_body_L")
    )
    expected_body_names = {
        f"SENSOR_T_body_{layer}_{sector}"
        for layer in LAYERS
        for sector in SECTORS
    }

    layer_descendants: dict[str, list[str]] = {}
    for layer, group_name in zip(LAYERS, SENSOR_LAYER_GROUPS):
        if group_name not in node_indices:
            layer_descendants[layer] = []
            continue
        descendants = node_descendants(node_indices[group_name], nodes)
        layer_descendants[layer] = sorted(
            nodes[index].get("name", "")
            for index in descendants
            if nodes[index].get("name", "").startswith(f"SENSOR_T_body_{layer}_")
        )

    material_index = material_indices.get(P50_MATERIAL_NAME)
    material = materials[material_index] if material_index is not None else {}
    pbr = material.get("pbrMetallicRoughness", {})
    base_color_factor = pbr.get("baseColorFactor", [1.0, 1.0, 1.0, 1.0])
    roughness_factor = float(pbr.get("roughnessFactor", 1.0))
    metallic_factor = float(pbr.get("metallicFactor", 1.0))
    alpha_mode = material.get("alphaMode")
    base_info = pbr.get("baseColorTexture")
    mr_info = pbr.get("metallicRoughnessTexture")
    normal_info = material.get("normalTexture")
    occlusion_info = material.get("occlusionTexture")
    texture_indices = {
        "BaseColor": base_info.get("index") if base_info else None,
        "ORM_metallicRoughness": mr_info.get("index") if mr_info else None,
        "NormalGL": normal_info.get("index") if normal_info else None,
        "ORM_occlusion": occlusion_info.get("index") if occlusion_info else None,
    }
    image_indices = {
        "BaseColor": texture_source(base_info, textures),
        "ORM_metallicRoughness": texture_source(mr_info, textures),
        "NormalGL": texture_source(normal_info, textures),
        "ORM_occlusion": texture_source(occlusion_info, textures),
    }
    image_names = {
        key: images[index].get("name") if index is not None and 0 <= index < len(images) else None
        for key, index in image_indices.items()
    }

    shell_materials: dict[str, list[int | None]] = {}
    shell_attributes: dict[str, list[list[str]]] = {}
    for name in PROCESS_ZONES:
        node = nodes[node_indices[name]] if name in node_indices else {}
        mesh_index = node.get("mesh")
        primitives = (
            meshes[int(mesh_index)].get("primitives", [])
            if mesh_index is not None
            else []
        )
        shell_materials[name] = [primitive.get("material") for primitive in primitives]
        shell_attributes[name] = [
            sorted(primitive.get("attributes", {}).keys()) for primitive in primitives
        ]

    band_extras = {
        layer: nodes[node_indices[name]].get("extras", {})
        for layer, name in zip(LAYERS, P36_BANDS)
        if name in node_indices
    }
    internal_exported = sorted(
        name
        for name in node_indices
        if name in INTERNAL_PROCESS_OBJECTS
        or any(name.startswith(prefix) for prefix in INTERNAL_PROCESS_PREFIXES)
    )
    external_uris = [
        {"kind": "buffer", "index": index, "uri": item["uri"]}
        for index, item in enumerate(gltf.get("buffers", []))
        if item.get("uri")
    ] + [
        {"kind": "image", "index": index, "uri": item["uri"]}
        for index, item in enumerate(images)
        if item.get("uri")
    ]
    compression_extensions = sorted(
        extension
        for extension in gltf.get("extensionsUsed", [])
        if extension in {"KHR_draco_mesh_compression", "EXT_meshopt_compression"}
    )
    embedded_images = extract_embedded_images(gltf, binary)

    checks = [
        {
            "id": "gltf_2_asset",
            "ok": gltf.get("asset", {}).get("version") == "2.0",
            "detail": gltf.get("asset", {}),
        },
        {
            "id": "p50_material_exported",
            "ok": material_index is not None,
            "detail": material_index,
        },
        {
            "id": "base_color_texture_exported",
            "ok": texture_indices["BaseColor"] is not None
            and image_indices["BaseColor"] is not None,
            "detail": {
                "texture": texture_indices["BaseColor"],
                "image": image_indices["BaseColor"],
                "name": image_names["BaseColor"],
            },
        },
        {
            "id": "opaque_shell_base_color_factor_alpha",
            "ok": len(base_color_factor) == 4
            and abs(float(base_color_factor[3]) - 1.0) <= 1e-8,
            "detail": base_color_factor,
        },
        {
            "id": "opaque_shell_alpha_mode",
            "ok": alpha_mode in {None, "OPAQUE"},
            "detail": alpha_mode if alpha_mode is not None else "omitted_glTF_default_OPAQUE",
        },
        {
            "id": "roughness_and_metallic_factors_remain_one",
            "ok": abs(roughness_factor - 1.0) <= 1e-8
            and abs(metallic_factor - 1.0) <= 1e-8,
            "detail": {
                "roughnessFactor": roughness_factor,
                "metallicFactor": metallic_factor,
            },
        },
        {
            "id": "metallic_roughness_texture_exported",
            "ok": texture_indices["ORM_metallicRoughness"] is not None
            and image_indices["ORM_metallicRoughness"] is not None,
            "detail": {
                "texture": texture_indices["ORM_metallicRoughness"],
                "image": image_indices["ORM_metallicRoughness"],
                "name": image_names["ORM_metallicRoughness"],
            },
        },
        {
            "id": "normal_texture_exported",
            "ok": texture_indices["NormalGL"] is not None
            and image_indices["NormalGL"] is not None,
            "detail": {
                "texture": texture_indices["NormalGL"],
                "image": image_indices["NormalGL"],
                "name": image_names["NormalGL"],
                "scale": normal_info.get("scale") if normal_info else None,
            },
        },
        {
            "id": "normal_scale_preserved",
            "ok": normal_info is not None
            and abs(float(normal_info.get("scale", 1.0)) - NORMAL_SCALE) <= 1e-8,
            "detail": normal_info.get("scale") if normal_info else None,
        },
        {
            "id": "occlusion_texture_exported",
            "ok": texture_indices["ORM_occlusion"] is not None
            and image_indices["ORM_occlusion"] is not None,
            "detail": {
                "texture": texture_indices["ORM_occlusion"],
                "image": image_indices["ORM_occlusion"],
                "name": image_names["ORM_occlusion"],
            },
        },
        {
            "id": "occlusion_reuses_metallic_roughness_orm_texture",
            "ok": texture_indices["ORM_occlusion"]
            == texture_indices["ORM_metallicRoughness"]
            and image_indices["ORM_occlusion"]
            == image_indices["ORM_metallicRoughness"]
            and texture_indices["ORM_occlusion"] is not None,
            "detail": {
                "textures": texture_indices,
                "images": image_indices,
                "image_names": image_names,
            },
        },
        {
            "id": "five_shell_zones_share_p50_material",
            "ok": material_index is not None
            and all(
                values and all(value == material_index for value in values)
                for values in shell_materials.values()
            ),
            "detail": shell_materials,
        },
        {
            "id": "five_shell_zones_have_position_normal_uv",
            "ok": all(
                values
                and all(
                    {"POSITION", "NORMAL", "TEXCOORD_0"}.issubset(set(attributes))
                    for attributes in values
                )
                for values in shell_attributes.values()
            ),
            "detail": shell_attributes,
        },
        {
            "id": "all_115_sensor_nodes",
            "ok": len(sensor_names) == 115,
            "detail": len(sensor_names),
        },
        {
            "id": "all_80_body_temperature_nodes",
            "ok": len(body_names) == 80 and set(body_names) == expected_body_names,
            "detail": len(body_names),
        },
        {
            "id": "each_layer_has_exact_a_to_h",
            "ok": all(
                descendants
                == sorted(
                    f"SENSOR_T_body_{layer}_{sector}" for sector in SECTORS
                )
                for layer, descendants in layer_descendants.items()
            ),
            "detail": layer_descendants,
        },
        {
            "id": "ten_p36_layer_groups",
            "ok": all(name in node_indices for name in P36_GROUPS),
            "detail": sorted(name for name in P36_GROUPS if name in node_indices),
        },
        {
            "id": "ten_p36_band_mesh_nodes",
            "ok": all(
                name in node_indices and "mesh" in nodes[node_indices[name]]
                for name in P36_BANDS
            ),
            "detail": sorted(name for name in P36_BANDS if name in node_indices),
        },
        {
            "id": "p36_band_extras_preserved",
            "ok": all(
                band_extras.get(layer, {}).get("bf3d_role")
                == "temperature_layer_overlay_mesh"
                and band_extras.get(layer, {}).get("layer_id") == layer
                and band_extras.get(layer, {}).get("default_visible") is False
                for layer in LAYERS
            ),
            "detail": band_extras,
        },
        {
            "id": "five_process_zone_nodes",
            "ok": all(name in node_indices for name in PROCESS_ZONES),
            "detail": sorted(name for name in PROCESS_ZONES if name in node_indices),
        },
        {
            "id": "internal_process_objects_preserved",
            "ok": all(name in node_indices for name in INTERNAL_PROCESS_OBJECTS)
            and len(
                [
                    name
                    for name in node_indices
                    if name.startswith(INTERNAL_PROCESS_PREFIXES[0])
                ]
            )
            == 36,
            "detail": internal_exported,
        },
        {
            "id": "no_external_uris",
            "ok": not external_uris,
            "detail": external_uris,
        },
        {
            "id": "no_draco_or_meshopt_baseline_compression",
            "ok": not compression_extensions,
            "detail": compression_extensions,
        },
        {
            "id": "no_absolute_paths_or_secret_fields_in_gltf_json",
            "ok": not collect_sensitive_strings(gltf),
            "detail": collect_sensitive_strings(gltf),
        },
    ]
    return {
        "asset": gltf.get("asset", {}),
        "scene_count": len(gltf.get("scenes", [])),
        "node_count": len(nodes),
        "mesh_count": len(meshes),
        "material_count": len(materials),
        "texture_count": len(textures),
        "image_count": len(images),
        "buffer_view_count": len(gltf.get("bufferViews", [])),
        "accessor_count": len(gltf.get("accessors", [])),
        "extensions_used": gltf.get("extensionsUsed", []),
        "p50_material_index": material_index,
        "p50_material": material,
        "p50_base_color_factor": base_color_factor,
        "p50_alpha_mode": alpha_mode,
        "p50_roughness_factor": roughness_factor,
        "p50_metallic_factor": metallic_factor,
        "texture_indices": texture_indices,
        "image_indices": image_indices,
        "image_names": image_names,
        "embedded_images": embedded_images,
        "shell_material_indices": shell_materials,
        "shell_primitive_attributes": shell_attributes,
        "sensor_count": len(sensor_names),
        "body_sensor_count": len(body_names),
        "internal_process_objects": internal_exported,
        "checks": checks,
        "ok": all(bool(check["ok"]) for check in checks),
    }


def reload_smoke(glb_path: Path) -> dict[str, Any]:
    bpy.ops.wm.read_factory_settings(use_empty=True)
    supported = set(bpy.ops.import_scene.gltf.get_rna_type().properties.keys())
    requested: dict[str, Any] = {
        "filepath": str(glb_path),
        "import_pack_images": False,
        "import_merge_vertices": False,
        "import_shading": "NORMALS",
    }
    kwargs = {key: value for key, value in requested.items() if key in supported}
    started = time.perf_counter()
    result = bpy.ops.import_scene.gltf(**kwargs)
    elapsed = time.perf_counter() - started
    names = {obj.name for obj in bpy.data.objects}
    sensors = sorted(name for name in names if name.startswith("SENSOR_"))
    body = sorted(
        name for name in sensors if name.startswith("SENSOR_T_body_L")
    )
    checks = [
        {"id": "reload_operator_finished", "ok": "FINISHED" in result},
        {"id": "reload_115_sensors", "ok": len(sensors) == 115, "detail": len(sensors)},
        {"id": "reload_80_body_sensors", "ok": len(body) == 80, "detail": len(body)},
        {
            "id": "reload_five_process_zones",
            "ok": all(name in names for name in PROCESS_ZONES),
        },
        {
            "id": "reload_ten_p36_groups",
            "ok": all(name in names for name in P36_GROUPS),
        },
        {
            "id": "reload_ten_p36_bands",
            "ok": all(name in names for name in P36_BANDS),
        },
        {
            "id": "reload_internal_process_objects",
            "ok": all(name in names for name in INTERNAL_PROCESS_OBJECTS)
            and len(
                [
                    name
                    for name in names
                    if name.startswith(INTERNAL_PROCESS_PREFIXES[0])
                ]
            )
            == 36,
        },
        {
            "id": "reload_p50_material",
            "ok": P50_MATERIAL_NAME in bpy.data.materials,
        },
    ]
    return {
        "operator_result": sorted(result),
        "seconds": elapsed,
        "options": kwargs,
        "object_count": len(names),
        "material_count": len(bpy.data.materials),
        "image_count": len(bpy.data.images),
        "checks": checks,
        "ok": all(bool(check["ok"]) for check in checks),
    }


def find_local_validator(repo_root: Path) -> dict[str, Any]:
    checked_commands = [
        "gltf_validator",
        "gltf-validator",
        "gltf_validator_cli",
    ]
    commands = [
        {"name": name, "path": shutil.which(name)}
        for name in checked_commands
    ]
    node = shutil.which("node")
    candidate_modules = [
        repo_root / "node_modules" / "gltf-validator",
        repo_root / "node_modules" / "@khronosgroup" / "gltf-validator",
    ]
    appdata = os.environ.get("APPDATA")
    if appdata:
        candidate_modules.append(
            Path(appdata) / "npm" / "node_modules" / "gltf-validator"
        )
    module_paths = [
        {"path": str(path), "exists": path.is_dir()} for path in candidate_modules
    ]
    python_spec = importlib.util.find_spec("gltf_validator")
    return {
        "checked_commands": commands,
        "node": node,
        "checked_node_modules": module_paths,
        "python_module": python_spec.origin if python_spec else None,
        "available_executable": next(
            (item["path"] for item in commands if item["path"]), None
        ),
        "available_node_module": next(
            (item["path"] for item in module_paths if item["exists"]), None
        ),
    }


def run_local_validator(glb_path: Path, output_dir: Path) -> dict[str, Any]:
    probe = find_local_validator(REPO_ROOT)
    executable = probe["available_executable"]
    node_module = probe["available_node_module"]
    node = probe["node"]
    if executable:
        report_path = output_dir / "gltf_validator_report.json"
        attempts = [
            [executable, "-o", str(report_path), str(glb_path)],
            [executable, str(glb_path), "-o", str(report_path)],
        ]
        attempt_records: list[dict[str, Any]] = []
        for command in attempts:
            completed = subprocess.run(
                command,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=300,
                check=False,
            )
            attempt_records.append(
                {
                    "command": command,
                    "returncode": completed.returncode,
                    "stdout": completed.stdout[-4000:],
                    "stderr": completed.stderr[-4000:],
                }
            )
            if completed.returncode == 0 and report_path.is_file():
                payload = json.loads(report_path.read_text(encoding="utf-8"))
                issues = payload.get("issues", {})
                return {
                    "status": "passed"
                    if int(issues.get("numErrors", 0)) == 0
                    else "failed",
                    "probe": probe,
                    "attempts": attempt_records,
                    "report": file_record(report_path),
                    "issues": issues,
                }
        return {
            "status": "failed_to_run",
            "probe": probe,
            "attempts": attempt_records,
        }
    if node and node_module:
        script = (
            "const fs=require('fs');"
            "const v=require(process.argv[1]);"
            "const p=process.argv[2];"
            "v.validateBytes(new Uint8Array(fs.readFileSync(p)),{uri:p})"
            ".then(r=>process.stdout.write(JSON.stringify(r)));"
        )
        completed = subprocess.run(
            [node, "-e", script, node_module, str(glb_path)],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=300,
            check=False,
        )
        if completed.returncode == 0 and completed.stdout.strip():
            payload = json.loads(completed.stdout)
            report_path = output_dir / "gltf_validator_report.json"
            write_json(report_path, payload)
            issues = payload.get("issues", {})
            return {
                "status": "passed"
                if int(issues.get("numErrors", 0)) == 0
                else "failed",
                "probe": probe,
                "returncode": completed.returncode,
                "stderr": completed.stderr[-4000:],
                "report": file_record(report_path),
                "issues": issues,
            }
        return {
            "status": "failed_to_run",
            "probe": probe,
            "returncode": completed.returncode,
            "stdout": completed.stdout[-4000:],
            "stderr": completed.stderr[-4000:],
        }
    return {
        "status": "unavailable",
        "probe": probe,
        "reason": (
            "No local Khronos glTF Validator executable, Python module, or "
            "installed Node module was found. No network install was attempted."
        ),
    }


def assertion(identifier: str, ok: bool, detail: Any = None) -> dict[str, Any]:
    record: dict[str, Any] = {"id": identifier, "ok": bool(ok)}
    if detail is not None:
        record["detail"] = detail
    return record


def main() -> int:
    args = parse_args()
    input_blend = args.input_blend.resolve()
    output_dir = args.output_dir.resolve()
    formal_glb = args.formal_glb.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    if not input_blend.is_file():
        raise FileNotFoundError(input_blend)
    if not formal_glb.is_file():
        raise FileNotFoundError(formal_glb)

    script_record = file_record(SCRIPT_PATH)
    input_record = file_record(input_blend)
    formal_before = file_record(formal_glb)
    if not bpy.data.filepath or Path(bpy.data.filepath).resolve() != input_blend:
        bpy.ops.wm.open_mainfile(filepath=str(input_blend))

    source_contract = scene_contract()
    material_setup = configure_p50_material_for_gltf()
    sanitized_extras = sanitize_export_extras()
    post_setup_contract = scene_contract()
    export_copy = output_dir / EXPORT_COPY_NAME
    bpy.context.preferences.filepaths.save_version = 0
    bpy.ops.wm.save_as_mainfile(filepath=str(export_copy), check_existing=False)
    export_copy_record = file_record(export_copy)

    glb_path = output_dir / GLB_NAME
    export_result = export_glb(glb_path)
    glb_record = file_record(glb_path)
    gltf, binary, chunks = read_glb(glb_path)
    glb_audit = audit_glb(gltf, binary)
    reload_result = reload_smoke(glb_path)
    validator = run_local_validator(glb_path, output_dir)
    validator_status_path = output_dir / VALIDATOR_STATUS_NAME
    write_json(validator_status_path, validator)
    validator_status_record = file_record(validator_status_path)
    formal_after = file_record(formal_glb)

    geometry_unchanged = (
        source_contract["mesh_geometry_sha256"]
        == post_setup_contract["mesh_geometry_sha256"]
    )
    sensor_matrices_unchanged = (
        source_contract["sensor_matrices_sha256"]
        == post_setup_contract["sensor_matrices_sha256"]
    )
    object_names_unchanged = (
        source_contract["object_names_sha256"]
        == post_setup_contract["object_names_sha256"]
    )
    source_internal_expected = sorted(
        list(INTERNAL_PROCESS_OBJECTS)
        + [
            f"{INTERNAL_PROCESS_PREFIXES[0]}{index:02d}"
            for index in range(36)
        ]
    )
    source_internal_complete = (
        source_contract["internal_process_objects"] == source_internal_expected
    )
    material_images = material_setup["images"]
    assertions = [
        assertion(
            "input_is_requested_p50_master_4k",
            input_blend == DEFAULT_INPUT.resolve(),
            input_record,
        ),
        assertion(
            "source_scene_115_sensors",
            source_contract["sensor_count"] == 115,
            source_contract["sensor_count"],
        ),
        assertion(
            "source_scene_80_body_sensors",
            source_contract["body_sensor_count"] == 80,
            source_contract["body_sensor_count"],
        ),
        assertion(
            "source_scene_ten_layers_and_bands",
            len(source_contract["p36_groups"]) == 10
            and len(source_contract["p36_bands"]) == 10
            and len(source_contract["sensor_layer_groups"]) == 10,
        ),
        assertion(
            "source_internal_process_objects_complete",
            source_internal_complete,
            source_contract["internal_process_objects"],
        ),
        assertion(
            "p50_images_are_4k",
            all(
                record["width"] == 4096 and record["height"] == 4096
                for record in material_images.values()
            ),
            material_images,
        ),
        assertion(
            "p50_texture_colorspaces_preserved",
            material_images["BaseColor"]["colorspace"] == "sRGB"
            and material_images["ORM"]["colorspace"] == "Non-Color"
            and material_images["NormalGL"]["colorspace"] == "Non-Color",
            {
                name: record["colorspace"]
                for name, record in material_images.items()
            },
        ),
        assertion(
            "p50_normal_scale_preserved_in_blender",
            abs(material_setup["normal_map_strength"] - NORMAL_SCALE) <= 1e-8,
            material_setup["normal_map_strength"],
        ),
        assertion(
            "p50_export_copy_shell_is_opaque",
            abs(material_setup["principled_alpha"] - 1.0) <= 1e-8
            and abs(material_setup["diffuse_color_alpha"] - 1.0) <= 1e-8
            and material_setup["delivery_alpha_mode"] == "OPAQUE",
            {
                "principled_alpha": material_setup["principled_alpha"],
                "diffuse_color_alpha": material_setup["diffuse_color_alpha"],
                "delivery_alpha_mode": material_setup["delivery_alpha_mode"],
            },
        ),
        assertion(
            "five_shell_zones_share_standard_p50_material_in_export_copy",
            all(
                values == [P50_MATERIAL_NAME]
                for values in material_setup["final_shell_assignments"].values()
            ),
            material_setup["final_shell_assignments"],
        ),
        assertion("scene_geometry_unchanged", geometry_unchanged),
        assertion("sensor_world_matrices_unchanged", sensor_matrices_unchanged),
        assertion("scene_object_names_unchanged", object_names_unchanged),
        assertion("isolated_export_copy_saved", export_copy.is_file(), export_copy_record),
        assertion("uncompressed_glb_exported", glb_path.is_file(), glb_record),
        assertion("internal_glb_contract_parser_passed", glb_audit["ok"]),
        assertion("blender_glb_reload_smoke_passed", reload_result["ok"]),
        assertion(
            "local_validator_probed_without_network_install",
            validator["status"]
            in {"passed", "failed", "failed_to_run", "unavailable"},
            validator["status"],
        ),
        assertion(
            "formal_glb_hash_unchanged",
            formal_before["sha256"] == formal_after["sha256"]
            == EXPECTED_FORMAL_GLB_SHA256,
            {
                "before": formal_before["sha256"],
                "after": formal_after["sha256"],
                "expected": EXPECTED_FORMAL_GLB_SHA256,
            },
        ),
        assertion(
            "formal_glb_not_same_path_as_preflight",
            formal_glb != glb_path,
            {"formal": str(formal_glb), "preflight": str(glb_path)},
        ),
    ]
    internal_preflight_ok = all(bool(item["ok"]) for item in assertions)
    validator_passed = validator["status"] == "passed"
    p60_gate_ok = False
    warnings = [
        (
            "This is an isolated uncompressed P60 preflight. It does not replace "
            "the production GLB and cannot approve P50 or P60."
        ),
        (
            "P50 prerequisite approval and the required Three.js/browser "
            "handoff matrix are outside this preflight."
        ),
        (
            "No Draco, Meshopt, or KTX2 compression is enabled in this baseline."
        ),
        (
            "The five delivery shell zones are opaque (alpha 1); any future "
            "cutaway must use viewer clipping and must not weaken the baked "
            "roughness/metallic/normal response with shell transparency."
        ),
        (
            "Blender can log a shared image-node sampler warning because the "
            "same ORM image intentionally feeds Occlusion and metallic-roughness; "
            "the GLB parser verifies one shared texture and image index."
        ),
    ]
    if validator["status"] == "unavailable":
        warnings.append(
            "Local Khronos glTF Validator is unavailable; no network package "
            "installation was attempted."
        )
    elif validator["status"] != "passed":
        warnings.append(
            f"Local glTF Validator did not pass: {validator['status']}."
        )

    report_path = output_dir / REPORT_NAME
    manifest_path = output_dir / MANIFEST_NAME
    report = {
        "schema_version": 1,
        "stage": "P60_PREFLIGHT_4K_UNCOMPRESSED",
        "status": (
            "internal_preflight_passed"
            if internal_preflight_ok
            else "internal_preflight_failed"
        ),
        "approval": "not_granted_preflight_only",
        "p50_approved": False,
        "p60_approved": False,
        "p60_gate_ok": p60_gate_ok,
        "validator_passed": validator_passed,
        "input": input_record,
        "script": script_record,
        "formal_glb": {
            "before": formal_before,
            "after": formal_after,
            "modified": formal_before["sha256"] != formal_after["sha256"],
        },
        "isolated_export_copy": export_copy_record,
        "uncompressed_glb": glb_record,
        "material_setup": material_setup,
        "sanitized_export_extras": sanitized_extras,
        "source_contract": {
            key: value
            for key, value in source_contract.items()
            if key != "meshes"
        },
        "post_setup_contract": {
            key: value
            for key, value in post_setup_contract.items()
            if key != "meshes"
        },
        "export": export_result,
        "glb_chunks": chunks,
        "glb_audit": glb_audit,
        "reload_smoke": reload_result,
        "validator": validator,
        "assertions": assertions,
        "assertion_summary": {
            "passed": sum(bool(item["ok"]) for item in assertions),
            "total": len(assertions),
        },
        "warnings": warnings,
        "next_gates": [
            "Independent P50 approval",
            "Khronos glTF Validator with zero errors and explained warnings",
            "Three.js material/node/layer validation",
            "Required Chromium, Firefox, WebKit, and Edge viewport matrix",
            "Performance and 100-layer-switch resource stability",
        ],
        "manifest_path": str(manifest_path),
    }
    write_json(report_path, report)
    report_record = file_record(report_path)

    texture_sources = {
        name: record["source_file"]
        for name, record in material_images.items()
        if record["source_file"] is not None
    }
    manifest = {
        "schema_version": 1,
        "stage": "P60_PREFLIGHT_4K_UNCOMPRESSED",
        "approval": "not_granted_preflight_only",
        "generated_files": {
            "export_copy": export_copy_record,
            "uncompressed_glb": glb_record,
            "report": report_record,
            "validator_status": validator_status_record,
        },
        "inputs": {
            "p50_master_4k_blend": input_record,
            "script": script_record,
            "texture_sources": texture_sources,
        },
        "formal_glb": {
            "record": formal_after,
            "expected_sha256": EXPECTED_FORMAL_GLB_SHA256,
            "unchanged": formal_before["sha256"] == formal_after["sha256"],
        },
        "glb_summary": {
            "asset": glb_audit["asset"],
            "nodes": glb_audit["node_count"],
            "meshes": glb_audit["mesh_count"],
            "materials": glb_audit["material_count"],
            "textures": glb_audit["texture_count"],
            "images": glb_audit["image_count"],
            "embedded_images": glb_audit["embedded_images"],
            "sensors": glb_audit["sensor_count"],
            "body_temperature_sensors": glb_audit["body_sensor_count"],
            "p36_groups": len(P36_GROUPS),
            "p36_bands": len(P36_BANDS),
            "process_zones": list(PROCESS_ZONES),
            "internal_process_objects": glb_audit["internal_process_objects"],
        },
        "validator_status": validator["status"],
        "internal_preflight_ok": internal_preflight_ok,
        "p60_gate_ok": False,
        "warnings": warnings,
    }
    write_json(manifest_path, manifest)
    manifest_record = file_record(manifest_path)
    checksum_path = output_dir / CHECKSUM_NAME
    write_json(
        checksum_path,
        {
            "schema_version": 1,
            "algorithm": "SHA-256",
            "files": {
                "input_blend": input_record,
                "script": script_record,
                "export_copy": export_copy_record,
                "uncompressed_glb": glb_record,
                "report": report_record,
                "manifest": manifest_record,
                "validator_status": validator_status_record,
                "formal_glb": formal_after,
                "texture_sources": texture_sources,
            },
        },
    )

    print(
        "P60_PREFLIGHT_RESULT="
        + json.dumps(
            {
                "status": report["status"],
                "approval": report["approval"],
                "assertions": report["assertion_summary"],
                "validator": validator["status"],
                "glb": glb_record,
                "report": file_record(report_path),
                "manifest": file_record(manifest_path),
                "checksums": file_record(checksum_path),
                "formal_glb_unchanged": manifest["formal_glb"]["unchanged"],
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    return 0 if internal_preflight_ok else 2


if __name__ == "__main__":
    raise SystemExit(main())
