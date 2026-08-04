"""Build INT-30 R1B static-pressure overlay candidate for GL02.

Host-side runner and Blender-side stage implementation live in this file.
The stage is intentionally narrow: add 18 measured HMI static-pressure point
markers as neutral cutaway-only evidence, keep prior INT20 geometry untouched,
and stop at the visual/spec review gate.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
DEFAULT_BLENDER = Path(r"D:\Program Files\Blender Foundation\Blender 5.2\blender.exe")
DEFAULT_INPUT = HERE / "work" / "INT_20_20260718_R5" / "INT_20_R5_ANNOTATED_CUTAWAY_CANDIDATE.blend"
DEFAULT_FIXTURE = HERE / "work" / "INT_30_20260718_R1" / "fixtures" / "int30_c1_hmi_snapshot_20260715_104809.json"
DEFAULT_OUTPUT = HERE / "work" / "INT_30_20260718_R1B"
EXPECTED_INPUT_SHA256 = "2f82171b86bad34b6627a98183134607786e253919cf1d2b3a0afc5564da4161"
EXPECTED_FIXTURE_SHA256 = "33cf9b939f3767e8ae4c93a0b31c13dd529546939f2b3d5c6602a2476fbcefac"
FORMAL_GLB = ROOT / "高炉前端数据" / "models" / "gl02_blast_furnace.glb"
EXPECTED_FORMAL_GLB_SHA256 = "808960f1b2703e7fb27df35f1b1b1a17063b9b10d2267acba593fc3872b62af6"
STAGE_ID = "INT-30_R1B"
REQUIREMENT_ID = "REQ-BF3D-INT30-R1B-STATIC-PRESSURE-OVERLAY-20260718"

PROFILE = [
    {"h_m": 0.0, "r_m": 2.05, "zone": "hearth"},
    {"h_m": 4.8, "r_m": 2.35, "zone": "hearth"},
    {"h_m": 8.8, "r_m": 2.95, "zone": "tuyere"},
    {"h_m": 13.8, "r_m": 4.15, "zone": "bosh"},
    {"h_m": 18.6, "r_m": 4.46, "zone": "belly"},
    {"h_m": 24.5, "r_m": 4.05, "zone": "lower_stack"},
    {"h_m": 30.6, "r_m": 3.36, "zone": "upper_stack"},
    {"h_m": 35.2, "r_m": 2.78, "zone": "lower_throat"},
    {"h_m": 37.2, "r_m": 2.42, "zone": "throat"},
    {"h_m": 40.0, "r_m": 2.18, "zone": "top"},
]

INT10_OBJECTS = [
    "APPROX_GL02_INT10_STEEL_SHELL_FULL",
    "APPROX_GL02_INT10_STEEL_SHELL_HALF",
    "APPROX_GL02_INT10_STEEL_SHELL_QUARTER",
    "APPROX_GL02_INT10_COOLING_WALL_FULL",
    "APPROX_GL02_INT10_COOLING_WALL_HALF",
    "APPROX_GL02_INT10_COOLING_WALL_QUARTER",
    "APPROX_GL02_INT10_REFRACTORY_LINING_FULL",
    "APPROX_GL02_INT10_REFRACTORY_LINING_HALF",
    "APPROX_GL02_INT10_REFRACTORY_LINING_QUARTER",
    "APPROX_GL02_INT10_PROCESS_SPACE_FULL",
    "APPROX_GL02_INT10_PROCESS_SPACE_HALF",
    "APPROX_GL02_INT10_PROCESS_SPACE_QUARTER",
]
PROTECTED_SEGMENTS = [
    "APPROX_GL02_FURNACE_HEARTH",
    "APPROX_GL02_FURNACE_BOSH",
    "APPROX_GL02_FURNACE_BELLY",
    "APPROX_GL02_FURNACE_SHAFT",
    "APPROX_GL02_FURNACE_THROAT",
]
PROTECTED_LAYER_GROUPS = [f"GL02_SENSOR_LAYER_L{layer}" for layer in range(7, 17)]
EXPLANATORY_INTERNAL_TOKENS = (
    "burden_column_layered_charge",
    "cohesive_zone_softening_melting_band",
    "countercurrent_gas_flow_streamlines",
    "hot_blast_raceway_plumes",
    "hot_metal_dripping_",
    "hearth_molten_iron_pool",
    "hearth_slag_layer",
    "cold_blast_supply_flow",
    "internal_burden_reference_bands",
    "temp_layer_band_",
)
PRESSURE_MATERIAL = "MI_INT30_R1B_STATIC_PRESSURE_NEUTRAL_STEEL_BLUE"
NO_DATA_MATERIAL = "MI_INT30_R1B_STATIC_PRESSURE_NO_DATA_GRAY"
PRESSURE_RADIUS_M = 0.115
PRESSURE_OBJECT_PREFIX = "GL02_INT30_PRESSURE_"
RENDER_NAMES = [
    "INT30_R1B_FULL_18_CONTEXT.png",
    "INT30_R1B_LOWER_6_CLOSEUP.png",
    "INT30_R1B_MIDDLE_6_CLOSEUP.png",
    "INT30_R1B_UPPER_6_CLOSEUP.png",
    "INT30_R1B_ORIENTATION_PENDING_DIAGNOSTIC.png",
    "INT30_R1B_NO_DATA_GRAY_STATE.png",
    "INT30_R1B_EVIDENCE_LABELS.png",
]


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def canonical_json_sha256(path: Path) -> tuple[str, int]:
    value = json.loads(path.read_text(encoding="utf-8"))
    payload = (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False) + "\n").encode("utf-8")
    return hashlib.sha256(payload).hexdigest(), len(payload)


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def write_text(path: Path, value: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(value, encoding="utf-8")


def now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def rel(path: Path) -> str:
    try:
        return path.resolve().relative_to(ROOT.resolve()).as_posix()
    except ValueError:
        return str(path.resolve())


def interp_profile_radius(height_m: float) -> float:
    points = sorted((float(item["h_m"]), float(item["r_m"])) for item in PROFILE)
    if height_m <= points[0][0]:
        return points[0][1]
    if height_m >= points[-1][0]:
        return points[-1][1]
    for (h0, r0), (h1, r1) in zip(points, points[1:]):
        if h0 <= height_m <= h1:
            t = (height_m - h0) / (h1 - h0)
            return r0 + (r1 - r0) * t
    raise RuntimeError(f"Cannot interpolate profile radius for height {height_m}")


def normalized_pressure_points(fixture_path: Path) -> list[dict[str, Any]]:
    fixture = json.loads(fixture_path.read_text(encoding="utf-8"))
    points = fixture.get("static_pressure", {}).get("points", [])
    if len(points) != 18:
        raise RuntimeError(f"Expected 18 static_pressure points, got {len(points)}")
    normalized: list[dict[str, Any]] = []
    for raw in points:
        variable = str(raw["variable_name"])
        band = variable.split("_")[2].upper()
        position = str(raw["position"]).upper()
        height_m = float(raw["height_m"])
        relative_angle_deg = float(raw["relative_angle_deg"])
        shell_radius_m = interp_profile_radius(height_m)
        placement_radius_m = shell_radius_m + 0.12
        theta = math.radians(relative_angle_deg)
        normalized.append(
            {
                "band": band,
                "position": position,
                "name": f"{PRESSURE_OBJECT_PREFIX}{band}_{position}",
                "variable_name": variable,
                "height_m": height_m,
                "blender_z_m": height_m - 20.0,
                "shell_outer_radius_m": shell_radius_m,
                "placement_radius_m": placement_radius_m,
                "x_m": placement_radius_m * math.cos(theta),
                "y_m": placement_radius_m * math.sin(theta),
                "relative_angle_deg": relative_angle_deg,
                "value_kpa": float(raw["value"]),
                "sample_time": raw.get("sample_time"),
                "driver_id": raw.get("short_name") or variable,
                "hmi_id": raw.get("point_id") or raw.get("tag_long_name") or raw.get("short_name") or variable,
                "tag_long_name": raw.get("tag_long_name"),
                "source_branch": raw.get("source_branch"),
                "evidence": "measured",
                "evidence_detail": "measured_hmi_snapshot",
                "quality": "unverified",
                "orientation_status": "blocked_pending_azimuth_confirmation",
                "azimuth_deg": None,
                "not_cfd": True,
                "not_for_control": True,
                "default_visible": False,
                "cutaway_only": True,
                "unit": "kPa",
            }
        )
    expected = {(band, pos) for band in ("LOWER", "MIDDLE", "UPPER") for pos in "ABCDEF"}
    actual = {(item["band"], item["position"]) for item in normalized}
    if actual != expected:
        raise RuntimeError(f"Static pressure point set mismatch: {sorted(expected - actual)} missing")
    return normalized


def assert_stage_output_dir(path: Path) -> None:
    resolved = path.resolve()
    expected_parent = (HERE / "work").resolve()
    if resolved.name != "INT_30_20260718_R1B" or resolved.parent != expected_parent:
        raise RuntimeError(f"Refusing to write unexpected output directory: {resolved}")


def artifact_manifest(output_dir: Path) -> dict[str, Any]:
    records = []
    for artifact in sorted(path for path in output_dir.rglob("*") if path.is_file()):
        if artifact.name == "artifact_sha256.json":
            continue
        records.append(
            {
                "path": artifact.relative_to(output_dir).as_posix(),
                "bytes": artifact.stat().st_size,
                "sha256": sha256_file(artifact),
            }
        )
    return {
        "schema_version": "bf3d.int30_r1b.artifact_sha256.v1",
        "stage": STAGE_ID,
        "requirement_id": REQUIREMENT_ID,
        "generated_at": now_iso(),
        "artifacts": records,
    }


def host_main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--blender", type=Path, default=DEFAULT_BLENDER)
    parser.add_argument("--input-blend", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--fixture", type=Path, default=DEFAULT_FIXTURE)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--width", type=int, default=1440)
    parser.add_argument("--height", type=int, default=960)
    args = parser.parse_args()

    blender = args.blender.resolve()
    input_blend = args.input_blend.resolve()
    fixture = args.fixture.resolve()
    output_dir = args.output_dir.resolve()
    assert_stage_output_dir(output_dir)

    if not blender.is_file():
        raise FileNotFoundError(blender)
    if not input_blend.is_file():
        raise FileNotFoundError(input_blend)
    if not fixture.is_file():
        raise FileNotFoundError(fixture)

    input_sha = sha256_file(input_blend)
    fixture_byte_sha = sha256_file(fixture)
    fixture_sha, fixture_canonical_bytes = canonical_json_sha256(fixture)
    formal_sha = sha256_file(FORMAL_GLB)
    if input_sha != EXPECTED_INPUT_SHA256:
        raise RuntimeError(f"Input SHA mismatch: {input_sha}")
    if fixture_sha != EXPECTED_FIXTURE_SHA256:
        raise RuntimeError(f"Fixture SHA mismatch: {fixture_sha}")
    if formal_sha != EXPECTED_FORMAL_GLB_SHA256:
        raise RuntimeError(f"Formal GLB SHA mismatch before stage: {formal_sha}")

    if output_dir.exists():
        shutil.rmtree(output_dir)
    (output_dir / "renders").mkdir(parents=True)
    (output_dir / "reports").mkdir(parents=True)

    command = [
        str(blender),
        "--background",
        str(input_blend),
        "--python",
        str(Path(__file__).resolve()),
        "--",
        "--run-blender-stage",
        "--input-blend",
        str(input_blend),
        "--fixture",
        str(fixture),
        "--output-dir",
        str(output_dir),
        "--width",
        str(args.width),
        "--height",
        str(args.height),
    ]
    command_record = {
        "schema_version": "bf3d.int30_r1b.command.v1",
        "stage": STAGE_ID,
        "generated_at": now_iso(),
        "parser_chain": "PowerShell -> subprocess -> blender.exe -> Python bpy",
        "command": command,
        "input_blend": str(input_blend),
        "input_sha256": input_sha,
        "fixture": str(fixture),
        "fixture_byte_sha256": fixture_byte_sha,
        "fixture_canonical_sha256": fixture_sha,
        "fixture_canonical_bytes": fixture_canonical_bytes,
        "formal_glb": str(FORMAL_GLB),
        "formal_glb_sha256": formal_sha,
    }
    write_json(output_dir / "command.json", command_record)

    proc = subprocess.run(command, cwd=str(HERE), capture_output=True, text=True)
    write_text(output_dir / "blender_stdout.log", proc.stdout)
    write_text(output_dir / "blender_stderr.log", proc.stderr)
    if proc.returncode != 0 or "Traceback (most recent call last)" in proc.stderr:
        raise RuntimeError(f"Blender stage failed with {proc.returncode}; see logs in {output_dir}")
    postprocess_host_render_labels(output_dir, fixture)

    candidate = output_dir / "INT_30_R1B_STATIC_PRESSURE_OVERLAY_CANDIDATE.blend"
    reopen_command = [
        str(blender),
        "--background",
        str(candidate),
        "--python",
        str(Path(__file__).resolve()),
        "--",
        "--reopen-validate",
        "--candidate",
        str(candidate),
        "--fixture",
        str(fixture),
        "--output-dir",
        str(output_dir),
    ]
    reopen = subprocess.run(reopen_command, cwd=str(HERE), capture_output=True, text=True)
    write_text(output_dir / "reopen_stdout.log", reopen.stdout)
    write_text(output_dir / "reopen_stderr.log", reopen.stderr)
    if reopen.returncode != 0 or "Traceback (most recent call last)" in reopen.stderr:
        raise RuntimeError(f"Reopen validation failed with {reopen.returncode}; see logs in {output_dir}")

    manifest = artifact_manifest(output_dir)
    write_json(output_dir / "artifact_sha256.json", manifest)
    print(json.dumps({"stage": STAGE_ID, "status": "candidate_ready_for_review", "output": str(output_dir)}, ensure_ascii=False))
    return 0


def postprocess_host_render_labels(output_dir: Path, fixture: Path) -> None:
    points = normalized_pressure_points(fixture)
    for spec in build_render_specs(points):
        overlay_labels(output_dir / "renders" / spec["file"], spec, points)

    render_hashes = {
        spec["file"]: {
            "bytes": (output_dir / "renders" / spec["file"]).stat().st_size,
            "sha256": sha256_file(output_dir / "renders" / spec["file"]),
        }
        for spec in build_render_specs(points)
    }
    for json_path in [output_dir / "int30_r1b_machine_report.json", output_dir / "int30_r1b_visual_manifest.json"]:
        if not json_path.is_file():
            continue
        data = json.loads(json_path.read_text(encoding="utf-8"))
        if "render_policy" in data:
            data["render_policy"]["host_python_pillow_overlay_applied"] = True
        for key in ("evidence_renders", "renders"):
            if key in data:
                for item in data[key]:
                    info = render_hashes.get(item.get("file"))
                    if info:
                        item["bytes"] = info["bytes"]
                        item["sha256"] = info["sha256"]
                        item["labels"] = "host_python_pillow_postprocess_text_overlay"
        write_json(json_path, data)


def blender_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-blender-stage", action="store_true")
    parser.add_argument("--reopen-validate", action="store_true")
    parser.add_argument("--input-blend", type=Path)
    parser.add_argument("--fixture", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--candidate", type=Path)
    parser.add_argument("--width", type=int, default=1440)
    parser.add_argument("--height", type=int, default=960)
    if "--" in sys.argv:
        argv = sys.argv[sys.argv.index("--") + 1 :]
    else:
        argv = []
    return parser.parse_args(argv)


def blender_main() -> int:
    args = blender_args()
    if args.run_blender_stage:
        run_blender_stage(args)
        return 0
    if args.reopen_validate:
        run_reopen_validation(args)
        return 0
    raise RuntimeError("Missing Blender-side mode")


def run_blender_stage(args: argparse.Namespace) -> None:
    import bpy
    from mathutils import Vector

    output_dir = args.output_dir.resolve()
    renders_dir = output_dir / "renders"
    reports_dir = output_dir / "reports"
    candidate = output_dir / "INT_30_R1B_STATIC_PRESSURE_OVERLAY_CANDIDATE.blend"
    points = normalized_pressure_points(args.fixture.resolve())
    source_sig_before = mesh_signature(INT10_OBJECTS)
    sensor_sig_before = sensor_signature()
    body_temp_before = len([obj for obj in bpy.data.objects if obj.name.startswith("SENSOR_T_body_")])
    sensor_count_before = len([obj for obj in bpy.data.objects if obj.name.startswith("SENSOR_")])

    old_hidden_before = hide_old_explanatory_objects()
    for name in INT10_OBJECTS:
        if not bpy.data.objects.get(name):
            raise RuntimeError(f"Missing protected INT10 object: {name}")
    for name in PROTECTED_SEGMENTS + PROTECTED_LAYER_GROUPS:
        if not bpy.data.objects.get(name):
            raise RuntimeError(f"Missing protected object/group: {name}")

    scene = bpy.context.scene
    scene["bf3d_stage"] = STAGE_ID
    try:
        scene.render.engine = "BLENDER_EEVEE_NEXT"
    except TypeError:
        scene.render.engine = "BLENDER_EEVEE"
    scene.render.resolution_x = int(args.width)
    scene.render.resolution_y = int(args.height)
    scene.view_settings.view_transform = "AgX"
    scene.view_settings.look = "AgX - Medium High Contrast"
    scene.view_settings.exposure = 0
    scene.view_settings.gamma = 1
    scene.unit_settings.system = "METRIC"

    root_empty = make_empty("BF3D_INT30_C1_ROOT", None, (0, 0, 0))
    pressure_group = make_empty("GL02_INT30_STATIC_PRESSURE_GROUP", root_empty, (0, 0, 0))
    band_empties = {
        band: make_empty(f"GL02_INT30_STATIC_PRESSURE_{band}_GROUP", pressure_group, (0, 0, 0))
        for band in ("LOWER", "MIDDLE", "UPPER")
    }
    collection = bpy.data.collections.new("INT30_R1B_STATIC_PRESSURE_OVERLAY")
    bpy.context.scene.collection.children.link(collection)
    for empty in [root_empty, pressure_group, *band_empties.values()]:
        link_to_collection(empty, collection)

    pressure_mat = make_principled_material(PRESSURE_MATERIAL, (0.20, 0.74, 0.86, 1.0), roughness=0.48, metallic=0.0, emission_strength=0.85)
    no_data_mat = make_principled_material(NO_DATA_MATERIAL, (0.48, 0.51, 0.52, 1.0), roughness=0.78, metallic=0.0, emission_strength=0.0)
    marker_objects = []
    for item in points:
        bpy.ops.mesh.primitive_ico_sphere_add(subdivisions=2, radius=PRESSURE_RADIUS_M, location=(item["x_m"], item["y_m"], item["blender_z_m"]))
        obj = bpy.context.object
        obj.name = item["name"]
        obj.data.name = f"{item['name']}_MESH"
        obj.parent = band_empties[item["band"]]
        obj.data.materials.append(pressure_mat)
        obj.show_name = True
        obj["bf3d_stage"] = STAGE_ID
        obj["bf3d_role"] = "static_pressure_overlay_point"
        obj["bf3d_extras_json"] = json.dumps(item, ensure_ascii=False, sort_keys=True)
        for key, value in item.items():
            if value is None:
                obj[key] = ""
            elif isinstance(value, (str, int, float, bool)):
                obj[key] = value
        obj["marker_radius_m"] = PRESSURE_RADIUS_M
        link_to_collection(obj, collection)
        marker_objects.append(obj)

    add_lights()
    render_manifest = []
    render_specs = build_render_specs(points)
    for spec in render_specs:
        cam = make_camera(spec["camera"], spec["location"], spec["target"], spec["ortho_scale"])
        scene.camera = cam
        if spec.get("no_data"):
            for obj in marker_objects:
                obj.data.materials.clear()
                obj.data.materials.append(no_data_mat)
        else:
            for obj in marker_objects:
                obj.data.materials.clear()
                obj.data.materials.append(pressure_mat)
        path = renders_dir / spec["file"]
        scene.render.filepath = str(path)
        bpy.ops.render.render(write_still=True)
        overlay_labels(path, spec, points)
        render_manifest.append(
            {
                "id": spec["id"],
                "file": spec["file"],
                "path": str(path),
                "camera": cam.name,
                "projection": "ORTHO",
                "purpose": spec["purpose"],
                "resolution_px": [scene.render.resolution_x, scene.render.resolution_y],
                "labels": "postprocess_text_overlay_render_only",
                "bytes": path.stat().st_size,
                "sha256": sha256_file(path),
            }
        )
        bpy.data.objects.remove(cam, do_unlink=True)
    for obj in marker_objects:
        obj.data.materials.clear()
        obj.data.materials.append(pressure_mat)

    source_sig_after = mesh_signature(INT10_OBJECTS)
    sensor_sig_after = sensor_signature()
    old_hidden_after = hide_old_explanatory_objects()
    object_records = pressure_object_records(marker_objects)
    group_counts = {band: len([item for item in points if item["band"] == band]) for band in ("LOWER", "MIDDLE", "UPPER")}
    material_names = sorted({slot.material.name for obj in marker_objects for slot in obj.material_slots if slot.material})
    radii = [round(math.hypot(obj.location.x, obj.location.y), 6) for obj in marker_objects]
    scales = [tuple(round(float(v), 6) for v in obj.scale[:]) for obj in marker_objects]
    mesh_types = sorted({obj.type for obj in marker_objects})
    output_glbs = list(output_dir.rglob("*.glb"))
    output_blend1 = list(output_dir.rglob("*.blend1"))
    formal_sha_after = sha256_file(FORMAL_GLB)

    assertions = {
        "input_sha256_matches": sha256_file(args.input_blend.resolve()) == EXPECTED_INPUT_SHA256,
        "fixture_sha256_matches": canonical_json_sha256(args.fixture.resolve())[0] == EXPECTED_FIXTURE_SHA256,
        "formal_glb_sha256_unchanged": formal_sha_after == EXPECTED_FORMAL_GLB_SHA256,
        "pressure_object_count_18": len(marker_objects) == 18,
        "group_counts_6_each": group_counts == {"LOWER": 6, "MIDDLE": 6, "UPPER": 6},
        "pressure_names_exact": sorted(obj.name for obj in marker_objects) == sorted(item["name"] for item in points),
        "all_pressure_objects_mesh": mesh_types == ["MESH"],
        "no_curve_torus_cylinder_created": not any(obj.name.startswith(PRESSURE_OBJECT_PREFIX) and obj.type in {"CURVE", "FONT"} for obj in bpy.data.objects),
        "all_same_marker_radius": len({round(float(obj["marker_radius_m"]), 6) for obj in marker_objects}) == 1,
        "all_same_scale": len(set(scales)) == 1,
        "all_same_material": material_names == [PRESSURE_MATERIAL],
        "not_value_scaled": len(set(scales)) == 1 and len({round(float(obj["marker_radius_m"]), 6) for obj in marker_objects}) == 1,
        "coordinates_match_profile_plus_offset": all(record["coordinate_match"] for record in object_records),
        "extras_complete": all(record["extras_complete"] for record in object_records),
        "azimuth_deg_empty": all(record["extras"].get("azimuth_deg") is None for record in object_records),
        "not_cfd_and_not_for_control": all(record["extras"].get("not_cfd") is True and record["extras"].get("not_for_control") is True for record in object_records),
        "default_visible_false_cutaway_only_true": all(record["extras"].get("default_visible") is False and record["extras"].get("cutaway_only") is True for record in object_records),
        "no_nan_in_pressure_records": not contains_nan(object_records),
        "old_55_hidden_preserved": old_hidden_after["hidden_count"] >= 55,
        "old_hidden_count_not_reduced": old_hidden_after["hidden_count"] >= old_hidden_before["hidden_count"],
        "int10_12_objects_present": all(bpy.data.objects.get(name) for name in INT10_OBJECTS),
        "int10_mesh_signature_unchanged": source_sig_before == source_sig_after,
        "sensor_count_115_preserved": len([obj for obj in bpy.data.objects if obj.name.startswith("SENSOR_")]) == 115 and sensor_count_before == 115,
        "body_temperature_80_preserved": len([obj for obj in bpy.data.objects if obj.name.startswith("SENSOR_T_body_")]) == 80 and body_temp_before == 80,
        "sensor_signature_unchanged": sensor_sig_before == sensor_sig_after,
        "l7_l16_groups_present": all(bpy.data.objects.get(name) for name in PROTECTED_LAYER_GROUPS),
        "five_furnace_segments_present": all(bpy.data.objects.get(name) for name in PROTECTED_SEGMENTS),
        "renders_exist": all((renders_dir / name).is_file() and (renders_dir / name).stat().st_size > 1000 for name in RENDER_NAMES),
        "no_output_glb": len(output_glbs) == 0,
        "blend1_not_generated": len(output_blend1) == 0,
        "machine_assertions_pass": False,
    }
    assertions["machine_assertions_pass"] = all(
        bool(value) for key, value in assertions.items() if key != "machine_assertions_pass"
    )
    if not assertions["machine_assertions_pass"]:
        failed = [key for key, value in assertions.items() if not value]
        raise RuntimeError(f"INT-30 R1B assertions failed before save: {failed}")

    visual_manifest = {
        "schema_version": "bf3d.int30_r1b.visual_manifest.v1",
        "stage": STAGE_ID,
        "generated_at": now_iso(),
        "single_changed_dimension": "measured_static_pressure_overlay_only",
        "render_policy": {
            "values_shown_only_in_evidence_labels": True,
            "uniform_marker_scale": True,
            "neutral_material": PRESSURE_MATERIAL,
            "no_risk_coloring": True,
            "no_cfd_claim": True,
            "orientation_note": "relative_angle_deg only; azimuth_deg blocked pending field confirmation",
            "render_text_overlay": "postprocessed bitmap labels only; no Blender text/curve label objects added",
        },
        "renders": render_manifest,
        "pressure_points": points,
    }
    visual_manifest_path = output_dir / "int30_r1b_visual_manifest.json"
    write_json(visual_manifest_path, visual_manifest)

    report = {
        "schema_version": "bf3d.int30_r1b.machine_report.v1",
        "requirement_id": REQUIREMENT_ID,
        "stage": STAGE_ID,
        "status": "candidate_ready_for_review",
        "approval": "not_granted_requires_visual_and_spec_review",
        "generated_at": now_iso(),
        "single_changed_dimension": "static_pressure_overlay_points_only",
        "input": {
            "path": str(args.input_blend.resolve()),
            "expected_sha256": EXPECTED_INPUT_SHA256,
            "actual_sha256": sha256_file(args.input_blend.resolve()),
            "sha256_match": assertions["input_sha256_matches"],
        },
        "fixture": {
            "path": str(args.fixture.resolve()),
            "expected_canonical_sha256": EXPECTED_FIXTURE_SHA256,
            "actual_canonical_sha256": canonical_json_sha256(args.fixture.resolve())[0],
            "canonical_bytes": canonical_json_sha256(args.fixture.resolve())[1],
            "byte_sha256": sha256_file(args.fixture.resolve()),
            "sha256_match": assertions["fixture_sha256_matches"],
            "point_count": len(points),
        },
        "candidate": {
            "path": str(candidate),
            "bytes": None,
            "sha256": None,
        },
        "blender": {
            "version": bpy.app.version_string,
            "binary_path": bpy.app.binary_path,
            "background": bpy.app.background,
            "render_engine": scene.render.engine,
            "render_resolution": [scene.render.resolution_x, scene.render.resolution_y],
        },
        "protected_contract": {
            "sensor_count_before": sensor_count_before,
            "sensor_count_after": len([obj for obj in bpy.data.objects if obj.name.startswith("SENSOR_")]),
            "body_temp_sensor_count_before": body_temp_before,
            "body_temp_sensor_count_after": len([obj for obj in bpy.data.objects if obj.name.startswith("SENSOR_T_body_")]),
            "sensor_signature_before": sensor_sig_before,
            "sensor_signature_after": sensor_sig_after,
            "sensor_names_parents_matrices_unchanged": sensor_sig_before == sensor_sig_after,
            "l7_l16_groups_present": assertions["l7_l16_groups_present"],
            "five_furnace_segments_present": assertions["five_furnace_segments_present"],
            "old_55_explanatory_objects_hidden_count": old_hidden_after["hidden_count"],
            "int10_mesh_signature_before": source_sig_before,
            "int10_mesh_signature_after": source_sig_after,
        },
        "pressure_overlay": {
            "root_empty": "BF3D_INT30_C1_ROOT",
            "group_empty": "GL02_INT30_STATIC_PRESSURE_GROUP",
            "subgroups": [empty.name for empty in band_empties.values()],
            "object_count": len(marker_objects),
            "group_counts": group_counts,
            "material": PRESSURE_MATERIAL,
            "marker_radius_m": PRESSURE_RADIUS_M,
            "records": object_records,
        },
        "visual_manifest": str(visual_manifest_path),
        "evidence_renders": render_manifest,
        "assertions": assertions,
        "known_issues": [
            "Azimuth is blocked pending field confirmation; relative_angle_deg is used only to preserve A-F order.",
            "Values are HMI snapshot evidence labels only, not baseline/risk coloring and not CFD.",
            "No stockline deformation, event animation, gas-flow curves, torus rings, cylinders, GLB export, or production control behavior was created.",
            "Root-level specs/avatar_spec.json and specs/acceptance_checklist.md are absent in this workspace; project-local BF3D contract files were used.",
        ],
        "formal_asset_changes": {
            "formal_glb_exported": False,
            "formal_glb_sha256": formal_sha_after,
            "frontend_modified": False,
            "global_pipeline_status_modified": False,
        },
    }
    report_path = output_dir / "int30_r1b_machine_report.json"
    write_json(report_path, report)
    write_stage_pipeline_status(output_dir, candidate, report_path, visual_manifest_path, formal_sha_after)
    write_summary(output_dir, report)

    bpy.ops.wm.save_as_mainfile(filepath=str(candidate), compress=False)
    report = json.loads(report_path.read_text(encoding="utf-8"))
    report["candidate"]["bytes"] = candidate.stat().st_size
    report["candidate"]["sha256"] = sha256_file(candidate)
    report["execution"] = {
        "finished_at": now_iso(),
        "stdout_log": str(output_dir / "blender_stdout.log"),
        "stderr_log": str(output_dir / "blender_stderr.log"),
        "reopen_stdout_log": str(output_dir / "reopen_stdout.log"),
        "reopen_stderr_log": str(output_dir / "reopen_stderr.log"),
    }
    write_json(report_path, report)
    status_path = output_dir / "reports" / "pipeline_status.json"
    status = json.loads(status_path.read_text(encoding="utf-8"))
    status["stages"][STAGE_ID]["candidate_sha256"] = report["candidate"]["sha256"]
    write_json(status_path, status)


def run_reopen_validation(args: argparse.Namespace) -> None:
    import bpy

    output_dir = args.output_dir.resolve()
    reports_dir = output_dir / "reports"
    points = normalized_pressure_points(args.fixture.resolve())
    expected_names = sorted(item["name"] for item in points)
    marker_objects = [bpy.data.objects[name] for name in expected_names if bpy.data.objects.get(name)]
    records = pressure_object_records(marker_objects)
    group_counts = {
        band: len([obj for obj in marker_objects if obj.name.startswith(f"{PRESSURE_OBJECT_PREFIX}{band}_")])
        for band in ("LOWER", "MIDDLE", "UPPER")
    }
    output_glbs = list(output_dir.rglob("*.glb"))
    output_blend1 = list(output_dir.rglob("*.blend1"))
    validation = {
        "schema_version": "bf3d.int30_r1b.reopen_validation.v1",
        "stage": STAGE_ID,
        "validated_at": now_iso(),
        "candidate_path": str(args.candidate.resolve() if args.candidate else ""),
        "candidate_reopened_without_error": True,
        "candidate_sha256": sha256_file(args.candidate.resolve()) if args.candidate else None,
        "scene_stage": bpy.context.scene.get("bf3d_stage", ""),
        "pressure_object_count": len(marker_objects),
        "pressure_names_exact": sorted(obj.name for obj in marker_objects) == expected_names,
        "group_counts": group_counts,
        "group_counts_6_each": group_counts == {"LOWER": 6, "MIDDLE": 6, "UPPER": 6},
        "all_same_marker_radius": len({round(float(obj.get("marker_radius_m", -1)), 6) for obj in marker_objects}) == 1,
        "all_same_material": sorted({slot.material.name for obj in marker_objects for slot in obj.material_slots if slot.material}) == [PRESSURE_MATERIAL],
        "all_same_scale": len({tuple(round(float(v), 6) for v in obj.scale[:]) for obj in marker_objects}) == 1,
        "not_value_scaled": len({tuple(round(float(v), 6) for v in obj.scale[:]) for obj in marker_objects}) == 1,
        "coordinates_match_profile_plus_offset": all(record["coordinate_match"] for record in records),
        "extras_complete": all(record["extras_complete"] for record in records),
        "sensor_count": len([obj for obj in bpy.data.objects if obj.name.startswith("SENSOR_")]),
        "body_temp_sensor_count": len([obj for obj in bpy.data.objects if obj.name.startswith("SENSOR_T_body_")]),
        "l7_l16_groups_present": all(bpy.data.objects.get(name) for name in PROTECTED_LAYER_GROUPS),
        "int10_12_objects_present": all(bpy.data.objects.get(name) for name in INT10_OBJECTS),
        "old_55_hidden_count": hide_old_explanatory_objects()["hidden_count"],
        "renders_present": {name: (output_dir / "renders" / name).is_file() for name in RENDER_NAMES},
        "no_output_glb": len(output_glbs) == 0,
        "blend1_not_present": len(output_blend1) == 0,
        "formal_glb_sha256_unchanged": sha256_file(FORMAL_GLB) == EXPECTED_FORMAL_GLB_SHA256,
        "no_nan_in_pressure_records": not contains_nan(records),
    }
    validation["status"] = "pass" if all(
        bool(value)
        for key, value in validation.items()
        if key not in {"schema_version", "stage", "validated_at", "candidate_path", "candidate_sha256", "scene_stage", "group_counts", "renders_present", "old_55_hidden_count"}
    ) and all(validation["renders_present"].values()) and validation["old_55_hidden_count"] >= 55 else "fail"
    write_json(output_dir / "reopen_validation.json", validation)
    if validation["status"] != "pass":
        raise RuntimeError(f"Reopen validation failed: {validation}")


def make_empty(name: str, parent: Any, location: tuple[float, float, float]) -> Any:
    import bpy

    existing = bpy.data.objects.get(name)
    if existing:
        raise RuntimeError(f"Refusing to overwrite existing object: {name}")
    empty = bpy.data.objects.new(name, None)
    empty.empty_display_type = "PLAIN_AXES"
    empty.empty_display_size = 0.45
    empty.location = location
    empty.parent = parent
    empty["bf3d_stage"] = STAGE_ID
    bpy.context.scene.collection.objects.link(empty)
    return empty


def link_to_collection(obj: Any, collection: Any) -> None:
    if collection.objects.get(obj.name) is None:
        try:
            collection.objects.link(obj)
        except RuntimeError:
            pass


def make_principled_material(name: str, color: tuple[float, float, float, float], roughness: float, metallic: float, emission_strength: float = 0.0) -> Any:
    import bpy

    mat = bpy.data.materials.get(name)
    if mat is None:
        mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    mat.diffuse_color = color
    if emission_strength > 0:
        mat.node_tree.nodes.clear()
        output = mat.node_tree.nodes.new(type="ShaderNodeOutputMaterial")
        emission = mat.node_tree.nodes.new(type="ShaderNodeEmission")
        emission.inputs["Color"].default_value = color
        emission.inputs["Strength"].default_value = emission_strength
        mat.node_tree.links.new(emission.outputs["Emission"], output.inputs["Surface"])
        mat["bf3d_stage"] = STAGE_ID
        mat["emission_strength"] = emission_strength
        mat["marker_color_contract"] = "uniform neutral steel-blue/cyan-gray; no value/risk encoding"
        mat["no_value_encoding"] = True
        return mat
    bsdf = mat.node_tree.nodes.get("Principled BSDF")
    if bsdf:
        if "Base Color" in bsdf.inputs:
            bsdf.inputs["Base Color"].default_value = color
        if "Roughness" in bsdf.inputs:
            bsdf.inputs["Roughness"].default_value = roughness
        if "Metallic" in bsdf.inputs:
            bsdf.inputs["Metallic"].default_value = metallic
        if "Emission Color" in bsdf.inputs:
            bsdf.inputs["Emission Color"].default_value = color
        if "Emission Strength" in bsdf.inputs:
            bsdf.inputs["Emission Strength"].default_value = emission_strength
    mat["bf3d_stage"] = STAGE_ID
    mat["no_value_encoding"] = True
    return mat


def add_lights() -> None:
    import bpy

    bpy.ops.object.light_add(type="AREA", location=(0, -7, 14))
    key = bpy.context.object
    key.name = "INT30_R1B_RENDER_ONLY_KEY_AREA"
    key.data.energy = 460
    key.data.size = 6.5
    key["render_only"] = True
    bpy.ops.object.light_add(type="AREA", location=(-5, 5, 9))
    fill = bpy.context.object
    fill.name = "INT30_R1B_RENDER_ONLY_FILL_AREA"
    fill.data.energy = 120
    fill.data.size = 9
    fill["render_only"] = True


def look_at(obj: Any, target: tuple[float, float, float]) -> None:
    from mathutils import Vector

    direction = Vector(target) - obj.location
    obj.rotation_euler = direction.to_track_quat("-Z", "Y").to_euler()


def make_camera(name: str, location: tuple[float, float, float], target: tuple[float, float, float], ortho_scale: float) -> Any:
    import bpy

    bpy.ops.object.camera_add(location=location)
    cam = bpy.context.object
    cam.name = name
    cam.data.name = f"{name}_DATA"
    cam.data.type = "ORTHO"
    cam.data.ortho_scale = ortho_scale
    look_at(cam, target)
    cam["render_only"] = True
    return cam


def build_render_specs(points: list[dict[str, Any]]) -> list[dict[str, Any]]:
    z_by_band = {band: sum(item["blender_z_m"] for item in points if item["band"] == band) / 6.0 for band in ("LOWER", "MIDDLE", "UPPER")}
    return [
        {
            "id": "FULL_18_CONTEXT",
            "file": "INT30_R1B_FULL_18_CONTEXT.png",
            "camera": "INT30_R1B_CAM_FULL_CONTEXT_ORTHO",
            "location": (9.5, -16.0, 13.0),
            "target": (0, 0, 2.8),
            "ortho_scale": 26.0,
            "purpose": "full_furnace_context_all_18_static_pressure_points",
            "title": "INT-30 R1B 全炉18点静压力覆盖 / HMI snapshot, relative orientation, non-CFD",
            "subtitle": "18 independent points; uniform neutral material; values only in evidence labels",
        },
        {
            "id": "LOWER_6_CLOSEUP",
            "file": "INT30_R1B_LOWER_6_CLOSEUP.png",
            "camera": "INT30_R1B_CAM_LOWER_CLOSEUP_ORTHO",
            "location": (0, -13.0, z_by_band["LOWER"] + 3.4),
            "target": (0, 0, z_by_band["LOWER"]),
            "ortho_scale": 13.8,
            "purpose": "lower_level_a_to_f_closeup",
            "band": "LOWER",
            "title": "LOWER 20.350m / HMI快照 / 相对方位示意 / 非CFD",
            "subtitle": "Same size, same material; azimuth blocked pending confirmation",
        },
        {
            "id": "MIDDLE_6_CLOSEUP",
            "file": "INT30_R1B_MIDDLE_6_CLOSEUP.png",
            "camera": "INT30_R1B_CAM_MIDDLE_CLOSEUP_ORTHO",
            "location": (0, -13.0, z_by_band["MIDDLE"] + 3.4),
            "target": (0, 0, z_by_band["MIDDLE"]),
            "ortho_scale": 13.2,
            "purpose": "middle_level_a_to_f_closeup",
            "band": "MIDDLE",
            "title": "MIDDLE 23.488m / HMI快照 / 相对方位示意 / 非CFD",
            "subtitle": "Relative A-F order only; no risk coloring",
        },
        {
            "id": "UPPER_6_CLOSEUP",
            "file": "INT30_R1B_UPPER_6_CLOSEUP.png",
            "camera": "INT30_R1B_CAM_UPPER_CLOSEUP_ORTHO",
            "location": (0, -12.0, z_by_band["UPPER"] + 3.4),
            "target": (0, 0, z_by_band["UPPER"]),
            "ortho_scale": 12.4,
            "purpose": "upper_level_a_to_f_closeup",
            "band": "UPPER",
            "title": "UPPER 28.976m / HMI快照 / 相对方位示意 / 非CFD",
            "subtitle": "Uniform neutral steel-blue markers; values are evidence only",
        },
        {
            "id": "ORIENTATION_PENDING_DIAGNOSTIC",
            "file": "INT30_R1B_ORIENTATION_PENDING_DIAGNOSTIC.png",
            "camera": "INT30_R1B_CAM_ORIENTATION_PENDING_TOP_ORTHO",
            "location": (0, 0, 36),
            "target": (0, 0, 4.5),
            "ortho_scale": 15.0,
            "purpose": "topdown_relative_angle_diagnostic_pending_real_azimuth",
            "title": "方位待确认诊断图 / Relative orientation only",
            "subtitle": "A-F use fixture relative_angle_deg; azimuth_deg is empty; not for control",
        },
        {
            "id": "NO_DATA_GRAY_STATE",
            "file": "INT30_R1B_NO_DATA_GRAY_STATE.png",
            "camera": "INT30_R1B_CAM_NO_DATA_GRAY_ORTHO",
            "location": (8, -14, 12),
            "target": (0, 0, 3.0),
            "ortho_scale": 18.0,
            "purpose": "no_data_gray_state_no_nan_no_risk_coloring",
            "title": "No-data 灰态示意 / no baseline, no NaN, non-CFD",
            "subtitle": "Gray state is visual fallback only; source extras keep measured HMI snapshot",
            "no_data": True,
        },
        {
            "id": "EVIDENCE_LABELS",
            "file": "INT30_R1B_EVIDENCE_LABELS.png",
            "camera": "INT30_R1B_CAM_EVIDENCE_LABELS_ORTHO",
            "location": (10, -16, 11.5),
            "target": (0, 0, 3.5),
            "ortho_scale": 16.0,
            "purpose": "evidence_label_context_values_not_encoded_as_scale_or_risk",
            "title": "证据标签 / values shown only as HMI snapshot text",
            "subtitle": "quality=unverified; default_visible=false; cutaway_only=true; not_for_control",
            "label_all_values": True,
        },
    ]


def overlay_labels(path: Path, spec: dict[str, Any], points: list[dict[str, Any]]) -> None:
    try:
        from PIL import Image, ImageDraw, ImageFont
    except Exception:
        return

    img = Image.open(path).convert("RGBA")
    draw = ImageDraw.Draw(img, "RGBA")
    width, height = img.size
    font_big = load_font(30)
    font_med = load_font(22)
    font_small = load_font(17)
    draw.rectangle([0, 0, width, 86], fill=(13, 22, 28, 188))
    draw.text((24, 14), spec["title"], font=font_big, fill=(238, 248, 250, 255))
    draw.text((24, 52), spec["subtitle"], font=font_med, fill=(186, 215, 218, 255))
    footer = "HMI快照 2026-07-15 10:48:09+08:00 | 相对方位示意 | 非CFD | 不用于控制"
    draw.rectangle([0, height - 48, width, height], fill=(13, 22, 28, 178))
    draw.text((24, height - 35), footer, font=font_med, fill=(225, 234, 232, 255))
    band_points = points
    if spec.get("band"):
        band_points = [item for item in points if item["band"] == spec["band"]]
    if spec["id"] == "ORIENTATION_PENDING_DIAGNOSTIC":
        band_points = [item for item in points if item["band"] == "LOWER"]
    if spec.get("band") or spec["id"] == "ORIENTATION_PENDING_DIAGNOSTIC":
        rows = []
        for item in band_points:
            if spec["id"] == "ORIENTATION_PENDING_DIAGNOSTIC":
                rows.append(f"{item['position']}: rel {item['relative_angle_deg']:.0f} deg / azimuth empty")
            elif spec.get("band"):
                rows.append(f"{item['position']} {item['value_kpa']:.1f} kPa")
            else:
                rows.append(f"{item['band']} {item['position']}: {item['value_kpa']:.1f} kPa ({item['driver_id']})")
        x0 = width - 560
        y0 = 104
        row_h = 31 if spec.get("band") else 24
        panel_h = min(height - 170, 42 + row_h * len(rows))
        draw.rounded_rectangle([x0 - 16, y0 - 12, width - 24, y0 - 12 + panel_h], radius=8, fill=(5, 15, 19, 224), outline=(126, 204, 214, 230), width=2)
        heading = "A-F values / A-F数值" if spec.get("band") else "Evidence labels / 证据标签"
        if spec["id"] == "ORIENTATION_PENDING_DIAGNOSTIC":
            heading = "A-F relative order / 相对顺序"
        draw.text((x0, y0), heading, font=font_med, fill=(238, 252, 250, 255))
        for idx, row in enumerate(rows[: int((panel_h - 34) / row_h)]):
            y = y0 + 38 + idx * row_h
            if spec.get("band"):
                draw.rounded_rectangle([x0 - 2, y - 4, x0 + 210, y + 23], radius=5, fill=(20, 65, 74, 210))
                draw.text((x0 + 8, y), row, font=font_med, fill=(232, 252, 252, 255))
            else:
                draw.text((x0, y), row, font=font_small, fill=(214, 236, 236, 255))
    if spec.get("label_all_values"):
        draw_expanded_evidence_table(draw, points, width, height, font_med, font_small)
    if spec.get("no_data"):
        draw.rounded_rectangle([24, 104, 540, 190], radius=8, fill=(28, 31, 32, 178), outline=(150, 154, 154, 180), width=1)
        draw.text((44, 122), "No-data gray fallback", font=font_med, fill=(232, 235, 234, 255))
        draw.text((44, 154), "No NaN, no baseline risk color, no value scaling", font=font_small, fill=(214, 220, 219, 255))
    img.convert("RGB").save(path)


def draw_expanded_evidence_table(draw: Any, points: list[dict[str, Any]], width: int, height: int, font_med: Any, font_small: Any) -> None:
    left = 34
    top = 108
    col_w = 320
    row_h = 30
    band_titles = {
        "LOWER": "LOWER 20.350m",
        "MIDDLE": "MIDDLE 23.488m",
        "UPPER": "UPPER 28.976m",
    }
    draw.rounded_rectangle([left - 14, top - 18, left + col_w * 3 + 34, top + 254], radius=8, fill=(4, 13, 17, 226), outline=(124, 205, 216, 230), width=2)
    draw.text((left, top - 8), "3 levels x 6 points = 18 independent static pressure markers", font=font_med, fill=(240, 253, 252, 255))
    for ci, band in enumerate(("LOWER", "MIDDLE", "UPPER")):
        x = left + ci * col_w
        y = top + 34
        draw.rounded_rectangle([x, y, x + 285, y + 28], radius=5, fill=(18, 66, 77, 230))
        draw.text((x + 10, y + 5), band_titles[band], font=font_small, fill=(235, 252, 252, 255))
        for ri, item in enumerate([p for p in points if p["band"] == band]):
            yy = y + 36 + ri * row_h
            label = f"{item['position']} {item['value_kpa']:.1f} kPa"
            draw.text((x + 12, yy), label, font=font_med, fill=(225, 249, 250, 255))
            draw.text((x + 142, yy + 3), f"rel {item['relative_angle_deg']:.0f} deg", font=font_small, fill=(177, 210, 212, 255))


def load_font(size: int) -> Any:
    from PIL import ImageFont

    candidates = [
        Path(r"C:\Windows\Fonts\simsun.ttc"),
        Path(r"C:\Windows\Fonts\simhei.ttf"),
        Path(r"C:\Windows\Fonts\arial.ttf"),
    ]
    for candidate in candidates:
        if candidate.is_file():
            try:
                return ImageFont.truetype(str(candidate), size)
            except Exception:
                pass
    return ImageFont.load_default()


def mesh_signature(names: list[str]) -> str:
    import bpy

    payload = []
    for name in names:
        obj = bpy.data.objects.get(name)
        if obj is None:
            payload.append({"name": name, "missing": True})
            continue
        mesh = obj.data
        payload.append(
            {
                "name": obj.name,
                "type": obj.type,
                "parent": obj.parent.name if obj.parent else None,
                "matrix_world": [round(float(v), 7) for row in obj.matrix_world for v in row],
                "vertices": len(mesh.vertices) if mesh else None,
                "edges": len(mesh.edges) if mesh else None,
                "polygons": len(mesh.polygons) if mesh else None,
                "materials": [slot.material.name if slot.material else None for slot in obj.material_slots],
            }
        )
    return hashlib.sha256(json.dumps(payload, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()


def sensor_signature() -> str:
    import bpy

    payload = []
    for obj in sorted((obj for obj in bpy.data.objects if obj.name.startswith("SENSOR_")), key=lambda item: item.name):
        payload.append(
            {
                "name": obj.name,
                "parent": obj.parent.name if obj.parent else None,
                "matrix_world": [round(float(v), 7) for row in obj.matrix_world for v in row],
            }
        )
    return hashlib.sha256(json.dumps(payload, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()


def hide_old_explanatory_objects() -> dict[str, Any]:
    import bpy

    matched = []
    hidden = []
    for obj in bpy.data.objects:
        lower_name = obj.name.lower()
        if any(token in lower_name for token in EXPLANATORY_INTERNAL_TOKENS):
            matched.append(obj.name)
            obj.hide_render = True
            obj.hide_viewport = True
            hidden.append(obj.name)
    return {"matched_count": len(matched), "hidden_count": len(hidden), "hidden_names": sorted(hidden)}


def pressure_object_records(marker_objects: list[Any]) -> list[dict[str, Any]]:
    records = []
    required = {
        "driver_id",
        "hmi_id",
        "value_kpa",
        "sample_time",
        "evidence",
        "evidence_detail",
        "quality",
        "orientation_status",
        "relative_angle_deg",
        "azimuth_deg",
        "not_cfd",
        "not_for_control",
        "default_visible",
        "cutaway_only",
    }
    for obj in sorted(marker_objects, key=lambda item: item.name):
        extras = json.loads(obj.get("bf3d_extras_json", "{}"))
        expected_radius = float(extras.get("placement_radius_m", -999))
        expected_z = float(extras.get("blender_z_m", -999))
        actual_radius = math.hypot(float(obj.location.x), float(obj.location.y))
        records.append(
            {
                "name": obj.name,
                "type": obj.type,
                "parent": obj.parent.name if obj.parent else None,
                "location_xyz_m": [round(float(obj.location.x), 6), round(float(obj.location.y), 6), round(float(obj.location.z), 6)],
                "actual_radius_m": round(actual_radius, 6),
                "expected_radius_m": round(expected_radius, 6),
                "expected_blender_z_m": round(expected_z, 6),
                "coordinate_match": abs(actual_radius - expected_radius) < 1e-5 and abs(float(obj.location.z) - expected_z) < 1e-5,
                "scale": [round(float(v), 6) for v in obj.scale[:]],
                "marker_radius_m": round(float(obj.get("marker_radius_m", -1)), 6),
                "materials": [slot.material.name if slot.material else None for slot in obj.material_slots],
                "extras_complete": required.issubset(extras.keys()),
                "extras_missing": sorted(required - set(extras.keys())),
                "extras": extras,
            }
        )
    return records


def contains_nan(value: Any) -> bool:
    if isinstance(value, float):
        return math.isnan(value) or math.isinf(value)
    if isinstance(value, dict):
        return any(contains_nan(item) for item in value.values())
    if isinstance(value, list):
        return any(contains_nan(item) for item in value)
    return False


def write_stage_pipeline_status(output_dir: Path, candidate: Path, report_path: Path, visual_manifest_path: Path, formal_sha: str) -> None:
    status = {
        "schema_version": 1,
        "updated_at": now_iso(),
        "current_stage": STAGE_ID,
        "stages": {
            STAGE_ID: {
                "status": "candidate_ready_for_review",
                "approval": "not_granted_requires_visual_and_spec_review",
                "candidate_blend": rel(candidate),
                "candidate_sha256": None,
                "input_blend": rel(DEFAULT_INPUT),
                "input_sha256": EXPECTED_INPUT_SHA256,
                "fixture": rel(DEFAULT_FIXTURE),
                "fixture_sha256": EXPECTED_FIXTURE_SHA256,
                "machine_report": rel(report_path),
                "visual_manifest": rel(visual_manifest_path),
                "summary": rel(output_dir / "INT-30_R1B_阶段成果总结.md"),
                "formal_glb_unchanged": True,
                "formal_glb_sha256": formal_sha,
                "next_stop_line": "independent_visual_and_spec_review_required_before_any_next_stage",
            }
        },
    }
    write_json(output_dir / "reports" / "pipeline_status.json", status)


def write_summary(output_dir: Path, report: dict[str, Any]) -> None:
    lines = [
        "# INT-30_R1B 阶段成果总结",
        "",
        f"- 阶段：`{STAGE_ID}`",
        "- 状态：`candidate_ready_for_review`，停在独立视觉/规格审核门。",
        f"- 输入候选：`{rel(Path(report['input']['path']))}`",
        f"- 输入 SHA：`{report['input']['actual_sha256']}`",
        f"- Fixture：`{rel(Path(report['fixture']['path']))}`",
        f"- Fixture canonical SHA：`{report['fixture']['actual_canonical_sha256']}`",
        f"- Fixture byte SHA：`{report['fixture']['byte_sha256']}`",
        "- 本阶段只新增 18 个独立静压力覆盖点，lower/middle/upper 各 6 个；未创建汇总点。",
        "- 点对象命名：`GL02_INT30_PRESSURE_{LOWER|MIDDLE|UPPER}_{A..F}`，父级为 `BF3D_INT30_C1_ROOT / GL02_INT30_STATIC_PRESSURE_GROUP`。",
        "- 坐标：`Blender Z = height_m - 20`；半径为 INT10 source profile 钢壳外半径插值值 + `0.12m`；A-F 仅使用 fixture `relative_angle_deg` 保持相对顺序。",
        "- 视觉策略：所有点同尺寸、同中性钢蓝/青灰材质；不按值缩放，不做风险着色；数值只出现在证据标签。",
        "- 安全合同：`azimuth_deg=null`、`orientation_status=blocked_pending_azimuth_confirmation`、`not_cfd=true`、`not_for_control=true`、`default_visible=false`、`cutaway_only=true`。",
        f"- 候选 blend：`{rel(DEFAULT_OUTPUT / 'INT_30_R1B_STATIC_PRESSURE_OVERLAY_CANDIDATE.blend')}`",
        f"- 机器报告：`{rel(output_dir / 'int30_r1b_machine_report.json')}`",
        f"- 视觉清单：`{rel(output_dir / 'int30_r1b_visual_manifest.json')}`",
        f"- Reopen 校验：`{rel(output_dir / 'reopen_validation.json')}`",
        f"- Artifact SHA：`{rel(output_dir / 'artifact_sha256.json')}`",
        f"- 阶段本地 pipeline_status：`{rel(output_dir / 'reports' / 'pipeline_status.json')}`",
        "",
        "## 证据图",
    ]
    for item in report["evidence_renders"]:
        lines.append(f"- `{item['file']}`：{item['purpose']}")
    lines.extend(
        [
            "",
            "## 门禁",
            f"- 18 对象断言：`{report['assertions']['pressure_object_count_18']}`",
            f"- 每组 6 点：`{report['assertions']['group_counts_6_each']}`",
            f"- 坐标/半径：`{report['assertions']['coordinates_match_profile_plus_offset']}`",
            f"- 同尺度同材质且不按值缩放：`{report['assertions']['all_same_scale'] and report['assertions']['all_same_material'] and report['assertions']['not_value_scaled']}`",
            f"- extras 完整：`{report['assertions']['extras_complete']}`",
            f"- 旧 55 解释对象隐藏：`{report['assertions']['old_55_hidden_preserved']}`",
            f"- 12 个 INT10 实体签名不变：`{report['assertions']['int10_mesh_signature_unchanged']}`",
            f"- 115/80 传感器保护：`{report['assertions']['sensor_count_115_preserved'] and report['assertions']['body_temperature_80_preserved']}`",
            f"- L7-L16 保留：`{report['assertions']['l7_l16_groups_present']}`",
            f"- no-data 无 NaN：`{report['assertions']['no_nan_in_pressure_records']}`",
            f"- 未生成 .blend1/.glb：`{report['assertions']['blend1_not_generated'] and report['assertions']['no_output_glb']}`",
            f"- 正式 GLB SHA 不变：`{report['assertions']['formal_glb_sha256_unchanged']}`",
        ]
    )
    write_text(output_dir / "INT-30_R1B_阶段成果总结.md", "\n".join(lines) + "\n")


if __name__ == "__main__":
    if "--run-blender-stage" in sys.argv or "--reopen-validate" in sys.argv:
        raise SystemExit(blender_main())
    raise SystemExit(host_main())
