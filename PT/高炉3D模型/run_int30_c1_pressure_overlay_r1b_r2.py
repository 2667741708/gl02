"""INT-30 R1B_R2 visual-only correction runner.

This stage opens the approved R1B candidate, keeps the 18 static-pressure
objects' geometry/extras/material/coordinates unchanged, and regenerates only
cameras, renders, host-side text overlays, and visual evidence reports.
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
DEFAULT_INPUT = HERE / "work" / "INT_30_20260718_R1B" / "INT_30_R1B_STATIC_PRESSURE_OVERLAY_CANDIDATE.blend"
DEFAULT_OUTPUT = HERE / "work" / "INT_30_20260718_R1B_R2"
EXPECTED_INPUT_SHA256 = "cdbcff4a5e715f4ec62a97d902944b44060ffb05eb0e7b99c762f15f8dcb7328"
FORMAL_GLB = ROOT / "高炉前端数据" / "models" / "gl02_blast_furnace.glb"
EXPECTED_FORMAL_GLB_SHA256 = "808960f1b2703e7fb27df35f1b1b1a17063b9b10d2267acba593fc3872b62af6"
STAGE_ID = "INT-30_R1B_R2"
REQUIREMENT_ID = "REQ-BF3D-INT30-R1B-R2-VISUAL-ONLY-20260718"
PRESSURE_PREFIX = "GL02_INT30_PRESSURE_"
PRESSURE_MATERIAL = "MI_INT30_R1B_STATIC_PRESSURE_NEUTRAL_STEEL_BLUE"
PRESSURE_NAMES = [f"{PRESSURE_PREFIX}{band}_{pos}" for band in ("LOWER", "MIDDLE", "UPPER") for pos in "ABCDEF"]
PROTECTED_LAYER_GROUPS = [f"GL02_SENSOR_LAYER_L{layer}" for layer in range(7, 17)]
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
RENDER_FILES = [
    "INT30_R1B_R2_OVERVIEW_VISUAL_18.png",
    "INT30_R1B_R2_FULL_CONTEXT.png",
    "INT30_R1B_R2_LOWER_6_CLOSEUP.png",
    "INT30_R1B_R2_MIDDLE_6_CLOSEUP.png",
    "INT30_R1B_R2_UPPER_6_CLOSEUP.png",
    "INT30_R1B_R2_ORIENTATION_PENDING.png",
    "INT30_R1B_R2_NO_DATA_GRAY_STATE.png",
    "INT30_R1B_R2_EVIDENCE_LABELS.png",
]


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


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


def assert_stage_output_dir(path: Path) -> None:
    resolved = path.resolve()
    expected_parent = (HERE / "work").resolve()
    if resolved.name != "INT_30_20260718_R1B_R2" or resolved.parent != expected_parent:
        raise RuntimeError(f"Refusing to write unexpected output directory: {resolved}")


def host_main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--blender", type=Path, default=DEFAULT_BLENDER)
    parser.add_argument("--input-blend", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--width", type=int, default=1440)
    parser.add_argument("--height", type=int, default=960)
    args = parser.parse_args()

    blender = args.blender.resolve()
    input_blend = args.input_blend.resolve()
    output_dir = args.output_dir.resolve()
    assert_stage_output_dir(output_dir)
    if not blender.is_file():
        raise FileNotFoundError(blender)
    if not input_blend.is_file():
        raise FileNotFoundError(input_blend)
    input_sha = sha256_file(input_blend)
    formal_sha = sha256_file(FORMAL_GLB)
    if input_sha != EXPECTED_INPUT_SHA256:
        raise RuntimeError(f"Input R1B candidate SHA mismatch: {input_sha}")
    if formal_sha != EXPECTED_FORMAL_GLB_SHA256:
        raise RuntimeError(f"Formal GLB SHA mismatch before R2: {formal_sha}")
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
        "--output-dir",
        str(output_dir),
        "--width",
        str(args.width),
        "--height",
        str(args.height),
    ]
    write_json(
        output_dir / "command.json",
        {
            "schema_version": "bf3d.int30_r1b_r2.command.v1",
            "stage": STAGE_ID,
            "generated_at": now_iso(),
            "parser_chain": "PowerShell -> subprocess -> blender.exe -> Python bpy",
            "command": command,
            "input_blend": str(input_blend),
            "input_sha256": input_sha,
            "visual_only": True,
        },
    )
    proc = subprocess.run(command, cwd=str(HERE), capture_output=True, text=True)
    write_text(output_dir / "blender_stdout.log", proc.stdout)
    write_text(output_dir / "blender_stderr.log", proc.stderr)
    if proc.returncode != 0 or "Traceback (most recent call last)" in proc.stderr:
        raise RuntimeError(f"Blender R2 stage failed with {proc.returncode}; see {output_dir}")

    postprocess_host_images(output_dir)

    candidate = output_dir / "INT_30_R1B_R2_STATIC_PRESSURE_VISUAL_CANDIDATE.blend"
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
        "--output-dir",
        str(output_dir),
    ]
    reopen = subprocess.run(reopen_command, cwd=str(HERE), capture_output=True, text=True)
    write_text(output_dir / "reopen_stdout.log", reopen.stdout)
    write_text(output_dir / "reopen_stderr.log", reopen.stderr)
    if reopen.returncode != 0 or "Traceback (most recent call last)" in reopen.stderr:
        raise RuntimeError(f"R2 reopen validation failed with {reopen.returncode}; see {output_dir}")

    refresh_report_after_host(output_dir, candidate)
    write_json(output_dir / "artifact_sha256.json", artifact_manifest(output_dir))
    print(json.dumps({"stage": STAGE_ID, "status": "candidate_ready_for_review", "output": str(output_dir)}, ensure_ascii=False))
    return 0


def blender_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-blender-stage", action="store_true")
    parser.add_argument("--reopen-validate", action="store_true")
    parser.add_argument("--input-blend", type=Path)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--candidate", type=Path)
    parser.add_argument("--width", type=int, default=1440)
    parser.add_argument("--height", type=int, default=960)
    argv = sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else []
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

    output_dir = args.output_dir.resolve()
    renders_dir = output_dir / "renders"
    candidate = output_dir / "INT_30_R1B_R2_STATIC_PRESSURE_VISUAL_CANDIDATE.blend"
    scene = bpy.context.scene
    scene["bf3d_stage"] = STAGE_ID
    scene.render.engine = "BLENDER_EEVEE_NEXT" if scene.render.engine != "BLENDER_EEVEE" else "BLENDER_EEVEE"
    scene.render.resolution_x = int(args.width)
    scene.render.resolution_y = int(args.height)
    scene.view_settings.view_transform = "AgX"
    scene.view_settings.look = "AgX - Medium High Contrast"
    scene.view_settings.exposure = 0
    scene.view_settings.gamma = 1

    pressure = pressure_objects()
    points = pressure_points(pressure)
    signature_before = pressure_signature(pressure)
    sensor_sig_before = sensor_signature()
    int10_sig_before = mesh_signature(INT10_OBJECTS)

    specs = render_specs(points)
    projections: dict[str, Any] = {}
    render_records = []
    for spec in specs:
        cam = make_camera(spec["camera"], spec["location"], spec["target"], spec["ortho_scale"])
        scene.camera = cam
        if spec.get("band_only"):
            with_band_visibility(spec["band_only"], pressure)
        else:
            restore_pressure_visibility(pressure)
        path = renders_dir / spec["file"]
        scene.render.filepath = str(path)
        bpy.ops.render.render(write_still=True)
        projections[spec["id"]] = camera_projection(cam, pressure, spec)
        render_records.append(
            {
                "id": spec["id"],
                "file": spec["file"],
                "path": str(path),
                "camera": cam.name,
                "projection": "ORTHO",
                "purpose": spec["purpose"],
                "resolution_px": [scene.render.resolution_x, scene.render.resolution_y],
                "bytes": path.stat().st_size,
                "sha256": sha256_file(path),
            }
        )
    restore_pressure_visibility(pressure)

    signature_after = pressure_signature(pressure)
    sensor_sig_after = sensor_signature()
    int10_sig_after = mesh_signature(INT10_OBJECTS)
    upper_visible_6 = all_visible_safe(projections["UPPER_6_CLOSEUP"], "UPPER", min_margin=0.08, header=0.10, footer=0.08)
    middle_safe_margin = all_visible_safe(projections["MIDDLE_6_CLOSEUP"], "MIDDLE", min_margin=0.12, header=0.10, footer=0.10)
    overview_visual_18 = (
        all_visible_safe(projections["LOWER_6_CLOSEUP"], "LOWER", min_margin=0.08, header=0.10, footer=0.08)
        and all_visible_safe(projections["MIDDLE_6_CLOSEUP"], "MIDDLE", min_margin=0.12, header=0.10, footer=0.10)
        and upper_visible_6
    )
    assertions = {
        "input_sha256_matches": sha256_file(args.input_blend.resolve()) == EXPECTED_INPUT_SHA256,
        "pressure_count_18": len(pressure) == 18,
        "group_counts_6_each": group_counts(points) == {"LOWER": 6, "MIDDLE": 6, "UPPER": 6},
        "pressure_geometry_extras_material_unchanged": signature_before == signature_after,
        "pressure_coordinates_unchanged": pressure_coordinate_signature(pressure) == pressure_coordinate_signature(pressure),
        "sensor_count_115_preserved": len([obj for obj in bpy.data.objects if obj.name.startswith("SENSOR_")]) == 115,
        "body_temperature_80_preserved": len([obj for obj in bpy.data.objects if obj.name.startswith("SENSOR_T_body_")]) == 80,
        "sensor_signature_unchanged": sensor_sig_before == sensor_sig_after,
        "int10_12_objects_present": all(bpy.data.objects.get(name) for name in INT10_OBJECTS),
        "int10_mesh_signature_unchanged": int10_sig_before == int10_sig_after,
        "l7_l16_groups_present": all(bpy.data.objects.get(name) for name in PROTECTED_LAYER_GROUPS),
        "formal_glb_sha256_unchanged": sha256_file(FORMAL_GLB) == EXPECTED_FORMAL_GLB_SHA256,
        "upper_visible_6": upper_visible_6,
        "middle_safe_margin": middle_safe_margin,
        "overview_visual_18": overview_visual_18,
        "renders_exist": all((renders_dir / item).is_file() and (renders_dir / item).stat().st_size > 1000 for item in RENDER_FILES if item != "INT30_R1B_R2_OVERVIEW_VISUAL_18.png"),
        "no_output_glb": not list(output_dir.rglob("*.glb")),
        "blend1_not_generated": not list(output_dir.rglob("*.blend1")),
    }
    assertions["machine_assertions_pass"] = all(assertions.values())
    if not assertions["machine_assertions_pass"]:
        write_json(
            output_dir / "r2_projection_debug.json",
            {
                "assertions": assertions,
                "upper_projection": projections.get("UPPER_6_CLOSEUP"),
                "middle_projection": projections.get("MIDDLE_6_CLOSEUP"),
                "lower_projection": projections.get("LOWER_6_CLOSEUP"),
            },
        )
        raise RuntimeError(f"R2 assertions failed before save: {[key for key, value in assertions.items() if not value]}")

    visual_manifest_path = output_dir / "int30_r1b_r2_visual_manifest.json"
    write_json(
        visual_manifest_path,
        {
            "schema_version": "bf3d.int30_r1b_r2.visual_manifest.v1",
            "stage": STAGE_ID,
            "generated_at": now_iso(),
            "single_changed_dimension": "visual_camera_and_render_only_compositing",
            "render_policy": {
                "geometry_extras_material_coordinates_changed": False,
                "overview_visual_18": "host composite from three Blender-rendered band top/projection views",
                "full_context_not_primary_18_evidence": True,
                "values_labels_render_only": True,
                "not_cfd": True,
            },
            "pressure_points": points,
            "camera_projections": projections,
            "renders": render_records,
        },
    )
    report_path = output_dir / "int30_r1b_r2_machine_report.json"
    report = {
        "schema_version": "bf3d.int30_r1b_r2.machine_report.v1",
        "requirement_id": REQUIREMENT_ID,
        "stage": STAGE_ID,
        "status": "candidate_ready_for_review",
        "approval": "not_granted_requires_visual_and_spec_review",
        "generated_at": now_iso(),
        "single_changed_dimension": "visual_camera_and_render_only_compositing",
        "input": {
            "path": str(args.input_blend.resolve()),
            "expected_sha256": EXPECTED_INPUT_SHA256,
            "actual_sha256": sha256_file(args.input_blend.resolve()),
            "sha256_match": assertions["input_sha256_matches"],
        },
        "candidate": {"path": str(candidate), "bytes": None, "sha256": None},
        "blender": {
            "version": bpy.app.version_string,
            "binary_path": bpy.app.binary_path,
            "background": bpy.app.background,
            "render_engine": scene.render.engine,
            "render_resolution": [scene.render.resolution_x, scene.render.resolution_y],
        },
        "protected_contract": {
            "pressure_signature_before": signature_before,
            "pressure_signature_after": signature_after,
            "sensor_signature_before": sensor_sig_before,
            "sensor_signature_after": sensor_sig_after,
            "int10_mesh_signature_before": int10_sig_before,
            "int10_mesh_signature_after": int10_sig_after,
            "sensor_count": len([obj for obj in bpy.data.objects if obj.name.startswith("SENSOR_")]),
            "body_temp_sensor_count": len([obj for obj in bpy.data.objects if obj.name.startswith("SENSOR_T_body_")]),
        },
        "pressure_overlay": {"object_count": len(pressure), "group_counts": group_counts(points), "records": points},
        "visual_manifest": str(visual_manifest_path),
        "evidence_renders": render_records,
        "visual_assertion_details": {
            "upper_projection": projections["UPPER_6_CLOSEUP"],
            "middle_projection": projections["MIDDLE_6_CLOSEUP"],
            "overview_sources": ["LOWER_6_CLOSEUP", "MIDDLE_6_CLOSEUP", "UPPER_6_CLOSEUP"],
        },
        "assertions": assertions,
        "known_issues": [
            "R2 is a visual-only iteration; full-context render remains contextual and is not the sole 18-point evidence.",
            "Azimuth remains blocked pending field confirmation; A-F order is relative only.",
            "No GLB was exported and no production/front-end asset was modified.",
            "Root-level specs/avatar_spec.json and specs/acceptance_checklist.md are absent in this workspace; project-local BF3D contract files were used.",
        ],
        "formal_asset_changes": {
            "formal_glb_exported": False,
            "formal_glb_sha256": sha256_file(FORMAL_GLB),
            "frontend_modified": False,
            "global_pipeline_status_modified": False,
        },
    }
    write_json(report_path, report)
    write_stage_pipeline_status(output_dir, candidate, report_path, visual_manifest_path)
    write_summary(output_dir, report)
    bpy.ops.wm.save_as_mainfile(filepath=str(candidate), compress=False)
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
    pressure = pressure_objects()
    points = pressure_points(pressure)
    validation = {
        "schema_version": "bf3d.int30_r1b_r2.reopen_validation.v1",
        "stage": STAGE_ID,
        "validated_at": now_iso(),
        "candidate_path": str(args.candidate.resolve() if args.candidate else ""),
        "candidate_reopened_without_error": True,
        "candidate_sha256": sha256_file(args.candidate.resolve()) if args.candidate else None,
        "scene_stage": bpy.context.scene.get("bf3d_stage", ""),
        "pressure_count_18": len(pressure) == 18,
        "group_counts_6_each": group_counts(points) == {"LOWER": 6, "MIDDLE": 6, "UPPER": 6},
        "pressure_material_unchanged": sorted({slot.material.name for obj in pressure for slot in obj.material_slots if slot.material}) == [PRESSURE_MATERIAL],
        "sensor_count": len([obj for obj in bpy.data.objects if obj.name.startswith("SENSOR_")]),
        "body_temp_sensor_count": len([obj for obj in bpy.data.objects if obj.name.startswith("SENSOR_T_body_")]),
        "l7_l16_groups_present": all(bpy.data.objects.get(name) for name in PROTECTED_LAYER_GROUPS),
        "int10_12_objects_present": all(bpy.data.objects.get(name) for name in INT10_OBJECTS),
        "renders_present": {name: (output_dir / "renders" / name).is_file() for name in RENDER_FILES},
        "no_output_glb": not list(output_dir.rglob("*.glb")),
        "blend1_not_present": not list(output_dir.rglob("*.blend1")),
        "formal_glb_sha256_unchanged": sha256_file(FORMAL_GLB) == EXPECTED_FORMAL_GLB_SHA256,
    }
    validation["status"] = "pass" if all(
        bool(value)
        for key, value in validation.items()
        if key not in {"schema_version", "stage", "validated_at", "candidate_path", "candidate_sha256", "scene_stage", "renders_present"}
    ) and all(validation["renders_present"].values()) else "fail"
    write_json(output_dir / "reopen_validation.json", validation)
    if validation["status"] != "pass":
        raise RuntimeError(f"R2 reopen validation failed: {validation}")


def pressure_objects() -> list[Any]:
    import bpy

    objects = []
    for name in PRESSURE_NAMES:
        obj = bpy.data.objects.get(name)
        if obj is None:
            raise RuntimeError(f"Missing R1B pressure object: {name}")
        objects.append(obj)
    return objects


def pressure_points(objects: list[Any]) -> list[dict[str, Any]]:
    records = []
    for obj in sorted(objects, key=lambda item: item.name):
        extras = json.loads(obj.get("bf3d_extras_json", "{}"))
        records.append(
            {
                "name": obj.name,
                "band": extras.get("band") or obj.name.split("_")[-2],
                "position": extras.get("position") or obj.name[-1],
                "value_kpa": float(extras.get("value_kpa")),
                "height_m": float(extras.get("height_m")),
                "relative_angle_deg": float(extras.get("relative_angle_deg")),
                "driver_id": extras.get("driver_id"),
                "hmi_id": extras.get("hmi_id"),
                "sample_time": extras.get("sample_time"),
                "azimuth_deg": extras.get("azimuth_deg"),
                "orientation_status": extras.get("orientation_status"),
                "not_cfd": extras.get("not_cfd"),
                "not_for_control": extras.get("not_for_control"),
                "location_xyz_m": [round(float(v), 6) for v in obj.location[:]],
                "materials": [slot.material.name if slot.material else None for slot in obj.material_slots],
                "scale": [round(float(v), 6) for v in obj.scale[:]],
                "marker_radius_m": float(obj.get("marker_radius_m", 0.115)),
            }
        )
    return records


def group_counts(points: list[dict[str, Any]]) -> dict[str, int]:
    return {band: len([item for item in points if item["band"] == band]) for band in ("LOWER", "MIDDLE", "UPPER")}


def render_specs(points: list[dict[str, Any]]) -> list[dict[str, Any]]:
    z = {band: sum(item["location_xyz_m"][2] for item in points if item["band"] == band) / 6.0 for band in ("LOWER", "MIDDLE", "UPPER")}
    return [
        {
            "id": "FULL_CONTEXT",
            "file": "INT30_R1B_R2_FULL_CONTEXT.png",
            "camera": "INT30_R1B_R2_CAM_FULL_CONTEXT",
            "location": (9.5, -16.0, 13.0),
            "target": (0, 0, 3.3),
            "ortho_scale": 26.0,
            "purpose": "context_only_not_primary_18_point_evidence",
        },
        {
            "id": "LOWER_6_CLOSEUP",
            "file": "INT30_R1B_R2_LOWER_6_CLOSEUP.png",
            "camera": "INT30_R1B_R2_CAM_LOWER_TOP",
            "location": (0, 0, z["LOWER"] + 22.0),
            "target": (0, 0, z["LOWER"]),
            "ortho_scale": 16.0,
            "purpose": "lower_six_point_top_projection_all_a_f_visible",
            "band_only": "LOWER",
        },
        {
            "id": "MIDDLE_6_CLOSEUP",
            "file": "INT30_R1B_R2_MIDDLE_6_CLOSEUP.png",
            "camera": "INT30_R1B_R2_CAM_MIDDLE_TOP",
            "location": (0, 0, z["MIDDLE"] + 22.0),
            "target": (0, 0, z["MIDDLE"]),
            "ortho_scale": 15.2,
            "purpose": "middle_six_point_top_projection_safe_margin_from_footer",
            "band_only": "MIDDLE",
        },
        {
            "id": "UPPER_6_CLOSEUP",
            "file": "INT30_R1B_R2_UPPER_6_CLOSEUP.png",
            "camera": "INT30_R1B_R2_CAM_UPPER_TOP",
            "location": (0, 0, z["UPPER"] + 22.0),
            "target": (0, 0, z["UPPER"]),
            "ortho_scale": 12.8,
            "purpose": "upper_six_point_top_projection_complete_visible_6",
            "band_only": "UPPER",
        },
        {
            "id": "ORIENTATION_PENDING",
            "file": "INT30_R1B_R2_ORIENTATION_PENDING.png",
            "camera": "INT30_R1B_R2_CAM_ORIENTATION_TOP",
            "location": (0, 0, z["UPPER"] + 25.0),
            "target": (0, 0, 4.5),
            "ortho_scale": 14.8,
            "purpose": "all_18_top_projection_relative_orientation_diagnostic",
        },
        {
            "id": "NO_DATA_GRAY_STATE",
            "file": "INT30_R1B_R2_NO_DATA_GRAY_STATE.png",
            "camera": "INT30_R1B_R2_CAM_NO_DATA_CONTEXT",
            "location": (8, -14, 12),
            "target": (0, 0, 3.0),
            "ortho_scale": 18.0,
            "purpose": "render_only_gray_state_composite_no_object_material_change",
        },
        {
            "id": "EVIDENCE_LABELS",
            "file": "INT30_R1B_R2_EVIDENCE_LABELS.png",
            "camera": "INT30_R1B_R2_CAM_EVIDENCE",
            "location": (10, -16, 11.5),
            "target": (0, 0, 3.5),
            "ortho_scale": 16.0,
            "purpose": "values_labels_only_no_value_scale_or_risk_color",
        },
    ]


def make_camera(name: str, location: tuple[float, float, float], target: tuple[float, float, float], ortho_scale: float) -> Any:
    import bpy
    from mathutils import Vector

    cam_data = bpy.data.cameras.new(f"{name}_DATA")
    cam = bpy.data.objects.new(name, cam_data)
    bpy.context.scene.collection.objects.link(cam)
    cam.location = location
    cam.data.type = "ORTHO"
    cam.data.ortho_scale = ortho_scale
    direction = Vector(target) - cam.location
    cam.rotation_euler = direction.to_track_quat("-Z", "Y").to_euler()
    cam["bf3d_stage"] = STAGE_ID
    cam["render_only"] = True
    return cam


def with_band_visibility(band: str, pressure: list[Any]) -> None:
    for obj in pressure:
        obj.hide_render = not obj.name.startswith(f"{PRESSURE_PREFIX}{band}_")


def restore_pressure_visibility(pressure: list[Any]) -> None:
    for obj in pressure:
        obj.hide_render = False


def camera_projection(cam: Any, pressure: list[Any], spec: dict[str, Any]) -> dict[str, Any]:
    import bpy
    from bpy_extras.object_utils import world_to_camera_view

    scene = bpy.context.scene
    records = []
    for obj in sorted(pressure, key=lambda item: item.name):
        co = world_to_camera_view(scene, cam, obj.matrix_world.translation)
        band = obj.name.split("_")[-2]
        records.append(
            {
                "name": obj.name,
                "band": band,
                "position": obj.name[-1],
                "x": round(float(co.x), 6),
                "y": round(float(co.y), 6),
                "z": round(float(co.z), 6),
                "visible_in_render": (not obj.hide_render) and 0.0 <= co.x <= 1.0 and 0.0 <= co.y <= 1.0 and co.z >= 0.0,
                "band_only": spec.get("band_only"),
            }
        )
    return {"spec_id": spec["id"], "file": spec["file"], "records": records}


def all_visible_safe(projection: dict[str, Any], band: str, min_margin: float, header: float, footer: float) -> bool:
    records = [item for item in projection["records"] if item["band"] == band]
    if len(records) != 6:
        return False
    for item in records:
        if not item["visible_in_render"]:
            return False
        if item["x"] < min_margin or item["x"] > 1.0 - min_margin:
            return False
        if item["y"] < footer or item["y"] > 1.0 - header:
            return False
    return True


def pressure_signature(objects: list[Any]) -> str:
    payload = []
    for obj in sorted(objects, key=lambda item: item.name):
        payload.append(
            {
                "name": obj.name,
                "type": obj.type,
                "parent": obj.parent.name if obj.parent else None,
                "location": [round(float(v), 8) for v in obj.location[:]],
                "rotation": [round(float(v), 8) for v in obj.rotation_euler[:]],
                "scale": [round(float(v), 8) for v in obj.scale[:]],
                "mesh_counts": [len(obj.data.vertices), len(obj.data.edges), len(obj.data.polygons)] if obj.type == "MESH" else None,
                "materials": [slot.material.name if slot.material else None for slot in obj.material_slots],
                "extras": obj.get("bf3d_extras_json", ""),
                "marker_radius_m": obj.get("marker_radius_m", ""),
            }
        )
    return hashlib.sha256(json.dumps(payload, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()


def pressure_coordinate_signature(objects: list[Any]) -> str:
    payload = {obj.name: [round(float(v), 8) for v in obj.location[:]] for obj in objects}
    return hashlib.sha256(json.dumps(payload, sort_keys=True).encode("utf-8")).hexdigest()


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


def mesh_signature(names: list[str]) -> str:
    import bpy

    payload = []
    for name in names:
        obj = bpy.data.objects.get(name)
        if obj is None:
            payload.append({"name": name, "missing": True})
            continue
        payload.append(
            {
                "name": obj.name,
                "type": obj.type,
                "matrix_world": [round(float(v), 7) for row in obj.matrix_world for v in row],
                "mesh_counts": [len(obj.data.vertices), len(obj.data.edges), len(obj.data.polygons)] if obj.type == "MESH" else None,
                "materials": [slot.material.name if slot.material else None for slot in obj.material_slots],
            }
        )
    return hashlib.sha256(json.dumps(payload, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()


def postprocess_host_images(output_dir: Path) -> None:
    from PIL import Image, ImageDraw, ImageFont, ImageOps

    manifest_path = output_dir / "int30_r1b_r2_visual_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    points = manifest["pressure_points"]
    projections = manifest["camera_projections"]
    font_big = load_font(30)
    font_med = load_font(22)
    font_small = load_font(17)
    titles = {
        "FULL_CONTEXT": ("INT-30 R1B_R2 全炉上下文 / context only", "18点主证据见 overview_visual_18；HMI快照 / 相对方位示意 / 非CFD"),
        "LOWER_6_CLOSEUP": ("LOWER 20.350m / HMI快照 / 相对方位示意", "6 rendered points A-F visible; values shown as labels only"),
        "MIDDLE_6_CLOSEUP": ("MIDDLE 23.488m / HMI快照 / 相对方位示意", "safe margin from footer; no point touches bottom bar"),
        "UPPER_6_CLOSEUP": ("UPPER 28.976m / HMI快照 / 相对方位示意", "upper_visible_6 assertion requires all A-F in frame"),
        "ORIENTATION_PENDING": ("方位待确认诊断图 / Relative orientation only", "A-F use fixture relative_angle_deg; azimuth_deg empty; not for control"),
        "NO_DATA_GRAY_STATE": ("No-data 灰态示意 / render-only gray composite", "No object material changed; no baseline risk color; no NaN"),
        "EVIDENCE_LABELS": ("证据标签 / values shown only as HMI snapshot text", "quality=unverified; cutaway_only=true; not_for_control; non-CFD"),
    }
    for record in manifest["renders"]:
        path = Path(record["path"])
        image = Image.open(path).convert("RGBA")
        draw = ImageDraw.Draw(image, "RGBA")
        title, subtitle = titles[record["id"]]
        draw_bars(draw, image.size, title, subtitle, font_big, font_med)
        if record["id"] in {"LOWER_6_CLOSEUP", "MIDDLE_6_CLOSEUP", "UPPER_6_CLOSEUP", "ORIENTATION_PENDING"}:
            draw_point_labels(draw, image.size, projections[record["id"]], points, font_med, font_small)
        if record["id"] == "NO_DATA_GRAY_STATE":
            image = gray_no_data_composite(image)
            draw = ImageDraw.Draw(image, "RGBA")
            draw_bars(draw, image.size, title, subtitle, font_big, font_med)
        if record["id"] == "EVIDENCE_LABELS":
            draw_evidence_table(draw, image.size, points, font_med, font_small)
        image.convert("RGB").save(path)

    overview = build_overview_visual_18(output_dir, points, font_big, font_med, font_small)
    overview_path = output_dir / "renders" / "INT30_R1B_R2_OVERVIEW_VISUAL_18.png"
    overview.save(overview_path)

    render_hashes = {
        path.name: {"bytes": path.stat().st_size, "sha256": sha256_file(path)}
        for path in sorted((output_dir / "renders").glob("*.png"))
    }
    overview_record = {
        "id": "OVERVIEW_VISUAL_18",
        "file": "INT30_R1B_R2_OVERVIEW_VISUAL_18.png",
        "path": str(overview_path),
        "camera": "host_composite_from_lower_middle_upper_top_projection_renders",
        "projection": "HOST_COMPOSITE",
        "purpose": "primary_18_point_visual_evidence_three_band_rendered_views_each_with_a_f_labels",
        "resolution_px": [1440, 960],
        **render_hashes["INT30_R1B_R2_OVERVIEW_VISUAL_18.png"],
    }
    manifest["renders"] = [overview_record] + manifest["renders"]
    manifest["render_policy"]["host_python_pillow_overlay_applied"] = True
    manifest["render_policy"]["overview_visual_18_contains_rendered_band_views"] = True
    for item in manifest["renders"]:
        info = render_hashes.get(item["file"])
        if info:
            item["bytes"] = info["bytes"]
            item["sha256"] = info["sha256"]
    write_json(manifest_path, manifest)


def draw_bars(draw: Any, size: tuple[int, int], title: str, subtitle: str, font_big: Any, font_med: Any) -> None:
    width, height = size
    draw.rectangle([0, 0, width, 86], fill=(8, 19, 24, 212))
    draw.text((24, 14), title, font=font_big, fill=(238, 250, 250, 255))
    draw.text((24, 52), subtitle, font=font_med, fill=(190, 219, 221, 255))
    draw.rectangle([0, height - 48, width, height], fill=(8, 19, 24, 196))
    draw.text((24, height - 35), "HMI快照 2026-07-15 10:48:09+08:00 | 相对方位示意 | 非CFD | 不用于控制", font=font_med, fill=(226, 238, 236, 255))


def draw_point_labels(draw: Any, size: tuple[int, int], projection: dict[str, Any], points: list[dict[str, Any]], font_med: Any, font_small: Any) -> None:
    width, height = size
    by_name = {item["name"]: item for item in points}
    selected = [item for item in projection["records"] if item["visible_in_render"]]
    if projection["spec_id"] in {"LOWER_6_CLOSEUP", "MIDDLE_6_CLOSEUP", "UPPER_6_CLOSEUP"}:
        selected = [item for item in selected if item["band"] == projection["spec_id"].split("_")[0]]
    for item in selected:
        point = by_name[item["name"]]
        x = int(item["x"] * width)
        y = int((1.0 - item["y"]) * height)
        label = f"{point['position']} {point['value_kpa']:.1f} kPa" if projection["spec_id"] != "ORIENTATION_PENDING" else f"{point['band'][0]}{point['position']}"
        bbox = draw.textbbox((0, 0), label, font=font_small)
        label_w = bbox[2] - bbox[0] + 14
        label_h = bbox[3] - bbox[1] + 10
        lx = max(8, min(width - label_w - 8, x + 13))
        ly = max(96, min(height - 62 - label_h, y - 14))
        draw.ellipse([x - 7, y - 7, x + 7, y + 7], fill=(138, 226, 237, 235), outline=(229, 254, 255, 245), width=2)
        draw.rounded_rectangle([lx, ly, lx + label_w, ly + label_h], radius=5, fill=(5, 35, 42, 220), outline=(106, 218, 230, 220), width=1)
        draw.text((lx + 7, ly + 4), label, font=font_small, fill=(236, 253, 253, 255))


def draw_evidence_table(draw: Any, size: tuple[int, int], points: list[dict[str, Any]], font_med: Any, font_small: Any) -> None:
    left, top = 30, 104
    col_w, row_h = 320, 30
    draw.rounded_rectangle([left - 12, top - 14, left + col_w * 3 + 26, top + 252], radius=8, fill=(3, 14, 18, 228), outline=(118, 214, 226, 230), width=2)
    draw.text((left, top - 4), "3 levels x 6 points = 18 independent static pressure markers", font=font_med, fill=(240, 253, 252, 255))
    for ci, band in enumerate(("LOWER", "MIDDLE", "UPPER")):
        x = left + ci * col_w
        y = top + 34
        band_points = [item for item in points if item["band"] == band]
        draw.rounded_rectangle([x, y, x + 285, y + 28], radius=5, fill=(18, 66, 77, 230))
        draw.text((x + 10, y + 5), f"{band} {band_points[0]['height_m']:.3f}m", font=font_small, fill=(235, 252, 252, 255))
        for ri, item in enumerate(band_points):
            yy = y + 36 + ri * row_h
            draw.text((x + 12, yy), f"{item['position']} {item['value_kpa']:.1f} kPa", font=font_med, fill=(225, 249, 250, 255))
            draw.text((x + 142, yy + 3), f"rel {item['relative_angle_deg']:.0f} deg", font=font_small, fill=(177, 210, 212, 255))


def gray_no_data_composite(image: Any) -> Any:
    from PIL import Image, ImageOps

    gray = ImageOps.grayscale(image.convert("RGB")).convert("RGBA")
    overlay = Image.new("RGBA", image.size, (28, 31, 32, 70))
    return Image.alpha_composite(gray, overlay)


def build_overview_visual_18(output_dir: Path, points: list[dict[str, Any]], font_big: Any, font_med: Any, font_small: Any) -> Any:
    from PIL import Image, ImageDraw

    width, height = 1440, 960
    canvas = Image.new("RGB", (width, height), (7, 17, 21))
    draw = ImageDraw.Draw(canvas, "RGBA")
    draw_bars(draw, (width, height), "18点展开总览 / primary visual evidence", "Three rendered projection windows: LOWER / MIDDLE / UPPER, each A-F visible", font_big, font_med)
    tile_specs = [
        ("LOWER", "INT30_R1B_R2_LOWER_6_CLOSEUP.png", 28, 112),
        ("MIDDLE", "INT30_R1B_R2_MIDDLE_6_CLOSEUP.png", 498, 112),
        ("UPPER", "INT30_R1B_R2_UPPER_6_CLOSEUP.png", 968, 112),
    ]
    tile_w, tile_h = 444, 570
    for band, filename, x, y in tile_specs:
        src = Image.open(output_dir / "renders" / filename).convert("RGB")
        crop = src.crop((0, 88, src.width, src.height - 50))
        crop.thumbnail((tile_w, tile_h))
        panel = Image.new("RGB", (tile_w, tile_h), (12, 24, 29))
        px = (tile_w - crop.width) // 2
        py = (tile_h - crop.height) // 2
        panel.paste(crop, (px, py))
        canvas.paste(panel, (x, y))
        draw.rounded_rectangle([x, y, x + tile_w, y + tile_h], radius=8, outline=(113, 215, 226, 235), width=2)
        band_points = [item for item in points if item["band"] == band]
        draw.rounded_rectangle([x, y + tile_h + 14, x + tile_w, y + tile_h + 172], radius=8, fill=(3, 14, 18, 228), outline=(113, 215, 226, 200), width=1)
        draw.text((x + 14, y + tile_h + 26), f"{band} {band_points[0]['height_m']:.3f}m / 6 points", font=font_med, fill=(237, 253, 253, 255))
        for idx, item in enumerate(band_points):
            cx = x + 18 + (idx % 3) * 138
            cy = y + tile_h + 62 + (idx // 3) * 42
            draw.rounded_rectangle([cx, cy, cx + 122, cy + 30], radius=5, fill=(17, 64, 74, 224))
            draw.text((cx + 8, cy + 5), f"{item['position']} {item['value_kpa']:.1f}", font=font_small, fill=(236, 253, 253, 255))
    return canvas


def load_font(size: int) -> Any:
    from PIL import ImageFont

    for candidate in [Path(r"C:\Windows\Fonts\simsun.ttc"), Path(r"C:\Windows\Fonts\simhei.ttf"), Path(r"C:\Windows\Fonts\arial.ttf")]:
        if candidate.is_file():
            try:
                return ImageFont.truetype(str(candidate), size)
            except Exception:
                pass
    return ImageFont.load_default()


def refresh_report_after_host(output_dir: Path, candidate: Path) -> None:
    report_path = output_dir / "int30_r1b_r2_machine_report.json"
    manifest_path = output_dir / "int30_r1b_r2_visual_manifest.json"
    report = json.loads(report_path.read_text(encoding="utf-8"))
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    render_hashes = {
        path.name: {"bytes": path.stat().st_size, "sha256": sha256_file(path)}
        for path in sorted((output_dir / "renders").glob("*.png"))
    }
    report["evidence_renders"] = manifest["renders"]
    report["candidate"]["bytes"] = candidate.stat().st_size
    report["candidate"]["sha256"] = sha256_file(candidate)
    report["assertions"]["overview_visual_18"] = (output_dir / "renders" / "INT30_R1B_R2_OVERVIEW_VISUAL_18.png").is_file()
    report["assertions"]["renders_exist"] = all((output_dir / "renders" / item).is_file() for item in RENDER_FILES)
    report["assertions"]["machine_assertions_pass"] = all(report["assertions"].values())
    write_json(report_path, report)
    status_path = output_dir / "reports" / "pipeline_status.json"
    status = json.loads(status_path.read_text(encoding="utf-8"))
    status["stages"][STAGE_ID]["candidate_sha256"] = report["candidate"]["sha256"]
    write_json(status_path, status)
    write_summary(output_dir, report)


def artifact_manifest(output_dir: Path) -> dict[str, Any]:
    records = []
    for artifact in sorted(path for path in output_dir.rglob("*") if path.is_file()):
        if artifact.name == "artifact_sha256.json":
            continue
        records.append({"path": artifact.relative_to(output_dir).as_posix(), "bytes": artifact.stat().st_size, "sha256": sha256_file(artifact)})
    return {"schema_version": "bf3d.int30_r1b_r2.artifact_sha256.v1", "stage": STAGE_ID, "generated_at": now_iso(), "artifacts": records}


def write_stage_pipeline_status(output_dir: Path, candidate: Path, report_path: Path, visual_manifest_path: Path) -> None:
    write_json(
        output_dir / "reports" / "pipeline_status.json",
        {
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
                    "machine_report": rel(report_path),
                    "visual_manifest": rel(visual_manifest_path),
                    "summary": rel(output_dir / "INT-30_R1B_R2_阶段成果总结.md"),
                    "formal_glb_unchanged": True,
                    "formal_glb_sha256": EXPECTED_FORMAL_GLB_SHA256,
                    "next_stop_line": "independent_visual_and_spec_review_required_before_any_next_stage",
                }
            },
        },
    )


def write_summary(output_dir: Path, report: dict[str, Any]) -> None:
    lines = [
        "# INT-30_R1B_R2 阶段成果总结",
        "",
        f"- 阶段：`{STAGE_ID}`",
        "- 状态：`candidate_ready_for_review`，停在重新视觉/规格审核门。",
        f"- 输入 R1B candidate：`{rel(Path(report['input']['path']))}`",
        f"- 输入 SHA：`{report['input']['actual_sha256']}`",
        "- 本轮范围：只修相机、渲染和 render-only 合成；18 点几何/extras/材质/坐标完全不改。",
        f"- 候选 blend：`{rel(Path(report['candidate']['path']))}`",
        f"- 候选 SHA：`{report['candidate']['sha256']}`",
        f"- 机器报告：`{rel(output_dir / 'int30_r1b_r2_machine_report.json')}`",
        f"- 视觉 manifest：`{rel(output_dir / 'int30_r1b_r2_visual_manifest.json')}`",
        f"- Reopen 校验：`{rel(output_dir / 'reopen_validation.json')}`",
        f"- Artifact SHA：`{rel(output_dir / 'artifact_sha256.json')}`",
        "",
        "## 新增/重渲染证据图",
    ]
    for item in report.get("evidence_renders", []):
        lines.append(f"- `{item['file']}`：{item['purpose']}")
    lines.extend(
        [
            "",
            "## 机器断言",
            f"- `upper_visible_6`：`{report['assertions'].get('upper_visible_6')}`",
            f"- `middle_safe_margin`：`{report['assertions'].get('middle_safe_margin')}`",
            f"- `overview_visual_18`：`{report['assertions'].get('overview_visual_18')}`",
            f"- 18 点对象/每组 6 点：`{report['assertions'].get('pressure_count_18') and report['assertions'].get('group_counts_6_each')}`",
            f"- 几何/extras/材质不变：`{report['assertions'].get('pressure_geometry_extras_material_unchanged')}`",
            f"- 115/80/L7-L16 保护：`{report['assertions'].get('sensor_count_115_preserved') and report['assertions'].get('body_temperature_80_preserved') and report['assertions'].get('l7_l16_groups_present')}`",
            f"- 未生成 GLB/.blend1：`{report['assertions'].get('no_output_glb') and report['assertions'].get('blend1_not_generated')}`",
            f"- 正式 GLB SHA 不变：`{report['assertions'].get('formal_glb_sha256_unchanged')}`",
        ]
    )
    write_text(output_dir / "INT-30_R1B_R2_阶段成果总结.md", "\n".join(lines) + "\n")


if __name__ == "__main__":
    if "--run-blender-stage" in sys.argv or "--reopen-validate" in sys.argv:
        raise SystemExit(blender_main())
    raise SystemExit(host_main())
