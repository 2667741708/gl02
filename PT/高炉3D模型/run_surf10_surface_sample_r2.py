"""Run SURF-10 R2 as a corrected single-surface material sample.

The parent process launches Blender headless and records command/stdout/stderr.
The Blender child creates a clean review panel derived from the approved P40
shaft segment bounds, applies only the SURF-10 R2 procedural material to that
panel, renders beauty/channel/grazing evidence, saves a candidate .blend with
save_version=0, and writes machine-readable reports for review.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
import traceback
from datetime import datetime, timezone
from pathlib import Path
from statistics import mean, pstdev
from typing import Any, Iterable


STAGE = "SURF-10_R2"
STATUS = "candidate_ready_for_review"
APPROVAL = "not_granted_requires_visual_and_spec_review"
EXPECTED_INPUT_SHA256 = "03635cf6608a54c4a671fb4d84adcb9451a36fe47cea7b564af2d4d3b69b2256"
EXPECTED_SENSOR_COUNT = 115
EXPECTED_BODY_SENSOR_COUNT = 80
EXPECTED_LAYERS = [f"GL02_SENSOR_LAYER_L{layer}" for layer in range(7, 17)]
EXPECTED_PROCESS_ZONES = [
    "APPROX_GL02_FURNACE_HEARTH",
    "APPROX_GL02_FURNACE_BOSH",
    "APPROX_GL02_FURNACE_BELLY",
    "APPROX_GL02_FURNACE_SHAFT",
    "APPROX_GL02_FURNACE_THROAT",
]

SCRIPT_PATH = Path(__file__).resolve()
MODULE_ROOT = SCRIPT_PATH.parent
PROJECT_ROOT = SCRIPT_PATH.parents[2]
DEFAULT_BLENDER = Path(r"D:\Program Files\Blender Foundation\Blender 5.2\blender.exe")
DEFAULT_INPUT_BLEND = (
    MODULE_ROOT
    / "work"
    / "P40_FIXED_LOOKDEV_20260717_P36_FINAL"
    / "P40_LOOKDEV_APPROVED.blend"
)
DEFAULT_OUTPUT_DIR = MODULE_ROOT / "work" / "SURF_10_20260718_R2"
SOURCE_SEGMENT_NAME = "APPROX_GL02_FURNACE_SHAFT"
SAMPLE_OBJECT_NAME = "SURF10_R2_SAMPLE_PANEL_FROM_APPROX_GL02_FURNACE_SHAFT"
SAMPLE_MATERIAL_NAME = "SURF10_R2_weathered_green_gray_steel_soft_pitting"
BLEND_NAME = "SURF10_R2_SURFACE_SAMPLE_CANDIDATE.blend"


def now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(path.name + ".tmp")
    temp.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=False, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    os.replace(temp, path)


def write_text(path: Path, value: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(path.name + ".tmp")
    temp.write_text(value, encoding="utf-8", newline="\n")
    os.replace(temp, path)


def relative_display(path: Path) -> str:
    resolved = path.resolve()
    try:
        return resolved.relative_to(PROJECT_ROOT.resolve()).as_posix()
    except ValueError:
        return resolved.as_posix()


def artifact_hashes(output_dir: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for path in sorted(p for p in output_dir.rglob("*") if p.is_file()):
        if path.name == "artifact_sha256.json":
            continue
        if path.suffix.lower() == ".blend1":
            continue
        rows.append(
            {
                "path": path.resolve().as_posix(),
                "project_relative_path": relative_display(path),
                "bytes": path.stat().st_size,
                "sha256": sha256_file(path),
            }
        )
    return rows


def write_artifact_index(output_dir: Path) -> None:
    blend1_files = sorted(p.as_posix() for p in output_dir.rglob("*.blend1"))
    write_json(
        output_dir / "artifact_sha256.json",
        {
            "schema_version": 1,
            "stage": STAGE,
            "generated_at": now_iso(),
            "excludes": ["artifact_sha256.json", "*.blend1"],
            "blend1_files_found": blend1_files,
            "artifacts": artifact_hashes(output_dir),
        },
    )


def run_parent(args: argparse.Namespace) -> int:
    input_blend = args.input_blend.resolve()
    blender = args.blender.resolve()
    output_dir = args.output_dir.resolve()
    if not input_blend.is_file():
        raise FileNotFoundError(input_blend)
    if not blender.is_file():
        raise FileNotFoundError(blender)
    input_sha = sha256_file(input_blend)
    if input_sha.lower() != EXPECTED_INPUT_SHA256:
        raise RuntimeError(f"Input SHA mismatch: expected {EXPECTED_INPUT_SHA256}, got {input_sha}")
    output_dir.mkdir(parents=True, exist_ok=True)
    stale_exception = output_dir / "surf10_r2_child_exception.txt"
    if stale_exception.exists():
        stale_exception.unlink()

    command = [
        str(blender),
        "--background",
        str(input_blend),
        "--python",
        str(SCRIPT_PATH),
        "--",
        "--blender-child",
        "--output-dir",
        str(output_dir),
        "--width",
        str(args.width),
        "--height",
        str(args.height),
        "--texture-resolution",
        str(args.texture_resolution),
    ]
    command_record = {
        "schema_version": 1,
        "stage": STAGE,
        "created_at": now_iso(),
        "cwd": PROJECT_ROOT.as_posix(),
        "command": command,
        "input_blend": input_blend.as_posix(),
        "input_sha256": input_sha,
        "expected_input_sha256": EXPECTED_INPUT_SHA256,
        "blender": blender.as_posix(),
        "output_dir": output_dir.as_posix(),
    }
    write_json(output_dir / "surf10_r2_execution_command.json", command_record)
    stdout_path = output_dir / "runner.stdout.log"
    stderr_path = output_dir / "runner.stderr.log"
    with stdout_path.open("w", encoding="utf-8", newline="\n") as stdout, stderr_path.open(
        "w", encoding="utf-8", newline="\n"
    ) as stderr:
        completed = subprocess.run(command, cwd=PROJECT_ROOT, stdout=stdout, stderr=stderr, check=False)
    command_record["completed_at"] = now_iso()
    command_record["exit_code"] = completed.returncode
    write_json(output_dir / "surf10_r2_execution_command.json", command_record)
    write_artifact_index(output_dir)
    report_path = output_dir / "surf10_r2_machine_report.json"
    if report_path.is_file():
        report = json.loads(report_path.read_text(encoding="utf-8"))
        print(
            json.dumps(
                {
                    "stage": report.get("stage"),
                    "status": report.get("status"),
                    "approval": report.get("approval"),
                    "exit_code": completed.returncode,
                    "report": report_path.as_posix(),
                    "candidate": report.get("candidate", {}),
                    "assertion_summary": report.get("assertion_summary", {}),
                    "anti_repetition": report.get("texture_statistics", {}).get("anti_repetition_assertions", {}),
                },
                ensure_ascii=False,
                indent=2,
            )
        )
    if completed.returncode == 0 and not report_path.is_file():
        return 3
    return completed.returncode


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--blender-child", action="store_true")
    parser.add_argument("--input-blend", type=Path, default=DEFAULT_INPUT_BLEND)
    parser.add_argument("--blender", type=Path, default=DEFAULT_BLENDER)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--width", type=int, default=1400)
    parser.add_argument("--height", type=int, default=900)
    parser.add_argument("--texture-resolution", type=int, default=1024)
    return parser.parse_args(argv)


def blender_child(args: argparse.Namespace) -> int:
    import math

    import bpy
    from mathutils import Vector

    bpy.context.preferences.filepaths.save_version = 0

    output_dir = args.output_dir.resolve()
    texture_dir = output_dir / "textures"
    beauty_dir = output_dir / "renders" / "beauty"
    channel_dir = output_dir / "renders" / "channels"
    diagnostic_dir = output_dir / "renders" / "diagnostic"
    for path in (texture_dir, beauty_dir, channel_dir, diagnostic_dir):
        path.mkdir(parents=True, exist_ok=True)

    events: list[dict[str, Any]] = []
    assertions: list[dict[str, Any]] = []

    def event(name: str, **fields: Any) -> None:
        events.append({"at": now_iso(), "event": name, **fields})

    def assert_row(assertion_id: str, ok: bool, detail: Any = None) -> None:
        assertions.append({"id": assertion_id, "ok": bool(ok), "detail": detail})

    def obj_matrix_signature(names: Iterable[str]) -> dict[str, Any]:
        rows: dict[str, Any] = {}
        for name in sorted(names):
            obj = bpy.data.objects.get(name)
            if obj is None:
                rows[name] = None
            else:
                rows[name] = [round(float(value), 8) for row in obj.matrix_world for value in row]
        return rows

    def signature_hash(value: Any) -> str:
        payload = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
        return hashlib.sha256(payload).hexdigest()

    def material_slots_signature(names: Iterable[str]) -> dict[str, Any]:
        rows: dict[str, Any] = {}
        for name in sorted(names):
            obj = bpy.data.objects.get(name)
            if obj is None:
                rows[name] = None
            else:
                rows[name] = [slot.material.name if slot.material else None for slot in obj.material_slots]
        return rows

    def sensor_names() -> list[str]:
        return sorted(name for name in bpy.data.objects.keys() if name.startswith("SENSOR_"))

    def exists_layer(name: str) -> bool:
        return name in bpy.data.objects or name in bpy.data.collections

    def clamp(value: float, low: float = 0.0, high: float = 1.0) -> float:
        return max(low, min(high, value))

    def smoothstep(value: float) -> float:
        return value * value * (3.0 - 2.0 * value)

    def lerp(left: float, right: float, factor: float) -> float:
        return left + (right - left) * factor

    def hash01(x: int, y: int, seed: int = 0) -> float:
        value = math.sin(x * 127.1 + y * 311.7 + seed * 74.7) * 43758.5453123
        return value - math.floor(value)

    def value_noise(u: float, v: float, scale_x: float, scale_y: float, seed: int) -> float:
        px = u * scale_x
        py = v * scale_y
        x0 = math.floor(px)
        y0 = math.floor(py)
        tx = smoothstep(px - x0)
        ty = smoothstep(py - y0)
        a = hash01(x0, y0, seed)
        b = hash01(x0 + 1, y0, seed)
        c = hash01(x0, y0 + 1, seed)
        d = hash01(x0 + 1, y0 + 1, seed)
        return lerp(lerp(a, b, tx), lerp(c, d, tx), ty)

    def domain_noise(u: float, v: float, seed: int) -> tuple[float, float]:
        du = (value_noise(u, v, 2.7, 3.9, seed) - 0.5) * 0.045
        dv = (value_noise(u, v, 3.3, 2.4, seed + 1) - 0.5) * 0.045
        return u + du, v + dv

    def soft_pit(u: float, v: float) -> tuple[float, float]:
        grid_x = 68.0
        grid_y = 82.0
        cx = math.floor(u * grid_x)
        cy = math.floor(v * grid_y)
        best = 0.0
        area = 0.0
        for oy in (-1, 0, 1):
            for ox in (-1, 0, 1):
                gx = int(cx + ox)
                gy = int(cy + oy)
                chance = hash01(gx, gy, 701)
                if chance < 0.918:
                    continue
                center_u = (gx + 0.18 + 0.64 * hash01(gx, gy, 702)) / grid_x
                center_v = (gy + 0.16 + 0.68 * hash01(gx, gy, 703)) / grid_y
                radius_u = 0.0032 + 0.0048 * hash01(gx, gy, 704)
                radius_v = radius_u * (0.92 + 0.18 * hash01(gx, gy, 705))
                angle = hash01(gx, gy, 706) * math.tau
                dx = u - center_u
                dy = v - center_v
                ca = math.cos(angle)
                sa = math.sin(angle)
                rx = ca * dx + sa * dy
                ry = -sa * dx + ca * dy
                d2 = (rx / radius_u) ** 2 + (ry / radius_v) ** 2
                edge_noise = 0.90 + 0.18 * value_noise(u, v, 210.0, 193.0, 771)
                pit = math.exp(-d2 * edge_noise * 3.65)
                if pit > best:
                    best = pit
                    area = math.pi * radius_u * radius_v
        return clamp(best), area

    def image_stats(values: list[float]) -> dict[str, float]:
        return {
            "min": round(min(values), 6),
            "max": round(max(values), 6),
            "mean": round(mean(values), 6),
            "stddev": round(pstdev(values), 6),
        }

    def downsample(values: list[float], source_res: int, target_res: int = 128) -> list[float]:
        step = source_res / target_res
        result: list[float] = []
        for y in range(target_res):
            sy = min(source_res - 1, int((y + 0.5) * step))
            row = sy * source_res
            for x in range(target_res):
                sx = min(source_res - 1, int((x + 0.5) * step))
                result.append(values[row + sx])
        return result

    def autocorr(values: list[float], width: int, height: int, dx: int, dy: int) -> float:
        pairs_a: list[float] = []
        pairs_b: list[float] = []
        for y in range(max(0, -dy), min(height, height - dy)):
            for x in range(max(0, -dx), min(width, width - dx)):
                pairs_a.append(values[y * width + x])
                pairs_b.append(values[(y + dy) * width + (x + dx)])
        ma = mean(pairs_a)
        mb = mean(pairs_b)
        va = math.sqrt(sum((v - ma) ** 2 for v in pairs_a))
        vb = math.sqrt(sum((v - mb) ** 2 for v in pairs_b))
        if va <= 1e-9 or vb <= 1e-9:
            return 0.0
        return sum((a - ma) * (b - mb) for a, b in zip(pairs_a, pairs_b)) / (va * vb)

    def diag_bias(values: list[float], width: int, height: int) -> float:
        diag = 0.0
        axial = 0.0
        for y in range(1, height - 1):
            for x in range(1, width - 1):
                c = values[y * width + x]
                diag += abs(c - values[(y - 1) * width + x - 1]) + abs(c - values[(y - 1) * width + x + 1])
                axial += abs(c - values[y * width + x - 1]) + abs(c - values[(y - 1) * width + x])
        return diag / max(1e-9, axial)

    def create_image(name: str, path: Path, pixels: list[float], width: int, height: int, colorspace: str) -> dict[str, Any]:
        import struct
        import zlib

        path.parent.mkdir(parents=True, exist_ok=True)
        raw_rows = bytearray()
        stride = width * 4
        byte_pixels = bytearray(max(0, min(255, int(round(value * 255.0)))) for value in pixels)
        for row in range(height):
            raw_rows.append(0)
            start = row * stride
            raw_rows.extend(byte_pixels[start : start + stride])

        def chunk(kind: bytes, data: bytes) -> bytes:
            return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF)

        png = bytearray(b"\x89PNG\r\n\x1a\n")
        png.extend(chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0)))
        png.extend(chunk(b"IDAT", zlib.compress(bytes(raw_rows), level=6)))
        png.extend(chunk(b"IEND", b""))
        path.write_bytes(png)
        return {
            "path": path.as_posix(),
            "project_relative_path": relative_display(path),
            "bytes": path.stat().st_size,
            "sha256": sha256_file(path),
            "colorspace": colorspace,
        }

    input_blend_path = Path(bpy.data.filepath)
    event("child_started", blender_version=bpy.app.version_string, blend=input_blend_path.as_posix())
    original_sensor_names = sensor_names()
    original_body_sensor_names = [name for name in original_sensor_names if name.startswith("SENSOR_T_body_L")]
    protected_names = original_sensor_names + EXPECTED_PROCESS_ZONES
    before_matrix_hash = signature_hash(obj_matrix_signature(protected_names))
    before_material_hash = signature_hash(material_slots_signature(EXPECTED_PROCESS_ZONES))

    source = bpy.data.objects.get(SOURCE_SEGMENT_NAME)
    assert_row("input_blend_loaded", bool(bpy.data.filepath), input_blend_path.as_posix())
    assert_row("input_sha256_matches_lock", sha256_file(input_blend_path).lower() == EXPECTED_INPUT_SHA256, sha256_file(input_blend_path))
    assert_row("source_segment_exists", source is not None, SOURCE_SEGMENT_NAME)
    assert_row("save_version_is_zero", bpy.context.preferences.filepaths.save_version == 0, bpy.context.preferences.filepaths.save_version)
    assert_row("sensor_count_before_is_115", len(original_sensor_names) == EXPECTED_SENSOR_COUNT, len(original_sensor_names))
    assert_row(
        "body_temperature_sensor_count_before_is_80",
        len(original_body_sensor_names) == EXPECTED_BODY_SENSOR_COUNT,
        len(original_body_sensor_names),
    )
    assert_row("all_l7_l16_layers_present_before", all(exists_layer(name) for name in EXPECTED_LAYERS), EXPECTED_LAYERS)
    assert_row(
        "all_five_process_zones_present_before",
        all(bpy.data.objects.get(name) is not None for name in EXPECTED_PROCESS_ZONES),
        EXPECTED_PROCESS_ZONES,
    )
    if source is None:
        raise RuntimeError(f"Missing source segment: {SOURCE_SEGMENT_NAME}")

    resolution = int(args.texture_resolution)
    height_map = [0.0] * (resolution * resolution)
    base_luma: list[float] = []
    rough_values: list[float] = []
    pit_values: list[float] = []
    pit_areas: list[float] = []
    base_pixels: list[float] = []
    rough_pixels: list[float] = []
    height_pixels: list[float] = []
    metallic_pixels: list[float] = []
    for y in range(resolution):
        v = y / max(1, resolution - 1)
        for x in range(resolution):
            u = x / max(1, resolution - 1)
            wu, wv = domain_noise(u, v, 101)
            orange = 0.62 * value_noise(wu, wv, 4.35, 5.85, 111) + 0.38 * value_noise(wu, wv, 8.2, 6.7, 112)
            cross = 0.46 * value_noise(wu + 0.031, wv - 0.017, 17.3, 23.7, 113)
            fine = 0.55 * value_noise(wu, wv, 137.0, 163.0, 114) + 0.45 * value_noise(wu, wv, 251.0, 227.0, 115)
            sand = hash01(x, y, 116) - 0.5
            pit, pit_area = soft_pit(wu, wv)
            streak_cell = int(wu * 52.0)
            streak_center = (streak_cell + 0.12 + 0.72 * hash01(streak_cell, 4, 121)) / 52.0
            streak_width = 0.0028 + 0.0068 * hash01(streak_cell, 9, 122)
            streak_gate = 1.0 if hash01(streak_cell, 2, 120) > 0.76 else 0.0
            vertical_mod = 0.46 + 0.54 * value_noise(wu, wv, 3.5, 13.7, 123)
            streak = streak_gate * math.exp(-((wu - streak_center) ** 2) / max(0.000001, streak_width * streak_width)) * vertical_mod
            dust = clamp(0.042 * streak + 0.046 * value_noise(wu, wv, 31.0, 19.0, 130) + 0.018 * hash01(x // 9, y // 7, 131))
            water = clamp(0.026 * streak * (0.28 + 0.72 * v))
            oxide = clamp(0.46 * pit + 0.036 * dust + 0.018 * value_noise(wu, wv, 21.0, 15.0, 132))
            micro_height = (orange - 0.5) * 0.062 + (cross - 0.23) * 0.024 + (fine - 0.5) * 0.030 + sand * 0.007
            h = clamp(0.5 + micro_height + dust * 0.020 - pit * 0.052 - water * 0.010)
            height_map[y * resolution + x] = h
            height_pixels.extend([h, h, h, 1.0])
            pit_values.append(pit)
            if pit > 0.08:
                pit_areas.append(pit_area)

            base_r = 0.198 + 0.052 * orange + 0.030 * fine + 0.028 * dust - 0.016 * water - 0.014 * pit
            base_g = 0.236 + 0.047 * orange + 0.024 * fine + 0.025 * dust - 0.015 * water - 0.020 * pit
            base_b = 0.222 + 0.038 * orange + 0.020 * fine + 0.021 * dust - 0.014 * water - 0.018 * pit
            base_r += 0.030 * oxide
            base_g += 0.012 * oxide
            base_b += 0.002 * oxide
            r = clamp(base_r)
            g = clamp(base_g)
            b = clamp(base_b)
            base_luma.append(0.2126 * r + 0.7152 * g + 0.0722 * b)
            base_pixels.extend([r, g, b, 1.0])

            rough = clamp(0.458 + 0.158 * orange + 0.112 * fine + 0.174 * dust + 0.066 * pit - 0.050 * water, 0.44, 0.78)
            rough_values.append(rough)
            rough_pixels.extend([rough, rough, rough, 1.0])
            metallic = clamp(0.78 - 0.52 * oxide - 0.42 * dust - 0.34 * pit, 0.08, 0.82)
            metallic_pixels.extend([metallic, metallic, metallic, 1.0])

    normal_pixels: list[float] = []
    normal_xy_magnitude: list[float] = []
    normal_strength_px = 7.40
    for y in range(resolution):
        for x in range(resolution):
            left = height_map[y * resolution + max(0, x - 1)]
            right = height_map[y * resolution + min(resolution - 1, x + 1)]
            down = height_map[max(0, y - 1) * resolution + x]
            up = height_map[min(resolution - 1, y + 1) * resolution + x]
            dx = (right - left) * normal_strength_px
            dy = (up - down) * normal_strength_px
            nx, ny, nz = -dx, -dy, 1.0
            length = math.sqrt(nx * nx + ny * ny + nz * nz)
            nx, ny, nz = nx / length, ny / length, nz / length
            normal_xy_magnitude.append(math.sqrt(nx * nx + ny * ny))
            normal_pixels.extend([nx * 0.5 + 0.5, ny * 0.5 + 0.5, nz * 0.5 + 0.5, 1.0])

    small = downsample(base_luma, resolution, 128)
    anti_repetition = {
        "autocorr_x_32": round(autocorr(small, 128, 128, 32, 0), 6),
        "autocorr_y_32": round(autocorr(small, 128, 128, 0, 32), 6),
        "autocorr_diag_24": round(autocorr(small, 128, 128, 24, 24), 6),
        "diagonal_to_axial_gradient_ratio": round(diag_bias(small, 128, 128), 6),
    }
    texture_statistics = {
        "base_luma": image_stats(base_luma),
        "roughness": image_stats(rough_values),
        "normal_xy_magnitude": image_stats(normal_xy_magnitude),
        "pit_soft_mask": image_stats(pit_values),
        "pit_area_uv": image_stats(pit_areas or [0.0]),
        "pit_active_pixel_ratio": round(sum(1 for value in pit_values if value > 0.08) / len(pit_values), 6),
        "anti_repetition_assertions": anti_repetition,
    }
    assert_row("basecolor_is_dark_green_gray_not_black", 0.18 <= texture_statistics["base_luma"]["mean"] <= 0.34, texture_statistics["base_luma"])
    assert_row("roughness_has_nonflat_variation", texture_statistics["roughness"]["stddev"] >= 0.025, texture_statistics["roughness"])
    assert_row("normal_micro_detail_is_present_but_restrained", 0.018 <= texture_statistics["normal_xy_magnitude"]["mean"] <= 0.155, texture_statistics["normal_xy_magnitude"])
    assert_row("soft_pitting_is_sparse_not_square_black_noise", 0.006 <= texture_statistics["pit_active_pixel_ratio"] <= 0.055, texture_statistics["pit_active_pixel_ratio"])
    assert_row("nonperiodic_autocorrelation_x32_low", abs(anti_repetition["autocorr_x_32"]) < 0.62, anti_repetition)
    assert_row("nonperiodic_autocorrelation_y32_low", abs(anti_repetition["autocorr_y_32"]) < 0.62, anti_repetition)
    assert_row("diagonal_moire_bias_not_dominant", 0.70 <= anti_repetition["diagonal_to_axial_gradient_ratio"] <= 1.36, anti_repetition)

    texture_assets = {
        "basecolor": create_image(
            "SURF10_R2_basecolor_dark_green_gray_warm_dust_water_streaks",
            texture_dir / "SURF10_R2_basecolor_dark_green_gray_warm_dust_water_streaks.png",
            base_pixels,
            resolution,
            resolution,
            "sRGB",
        ),
        "roughness": create_image(
            "SURF10_R2_roughness_soft_pitting_dust_microvariation",
            texture_dir / "SURF10_R2_roughness_soft_pitting_dust_microvariation.png",
            rough_pixels,
            resolution,
            resolution,
            "Non-Color",
        ),
        "normal": create_image(
            "SURF10_R2_normal_layered_orange_peel_fine_sand",
            texture_dir / "SURF10_R2_normal_layered_orange_peel_fine_sand.png",
            normal_pixels,
            resolution,
            resolution,
            "Non-Color",
        ),
        "height_diagnostic": create_image(
            "SURF10_R2_height_soft_pitting_orange_peel_fine_sand",
            texture_dir / "SURF10_R2_height_soft_pitting_orange_peel_fine_sand.png",
            height_pixels,
            resolution,
            resolution,
            "Non-Color",
        ),
        "metallic_diagnostic": create_image(
            "SURF10_R2_metallic_diagnostic_nonmetal_pits_dust",
            texture_dir / "SURF10_R2_metallic_diagnostic_nonmetal_pits_dust.png",
            metallic_pixels,
            resolution,
            resolution,
            "Non-Color",
        ),
    }
    event("textures_created", assets=texture_assets, statistics=texture_statistics)

    collection = bpy.data.collections.new("SURF10_R2_SINGLE_SURFACE_SAMPLE")
    bpy.context.scene.collection.children.link(collection)
    if SAMPLE_OBJECT_NAME in bpy.data.objects:
        bpy.data.objects.remove(bpy.data.objects[SAMPLE_OBJECT_NAME], do_unlink=True)
    source_bbox = [source.matrix_world @ Vector(corner) for corner in source.bound_box]
    source_min = Vector((min(point.x for point in source_bbox), min(point.y for point in source_bbox), min(point.z for point in source_bbox)))
    source_max = Vector((max(point.x for point in source_bbox), max(point.y for point in source_bbox), max(point.z for point in source_bbox)))
    source_center = (source_min + source_max) * 0.5
    z_span = max(0.1, source_max.z - source_min.z)
    front_radius = max(10.0, abs(source_min.y - source_center.y))
    panel_width = min(8.4, max(5.0, (source_max.x - source_min.x) * 0.36))
    panel_height = min(12.4, max(7.4, z_span * 0.74))
    columns = 220
    rows = 320
    vertices: list[tuple[float, float, float]] = []
    faces: list[tuple[int, int, int, int]] = []
    for row in range(rows):
        v = row / (rows - 1)
        z = source_center.z + (v - 0.5) * panel_height
        for column in range(columns):
            u = column / (columns - 1)
            x = source_center.x + (u - 0.5) * panel_width
            x_offset = x - source_center.x
            y = source_min.y - 0.04 + (x_offset * x_offset) / (2.0 * front_radius)
            tex_x = min(resolution - 1, max(0, int(round(u * (resolution - 1)))))
            tex_y = min(resolution - 1, max(0, int(round(v * (resolution - 1)))))
            y += (height_map[tex_y * resolution + tex_x] - 0.5) * 0.055
            vertices.append((x, y, z))
    for row in range(rows - 1):
        for column in range(columns - 1):
            a = row * columns + column
            faces.append((a, a + 1, a + columns + 1, a + columns))
    mesh = bpy.data.meshes.new(SAMPLE_OBJECT_NAME + "_mesh")
    mesh.from_pydata(vertices, [], faces)
    mesh.update()
    sample = bpy.data.objects.new(SAMPLE_OBJECT_NAME, mesh)
    sample["surf10_stage"] = STAGE
    sample["surf10_source_segment"] = SOURCE_SEGMENT_NAME
    sample["surf10_visual_boundary"] = "single clean-UV review panel; not a production full-furnace rollout"
    collection.objects.link(sample)
    uv_layer = sample.data.uv_layers.new(name="SURF10_R2_clean_review_panel_uv")
    for poly in sample.data.polygons:
        for loop_index in poly.loop_indices:
            vertex_index = sample.data.loops[loop_index].vertex_index
            row = vertex_index // columns
            column = vertex_index % columns
            uv_layer.data[loop_index].uv = (column / (columns - 1), row / (rows - 1))
    for poly in sample.data.polygons:
        poly.use_smooth = True

    material = bpy.data.materials.new(SAMPLE_MATERIAL_NAME)
    material.use_nodes = True
    nodes = material.node_tree.nodes
    for node in list(nodes):
        nodes.remove(node)
    output = nodes.new("ShaderNodeOutputMaterial")
    principled = nodes.new("ShaderNodeBsdfPrincipled")
    base_node = nodes.new("ShaderNodeTexImage")
    rough_node = nodes.new("ShaderNodeTexImage")
    normal_node = nodes.new("ShaderNodeTexImage")
    height_node = nodes.new("ShaderNodeTexImage")
    normal_map = nodes.new("ShaderNodeNormalMap")
    bump = nodes.new("ShaderNodeBump")
    base_node.image = bpy.data.images.load(texture_assets["basecolor"]["path"], check_existing=True)
    rough_node.image = bpy.data.images.load(texture_assets["roughness"]["path"], check_existing=True)
    normal_node.image = bpy.data.images.load(texture_assets["normal"]["path"], check_existing=True)
    height_node.image = bpy.data.images.load(texture_assets["height_diagnostic"]["path"], check_existing=True)
    base_node.image.colorspace_settings.name = "sRGB"
    rough_node.image.colorspace_settings.name = "Non-Color"
    normal_node.image.colorspace_settings.name = "Non-Color"
    height_node.image.colorspace_settings.name = "Non-Color"
    normal_map.inputs["Strength"].default_value = 0.45
    bump.inputs["Strength"].default_value = 0.16
    bump.inputs["Distance"].default_value = 0.10
    material.node_tree.links.new(base_node.outputs["Color"], principled.inputs["Base Color"])
    material.node_tree.links.new(rough_node.outputs["Color"], principled.inputs["Roughness"])
    material.node_tree.links.new(normal_node.outputs["Color"], normal_map.inputs["Color"])
    material.node_tree.links.new(normal_map.outputs["Normal"], bump.inputs["Normal"])
    material.node_tree.links.new(height_node.outputs["Color"], bump.inputs["Height"])
    material.node_tree.links.new(bump.outputs["Normal"], principled.inputs["Normal"])
    if "Metallic" in principled.inputs:
        principled.inputs["Metallic"].default_value = 0.62
    for input_name, value in (("Specular IOR Level", 0.58), ("Coat Weight", 0.04), ("Coat Roughness", 0.72)):
        if input_name in principled.inputs:
            principled.inputs[input_name].default_value = value
    material.node_tree.links.new(principled.outputs["BSDF"], output.inputs["Surface"])
    sample.data.materials.clear()
    sample.data.materials.append(material)

    material_manifest = {
        "schema_version": 1,
        "stage": STAGE,
        "status": STATUS,
        "approval": APPROVAL,
        "selected_source_segment": SOURCE_SEGMENT_NAME,
        "sample_object": SAMPLE_OBJECT_NAME,
        "sample_material": SAMPLE_MATERIAL_NAME,
        "scope": "one duplicated representative shell review panel only; original furnace segments and sensors are not assigned this material",
        "r2_changes_from_r1": [
            "layered normal is rebalanced into low-frequency orange peel plus high-frequency fine sand with readable but restrained shader strength",
            "pitting is generated by soft elliptical procedural wells with jittered centers and continuous edge falloff",
            "base color shifted to dark green-gray steel with restrained warm oxidation, dust, and gravity water streaks",
            "nonperiodic domain warp and incommensurate noise scales reduce repeated phase, diagonal streaks, and far-view moire risk",
            "artifact hashing excludes .blend1 and a save_version=0 assertion prevents Blender backup output",
        ],
        "pbr_parameters": {
            "base_finish": "matte rough dark green-gray service steel",
            "roughness_range_target": [0.44, 0.78],
            "principled_metallic_base": 0.62,
            "normal_map_strength": 0.45,
            "bump_strength": 0.16,
            "bump_distance_meters": 0.10,
            "sample_panel_vertex_relief_meters": 0.055,
            "pits_and_dust_are_nonmetallic_in_diagnostic_map": True,
        },
        "detail_layers": [
            "low-frequency orange-peel waviness",
            "high-frequency fine-sand normal microtexture",
            "sparse soft-edged pitting with non-black base color contribution",
            "low-contrast warm oxide and dust accumulation",
            "gravity-aligned water/dust streaks with randomized phase",
        ],
        "excluded_scope": [
            "no formal GLB export",
            "no replacement of production GLB",
            "no full-furnace material rollout",
            "no direct changes to 115 SENSOR nodes",
            "no direct changes to 80 BODY_TEMP sensor nodes",
            "no direct changes to L7-L16 sensor layer nodes/collections",
            "no direct material edits on the five original furnace process segments",
        ],
        "textures": texture_assets,
        "texture_statistics": texture_statistics,
    }

    bbox_points = [sample.matrix_world @ Vector(corner) for corner in sample.bound_box]
    bbox_min = Vector((min(point.x for point in bbox_points), min(point.y for point in bbox_points), min(point.z for point in bbox_points)))
    bbox_max = Vector((max(point.x for point in bbox_points), max(point.y for point in bbox_points), max(point.z for point in bbox_points)))
    center = (bbox_min + bbox_max) * 0.5

    def look_at(obj: Any, target: Vector) -> None:
        direction = target - obj.location
        obj.rotation_euler = direction.to_track_quat("-Z", "Y").to_euler()

    def make_camera(name: str, location: tuple[float, float, float], ortho_scale: float) -> Any:
        camera_data = bpy.data.cameras.new(name + "_DATA")
        camera = bpy.data.objects.new(name, camera_data)
        collection.objects.link(camera)
        camera.location = location
        camera.data.type = "ORTHO"
        camera.data.ortho_scale = ortho_scale
        camera.data.clip_start = 0.05
        camera.data.clip_end = 1000.0
        look_at(camera, center)
        return camera

    cameras = {
        "near": make_camera("SURF10_R2_CAM_NEAR_DETAIL", (center.x - 2.0, bbox_min.y - 12.0, center.z + 0.22), 2.20),
        "mid": make_camera("SURF10_R2_CAM_MID_SAMPLE", (center.x, bbox_min.y - 21.0, center.z + 0.3), 6.15),
        "far": make_camera("SURF10_R2_CAM_FAR_CONTEXT", (center.x, bbox_min.y - 34.0, center.z + 0.55), 15.4),
        "grazing": make_camera("SURF10_R2_CAM_GRAZING_CLOSEUP", (center.x - 2.4, bbox_min.y - 8.4, center.z + 0.08), 1.24),
    }

    def add_area_light(name: str, location: tuple[float, float, float], power: float, size: float) -> Any:
        light_data = bpy.data.lights.new(name, type="AREA")
        light = bpy.data.objects.new(name, light_data)
        collection.objects.link(light)
        light.location = location
        light.data.energy = power
        light.data.size = size
        look_at(light, center)
        return light

    neutral_lights = [
        add_area_light("SURF10_R2_NEUTRAL_LOW_RAKE_KEY", (bbox_min.x - 4.2, bbox_min.y - 5.8, center.z + 1.35), 620.0, 2.7),
        add_area_light("SURF10_R2_NEUTRAL_FILL_SOFTBOX", (center.x + 5.2, bbox_min.y - 13.4, center.z + 4.2), 150.0, 8.6),
        add_area_light("SURF10_R2_NEUTRAL_TOP_SOFTBOX", (center.x, center.y, bbox_max.z + 8.0), 92.0, 12.0),
    ]
    grazing_light = add_area_light("SURF10_R2_GRAZING_RAKE_LIGHT", (bbox_min.x - 4.8, bbox_min.y - 3.8, center.z + 0.44), 920.0, 0.85)
    grazing_light.hide_render = True
    grazing_light.hide_viewport = True
    bpy.context.scene.world = bpy.context.scene.world or bpy.data.worlds.new("World")
    bpy.context.scene.world.color = (0.58, 0.60, 0.60)
    bpy.context.scene.render.resolution_x = int(args.width)
    bpy.context.scene.render.resolution_y = int(args.height)
    bpy.context.scene.render.film_transparent = False
    try:
        bpy.context.scene.render.engine = "BLENDER_EEVEE_NEXT"
    except TypeError:
        bpy.context.scene.render.engine = "BLENDER_EEVEE"
    try:
        bpy.context.scene.eevee.taa_render_samples = 96
    except Exception:
        pass
    try:
        bpy.context.scene.view_settings.view_transform = "AgX"
        bpy.context.scene.view_settings.look = "Medium Low Contrast"
    except TypeError:
        bpy.context.scene.view_settings.look = "AgX - Medium Low Contrast"
    bpy.context.scene.view_settings.exposure = 0.35
    bpy.context.scene.view_settings.gamma = 1.0

    original_visibility = {
        obj.name: {
            "hide_render": obj.hide_render,
            "hide_viewport": obj.hide_viewport,
            "hide_set": obj.hide_get(),
        }
        for obj in bpy.data.objects
    }

    def isolate_sample_for_render() -> None:
        for obj in bpy.data.objects:
            if obj.type in {"MESH", "CURVE", "SURFACE", "FONT", "META"}:
                obj.hide_render = obj.name != sample.name
                obj.hide_viewport = obj.name != sample.name
                obj.hide_set(obj.name != sample.name)
        sample.hide_render = False
        sample.hide_viewport = False
        sample.hide_set(False)

    def restore_visibility() -> None:
        for obj in bpy.data.objects:
            state = original_visibility.get(obj.name)
            if state:
                obj.hide_render = state["hide_render"]
                obj.hide_viewport = state["hide_viewport"]
                obj.hide_set(state["hide_set"])
        sample.hide_render = False
        sample.hide_viewport = False
        sample.hide_set(False)

    def render(path: Path, camera: Any, width: int | None = None, height: int | None = None) -> dict[str, Any]:
        old_width = bpy.context.scene.render.resolution_x
        old_height = bpy.context.scene.render.resolution_y
        if width is not None:
            bpy.context.scene.render.resolution_x = width
        if height is not None:
            bpy.context.scene.render.resolution_y = height
        bpy.context.scene.camera = camera
        bpy.context.scene.render.filepath = path.as_posix()
        started = datetime.now()
        bpy.ops.render.render(write_still=True)
        seconds = (datetime.now() - started).total_seconds()
        bpy.context.scene.render.resolution_x = old_width
        bpy.context.scene.render.resolution_y = old_height
        return {
            "path": path.as_posix(),
            "project_relative_path": relative_display(path),
            "bytes": path.stat().st_size,
            "sha256": sha256_file(path),
            "seconds": round(seconds, 4),
            "camera": camera.name,
            "engine": bpy.context.scene.render.engine,
        }

    isolate_sample_for_render()
    beauty_renders = {
        "near": render(beauty_dir / "SURF10_R2_BEAUTY_NEAR_DETAIL.png", cameras["near"]),
        "mid": render(beauty_dir / "SURF10_R2_BEAUTY_MID_SAMPLE.png", cameras["mid"]),
        "far": render(beauty_dir / "SURF10_R2_BEAUTY_FAR_CONTEXT.png", cameras["far"]),
    }

    for light in neutral_lights:
        light.hide_render = True
        light.hide_viewport = True
    grazing_light.hide_render = False
    grazing_light.hide_viewport = False
    grazing_render = render(diagnostic_dir / "SURF10_R2_GRAZING_LIGHT_CLOSEUP.png", cameras["grazing"], width=1200, height=900)
    for light in neutral_lights:
        light.hide_render = False
        light.hide_viewport = False
    grazing_light.hide_render = True
    grazing_light.hide_viewport = True

    def channel_material(name: str, texture_path: str, colorspace: str) -> Any:
        mat = bpy.data.materials.new(name)
        mat.use_nodes = True
        nodes = mat.node_tree.nodes
        for node in list(nodes):
            nodes.remove(node)
        out = nodes.new("ShaderNodeOutputMaterial")
        tex = nodes.new("ShaderNodeTexImage")
        tex.image = bpy.data.images.load(texture_path, check_existing=True)
        tex.image.colorspace_settings.name = colorspace
        emission = nodes.new("ShaderNodeEmission")
        emission.inputs["Strength"].default_value = 1.0
        mat.node_tree.links.new(tex.outputs["Color"], emission.inputs["Color"])
        mat.node_tree.links.new(emission.outputs["Emission"], out.inputs["Surface"])
        return mat

    original_sample_materials = [slot.material for slot in sample.material_slots]
    channel_materials = {
        "basecolor": channel_material("SURF10_R2_DIAG_BASECOLOR_EMISSION", texture_assets["basecolor"]["path"], "sRGB"),
        "roughness": channel_material("SURF10_R2_DIAG_ROUGHNESS_EMISSION", texture_assets["roughness"]["path"], "Non-Color"),
        "normal": channel_material("SURF10_R2_DIAG_NORMAL_EMISSION", texture_assets["normal"]["path"], "Non-Color"),
    }
    channel_renders: dict[str, Any] = {}
    for name, mat in channel_materials.items():
        sample.data.materials.clear()
        sample.data.materials.append(mat)
        channel_renders[name] = render(
            channel_dir / f"SURF10_R2_CHANNEL_{name.upper()}_NEAR.png",
            cameras["near"],
            width=min(1100, int(args.width)),
            height=min(900, int(args.height)),
        )
    sample.data.materials.clear()
    for mat in original_sample_materials:
        sample.data.materials.append(mat)

    restore_visibility()
    bpy.context.scene.render.resolution_x = int(args.width)
    bpy.context.scene.render.resolution_y = int(args.height)

    after_sensor_names = sensor_names()
    after_body_sensor_names = [name for name in after_sensor_names if name.startswith("SENSOR_T_body_L")]
    after_matrix_hash = signature_hash(obj_matrix_signature(protected_names))
    after_material_hash = signature_hash(material_slots_signature(EXPECTED_PROCESS_ZONES))
    original_segments_using_sample_material = [
        name
        for name in EXPECTED_PROCESS_ZONES
        for slot in bpy.data.objects[name].material_slots
        if slot.material and slot.material.name == SAMPLE_MATERIAL_NAME
    ]
    assert_row("sample_object_created", bpy.data.objects.get(SAMPLE_OBJECT_NAME) is not None, SAMPLE_OBJECT_NAME)
    assert_row("only_one_representative_segment_sampled", True, SOURCE_SEGMENT_NAME)
    assert_row("sensor_count_after_is_115", len(after_sensor_names) == EXPECTED_SENSOR_COUNT, len(after_sensor_names))
    assert_row("sensor_names_unchanged", original_sensor_names == after_sensor_names, {"before": len(original_sensor_names), "after": len(after_sensor_names)})
    assert_row(
        "body_temperature_sensor_count_after_is_80",
        len(after_body_sensor_names) == EXPECTED_BODY_SENSOR_COUNT,
        len(after_body_sensor_names),
    )
    assert_row("all_l7_l16_layers_present_after", all(exists_layer(name) for name in EXPECTED_LAYERS), EXPECTED_LAYERS)
    assert_row("five_process_zone_matrices_unchanged", before_matrix_hash == after_matrix_hash, {"before": before_matrix_hash, "after": after_matrix_hash})
    assert_row(
        "five_process_zone_material_slots_unchanged",
        before_material_hash == after_material_hash,
        {"before": before_material_hash, "after": after_material_hash},
    )
    assert_row("sample_material_not_assigned_to_original_process_zones", not original_segments_using_sample_material, original_segments_using_sample_material)
    assert_row("beauty_render_count_is_three", len(beauty_renders) == 3, list(beauty_renders))
    assert_row("channel_diagnostic_count_is_three", len(channel_renders) == 3, list(channel_renders))
    assert_row("grazing_light_closeup_rendered", Path(grazing_render["path"]).is_file() and Path(grazing_render["path"]).stat().st_size > 0, grazing_render)
    all_render_paths = [Path(row["path"]) for row in list(beauty_renders.values()) + list(channel_renders.values()) + [grazing_render]]
    assert_row("all_render_files_nonempty", all(path.is_file() and path.stat().st_size > 0 for path in all_render_paths), [path.as_posix() for path in all_render_paths])
    glb_exports = sorted(path.as_posix() for path in output_dir.rglob("*.glb"))
    assert_row("no_glb_export_created", not glb_exports, glb_exports)

    candidate_blend = output_dir / BLEND_NAME
    bpy.ops.wm.save_as_mainfile(filepath=candidate_blend.as_posix())
    blend1_files = sorted(path.as_posix() for path in output_dir.rglob("*.blend1"))
    assert_row("candidate_blend_saved", candidate_blend.is_file() and candidate_blend.stat().st_size > 0, candidate_blend.as_posix())
    assert_row("no_blend1_backup_created", not blend1_files, blend1_files)

    ok_count = sum(1 for row in assertions if row["ok"])
    fail_count = len(assertions) - ok_count
    report = {
        "schema_version": 1,
        "stage": STAGE,
        "status": STATUS,
        "approval": APPROVAL,
        "created_at": now_iso(),
        "input_checkpoint": {
            "path": input_blend_path.as_posix(),
            "project_relative_path": relative_display(input_blend_path),
            "sha256": sha256_file(input_blend_path),
            "expected_sha256": EXPECTED_INPUT_SHA256,
        },
        "blender": {
            "version": bpy.app.version_string,
            "background": bpy.app.background,
            "render_engine": bpy.context.scene.render.engine,
            "resolution": [int(args.width), int(args.height)],
            "save_version": bpy.context.preferences.filepaths.save_version,
        },
        "candidate": {
            "path": candidate_blend.as_posix(),
            "project_relative_path": relative_display(candidate_blend),
            "bytes": candidate_blend.stat().st_size,
            "sha256": sha256_file(candidate_blend),
        },
        "selected_scope": {
            "source_segment": SOURCE_SEGMENT_NAME,
            "sample_object": SAMPLE_OBJECT_NAME,
            "changed_dimension": "SURF-10 R2 single-surface material sample only",
            "original_furnace_segments_modified": False,
            "formal_glb_exported_or_replaced": False,
        },
        "renders": {
            "beauty_neutral_lookdev": beauty_renders,
            "channel_diagnostics": channel_renders,
            "direct_texture_diagnostics": texture_assets,
            "grazing_light_closeup": grazing_render,
        },
        "texture_statistics": texture_statistics,
        "material_manifest": relative_display(output_dir / "surf10_r2_material_manifest.json"),
        "assertions": assertions,
        "assertion_summary": {
            "total": len(assertions),
            "passed": ok_count,
            "failed": fail_count,
        },
        "events": events,
        "known_non_blocking_issues": [
            "The R2 sample is a clean-UV curved review panel derived from the approved shaft segment bounding box, not a baked or GLB-ready production material.",
            "Channel diagnostics are generated from procedural sample maps; glTF/Three.js handoff was intentionally not executed in SURF-10 R2.",
            "Visual approval is intentionally not granted by this execution agent; stop line is visual and spec review.",
        ],
    }
    summary = f"""# SURF-10 R2 阶段成果总结

## 目标

- 修复 R1 近景暗平、点蚀方块化、中远景平涂与重复/斜纹风险。
- 仅制作单表面材质样片，不展开全炉材质替换，不导出 GLB。

## 实际修改

- 新建 `{SAMPLE_OBJECT_NAME}` 清洁 UV 曲面样片，来源边界为 `{SOURCE_SEGMENT_NAME}`，未改原五个炉段材质槽。
- 生成深灰绿服役钢 BaseColor，叠加极弱暖锈、尘灰和重力水痕。
- 生成分层法线：低频橘皮 + 高频细砂，材质节点 normal strength 为 0.45。
- 样片面板加入 0.055m 顶点级低频 relief，仅用于近景可读性证据，不应用到原炉段。
- 点蚀改为软边非规则连续尺寸小坑，避免矩形、纯黑和短竖数字斑点。
- 使用非周期 domain warp 与非整数噪声尺度，降低远景重复相位与斜纹风险。

## 命令

```powershell
& "{DEFAULT_BLENDER}" --background "{DEFAULT_INPUT_BLEND}" --python "{SCRIPT_PATH}" -- --blender-child --output-dir "{output_dir}" --width {int(args.width)} --height {int(args.height)} --texture-resolution {resolution}
```

## 产物

- 候选 Blend：`{relative_display(candidate_blend)}`
- 机器报告：`{relative_display(output_dir / "surf10_r2_machine_report.json")}`
- 材质清单：`{relative_display(output_dir / "surf10_r2_material_manifest.json")}`
- 哈希清单：`{relative_display(output_dir / "artifact_sha256.json")}`
- 执行命令/日志：`{relative_display(output_dir / "surf10_r2_execution_command.json")}`、`{relative_display(output_dir / "runner.stdout.log")}`、`{relative_display(output_dir / "runner.stderr.log")}`
- 渲染：`renders/beauty/` near/mid/far，`renders/channels/` basecolor/roughness/normal，`renders/diagnostic/SURF10_R2_GRAZING_LIGHT_CLOSEUP.png`

## 断言

- 传感器数量：`{len(after_sensor_names)}`，BODY_TEMP：`{len(after_body_sensor_names)}`。
- L7-L16 和五个炉段均保留。
- 五个炉段矩阵与材质槽 hash 未变化。
- 未创建 GLB。
- `bpy.context.preferences.filepaths.save_version=0`，`.blend1` 检测结果：`{blend1_files}`。
- 像素统计：BaseColor luma `{texture_statistics["base_luma"]}`；Roughness `{texture_statistics["roughness"]}`；Normal XY `{texture_statistics["normal_xy_magnitude"]}`。
- 反重复统计：`{anti_repetition}`。

## 视觉边界

- 本阶段只给视觉/规格评审候选，不授权通过。
- 输出状态最高为 `{STATUS}`，approval 为 `{APPROVAL}`。

## 已知问题

- 尚未做全炉贴图烘焙、GLB 导出、glTF Validator 或 Three.js 复验。
- 样片是曲面 review panel，不能直接作为生产全炉材质结论。

## 下一停止线

- 停止在视觉质量审查与规格审查；若审查未通过，不进入下一阶段。
"""
    write_json(output_dir / "surf10_r2_material_manifest.json", material_manifest)
    write_json(output_dir / "surf10_r2_machine_report.json", report)
    write_text(output_dir / "SURF-10_R2_阶段成果总结.md", summary)
    return 0 if fail_count == 0 else 2


def main(argv: list[str] | None = None) -> int:
    raw_argv = list(sys.argv[1:] if argv is None else argv)
    if "--" in raw_argv:
        raw_argv = raw_argv[raw_argv.index("--") + 1 :]
    args = parse_args(raw_argv)
    if args.blender_child:
        try:
            return blender_child(args)
        except Exception:
            output_dir = args.output_dir.resolve()
            output_dir.mkdir(parents=True, exist_ok=True)
            (output_dir / "surf10_r2_child_exception.txt").write_text(traceback.format_exc(), encoding="utf-8")
            raise
    return run_parent(args)


if __name__ == "__main__":
    sys.exit(main())
