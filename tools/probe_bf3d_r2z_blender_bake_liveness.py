#!/usr/bin/env python3
"""Probe Blender/Cycles EMIT bake liveness for BF3D R2Z Phase A.

This file has two execution modes:

* the normal Python orchestrator validates the R2Z input lock, launches the
  locked Blender executable for ``factory_startup`` and ``v5_scene_clone``,
  and aggregates the machine gates;
* Blender's embedded Python executes one isolated scene context and writes an
  internal JSON report for both ``byte_srgb`` and ``float_linear`` targets.

The probe never saves a ``.blend`` file and never advances into R2Z Phase B.

Requirement:
    REQ-BF3D-R2Z-TRUE-PBR-BAKE-RECOVERY-20260720
Contract:
    PT/高炉3D模型/work/
    WEB_60_20260720_R2Z_TRUE_PBR_BAKE_RECOVERY_AND_CHANNEL_LIVENESS/
    WEB-60_R2Z_阶段预注册合同.md
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import struct
import subprocess
import sys
import time
import traceback
import zlib
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Sequence


REQUIREMENT_ID = "REQ-BF3D-R2Z-TRUE-PBR-BAKE-RECOVERY-20260720"
STAGE_ID = "WEB_60_20260720_R2Z_TRUE_PBR_BAKE_RECOVERY_AND_CHANNEL_LIVENESS"
DEFAULT_STAGE_REL = Path("PT/高炉3D模型/work") / STAGE_ID
DEFAULT_INPUT_LOCK_NAME = "input_lock.json"
SCRIPT_SCHEMA = "bf3d.r2z.phase_a_bake_liveness.v1"
INTERNAL_SCHEMA = "bf3d.r2z.phase_a_bake_liveness.internal.v1"
TARGET_LINEAR_RGB = (0.25, 0.50, 0.75)
IMAGE_SIZE = 64
BAKE_MARGIN = 2

THRESHOLDS: dict[str, Any] = {
    "operator_return_must_include": "FINISHED",
    "nonzero_rgb_pixels_min": 4096,
    "mean_error_per_channel_max": 0.03,
    "spatial_std_per_channel_max": 0.01,
    "factory_v5_mean_delta_per_channel_max": 0.02,
    "nonzero_epsilon": 1.0e-6,
}

CASE_DEFINITIONS: dict[str, dict[str, Any]] = {
    "byte_srgb": {
        "float_buffer": False,
        "colorspace": "sRGB",
        "file_format": "PNG",
        "extension": ".png",
    },
    "float_linear": {
        "float_buffer": True,
        "colorspace": "Non-Color",
        "file_format": "OPEN_EXR",
        "extension": ".exr",
    },
}


def utc_now() -> str:
    """Return a stable ISO timestamp in UTC."""

    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def sha256_file(path: Path) -> str:
    """Return a SHA-256 digest without mutating the file."""

    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def file_record(path: Path, *, root: Path | None = None) -> dict[str, Any]:
    """Describe one file with path, byte length and SHA-256."""

    resolved = path.resolve()
    display_path: str
    if root is not None:
        try:
            display_path = resolved.relative_to(root.resolve()).as_posix()
        except ValueError:
            display_path = resolved.as_posix()
    else:
        display_path = resolved.as_posix()
    if not resolved.is_file():
        return {"path": display_path, "exists": False, "bytes": None, "sha256": None}
    return {
        "path": display_path,
        "exists": True,
        "bytes": resolved.stat().st_size,
        "sha256": sha256_file(resolved),
    }


def write_json(path: Path, payload: dict[str, Any]) -> None:
    """Write UTF-8 JSON atomically enough for the local diagnostic workflow."""

    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=False) + "\n",
        encoding="utf-8",
    )
    os.replace(temporary, path)


def repository_root() -> Path:
    """Resolve the repository root from this checked-in tool."""

    return Path(__file__).resolve().parents[1]


def resolve_lock_path(raw_path: str, root: Path) -> Path:
    """Resolve either a locked absolute path or a repository-relative path."""

    candidate = Path(raw_path)
    return candidate if candidate.is_absolute() else root / candidate


def read_input_lock(path: Path) -> dict[str, Any]:
    """Load and minimally validate the R2Z input lock schema and identity."""

    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("stage_id") != STAGE_ID:
        raise RuntimeError(f"Unexpected stage_id in {path}: {payload.get('stage_id')!r}")
    if payload.get("requirement_id") != REQUIREMENT_ID:
        raise RuntimeError(
            f"Unexpected requirement_id in {path}: {payload.get('requirement_id')!r}"
        )
    if payload.get("phase") != "phase_a_bake_liveness_only":
        raise RuntimeError(f"Input lock is not scoped to Phase A: {payload.get('phase')!r}")
    if payload.get("stop_lines", {}).get("phase_a_execution_allowed") is not True:
        raise RuntimeError("Input lock does not allow Phase A execution")
    forbidden_unlocks = (
        "phase_b_true_bake_allowed",
        "phase_c_glb_allowed",
        "phase_d_web_allowed",
        "asset_mutation_allowed",
        "full_matrix_allowed",
        "production_integration_allowed",
    )
    unexpectedly_unlocked = [
        key for key in forbidden_unlocks if payload.get("stop_lines", {}).get(key) is not False
    ]
    if unexpectedly_unlocked:
        raise RuntimeError(f"Phase A stop-lines are not locked: {unexpectedly_unlocked}")
    return payload


def locked_files(input_lock: dict[str, Any], root: Path) -> list[dict[str, Any]]:
    """Return de-duplicated authoritative/protected file locks."""

    combined: list[dict[str, Any]] = []
    seen: set[str] = set()
    contract = input_lock.get("contract") or {}
    if contract.get("path") and contract.get("bytes") is not None and contract.get("sha256"):
        contract_path = resolve_lock_path(contract["path"], root).resolve()
        combined.append(
            {
                "role": "phase_contract",
                "path": contract_path,
                "expected_bytes": int(contract["bytes"]),
                "expected_sha256": str(contract["sha256"]),
            }
        )
        seen.add(os.path.normcase(str(contract_path)))
    for group in ("authoritative_inputs", "protected_assets"):
        for entry in input_lock.get(group, []):
            resolved = resolve_lock_path(entry["path"], root).resolve()
            key = os.path.normcase(str(resolved))
            if key in seen:
                continue
            seen.add(key)
            combined.append(
                {
                    "role": entry.get("role") or group,
                    "path": resolved,
                    "expected_bytes": int(entry["bytes"]),
                    "expected_sha256": str(entry["sha256"]),
                }
            )
    return combined


def audit_locks(locks: Sequence[dict[str, Any]], root: Path) -> dict[str, Any]:
    """Recompute every locked file and report exact mismatches."""

    records: list[dict[str, Any]] = []
    for lock in locks:
        actual = file_record(lock["path"], root=root)
        ok = (
            actual["exists"]
            and actual["bytes"] == lock["expected_bytes"]
            and actual["sha256"] == lock["expected_sha256"]
        )
        records.append(
            {
                "role": lock["role"],
                **actual,
                "expected_bytes": lock["expected_bytes"],
                "expected_sha256": lock["expected_sha256"],
                "ok": ok,
            }
        )
    return {
        "all_match": all(item["ok"] for item in records),
        "count": len(records),
        "records": records,
    }


def srgb_encode_channel(linear: float) -> float:
    """Encode one normalized scene-linear channel using IEC 61966-2-1."""

    if linear <= 0.0031308:
        return 12.92 * linear
    return 1.055 * math.pow(linear, 1.0 / 2.4) - 0.055


def srgb_decode_channel(encoded: float) -> float:
    """Decode one normalized IEC 61966-2-1 channel to scene-linear."""

    if encoded <= 0.04045:
        return encoded / 12.92
    return math.pow((encoded + 0.055) / 1.055, 2.4)


def encoded_target_rgb() -> list[float]:
    """Return the expected PNG sample values for the locked linear color."""

    return [srgb_encode_channel(value) for value in TARGET_LINEAR_RGB]


def _paeth_predictor(left: int, above: int, upper_left: int) -> int:
    estimate = left + above - upper_left
    delta_left = abs(estimate - left)
    delta_above = abs(estimate - above)
    delta_upper_left = abs(estimate - upper_left)
    if delta_left <= delta_above and delta_left <= delta_upper_left:
        return left
    if delta_above <= delta_upper_left:
        return above
    return upper_left


def decode_png_rgba8(path: Path) -> dict[str, Any]:
    """Decode a non-interlaced 8-bit RGB/RGBA PNG using only stdlib.

    Blender's image API reports scene-linear values after color management.  A
    raw PNG decode is therefore also retained so the byte/sRGB encoding itself
    is independently auditable.
    """

    data = path.read_bytes()
    if not data.startswith(b"\x89PNG\r\n\x1a\n"):
        raise RuntimeError(f"Not a PNG file: {path}")
    offset = 8
    width = height = bit_depth = color_type = interlace = None
    compressed = bytearray()
    while offset < len(data):
        if offset + 12 > len(data):
            raise RuntimeError("Truncated PNG chunk")
        length = struct.unpack(">I", data[offset : offset + 4])[0]
        chunk_type = data[offset + 4 : offset + 8]
        chunk_data = data[offset + 8 : offset + 8 + length]
        offset += 12 + length
        if chunk_type == b"IHDR":
            width, height, bit_depth, color_type, _compression, _filter, interlace = (
                struct.unpack(">IIBBBBB", chunk_data)
            )
        elif chunk_type == b"IDAT":
            compressed.extend(chunk_data)
        elif chunk_type == b"IEND":
            break
    if width is None or height is None:
        raise RuntimeError("PNG has no IHDR")
    if bit_depth != 8 or color_type not in (2, 6) or interlace != 0:
        raise RuntimeError(
            f"Unsupported PNG layout: depth={bit_depth}, type={color_type}, interlace={interlace}"
        )
    channels = 4 if color_type == 6 else 3
    stride = int(width) * channels
    raw = zlib.decompress(bytes(compressed))
    expected = int(height) * (stride + 1)
    if len(raw) != expected:
        raise RuntimeError(f"PNG decompressed byte count {len(raw)} != {expected}")
    rows: list[bytearray] = []
    cursor = 0
    prior = bytearray(stride)
    for _row_index in range(int(height)):
        filter_type = raw[cursor]
        cursor += 1
        scanline = raw[cursor : cursor + stride]
        cursor += stride
        recon = bytearray(stride)
        for index, byte in enumerate(scanline):
            left = recon[index - channels] if index >= channels else 0
            above = prior[index]
            upper_left = prior[index - channels] if index >= channels else 0
            if filter_type == 0:
                value = byte
            elif filter_type == 1:
                value = byte + left
            elif filter_type == 2:
                value = byte + above
            elif filter_type == 3:
                value = byte + ((left + above) // 2)
            elif filter_type == 4:
                value = byte + _paeth_predictor(left, above, upper_left)
            else:
                raise RuntimeError(f"Unsupported PNG filter {filter_type}")
            recon[index] = value & 0xFF
        rows.append(recon)
        prior = recon

    count = int(width) * int(height)
    sums = [0.0, 0.0, 0.0]
    sums_squared = [0.0, 0.0, 0.0]
    linear_sums = [0.0, 0.0, 0.0]
    linear_sums_squared = [0.0, 0.0, 0.0]
    minima = [255, 255, 255]
    maxima = [0, 0, 0]
    nonzero = 0
    for row in rows:
        for x in range(int(width)):
            rgb = [row[x * channels + channel] for channel in range(3)]
            if any(value > 0 for value in rgb):
                nonzero += 1
            for channel, value in enumerate(rgb):
                normalized = value / 255.0
                linear = srgb_decode_channel(normalized)
                sums[channel] += normalized
                sums_squared[channel] += normalized * normalized
                linear_sums[channel] += linear
                linear_sums_squared[channel] += linear * linear
                minima[channel] = min(minima[channel], value)
                maxima[channel] = max(maxima[channel], value)
    means = [value / count for value in sums]
    standard_deviations = [
        math.sqrt(max(0.0, sums_squared[channel] / count - means[channel] ** 2))
        for channel in range(3)
    ]
    linear_means = [value / count for value in linear_sums]
    linear_standard_deviations = [
        math.sqrt(
            max(
                0.0,
                linear_sums_squared[channel] / count - linear_means[channel] ** 2,
            )
        )
        for channel in range(3)
    ]
    return {
        "decoder": "stdlib_png_unfilter_rgba8",
        "width": int(width),
        "height": int(height),
        "bit_depth": int(bit_depth),
        "color_type": int(color_type),
        "channels": channels,
        "rgb_nonzero_pixels": nonzero,
        "rgb_min_u8": minima,
        "rgb_max_u8": maxima,
        "rgb_mean_encoded": means,
        "rgb_std_encoded": standard_deviations,
        "rgb_mean_linear_decoded": linear_means,
        "rgb_std_linear_decoded": linear_standard_deviations,
        "target_encoded": encoded_target_rgb(),
        "target_linear": list(TARGET_LINEAR_RGB),
        "mean_encoded_abs_error": [
            abs(means[channel] - encoded_target_rgb()[channel]) for channel in range(3)
        ],
        "mean_linear_abs_error": [
            abs(linear_means[channel] - TARGET_LINEAR_RGB[channel])
            for channel in range(3)
        ],
    }


def command_record(command: Sequence[str], *, root: Path) -> list[str]:
    """Make command arguments readable while retaining exact invocation order."""

    readable: list[str] = []
    for item in command:
        candidate = Path(item)
        if candidate.is_absolute():
            try:
                readable.append(candidate.resolve().relative_to(root.resolve()).as_posix())
                continue
            except (OSError, ValueError):
                pass
        readable.append(item)
    return readable


def run_blender_context(
    *,
    blender: Path,
    script: Path,
    root: Path,
    stage_dir: Path,
    context_name: str,
    v5_blend: Path,
    timeout_seconds: int,
) -> dict[str, Any]:
    """Launch one locked Blender scene context and retain its process evidence."""

    reports_dir = stage_dir / "reports"
    internal_report = reports_dir / f"phase_a_{context_name}_internal.json"
    stdout_path = reports_dir / f"phase_a_{context_name}.stdout.log"
    stderr_path = reports_dir / f"phase_a_{context_name}.stderr.log"
    common_tail = [
        "--python",
        str(script),
        "--",
        "--internal-context",
        context_name,
        "--internal-output",
        str(internal_report),
        "--stage-dir",
        str(stage_dir),
    ]
    if context_name == "factory_startup":
        command = [str(blender), "--factory-startup", "--background", *common_tail]
    elif context_name == "v5_scene_clone":
        command = [str(blender), str(v5_blend), "--background", *common_tail]
    else:
        raise ValueError(f"Unknown context: {context_name}")

    started = time.perf_counter()
    timed_out = False
    exception_text: str | None = None
    return_code: int | None = None
    stdout = ""
    stderr = ""
    try:
        completed = subprocess.run(
            command,
            cwd=root,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout_seconds,
            check=False,
        )
        return_code = completed.returncode
        stdout = completed.stdout
        stderr = completed.stderr
    except subprocess.TimeoutExpired as exc:
        timed_out = True
        stdout = (exc.stdout or "") if isinstance(exc.stdout, str) else (exc.stdout or b"").decode("utf-8", "replace")
        stderr = (exc.stderr or "") if isinstance(exc.stderr, str) else (exc.stderr or b"").decode("utf-8", "replace")
        exception_text = f"TimeoutExpired: {exc}"
    except Exception:
        exception_text = traceback.format_exc()

    stdout_path.write_text(stdout, encoding="utf-8")
    stderr_path.write_text(stderr, encoding="utf-8")
    internal_payload: dict[str, Any] | None = None
    internal_load_error: str | None = None
    if internal_report.is_file():
        try:
            internal_payload = json.loads(internal_report.read_text(encoding="utf-8"))
        except Exception:
            internal_load_error = traceback.format_exc()
    return {
        "context": context_name,
        "command": command_record(command, root=root),
        "return_code": return_code,
        "timed_out": timed_out,
        "elapsed_seconds": round(time.perf_counter() - started, 3),
        "exception": exception_text,
        "stdout": file_record(stdout_path, root=root),
        "stderr": file_record(stderr_path, root=root),
        "internal_report": file_record(internal_report, root=root),
        "internal_report_load_error": internal_load_error,
        "internal": internal_payload,
    }


def case_gate(context_name: str, case_name: str, case: dict[str, Any] | None) -> dict[str, Any]:
    """Evaluate one bake case strictly from recorded pixel evidence."""

    if not case:
        return {
            "context": context_name,
            "case": case_name,
            "passed": False,
            "checks": [{"id": "case_report_present", "ok": False, "actual": None}],
        }
    operator_return = case.get("operator", {}).get("return", [])
    audit = case.get("context_audit_before_operator", {})
    buffer_stats = case.get("image_buffer", {})
    file_stats = case.get("saved_file", {}).get("blender_reload_buffer", {})
    encoded_stats = case.get("saved_file", {}).get("raw_encoded")
    saved_file = case.get("saved_file", {})
    definition = CASE_DEFINITIONS[case_name]
    expected_float = bool(definition["float_buffer"])
    expected_colorspace = str(definition["colorspace"])
    contract_context_actual = {
        "engine": audit.get("engine"),
        "cycles_device": audit.get("cycles_device"),
        "cycles_bake_type": audit.get("cycles_bake_type"),
        "scene_bake_target": audit.get("scene_bake_target"),
        "scene_bake_margin": audit.get("scene_bake_margin"),
        "scene_use_selected_to_active": audit.get("scene_use_selected_to_active"),
        "selected_count": audit.get("selected_count"),
        "selected_editable_count": audit.get("selected_editable_count"),
        "active_image_node_matches_target": audit.get("active_image_node_matches_target"),
        "uv_full_zero_to_one": (audit.get("uv") or {}).get("full_zero_to_one"),
        "bake_operator_poll": audit.get("bake_operator_poll"),
        "image_size": (audit.get("image") or {}).get("size"),
        "image_float_buffer": (audit.get("image") or {}).get("float_buffer"),
        "image_colorspace": (audit.get("image") or {}).get("colorspace"),
    }
    contract_context_ok = contract_context_actual == {
        "engine": "CYCLES",
        "cycles_device": "CPU",
        "cycles_bake_type": "EMIT",
        "scene_bake_target": "IMAGE_TEXTURES",
        "scene_bake_margin": BAKE_MARGIN,
        "scene_use_selected_to_active": False,
        "selected_count": 1,
        "selected_editable_count": 1,
        "active_image_node_matches_target": True,
        "uv_full_zero_to_one": True,
        "bake_operator_poll": True,
        "image_size": [IMAGE_SIZE, IMAGE_SIZE],
        "image_float_buffer": expected_float,
        "image_colorspace": expected_colorspace,
    }
    saved_format_ok = (
        saved_file.get("record", {}).get("exists") is True
        and saved_file.get("format") == definition["file_format"]
        and file_stats.get("width") == IMAGE_SIZE
        and file_stats.get("height") == IMAGE_SIZE
        and file_stats.get("is_float") is expected_float
        and file_stats.get("colorspace") == expected_colorspace
    )
    if case_name == "byte_srgb":
        saved_format_ok = saved_format_ok and bool(encoded_stats) and (
            encoded_stats.get("bit_depth") == 8
            and encoded_stats.get("width") == IMAGE_SIZE
            and encoded_stats.get("height") == IMAGE_SIZE
            and encoded_stats.get("channels") == 4
        )
    checks: list[dict[str, Any]] = [
        {
            "id": "probe_context_matches_contract",
            "ok": contract_context_ok,
            "actual": contract_context_actual,
            "expected": {
                "engine": "CYCLES",
                "cycles_device": "CPU",
                "cycles_bake_type": "EMIT",
                "scene_bake_target": "IMAGE_TEXTURES",
                "scene_bake_margin": BAKE_MARGIN,
                "scene_use_selected_to_active": False,
                "selected_count": 1,
                "selected_editable_count": 1,
                "active_image_node_matches_target": True,
                "uv_full_zero_to_one": True,
                "bake_operator_poll": True,
                "image_size": [IMAGE_SIZE, IMAGE_SIZE],
                "image_float_buffer": expected_float,
                "image_colorspace": expected_colorspace,
            },
        },
        {
            "id": "saved_file_format_matches_contract",
            "ok": saved_format_ok,
            "actual": {
                "record_exists": saved_file.get("record", {}).get("exists"),
                "format": saved_file.get("format"),
                "width": file_stats.get("width"),
                "height": file_stats.get("height"),
                "is_float": file_stats.get("is_float"),
                "colorspace": file_stats.get("colorspace"),
                "png_bit_depth": (encoded_stats or {}).get("bit_depth"),
                "png_channels": (encoded_stats or {}).get("channels"),
            },
        },
        {
            "id": "operator_finished",
            "ok": "FINISHED" in operator_return,
            "actual": operator_return,
            "expected": "contains FINISHED",
        },
        {
            "id": "buffer_nonzero_rgb_pixels",
            "ok": int(buffer_stats.get("rgb_nonzero_pixels", -1))
            >= THRESHOLDS["nonzero_rgb_pixels_min"],
            "actual": buffer_stats.get("rgb_nonzero_pixels"),
            "expected_min": THRESHOLDS["nonzero_rgb_pixels_min"],
        },
        {
            "id": "saved_file_nonzero_rgb_pixels",
            "ok": int(file_stats.get("rgb_nonzero_pixels", -1))
            >= THRESHOLDS["nonzero_rgb_pixels_min"],
            "actual": file_stats.get("rgb_nonzero_pixels"),
            "expected_min": THRESHOLDS["nonzero_rgb_pixels_min"],
        },
        {
            "id": "buffer_linear_and_encoding_mean_error",
            "ok": bool(buffer_stats.get("contract_mean_abs_error"))
            and max(buffer_stats["contract_mean_abs_error"])
            <= THRESHOLDS["mean_error_per_channel_max"],
            "actual": buffer_stats.get("contract_mean_abs_error"),
            "storage_domain": buffer_stats.get("storage_domain"),
            "expected_max_each": THRESHOLDS["mean_error_per_channel_max"],
        },
        {
            "id": "saved_file_linear_and_encoding_mean_error",
            "ok": bool(file_stats.get("contract_mean_abs_error"))
            and max(file_stats["contract_mean_abs_error"])
            <= THRESHOLDS["mean_error_per_channel_max"],
            "actual": file_stats.get("contract_mean_abs_error"),
            "storage_domain": file_stats.get("storage_domain"),
            "expected_max_each": THRESHOLDS["mean_error_per_channel_max"],
        },
        {
            "id": "buffer_spatial_std",
            "ok": bool(buffer_stats.get("contract_spatial_std"))
            and max(buffer_stats["contract_spatial_std"])
            <= THRESHOLDS["spatial_std_per_channel_max"],
            "actual": buffer_stats.get("contract_spatial_std"),
            "storage_domain": buffer_stats.get("storage_domain"),
            "expected_max_each": THRESHOLDS["spatial_std_per_channel_max"],
        },
        {
            "id": "saved_file_spatial_std",
            "ok": bool(file_stats.get("contract_spatial_std"))
            and max(file_stats["contract_spatial_std"])
            <= THRESHOLDS["spatial_std_per_channel_max"],
            "actual": file_stats.get("contract_spatial_std"),
            "storage_domain": file_stats.get("storage_domain"),
            "expected_max_each": THRESHOLDS["spatial_std_per_channel_max"],
        },
        {
            "id": "no_internal_exception",
            "ok": case.get("exception") is None,
            "actual": case.get("exception"),
        },
    ]
    if case_name == "byte_srgb":
        encoded_error = (encoded_stats or {}).get("mean_encoded_abs_error")
        checks.append(
            {
                "id": "png_raw_encoded_mean_error",
                "ok": bool(encoded_error)
                and max(encoded_error) <= THRESHOLDS["mean_error_per_channel_max"],
                "actual": encoded_error,
                "expected_max_each": THRESHOLDS["mean_error_per_channel_max"],
            }
        )
        raw_linear_error = (encoded_stats or {}).get("mean_linear_abs_error")
        checks.append(
            {
                "id": "png_raw_decoded_linear_mean_error",
                "ok": bool(raw_linear_error)
                and max(raw_linear_error) <= THRESHOLDS["mean_error_per_channel_max"],
                "actual": raw_linear_error,
                "expected_max_each": THRESHOLDS["mean_error_per_channel_max"],
            }
        )
    return {
        "context": context_name,
        "case": case_name,
        "passed": all(check["ok"] for check in checks),
        "checks": checks,
    }


def aggregate_report(
    *,
    root: Path,
    stage_dir: Path,
    input_lock_path: Path,
    input_lock: dict[str, Any],
    pre_lock_audit: dict[str, Any],
    post_lock_audit: dict[str, Any],
    input_lock_before: dict[str, Any],
    input_lock_after: dict[str, Any],
    context_runs: list[dict[str, Any]],
    blender: Path,
    v5_blend: Path,
) -> dict[str, Any]:
    """Build the fail-closed Phase A machine decision."""

    context_map = {run["context"]: run for run in context_runs}
    gates: list[dict[str, Any]] = []
    for context_name in ("factory_startup", "v5_scene_clone"):
        internal = (context_map.get(context_name) or {}).get("internal") or {}
        cases = internal.get("cases", {})
        for case_name in CASE_DEFINITIONS:
            gates.append(case_gate(context_name, case_name, cases.get(case_name)))

    cross_context_gates: list[dict[str, Any]] = []
    for case_name in CASE_DEFINITIONS:
        factory_case = (
            ((context_map.get("factory_startup") or {}).get("internal") or {})
            .get("cases", {})
            .get(case_name)
        )
        v5_case = (
            ((context_map.get("v5_scene_clone") or {}).get("internal") or {})
            .get("cases", {})
            .get(case_name)
        )
        factory_mean = (factory_case or {}).get("image_buffer", {}).get(
            "rgb_mean_linear_interpreted"
        )
        v5_mean = (v5_case or {}).get("image_buffer", {}).get(
            "rgb_mean_linear_interpreted"
        )
        if factory_mean and v5_mean:
            delta = [abs(float(factory_mean[i]) - float(v5_mean[i])) for i in range(3)]
        else:
            delta = None
        cross_context_gates.append(
            {
                "id": f"factory_v5_buffer_mean_delta_{case_name}",
                "case": case_name,
                "ok": bool(delta)
                and max(delta) <= THRESHOLDS["factory_v5_mean_delta_per_channel_max"],
                "actual": delta,
                "expected_max_each": THRESHOLDS[
                    "factory_v5_mean_delta_per_channel_max"
                ],
            }
        )
        factory_saved_mean = (
            (factory_case or {})
            .get("saved_file", {})
            .get("blender_reload_buffer", {})
            .get("rgb_mean_linear_interpreted")
        )
        v5_saved_mean = (
            (v5_case or {})
            .get("saved_file", {})
            .get("blender_reload_buffer", {})
            .get("rgb_mean_linear_interpreted")
        )
        if factory_saved_mean and v5_saved_mean:
            saved_delta = [
                abs(float(factory_saved_mean[i]) - float(v5_saved_mean[i]))
                for i in range(3)
            ]
        else:
            saved_delta = None
        cross_context_gates.append(
            {
                "id": f"factory_v5_saved_reload_mean_delta_{case_name}",
                "case": case_name,
                "ok": bool(saved_delta)
                and max(saved_delta)
                <= THRESHOLDS["factory_v5_mean_delta_per_channel_max"],
                "actual": saved_delta,
                "expected_max_each": THRESHOLDS[
                    "factory_v5_mean_delta_per_channel_max"
                ],
            }
        )

    process_checks = [
        {
            "id": f"{run['context']}_blender_process_and_report",
            "ok": run["return_code"] == 0
            and not run["timed_out"]
            and run["internal"] is not None
            and run["internal_report_load_error"] is None,
            "detail": {
                "return_code": run["return_code"],
                "timed_out": run["timed_out"],
                "internal_report_exists": run["internal_report"]["exists"],
                "internal_report_load_error": run["internal_report_load_error"],
            },
        }
        for run in context_runs
    ]
    all_cases_pass = all(gate["passed"] for gate in gates)
    cross_pass = all(gate["ok"] for gate in cross_context_gates)
    processes_pass = all(item["ok"] for item in process_checks)
    input_lock_unchanged = input_lock_before == input_lock_after
    input_integrity_pass = (
        pre_lock_audit["all_match"]
        and post_lock_audit["all_match"]
        and input_lock_unchanged
    )
    phase_a_passed = all_cases_pass and cross_pass and processes_pass and input_integrity_pass

    artifact_paths: list[Path] = []
    for run in context_runs:
        artifact_paths.extend(
            [
                root / run["stdout"]["path"] if not Path(run["stdout"]["path"]).is_absolute() else Path(run["stdout"]["path"]),
                root / run["stderr"]["path"] if not Path(run["stderr"]["path"]).is_absolute() else Path(run["stderr"]["path"]),
                root / run["internal_report"]["path"] if not Path(run["internal_report"]["path"]).is_absolute() else Path(run["internal_report"]["path"]),
            ]
        )
        internal = run.get("internal") or {}
        for case in internal.get("cases", {}).values():
            saved_path = case.get("saved_file", {}).get("record", {}).get("path")
            if saved_path:
                artifact_paths.append(root / saved_path if not Path(saved_path).is_absolute() else Path(saved_path))
    artifacts = [file_record(path, root=root) for path in artifact_paths]

    return {
        "schema_version": SCRIPT_SCHEMA,
        "requirement_id": REQUIREMENT_ID,
        "stage_id": STAGE_ID,
        "generated_at": utc_now(),
        "scope": "phase_a_bake_liveness_only",
        "status": (
            "phase_a_passed_true_cycles_bake_liveness"
            if phase_a_passed
            else "phase_a_failed_closed_no_candidate"
        ),
        "classification": (
            "phase_a_bake_pipeline_live"
            if phase_a_passed
            else "bake_pipeline_liveness_failure"
        ),
        "phase_a_bake_liveness_passed": phase_a_passed,
        "phase_b_true_bake_executed": False,
        "phase_b_machine_prerequisite_satisfied": phase_a_passed,
        "phase_b_prerequisite_satisfied": False,
        "phase_b_true_bake_allowed_by_this_report": False,
        "protected_asset_mutation_performed": False,
        "stage_evidence_written": True,
        "contract": {
            "input_lock": file_record(input_lock_path, root=root),
            "contract": input_lock.get("contract"),
            "target_linear_rgb": list(TARGET_LINEAR_RGB),
            "target_encoded_srgb": encoded_target_rgb(),
            "image_size": [IMAGE_SIZE, IMAGE_SIZE],
            "bake_type": "EMIT",
            "margin": BAKE_MARGIN,
            "use_selected_to_active": False,
            "engine": "CYCLES",
            "device": "CPU",
            "thresholds": THRESHOLDS,
        },
        "runtime": {
            "orchestrator_python": sys.executable,
            "orchestrator_version": sys.version,
            "platform": sys.platform,
            "blender": file_record(blender, root=root),
            "v5_scene_clone_source": file_record(v5_blend, root=root),
        },
        "input_integrity": {
            "passed": input_integrity_pass,
            "input_lock_unchanged": input_lock_unchanged,
            "input_lock_before": input_lock_before,
            "input_lock_after": input_lock_after,
            "before": pre_lock_audit,
            "after": post_lock_audit,
        },
        "process_checks": process_checks,
        "case_gates": gates,
        "cross_context_gates": cross_context_gates,
        "gate_summary": {
            "processes_passed": processes_pass,
            "case_count": len(gates),
            "case_pass_count": sum(1 for gate in gates if gate["passed"]),
            "all_cases_passed": all_cases_pass,
            "cross_context_passed": cross_pass,
            "input_integrity_passed": input_integrity_pass,
            "phase_a_passed": phase_a_passed,
        },
        "contexts": context_runs,
        "artifacts": artifacts,
        "stop_lines": {
            "phase_a_execution_completed": True,
            "phase_a_bake_liveness_passed": phase_a_passed,
            "phase_b_executed": False,
            "phase_c_executed": False,
            "phase_d_executed": False,
            "full_matrix_executed": False,
            "beauty_approved": False,
            "golden_approved": False,
            "ao_2k_approved": False,
            "p50_approved": False,
            "p60_approved": False,
            "production_integration_allowed": False,
        },
        "decision": (
            "All four constant-EMIT cases produced numerically correct non-black pixels; "
            "Phase A is machine-live. This report does not execute or approve Phase B."
            if phase_a_passed
            else "At least one Phase A process, pixel gate, cross-context gate, or input lock "
            "failed. Stop as phase_a_failed_closed_no_candidate; Phase B remains forbidden."
        ),
    }


def orchestrator_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    """Parse normal-Python orchestrator arguments."""

    root = repository_root()
    parser = argparse.ArgumentParser(
        description=(
            "Run R2Z Phase A constant-EMIT bake liveness in factory-startup and locked "
            "V5 scene-clone contexts. Exit 0 only when all pixel gates pass."
        )
    )
    parser.add_argument(
        "--stage-dir",
        type=Path,
        default=root / DEFAULT_STAGE_REL,
        help="R2Z stage directory (default: pre-registered stage)",
    )
    parser.add_argument(
        "--input-lock",
        type=Path,
        default=None,
        help="Input lock JSON (default: <stage-dir>/input_lock.json)",
    )
    parser.add_argument(
        "--timeout-seconds",
        type=int,
        default=300,
        help="Per-Blender-process timeout in seconds (default: 300)",
    )
    return parser.parse_args(argv)


def run_orchestrator(argv: Sequence[str] | None = None) -> int:
    """Execute both Blender contexts and write the Phase A aggregate report."""

    args = orchestrator_args(argv)
    root = repository_root()
    stage_dir = args.stage_dir.resolve()
    input_lock_path = (
        args.input_lock.resolve()
        if args.input_lock is not None
        else stage_dir / DEFAULT_INPUT_LOCK_NAME
    )
    reports_dir = stage_dir / "reports"
    preview_dir = stage_dir / "preview"
    reports_dir.mkdir(parents=True, exist_ok=True)
    preview_dir.mkdir(parents=True, exist_ok=True)
    aggregate_path = reports_dir / "phase_a_blender_bake_liveness_report.json"
    started = time.perf_counter()

    try:
        input_lock = read_input_lock(input_lock_path)
        input_lock_before = file_record(input_lock_path, root=root)
        locks = locked_files(input_lock, root)
        pre_audit = audit_locks(locks, root)
        if not pre_audit["all_match"]:
            payload = {
                "schema_version": SCRIPT_SCHEMA,
                "requirement_id": REQUIREMENT_ID,
                "stage_id": STAGE_ID,
                "generated_at": utc_now(),
                "scope": "phase_a_bake_liveness_only",
                "status": "phase_a_failed_closed_input_lock_mismatch",
                "classification": "input_integrity_failure",
                "phase_a_bake_liveness_passed": False,
                "input_integrity": {"passed": False, "before": pre_audit, "after": None},
                "phase_b_true_bake_executed": False,
                "decision": "Locked input mismatch detected before Blender execution.",
            }
            write_json(aggregate_path, payload)
            print(json.dumps({"report": str(aggregate_path), "status": payload["status"]}))
            return 1

        blender_entry = next(
            entry
            for entry in input_lock["authoritative_inputs"]
            if entry.get("role") == "blender_runtime"
        )
        v5_entry = next(
            entry
            for entry in input_lock["authoritative_inputs"]
            if entry.get("role") == "v5_geometry_uv_source"
        )
        blender = resolve_lock_path(blender_entry["path"], root).resolve()
        v5_blend = resolve_lock_path(v5_entry["path"], root).resolve()
        script = Path(__file__).resolve()
        context_runs = [
            run_blender_context(
                blender=blender,
                script=script,
                root=root,
                stage_dir=stage_dir,
                context_name=context_name,
                v5_blend=v5_blend,
                timeout_seconds=args.timeout_seconds,
            )
            for context_name in ("factory_startup", "v5_scene_clone")
        ]
        post_audit = audit_locks(locks, root)
        input_lock_after = file_record(input_lock_path, root=root)
        payload = aggregate_report(
            root=root,
            stage_dir=stage_dir,
            input_lock_path=input_lock_path,
            input_lock=input_lock,
            pre_lock_audit=pre_audit,
            post_lock_audit=post_audit,
            input_lock_before=input_lock_before,
            input_lock_after=input_lock_after,
            context_runs=context_runs,
            blender=blender,
            v5_blend=v5_blend,
        )
        payload["elapsed_seconds"] = round(time.perf_counter() - started, 3)
        write_json(aggregate_path, payload)
        print(
            json.dumps(
                {
                    "report": str(aggregate_path),
                    "status": payload["status"],
                    "phase_a_bake_liveness_passed": payload[
                        "phase_a_bake_liveness_passed"
                    ],
                },
                ensure_ascii=False,
            )
        )
        return 0 if payload["phase_a_bake_liveness_passed"] else 1
    except Exception:
        failure = {
            "schema_version": SCRIPT_SCHEMA,
            "requirement_id": REQUIREMENT_ID,
            "stage_id": STAGE_ID,
            "generated_at": utc_now(),
            "scope": "phase_a_bake_liveness_only",
            "status": "phase_a_failed_closed_orchestrator_exception",
            "classification": "bake_pipeline_liveness_failure",
            "phase_a_bake_liveness_passed": False,
            "phase_b_true_bake_executed": False,
            "exception": traceback.format_exc(),
            "decision": "Orchestrator exception; Phase B remains forbidden.",
        }
        write_json(aggregate_path, failure)
        print(failure["exception"], file=sys.stderr)
        return 1


def blender_args() -> argparse.Namespace:
    """Parse arguments after Blender's ``--`` separator."""

    argv = sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else []
    parser = argparse.ArgumentParser(description="R2Z Phase A Blender-internal probe")
    parser.add_argument(
        "--internal-context",
        required=True,
        choices=("factory_startup", "v5_scene_clone"),
    )
    parser.add_argument("--internal-output", required=True, type=Path)
    parser.add_argument("--stage-dir", required=True, type=Path)
    return parser.parse_args(argv)


def _float_list(values: Sequence[Any]) -> list[float]:
    return [float(value) for value in values]


def _image_contract_metrics(
    image: Any, np_module: Any, *, storage_domain: str
) -> dict[str, Any]:
    """Read Blender pixels in their actual storage domain and linearize them.

    Blender exposes an RGBA8/sRGB image's byte-backed samples as normalized
    encoded values through ``Image.pixels``. Float/Non-Color samples are
    scene-linear. Both representations are retained so neither domain is
    mislabeled and the contract can bound both encoding and linear error.
    """

    width, height = int(image.size[0]), int(image.size[1])
    flat = np_module.empty(width * height * 4, dtype=np_module.float32)
    image.pixels.foreach_get(flat)
    rgba = flat.reshape((height, width, 4))
    rgb_storage = rgba[..., :3].astype(np_module.float64)
    if storage_domain == "srgb_encoded":
        rgb_linear = np_module.where(
            rgb_storage <= 0.04045,
            rgb_storage / 12.92,
            np_module.power((rgb_storage + 0.055) / 1.055, 2.4),
        )
        target_storage = np_module.asarray(encoded_target_rgb(), dtype=np_module.float64)
    elif storage_domain == "linear":
        rgb_linear = rgb_storage
        target_storage = np_module.asarray(TARGET_LINEAR_RGB, dtype=np_module.float64)
    else:
        raise ValueError(f"Unknown image storage domain: {storage_domain}")
    storage_means = rgb_storage.mean(axis=(0, 1))
    storage_deviations = rgb_storage.std(axis=(0, 1))
    linear_means = rgb_linear.mean(axis=(0, 1))
    linear_deviations = rgb_linear.std(axis=(0, 1))
    storage_errors = np_module.abs(storage_means - target_storage)
    linear_errors = np_module.abs(
        linear_means - np_module.asarray(TARGET_LINEAR_RGB, dtype=np_module.float64)
    )
    nonzero = int(
        np_module.count_nonzero(
            np_module.any(rgb_storage > THRESHOLDS["nonzero_epsilon"], axis=2)
        )
    )
    return {
        "width": width,
        "height": height,
        "is_float": bool(image.is_float),
        "channels": int(image.channels),
        "colorspace": image.colorspace_settings.name,
        "storage_domain": storage_domain,
        "alpha_mode": image.alpha_mode,
        "rgb_nonzero_pixels": nonzero,
        "rgb_min_storage": _float_list(rgb_storage.min(axis=(0, 1))),
        "rgb_max_storage": _float_list(rgb_storage.max(axis=(0, 1))),
        "rgb_mean_storage": _float_list(storage_means),
        "rgb_std_storage": _float_list(storage_deviations),
        "target_storage": _float_list(target_storage),
        "mean_storage_abs_error": _float_list(storage_errors),
        "rgb_mean_linear_interpreted": _float_list(linear_means),
        "rgb_std_linear_interpreted": _float_list(linear_deviations),
        "target_linear": list(TARGET_LINEAR_RGB),
        "mean_linear_abs_error": _float_list(linear_errors),
        "contract_mean_abs_error": _float_list(
            np_module.maximum(storage_errors, linear_errors)
        ),
        "contract_spatial_std": _float_list(
            np_module.maximum(storage_deviations, linear_deviations)
        ),
        "alpha_min": float(rgba[..., 3].min()),
        "alpha_max": float(rgba[..., 3].max()),
        "alpha_mean": float(rgba[..., 3].mean()),
    }


def _uv_record(mesh: Any) -> dict[str, Any]:
    uv_layer = mesh.uv_layers.active
    values = [[float(loop.uv[0]), float(loop.uv[1])] for loop in uv_layer.data]
    return {
        "name": uv_layer.name,
        "active": mesh.uv_layers.active.name if mesh.uv_layers.active else None,
        "active_render": bool(uv_layer.active_render),
        "loop_count": len(values),
        "coordinates": values,
        "u_range": [min(item[0] for item in values), max(item[0] for item in values)],
        "v_range": [min(item[1] for item in values), max(item[1] for item in values)],
        "full_zero_to_one": (
            min(item[0] for item in values) == 0.0
            and max(item[0] for item in values) == 1.0
            and min(item[1] for item in values) == 0.0
            and max(item[1] for item in values) == 1.0
        ),
    }


def _cycles_devices(bpy_module: Any) -> dict[str, Any]:
    try:
        addon = bpy_module.context.preferences.addons.get("cycles")
        if addon is None:
            return {"cycles_addon_present": False, "devices": []}
        preferences = addon.preferences
        preferences.get_devices()
        return {
            "cycles_addon_present": True,
            "compute_device_type": getattr(preferences, "compute_device_type", None),
            "devices": [
                {
                    "name": device.name,
                    "type": device.type,
                    "id": device.id,
                    "use": bool(device.use),
                }
                for device in preferences.devices
            ],
        }
    except Exception:
        return {"cycles_addon_present": None, "devices": [], "exception": traceback.format_exc()}


def _make_probe_scene_data(bpy_module: Any, context_name: str, case_name: str) -> dict[str, Any]:
    """Create one temporary full-UV quad, constant emission material and target image."""

    prefix = f"R2Z_PHASE_A_{context_name}_{case_name}"
    scene = bpy_module.context.scene
    collection = bpy_module.data.collections.new(f"{prefix}_TEMP_COLLECTION")
    scene.collection.children.link(collection)
    mesh = bpy_module.data.meshes.new(f"{prefix}_MESH")
    mesh.from_pydata(
        [(-1.0, -1.0, 0.0), (1.0, -1.0, 0.0), (1.0, 1.0, 0.0), (-1.0, 1.0, 0.0)],
        [],
        [(0, 1, 2, 3)],
    )
    mesh.update(calc_edges=True)
    uv = mesh.uv_layers.new(name="UVMap")
    uv.active_render = True
    mesh.uv_layers.active_index = 0
    uv_coords = ((0.0, 0.0), (1.0, 0.0), (1.0, 1.0), (0.0, 1.0))
    for polygon in mesh.polygons:
        for loop_index in polygon.loop_indices:
            vertex_index = mesh.loops[loop_index].vertex_index
            uv.data[loop_index].uv = uv_coords[vertex_index]

    obj = bpy_module.data.objects.new(f"{prefix}_OBJECT", mesh)
    collection.objects.link(obj)
    obj.hide_viewport = False
    obj.hide_render = False
    obj.hide_select = False
    obj.hide_set(False)

    material = bpy_module.data.materials.new(f"{prefix}_MATERIAL")
    material.use_nodes = True
    nodes = material.node_tree.nodes
    nodes.clear()
    output = nodes.new("ShaderNodeOutputMaterial")
    output.name = f"{prefix}_OUTPUT"
    output.is_active_output = True
    emission = nodes.new("ShaderNodeEmission")
    emission.name = f"{prefix}_CONSTANT_EMISSION"
    emission.inputs["Color"].default_value = (*TARGET_LINEAR_RGB, 1.0)
    emission.inputs["Strength"].default_value = 1.0

    definition = CASE_DEFINITIONS[case_name]
    image = bpy_module.data.images.new(
        f"{prefix}_IMAGE",
        width=IMAGE_SIZE,
        height=IMAGE_SIZE,
        alpha=True,
        float_buffer=definition["float_buffer"],
        is_data=case_name == "float_linear",
    )
    image.colorspace_settings.name = definition["colorspace"]
    image.alpha_mode = "STRAIGHT"
    image.generated_color = (0.0, 0.0, 0.0, 0.0)
    zeros = [0.0] * (IMAGE_SIZE * IMAGE_SIZE * 4)
    image.pixels.foreach_set(zeros)
    image.update()

    target = nodes.new("ShaderNodeTexImage")
    target.name = f"{prefix}_ACTIVE_IMAGE_TARGET"
    target.image = image
    for node in nodes:
        node.select = False
    target.select = True
    nodes.active = target
    material.node_tree.links.new(emission.outputs["Emission"], output.inputs["Surface"])
    obj.data.materials.append(material)
    obj.active_material_index = 0
    return {
        "prefix": prefix,
        "collection": collection,
        "mesh": mesh,
        "object": obj,
        "material": material,
        "output": output,
        "emission": emission,
        "image": image,
        "target": target,
    }


def _select_probe(bpy_module: Any, obj: Any) -> None:
    if bpy_module.context.object is not None and bpy_module.context.object.mode != "OBJECT":
        bpy_module.ops.object.mode_set(mode="OBJECT")
    bpy_module.ops.object.select_all(action="DESELECT")
    obj.select_set(True)
    bpy_module.context.view_layer.objects.active = obj
    bpy_module.context.view_layer.update()
    bpy_module.context.evaluated_depsgraph_get().update()


def _save_and_reload(
    bpy_module: Any,
    np_module: Any,
    image: Any,
    case_name: str,
    path: Path,
) -> dict[str, Any]:
    """Save the bake target and independently reload its pixels through Blender."""

    definition = CASE_DEFINITIONS[case_name]
    scene = bpy_module.context.scene
    path.parent.mkdir(parents=True, exist_ok=True)
    scene.render.image_settings.file_format = definition["file_format"]
    scene.render.image_settings.color_mode = "RGBA"
    if case_name == "byte_srgb":
        scene.render.image_settings.color_depth = "8"
    else:
        scene.render.image_settings.color_depth = "32"
        scene.render.image_settings.exr_codec = "ZIP"
    image.file_format = definition["file_format"]
    image.filepath_raw = str(path)
    image.save()
    if not path.is_file():
        raise RuntimeError(f"Blender image.save() did not create {path}")

    raw_encoded = decode_png_rgba8(path) if case_name == "byte_srgb" else None
    reloaded = bpy_module.data.images.load(str(path), check_existing=False)
    try:
        if case_name == "float_linear":
            reloaded.colorspace_settings.name = "Non-Color"
        reloaded.update()
        storage_domain = "srgb_encoded" if case_name == "byte_srgb" else "linear"
        reload_buffer = _image_contract_metrics(
            reloaded, np_module, storage_domain=storage_domain
        )
        reloaded_record = {
            "name": reloaded.name,
            "source": reloaded.source,
            "file_format": reloaded.file_format,
            "colorspace": reloaded.colorspace_settings.name,
            "is_float": bool(reloaded.is_float),
        }
    finally:
        bpy_module.data.images.remove(reloaded)
    return {
        "record": file_record(path, root=repository_root()),
        "format": definition["file_format"],
        "raw_encoded": raw_encoded,
        "reloaded_image": reloaded_record,
        "blender_reload_buffer": reload_buffer,
    }


def _cleanup_probe(bpy_module: Any, created: dict[str, Any]) -> dict[str, Any]:
    cleanup: dict[str, Any] = {"attempted": True, "exception": None}
    try:
        obj = created["object"]
        mesh = created["mesh"]
        material = created["material"]
        image = created["image"]
        collection = created["collection"]
        bpy_module.data.objects.remove(obj, do_unlink=True)
        if mesh.users == 0:
            bpy_module.data.meshes.remove(mesh)
        if material.users == 0:
            bpy_module.data.materials.remove(material)
        if image.users == 0:
            bpy_module.data.images.remove(image)
        if collection.users == 0:
            bpy_module.data.collections.remove(collection)
        cleanup["completed"] = True
    except Exception:
        cleanup["completed"] = False
        cleanup["exception"] = traceback.format_exc()
    return cleanup


def _run_blender_case(
    bpy_module: Any,
    np_module: Any,
    *,
    context_name: str,
    case_name: str,
    stage_dir: Path,
) -> dict[str, Any]:
    """Bake and audit one of the four pre-registered Phase A combinations."""

    started = time.perf_counter()
    result: dict[str, Any] = {
        "context": context_name,
        "case": case_name,
        "started_at": utc_now(),
        "exception": None,
    }
    created: dict[str, Any] | None = None
    try:
        scene = bpy_module.context.scene
        scene.render.engine = "CYCLES"
        scene.cycles.device = "CPU"
        scene.cycles.samples = 1
        scene.cycles.use_denoising = False
        scene.render.bake.target = "IMAGE_TEXTURES"
        scene.render.bake.margin = BAKE_MARGIN
        scene.render.bake.use_selected_to_active = False
        if hasattr(scene.render.bake, "margin_type"):
            scene.render.bake.margin_type = "EXTEND"
        scene.cycles.bake_type = "EMIT"
        scene.view_settings.view_transform = "Standard"
        if hasattr(scene.view_settings, "look"):
            try:
                scene.view_settings.look = "None"
            except TypeError:
                pass

        created = _make_probe_scene_data(bpy_module, context_name, case_name)
        obj = created["object"]
        material = created["material"]
        image = created["image"]
        target = created["target"]
        emission = created["emission"]
        _select_probe(bpy_module, obj)
        bpy_module.context.view_layer.update()
        bpy_module.context.evaluated_depsgraph_get().update()

        active_node = material.node_tree.nodes.active
        context_audit = {
            "background": bool(bpy_module.app.background),
            "scene": scene.name,
            "view_layer": bpy_module.context.view_layer.name,
            "engine": scene.render.engine,
            "cycles_device": scene.cycles.device,
            "cycles_samples": int(scene.cycles.samples),
            "cycles_bake_type": scene.cycles.bake_type,
            "scene_bake_target": scene.render.bake.target,
            "scene_bake_margin": int(scene.render.bake.margin),
            "scene_use_selected_to_active": bool(scene.render.bake.use_selected_to_active),
            "active_object": bpy_module.context.view_layer.objects.active.name
            if bpy_module.context.view_layer.objects.active
            else None,
            "active_object_mode": obj.mode,
            "selected_count": len(bpy_module.context.selected_objects),
            "selected_objects": [candidate.name for candidate in bpy_module.context.selected_objects],
            "selected_editable_count": len(bpy_module.context.selected_editable_objects),
            "object_visible_get": bool(obj.visible_get()),
            "object_hide_viewport": bool(obj.hide_viewport),
            "object_hide_render": bool(obj.hide_render),
            "object_hide_select": bool(obj.hide_select),
            "object_local_hidden": bool(obj.hide_get()),
            "mesh_vertices": len(obj.data.vertices),
            "mesh_polygons": len(obj.data.polygons),
            "mesh_loops": len(obj.data.loops),
            "uv": _uv_record(obj.data),
            "material": obj.active_material.name if obj.active_material else None,
            "active_image_node": active_node.name if active_node else None,
            "active_image_node_type": active_node.bl_idname if active_node else None,
            "active_image_node_selected": bool(active_node.select) if active_node else None,
            "active_image_node_image": active_node.image.name
            if active_node and getattr(active_node, "image", None)
            else None,
            "active_image_node_matches_target": active_node == target,
            "emission_node": emission.name,
            "emission_color_linear": _float_list(emission.inputs["Color"].default_value[:3]),
            "emission_strength": float(emission.inputs["Strength"].default_value),
            "output_surface_linked": bool(created["output"].inputs["Surface"].is_linked),
            "image": {
                "name": image.name,
                "size": [int(image.size[0]), int(image.size[1])],
                "float_buffer": bool(image.is_float),
                "colorspace": image.colorspace_settings.name,
                "alpha_mode": image.alpha_mode,
            },
            "bake_operator_poll": bool(bpy_module.ops.object.bake.poll()),
            "depsgraph_updated": True,
            "temp_override_keys": [
                "scene",
                "view_layer",
                "active_object",
                "object",
                "selected_objects",
                "selected_editable_objects",
            ],
        }
        result["context_audit_before_operator"] = context_audit

        override = {
            "scene": scene,
            "view_layer": bpy_module.context.view_layer,
            "active_object": obj,
            "object": obj,
            "selected_objects": [obj],
            "selected_editable_objects": [obj],
        }
        operator_started = time.perf_counter()
        with bpy_module.context.temp_override(**override):
            operator_return = bpy_module.ops.object.bake(
                type="EMIT",
                margin=BAKE_MARGIN,
                margin_type="EXTEND",
                use_selected_to_active=False,
                use_clear=True,
                target="IMAGE_TEXTURES",
                save_mode="INTERNAL",
                uv_layer="UVMap",
            )
        image.update()
        bpy_module.context.view_layer.update()
        result["operator"] = {
            "return": sorted(operator_return),
            "elapsed_seconds": round(time.perf_counter() - operator_started, 6),
            "kwargs": {
                "type": "EMIT",
                "margin": BAKE_MARGIN,
                "margin_type": "EXTEND",
                "use_selected_to_active": False,
                "use_clear": True,
                "target": "IMAGE_TEXTURES",
                "save_mode": "INTERNAL",
                "uv_layer": "UVMap",
            },
        }
        storage_domain = "srgb_encoded" if case_name == "byte_srgb" else "linear"
        result["image_buffer"] = _image_contract_metrics(
            image, np_module, storage_domain=storage_domain
        )
        output_path = (
            stage_dir
            / "preview"
            / f"phase_a_{context_name}_{case_name}{CASE_DEFINITIONS[case_name]['extension']}"
        )
        result["saved_file"] = _save_and_reload(
            bpy_module, np_module, image, case_name, output_path
        )
    except Exception:
        result["exception"] = traceback.format_exc()
    finally:
        if created is not None:
            result["cleanup"] = _cleanup_probe(bpy_module, created)
        result["elapsed_seconds"] = round(time.perf_counter() - started, 3)
    return result


def run_blender_internal() -> int:
    """Run the selected isolated Blender scene context without saving the Blend."""

    import bpy  # type: ignore[import-not-found]
    import numpy as np  # type: ignore[import-not-found]

    args = blender_args()
    output_path = args.internal_output.resolve()
    stage_dir = args.stage_dir.resolve()
    source_filepath = Path(bpy.data.filepath).resolve() if bpy.data.filepath else None
    source_before = file_record(source_filepath, root=repository_root()) if source_filepath else None
    report: dict[str, Any] = {
        "schema_version": INTERNAL_SCHEMA,
        "requirement_id": REQUIREMENT_ID,
        "stage_id": STAGE_ID,
        "generated_at": utc_now(),
        "scope": "phase_a_bake_liveness_only",
        "context": args.internal_context,
        "source_blend": source_before,
        "source_blend_saved_by_probe": False,
        "runtime": {
            "blender_version": bpy.app.version_string,
            "blender_version_tuple": list(bpy.app.version),
            "blender_build_hash": bpy.app.build_hash.decode("utf-8", "replace")
            if isinstance(bpy.app.build_hash, bytes)
            else str(bpy.app.build_hash),
            "background": bool(bpy.app.background),
            "binary_path": bpy.app.binary_path,
            "python": sys.executable,
            "python_version": sys.version,
            "numpy_version": np.__version__,
            "cycles_devices": _cycles_devices(bpy),
        },
        "contract": {
            "target_linear_rgb": list(TARGET_LINEAR_RGB),
            "target_encoded_srgb": encoded_target_rgb(),
            "image_size": [IMAGE_SIZE, IMAGE_SIZE],
            "bake_type": "EMIT",
            "engine": "CYCLES",
            "device": "CPU",
            "margin": BAKE_MARGIN,
            "use_selected_to_active": False,
        },
        "cases": {},
        "exception": None,
    }
    exit_code = 0
    try:
        if args.internal_context == "factory_startup" and bpy.data.filepath:
            raise RuntimeError(
                f"factory_startup context unexpectedly has a source filepath: {bpy.data.filepath}"
            )
        if args.internal_context == "v5_scene_clone" and not bpy.data.filepath:
            raise RuntimeError("v5_scene_clone context did not open the locked V5 Blend")
        for case_name in CASE_DEFINITIONS:
            report["cases"][case_name] = _run_blender_case(
                bpy,
                np,
                context_name=args.internal_context,
                case_name=case_name,
                stage_dir=stage_dir,
            )
            if report["cases"][case_name]["exception"] is not None:
                exit_code = 1
    except Exception:
        report["exception"] = traceback.format_exc()
        exit_code = 1
    finally:
        source_after = (
            file_record(source_filepath, root=repository_root()) if source_filepath else None
        )
        report["source_blend_after"] = source_after
        report["source_blend_unchanged_during_internal_process"] = (
            source_before == source_after if source_before is not None else True
        )
        if report["source_blend_unchanged_during_internal_process"] is not True:
            exit_code = 1
        write_json(output_path, report)
    print(
        json.dumps(
            {
                "internal_report": str(output_path),
                "context": args.internal_context,
                "case_exceptions": {
                    name: case.get("exception") is not None
                    for name, case in report.get("cases", {}).items()
                },
            },
            ensure_ascii=False,
        )
    )
    return exit_code


def main() -> int:
    """Dispatch between normal orchestration and Blender-internal execution."""

    if "--internal-context" in sys.argv:
        return run_blender_internal()
    return run_orchestrator()


if __name__ == "__main__":
    raise SystemExit(main())
