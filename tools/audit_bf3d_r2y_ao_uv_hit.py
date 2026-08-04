#!/usr/bin/env python3
"""Deterministically audit R2Y AO UV hits without rendering or mutation.

Requirement:
    REQ-BF3D-R2Y-MATERIAL-SIGNAL-VISIBILITY-DIAGNOSTIC-20260720

The audit strictly parses the locked R2X GLB, rasterizes ``POSITION``,
``indices`` and ``TEXCOORD_2`` on the CPU, performs front-face culling and a
z-buffer, and evaluates nearest, bilinear and trilinear mip AO samples for the
locked global/detail cameras.  It also maps atlas signal texels and visible
fragments to process-elevation bands.

This is diagnostic evidence only.  A CPU hit does not prove WebGL shader
consumption or final 8-bit visibility, and this command never mutates V5,
R2X, formal, production, Blend, GLB or texture inputs.
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import math
import platform
import struct
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image
from scipy import __version__ as scipy_version
from scipy import ndimage


REQUIREMENT_ID = (
    "REQ-BF3D-R2Y-MATERIAL-SIGNAL-VISIBILITY-DIAGNOSTIC-20260720"
)
STAGE_ID = "WEB_60_20260720_R2Y_MATERIAL_SIGNAL_VISIBILITY_DIAGNOSTIC"
ROOT = Path(__file__).resolve().parents[1]
STAGE = ROOT / "PT" / "高炉3D模型" / "work" / STAGE_ID
R2X_STAGE = (
    ROOT
    / "PT"
    / "高炉3D模型"
    / "work"
    / "WEB_60_20260720_R2X_R2J_AO_REBAKE_CANDIDATE"
)
MODEL = (
    R2X_STAGE
    / "glb"
    / "gl02_blast_furnace_material_review.r2x-ao-smoke1k.v5payload.glb"
)
AO_PNG = R2X_STAGE / "textures" / "GL02_R2J_LOCAL_CONTACT_AO_1K.png"
RUNTIME_REPORT = (
    R2X_STAGE / "reports" / "bf3d_review_r2x_representative_report.json"
)
DEFAULT_REPORT = STAGE / "reports" / "r2y_ao_uv_hit_raster_audit.json"
DEFAULT_PREVIEW_DIR = STAGE / "preview" / "uv-hit"

EXPECTED_INPUTS: dict[str, tuple[int, str]] = {
    "高炉前端数据/models/gl02_blast_furnace_material_review.v5.glb": (
        994_372,
        "652be1b2c9147d5a7392497c7ae4964d19bdd7095b5435b87c105f9eb3fb66bc",
    ),
    (
        "PT/高炉3D模型/work/"
        "WEB_60_20260720_R2X_R2J_AO_REBAKE_CANDIDATE/glb/"
        "gl02_blast_furnace_material_review.r2x-ao-smoke1k.v5payload.glb"
    ): (
        1_115_216,
        "bd074c23c237fe7ff3abac0f823bd9aef978021e4e829963b3f979e9b58f1c00",
    ),
    (
        "PT/高炉3D模型/work/"
        "WEB_60_20260720_R2X_R2J_AO_REBAKE_CANDIDATE/textures/"
        "GL02_R2J_LOCAL_CONTACT_AO_1K.png"
    ): (
        24_655,
        "c1362fa572e94e2b8f704ab9d3ec46aed6cc930d7616bb4ad14a38793abcf786",
    ),
    (
        "PT/高炉3D模型/work/"
        "WEB_60_20260720_R2X_R2J_AO_REBAKE_CANDIDATE/reports/"
        "bf3d_review_r2x_representative_report.json"
    ): (
        96_430,
        "3a70ec80dfd3f98fe15a4e69e35cbe086b906f91f72f9a2cd520c1d6bd01cdd8",
    ),
    "高炉前端数据/assets/bf3d-review-renderer-r2x.js": (
        43_968,
        "807b5697d8d74c640860e169b0c77ce8b1a06ca5653941a37d7953f53dc8edf2",
    ),
    "高炉前端数据/libs/three/three.module.js": (
        1_272_972,
        "76dea8151bc9352aef3528b4262e249b2604f62543828328db978d060d61a495",
    ),
    "高炉前端数据/libs/three/loaders/GLTFLoader.js": (
        108_522,
        "d073b438e6a07e1359741dd5d6c76c953420cc0d4fd84eb1bdde94315540e6a3",
    ),
}

TARGET_NAMES = (
    "R2J_ASM_GL02_FURNACE_BELLY_SHELL_55MM_E",
    "R2J_ASM_GL02_FURNACE_BOSH_SHELL_55MM_E",
    "R2J_ASM_GL02_FURNACE_HEARTH_SHELL_65MM_E",
    "R2J_ASM_GL02_FURNACE_SHAFT_SHELL_45MM_E",
    "R2J_ASM_GL02_FURNACE_THROAT_SHELL_45MM_E",
)

THRESHOLDS = {
    "uv_triangle_interior_nonwhite_texels_minimum": 64,
    "view_mip_nonwhite_pixels_minimum": 64,
    "view_mip_nonwhite_ratio_minimum": 0.00005,
    "view_mip_minimum_r_maximum": 0.98,
    "affected_pixel_mean_ao_drop_minimum": 0.002,
    "cpu_runtime_projection_score_error_maximum": 0.005,
    "synthetic_black_ao_changed_pixels_minimum": 64,
    "float_linear_max_abs_diff_minimum_exclusive": 1.0e-5,
    "final_u8_changed_pixels_minimum": 64,
    "final_u8_mean_abs_diff_rgb_minimum": 0.25,
}

GLB_MAGIC = b"glTF"
GLB_JSON_CHUNK = b"JSON"
GLB_BIN_CHUNK = b"BIN\x00"
NONWHITE_EPSILON = 1.0e-9
RASTER_EPSILON = 1.0e-9
MARGIN_WORLD_MAP_MAXIMUM_PX = 32.0
WORLD_BAND_BIN_M = 0.05

COMPONENT_DTYPES: dict[int, tuple[str, int, bool, float | None]] = {
    5120: ("i1", 1, True, 127.0),
    5121: ("u1", 1, False, 255.0),
    5122: ("<i2", 2, True, 32767.0),
    5123: ("<u2", 2, False, 65535.0),
    5125: ("<u4", 4, False, 4294967295.0),
    5126: ("<f4", 4, True, None),
}
TYPE_COMPONENT_COUNTS = {
    "SCALAR": 1,
    "VEC2": 2,
    "VEC3": 3,
    "VEC4": 4,
    "MAT2": 4,
    "MAT3": 9,
    "MAT4": 16,
}


class AuditError(RuntimeError):
    """Raised when deterministic evidence cannot be established."""


@dataclass(frozen=True)
class Primitive:
    """One scene-instantiated triangle primitive used by the audit."""

    mesh_id: int
    node_name: str
    mesh_name: str
    material_index: int
    positions: np.ndarray
    texcoord_2: np.ndarray
    triangles: np.ndarray
    front_face_sign: float
    process_elevation_offset_m: float
    accessor_indices: dict[str, int]


def parse_args() -> argparse.Namespace:
    """Parse the small reproducible CLI surface."""

    parser = argparse.ArgumentParser(
        description=(
            "Run the locked R2Y CPU AO/UV hit raster audit and write JSON/"
            "PNG diagnostic evidence. Inputs are immutable pre-registered "
            "R2X artifacts."
        )
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_REPORT,
        help=(
            "Output JSON path inside the R2Y stage "
            f"(default: {DEFAULT_REPORT.relative_to(ROOT).as_posix()})"
        ),
    )
    parser.add_argument(
        "--preview-dir",
        type=Path,
        default=DEFAULT_PREVIEW_DIR,
        help=(
            "Heatmap directory inside the R2Y stage "
            f"(default: {DEFAULT_PREVIEW_DIR.relative_to(ROOT).as_posix()})"
        ),
    )
    return parser.parse_args()


def now_iso() -> str:
    """Return an RFC 3339 UTC timestamp."""

    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def sha256_bytes(payload: bytes) -> str:
    """Return lowercase SHA-256 for bytes."""

    return hashlib.sha256(payload).hexdigest()


def sha256_file(path: Path) -> str:
    """Return lowercase SHA-256 for one file."""

    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def relative_path(path: Path) -> str:
    """Return one repository-relative POSIX path."""

    try:
        return path.resolve().relative_to(ROOT.resolve()).as_posix()
    except ValueError as exc:
        raise AuditError(f"Path is outside the repository: {path}") from exc


def ensure_owned_output(path: Path) -> Path:
    """Resolve an output and reject paths outside the owned R2Y stage."""

    resolved = path if path.is_absolute() else ROOT / path
    resolved = resolved.resolve()
    try:
        resolved.relative_to(STAGE.resolve())
    except ValueError as exc:
        raise AuditError(
            f"Output must stay inside the R2Y stage: {resolved}"
        ) from exc
    return resolved


def write_json(path: Path, payload: dict[str, Any]) -> None:
    """Write deterministic UTF-8 JSON inside the owned stage."""

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def inspect_input_locks() -> tuple[list[dict[str, Any]], bool]:
    """Inspect every pre-registered immutable R2Y input."""

    records: list[dict[str, Any]] = []
    for relative, (expected_bytes, expected_sha) in EXPECTED_INPUTS.items():
        path = ROOT / Path(relative)
        exists = path.is_file()
        actual_bytes = path.stat().st_size if exists else None
        actual_sha = sha256_file(path) if exists else None
        passed = (
            exists
            and actual_bytes == expected_bytes
            and actual_sha == expected_sha
        )
        records.append(
            {
                "path": relative,
                "exists": exists,
                "expected_bytes": expected_bytes,
                "actual_bytes": actual_bytes,
                "expected_sha256": expected_sha,
                "actual_sha256": actual_sha,
                "passed": passed,
            }
        )
    return records, all(record["passed"] for record in records)


def load_json_object(path: Path) -> dict[str, Any]:
    """Load a JSON object or fail closed."""

    if not path.is_file():
        raise AuditError(f"Required JSON is missing: {path}")
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise AuditError(f"Invalid JSON: {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise AuditError(f"Expected JSON object: {path}")
    return value


def read_glb(path: Path) -> tuple[dict[str, Any], bytes, dict[str, Any]]:
    """Read one strict GLB 2.0 with exactly one JSON and at most one BIN."""

    if not path.is_file():
        raise AuditError(f"Required GLB is missing: {path}")
    payload = path.read_bytes()
    if len(payload) < 20:
        raise AuditError(f"GLB is too small: {path}")
    magic, version, declared_length = struct.unpack_from("<4sII", payload, 0)
    if (
        magic != GLB_MAGIC
        or version != 2
        or declared_length != len(payload)
    ):
        raise AuditError(
            "GLB header mismatch: "
            f"magic={magic!r}, version={version}, "
            f"length={declared_length}/{len(payload)}"
        )

    chunks: list[tuple[bytes, bytes]] = []
    offset = 12
    while offset < declared_length:
        if offset + 8 > declared_length:
            raise AuditError("Truncated GLB chunk header")
        chunk_length, chunk_type = struct.unpack_from(
            "<I4s", payload, offset
        )
        offset += 8
        if chunk_length % 4:
            raise AuditError(f"Unaligned GLB chunk: {chunk_length}")
        end = offset + chunk_length
        if end > declared_length:
            raise AuditError("Truncated GLB chunk payload")
        chunks.append((chunk_type, payload[offset:end]))
        offset = end
    json_chunks = [
        chunk for chunk_type, chunk in chunks
        if chunk_type == GLB_JSON_CHUNK
    ]
    bin_chunks = [
        chunk for chunk_type, chunk in chunks
        if chunk_type == GLB_BIN_CHUNK
    ]
    if len(json_chunks) != 1 or len(bin_chunks) != 1:
        raise AuditError(
            "R2Y requires exactly one JSON and one BIN chunk: "
            f"JSON={len(json_chunks)}, BIN={len(bin_chunks)}"
        )
    try:
        document = json.loads(
            json_chunks[0].decode("utf-8").rstrip(" \t\r\n\x00")
        )
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise AuditError(f"Invalid GLB JSON chunk: {exc}") from exc
    if not isinstance(document, dict):
        raise AuditError("GLB JSON root is not an object")
    buffers = document.get("buffers") or []
    if (
        len(buffers) != 1
        or not isinstance(buffers[0], dict)
        or buffers[0].get("uri") is not None
    ):
        raise AuditError("R2Y requires one embedded glTF buffer")
    logical_binary_length = int(buffers[0].get("byteLength", -1))
    physical_binary = bin_chunks[0]
    padding_length = len(physical_binary) - logical_binary_length
    if (
        logical_binary_length < 0
        or padding_length not in (0, 1, 2, 3)
        or any(physical_binary[logical_binary_length:])
    ):
        raise AuditError(
            "GLB BIN logical length/padding mismatch: "
            f"logical={logical_binary_length}, "
            f"physical={len(physical_binary)}"
        )
    logical_binary = physical_binary[:logical_binary_length]
    chunk_record = {
        "declared_bytes": declared_length,
        "json_chunk_bytes": len(json_chunks[0]),
        "bin_chunk_physical_bytes": len(physical_binary),
        "bin_buffer_logical_bytes": logical_binary_length,
        "bin_zero_padding_bytes": padding_length,
        "chunk_types": [
            chunk_type.decode("ascii", errors="backslashreplace")
            for chunk_type, _ in chunks
        ],
    }
    return document, logical_binary, chunk_record


def buffer_view_payload(
    document: dict[str, Any],
    binary: bytes,
    view_index: int,
) -> bytes:
    """Return one validated embedded buffer-view payload."""

    views = document.get("bufferViews") or []
    if not (0 <= view_index < len(views)):
        raise AuditError(f"bufferView index out of range: {view_index}")
    view = views[view_index]
    if not isinstance(view, dict) or int(view.get("buffer", 0)) != 0:
        raise AuditError(f"Unsupported bufferView: {view_index}")
    offset = int(view.get("byteOffset", 0))
    length = int(view.get("byteLength", -1))
    end = offset + length
    if offset < 0 or length < 0 or end > len(binary):
        raise AuditError(f"Invalid bufferView range: {view_index}")
    return binary[offset:end]


def decode_accessor(
    document: dict[str, Any],
    binary: bytes,
    accessor_index: int,
) -> np.ndarray:
    """Decode a non-sparse accessor, honoring stride and normalization."""

    accessors = document.get("accessors") or []
    views = document.get("bufferViews") or []
    if not (0 <= accessor_index < len(accessors)):
        raise AuditError(f"Accessor index out of range: {accessor_index}")
    accessor = accessors[accessor_index]
    if not isinstance(accessor, dict) or accessor.get("sparse") is not None:
        raise AuditError(f"Sparse/invalid accessor: {accessor_index}")
    view_index = accessor.get("bufferView")
    if not isinstance(view_index, int) or not (0 <= view_index < len(views)):
        raise AuditError(f"Accessor has invalid bufferView: {accessor_index}")
    view = views[view_index]
    if not isinstance(view, dict) or int(view.get("buffer", 0)) != 0:
        raise AuditError(f"Accessor uses unsupported buffer: {accessor_index}")

    component_type = int(accessor.get("componentType", 0))
    layout = COMPONENT_DTYPES.get(component_type)
    component_count = TYPE_COMPONENT_COUNTS.get(str(accessor.get("type", "")))
    if layout is None or component_count is None:
        raise AuditError(f"Unsupported accessor layout: {accessor_index}")
    dtype_name, component_bytes, signed, denominator = layout
    dtype = np.dtype(dtype_name)
    element_bytes = component_count * component_bytes
    stride = int(view.get("byteStride", element_bytes))
    if stride < element_bytes:
        raise AuditError(f"Accessor stride is too small: {accessor_index}")

    view_offset = int(view.get("byteOffset", 0))
    view_length = int(view.get("byteLength", -1))
    accessor_offset = int(accessor.get("byteOffset", 0))
    count = int(accessor.get("count", -1))
    if min(view_offset, view_length, accessor_offset, count) < 0:
        raise AuditError(f"Negative accessor range: {accessor_index}")
    start = view_offset + accessor_offset
    end = start + max(count - 1, 0) * stride
    end += element_bytes if count else 0
    if (
        start < view_offset
        or end > view_offset + view_length
        or end > len(binary)
    ):
        raise AuditError(f"Accessor exceeds bufferView: {accessor_index}")

    array = np.ndarray(
        shape=(count, component_count),
        dtype=dtype,
        buffer=binary,
        offset=start,
        strides=(stride, component_bytes),
    ).copy()
    if bool(accessor.get("normalized", False)) and denominator is not None:
        normalized = array.astype(np.float64) / denominator
        if signed:
            normalized = np.maximum(normalized, -1.0)
        return normalized
    return array


def quaternion_matrix(values: list[float] | np.ndarray) -> np.ndarray:
    """Return a 4x4 column-vector rotation matrix for x/y/z/w quaternion."""

    x, y, z, w = (float(value) for value in values)
    length = math.sqrt(x * x + y * y + z * z + w * w)
    if length <= 0.0:
        raise AuditError("Quaternion length is zero")
    x, y, z, w = x / length, y / length, z / length, w / length
    matrix = np.eye(4, dtype=np.float64)
    matrix[:3, :3] = np.array(
        [
            [
                1.0 - 2.0 * (y * y + z * z),
                2.0 * (x * y - z * w),
                2.0 * (x * z + y * w),
            ],
            [
                2.0 * (x * y + z * w),
                1.0 - 2.0 * (x * x + z * z),
                2.0 * (y * z - x * w),
            ],
            [
                2.0 * (x * z - y * w),
                2.0 * (y * z + x * w),
                1.0 - 2.0 * (x * x + y * y),
            ],
        ],
        dtype=np.float64,
    )
    return matrix


def node_local_matrix(node: dict[str, Any]) -> np.ndarray:
    """Build one glTF node matrix using matrix or T*R*S."""

    if "matrix" in node:
        values = node["matrix"]
        if not isinstance(values, list) or len(values) != 16:
            raise AuditError("Invalid glTF node matrix")
        return np.asarray(values, dtype=np.float64).reshape((4, 4), order="F")
    translation = np.eye(4, dtype=np.float64)
    translation[:3, 3] = np.asarray(
        node.get("translation", [0.0, 0.0, 0.0]),
        dtype=np.float64,
    )
    rotation = quaternion_matrix(
        node.get("rotation", [0.0, 0.0, 0.0, 1.0])
    )
    scale = np.eye(4, dtype=np.float64)
    scale_values = np.asarray(
        node.get("scale", [1.0, 1.0, 1.0]),
        dtype=np.float64,
    )
    scale[0, 0], scale[1, 1], scale[2, 2] = scale_values
    return translation @ rotation @ scale


def process_elevation_offset(node: dict[str, Any]) -> float:
    """Infer the documented local/world Y to process-elevation offset."""

    extras = node.get("extras") or {}
    pairs = (
        ("start_elevation_m", "local_z_bottom"),
        ("end_elevation_m", "local_z_top"),
    )
    offsets = []
    for elevation_key, local_key in pairs:
        if elevation_key in extras and local_key in extras:
            offsets.append(
                float(extras[elevation_key]) - float(extras[local_key])
            )
    if not offsets or max(offsets) - min(offsets) > 1.0e-5:
        raise AuditError(
            f"Cannot infer stable process-elevation offset: {node.get('name')}"
        )
    return float(sum(offsets) / len(offsets))


def load_primitives(
    document: dict[str, Any],
    binary: bytes,
) -> list[Primitive]:
    """Instantiate the five scene primitives with world positions."""

    nodes = document.get("nodes") or []
    meshes = document.get("meshes") or []
    scenes = document.get("scenes") or []
    scene_index = int(document.get("scene", 0))
    if not (0 <= scene_index < len(scenes)):
        raise AuditError("Invalid default scene")
    roots = scenes[scene_index].get("nodes") or []
    found: list[Primitive] = []

    def visit(
        node_index: int,
        parent_matrix: np.ndarray,
        ancestry: tuple[int, ...],
    ) -> None:
        if node_index in ancestry:
            raise AuditError(f"Node cycle detected: {node_index}")
        if not (0 <= node_index < len(nodes)):
            raise AuditError(f"Node index out of range: {node_index}")
        node = nodes[node_index]
        world = parent_matrix @ node_local_matrix(node)
        mesh_index = node.get("mesh")
        if isinstance(mesh_index, int):
            if not (0 <= mesh_index < len(meshes)):
                raise AuditError(f"Mesh index out of range: {mesh_index}")
            mesh = meshes[mesh_index]
            primitives = mesh.get("primitives") or []
            if len(primitives) != 1:
                raise AuditError(
                    f"R2Y target requires one primitive: {node.get('name')}"
                )
            primitive = primitives[0]
            if int(primitive.get("mode", 4)) != 4:
                raise AuditError("Only TRIANGLES primitives are supported")
            attributes = primitive.get("attributes") or {}
            required = {"POSITION", "TEXCOORD_2"}
            if not required.issubset(attributes):
                raise AuditError(
                    f"Missing POSITION/TEXCOORD_2: {node.get('name')}"
                )
            indices_index = primitive.get("indices")
            if not isinstance(indices_index, int):
                raise AuditError("Non-indexed primitive is outside R2Y")
            positions_local = decode_accessor(
                document, binary, int(attributes["POSITION"])
            ).astype(np.float64)
            uv2 = decode_accessor(
                document, binary, int(attributes["TEXCOORD_2"])
            ).astype(np.float64)
            indices = decode_accessor(
                document, binary, indices_index
            ).reshape(-1)
            if positions_local.shape[1] != 3 or uv2.shape != (
                positions_local.shape[0],
                2,
            ):
                raise AuditError("POSITION/TEXCOORD_2 shape mismatch")
            if indices.size % 3:
                raise AuditError("Index count is not divisible by three")
            indices = indices.astype(np.int64)
            if (
                indices.size == 0
                or int(indices.min()) < 0
                or int(indices.max()) >= positions_local.shape[0]
            ):
                raise AuditError("Primitive index range is invalid")
            homogeneous = np.concatenate(
                [
                    positions_local,
                    np.ones((positions_local.shape[0], 1)),
                ],
                axis=1,
            )
            positions_world = (world @ homogeneous.T).T[:, :3]
            determinant = float(np.linalg.det(world[:3, :3]))
            if abs(determinant) <= 1.0e-12:
                raise AuditError("Node world transform is singular")
            found.append(
                Primitive(
                    mesh_id=-1,
                    node_name=str(node.get("name", "")),
                    mesh_name=str(mesh.get("name", "")),
                    material_index=int(primitive.get("material", -1)),
                    positions=positions_world,
                    texcoord_2=uv2,
                    triangles=indices.reshape((-1, 3)),
                    front_face_sign=1.0 if determinant > 0.0 else -1.0,
                    process_elevation_offset_m=process_elevation_offset(node),
                    accessor_indices={
                        "POSITION": int(attributes["POSITION"]),
                        "TEXCOORD_2": int(attributes["TEXCOORD_2"]),
                        "indices": indices_index,
                    },
                )
            )
        for child in node.get("children") or []:
            visit(int(child), world, ancestry + (node_index,))

    for root in roots:
        visit(int(root), np.eye(4, dtype=np.float64), ())

    by_name = {primitive.node_name: primitive for primitive in found}
    if set(by_name) != set(TARGET_NAMES) or len(found) != len(TARGET_NAMES):
        raise AuditError(
            "Scene target mismatch: "
            f"expected={list(TARGET_NAMES)}, actual={sorted(by_name)}"
        )
    ordered: list[Primitive] = []
    for mesh_id, name in enumerate(TARGET_NAMES):
        item = by_name[name]
        ordered.append(
            Primitive(
                mesh_id=mesh_id,
                node_name=item.node_name,
                mesh_name=item.mesh_name,
                material_index=item.material_index,
                positions=item.positions,
                texcoord_2=item.texcoord_2,
                triangles=item.triangles,
                front_face_sign=item.front_face_sign,
                process_elevation_offset_m=item.process_elevation_offset_m,
                accessor_indices=item.accessor_indices,
            )
        )
    return ordered


def embedded_ao_payload(
    document: dict[str, Any],
    binary: bytes,
) -> tuple[bytes, dict[str, Any]]:
    """Resolve the one occlusion image used by both locked materials."""

    materials = document.get("materials") or []
    textures = document.get("textures") or []
    images = document.get("images") or []
    texture_indices = {
        int(material.get("occlusionTexture", {}).get("index", -1))
        for material in materials
    }
    texcoord_indices = {
        int(material.get("occlusionTexture", {}).get("texCoord", 0))
        for material in materials
    }
    if len(materials) != 2 or len(texture_indices) != 1 or texcoord_indices != {
        2
    }:
        raise AuditError("Material occlusion binding contract failed")
    if any(
        material.get("occlusionTexture", {}).get("extensions")
        for material in materials
    ):
        raise AuditError(
            "R2Y does not silently ignore occlusion texture extensions"
        )
    texture_index = next(iter(texture_indices))
    if not (0 <= texture_index < len(textures)):
        raise AuditError("Occlusion texture index is invalid")
    texture = textures[texture_index]
    source = texture.get("source")
    if not isinstance(source, int) or not (0 <= source < len(images)):
        raise AuditError("Occlusion texture has no valid source")
    image = images[source]
    view_index = image.get("bufferView")
    if (
        image.get("mimeType") != "image/png"
        or not isinstance(view_index, int)
    ):
        raise AuditError("Occlusion image is not embedded PNG")
    payload = buffer_view_payload(document, binary, view_index)
    sampler_index = texture.get("sampler")
    samplers = document.get("samplers") or []
    sampler = (
        samplers[sampler_index]
        if isinstance(sampler_index, int)
        and 0 <= sampler_index < len(samplers)
        else {}
    )
    effective_sampler = {
        "magFilter": int(sampler.get("magFilter", 9729)),
        "minFilter": int(sampler.get("minFilter", 9987)),
        "wrapS": int(sampler.get("wrapS", 10497)),
        "wrapT": int(sampler.get("wrapT", 10497)),
    }
    expected_sampler = {
        "magFilter": 9729,
        "minFilter": 9987,
        "wrapS": 10497,
        "wrapT": 10497,
    }
    if effective_sampler != expected_sampler:
        raise AuditError(
            "AO sampler is not LINEAR/LINEAR_MIPMAP_LINEAR/REPEAT: "
            f"{effective_sampler}"
        )
    return payload, {
        "material_count": len(materials),
        "occlusion_texture_index": texture_index,
        "occlusion_texcoord_indices": sorted(texcoord_indices),
        "image_index": source,
        "image_name": image.get("name"),
        "image_mime_type": image.get("mimeType"),
        "image_buffer_view": view_index,
        "sampler_index": sampler_index,
        "declared_sampler": sampler,
        "effective_sampler": effective_sampler,
        "sampler_contract_passed": True,
    }


def decode_ao(payload: bytes) -> tuple[np.ndarray, dict[str, Any]]:
    """Decode AO PNG to normalized float64 red channel."""

    with Image.open(io.BytesIO(payload)) as image:
        image.load()
        source_format = image.format
        source_mode = image.mode
        rgba = np.asarray(image.convert("RGBA"), dtype=np.uint8)
    red = rgba[..., 0].astype(np.float64) / 255.0
    return red, {
        "source_format": source_format,
        "source_mode": source_mode,
        "decoded_mode": "RGBA",
        "width": int(rgba.shape[1]),
        "height": int(rgba.shape[0]),
        "minimum_r_u8": int(rgba[..., 0].min()),
        "maximum_r_u8": int(rgba[..., 0].max()),
        "mean_r_u8": float(rgba[..., 0].mean()),
        "std_r_u8": float(rgba[..., 0].std()),
        "unique_r_values": int(np.unique(rgba[..., 0]).size),
        "nonwhite_r_texels": int(np.count_nonzero(rgba[..., 0] < 255)),
        "nonwhite_r_ratio": float(np.count_nonzero(rgba[..., 0] < 255))
        / float(rgba.shape[0] * rgba.shape[1]),
    }


def camera_matrices(composition: dict[str, Any]) -> tuple[np.ndarray, np.ndarray]:
    """Build view and projection matrices from Three.js report arrays."""

    position = np.asarray(
        composition.get("cameraPosition"), dtype=np.float64
    )
    quaternion = composition.get("cameraQuaternion")
    projection_values = composition.get("projectionMatrix")
    if (
        position.shape != (3,)
        or not isinstance(quaternion, list)
        or len(quaternion) != 4
        or not isinstance(projection_values, list)
        or len(projection_values) != 16
    ):
        raise AuditError("Runtime camera composition is incomplete")
    camera_world = quaternion_matrix(quaternion)
    camera_world[:3, 3] = position
    view = np.linalg.inv(camera_world)
    projection = np.asarray(
        projection_values, dtype=np.float64
    ).reshape((4, 4), order="F")
    return view, projection


def locked_views(runtime: dict[str, Any]) -> tuple[dict[str, Any], int, int]:
    """Extract immutable global/detail cameras and drawing-buffer size."""

    states = runtime.get("runtime_contract", {}).get("states", {})
    views: dict[str, Any] = {}
    for view_name in ("global", "detail"):
        off = states.get(f"{view_name}-off", {}).get("composition")
        on = states.get(f"{view_name}-on", {}).get("composition")
        if not isinstance(off, dict) or not isinstance(on, dict):
            raise AuditError(f"Missing R2X camera states: {view_name}")
        for field in (
            "cameraPosition",
            "cameraQuaternion",
            "projectionMatrix",
        ):
            if off.get(field) != on.get(field):
                raise AuditError(
                    f"R2X off/on camera differs: {view_name}/{field}"
                )
        views[view_name] = off
    canvas = runtime.get("layout", {}).get("canvas_rect", {})
    width = int(round(float(canvas.get("width", 0))))
    height = int(round(float(canvas.get("height", 0))))
    if width <= 0 or height <= 0:
        raise AuditError("R2X canvas dimensions are invalid")
    return views, width, height


def projection_metrics(
    primitives: list[Primitive],
    composition: dict[str, Any],
) -> dict[str, Any]:
    """Reproduce Three.js ``projected_mesh_vertices_ndc`` metrics."""

    audit = composition.get("projectionAudit") or {}
    target = audit.get("target")
    selected = (
        primitives
        if target == "ALL_FIVE_R2J_SHELLS"
        else [item for item in primitives if item.node_name == target]
    )
    if not selected:
        raise AuditError(f"Projection target not found: {target}")
    view, projection = camera_matrices(composition)
    ndc_arrays = []
    for primitive in selected:
        positions = primitive.positions
        homogeneous = np.concatenate(
            [positions, np.ones((positions.shape[0], 1))], axis=1
        )
        clip = (projection @ view @ homogeneous.T).T
        finite = np.all(np.isfinite(clip), axis=1) & (
            np.abs(clip[:, 3]) > 1.0e-15
        )
        ndc = clip[finite, :3] / clip[finite, 3:4]
        ndc_arrays.append(ndc)
    ndc = np.concatenate(ndc_arrays, axis=0)
    minimum = ndc[:, :2].min(axis=0)
    maximum = ndc[:, :2].max(axis=0)
    center = (minimum + maximum) * 0.5
    cpu = {
        "widthFraction": float((maximum[0] - minimum[0]) * 0.5),
        "heightFraction": float((maximum[1] - minimum[1]) * 0.5),
        "centerOffsetXFraction": float(abs(center[0]) * 0.5),
        "centerOffsetYFraction": float(abs(center[1]) * 0.5),
        "centerOffsetFraction": float(np.max(np.abs(center)) * 0.5),
        "ndcBounds": [
            float(minimum[0]),
            float(minimum[1]),
            float(maximum[0]),
            float(maximum[1]),
        ],
        "projectedVertexCount": int(ndc.shape[0]),
    }
    runtime_metrics = audit.get("metrics") or {}
    scalar_fields = (
        "widthFraction",
        "heightFraction",
        "centerOffsetXFraction",
        "centerOffsetYFraction",
        "centerOffsetFraction",
    )
    errors = {
        field: abs(float(cpu[field]) - float(runtime_metrics[field]))
        for field in scalar_fields
    }
    runtime_bounds = runtime_metrics.get("ndcBounds") or []
    if len(runtime_bounds) != 4:
        raise AuditError("Runtime projection audit has no ndcBounds")
    bound_errors = [
        abs(cpu_value - float(runtime_value))
        for cpu_value, runtime_value in zip(
            cpu["ndcBounds"], runtime_bounds, strict=True
        )
    ]
    maximum_error = max([*errors.values(), *bound_errors])
    count_matches = (
        int(cpu["projectedVertexCount"])
        == int(runtime_metrics.get("projectedVertexCount", -1))
    )
    return {
        "view": composition.get("view"),
        "target": target,
        "method": "projected_mesh_vertices_ndc",
        "cpu_metrics": cpu,
        "runtime_metrics": runtime_metrics,
        "absolute_errors": {
            **errors,
            "ndcBounds": bound_errors,
        },
        "maximum_fraction_error": float(maximum_error),
        "projected_vertex_count_matches": count_matches,
        "threshold": THRESHOLDS[
            "cpu_runtime_projection_score_error_maximum"
        ],
        "passed": bool(
            count_matches
            and maximum_error
            <= THRESHOLDS[
                "cpu_runtime_projection_score_error_maximum"
            ]
        ),
    }


def triangle_patch(
    points: np.ndarray,
    width: int,
    height: int,
) -> tuple[int, int, int, int, np.ndarray, np.ndarray, np.ndarray] | None:
    """Return a clipped pixel-center barycentric patch for one triangle."""

    minimum_x = max(0, int(math.ceil(float(points[:, 0].min()))))
    maximum_x = min(
        width - 1, int(math.floor(float(points[:, 0].max())))
    )
    minimum_y = max(0, int(math.ceil(float(points[:, 1].min()))))
    maximum_y = min(
        height - 1, int(math.floor(float(points[:, 1].max())))
    )
    if minimum_x > maximum_x or minimum_y > maximum_y:
        return None
    x0, y0 = points[0]
    x1, y1 = points[1]
    x2, y2 = points[2]
    denominator = (y1 - y2) * (x0 - x2)
    denominator += (x2 - x1) * (y0 - y2)
    if abs(float(denominator)) <= 1.0e-15:
        return None
    xs = np.arange(minimum_x, maximum_x + 1, dtype=np.float64)
    ys = np.arange(minimum_y, maximum_y + 1, dtype=np.float64)
    grid_x, grid_y = np.meshgrid(xs, ys)
    bary0 = (
        (y1 - y2) * (grid_x - x2)
        + (x2 - x1) * (grid_y - y2)
    ) / denominator
    bary1 = (
        (y2 - y0) * (grid_x - x2)
        + (x0 - x2) * (grid_y - y2)
    ) / denominator
    bary2 = 1.0 - bary0 - bary1
    return (
        minimum_x,
        maximum_x,
        minimum_y,
        maximum_y,
        bary0,
        bary1,
        bary2,
    )


def continuous_bands(
    values: np.ndarray,
    bin_size_m: float = WORLD_BAND_BIN_M,
) -> dict[str, Any]:
    """Summarize finite elevations into deterministic occupied-bin bands."""

    finite = np.asarray(values, dtype=np.float64)
    finite = finite[np.isfinite(finite)]
    if finite.size == 0:
        return {
            "sample_count": 0,
            "bin_size_m": bin_size_m,
            "continuous_bands": [],
        }
    bins = np.floor(finite / bin_size_m).astype(np.int64)
    unique, counts = np.unique(bins, return_counts=True)
    bands: list[dict[str, Any]] = []
    run_start = 0
    for index in range(1, unique.size + 1):
        if index < unique.size and unique[index] == unique[index - 1] + 1:
            continue
        run_bins = unique[run_start:index]
        run_min = int(run_bins[0])
        run_max = int(run_bins[-1])
        mask = (bins >= run_min) & (bins <= run_max)
        run_values = finite[mask]
        bands.append(
            {
                "start_m": float(run_min * bin_size_m),
                "end_m_exclusive": float((run_max + 1) * bin_size_m),
                "actual_minimum_m": float(run_values.min()),
                "actual_maximum_m": float(run_values.max()),
                "occupied_bin_count": int(run_bins.size),
                "sample_count": int(counts[run_start:index].sum()),
            }
        )
        run_start = index
    return {
        "sample_count": int(finite.size),
        "minimum_m": float(finite.min()),
        "maximum_m": float(finite.max()),
        "mean_m": float(finite.mean()),
        "std_m": float(finite.std()),
        "quantiles_m": {
            "p05": float(np.quantile(finite, 0.05)),
            "p50": float(np.quantile(finite, 0.50)),
            "p95": float(np.quantile(finite, 0.95)),
        },
        "bin_size_m": bin_size_m,
        "continuous_bands": bands,
    }


def distance_distribution(values: np.ndarray) -> dict[str, Any]:
    """Summarize bake-margin distances with fixed audit bins."""

    finite = np.asarray(values, dtype=np.float64)
    finite = finite[np.isfinite(finite)]
    edges = [0.0, 1.0, 2.0, 4.0, 8.0, 16.0, 32.0, math.inf]
    labels = [
        "(0,1]",
        "(1,2]",
        "(2,4]",
        "(4,8]",
        "(8,16]",
        "(16,32]",
        "(32,inf)",
    ]
    if finite.size == 0:
        return {
            "sample_count": 0,
            "bins_px": {label: 0 for label in labels},
        }
    counts: dict[str, int] = {}
    for lower, upper, label in zip(
        edges[:-1], edges[1:], labels, strict=True
    ):
        counts[label] = int(
            np.count_nonzero((finite > lower) & (finite <= upper))
        )
    return {
        "sample_count": int(finite.size),
        "minimum_px": float(finite.min()),
        "maximum_px": float(finite.max()),
        "mean_px": float(finite.mean()),
        "quantiles_px": {
            "p50": float(np.quantile(finite, 0.50)),
            "p95": float(np.quantile(finite, 0.95)),
            "p99": float(np.quantile(finite, 0.99)),
        },
        "bins_px": counts,
    }


def rasterize_uv_atlas(
    primitives: list[Primitive],
    ao: np.ndarray,
) -> tuple[dict[str, Any], dict[str, np.ndarray]]:
    """Rasterize UV triangle interiors and map AO margin/world evidence."""

    height, width = ao.shape
    coverage = np.zeros((height, width), dtype=np.uint16)
    height_sum = np.zeros((height, width), dtype=np.float64)
    owner = np.full((height, width), -1, dtype=np.int16)
    mesh_coverage = np.zeros(
        (len(primitives), height, width), dtype=np.bool_
    )
    triangle_count = 0
    covered_triangle_count = 0
    degenerate_triangle_count = 0

    for primitive in primitives:
        positions_y = (
            primitive.positions[:, 1]
            + primitive.process_elevation_offset_m
        )
        for triangle in primitive.triangles:
            triangle_count += 1
            uv = primitive.texcoord_2[triangle]
            points = np.column_stack(
                [
                    uv[:, 0] * width - 0.5,
                    uv[:, 1] * height - 0.5,
                ]
            )
            patch = triangle_patch(points, width, height)
            if patch is None:
                degenerate_triangle_count += 1
                continue
            (
                minimum_x,
                maximum_x,
                minimum_y,
                maximum_y,
                bary0,
                bary1,
                bary2,
            ) = patch
            inside = (
                (bary0 >= -RASTER_EPSILON)
                & (bary1 >= -RASTER_EPSILON)
                & (bary2 >= -RASTER_EPSILON)
            )
            if not np.any(inside):
                continue
            covered_triangle_count += 1
            selection = np.s_[
                minimum_y : maximum_y + 1,
                minimum_x : maximum_x + 1,
            ]
            coverage_view = coverage[selection]
            new_pixels = inside & (coverage_view == 0)
            owner_view = owner[selection]
            owner_view[new_pixels] = primitive.mesh_id
            mesh_coverage[primitive.mesh_id][selection][inside] = True
            interpolated_height = (
                bary0 * positions_y[triangle[0]]
                + bary1 * positions_y[triangle[1]]
                + bary2 * positions_y[triangle[2]]
            )
            height_sum[selection][inside] += interpolated_height[inside]
            coverage_view[inside] += 1

    interior = coverage > 0
    signal = ao < 1.0 - NONWHITE_EPSILON
    diagnostic_v_flipped_signal = np.flipud(signal)
    signal_interior = signal & interior
    signal_margin = signal & ~interior
    mean_height = np.full((height, width), np.nan, dtype=np.float64)
    mean_height[interior] = height_sum[interior] / coverage[interior]

    distance, nearest_indices = ndimage.distance_transform_edt(
        ~interior,
        return_indices=True,
    )
    margin_y, margin_x = np.nonzero(signal_margin)
    margin_distances = distance[margin_y, margin_x]
    nearest_y = nearest_indices[0, margin_y, margin_x]
    nearest_x = nearest_indices[1, margin_y, margin_x]
    margin_mappable = (
        margin_distances <= MARGIN_WORLD_MAP_MAXIMUM_PX
    )
    mapped_margin_heights = mean_height[
        nearest_y[margin_mappable],
        nearest_x[margin_mappable],
    ]
    mapped_margin_owners = owner[
        nearest_y[margin_mappable],
        nearest_x[margin_mappable],
    ]
    interior_y, interior_x = np.nonzero(signal_interior)
    interior_heights = mean_height[interior_y, interior_x]
    interior_owners = owner[interior_y, interior_x]
    all_mapped_heights = np.concatenate(
        [interior_heights, mapped_margin_heights]
    )
    all_mapped_owners = np.concatenate(
        [interior_owners, mapped_margin_owners]
    )

    per_mesh: dict[str, Any] = {}
    for primitive in primitives:
        mesh_signal_interior = signal & mesh_coverage[primitive.mesh_id]
        mesh_heights = all_mapped_heights[
            all_mapped_owners == primitive.mesh_id
        ]
        per_mesh[primitive.node_name] = {
            "uv_triangle_interior_texels": int(
                np.count_nonzero(mesh_coverage[primitive.mesh_id])
            ),
            "nonwhite_interior_texels": int(
                np.count_nonzero(mesh_signal_interior)
            ),
            "mapped_signal_world_bands": continuous_bands(mesh_heights),
        }

    overlap = coverage > 1
    metrics = {
        "resolution": [width, height],
        "pixel_center_convention": (
            "texel center (x+0.5)/width,(y+0.5)/height"
        ),
        "triangle_count": triangle_count,
        "triangles_covering_at_least_one_texel": covered_triangle_count,
        "degenerate_or_subtexel_triangle_count": degenerate_triangle_count,
        "uv_minimum": [
            float(
                min(
                    primitive.texcoord_2[:, axis].min()
                    for primitive in primitives
                )
            )
            for axis in (0, 1)
        ],
        "uv_maximum": [
            float(
                max(
                    primitive.texcoord_2[:, axis].max()
                    for primitive in primitives
                )
            )
            for axis in (0, 1)
        ],
        "triangle_interior_texels": int(np.count_nonzero(interior)),
        "triangle_overlap_texels": int(np.count_nonzero(overlap)),
        "maximum_triangle_overlap": int(coverage.max()),
        "ao_nonwhite_texels": int(np.count_nonzero(signal)),
        "ao_nonwhite_triangle_interior_texels": int(
            np.count_nonzero(signal_interior)
        ),
        "diagnostic_only_v_flipped_nonwhite_interior_texels": int(
            np.count_nonzero(diagnostic_v_flipped_signal & interior)
        ),
        "texture_v_axis_policy": (
            "authoritative direct glTF v -> decoded image row v; matches "
            "Three GLTFLoader flipY=false; diagnostic V flip is not used "
            "to force a gate"
        ),
        "ao_nonwhite_bake_margin_texels": int(
            np.count_nonzero(signal_margin)
        ),
        "ao_nonwhite_interior_ratio_of_signal": float(
            np.count_nonzero(signal_interior)
            / max(np.count_nonzero(signal), 1)
        ),
        "bake_margin_distance_to_triangle_interior": (
            distance_distribution(margin_distances)
        ),
        "bake_margin_world_mapping": {
            "maximum_distance_px": MARGIN_WORLD_MAP_MAXIMUM_PX,
            "mapped_texels": int(np.count_nonzero(margin_mappable)),
            "unmapped_texels": int(
                margin_mappable.size - np.count_nonzero(margin_mappable)
            ),
        },
        "mapped_signal_world_bands_process_elevation_m": continuous_bands(
            all_mapped_heights
        ),
        "per_mesh": per_mesh,
        "threshold": THRESHOLDS[
            "uv_triangle_interior_nonwhite_texels_minimum"
        ],
        "passed": bool(
            np.count_nonzero(signal_interior)
            >= THRESHOLDS[
                "uv_triangle_interior_nonwhite_texels_minimum"
            ]
        ),
    }
    arrays = {
        "coverage": coverage,
        "interior": interior,
        "overlap": overlap,
        "signal": signal,
        "signal_interior": signal_interior,
        "signal_margin": signal_margin,
        "margin_distance": distance,
    }
    return metrics, arrays


def build_mips(ao: np.ndarray) -> list[np.ndarray]:
    """Build deterministic 2x2 box-filter mip levels through 1x1."""

    levels = [np.asarray(ao, dtype=np.float64)]
    while levels[-1].shape != (1, 1):
        source = levels[-1]
        height, width = source.shape
        if height % 2 or width % 2:
            raise AuditError("R2Y AO mip estimator requires power-of-two image")
        levels.append(
            source.reshape(height // 2, 2, width // 2, 2).mean(axis=(1, 3))
        )
    return levels


def sample_nearest(image: np.ndarray, uv: np.ndarray) -> np.ndarray:
    """Sample a repeat-wrapped scalar texture with nearest filtering."""

    height, width = image.shape
    wrapped = np.mod(uv, 1.0)
    x = np.floor(wrapped[:, 0] * width).astype(np.int64) % width
    y = np.floor(wrapped[:, 1] * height).astype(np.int64) % height
    return image[y, x]


def sample_bilinear(image: np.ndarray, uv: np.ndarray) -> np.ndarray:
    """Sample a repeat-wrapped scalar texture with bilinear filtering."""

    height, width = image.shape
    wrapped = np.mod(uv, 1.0)
    x = wrapped[:, 0] * width - 0.5
    y = wrapped[:, 1] * height - 0.5
    x0 = np.floor(x).astype(np.int64)
    y0 = np.floor(y).astype(np.int64)
    tx = x - x0
    ty = y - y0
    x0 %= width
    y0 %= height
    x1 = (x0 + 1) % width
    y1 = (y0 + 1) % height
    top = image[y0, x0] * (1.0 - tx) + image[y0, x1] * tx
    bottom = image[y1, x0] * (1.0 - tx) + image[y1, x1] * tx
    return top * (1.0 - ty) + bottom * ty


def sample_trilinear(
    mips: list[np.ndarray],
    uv: np.ndarray,
    lod: np.ndarray,
) -> np.ndarray:
    """Sample deterministic LINEAR_MIPMAP_LINEAR estimates."""

    clamped = np.clip(lod, 0.0, float(len(mips) - 1))
    low = np.floor(clamped).astype(np.int64)
    high = np.minimum(low + 1, len(mips) - 1)
    fraction = clamped - low
    result = np.empty(uv.shape[0], dtype=np.float64)
    for low_level in np.unique(low):
        mask = low == low_level
        low_values = sample_bilinear(mips[int(low_level)], uv[mask])
        high_level_values = high[mask]
        high_values = np.empty_like(low_values)
        for high_level in np.unique(high_level_values):
            high_mask = high_level_values == high_level
            high_values[high_mask] = sample_bilinear(
                mips[int(high_level)], uv[mask][high_mask]
            )
        result[mask] = (
            low_values * (1.0 - fraction[mask])
            + high_values * fraction[mask]
        )
    return result


def scalar_sample_metrics(
    values: np.ndarray,
    canvas_pixel_count: int,
    visible_pixel_count: int,
) -> dict[str, Any]:
    """Summarize one AO sampling estimator."""

    array = np.asarray(values, dtype=np.float64)
    affected = array < 1.0 - NONWHITE_EPSILON
    affected_values = array[affected]
    drop = 1.0 - affected_values
    return {
        "visible_sample_count": int(array.size),
        "minimum_r": float(array.min()) if array.size else None,
        "maximum_r": float(array.max()) if array.size else None,
        "mean_r": float(array.mean()) if array.size else None,
        "nonwhite_pixels": int(np.count_nonzero(affected)),
        "nonwhite_ratio_of_canvas": float(np.count_nonzero(affected))
        / max(canvas_pixel_count, 1),
        "nonwhite_ratio_of_visible_geometry": float(
            np.count_nonzero(affected)
        )
        / max(visible_pixel_count, 1),
        "affected_pixel_mean_ao_drop": (
            float(drop.mean()) if drop.size else 0.0
        ),
        "affected_pixel_maximum_ao_drop": (
            float(drop.max()) if drop.size else 0.0
        ),
    }


def rasterize_view(
    primitives: list[Primitive],
    composition: dict[str, Any],
    width: int,
    height: int,
    mips: list[np.ndarray],
) -> tuple[dict[str, Any], dict[str, np.ndarray]]:
    """Rasterize one camera with culling, z-buffer and perspective UV."""

    view, projection = camera_matrices(composition)
    z_buffer = np.full((height, width), np.inf, dtype=np.float64)
    owner = np.full((height, width), -1, dtype=np.int16)
    uv_buffer = np.full((height, width, 2), np.nan, dtype=np.float64)
    elevation_buffer = np.full(
        (height, width), np.nan, dtype=np.float64
    )
    lod_buffer = np.full((height, width), np.nan, dtype=np.float64)
    triangle_counts = {
        "total": 0,
        "front_facing": 0,
        "backface_culled": 0,
        "outside_frustum": 0,
        "mixed_nonpositive_w": 0,
        "degenerate": 0,
        "rasterized": 0,
    }
    texture_height, texture_width = mips[0].shape

    for primitive in primitives:
        positions = primitive.positions
        homogeneous = np.concatenate(
            [positions, np.ones((positions.shape[0], 1))], axis=1
        )
        clip_all = (projection @ view @ homogeneous.T).T
        for triangle in primitive.triangles:
            triangle_counts["total"] += 1
            clip = clip_all[triangle]
            if not np.all(np.isfinite(clip)):
                triangle_counts["outside_frustum"] += 1
                continue
            positive_w = clip[:, 3] > 1.0e-12
            if not np.all(positive_w):
                if np.any(positive_w):
                    triangle_counts["mixed_nonpositive_w"] += 1
                    raise AuditError(
                        "A triangle crosses the camera w=0 plane; "
                        "homogeneous clipping is required"
                    )
                triangle_counts["outside_frustum"] += 1
                continue
            if (
                np.all(clip[:, 0] < -clip[:, 3])
                or np.all(clip[:, 0] > clip[:, 3])
                or np.all(clip[:, 1] < -clip[:, 3])
                or np.all(clip[:, 1] > clip[:, 3])
                or np.all(clip[:, 2] < -clip[:, 3])
                or np.all(clip[:, 2] > clip[:, 3])
            ):
                triangle_counts["outside_frustum"] += 1
                continue
            ndc = clip[:, :3] / clip[:, 3:4]
            area_ndc = (
                (ndc[1, 0] - ndc[0, 0])
                * (ndc[2, 1] - ndc[0, 1])
                - (ndc[1, 1] - ndc[0, 1])
                * (ndc[2, 0] - ndc[0, 0])
            )
            if abs(float(area_ndc)) <= 1.0e-15:
                triangle_counts["degenerate"] += 1
                continue
            if area_ndc * primitive.front_face_sign <= 0.0:
                triangle_counts["backface_culled"] += 1
                continue
            triangle_counts["front_facing"] += 1
            points = np.column_stack(
                [
                    (ndc[:, 0] + 1.0) * 0.5 * width - 0.5,
                    (1.0 - ndc[:, 1]) * 0.5 * height - 0.5,
                ]
            )
            patch = triangle_patch(points, width, height)
            if patch is None:
                triangle_counts["degenerate"] += 1
                continue
            (
                minimum_x,
                maximum_x,
                minimum_y,
                maximum_y,
                bary0,
                bary1,
                bary2,
            ) = patch
            inside = (
                (bary0 >= -RASTER_EPSILON)
                & (bary1 >= -RASTER_EPSILON)
                & (bary2 >= -RASTER_EPSILON)
            )
            depth = (
                bary0 * ndc[0, 2]
                + bary1 * ndc[1, 2]
                + bary2 * ndc[2, 2]
            )
            inside &= (depth >= -1.0) & (depth <= 1.0)
            if not np.any(inside):
                continue
            selection = np.s_[
                minimum_y : maximum_y + 1,
                minimum_x : maximum_x + 1,
            ]
            update = inside & (depth < z_buffer[selection])
            if not np.any(update):
                continue
            triangle_counts["rasterized"] += 1

            inv_w = 1.0 / clip[:, 3]
            denominator = (
                bary0 * inv_w[0]
                + bary1 * inv_w[1]
                + bary2 * inv_w[2]
            )
            uv_vertices = primitive.texcoord_2[triangle]
            numerator_u = (
                bary0 * uv_vertices[0, 0] * inv_w[0]
                + bary1 * uv_vertices[1, 0] * inv_w[1]
                + bary2 * uv_vertices[2, 0] * inv_w[2]
            )
            numerator_v = (
                bary0 * uv_vertices[0, 1] * inv_w[0]
                + bary1 * uv_vertices[1, 1] * inv_w[1]
                + bary2 * uv_vertices[2, 1] * inv_w[2]
            )
            interpolated_u = numerator_u / denominator
            interpolated_v = numerator_v / denominator

            process_height = (
                primitive.positions[triangle, 1]
                + primitive.process_elevation_offset_m
            )
            numerator_height = (
                bary0 * process_height[0] * inv_w[0]
                + bary1 * process_height[1] * inv_w[1]
                + bary2 * process_height[2] * inv_w[2]
            )
            interpolated_height = numerator_height / denominator

            x0, y0 = points[0]
            x1, y1 = points[1]
            x2, y2 = points[2]
            bary_denominator = (y1 - y2) * (x0 - x2)
            bary_denominator += (x2 - x1) * (y0 - y2)
            grad_x = np.array(
                [
                    (y1 - y2) / bary_denominator,
                    (y2 - y0) / bary_denominator,
                    (y0 - y1) / bary_denominator,
                ]
            )
            grad_y = np.array(
                [
                    (x2 - x1) / bary_denominator,
                    (x0 - x2) / bary_denominator,
                    (x1 - x0) / bary_denominator,
                ]
            )
            denominator_dx = float(np.dot(grad_x, inv_w))
            denominator_dy = float(np.dot(grad_y, inv_w))
            u_over_w = uv_vertices[:, 0] * inv_w
            v_over_w = uv_vertices[:, 1] * inv_w
            numerator_u_dx = float(np.dot(grad_x, u_over_w))
            numerator_u_dy = float(np.dot(grad_y, u_over_w))
            numerator_v_dx = float(np.dot(grad_x, v_over_w))
            numerator_v_dy = float(np.dot(grad_y, v_over_w))
            denominator_squared = denominator * denominator
            du_dx = (
                numerator_u_dx * denominator
                - numerator_u * denominator_dx
            ) / denominator_squared
            du_dy = (
                numerator_u_dy * denominator
                - numerator_u * denominator_dy
            ) / denominator_squared
            dv_dx = (
                numerator_v_dx * denominator
                - numerator_v * denominator_dx
            ) / denominator_squared
            dv_dy = (
                numerator_v_dy * denominator
                - numerator_v * denominator_dy
            ) / denominator_squared
            rho_x = np.hypot(
                du_dx * texture_width,
                dv_dx * texture_height,
            )
            rho_y = np.hypot(
                du_dy * texture_width,
                dv_dy * texture_height,
            )
            rho = np.maximum(rho_x, rho_y)
            lod = np.log2(np.maximum(rho, 1.0e-12))
            lod = np.clip(lod, 0.0, float(len(mips) - 1))

            z_buffer[selection][update] = depth[update]
            owner[selection][update] = primitive.mesh_id
            uv_buffer[selection][..., 0][update] = interpolated_u[update]
            uv_buffer[selection][..., 1][update] = interpolated_v[update]
            elevation_buffer[selection][update] = interpolated_height[update]
            lod_buffer[selection][update] = lod[update]

    visible = owner >= 0
    visible_count = int(np.count_nonzero(visible))
    if visible_count == 0:
        raise AuditError("CPU raster produced no visible pixels")
    visible_uv = uv_buffer[visible]
    visible_lod = lod_buffer[visible]
    nearest = sample_nearest(mips[0], visible_uv)
    bilinear = sample_bilinear(mips[0], visible_uv)
    trilinear = sample_trilinear(mips, visible_uv, visible_lod)
    diagnostic_v_flipped_uv = visible_uv.copy()
    diagnostic_v_flipped_uv[:, 1] = 1.0 - diagnostic_v_flipped_uv[:, 1]
    diagnostic_v_flipped_trilinear = sample_trilinear(
        mips,
        diagnostic_v_flipped_uv,
        visible_lod,
    )
    canvas_count = width * height
    sampling = {
        "nearest_level_0": scalar_sample_metrics(
            nearest, canvas_count, visible_count
        ),
        "bilinear_level_0": scalar_sample_metrics(
            bilinear, canvas_count, visible_count
        ),
        "trilinear_mip_estimate": scalar_sample_metrics(
            trilinear, canvas_count, visible_count
        ),
        "diagnostic_only_v_flipped_trilinear_mip_estimate": (
            scalar_sample_metrics(
                diagnostic_v_flipped_trilinear,
                canvas_count,
                visible_count,
            )
        ),
    }
    trilinear_image = np.full((height, width), np.nan, dtype=np.float64)
    trilinear_image[visible] = trilinear
    affected = visible & (
        trilinear_image < 1.0 - NONWHITE_EPSILON
    )

    per_mesh: dict[str, Any] = {}
    for primitive in primitives:
        mesh_mask = owner == primitive.mesh_id
        mesh_values = trilinear_image[mesh_mask]
        per_mesh[primitive.node_name] = {
            "visible_pixels": int(np.count_nonzero(mesh_mask)),
            "trilinear_mip_estimate": scalar_sample_metrics(
                mesh_values,
                canvas_count,
                int(np.count_nonzero(mesh_mask)),
            ),
            "affected_world_bands_process_elevation_m": continuous_bands(
                elevation_buffer[mesh_mask & affected]
            ),
        }

    mip = sampling["trilinear_mip_estimate"]
    checks = {
        "visible_nonwhite_pixels": (
            mip["nonwhite_pixels"]
            >= THRESHOLDS["view_mip_nonwhite_pixels_minimum"]
        ),
        "visible_nonwhite_ratio": (
            mip["nonwhite_ratio_of_canvas"]
            >= THRESHOLDS["view_mip_nonwhite_ratio_minimum"]
        ),
        "minimum_r": (
            mip["minimum_r"]
            <= THRESHOLDS["view_mip_minimum_r_maximum"]
        ),
        "affected_pixel_mean_ao_drop": (
            mip["affected_pixel_mean_ao_drop"]
            >= THRESHOLDS["affected_pixel_mean_ao_drop_minimum"]
        ),
    }
    metrics = {
        "view": composition.get("view"),
        "raster_resolution": [width, height],
        "canvas_pixel_count": canvas_count,
        "front_face_policy": (
            "glTF CCW corrected for negative world determinant; "
            "default material FrontSide"
        ),
        "depth_policy": "NDC z-buffer, lower depth wins",
        "uv_policy": "perspective-correct interpolation using 1/clip.w",
        "texture_v_axis_policy": (
            "authoritative direct glTF v -> decoded image row v for Three "
            "GLTFLoader flipY=false; V-flipped result is diagnostic only"
        ),
        "lod_policy": (
            "analytic quotient-rule dUV/dscreen; rho=max(dx,dy); "
            "log2 rho; deterministic 2x2 box mips"
        ),
        "triangle_counts": triangle_counts,
        "visible_geometry_pixels": visible_count,
        "visible_geometry_ratio": visible_count / canvas_count,
        "lod": {
            "minimum": float(visible_lod.min()),
            "maximum": float(visible_lod.max()),
            "mean": float(visible_lod.mean()),
            "quantiles": {
                "p05": float(np.quantile(visible_lod, 0.05)),
                "p50": float(np.quantile(visible_lod, 0.50)),
                "p95": float(np.quantile(visible_lod, 0.95)),
            },
        },
        "sampling": sampling,
        "affected_world_bands_process_elevation_m": continuous_bands(
            elevation_buffer[affected]
        ),
        "per_mesh": per_mesh,
        "thresholds": {
            key: THRESHOLDS[key]
            for key in (
                "view_mip_nonwhite_pixels_minimum",
                "view_mip_nonwhite_ratio_minimum",
                "view_mip_minimum_r_maximum",
                "affected_pixel_mean_ao_drop_minimum",
            )
        },
        "checks": checks,
        "passed": all(checks.values()),
    }
    arrays = {
        "visible": visible,
        "owner": owner,
        "lod": lod_buffer,
        "trilinear": trilinear_image,
        "affected": affected,
        "elevation": elevation_buffer,
    }
    return metrics, arrays


def save_png(path: Path, rgb: np.ndarray) -> dict[str, Any]:
    """Save a deterministic RGB PNG and return its artifact record."""

    path.parent.mkdir(parents=True, exist_ok=True)
    Image.fromarray(np.asarray(rgb, dtype=np.uint8), mode="RGB").save(
        path,
        format="PNG",
        optimize=False,
        compress_level=9,
    )
    return {
        "path": relative_path(path),
        "bytes": path.stat().st_size,
        "sha256": sha256_file(path),
        "width": int(rgb.shape[1]),
        "height": int(rgb.shape[0]),
    }


def atlas_heatmaps(
    preview_dir: Path,
    ao: np.ndarray,
    arrays: dict[str, np.ndarray],
) -> list[dict[str, Any]]:
    """Write atlas AO intensity and UV/margin classification heatmaps."""

    drop = 1.0 - ao
    maximum = max(float(drop.max()), 1.0e-12)
    normalized = np.clip(drop / maximum, 0.0, 1.0)
    signal_rgb = np.zeros((*ao.shape, 3), dtype=np.uint8)
    signal_rgb[..., 0] = np.round(normalized * 255.0).astype(np.uint8)
    signal_rgb[..., 1] = np.round(normalized * 120.0).astype(np.uint8)
    signal_rgb[..., 2] = np.where(arrays["signal"], 24, 12).astype(np.uint8)

    classes = np.full((*ao.shape, 3), [16, 18, 22], dtype=np.uint8)
    classes[arrays["interior"]] = [45, 90, 160]
    classes[arrays["overlap"]] = [125, 70, 190]
    classes[arrays["signal_margin"]] = [255, 180, 0]
    classes[arrays["signal_interior"]] = [235, 45, 38]
    return [
        save_png(preview_dir / "atlas_ao_signal_heatmap.png", signal_rgb),
        save_png(
            preview_dir / "atlas_uv_interior_margin_classes.png",
            classes,
        ),
    ]


def view_heatmaps(
    preview_dir: Path,
    view_name: str,
    arrays: dict[str, np.ndarray],
    mip_count: int,
) -> list[dict[str, Any]]:
    """Write visible AO-hit and LOD heatmaps for one representative view."""

    visible = arrays["visible"]
    affected = arrays["affected"]
    trilinear = arrays["trilinear"]
    owner = arrays["owner"]
    colors = np.asarray(
        [
            [75, 110, 135],
            [85, 125, 150],
            [95, 135, 160],
            [105, 145, 170],
            [115, 155, 180],
        ],
        dtype=np.uint8,
    )
    hit_rgb = np.full((*visible.shape, 3), [15, 17, 20], dtype=np.uint8)
    for mesh_id, color in enumerate(colors):
        hit_rgb[owner == mesh_id] = color
    drop = np.zeros_like(trilinear)
    drop[visible] = 1.0 - trilinear[visible]
    maximum = max(float(drop[affected].max()) if np.any(affected) else 0.0, 1e-12)
    intensity = np.clip(drop / maximum, 0.0, 1.0)
    hit_rgb[..., 0][affected] = 255
    hit_rgb[..., 1][affected] = np.round(
        220.0 * (1.0 - intensity[affected])
    ).astype(np.uint8)
    hit_rgb[..., 2][affected] = 20

    lod = arrays["lod"]
    lod_rgb = np.full((*visible.shape, 3), [15, 17, 20], dtype=np.uint8)
    normalized = np.zeros_like(lod)
    normalized[visible] = np.clip(
        lod[visible] / max(float(mip_count - 1), 1.0), 0.0, 1.0
    )
    lod_rgb[..., 0][visible] = np.round(
        255.0 * normalized[visible]
    ).astype(np.uint8)
    lod_rgb[..., 1][visible] = np.round(
        255.0 * (1.0 - np.abs(normalized[visible] * 2.0 - 1.0))
    ).astype(np.uint8)
    lod_rgb[..., 2][visible] = np.round(
        255.0 * (1.0 - normalized[visible])
    ).astype(np.uint8)
    return [
        save_png(preview_dir / f"{view_name}_mip_hit_heatmap.png", hit_rgb),
        save_png(preview_dir / f"{view_name}_lod_heatmap.png", lod_rgb),
    ]


def runtime_u8_evidence(runtime: dict[str, Any]) -> dict[str, Any]:
    """Extract the locked R2X final 8-bit pair evidence."""

    pairs = runtime.get("pairs") or {}
    result: dict[str, Any] = {}
    for view_name in ("global", "detail"):
        pair = pairs.get(view_name)
        if not isinstance(pair, dict):
            raise AuditError(f"Missing R2X final pair: {view_name}")
        changed = int(pair.get("changed_pixels", -1))
        ratio = float(pair.get("changed_ratio", -1.0))
        mean_changed = float(
            pair.get("mean_abs_diff_changed_rgb_u8", -1.0)
        )
        checks = {
            "changed_pixels": (
                changed
                >= THRESHOLDS["final_u8_changed_pixels_minimum"]
            ),
            "changed_ratio": (
                ratio
                >= THRESHOLDS["view_mip_nonwhite_ratio_minimum"]
            ),
            "mean_abs_diff_changed_rgb_u8": (
                mean_changed
                >= THRESHOLDS["final_u8_mean_abs_diff_rgb_minimum"]
            ),
        }
        result[view_name] = {
            "source": "locked_r2x_representative_report",
            "width": int(pair.get("width", 0)),
            "height": int(pair.get("height", 0)),
            "pixel_count": int(pair.get("pixel_count", 0)),
            "changed_pixels": changed,
            "changed_ratio": ratio,
            "mean_abs_diff_all_rgb_u8": float(
                pair.get("mean_abs_diff_all_rgb_u8", 0.0)
            ),
            "mean_abs_diff_changed_rgb_u8": mean_changed,
            "max_abs_diff_u8": float(pair.get("max_abs_diff_u8", 0.0)),
            "checks": checks,
            "passed": all(checks.values()),
        }
    return result


def classify_ao(
    atlas: dict[str, Any],
    views: dict[str, dict[str, Any]],
    final_u8: dict[str, Any],
) -> dict[str, Any]:
    """Apply the pre-registered priority without inventing WebGL evidence."""

    cpu_any_hit = (
        atlas["ao_nonwhite_triangle_interior_texels"] > 0
        and all(
            metrics["sampling"]["trilinear_mip_estimate"][
                "nonwhite_pixels"
            ]
            > 0
            for metrics in views.values()
        )
    )
    cpu_gate = bool(
        atlas["passed"] and all(metrics["passed"] for metrics in views.values())
    )
    final_u8_passed = all(item["passed"] for item in final_u8.values())
    if not cpu_any_hit:
        classification = "uv_or_camera_miss"
        classification_status = "classified_from_cpu_priority_1"
        remaining: list[str] = []
    else:
        classification = None
        classification_status = (
            "deferred_pending_webgl_synthetic_black_and_float_evidence"
        )
        remaining = [
            "shader_uniform_or_texture_consumption_failure",
            "subquantization_visibility_failure",
            "ao_signal_too_weak",
            "ao_signal_visible_candidate_only",
        ]
    return {
        "priority_contract": [
            "uv_or_camera_miss",
            "shader_uniform_or_texture_consumption_failure",
            "subquantization_visibility_failure",
            "ao_signal_too_weak",
            "ao_signal_visible_candidate_only",
        ],
        "classification": classification,
        "classification_status": classification_status,
        "remaining_classes_requiring_webgl_evidence": remaining,
        "evidence": {
            "cpu_any_signal_hit_each_view": cpu_any_hit,
            "cpu_preregistered_gate_passed": cpu_gate,
            "webgl_synthetic_black_ao": {
                "observed": False,
                "changed_pixels": None,
                "reason": (
                    "Offline CPU audit cannot establish shader/uniform/"
                    "texture consumption."
                ),
            },
            "webgl_float_linear_off_on": {
                "observed": False,
                "maximum_absolute_difference": None,
                "reason": (
                    "Locked R2X report contains final PNG pairs, not a "
                    "floating-point framebuffer probe."
                ),
            },
            "final_u8_off_on": {
                "observed": True,
                "all_views_passed": final_u8_passed,
            },
        },
        "fail_closed": classification != "ao_signal_visible_candidate_only",
    }


def artifact_record(path: Path) -> dict[str, Any]:
    """Return a traceable artifact record."""

    return {
        "path": relative_path(path),
        "exists": path.is_file(),
        "bytes": path.stat().st_size if path.is_file() else None,
        "sha256": sha256_file(path) if path.is_file() else None,
    }


def run_audit(output: Path, preview_dir: Path) -> dict[str, Any]:
    """Run the complete immutable R2Y AO/UV audit."""

    locks_before, locks_before_passed = inspect_input_locks()
    if not locks_before_passed:
        raise AuditError("Pre-registered input lock mismatch")
    runtime = load_json_object(RUNTIME_REPORT)
    document, binary, glb_chunks = read_glb(MODEL)
    primitives = load_primitives(document, binary)
    embedded_payload, ao_binding = embedded_ao_payload(document, binary)
    external_payload = AO_PNG.read_bytes()
    if embedded_payload != external_payload:
        raise AuditError("Embedded AO PNG differs from locked external AO")
    ao, ao_decode = decode_ao(embedded_payload)
    if ao.shape != (1024, 1024):
        raise AuditError(f"AO resolution is not locked 1K: {ao.shape}")
    views, raster_width, raster_height = locked_views(runtime)

    atlas_metrics, atlas_arrays = rasterize_uv_atlas(primitives, ao)
    mips = build_mips(ao)
    projection: dict[str, Any] = {}
    view_metrics: dict[str, Any] = {}
    view_arrays: dict[str, dict[str, np.ndarray]] = {}
    for view_name in ("global", "detail"):
        projection[view_name] = projection_metrics(
            primitives, views[view_name]
        )
        metrics, arrays = rasterize_view(
            primitives,
            views[view_name],
            raster_width,
            raster_height,
            mips,
        )
        view_metrics[view_name] = metrics
        view_arrays[view_name] = arrays

    heatmaps = atlas_heatmaps(preview_dir, ao, atlas_arrays)
    for view_name in ("global", "detail"):
        heatmaps.extend(
            view_heatmaps(
                preview_dir,
                view_name,
                view_arrays[view_name],
                len(mips),
            )
        )
    final_u8 = runtime_u8_evidence(runtime)
    classification = classify_ao(
        atlas_metrics,
        view_metrics,
        final_u8,
    )
    locks_after, locks_after_passed = inspect_input_locks()
    locks_unchanged = locks_before == locks_after

    primitive_records = []
    for primitive in primitives:
        primitive_records.append(
            {
                "mesh_id": primitive.mesh_id,
                "node": primitive.node_name,
                "mesh": primitive.mesh_name,
                "material_index": primitive.material_index,
                "vertex_count": int(primitive.positions.shape[0]),
                "triangle_count": int(primitive.triangles.shape[0]),
                "accessors": primitive.accessor_indices,
                "world_bounds": {
                    "minimum": [
                        float(value)
                        for value in primitive.positions.min(axis=0)
                    ],
                    "maximum": [
                        float(value)
                        for value in primitive.positions.max(axis=0)
                    ],
                },
                "process_elevation_offset_m": (
                    primitive.process_elevation_offset_m
                ),
                "process_elevation_range_m": [
                    float(
                        primitive.positions[:, 1].min()
                        + primitive.process_elevation_offset_m
                    ),
                    float(
                        primitive.positions[:, 1].max()
                        + primitive.process_elevation_offset_m
                    ),
                ],
                "uv2_bounds": {
                    "minimum": [
                        float(value)
                        for value in primitive.texcoord_2.min(axis=0)
                    ],
                    "maximum": [
                        float(value)
                        for value in primitive.texcoord_2.max(axis=0)
                    ],
                },
            }
        )

    projection_passed = all(
        item["passed"] for item in projection.values()
    )
    cpu_gate_passed = bool(
        atlas_metrics["passed"]
        and all(item["passed"] for item in view_metrics.values())
        and projection_passed
    )
    final_u8_passed = all(item["passed"] for item in final_u8.values())
    diagnostic_inputs_unchanged = (
        locks_before_passed and locks_after_passed and locks_unchanged
    )
    report = {
        "schema_version": "bf3d.r2y.ao_uv_hit_raster_audit.v1",
        "requirement_id": REQUIREMENT_ID,
        "stage_id": STAGE_ID,
        "generated_at": now_iso(),
        "scope": (
            "offline_cpu_uv_ao_raster_diagnostic_not_webgl_or_production"
        ),
        "algorithm": {
            "version": "r2y_cpu_raster_v1",
            "implementation": artifact_record(Path(__file__).resolve()),
            "glb_parser": (
                "strict GLB 2.0 JSON/BIN; accessor stride/normalization; "
                "scene TRS/matrix instancing"
            ),
            "raster": (
                "pixel centers, glTF front-face culling, NDC z-buffer, "
                "perspective-correct TEXCOORD_2"
            ),
            "sampler": (
                "REPEAT wrap; nearest level0, bilinear level0, "
                "LINEAR_MIPMAP_LINEAR estimate; direct glTF v to decoded "
                "image row for Three GLTFLoader flipY=false"
            ),
            "world_band_bin_m": WORLD_BAND_BIN_M,
            "runtime": {
                "python": platform.python_version(),
                "numpy": np.__version__,
                "pillow": Image.__version__,
                "scipy": scipy_version,
            },
        },
        "input_locks_before": locks_before,
        "input_locks_after": locks_after,
        "input_locks": {
            "before_passed": locks_before_passed,
            "after_passed": locks_after_passed,
            "unchanged_during_audit": locks_unchanged,
            "passed": diagnostic_inputs_unchanged,
        },
        "glb": {
            "artifact": artifact_record(MODEL),
            "chunks": glb_chunks,
            "counts": {
                "scenes": len(document.get("scenes", [])),
                "nodes": len(document.get("nodes", [])),
                "meshes": len(document.get("meshes", [])),
                "materials": len(document.get("materials", [])),
                "textures": len(document.get("textures", [])),
                "images": len(document.get("images", [])),
                "accessors": len(document.get("accessors", [])),
                "buffer_views": len(document.get("bufferViews", [])),
            },
            "primitives": primitive_records,
            "ao_binding": ao_binding,
        },
        "ao_texture": {
            "external_artifact": artifact_record(AO_PNG),
            "embedded_bytes": len(embedded_payload),
            "embedded_sha256": sha256_bytes(embedded_payload),
            "embedded_matches_external_byte_for_byte": True,
            "decoded": ao_decode,
            "mip_levels": [
                {
                    "level": level,
                    "width": int(image.shape[1]),
                    "height": int(image.shape[0]),
                    "minimum_r": float(image.min()),
                    "maximum_r": float(image.max()),
                    "mean_r": float(image.mean()),
                }
                for level, image in enumerate(mips)
            ],
        },
        "uv_atlas": atlas_metrics,
        "projection_cross_check": projection,
        "representative_views": view_metrics,
        "webgl_classification_inputs": {
            "cpu_synthetic_black_potential": {
                view_name: {
                    "changed_pixels_if_consumed": metrics[
                        "visible_geometry_pixels"
                    ],
                    "threshold": THRESHOLDS[
                        "synthetic_black_ao_changed_pixels_minimum"
                    ],
                    "passed_as_cpu_potential_only": (
                        metrics["visible_geometry_pixels"]
                        >= THRESHOLDS[
                            "synthetic_black_ao_changed_pixels_minimum"
                        ]
                    ),
                }
                for view_name, metrics in view_metrics.items()
            },
            "cpu_float_ao_drop_estimate": {
                view_name: {
                    "maximum_absolute_difference_estimate": metrics[
                        "sampling"
                    ]["trilinear_mip_estimate"][
                        "affected_pixel_maximum_ao_drop"
                    ],
                    "threshold_exclusive": THRESHOLDS[
                        "float_linear_max_abs_diff_minimum_exclusive"
                    ],
                    "passed_as_cpu_estimate_only": (
                        metrics["sampling"]["trilinear_mip_estimate"][
                            "affected_pixel_maximum_ao_drop"
                        ]
                        > THRESHOLDS[
                            "float_linear_max_abs_diff_minimum_exclusive"
                        ]
                    ),
                }
                for view_name, metrics in view_metrics.items()
            },
            "webgl_synthetic_black_observation": None,
            "webgl_float_linear_observation": None,
            "final_u8_r2x_observation": final_u8,
        },
        "classification": classification,
        "thresholds": THRESHOLDS,
        "checks": {
            "input_locks_unchanged": diagnostic_inputs_unchanged,
            "embedded_ao_matches_external": True,
            "uv_triangle_interior_nonwhite_texels": atlas_metrics["passed"],
            "global_projection_cross_check": projection["global"]["passed"],
            "detail_projection_cross_check": projection["detail"]["passed"],
            "global_cpu_mip_visibility": view_metrics["global"]["passed"],
            "detail_cpu_mip_visibility": view_metrics["detail"]["passed"],
            "cpu_preregistered_gate_passed": cpu_gate_passed,
            "webgl_synthetic_black_gate_observed": False,
            "webgl_float_linear_gate_observed": False,
            "final_u8_gate_passed": final_u8_passed,
        },
        "audit_completed": True,
        "cpu_preregistered_gate_passed": cpu_gate_passed,
        "full_ao_visibility_gate_passed": False,
        "status": (
            "cpu_gate_passed_webgl_evidence_pending_fail_closed"
            if cpu_gate_passed
            else "cpu_gate_failed_closed"
        ),
        "artifacts": {
            "report": relative_path(output),
            "heatmaps": heatmaps,
        },
        "limitations": [
            (
                "CPU mip filtering is a deterministic estimate; GPU "
                "derivatives, driver mip generation and anisotropy can differ."
            ),
            (
                "CPU synthetic-black potential is geometry coverage only; "
                "it is not evidence that a Three.js shader consumed AO."
            ),
            (
                "The locked R2X report contains final 8-bit PNG pairs but no "
                "floating-point framebuffer or synthetic-black liveness pair."
            ),
            (
                "This diagnostic cannot approve AO 2K, P50/P60, Golden, "
                "formal GLB replacement, production integration or release."
            ),
        ],
        "approval_stop_lines": {
            "asset_mutation_allowed": False,
            "representative_visual_approved": False,
            "full_matrix_allowed": False,
            "ao_rebake_allowed": False,
            "ao_2k_approved": False,
            "p50_approved": False,
            "p60_approved": False,
            "production_integration_allowed": False,
            "next_release_stage_allowed": False,
        },
    }
    return report


def main() -> int:
    """Run the audit, always preserving fail-closed stop lines."""

    args = parse_args()
    try:
        output = ensure_owned_output(args.output)
        preview_dir = ensure_owned_output(args.preview_dir)
        report = run_audit(output, preview_dir)
        write_json(output, report)
        summary = {
            "audit_completed": True,
            "status": report["status"],
            "cpu_preregistered_gate_passed": report[
                "cpu_preregistered_gate_passed"
            ],
            "classification": report["classification"]["classification"],
            "report": str(output),
            "heatmap_count": len(report["artifacts"]["heatmaps"]),
        }
        print(json.dumps(summary, ensure_ascii=False))
        return 0
    except Exception as exc:  # fail-closed evidence must survive diagnostics
        output = ensure_owned_output(args.output)
        failure = {
            "schema_version": "bf3d.r2y.ao_uv_hit_raster_audit.v1",
            "requirement_id": REQUIREMENT_ID,
            "stage_id": STAGE_ID,
            "generated_at": now_iso(),
            "scope": (
                "offline_cpu_uv_ao_raster_diagnostic_not_webgl_or_production"
            ),
            "audit_completed": False,
            "status": "audit_execution_failed_closed",
            "error": {
                "type": type(exc).__name__,
                "message": str(exc),
            },
            "approval_stop_lines": {
                "asset_mutation_allowed": False,
                "representative_visual_approved": False,
                "full_matrix_allowed": False,
                "ao_rebake_allowed": False,
                "ao_2k_approved": False,
                "p50_approved": False,
                "p60_approved": False,
                "production_integration_allowed": False,
                "next_release_stage_allowed": False,
            },
        }
        write_json(output, failure)
        print(json.dumps(failure, ensure_ascii=False), file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
