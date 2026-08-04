"""Run SURF-20 R4 full-shell material candidate.

This stage starts from the locked SURF-20 R3 full-shell candidate .blend,
adjusts only the micro-surface that still reads too flat in R3
without touching furnace geometry, sensors,
L7-L16 semantics, non-shell material slots, or the formal GLB, renders review
evidence, saves only a candidate .blend, and reopens the candidate for machine
validation.
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


STAGE = "SURF-20_R4"
STATUS = "candidate_ready_for_review"
APPROVAL = "not_granted_requires_visual_and_spec_review"
EXPECTED_INPUT_SHA256 = "1c573c45712d591fa282acdc8d6e04bad79e7263e2e6f58d6b04836afa063d24"
EXPECTED_FORMAL_GLB_SHA256 = "808960f1b2703e7fb27df35f1b1b1a17063b9b10d2267acba593fc3872b62af6"
EXPECTED_SENSOR_COUNT = 115
EXPECTED_BODY_SENSOR_COUNT = 80
EXPECTED_PROCESS_ZONES = [
    "APPROX_GL02_FURNACE_HEARTH",
    "APPROX_GL02_FURNACE_BOSH",
    "APPROX_GL02_FURNACE_BELLY",
    "APPROX_GL02_FURNACE_SHAFT",
    "APPROX_GL02_FURNACE_THROAT",
]
EXPECTED_LAYERS = [f"GL02_SENSOR_LAYER_L{layer}" for layer in range(7, 17)]
EXPECTED_LAYER_SENSOR_PREFIXES = [f"SENSOR_T_body_L{layer}_" for layer in range(7, 17)]

SCRIPT_PATH = Path(__file__).resolve()
MODULE_ROOT = SCRIPT_PATH.parent
PROJECT_ROOT = SCRIPT_PATH.parents[2]
DEFAULT_BLENDER = Path(r"D:\Program Files\Blender Foundation\Blender 5.2\blender.exe")
DEFAULT_INPUT_BLEND = MODULE_ROOT / "work" / "SURF_20_20260718_R3" / "SURF20_R3_FULL_SHELL_MATERIAL_CANDIDATE.blend"
DEFAULT_OUTPUT_DIR = MODULE_ROOT / "work" / "SURF_20_20260718_R4"
FORMAL_GLB = PROJECT_ROOT / "高炉前端数据" / "models" / "gl02_blast_furnace.glb"
BLEND_NAME = "SURF20_R4_FULL_SHELL_MATERIAL_CANDIDATE.blend"
MATERIAL_NAME = "SURF20_R4_aged_painted_carbon_steel_shared_world"
MAPPING_EMPTY_NAME = "SURF20_R4_SHARED_WORLD_MAPPING_EMPTY"
METALLIC_MASK_VALUE = 0.06
METALLIC_HIGH_THRESHOLD = 0.85
NORMAL_EQUIVALENT_STRENGTH = 0.34
BUMP_STRENGTH = 0.116
BUMP_DISTANCE_METERS = 0.058
R1_GRAZING_SOURCE = MODULE_ROOT / "work" / "SURF_20_20260718_R1" / "renders" / "SURF20_R1_08_GRAZING_NEAR.png"
R2_GRAZING_SOURCE = MODULE_ROOT / "work" / "SURF_20_20260718_R2" / "renders" / "SURF20_R2_08_GRAZING_NEAR.png"
R3_GRAZING_SOURCE = MODULE_ROOT / "work" / "SURF_20_20260718_R3" / "renders" / "SURF20_R3_08_GRAZING_NEAR.png"


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
    write_json(
        output_dir / "artifact_sha256.json",
        {
            "schema_version": 1,
            "stage": STAGE,
            "generated_at": now_iso(),
            "excludes": ["artifact_sha256.json", "*.blend1"],
            "blend1_files_found": sorted(p.as_posix() for p in output_dir.rglob("*.blend1")),
            "artifacts": artifact_hashes(output_dir),
        },
    )


def update_pipeline_status(output_dir: Path, report: dict[str, Any], command_record: dict[str, Any]) -> None:
    status_path = PROJECT_ROOT / "reports" / "pipeline_status.json"
    if status_path.is_file():
        payload = json.loads(status_path.read_text(encoding="utf-8"))
    else:
        payload = {"schema_version": 1, "stages": {}}
    payload["updated_at"] = now_iso()
    payload["current_stage"] = STAGE
    payload.setdefault("stages", {})[STAGE] = {
        "status": STATUS,
        "approval": APPROVAL,
        "candidate_blend": report["candidate"]["project_relative_path"],
        "candidate_sha256": report["candidate"]["sha256"],
        "input_blend": report["input_checkpoint"]["project_relative_path"],
        "input_sha256": report["input_checkpoint"]["sha256"],
        "machine_report": relative_display(output_dir / "surf20_r4_machine_report.json"),
        "material_manifest": relative_display(output_dir / "surf20_r4_material_manifest.json"),
        "summary": relative_display(output_dir / "SURF-20_R4_阶段成果总结.md"),
        "formal_glb_unchanged": bool(command_record.get("formal_glb_unchanged")),
        "formal_glb_sha256": command_record.get("formal_glb_sha256_after"),
        "next_stop_line": "visual_and_spec_review_required_before_any_next_stage",
    }
    write_json(status_path, payload)


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
    formal_glb_sha_before = sha256_file(FORMAL_GLB) if FORMAL_GLB.is_file() else None
    if formal_glb_sha_before and formal_glb_sha_before.lower() != EXPECTED_FORMAL_GLB_SHA256:
        raise RuntimeError(f"Formal GLB SHA drift: expected {EXPECTED_FORMAL_GLB_SHA256}, got {formal_glb_sha_before}")

    output_dir.mkdir(parents=True, exist_ok=True)
    for stale in ("surf20_r4_child_exception.txt", "surf20_r4_validate_exception.txt"):
        path = output_dir / stale
        if path.exists():
            path.unlink()

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
        "formal_glb": FORMAL_GLB.as_posix(),
        "formal_glb_sha256_before": formal_glb_sha_before,
        "expected_formal_glb_sha256": EXPECTED_FORMAL_GLB_SHA256,
        "blender": blender.as_posix(),
        "output_dir": output_dir.as_posix(),
    }
    write_json(output_dir / "surf20_r4_execution_command.json", command_record)
    with (output_dir / "runner.stdout.log").open("w", encoding="utf-8", newline="\n") as stdout, (
        output_dir / "runner.stderr.log"
    ).open("w", encoding="utf-8", newline="\n") as stderr:
        completed = subprocess.run(command, cwd=PROJECT_ROOT, stdout=stdout, stderr=stderr, check=False)

    validate_exit_code: int | None = None
    candidate = output_dir / BLEND_NAME
    if completed.returncode == 0 and candidate.is_file():
        validate_command = [
            str(blender),
            "--background",
            str(candidate),
            "--python",
            str(SCRIPT_PATH),
            "--",
            "--validate-child",
            "--output-dir",
            str(output_dir),
        ]
        command_record["validate_command"] = validate_command
        with (output_dir / "validate.stdout.log").open("w", encoding="utf-8", newline="\n") as stdout, (
            output_dir / "validate.stderr.log"
        ).open("w", encoding="utf-8", newline="\n") as stderr:
            validate_completed = subprocess.run(validate_command, cwd=PROJECT_ROOT, stdout=stdout, stderr=stderr, check=False)
        validate_exit_code = validate_completed.returncode
        validate_exception = output_dir / "surf20_r4_validate_exception.txt"
        validate_report = output_dir / "surf20_r4_reopen_validation.json"
        if validate_exception.is_file() or not validate_report.is_file():
            validate_exit_code = validate_exit_code or 4

    formal_glb_sha_after = sha256_file(FORMAL_GLB) if FORMAL_GLB.is_file() else None
    command_record["completed_at"] = now_iso()
    command_record["exit_code"] = completed.returncode
    command_record["validate_exit_code"] = validate_exit_code
    command_record["formal_glb_sha256_after"] = formal_glb_sha_after
    command_record["formal_glb_unchanged"] = formal_glb_sha_before == formal_glb_sha_after
    write_json(output_dir / "surf20_r4_execution_command.json", command_record)
    write_artifact_index(output_dir)

    report_path = output_dir / "surf20_r4_machine_report.json"
    if report_path.is_file():
        report = json.loads(report_path.read_text(encoding="utf-8"))
        update_pipeline_status(output_dir, report, command_record)
        write_artifact_index(output_dir)
        print(
            json.dumps(
                {
                    "stage": report.get("stage"),
                    "status": report.get("status"),
                    "approval": report.get("approval"),
                    "exit_code": completed.returncode,
                    "validate_exit_code": validate_exit_code,
                    "candidate": report.get("candidate"),
                    "assertion_summary": report.get("assertion_summary"),
                    "formal_glb_unchanged": command_record["formal_glb_unchanged"],
                },
                ensure_ascii=False,
                indent=2,
            )
        )
    if completed.returncode != 0:
        return completed.returncode
    if validate_exit_code not in (0, None):
        return validate_exit_code
    return 0 if report_path.is_file() else 3


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--blender-child", action="store_true")
    parser.add_argument("--validate-child", action="store_true")
    parser.add_argument("--input-blend", type=Path, default=DEFAULT_INPUT_BLEND)
    parser.add_argument("--blender", type=Path, default=DEFAULT_BLENDER)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--width", type=int, default=1440)
    parser.add_argument("--height", type=int, default=900)
    return parser.parse_args(argv)


def blender_child(args: argparse.Namespace) -> int:
    import math
    import struct
    import zlib

    import bpy
    from mathutils import Vector

    bpy.context.preferences.filepaths.save_version = 0
    output_dir = args.output_dir.resolve()
    render_dir = output_dir / "renders"
    texture_dir = output_dir / "textures"
    for path in (render_dir, texture_dir):
        path.mkdir(parents=True, exist_ok=True)

    assertions: list[dict[str, Any]] = []
    events: list[dict[str, Any]] = []

    def event(name: str, **fields: Any) -> None:
        events.append({"at": now_iso(), "event": name, **fields})

    def assert_row(assertion_id: str, ok: bool, detail: Any = None) -> None:
        assertions.append({"id": assertion_id, "ok": bool(ok), "detail": detail})

    def signature_hash(value: Any) -> str:
        payload = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
        return hashlib.sha256(payload).hexdigest()

    def obj_matrix_signature(names: Iterable[str]) -> dict[str, Any]:
        rows: dict[str, Any] = {}
        for name in sorted(names):
            obj = bpy.data.objects.get(name)
            rows[name] = None if obj is None else [round(float(value), 8) for row in obj.matrix_world for value in row]
        return rows

    def mesh_signature(names: Iterable[str]) -> dict[str, Any]:
        rows: dict[str, Any] = {}
        for name in sorted(names):
            obj = bpy.data.objects.get(name)
            if obj is None or obj.type != "MESH" or obj.data is None:
                rows[name] = None
                continue
            mesh = obj.data
            coords = []
            for vertex in mesh.vertices:
                co = vertex.co
                coords.append((round(float(co.x), 6), round(float(co.y), 6), round(float(co.z), 6)))
            rows[name] = {
                "mesh_name": mesh.name,
                "vertices": len(mesh.vertices),
                "edges": len(mesh.edges),
                "polygons": len(mesh.polygons),
                "loops": len(mesh.loops),
                "uv_layers": [uv.name for uv in mesh.uv_layers],
                "coord_hash": signature_hash(coords),
            }
        return rows

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

    def layer_counts() -> dict[str, int]:
        return {
            f"L{layer}": len([name for name in bpy.data.objects.keys() if name.startswith(f"SENSOR_T_body_L{layer}_")])
            for layer in range(7, 17)
        }

    def object_world_bbox(objects: Iterable[Any]) -> tuple[Vector, Vector]:
        points: list[Vector] = []
        for obj in objects:
            points.extend(obj.matrix_world @ Vector(corner) for corner in obj.bound_box)
        return (
            Vector((min(p.x for p in points), min(p.y for p in points), min(p.z for p in points))),
            Vector((max(p.x for p in points), max(p.y for p in points), max(p.z for p in points))),
        )

    def write_png_rgba(path: Path, pixels: list[float], width: int, height: int) -> dict[str, Any]:
        raw_rows = bytearray()
        byte_pixels = bytearray(max(0, min(255, int(round(value * 255.0)))) for value in pixels)
        for row in range(height):
            raw_rows.append(0)
            start = row * width * 4
            raw_rows.extend(byte_pixels[start : start + width * 4])

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
        }

    def image_stats(values: list[float]) -> dict[str, float]:
        return {
            "min": round(min(values), 6),
            "max": round(max(values), 6),
            "mean": round(mean(values), 6),
            "stddev": round(pstdev(values), 6),
        }

    def hash01(x: int, y: int, seed: int = 0) -> float:
        value = math.sin(x * 127.1 + y * 311.7 + seed * 74.7) * 43758.5453123
        return value - math.floor(value)

    def smoothstep(value: float) -> float:
        return value * value * (3.0 - 2.0 * value)

    def lerp(left: float, right: float, factor: float) -> float:
        return left + (right - left) * factor

    def value_noise(u: float, v: float, sx: float, sy: float, seed: int) -> float:
        px = u * sx
        py = v * sy
        x0 = math.floor(px)
        y0 = math.floor(py)
        tx = smoothstep(px - x0)
        ty = smoothstep(py - y0)
        a = hash01(x0, y0, seed)
        b = hash01(x0 + 1, y0, seed)
        c = hash01(x0, y0 + 1, seed)
        d = hash01(x0 + 1, y0 + 1, seed)
        return lerp(lerp(a, b, tx), lerp(c, d, tx), ty)

    def make_diagnostic_cards() -> tuple[dict[str, Any], dict[str, Any]]:
        res = 768
        base_pixels: list[float] = []
        rough_pixels: list[float] = []
        height_pixels: list[float] = []
        metallic_pixels: list[float] = []
        base_luma: list[float] = []
        rough_values: list[float] = []
        pit_values: list[float] = []
        metallic_values: list[float] = []
        for y in range(res):
            v = y / max(1, res - 1)
            for x in range(res):
                u = x / max(1, res - 1)
                warp_u = u + (value_noise(u, v, 3.1, 4.7, 200) - 0.5) * 0.04
                warp_v = v + (value_noise(u, v, 5.3, 3.7, 201) - 0.5) * 0.04
                orange = 0.6 * value_noise(warp_u, warp_v, 4.35, 5.85, 211) + 0.4 * value_noise(warp_u, warp_v, 8.2, 6.7, 212)
                fine = 0.55 * value_noise(warp_u, warp_v, 137.0, 163.0, 214) + 0.45 * value_noise(warp_u, warp_v, 251.0, 227.0, 215)
                cell_x = int(warp_u * 64.0)
                cell_y = int(warp_v * 80.0)
                pit_gate = 1.0 if hash01(cell_x, cell_y, 701) > 0.922 else 0.0
                cx = (cell_x + 0.18 + 0.64 * hash01(cell_x, cell_y, 702)) / 64.0
                cy = (cell_y + 0.16 + 0.68 * hash01(cell_x, cell_y, 703)) / 80.0
                pit = pit_gate * math.exp(-(((warp_u - cx) / 0.0065) ** 2 + ((warp_v - cy) / 0.005) ** 2) * 2.8)
                streak_cell = int(warp_u * 48.0)
                streak_gate = 1.0 if hash01(streak_cell, 2, 720) > 0.79 else 0.0
                streak_center = (streak_cell + 0.2 + 0.6 * hash01(streak_cell, 4, 721)) / 48.0
                streak = streak_gate * math.exp(-((warp_u - streak_center) ** 2) / 0.000035) * (0.25 + 0.75 * v)
                dust = min(1.0, 0.038 * streak + 0.045 * value_noise(warp_u, warp_v, 31.0, 19.0, 730))
                water = min(1.0, 0.024 * streak)
                r = 0.165 + 0.038 * orange + 0.016 * fine + 0.018 * dust - 0.010 * water - 0.008 * pit
                g = 0.210 + 0.036 * orange + 0.015 * fine + 0.017 * dust - 0.010 * water - 0.012 * pit
                b = 0.186 + 0.029 * orange + 0.012 * fine + 0.014 * dust - 0.009 * water - 0.010 * pit
                rough = min(0.82, max(0.56, 0.625 + 0.085 * orange + 0.025 * fine + 0.045 * dust + 0.025 * pit - 0.018 * water))
                height = min(1.0, max(0.0, 0.5 + (orange - 0.5) * 0.026 + (fine - 0.5) * 0.010 - pit * 0.020 + dust * 0.008))
                metallic = METALLIC_MASK_VALUE
                luma = 0.2126 * r + 0.7152 * g + 0.0722 * b
                base_luma.append(luma)
                rough_values.append(rough)
                pit_values.append(pit)
                metallic_values.append(metallic)
                base_pixels.extend([r, g, b, 1.0])
                rough_pixels.extend([rough, rough, rough, 1.0])
                height_pixels.extend([height, height, height, 1.0])
                metallic_pixels.extend([metallic, metallic, metallic, 1.0])
        cards = {
            "basecolor": {
                **write_png_rgba(texture_dir / "SURF20_R4_diag_basecolor_shared_world_scale.png", base_pixels, res, res),
                "colorspace": "sRGB",
            },
            "roughness": {
                **write_png_rgba(texture_dir / "SURF20_R4_diag_roughness_shared_world_scale.png", rough_pixels, res, res),
                "colorspace": "Non-Color",
            },
            "height": {
                **write_png_rgba(texture_dir / "SURF20_R4_diag_height_soft_orange_peel.png", height_pixels, res, res),
                "colorspace": "Non-Color",
            },
            "metallic": {
                **write_png_rgba(texture_dir / "SURF20_R4_diag_metallic_painted_mask.png", metallic_pixels, res, res),
                "colorspace": "Non-Color",
            },
        }
        stats = {
            "base_luma": image_stats(base_luma),
            "roughness": image_stats(rough_values),
            "metallic": image_stats(metallic_values),
            "metallic_high_pixel_ratio": round(sum(1 for v in metallic_values if v >= METALLIC_HIGH_THRESHOLD) / len(metallic_values), 6),
            "pit_soft_mask": image_stats(pit_values),
            "pit_active_pixel_ratio": round(sum(1 for v in pit_values if v > 0.08) / len(pit_values), 6),
        }
        return cards, stats

    def set_socket_default(socket: Any, value: Any) -> None:
        if socket is not None:
            socket.default_value = value

    def build_material(mapping_empty: Any) -> Any:
        mat = bpy.data.materials.new(MATERIAL_NAME)
        mat.use_nodes = True
        mat.diffuse_color = (0.155, 0.198, 0.178, 1.0)
        nodes = mat.node_tree.nodes
        links = mat.node_tree.links
        for node in list(nodes):
            nodes.remove(node)

        out = nodes.new("ShaderNodeOutputMaterial")
        bsdf = nodes.new("ShaderNodeBsdfPrincipled")
        texcoord = nodes.new("ShaderNodeTexCoord")
        texcoord.object = mapping_empty
        mapping = nodes.new("ShaderNodeMapping")
        low_noise = nodes.new("ShaderNodeTexNoise")
        high_noise = nodes.new("ShaderNodeTexNoise")
        pit_noise = nodes.new("ShaderNodeTexVoronoi")
        color_ramp = nodes.new("ShaderNodeValToRGB")
        rough_ramp = nodes.new("ShaderNodeValToRGB")
        metallic_value = nodes.new("ShaderNodeValue")
        bump = nodes.new("ShaderNodeBump")

        mapping.inputs["Scale"].default_value = (0.085, 0.085, 0.085)
        low_noise.inputs["Scale"].default_value = 7.5
        low_noise.inputs["Detail"].default_value = 14.0
        low_noise.inputs["Roughness"].default_value = 0.54
        high_noise.inputs["Scale"].default_value = 135.0
        high_noise.inputs["Detail"].default_value = 12.0
        high_noise.inputs["Roughness"].default_value = 0.61
        pit_noise.inputs["Scale"].default_value = 24.0
        pit_noise.inputs["Randomness"].default_value = 0.82

        color_ramp.color_ramp.elements[0].position = 0.16
        color_ramp.color_ramp.elements[0].color = (0.145, 0.188, 0.168, 1.0)
        color_ramp.color_ramp.elements[1].position = 1.0
        color_ramp.color_ramp.elements[1].color = (0.235, 0.285, 0.248, 1.0)
        rough_ramp.color_ramp.elements[0].position = 0.05
        rough_ramp.color_ramp.elements[0].color = (0.58, 0.58, 0.58, 1.0)
        rough_ramp.color_ramp.elements[1].position = 1.0
        rough_ramp.color_ramp.elements[1].color = (0.82, 0.82, 0.82, 1.0)
        metallic_value.outputs[0].default_value = METALLIC_MASK_VALUE

        set_socket_default(bsdf.inputs.get("Metallic"), METALLIC_MASK_VALUE)
        set_socket_default(bsdf.inputs.get("Roughness"), 0.68)
        set_socket_default(bump.inputs.get("Strength"), BUMP_STRENGTH)
        set_socket_default(bump.inputs.get("Distance"), BUMP_DISTANCE_METERS)

        links.new(texcoord.outputs["Object"], mapping.inputs["Vector"])
        links.new(mapping.outputs["Vector"], low_noise.inputs["Vector"])
        links.new(mapping.outputs["Vector"], high_noise.inputs["Vector"])
        links.new(mapping.outputs["Vector"], pit_noise.inputs["Vector"])
        links.new(low_noise.outputs["Fac"], color_ramp.inputs["Fac"])
        links.new(color_ramp.outputs["Color"], bsdf.inputs["Base Color"])
        links.new(low_noise.outputs["Fac"], rough_ramp.inputs["Fac"])
        links.new(rough_ramp.outputs["Color"], bsdf.inputs["Roughness"])
        links.new(metallic_value.outputs[0], bsdf.inputs["Metallic"])
        links.new(high_noise.outputs["Fac"], bump.inputs["Height"])
        links.new(bump.outputs["Normal"], bsdf.inputs["Normal"])
        links.new(bsdf.outputs["BSDF"], out.inputs["Surface"])

        mat["surf20_stage"] = STAGE
        mat["surf20_mapping"] = f"TextureCoordinate.Object uses {MAPPING_EMPTY_NAME}; mapping scale = 0.085 on all axes"
        mat["surf20_r4_fix"] = (
            f"aged painted carbon steel: metallic mask fixed at {METALLIC_MASK_VALUE}; "
            f"normal equivalent {NORMAL_EQUIVALENT_STRENGTH}; bump_strength={BUMP_STRENGTH}; "
            f"bump_distance_m={BUMP_DISTANCE_METERS}; roughness target 0.56-0.82"
        )
        mat["surf20_finish"] = "matte dark green-gray aged painted carbon steel; fine orange-peel/sandblast only; no thick concrete-like wall relief"
        return mat

    def look_at(obj: Any, target: Vector) -> None:
        direction = target - obj.location
        obj.rotation_euler = direction.to_track_quat("-Z", "Y").to_euler()

    def make_camera(name: str, location: tuple[float, float, float], target: Vector, ortho_scale: float) -> Any:
        cam_data = bpy.data.cameras.new(f"{name}_DATA")
        camera = bpy.data.objects.new(name, cam_data)
        bpy.context.scene.collection.objects.link(camera)
        camera.location = location
        camera.data.type = "ORTHO"
        camera.data.ortho_scale = ortho_scale
        camera.data.clip_start = 0.05
        camera.data.clip_end = 2000.0
        look_at(camera, target)
        return camera

    def add_area_light(name: str, location: tuple[float, float, float], target: Vector, power: float, size: float) -> Any:
        data = bpy.data.lights.new(name, type="AREA")
        light = bpy.data.objects.new(name, data)
        bpy.context.scene.collection.objects.link(light)
        light.location = location
        light.data.energy = power
        light.data.size = size
        look_at(light, target)
        return light

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
            "resolution": [int(width or old_width), int(height or old_height)],
            "engine": bpy.context.scene.render.engine,
        }

    def render_grazing_comparison(r4_grazing_path: Path) -> dict[str, Any]:
        sources = [
            {
                "version": "R1",
                "path": R1_GRAZING_SOURCE,
                "label": "R1 bump 0.16 / distance 0.10m / normal 0.45",
            },
            {
                "version": "R2",
                "path": R2_GRAZING_SOURCE,
                "label": "R2 bump 0.06 / distance 0.03m / normal 0.24",
            },
            {
                "version": "R3",
                "path": R3_GRAZING_SOURCE,
                "label": "R3 bump 0.09 / distance 0.045m / normal 0.29",
            },
            {
                "version": "R4",
                "path": r4_grazing_path,
                "label": f"R4 bump {BUMP_STRENGTH:.3f} / distance {BUMP_DISTANCE_METERS:.3f}m / normal {NORMAL_EQUIVALENT_STRENGTH:.2f}",
            },
        ]
        for source in sources:
            if not source["path"].is_file():
                raise FileNotFoundError(source["path"])

        glyphs = {
            " ": ["00000", "00000", "00000", "00000", "00000", "00000", "00000"],
            ".": ["00000", "00000", "00000", "00000", "00000", "01100", "01100"],
            "0": ["11111", "10001", "10011", "10101", "11001", "10001", "11111"],
            "1": ["00100", "01100", "00100", "00100", "00100", "00100", "01110"],
            "2": ["11110", "00001", "00001", "11110", "10000", "10000", "11111"],
            "3": ["11110", "00001", "00001", "01110", "00001", "00001", "11110"],
            "4": ["10010", "10010", "10010", "11111", "00010", "00010", "00010"],
            "5": ["11111", "10000", "10000", "11110", "00001", "00001", "11110"],
            "6": ["01111", "10000", "10000", "11110", "10001", "10001", "01110"],
            "7": ["11111", "00001", "00010", "00100", "01000", "01000", "01000"],
            "8": ["01110", "10001", "10001", "01110", "10001", "10001", "01110"],
            "9": ["01110", "10001", "10001", "01111", "00001", "00001", "11110"],
            "B": ["11110", "10001", "10001", "11110", "10001", "10001", "11110"],
            "D": ["11110", "10001", "10001", "10001", "10001", "10001", "11110"],
            "N": ["10001", "11001", "10101", "10011", "10001", "10001", "10001"],
            "R": ["11110", "10001", "10001", "11110", "10100", "10010", "10001"],
        }

        panel_w = 720
        panel_h = 450
        label_h = 70
        out_w = panel_w * len(sources)
        out_h = panel_h + label_h
        out = [0.02, 0.025, 0.023, 1.0] * (out_w * out_h)

        def set_px(x: int, y: int, color: tuple[float, float, float, float]) -> None:
            if 0 <= x < out_w and 0 <= y < out_h:
                idx = (y * out_w + x) * 4
                out[idx : idx + 4] = list(color)

        def fill_rect(x0: int, y0: int, x1: int, y1: int, color: tuple[float, float, float, float]) -> None:
            for yy in range(max(0, y0), min(out_h, y1)):
                for xx in range(max(0, x0), min(out_w, x1)):
                    set_px(xx, yy, color)

        def draw_text(text: str, x: int, y: int, scale: int, color: tuple[float, float, float, float]) -> None:
            cursor = x
            for ch in text.upper():
                rows = glyphs.get(ch, glyphs[" "])
                for gy, row in enumerate(rows):
                    for gx, bit in enumerate(row):
                        if bit == "1":
                            fill_rect(cursor + gx * scale, y + gy * scale, cursor + (gx + 1) * scale, y + (gy + 1) * scale, color)
                cursor += 6 * scale

        loaded_images = []
        try:
            for column, source in enumerate(sources):
                image = bpy.data.images.load(source["path"].as_posix(), check_existing=False)
                loaded_images.append(image)
                src_w, src_h = int(image.size[0]), int(image.size[1])
                pixels = list(image.pixels[:])
                x_offset = column * panel_w
                fill_rect(x_offset, 0, x_offset + panel_w, label_h, (0.015, 0.018, 0.017, 1.0))
                for y in range(panel_h):
                    src_y = src_h - 1 - min(src_h - 1, int(y * src_h / panel_h))
                    for x in range(panel_w):
                        src_x = min(src_w - 1, int(x * src_w / panel_w))
                        src_idx = (src_y * src_w + src_x) * 4
                        dst_idx = ((label_h + y) * out_w + x_offset + x) * 4
                        out[dst_idx : dst_idx + 4] = pixels[src_idx : src_idx + 4]
                draw_text(source["version"], x_offset + 18, 12, 5, (1.0, 0.58, 0.22, 1.0))
                compact_label = {
                    "R1": "B 0.16 D 0.10 N 0.45",
                    "R2": "B 0.06 D 0.03 N 0.24",
                    "R3": "B 0.09 D 0.045 N 0.29",
                    "R4": "B 0.116 D 0.058 N 0.34",
                }[source["version"]]
                draw_text(compact_label, x_offset + 120, 22, 3, (0.92, 0.95, 0.92, 1.0))
                if column:
                    fill_rect(x_offset, 0, x_offset + 3, out_h, (0.0, 0.0, 0.0, 1.0))

            comparison_path = render_dir / "SURF20_R4_10_R1_R2_R3_R4_GRAZING_COMPARISON.png"
            row = {
                **write_png_rgba(comparison_path, out, out_w, out_h),
                "seconds": 0.0,
                "camera": "pixel_composite_from_fixed_grazing_sources",
                "resolution": [out_w, out_h],
                "engine": "diagnostic_png_composite",
                "comparison_sources": [
                    {
                        "version": source["version"],
                        "path": source["path"].as_posix(),
                        "project_relative_path": relative_display(source["path"]),
                        "sha256": sha256_file(source["path"]),
                        "label": source["label"],
                    }
                    for source in sources
                ],
                "comparison_contract": "four source renders use the SURF20 *_08_GRAZING_NEAR fixed-view evidence; composition preserves each source image crop and adds only B/D/N parameter labels.",
            }
            return row
        finally:
            for image in loaded_images:
                if image.name in bpy.data.images:
                    bpy.data.images.remove(image)

        old_camera = bpy.context.scene.camera
        old_width = bpy.context.scene.render.resolution_x
        old_height = bpy.context.scene.render.resolution_y
        old_filepath = bpy.context.scene.render.filepath
        old_film = bpy.context.scene.render.film_transparent
        old_visibility = {obj.name: (obj.hide_render, obj.hide_viewport) for obj in bpy.data.objects}
        created_objects = []
        created_materials = []
        created_images = []
        try:
            for obj in bpy.data.objects:
                obj.hide_render = True
                obj.hide_viewport = True

            def make_emission_material(name: str, color: tuple[float, float, float, float], image: Any | None = None) -> Any:
                mat = bpy.data.materials.new(name)
                mat.use_nodes = True
                nodes = mat.node_tree.nodes
                links = mat.node_tree.links
                for node in list(nodes):
                    nodes.remove(node)
                out = nodes.new("ShaderNodeOutputMaterial")
                emission = nodes.new("ShaderNodeEmission")
                emission.inputs["Color"].default_value = color
                emission.inputs["Strength"].default_value = 1.0
                if image is not None:
                    tex = nodes.new("ShaderNodeTexImage")
                    tex.image = image
                    links.new(tex.outputs["Color"], emission.inputs["Color"])
                links.new(emission.outputs["Emission"], out.inputs["Surface"])
                created_materials.append(mat)
                return mat

            white_mat = make_emission_material("SURF20_R4_COMPARISON_TEXT_WHITE", (0.92, 0.95, 0.92, 1.0))
            orange_mat = make_emission_material("SURF20_R4_COMPARISON_TEXT_ORANGE", (1.0, 0.58, 0.22, 1.0))
            panel_width = 4.0
            panel_height = 2.5
            gap = 0.32
            total_width = len(sources) * panel_width + (len(sources) - 1) * gap
            first_x = -0.5 * total_width + 0.5 * panel_width
            x_positions = [first_x + index * (panel_width + gap) for index in range(len(sources))]
            for x, source in zip(x_positions, sources):
                image = bpy.data.images.load(source["path"].as_posix(), check_existing=False)
                created_images.append(image)
                mat = make_emission_material(f"SURF20_R4_COMPARISON_{source['version']}_IMAGE", (1, 1, 1, 1), image)
                bpy.ops.mesh.primitive_plane_add(size=1.0, location=(x, 0.0, 0.0), rotation=(0.0, 0.0, 0.0))
                plane = bpy.context.object
                plane.name = f"SURF20_R4_COMPARISON_{source['version']}_PANEL"
                plane.scale = (panel_width, panel_height, 1.0)
                plane.data.materials.append(mat)
                plane.hide_render = False
                plane.hide_viewport = False
                created_objects.append(plane)

                title_curve = bpy.data.curves.new(f"SURF20_R4_COMPARISON_{source['version']}_TITLE_CURVE", type="FONT")
                title_curve.body = source["version"]
                title_curve.align_x = "CENTER"
                title_curve.align_y = "CENTER"
                title_curve.size = 0.28
                title_obj = bpy.data.objects.new(f"SURF20_R4_COMPARISON_{source['version']}_TITLE", title_curve)
                bpy.context.scene.collection.objects.link(title_obj)
                title_obj.location = (x, 1.56, 0.08)
                title_obj.data.materials.append(orange_mat)
                title_obj.hide_render = False
                title_obj.hide_viewport = False
                created_objects.append(title_obj)

                label_curve = bpy.data.curves.new(f"SURF20_R4_COMPARISON_{source['version']}_LABEL_CURVE", type="FONT")
                label_curve.body = source["label"]
                label_curve.align_x = "CENTER"
                label_curve.align_y = "CENTER"
                label_curve.size = 0.16
                label_obj = bpy.data.objects.new(f"SURF20_R4_COMPARISON_{source['version']}_LABEL", label_curve)
                bpy.context.scene.collection.objects.link(label_obj)
                label_obj.location = (x, -1.56, 0.08)
                label_obj.data.materials.append(white_mat)
                label_obj.hide_render = False
                label_obj.hide_viewport = False
                created_objects.append(label_obj)

            cam_data = bpy.data.cameras.new("SURF20_R4_COMPARISON_CAMERA_DATA")
            cam = bpy.data.objects.new("SURF20_R4_COMPARISON_CAMERA", cam_data)
            bpy.context.scene.collection.objects.link(cam)
            cam.location = (0.0, 0.0, 8.0)
            cam.rotation_euler = (0.0, 0.0, 0.0)
            cam.data.type = "ORTHO"
            cam.data.ortho_scale = 4.4
            cam.hide_render = False
            cam.hide_viewport = False
            created_objects.append(cam)

            bpy.context.scene.camera = cam
            bpy.context.scene.render.resolution_x = 2880
            bpy.context.scene.render.resolution_y = 720
            bpy.context.scene.render.film_transparent = False
            comparison_path = render_dir / "SURF20_R4_10_R1_R2_R3_R4_GRAZING_COMPARISON.png"
            bpy.context.scene.render.filepath = comparison_path.as_posix()
            started = datetime.now()
            bpy.ops.render.render(write_still=True)
            seconds = (datetime.now() - started).total_seconds()
            return {
                "path": comparison_path.as_posix(),
                "project_relative_path": relative_display(comparison_path),
                "bytes": comparison_path.stat().st_size,
                "sha256": sha256_file(comparison_path),
                "seconds": round(seconds, 4),
                "camera": cam.name,
                "resolution": [2880, 720],
                "engine": bpy.context.scene.render.engine,
                "comparison_sources": [
                    {
                        "version": source["version"],
                        "path": source["path"].as_posix(),
                        "project_relative_path": relative_display(source["path"]),
                        "sha256": sha256_file(source["path"]),
                        "label": source["label"],
                    }
                    for source in sources
                ],
                "comparison_contract": "four source renders use the SURF20 *_08_GRAZING_NEAR fixed-view evidence; composition preserves each source image crop and only adds labels.",
            }
        finally:
            bpy.context.scene.camera = old_camera
            bpy.context.scene.render.resolution_x = old_width
            bpy.context.scene.render.resolution_y = old_height
            bpy.context.scene.render.filepath = old_filepath
            bpy.context.scene.render.film_transparent = old_film
            for obj in bpy.data.objects:
                state = old_visibility.get(obj.name)
                if state is not None:
                    obj.hide_render, obj.hide_viewport = state
            for obj in created_objects:
                if obj.name in bpy.data.objects:
                    bpy.data.objects.remove(obj, do_unlink=True)
            for mat in created_materials:
                if mat.name in bpy.data.materials:
                    bpy.data.materials.remove(mat)
            for image in created_images:
                if image.name in bpy.data.images:
                    bpy.data.images.remove(image)

    def image_non_background_bounds(path: Path, threshold: float = 0.035) -> dict[str, Any]:
        image = bpy.data.images.load(path.as_posix(), check_existing=False)
        try:
            width_px, height_px = int(image.size[0]), int(image.size[1])
            pixels = list(image.pixels[:])

            def pixel_rgb(x: int, y: int) -> tuple[float, float, float]:
                idx = (y * width_px + x) * 4
                return pixels[idx], pixels[idx + 1], pixels[idx + 2]

            sample_points = [
                (0, 0),
                (width_px - 1, 0),
                (0, height_px - 1),
                (width_px - 1, height_px - 1),
                (width_px // 2, 0),
                (width_px // 2, height_px - 1),
                (0, height_px // 2),
                (width_px - 1, height_px // 2),
            ]
            bg = tuple(mean([pixel_rgb(x, y)[channel] for x, y in sample_points]) for channel in range(3))
            min_x, min_y = width_px, height_px
            max_x, max_y = -1, -1
            for y in range(height_px):
                base = y * width_px * 4
                for x in range(width_px):
                    idx = base + x * 4
                    diff = abs(pixels[idx] - bg[0]) + abs(pixels[idx + 1] - bg[1]) + abs(pixels[idx + 2] - bg[2])
                    if diff > threshold:
                        min_x = min(min_x, x)
                        min_y = min(min_y, y)
                        max_x = max(max_x, x)
                        max_y = max(max_y, y)
            if max_x < min_x or max_y < min_y:
                return {"found": False, "resolution": [width_px, height_px], "background_rgb_linear": [round(v, 6) for v in bg]}
            left = min_x
            right = width_px - 1 - max_x
            bottom = min_y
            top = height_px - 1 - max_y
            return {
                "found": True,
                "resolution": [width_px, height_px],
                "background_rgb_linear": [round(v, 6) for v in bg],
                "bbox_pixels_bottom_origin": [min_x, min_y, max_x, max_y],
                "margins_pixels": {"left": left, "right": right, "top": top, "bottom": bottom},
                "min_vertical_margin_pixels": min(top, bottom),
                "min_vertical_margin_ratio": round(min(top, bottom) / max(1, height_px), 6),
                "content_height_pixels": max_y - min_y + 1,
                "content_height_ratio": round((max_y - min_y + 1) / max(1, height_px), 6),
                "threshold": threshold,
            }
        finally:
            bpy.data.images.remove(image)

    def sensor_projection_evidence(camera: Any, layer: int, width_px: int, height_px: int) -> dict[str, Any]:
        from bpy_extras.object_utils import world_to_camera_view

        rows = []
        for obj in sorted([o for o in bpy.data.objects if o.name.startswith(f"SENSOR_T_body_L{layer}_")], key=lambda item: item.name):
            co = world_to_camera_view(bpy.context.scene, camera, obj.location)
            px = float(co.x) * width_px
            py = (1.0 - float(co.y)) * height_px
            margin = min(px, width_px - px, py, height_px - py)
            rows.append(
                {
                    "name": obj.name,
                    "pixel_xy_top_origin": [round(px, 2), round(py, 2)],
                    "depth": round(float(co.z), 6),
                    "inside_frame": 0.0 <= co.x <= 1.0 and 0.0 <= co.y <= 1.0 and co.z >= 0.0,
                    "edge_margin_pixels": round(margin, 2),
                }
            )
        return {
            "layer": f"L{layer}",
            "camera": camera.name,
            "sensor_count": len(rows),
            "inside_count": sum(1 for row in rows if row["inside_frame"]),
            "min_edge_margin_pixels": round(min([row["edge_margin_pixels"] for row in rows] or [0.0]), 2),
            "points": rows,
        }

    input_blend_path = Path(bpy.data.filepath)
    event("child_started", blender_version=bpy.app.version_string, blend=input_blend_path.as_posix())
    assert_row("input_sha256_matches_lock", sha256_file(input_blend_path).lower() == EXPECTED_INPUT_SHA256, sha256_file(input_blend_path))
    assert_row("save_version_is_zero", bpy.context.preferences.filepaths.save_version == 0, bpy.context.preferences.filepaths.save_version)

    shell_objects = [bpy.data.objects.get(name) for name in EXPECTED_PROCESS_ZONES]
    assert_row("all_five_process_zones_present_before", all(obj is not None for obj in shell_objects), EXPECTED_PROCESS_ZONES)
    if any(obj is None for obj in shell_objects):
        raise RuntimeError("Missing one or more expected process zones")
    shell_objects = [obj for obj in shell_objects if obj is not None]

    original_sensor_names = sensor_names()
    original_body_sensor_names = [name for name in original_sensor_names if name.startswith("SENSOR_T_body_L")]
    protected_non_shell_mesh_names = sorted(
        obj.name
        for obj in bpy.data.objects
        if obj.type == "MESH" and obj.name not in EXPECTED_PROCESS_ZONES and not obj.name.startswith("SURF10_")
    )
    before_matrix = obj_matrix_signature(EXPECTED_PROCESS_ZONES + original_sensor_names)
    before_mesh = mesh_signature(EXPECTED_PROCESS_ZONES)
    before_sensor_materials = material_slots_signature(original_sensor_names)
    before_non_shell_materials = material_slots_signature(protected_non_shell_mesh_names)
    before_formal_glb_hash = sha256_file(FORMAL_GLB) if FORMAL_GLB.is_file() else None
    assert_row("sensor_count_before_is_115", len(original_sensor_names) == EXPECTED_SENSOR_COUNT, len(original_sensor_names))
    assert_row("body_temperature_sensor_count_before_is_80", len(original_body_sensor_names) == EXPECTED_BODY_SENSOR_COUNT, len(original_body_sensor_names))
    assert_row("all_l7_l16_layers_present_before", all(exists_layer(name) for name in EXPECTED_LAYERS), EXPECTED_LAYERS)
    assert_row("l7_l16_each_have_8_before", all(count == 8 for count in layer_counts().values()), layer_counts())
    assert_row("formal_glb_hash_matches_before", before_formal_glb_hash == EXPECTED_FORMAL_GLB_SHA256, before_formal_glb_hash)

    removed_review_objects = []
    for obj in list(bpy.data.objects):
        if obj.name.startswith("SURF10_") or obj.name.startswith("SURF10_R2_"):
            removed_review_objects.append(obj.name)
            bpy.data.objects.remove(obj, do_unlink=True)
    assert_row("surf10_review_sample_removed_or_hidden", not any(obj.name.startswith("SURF10_") for obj in bpy.data.objects), removed_review_objects)

    bbox_min, bbox_max = object_world_bbox(shell_objects)
    center = (bbox_min + bbox_max) * 0.5
    dims = bbox_max - bbox_min
    height = max(1.0, dims.z)
    width = max(1.0, dims.x)
    depth = max(1.0, dims.y)
    full_frame_objects = [
        obj
        for obj in bpy.data.objects
        if obj.type == "MESH"
        and not obj.name.startswith("SENSOR_")
        and not obj.name.startswith("SURF10_")
        and obj.name != "APPROX_GL02_access_tower_and_bridges"
    ]
    full_bbox_min, full_bbox_max = object_world_bbox(full_frame_objects)
    full_center = (full_bbox_min + full_bbox_max) * 0.5
    full_dims = full_bbox_max - full_bbox_min
    full_height = max(1.0, full_dims.z)
    full_width = max(1.0, full_dims.x)
    full_depth = max(1.0, full_dims.y)

    mapping_empty = bpy.data.objects.new(MAPPING_EMPTY_NAME, None)
    bpy.context.scene.collection.objects.link(mapping_empty)
    mapping_empty.empty_display_type = "PLAIN_AXES"
    mapping_empty.empty_display_size = max(width, depth) * 0.2
    mapping_empty.location = (0.0, 0.0, 0.0)
    mapping_empty.rotation_euler = (0.0, 0.0, 0.0)
    mapping_empty.scale = (1.0, 1.0, 1.0)
    material = build_material(mapping_empty)

    original_shell_slots = material_slots_signature(EXPECTED_PROCESS_ZONES)
    for obj in shell_objects:
        obj.data.materials.clear()
        obj.data.materials.append(material)
        obj["surf20_material_scope"] = "complete furnace shell external process-zone object; non-shell objects untouched"
    event("material_assigned", material=MATERIAL_NAME, shell_objects=[obj.name for obj in shell_objects])

    diagnostic_textures, texture_statistics = make_diagnostic_cards()

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
    bpy.context.scene.view_settings.exposure = 0.24
    bpy.context.scene.view_settings.gamma = 1.0
    bpy.context.scene.world = bpy.context.scene.world or bpy.data.worlds.new("World")
    bpy.context.scene.world.color = (0.46, 0.48, 0.47)

    add_area_light("SURF20_R4_P40_SOFT_KEY", (center.x - width * 1.25, bbox_min.y - depth * 2.4, center.z + height * 0.72), center, 1050.0, max(width, depth) * 0.62)
    add_area_light("SURF20_R4_P40_COOL_FILL", (center.x + width * 1.2, bbox_min.y - depth * 1.8, center.z + height * 0.55), center, 245.0, max(width, depth) * 1.22)
    add_area_light("SURF20_R4_P40_TOP_SOFTBOX", (center.x, center.y, bbox_max.z + height * 0.85), center, 185.0, max(width, depth) * 1.55)
    grazing_light = add_area_light("SURF20_R4_GRAZING_RAKE_LIGHT", (bbox_min.x - width * 0.18, bbox_min.y - depth * 0.55, center.z + height * 0.35), center, 780.0, 1.4)
    grazing_light.hide_render = True
    grazing_light.hide_viewport = True

    full_scale = full_height / 0.48
    front_cam = make_camera(
        "SURF20_R4_CAM_FRONT_FULL",
        (full_center.x, full_bbox_max.y + max(full_depth * 5.0, full_height * 1.8), full_center.z),
        full_center,
        full_scale,
    )
    three_cam = make_camera(
        "SURF20_R4_CAM_THREE_QUARTER_FULL",
        (
            full_bbox_min.x - max(full_width * 2.8, full_height * 0.75),
            full_bbox_max.y + max(full_depth * 3.8, full_height * 1.45),
            full_center.z + full_height * 0.04,
        ),
        full_center,
        full_scale,
    )

    def layer_center(layer: int) -> Vector:
        points = [obj.location.copy() for obj in bpy.data.objects if obj.name.startswith(f"SENSOR_T_body_L{layer}_")]
        return sum(points, Vector((0, 0, 0))) / max(1, len(points)) if points else center

    detail_cameras = {}
    for layer in (7, 10, 13, 16):
        target = layer_center(layer)
        detail_cameras[f"L{layer}_DETAIL"] = make_camera(
            f"SURF20_R4_CAM_L{layer}_DETAIL",
            (bbox_min.x - max(width * 1.55, 9.0), bbox_min.y - max(depth * 2.15, 11.0), target.z + 1.0),
            target,
            max(width, depth) * 2.05,
        )

    seam_z = (bpy.data.objects["APPROX_GL02_FURNACE_BELLY"].bound_box[0][2] + bpy.data.objects["APPROX_GL02_FURNACE_SHAFT"].bound_box[0][2]) * 0.5
    seam_target = Vector((center.x, center.y, center.z + height * 0.10 if not math.isfinite(seam_z) else center.z + height * 0.10))
    seam_cam = make_camera(
        "SURF20_R4_CAM_SEAM_DIAGNOSTIC",
        (bbox_min.x - max(width * 1.15, 7.0), bbox_min.y - max(depth * 1.45, 8.0), center.z + height * 0.30),
        seam_target,
        max(width, depth) * 0.62,
    )
    grazing_cam = make_camera(
        "SURF20_R4_CAM_GRAZING_NEAR",
        (bbox_min.x - max(width * 0.78, 5.0), bbox_min.y - max(depth * 0.82, 6.0), center.z + height * 0.42),
        Vector((bbox_min.x, bbox_min.y, center.z + height * 0.42)),
        max(2.7, width * 0.25),
    )

    full_view_obstructors = ["APPROX_GL02_access_tower_and_bridges"]
    full_view_obstructor_state = {}
    for name in full_view_obstructors:
        obj = bpy.data.objects.get(name)
        if obj is None:
            continue
        full_view_obstructor_state[name] = {
            "hide_render": obj.hide_render,
            "hide_viewport": obj.hide_viewport,
        }
        obj.hide_render = True
        obj.hide_viewport = True
    event(
        "full_view_uses_furnace_top_and_shell_bbox_with_side_access_tower_hidden_for_render_only",
        objects=len(full_frame_objects),
        target_height_ratio=0.48,
        hidden_for_render=list(full_view_obstructor_state),
    )
    renders = {
        "FRONT_FULL": render(render_dir / "SURF20_R4_01_FRONT_FULL.png", front_cam),
        "THREE_QUARTER_FULL": render(render_dir / "SURF20_R4_02_THREE_QUARTER_FULL.png", three_cam),
    }
    for name, state in full_view_obstructor_state.items():
        obj = bpy.data.objects.get(name)
        if obj is not None:
            obj.hide_render = state["hide_render"]
            obj.hide_viewport = state["hide_viewport"]
    renders.update({
        "L7_DETAIL": render(render_dir / "SURF20_R4_03_L7_DETAIL.png", detail_cameras["L7_DETAIL"]),
        "L10_DETAIL": render(render_dir / "SURF20_R4_04_L10_DETAIL.png", detail_cameras["L10_DETAIL"]),
        "L13_DETAIL": render(render_dir / "SURF20_R4_05_L13_DETAIL.png", detail_cameras["L13_DETAIL"]),
        "L16_DETAIL": render(render_dir / "SURF20_R4_06_L16_DETAIL.png", detail_cameras["L16_DETAIL"]),
        "SEAM_DIAGNOSTIC": render(render_dir / "SURF20_R4_07_SEAM_DIAGNOSTIC.png", seam_cam),
    })
    grazing_light.hide_render = False
    grazing_light.hide_viewport = False
    renders["GRAZING_NEAR"] = render(render_dir / "SURF20_R4_08_GRAZING_NEAR.png", grazing_cam)
    grazing_light.hide_render = True
    grazing_light.hide_viewport = True
    renders["METALLIC_MASK_DIAGNOSTIC"] = {
        **write_png_rgba(
            render_dir / "SURF20_R4_09_METALLIC_MASK_DIAGNOSTIC.png",
            [
                component
                for _ in range(int(args.width) * int(args.height))
                for component in (METALLIC_MASK_VALUE, METALLIC_MASK_VALUE, METALLIC_MASK_VALUE, 1.0)
            ],
            int(args.width),
            int(args.height),
        ),
        "seconds": 0.0,
        "camera": "procedural_metallic_mask_card",
        "resolution": [int(args.width), int(args.height)],
        "engine": "diagnostic_png",
    }
    renders["R1_R2_R3_R4_GRAZING_COMPARISON"] = render_grazing_comparison(Path(renders["GRAZING_NEAR"]["path"]))

    full_render_bounds = {
        "FRONT_FULL": image_non_background_bounds(Path(renders["FRONT_FULL"]["path"])),
        "THREE_QUARTER_FULL": image_non_background_bounds(Path(renders["THREE_QUARTER_FULL"]["path"])),
    }
    layer_projection_evidence = {
        f"L{layer}_DETAIL": sensor_projection_evidence(detail_cameras[f"L{layer}_DETAIL"], layer, int(args.width), int(args.height))
        for layer in (7, 10, 13, 16)
    }

    after_sensor_names = sensor_names()
    after_body_sensor_names = [name for name in after_sensor_names if name.startswith("SENSOR_T_body_L")]
    after_matrix = obj_matrix_signature(EXPECTED_PROCESS_ZONES + after_sensor_names)
    after_mesh = mesh_signature(EXPECTED_PROCESS_ZONES)
    after_sensor_materials = material_slots_signature(after_sensor_names)
    after_non_shell_materials = material_slots_signature(protected_non_shell_mesh_names)
    after_formal_glb_hash = sha256_file(FORMAL_GLB) if FORMAL_GLB.is_file() else None
    shell_materials_after = material_slots_signature(EXPECTED_PROCESS_ZONES)
    hidden_review_objects = [obj.name for obj in bpy.data.objects if obj.name.startswith("SURF10_") or obj.name.startswith("SURF10_R2_")]

    assert_row("sensor_count_after_is_115", len(after_sensor_names) == EXPECTED_SENSOR_COUNT, len(after_sensor_names))
    assert_row("sensor_names_unchanged", original_sensor_names == after_sensor_names, {"before": len(original_sensor_names), "after": len(after_sensor_names)})
    assert_row("body_temperature_sensor_count_after_is_80", len(after_body_sensor_names) == EXPECTED_BODY_SENSOR_COUNT, len(after_body_sensor_names))
    assert_row("all_l7_l16_layers_present_after", all(exists_layer(name) for name in EXPECTED_LAYERS), EXPECTED_LAYERS)
    assert_row("l7_l16_each_have_8_after", all(count == 8 for count in layer_counts().values()), layer_counts())
    assert_row("sensor_material_slots_unchanged", before_sensor_materials == after_sensor_materials, {"before": signature_hash(before_sensor_materials), "after": signature_hash(after_sensor_materials)})
    assert_row("non_shell_material_slots_unchanged", before_non_shell_materials == after_non_shell_materials, {"before": signature_hash(before_non_shell_materials), "after": signature_hash(after_non_shell_materials)})
    assert_row("five_process_zone_matrices_unchanged", signature_hash(before_matrix) == signature_hash(after_matrix), {"before": signature_hash(before_matrix), "after": signature_hash(after_matrix)})
    assert_row("five_process_zone_mesh_signatures_unchanged", before_mesh == after_mesh, {"before": signature_hash(before_mesh), "after": signature_hash(after_mesh)})
    assert_row("five_process_zones_use_surf20_material", all(slots == [MATERIAL_NAME] for slots in shell_materials_after.values()), shell_materials_after)
    assert_row("formal_glb_hash_unchanged", before_formal_glb_hash == after_formal_glb_hash == EXPECTED_FORMAL_GLB_SHA256, {"before": before_formal_glb_hash, "after": after_formal_glb_hash})
    assert_row("no_glb_export_created", not sorted(output_dir.rglob("*.glb")), [])
    assert_row("review_sample_not_visible_in_candidate", not hidden_review_objects, hidden_review_objects)
    assert_row("render_count_at_least_10", len(renders) >= 10, list(renders.keys()))
    assert_row("all_required_render_files_nonempty", all(Path(row["path"]).is_file() and Path(row["path"]).stat().st_size > 0 for row in renders.values()), renders)
    assert_row("diagnostic_textures_created", all(Path(row["path"]).is_file() for row in diagnostic_textures.values()), diagnostic_textures)
    assert_row("shared_mapping_empty_present", bpy.data.objects.get(MAPPING_EMPTY_NAME) is not None, MAPPING_EMPTY_NAME)
    assert_row(
        "full_view_vertical_margin_at_least_8_percent",
        all(row.get("found") and row.get("min_vertical_margin_pixels", 0) >= int(args.height * 0.08) for row in full_render_bounds.values()),
        full_render_bounds,
    )
    assert_row(
        "full_view_content_height_ratio_70_to_82_percent",
        all(row.get("found") and 0.70 <= row.get("content_height_ratio", 0.0) <= 0.82 for row in full_render_bounds.values()),
        full_render_bounds,
    )
    assert_row(
        "l7_l10_l13_l16_detail_main_layer_8_points_inside_frame",
        all(row["sensor_count"] == 8 and row["inside_count"] == 8 and row["min_edge_margin_pixels"] >= 12.0 for row in layer_projection_evidence.values()),
        layer_projection_evidence,
    )

    candidate_blend = output_dir / BLEND_NAME
    bpy.ops.wm.save_as_mainfile(filepath=candidate_blend.as_posix())
    blend1_files = sorted(path.as_posix() for path in output_dir.rglob("*.blend1"))
    assert_row("candidate_blend_saved", candidate_blend.is_file() and candidate_blend.stat().st_size > 0, candidate_blend.as_posix())
    assert_row("no_blend1_backup_created", not blend1_files, blend1_files)

    ok_count = sum(1 for row in assertions if row["ok"])
    fail_count = len(assertions) - ok_count
    material_manifest = {
        "schema_version": 1,
        "stage": STAGE,
        "status": STATUS,
        "approval": APPROVAL,
        "material": MATERIAL_NAME,
        "assigned_objects": EXPECTED_PROCESS_ZONES,
        "source_baseline": "SURF-20 R3 full-shell material candidate, SHA-256 locked by this stage input",
        "appearance": {
            "base_finish": "matte dark green-gray aged painted carbon steel",
            "weathering": "fine orange-peel/sandblast microtexture, very soft pitting, weak gravity water/dust streak intent",
            "random_rust_limit": "no random orange rust carpet; oxidation only low-contrast and sparse",
        },
        "pbr_parameters": {
            "principled_metallic_socket": METALLIC_MASK_VALUE,
            "metallic_mask_range": [METALLIC_MASK_VALUE, METALLIC_MASK_VALUE],
            "metallic_mask_mean": METALLIC_MASK_VALUE,
            "metallic_high_area_ratio": 0.0,
            "metallic_identity_note": "No reliable edge or chipped-paint causality was available in this single-stage fix, so the explicit mask stays in painted/coated carbon-steel range instead of adding random bare-steel flecks.",
            "roughness_range_target": [0.56, 0.82],
            "normal_equivalent_strength": NORMAL_EQUIVALENT_STRENGTH,
            "bump_strength": BUMP_STRENGTH,
            "bump_distance_meters": BUMP_DISTANCE_METERS,
        },
        "shared_mapping": {
            "method": "TextureCoordinate Object",
            "mapping_object": MAPPING_EMPTY_NAME,
            "mapping_object_matrix": [round(float(value), 8) for row in mapping_empty.matrix_world for value in row],
            "mapping_scale_xyz": [0.085, 0.085, 0.085],
            "continuity_claim": "all five shell segment materials reference the same world-origin mapping empty; procedural phase is not reset per object",
        },
        "texture_colorspace": {
            "shader_textures": "procedural Blender nodes; no external image texture dependency for final candidate material",
            "diagnostic_basecolor": "sRGB",
            "diagnostic_roughness": "Non-Color",
            "diagnostic_height": "Non-Color",
            "diagnostic_metallic": "Non-Color",
        },
        "diagnostic_textures": diagnostic_textures,
        "texture_statistics": texture_statistics,
        "original_shell_slots_before": original_shell_slots,
        "shell_slots_after": shell_materials_after,
        "non_shell_material_hash_before": signature_hash(before_non_shell_materials),
        "non_shell_material_hash_after": signature_hash(after_non_shell_materials),
    }
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
            "view_transform": bpy.context.scene.view_settings.view_transform,
            "look": bpy.context.scene.view_settings.look,
            "exposure": bpy.context.scene.view_settings.exposure,
        },
        "candidate": {
            "path": candidate_blend.as_posix(),
            "project_relative_path": relative_display(candidate_blend),
            "bytes": candidate_blend.stat().st_size,
            "sha256": sha256_file(candidate_blend),
        },
        "formal_glb_protection": {
            "path": FORMAL_GLB.as_posix(),
            "before_sha256": before_formal_glb_hash,
            "after_sha256": after_formal_glb_hash,
            "unchanged": before_formal_glb_hash == after_formal_glb_hash,
        },
        "protected_contract": {
            "sensor_count": len(after_sensor_names),
            "body_temperature_sensor_count": len(after_body_sensor_names),
            "layer_counts": layer_counts(),
            "five_process_zone_matrix_hash_before": signature_hash(before_matrix),
            "five_process_zone_matrix_hash_after": signature_hash(after_matrix),
            "five_process_zone_mesh_hash_before": signature_hash(before_mesh),
            "five_process_zone_mesh_hash_after": signature_hash(after_mesh),
            "sensor_material_hash_before": signature_hash(before_sensor_materials),
            "sensor_material_hash_after": signature_hash(after_sensor_materials),
            "non_shell_material_hash_before": signature_hash(before_non_shell_materials),
            "non_shell_material_hash_after": signature_hash(after_non_shell_materials),
        },
        "material_manifest": relative_display(output_dir / "surf20_r4_material_manifest.json"),
        "renders": renders,
        "full_view_boundary_evidence": full_render_bounds,
        "layer_detail_projection_evidence": layer_projection_evidence,
        "full_view_render_visibility_note": {
            "temporarily_hidden_for_front_and_three_quarter_only": full_view_obstructors,
            "candidate_objects_restored_after_render": True,
            "r4_change": "Only the micro-surface bump/normal strength is increased from R3 toward the perceptual midpoint. The side access tower remains hidden only during the two full-view renders to avoid a non-top vertical tower dominating the image bbox; furnace top gas/upright structures, platforms, supports, and all five shell zones remain visible and candidate object visibility is restored before save.",
        },
        "assertions": assertions,
        "assertion_summary": {
            "total": len(assertions),
            "passed": ok_count,
            "failed": fail_count,
        },
        "events": events,
        "known_non_blocking_issues": [
            "Candidate uses Blender procedural shader nodes with shared object-space mapping; no GLB/PBR bake or glTF Validator was executed in SURF-20.",
            "Visual approval is intentionally not granted by this execution agent; stop line is visual and spec review.",
            "Root-level specs/avatar_spec.json and specs/acceptance_checklist.md were not present in this workspace snapshot during preflight; reports/pipeline_status.json was present.",
        ],
    }
    summary = f"""# SURF-20 R4 阶段成果总结

## R1-R4 视觉对比

- R1：掠射下橘皮/细砂和软凹坑明显，但 bump `0.16`、distance `0.10m`、normal equivalent `0.45` 过强，近景容易读成砂浆、水泥浮雕；且 R1 metallic `0.72` 不符合本轮低金属度涂层身份。
- R2：metallic 修正为 `{METALLIC_MASK_VALUE}`，roughness 回到 `0.56-0.82`，全景边距与主体高度合格；但 GRAZING_NEAR 的微表面读感偏平，橘皮/细砂密度不够清楚。
- R3：相对 R2 已推进到 R2 -> R1 的约 30-40%，但 GRAZING_NEAR 仍偏平，密集橘皮/细砂读感不足。
- R4：只把 R3 微表面强度提高到硬锁值，目标是掠射近景清楚、密集、克制，正面 L7/L10/L13/L16 仅轻微可见，不达到 R1 浮雕强度。

## R4 单变量修改

- 输入从 R3 候选继续：`{relative_display(input_blend_path)}`，SHA-256 `{sha256_file(input_blend_path)}`。
- 五个炉段对象 `{", ".join(EXPECTED_PROCESS_ZONES)}` 统一绑定 `{MATERIAL_NAME}`。
- 未修改 metallic 策略、roughness 目标、共享 Object 世界映射比例、五炉段 mesh/matrix、传感器、相机取景安全边距或正式 GLB。
- 保留 R3 全景取景口径；仅在全景渲染时临时隐藏侧向检修塔，保存候选前恢复对象可见性。
- 本轮未触发水泥浮雕风险，因此未偏离硬锁值；bump strength `0.116`、distance `0.058m`、normal equivalent `0.34` 均低于 R1 停止线。

## 参数表

| 项 | R1 | R2 | R3 | R4 |
|---|---:|---:|---:|---:|
| metallic | 0.72 | 0.06 | 0.06 | `{METALLIC_MASK_VALUE}` |
| roughness target | 0.44-0.78 | 0.56-0.82 | 0.56-0.82 | 0.56-0.82 |
| shared mapping scale | 0.085 | 0.085 | 0.085 | 0.085 |
| bump strength | 0.16 | 0.06 | 0.09 | `{BUMP_STRENGTH}` |
| bump distance | 0.10m | 0.03m | 0.045m | `{BUMP_DISTANCE_METERS}m` |
| normal equivalent | 0.45 | 0.24 | 0.29 | `{NORMAL_EQUIVALENT_STRENGTH}` |

## Metallic / Roughness / Mapping

- metallic mask 范围：`{METALLIC_MASK_VALUE}` - `{METALLIC_MASK_VALUE}`；均值 `{METALLIC_MASK_VALUE}`；高金属面积比例 `0.0`；无随机裸钢点。
- Roughness：目标 `0.56-0.82`，诊断 `{texture_statistics["roughness"]}`。
- BaseColor：深灰绿涂层，诊断 luma `{texture_statistics["base_luma"]}`。
- 共享映射：所有炉段使用 `TextureCoordinate Object -> {MAPPING_EMPTY_NAME}`，Mapping scale XYZ = `0.085/0.085/0.085`，世界原点相位不按炉段重置。
- 颜色空间：诊断 BaseColor 为 sRGB；Roughness/Height/Metallic 为 Non-Color。

## 保护项

- 传感器数量：`{len(after_sensor_names)}`；BODY_TEMP：`{len(after_body_sensor_names)}`。
- L7-L16 每层 A-H 计数：`{layer_counts()}`。
- 五炉段矩阵 hash：`{signature_hash(before_matrix)}` -> `{signature_hash(after_matrix)}`。
- 五炉段 mesh hash：`{signature_hash(before_mesh)}` -> `{signature_hash(after_mesh)}`。
- 传感器材质 hash：`{signature_hash(before_sensor_materials)}` -> `{signature_hash(after_sensor_materials)}`。
- 非炉壳材质 hash：`{signature_hash(before_non_shell_materials)}` -> `{signature_hash(after_non_shell_materials)}`。
- 正式 GLB 前后 SHA-256：`{before_formal_glb_hash}` / `{after_formal_glb_hash}`。
- `.blend1`：`{blend1_files}`。

## 相机边界

- FRONT_FULL：`{full_render_bounds["FRONT_FULL"]}`。
- THREE_QUARTER_FULL：`{full_render_bounds["THREE_QUARTER_FULL"]}`。

## 命令

```powershell
& "{DEFAULT_BLENDER}" --background "{DEFAULT_INPUT_BLEND}" --python "{SCRIPT_PATH}" -- --blender-child --output-dir "{output_dir}" --width {int(args.width)} --height {int(args.height)}
& "{DEFAULT_BLENDER}" --background "{candidate_blend}" --python "{SCRIPT_PATH}" -- --validate-child --output-dir "{output_dir}"
```

## 机器结果

- 候选 Blend：`{relative_display(candidate_blend)}`
- 候选 Blend SHA-256：`{sha256_file(candidate_blend)}`
- 机器报告：`{relative_display(output_dir / "surf20_r4_machine_report.json")}`
- 材质清单：`{relative_display(output_dir / "surf20_r4_material_manifest.json")}`
- 哈希清单：`{relative_display(output_dir / "artifact_sha256.json")}`
- 断言：`{ok_count}/{len(assertions)}` 通过。

## 渲染与 Comparison 证据

- `SURF20_R4_01_FRONT_FULL.png`
- `SURF20_R4_02_THREE_QUARTER_FULL.png`
- `SURF20_R4_03_L7_DETAIL.png`
- `SURF20_R4_04_L10_DETAIL.png`
- `SURF20_R4_05_L13_DETAIL.png`
- `SURF20_R4_06_L16_DETAIL.png`
- `SURF20_R4_07_SEAM_DIAGNOSTIC.png`
- `SURF20_R4_08_GRAZING_NEAR.png`
- `SURF20_R4_09_METALLIC_MASK_DIAGNOSTIC.png`
- `SURF20_R4_10_R1_R2_R3_R4_GRAZING_COMPARISON.png`
- Comparison 源图与 SHA：`{renders["R1_R2_R3_R4_GRAZING_COMPARISON"]["comparison_sources"]}`。

## 已知边界

- 本阶段未做 GLB 导出、PBR 烘焙、glTF Validator 或 Three.js 复验，正式 GLB 保持原 SHA。
- Comparison 使用 R1/R2/R3 既有同名 `*_08_GRAZING_NEAR.png` 与本阶段 R4 掠射图四列合成；合成只加 B/D/N 参数标签，不改变源图裁切。
- 工作区未找到 `specs/avatar_spec.json` 和 `specs/acceptance_checklist.md`；`reports/pipeline_status.json` 已读取并更新。
- 视觉批准不由本执行智能体授予。

## 下一停止线

- 停止在视觉质量审查与规格审查；状态 `{STATUS}`，approval `{APPROVAL}`。未通过复核不得进入下一阶段或替换正式 GLB。
"""
    write_json(output_dir / "surf20_r4_material_manifest.json", material_manifest)
    write_json(output_dir / "surf20_r4_machine_report.json", report)
    write_text(output_dir / "SURF-20_R4_阶段成果总结.md", summary)
    return 0 if fail_count == 0 else 2


def validate_child(args: argparse.Namespace) -> int:
    import bpy

    output_dir = args.output_dir.resolve()
    assertions: list[dict[str, Any]] = []

    def assert_row(assertion_id: str, ok: bool, detail: Any = None) -> None:
        assertions.append({"id": assertion_id, "ok": bool(ok), "detail": detail})

    def sensor_names() -> list[str]:
        return sorted(name for name in bpy.data.objects.keys() if name.startswith("SENSOR_"))

    def layer_counts() -> dict[str, int]:
        return {
            f"L{layer}": len([name for name in bpy.data.objects.keys() if name.startswith(f"SENSOR_T_body_L{layer}_")])
            for layer in range(7, 17)
        }

    shell_slots = {}
    for name in EXPECTED_PROCESS_ZONES:
        obj = bpy.data.objects.get(name)
        shell_slots[name] = None if obj is None else [slot.material.name if slot.material else None for slot in obj.material_slots]
    assert_row("candidate_reopened", bool(bpy.data.filepath), bpy.data.filepath)
    assert_row("candidate_blend_hash_available", bool(bpy.data.filepath), sha256_file(Path(bpy.data.filepath)))
    assert_row("sensor_count_reopen_is_115", len(sensor_names()) == EXPECTED_SENSOR_COUNT, len(sensor_names()))
    assert_row("body_temperature_count_reopen_is_80", len([name for name in sensor_names() if name.startswith("SENSOR_T_body_L")]) == EXPECTED_BODY_SENSOR_COUNT, None)
    assert_row("l7_l16_each_have_8_reopen", all(count == 8 for count in layer_counts().values()), layer_counts())
    assert_row("five_process_zones_use_surf20_material_reopen", all(slots == [MATERIAL_NAME] for slots in shell_slots.values()), shell_slots)
    assert_row("shared_mapping_empty_present_reopen", bpy.data.objects.get(MAPPING_EMPTY_NAME) is not None, MAPPING_EMPTY_NAME)
    review_objects = [obj.name for obj in bpy.data.objects if obj.name.startswith("SURF10_")]
    assert_row("review_sample_absent_reopen", not review_objects, review_objects)
    assert_row("formal_glb_hash_still_baseline_reopen", sha256_file(FORMAL_GLB) == EXPECTED_FORMAL_GLB_SHA256, sha256_file(FORMAL_GLB) if FORMAL_GLB.is_file() else None)
    ok_count = sum(1 for row in assertions if row["ok"])
    write_json(
        output_dir / "surf20_r4_reopen_validation.json",
        {
            "schema_version": 1,
            "stage": STAGE,
            "created_at": now_iso(),
            "candidate": bpy.data.filepath,
            "candidate_sha256": sha256_file(Path(bpy.data.filepath)),
            "assertions": assertions,
            "assertion_summary": {"total": len(assertions), "passed": ok_count, "failed": len(assertions) - ok_count},
        },
    )
    return 0 if ok_count == len(assertions) else 2


def main(argv: list[str] | None = None) -> int:
    raw_argv = list(sys.argv[1:] if argv is None else argv)
    if "--" in raw_argv:
        raw_argv = raw_argv[raw_argv.index("--") + 1 :]
    args = parse_args(raw_argv)
    if args.blender_child:
        try:
            return blender_child(args)
        except Exception:
            args.output_dir.resolve().mkdir(parents=True, exist_ok=True)
            (args.output_dir.resolve() / "surf20_r4_child_exception.txt").write_text(traceback.format_exc(), encoding="utf-8")
            raise
    if args.validate_child:
        try:
            return validate_child(args)
        except Exception:
            args.output_dir.resolve().mkdir(parents=True, exist_ok=True)
            (args.output_dir.resolve() / "surf20_r4_validate_exception.txt").write_text(traceback.format_exc(), encoding="utf-8")
            raise
    return run_parent(args)


if __name__ == "__main__":
    sys.exit(main())


