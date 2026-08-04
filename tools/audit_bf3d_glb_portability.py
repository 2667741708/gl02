"""Audit GLB portability, tangent-space and decoded texture budgets.

Requirement:
    REQ-BF3D-R2V-GLTF-PORTABILITY-TANGENT-BUDGET-20260720

The audit is intentionally read-only for GLB inputs.  It parses the JSON/BIN
chunks directly, reports local absolute paths stored in ``extras``, lists every
normal-mapped primitive without an explicit ``TANGENT`` attribute, verifies
that explicit tangent XYZ vectors are finite and unit length with W=+/-1, and
calculates the RGBA8 decode footprint of embedded images.

The report distinguishes two outcomes:

* ``audit_completed`` proves that the binary was parsed and measured.
* ``release_ready`` proves that no portability/tangent blocker remains.

Use ``--require-release-ready`` only for a release candidate.  A V4 baseline is
expected to complete the audit while remaining not release-ready.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import struct
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Iterable


SCHEMA_VERSION = "bf3d.glb_portability_audit.v1"
REQUIREMENT_ID = "REQ-BF3D-R2V-GLTF-PORTABILITY-TANGENT-BUDGET-20260720"
GLB_MAGIC = b"glTF"
JSON_CHUNK = b"JSON"
BIN_CHUNK = b"BIN\x00"
TRIANGLES_MODE = 4
FLOAT_COMPONENT_TYPE = 5126
TANGENT_UNIT_TOLERANCE = 1.0e-4
LOCAL_ABSOLUTE_PATH = re.compile(r"^(?:[A-Za-z]:[\\/]|\\\\)")


class AuditError(RuntimeError):
    """Raised when an input cannot be audited without ambiguity."""


def sha256_bytes(payload: bytes) -> str:
    """Return the lowercase SHA-256 digest for ``payload``."""

    return hashlib.sha256(payload).hexdigest()


def sha256_file(path: Path) -> str:
    """Return the lowercase SHA-256 digest for a file."""

    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def read_glb(path: Path) -> tuple[dict[str, Any], bytes]:
    """Read and validate the JSON and BIN chunks of a GLB 2.0 file."""

    with path.open("rb") as stream:
        header = stream.read(12)
        if len(header) != 12:
            raise AuditError(f"GLB header is truncated: {path}")
        magic, version, total_length = struct.unpack("<4sII", header)
        if magic != GLB_MAGIC or version != 2:
            raise AuditError(f"Not a GLB 2.0 file: {path}")
        if total_length != path.stat().st_size:
            raise AuditError(
                f"GLB length mismatch for {path}: header={total_length}, "
                f"file={path.stat().st_size}"
            )
        chunks: list[tuple[bytes, bytes]] = []
        while stream.tell() < total_length:
            chunk_header = stream.read(8)
            if len(chunk_header) != 8:
                raise AuditError(f"GLB chunk header is truncated: {path}")
            length, chunk_type = struct.unpack("<I4s", chunk_header)
            payload = stream.read(length)
            if len(payload) != length:
                raise AuditError(f"GLB chunk payload is truncated: {path}")
            chunks.append((chunk_type, payload))
    json_payload = next(
        (payload for chunk_type, payload in chunks if chunk_type == JSON_CHUNK),
        None,
    )
    if json_payload is None:
        raise AuditError(f"GLB has no JSON chunk: {path}")
    try:
        gltf = json.loads(json_payload.decode("utf-8").rstrip(" \t\r\n\x00"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise AuditError(f"GLB JSON is invalid: {path}: {exc}") from exc
    binary = next(
        (payload for chunk_type, payload in chunks if chunk_type == BIN_CHUNK),
        b"",
    )
    return gltf, binary


def buffer_view_payload(
    gltf: dict[str, Any],
    binary: bytes,
    view_index: int,
) -> bytes:
    """Return a buffer-view payload from the GLB BIN chunk."""

    views = gltf.get("bufferViews") or []
    if view_index < 0 or view_index >= len(views):
        raise AuditError(f"bufferView index out of range: {view_index}")
    view = views[view_index]
    if int(view.get("buffer", 0)) != 0:
        raise AuditError("External/multi-buffer GLB payload is not supported")
    offset = int(view.get("byteOffset", 0))
    length = int(view.get("byteLength", 0))
    end = offset + length
    if offset < 0 or length < 0 or end > len(binary):
        raise AuditError(
            f"bufferView range is invalid: index={view_index}, "
            f"offset={offset}, length={length}, bin={len(binary)}"
        )
    return binary[offset:end]


def png_dimensions(payload: bytes) -> tuple[int, int] | None:
    """Return PNG dimensions when the payload has a valid IHDR prefix."""

    if len(payload) < 24 or payload[:8] != b"\x89PNG\r\n\x1a\n":
        return None
    width, height = struct.unpack(">II", payload[16:24])
    return (width, height) if width > 0 and height > 0 else None


def webp_dimensions(payload: bytes) -> tuple[int, int] | None:
    """Return dimensions for VP8X, VP8L or VP8 WebP payloads."""

    if len(payload) < 30 or payload[:4] != b"RIFF" or payload[8:12] != b"WEBP":
        return None
    offset = 12
    while offset + 8 <= len(payload):
        chunk_type = payload[offset : offset + 4]
        chunk_length = struct.unpack("<I", payload[offset + 4 : offset + 8])[0]
        data_start = offset + 8
        data_end = data_start + chunk_length
        if data_end > len(payload):
            return None
        data = payload[data_start:data_end]
        if chunk_type == b"VP8X" and len(data) >= 10:
            width = 1 + int.from_bytes(data[4:7], "little")
            height = 1 + int.from_bytes(data[7:10], "little")
            return width, height
        if chunk_type == b"VP8L" and len(data) >= 5 and data[0] == 0x2F:
            bits = int.from_bytes(data[1:5], "little")
            width = 1 + (bits & 0x3FFF)
            height = 1 + ((bits >> 14) & 0x3FFF)
            return width, height
        if (
            chunk_type == b"VP8 "
            and len(data) >= 10
            and data[3:6] == b"\x9d\x01\x2a"
        ):
            width = struct.unpack("<H", data[6:8])[0] & 0x3FFF
            height = struct.unpack("<H", data[8:10])[0] & 0x3FFF
            return (width, height) if width > 0 and height > 0 else None
        offset = data_end + (chunk_length & 1)
    return None


def jpeg_dimensions(payload: bytes) -> tuple[int, int] | None:
    """Return JPEG dimensions from a Start Of Frame marker."""

    if len(payload) < 4 or payload[:2] != b"\xff\xd8":
        return None
    offset = 2
    while offset + 4 <= len(payload):
        if payload[offset] != 0xFF:
            offset += 1
            continue
        while offset < len(payload) and payload[offset] == 0xFF:
            offset += 1
        if offset >= len(payload):
            break
        marker = payload[offset]
        offset += 1
        if marker in (0xD8, 0xD9) or 0xD0 <= marker <= 0xD7:
            continue
        if offset + 2 > len(payload):
            break
        segment_length = struct.unpack(">H", payload[offset : offset + 2])[0]
        if segment_length < 2 or offset + segment_length > len(payload):
            break
        if marker in {
            0xC0,
            0xC1,
            0xC2,
            0xC3,
            0xC5,
            0xC6,
            0xC7,
            0xC9,
            0xCA,
            0xCB,
            0xCD,
            0xCE,
            0xCF,
        }:
            if segment_length < 7:
                break
            height, width = struct.unpack(
                ">HH", payload[offset + 3 : offset + 7]
            )
            return (width, height) if width > 0 and height > 0 else None
        offset += segment_length
    return None


def image_dimensions(payload: bytes, mime_type: str) -> tuple[int, int] | None:
    """Return embedded image dimensions for supported browser formats."""

    candidates = {
        "image/png": png_dimensions,
        "image/webp": webp_dimensions,
        "image/jpeg": jpeg_dimensions,
    }
    preferred = candidates.get(mime_type)
    if preferred is not None:
        result = preferred(payload)
        if result is not None:
            return result
    for parser in candidates.values():
        result = parser(payload)
        if result is not None:
            return result
    return None


def pointer_token(token: str) -> str:
    """Escape a JSON Pointer token."""

    return token.replace("~", "~0").replace("/", "~1")


def walk_json(value: Any, pointer: str = "") -> Iterable[tuple[str, Any]]:
    """Yield ``(json_pointer, value)`` pairs recursively."""

    yield pointer or "/", value
    if isinstance(value, dict):
        for key, child in value.items():
            yield from walk_json(child, f"{pointer}/{pointer_token(str(key))}")
    elif isinstance(value, list):
        for index, child in enumerate(value):
            yield from walk_json(child, f"{pointer}/{index}")


def local_absolute_paths(gltf: dict[str, Any]) -> list[dict[str, str]]:
    """Find Windows local absolute paths stored anywhere under ``extras``."""

    findings: list[dict[str, str]] = []
    for pointer, value in walk_json(gltf):
        if "/extras" not in pointer or not isinstance(value, str):
            continue
        if LOCAL_ABSOLUTE_PATH.match(value):
            findings.append({"pointer": pointer, "value": value})
    return findings


def normal_mapped_tangent_risks(gltf: dict[str, Any]) -> list[dict[str, Any]]:
    """List normal-mapped mesh primitives without explicit tangents."""

    materials = gltf.get("materials") or []
    findings: list[dict[str, Any]] = []
    for mesh_index, mesh in enumerate(gltf.get("meshes") or []):
        mesh_name = mesh.get("name") or f"mesh_{mesh_index}"
        for primitive_index, primitive in enumerate(mesh.get("primitives") or []):
            material_index = primitive.get("material")
            if material_index is None or not (0 <= material_index < len(materials)):
                continue
            material = materials[material_index]
            normal_texture = material.get("normalTexture")
            if not normal_texture:
                continue
            attributes = primitive.get("attributes") or {}
            if "TANGENT" in attributes:
                continue
            findings.append(
                {
                    "mesh_index": mesh_index,
                    "mesh_name": mesh_name,
                    "primitive_index": primitive_index,
                    "material_index": material_index,
                    "material_name": material.get("name")
                    or f"material_{material_index}",
                    "normal_texcoord": int(normal_texture.get("texCoord", 0)),
                    "attributes": sorted(attributes),
                    "json_pointer": (
                        f"/meshes/{mesh_index}/primitives/{primitive_index}/material"
                    ),
                }
            )
    return findings


def float_accessor_vectors(
    gltf: dict[str, Any],
    binary: bytes,
    accessor_index: int,
    *,
    components: int,
) -> list[tuple[float, ...]]:
    """Decode a non-sparse FLOAT VEC3/VEC4 accessor from the GLB BIN chunk."""

    accessors = gltf.get("accessors") or []
    if accessor_index < 0 or accessor_index >= len(accessors):
        raise AuditError(f"Accessor index out of range: {accessor_index}")
    accessor = accessors[accessor_index]
    expected_type = f"VEC{components}"
    if (
        int(accessor.get("componentType", 0)) != FLOAT_COMPONENT_TYPE
        or accessor.get("type") != expected_type
        or accessor.get("sparse") is not None
    ):
        raise AuditError(
            f"Accessor {accessor_index} is not a non-sparse FLOAT {expected_type}"
        )
    view_index = accessor.get("bufferView")
    if view_index is None:
        raise AuditError(f"Accessor {accessor_index} has no bufferView")
    views = gltf.get("bufferViews") or []
    if not (0 <= int(view_index) < len(views)):
        raise AuditError(f"Accessor {accessor_index} bufferView is invalid")
    view = views[int(view_index)]
    if int(view.get("buffer", 0)) != 0:
        raise AuditError("External/multi-buffer accessor is not supported")
    component_bytes = components * 4
    stride = int(view.get("byteStride", component_bytes))
    if stride < component_bytes:
        raise AuditError(
            f"Accessor {accessor_index} byteStride is smaller than its element"
        )
    offset = int(view.get("byteOffset", 0)) + int(
        accessor.get("byteOffset", 0)
    )
    count = int(accessor.get("count", 0))
    if count < 0:
        raise AuditError(f"Accessor {accessor_index} has a negative count")
    end = offset + max(count - 1, 0) * stride + (
        component_bytes if count else 0
    )
    if offset < 0 or end > len(binary):
        raise AuditError(
            f"Accessor {accessor_index} range exceeds the GLB BIN chunk"
        )
    return [
        struct.unpack_from(f"<{components}f", binary, offset + index * stride)
        for index in range(count)
    ]


def explicit_tangent_vector_risks(
    gltf: dict[str, Any],
    binary: bytes,
) -> list[dict[str, Any]]:
    """Report explicit tangent accessors containing invalid unit vectors."""

    findings: list[dict[str, Any]] = []
    seen: set[int] = set()
    for mesh_index, mesh in enumerate(gltf.get("meshes") or []):
        mesh_name = mesh.get("name") or f"mesh_{mesh_index}"
        for primitive_index, primitive in enumerate(mesh.get("primitives") or []):
            tangent_index = (primitive.get("attributes") or {}).get("TANGENT")
            if not isinstance(tangent_index, int) or tangent_index in seen:
                continue
            seen.add(tangent_index)
            vectors = float_accessor_vectors(
                gltf,
                binary,
                tangent_index,
                components=4,
            )
            examples = []
            non_finite = 0
            non_unit_xyz = 0
            invalid_handedness = 0
            maximum_xyz_unit_error = 0.0
            for vector_index, (x, y, z, w) in enumerate(vectors):
                if not all(math.isfinite(value) for value in (x, y, z, w)):
                    non_finite += 1
                    if len(examples) < 20:
                        examples.append(
                            {
                                "index": vector_index,
                                "vector": [x, y, z, w],
                                "reason": "non_finite",
                            }
                        )
                    continue
                length = math.sqrt(x * x + y * y + z * z)
                unit_error = abs(length - 1.0)
                maximum_xyz_unit_error = max(
                    maximum_xyz_unit_error, unit_error
                )
                reasons = []
                if unit_error > TANGENT_UNIT_TOLERANCE:
                    non_unit_xyz += 1
                    reasons.append("xyz_not_unit")
                if min(abs(w - 1.0), abs(w + 1.0)) > 1.0e-5:
                    invalid_handedness += 1
                    reasons.append("w_not_plus_or_minus_one")
                if reasons and len(examples) < 20:
                    examples.append(
                        {
                            "index": vector_index,
                            "vector": [x, y, z, w],
                            "xyz_length": length,
                            "reason": ",".join(reasons),
                        }
                    )
            violation_count = non_finite + non_unit_xyz + invalid_handedness
            if violation_count:
                findings.append(
                    {
                        "mesh_index": mesh_index,
                        "mesh_name": mesh_name,
                        "primitive_index": primitive_index,
                        "tangent_accessor": tangent_index,
                        "accessor_count": len(vectors),
                        "non_finite_vectors": non_finite,
                        "non_unit_xyz_vectors": non_unit_xyz,
                        "invalid_handedness_vectors": invalid_handedness,
                        "maximum_xyz_unit_error": maximum_xyz_unit_error,
                        "violation_count": violation_count,
                        "examples": examples,
                        "json_pointer": (
                            f"/meshes/{mesh_index}/primitives/"
                            f"{primitive_index}/attributes/TANGENT"
                        ),
                    }
                )
    return findings


def image_records(
    gltf: dict[str, Any],
    binary: bytes,
) -> tuple[list[dict[str, Any]], list[str]]:
    """Build embedded-image records and return unresolved image names."""

    records: list[dict[str, Any]] = []
    unresolved: list[str] = []
    for index, image in enumerate(gltf.get("images") or []):
        name = image.get("name") or f"image_{index}"
        mime_type = image.get("mimeType") or ""
        view_index = image.get("bufferView")
        if view_index is None:
            unresolved.append(name)
            records.append(
                {
                    "index": index,
                    "name": name,
                    "mime_type": mime_type,
                    "uri": image.get("uri"),
                    "embedded": False,
                    "dimensions": None,
                    "decoded_rgba8_bytes": None,
                    "decoded_rgba8_with_full_mips_bytes": None,
                }
            )
            continue
        payload = buffer_view_payload(gltf, binary, int(view_index))
        dimensions = image_dimensions(payload, mime_type)
        if dimensions is None:
            unresolved.append(name)
            decoded = None
            decoded_mips = None
        else:
            width, height = dimensions
            decoded = width * height * 4
            decoded_mips = full_mip_rgba8_bytes(width, height)
        records.append(
            {
                "index": index,
                "name": name,
                "mime_type": mime_type,
                "embedded": True,
                "payload_bytes": len(payload),
                "payload_sha256": sha256_bytes(payload),
                "dimensions": (
                    {"width": dimensions[0], "height": dimensions[1]}
                    if dimensions is not None
                    else None
                ),
                "decoded_rgba8_bytes": decoded,
                "decoded_rgba8_with_full_mips_bytes": decoded_mips,
            }
        )
    return records, unresolved


def full_mip_rgba8_bytes(width: int, height: int) -> int:
    """Return exact RGBA8 bytes for a complete 2D mip pyramid."""

    total = 0
    current_width = width
    current_height = height
    while True:
        total += current_width * current_height * 4
        if current_width == 1 and current_height == 1:
            return total
        current_width = max(1, current_width // 2)
        current_height = max(1, current_height // 2)


def duplicate_payload_groups(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Return groups of embedded images that contain identical bytes."""

    groups: defaultdict[str, list[str]] = defaultdict(list)
    for record in records:
        digest = record.get("payload_sha256")
        if digest:
            groups[str(digest)].append(str(record["name"]))
    return [
        {"sha256": digest, "image_names": names, "count": len(names)}
        for digest, names in sorted(groups.items())
        if len(names) > 1
    ]


def audit_asset(path: Path, expected_sha256: str | None) -> dict[str, Any]:
    """Audit one GLB and return a machine-readable record."""

    if not path.is_file():
        raise AuditError(f"GLB does not exist: {path}")
    actual_sha256 = sha256_file(path)
    if expected_sha256 is not None and actual_sha256 != expected_sha256:
        raise AuditError(
            f"SHA-256 mismatch for {path}: expected={expected_sha256}, "
            f"actual={actual_sha256}"
        )
    gltf, binary = read_glb(path)
    paths = local_absolute_paths(gltf)
    tangent_risks = normal_mapped_tangent_risks(gltf)
    tangent_vector_risks = explicit_tangent_vector_risks(gltf, binary)
    images, unresolved_images = image_records(gltf, binary)
    decoded_values = [
        int(record["decoded_rgba8_bytes"])
        for record in images
        if record.get("decoded_rgba8_bytes") is not None
    ]
    mip_values = [
        int(record["decoded_rgba8_with_full_mips_bytes"])
        for record in images
        if record.get("decoded_rgba8_with_full_mips_bytes") is not None
    ]
    primitive_modes = Counter()
    non_triangle_primitives: list[dict[str, Any]] = []
    primitive_count = 0
    explicit_tangent_primitives = 0
    for mesh_index, mesh in enumerate(gltf.get("meshes") or []):
        mesh_name = mesh.get("name") or f"mesh_{mesh_index}"
        for primitive_index, primitive in enumerate(mesh.get("primitives") or []):
            primitive_count += 1
            mode = int(primitive.get("mode", TRIANGLES_MODE))
            primitive_modes[str(mode)] += 1
            if "TANGENT" in (primitive.get("attributes") or {}):
                explicit_tangent_primitives += 1
            if mode != TRIANGLES_MODE:
                non_triangle_primitives.append(
                    {
                        "mesh_index": mesh_index,
                        "mesh_name": mesh_name,
                        "primitive_index": primitive_index,
                        "mode": mode,
                    }
                )
    extensions_required = sorted(gltf.get("extensionsRequired") or [])
    extensions_used = sorted(gltf.get("extensionsUsed") or [])
    release_checks = {
        "sha256_matches_expected": (
            expected_sha256 is None or actual_sha256 == expected_sha256
        ),
        "no_local_absolute_paths_in_extras": len(paths) == 0,
        "no_normal_mapped_primitive_without_tangent": len(tangent_risks) == 0,
        "all_explicit_tangent_vectors_are_valid_unit_vectors": len(
            tangent_vector_risks
        )
        == 0,
        "all_primitives_are_triangles": len(non_triangle_primitives) == 0,
        "all_embedded_image_dimensions_resolved": len(unresolved_images) == 0,
    }
    return {
        "path": path.as_posix(),
        "bytes": path.stat().st_size,
        "sha256": actual_sha256,
        "expected_sha256": expected_sha256,
        "asset_structure": {
            "nodes": len(gltf.get("nodes") or []),
            "meshes": len(gltf.get("meshes") or []),
            "materials": len(gltf.get("materials") or []),
            "textures": len(gltf.get("textures") or []),
            "images": len(gltf.get("images") or []),
            "animations": len(gltf.get("animations") or []),
            "skins": len(gltf.get("skins") or []),
            "primitive_count": primitive_count,
            "primitive_modes": dict(sorted(primitive_modes.items())),
            "explicit_tangent_primitives": explicit_tangent_primitives,
            "tangent_unit_tolerance": TANGENT_UNIT_TOLERANCE,
            "extensions_used": extensions_used,
            "extensions_required": extensions_required,
        },
        "local_absolute_paths_in_extras": paths,
        "normal_mapped_primitives_without_tangent": tangent_risks,
        "invalid_explicit_tangent_accessors": tangent_vector_risks,
        "non_triangle_primitives": non_triangle_primitives,
        "images": images,
        "unresolved_images": unresolved_images,
        "duplicate_image_payload_groups": duplicate_payload_groups(images),
        "texture_budget": {
            "embedded_payload_bytes": sum(
                int(record.get("payload_bytes") or 0) for record in images
            ),
            "decoded_rgba8_bytes": sum(decoded_values),
            "decoded_rgba8_mib": sum(decoded_values) / (1024 * 1024),
            "decoded_rgba8_with_full_mips_bytes": sum(mip_values),
            "decoded_rgba8_with_full_mips_mib": sum(mip_values)
            / (1024 * 1024),
        },
        "release_checks": release_checks,
        "audit_completed": all(
            (
                release_checks["sha256_matches_expected"],
                release_checks["all_primitives_are_triangles"],
                release_checks["all_embedded_image_dimensions_resolved"],
            )
        ),
        "release_ready": all(release_checks.values()),
    }


def parse_expected_sha256(
    values: list[str],
    root: Path,
) -> dict[Path, str]:
    """Parse repeated ``PATH=SHA256`` arguments."""

    expected: dict[Path, str] = {}
    for value in values:
        if "=" not in value:
            raise AuditError(
                f"--expected-sha256 requires PATH=SHA256, got: {value}"
            )
        raw_path, digest = value.rsplit("=", 1)
        path = resolve_path(raw_path, root)
        normalized_digest = digest.strip().lower()
        if not re.fullmatch(r"[0-9a-f]{64}", normalized_digest):
            raise AuditError(f"Invalid SHA-256 for {raw_path}: {digest}")
        expected[path] = normalized_digest
    return expected


def resolve_path(value: str, root: Path) -> Path:
    """Resolve a CLI path against the selected workspace root."""

    path = Path(value)
    if not path.is_absolute():
        path = root / path
    return path.resolve()


def relative_or_absolute(path: Path, root: Path) -> str:
    """Return a portable workspace-relative path where possible."""

    try:
        return path.relative_to(root).as_posix()
    except ValueError:
        return path.as_posix()


def build_parser() -> argparse.ArgumentParser:
    """Create the CLI parser."""

    parser = argparse.ArgumentParser(
        description=(
            "Audit GLB extras portability, explicit tangent-space coverage and "
            "decoded RGBA8 texture budgets."
        )
    )
    parser.add_argument(
        "--workspace-root",
        default=str(Path(__file__).resolve().parents[1]),
        help="Workspace root used to resolve relative paths.",
    )
    parser.add_argument(
        "--asset",
        action="append",
        required=True,
        help="GLB path to audit. Repeat for multiple assets.",
    )
    parser.add_argument(
        "--expected-sha256",
        action="append",
        default=[],
        metavar="PATH=SHA256",
        help="Optional fail-closed input hash. Repeat for multiple assets.",
    )
    parser.add_argument(
        "--output",
        help="Optional JSON report path. Parent directories are created.",
    )
    parser.add_argument(
        "--require-release-ready",
        action="store_true",
        help="Exit 2 unless every asset has zero portability/tangent blockers.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    """Run the audit CLI and return 0, or 2 for a release-gate failure."""

    args = build_parser().parse_args(argv)
    root = Path(args.workspace_root).resolve()
    try:
        expected = parse_expected_sha256(args.expected_sha256, root)
        paths = [resolve_path(value, root) for value in args.asset]
        assets = [
            audit_asset(path, expected.get(path))
            for path in paths
        ]
    except (AuditError, OSError) as exc:
        print(f"BF3D_GLB_PORTABILITY_AUDIT_ERROR={exc}", file=sys.stderr)
        return 1
    report = {
        "schema_version": SCHEMA_VERSION,
        "requirement_id": REQUIREMENT_ID,
        "workspace_root": root.as_posix(),
        "assets": assets,
        "summary": {
            "asset_count": len(assets),
            "audit_completed_assets": sum(
                1 for asset in assets if asset["audit_completed"]
            ),
            "release_ready_assets": sum(
                1 for asset in assets if asset["release_ready"]
            ),
            "local_absolute_path_count": sum(
                len(asset["local_absolute_paths_in_extras"])
                for asset in assets
            ),
            "normal_mapped_primitives_without_tangent": sum(
                len(asset["normal_mapped_primitives_without_tangent"])
                for asset in assets
            ),
            "invalid_explicit_tangent_accessors": sum(
                len(asset["invalid_explicit_tangent_accessors"])
                for asset in assets
            ),
            "decoded_rgba8_mib": sum(
                float(asset["texture_budget"]["decoded_rgba8_mib"])
                for asset in assets
            ),
            "decoded_rgba8_with_full_mips_mib": sum(
                float(
                    asset["texture_budget"][
                        "decoded_rgba8_with_full_mips_mib"
                    ]
                )
                for asset in assets
            ),
        },
        "audit_completed": all(asset["audit_completed"] for asset in assets),
        "release_ready": all(asset["release_ready"] for asset in assets),
    }
    if args.output:
        output = resolve_path(args.output, root)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(
            json.dumps(report, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        report["output"] = relative_or_absolute(output, root)
    print(
        "BF3D_GLB_PORTABILITY_AUDIT="
        + json.dumps(
            {
                "audit_completed": report["audit_completed"],
                "release_ready": report["release_ready"],
                **report["summary"],
                "output": report.get("output"),
            },
            ensure_ascii=False,
        )
    )
    if not report["audit_completed"]:
        return 1
    if args.require_release_ready and not report["release_ready"]:
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
