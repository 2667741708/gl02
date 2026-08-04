#!/usr/bin/env python3
"""Audit the locked V5 PBR texture signal without rendering or mutation.

Requirement:
    REQ-BF3D-R2Y-MATERIAL-SIGNAL-VISIBILITY-DIAGNOSTIC-20260720

The report proves only that BaseColor, Normal and Roughness data exist and
meet the pre-registered numeric signal floor.  It does not prove that Three.js
consumes them or that a viewer can see them under a particular light/camera.
"""

from __future__ import annotations

import hashlib
import io
import json
import struct
import sys
from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import numpy as np
from PIL import Image


REQUIREMENT_ID = (
    "REQ-BF3D-R2Y-MATERIAL-SIGNAL-VISIBILITY-DIAGNOSTIC-20260720"
)
STAGE_ID = "WEB_60_20260720_R2Y_MATERIAL_SIGNAL_VISIBILITY_DIAGNOSTIC"
ROOT = Path(__file__).resolve().parents[1]
MODEL = (
    ROOT
    / "高炉前端数据"
    / "models"
    / "gl02_blast_furnace_material_review.v5.glb"
)
MODEL_BYTES = 994_372
MODEL_SHA256 = (
    "652be1b2c9147d5a7392497c7ae4964d19bdd7095b5435b87c105f9eb3fb66bc"
)
REPORT = (
    ROOT
    / "PT"
    / "高炉3D模型"
    / "work"
    / STAGE_ID
    / "reports"
    / "r2y_pbr_texture_signal_audit.json"
)


def sha256_bytes(payload: bytes) -> str:
    """Return a lowercase SHA-256 for bytes."""

    return hashlib.sha256(payload).hexdigest()


def sha256_file(path: Path) -> str:
    """Return a lowercase SHA-256 for one file."""

    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def parse_glb(path: Path) -> tuple[dict[str, Any], bytes]:
    """Parse GLB JSON and BIN chunks with strict header checks."""

    payload = path.read_bytes()
    if len(payload) < 20:
        raise RuntimeError("GLB is too small")
    magic, version, declared_length = struct.unpack_from("<4sII", payload, 0)
    if magic != b"glTF" or version != 2 or declared_length != len(payload):
        raise RuntimeError(
            "GLB header mismatch: "
            f"magic={magic!r}, version={version}, "
            f"length={declared_length}/{len(payload)}"
        )
    offset = 12
    document: dict[str, Any] | None = None
    binary = b""
    while offset + 8 <= len(payload):
        length, chunk_type = struct.unpack_from("<I4s", payload, offset)
        offset += 8
        chunk = payload[offset : offset + length]
        offset += length
        if chunk_type == b"JSON":
            document = json.loads(chunk.decode("utf-8").rstrip(" \t\r\n\x00"))
        elif chunk_type == b"BIN\x00":
            binary = chunk
    if document is None or not binary:
        raise RuntimeError("GLB is missing JSON or BIN chunk")
    return document, binary


def buffer_view_bytes(
    document: dict[str, Any], binary: bytes, view_index: int
) -> bytes:
    """Read one embedded bufferView payload."""

    view = document["bufferViews"][view_index]
    start = int(view.get("byteOffset", 0))
    end = start + int(view["byteLength"])
    return binary[start:end]


def texture_source(texture: dict[str, Any]) -> int:
    """Resolve a texture image source, including WebP/Basis extensions."""

    extensions = texture.get("extensions", {})
    for extension_name in ("EXT_texture_webp", "KHR_texture_basisu"):
        source = extensions.get(extension_name, {}).get("source")
        if isinstance(source, int):
            return source
    source = texture.get("source")
    if not isinstance(source, int):
        raise RuntimeError(f"Texture has no embedded source: {texture}")
    return source


def image_payload(
    document: dict[str, Any], binary: bytes, image_index: int
) -> tuple[dict[str, Any], bytes]:
    """Return one embedded image record and payload."""

    record = document["images"][image_index]
    view_index = record.get("bufferView")
    if not isinstance(view_index, int):
        raise RuntimeError(
            f"Image {image_index} is external; R2Y requires embedded payload"
        )
    return record, buffer_view_bytes(document, binary, view_index)


def decode_rgb(payload: bytes) -> tuple[np.ndarray, dict[str, Any]]:
    """Decode an embedded image as uint8 RGB."""

    with Image.open(io.BytesIO(payload)) as image:
        image.load()
        source_mode = image.mode
        rgb_image = image.convert("RGB")
        array = np.asarray(rgb_image, dtype=np.uint8)
        metadata = {
            "format": image.format,
            "source_mode": source_mode,
            "decoded_mode": rgb_image.mode,
            "width": rgb_image.width,
            "height": rgb_image.height,
        }
    return array, metadata


def scalar_stats(values: np.ndarray) -> dict[str, float]:
    """Return deterministic scalar statistics as Python floats."""

    array = np.asarray(values, dtype=np.float64)
    return {
        "minimum": float(array.min()),
        "maximum": float(array.max()),
        "mean": float(array.mean()),
        "std": float(array.std()),
    }


def channel_stats_u8(rgb: np.ndarray) -> dict[str, list[float | int]]:
    """Return per-channel uint8 statistics."""

    reshaped = rgb.reshape(-1, 3)
    return {
        "minimum": [int(value) for value in reshaped.min(axis=0)],
        "maximum": [int(value) for value in reshaped.max(axis=0)],
        "span": [
            int(value)
            for value in (reshaped.max(axis=0) - reshaped.min(axis=0))
        ],
        "mean": [float(value) for value in reshaped.mean(axis=0)],
        "std": [float(value) for value in reshaped.std(axis=0)],
    }


def basecolor_metrics(rgb: np.ndarray) -> dict[str, Any]:
    """Measure encoded BaseColor signal without altering color space."""

    rgb64 = rgb.astype(np.float64)
    luma_u8 = (
        rgb64[..., 0] * 0.2126
        + rgb64[..., 1] * 0.7152
        + rgb64[..., 2] * 0.0722
    )
    channels = channel_stats_u8(rgb)
    return {
        "encoded_space": "sRGB_u8",
        "channels": channels,
        "luma_u8": scalar_stats(luma_u8),
        "thresholds": {
            "per_channel_span_minimum_u8": 8,
            "luma_std_minimum_u8": 1.0,
        },
        "checks": {
            "per_channel_span": all(value >= 8 for value in channels["span"]),
            "luma_std": float(luma_u8.std()) >= 1.0,
        },
    }


def normal_metrics(rgb: np.ndarray) -> dict[str, Any]:
    """Measure tangent-space NormalGL signal."""

    normal = rgb.astype(np.float64) / 255.0 * 2.0 - 1.0
    std_x = float(normal[..., 0].std())
    std_y = float(normal[..., 1].std())
    xy_std_norm = float(np.hypot(std_x, std_y))
    mean_z = float(normal[..., 2].mean())
    return {
        "encoding": "NormalGL_u8_to_signed",
        "x": scalar_stats(normal[..., 0]),
        "y": scalar_stats(normal[..., 1]),
        "z": scalar_stats(normal[..., 2]),
        "xy_std_norm": xy_std_norm,
        "mean_z": mean_z,
        "thresholds": {
            "xy_std_norm_minimum": 0.008,
            "mean_z_minimum": 0.98,
            "runtime_normal_scale": 0.45,
        },
        "checks": {
            "xy_std_norm": xy_std_norm >= 0.008,
            "mean_z": mean_z >= 0.98,
        },
    }


def orm_metrics(rgb: np.ndarray) -> dict[str, Any]:
    """Measure ORM channels; G is Roughness and B is Metallic."""

    linear = rgb.astype(np.float64) / 255.0
    occlusion = scalar_stats(linear[..., 0])
    roughness = scalar_stats(linear[..., 1])
    metallic = scalar_stats(linear[..., 2])
    roughness_range = roughness["maximum"] - roughness["minimum"]
    return {
        "encoding": "linear_u8",
        "occlusion_r": occlusion,
        "roughness_g": roughness,
        "metallic_b": metallic,
        "thresholds": {
            "roughness_range_minimum": 0.10,
            "roughness_std_minimum": 0.02,
            "roughness_allowed_range": [0.56, 0.82],
        },
        "checks": {
            "roughness_range": roughness_range >= 0.10,
            "roughness_std": roughness["std"] >= 0.02,
            "roughness_allowed_range": (
                roughness["minimum"] >= 0.56
                and roughness["maximum"] <= 0.82
            ),
        },
    }


def material_bindings(document: dict[str, Any]) -> list[dict[str, Any]]:
    """Record all PBR texture bindings and normal scale."""

    textures = document.get("textures", [])
    images = document.get("images", [])
    bindings: list[dict[str, Any]] = []

    def texture_record(texture_info: dict[str, Any] | None) -> Any:
        if not texture_info:
            return None
        texture_index = texture_info.get("index")
        if not isinstance(texture_index, int):
            return None
        image_index = texture_source(textures[texture_index])
        return {
            "texture_index": texture_index,
            "tex_coord": int(texture_info.get("texCoord", 0)),
            "image_index": image_index,
            "image_name": images[image_index].get("name", ""),
        }

    for index, material in enumerate(document.get("materials", [])):
        pbr = material.get("pbrMetallicRoughness", {})
        normal_info = material.get("normalTexture", {})
        bindings.append(
            {
                "material_index": index,
                "name": material.get("name", ""),
                "basecolor": texture_record(pbr.get("baseColorTexture")),
                "metallic_roughness": texture_record(
                    pbr.get("metallicRoughnessTexture")
                ),
                "normal": texture_record(normal_info),
                "normal_scale": float(normal_info.get("scale", 1.0)),
                "occlusion": texture_record(material.get("occlusionTexture")),
            }
        )
    return bindings


def main() -> int:
    """Run the immutable texture-data audit and write its report."""

    document, binary = parse_glb(MODEL)
    model_actual_sha = sha256_file(MODEL)
    model_lock_passed = (
        MODEL.stat().st_size == MODEL_BYTES
        and model_actual_sha == MODEL_SHA256
    )
    bindings = material_bindings(document)
    semantics: dict[str, set[int]] = {
        "basecolor": set(),
        "normal": set(),
        "metallic_roughness": set(),
    }
    for binding in bindings:
        for semantic in semantics:
            record = binding[semantic]
            if record:
                semantics[semantic].add(int(record["image_index"]))

    expected_unique = all(len(indices) == 1 for indices in semantics.values())
    decoded: dict[str, Any] = {}
    metric_functions = {
        "basecolor": basecolor_metrics,
        "normal": normal_metrics,
        "metallic_roughness": orm_metrics,
    }
    if expected_unique:
        for semantic, indices in semantics.items():
            image_index = next(iter(indices))
            image_record, payload = image_payload(
                document, binary, image_index
            )
            rgb, metadata = decode_rgb(payload)
            decoded[semantic] = {
                "image_index": image_index,
                "image_name": image_record.get("name", ""),
                "mime_type": image_record.get("mimeType"),
                "encoded_bytes": len(payload),
                "encoded_sha256": sha256_bytes(payload),
                "decoded": metadata,
                "metrics": metric_functions[semantic](rgb),
            }

    binding_checks = {
        "exact_two_materials": len(bindings) == 2,
        "all_three_semantics_bound": expected_unique,
        "all_texture_coords_zero": all(
            binding[semantic]
            and binding[semantic]["tex_coord"] == 0
            for binding in bindings
            for semantic in semantics
        ),
        "normal_scale_is_0_45": all(
            abs(binding["normal_scale"] - 0.45) <= 1e-6
            for binding in bindings
        ),
        "v5_has_no_occlusion_binding": all(
            binding["occlusion"] is None for binding in bindings
        ),
    }
    data_checks = {
        "basecolor_signal_floor": bool(decoded)
        and all(decoded["basecolor"]["metrics"]["checks"].values()),
        "normal_signal_floor": bool(decoded)
        and all(decoded["normal"]["metrics"]["checks"].values()),
        "roughness_signal_floor": bool(decoded)
        and all(
            decoded["metallic_roughness"]["metrics"]["checks"].values()
        ),
    }
    passed = (
        model_lock_passed
        and all(binding_checks.values())
        and all(data_checks.values())
    )
    report = {
        "schema_version": "bf3d.r2y.pbr_texture_signal_audit.v1",
        "requirement_id": REQUIREMENT_ID,
        "stage_id": STAGE_ID,
        "generated_at": datetime.now(
            ZoneInfo("Asia/Shanghai")
        ).isoformat(),
        "scope": "data_present_only_not_runtime_or_visual_approval",
        "model": {
            "path": MODEL.relative_to(ROOT).as_posix(),
            "expected_bytes": MODEL_BYTES,
            "actual_bytes": MODEL.stat().st_size,
            "expected_sha256": MODEL_SHA256,
            "actual_sha256": model_actual_sha,
            "lock_passed": model_lock_passed,
        },
        "glb_counts": {
            "materials": len(document.get("materials", [])),
            "textures": len(document.get("textures", [])),
            "images": len(document.get("images", [])),
            "meshes": len(document.get("meshes", [])),
            "nodes": len(document.get("nodes", [])),
        },
        "material_bindings": bindings,
        "decoded_signals": decoded,
        "checks": {
            **binding_checks,
            **data_checks,
        },
        "channel_classification": {
            "basecolor": {
                "data_present": data_checks["basecolor_signal_floor"],
                "sampled": None,
                "consumed": None,
                "visible": None,
            },
            "normal": {
                "data_present": data_checks["normal_signal_floor"],
                "sampled": None,
                "consumed": None,
                "visible": None,
            },
            "roughness": {
                "data_present": data_checks["roughness_signal_floor"],
                "sampled": None,
                "consumed": None,
                "visible": None,
            },
        },
        "limitations": [
            (
                "Decoded embedded WebP statistics can include codec "
                "quantization or cross-channel residual; this audit does not "
                "separate authored signal from codec residual."
            ),
            (
                "The V5 ORM R channel is not authoritative AO because the "
                "locked source ORM.R was white and V5 has no "
                "occlusionTexture binding."
            ),
            (
                "Passing data floors proves neither Three.js texture "
                "consumption nor visibility at the final 8-bit framebuffer."
            ),
        ],
        "passed": passed,
        "approval_stop_lines": {
            "runtime_consumption_approved": False,
            "visual_visibility_approved": False,
            "golden_approved": False,
            "production_integration_allowed": False,
        },
    }
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(
        json.dumps(
            {
                "passed": passed,
                "report": str(REPORT),
                "basecolor_luma_std_u8": decoded.get("basecolor", {})
                .get("metrics", {})
                .get("luma_u8", {})
                .get("std"),
                "normal_xy_std_norm": decoded.get("normal", {})
                .get("metrics", {})
                .get("xy_std_norm"),
                "roughness": decoded.get("metallic_roughness", {})
                .get("metrics", {})
                .get("roughness_g"),
            },
            ensure_ascii=False,
        )
    )
    return 0 if passed else 2


if __name__ == "__main__":
    sys.exit(main())
