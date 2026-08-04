"""Fail-closed V5-payload repacker for the WEB-60 R2X 1K AO smoke GLB.

The locked V5 material-review GLB is the only geometry and PBR payload
baseline.  The older R2X smoke candidate contributes only:

* one TEXCOORD_2 sequence for each of the five R2J shell primitives; and
* the embedded 1K AO PNG plus its texture binding semantics.

No candidate BaseColor, Normal, ORM, material, node, mesh, tangent, or other
attribute payload is copied.  In particular, the candidate clamp sampler is
not copied: the appended AO texture reuses locked V5 sampler 0.  The output
remains a smoke artifact and grants no 2K/P50/P60/production/next-stage
approval.
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import math
import os
import re
import shutil
import struct
import subprocess
import sys
import traceback
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator


ROOT = Path(__file__).resolve().parents[1]
STAGE = (
    ROOT
    / "PT"
    / "高炉3D模型"
    / "work"
    / "WEB_60_20260720_R2X_R2J_AO_REBAKE_CANDIDATE"
)
GLB_DIR = STAGE / "glb"
REPORT_DIR = STAGE / "reports"

V5_GLB = (
    ROOT
    / "高炉前端数据"
    / "models"
    / "gl02_blast_furnace_material_review.v5.glb"
)
R2X_SOURCE_GLB = (
    GLB_DIR / "gl02_blast_furnace_material_review.r2x-ao-smoke1k.glb"
)
AO_PNG = STAGE / "textures" / "GL02_R2J_LOCAL_CONTACT_AO_1K.png"
OUTPUT_GLB = (
    GLB_DIR
    / "gl02_blast_furnace_material_review.r2x-ao-smoke1k.v5payload.glb"
)
TEMP_GLB = OUTPUT_GLB.with_name(OUTPUT_GLB.name + ".building")
REPORT = REPORT_DIR / "r2x_ao_v5_payload_repack_report.json"
KHRONOS_REPORT = (
    REPORT_DIR / "khronos_gltf_validator_r2x_ao_v5payload.json"
)
CONTRACT = STAGE / "WEB-60_R2X_阶段预注册合同.md"

KHRONOS_MODULE = (
    ROOT
    / "PT"
    / "高炉3D模型"
    / "work"
    / "WEB_60_20260720_R2U_SECTION_CAP_CONTROLLED_V4"
    / "vendor"
    / "gltf-validator-runtime"
    / "node_modules"
    / "gltf-validator"
)

STAGE_ID = "WEB_60_20260720_R2X_R2J_AO_REBAKE_CANDIDATE"
REQUIREMENT_ID = "REQ-BF3D-R2X-R2J-AO-REBAKE-CONSUMPTION-20260720"
SCHEMA_VERSION = "bf3d.r2x.r2j_ao_v5_payload_repack.v1"
EXPECTED_VALIDATOR_VERSION = "2.0.0-dev.3.10"
AO_IMAGE_NAME = "GL02_R2J_LOCAL_CONTACT_AO_1K"

TARGETS = (
    "R2J_ASM_GL02_FURNACE_HEARTH_SHELL_65MM_E",
    "R2J_ASM_GL02_FURNACE_BOSH_SHELL_55MM_E",
    "R2J_ASM_GL02_FURNACE_BELLY_SHELL_55MM_E",
    "R2J_ASM_GL02_FURNACE_SHAFT_SHELL_45MM_E",
    "R2J_ASM_GL02_FURNACE_THROAT_SHELL_45MM_E",
)
PROTECTED_SEMANTICS = (
    "POSITION",
    "NORMAL",
    "TANGENT",
    "TEXCOORD_0",
    "TEXCOORD_1",
)

LOCKS: dict[str, tuple[Path, str]] = {
    "v5_blend": (
        ROOT
        / "高炉前端数据"
        / "models"
        / "gl02_blast_furnace_review.v5.blend",
        "3e6df5fb02d3734d14923d4432739a5918ac8249d6a3c8ad1415395429b27e3a",
    ),
    "v5_unified_glb": (
        ROOT
        / "高炉前端数据"
        / "models"
        / "gl02_blast_furnace_review.v5.glb",
        "0ac031e626c9eaa0b0cdd8192cf9fda712324af174a4285f563a97309451ed3c",
    ),
    "v5_material_glb": (
        V5_GLB,
        "652be1b2c9147d5a7392497c7ae4964d19bdd7095b5435b87c105f9eb3fb66bc",
    ),
    "v5_structural_glb": (
        ROOT
        / "高炉前端数据"
        / "models"
        / "gl02_blast_furnace_structural_review.v5.glb",
        "e5c77d3834c631e2513209a690f6328d1c63dba2c8d489b2d2dbe17645465f71",
    ),
    "formal_glb": (
        ROOT / "高炉前端数据" / "models" / "gl02_blast_furnace.glb",
        "808960f1b2703e7fb27df35f1b1b1a17063b9b10d2267acba593fc3872b62af6",
    ),
    "current_orm_4k": (
        ROOT
        / "PT"
        / "高炉3D模型"
        / "work"
        / "INT_30_20260718_R2G_ISOLATED_GLB_WEB_PREVIEW"
        / "textures"
        / "final_4k"
        / "INT30_R2G_R1_LOCK_ORM_4K.png",
        "e3354cc5d793807ebb4f6b0d74593a7b6f09f18fcece8f9102e867f2c8570e17",
    ),
    "r2x_stage_contract": (
        CONTRACT,
        "14432e1cc140b29bff216df470018f028b579ad9ddc413446b07f47369847639",
    ),
    "r2x_source_glb": (
        R2X_SOURCE_GLB,
        "a7c9842331a3bae69d7555ac31c3310daec8d883f7b1afcbbf0d5f67c494c6ab",
    ),
    "r2x_ao_png": (
        AO_PNG,
        "c1362fa572e94e2b8f704ab9d3ec46aed6cc930d7616bb4ad14a38793abcf786",
    ),
}

V5_IMAGE_PAYLOAD_LOCKS = {
    "INT30_R2G_R1_LOCK_NormalGL_4K": (
        "image/webp",
        "6a8631eb85056cd8db287f5cb8a35c29c43140a871afd15931871d81a6188589",
    ),
    "INT30_R2G_R1_LOCK_BaseColor_4K": (
        "image/webp",
        "afa1c05099d229a5fbace9dc44ba33b90cd751ef8526ceafa440d9b5e3a8e54e",
    ),
    "INT30_R2G_R1_LOCK_ORM_4K": (
        "image/webp",
        "cb63d1cc1a8844e7a52029955f6857f990ac89e7cf5cff190ceabee23abfb599",
    ),
}

APPROVAL_STOP_LINES = {
    "approval_granted": False,
    "ao_2k_approved": False,
    "p50_approved": False,
    "p60_approved": False,
    "production_integration_allowed": False,
    "next_release_stage_allowed": False,
}

GLB_MAGIC = b"glTF"
GLB_JSON_CHUNK = b"JSON"
GLB_BIN_CHUNK = b"BIN\x00"
COMPONENT_FORMATS: dict[int, tuple[str, int, bool, int | None]] = {
    5120: ("b", 1, True, 127),
    5121: ("B", 1, False, 255),
    5122: ("h", 2, True, 32767),
    5123: ("H", 2, False, 65535),
    5125: ("I", 4, False, 4294967295),
    5126: ("f", 4, True, None),
}
TYPE_COMPONENT_COUNTS = {
    "SCALAR": 1,
    "VEC2": 2,
    "VEC3": 3,
    "VEC4": 4,
}
WINDOWS_ABSOLUTE_RE = re.compile(r"(?i)(?:^|[^A-Za-z0-9_])[A-Z]:[\\/]")


class RepackError(RuntimeError):
    """Raised when a fail-closed repack gate is not satisfied."""


def now_iso() -> str:
    """Return a local ISO timestamp with timezone."""

    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def relative_path(path: Path) -> str:
    """Return a stable project-relative path when possible."""

    try:
        return path.resolve().relative_to(ROOT.resolve()).as_posix()
    except ValueError:
        return str(path.resolve())


def sha256_bytes(payload: bytes) -> str:
    """Return the SHA-256 of bytes."""

    return hashlib.sha256(payload).hexdigest()


def sha256_file(path: Path) -> str:
    """Return the SHA-256 of a file without loading it all at once."""

    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def stable_sha(value: Any) -> str:
    """Hash a JSON value using a deterministic encoding."""

    return sha256_bytes(
        json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    )


def artifact_record(
    path: Path,
    expected_sha256: str | None = None,
) -> dict[str, Any]:
    """Describe one filesystem artifact."""

    exists = path.is_file()
    actual = sha256_file(path) if exists else None
    record: dict[str, Any] = {
        "path": relative_path(path),
        "exists": exists,
        "bytes": path.stat().st_size if exists else None,
        "sha256": actual,
    }
    if expected_sha256 is not None:
        record["expected_sha256"] = expected_sha256
        record["matches_expected"] = exists and actual == expected_sha256
    return record


def protected_snapshot() -> dict[str, dict[str, Any]]:
    """Measure every immutable input."""

    return {
        name: artifact_record(path, expected)
        for name, (path, expected) in LOCKS.items()
    }


def assert_protected_snapshot(
    snapshot: dict[str, dict[str, Any]],
) -> None:
    """Reject any missing or changed immutable input."""

    failed = [
        name
        for name, record in snapshot.items()
        if not record.get("matches_expected")
    ]
    if failed:
        raise RepackError(f"Protected input hash gate failed: {failed}")


def compare_protected_snapshots(
    before: dict[str, dict[str, Any]],
    after: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    """Return before/after identity records for immutable inputs."""

    records: dict[str, Any] = {}
    for name in LOCKS:
        first = before[name]
        second = after[name]
        records[name] = {
            "path": first["path"],
            "expected_sha256": first["expected_sha256"],
            "before_sha256": first["sha256"],
            "after_sha256": second["sha256"],
            "before_matches_expected": first["matches_expected"],
            "after_matches_expected": second["matches_expected"],
            "unchanged": (
                first["exists"]
                and second["exists"]
                and first["sha256"] == second["sha256"]
                and first["bytes"] == second["bytes"]
            ),
        }
    return {
        "artifacts": records,
        "all_unchanged": all(
            record["unchanged"] for record in records.values()
        ),
        "all_match_expected": all(
            record["before_matches_expected"]
            and record["after_matches_expected"]
            for record in records.values()
        ),
    }


def write_json_atomic(path: Path, value: Any) -> None:
    """Atomically write a UTF-8 JSON document."""

    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".writing")
    temporary.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=False) + "\n",
        encoding="utf-8",
    )
    os.replace(temporary, path)


def remove_if_file(path: Path) -> None:
    """Remove an owned output if it exists."""

    try:
        path.unlink()
    except FileNotFoundError:
        return


def read_glb(path: Path) -> tuple[dict[str, Any], bytes, dict[str, Any]]:
    """Read a single-buffer GLB 2.0 and return its logical BIN payload."""

    if not path.is_file():
        raise RepackError(f"Required GLB is missing: {path}")
    data = path.read_bytes()
    if len(data) < 20:
        raise RepackError(f"Truncated GLB: {path}")
    magic, version, declared_length = struct.unpack_from("<4sII", data, 0)
    if magic != GLB_MAGIC or version != 2 or declared_length != len(data):
        raise RepackError(
            f"Invalid GLB 2.0 header: {path}: "
            f"magic={magic!r}, version={version}, "
            f"declared={declared_length}, actual={len(data)}"
        )
    offset = 12
    json_chunks: list[bytes] = []
    bin_chunks: list[bytes] = []
    chunk_records: list[dict[str, Any]] = []
    while offset < len(data):
        if offset + 8 > len(data):
            raise RepackError(f"Truncated GLB chunk header: {path}")
        chunk_length, chunk_type = struct.unpack_from("<I4s", data, offset)
        offset += 8
        if chunk_length % 4:
            raise RepackError(f"Unaligned GLB chunk: {path}")
        end = offset + chunk_length
        if end > len(data):
            raise RepackError(f"Truncated GLB chunk payload: {path}")
        payload = data[offset:end]
        offset = end
        chunk_records.append(
            {
                "type": chunk_type.decode("ascii", errors="replace"),
                "bytes": chunk_length,
            }
        )
        if chunk_type == GLB_JSON_CHUNK:
            json_chunks.append(payload)
        elif chunk_type == GLB_BIN_CHUNK:
            bin_chunks.append(payload)
        else:
            raise RepackError(
                f"Unsupported GLB chunk type {chunk_type!r}: {path}"
            )
    if len(json_chunks) != 1 or len(bin_chunks) != 1:
        raise RepackError(
            f"Expected one JSON and one BIN chunk: {path}: "
            f"JSON={len(json_chunks)}, BIN={len(bin_chunks)}"
        )
    try:
        gltf = json.loads(
            json_chunks[0].decode("utf-8").rstrip(" \t\r\n\x00")
        )
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise RepackError(f"Invalid GLB JSON: {path}: {exc}") from exc
    if not isinstance(gltf, dict):
        raise RepackError(f"GLB JSON root is not an object: {path}")
    buffers = gltf.get("buffers")
    if not isinstance(buffers, list) or len(buffers) != 1:
        raise RepackError(f"Exactly one embedded buffer is required: {path}")
    if not isinstance(buffers[0], dict) or buffers[0].get("uri") is not None:
        raise RepackError(f"External GLB buffers are forbidden: {path}")
    logical_length = int(buffers[0].get("byteLength", -1))
    binary_chunk = bin_chunks[0]
    padding = binary_chunk[logical_length:]
    if (
        logical_length < 0
        or logical_length > len(binary_chunk)
        or len(padding) > 3
        or any(padding)
    ):
        raise RepackError(
            f"Invalid GLB logical buffer length/padding: {path}"
        )
    return (
        gltf,
        binary_chunk[:logical_length],
        {
            "artifact": artifact_record(path),
            "declared_length": declared_length,
            "logical_buffer_bytes": logical_length,
            "logical_buffer_sha256": sha256_bytes(
                binary_chunk[:logical_length]
            ),
            "bin_chunk_padding_bytes": len(padding),
            "chunks": chunk_records,
        },
    )


def write_glb(path: Path, gltf: dict[str, Any], binary: bytes) -> None:
    """Write a deterministic GLB 2.0 container."""

    json_payload = json.dumps(
        gltf,
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode("utf-8")
    json_chunk = json_payload + b" " * ((-len(json_payload)) % 4)
    bin_chunk = binary + b"\x00" * ((-len(binary)) % 4)
    total_length = 12 + 8 + len(json_chunk) + 8 + len(bin_chunk)
    payload = b"".join(
        (
            struct.pack("<4sII", GLB_MAGIC, 2, total_length),
            struct.pack("<I4s", len(json_chunk), GLB_JSON_CHUNK),
            json_chunk,
            struct.pack("<I4s", len(bin_chunk), GLB_BIN_CHUNK),
            bin_chunk,
        )
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(payload)


def buffer_view_payload(
    gltf: dict[str, Any],
    binary: bytes,
    view_index: int,
) -> bytes:
    """Return an embedded bufferView payload."""

    views = gltf.get("bufferViews")
    if not isinstance(views, list) or not (0 <= view_index < len(views)):
        raise RepackError(f"bufferView index is out of range: {view_index}")
    view = views[view_index]
    if not isinstance(view, dict) or int(view.get("buffer", 0)) != 0:
        raise RepackError(f"bufferView is not in buffer 0: {view_index}")
    offset = int(view.get("byteOffset", 0))
    length = int(view.get("byteLength", -1))
    end = offset + length
    if offset < 0 or length < 0 or end > len(binary):
        raise RepackError(
            f"bufferView exceeds BIN: index={view_index}, "
            f"offset={offset}, length={length}, bin={len(binary)}"
        )
    return binary[offset:end]


def accessor_snapshot(
    gltf: dict[str, Any],
    binary: bytes,
    accessor_index: int,
) -> dict[str, Any]:
    """Extract compact bytes and a canonical decoded sequence for an accessor."""

    accessors = gltf.get("accessors")
    views = gltf.get("bufferViews")
    if not isinstance(accessors, list) or not (
        0 <= accessor_index < len(accessors)
    ):
        raise RepackError(f"Accessor index is out of range: {accessor_index}")
    accessor = accessors[accessor_index]
    if not isinstance(accessor, dict):
        raise RepackError(f"Accessor is not an object: {accessor_index}")
    if accessor.get("sparse") is not None:
        raise RepackError(
            f"Sparse accessors are outside the R2X transplant contract: "
            f"{accessor_index}"
        )
    view_index = accessor.get("bufferView")
    if not isinstance(view_index, int):
        raise RepackError(f"Accessor has no bufferView: {accessor_index}")
    if not isinstance(views, list) or not (0 <= view_index < len(views)):
        raise RepackError(
            f"Accessor bufferView is out of range: {accessor_index}"
        )
    view = views[view_index]
    if not isinstance(view, dict) or int(view.get("buffer", 0)) != 0:
        raise RepackError(
            f"Accessor is not in embedded buffer 0: {accessor_index}"
        )
    component_type = int(accessor.get("componentType", 0))
    if component_type not in COMPONENT_FORMATS:
        raise RepackError(
            f"Unsupported accessor component type: {component_type}"
        )
    accessor_type = str(accessor.get("type", ""))
    components = TYPE_COMPONENT_COUNTS.get(accessor_type)
    if components is None:
        raise RepackError(f"Unsupported accessor type: {accessor_type}")
    format_char, component_bytes, signed, denominator = (
        COMPONENT_FORMATS[component_type]
    )
    element_bytes = components * component_bytes
    stride = int(view.get("byteStride", element_bytes))
    if stride < element_bytes:
        raise RepackError(f"Accessor stride is too small: {accessor_index}")
    view_offset = int(view.get("byteOffset", 0))
    view_length = int(view.get("byteLength", -1))
    accessor_offset = int(accessor.get("byteOffset", 0))
    count = int(accessor.get("count", -1))
    if min(view_offset, view_length, accessor_offset, count) < 0:
        raise RepackError(f"Negative accessor range: {accessor_index}")
    start = view_offset + accessor_offset
    end = start + max(count - 1, 0) * stride + (
        element_bytes if count else 0
    )
    if (
        start < view_offset
        or end > view_offset + view_length
        or end > len(binary)
    ):
        raise RepackError(f"Accessor exceeds bufferView: {accessor_index}")

    unpacker = struct.Struct("<" + format_char * components)
    normalized = bool(accessor.get("normalized", False))
    compact = bytearray()
    decoded = bytearray()
    non_finite = 0
    minimum = [math.inf] * components
    maximum = [-math.inf] * components
    for item_index in range(count):
        item_offset = start + item_index * stride
        raw_bytes = binary[item_offset : item_offset + element_bytes]
        compact.extend(raw_bytes)
        raw_values = unpacker.unpack(raw_bytes)
        if normalized and denominator is not None:
            if signed:
                values = tuple(
                    max(float(value) / denominator, -1.0)
                    for value in raw_values
                )
            else:
                values = tuple(
                    float(value) / denominator for value in raw_values
                )
        else:
            values = tuple(float(value) for value in raw_values)
        for axis, value in enumerate(values):
            decoded.extend(struct.pack("<d", value))
            if not math.isfinite(value):
                non_finite += 1
            else:
                minimum[axis] = min(minimum[axis], value)
                maximum[axis] = max(maximum[axis], value)

    metadata = {
        "componentType": component_type,
        "type": accessor_type,
        "count": count,
        "normalized": normalized,
        "min": copy.deepcopy(accessor.get("min")),
        "max": copy.deepcopy(accessor.get("max")),
    }
    return {
        "accessor_index": accessor_index,
        "buffer_view_index": view_index,
        "metadata": metadata,
        "layout": {
            "accessor_byte_offset": accessor_offset,
            "view_byte_offset": view_offset,
            "view_byte_length": view_length,
            "view_byte_stride": view.get("byteStride"),
            "view_target": view.get("target"),
            "element_bytes": element_bytes,
        },
        "compact_bytes": bytes(compact),
        "decoded_bytes": bytes(decoded),
        "compact_byte_length": len(compact),
        "compact_sha256": sha256_bytes(bytes(compact)),
        "decoded_canonical_byte_length": len(decoded),
        "decoded_sha256": sha256_bytes(bytes(decoded)),
        "decoded_component_count": count * components,
        "non_finite_component_count": non_finite,
        "decoded_minimum": minimum if count and not non_finite else None,
        "decoded_maximum": maximum if count and not non_finite else None,
    }


def public_accessor_snapshot(snapshot: dict[str, Any]) -> dict[str, Any]:
    """Remove private byte blobs from an accessor report record."""

    return {
        key: value
        for key, value in snapshot.items()
        if key not in {"compact_bytes", "decoded_bytes"}
    }


def find_target_primitive(
    gltf: dict[str, Any],
    target: str,
) -> dict[str, Any]:
    """Resolve one target node to exactly one mesh primitive."""

    nodes = gltf.get("nodes")
    meshes = gltf.get("meshes")
    if not isinstance(nodes, list) or not isinstance(meshes, list):
        raise RepackError("GLB nodes/meshes arrays are missing")
    matches = [
        (index, node)
        for index, node in enumerate(nodes)
        if isinstance(node, dict) and node.get("name") == target
    ]
    if len(matches) != 1:
        raise RepackError(
            f"Expected exactly one target node {target!r}, got {len(matches)}"
        )
    node_index, node = matches[0]
    mesh_index = node.get("mesh")
    if not isinstance(mesh_index, int) or not (0 <= mesh_index < len(meshes)):
        raise RepackError(f"Target node has no valid mesh: {target}")
    mesh = meshes[mesh_index]
    if not isinstance(mesh, dict):
        raise RepackError(f"Target mesh is not an object: {target}")
    primitives = mesh.get("primitives")
    if not isinstance(primitives, list) or len(primitives) != 1:
        raise RepackError(
            f"Target mesh must have exactly one primitive: "
            f"{target}: {0 if not isinstance(primitives, list) else len(primitives)}"
        )
    primitive = primitives[0]
    if not isinstance(primitive, dict):
        raise RepackError(f"Target primitive is not an object: {target}")
    return {
        "node_index": node_index,
        "node": node,
        "mesh_index": mesh_index,
        "mesh": mesh,
        "primitive_index": 0,
        "primitive": primitive,
    }


def resolve_texture(
    gltf: dict[str, Any],
    binary: bytes,
    texture_info: Any,
) -> dict[str, Any]:
    """Resolve an embedded textureInfo, including payload and sampler."""

    if not isinstance(texture_info, dict):
        raise RepackError("Texture info is not an object")
    texture_index = texture_info.get("index")
    textures = gltf.get("textures")
    images = gltf.get("images")
    samplers = gltf.get("samplers")
    if not isinstance(textures, list) or not isinstance(texture_index, int):
        raise RepackError("Texture index is missing")
    if not (0 <= texture_index < len(textures)):
        raise RepackError(f"Texture index out of range: {texture_index}")
    texture = textures[texture_index]
    if not isinstance(texture, dict):
        raise RepackError(f"Texture is not an object: {texture_index}")
    source_index = texture.get("source")
    if source_index is None:
        webp = (texture.get("extensions") or {}).get("EXT_texture_webp")
        if isinstance(webp, dict):
            source_index = webp.get("source")
    if not isinstance(images, list) or not isinstance(source_index, int):
        raise RepackError(f"Texture has no image source: {texture_index}")
    if not (0 <= source_index < len(images)):
        raise RepackError(f"Image index out of range: {source_index}")
    image = images[source_index]
    if not isinstance(image, dict) or not isinstance(
        image.get("bufferView"), int
    ):
        raise RepackError(f"Texture image is not embedded: {texture_index}")
    image_payload = buffer_view_payload(
        gltf,
        binary,
        int(image["bufferView"]),
    )
    sampler_index = texture.get("sampler")
    sampler = None
    if sampler_index is not None:
        if not isinstance(samplers, list) or not isinstance(
            sampler_index, int
        ):
            raise RepackError(f"Invalid texture sampler: {texture_index}")
        if not (0 <= sampler_index < len(samplers)):
            raise RepackError(f"Sampler index out of range: {sampler_index}")
        sampler = samplers[sampler_index]
        if not isinstance(sampler, dict):
            raise RepackError(f"Sampler is not an object: {sampler_index}")
    return {
        "texture_info": copy.deepcopy(texture_info),
        "texture_index": texture_index,
        "texture": copy.deepcopy(texture),
        "image_index": source_index,
        "image": copy.deepcopy(image),
        "image_payload": image_payload,
        "image_payload_sha256": sha256_bytes(image_payload),
        "sampler_index": sampler_index,
        "sampler": copy.deepcopy(sampler),
    }


def validate_v5_image_payloads(
    gltf: dict[str, Any],
    binary: bytes,
) -> list[dict[str, Any]]:
    """Validate and record the three locked embedded V5 WebP payloads."""

    images = gltf.get("images")
    if not isinstance(images, list) or len(images) != 3:
        raise RepackError("V5 must contain exactly three embedded images")
    records: list[dict[str, Any]] = []
    seen: set[str] = set()
    for index, image in enumerate(images):
        if not isinstance(image, dict):
            raise RepackError(f"V5 image is not an object: {index}")
        name = image.get("name")
        if not isinstance(name, str) or name not in V5_IMAGE_PAYLOAD_LOCKS:
            raise RepackError(f"Unexpected V5 image name: {name!r}")
        if not isinstance(image.get("bufferView"), int) or image.get("uri"):
            raise RepackError(f"V5 image is not embedded: {name}")
        payload = buffer_view_payload(
            gltf,
            binary,
            int(image["bufferView"]),
        )
        expected_mime, expected_sha = V5_IMAGE_PAYLOAD_LOCKS[name]
        actual_sha = sha256_bytes(payload)
        if image.get("mimeType") != expected_mime or actual_sha != expected_sha:
            raise RepackError(f"V5 image payload lock failed: {name}")
        seen.add(name)
        records.append(
            {
                "image_index": index,
                "name": name,
                "mimeType": image.get("mimeType"),
                "buffer_view_index": image["bufferView"],
                "bytes": len(payload),
                "sha256": actual_sha,
                "expected_sha256": expected_sha,
                "matches_expected": True,
            }
        )
    if seen != set(V5_IMAGE_PAYLOAD_LOCKS):
        raise RepackError("V5 image payload set is incomplete")
    return records


def inspect_sources(
    v5_gltf: dict[str, Any],
    v5_binary: bytes,
    r2x_gltf: dict[str, Any],
    r2x_binary: bytes,
) -> dict[str, Any]:
    """Compare every protected primitive value and inspect AO transplants."""

    mappings: list[dict[str, Any]] = []
    internal_uv2: dict[str, dict[str, Any]] = {}
    ao_sources: list[dict[str, Any]] = []
    v5_materials = v5_gltf.get("materials")
    r2x_materials = r2x_gltf.get("materials")
    if not isinstance(v5_materials, list) or not isinstance(
        r2x_materials, list
    ):
        raise RepackError("Materials arrays are missing")

    for target in TARGETS:
        v5 = find_target_primitive(v5_gltf, target)
        r2x = find_target_primitive(r2x_gltf, target)
        v5_primitive = v5["primitive"]
        r2x_primitive = r2x["primitive"]
        if int(v5_primitive.get("mode", 4)) != int(
            r2x_primitive.get("mode", 4)
        ):
            raise RepackError(f"Primitive mode mismatch: {target}")
        v5_attributes = v5_primitive.get("attributes")
        r2x_attributes = r2x_primitive.get("attributes")
        if not isinstance(v5_attributes, dict) or not isinstance(
            r2x_attributes, dict
        ):
            raise RepackError(f"Primitive attributes are missing: {target}")
        protected: dict[str, Any] = {}
        for semantic in PROTECTED_SEMANTICS:
            v5_index = v5_attributes.get(semantic)
            r2x_index = r2x_attributes.get(semantic)
            if not isinstance(v5_index, int) or not isinstance(r2x_index, int):
                raise RepackError(
                    f"Protected attribute is missing: {target}: {semantic}"
                )
            v5_snapshot = accessor_snapshot(v5_gltf, v5_binary, v5_index)
            r2x_snapshot = accessor_snapshot(
                r2x_gltf,
                r2x_binary,
                r2x_index,
            )
            metadata_exact = (
                v5_snapshot["metadata"] == r2x_snapshot["metadata"]
            )
            raw_exact = (
                v5_snapshot["compact_bytes"]
                == r2x_snapshot["compact_bytes"]
            )
            decoded_exact = (
                v5_snapshot["decoded_bytes"]
                == r2x_snapshot["decoded_bytes"]
            )
            if (
                not metadata_exact
                or not raw_exact
                or not decoded_exact
                or v5_snapshot["non_finite_component_count"]
                or r2x_snapshot["non_finite_component_count"]
            ):
                raise RepackError(
                    f"Protected accessor mismatch: {target}: {semantic}"
                )
            protected[semantic] = {
                "v5": public_accessor_snapshot(v5_snapshot),
                "r2x_source": public_accessor_snapshot(r2x_snapshot),
                "metadata_exact": metadata_exact,
                "compact_raw_sequence_exact": raw_exact,
                "decoded_value_order_exact": decoded_exact,
            }

        v5_indices = v5_primitive.get("indices")
        r2x_indices = r2x_primitive.get("indices")
        if not isinstance(v5_indices, int) or not isinstance(r2x_indices, int):
            raise RepackError(f"Indexed primitives are required: {target}")
        v5_index_snapshot = accessor_snapshot(
            v5_gltf,
            v5_binary,
            v5_indices,
        )
        r2x_index_snapshot = accessor_snapshot(
            r2x_gltf,
            r2x_binary,
            r2x_indices,
        )
        index_metadata_exact = (
            v5_index_snapshot["metadata"]
            == r2x_index_snapshot["metadata"]
        )
        index_raw_exact = (
            v5_index_snapshot["compact_bytes"]
            == r2x_index_snapshot["compact_bytes"]
        )
        index_decoded_exact = (
            v5_index_snapshot["decoded_bytes"]
            == r2x_index_snapshot["decoded_bytes"]
        )
        if (
            not index_metadata_exact
            or not index_raw_exact
            or not index_decoded_exact
        ):
            raise RepackError(f"Protected indices mismatch: {target}")
        protected["indices"] = {
            "v5": public_accessor_snapshot(v5_index_snapshot),
            "r2x_source": public_accessor_snapshot(r2x_index_snapshot),
            "metadata_exact": index_metadata_exact,
            "compact_raw_sequence_exact": index_raw_exact,
            "decoded_value_order_exact": index_decoded_exact,
        }

        if "TEXCOORD_2" in v5_attributes:
            raise RepackError(f"V5 already contains TEXCOORD_2: {target}")
        uv2_index = r2x_attributes.get("TEXCOORD_2")
        if not isinstance(uv2_index, int):
            raise RepackError(f"R2X source TEXCOORD_2 is missing: {target}")
        uv2 = accessor_snapshot(r2x_gltf, r2x_binary, uv2_index)
        position_count = int(
            protected["POSITION"]["v5"]["metadata"]["count"]
        )
        uv2_metadata = uv2["metadata"]
        uv2_range_ok = (
            uv2["non_finite_component_count"] == 0
            and uv2["decoded_minimum"] is not None
            and uv2["decoded_maximum"] is not None
            and min(uv2["decoded_minimum"]) >= -1.0e-7
            and max(uv2["decoded_maximum"]) <= 1.0 + 1.0e-7
        )
        if (
            uv2_metadata["componentType"] != 5126
            or uv2_metadata["type"] != "VEC2"
            or uv2_metadata["normalized"]
            or int(uv2_metadata["count"]) != position_count
            or uv2["layout"]["view_target"] != 34962
            or not uv2_range_ok
        ):
            raise RepackError(f"R2X TEXCOORD_2 contract failed: {target}")
        internal_uv2[target] = {
            "source_accessor": copy.deepcopy(
                r2x_gltf["accessors"][uv2_index]
            ),
            "compact_bytes": uv2["compact_bytes"],
            "decoded_bytes": uv2["decoded_bytes"],
            "public": public_accessor_snapshot(uv2),
        }

        r2x_material_index = r2x_primitive.get("material")
        v5_material_index = v5_primitive.get("material")
        if (
            not isinstance(r2x_material_index, int)
            or not (0 <= r2x_material_index < len(r2x_materials))
            or not isinstance(v5_material_index, int)
            or not (0 <= v5_material_index < len(v5_materials))
        ):
            raise RepackError(f"Primitive material is invalid: {target}")
        r2x_material = r2x_materials[r2x_material_index]
        if not isinstance(r2x_material, dict):
            raise RepackError(f"R2X material is invalid: {target}")
        occlusion_info = r2x_material.get("occlusionTexture")
        if not isinstance(occlusion_info, dict) or int(
            occlusion_info.get("texCoord", 0)
        ) != 2:
            raise RepackError(
                f"R2X occlusionTexture must use TEXCOORD_2: {target}"
            )
        ao_source = resolve_texture(
            r2x_gltf,
            r2x_binary,
            occlusion_info,
        )
        if (
            ao_source["image"].get("mimeType") != "image/png"
            or ao_source["image"].get("name") != AO_IMAGE_NAME
            or ao_source["image"].get("uri") is not None
            or ao_source["image_payload_sha256"]
            != LOCKS["r2x_ao_png"][1]
            or ao_source["image_payload"] != AO_PNG.read_bytes()
            or ao_source["texture"].get("source")
            != ao_source["image_index"]
            or ao_source["texture"].get("extensions")
        ):
            raise RepackError(f"R2X AO payload contract failed: {target}")
        if not isinstance(ao_source["sampler"], dict):
            raise RepackError(f"R2X AO sampler is missing: {target}")
        ao_sources.append(ao_source)

        mappings.append(
            {
                "target": target,
                "v5": {
                    "node_index": v5["node_index"],
                    "node_name": v5["node"].get("name"),
                    "mesh_index": v5["mesh_index"],
                    "mesh_name": v5["mesh"].get("name"),
                    "primitive_index": 0,
                    "material_index": v5_material_index,
                    "material_name": v5_materials[
                        v5_material_index
                    ].get("name"),
                },
                "r2x_source": {
                    "node_index": r2x["node_index"],
                    "node_name": r2x["node"].get("name"),
                    "mesh_index": r2x["mesh_index"],
                    "mesh_name": r2x["mesh"].get("name"),
                    "primitive_index": 0,
                    "material_index": r2x_material_index,
                    "material_name": r2x_material.get("name"),
                },
                "protected_semantics": protected,
                "uv2_source": public_accessor_snapshot(uv2),
                "ao_source": {
                    "occlusion_texture_info": copy.deepcopy(
                        occlusion_info
                    ),
                    "texture_index": ao_source["texture_index"],
                    "image_index": ao_source["image_index"],
                    "sampler_index": ao_source["sampler_index"],
                    "payload_bytes": len(ao_source["image_payload"]),
                    "payload_sha256": ao_source[
                        "image_payload_sha256"
                    ],
                },
            }
        )

    first_ao = ao_sources[0]
    for source in ao_sources[1:]:
        if (
            source["image_index"] != first_ao["image_index"]
            or source["image_payload"] != first_ao["image_payload"]
            or source["sampler"] != first_ao["sampler"]
            or source["texture"] != first_ao["texture"]
        ):
            raise RepackError(
                "The five R2X AO bindings do not share one payload/sampler"
            )
        first_info = copy.deepcopy(first_ao["texture_info"])
        source_info = copy.deepcopy(source["texture_info"])
        first_info.pop("index", None)
        source_info.pop("index", None)
        if source_info != first_info:
            raise RepackError(
                "The five R2X occlusionTexture descriptors disagree"
            )

    target_materials = sorted(
        {int(item["v5"]["material_index"]) for item in mappings}
    )
    if target_materials != [0, 1] or len(v5_materials) != 2:
        raise RepackError(
            f"Expected exactly the two locked V5 materials, got "
            f"{target_materials}/{len(v5_materials)}"
        )

    target_mesh_indices = {
        int(item["v5"]["mesh_index"]) for item in mappings
    }
    non_target_uses: list[dict[str, int]] = []
    for mesh_index, mesh in enumerate(v5_gltf.get("meshes") or []):
        if not isinstance(mesh, dict):
            raise RepackError(f"V5 mesh is invalid: {mesh_index}")
        for primitive_index, primitive in enumerate(
            mesh.get("primitives") or []
        ):
            if (
                isinstance(primitive, dict)
                and primitive.get("material") in target_materials
                and mesh_index not in target_mesh_indices
            ):
                non_target_uses.append(
                    {
                        "mesh_index": mesh_index,
                        "primitive_index": primitive_index,
                        "material_index": primitive["material"],
                    }
                )
    if non_target_uses:
        raise RepackError(
            f"V5 AO materials are shared by non-target primitives: "
            f"{non_target_uses}"
        )

    return {
        "mappings": mappings,
        "_uv2": internal_uv2,
        "_ao": first_ao,
        "target_material_indices": target_materials,
        "non_target_material_uses": non_target_uses,
    }


def append_aligned(buffer: bytearray, payload: bytes) -> tuple[int, int]:
    """Append a payload at a four-byte boundary."""

    padding = (-len(buffer)) % 4
    if padding:
        buffer.extend(b"\x00" * padding)
    offset = len(buffer)
    buffer.extend(payload)
    return offset, padding


def build_output(
    v5_gltf: dict[str, Any],
    v5_binary: bytes,
    source: dict[str, Any],
) -> tuple[dict[str, Any], bytes, dict[str, Any]]:
    """Append the allowed UV2/AO data to a deep copy of V5."""

    output = copy.deepcopy(v5_gltf)
    binary = bytearray(v5_binary)
    append_records: list[dict[str, Any]] = []
    mapping_by_target = {
        item["target"]: item for item in source["mappings"]
    }
    for target in TARGETS:
        mapping = mapping_by_target[target]
        uv2 = source["_uv2"][target]
        offset, padding = append_aligned(binary, uv2["compact_bytes"])
        view_index = len(output["bufferViews"])
        output["bufferViews"].append(
            {
                "buffer": 0,
                "byteOffset": offset,
                "byteLength": len(uv2["compact_bytes"]),
                "target": 34962,
            }
        )
        accessor = copy.deepcopy(uv2["source_accessor"])
        accessor["bufferView"] = view_index
        accessor.pop("byteOffset", None)
        accessor.pop("sparse", None)
        accessor_index = len(output["accessors"])
        output["accessors"].append(accessor)
        mesh_index = int(mapping["v5"]["mesh_index"])
        primitive = output["meshes"][mesh_index]["primitives"][0]
        primitive["attributes"]["TEXCOORD_2"] = accessor_index
        mapping["uv2_output"] = {
            "accessor_index": accessor_index,
            "buffer_view_index": view_index,
            "byte_offset": offset,
            "byte_length": len(uv2["compact_bytes"]),
            "alignment_padding_before": padding,
            "compact_sha256": sha256_bytes(uv2["compact_bytes"]),
            "decoded_sha256": sha256_bytes(uv2["decoded_bytes"]),
        }
        append_records.append(
            {
                "kind": "TEXCOORD_2",
                "target": target,
                **mapping["uv2_output"],
            }
        )

    ao_source = source["_ao"]
    ao_payload = ao_source["image_payload"]
    ao_offset, ao_padding = append_aligned(binary, ao_payload)
    ao_view_index = len(output["bufferViews"])
    output["bufferViews"].append(
        {
            "buffer": 0,
            "byteOffset": ao_offset,
            "byteLength": len(ao_payload),
        }
    )

    image = copy.deepcopy(ao_source["image"])
    image["bufferView"] = ao_view_index
    image.pop("uri", None)
    ao_image_index = len(output["images"])
    output["images"].append(image)

    samplers = output.get("samplers")
    if (
        not isinstance(samplers, list)
        or len(samplers) != 1
        or not isinstance(samplers[0], dict)
    ):
        raise RepackError("Locked V5 sampler 0 is unavailable")
    ao_sampler_index = 0

    texture = copy.deepcopy(ao_source["texture"])
    texture["source"] = ao_image_index
    texture["sampler"] = ao_sampler_index
    texture.pop("extensions", None)
    ao_texture_index = len(output["textures"])
    output["textures"].append(texture)

    texture_info = copy.deepcopy(ao_source["texture_info"])
    texture_info["index"] = ao_texture_index
    texture_info["texCoord"] = 2
    for material_index in source["target_material_indices"]:
        material = output["materials"][material_index]
        if material.get("occlusionTexture") is not None:
            raise RepackError(
                f"V5 material already has occlusionTexture: {material_index}"
            )
        material["occlusionTexture"] = copy.deepcopy(texture_info)

    output["buffers"][0]["byteLength"] = len(binary)
    append_records.append(
        {
            "kind": "AO_PNG",
            "image_index": ao_image_index,
            "texture_index": ao_texture_index,
            "sampler_index": ao_sampler_index,
            "sampler_provenance": "locked_v5_sampler_0_reused",
            "candidate_sampler_transplanted": False,
            "buffer_view_index": ao_view_index,
            "byte_offset": ao_offset,
            "byte_length": len(ao_payload),
            "alignment_padding_before": ao_padding,
            "payload_sha256": sha256_bytes(ao_payload),
        }
    )
    return (
        output,
        bytes(binary),
        {
            "append_records": append_records,
            "ao_image_index": ao_image_index,
            "ao_texture_index": ao_texture_index,
            "ao_sampler_index": ao_sampler_index,
            "ao_buffer_view_index": ao_view_index,
            "ao_payload_sha256": sha256_bytes(ao_payload),
            "ao_payload_bytes": len(ao_payload),
            "logical_buffer_bytes_before": len(v5_binary),
            "logical_buffer_bytes_after": len(binary),
            "logical_buffer_growth_bytes": len(binary) - len(v5_binary),
        },
    )


def normalized_meshes_without_uv2(
    meshes: Any,
) -> list[dict[str, Any]]:
    """Copy meshes while removing only the allowed TEXCOORD_2 additions."""

    normalized = copy.deepcopy(meshes)
    if not isinstance(normalized, list):
        raise RepackError("Meshes array is missing")
    for mesh in normalized:
        if not isinstance(mesh, dict):
            raise RepackError("Mesh entry is invalid")
        for primitive in mesh.get("primitives") or []:
            if not isinstance(primitive, dict):
                raise RepackError("Primitive entry is invalid")
            attributes = primitive.get("attributes")
            if not isinstance(attributes, dict):
                raise RepackError("Primitive attributes are invalid")
            attributes.pop("TEXCOORD_2", None)
    return normalized


def normalized_materials_without_ao(
    materials: Any,
    material_indices: list[int],
) -> list[dict[str, Any]]:
    """Copy materials while removing only the allowed AO bindings."""

    normalized = copy.deepcopy(materials)
    if not isinstance(normalized, list):
        raise RepackError("Materials array is missing")
    for material_index in material_indices:
        normalized[material_index].pop("occlusionTexture", None)
    return normalized


def iter_json_strings(
    value: Any,
    pointer: str = "",
) -> Iterator[tuple[str, str | None, str]]:
    """Yield all JSON strings with a pointer and parent key."""

    if isinstance(value, dict):
        for key, child in value.items():
            child_pointer = f"{pointer}/{key}"
            if isinstance(child, str):
                yield child_pointer, key, child
            yield from iter_json_strings(child, child_pointer)
    elif isinstance(value, list):
        for index, child in enumerate(value):
            child_pointer = f"{pointer}/{index}"
            if isinstance(child, str):
                yield child_pointer, None, child
            yield from iter_json_strings(child, child_pointer)


def resource_findings(gltf: dict[str, Any]) -> dict[str, Any]:
    """Find external resources and local absolute paths."""

    external: list[dict[str, Any]] = []
    absolute: list[dict[str, str]] = []
    for pointer, key, value in iter_json_strings(gltf):
        if key == "uri":
            external.append({"pointer": pointer, "uri": value})
        if (
            WINDOWS_ABSOLUTE_RE.search(value)
            or value.lower().startswith("file:")
            or (
                value.startswith("/")
                and not value.lower().startswith(
                    ("/http:", "/https:", "/data:")
                )
            )
        ):
            absolute.append({"pointer": pointer, "value": value})
    missing_embedded: list[dict[str, Any]] = []
    for index, image in enumerate(gltf.get("images") or []):
        if (
            not isinstance(image, dict)
            or not isinstance(image.get("bufferView"), int)
            or not image.get("mimeType")
        ):
            missing_embedded.append({"kind": "image", "index": index})
    for index, buffer in enumerate(gltf.get("buffers") or []):
        if not isinstance(buffer, dict) or buffer.get("uri") is not None:
            missing_embedded.append({"kind": "buffer", "index": index})
    return {
        "external_resources": external,
        "external_resource_count": len(external),
        "local_absolute_paths": absolute,
        "local_absolute_path_count": len(absolute),
        "missing_embedded_resources": missing_embedded,
        "missing_embedded_resource_count": len(missing_embedded),
    }


def section_ao_bindings(gltf: dict[str, Any]) -> list[dict[str, Any]]:
    """List section primitives whose material has an AO binding."""

    materials = gltf.get("materials") or []
    meshes = gltf.get("meshes") or []
    section_mesh_indices: set[int] = set()
    for index, mesh in enumerate(meshes):
        if isinstance(mesh, dict) and str(mesh.get("name", "")).startswith(
            "SECTION_"
        ):
            section_mesh_indices.add(index)
    for node in gltf.get("nodes") or []:
        if (
            isinstance(node, dict)
            and str(node.get("name", "")).startswith("SECTION_")
            and isinstance(node.get("mesh"), int)
        ):
            section_mesh_indices.add(int(node["mesh"]))
    bindings: list[dict[str, Any]] = []
    for mesh_index in sorted(section_mesh_indices):
        if not (0 <= mesh_index < len(meshes)):
            continue
        mesh = meshes[mesh_index]
        if not isinstance(mesh, dict):
            continue
        for primitive_index, primitive in enumerate(
            mesh.get("primitives") or []
        ):
            material_index = (
                primitive.get("material")
                if isinstance(primitive, dict)
                else None
            )
            material = (
                materials[material_index]
                if isinstance(material_index, int)
                and 0 <= material_index < len(materials)
                and isinstance(materials[material_index], dict)
                else {}
            )
            if material.get("occlusionTexture") is not None:
                bindings.append(
                    {
                        "mesh_index": mesh_index,
                        "mesh_name": mesh.get("name"),
                        "primitive_index": primitive_index,
                        "material_index": material_index,
                    }
                )
    return bindings


def audit_output(
    path: Path,
    v5_gltf: dict[str, Any],
    v5_binary: bytes,
    source: dict[str, Any],
    build: dict[str, Any],
) -> dict[str, Any]:
    """Reopen the temporary GLB and assert every preservation/transplant gate."""

    output, output_binary, container = read_glb(path)
    unchanged_keys = sorted(
        set(v5_gltf)
        - {
            "accessors",
            "bufferViews",
            "buffers",
            "images",
            "materials",
            "meshes",
            "samplers",
            "textures",
        }
    )
    top_level_identity = {
        key: {
            "v5_sha256": stable_sha(v5_gltf[key]),
            "output_sha256": stable_sha(output.get(key)),
            "exact": output.get(key) == v5_gltf[key],
        }
        for key in unchanged_keys
    }
    output_keyset_exact = set(output) == set(v5_gltf)
    array_prefix_identity: dict[str, Any] = {}
    for key in ("accessors", "bufferViews", "images", "samplers", "textures"):
        baseline_array = v5_gltf.get(key) or []
        output_array = output.get(key) or []
        exact = (
            isinstance(baseline_array, list)
            and isinstance(output_array, list)
            and output_array[: len(baseline_array)] == baseline_array
        )
        array_prefix_identity[key] = {
            "v5_count": len(baseline_array),
            "output_count": len(output_array),
            "v5_prefix_sha256": stable_sha(baseline_array),
            "output_prefix_sha256": stable_sha(
                output_array[: len(baseline_array)]
            ),
            "exact": exact,
        }

    meshes_normalized = normalized_meshes_without_uv2(
        output.get("meshes")
    )
    materials_normalized = normalized_materials_without_ao(
        output.get("materials"),
        source["target_material_indices"],
    )
    mesh_identity = {
        "v5_sha256": stable_sha(v5_gltf.get("meshes")),
        "output_without_texcoord_2_sha256": stable_sha(meshes_normalized),
        "exact_after_removing_texcoord_2": (
            meshes_normalized == v5_gltf.get("meshes")
        ),
    }
    material_identity = {
        "v5_sha256": stable_sha(v5_gltf.get("materials")),
        "output_without_occlusion_sha256": stable_sha(
            materials_normalized
        ),
        "exact_after_removing_occlusion": (
            materials_normalized == v5_gltf.get("materials")
        ),
    }
    buffer_identity = {
        "v5_logical_bytes": len(v5_binary),
        "output_logical_bytes": len(output_binary),
        "v5_prefix_sha256": sha256_bytes(v5_binary),
        "output_prefix_sha256": sha256_bytes(
            output_binary[: len(v5_binary)]
        ),
        "exact_prefix": output_binary[: len(v5_binary)] == v5_binary,
        "declared_output_buffer_bytes": output["buffers"][0][
            "byteLength"
        ],
        "declared_length_exact": (
            int(output["buffers"][0]["byteLength"]) == len(output_binary)
        ),
        "buffer_object_except_length_exact": (
            {
                key: value
                for key, value in output["buffers"][0].items()
                if key != "byteLength"
            }
            == {
                key: value
                for key, value in v5_gltf["buffers"][0].items()
                if key != "byteLength"
            }
        ),
    }
    existing_buffer_views: list[dict[str, Any]] = []
    for index in range(len(v5_gltf.get("bufferViews") or [])):
        before_payload = buffer_view_payload(
            v5_gltf,
            v5_binary,
            index,
        )
        after_payload = buffer_view_payload(output, output_binary, index)
        existing_buffer_views.append(
            {
                "buffer_view_index": index,
                "bytes": len(before_payload),
                "v5_sha256": sha256_bytes(before_payload),
                "output_sha256": sha256_bytes(after_payload),
                "exact": before_payload == after_payload,
            }
        )

    v5_images_before = validate_v5_image_payloads(
        v5_gltf,
        v5_binary,
    )
    v5_images_after = validate_v5_image_payloads(
        {
            **output,
            "images": output["images"][: len(v5_gltf["images"])],
        },
        output_binary,
    )
    v5_payload_identity: list[dict[str, Any]] = []
    for before, after in zip(v5_images_before, v5_images_after):
        v5_payload_identity.append(
            {
                "image_index": before["image_index"],
                "name": before["name"],
                "mimeType": before["mimeType"],
                "bytes": before["bytes"],
                "v5_sha256": before["sha256"],
                "output_sha256": after["sha256"],
                "exact": before["sha256"] == after["sha256"],
            }
        )

    mapping_by_target = {
        item["target"]: item for item in source["mappings"]
    }
    output_uv2_records: list[dict[str, Any]] = []
    protected_output_records: list[dict[str, Any]] = []
    for target in TARGETS:
        mapping = mapping_by_target[target]
        target_output = find_target_primitive(output, target)
        primitive = target_output["primitive"]
        uv2_index = primitive["attributes"].get("TEXCOORD_2")
        if not isinstance(uv2_index, int):
            raise RepackError(f"Output TEXCOORD_2 is missing: {target}")
        output_uv2 = accessor_snapshot(output, output_binary, uv2_index)
        source_uv2 = source["_uv2"][target]
        uv2_raw_exact = (
            output_uv2["compact_bytes"] == source_uv2["compact_bytes"]
        )
        uv2_decoded_exact = (
            output_uv2["decoded_bytes"] == source_uv2["decoded_bytes"]
        )
        uv2_metadata_exact = (
            output_uv2["metadata"]
            == source_uv2["public"]["metadata"]
        )
        output_uv2_records.append(
            {
                "target": target,
                "output": public_accessor_snapshot(output_uv2),
                "r2x_source_compact_sha256": source_uv2[
                    "public"
                ]["compact_sha256"],
                "r2x_source_decoded_sha256": source_uv2[
                    "public"
                ]["decoded_sha256"],
                "metadata_exact": uv2_metadata_exact,
                "compact_raw_sequence_exact": uv2_raw_exact,
                "decoded_value_order_exact": uv2_decoded_exact,
                "passed": (
                    uv2_metadata_exact
                    and uv2_raw_exact
                    and uv2_decoded_exact
                ),
            }
        )

        for semantic in (*PROTECTED_SEMANTICS, "indices"):
            if semantic == "indices":
                output_index = primitive.get("indices")
            else:
                output_index = primitive["attributes"].get(semantic)
            if not isinstance(output_index, int):
                raise RepackError(
                    f"Output protected accessor is missing: "
                    f"{target}: {semantic}"
                )
            output_snapshot = accessor_snapshot(
                output,
                output_binary,
                output_index,
            )
            v5_record = mapping["protected_semantics"][semantic]["v5"]
            protected_output_records.append(
                {
                    "target": target,
                    "semantic": semantic,
                    "v5_accessor_index": v5_record["accessor_index"],
                    "output_accessor_index": output_index,
                    "same_accessor_index": (
                        output_index == v5_record["accessor_index"]
                    ),
                    "metadata_exact": (
                        output_snapshot["metadata"]
                        == v5_record["metadata"]
                    ),
                    "compact_raw_sequence_exact": (
                        output_snapshot["compact_sha256"]
                        == v5_record["compact_sha256"]
                    ),
                    "decoded_value_order_exact": (
                        output_snapshot["decoded_sha256"]
                        == v5_record["decoded_sha256"]
                    ),
                }
            )

    ao_image = output["images"][build["ao_image_index"]]
    ao_payload = buffer_view_payload(
        output,
        output_binary,
        int(ao_image["bufferView"]),
    )
    ao_texture = output["textures"][build["ao_texture_index"]]
    ao_bindings: list[dict[str, Any]] = []
    for material_index in source["target_material_indices"]:
        descriptor = output["materials"][material_index].get(
            "occlusionTexture"
        )
        ao_bindings.append(
            {
                "material_index": material_index,
                "material_name": output["materials"][material_index].get(
                    "name"
                ),
                "descriptor": copy.deepcopy(descriptor),
                "shared_texture_index": (
                    isinstance(descriptor, dict)
                    and descriptor.get("index")
                    == build["ao_texture_index"]
                ),
                "texcoord_2": (
                    isinstance(descriptor, dict)
                    and int(descriptor.get("texCoord", 0)) == 2
                ),
            }
        )
    unexpected_ao_bindings = [
        index
        for index, material in enumerate(output.get("materials") or [])
        if index not in source["target_material_indices"]
        and isinstance(material, dict)
        and material.get("occlusionTexture") is not None
    ]
    sections = section_ao_bindings(output)
    resources = resource_findings(output)

    count_expectations = {
        "nodes": (
            len(output.get("nodes") or []),
            len(v5_gltf.get("nodes") or []),
        ),
        "meshes": (
            len(output.get("meshes") or []),
            len(v5_gltf.get("meshes") or []),
        ),
        "materials": (
            len(output.get("materials") or []),
            len(v5_gltf.get("materials") or []),
        ),
        "accessors": (
            len(output.get("accessors") or []),
            len(v5_gltf.get("accessors") or []) + len(TARGETS),
        ),
        "bufferViews": (
            len(output.get("bufferViews") or []),
            len(v5_gltf.get("bufferViews") or []) + len(TARGETS) + 1,
        ),
        "images": (
            len(output.get("images") or []),
            len(v5_gltf.get("images") or []) + 1,
        ),
        "textures": (
            len(output.get("textures") or []),
            len(v5_gltf.get("textures") or []) + 1,
        ),
        "samplers": (
            len(output.get("samplers") or []),
            len(v5_gltf.get("samplers") or []),
        ),
    }
    counts_exact = all(actual == expected for actual, expected in count_expectations.values())
    protected_output_exact = all(
        record["same_accessor_index"]
        and record["metadata_exact"]
        and record["compact_raw_sequence_exact"]
        and record["decoded_value_order_exact"]
        for record in protected_output_records
    )
    v5_json_identity = (
        output_keyset_exact
        and all(item["exact"] for item in top_level_identity.values())
        and all(item["exact"] for item in array_prefix_identity.values())
        and mesh_identity["exact_after_removing_texcoord_2"]
        and material_identity["exact_after_removing_occlusion"]
        and buffer_identity["buffer_object_except_length_exact"]
    )
    v5_payloads_exact = (
        buffer_identity["exact_prefix"]
        and all(item["exact"] for item in existing_buffer_views)
        and all(item["exact"] for item in v5_payload_identity)
    )
    uv2_exact = all(item["passed"] for item in output_uv2_records)
    ao_exact = (
        ao_image.get("name") == AO_IMAGE_NAME
        and ao_image.get("mimeType") == "image/png"
        and ao_image.get("uri") is None
        and sha256_bytes(ao_payload) == LOCKS["r2x_ao_png"][1]
        and ao_payload == AO_PNG.read_bytes()
        and ao_texture.get("source") == build["ao_image_index"]
        and ao_texture.get("sampler") == build["ao_sampler_index"]
        and all(
            item["shared_texture_index"] and item["texcoord_2"]
            for item in ao_bindings
        )
        and not unexpected_ao_bindings
    )

    gates = {
        "output_keyset_exact": output_keyset_exact,
        "v5_unchanged_top_level_json_exact": all(
            item["exact"] for item in top_level_identity.values()
        ),
        "v5_array_prefixes_exact": all(
            item["exact"] for item in array_prefix_identity.values()
        ),
        "v5_meshes_exact_after_removing_only_texcoord_2": mesh_identity[
            "exact_after_removing_texcoord_2"
        ],
        "v5_materials_exact_after_removing_only_occlusion": (
            material_identity["exact_after_removing_occlusion"]
        ),
        "v5_logical_buffer_exact_prefix": buffer_identity["exact_prefix"],
        "v5_existing_buffer_view_payloads_exact": all(
            item["exact"] for item in existing_buffer_views
        ),
        "v5_webp_payloads_exact": all(
            item["exact"] for item in v5_payload_identity
        ),
        "protected_output_accessors_exact": protected_output_exact,
        "r2x_uv2_transplants_exact": uv2_exact,
        "r2x_ao_png_transplant_exact": ao_exact,
        "single_appended_ao_image_texture_reusing_v5_sampler_0": (
            counts_exact
            and build["ao_image_index"] == len(v5_gltf["images"])
            and build["ao_texture_index"] == len(v5_gltf["textures"])
            and build["ao_sampler_index"] == 0
            and output.get("samplers") == v5_gltf.get("samplers")
        ),
        "two_v5_materials_share_one_ao_texture_texcoord_2": (
            len(ao_bindings) == 2
            and all(
                item["shared_texture_index"] and item["texcoord_2"]
                for item in ao_bindings
            )
        ),
        "section_ao_binding_count_zero": len(sections) == 0,
        "embedded_resources_only": (
            resources["external_resource_count"] == 0
            and resources["missing_embedded_resource_count"] == 0
        ),
        "no_local_absolute_paths": (
            resources["local_absolute_path_count"] == 0
        ),
        "array_counts_exact": counts_exact,
        "declared_buffer_length_exact": buffer_identity[
            "declared_length_exact"
        ],
    }
    if not all(gates.values()):
        failed = [name for name, passed in gates.items() if not passed]
        raise RepackError(f"Internal output audit failed: {failed}")
    return {
        "container": container,
        "unchanged_top_level_json": top_level_identity,
        "array_prefix_identity": array_prefix_identity,
        "mesh_identity": mesh_identity,
        "material_identity": material_identity,
        "buffer_identity": buffer_identity,
        "existing_buffer_view_payload_identity": existing_buffer_views,
        "v5_image_payload_identity": v5_payload_identity,
        "protected_output_accessors": protected_output_records,
        "uv2_output_identity": output_uv2_records,
        "ao": {
            "image_index": build["ao_image_index"],
            "texture_index": build["ao_texture_index"],
            "sampler_index": build["ao_sampler_index"],
            "sampler_provenance": "locked_v5_sampler_0_reused",
            "candidate_sampler_transplanted": False,
            "payload_bytes": len(ao_payload),
            "payload_sha256": sha256_bytes(ao_payload),
            "material_bindings": ao_bindings,
            "unexpected_material_bindings": unexpected_ao_bindings,
        },
        "section_nodes_or_meshes": [
            item
            for item in (
                [
                    node.get("name")
                    for node in output.get("nodes") or []
                    if isinstance(node, dict)
                    and str(node.get("name", "")).startswith("SECTION_")
                ]
                + [
                    mesh.get("name")
                    for mesh in output.get("meshes") or []
                    if isinstance(mesh, dict)
                    and str(mesh.get("name", "")).startswith("SECTION_")
                ]
            )
            if item
        ],
        "section_ao_bindings": sections,
        "section_ao_binding_count": len(sections),
        "resources": resources,
        "array_count_expectations": {
            key: {"actual": actual, "expected": expected, "exact": actual == expected}
            for key, (actual, expected) in count_expectations.items()
        },
        "gates": gates,
        "v5_json_identity_passed": v5_json_identity,
        "v5_payload_identity_passed": v5_payloads_exact,
        "protected_output_identity_passed": protected_output_exact,
        "uv2_transplant_identity_passed": uv2_exact,
        "ao_transplant_identity_passed": ao_exact,
        "passed": all(gates.values()),
    }


def run_khronos_validator(path: Path) -> dict[str, Any]:
    """Run the pinned Khronos glTF Validator and require zero errors/warnings."""

    node = shutil.which("node")
    if node is None:
        raise RepackError("Node.js is required for Khronos validation")
    if not KHRONOS_MODULE.is_dir():
        raise RepackError(
            f"Pinned Khronos validator module is missing: {KHRONOS_MODULE}"
        )
    script = (
        "const fs=require('fs');"
        "const path=require('path');"
        "const validator=require(process.argv[1]);"
        "const file=process.argv[2];"
        "validator.validateBytes(new Uint8Array(fs.readFileSync(file)),"
        "{uri:path.basename(file),maxIssues:10000})"
        ".then(report=>process.stdout.write(JSON.stringify(report)))"
        ".catch(error=>{console.error(error&&error.stack||String(error));"
        "process.exit(2);});"
    )
    completed = subprocess.run(
        [node, "-e", script, str(KHRONOS_MODULE), str(path)],
        cwd=str(STAGE),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    if completed.returncode != 0:
        raise RepackError(
            "Khronos Validator failed to run: "
            f"returncode={completed.returncode}, stderr={completed.stderr}"
        )
    try:
        raw = json.loads(completed.stdout)
    except json.JSONDecodeError as exc:
        raise RepackError(
            f"Khronos Validator returned invalid JSON: {exc}"
        ) from exc
    write_json_atomic(KHRONOS_REPORT, raw)
    issues = raw.get("issues") or {}
    errors = int(issues.get("numErrors", -1))
    warnings = int(issues.get("numWarnings", -1))
    version = raw.get("validatorVersion")
    result = {
        "available": True,
        "status": "completed",
        "node": node,
        "module": relative_path(KHRONOS_MODULE),
        "validator_version": version,
        "expected_validator_version": EXPECTED_VALIDATOR_VERSION,
        "version_matches_expected": version == EXPECTED_VALIDATOR_VERSION,
        "errors": errors,
        "warnings": warnings,
        "infos": int(issues.get("numInfos", 0)),
        "hints": int(issues.get("numHints", 0)),
        "raw_report": artifact_record(KHRONOS_REPORT),
        "passed": (
            version == EXPECTED_VALIDATOR_VERSION
            and errors == 0
            and warnings == 0
        ),
    }
    if not result["passed"]:
        raise RepackError(
            f"Khronos Validator gate failed: version={version!r}, "
            f"errors={errors}, warnings={warnings}"
        )
    return result


def public_source_report(source: dict[str, Any]) -> dict[str, Any]:
    """Return source inspection records without internal payload bytes."""

    return {
        "primitive_mapping": source["mappings"],
        "target_material_indices": source["target_material_indices"],
        "non_target_material_uses": source[
            "non_target_material_uses"
        ],
    }


def initial_report() -> dict[str, Any]:
    """Create the stable report envelope."""

    return {
        "schema": SCHEMA_VERSION,
        "status": "running",
        "stage_id": STAGE_ID,
        "requirement_id": REQUIREMENT_ID,
        "generated_at": now_iso(),
        "purpose": (
            "Repack the five-shell R2X 1K AO UV2/PNG payload onto the "
            "locked V5 material-review geometry and WebP PBR baseline"
        ),
        "scope": {
            "baseline": relative_path(V5_GLB),
            "r2x_source": relative_path(R2X_SOURCE_GLB),
            "allowed_transplants": [
                "five target TEXCOORD_2 accessor value sequences",
                "one embedded R2X AO PNG payload",
                "one AO texture and shared occlusionTexture texCoord=2 binding reusing locked V5 sampler 0",
            ],
            "forbidden_transplants": [
                "candidate POSITION/NORMAL/TANGENT/indices",
                "candidate TEXCOORD_0/TEXCOORD_1",
                "candidate BaseColor/Normal/ORM payloads",
                "candidate materials/nodes/meshes",
                "candidate clamp sampler",
            ],
        },
        "input_lock": {},
        "protected_hashes_before_after": {},
        "primitive_mapping": [],
        "baseline_identity": {},
        "v5_payload_identity": {},
        "r2x_transplants": {},
        "output": artifact_record(OUTPUT_GLB),
        "glb_contract": {},
        "khronos_validator": {
            "status": "not_run",
            "passed": False,
        },
        "machine_gates": {},
        "approval_stop_lines": copy.deepcopy(APPROVAL_STOP_LINES),
        "errors": [],
    }


def execute() -> dict[str, Any]:
    """Execute the complete fail-closed repack and publish the report."""

    report = initial_report()
    before: dict[str, dict[str, Any]] = {}
    try:
        GLB_DIR.mkdir(parents=True, exist_ok=True)
        REPORT_DIR.mkdir(parents=True, exist_ok=True)
        for owned in (TEMP_GLB, OUTPUT_GLB, KHRONOS_REPORT):
            remove_if_file(owned)

        before = protected_snapshot()
        report["input_lock"] = {
            "artifacts": before,
            "all_passed": all(
                record.get("matches_expected")
                for record in before.values()
            ),
        }
        assert_protected_snapshot(before)

        v5_gltf, v5_binary, v5_container = read_glb(V5_GLB)
        r2x_gltf, r2x_binary, r2x_container = read_glb(R2X_SOURCE_GLB)
        v5_image_payloads = validate_v5_image_payloads(
            v5_gltf,
            v5_binary,
        )
        source = inspect_sources(
            v5_gltf,
            v5_binary,
            r2x_gltf,
            r2x_binary,
        )
        source_public = public_source_report(source)
        report["primitive_mapping"] = source_public["primitive_mapping"]

        output_gltf, output_binary, build = build_output(
            v5_gltf,
            v5_binary,
            source,
        )
        write_glb(TEMP_GLB, output_gltf, output_binary)
        audit = audit_output(
            TEMP_GLB,
            v5_gltf,
            v5_binary,
            source,
            build,
        )
        validator = run_khronos_validator(TEMP_GLB)

        after = protected_snapshot()
        protected_identity = compare_protected_snapshots(before, after)
        if (
            not protected_identity["all_unchanged"]
            or not protected_identity["all_match_expected"]
        ):
            raise RepackError("Protected hashes changed during repack")

        os.replace(TEMP_GLB, OUTPUT_GLB)
        final_gltf, final_binary, final_container = read_glb(OUTPUT_GLB)
        if (
            final_gltf != output_gltf
            or final_binary != output_binary
            or sha256_file(OUTPUT_GLB)
            != final_container["artifact"]["sha256"]
        ):
            raise RepackError("Atomic publication identity check failed")

        report["protected_hashes_before_after"] = protected_identity
        report["baseline_identity"] = {
            "v5_container": v5_container,
            "r2x_source_container": r2x_container,
            "unchanged_top_level_json": audit[
                "unchanged_top_level_json"
            ],
            "array_prefix_identity": audit["array_prefix_identity"],
            "mesh_identity": audit["mesh_identity"],
            "material_identity": audit["material_identity"],
            "buffer_identity": audit["buffer_identity"],
            "existing_buffer_view_payload_identity": audit[
                "existing_buffer_view_payload_identity"
            ],
            "protected_output_accessors": audit[
                "protected_output_accessors"
            ],
            "passed": (
                audit["v5_json_identity_passed"]
                and audit["v5_payload_identity_passed"]
                and audit["protected_output_identity_passed"]
            ),
        }
        report["v5_payload_identity"] = {
            "locked_payloads_before": v5_image_payloads,
            "before_after": audit["v5_image_payload_identity"],
            "all_basecolor_normal_orm_webp_exact": audit[
                "v5_payload_identity_passed"
            ],
        }
        report["r2x_transplants"] = {
            "append_records": build["append_records"],
            "uv2_output_identity": audit["uv2_output_identity"],
            "ao": audit["ao"],
            "logical_buffer_bytes_before": build[
                "logical_buffer_bytes_before"
            ],
            "logical_buffer_bytes_after": build[
                "logical_buffer_bytes_after"
            ],
            "logical_buffer_growth_bytes": build[
                "logical_buffer_growth_bytes"
            ],
            "uv2_exact": audit["uv2_transplant_identity_passed"],
            "ao_exact": audit["ao_transplant_identity_passed"],
        }
        report["glb_contract"] = {
            "resources": audit["resources"],
            "array_count_expectations": audit[
                "array_count_expectations"
            ],
            "section_nodes_or_meshes": audit[
                "section_nodes_or_meshes"
            ],
            "section_ao_bindings": audit["section_ao_bindings"],
            "section_ao_binding_count": audit[
                "section_ao_binding_count"
            ],
            "all_resources_embedded": (
                audit["resources"]["external_resource_count"] == 0
                and audit["resources"][
                    "missing_embedded_resource_count"
                ]
                == 0
            ),
            "no_local_absolute_paths": (
                audit["resources"]["local_absolute_path_count"] == 0
            ),
            "passed": audit["passed"],
        }
        report["khronos_validator"] = validator
        report["output"] = {
            **artifact_record(OUTPUT_GLB),
            "logical_buffer_bytes": len(final_binary),
            "glb_declared_bytes": final_container["declared_length"],
            "baseline_glb_bytes": v5_container["artifact"]["bytes"],
            "file_growth_bytes": (
                final_container["artifact"]["bytes"]
                - v5_container["artifact"]["bytes"]
            ),
        }
        report["machine_gates"] = {
            "input_locks_passed": report["input_lock"]["all_passed"],
            "candidate_vs_v5_protected_decoded_values_and_order_exact": all(
                semantic["decoded_value_order_exact"]
                and semantic["compact_raw_sequence_exact"]
                and semantic["metadata_exact"]
                for mapping in report["primitive_mapping"]
                for semantic in mapping["protected_semantics"].values()
            ),
            "v5_json_and_mesh_material_baseline_preserved": audit[
                "v5_json_identity_passed"
            ],
            "v5_existing_binary_and_webp_payloads_preserved": audit[
                "v5_payload_identity_passed"
            ],
            "output_protected_accessors_preserved": audit[
                "protected_output_identity_passed"
            ],
            "five_uv2_sequences_exactly_transplanted": audit[
                "uv2_transplant_identity_passed"
            ],
            "single_ao_png_exactly_transplanted": audit[
                "ao_transplant_identity_passed"
            ],
            "section_ao_binding_count_zero": (
                audit["section_ao_binding_count"] == 0
            ),
            "resources_embedded_and_no_absolute_paths": (
                report["glb_contract"]["all_resources_embedded"]
                and report["glb_contract"]["no_local_absolute_paths"]
            ),
            "khronos_validator_zero_errors": validator["errors"] == 0,
            "khronos_validator_zero_warnings": (
                validator["warnings"] == 0
            ),
            "khronos_validator_pinned_version": validator[
                "version_matches_expected"
            ],
            "protected_hashes_unchanged": protected_identity[
                "all_unchanged"
            ],
            "output_published": OUTPUT_GLB.is_file(),
            "all_approval_stop_lines_false": not any(
                APPROVAL_STOP_LINES.values()
            ),
        }
        if not all(report["machine_gates"].values()):
            failed = [
                name
                for name, passed in report["machine_gates"].items()
                if not passed
            ]
            raise RepackError(f"Final machine gate failed: {failed}")
        report["status"] = "passed_smoke_only"
        report["completed_at"] = now_iso()
        report["passed"] = True
        write_json_atomic(REPORT, report)
        return report
    except Exception as exc:
        remove_if_file(TEMP_GLB)
        remove_if_file(OUTPUT_GLB)
        after = protected_snapshot() if before else {}
        if before and after:
            report["protected_hashes_before_after"] = (
                compare_protected_snapshots(before, after)
            )
        report["status"] = "failed_closed"
        report["completed_at"] = now_iso()
        report["passed"] = False
        report["output"] = artifact_record(OUTPUT_GLB)
        report["errors"].append(
            {
                "phase": "v5_payload_repack",
                "type": type(exc).__name__,
                "message": str(exc),
                "traceback": traceback.format_exc(),
            }
        )
        write_json_atomic(REPORT, report)
        raise


def parse_args(argv: list[str]) -> argparse.Namespace:
    """Parse the deliberately narrow command line."""

    parser = argparse.ArgumentParser(
        description=(
            "Fail-closed repack of five R2X TEXCOORD_2 sequences and one "
            "1K AO PNG onto the locked V5 material-review GLB."
        )
    )
    parser.add_argument(
        "--print-report",
        action="store_true",
        help="Print the complete report JSON after a successful run.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    """Command-line entry point."""

    args = parse_args(sys.argv[1:] if argv is None else argv)
    try:
        report = execute()
    except Exception as exc:
        print(
            json.dumps(
                {
                    "status": "failed_closed",
                    "error": str(exc),
                    "report": relative_path(REPORT),
                },
                ensure_ascii=False,
            ),
            file=sys.stderr,
        )
        return 1
    if args.print_report:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print(
            json.dumps(
                {
                    "status": report["status"],
                    "output": report["output"],
                    "report": artifact_record(REPORT),
                    "khronos": report["khronos_validator"],
                    "approval_stop_lines": report[
                        "approval_stop_lines"
                    ],
                },
                ensure_ascii=False,
            )
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
