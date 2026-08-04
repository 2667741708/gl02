r"""Fail-closed, read-only audit for the WEB-60 R2X 1K AO candidate.

Requirement:
    REQ-BF3D-R2X-R2J-AO-REBAKE-CONSUMPTION-20260720

This program never edits or saves a Blend/GLB/PNG.  Normal mode verifies the
locked V5/formal inputs, decodes the candidate GLB and PNG with ordinary
Python, and launches Blender 5.2 twice only as a read-only probe: once for the
locked V5 Blend and once for the R2X candidate.  The two probe snapshots are
compared outside Blender.

The only persistent write made by normal mode is:

    PT/高炉3D模型/work/
      WEB_60_20260720_R2X_R2J_AO_REBAKE_CANDIDATE/
      reports/r2x_ao_smoke1k_v5payload_audit.json

Temporary Blender probe JSON files live in the operating-system temporary
directory and are removed before the process exits.

Examples (PowerShell, from the repository root):

    python tools/audit_bf3d_r2x_ao_candidate.py
    python tools/audit_bf3d_r2x_ao_candidate.py --blender-exe `
      "D:\Program Files\Blender Foundation\Blender 5.2\blender.exe"

Exit codes:
    0: every assertion in this audit scope passed.
    1: evidence was missing, malformed, changed during the audit, or failed a
       mandatory assertion.

Passing this audit does not approve P50, production integration, a 2K bake,
Three.js runtime behavior, or the visual whitelist.  Those stop lines remain
explicitly closed in the emitted report.
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import math
import re
import struct
import subprocess
import sys
import tempfile
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Iterator, Sequence


SCHEMA_VERSION = "bf3d.r2x.ao_smoke1k_v5payload_audit.v2"
BLEND_PROBE_SCHEMA_VERSION = "bf3d.r2x.ao_smoke1k_blend_probe.v1"
REQUIREMENT_ID = "REQ-BF3D-R2X-R2J-AO-REBAKE-CONSUMPTION-20260720"
STAGE_ID = "WEB_60_20260720_R2X_R2J_AO_REBAKE_CANDIDATE"

REPO_ROOT = Path(__file__).resolve().parent.parent
MODULE_ROOT = REPO_ROOT / "PT" / "高炉3D模型"
STAGE_ROOT = MODULE_ROOT / "work" / STAGE_ID
REPORT_DIR = STAGE_ROOT / "reports"
MODEL_ROOT = REPO_ROOT / "高炉前端数据" / "models"

CONTRACT_PATH = STAGE_ROOT / "WEB-60_R2X_阶段预注册合同.md"
V5_BLEND = MODEL_ROOT / "gl02_blast_furnace_review.v5.blend"
V5_MAIN_GLB = MODEL_ROOT / "gl02_blast_furnace_review.v5.glb"
V5_MATERIAL_GLB = MODEL_ROOT / "gl02_blast_furnace_material_review.v5.glb"
V5_STRUCTURAL_GLB = (
    MODEL_ROOT / "gl02_blast_furnace_structural_review.v5.glb"
)
FORMAL_GLB = MODEL_ROOT / "gl02_blast_furnace.glb"
CURRENT_ORM_4K = (
    MODULE_ROOT
    / "work"
    / "INT_30_20260718_R2G_ISOLATED_GLB_WEB_PREVIEW"
    / "textures"
    / "final_4k"
    / "INT30_R2G_R1_LOCK_ORM_4K.png"
)

DEFAULT_CANDIDATE_BLEND = (
    STAGE_ROOT
    / "blends"
    / "gl02_blast_furnace_review.r2x-ao-smoke1k.blend"
)
DEFAULT_AO_PNG = (
    STAGE_ROOT / "textures" / "GL02_R2J_LOCAL_CONTACT_AO_1K.png"
)
DEFAULT_MATERIAL_GLB = (
    STAGE_ROOT
    / "glb"
    / "gl02_blast_furnace_material_review.r2x-ao-smoke1k.v5payload.glb"
)
DEFAULT_BUILD_REPORT = REPORT_DIR / "r2x_ao_smoke1k_build_report.json"
DEFAULT_REPACK_REPORT = REPORT_DIR / "r2x_ao_v5_payload_repack_report.json"
DEFAULT_KHRONOS_REPORT = (
    REPORT_DIR / "khronos_gltf_validator_r2x_ao_v5payload.json"
)
DEFAULT_OUTPUT = REPORT_DIR / "r2x_ao_smoke1k_v5payload_audit.json"
DEFAULT_BLENDER = Path(
    r"D:\Program Files\Blender Foundation\Blender 5.2\blender.exe"
)

LOCKS: dict[str, tuple[Path, str]] = {
    "v5_direct_open_blend": (
        V5_BLEND,
        "3e6df5fb02d3734d14923d4432739a5918ac8249d6a3c8ad1415395429b27e3a",
    ),
    "v5_main_glb": (
        V5_MAIN_GLB,
        "0ac031e626c9eaa0b0cdd8192cf9fda712324af174a4285f563a97309451ed3c",
    ),
    "v5_material_glb": (
        V5_MATERIAL_GLB,
        "652be1b2c9147d5a7392497c7ae4964d19bdd7095b5435b87c105f9eb3fb66bc",
    ),
    "v5_structural_glb": (
        V5_STRUCTURAL_GLB,
        "e5c77d3834c631e2513209a690f6328d1c63dba2c8d489b2d2dbe17645465f71",
    ),
    "formal_glb": (
        FORMAL_GLB,
        "808960f1b2703e7fb27df35f1b1b1a17063b9b10d2267acba593fc3872b62af6",
    ),
    "current_r2g_orm_4k": (
        CURRENT_ORM_4K,
        "e3354cc5d793807ebb4f6b0d74593a7b6f09f18fcece8f9102e867f2c8570e17",
    ),
}

R2J_EXTERIOR_OBJECTS = (
    "R2J_ASM_GL02_FURNACE_BELLY_SHELL_55MM_E",
    "R2J_ASM_GL02_FURNACE_BOSH_SHELL_55MM_E",
    "R2J_ASM_GL02_FURNACE_HEARTH_SHELL_65MM_E",
    "R2J_ASM_GL02_FURNACE_SHAFT_SHELL_45MM_E",
    "R2J_ASM_GL02_FURNACE_THROAT_SHELL_45MM_E",
)
R2J_EXTERIOR_SET = frozenset(R2J_EXTERIOR_OBJECTS)
UV0_NAME = "BF3D_R5_EXTERIOR_UV_1M"
UV1_NAME = "BF3D_INTERNAL_UV_1M"
UV2_NAME = "BF3D_R2X_AO_UV"
EXPECTED_BASE_UVS = (UV0_NAME, UV1_NAME)
EXPECTED_CANDIDATE_UVS = (UV0_NAME, UV1_NAME, UV2_NAME)
AO_IMAGE_TOKEN = "GL02_R2J_LOCAL_CONTACT_AO_1K"
AO_MATERIAL_PREFIX = "R2X_AO_"

GLB_MAGIC = b"glTF"
GLB_JSON_CHUNK = b"JSON"
GLB_BIN_CHUNK = b"BIN\x00"
FLOAT_TOLERANCE = 1.0e-6
UV_OVERLAP_AREA_EPSILON = 1.0e-12

FORBIDDEN_NAME_TOKENS = (
    "P50_UV0",
    "P50_BAKE_APPROVED",
    "P50_LOCAL_CONTACT_AO",
    "APPROX_GL02_FURNACE_",
    "PRODUCTION_APPROVED",
)
REGISTERED_ATTEMPT_HISTORY = (
    {
        "attempt": 1,
        "candidate_glb_sha256": (
            "c8b748ef03b516a78de658a3b25a5f2265fef9bd34cea334a3490fba1fbab139"
        ),
        "result": "fail_closed",
        "finding_code": "UNAUTHORIZED_EXTRA_AO_CLAMP_SAMPLER",
        "finding": (
            "The first V5-payload repack appended a second clamp sampler. "
            "The fixed contract allows only five TEXCOORD_2 accessors plus "
            "one AO image, one AO texture and occlusionTexture bindings; "
            "the AO texture must reuse locked V5 sampler 0."
        ),
        "p50_approved": False,
        "production_integration_allowed": False,
    },
)
WINDOWS_ABSOLUTE_RE = re.compile(
    r"(?i)(?:[a-z]:[\\/]|\\\\[^\\/\s]+[\\/][^\\/\s]+)"
)
FILE_URI_RE = re.compile(r"(?i)\bfile://")


class AuditError(RuntimeError):
    """Raised when mandatory evidence cannot be established unambiguously."""


def now_iso() -> str:
    """Return an RFC 3339 UTC timestamp."""

    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def sha256_bytes(payload: bytes) -> str:
    """Return a lowercase SHA-256 digest for a byte string."""

    return hashlib.sha256(payload).hexdigest()


def sha256_file(path: Path) -> str:
    """Return a lowercase SHA-256 digest for a file."""

    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def is_within(path: Path, root: Path) -> bool:
    """Return whether ``path`` resolves inside ``root``."""

    try:
        path.resolve().relative_to(root.resolve())
    except ValueError:
        return False
    return True


def relative_path(path: Path) -> str:
    """Return a repository-relative POSIX path."""

    try:
        return path.resolve().relative_to(REPO_ROOT.resolve()).as_posix()
    except ValueError as exc:
        raise AuditError(f"Path is outside the repository: {path}") from exc


def artifact_record(
    path: Path,
    expected_sha256: str | None = None,
) -> dict[str, Any]:
    """Return a traceable artifact record and optional lock result."""

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
        record["lock_passed"] = exists and actual == expected_sha256
    return record


def lock_snapshot() -> dict[str, Any]:
    """Measure every immutable V5/formal input."""

    records = {
        name: artifact_record(path, expected)
        for name, (path, expected) in LOCKS.items()
    }
    return {
        "artifacts": records,
        "all_locks_passed": all(
            bool(record["lock_passed"]) for record in records.values()
        ),
    }


def candidate_snapshot(
    blend: Path,
    ao_png: Path,
    material_glb: Path,
    build_report: Path,
    repack_report: Path,
    khronos_report: Path,
) -> dict[str, dict[str, Any]]:
    """Measure all candidate inputs without changing them."""

    return {
        "candidate_blend": artifact_record(blend),
        "ao_png": artifact_record(ao_png),
        "material_glb": artifact_record(material_glb),
        "build_report": artifact_record(build_report),
        "repack_report": artifact_record(repack_report),
        "khronos_report": artifact_record(khronos_report),
    }


def load_json_object(path: Path) -> dict[str, Any]:
    """Load a JSON object, rejecting missing, malformed or non-object input."""

    if not path.is_file():
        raise AuditError(f"Required JSON is missing: {path}")
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise AuditError(f"Invalid JSON: {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise AuditError(f"Expected a JSON object: {path}")
    return value


def write_json(path: Path, value: object) -> None:
    """Write one deterministic UTF-8 JSON report."""

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=False) + "\n",
        encoding="utf-8",
    )


def read_glb(path: Path) -> tuple[dict[str, Any], bytes]:
    """Read and validate a GLB 2.0 JSON/BIN container."""

    if not path.is_file():
        raise AuditError(f"Required GLB is missing: {path}")
    file_size = path.stat().st_size
    with path.open("rb") as stream:
        header = stream.read(12)
        if len(header) != 12:
            raise AuditError(f"Truncated GLB header: {path}")
        magic, version, declared_length = struct.unpack("<4sII", header)
        if magic != GLB_MAGIC or version != 2:
            raise AuditError(f"Not a GLB 2.0 file: {path}")
        if declared_length != file_size:
            raise AuditError(
                f"GLB length mismatch for {path}: "
                f"declared={declared_length}, actual={file_size}"
            )
        chunks: list[tuple[bytes, bytes]] = []
        while stream.tell() < declared_length:
            chunk_header = stream.read(8)
            if len(chunk_header) != 8:
                raise AuditError(f"Truncated GLB chunk header: {path}")
            chunk_length, chunk_type = struct.unpack("<I4s", chunk_header)
            if chunk_length % 4:
                raise AuditError(
                    f"Unaligned GLB chunk length: {chunk_length}: {path}"
                )
            payload = stream.read(chunk_length)
            if len(payload) != chunk_length:
                raise AuditError(f"Truncated GLB chunk payload: {path}")
            chunks.append((chunk_type, payload))
        if stream.tell() != declared_length:
            raise AuditError(f"GLB chunk walk did not end at EOF: {path}")

    json_chunks = [
        payload for chunk_type, payload in chunks
        if chunk_type == GLB_JSON_CHUNK
    ]
    bin_chunks = [
        payload for chunk_type, payload in chunks
        if chunk_type == GLB_BIN_CHUNK
    ]
    if len(json_chunks) != 1 or len(bin_chunks) > 1:
        raise AuditError(
            f"Unexpected GLB chunk cardinality: "
            f"JSON={len(json_chunks)}, BIN={len(bin_chunks)}: {path}"
        )
    try:
        gltf = json.loads(
            json_chunks[0].decode("utf-8").rstrip(" \t\r\n\x00")
        )
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise AuditError(f"Invalid GLB JSON chunk: {path}: {exc}") from exc
    if not isinstance(gltf, dict):
        raise AuditError(f"GLB JSON root is not an object: {path}")
    return gltf, bin_chunks[0] if bin_chunks else b""


def buffer_view_payload(
    gltf: dict[str, Any],
    binary: bytes,
    view_index: int,
) -> bytes:
    """Return one embedded buffer-view payload."""

    views = gltf.get("bufferViews") or []
    if not isinstance(view_index, int) or not (0 <= view_index < len(views)):
        raise AuditError(f"bufferView index out of range: {view_index}")
    view = views[view_index]
    if not isinstance(view, dict) or int(view.get("buffer", 0)) != 0:
        raise AuditError(
            f"External or multi-buffer view is outside the R2X contract: "
            f"{view_index}"
        )
    offset = int(view.get("byteOffset", 0))
    length = int(view.get("byteLength", -1))
    end = offset + length
    if offset < 0 or length < 0 or end > len(binary):
        raise AuditError(
            f"Invalid bufferView range: index={view_index}, "
            f"offset={offset}, length={length}, bin={len(binary)}"
        )
    return binary[offset:end]


def _walk_json(
    value: Any,
    pointer: str = "",
) -> Iterator[tuple[str, str | None, Any]]:
    """Yield every JSON value with a JSON-pointer-like location and key."""

    if isinstance(value, dict):
        for key, child in value.items():
            child_pointer = f"{pointer}/{key}"
            yield child_pointer, str(key), child
            yield from _walk_json(child, child_pointer)
    elif isinstance(value, list):
        for index, child in enumerate(value):
            child_pointer = f"{pointer}/{index}"
            yield child_pointer, None, child
            yield from _walk_json(child, child_pointer)


def glb_path_and_name_findings(gltf: dict[str, Any]) -> dict[str, Any]:
    """Find forbidden identifiers and local absolute paths in GLB JSON."""

    forbidden: list[dict[str, str]] = []
    absolute: list[dict[str, str]] = []
    for pointer, key, value in _walk_json(gltf):
        if not isinstance(value, str):
            continue
        upper = value.upper()
        if key == "name":
            for token in FORBIDDEN_NAME_TOKENS:
                if token.upper() in upper:
                    forbidden.append(
                        {
                            "pointer": pointer,
                            "value": value,
                            "token": token,
                        }
                    )
        is_web_uri = bool(re.match(r"(?i)^(?:https?|data):", value))
        posix_absolute = value.startswith("/") and not is_web_uri
        if (
            WINDOWS_ABSOLUTE_RE.search(value)
            or FILE_URI_RE.search(value)
            or posix_absolute
        ):
            absolute.append({"pointer": pointer, "value": value})
    return {
        "forbidden_names": forbidden,
        "forbidden_name_count": len(forbidden),
        "local_absolute_paths": absolute,
        "local_absolute_path_count": len(absolute),
    }


def glb_external_resource_findings(
    gltf: dict[str, Any],
) -> dict[str, Any]:
    """List external/missing buffer and image resources."""

    external: list[dict[str, Any]] = []
    missing: list[dict[str, Any]] = []
    buffers = gltf.get("buffers") or []
    if len(buffers) != 1:
        missing.append(
            {
                "kind": "buffer_cardinality",
                "expected": 1,
                "actual": len(buffers),
            }
        )
    for index, buffer in enumerate(buffers):
        if not isinstance(buffer, dict):
            missing.append({"kind": "invalid_buffer", "index": index})
            continue
        if buffer.get("uri") is not None:
            external.append(
                {
                    "kind": "buffer_uri",
                    "index": index,
                    "uri": buffer.get("uri"),
                }
            )
    for index, image in enumerate(gltf.get("images") or []):
        if not isinstance(image, dict):
            missing.append({"kind": "invalid_image", "index": index})
            continue
        if image.get("uri") is not None:
            external.append(
                {
                    "kind": "image_uri",
                    "index": index,
                    "uri": image.get("uri"),
                }
            )
        if image.get("bufferView") is None:
            missing.append(
                {
                    "kind": "image_without_buffer_view",
                    "index": index,
                    "name": image.get("name"),
                }
            )
        if not image.get("mimeType"):
            missing.append(
                {
                    "kind": "image_without_mime_type",
                    "index": index,
                    "name": image.get("name"),
                }
            )
    return {
        "external_resources": external,
        "external_resource_count": len(external),
        "missing_resources": missing,
        "missing_resource_count": len(missing),
    }


def texture_descriptor(
    gltf: dict[str, Any],
    binary: bytes,
    texture_info: dict[str, Any] | None,
) -> dict[str, Any] | None:
    """Resolve a glTF textureInfo to its embedded image and UV channel."""

    if texture_info is None:
        return None
    if not isinstance(texture_info, dict) or "index" not in texture_info:
        raise AuditError("Malformed glTF textureInfo")
    textures = gltf.get("textures") or []
    texture_index = int(texture_info["index"])
    if not (0 <= texture_index < len(textures)):
        raise AuditError(f"Texture index out of range: {texture_index}")
    texture = textures[texture_index]
    if not isinstance(texture, dict):
        raise AuditError(f"Texture entry is not an object: {texture_index}")

    source = texture.get("source")
    extensions = texture.get("extensions") or {}
    for extension_name in ("KHR_texture_basisu", "EXT_texture_webp"):
        extension = extensions.get(extension_name) or {}
        if source is None and isinstance(extension, dict):
            source = extension.get("source")
    if source is None:
        raise AuditError(f"Texture has no image source: {texture_index}")
    image_index = int(source)
    images = gltf.get("images") or []
    if not (0 <= image_index < len(images)):
        raise AuditError(f"Image index out of range: {image_index}")
    image = images[image_index]
    if not isinstance(image, dict):
        raise AuditError(f"Image entry is not an object: {image_index}")

    transform = (texture_info.get("extensions") or {}).get(
        "KHR_texture_transform"
    ) or {}
    if not isinstance(transform, dict):
        raise AuditError("KHR_texture_transform is not an object")
    declared_texcoord = int(texture_info.get("texCoord", 0))
    effective_texcoord = int(transform.get("texCoord", declared_texcoord))
    payload: bytes | None = None
    if image.get("bufferView") is not None:
        payload = buffer_view_payload(
            gltf, binary, int(image["bufferView"])
        )
    return {
        "texture_index": texture_index,
        "texture_name": texture.get("name"),
        "image_index": image_index,
        "image_name": image.get("name"),
        "image_mime_type": image.get("mimeType"),
        "image_uri": image.get("uri"),
        "image_buffer_view": image.get("bufferView"),
        "embedded_payload_bytes": len(payload) if payload is not None else None,
        "embedded_payload_sha256": (
            sha256_bytes(payload) if payload is not None else None
        ),
        "declared_texcoord": declared_texcoord,
        "effective_texcoord": effective_texcoord,
        "required_attribute": f"TEXCOORD_{effective_texcoord}",
        "texture_transform": transform or None,
        "strength": texture_info.get("strength"),
        "scale": texture_info.get("scale"),
        "_payload": payload,
    }


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
    "MAT2": 4,
    "MAT3": 9,
    "MAT4": 16,
}


def iter_accessor_values(
    gltf: dict[str, Any],
    binary: bytes,
    accessor_index: int,
) -> Iterator[tuple[float, ...]]:
    """Decode a non-sparse glTF accessor, honoring stride and normalization."""

    accessors = gltf.get("accessors") or []
    if not (0 <= accessor_index < len(accessors)):
        raise AuditError(f"Accessor index out of range: {accessor_index}")
    accessor = accessors[accessor_index]
    if not isinstance(accessor, dict):
        raise AuditError(f"Accessor is not an object: {accessor_index}")
    if accessor.get("sparse") is not None:
        raise AuditError(
            f"Sparse accessor is outside this R2X audit contract: "
            f"{accessor_index}"
        )
    view_index = accessor.get("bufferView")
    if view_index is None:
        raise AuditError(f"Accessor has no bufferView: {accessor_index}")
    views = gltf.get("bufferViews") or []
    view_index = int(view_index)
    if not (0 <= view_index < len(views)):
        raise AuditError(
            f"Accessor bufferView is out of range: {accessor_index}"
        )
    view = views[view_index]
    if not isinstance(view, dict) or int(view.get("buffer", 0)) != 0:
        raise AuditError(
            f"Accessor uses an external/multi-buffer view: {accessor_index}"
        )
    component_type = int(accessor.get("componentType", 0))
    if component_type not in COMPONENT_FORMATS:
        raise AuditError(
            f"Unsupported accessor component type: {component_type}"
        )
    accessor_type = str(accessor.get("type", ""))
    components = TYPE_COMPONENT_COUNTS.get(accessor_type)
    if components is None:
        raise AuditError(f"Unsupported accessor type: {accessor_type}")
    format_char, component_bytes, signed, normalization_denominator = (
        COMPONENT_FORMATS[component_type]
    )
    element_bytes = components * component_bytes
    stride = int(view.get("byteStride", element_bytes))
    if stride < element_bytes:
        raise AuditError(
            f"Accessor stride is too small: accessor={accessor_index}"
        )
    view_offset = int(view.get("byteOffset", 0))
    view_length = int(view.get("byteLength", -1))
    accessor_offset = int(accessor.get("byteOffset", 0))
    count = int(accessor.get("count", -1))
    if min(view_offset, view_length, accessor_offset, count) < 0:
        raise AuditError(f"Negative accessor range: {accessor_index}")
    start = view_offset + accessor_offset
    end = start + max(count - 1, 0) * stride + (
        element_bytes if count else 0
    )
    if (
        start < view_offset
        or end > view_offset + view_length
        or end > len(binary)
    ):
        raise AuditError(
            f"Accessor exceeds its bufferView: {accessor_index}"
        )
    unpacker = struct.Struct("<" + format_char * components)
    normalized = bool(accessor.get("normalized", False))
    for item_index in range(count):
        raw = unpacker.unpack_from(binary, start + item_index * stride)
        if normalized and normalization_denominator is not None:
            if signed:
                values = tuple(
                    max(float(value) / normalization_denominator, -1.0)
                    for value in raw
                )
            else:
                values = tuple(
                    float(value) / normalization_denominator for value in raw
                )
        else:
            values = tuple(float(value) for value in raw)
        yield values


def texcoord_accessor_statistics(
    gltf: dict[str, Any],
    binary: bytes,
    accessor_index: int,
) -> dict[str, Any]:
    """Measure finiteness and [0,1] range for a TEXCOORD accessor."""

    accessors = gltf.get("accessors") or []
    accessor = accessors[accessor_index]
    if accessor.get("type") != "VEC2":
        raise AuditError(
            f"TEXCOORD accessor is not VEC2: {accessor_index}"
        )
    count = 0
    non_finite = 0
    out_of_range = 0
    minimum = [math.inf, math.inf]
    maximum = [-math.inf, -math.inf]
    digest = hashlib.sha256()
    for vector in iter_accessor_values(gltf, binary, accessor_index):
        count += 1
        if len(vector) != 2:
            raise AuditError(
                f"TEXCOORD accessor did not decode to VEC2: {accessor_index}"
            )
        for axis, value in enumerate(vector):
            digest.update(struct.pack("<d", value))
            if not math.isfinite(value):
                non_finite += 1
                continue
            minimum[axis] = min(minimum[axis], value)
            maximum[axis] = max(maximum[axis], value)
            if value < -FLOAT_TOLERANCE or value > 1.0 + FLOAT_TOLERANCE:
                out_of_range += 1
    if count <= 0:
        raise AuditError(f"Empty TEXCOORD accessor: {accessor_index}")
    return {
        "accessor_index": accessor_index,
        "count": count,
        "component_type": accessor.get("componentType"),
        "normalized": bool(accessor.get("normalized", False)),
        "minimum": minimum,
        "maximum": maximum,
        "non_finite_component_count": non_finite,
        "out_of_unit_range_component_count": out_of_range,
        "all_finite": non_finite == 0,
        "in_unit_range": non_finite == 0 and out_of_range == 0,
        "decoded_loop_sha256": digest.hexdigest(),
    }


def full_mip_rgba8_bytes(width: int, height: int) -> int:
    """Return exact RGBA8 bytes for a complete mip pyramid."""

    total = 0
    current_width = width
    current_height = height
    while True:
        total += current_width * current_height * 4
        if current_width == 1 and current_height == 1:
            return total
        current_width = max(1, current_width // 2)
        current_height = max(1, current_height // 2)


def _channel_statistics(
    histogram: Sequence[int],
    pixel_count: int,
) -> dict[str, Any]:
    """Return exact 8-bit channel statistics from a 256-bin histogram."""

    observed = [index for index, count in enumerate(histogram) if count]
    if pixel_count <= 0 or not observed:
        raise AuditError("Empty image channel histogram")
    mean = sum(
        value * count for value, count in enumerate(histogram)
    ) / pixel_count
    variance = sum(
        ((value - mean) ** 2) * count
        for value, count in enumerate(histogram)
    ) / pixel_count
    nonwhite = pixel_count - int(histogram[255])
    return {
        "min_u8": observed[0],
        "max_u8": observed[-1],
        "mean_u8": mean,
        "stddev_u8": math.sqrt(max(variance, 0.0)),
        "white_sample_count": int(histogram[255]),
        "nonwhite_sample_count": nonwhite,
        "nonwhite_ratio": nonwhite / pixel_count,
        "threshold_distribution": {
            "0_63": int(sum(histogram[0:64])),
            "64_127": int(sum(histogram[64:128])),
            "128_191": int(sum(histogram[128:192])),
            "192_254": int(sum(histogram[192:255])),
            "255": int(histogram[255]),
            "lt_255": nonwhite,
            "le_204": int(sum(histogram[0:205])),
            "le_229": int(sum(histogram[0:230])),
            "le_242": int(sum(histogram[0:243])),
        },
    }


def decode_image_red(
    payload: bytes,
    source_label: str,
) -> dict[str, Any]:
    """Decode image bytes and return the exact R-channel signature."""

    try:
        from PIL import Image
    except ImportError as exc:
        raise AuditError(
            "Pillow is required for exact PNG R-channel auditing"
        ) from exc
    try:
        with Image.open(io.BytesIO(payload)) as source:
            source.load()
            source_format = source.format
            source_mode = source.mode
            rgba = source.convert("RGBA")
            width, height = rgba.size
            red_bytes = rgba.getchannel("R").tobytes()
            histogram = rgba.getchannel("R").histogram()
    except Exception as exc:
        raise AuditError(
            f"Cannot decode image {source_label}: {exc}"
        ) from exc
    pixel_count = width * height
    if len(red_bytes) != pixel_count or len(histogram) != 256:
        raise AuditError(f"Unexpected decoded image size: {source_label}")
    return {
        "source_format": source_format,
        "source_mode": source_mode,
        "decoded_mode": "RGBA",
        "width": width,
        "height": height,
        "pixel_count": pixel_count,
        "red_channel_sha256": sha256_bytes(red_bytes),
        "red": _channel_statistics(histogram, pixel_count),
    }


def png_statistics(path: Path) -> dict[str, Any]:
    """Decode the candidate AO PNG and return exact R-channel statistics."""

    if not path.is_file():
        raise AuditError(f"Candidate AO PNG is missing: {path}")
    payload = path.read_bytes()
    decoded = decode_image_red(payload, relative_path(path))
    width = int(decoded["width"])
    height = int(decoded["height"])
    decoded.update(
        {
            "artifact": artifact_record(path),
            "payload_sha256": sha256_bytes(payload),
            "decoded_rgba8_bytes": width * height * 4,
            "decoded_rgba8_mib": width * height * 4 / (1024 * 1024),
            "decoded_rgba8_with_full_mips_bytes": full_mip_rgba8_bytes(
                width, height
            ),
            "decoded_rgba8_with_full_mips_mib": full_mip_rgba8_bytes(
                width, height
            )
            / (1024 * 1024),
            "red_channel_is_uniform_white": (
                decoded["red"]["nonwhite_sample_count"] == 0
            ),
            "red_channel_has_variation": decoded["red"]["stddev_u8"] > 0.0,
        }
    )
    return decoded


def expected_mesh_name(object_name: str) -> str:
    """Return the exact Blender-exported mesh name for an R2J object."""

    return f"{object_name}_MESH"


def audit_material_glb(
    path: Path,
    *,
    require_ao: bool,
) -> dict[str, Any]:
    """Audit the five R2J exterior primitives in a material-review GLB."""

    gltf, binary = read_glb(path)
    materials = gltf.get("materials") or []
    path_findings = glb_path_and_name_findings(gltf)
    resource_findings = glb_external_resource_findings(gltf)
    records: dict[str, dict[str, Any]] = {}
    matched_mesh_indices: set[int] = set()
    section_meshes: list[str] = []
    primitive_count = 0

    for mesh_index, mesh in enumerate(gltf.get("meshes") or []):
        if not isinstance(mesh, dict):
            raise AuditError(f"GLB mesh is not an object: {mesh_index}")
        mesh_name = str(mesh.get("name") or f"mesh_{mesh_index}")
        primitives = mesh.get("primitives") or []
        primitive_count += len(primitives)
        if mesh_name.startswith("SECTION_"):
            section_meshes.append(mesh_name)
        target = next(
            (
                name
                for name in R2J_EXTERIOR_OBJECTS
                if mesh_name in (name, expected_mesh_name(name))
            ),
            None,
        )
        if target is None:
            continue
        if target in records:
            raise AuditError(f"Duplicate R2J exterior mesh in GLB: {target}")
        if len(primitives) != 1:
            raise AuditError(
                f"R2J material-review mesh must have one primitive: "
                f"{target}: {len(primitives)}"
            )
        primitive = primitives[0]
        if not isinstance(primitive, dict):
            raise AuditError(f"Malformed primitive for {target}")
        material_index = primitive.get("material")
        if material_index is None:
            raise AuditError(f"R2J primitive has no material: {target}")
        material_index = int(material_index)
        if not (0 <= material_index < len(materials)):
            raise AuditError(
                f"R2J material index out of range: "
                f"{target}:{material_index}"
            )
        material = materials[material_index]
        if not isinstance(material, dict):
            raise AuditError(f"Malformed material: {material_index}")
        pbr = material.get("pbrMetallicRoughness") or {}
        if not isinstance(pbr, dict):
            raise AuditError(f"Malformed PBR block: {target}")

        bindings = {
            "baseColorTexture": texture_descriptor(
                gltf, binary, pbr.get("baseColorTexture")
            ),
            "metallicRoughnessTexture": texture_descriptor(
                gltf, binary, pbr.get("metallicRoughnessTexture")
            ),
            "normalTexture": texture_descriptor(
                gltf, binary, material.get("normalTexture")
            ),
            "occlusionTexture": texture_descriptor(
                gltf, binary, material.get("occlusionTexture")
            ),
        }
        attributes = primitive.get("attributes") or {}
        if not isinstance(attributes, dict):
            raise AuditError(f"Malformed primitive attributes: {target}")
        texcoord_presence = {
            f"TEXCOORD_{index}": f"TEXCOORD_{index}" in attributes
            for index in range(3)
        }
        bound_attribute_checks = []
        for semantic, descriptor in bindings.items():
            if descriptor is None:
                continue
            required_attribute = descriptor["required_attribute"]
            bound_attribute_checks.append(
                {
                    "semantic": semantic,
                    "required_attribute": required_attribute,
                    "present": required_attribute in attributes,
                }
            )
        uv2_statistics = None
        if "TEXCOORD_2" in attributes:
            uv2_statistics = texcoord_accessor_statistics(
                gltf, binary, int(attributes["TEXCOORD_2"])
            )

        occlusion_red = None
        occlusion = bindings["occlusionTexture"]
        if occlusion is not None and occlusion.get("_payload") is not None:
            occlusion_red = decode_image_red(
                occlusion["_payload"],
                f"{relative_path(path)}:{target}:occlusionTexture",
            )
        public_bindings: dict[str, Any] = {}
        for semantic, descriptor in bindings.items():
            if descriptor is None:
                public_bindings[semantic] = None
            else:
                public_bindings[semantic] = {
                    key: value
                    for key, value in descriptor.items()
                    if key != "_payload"
                }

        records[target] = {
            "mesh_index": mesh_index,
            "mesh_name": mesh_name,
            "primitive_index": 0,
            "material_index": material_index,
            "material_name": material.get("name"),
            "primitive_attributes": sorted(attributes),
            "texcoord_presence": texcoord_presence,
            "bound_attribute_checks": bound_attribute_checks,
            "all_bound_attributes_present": all(
                item["present"] for item in bound_attribute_checks
            ),
            "texture_bindings": public_bindings,
            "uv2_statistics": uv2_statistics,
            "occlusion_red_channel": occlusion_red,
            "material_factors": {
                "baseColorFactor": pbr.get(
                    "baseColorFactor", [1.0, 1.0, 1.0, 1.0]
                ),
                "metallicFactor": pbr.get("metallicFactor", 1.0),
                "roughnessFactor": pbr.get("roughnessFactor", 1.0),
                "normalScale": (
                    material.get("normalTexture") or {}
                ).get("scale", 1.0),
                "alphaMode": material.get("alphaMode", "OPAQUE"),
                "alphaCutoff": material.get("alphaCutoff", 0.5),
                "doubleSided": bool(material.get("doubleSided", False)),
                "emissiveFactor": material.get(
                    "emissiveFactor", [0.0, 0.0, 0.0]
                ),
            },
        }
        matched_mesh_indices.add(mesh_index)

    image_records = []
    for image_index, image in enumerate(gltf.get("images") or []):
        if not isinstance(image, dict):
            continue
        payload = None
        if image.get("bufferView") is not None:
            payload = buffer_view_payload(
                gltf, binary, int(image["bufferView"])
            )
        image_records.append(
            {
                "image_index": image_index,
                "name": image.get("name"),
                "mime_type": image.get("mimeType"),
                "uri": image.get("uri"),
                "embedded": payload is not None,
                "payload_bytes": len(payload) if payload is not None else None,
                "payload_sha256": (
                    sha256_bytes(payload) if payload is not None else None
                ),
            }
        )

    missing_targets = sorted(R2J_EXTERIOR_SET.difference(records))
    extra_meshes = [
        str(mesh.get("name") or f"mesh_{index}")
        for index, mesh in enumerate(gltf.get("meshes") or [])
        if index not in matched_mesh_indices
    ]
    return {
        "artifact": artifact_record(path),
        "asset": gltf.get("asset"),
        "scene_count": len(gltf.get("scenes") or []),
        "node_count": len(gltf.get("nodes") or []),
        "mesh_count": len(gltf.get("meshes") or []),
        "primitive_count": primitive_count,
        "material_count": len(materials),
        "texture_count": len(gltf.get("textures") or []),
        "image_count": len(gltf.get("images") or []),
        "images": image_records,
        "r2j_exterior_primitive_count": len(records),
        "r2j_exterior_primitives": records,
        "missing_targets": missing_targets,
        "extra_meshes": extra_meshes,
        "section_meshes": section_meshes,
        "path_and_name_findings": path_findings,
        "resource_findings": resource_findings,
        "require_ao": require_ao,
    }


def compare_material_glbs(
    baseline: dict[str, Any],
    candidate: dict[str, Any],
    ao_png: dict[str, Any],
) -> dict[str, Any]:
    """Compare candidate texture bindings against locked V5 material GLB."""

    target_results: dict[str, Any] = {}
    ao_image_indices: set[int] = set()
    ao_payload_hashes: set[str] = set()
    all_results: list[bool] = []
    for target in R2J_EXTERIOR_OBJECTS:
        base = baseline["r2j_exterior_primitives"].get(target)
        current = candidate["r2j_exterior_primitives"].get(target)
        if base is None or current is None:
            target_results[target] = {
                "evidence_complete": False,
                "passed": False,
            }
            all_results.append(False)
            continue
        bindings = current["texture_bindings"]
        base_bindings = base["texture_bindings"]
        texcoord_checks = {
            semantic: (
                bindings.get(semantic) is not None
                and bindings[semantic]["declared_texcoord"] == expected
                and bindings[semantic]["effective_texcoord"] == expected
            )
            for semantic, expected in (
                ("baseColorTexture", 0),
                ("metallicRoughnessTexture", 0),
                ("normalTexture", 0),
                ("occlusionTexture", 2),
            )
        }
        preserved_payload_checks = {
            semantic: (
                bindings.get(semantic) is not None
                and base_bindings.get(semantic) is not None
                and bindings[semantic]["embedded_payload_sha256"]
                == base_bindings[semantic]["embedded_payload_sha256"]
            )
            for semantic in (
                "baseColorTexture",
                "metallicRoughnessTexture",
                "normalTexture",
            )
        }
        factor_preserved = (
            current["material_factors"] == base["material_factors"]
        )
        attributes = current["texcoord_presence"]
        all_three_texcoords = all(
            attributes.get(f"TEXCOORD_{index}") is True
            for index in range(3)
        )
        uv2 = current.get("uv2_statistics") or {}
        uv2_valid = (
            uv2.get("all_finite") is True
            and uv2.get("in_unit_range") is True
        )
        occlusion = bindings.get("occlusionTexture")
        occlusion_red = current.get("occlusion_red_channel") or {}
        ao_red_matches_png = (
            occlusion_red.get("width") == ao_png["width"]
            and occlusion_red.get("height") == ao_png["height"]
            and occlusion_red.get("red_channel_sha256")
            == ao_png["red_channel_sha256"]
        )
        ao_is_embedded_png = bool(
            occlusion
            and occlusion.get("image_uri") is None
            and occlusion.get("image_buffer_view") is not None
            and str(occlusion.get("image_mime_type") or "").lower()
            == "image/png"
        )
        if occlusion is not None:
            ao_image_indices.add(int(occlusion["image_index"]))
            payload_hash = occlusion.get("embedded_payload_sha256")
            if payload_hash:
                ao_payload_hashes.add(str(payload_hash))
        material_name_preserves_locked_v5 = (
            current.get("material_name") == base.get("material_name")
        )
        checks = {
            "all_texcoord_0_1_2_present": all_three_texcoords,
            "all_bound_attributes_present": bool(
                current["all_bound_attributes_present"]
            ),
            "basecolor_mr_normal_texcoord_0_and_occlusion_texcoord_2": all(
                texcoord_checks.values()
            ),
            "basecolor_mr_normal_payloads_match_locked_v5": all(
                preserved_payload_checks.values()
            ),
            "material_factors_match_locked_v5": factor_preserved,
            "uv2_accessor_finite_and_in_unit_range": uv2_valid,
            "ao_image_is_embedded_png": ao_is_embedded_png,
            "ao_image_red_channel_matches_candidate_png": ao_red_matches_png,
            "material_name_preserves_locked_v5": (
                material_name_preserves_locked_v5
            ),
        }
        passed = all(checks.values())
        all_results.append(passed)
        target_results[target] = {
            "texcoord_checks": texcoord_checks,
            "preserved_payload_checks": preserved_payload_checks,
            "factor_preserved": factor_preserved,
            "checks": checks,
            "passed": passed,
        }
    return {
        "targets": target_results,
        "unique_occlusion_image_indices": sorted(ao_image_indices),
        "unique_occlusion_payload_sha256": sorted(ao_payload_hashes),
        "all_targets_share_one_occlusion_image": len(ao_image_indices) == 1,
        "all_targets_passed": all(all_results) and len(all_results) == 5,
    }


def canonical_json_sha256(value: Any) -> str:
    """Hash a JSON-compatible value with deterministic key ordering."""

    payload = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return sha256_bytes(payload)


def accessor_decoded_identity(
    gltf: dict[str, Any],
    binary: bytes,
    accessor_index: int,
) -> dict[str, Any]:
    """Return metadata and a canonical decoded-value hash for one accessor."""

    accessors = gltf.get("accessors") or []
    if not (0 <= accessor_index < len(accessors)):
        raise AuditError(f"Accessor index out of range: {accessor_index}")
    accessor = accessors[accessor_index]
    digest = hashlib.sha256()
    decoded_count = 0
    component_count = None
    all_finite = True
    for vector in iter_accessor_values(gltf, binary, accessor_index):
        decoded_count += 1
        if component_count is None:
            component_count = len(vector)
        elif component_count != len(vector):
            raise AuditError(
                f"Accessor changed vector width while decoding: "
                f"{accessor_index}"
            )
        digest.update(struct.pack("<I", len(vector)))
        for value in vector:
            digest.update(struct.pack("<d", float(value)))
            all_finite = all_finite and math.isfinite(float(value))
    return {
        "accessor_index": accessor_index,
        "metadata": accessor,
        "metadata_sha256": canonical_json_sha256(accessor),
        "decoded_element_count": decoded_count,
        "decoded_component_count": component_count,
        "decoded_value_sha256": digest.hexdigest(),
        "all_decoded_values_finite": all_finite,
    }


def buffer_view_identity(
    gltf: dict[str, Any],
    binary: bytes,
    view_index: int,
) -> dict[str, Any]:
    """Return metadata and exact payload identity for one bufferView."""

    views = gltf.get("bufferViews") or []
    if not (0 <= view_index < len(views)):
        raise AuditError(f"bufferView index out of range: {view_index}")
    metadata = views[view_index]
    payload = buffer_view_payload(gltf, binary, view_index)
    return {
        "buffer_view_index": view_index,
        "metadata": metadata,
        "metadata_sha256": canonical_json_sha256(metadata),
        "payload_bytes": len(payload),
        "payload_sha256": sha256_bytes(payload),
    }


def _without_key(value: dict[str, Any], key: str) -> dict[str, Any]:
    """Return a shallow JSON mapping copy without one field."""

    return {
        item_key: item_value
        for item_key, item_value in value.items()
        if item_key != key
    }


def audit_v5_payload_identity(
    baseline_path: Path,
    candidate_path: Path,
    ao_png_path: Path,
) -> dict[str, Any]:
    """Prove a surgical V5-payload GLB differs only by the R2X AO contract.

    The comparison is index-preserving and fail-closed.  Every original
    accessor, bufferView, WebP image payload, texture, sampler, material field,
    node, scene and non-target primitive remains byte/JSON identical.  The
    only admitted additions are five TEXCOORD_2 accessors/bufferViews, one AO
    image/bufferView, one AO texture, and an occlusionTexture field on the
    pre-existing materials used by the five R2J exterior primitives.
    """

    baseline, baseline_binary = read_glb(baseline_path)
    candidate, candidate_binary = read_glb(candidate_path)
    ao_payload = ao_png_path.read_bytes()

    baseline_views = baseline.get("bufferViews") or []
    candidate_views = candidate.get("bufferViews") or []
    baseline_accessors = baseline.get("accessors") or []
    candidate_accessors = candidate.get("accessors") or []
    baseline_images = baseline.get("images") or []
    candidate_images = candidate.get("images") or []
    baseline_textures = baseline.get("textures") or []
    candidate_textures = candidate.get("textures") or []
    baseline_samplers = baseline.get("samplers") or []
    candidate_samplers = candidate.get("samplers") or []
    baseline_materials = baseline.get("materials") or []
    candidate_materials = candidate.get("materials") or []
    baseline_meshes = baseline.get("meshes") or []
    candidate_meshes = candidate.get("meshes") or []

    existing_view_results = []
    for index in range(len(baseline_views)):
        before = buffer_view_identity(
            baseline, baseline_binary, index
        )
        after = (
            buffer_view_identity(candidate, candidate_binary, index)
            if index < len(candidate_views)
            else None
        )
        existing_view_results.append(
            {
                "index": index,
                "before": before,
                "after": after,
                "metadata_equal": (
                    after is not None
                    and before["metadata"] == after["metadata"]
                ),
                "payload_byte_equal": (
                    after is not None
                    and before["payload_sha256"]
                    == after["payload_sha256"]
                    and before["payload_bytes"] == after["payload_bytes"]
                ),
            }
        )

    existing_accessor_results = []
    for index in range(len(baseline_accessors)):
        before = accessor_decoded_identity(
            baseline, baseline_binary, index
        )
        after = (
            accessor_decoded_identity(candidate, candidate_binary, index)
            if index < len(candidate_accessors)
            else None
        )
        existing_accessor_results.append(
            {
                "index": index,
                "metadata_equal": (
                    after is not None
                    and before["metadata"] == after["metadata"]
                ),
                "decoded_values_equal": (
                    after is not None
                    and before["decoded_value_sha256"]
                    == after["decoded_value_sha256"]
                    and before["decoded_element_count"]
                    == after["decoded_element_count"]
                    and before["decoded_component_count"]
                    == after["decoded_component_count"]
                ),
                "before": before,
                "after": after,
            }
        )

    existing_image_results = []
    for index, image in enumerate(baseline_images):
        before_payload = (
            buffer_view_payload(
                baseline, baseline_binary, int(image["bufferView"])
            )
            if isinstance(image, dict) and "bufferView" in image
            else None
        )
        after_image = (
            candidate_images[index]
            if index < len(candidate_images)
            else None
        )
        after_payload = (
            buffer_view_payload(
                candidate,
                candidate_binary,
                int(after_image["bufferView"]),
            )
            if isinstance(after_image, dict)
            and "bufferView" in after_image
            else None
        )
        existing_image_results.append(
            {
                "index": index,
                "name": (
                    image.get("name") if isinstance(image, dict) else None
                ),
                "mime_type": (
                    image.get("mimeType")
                    if isinstance(image, dict)
                    else None
                ),
                "json_equal": after_image == image,
                "payload_bytes_equal": (
                    before_payload is not None
                    and after_payload is not None
                    and before_payload == after_payload
                ),
                "baseline_payload_sha256": (
                    sha256_bytes(before_payload)
                    if before_payload is not None
                    else None
                ),
                "candidate_payload_sha256": (
                    sha256_bytes(after_payload)
                    if after_payload is not None
                    else None
                ),
            }
        )

    extra_image_indices = list(
        range(len(baseline_images), len(candidate_images))
    )
    extra_texture_indices = list(
        range(len(baseline_textures), len(candidate_textures))
    )
    new_ao_image_index = (
        extra_image_indices[0] if len(extra_image_indices) == 1 else None
    )
    new_ao_texture_index = (
        extra_texture_indices[0]
        if len(extra_texture_indices) == 1
        else None
    )
    new_ao_image = (
        candidate_images[new_ao_image_index]
        if new_ao_image_index is not None
        else None
    )
    new_ao_image_payload = (
        buffer_view_payload(
            candidate,
            candidate_binary,
            int(new_ao_image["bufferView"]),
        )
        if isinstance(new_ao_image, dict)
        and "bufferView" in new_ao_image
        else None
    )
    new_ao_texture = (
        candidate_textures[new_ao_texture_index]
        if new_ao_texture_index is not None
        else None
    )

    baseline_mesh_by_name = {
        str(mesh.get("name") or f"mesh_{index}"): (index, mesh)
        for index, mesh in enumerate(baseline_meshes)
    }
    candidate_mesh_by_name = {
        str(mesh.get("name") or f"mesh_{index}"): (index, mesh)
        for index, mesh in enumerate(candidate_meshes)
    }
    protected_semantics = (
        "POSITION",
        "NORMAL",
        "TANGENT",
        "TEXCOORD_0",
        "TEXCOORD_1",
    )
    target_results: dict[str, Any] = {}
    new_uv2_accessor_indices: set[int] = set()
    target_material_indices: set[int] = set()
    for target in R2J_EXTERIOR_OBJECTS:
        mesh_name = expected_mesh_name(target)
        baseline_entry = baseline_mesh_by_name.get(mesh_name)
        candidate_entry = candidate_mesh_by_name.get(mesh_name)
        if baseline_entry is None or candidate_entry is None:
            target_results[target] = {
                "present_in_both": False,
                "passed": False,
            }
            continue
        baseline_mesh_index, baseline_mesh = baseline_entry
        candidate_mesh_index, candidate_mesh = candidate_entry
        baseline_primitives = baseline_mesh.get("primitives") or []
        candidate_primitives = candidate_mesh.get("primitives") or []
        if len(baseline_primitives) != 1 or len(candidate_primitives) != 1:
            target_results[target] = {
                "present_in_both": True,
                "single_primitive_before_after": False,
                "passed": False,
            }
            continue
        before_primitive = baseline_primitives[0]
        after_primitive = candidate_primitives[0]
        before_attributes = before_primitive.get("attributes") or {}
        after_attributes = after_primitive.get("attributes") or {}
        uv2_accessor = after_attributes.get("TEXCOORD_2")
        if isinstance(uv2_accessor, int):
            new_uv2_accessor_indices.add(uv2_accessor)
        material_index = before_primitive.get("material")
        if isinstance(material_index, int):
            target_material_indices.add(material_index)
        protected_results = {}
        for semantic in protected_semantics:
            before_index = before_attributes.get(semantic)
            after_index = after_attributes.get(semantic)
            before_identity = (
                accessor_decoded_identity(
                    baseline, baseline_binary, int(before_index)
                )
                if isinstance(before_index, int)
                else None
            )
            after_identity = (
                accessor_decoded_identity(
                    candidate, candidate_binary, int(after_index)
                )
                if isinstance(after_index, int)
                else None
            )
            protected_results[semantic] = {
                "baseline_accessor": before_index,
                "candidate_accessor": after_index,
                "same_accessor_index": (
                    isinstance(before_index, int)
                    and before_index == after_index
                ),
                "metadata_equal": (
                    before_identity is not None
                    and after_identity is not None
                    and before_identity["metadata"]
                    == after_identity["metadata"]
                ),
                "decoded_values_equal": (
                    before_identity is not None
                    and after_identity is not None
                    and before_identity["decoded_value_sha256"]
                    == after_identity["decoded_value_sha256"]
                ),
            }
        before_indices = before_primitive.get("indices")
        after_indices = after_primitive.get("indices")
        before_indices_identity = (
            accessor_decoded_identity(
                baseline, baseline_binary, int(before_indices)
            )
            if isinstance(before_indices, int)
            else None
        )
        after_indices_identity = (
            accessor_decoded_identity(
                candidate, candidate_binary, int(after_indices)
            )
            if isinstance(after_indices, int)
            else None
        )
        indices_result = {
            "baseline_accessor": before_indices,
            "candidate_accessor": after_indices,
            "same_accessor_index": before_indices == after_indices,
            "metadata_equal": (
                before_indices_identity is not None
                and after_indices_identity is not None
                and before_indices_identity["metadata"]
                == after_indices_identity["metadata"]
            ),
            "decoded_values_equal": (
                before_indices_identity is not None
                and after_indices_identity is not None
                and before_indices_identity["decoded_value_sha256"]
                == after_indices_identity["decoded_value_sha256"]
            ),
        }
        before_without_attributes = _without_key(
            before_primitive, "attributes"
        )
        after_without_attributes = _without_key(
            after_primitive, "attributes"
        )
        before_mesh_without_primitives = _without_key(
            baseline_mesh, "primitives"
        )
        after_mesh_without_primitives = _without_key(
            candidate_mesh, "primitives"
        )
        uv2_stats = (
            texcoord_accessor_statistics(
                candidate, candidate_binary, uv2_accessor
            )
            if isinstance(uv2_accessor, int)
            else None
        )
        checks = {
            "mesh_index_unchanged": (
                baseline_mesh_index == candidate_mesh_index
            ),
            "mesh_nonprimitive_json_unchanged": (
                before_mesh_without_primitives
                == after_mesh_without_primitives
            ),
            "primitive_nonattribute_json_unchanged": (
                before_without_attributes == after_without_attributes
            ),
            "protected_attribute_set_unchanged": (
                set(before_attributes) == set(protected_semantics)
                and set(after_attributes)
                == set(protected_semantics).union({"TEXCOORD_2"})
            ),
            "protected_accessors_same_index_metadata_and_values": all(
                all(
                    result[field]
                    for field in (
                        "same_accessor_index",
                        "metadata_equal",
                        "decoded_values_equal",
                    )
                )
                for result in protected_results.values()
            ),
            "indices_same_index_metadata_and_values": all(
                indices_result[field]
                for field in (
                    "same_accessor_index",
                    "metadata_equal",
                    "decoded_values_equal",
                )
            ),
            "uv2_uses_new_accessor": (
                isinstance(uv2_accessor, int)
                and uv2_accessor >= len(baseline_accessors)
            ),
            "uv2_accessor_is_finite_and_in_range": (
                uv2_stats is not None
                and uv2_stats["all_finite"]
                and uv2_stats["in_unit_range"]
            ),
        }
        target_results[target] = {
            "present_in_both": True,
            "baseline_mesh_index": baseline_mesh_index,
            "candidate_mesh_index": candidate_mesh_index,
            "protected_accessors": protected_results,
            "indices": indices_result,
            "uv2_accessor": uv2_accessor,
            "uv2_statistics": uv2_stats,
            "checks": checks,
            "passed": all(checks.values()),
        }

    target_mesh_names = {
        expected_mesh_name(target) for target in R2J_EXTERIOR_OBJECTS
    }
    non_target_mesh_results = []
    for mesh_name, (index, baseline_mesh) in baseline_mesh_by_name.items():
        if mesh_name in target_mesh_names:
            continue
        candidate_entry = candidate_mesh_by_name.get(mesh_name)
        non_target_mesh_results.append(
            {
                "mesh_name": mesh_name,
                "baseline_index": index,
                "candidate_index": (
                    candidate_entry[0]
                    if candidate_entry is not None
                    else None
                ),
                "json_equal": (
                    candidate_entry is not None
                    and candidate_entry[0] == index
                    and candidate_entry[1] == baseline_mesh
                ),
            }
        )

    material_results = []
    for index, baseline_material in enumerate(baseline_materials):
        candidate_material = (
            candidate_materials[index]
            if index < len(candidate_materials)
            else None
        )
        occlusion = (
            candidate_material.get("occlusionTexture")
            if isinstance(candidate_material, dict)
            else None
        )
        expected_to_gain_ao = index in target_material_indices
        occlusion_keys_valid = (
            isinstance(occlusion, dict)
            and set(occlusion).issubset({"index", "texCoord", "strength"})
        )
        strength = (
            occlusion.get("strength", 1.0)
            if isinstance(occlusion, dict)
            else None
        )
        material_results.append(
            {
                "material_index": index,
                "material_name": (
                    baseline_material.get("name")
                    if isinstance(baseline_material, dict)
                    else None
                ),
                "expected_to_gain_ao": expected_to_gain_ao,
                "baseline_has_no_occlusion_texture": (
                    isinstance(baseline_material, dict)
                    and "occlusionTexture" not in baseline_material
                ),
                "all_non_occlusion_json_equal": (
                    isinstance(candidate_material, dict)
                    and _without_key(candidate_material, "occlusionTexture")
                    == baseline_material
                ),
                "pbr_block_equal": (
                    isinstance(candidate_material, dict)
                    and candidate_material.get("pbrMetallicRoughness")
                    == baseline_material.get("pbrMetallicRoughness")
                ),
                "occlusion_contract_exact": (
                    (
                        expected_to_gain_ao
                        and occlusion_keys_valid
                        and occlusion.get("index")
                        == new_ao_texture_index
                        and occlusion.get("texCoord") == 2
                        and isinstance(strength, (int, float))
                        and not isinstance(strength, bool)
                        and math.isfinite(float(strength))
                        and 0.0 < float(strength) <= 1.0
                    )
                    or (
                        not expected_to_gain_ao
                        and occlusion is None
                    )
                ),
            }
        )

    uv2_view_indices = {
        int(candidate_accessors[index]["bufferView"])
        for index in new_uv2_accessor_indices
        if (
            0 <= index < len(candidate_accessors)
            and isinstance(candidate_accessors[index], dict)
            and candidate_accessors[index].get("bufferView") is not None
        )
    }
    ao_view_index = (
        int(new_ao_image["bufferView"])
        if isinstance(new_ao_image, dict)
        and new_ao_image.get("bufferView") is not None
        else None
    )
    expected_extra_view_indices = set(uv2_view_indices)
    if ao_view_index is not None:
        expected_extra_view_indices.add(ao_view_index)
    actual_extra_view_indices = set(
        range(len(baseline_views), len(candidate_views))
    )
    actual_extra_accessor_indices = set(
        range(len(baseline_accessors), len(candidate_accessors))
    )

    allowed_top_level_changes = {
        "buffers",
        "bufferViews",
        "accessors",
        "images",
        "textures",
        "materials",
        "meshes",
    }
    top_level_identity = {
        key: baseline.get(key) == candidate.get(key)
        for key in sorted(set(baseline).union(candidate))
        if key not in allowed_top_level_changes
    }
    baseline_buffers = baseline.get("buffers") or []
    candidate_buffers = candidate.get("buffers") or []
    buffer_contract = {
        "one_embedded_buffer_before_and_after": (
            len(baseline_buffers) == 1
            and len(candidate_buffers) == 1
            and baseline_buffers[0].get("uri") is None
            and candidate_buffers[0].get("uri") is None
        ),
        "buffer_json_except_byte_length_equal": (
            len(baseline_buffers) == 1
            and len(candidate_buffers) == 1
            and _without_key(baseline_buffers[0], "byteLength")
            == _without_key(candidate_buffers[0], "byteLength")
        ),
        "declared_lengths_fit_bin_chunks": (
            len(baseline_buffers) == 1
            and len(candidate_buffers) == 1
            and 0
            <= len(baseline_binary)
            - int(baseline_buffers[0].get("byteLength", -1))
            <= 3
            and 0
            <= len(candidate_binary)
            - int(candidate_buffers[0].get("byteLength", -1))
            <= 3
        ),
    }

    checks = {
        "baseline_is_locked_v5_material_glb": (
            sha256_file(baseline_path)
            == LOCKS["v5_material_glb"][1]
        ),
        "top_level_non_payload_json_is_identical": all(
            top_level_identity.values()
        ),
        "buffer_contract_is_append_only": all(buffer_contract.values()),
        "all_existing_buffer_views_metadata_and_bytes_identical": (
            len(existing_view_results) == len(baseline_views)
            and all(
                item["metadata_equal"] and item["payload_byte_equal"]
                for item in existing_view_results
            )
        ),
        "all_existing_accessors_metadata_and_decoded_values_identical": (
            len(existing_accessor_results) == len(baseline_accessors)
            and all(
                item["metadata_equal"] and item["decoded_values_equal"]
                for item in existing_accessor_results
            )
        ),
        "all_existing_webp_images_json_and_payload_bytes_identical": (
            len(baseline_images) == 3
            and all(
                item["mime_type"] == "image/webp"
                and item["json_equal"]
                and item["payload_bytes_equal"]
                for item in existing_image_results
            )
        ),
        "all_existing_textures_identical": (
            candidate_textures[: len(baseline_textures)]
            == baseline_textures
        ),
        "samplers_identical_and_no_sampler_added": (
            candidate_samplers == baseline_samplers
        ),
        "exactly_one_ao_image_added_with_exact_png_payload": (
            len(extra_image_indices) == 1
            and isinstance(new_ao_image, dict)
            and new_ao_image.get("mimeType") == "image/png"
            and new_ao_image.get("uri") is None
            and AO_IMAGE_TOKEN.casefold()
            in str(new_ao_image.get("name") or "").casefold()
            and new_ao_image_payload == ao_payload
        ),
        "exactly_one_ao_texture_added": (
            len(extra_texture_indices) == 1
            and isinstance(new_ao_texture, dict)
            and new_ao_texture.get("source") == new_ao_image_index
            and not (new_ao_texture.get("extensions") or {})
        ),
        "material_count_unchanged": (
            len(candidate_materials) == len(baseline_materials)
        ),
        "materials_only_gain_valid_occlusion_texture": (
            len(material_results) == len(baseline_materials)
            and all(
                item["baseline_has_no_occlusion_texture"]
                and item["all_non_occlusion_json_equal"]
                and item["pbr_block_equal"]
                and item["occlusion_contract_exact"]
                for item in material_results
            )
        ),
        "mesh_identity_and_count_unchanged": (
            set(candidate_mesh_by_name) == set(baseline_mesh_by_name)
            and len(candidate_meshes) == len(baseline_meshes)
        ),
        "five_targets_only_gain_texcoord_2": (
            len(target_results) == 5
            and all(item.get("passed") for item in target_results.values())
        ),
        "all_non_target_meshes_are_identical": all(
            item["json_equal"] for item in non_target_mesh_results
        ),
        "exactly_five_new_uv2_accessors_and_no_other_accessors": (
            len(new_uv2_accessor_indices) == 5
            and new_uv2_accessor_indices == actual_extra_accessor_indices
        ),
        "new_buffer_views_are_only_uv2_and_ao": (
            expected_extra_view_indices == actual_extra_view_indices
            and len(uv2_view_indices) == 5
            and ao_view_index is not None
            and ao_view_index not in uv2_view_indices
        ),
    }
    return {
        "baseline_artifact": artifact_record(
            baseline_path, LOCKS["v5_material_glb"][1]
        ),
        "candidate_artifact": artifact_record(candidate_path),
        "baseline_counts": {
            "buffer_views": len(baseline_views),
            "accessors": len(baseline_accessors),
            "images": len(baseline_images),
            "textures": len(baseline_textures),
            "samplers": len(baseline_samplers),
            "materials": len(baseline_materials),
            "meshes": len(baseline_meshes),
        },
        "candidate_counts": {
            "buffer_views": len(candidate_views),
            "accessors": len(candidate_accessors),
            "images": len(candidate_images),
            "textures": len(candidate_textures),
            "samplers": len(candidate_samplers),
            "materials": len(candidate_materials),
            "meshes": len(candidate_meshes),
        },
        "top_level_identity": top_level_identity,
        "buffer_contract": buffer_contract,
        "existing_buffer_views": existing_view_results,
        "existing_accessors": existing_accessor_results,
        "existing_webp_images": existing_image_results,
        "new_ao_image": {
            "index": new_ao_image_index,
            "json": new_ao_image,
            "payload_bytes": (
                len(new_ao_image_payload)
                if new_ao_image_payload is not None
                else None
            ),
            "payload_sha256": (
                sha256_bytes(new_ao_image_payload)
                if new_ao_image_payload is not None
                else None
            ),
            "external_png_sha256": sha256_bytes(ao_payload),
        },
        "new_ao_texture": {
            "index": new_ao_texture_index,
            "json": new_ao_texture,
        },
        "materials": material_results,
        "targets": target_results,
        "non_target_meshes": non_target_mesh_results,
        "new_uv2_accessor_indices": sorted(new_uv2_accessor_indices),
        "new_uv2_buffer_view_indices": sorted(uv2_view_indices),
        "new_ao_buffer_view_index": ao_view_index,
        "actual_extra_accessor_indices": sorted(
            actual_extra_accessor_indices
        ),
        "actual_extra_buffer_view_indices": sorted(
            actual_extra_view_indices
        ),
        "checks": checks,
        "passed": all(checks.values()),
    }


def _hash_numbers(
    rows: Iterable[Iterable[float | int]],
    *,
    floats: bool,
) -> str:
    """Hash ordered numeric rows with explicit row framing."""

    digest = hashlib.sha256()
    for row in rows:
        values = tuple(row)
        digest.update(struct.pack("<I", len(values)))
        if floats:
            for value in values:
                digest.update(struct.pack("<d", float(value)))
        else:
            for value in values:
                digest.update(struct.pack("<q", int(value)))
    return digest.hexdigest()


def _uv_layer_record(layer: Any, active_layer: Any) -> dict[str, Any]:
    """Return a deterministic Blender UV-layer snapshot."""

    digest = hashlib.sha256()
    finite = True
    in_range = True
    minimum = [math.inf, math.inf]
    maximum = [-math.inf, -math.inf]
    for loop in layer.data:
        u = float(loop.uv[0])
        v = float(loop.uv[1])
        digest.update(struct.pack("<ff", u, v))
        for axis, value in enumerate((u, v)):
            if not math.isfinite(value):
                finite = False
                continue
            minimum[axis] = min(minimum[axis], value)
            maximum[axis] = max(maximum[axis], value)
            if value < -FLOAT_TOLERANCE or value > 1.0 + FLOAT_TOLERANCE:
                in_range = False
    if not layer.data:
        finite = False
        in_range = False
        minimum = [None, None]
        maximum = [None, None]
    return {
        "name": str(layer.name),
        "active": layer == active_layer,
        "active_render": bool(layer.active_render),
        "loop_count": len(layer.data),
        "loop_sha256": digest.hexdigest(),
        "all_finite": finite,
        "in_unit_range": finite and in_range,
        "minimum": minimum,
        "maximum": maximum,
    }


def _node_has_ao_image(node: Any, expected_ao: Path) -> bool:
    """Return whether a Blender image node references the candidate AO PNG."""

    image = getattr(node, "image", None)
    if image is None:
        return False
    values = [
        str(getattr(image, "name", "") or ""),
        str(getattr(image, "filepath", "") or ""),
        str(getattr(image, "filepath_raw", "") or ""),
    ]
    if any(AO_IMAGE_TOKEN.casefold() in value.casefold() for value in values):
        return True
    try:
        import bpy  # type: ignore

        resolved = Path(bpy.path.abspath(image.filepath_raw)).resolve()
        return resolved == expected_ao.resolve()
    except (OSError, RuntimeError, ValueError):
        return False


def _material_node_record(material: Any, expected_ao: Path) -> dict[str, Any]:
    """Inspect R2X AO nodes and the glTF Occlusion input without mutation."""

    tree = getattr(material, "node_tree", None)
    if tree is None:
        return {
            "material_name": str(material.name),
            "uses_nodes": False,
            "is_r2x_ao_material": str(material.name).startswith(
                AO_MATERIAL_PREFIX
            ),
            "ao_image_nodes": [],
            "uv2_nodes": [],
            "occlusion_input_links": [],
            "temporary_nodes": [],
            "ao_contract_consumed": False,
        }
    ao_image_nodes = []
    uv2_nodes = []
    temporary_nodes = []
    for node in tree.nodes:
        node_name = str(getattr(node, "name", "") or "")
        node_label = str(getattr(node, "label", "") or "")
        if _node_has_ao_image(node, expected_ao):
            image = getattr(node, "image", None)
            resolved_path = None
            if image is not None:
                try:
                    import bpy  # type: ignore

                    resolved = Path(
                        bpy.path.abspath(image.filepath_raw)
                    ).resolve()
                    resolved_path = (
                        relative_path(resolved)
                        if is_within(resolved, REPO_ROOT)
                        else "<outside-repository>"
                    )
                except (OSError, RuntimeError, ValueError):
                    resolved_path = None
            ao_image_nodes.append(
                {
                    "node_name": node_name,
                    "node_type": str(getattr(node, "type", "") or ""),
                    "image_name": str(getattr(image, "name", "") or ""),
                    "image_path": resolved_path,
                }
            )
        if (
            str(getattr(node, "type", "") or "") == "UVMAP"
            and str(getattr(node, "uv_map", "") or "") == UV2_NAME
        ):
            uv2_nodes.append(
                {
                    "node_name": node_name,
                    "uv_map": str(node.uv_map),
                }
            )
        combined = f"{node_name} {node_label}".upper()
        if any(
            token in combined
            for token in ("__TEMP", "BAKE_TEMP", "R2X_TEMP")
        ):
            temporary_nodes.append(
                {
                    "node_name": node_name,
                    "node_label": node_label,
                    "node_type": str(getattr(node, "type", "") or ""),
                }
            )
    occlusion_links = []
    for link in tree.links:
        destination_node = link.to_node
        destination_name = str(
            getattr(destination_node, "name", "") or ""
        )
        destination_tree_name = str(
            getattr(
                getattr(destination_node, "node_tree", None),
                "name",
                "",
            )
            or ""
        )
        destination_socket = str(
            getattr(link.to_socket, "name", "")
            or getattr(link.to_socket, "identifier", "")
            or ""
        )
        is_gltf_output = "GLTF MATERIAL OUTPUT" in (
            f"{destination_name} {destination_tree_name}".upper()
        )
        if is_gltf_output and destination_socket.casefold() == "occlusion":
            occlusion_links.append(
                {
                    "from_node": str(
                        getattr(link.from_node, "name", "") or ""
                    ),
                    "from_socket": str(
                        getattr(link.from_socket, "name", "")
                        or getattr(link.from_socket, "identifier", "")
                        or ""
                    ),
                    "to_node": destination_name,
                    "to_socket": destination_socket,
                }
            )
    # A generic glTF Material Output/Occlusion link is not R2X evidence:
    # several locked V5 Section materials already have that socket wired for
    # their ordinary material graph.  R2X identity requires the registered
    # material prefix, the registered AO image, or the registered UV2 layer.
    is_candidate = (
        str(material.name).startswith(AO_MATERIAL_PREFIX)
        or bool(ao_image_nodes)
        or bool(uv2_nodes)
    )
    return {
        "material_name": str(material.name),
        "uses_nodes": bool(material.use_nodes),
        "is_r2x_ao_material": is_candidate,
        "ao_image_nodes": ao_image_nodes,
        "uv2_nodes": uv2_nodes,
        "occlusion_input_links": occlusion_links,
        "temporary_nodes": temporary_nodes,
        "ao_contract_consumed": (
            bool(ao_image_nodes)
            and bool(uv2_nodes)
            and bool(occlusion_links)
            and not temporary_nodes
        ),
    }


def _object_mesh_record(obj: Any) -> dict[str, Any]:
    """Return topology, transform, slots, polygon indices and UV hashes."""

    mesh = obj.data
    vertex_hash = _hash_numbers(
        ((vertex.co[0], vertex.co[1], vertex.co[2]) for vertex in mesh.vertices),
        floats=True,
    )
    edge_hash = _hash_numbers(
        (tuple(edge.vertices) for edge in mesh.edges), floats=False
    )
    polygon_loop_hash = _hash_numbers(
        (
            (
                polygon.loop_start,
                polygon.loop_total,
                *tuple(polygon.vertices),
            )
            for polygon in mesh.polygons
        ),
        floats=False,
    )
    polygon_material_hash = _hash_numbers(
        ((polygon.material_index,) for polygon in mesh.polygons),
        floats=False,
    )
    matrix_world = [
        float(value)
        for row in obj.matrix_world
        for value in row
    ]
    matrix_local = [
        float(value)
        for row in obj.matrix_local
        for value in row
    ]
    transform_hash = _hash_numbers(
        (matrix_world, matrix_local), floats=True
    )
    uv_layers = [
        _uv_layer_record(layer, mesh.uv_layers.active)
        for layer in mesh.uv_layers
    ]
    slots = [
        {
            "slot_index": index,
            "material_name": (
                str(slot.material.name) if slot.material else None
            ),
        }
        for index, slot in enumerate(obj.material_slots)
    ]
    return {
        "object_name": str(obj.name),
        "mesh_name": str(mesh.name),
        "counts": {
            "vertices": len(mesh.vertices),
            "edges": len(mesh.edges),
            "polygons": len(mesh.polygons),
            "loops": len(mesh.loops),
        },
        "vertex_coordinate_sha256": vertex_hash,
        "edge_vertex_index_sha256": edge_hash,
        "polygon_loop_sha256": polygon_loop_hash,
        "polygon_material_index_sha256": polygon_material_hash,
        "matrix_world": matrix_world,
        "matrix_local": matrix_local,
        "transform_sha256": transform_hash,
        "parent_name": str(obj.parent.name) if obj.parent else None,
        "material_slot_count": len(slots),
        "material_slots": slots,
        "uv_layers": uv_layers,
    }


def _triangle_area(triangle: Sequence[tuple[float, float]]) -> float:
    """Return absolute area of one 2D triangle."""

    (ax, ay), (bx, by), (cx, cy) = triangle
    return abs(
        (bx - ax) * (cy - ay) - (by - ay) * (cx - ax)
    ) * 0.5


def _uv_triangles(obj: Any, layer: Any) -> list[tuple[tuple[float, float], ...]]:
    """Read loop triangles for one UV layer without modifying persistent data."""

    mesh = obj.data
    mesh.calc_loop_triangles()
    triangles = []
    for triangle in mesh.loop_triangles:
        points = tuple(
            (
                float(layer.data[loop_index].uv[0]),
                float(layer.data[loop_index].uv[1]),
            )
            for loop_index in triangle.loops
        )
        if len(points) == 3 and _triangle_area(points) > UV_OVERLAP_AREA_EPSILON:
            triangles.append(points)
    return triangles


def _signed_cross(
    a: tuple[float, float],
    b: tuple[float, float],
    p: tuple[float, float],
) -> float:
    """Return the oriented 2D cross product for edge ``a``→``b`` and point p."""

    return (
        (b[0] - a[0]) * (p[1] - a[1])
        - (b[1] - a[1]) * (p[0] - a[0])
    )


def _line_intersection(
    start: tuple[float, float],
    end: tuple[float, float],
    clip_a: tuple[float, float],
    clip_b: tuple[float, float],
) -> tuple[float, float]:
    """Intersect a segment with an infinite clipping line."""

    start_distance = _signed_cross(clip_a, clip_b, start)
    end_distance = _signed_cross(clip_a, clip_b, end)
    denominator = start_distance - end_distance
    if abs(denominator) <= 1.0e-30:
        return end
    ratio = start_distance / denominator
    return (
        start[0] + ratio * (end[0] - start[0]),
        start[1] + ratio * (end[1] - start[1]),
    )


def _triangle_intersection_area(
    first: Sequence[tuple[float, float]],
    second: Sequence[tuple[float, float]],
) -> float:
    """Return the polygon-clipped intersection area of two UV triangles."""

    polygon = list(first)
    orientation = (
        1.0
        if _signed_cross(second[0], second[1], second[2]) >= 0.0
        else -1.0
    )
    for index in range(3):
        clip_a = second[index]
        clip_b = second[(index + 1) % 3]
        if not polygon:
            return 0.0
        output = []
        start = polygon[-1]
        start_inside = (
            orientation * _signed_cross(clip_a, clip_b, start)
            >= -UV_OVERLAP_AREA_EPSILON
        )
        for end in polygon:
            end_inside = (
                orientation * _signed_cross(clip_a, clip_b, end)
                >= -UV_OVERLAP_AREA_EPSILON
            )
            if end_inside:
                if not start_inside:
                    output.append(
                        _line_intersection(start, end, clip_a, clip_b)
                    )
                output.append(end)
            elif start_inside:
                output.append(
                    _line_intersection(start, end, clip_a, clip_b)
                )
            start = end
            start_inside = end_inside
        polygon = output
    if len(polygon) < 3:
        return 0.0
    signed = 0.0
    for index, point in enumerate(polygon):
        next_point = polygon[(index + 1) % len(polygon)]
        signed += point[0] * next_point[1] - point[1] * next_point[0]
    return abs(signed) * 0.5


def _bounds_for_triangles(
    triangles: Sequence[Sequence[tuple[float, float]]],
) -> tuple[float, float, float, float] | None:
    """Return a UV bounding rectangle for a triangle sequence."""

    if not triangles:
        return None
    xs = [point[0] for triangle in triangles for point in triangle]
    ys = [point[1] for triangle in triangles for point in triangle]
    return min(xs), min(ys), max(xs), max(ys)


def _rectangles_overlap(
    first: tuple[float, float, float, float],
    second: tuple[float, float, float, float],
) -> bool:
    """Return whether two rectangles have positive-area intersection."""

    return (
        min(first[2], second[2]) - max(first[0], second[0])
        > FLOAT_TOLERANCE
        and min(first[3], second[3]) - max(first[1], second[1])
        > FLOAT_TOLERANCE
    )


def _cross_object_uv_overlaps(
    triangles_by_object: dict[
        str, list[tuple[tuple[float, float], ...]]
    ],
) -> dict[str, Any]:
    """Find positive-area UV triangle overlaps between different R2J shells."""

    overlap_pairs = []
    tested_triangle_pairs = 0
    names = sorted(triangles_by_object)
    bounds = {
        name: _bounds_for_triangles(triangles_by_object[name])
        for name in names
    }
    for first_index, first_name in enumerate(names):
        first_bounds = bounds[first_name]
        if first_bounds is None:
            continue
        for second_name in names[first_index + 1 :]:
            second_bounds = bounds[second_name]
            if (
                second_bounds is None
                or not _rectangles_overlap(first_bounds, second_bounds)
            ):
                continue
            found_area = 0.0
            first_triangles = triangles_by_object[first_name]
            second_triangles = triangles_by_object[second_name]
            second_records = [
                (
                    triangle,
                    _bounds_for_triangles([triangle]),
                )
                for triangle in second_triangles
            ]
            for first_triangle in first_triangles:
                first_triangle_bounds = _bounds_for_triangles(
                    [first_triangle]
                )
                if first_triangle_bounds is None:
                    continue
                for second_triangle, second_triangle_bounds in second_records:
                    if (
                        second_triangle_bounds is None
                        or not _rectangles_overlap(
                            first_triangle_bounds,
                            second_triangle_bounds,
                        )
                    ):
                        continue
                    tested_triangle_pairs += 1
                    area = _triangle_intersection_area(
                        first_triangle, second_triangle
                    )
                    if area > UV_OVERLAP_AREA_EPSILON:
                        found_area = area
                        break
                if found_area > 0.0:
                    break
            if found_area > 0.0:
                overlap_pairs.append(
                    {
                        "objects": [first_name, second_name],
                        "example_intersection_area": found_area,
                    }
                )
    return {
        "triangle_counts": {
            name: len(triangles)
            for name, triangles in triangles_by_object.items()
        },
        "object_bounds": {
            name: list(value) if value is not None else None
            for name, value in bounds.items()
        },
        "tested_triangle_pairs": tested_triangle_pairs,
        "overlap_pairs": overlap_pairs,
        "overlap_pair_count": len(overlap_pairs),
        "no_cross_object_overlap": not overlap_pairs,
    }


def run_blend_probe(
    output: Path,
    expected_blend: Path,
    role: str,
    expected_ao: Path,
) -> int:
    """Run one Blender read-only snapshot and write only temporary JSON."""

    try:
        import bpy  # type: ignore
    except ImportError as exc:
        raise AuditError("--blend-probe must run inside Blender") from exc

    actual_blend = Path(bpy.data.filepath).resolve()
    expected_blend = expected_blend.resolve()
    if actual_blend != expected_blend:
        raise AuditError(
            f"Blender opened the wrong file: "
            f"actual={actual_blend}, expected={expected_blend}"
        )
    if role not in {"baseline", "candidate"}:
        raise AuditError(f"Unknown Blender probe role: {role}")

    targets: dict[str, Any] = {}
    triangles_by_object: dict[
        str, list[tuple[tuple[float, float], ...]]
    ] = {}
    for object_name in R2J_EXTERIOR_OBJECTS:
        obj = bpy.data.objects.get(object_name)
        if obj is None or obj.type != "MESH":
            raise AuditError(
                f"Blend is missing R2J mesh object: {object_name}"
            )
        targets[object_name] = _object_mesh_record(obj)
        ao_layer = obj.data.uv_layers.get(UV2_NAME)
        if role == "candidate" and ao_layer is not None:
            triangles_by_object[object_name] = _uv_triangles(
                obj, ao_layer
            )

    mesh_objects = [
        obj for obj in bpy.data.objects if obj.type == "MESH"
    ]
    section_objects = sorted(
        obj.name for obj in mesh_objects if obj.name.startswith("SECTION_")
    )
    uv2_owners = sorted(
        obj.name
        for obj in mesh_objects
        if obj.data.uv_layers.get(UV2_NAME) is not None
    )
    material_users: defaultdict[str, list[str]] = defaultdict(list)
    used_materials: dict[str, Any] = {}
    for obj in mesh_objects:
        for slot in obj.material_slots:
            material = slot.material
            if material is None:
                continue
            material_name = str(material.name)
            material_users[material_name].append(str(obj.name))
            used_materials[material_name] = material
    material_records = {
        name: _material_node_record(material, expected_ao)
        for name, material in sorted(used_materials.items())
    }
    ao_material_users = {
        name: sorted(set(material_users[name]))
        for name, record in material_records.items()
        if record["is_r2x_ao_material"]
    }
    section_ao_materials = {
        section_name: sorted(
            {
                slot.material.name
                for slot in bpy.data.objects[section_name].material_slots
                if (
                    slot.material is not None
                    and material_records[str(slot.material.name)][
                        "is_r2x_ao_material"
                    ]
                )
            }
        )
        for section_name in section_objects
    }
    object_states = {
        str(obj.name): {
            "type": str(obj.type),
            "hide_viewport": bool(obj.hide_viewport),
            "hide_render": bool(obj.hide_render),
            "hide_get": bool(obj.hide_get()),
            "selected": bool(obj.select_get()),
        }
        for obj in bpy.data.objects
    }
    active_object = bpy.context.view_layer.objects.active
    scene_state = {
        "render_engine": str(bpy.context.scene.render.engine),
        "active_object": str(active_object.name) if active_object else None,
        "selected_objects": sorted(
            str(obj.name) for obj in bpy.context.selected_objects
        ),
        "object_states": object_states,
    }
    overlap = (
        _cross_object_uv_overlaps(triangles_by_object)
        if role == "candidate"
        else None
    )
    report = {
        "schema_version": BLEND_PROBE_SCHEMA_VERSION,
        "requirement_id": REQUIREMENT_ID,
        "stage_id": STAGE_ID,
        "generated_at": now_iso(),
        "probe_role": role,
        "probe_mode": "background_read_only_no_save",
        "blender_version": ".".join(
            str(value) for value in bpy.app.version
        ),
        "opened_blend_path": relative_path(actual_blend),
        "opened_blend_artifact": artifact_record(actual_blend),
        "targets": targets,
        "target_count": len(targets),
        "mesh_object_count": len(mesh_objects),
        "all_object_names_and_types": sorted(
            [str(obj.name), str(obj.type)] for obj in bpy.data.objects
        ),
        "section_objects": section_objects,
        "section_object_count": len(section_objects),
        "uv2_owners": uv2_owners,
        "materials": material_records,
        "ao_material_users": ao_material_users,
        "section_ao_materials": section_ao_materials,
        "scene_state": scene_state,
        "uv2_cross_object_overlap": overlap,
        "blend_was_dirty_when_probed": bool(bpy.data.is_dirty),
        "scene_saved": False,
        "scene_mutations_requested": False,
        "probe_completed": (
            len(targets) == 5
            and actual_blend == expected_blend
        ),
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    write_json(output, report)
    return 0 if report["probe_completed"] else 1


def launch_blend_probe(
    blender_exe: Path,
    blend: Path,
    role: str,
    ao_png: Path,
    output: Path,
    timeout_seconds: int,
) -> dict[str, Any]:
    """Launch Blender 5.2 in background mode for one read-only probe."""

    if not blender_exe.is_file():
        raise AuditError(f"Blender executable not found: {blender_exe}")
    if not blend.is_file():
        raise AuditError(f"Blend file not found: {blend}")
    command = [
        str(blender_exe),
        "--background",
        str(blend),
        "--disable-autoexec",
        "--python-exit-code",
        "3",
        "--python",
        str(Path(__file__).resolve()),
        "--",
        "--blend-probe",
        "--output",
        str(output),
        "--expected-blend",
        str(blend),
        "--probe-role",
        role,
        "--ao-png",
        str(ao_png),
    ]
    try:
        result = subprocess.run(
            command,
            cwd=str(REPO_ROOT),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
            timeout=timeout_seconds,
        )
    except subprocess.TimeoutExpired as exc:
        raise AuditError(
            f"Blender {role} probe timed out after "
            f"{timeout_seconds} seconds"
        ) from exc
    if result.returncode != 0:
        raise AuditError(
            f"Blender {role} read-only probe failed: "
            f"exit={result.returncode}; "
            f"stdout_tail={result.stdout[-2000:]!r}; "
            f"stderr_tail={result.stderr[-2000:]!r}"
        )
    report = load_json_object(output)
    if report.get("schema_version") != BLEND_PROBE_SCHEMA_VERSION:
        raise AuditError(f"Unexpected Blender probe schema: {role}")
    if report.get("probe_role") != role or not report.get("probe_completed"):
        raise AuditError(f"Incomplete Blender probe: {role}")
    return report


def _uv_by_name(record: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """Index an object probe's UV layers by name."""

    return {
        str(layer["name"]): layer
        for layer in record.get("uv_layers") or []
    }


def compare_blend_probes(
    baseline: dict[str, Any],
    candidate: dict[str, Any],
) -> dict[str, Any]:
    """Compare V5 and candidate Blender snapshots against the R2X contract."""

    target_results: dict[str, Any] = {}
    target_passes = []
    for target in R2J_EXTERIOR_OBJECTS:
        base = baseline["targets"].get(target)
        current = candidate["targets"].get(target)
        if base is None or current is None:
            target_results[target] = {
                "evidence_complete": False,
                "passed": False,
            }
            target_passes.append(False)
            continue
        base_uv_names = [
            layer["name"] for layer in base["uv_layers"]
        ]
        current_uv_names = [
            layer["name"] for layer in current["uv_layers"]
        ]
        base_uvs = _uv_by_name(base)
        current_uvs = _uv_by_name(current)
        uv0_uv1_checks = {}
        for uv_name in EXPECTED_BASE_UVS:
            before = base_uvs.get(uv_name)
            after = current_uvs.get(uv_name)
            uv0_uv1_checks[uv_name] = {
                "exists_before_and_after": (
                    before is not None and after is not None
                ),
                "loop_count_unchanged": (
                    before is not None
                    and after is not None
                    and before["loop_count"] == after["loop_count"]
                ),
                "loop_sha256_unchanged": (
                    before is not None
                    and after is not None
                    and before["loop_sha256"] == after["loop_sha256"]
                ),
                "active_state_unchanged": (
                    before is not None
                    and after is not None
                    and before["active"] == after["active"]
                ),
                "active_render_state_unchanged": (
                    before is not None
                    and after is not None
                    and before["active_render"] == after["active_render"]
                ),
            }
        uv2 = current_uvs.get(UV2_NAME) or {}
        baseline_slots = base["material_slots"]
        candidate_slots = current["material_slots"]
        inner_cap_slot_names_unchanged = (
            len(baseline_slots) == 3
            and len(candidate_slots) == 3
            and all(
                baseline_slots[index]["material_name"]
                == candidate_slots[index]["material_name"]
                for index in (1, 2)
            )
        )
        exterior_material_name = (
            candidate_slots[0]["material_name"]
            if candidate_slots
            else None
        )
        exterior_material = candidate["materials"].get(
            exterior_material_name
        ) if exterior_material_name else None
        checks = {
            "baseline_uv_names_and_order_are_locked": (
                base_uv_names == list(EXPECTED_BASE_UVS)
            ),
            "candidate_uv_names_and_order_are_uv0_uv1_uv2": (
                current_uv_names == list(EXPECTED_CANDIDATE_UVS)
            ),
            "uv0_uv1_loop_hash_and_states_unchanged": all(
                all(result.values())
                for result in uv0_uv1_checks.values()
            ),
            "uv2_is_finite": uv2.get("all_finite") is True,
            "uv2_is_in_unit_range": uv2.get("in_unit_range") is True,
            "vertex_edge_polygon_loop_counts_unchanged": (
                base["counts"] == current["counts"]
            ),
            "vertex_coordinates_unchanged": (
                base["vertex_coordinate_sha256"]
                == current["vertex_coordinate_sha256"]
            ),
            "edge_vertex_indices_unchanged": (
                base["edge_vertex_index_sha256"]
                == current["edge_vertex_index_sha256"]
            ),
            "polygon_loop_structure_unchanged": (
                base["polygon_loop_sha256"]
                == current["polygon_loop_sha256"]
            ),
            "transform_unchanged": (
                base["transform_sha256"] == current["transform_sha256"]
                and base["parent_name"] == current["parent_name"]
            ),
            "exactly_three_material_slots_before_and_after": (
                base["material_slot_count"] == 3
                and current["material_slot_count"] == 3
            ),
            "inner_and_cap_slot_names_unchanged": (
                inner_cap_slot_names_unchanged
            ),
            "polygon_material_indices_unchanged": (
                base["polygon_material_index_sha256"]
                == current["polygon_material_index_sha256"]
            ),
            "slot0_is_r2x_ao_candidate_material": bool(
                exterior_material
                and exterior_material["is_r2x_ao_material"]
                and str(exterior_material_name).startswith(
                    AO_MATERIAL_PREFIX
                )
            ),
            "slot0_blender_material_consumes_ao_uv2": bool(
                exterior_material
                and exterior_material["ao_contract_consumed"]
            ),
        }
        passed = all(checks.values())
        target_passes.append(passed)
        target_results[target] = {
            "baseline_uv_names": base_uv_names,
            "candidate_uv_names": current_uv_names,
            "uv0_uv1_checks": uv0_uv1_checks,
            "uv2": uv2,
            "checks": checks,
            "passed": passed,
        }

    ao_user_objects = sorted(
        {
            object_name
            for users in candidate["ao_material_users"].values()
            for object_name in users
        }
    )
    section_ao_bindings = {
        name: materials
        for name, materials in candidate["section_ao_materials"].items()
        if materials
    }
    scene_state_checks = {
        "render_engine_restored": (
            baseline["scene_state"]["render_engine"]
            == candidate["scene_state"]["render_engine"]
        ),
        "active_object_restored": (
            baseline["scene_state"]["active_object"]
            == candidate["scene_state"]["active_object"]
        ),
        "selection_restored": (
            baseline["scene_state"]["selected_objects"]
            == candidate["scene_state"]["selected_objects"]
        ),
        "visibility_and_render_flags_restored": (
            baseline["scene_state"]["object_states"]
            == candidate["scene_state"]["object_states"]
        ),
    }
    global_checks = {
        "five_targets_present_in_both_blends": (
            baseline["target_count"] == 5
            and candidate["target_count"] == 5
        ),
        "object_identity_and_types_unchanged": (
            baseline["all_object_names_and_types"]
            == candidate["all_object_names_and_types"]
        ),
        "baseline_has_no_r2x_uv2_owner": (
            baseline["uv2_owners"] == []
        ),
        "candidate_uv2_owners_are_exactly_five_r2j_shells": (
            set(candidate["uv2_owners"]) == R2J_EXTERIOR_SET
            and len(candidate["uv2_owners"]) == 5
        ),
        "baseline_and_candidate_have_same_ten_sections": (
            baseline["section_object_count"] == 10
            and candidate["section_object_count"] == 10
            and baseline["section_objects"] == candidate["section_objects"]
        ),
        "ten_sections_have_no_r2x_ao_material": (
            not section_ao_bindings
        ),
        "r2x_ao_material_users_are_only_the_five_targets": (
            set(ao_user_objects) == R2J_EXTERIOR_SET
        ),
        "scene_transaction_state_restored": all(
            scene_state_checks.values()
        ),
        "candidate_blend_was_not_dirty_when_opened": (
            candidate["blend_was_dirty_when_probed"] is False
        ),
        "candidate_probe_requested_no_save_or_mutation": (
            candidate["scene_saved"] is False
            and candidate["scene_mutations_requested"] is False
        ),
        "direct_uv2_cross_object_overlap_is_zero": (
            (
                candidate.get("uv2_cross_object_overlap") or {}
            ).get("no_cross_object_overlap")
            is True
        ),
    }
    return {
        "targets": target_results,
        "scene_state_checks": scene_state_checks,
        "section_ao_bindings": section_ao_bindings,
        "ao_material_users": candidate["ao_material_users"],
        "global_checks": global_checks,
        "all_targets_passed": all(target_passes)
        and len(target_passes) == 5,
        "all_global_checks_passed": all(global_checks.values()),
        "passed": (
            all(target_passes)
            and len(target_passes) == 5
            and all(global_checks.values())
        ),
    }


def _collect_artifact_records(value: Any) -> list[dict[str, Any]]:
    """Collect nested build-report objects containing path/SHA evidence."""

    records: list[dict[str, Any]] = []
    if isinstance(value, dict):
        lowered = {str(key).casefold(): key for key in value}
        path_key = next(
            (
                lowered[name]
                for name in ("path", "file", "filepath")
                if name in lowered
            ),
            None,
        )
        sha_key = next(
            (
                lowered[name]
                for name in ("sha256", "sha-256", "digest")
                if name in lowered
            ),
            None,
        )
        if path_key is not None and sha_key is not None:
            records.append(
                {
                    "path": value[path_key],
                    "sha256": value[sha_key],
                }
            )
        for child in value.values():
            records.extend(_collect_artifact_records(child))
    elif isinstance(value, list):
        for child in value:
            records.extend(_collect_artifact_records(child))
    return records


def _all_string_values(value: Any) -> Iterator[str]:
    """Yield all nested string values from a JSON-compatible object."""

    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for child in value.values():
            yield from _all_string_values(child)
    elif isinstance(value, list):
        for child in value:
            yield from _all_string_values(child)


def _find_mapping_by_key_fragment(
    value: Any,
    fragment: str,
) -> list[dict[str, Any]]:
    """Return nested mappings stored under keys containing a fragment."""

    findings: list[dict[str, Any]] = []
    if isinstance(value, dict):
        for key, child in value.items():
            if (
                fragment.casefold() in str(key).casefold()
                and isinstance(child, dict)
            ):
                findings.append(child)
            findings.extend(_find_mapping_by_key_fragment(child, fragment))
    elif isinstance(value, list):
        for child in value:
            findings.extend(_find_mapping_by_key_fragment(child, fragment))
    return findings


def _truthy_restored(value: Any) -> bool:
    """Normalize build-report transaction restoration values."""

    if value is True:
        return True
    if isinstance(value, str):
        return value.casefold() in {
            "true",
            "restored",
            "removed",
            "clean",
            "passed",
            "pass",
        }
    return False


def _transaction_restore_check(
    transaction: dict[str, Any],
    key_fragments: Sequence[str],
) -> bool:
    """Find at least one true restoration field matching all fragments."""

    for pointer, key, value in _walk_json(transaction):
        location = f"{pointer}/{key or ''}".casefold()
        if all(
            fragment.casefold() in location for fragment in key_fragments
        ) and _truthy_restored(value):
            return True
    return False


def _extract_visible_whitelist(
    transaction: dict[str, Any],
) -> list[str] | None:
    """Extract the exact visible-mesh whitelist from a build report."""

    preferred = (
        "visible_mesh_whitelist",
        "visible_objects_whitelist",
        "bake_visible_meshes",
        "visible_meshes",
    )
    for name in preferred:
        value = transaction.get(name)
        if isinstance(value, list):
            return [str(item) for item in value]
    for _, key, value in _walk_json(transaction):
        if (
            key is not None
            and "visible" in key.casefold()
            and "mesh" in key.casefold()
            and isinstance(value, list)
        ):
            return [str(item) for item in value]
    return None


def _atlas_target_entries(
    atlas: dict[str, Any],
) -> dict[str, dict[str, Any]]:
    """Extract per-target UV2 atlas evidence from common report layouts."""

    for container_name in ("targets", "objects", "per_object"):
        container = atlas.get(container_name)
        if isinstance(container, dict):
            return {
                str(name): value
                for name, value in container.items()
                if isinstance(value, dict)
            }
    return {
        str(name): value
        for name, value in atlas.items()
        if name in R2J_EXTERIOR_SET and isinstance(value, dict)
    }


def _positive_number(value: Any) -> bool:
    """Return whether a value is a finite number greater than zero."""

    return (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and math.isfinite(float(value))
        and float(value) > 0.0
    )


def _entry_padding_valid(entry: dict[str, Any]) -> bool:
    """Return whether one atlas entry records positive pixel/UV padding."""

    padding_px = entry.get("padding_px")
    padding_uv = entry.get("padding_uv")
    if padding_px is None and isinstance(entry.get("padding"), dict):
        padding_px = entry["padding"].get("px")
        padding_uv = entry["padding"].get("uv")
    return _positive_number(padding_px) and _positive_number(padding_uv)


def _validator_contract(
    report: dict[str, Any],
) -> dict[str, Any]:
    """Normalize official Khronos Validator availability and 0/0 counts."""

    candidates = _find_mapping_by_key_fragment(report, "validator")
    selected = next(
        (
            item
            for item in candidates
            if any(
                key in item
                for key in (
                    "errors",
                    "warnings",
                    "numErrors",
                    "numWarnings",
                    "issue_counts",
                )
            )
        ),
        candidates[0] if candidates else None,
    )
    if selected is None:
        return {
            "available": False,
            "status": "missing",
            "errors": None,
            "warnings": None,
            "zero_errors_zero_warnings": False,
        }
    issue_counts = selected.get("issue_counts")
    if not isinstance(issue_counts, dict):
        issue_counts = {}
    errors = selected.get("errors", selected.get("numErrors"))
    warnings = selected.get("warnings", selected.get("numWarnings"))
    if errors is None:
        errors = issue_counts.get("errors", issue_counts.get("numErrors"))
    if warnings is None:
        warnings = issue_counts.get(
            "warnings", issue_counts.get("numWarnings")
        )
    available_value = selected.get("available")
    status = str(selected.get("status", "") or "")
    implementation = str(
        selected.get("implementation")
        or selected.get("package")
        or selected.get("tool")
        or selected.get("module")
        or ""
    )
    available = (
        available_value is True
        or (
            errors is not None
            and warnings is not None
            and status.casefold() not in {
                "not_run",
                "unavailable",
                "missing",
            }
        )
    )
    official_identity = (
        "khronos" in implementation.casefold()
        or "gltf-validator" in implementation.casefold()
        or "gltf validator" in implementation.casefold()
    )
    try:
        error_count = int(errors) if errors is not None else None
        warning_count = int(warnings) if warnings is not None else None
    except (TypeError, ValueError):
        error_count = None
        warning_count = None
    return {
        "available": available,
        "status": status or None,
        "implementation": implementation or None,
        "official_identity_recorded": official_identity,
        "errors": error_count,
        "warnings": warning_count,
        "zero_errors_zero_warnings": (
            available
            and official_identity
            and error_count == 0
            and warning_count == 0
        ),
        "raw": selected,
    }


def audit_build_report(
    path: Path,
    actual_artifacts: dict[str, dict[str, Any]],
    ao_png: dict[str, Any],
) -> dict[str, Any]:
    """Validate build-time UV/transaction/hash/stop-line evidence."""

    report = load_json_object(path)
    target_block = report.get("targets")
    if not isinstance(target_block, dict):
        target_block = {}
    atlas = report.get("uv2_atlas")
    if not isinstance(atlas, dict):
        atlas = {}
    atlas_entries = _atlas_target_entries(atlas)
    transaction = report.get("bake_transaction")
    if not isinstance(transaction, dict):
        transaction = {}
    stop_lines = report.get("approval_stop_lines")
    if not isinstance(stop_lines, dict):
        stop_lines = {}
    output_records = _collect_artifact_records(report.get("outputs") or {})
    normalized_output_hashes = {
        str(record.get("sha256") or "").casefold()
        for record in output_records
    }
    output_hash_checks = {
        name: (
            artifact.get("sha256") is not None
            and str(artifact["sha256"]).casefold()
            in normalized_output_hashes
        )
        for name, artifact in actual_artifacts.items()
        if name in {"candidate_blend", "ao_png"}
    }
    input_lock_strings = {
        value.casefold()
        for value in _all_string_values(report.get("input_lock") or {})
    }
    target_uv_checks = {
        target: (
            isinstance(target_block.get(target), dict)
            and target_block[target].get("uv0_uv1_unchanged") is True
        )
        for target in R2J_EXTERIOR_OBJECTS
    }
    atlas_target_checks = {}
    for target in R2J_EXTERIOR_OBJECTS:
        entry = atlas_entries.get(target) or {}
        atlas_target_checks[target] = {
            "entry_present": bool(entry),
            "finite": entry.get("finite") is True,
            "in_range": entry.get("in_range") is True,
            "positive_padding_uv_and_px": _entry_padding_valid(entry),
            "bounds_recorded": isinstance(entry.get("bounds"), (dict, list)),
        }
    whitelist = _extract_visible_whitelist(transaction)
    transaction_checks = {
        "visible_mesh_whitelist_is_exactly_five_targets": (
            whitelist is not None
            and set(whitelist) == R2J_EXTERIOR_SET
            and len(whitelist) == 5
        ),
        "visibility_restored": _transaction_restore_check(
            transaction, ("visibility", "restore")
        ),
        "selection_restored": _transaction_restore_check(
            transaction, ("selection", "restore")
        ),
        "render_engine_restored": _transaction_restore_check(
            transaction, ("render", "restore")
        ),
        "temporary_nodes_restored_or_removed": (
            _transaction_restore_check(
                transaction, ("temporary", "node")
            )
            or _transaction_restore_check(transaction, ("temp", "node"))
        ),
    }
    ao_image = report.get("ao_image")
    if not isinstance(ao_image, dict):
        ao_image = {}
    report_min = ao_image.get("min_u8", ao_image.get("min"))
    report_max = ao_image.get("max_u8", ao_image.get("max"))
    report_mean = ao_image.get("mean_u8", ao_image.get("mean"))
    report_std = ao_image.get(
        "stddev_u8", ao_image.get("std", ao_image.get("stddev"))
    )
    report_nonwhite = ao_image.get("nonwhite_ratio")
    numeric_image_stats = (
        report_min,
        report_max,
        report_mean,
        report_std,
    )
    normalized_unit_stats = (
        all(
            isinstance(value, (int, float)) and not isinstance(value, bool)
            for value in numeric_image_stats
        )
        and float(report_max) <= 1.0 + FLOAT_TOLERANCE
    )

    def stat_matches(
        report_value: Any,
        independent_u8_value: float,
    ) -> bool:
        """Compare either normalized [0,1] or direct u8 report statistics."""

        if not isinstance(report_value, (int, float)) or isinstance(
            report_value, bool
        ):
            return False
        expected = (
            independent_u8_value / 255.0
            if normalized_unit_stats
            else independent_u8_value
        )
        tolerance = 1.0e-6 if normalized_unit_stats else 1.0e-6
        return math.isclose(
            float(report_value),
            float(expected),
            rel_tol=0.0,
            abs_tol=tolerance,
        )

    ao_image_checks = {
        "sha256_matches": str(ao_image.get("sha256") or "").casefold()
        == str(ao_png["payload_sha256"]).casefold(),
        "dimensions_match": (
            int(ao_image.get("width", -1)) == ao_png["width"]
            and int(ao_image.get("height", -1)) == ao_png["height"]
        ),
        "statistics_scale_is_u8_or_normalized_unit": (
            all(
                isinstance(value, (int, float))
                and not isinstance(value, bool)
                for value in numeric_image_stats
            )
        ),
        "min_matches": stat_matches(
            report_min, float(ao_png["red"]["min_u8"])
        ),
        "max_matches": stat_matches(
            report_max, float(ao_png["red"]["max_u8"])
        ),
        "mean_matches": stat_matches(
            report_mean, float(ao_png["red"]["mean_u8"])
        ),
        "std_matches": stat_matches(
            report_std, float(ao_png["red"]["stddev_u8"])
        ),
        "nonwhite_ratio_matches": (
            isinstance(report_nonwhite, (int, float))
            and math.isclose(
                float(report_nonwhite),
                float(ao_png["red"]["nonwhite_ratio"]),
                rel_tol=0.0,
                abs_tol=1.0e-9,
            )
        ),
    }
    stop_line_checks = {
        name: stop_lines.get(name) is False
        for name in (
            "approval_granted",
            "p50_approved",
            "production_integration_allowed",
            "next_release_stage_allowed",
        )
    }
    validator = _validator_contract(report)
    cross_object_overlap_pairs = atlas.get(
        "cross_object_overlap_pairs",
        atlas.get("overlap_pairs"),
    )
    checks = {
        "schema_version_recorded": bool(report.get("schema_version")),
        "stage_id_matches": report.get("stage_id") == STAGE_ID,
        "requirement_id_matches": (
            report.get("requirement_id") == REQUIREMENT_ID
        ),
        "locked_v5_blend_hash_recorded": (
            LOCKS["v5_direct_open_blend"][1].casefold()
            in input_lock_strings
        ),
        "all_candidate_output_hashes_match": all(
            output_hash_checks.values()
        )
        and len(output_hash_checks) == 2,
        "targets_are_exactly_the_five_r2j_shells": (
            set(target_block) == R2J_EXTERIOR_SET
            and len(target_block) == 5
        ),
        "build_reports_uv0_uv1_unchanged_for_all_targets": all(
            target_uv_checks.values()
        ),
        "atlas_entries_are_exactly_the_five_targets": (
            set(atlas_entries) == R2J_EXTERIOR_SET
            and len(atlas_entries) == 5
        ),
        "atlas_targets_are_finite_in_range_and_padded": all(
            all(result.values()) for result in atlas_target_checks.values()
        ),
        "atlas_cross_object_overlap_pairs_empty": (
            cross_object_overlap_pairs == []
            and atlas.get("all_cross_object_disjoint", True) is True
        ),
        "atlas_expanded_overlap_pairs_empty": (
            atlas.get("expanded_overlap_pairs") == []
            and atlas.get("all_bake_margin_expanded_disjoint", True) is True
        ),
        "bake_transaction_restored": all(transaction_checks.values()),
        "ao_image_statistics_match_independent_decode": all(
            ao_image_checks.values()
        ),
        "approval_stop_lines_are_all_false": all(
            stop_line_checks.values()
        ),
        "official_khronos_validator_is_zero_errors_zero_warnings": (
            validator["zero_errors_zero_warnings"] is True
        ),
    }
    return {
        "artifact": artifact_record(path),
        "schema_version": report.get("schema_version"),
        "status": report.get("status"),
        "output_artifact_records": output_records,
        "output_hash_checks": output_hash_checks,
        "target_uv0_uv1_checks": target_uv_checks,
        "atlas_target_checks": atlas_target_checks,
        "transaction_visible_mesh_whitelist": whitelist,
        "transaction_checks": transaction_checks,
        "ao_image_checks": ao_image_checks,
        "stop_lines": stop_lines,
        "stop_line_checks": stop_line_checks,
        "khronos_validator": validator,
        "checks": checks,
        "passed": all(checks.values()),
    }


def audit_khronos_report(
    path: Path,
    candidate_glb: Path,
) -> dict[str, Any]:
    """Verify the raw official Khronos report is bound to this exact GLB."""

    report = load_json_object(path)
    candidate_sha256 = sha256_file(candidate_glb)
    assets = report.get("assets")
    if not isinstance(assets, list):
        assets = []
    matching_assets = [
        asset
        for asset in assets
        if (
            isinstance(asset, dict)
            and str(asset.get("sha256") or "").casefold()
            == candidate_sha256.casefold()
        )
    ]
    asset = matching_assets[0] if len(matching_assets) == 1 else None
    native_issues = report.get("issues")
    native_schema = (
        isinstance(native_issues, dict)
        and isinstance(report.get("validatorVersion"), str)
        and report.get("mimeType") == "model/gltf-binary"
    )
    issue_counts = (
        asset.get("issue_counts")
        if isinstance(asset, dict)
        and isinstance(asset.get("issue_counts"), dict)
        else native_issues
        if isinstance(native_issues, dict)
        else {}
    )
    errors = issue_counts.get(
        "errors",
        issue_counts.get(
            "numErrors",
            asset.get("errors")
            if isinstance(asset, dict)
            else issue_counts.get("numErrors"),
        ),
    )
    warnings = issue_counts.get(
        "warnings",
        issue_counts.get(
            "numWarnings",
            asset.get("warnings")
            if isinstance(asset, dict)
            else issue_counts.get("numWarnings"),
        ),
    )
    try:
        error_count = int(errors) if errors is not None else None
        warning_count = int(warnings) if warnings is not None else None
    except (TypeError, ValueError):
        error_count = None
        warning_count = None
    validator = report.get("validator")
    if not isinstance(validator, dict):
        validator = {}
    if native_schema:
        validator = {
            "implementation": "KhronosGroup/glTF-Validator native report",
            "validator_version": report.get("validatorVersion"),
        }
    identity_text = " ".join(
        str(value)
        for value in (
            validator.get("implementation"),
            validator.get("package"),
            validator.get("module"),
            validator.get("validator_version"),
        )
        if value
    )
    official_identity = any(
        token in identity_text.casefold()
        for token in ("khronos", "gltf-validator", "gltf validator")
    )
    raw_uri_name = Path(str(report.get("uri") or "")).name
    native_uri_matches = raw_uri_name in {
        candidate_glb.name,
        candidate_glb.name + ".building",
    }
    wrapper_asset_matches = (
        len(matching_assets) == 1
        and isinstance(asset, dict)
        and Path(str(asset.get("path") or "")).name
        == candidate_glb.name
    )
    checks = {
        "report_identity_is_bound_to_candidate_name_or_sha256": (
            native_uri_matches if native_schema else wrapper_asset_matches
        ),
        "official_khronos_validator_identity_recorded": official_identity,
        "zero_errors": error_count == 0,
        "zero_warnings": warning_count == 0,
        "asset_or_native_report_passed": (
            error_count == 0 and warning_count == 0
            if native_schema
            else isinstance(asset, dict) and asset.get("passed") is True
        ),
        "wrapper_report_passed_or_native_schema_valid": (
            native_schema or report.get("passed") is True
        ),
    }
    return {
        "artifact": artifact_record(path),
        "candidate_glb_sha256": candidate_sha256,
        "validator": validator,
        "native_report_schema": native_schema,
        "raw_uri": report.get("uri"),
        "matching_asset": asset,
        "errors": error_count,
        "warnings": warning_count,
        "checks": checks,
        "passed": all(checks.values()),
    }


def _before_after_hash_pairs(
    value: Any,
    pointer: str = "",
) -> list[dict[str, Any]]:
    """Collect nested before/after hash pairs from a repack report."""

    pairs: list[dict[str, Any]] = []
    if isinstance(value, dict):
        before_key = (
            "before"
            if "before" in value
            else "before_sha256"
            if "before_sha256" in value
            else None
        )
        after_key = (
            "after"
            if "after" in value
            else "after_sha256"
            if "after_sha256" in value
            else None
        )
        if before_key is not None and after_key is not None:
            before = value[before_key]
            after = value[after_key]
            if isinstance(before, dict):
                before = before.get("sha256", before.get("hash"))
            if isinstance(after, dict):
                after = after.get("sha256", after.get("hash"))
            if isinstance(before, str) and isinstance(after, str):
                pairs.append(
                    {
                        "pointer": pointer or "/",
                        "before": before,
                        "after": after,
                        "equal": before.casefold() == after.casefold(),
                    }
                )
        for key, child in value.items():
            pairs.extend(
                _before_after_hash_pairs(child, f"{pointer}/{key}")
            )
    elif isinstance(value, list):
        for index, child in enumerate(value):
            pairs.extend(
                _before_after_hash_pairs(child, f"{pointer}/{index}")
            )
    return pairs


def audit_repack_report(
    path: Path,
    candidate_glb: Path,
    khronos_report_path: Path,
) -> dict[str, Any]:
    """Validate the surgical v5payload repack report and closed stop lines."""

    report = load_json_object(path)
    candidate_sha256 = sha256_file(candidate_glb)
    output_records = _collect_artifact_records(report.get("output") or {})
    output_hashes = {
        str(record.get("sha256") or "").casefold()
        for record in output_records
    }
    baseline_evidence = {
        value.casefold()
        for value in _all_string_values(
            {
                "input_lock": report.get("input_lock"),
                "baseline_identity": report.get("baseline_identity"),
                "v5_payload_identity": report.get("v5_payload_identity"),
            }
        )
    }
    protected = report.get("protected_hashes_before_after")
    protected_pairs = _before_after_hash_pairs(protected)
    protected_unchanged_flags = [
        value
        for pointer, key, value in _walk_json(protected)
        if (
            key is not None
            and any(
                token in key.casefold()
                for token in ("unchanged", "equal", "matches")
            )
            and isinstance(value, bool)
        )
    ]
    glb_contract = report.get("glb_contract")
    if not isinstance(glb_contract, dict):
        glb_contract = {}
    stop_lines = report.get("approval_stop_lines")
    if not isinstance(stop_lines, dict):
        stop_lines = {}
    stop_line_checks = {
        name: stop_lines.get(name) is False
        for name in (
            "approval_granted",
            "p50_approved",
            "production_integration_allowed",
            "next_release_stage_allowed",
            "ao_2k_approved",
        )
    }
    validator = _validator_contract(report)
    validator_artifacts = _collect_artifact_records(
        report.get("khronos_validator") or {}
    )
    actual_khronos_sha256 = sha256_file(khronos_report_path)
    validator_report_hashes = {
        str(record.get("sha256") or "").casefold()
        for record in validator_artifacts
    }
    errors = report.get("errors")
    status = str(report.get("status") or "")
    checks = {
        "schema_version_matches": (
            report.get("schema_version", report.get("schema"))
            == "bf3d.r2x.r2j_ao_v5_payload_repack.v1"
        ),
        "stage_id_matches": report.get("stage_id") == STAGE_ID,
        "requirement_id_matches": (
            report.get("requirement_id") == REQUIREMENT_ID
        ),
        "locked_v5_material_glb_hash_recorded": (
            LOCKS["v5_material_glb"][1].casefold()
            in baseline_evidence
        ),
        "output_hash_matches_exact_candidate_glb": (
            candidate_sha256.casefold() in output_hashes
        ),
        "protected_before_after_hashes_recorded_and_equal": (
            bool(protected_pairs)
            and all(pair["equal"] for pair in protected_pairs)
            and all(protected_unchanged_flags)
        ),
        "reported_glb_contract_passed": (
            glb_contract.get("passed") is True
        ),
        "reported_khronos_zero_errors_zero_warnings": (
            validator["zero_errors_zero_warnings"] is True
        ),
        "reported_khronos_artifact_matches_raw_report": (
            actual_khronos_sha256.casefold() in validator_report_hashes
        ),
        "errors_empty": errors in (None, []),
        "status_does_not_claim_p50_or_production_approval": (
            "p50_approved" not in status.casefold()
            and "production_approved" not in status.casefold()
        ),
        "approval_stop_lines_are_all_false": all(
            stop_line_checks.values()
        ),
    }
    return {
        "artifact": artifact_record(path),
        "schema_version": report.get("schema_version", report.get("schema")),
        "status": status,
        "output_records": output_records,
        "protected_hash_pairs": protected_pairs,
        "protected_unchanged_flags": protected_unchanged_flags,
        "glb_contract": glb_contract,
        "khronos_validator": validator,
        "khronos_artifact_records": validator_artifacts,
        "actual_khronos_report": artifact_record(khronos_report_path),
        "stop_lines": stop_lines,
        "stop_line_checks": stop_line_checks,
        "checks": checks,
        "passed": all(checks.values()),
    }


def _paths_are_safe_and_distinct(
    blend: Path,
    ao_png: Path,
    material_glb: Path,
    build_report: Path,
    repack_report: Path,
    khronos_report: Path,
    output: Path,
) -> dict[str, Any]:
    """Prove every candidate/report path is scoped to the R2X stage."""

    candidate_paths = {
        "candidate_blend": blend.resolve(),
        "ao_png": ao_png.resolve(),
        "material_glb": material_glb.resolve(),
        "build_report": build_report.resolve(),
        "repack_report": repack_report.resolve(),
        "khronos_report": khronos_report.resolve(),
    }
    locked_paths = {path.resolve() for path, _ in LOCKS.values()}
    return {
        "candidate_paths_inside_stage_root": all(
            is_within(path, STAGE_ROOT)
            for path in candidate_paths.values()
        ),
        "output_is_exact_locked_audit_path": (
            output.resolve() == DEFAULT_OUTPUT.resolve()
        ),
        "candidate_paths_do_not_alias_locked_inputs": all(
            path not in locked_paths for path in candidate_paths.values()
        ),
        "candidate_paths_are_unique": (
            len(set(candidate_paths.values())) == len(candidate_paths)
        ),
        "candidate_filenames_do_not_claim_approval_or_production": all(
            not any(
                token in path.name.casefold()
                for token in ("approved", "production", "p50")
            )
            for path in candidate_paths.values()
        ),
        "resolved_candidate_paths": {
            name: relative_path(path)
            for name, path in candidate_paths.items()
        },
    }


def _snapshots_unchanged(
    before: dict[str, dict[str, Any]],
    after: dict[str, dict[str, Any]],
) -> bool:
    """Return whether all measured candidate SHA values stayed unchanged."""

    return (
        set(before) == set(after)
        and all(
            before[name].get("sha256") == after[name].get("sha256")
            and before[name].get("bytes") == after[name].get("bytes")
            for name in before
        )
    )


def build_audit(
    *,
    blender_exe: Path,
    candidate_blend: Path,
    ao_png_path: Path,
    material_glb_path: Path,
    build_report_path: Path,
    repack_report_path: Path,
    khronos_report_path: Path,
    output: Path,
    blender_timeout: int,
) -> dict[str, Any]:
    """Build the complete fail-closed R2X 1K audit report."""

    path_safety = _paths_are_safe_and_distinct(
        candidate_blend,
        ao_png_path,
        material_glb_path,
        build_report_path,
        repack_report_path,
        khronos_report_path,
        output,
    )
    if not all(
        value
        for key, value in path_safety.items()
        if key != "resolved_candidate_paths"
    ):
        raise AuditError(f"Unsafe R2X path configuration: {path_safety}")

    pre_locks = lock_snapshot()
    if not pre_locks["all_locks_passed"]:
        failed = [
            name
            for name, record in pre_locks["artifacts"].items()
            if not record["lock_passed"]
        ]
        raise AuditError(f"Locked V5/formal input hash failed: {failed}")
    pre_candidates = candidate_snapshot(
        candidate_blend,
        ao_png_path,
        material_glb_path,
        build_report_path,
        repack_report_path,
        khronos_report_path,
    )
    missing = [
        name
        for name, record in pre_candidates.items()
        if not record["exists"]
    ]
    if missing:
        raise AuditError(f"R2X candidate artifacts are missing: {missing}")

    ao_png = png_statistics(ao_png_path)
    baseline_glb = audit_material_glb(V5_MATERIAL_GLB, require_ao=False)
    candidate_glb = audit_material_glb(
        material_glb_path, require_ao=True
    )
    glb_comparison = compare_material_glbs(
        baseline_glb, candidate_glb, ao_png
    )
    build_report = audit_build_report(
        build_report_path, pre_candidates, ao_png
    )
    repack_report = audit_repack_report(
        repack_report_path, material_glb_path, khronos_report_path
    )
    khronos_report = audit_khronos_report(
        khronos_report_path, material_glb_path
    )
    v5_payload_identity = audit_v5_payload_identity(
        V5_MATERIAL_GLB, material_glb_path, ao_png_path
    )

    with tempfile.TemporaryDirectory(
        prefix="bf3d_r2x_ao_audit_"
    ) as temporary:
        temporary_root = Path(temporary)
        baseline_probe = launch_blend_probe(
            blender_exe,
            V5_BLEND,
            "baseline",
            ao_png_path,
            temporary_root / "baseline_probe.json",
            blender_timeout,
        )
        candidate_probe = launch_blend_probe(
            blender_exe,
            candidate_blend,
            "candidate",
            ao_png_path,
            temporary_root / "candidate_probe.json",
            blender_timeout,
        )
    blend_comparison = compare_blend_probes(
        baseline_probe, candidate_probe
    )

    post_locks = lock_snapshot()
    post_candidates = candidate_snapshot(
        candidate_blend,
        ao_png_path,
        material_glb_path,
        build_report_path,
        repack_report_path,
        khronos_report_path,
    )
    locks_unchanged = (
        pre_locks["all_locks_passed"]
        and post_locks["all_locks_passed"]
        and all(
            pre_locks["artifacts"][name]["sha256"]
            == post_locks["artifacts"][name]["sha256"]
            for name in pre_locks["artifacts"]
        )
    )
    candidates_unchanged = _snapshots_unchanged(
        pre_candidates, post_candidates
    )

    candidate_glb_structure_checks = {
        "gltf_asset_version_is_2_0": str(
            (candidate_glb.get("asset") or {}).get("version")
        )
        == "2.0",
        "material_review_contains_exactly_five_meshes_and_primitives": (
            candidate_glb["mesh_count"] == 5
            and candidate_glb["primitive_count"] == 5
            and candidate_glb["r2j_exterior_primitive_count"] == 5
            and candidate_glb["missing_targets"] == []
            and candidate_glb["extra_meshes"] == []
        ),
        "material_review_contains_no_section_mesh": (
            candidate_glb["section_meshes"] == []
        ),
        "forbidden_name_count_is_zero": (
            candidate_glb["path_and_name_findings"][
                "forbidden_name_count"
            ]
            == 0
        ),
        "local_absolute_path_count_is_zero": (
            candidate_glb["path_and_name_findings"][
                "local_absolute_path_count"
            ]
            == 0
        ),
        "external_resource_count_is_zero": (
            candidate_glb["resource_findings"][
                "external_resource_count"
            ]
            == 0
        ),
        "missing_resource_count_is_zero": (
            candidate_glb["resource_findings"]["missing_resource_count"]
            == 0
        ),
        "five_exterior_primitives_pass_texture_and_uv_contract": (
            glb_comparison["all_targets_passed"]
        ),
        "all_five_exteriors_share_one_embedded_ao_image": (
            glb_comparison["all_targets_share_one_occlusion_image"]
        ),
    }
    png_checks = {
        "source_is_png": str(ao_png["source_format"]).upper() == "PNG",
        "resolution_is_exactly_1024_square": (
            ao_png["width"] == 1024 and ao_png["height"] == 1024
        ),
        "red_channel_is_not_uniform_white": (
            ao_png["red_channel_is_uniform_white"] is False
            and ao_png["red"]["min_u8"] < 255
            and ao_png["red"]["nonwhite_sample_count"] > 0
        ),
        "red_channel_has_nonzero_variation": (
            ao_png["red_channel_has_variation"] is True
        ),
    }
    assertions = {
        "contract_file_exists": CONTRACT_PATH.is_file(),
        "candidate_path_scope_is_safe": all(
            value
            for key, value in path_safety.items()
            if key != "resolved_candidate_paths"
        ),
        "locked_v5_and_formal_hashes_pass_before_audit": (
            pre_locks["all_locks_passed"]
        ),
        "locked_v5_and_formal_hashes_pass_after_audit": (
            post_locks["all_locks_passed"]
        ),
        "locked_v5_and_formal_hashes_unchanged_during_audit": (
            locks_unchanged
        ),
        "candidate_artifacts_unchanged_during_audit": candidates_unchanged,
        "ao_png_1k_red_channel_contract_passed": all(
            png_checks.values()
        ),
        "build_report_contract_passed": build_report["passed"],
        "v5_payload_repack_report_contract_passed": (
            repack_report["passed"]
        ),
        "raw_khronos_validator_zero_errors_zero_warnings": (
            khronos_report["passed"]
        ),
        "v5_payload_surgical_identity_contract_passed": (
            v5_payload_identity["passed"]
        ),
        "blend_uv_geometry_material_contract_passed": (
            blend_comparison["passed"]
        ),
        "material_glb_contract_passed": all(
            candidate_glb_structure_checks.values()
        ),
    }
    audit_passed = all(assertions.values())
    report = {
        "schema_version": SCHEMA_VERSION,
        "requirement_id": REQUIREMENT_ID,
        "stage_id": STAGE_ID,
        "generated_at": now_iso(),
        "attempt_history": list(REGISTERED_ATTEMPT_HISTORY),
        "audit_mode": "fail_closed_read_only",
        "contract": artifact_record(CONTRACT_PATH),
        "scope": {
            "persistent_write": relative_path(output),
            "asset_mutation_allowed": False,
            "blend_save_allowed": False,
            "model_or_texture_generation_allowed": False,
            "does_not_approve_or_complete": [
                "Three.js runtime aoMap.channel===2 verification",
                "AO on/off visual whitelist",
                "cross-engine/cross-viewport matrix",
                "2K controlled candidate",
                "P50",
                "production integration",
                "next release stage",
            ],
        },
        "path_safety": path_safety,
        "input_locks_before": pre_locks,
        "input_locks_after": post_locks,
        "candidate_artifacts_before": pre_candidates,
        "candidate_artifacts_after": post_candidates,
        "ao_png": {
            "statistics": ao_png,
            "checks": png_checks,
            "passed": all(png_checks.values()),
        },
        "build_report_audit": build_report,
        "v5_payload_repack_report_audit": repack_report,
        "raw_khronos_validator_audit": khronos_report,
        "v5_payload_surgical_identity": v5_payload_identity,
        "locked_v5_material_glb": baseline_glb,
        "candidate_material_glb": candidate_glb,
        "material_glb_comparison": glb_comparison,
        "candidate_material_glb_checks": candidate_glb_structure_checks,
        "blender_read_only_probes": {
            "baseline": baseline_probe,
            "candidate": candidate_probe,
            "comparison": blend_comparison,
        },
        "size_budget": {
            "ao_png_payload_bytes": ao_png["artifact"]["bytes"],
            "ao_decoded_rgba8_bytes": ao_png["decoded_rgba8_bytes"],
            "ao_decoded_rgba8_mib": ao_png["decoded_rgba8_mib"],
            "ao_decoded_rgba8_with_full_mips_bytes": (
                ao_png["decoded_rgba8_with_full_mips_bytes"]
            ),
            "ao_decoded_rgba8_with_full_mips_mib": (
                ao_png["decoded_rgba8_with_full_mips_mib"]
            ),
            "locked_v5_material_glb_bytes": baseline_glb["artifact"][
                "bytes"
            ],
            "candidate_material_glb_bytes": candidate_glb["artifact"][
                "bytes"
            ],
            "candidate_material_glb_delta_bytes": (
                int(candidate_glb["artifact"]["bytes"])
                - int(baseline_glb["artifact"]["bytes"])
            ),
        },
        "assertions": assertions,
        "audit_completed": True,
        "audit_passed": audit_passed,
        "contract_machine_gate_passed": audit_passed,
        "smoke1k_upgrade_gate_passed": False,
        "three_runtime_gate_passed": False,
        "visual_whitelist_gate_passed": False,
        "ao_2k_approved": False,
        "approval_granted": False,
        "p50_approved": False,
        "production_integration_allowed": False,
        "next_release_stage_allowed": False,
        "conclusion": (
            "R2X 1K AO candidate machine evidence passed this read-only "
            "audit scope."
            if audit_passed
            else "R2X 1K AO candidate failed closed; see false assertions."
        ),
        "next_action_boundary": (
            "Even when this audit passes, Three.js runtime consumption, "
            "AO on/off visual review and the required browser matrix remain "
            "separate mandatory evidence before any 2K/P50/release decision."
        ),
    }
    return report


def parse_args(argv: Sequence[str]) -> argparse.Namespace:
    """Create and parse the normal/internal Blender-probe CLI."""

    parser = argparse.ArgumentParser(
        description=(
            "Read-only, fail-closed audit of the WEB-60 R2X R2J 1K AO "
            "candidate Blend, PNG, material GLB and build report."
        )
    )
    parser.add_argument(
        "--candidate-blend",
        type=Path,
        default=DEFAULT_CANDIDATE_BLEND,
        help="R2X candidate Blend; must remain inside the R2X stage.",
    )
    parser.add_argument(
        "--ao-png",
        type=Path,
        default=DEFAULT_AO_PNG,
        help="Independent 1K AO PNG.",
    )
    parser.add_argument(
        "--material-glb",
        type=Path,
        default=DEFAULT_MATERIAL_GLB,
        help="R2X material-review GLB.",
    )
    parser.add_argument(
        "--build-report",
        type=Path,
        default=DEFAULT_BUILD_REPORT,
        help="R2X build report containing transaction/atlas evidence.",
    )
    parser.add_argument(
        "--repack-report",
        type=Path,
        default=DEFAULT_REPACK_REPORT,
        help="Surgical V5-payload repack report.",
    )
    parser.add_argument(
        "--khronos-report",
        type=Path,
        default=DEFAULT_KHRONOS_REPORT,
        help="Raw Khronos glTF Validator report for the V5-payload GLB.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT,
        help=(
            "Audit report. Normal mode only accepts the registered R2X "
            "audit output path."
        ),
    )
    parser.add_argument(
        "--blender-exe",
        type=Path,
        default=DEFAULT_BLENDER,
        help="Blender 5.2 executable used for the read-only probes.",
    )
    parser.add_argument(
        "--blender-timeout",
        type=int,
        default=600,
        help="Per-probe timeout in seconds (default: 600).",
    )
    parser.add_argument(
        "--blend-probe",
        action="store_true",
        help="Internal mode used only by Blender background subprocesses.",
    )
    parser.add_argument(
        "--expected-blend",
        type=Path,
        help="Internal probe: exact Blend expected to be open.",
    )
    parser.add_argument(
        "--probe-role",
        choices=("baseline", "candidate"),
        help="Internal probe role.",
    )
    return parser.parse_args(list(argv))


def failure_report(
    error: BaseException,
    output: Path,
) -> dict[str, Any]:
    """Build a fail-closed report when evidence collection aborts."""

    return {
        "schema_version": SCHEMA_VERSION,
        "requirement_id": REQUIREMENT_ID,
        "stage_id": STAGE_ID,
        "generated_at": now_iso(),
        "attempt_history": list(REGISTERED_ATTEMPT_HISTORY),
        "audit_mode": "fail_closed_read_only",
        "audit_completed": False,
        "audit_passed": False,
        "contract_machine_gate_passed": False,
        "smoke1k_upgrade_gate_passed": False,
        "three_runtime_gate_passed": False,
        "visual_whitelist_gate_passed": False,
        "ao_2k_approved": False,
        "approval_granted": False,
        "p50_approved": False,
        "production_integration_allowed": False,
        "next_release_stage_allowed": False,
        "output": (
            relative_path(output)
            if is_within(output, REPO_ROOT)
            else "<outside-repository>"
        ),
        "error": {
            "type": type(error).__name__,
            "message": str(error),
        },
        "conclusion": "R2X 1K AO candidate audit failed closed.",
    }


def main() -> int:
    """Run normal audit mode or the internal Blender probe mode."""

    argv = (
        sys.argv[sys.argv.index("--") + 1 :]
        if "--" in sys.argv
        else sys.argv[1:]
    )
    args = parse_args(argv)
    output = args.output.resolve()
    try:
        if args.blend_probe:
            if args.expected_blend is None or args.probe_role is None:
                raise AuditError(
                    "--blend-probe requires --expected-blend and --probe-role"
                )
            return run_blend_probe(
                output,
                args.expected_blend.resolve(),
                args.probe_role,
                args.ao_png.resolve(),
            )
        if output != DEFAULT_OUTPUT.resolve():
            raise AuditError(
                "Normal mode may write only the registered R2X audit path: "
                f"{DEFAULT_OUTPUT}"
            )
        if args.blender_timeout <= 0:
            raise AuditError("--blender-timeout must be positive")
        report = build_audit(
            blender_exe=args.blender_exe.resolve(),
            candidate_blend=args.candidate_blend.resolve(),
            ao_png_path=args.ao_png.resolve(),
            material_glb_path=args.material_glb.resolve(),
            build_report_path=args.build_report.resolve(),
            repack_report_path=args.repack_report.resolve(),
            khronos_report_path=args.khronos_report.resolve(),
            output=output,
            blender_timeout=args.blender_timeout,
        )
        write_json(output, report)
        print(
            json.dumps(
                {
                    "status": "PASS" if report["audit_passed"] else "FAIL",
                    "report": relative_path(output),
                    "audit_completed": report["audit_completed"],
                    "audit_passed": report["audit_passed"],
                    "smoke1k_upgrade_gate_passed": False,
                    "p50_approved": False,
                    "production_integration_allowed": False,
                },
                ensure_ascii=False,
            )
        )
        return 0 if report["audit_passed"] else 1
    except (
        AuditError,
        OSError,
        ValueError,
        KeyError,
        TypeError,
        subprocess.SubprocessError,
    ) as exc:
        if not args.blend_probe and output == DEFAULT_OUTPUT.resolve():
            write_json(output, failure_report(exc, output))
        print(f"R2X AO candidate audit failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
