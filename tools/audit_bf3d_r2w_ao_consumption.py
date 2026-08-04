"""Fail-closed, read-only audit of R2W ambient-occlusion consumption.

Requirement:
    REQ-BF3D-R2W-MATERIAL-READABILITY-AO-EDGE-20260720

The audit intentionally does not generate textures, edit a Blend file, rewrite
a GLB, change lighting, or touch a review page.  It proves five separate facts:

1. the controlled V5 main/material/structural GLBs and direct-open Blend still
   match their locked SHA-256 digests;
2. the current R2G 4K ORM image is decoded as RGBA and measured per channel;
3. each R2J exterior primitive's glTF texture bindings and TEXCOORD_0/1/2
   availability are enumerated directly from the GLB JSON chunk;
4. a Blender background probe records the actual R2J exterior UV-layer names
   and whether the current ORM image's red branch has any node-graph consumer;
5. the historical P50 AO R3 atlas is rejected for direct reuse because its
   ``P50_UV0`` atlas and APPROX_GL02 target identity do not match V5 R2J.

Normal execution launches Blender in background mode for the read-only probe,
then writes one consolidated JSON report.  Blender invokes this same file with
``--blend-probe``; that mode writes only the temporary probe report.

Examples (PowerShell, from repository root):

    python tools/audit_bf3d_r2w_ao_consumption.py
    python tools/audit_bf3d_r2w_ao_consumption.py --output <report.json>
    python tools/audit_bf3d_r2w_ao_consumption.py --blender-exe <blender.exe>

Exit codes:
    0: evidence was complete and the expected "AO not consumed" state was
       proven.
    1: an input lock, parse/probe step, or mandatory assertion failed.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import struct
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable


SCHEMA_VERSION = "bf3d.r2w.ao_consumption_audit.v1"
BLEND_PROBE_SCHEMA_VERSION = "bf3d.r2w.ao_consumption_blend_probe.v1"
REQUIREMENT_ID = "REQ-BF3D-R2W-MATERIAL-READABILITY-AO-EDGE-20260720"
STAGE_ID = "WEB_60_20260720_R2W_MATERIAL_READABILITY_AO_EDGE"

REPO_ROOT = Path(__file__).resolve().parent.parent
MODULE_ROOT = REPO_ROOT / "PT" / "高炉3D模型"
STAGE_ROOT = MODULE_ROOT / "work" / STAGE_ID
REPORT_DIR = STAGE_ROOT / "reports"
DEFAULT_OUTPUT = REPORT_DIR / "ao_consumption_audit.json"
DEFAULT_BLEND_PROBE_OUTPUT = REPORT_DIR / "ao_consumption_blend_probe.json"
DEFAULT_BLENDER = Path(
    r"D:\Program Files\Blender Foundation\Blender 5.2\blender.exe"
)

MODEL_ROOT = REPO_ROOT / "高炉前端数据" / "models"
V5_MAIN = MODEL_ROOT / "gl02_blast_furnace_review.v5.glb"
V5_MATERIAL = MODEL_ROOT / "gl02_blast_furnace_material_review.v5.glb"
V5_STRUCTURAL = MODEL_ROOT / "gl02_blast_furnace_structural_review.v5.glb"
V5_BLEND = MODEL_ROOT / "gl02_blast_furnace_review.v5.blend"
CURRENT_ORM = (
    MODULE_ROOT
    / "work"
    / "INT_30_20260718_R2G_ISOLATED_GLB_WEB_PREVIEW"
    / "textures"
    / "final_4k"
    / "INT30_R2G_R1_LOCK_ORM_4K.png"
)
P50_R3_MANIFEST = (
    MODULE_ROOT
    / "work"
    / "P50_LOCAL_CONTACT_AO_1K_20260717_1702_R3"
    / "p50_texture_manifest.json"
)

LOCKS: dict[str, tuple[Path, str]] = {
    "v5_main_glb": (
        V5_MAIN,
        "0ac031e626c9eaa0b0cdd8192cf9fda712324af174a4285f563a97309451ed3c",
    ),
    "v5_material_glb": (
        V5_MATERIAL,
        "652be1b2c9147d5a7392497c7ae4964d19bdd7095b5435b87c105f9eb3fb66bc",
    ),
    "v5_structural_glb": (
        V5_STRUCTURAL,
        "e5c77d3834c631e2513209a690f6328d1c63dba2c8d489b2d2dbe17645465f71",
    ),
    "v5_direct_open_blend": (
        V5_BLEND,
        "3e6df5fb02d3734d14923d4432739a5918ac8249d6a3c8ad1415395429b27e3a",
    ),
    "current_r2g_orm_4k": (
        CURRENT_ORM,
        "e3354cc5d793807ebb4f6b0d74593a7b6f09f18fcece8f9102e867f2c8570e17",
    ),
    "legacy_p50_ao_r3_manifest": (
        P50_R3_MANIFEST,
        "9d476f41759c5779930764064d0e7f150b0c6fa216e3de1bf9118f4d0245d061",
    ),
}

GLB_MAGIC = b"glTF"
GLB_JSON_CHUNK = b"JSON"
GLB_BIN_CHUNK = b"BIN\x00"
R2J_EXTERIOR_PREFIX = "R2J_ASM_GL02_FURNACE_"
R2J_EXTERIOR_OBJECTS = {
    "R2J_ASM_GL02_FURNACE_BELLY_SHELL_55MM_E",
    "R2J_ASM_GL02_FURNACE_BOSH_SHELL_55MM_E",
    "R2J_ASM_GL02_FURNACE_HEARTH_SHELL_65MM_E",
    "R2J_ASM_GL02_FURNACE_SHAFT_SHELL_45MM_E",
    "R2J_ASM_GL02_FURNACE_THROAT_SHELL_45MM_E",
}
CURRENT_ORM_TOKEN = "INT30_R2G_R1_LOCK_ORM_4K"


class AuditError(RuntimeError):
    """Raised when mandatory evidence cannot be established unambiguously."""


def now_iso() -> str:
    """Return an RFC 3339 UTC timestamp."""

    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def relative_path(path: Path) -> str:
    """Return a repository-relative POSIX path, failing outside the workspace."""

    try:
        return path.resolve().relative_to(REPO_ROOT.resolve()).as_posix()
    except ValueError as exc:
        raise AuditError(f"Evidence path is outside the repository: {path}") from exc


def sha256_file(path: Path) -> str:
    """Return a lowercase SHA-256 digest for ``path``."""

    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def artifact_record(path: Path, expected_sha256: str | None = None) -> dict[str, Any]:
    """Return a traceable artifact record and optional SHA lock result."""

    exists = path.is_file()
    actual_sha256 = sha256_file(path) if exists else None
    record: dict[str, Any] = {
        "path": relative_path(path),
        "exists": exists,
        "bytes": path.stat().st_size if exists else None,
        "sha256": actual_sha256,
    }
    if expected_sha256 is not None:
        record["expected_sha256"] = expected_sha256
        record["lock_passed"] = exists and actual_sha256 == expected_sha256
    return record


def validate_locks() -> dict[str, Any]:
    """Measure every controlled input and record its fail-closed lock result."""

    artifacts = {
        name: artifact_record(path, expected)
        for name, (path, expected) in LOCKS.items()
    }
    return {
        "artifacts": artifacts,
        "all_locks_passed": all(
            record["lock_passed"] for record in artifacts.values()
        ),
    }


def read_glb(path: Path) -> tuple[dict[str, Any], bytes]:
    """Read and validate the JSON and BIN chunks of a GLB 2.0 file."""

    with path.open("rb") as stream:
        header = stream.read(12)
        if len(header) != 12:
            raise AuditError(f"Truncated GLB header: {path}")
        magic, version, declared_length = struct.unpack("<4sII", header)
        if magic != GLB_MAGIC or version != 2:
            raise AuditError(f"Not a GLB 2.0 file: {path}")
        if declared_length != path.stat().st_size:
            raise AuditError(
                f"GLB length mismatch: {path}: "
                f"declared={declared_length}, actual={path.stat().st_size}"
            )
        chunks: list[tuple[bytes, bytes]] = []
        while stream.tell() < declared_length:
            chunk_header = stream.read(8)
            if len(chunk_header) != 8:
                raise AuditError(f"Truncated GLB chunk header: {path}")
            chunk_length, chunk_type = struct.unpack("<I4s", chunk_header)
            payload = stream.read(chunk_length)
            if len(payload) != chunk_length:
                raise AuditError(f"Truncated GLB chunk payload: {path}")
            chunks.append((chunk_type, payload))
    json_payload = next(
        (payload for chunk_type, payload in chunks if chunk_type == GLB_JSON_CHUNK),
        None,
    )
    if json_payload is None:
        raise AuditError(f"GLB has no JSON chunk: {path}")
    try:
        gltf = json.loads(json_payload.decode("utf-8").rstrip(" \t\r\n\x00"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise AuditError(f"Invalid GLB JSON: {path}: {exc}") from exc
    binary = next(
        (payload for chunk_type, payload in chunks if chunk_type == GLB_BIN_CHUNK),
        b"",
    )
    return gltf, binary


def buffer_view_payload(
    gltf: dict[str, Any],
    binary: bytes,
    view_index: int,
) -> bytes:
    """Return an embedded GLB buffer-view payload."""

    views = gltf.get("bufferViews") or []
    if view_index < 0 or view_index >= len(views):
        raise AuditError(f"bufferView index out of range: {view_index}")
    view = views[view_index]
    if int(view.get("buffer", 0)) != 0:
        raise AuditError("External or multi-buffer GLB is outside this audit contract")
    offset = int(view.get("byteOffset", 0))
    length = int(view.get("byteLength", 0))
    end = offset + length
    if offset < 0 or length < 0 or end > len(binary):
        raise AuditError(
            f"Invalid bufferView range: index={view_index}, "
            f"offset={offset}, length={length}, bin={len(binary)}"
        )
    return binary[offset:end]


def gltf_texture_descriptor(
    gltf: dict[str, Any],
    binary: bytes,
    texture_info: dict[str, Any] | None,
) -> dict[str, Any] | None:
    """Resolve a glTF textureInfo to texture/image identity and effective UV set."""

    if texture_info is None:
        return None
    texture_index = int(texture_info["index"])
    textures = gltf.get("textures") or []
    if texture_index < 0 or texture_index >= len(textures):
        raise AuditError(f"Texture index out of range: {texture_index}")
    texture = textures[texture_index]
    transform = (texture_info.get("extensions") or {}).get(
        "KHR_texture_transform"
    ) or {}
    effective_texcoord = int(transform.get("texCoord", texture_info.get("texCoord", 0)))
    source_index = texture.get("source")
    basisu = (texture.get("extensions") or {}).get("KHR_texture_basisu") or {}
    if source_index is None:
        source_index = basisu.get("source")
    webp = (texture.get("extensions") or {}).get("EXT_texture_webp") or {}
    if source_index is None:
        source_index = webp.get("source")
    if source_index is None:
        raise AuditError(f"Texture {texture_index} has no image source")
    source_index = int(source_index)
    images = gltf.get("images") or []
    if source_index < 0 or source_index >= len(images):
        raise AuditError(f"Image index out of range: {source_index}")
    image = images[source_index]
    payload_sha256 = None
    if "bufferView" in image:
        payload_sha256 = hashlib.sha256(
            buffer_view_payload(gltf, binary, int(image["bufferView"]))
        ).hexdigest()
    return {
        "texture_index": texture_index,
        "texture_name": texture.get("name"),
        "image_index": source_index,
        "image_name": image.get("name"),
        "image_mime_type": image.get("mimeType"),
        "image_uri": image.get("uri"),
        "embedded_payload_sha256": payload_sha256,
        "declared_texCoord": int(texture_info.get("texCoord", 0)),
        "effective_texCoord": effective_texcoord,
        "required_attribute": f"TEXCOORD_{effective_texcoord}",
        "strength": texture_info.get("strength"),
        "scale": texture_info.get("scale"),
        "texture_transform": transform or None,
    }


def r2j_exterior_mesh(mesh_name: str) -> bool:
    """Return whether ``mesh_name`` is one of the five complete R2J exteriors."""

    return mesh_name.startswith(R2J_EXTERIOR_PREFIX) and not mesh_name.startswith(
        "SECTION_"
    )


def audit_glb_material_consumption(path: Path) -> dict[str, Any]:
    """Audit R2J exterior material bindings and UV attributes in one GLB."""

    gltf, binary = read_glb(path)
    materials = gltf.get("materials") or []
    records: list[dict[str, Any]] = []
    material_indices: set[int] = set()
    occlusion_bound_count = 0
    bound_texcoord_missing_count = 0
    texcoord_presence_counts = {f"TEXCOORD_{index}": 0 for index in range(3)}

    for mesh_index, mesh in enumerate(gltf.get("meshes") or []):
        mesh_name = str(mesh.get("name") or f"mesh_{mesh_index}")
        if not r2j_exterior_mesh(mesh_name):
            continue
        for primitive_index, primitive in enumerate(mesh.get("primitives") or []):
            material_index = primitive.get("material")
            if material_index is None:
                raise AuditError(
                    f"R2J exterior primitive has no material: "
                    f"{path.name}:{mesh_name}:{primitive_index}"
                )
            material_index = int(material_index)
            if material_index < 0 or material_index >= len(materials):
                raise AuditError(
                    f"R2J exterior material index out of range: {material_index}"
                )
            material_indices.add(material_index)
            material = materials[material_index]
            pbr = material.get("pbrMetallicRoughness") or {}
            base_color = gltf_texture_descriptor(
                gltf, binary, pbr.get("baseColorTexture")
            )
            metallic_roughness = gltf_texture_descriptor(
                gltf, binary, pbr.get("metallicRoughnessTexture")
            )
            normal = gltf_texture_descriptor(
                gltf, binary, material.get("normalTexture")
            )
            occlusion = gltf_texture_descriptor(
                gltf, binary, material.get("occlusionTexture")
            )
            if occlusion is not None:
                occlusion_bound_count += 1
            attributes = sorted((primitive.get("attributes") or {}).keys())
            texcoord_presence = {
                f"TEXCOORD_{index}": f"TEXCOORD_{index}" in attributes
                for index in range(3)
            }
            for name, present in texcoord_presence.items():
                texcoord_presence_counts[name] += int(present)
            texture_bindings = {
                "baseColorTexture": base_color,
                "metallicRoughnessTexture": metallic_roughness,
                "normalTexture": normal,
                "occlusionTexture": occlusion,
            }
            bound_texcoord_checks: list[dict[str, Any]] = []
            for semantic, descriptor in texture_bindings.items():
                if descriptor is None:
                    continue
                required = descriptor["required_attribute"]
                present = required in attributes
                bound_texcoord_missing_count += int(not present)
                bound_texcoord_checks.append(
                    {
                        "semantic": semantic,
                        "required_attribute": required,
                        "attribute_present": present,
                    }
                )
            records.append(
                {
                    "mesh_index": mesh_index,
                    "mesh_name": mesh_name,
                    "primitive_index": primitive_index,
                    "material_index": material_index,
                    "material_name": material.get("name"),
                    "primitive_attributes": attributes,
                    "texcoord_0_1_2_presence": texcoord_presence,
                    "bound_texcoord_checks": bound_texcoord_checks,
                    "all_bound_texcoords_present": all(
                        item["attribute_present"] for item in bound_texcoord_checks
                    ),
                    "baseColor": {
                        "factor": pbr.get("baseColorFactor", [1.0, 1.0, 1.0, 1.0]),
                        "texture": base_color,
                    },
                    "metallicRoughness": {
                        "metallicFactor": pbr.get("metallicFactor", 1.0),
                        "roughnessFactor": pbr.get("roughnessFactor", 1.0),
                        "texture": metallic_roughness,
                    },
                    "normal": {
                        "texture": normal,
                        "scale": (material.get("normalTexture") or {}).get(
                            "scale", 1.0
                        ),
                    },
                    "occlusionTexture": {
                        "texture": occlusion,
                        "strength": (material.get("occlusionTexture") or {}).get(
                            "strength", 1.0
                        )
                        if material.get("occlusionTexture") is not None
                        else None,
                    },
                }
            )

    return {
        "artifact": artifact_record(path),
        "gltf_asset": gltf.get("asset"),
        "r2j_exterior_primitive_count": len(records),
        "r2j_exterior_material_count": len(material_indices),
        "r2j_exterior_primitives": records,
        "texcoord_0_1_2_primitive_presence_counts": texcoord_presence_counts,
        "bound_texcoord_missing_count": bound_texcoord_missing_count,
        "all_bound_texcoords_present": bound_texcoord_missing_count == 0,
        "occlusion_texture_bound_count": occlusion_bound_count,
        "any_r2j_exterior_occlusion_texture_bound": occlusion_bound_count > 0,
    }


def png_rgba_channel_statistics(path: Path) -> dict[str, Any]:
    """Decode a PNG with Pillow and calculate exact histogram statistics."""

    try:
        from PIL import Image
    except ImportError as exc:
        raise AuditError("Pillow is required for exact PNG channel statistics") from exc

    with Image.open(path) as source:
        source.load()
        source_format = source.format
        source_mode = source.mode
        rgba = source.convert("RGBA")
        width, height = rgba.size
        histogram = rgba.histogram()
    pixel_count = width * height
    if len(histogram) != 4 * 256 or pixel_count <= 0:
        raise AuditError(f"Unexpected RGBA histogram for {path}")

    channel_names = ("R", "G", "B", "A")
    channels: dict[str, dict[str, Any]] = {}
    for channel_index, channel_name in enumerate(channel_names):
        counts = histogram[channel_index * 256 : (channel_index + 1) * 256]
        observed = [value for value, count in enumerate(counts) if count]
        if not observed:
            raise AuditError(f"Empty {channel_name} histogram for {path}")
        mean = sum(value * count for value, count in enumerate(counts)) / pixel_count
        variance = (
            sum(((value - mean) ** 2) * count for value, count in enumerate(counts))
            / pixel_count
        )
        nonwhite = pixel_count - counts[255]
        channels[channel_name] = {
            "min_u8": observed[0],
            "max_u8": observed[-1],
            "mean_u8": mean,
            "stddev_u8": math.sqrt(max(variance, 0.0)),
            "nonwhite_sample_count": nonwhite,
            "nonwhite_ratio": nonwhite / pixel_count,
            "white_sample_count": counts[255],
        }

    red = channels["R"]
    red_signal_present = bool(
        red["min_u8"] < 255
        or red["max_u8"] < 255
        or red["stddev_u8"] > 0.0
        or red["nonwhite_sample_count"] > 0
    )
    return {
        "source_format": source_format,
        "source_mode": source_mode,
        "decoded_mode": "RGBA",
        "width": width,
        "height": height,
        "pixel_count": pixel_count,
        "channels": channels,
        "orm_semantics": {
            "R": "ambient_occlusion",
            "G": "roughness",
            "B": "metallic",
            "A": "alpha_or_constant",
        },
        "red_channel_ao_signal_present": red_signal_present,
        "red_channel_is_uniform_white": not red_signal_present,
    }


def _iter_node_links(node_tree: Any) -> Iterable[Any]:
    """Yield links from a Blender node tree without mutating it."""

    return list(node_tree.links) if node_tree is not None else []


def _socket_name(socket: Any) -> str:
    """Return a stable Blender socket name."""

    return str(getattr(socket, "name", "") or getattr(socket, "identifier", ""))


def _node_record(node: Any) -> dict[str, Any]:
    """Return a compact, JSON-safe Blender node record."""

    image = getattr(node, "image", None)
    image_path = None
    packed = False
    if image is not None:
        image_path = str(getattr(image, "filepath", "") or "")
        packed = bool(getattr(image, "packed_file", None))
    return {
        "name": str(node.name),
        "label": str(getattr(node, "label", "") or ""),
        "bl_idname": str(node.bl_idname),
        "type": str(node.type),
        "image_name": str(image.name) if image is not None else None,
        "image_filepath": image_path,
        "image_packed": packed,
    }


def _is_current_orm_node(node: Any) -> bool:
    """Identify the controlled R2G ORM image node by stable image/path token."""

    image = getattr(node, "image", None)
    if image is None:
        return False
    values = (
        str(getattr(image, "name", "") or ""),
        str(getattr(image, "filepath", "") or ""),
        str(getattr(node, "name", "") or ""),
        str(getattr(node, "label", "") or ""),
    )
    return any(CURRENT_ORM_TOKEN.lower() in value.lower() for value in values)


def _outgoing_links(node_tree: Any, node: Any, socket_names: set[str] | None = None) -> list[Any]:
    """Return outgoing links, optionally limited to named source sockets."""

    result = []
    normalized = {name.lower() for name in socket_names} if socket_names else None
    for link in _iter_node_links(node_tree):
        if link.from_node != node:
            continue
        if normalized is not None and _socket_name(link.from_socket).lower() not in normalized:
            continue
        result.append(link)
    return result


def _link_record(link: Any) -> dict[str, Any]:
    """Return a compact, JSON-safe Blender link record."""

    return {
        "from_node": str(link.from_node.name),
        "from_node_type": str(link.from_node.bl_idname),
        "from_socket": _socket_name(link.from_socket),
        "to_node": str(link.to_node.name),
        "to_node_type": str(link.to_node.bl_idname),
        "to_socket": _socket_name(link.to_socket),
    }


def _trace_downstream_paths(
    node_tree: Any,
    start_node: Any,
    *,
    start_socket_names: set[str] | None = None,
    maximum_depth: int = 12,
) -> list[list[dict[str, Any]]]:
    """Trace finite downstream node-link paths from a node/socket selection."""

    initial = _outgoing_links(node_tree, start_node, start_socket_names)
    paths: list[list[dict[str, Any]]] = []

    def visit(link: Any, path: list[dict[str, Any]], seen: set[tuple[str, str, str]]) -> None:
        record = _link_record(link)
        new_path = [*path, record]
        target = link.to_node
        key = (str(target.name), record["to_socket"], record["from_node"])
        if key in seen or len(new_path) >= maximum_depth:
            paths.append(new_path)
            return
        outgoing = _outgoing_links(node_tree, target)
        if not outgoing:
            paths.append(new_path)
            return
        for child in outgoing:
            visit(child, new_path, {*seen, key})

    for link in initial:
        visit(link, [], set())
    return paths


def inspect_orm_r_branch(material: Any) -> dict[str, Any]:
    """Inspect whether a material's current ORM red branch has any consumer."""

    node_tree = material.node_tree if material and material.use_nodes else None
    if node_tree is None:
        return {
            "material_name": material.name if material else None,
            "uses_nodes": False,
            "orm_nodes": [],
            "orm_r_connected": False,
        }

    orm_nodes = [node for node in node_tree.nodes if _is_current_orm_node(node)]
    orm_records: list[dict[str, Any]] = []
    any_r_connected = False
    for orm_node in orm_nodes:
        color_links = _outgoing_links(node_tree, orm_node, {"Color"})
        direct_occlusion = [
            link
            for link in color_links
            if "occlusion" in _socket_name(link.to_socket).lower()
            or "ambient occlusion" in _socket_name(link.to_socket).lower()
        ]
        separators = [
            link.to_node
            for link in color_links
            if str(link.to_node.bl_idname)
            in {"ShaderNodeSeparateColor", "ShaderNodeSeparateRGB"}
        ]
        r_branch_links: list[Any] = []
        r_paths: list[list[dict[str, Any]]] = []
        for separator in separators:
            links = _outgoing_links(node_tree, separator, {"Red", "R"})
            r_branch_links.extend(links)
            r_paths.extend(
                _trace_downstream_paths(
                    node_tree,
                    separator,
                    start_socket_names={"Red", "R"},
                )
            )
        connected = bool(direct_occlusion or r_branch_links)
        any_r_connected = any_r_connected or connected
        orm_records.append(
            {
                "node": _node_record(orm_node),
                "color_output_links": [_link_record(link) for link in color_links],
                "direct_occlusion_links": [
                    _link_record(link) for link in direct_occlusion
                ],
                "separator_nodes": [_node_record(node) for node in separators],
                "r_branch_link_count": len(r_branch_links),
                "r_branch_links": [_link_record(link) for link in r_branch_links],
                "r_branch_downstream_paths": r_paths,
                "orm_r_connected": connected,
            }
        )
    return {
        "material_name": str(material.name),
        "uses_nodes": True,
        "all_image_nodes": [
            _node_record(node)
            for node in node_tree.nodes
            if getattr(node, "image", None) is not None
        ],
        "orm_node_count": len(orm_nodes),
        "orm_nodes": orm_records,
        "orm_r_connected": any_r_connected,
    }


def run_blend_probe(output: Path) -> int:
    """Inspect the already-open V5 Blend without changing or saving it."""

    try:
        import bpy  # type: ignore
    except ImportError as exc:
        raise AuditError("--blend-probe must run inside Blender") from exc

    actual_blend = Path(bpy.data.filepath).resolve()
    expected_blend = V5_BLEND.resolve()
    blend_lock = artifact_record(V5_BLEND, LOCKS["v5_direct_open_blend"][1])
    if actual_blend != expected_blend:
        raise AuditError(
            f"Blender opened the wrong file: actual={actual_blend}, "
            f"expected={expected_blend}"
        )
    if not blend_lock["lock_passed"]:
        raise AuditError("V5 Blend SHA lock failed inside Blender probe")

    objects: list[dict[str, Any]] = []
    material_names: set[str] = set()
    for object_name in sorted(R2J_EXTERIOR_OBJECTS):
        obj = bpy.data.objects.get(object_name)
        if obj is None:
            raise AuditError(f"V5 Blend is missing R2J exterior object: {object_name}")
        if obj.type != "MESH":
            raise AuditError(f"R2J exterior is not a mesh: {object_name}:{obj.type}")
        uv_layers = [
            {
                "name": str(layer.name),
                "active": obj.data.uv_layers.active == layer,
                "active_render": bool(layer.active_render),
            }
            for layer in obj.data.uv_layers
        ]
        slots = []
        for slot_index, slot in enumerate(obj.material_slots):
            material = slot.material
            slots.append(
                {
                    "slot_index": slot_index,
                    "material_name": str(material.name) if material else None,
                }
            )
            if material is not None:
                material_names.add(str(material.name))
        objects.append(
            {
                "object_name": object_name,
                "mesh_name": str(obj.data.name),
                "uv_layers": uv_layers,
                "material_slots": slots,
            }
        )

    materials = []
    for material_name in sorted(material_names):
        material = bpy.data.materials.get(material_name)
        if material is None:
            raise AuditError(f"Material disappeared during probe: {material_name}")
        materials.append(inspect_orm_r_branch(material))

    all_uv_layer_names = sorted(
        {
            layer["name"]
            for object_record in objects
            for layer in object_record["uv_layers"]
        }
    )
    current_orm_material_count = sum(
        int(material["orm_node_count"] > 0) for material in materials
    )
    connected_material_count = sum(
        int(material["orm_r_connected"]) for material in materials
    )
    report = {
        "schema_version": BLEND_PROBE_SCHEMA_VERSION,
        "requirement_id": REQUIREMENT_ID,
        "stage_id": STAGE_ID,
        "generated_at": now_iso(),
        "probe_mode": "read_only_no_save",
        "blender_version": ".".join(str(value) for value in bpy.app.version),
        "opened_blend_path": relative_path(actual_blend),
        "blend_lock": blend_lock,
        "r2j_exterior_object_count": len(objects),
        "r2j_exterior_objects": objects,
        "r2j_exterior_uv_layer_names": all_uv_layer_names,
        "r2j_exterior_material_count": len(materials),
        "r2j_exterior_materials": materials,
        "current_orm_material_count": current_orm_material_count,
        "current_orm_r_connected_material_count": connected_material_count,
        "current_blend_orm_r_connected": connected_material_count > 0,
        "probe_completed": (
            len(objects) == 5
            and len(materials) > 0
            and bool(all_uv_layer_names)
            and blend_lock["lock_passed"]
        ),
        "scene_saved": False,
        "scene_mutations_requested": False,
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    if not report["probe_completed"]:
        raise AuditError("Blend probe evidence is incomplete")
    return 0


def launch_blend_probe(blender_exe: Path, output: Path) -> dict[str, Any]:
    """Launch Blender background mode and return its read-only probe report."""

    if not blender_exe.is_file():
        raise AuditError(f"Blender executable not found: {blender_exe}")
    command = [
        str(blender_exe),
        "--background",
        str(V5_BLEND),
        "--python-exit-code",
        "1",
        "--python",
        str(Path(__file__).resolve()),
        "--",
        "--blend-probe",
        "--output",
        str(output),
    ]
    result = subprocess.run(
        command,
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    if result.returncode != 0:
        raise AuditError(
            "Blender read-only probe failed: "
            f"exit={result.returncode}; stdout_tail={result.stdout[-2000:]!r}; "
            f"stderr_tail={result.stderr[-2000:]!r}"
        )
    if not output.is_file():
        raise AuditError("Blender returned success without the required probe report")
    try:
        report = json.loads(output.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise AuditError(f"Invalid Blender probe JSON: {output}: {exc}") from exc
    if report.get("schema_version") != BLEND_PROBE_SCHEMA_VERSION:
        raise AuditError("Unexpected Blender probe schema")
    if not report.get("probe_completed"):
        raise AuditError("Blender probe did not complete")
    return report


def read_p50_r3_uv_contract(blend_probe: dict[str, Any]) -> dict[str, Any]:
    """Record why the historical P50 R3 atlas cannot be reused on V5 R2J."""

    try:
        manifest = json.loads(P50_R3_MANIFEST.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise AuditError(f"Invalid P50 R3 manifest JSON: {exc}") from exc
    atlas = manifest.get("atlas") or {}
    old_uv_layer = atlas.get("uv_layer")
    old_targets = sorted(str(value) for value in (atlas.get("targets") or []))
    current_uv_layers = sorted(
        str(value) for value in (blend_probe.get("r2j_exterior_uv_layer_names") or [])
    )
    current_targets = sorted(
        str(item.get("object_name"))
        for item in (blend_probe.get("r2j_exterior_objects") or [])
    )
    uv_layer_name_compatible = old_uv_layer in current_uv_layers
    target_identity_compatible = set(old_targets) == set(current_targets)
    reasons = []
    if not uv_layer_name_compatible:
        reasons.append(
            "UV_LAYER_NAME_MISMATCH_P50_UV0_NOT_PRESENT_ON_V5_R2J_EXTERIORS"
        )
    if not target_identity_compatible:
        reasons.append(
            "TARGET_OBJECT_IDENTITY_MISMATCH_APPROX_GL02_VS_R2J_ASM_GL02"
        )
    reuse_allowed = uv_layer_name_compatible and target_identity_compatible
    return {
        "manifest": artifact_record(
            P50_R3_MANIFEST, LOCKS["legacy_p50_ao_r3_manifest"][1]
        ),
        "candidate": manifest.get("candidate"),
        "legacy_atlas": {
            "layout_id": atlas.get("layout_id"),
            "uv_layer": old_uv_layer,
            "targets": old_targets,
            "texture_size": atlas.get("texture_size"),
            "island_count": atlas.get("island_count"),
        },
        "legacy_ao_map": (manifest.get("maps") or {}).get("AO"),
        "legacy_orm_map": (manifest.get("maps") or {}).get("ORM"),
        "v5_r2j_exterior_uv_layer_names": current_uv_layers,
        "v5_r2j_exterior_targets": current_targets,
        "uv_layer_name_compatible": uv_layer_name_compatible,
        "target_identity_compatible": target_identity_compatible,
        "incompatibility_reason_codes": reasons,
        "reuse_old_p50_atlas_allowed": reuse_allowed,
        "finding": (
            "The P50 R3 AO atlas is a P50_UV0 atlas for five APPROX_GL02 "
            "targets; V5 uses five R2J_ASM_GL02 exterior meshes and different "
            "named UV layers. Direct reuse is therefore forbidden."
        ),
    }


def build_audit(blender_exe: Path, blend_probe_output: Path) -> dict[str, Any]:
    """Build the consolidated R2W AO-consumption evidence report."""

    locks = validate_locks()
    if not locks["all_locks_passed"]:
        failed = [
            name
            for name, record in locks["artifacts"].items()
            if not record["lock_passed"]
        ]
        raise AuditError(f"Controlled input lock failed: {failed}")

    orm_stats = png_rgba_channel_statistics(CURRENT_ORM)
    glb_audits = {
        "main": audit_glb_material_consumption(V5_MAIN),
        "material": audit_glb_material_consumption(V5_MATERIAL),
        "structural": audit_glb_material_consumption(V5_STRUCTURAL),
    }
    blend_probe = launch_blend_probe(blender_exe, blend_probe_output)
    post_probe_locks = validate_locks()
    p50 = read_p50_r3_uv_contract(blend_probe)

    current_ao_signal_present = bool(
        orm_stats["red_channel_ao_signal_present"]
    )
    current_glb_occlusion_bound = any(
        audit["any_r2j_exterior_occlusion_texture_bound"]
        for audit in glb_audits.values()
    )
    current_blend_orm_r_connected = bool(
        blend_probe["current_blend_orm_r_connected"]
    )
    reuse_old_p50_atlas_allowed = bool(
        p50["reuse_old_p50_atlas_allowed"]
    )

    assertions = {
        "controlled_input_sha_locks_pass": locks["all_locks_passed"],
        "controlled_input_sha_locks_still_pass_after_blender_probe": (
            post_probe_locks["all_locks_passed"]
        ),
        "controlled_input_hashes_unchanged_during_audit": all(
            locks["artifacts"][name]["sha256"]
            == post_probe_locks["artifacts"][name]["sha256"]
            for name in locks["artifacts"]
        ),
        "current_orm_decodes_to_rgba": orm_stats["decoded_mode"] == "RGBA",
        "current_orm_is_4096_square": (
            orm_stats["width"] == 4096 and orm_stats["height"] == 4096
        ),
        "current_ao_signal_present_is_false": not current_ao_signal_present,
        "current_glb_occlusion_bound_is_false": not current_glb_occlusion_bound,
        "blend_probe_completed": bool(blend_probe["probe_completed"]),
        "five_v5_r2j_exterior_objects_in_blend": (
            blend_probe["r2j_exterior_object_count"] == 5
        ),
        "five_r2j_exterior_primitives_in_main_glb": (
            glb_audits["main"]["r2j_exterior_primitive_count"] == 5
        ),
        "five_r2j_exterior_primitives_in_material_glb": (
            glb_audits["material"]["r2j_exterior_primitive_count"] == 5
        ),
        "no_r2j_exterior_primitives_in_structural_glb": (
            glb_audits["structural"]["r2j_exterior_primitive_count"] == 0
        ),
        "all_bound_texture_texcoords_exist": all(
            audit["all_bound_texcoords_present"] for audit in glb_audits.values()
        ),
        "texcoord_0_1_2_enumerated_for_every_r2j_primitive": all(
            set(record["texcoord_0_1_2_presence"])
            == {"TEXCOORD_0", "TEXCOORD_1", "TEXCOORD_2"}
            for audit in glb_audits.values()
            for record in audit["r2j_exterior_primitives"]
        ),
        "legacy_p50_r3_manifest_lock_pass": p50["manifest"]["lock_passed"],
        "legacy_p50_uv_contract_is_incompatible": (
            not p50["uv_layer_name_compatible"]
            and not p50["target_identity_compatible"]
        ),
        "reuse_old_p50_atlas_allowed_is_false": (
            not reuse_old_p50_atlas_allowed
        ),
    }
    audit_passed = all(assertions.values())
    report = {
        "schema_version": SCHEMA_VERSION,
        "requirement_id": REQUIREMENT_ID,
        "stage_id": STAGE_ID,
        "generated_at": now_iso(),
        "audit_mode": "fail_closed_read_only",
        "scope": {
            "writes_allowed": [
                relative_path(blend_probe_output),
                relative_path(DEFAULT_OUTPUT),
            ],
            "asset_mutation_allowed": False,
            "ao_generation_allowed": False,
            "lighting_changes_allowed": False,
            "page_changes_allowed": False,
            "model_changes_allowed": False,
        },
        "input_locks": locks,
        "post_blender_probe_input_locks": post_probe_locks,
        "current_r2g_orm_4k": {
            "artifact": locks["artifacts"]["current_r2g_orm_4k"],
            "decoded_statistics": orm_stats,
        },
        "v5_glb_material_consumption": glb_audits,
        "v5_blend_material_consumption": {
            "probe_report": artifact_record(blend_probe_output),
            "probe": blend_probe,
        },
        "legacy_p50_r3_uv_compatibility": p50,
        "current_ao_signal_present": current_ao_signal_present,
        "current_glb_occlusion_bound": current_glb_occlusion_bound,
        "current_blend_orm_r_connected": current_blend_orm_r_connected,
        "reuse_old_p50_atlas_allowed": reuse_old_p50_atlas_allowed,
        "assertions": assertions,
        "audit_completed": audit_passed,
        "audit_passed": audit_passed,
        "ao_consumption_ready": (
            current_ao_signal_present
            and current_glb_occlusion_bound
            and current_blend_orm_r_connected
        ),
        "release_or_production_approval_granted": False,
        "conclusion": (
            "The controlled ORM file exists, but its R channel contains no AO "
            "variation; V5 R2J exterior glTF materials do not bind an "
            "occlusionTexture. The old P50 R3 AO atlas is not UV/target "
            "compatible with V5 and must not be reused directly."
        ),
        "next_action_boundary": (
            "A later controlled stage may generate AO for the actual V5 R2J UV "
            "contract and bind it explicitly. This audit did not do so."
        ),
    }
    if not audit_passed:
        failed = [name for name, passed in assertions.items() if not passed]
        raise AuditError(f"Mandatory AO-consumption assertions failed: {failed}")
    return report


def parse_args(argv: list[str]) -> argparse.Namespace:
    """Parse command-line arguments for normal or Blender-probe mode."""

    parser = argparse.ArgumentParser(
        description=(
            "Read-only, fail-closed audit of V5 R2J AO signal, glTF binding, "
            "Blend node consumption, UV attributes and P50 R3 incompatibility."
        )
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT,
        help="Consolidated report path, or probe report path in --blend-probe mode.",
    )
    parser.add_argument(
        "--blend-probe",
        action="store_true",
        help="Run only the read-only bpy probe; Blender background mode only.",
    )
    parser.add_argument(
        "--blend-probe-output",
        type=Path,
        default=DEFAULT_BLEND_PROBE_OUTPUT,
        help="Temporary read-only Blender probe report path.",
    )
    parser.add_argument(
        "--blender-exe",
        type=Path,
        default=DEFAULT_BLENDER,
        help="Blender executable used for the background read-only probe.",
    )
    return parser.parse_args(argv)


def main() -> int:
    """Run the requested audit mode and return a process exit code."""

    argv = sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else sys.argv[1:]
    args = parse_args(argv)
    try:
        if args.blend_probe:
            return run_blend_probe(args.output.resolve())
        output = args.output.resolve()
        probe_output = args.blend_probe_output.resolve()
        report = build_audit(args.blender_exe.resolve(), probe_output)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(
            json.dumps(report, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        print(
            json.dumps(
                {
                    "status": "PASS",
                    "report": str(output),
                    "current_ao_signal_present": report[
                        "current_ao_signal_present"
                    ],
                    "current_glb_occlusion_bound": report[
                        "current_glb_occlusion_bound"
                    ],
                    "current_blend_orm_r_connected": report[
                        "current_blend_orm_r_connected"
                    ],
                    "reuse_old_p50_atlas_allowed": report[
                        "reuse_old_p50_atlas_allowed"
                    ],
                },
                ensure_ascii=False,
            )
        )
        return 0
    except (AuditError, OSError, ValueError, KeyError, TypeError) as exc:
        print(f"AO consumption audit failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
