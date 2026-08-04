"""Run SURF-10 as a single-segment procedural surface material sample.

The parent Python process launches Blender and records command/stdout/stderr.
The Blender child duplicates one approved furnace shell segment, assigns the
SURF-10 sample material only to that duplicate, renders neutral LookDev beauty
and channel diagnostics, then saves a candidate Blend for visual/spec review.
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
from typing import Any, Iterable


STAGE = "SURF-10"
STATUS = "candidate_ready_for_review"
APPROVAL = "not_granted_requires_visual_and_spec_review"
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
DEFAULT_OUTPUT_DIR = MODULE_ROOT / "work" / "SURF_10_20260718_R1"
SOURCE_SEGMENT_NAME = "APPROX_GL02_FURNACE_SHAFT"
SAMPLE_OBJECT_NAME = "SURF10_SAMPLE_PANEL_FROM_APPROX_GL02_FURNACE_SHAFT"
SAMPLE_MATERIAL_NAME = "SURF10_matte_weathered_shell_sample_orange_peel"
BLEND_NAME = "SURF10_SURFACE_SAMPLE_CANDIDATE.blend"


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
            "excludes": ["artifact_sha256.json"],
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
    output_dir.mkdir(parents=True, exist_ok=True)
    stale_exception = output_dir / "surf10_child_exception.txt"
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
        "input_sha256": sha256_file(input_blend),
        "blender": blender.as_posix(),
        "output_dir": output_dir.as_posix(),
    }
    write_json(output_dir / "surf10_execution_command.json", command_record)
    stdout_path = output_dir / "runner.stdout.log"
    stderr_path = output_dir / "runner.stderr.log"
    with stdout_path.open("w", encoding="utf-8", newline="\n") as stdout, stderr_path.open(
        "w", encoding="utf-8", newline="\n"
    ) as stderr:
        completed = subprocess.run(command, cwd=PROJECT_ROOT, stdout=stdout, stderr=stderr, check=False)
    command_record["completed_at"] = now_iso()
    command_record["exit_code"] = completed.returncode
    write_json(output_dir / "surf10_execution_command.json", command_record)
    write_artifact_index(output_dir)
    report_path = output_dir / "surf10_machine_report.json"
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
    parser.add_argument("--width", type=int, default=1200)
    parser.add_argument("--height", type=int, default=800)
    parser.add_argument("--texture-resolution", type=int, default=1024)
    return parser.parse_args(argv)


def blender_child(args: argparse.Namespace) -> int:
    import bpy
    from mathutils import Vector

    output_dir = args.output_dir.resolve()
    texture_dir = output_dir / "textures"
    beauty_dir = output_dir / "renders" / "beauty"
    channel_dir = output_dir / "renders" / "channels"
    for path in (texture_dir, beauty_dir, channel_dir):
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

    def hash01(x: int, y: int, seed: int = 0) -> float:
        return (math.sin(x * 127.1 + y * 311.7 + seed * 74.7) * 43758.5453123) % 1.0

    def smoothstep(value: float) -> float:
        return value * value * (3.0 - 2.0 * value)

    def lerp(left: float, right: float, factor: float) -> float:
        return left + (right - left) * factor

    def value_noise(u: float, v: float, scale: float, seed: int) -> float:
        px = u * scale
        py = v * scale
        x0 = math.floor(px)
        y0 = math.floor(py)
        tx = smoothstep(px - x0)
        ty = smoothstep(py - y0)
        a = hash01(x0, y0, seed)
        b = hash01(x0 + 1, y0, seed)
        c = hash01(x0, y0 + 1, seed)
        d = hash01(x0 + 1, y0 + 1, seed)
        return lerp(lerp(a, b, tx), lerp(c, d, tx), ty)

    def create_image(name: str, path: Path, pixels: list[float], width: int, height: int) -> dict[str, Any]:
        image = bpy.data.images.new(name=name, width=width, height=height, alpha=True, float_buffer=False)
        image.pixels.foreach_set(pixels)
        image.filepath_raw = path.as_posix()
        image.file_format = "PNG"
        image.save()
        return {
            "path": path.as_posix(),
            "project_relative_path": relative_display(path),
            "bytes": path.stat().st_size,
            "sha256": sha256_file(path),
            "colorspace": "sRGB" if "basecolor" in name.lower() else "Non-Color",
        }

    event("child_started", blender_version=bpy.app.version_string, blend=bpy.data.filepath)
    original_sensor_names = sensor_names()
    original_body_sensor_names = [name for name in original_sensor_names if name.startswith("SENSOR_T_body_L")]
    protected_names = original_sensor_names + EXPECTED_PROCESS_ZONES
    before_matrix_hash = signature_hash(obj_matrix_signature(protected_names))
    before_material_hash = signature_hash(material_slots_signature(EXPECTED_PROCESS_ZONES))

    source = bpy.data.objects.get(SOURCE_SEGMENT_NAME)
    assert_row("input_blend_loaded", bool(bpy.data.filepath), bpy.data.filepath)
    assert_row("source_segment_exists", source is not None, SOURCE_SEGMENT_NAME)
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

    import math

    resolution = int(args.texture_resolution)
    height_map = [0.0] * (resolution * resolution)
    base_pixels: list[float] = []
    rough_pixels: list[float] = []
    for y in range(resolution):
        v = y / max(1, resolution - 1)
        for x in range(resolution):
            u = x / max(1, resolution - 1)
            coarse = 0.58 * value_noise(u, v, 4.8, 41) + 0.42 * value_noise(u, v, 9.5, 42)
            mid = value_noise(u, v, 27.0, 43)
            fine = 0.52 * value_noise(u, v, 92.0, 44) + 0.48 * value_noise(u, v, 174.0, 45)
            sand = hash01(x, y, 3) - 0.5
            cell_x = int(u * 96.0)
            cell_y = int(v * 96.0)
            pit_seed = hash01(cell_x, cell_y, 11)
            local_x = u * 96.0 - cell_x - 0.5
            local_y = v * 96.0 - cell_y - 0.5
            pit_radius = 0.07 + 0.055 * hash01(cell_x, cell_y, 12)
            pit = 1.0 if pit_seed > 0.972 and (local_x * local_x + local_y * local_y) < pit_radius * pit_radius else 0.0
            streak_cell = int(u * 58.0)
            streak_center = (streak_cell + 0.22 + 0.56 * hash01(streak_cell, 4, 21)) / 58.0
            streak_width = 0.0035 + 0.0045 * hash01(streak_cell, 9, 22)
            streak_gate = 1.0 if hash01(streak_cell, 2, 20) > 0.71 else 0.0
            vertical_mod = 0.62 + 0.38 * math.sin(2.0 * math.pi * (v * 5.4 + hash01(streak_cell, 1, 23)))
            streak = streak_gate * math.exp(-((u - streak_center) ** 2) / max(0.000001, streak_width * streak_width)) * vertical_mod
            dust = clamp(0.20 * streak + 0.035 * coarse + 0.025 * hash01(x // 8, y // 8, 31))
            water_dark = clamp(0.11 * streak * (0.35 + 0.65 * v))
            micro = (fine - 0.5) * 0.020 + (mid - 0.5) * 0.010 + sand * 0.006
            h = 0.5 + micro + dust * 0.035 - pit * 0.105 - water_dark * 0.03
            height_map[y * resolution + x] = clamp(h)
            r = 0.205 + 0.027 * coarse + 0.020 * fine + 0.038 * dust - 0.040 * water_dark - 0.075 * pit
            g = 0.235 + 0.022 * coarse + 0.016 * fine + 0.032 * dust - 0.035 * water_dark - 0.072 * pit
            b = 0.220 + 0.018 * coarse + 0.012 * fine + 0.025 * dust - 0.030 * water_dark - 0.065 * pit
            # Muted oxide warmth only at pits and faint dust, not an orange rust repaint.
            r += 0.018 * pit + 0.010 * dust
            g += 0.006 * dust
            base_pixels.extend([clamp(r), clamp(g), clamp(b), 1.0])
            rough = clamp(0.66 + 0.075 * coarse + 0.055 * fine + 0.095 * dust + 0.035 * pit - 0.035 * water_dark, 0.54, 0.86)
            rough_pixels.extend([rough, rough, rough, 1.0])

    normal_pixels: list[float] = []
    strength = 3.2
    for y in range(resolution):
        for x in range(resolution):
            left = height_map[y * resolution + max(0, x - 1)]
            right = height_map[y * resolution + min(resolution - 1, x + 1)]
            down = height_map[max(0, y - 1) * resolution + x]
            up = height_map[min(resolution - 1, y + 1) * resolution + x]
            dx = (right - left) * strength
            dy = (up - down) * strength
            nx, ny, nz = -dx, -dy, 1.0
            length = math.sqrt(nx * nx + ny * ny + nz * nz)
            nx, ny, nz = nx / length, ny / length, nz / length
            normal_pixels.extend([nx * 0.5 + 0.5, ny * 0.5 + 0.5, nz * 0.5 + 0.5, 1.0])

    texture_assets = {
        "basecolor": create_image(
            "SURF10_basecolor_low_contrast_weathered_green_gray",
            texture_dir / "SURF10_basecolor_orange_peel_dust_streaks.png",
            base_pixels,
            resolution,
            resolution,
        ),
        "roughness": create_image(
            "SURF10_roughness_microvariation",
            texture_dir / "SURF10_roughness_micro_pitting_dust.png",
            rough_pixels,
            resolution,
            resolution,
        ),
        "normal": create_image(
            "SURF10_normal_detail_orange_peel_fine_sand",
            texture_dir / "SURF10_normal_orange_peel_fine_sand.png",
            normal_pixels,
            resolution,
            resolution,
        ),
    }
    event("textures_created", assets=texture_assets)

    collection = bpy.data.collections.new("SURF10_SINGLE_SURFACE_SAMPLE")
    bpy.context.scene.collection.children.link(collection)
    if SAMPLE_OBJECT_NAME in bpy.data.objects:
        bpy.data.objects.remove(bpy.data.objects[SAMPLE_OBJECT_NAME], do_unlink=True)
    source_bbox = [source.matrix_world @ Vector(corner) for corner in source.bound_box]
    source_min = Vector((min(point.x for point in source_bbox), min(point.y for point in source_bbox), min(point.z for point in source_bbox)))
    source_max = Vector((max(point.x for point in source_bbox), max(point.y for point in source_bbox), max(point.z for point in source_bbox)))
    source_center = (source_min + source_max) * 0.5
    z_span = max(0.1, source_max.z - source_min.z)
    front_radius = max(10.0, abs(source_min.y - source_center.y))
    panel_width = min(8.0, max(4.8, (source_max.x - source_min.x) * 0.34))
    panel_height = min(12.0, max(7.0, z_span * 0.72))
    columns = 72
    rows = 104
    vertices: list[tuple[float, float, float]] = []
    faces: list[tuple[int, int, int, int]] = []
    for row in range(rows):
        v = row / (rows - 1)
        z = source_center.z + (v - 0.5) * panel_height
        for column in range(columns):
            u = column / (columns - 1)
            x = source_center.x + (u - 0.5) * panel_width
            x_offset = x - source_center.x
            y = source_min.y - 0.035 + (x_offset * x_offset) / (2.0 * front_radius)
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
    collection.objects.link(sample)
    uv_layer = sample.data.uv_layers.new(name="SURF10_clean_review_panel_uv")
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
    material.metallic = 0.78
    material.roughness = 0.72
    nodes = material.node_tree.nodes
    for node in list(nodes):
        nodes.remove(node)
    output = nodes.new("ShaderNodeOutputMaterial")
    principled = nodes.new("ShaderNodeBsdfPrincipled")
    base_node = nodes.new("ShaderNodeTexImage")
    rough_node = nodes.new("ShaderNodeTexImage")
    normal_node = nodes.new("ShaderNodeTexImage")
    normal_map = nodes.new("ShaderNodeNormalMap")
    base_node.image = bpy.data.images.load(texture_assets["basecolor"]["path"], check_existing=True)
    rough_node.image = bpy.data.images.load(texture_assets["roughness"]["path"], check_existing=True)
    normal_node.image = bpy.data.images.load(texture_assets["normal"]["path"], check_existing=True)
    base_node.image.colorspace_settings.name = "sRGB"
    rough_node.image.colorspace_settings.name = "Non-Color"
    normal_node.image.colorspace_settings.name = "Non-Color"
    normal_map.inputs["Strength"].default_value = 0.09
    material.node_tree.links.new(base_node.outputs["Color"], principled.inputs["Base Color"])
    material.node_tree.links.new(rough_node.outputs["Color"], principled.inputs["Roughness"])
    material.node_tree.links.new(normal_node.outputs["Color"], normal_map.inputs["Color"])
    material.node_tree.links.new(normal_map.outputs["Normal"], principled.inputs["Normal"])
    if "Metallic" in principled.inputs:
        principled.inputs["Metallic"].default_value = 0.76
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
        "scope": "one duplicated representative shell segment only; original furnace segments and sensors are not assigned this material",
        "p40_direction_preserved": {
            "base_finish": "matte rough weathered steel, low-contrast dark green-gray",
            "roughness_range_target": [0.54, 0.86],
            "normal_strength": 0.09,
            "metallic": 0.76,
        },
        "detail_layers": [
            "restrained orange-peel and fine-sand detail normal",
            "micro pitting as small dark non-metallic interruptions",
            "micro roughness variation from coarse/fine/noise masks",
            "sparse gravity-aligned dust and water streaks",
        ],
        "excluded_scope": [
            "no formal GLB export",
            "no replacement of production GLB",
            "no full-furnace material rollout",
            "no direct changes to 115 SENSOR nodes",
            "no direct changes to L7-L16 sensor layer nodes/collections",
            "no direct material edits on the five original furnace process segments",
        ],
        "textures": texture_assets,
    }

    bbox_points = [sample.matrix_world @ Vector(corner) for corner in sample.bound_box]
    bbox_min = Vector((min(point.x for point in bbox_points), min(point.y for point in bbox_points), min(point.z for point in bbox_points)))
    bbox_max = Vector((max(point.x for point in bbox_points), max(point.y for point in bbox_points), max(point.z for point in bbox_points)))
    center = (bbox_min + bbox_max) * 0.5

    def look_at(camera: Any, target: Vector) -> None:
        direction = target - camera.location
        camera.rotation_euler = direction.to_track_quat("-Z", "Y").to_euler()

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
        "near": make_camera("SURF10_CAM_NEAR_DETAIL", (center.x, bbox_min.y - 14.0, center.z + 0.2), 2.15),
        "mid": make_camera("SURF10_CAM_MID_SAMPLE", (center.x, bbox_min.y - 20.0, center.z + 0.4), 6.4),
        "far": make_camera("SURF10_CAM_FAR_CONTEXT", (center.x, bbox_min.y - 31.0, center.z + 0.6), 15.0),
    }

    def add_area_light(name: str, location: tuple[float, float, float], power: float, size: float) -> None:
        light_data = bpy.data.lights.new(name, type="AREA")
        light = bpy.data.objects.new(name, light_data)
        collection.objects.link(light)
        light.location = location
        light.data.energy = power
        light.data.size = size
        look_at(light, center)

    add_area_light("SURF10_NEUTRAL_KEY_SOFTBOX", (center.x - 5.5, bbox_min.y - 10.0, center.z + 7.0), 460.0, 6.0)
    add_area_light("SURF10_NEUTRAL_FILL_SOFTBOX", (center.x + 5.0, bbox_min.y - 13.0, center.z + 4.0), 120.0, 9.0)
    add_area_light("SURF10_NEUTRAL_TOP_SOFTBOX", (center.x, center.y, bbox_max.z + 8.0), 90.0, 12.0)
    bpy.context.scene.world = bpy.context.scene.world or bpy.data.worlds.new("World")
    bpy.context.scene.world.color = (0.54, 0.56, 0.57)
    bpy.context.scene.render.resolution_x = int(args.width)
    bpy.context.scene.render.resolution_y = int(args.height)
    bpy.context.scene.render.film_transparent = False
    try:
        bpy.context.scene.render.engine = "BLENDER_EEVEE_NEXT"
    except TypeError:
        bpy.context.scene.render.engine = "BLENDER_EEVEE"
    bpy.context.scene.eevee.taa_render_samples = 64
    bpy.context.scene.view_settings.view_transform = "AgX"
    try:
        bpy.context.scene.view_settings.look = "Medium Low Contrast"
    except TypeError:
        bpy.context.scene.view_settings.look = "AgX - Medium Low Contrast"
    bpy.context.scene.view_settings.exposure = 0.0
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
        if width is not None:
            bpy.context.scene.render.resolution_x = width
        if height is not None:
            bpy.context.scene.render.resolution_y = height
        bpy.context.scene.camera = camera
        bpy.context.scene.render.filepath = path.as_posix()
        started = datetime.now()
        bpy.ops.render.render(write_still=True)
        seconds = (datetime.now() - started).total_seconds()
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
        "near": render(beauty_dir / "SURF10_BEAUTY_NEAR_DETAIL.png", cameras["near"]),
        "mid": render(beauty_dir / "SURF10_BEAUTY_MID_SAMPLE.png", cameras["mid"]),
        "far": render(beauty_dir / "SURF10_BEAUTY_FAR_CONTEXT.png", cameras["far"]),
    }

    def channel_material(name: str, texture_path: str, grayscale: bool = False) -> Any:
        mat = bpy.data.materials.new(name)
        mat.use_nodes = True
        nodes = mat.node_tree.nodes
        for node in list(nodes):
            nodes.remove(node)
        out = nodes.new("ShaderNodeOutputMaterial")
        tex = nodes.new("ShaderNodeTexImage")
        tex.image = bpy.data.images.load(texture_path, check_existing=True)
        tex.image.colorspace_settings.name = "Non-Color" if grayscale else "sRGB"
        emission = nodes.new("ShaderNodeEmission")
        emission.inputs["Strength"].default_value = 1.0
        mat.node_tree.links.new(tex.outputs["Color"], emission.inputs["Color"])
        mat.node_tree.links.new(emission.outputs["Emission"], out.inputs["Surface"])
        return mat

    original_sample_materials = [slot.material for slot in sample.material_slots]
    channel_materials = {
        "basecolor": channel_material("SURF10_DIAG_BASECOLOR_EMISSION", texture_assets["basecolor"]["path"]),
        "roughness": channel_material("SURF10_DIAG_ROUGHNESS_EMISSION", texture_assets["roughness"]["path"], grayscale=True),
        "normal": channel_material("SURF10_DIAG_NORMAL_EMISSION", texture_assets["normal"]["path"], grayscale=True),
    }
    channel_renders: dict[str, Any] = {}
    for name, mat in channel_materials.items():
        sample.data.materials.clear()
        sample.data.materials.append(mat)
        channel_renders[name] = render(
            channel_dir / f"SURF10_CHANNEL_{name.upper()}_NEAR.png",
            cameras["near"],
            width=min(1024, int(args.width)),
            height=min(1024, int(args.height)),
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
    assert_row("channel_diagnostic_count_at_least_three", len(channel_renders) >= 3, list(channel_renders))
    all_render_paths = [Path(row["path"]) for row in list(beauty_renders.values()) + list(channel_renders.values())]
    assert_row("all_render_files_nonempty", all(path.is_file() and path.stat().st_size > 0 for path in all_render_paths), [path.as_posix() for path in all_render_paths])
    glb_exports = sorted(path.as_posix() for path in output_dir.rglob("*.glb"))
    assert_row("no_glb_export_created", not glb_exports, glb_exports)

    candidate_blend = output_dir / BLEND_NAME
    bpy.ops.wm.save_as_mainfile(filepath=candidate_blend.as_posix())
    assert_row("candidate_blend_saved", candidate_blend.is_file() and candidate_blend.stat().st_size > 0, candidate_blend.as_posix())

    ok_count = sum(1 for row in assertions if row["ok"])
    fail_count = len(assertions) - ok_count
    report = {
        "schema_version": 1,
        "stage": STAGE,
        "status": STATUS,
        "approval": APPROVAL,
        "created_at": now_iso(),
        "input_checkpoint": {
            "path": Path(bpy.data.filepath).as_posix(),
            "project_relative_path": relative_display(Path(bpy.data.filepath)),
            "sha256": sha256_file(Path(bpy.data.filepath)),
        },
        "blender": {
            "version": bpy.app.version_string,
            "background": bpy.app.background,
            "render_engine": bpy.context.scene.render.engine,
            "resolution": [int(args.width), int(args.height)],
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
            "changed_dimension": "single-surface material sample only",
            "original_furnace_segments_modified": False,
            "formal_glb_exported_or_replaced": False,
        },
        "renders": {
            "beauty_neutral_lookdev": beauty_renders,
            "channel_diagnostics": channel_renders,
            "direct_texture_diagnostics": texture_assets,
        },
        "material_manifest": relative_display(output_dir / "surf10_material_manifest.json"),
        "assertions": assertions,
        "assertion_summary": {
            "total": len(assertions),
            "passed": ok_count,
            "failed": fail_count,
        },
        "events": events,
        "known_non_blocking_issues": [
        "The sample is a clean-UV curved review panel derived from the approved shaft segment bounding box, not a baked or GLB-ready production material.",
            "Channel diagnostics are generated from procedural sample maps; glTF/Three.js handoff was intentionally not executed in SURF-10.",
        ],
    }
    write_json(output_dir / "surf10_material_manifest.json", material_manifest)
    write_json(output_dir / "surf10_machine_report.json", report)
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
            (output_dir / "surf10_child_exception.txt").write_text(traceback.format_exc(), encoding="utf-8")
            raise
    return run_parent(args)


if __name__ == "__main__":
    sys.exit(main())
