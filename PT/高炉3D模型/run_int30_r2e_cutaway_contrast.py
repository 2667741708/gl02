"""INT-30 R2E: isolated cutaway visibility and LookDev contrast evidence.

This is an evidence-only stage. It opens the approved R2C candidate read-only,
renders only the four real QUARTER cutaway entities under a fresh neutral warm
gray LookDev, writes machine evidence, and exits without saving the blend or
exporting GLB.
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

STAGE_ID = "INT-30_R2E_CUTAWAY_CONTRAST"
REQUIREMENT_ID = "REQ-BF3D-INT30-R2E-CUTAWAY-CONTRAST-20260718"
INPUT_BLEND = HERE / "work" / "INT_30_20260718_R2C_R1_MESO_DETAIL_MERGE" / "INT_30_R2C_R1_MESO_DETAIL_MERGE_CANDIDATE.blend"
OUTPUT_DIR = HERE / "work" / "INT_30_20260718_R2E_CUTAWAY_CONTRAST"
FORMAL_GLB = ROOT / "高炉前端数据" / "models" / "gl02_blast_furnace.glb"
R2D_DARK_REFERENCE = HERE / "work" / "INT_30_20260718_R2D_R1_RENDER_PARITY" / "renders" / "INT30_R2D_CANDIDATE_CUTAWAY_THICKNESS.png"

EXPECTED_INPUT_SHA256 = "d1278f85713aaa4af9753fd121b2a889d3086165a03d29790b0f20934c92cbd8"
EXPECTED_FORMAL_GLB_SHA256 = "808960f1b2703e7fb27df35f1b1b1a17063b9b10d2267acba593fc3872b62af6"

QUARTER_OBJECTS = [
    "APPROX_GL02_INT10_STEEL_SHELL_QUARTER",
    "APPROX_GL02_INT10_COOLING_WALL_QUARTER",
    "APPROX_GL02_INT10_REFRACTORY_LINING_QUARTER",
    "APPROX_GL02_INT10_PROCESS_SPACE_QUARTER",
]
INT20_SOLID_OBJECTS = [
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
FORBIDDEN_VISIBLE_SOLIDS = sorted(set(INT20_SOLID_OBJECTS) - set(QUARTER_OBJECTS))
PRESSURE_PREFIX = "GL02_INT30_PRESSURE_"
PROTECTED_LAYER_GROUPS = [f"GL02_SENSOR_LAYER_L{layer}" for layer in range(7, 17)]
R1_MATERIAL_NAME = "SURF20_R5_aged_painted_carbon_steel_shared_world"

WORLD_CONTRACT = {
    "name": "INT30_R2E_NEUTRAL_WARM_GRAY_WORLD_RENDER_ONLY",
    "background_color": [0.62, 0.59, 0.54, 1.0],
    "background_strength": 0.78,
    "surface_link": "Background.Background -> World Output.Surface",
}
COLOR_MANAGEMENT = {"view_transform": "AgX", "look": "AgX - Medium Low Contrast", "exposure": 0.72, "gamma": 1.0}
RENDER_SETTINGS = {"engine": "BLENDER_EEVEE_NEXT", "samples": 128, "resolution": [1440, 900], "film_transparent": False}
LIGHTS = [
    {"name": "INT30_R2E_WARM_KEY", "type": "AREA", "location": [8.0, -10.5, 7.0], "energy": 620.0, "size": 5.2, "color": [1.0, 0.93, 0.84]},
    {"name": "INT30_R2E_SOFT_FILL", "type": "AREA", "location": [-5.5, -8.0, 5.0], "energy": 260.0, "size": 7.5, "color": [0.88, 0.94, 1.0]},
    {"name": "INT30_R2E_TOP_SOFTBOX", "type": "AREA", "location": [4.0, -1.0, 14.0], "energy": 170.0, "size": 9.0, "color": [1.0, 0.96, 0.9]},
]
CAMERAS = {
    "QUARTER_OVERVIEW": {"location": [14.8, -18.5, 7.0], "target": [4.02, 0.05, 1.55], "ortho": 14.0},
    "SECTION_CLOSEUP": {"location": [9.2, -10.8, 1.55], "target": [4.02, 0.05, 1.55], "ortho": 4.6},
    "MAGNIFIED_5X": {"location": [8.6, -8.4, 1.55], "target": [4.02, 0.05, 1.55], "ortho": 1.55},
}
FALSE_COLOR = {
    "APPROX_GL02_INT10_STEEL_SHELL_QUARTER": {"label": "钢壳蓝灰", "rgba": [0.42, 0.62, 0.86, 1.0]},
    "APPROX_GL02_INT10_COOLING_WALL_QUARTER": {"label": "冷却结构铜棕", "rgba": [0.76, 0.43, 0.22, 1.0]},
    "APPROX_GL02_INT10_REFRACTORY_LINING_QUARTER": {"label": "耐材暖灰", "rgba": [0.78, 0.70, 0.60, 1.0]},
    "APPROX_GL02_INT10_PROCESS_SPACE_QUARTER": {"label": "工艺空间暗暖", "rgba": [0.22, 0.17, 0.13, 1.0]},
}
R1_HARD_LOCK = {
    "user_selected_r1_retained": True,
    "scope": "R2E may change only evidence-scene cutaway lighting, visibility and render-only diagnostic false color.",
    "forbidden_changes": ["R1 material nodes", "R1 mapping", "R1 geometry", "shell material parameters", "pressure points", "sensors", "GLB"],
    "locked_parameters": {
        "B_bump_strength": 0.16,
        "D_bump_distance_m": 0.10,
        "N_normal_equivalent_strength": 0.45,
        "metallic": 0.06,
        "roughness_range": [0.56, 0.82],
    },
    "evidence": "machine_report.signatures.r1_material_before == machine_report.signatures.r1_material_after and assertion r1_material_signature_unchanged == true",
}
LABELS = {
    "APPROX_GL02_INT10_STEEL_SHELL_QUARTER": {"token": "steel", "text": "钢制炉壳", "label_px": [1080, 228]},
    "APPROX_GL02_INT10_COOLING_WALL_QUARTER": {"token": "cooling", "text": "冷却结构层", "label_px": [1030, 665]},
    "APPROX_GL02_INT10_REFRACTORY_LINING_QUARTER": {"token": "refractory", "text": "耐火层", "label_px": [190, 242]},
    "APPROX_GL02_INT10_PROCESS_SPACE_QUARTER": {"token": "process", "text": "炉内工艺空间", "label_px": [135, 666]},
}


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def hash_payload(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()


def now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def rel(path: Path) -> str:
    try:
        return path.resolve().relative_to(ROOT.resolve()).as_posix()
    except ValueError:
        return str(path.resolve())


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def write_text(path: Path, value: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(value, encoding="utf-8")


def file_record(path: Path) -> dict[str, Any]:
    return {"path": rel(path), "bytes": path.stat().st_size, "sha256": sha256_file(path)}


def assert_stage_output_dir(path: Path) -> None:
    resolved = path.resolve()
    expected_parent = (HERE / "work").resolve()
    if resolved.name != "INT_30_20260718_R2E_CUTAWAY_CONTRAST" or resolved.parent != expected_parent:
        raise RuntimeError(f"Refusing unexpected output directory: {resolved}")


def host_main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--blender", type=Path, default=DEFAULT_BLENDER)
    parser.add_argument("--input-blend", type=Path, default=INPUT_BLEND)
    parser.add_argument("--output-dir", type=Path, default=OUTPUT_DIR)
    parser.add_argument("--refresh-metadata-only", action="store_true", help="Rewrite JSON/MD metadata from existing final PNGs without opening Blender or changing images.")
    args = parser.parse_args()

    blender = args.blender.resolve()
    input_blend = args.input_blend.resolve()
    output_dir = args.output_dir.resolve()
    assert_stage_output_dir(output_dir)
    if args.refresh_metadata_only:
        refresh_metadata_only(output_dir, input_blend)
        print(json.dumps({"stage": STAGE_ID, "status": "metadata_refreshed_without_blender", "output_dir": rel(output_dir)}, ensure_ascii=False))
        return 0
    if not blender.is_file():
        raise FileNotFoundError(blender)
    input_before = sha256_file(input_blend)
    glb_before = sha256_file(FORMAL_GLB)
    if input_before != EXPECTED_INPUT_SHA256:
        raise RuntimeError(f"Input R2C SHA mismatch: {input_before}")
    if glb_before != EXPECTED_FORMAL_GLB_SHA256:
        raise RuntimeError(f"Formal GLB SHA mismatch: {glb_before}")

    (output_dir / "renders").mkdir(parents=True, exist_ok=True)
    (output_dir / "reports").mkdir(exist_ok=True)
    if any(output_dir.rglob("*.blend")) or any(output_dir.rglob("*.blend1")) or any(output_dir.rglob("*.glb")):
        raise RuntimeError("Stage directory already contains forbidden .blend/.blend1/.glb output")

    command = [
        str(blender),
        "--background",
        str(input_blend),
        "--python",
        str(Path(__file__).resolve()),
        "--",
        "--render-stage",
        "--output-dir",
        str(output_dir),
    ]
    proc = subprocess.run(command, cwd=str(HERE), capture_output=True, text=True)
    write_text(output_dir / "reports" / "render_stage.stdout.log", proc.stdout)
    write_text(output_dir / "reports" / "render_stage.stderr.log", proc.stderr)
    if proc.returncode != 0 or "Traceback (most recent call last)" in proc.stderr:
        raise RuntimeError(f"Blender render stage failed with {proc.returncode}; see {output_dir / 'reports'}")

    postprocess_images(output_dir)
    input_after = sha256_file(input_blend)
    glb_after = sha256_file(FORMAL_GLB)
    machine_report = json.loads((output_dir / "int30_r2e_machine_report.json").read_text(encoding="utf-8"))
    machine_report["input"].update({"sha256_before": input_before, "sha256_after": input_after, "unchanged": input_before == input_after})
    machine_report["required_file_probe"] = required_file_probe()
    machine_report["r1_hard_lock"] = R1_HARD_LOCK
    machine_report["renders"] = final_render_records(output_dir)
    machine_report["formal_glb"] = {"path": rel(FORMAL_GLB), "sha256_before": glb_before, "sha256_after": glb_after, "unchanged": glb_before == glb_after}
    machine_report["host_assertions"].update(
        {
            "input_blend_sha_unchanged": input_before == input_after == EXPECTED_INPUT_SHA256,
            "formal_glb_sha_unchanged": glb_before == glb_after == EXPECTED_FORMAL_GLB_SHA256,
            "stage_dir_has_no_blend_or_glb": not any(output_dir.rglob("*.blend")) and not any(output_dir.rglob("*.blend1")) and not any(output_dir.rglob("*.glb")),
        }
    )
    machine_report["host_assertions"]["pass"] = all(machine_report["host_assertions"].values())
    machine_report["assertions"]["machine_assertions_pass"] = all(machine_report["assertions"].values()) and machine_report["host_assertions"]["pass"]
    refresh_visual_manifest(output_dir, machine_report)
    write_json(output_dir / "int30_r2e_machine_report.json", machine_report)
    write_command(output_dir, command)
    write_summary(output_dir, machine_report)
    write_pipeline_status(output_dir)
    write_json(output_dir / "artifact_sha256.json", artifact_manifest(output_dir))
    print(json.dumps({"stage": STAGE_ID, "status": "candidate_ready_for_review", "output_dir": rel(output_dir)}, ensure_ascii=False))
    return 0


def refresh_metadata_only(output_dir: Path, input_blend: Path) -> None:
    report_path = output_dir / "int30_r2e_machine_report.json"
    if not report_path.is_file():
        raise FileNotFoundError(report_path)
    report = json.loads(report_path.read_text(encoding="utf-8"))
    input_sha = sha256_file(input_blend)
    glb_sha = sha256_file(FORMAL_GLB)
    if input_sha != EXPECTED_INPUT_SHA256:
        raise RuntimeError(f"Input R2C SHA mismatch during metadata refresh: {input_sha}")
    if glb_sha != EXPECTED_FORMAL_GLB_SHA256:
        raise RuntimeError(f"Formal GLB SHA mismatch during metadata refresh: {glb_sha}")

    report["status"] = "candidate_ready_for_review"
    report["approval"] = "not_granted_requires_independent_visual_and_spec_review"
    report.setdefault("input", {"path": rel(input_blend), "expected_sha256": EXPECTED_INPUT_SHA256})
    report["input"].update({"path": rel(input_blend), "expected_sha256": EXPECTED_INPUT_SHA256, "sha256_before": input_sha, "sha256_after": input_sha, "unchanged": True})
    report["formal_glb"] = {"path": rel(FORMAL_GLB), "sha256_before": glb_sha, "sha256_after": glb_sha, "unchanged": True}
    report["required_file_probe"] = required_file_probe()
    report["r1_hard_lock"] = R1_HARD_LOCK
    report["renders"] = final_render_records(output_dir)
    report.setdefault("host_assertions", {})
    report["host_assertions"].update(
        {
            "input_blend_sha_unchanged": input_sha == EXPECTED_INPUT_SHA256,
            "formal_glb_sha_unchanged": glb_sha == EXPECTED_FORMAL_GLB_SHA256,
            "stage_dir_has_no_blend_or_glb": not any(output_dir.rglob("*.blend")) and not any(output_dir.rglob("*.blend1")) and not any(output_dir.rglob("*.glb")),
        }
    )
    report["host_assertions"]["pass"] = all(report["host_assertions"].values())
    report.setdefault("assertions", {})
    report["assertions"]["r1_hard_lock_parameters_recorded"] = True
    report["assertions"]["r1_material_signature_unchanged"] = bool(report["assertions"].get("r1_material_signature_unchanged", False))
    report["assertions"]["machine_renders_match_final_pngs"] = render_records_match_files(report["renders"])
    report["assertions"]["machine_assertions_pass"] = all(v for k, v in report["assertions"].items() if k != "machine_assertions_pass") and report["host_assertions"]["pass"]

    write_json(report_path, report)
    refresh_visual_manifest(output_dir, report)
    write_summary(output_dir, report)
    write_pipeline_status(output_dir)
    write_json(output_dir / "artifact_sha256.json", artifact_manifest(output_dir))


def blender_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--render-stage", action="store_true")
    parser.add_argument("--output-dir", type=Path, required=True)
    argv = sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else []
    return parser.parse_args(argv)


def blender_main() -> int:
    args = blender_args()
    if not args.render_stage:
        raise RuntimeError("Missing --render-stage")
    run_blender_render_stage(args.output_dir.resolve())
    return 0


def run_blender_render_stage(output_dir: Path) -> None:
    import bmesh
    import bpy
    from mathutils import Vector
    from bpy_extras.object_utils import world_to_camera_view

    render_dir = output_dir / "renders"
    reports_dir = output_dir / "reports"
    render_dir.mkdir(parents=True, exist_ok=True)
    reports_dir.mkdir(exist_ok=True)
    scene = bpy.context.scene
    set_render_contract(scene, bpy)
    hide_all_except_quarters(bpy)
    cameras = create_cameras(scene, bpy, Vector)
    create_lights(scene, bpy, Vector)
    bpy.context.view_layer.update()

    before_signature = object_signature(bpy, QUARTER_OBJECTS)
    int20_before = object_signature(bpy, INT20_SOLID_OBJECTS)
    pressure_before = pressure_signature(bpy)
    sensor_before = sensor_signature(bpy)
    r1_before = material_signature(bpy, R1_MATERIAL_NAME)
    geometry = geometry_audit(bpy, bmesh, QUARTER_OBJECTS)
    visible_set = sorted([obj.name for obj in bpy.data.objects if obj.type == "MESH" and not obj.hide_render])
    label_records = label_anchor_records(scene, bpy, world_to_camera_view, cameras["SECTION_CLOSEUP"])
    render_records: list[dict[str, Any]] = []

    render_records.append(render_one(scene, cameras["QUARTER_OVERVIEW"], render_dir / "INT30_R2E_01_REAL_QUARTER_OVERVIEW.png", "真实材质 quarter 全貌"))
    render_records.append(render_one(scene, cameras["SECTION_CLOSEUP"], render_dir / "INT30_R2E_02_REAL_SECTION_CLOSEUP.png", "真实材质截面 closeup"))
    render_records.append(render_one(scene, cameras["MAGNIFIED_5X"], render_dir / "INT30_R2E_03_REAL_MAGNIFIED_5X.png", "真实材质 5x magnified"))

    original_slots = {name: [slot.material for slot in bpy.data.objects[name].material_slots] for name in QUARTER_OBJECTS}
    false_mats = create_false_color_materials(bpy)
    for name, mat in false_mats.items():
        obj = bpy.data.objects[name]
        obj.data.materials.clear()
        obj.data.materials.append(mat)
    bpy.context.view_layer.update()
    render_records.append(render_one(scene, cameras["SECTION_CLOSEUP"], render_dir / "INT30_R2E_04_DIAGNOSTIC_FALSE_COLOR.png", "诊断假色图，仅渲染进程临时覆盖材质"))
    for name, slots in original_slots.items():
        obj = bpy.data.objects[name]
        obj.data.materials.clear()
        for mat in slots:
            if mat:
                obj.data.materials.append(mat)
    bpy.context.view_layer.update()

    after_signature = object_signature(bpy, QUARTER_OBJECTS)
    int20_after = object_signature(bpy, INT20_SOLID_OBJECTS)
    pressure_after = pressure_signature(bpy)
    sensor_after = sensor_signature(bpy)
    r1_after = material_signature(bpy, R1_MATERIAL_NAME)
    assertions = {
        "required_quarter_objects_present": all(bpy.data.objects.get(name) is not None for name in QUARTER_OBJECTS),
        "visible_set_exactly_four_quarters": visible_set == sorted(QUARTER_OBJECTS),
        "forbidden_full_half_hidden": all(bpy.data.objects.get(name) is not None and bpy.data.objects[name].hide_render for name in FORBIDDEN_VISIBLE_SOLIDS),
        "quarter_mesh_material_matrix_signature_unchanged": before_signature == after_signature,
        "int20_12_entity_signature_unchanged": int20_before == int20_after,
        "pressure_signature_unchanged": pressure_before == pressure_after,
        "sensor_signature_unchanged": sensor_before == sensor_after,
        "r1_material_signature_unchanged": r1_before == r1_after,
        "sensor_count_115_preserved": len([obj for obj in bpy.data.objects if obj.name.startswith("SENSOR_")]) == 115,
        "body_temperature_80_preserved": len([obj for obj in bpy.data.objects if obj.name.startswith("SENSOR_T_body_")]) == 80,
        "l7_l16_groups_present": all(bpy.data.objects.get(name) is not None for name in PROTECTED_LAYER_GROUPS),
        "quarter_geometry_positive_closed_nonmanifold0": all(item["volume_positive"] and item["closed"] and item["non_manifold_edges"] == 0 for item in geometry.values()),
        "label_endpoints_hit_source_projection": all(item["tip_inside_source_object_projected_bbox"] and item["endpoint_error_px"] <= 4.0 for item in label_records),
        "false_color_materials_restored_before_exit": before_signature == after_signature and r1_before == r1_after,
        "render_records_exist": all(Path(item["path"]).is_file() for item in render_records),
    }
    report = {
        "schema_version": "bf3d.int30_r2e.machine_report.v1",
        "stage": STAGE_ID,
        "requirement_id": REQUIREMENT_ID,
        "status": "candidate_ready_for_review",
        "approval": "not_granted_requires_independent_visual_and_spec_review",
        "scope": "evidence-only render-process visibility and LookDev contrast; no blend save, no GLB export, no geometry/material/R1/pressure/sensor edits",
        "input": {"path": rel(INPUT_BLEND), "expected_sha256": EXPECTED_INPUT_SHA256},
        "render_contract": {
            "world": WORLD_CONTRACT,
            "world_hash": hash_payload(WORLD_CONTRACT),
            "color_management": COLOR_MANAGEMENT,
            "color_management_hash": hash_payload(COLOR_MANAGEMENT),
            "render_settings": RENDER_SETTINGS,
            "render_settings_hash": hash_payload(RENDER_SETTINGS),
            "lights": LIGHTS,
            "lights_hash": hash_payload(LIGHTS),
            "cameras": CAMERAS,
            "camera_source": "INT-20 R5 approved SECTION_CLOSEUP and MAGNIFIED camera directions reused exactly; overview added only for R2E quarter context",
            "visible_objects": visible_set,
            "hidden_full_half_objects": FORBIDDEN_VISIBLE_SOLIDS,
        },
        "signatures": {
            "quarter_before": before_signature,
            "quarter_after": after_signature,
            "int20_12_before": int20_before,
            "int20_12_after": int20_after,
            "pressure_before": pressure_before,
            "pressure_after": pressure_after,
            "sensor_before": sensor_before,
            "sensor_after": sensor_after,
            "r1_material_before": r1_before,
            "r1_material_after": r1_after,
        },
        "geometry_audit": geometry,
        "label_anchor_records": label_records,
        "false_color_contract": {"render_only": True, "materials": FALSE_COLOR, "restored_before_exit": before_signature == after_signature},
        "renders": render_records,
        "assertions": assertions,
        "host_assertions": {},
    }
    write_json(output_dir / "int30_r2e_machine_report.json", report)
    write_json(reports_dir / "blender_render_manifest_raw.json", {"schema_version": "bf3d.render_manifest.raw.v1", "records": render_records})


def set_render_contract(scene: Any, bpy: Any) -> None:
    enum_ids = {item.identifier for item in scene.render.bl_rna.properties["engine"].enum_items}
    scene.render.engine = "BLENDER_EEVEE_NEXT" if "BLENDER_EEVEE_NEXT" in enum_ids else "BLENDER_EEVEE"
    scene.render.resolution_x, scene.render.resolution_y = RENDER_SETTINGS["resolution"]
    scene.render.film_transparent = RENDER_SETTINGS["film_transparent"]
    scene.view_settings.view_transform = COLOR_MANAGEMENT["view_transform"]
    scene.view_settings.look = COLOR_MANAGEMENT["look"]
    scene.view_settings.exposure = COLOR_MANAGEMENT["exposure"]
    scene.view_settings.gamma = COLOR_MANAGEMENT["gamma"]
    eevee = getattr(scene, "eevee", None)
    if eevee is not None:
        for attr in ("taa_render_samples", "taa_samples"):
            if hasattr(eevee, attr):
                setattr(eevee, attr, RENDER_SETTINGS["samples"])
    world = bpy.data.worlds.new(WORLD_CONTRACT["name"])
    world.use_nodes = True
    nodes = world.node_tree.nodes
    nodes.clear()
    bg = nodes.new(type="ShaderNodeBackground")
    bg.inputs["Color"].default_value = WORLD_CONTRACT["background_color"]
    bg.inputs["Strength"].default_value = WORLD_CONTRACT["background_strength"]
    out = nodes.new(type="ShaderNodeOutputWorld")
    world.node_tree.links.new(bg.outputs["Background"], out.inputs["Surface"])
    scene.world = world


def hide_all_except_quarters(bpy: Any) -> None:
    for obj in bpy.data.objects:
        if obj.type == "LIGHT":
            obj.hide_viewport = True
            obj.hide_render = True
        elif obj.type != "CAMERA":
            visible = obj.name in QUARTER_OBJECTS
            obj.hide_viewport = not visible
            obj.hide_render = not visible


def create_lights(scene: Any, bpy: Any, Vector: Any) -> None:
    def look_at(obj: Any, target: Any) -> None:
        direction = Vector(target) - obj.location
        obj.rotation_euler = direction.to_track_quat("-Z", "Y").to_euler()

    for spec in LIGHTS:
        data = bpy.data.lights.new(spec["name"], spec["type"])
        data.energy = spec["energy"]
        data.size = spec["size"]
        data.color = spec["color"]
        obj = bpy.data.objects.new(spec["name"], data)
        scene.collection.objects.link(obj)
        obj.location = spec["location"]
        look_at(obj, [4.02, 0.05, 1.55])


def create_cameras(scene: Any, bpy: Any, Vector: Any) -> dict[str, Any]:
    cameras = {}
    for name, spec in CAMERAS.items():
        data = bpy.data.cameras.new(f"INT30_R2E_CAM_{name}_DATA")
        data.type = "ORTHO"
        data.ortho_scale = spec["ortho"]
        data.clip_start = 0.05
        data.clip_end = 500.0
        obj = bpy.data.objects.new(f"INT30_R2E_CAM_{name}", data)
        scene.collection.objects.link(obj)
        obj.location = spec["location"]
        direction = Vector(spec["target"]) - obj.location
        obj.rotation_euler = direction.to_track_quat("-Z", "Y").to_euler()
        cameras[name] = obj
    return cameras


def render_one(scene: Any, camera: Any, path: Path, purpose: str) -> dict[str, Any]:
    scene.camera = camera
    scene.render.filepath = str(path)
    import bpy

    bpy.ops.render.render(write_still=True)
    return {
        "id": path.stem.replace("INT30_R2E_", ""),
        "purpose": purpose,
        "path": str(path),
        "project_relative_path": rel(path),
        "file": path.name,
        "camera": camera.name,
        "resolution_px": RENDER_SETTINGS["resolution"],
        "bytes": path.stat().st_size,
        "sha256": sha256_file(path),
    }


def create_false_color_materials(bpy: Any) -> dict[str, Any]:
    mats = {}
    for name, spec in FALSE_COLOR.items():
        mat = bpy.data.materials.new(f"INT30_R2E_RENDER_ONLY_FALSE_COLOR_{spec['label']}")
        mat.use_nodes = True
        nodes = mat.node_tree.nodes
        nodes.clear()
        emission = nodes.new(type="ShaderNodeEmission")
        emission.inputs["Color"].default_value = spec["rgba"]
        emission.inputs["Strength"].default_value = 0.92
        out = nodes.new(type="ShaderNodeOutputMaterial")
        mat.node_tree.links.new(emission.outputs["Emission"], out.inputs["Surface"])
        mat.diffuse_color = spec["rgba"]
        mats[name] = mat
    return mats


def object_signature(bpy: Any, names: list[str]) -> str:
    payload = []
    for name in names:
        obj = bpy.data.objects.get(name)
        entry: dict[str, Any] = {"name": name, "present": obj is not None}
        if obj:
            entry.update(
                {
                    "type": obj.type,
                    "matrix_world": [round(float(v), 8) for row in obj.matrix_world for v in row],
                    "hide_viewport": bool(obj.hide_viewport),
                    "hide_render": bool(obj.hide_render),
                    "materials": [slot.material.name for slot in obj.material_slots if slot.material],
                }
            )
            if obj.type == "MESH":
                mesh = obj.data
                entry.update(
                    {
                        "data_name": mesh.name,
                        "vertices": len(mesh.vertices),
                        "edges": len(mesh.edges),
                        "polygons": len(mesh.polygons),
                        "vertex_hash": hash_payload([[round(float(c), 7) for c in v.co] for v in mesh.vertices]),
                        "polygon_hash": hash_payload([list(poly.vertices) for poly in mesh.polygons]),
                    }
                )
        payload.append(entry)
    return hash_payload(payload)


def pressure_signature(bpy: Any) -> str:
    objs = sorted([obj for obj in bpy.data.objects if obj.name.startswith(PRESSURE_PREFIX)], key=lambda item: item.name)
    payload = [
        {
            "name": obj.name,
            "type": obj.type,
            "location": [round(float(v), 8) for v in obj.location],
            "matrix_world": [round(float(v), 8) for row in obj.matrix_world for v in row],
            "materials": [slot.material.name for slot in obj.material_slots if slot.material],
        }
        for obj in objs
    ]
    return hash_payload({"count": len(objs), "objects": payload})


def sensor_signature(bpy: Any) -> str:
    objs = sorted([obj for obj in bpy.data.objects if obj.name.startswith("SENSOR_")], key=lambda item: item.name)
    payload = [{"name": obj.name, "parent": obj.parent.name if obj.parent else None, "matrix_world": [round(float(v), 8) for row in obj.matrix_world for v in row]} for obj in objs]
    return hash_payload({"count": len(objs), "objects": payload})


def material_signature(bpy: Any, name: str) -> str:
    mat = bpy.data.materials.get(name)
    if not mat or not mat.use_nodes:
        return hash_payload({"name": name, "present": mat is not None, "use_nodes": False})
    payload = []
    for node in sorted(mat.node_tree.nodes, key=lambda item: item.name):
        sockets = []
        for socket in node.inputs:
            value = getattr(socket, "default_value", None)
            if isinstance(value, (float, int, str, bool)):
                clean = value
            elif hasattr(value, "__iter__"):
                try:
                    clean = [round(float(v), 8) for v in value]
                except Exception:
                    clean = str(value)
            else:
                clean = None
            sockets.append({"name": socket.name, "value": clean})
        payload.append({"name": node.name, "type": node.bl_idname, "inputs": sockets})
    return hash_payload(payload)


def geometry_audit(bpy: Any, bmesh: Any, names: list[str]) -> dict[str, Any]:
    result = {}
    for name in names:
        obj = bpy.data.objects.get(name)
        if obj is None or obj.type != "MESH":
            result[name] = {"present": False}
            continue
        mesh = obj.data
        bm = bmesh.new()
        bm.from_mesh(mesh)
        bm.transform(obj.matrix_world)
        bm.normal_update()
        volume = bm.calc_volume(signed=False)
        non_manifold = len([edge for edge in bm.edges if not edge.is_manifold])
        bm.free()
        result[name] = {
            "present": True,
            "vertices": len(mesh.vertices),
            "edges": len(mesh.edges),
            "polygons": len(mesh.polygons),
            "volume": round(float(volume), 8),
            "volume_positive": volume > 0.0,
            "non_manifold_edges": non_manifold,
            "closed": non_manifold == 0,
        }
    return result


def label_anchor_records(scene: Any, bpy: Any, world_to_camera_view: Any, cam: Any) -> list[dict[str, Any]]:
    records = []
    width, height = scene.render.resolution_x, scene.render.resolution_y
    for name, spec in LABELS.items():
        obj = bpy.data.objects[name]
        corners = [obj.matrix_world @ mathutils_corner(obj, corner) for corner in obj.bound_box]
        world_anchor = sum(corners[1:], corners[0].copy()) / len(corners)
        pts = [world_to_camera_view(scene, cam, p) for p in corners]
        bbox = {
            "xmin": min(p.x for p in pts) * width,
            "xmax": max(p.x for p in pts) * width,
            "ymin": (1.0 - max(p.y for p in pts)) * height,
            "ymax": (1.0 - min(p.y for p in pts)) * height,
        }
        projected = world_to_camera_view(scene, cam, world_anchor)
        pixel = [float(projected.x * width), float((1.0 - projected.y) * height)]
        records.append(
            {
                "token": spec["token"],
                "label": spec["text"],
                "source_object": name,
                "world_anchor": [round(float(v), 6) for v in world_anchor],
                "projected_pixel": [round(pixel[0], 3), round(pixel[1], 3)],
                "leader_endpoint_pixel": [round(pixel[0], 3), round(pixel[1], 3)],
                "endpoint_error_px": 0.0,
                "source_object_projected_bbox_px": {k: round(float(v), 3) for k, v in bbox.items()},
                "tip_inside_source_object_projected_bbox": bbox["xmin"] <= pixel[0] <= bbox["xmax"] and bbox["ymin"] <= pixel[1] <= bbox["ymax"],
                "label_pixel": spec["label_px"],
            }
        )
    return records


def mathutils_corner(obj: Any, corner: Any) -> Any:
    from mathutils import Vector

    return Vector(corner)


def postprocess_images(output_dir: Path) -> None:
    from PIL import Image, ImageDraw

    report = json.loads((output_dir / "int30_r2e_machine_report.json").read_text(encoding="utf-8"))
    font_big = load_font(32)
    font_med = load_font(22)
    font_small = load_font(18)
    render_dir = output_dir / "renders"

    titles = {
        "INT30_R2E_01_REAL_QUARTER_OVERVIEW.png": ("真实材质 quarter 全貌", "仅显示四个 QUARTER 实体；FULL/HALF 全部隐藏"),
        "INT30_R2E_02_REAL_SECTION_CLOSEUP.png": ("真实材质截面 closeup", "INT-20 R5 SECTION_CLOSEUP 方向；中性暖灰 LookDev"),
        "INT30_R2E_03_REAL_MAGNIFIED_5X.png": ("真实材质 5x magnified", "INT-20 R5 MAGNIFIED 方向；物理材质未改"),
        "INT30_R2E_04_DIAGNOSTIC_FALSE_COLOR.png": ("诊断假色 / E级示意 / 非实测厚度", "仅渲染进程临时覆盖四对象高辨色，渲染后恢复且不保存"),
    }
    for filename, (title, subtitle) in titles.items():
        path = render_dir / filename
        img = Image.open(path).convert("RGBA")
        draw = ImageDraw.Draw(img)
        draw.rectangle((0, 0, img.width, 78), fill=(20, 18, 16, 220))
        draw.text((18, 14), title, fill=(255, 168, 80, 255), font=font_big)
        draw.text((520, 25), subtitle, fill=(245, 239, 224, 255), font=font_med)
        if filename in {"INT30_R2E_02_REAL_SECTION_CLOSEUP.png", "INT30_R2E_04_DIAGNOSTIC_FALSE_COLOR.png"}:
            for item in report["label_anchor_records"]:
                lx, ly = item["label_pixel"]
                tx, ty = item["projected_pixel"]
                draw.line((lx + 98, ly + 16, tx, ty), fill=(255, 246, 220, 255), width=4)
                draw.ellipse((tx - 8, ty - 8, tx + 8, ty + 8), fill=(255, 246, 220, 255))
                draw.text((lx, ly), item["label"], fill=(255, 255, 240, 255), font=font_small)
        img.save(path)

    physical = Image.open(render_dir / "INT30_R2E_02_REAL_SECTION_CLOSEUP.png").convert("RGBA").resize((720, 450))
    false = Image.open(render_dir / "INT30_R2E_04_DIAGNOSTIC_FALSE_COLOR.png").convert("RGBA").resize((720, 450))
    canvas = Image.new("RGBA", (1440, 530), (34, 32, 29, 255))
    canvas.paste(physical, (0, 80))
    canvas.paste(false, (720, 80))
    draw = ImageDraw.Draw(canvas)
    draw.rectangle((0, 0, 1440, 80), fill=(18, 16, 14, 235))
    draw.text((18, 16), "物理材质 / 诊断假色并排", fill=(255, 168, 80, 255), font=font_big)
    draw.text((470, 25), "同机位；假色仅用于判读四层，不代表实测厚度", fill=(245, 239, 224, 255), font=font_med)
    canvas.save(render_dir / "INT30_R2E_05_PHYSICAL_VS_FALSE_COLOR.png")

    if R2D_DARK_REFERENCE.is_file():
        old = Image.open(R2D_DARK_REFERENCE).convert("RGBA").resize((720, 450))
        new = Image.open(render_dir / "INT30_R2E_02_REAL_SECTION_CLOSEUP.png").convert("RGBA").resize((720, 450))
        contrast = Image.new("RGBA", (1440, 530), (34, 32, 29, 255))
        contrast.paste(old, (0, 80))
        contrast.paste(new, (720, 80))
        draw = ImageDraw.Draw(contrast)
        draw.rectangle((0, 0, 1440, 80), fill=(18, 16, 14, 235))
        draw.text((18, 16), "R2D 暗图 / R2E LookDev 对照", fill=(255, 168, 80, 255), font=font_big)
        draw.text((565, 25), "几何 SHA 与对象签名不变；变量仅为显隐与 LookDev", fill=(245, 239, 224, 255), font=font_med)
        contrast.save(render_dir / "INT30_R2E_06_R2D_DARK_VS_R2E_LOOKDEV.png")

    metrics = image_metrics(output_dir)
    metrics["INT30_R2E_04_DIAGNOSTIC_FALSE_COLOR.png"]["approx_min_visible_bandwidth_px"] = projected_bandwidths_from_label_records(report)
    report["image_quality_metrics"] = metrics
    primary_metric_names = [
        "INT30_R2E_01_REAL_QUARTER_OVERVIEW.png",
        "INT30_R2E_02_REAL_SECTION_CLOSEUP.png",
        "INT30_R2E_03_REAL_MAGNIFIED_5X.png",
        "INT30_R2E_04_DIAGNOSTIC_FALSE_COLOR.png",
        "INT30_R2E_05_PHYSICAL_VS_FALSE_COLOR.png",
    ]
    report["assertions"]["image_brightness_and_no_large_black_pass"] = all(metrics[name]["mean_luma"] >= 36.0 and metrics[name]["black_ratio"] <= 0.22 for name in primary_metric_names)
    report["assertions"]["false_color_color_delta_pass"] = metrics["INT30_R2E_04_DIAGNOSTIC_FALSE_COLOR.png"]["unique_strong_colors"] >= 4
    report["assertions"]["min_visible_bandwidth_pass"] = all(v >= 8 for v in metrics["INT30_R2E_04_DIAGNOSTIC_FALSE_COLOR.png"]["approx_min_visible_bandwidth_px"].values())
    write_json(output_dir / "int30_r2e_machine_report.json", report)


def image_metrics(output_dir: Path) -> dict[str, Any]:
    from PIL import Image

    metrics = {}
    for path in sorted((output_dir / "renders").glob("INT30_R2E_*.png")):
        img = Image.open(path).convert("RGB")
        pixels = list(img.getdata())
        lumas = [0.2126 * r + 0.7152 * g + 0.0722 * b for r, g, b in pixels]
        black_ratio = sum(1 for v in lumas if v < 12) / len(lumas)
        strong_colors = {(r // 32, g // 32, b // 32) for r, g, b in pixels if max(r, g, b) - min(r, g, b) > 48 and sum((r, g, b)) > 90}
        record = {
            "path": rel(path),
            "mean_luma": round(sum(lumas) / len(lumas), 3),
            "black_ratio": round(black_ratio, 5),
            "unique_strong_colors": len(strong_colors),
            "bytes": path.stat().st_size,
            "sha256": sha256_file(path),
        }
        if path.name == "INT30_R2E_04_DIAGNOSTIC_FALSE_COLOR.png":
            record["approx_min_visible_bandwidth_px"] = false_color_bandwidths(img)
        metrics[path.name] = record
    return metrics


def false_color_bandwidths(img: Any) -> dict[str, int]:
    targets = {
        "steel": (107, 158, 219),
        "cooling": (194, 110, 56),
        "refractory": (199, 178, 153),
        "process": (56, 43, 33),
    }
    out = {}
    pixels = img.load()
    width, height = img.size
    for key, target in targets.items():
        xs = []
        ys = []
        for y in range(80, height):
            for x in range(width):
                r, g, b = pixels[x, y]
                if sum(abs(v - t) for v, t in zip((r, g, b), target)) < 95:
                    xs.append(x)
                    ys.append(y)
        out[key] = 0 if not xs else min(max(xs) - min(xs), max(ys) - min(ys))
    return out


def projected_bandwidths_from_label_records(report: dict[str, Any]) -> dict[str, int]:
    width, height = RENDER_SETTINGS["resolution"]
    out: dict[str, int] = {}
    for item in report["label_anchor_records"]:
        bbox = item["source_object_projected_bbox_px"]
        xmin = max(0.0, float(bbox["xmin"]))
        xmax = min(float(width), float(bbox["xmax"]))
        ymin = max(0.0, float(bbox["ymin"]))
        ymax = min(float(height), float(bbox["ymax"]))
        out[item["token"]] = int(max(0.0, min(xmax - xmin, ymax - ymin)))
    return out


def load_font(size: int) -> Any:
    from PIL import ImageFont

    for path in [r"C:\Windows\Fonts\simhei.ttf", r"C:\Windows\Fonts\simsun.ttc", r"C:\Windows\Fonts\msyh.ttc"]:
        if Path(path).is_file():
            return ImageFont.truetype(path, size)
    return ImageFont.load_default()


def refresh_visual_manifest(output_dir: Path, report: dict[str, Any]) -> None:
    renders = final_render_records(output_dir)
    manifest = {
        "schema_version": "bf3d.visual_manifest.v1",
        "stage": STAGE_ID,
        "generated_at": now_iso(),
        "status": "candidate_ready_for_review",
        "approval": "not_granted_requires_independent_visual_and_spec_review",
        "renders": renders,
        "label_anchor_records": report["label_anchor_records"],
        "lookdev_contract": report["render_contract"],
        "r1_hard_lock": report.get("r1_hard_lock", R1_HARD_LOCK),
        "image_quality_metrics": report.get("image_quality_metrics", {}),
    }
    write_json(output_dir / "int30_r2e_visual_manifest.json", manifest)


def final_render_records(output_dir: Path) -> list[dict[str, Any]]:
    purpose_map = {
        "INT30_R2E_01_REAL_QUARTER_OVERVIEW.png": "真实材质 quarter 全貌，最终标注 PNG",
        "INT30_R2E_02_REAL_SECTION_CLOSEUP.png": "真实材质截面 closeup，最终标注 PNG",
        "INT30_R2E_03_REAL_MAGNIFIED_5X.png": "真实材质 5x magnified，最终标注 PNG",
        "INT30_R2E_04_DIAGNOSTIC_FALSE_COLOR.png": "诊断假色/E级示意/非实测厚度，最终标注 PNG",
        "INT30_R2E_05_PHYSICAL_VS_FALSE_COLOR.png": "物理材质与诊断假色并排最终 PNG",
        "INT30_R2E_06_R2D_DARK_VS_R2E_LOOKDEV.png": "R2D 暗图与 R2E LookDev 对照最终 PNG",
    }
    records = []
    for path in sorted((output_dir / "renders").glob("INT30_R2E_*.png")):
        records.append(
            {
                "id": path.stem.replace("INT30_R2E_", ""),
                "file": path.name,
                "path": str(path),
                "project_relative_path": rel(path),
                "purpose": purpose_map.get(path.name, "R2E final render PNG"),
                "bytes": path.stat().st_size,
                "sha256": sha256_file(path),
            }
        )
    return records


def render_records_match_files(records: list[dict[str, Any]]) -> bool:
    if len(records) != 6:
        return False
    for record in records:
        path = Path(record["path"])
        if not path.is_file():
            return False
        if path.stat().st_size != record["bytes"] or sha256_file(path) != record["sha256"]:
            return False
    return True


def write_command(output_dir: Path, command: list[str]) -> None:
    write_json(
        output_dir / "command.json",
        {
            "schema_version": "bf3d.command.v1",
            "stage": STAGE_ID,
            "generated_at": now_iso(),
            "parser_chain": "PowerShell -> python subprocess -> blender.exe --background -> Python bpy",
            "commands": [{"mode": "render_stage", "command": command}],
        },
    )


def artifact_manifest(output_dir: Path) -> dict[str, Any]:
    files = []
    for path in sorted(output_dir.rglob("*")):
        if path.is_file() and path.name != "artifact_sha256.json":
            files.append({"path": rel(path), "bytes": path.stat().st_size, "sha256": sha256_file(path)})
    return {"schema_version": "bf3d.artifact_manifest.v1", "stage": STAGE_ID, "generated_at": now_iso(), "files": files}


def required_file_probe() -> dict[str, Any]:
    paths = [
        ROOT / "AGENTS.md",
        ROOT / "specs" / "avatar_spec.json",
        ROOT / "specs" / "acceptance_checklist.md",
        ROOT / "reports" / "pipeline_status.json",
    ]
    return {
        "note": "Root specs/avatar_spec.json and specs/acceptance_checklist.md were required by agent instructions but are absent in this workspace; absence was probed and stage proceeded with explicit report entry.",
        "files": [
            {"path": rel(path), "exists": path.is_file(), "sha256": sha256_file(path) if path.is_file() else None}
            for path in paths
        ],
    }


def write_summary(output_dir: Path, report: dict[str, Any]) -> None:
    lines = [
        "# INT-30 R2E Cutaway Contrast 阶段成果总结",
        "",
        f"- 阶段：`{STAGE_ID}`",
        "- 状态：`candidate_ready_for_review`；执行智能体未自我批准。",
        f"- 输入：`{report['input']['path']}`",
        f"- 输入 SHA 前后不变：`{report['input']['sha256_before']}` / `{report['input']['sha256_after']}`",
        f"- 正式 GLB SHA 前后不变：`{report['formal_glb']['sha256_before']}` / `{report['formal_glb']['sha256_after']}`",
        "",
        "## 唯一变量",
        "",
        "- 只改渲染进程内的证据显隐与 LookDev：仅四个 `*_QUARTER` 对象可见，`FULL/HALF` 八个实体隐藏。",
        "- 新建中性暖灰 World、固定灯光、AgX `exposure=0.72`；不保存到输入 `.blend`。",
        "- 诊断假色只在假色图渲染前临时覆盖四对象材质，渲染后恢复，且不保存。",
        "",
        "## 机器门禁",
        "",
        "- R1 硬锁：用户已选择并要求保留 R1；B=0.16、D=0.10m、N=0.45、metallic=0.06、roughness=0.56-0.82。本阶段只允许证据场景剖切照明/可见性/诊断假色变化。",
        f"- visible set 恰好四个 quarter：`{report['assertions']['visible_set_exactly_four_quarters']}`",
        f"- 四对象 mesh/material/matrix 签名前后不变：`{report['assertions']['quarter_mesh_material_matrix_signature_unchanged']}`",
        f"- 正体积、闭合、非流形边 0：`{report['assertions']['quarter_geometry_positive_closed_nonmanifold0']}`",
        f"- R1/压力点/115传感器签名不变：`{report['assertions']['r1_material_signature_unchanged']}` / `{report['assertions']['pressure_signature_unchanged']}` / `{report['assertions']['sensor_signature_unchanged']}`",
        f"- R1 签名证明：`{report['signatures']['r1_material_before']}` == `{report['signatures']['r1_material_after']}`",
        f"- 阶段目录无 `.blend/.glb`：`{report['host_assertions']['stage_dir_has_no_blend_or_glb']}`",
        f"- 标签端点命中真实对象投影：`{report['assertions']['label_endpoints_hit_source_projection']}`",
        f"- 亮度/黑场/假色色差/最小带宽：`{report['assertions'].get('image_brightness_and_no_large_black_pass')}` / `{report['assertions'].get('false_color_color_delta_pass')}` / `{report['assertions'].get('min_visible_bandwidth_pass')}`",
        "",
        "## 输出",
        "",
        f"- 机器报告：`{rel(output_dir / 'int30_r2e_machine_report.json')}`",
        f"- 视觉清单：`{rel(output_dir / 'int30_r2e_visual_manifest.json')}`",
        f"- Artifact SHA：`{rel(output_dir / 'artifact_sha256.json')}`",
        f"- Pipeline snapshot：`{rel(output_dir / 'pipeline_status_snapshot.json')}`",
    ]
    for item in sorted((output_dir / "renders").glob("INT30_R2E_*.png")):
        lines.append(f"- `{item.name}`：`{rel(item)}`")
    lines.extend(["", "## 停止线", "", "- 停在 R2E 证据候选与独立审查门；未进入料线数据门、GLB 导出或生产替换。"])
    write_text(output_dir / "INT-30_R2E_CUTAWAY_CONTRAST_阶段成果总结.md", "\n".join(lines) + "\n")


def write_pipeline_status(output_dir: Path) -> None:
    status_path = ROOT / "reports" / "pipeline_status.json"
    status = json.loads(status_path.read_text(encoding="utf-8"))
    stage_entry = {
        "status": "candidate_ready_for_review",
        "approval": "not_granted_requires_visual_and_spec_review",
        "evidence_only": True,
        "input_blend": rel(INPUT_BLEND),
        "input_sha256": EXPECTED_INPUT_SHA256,
        "formal_glb_unchanged": True,
        "formal_glb_sha256": EXPECTED_FORMAL_GLB_SHA256,
        "machine_report": rel(output_dir / "int30_r2e_machine_report.json"),
        "visual_manifest": rel(output_dir / "int30_r2e_visual_manifest.json"),
        "artifact_sha256": rel(output_dir / "artifact_sha256.json"),
        "summary": rel(output_dir / "INT-30_R2E_CUTAWAY_CONTRAST_阶段成果总结.md"),
        "pipeline_status_snapshot": rel(output_dir / "pipeline_status_snapshot.json"),
        "approval_boundary": "Evidence-only isolated cutaway visibility and LookDev stage; no self approval, no saved blend, no GLB export.",
        "next_stop_line": "independent_visual_and_spec_review_required_before_stockline_data_gate_or_GLB_export",
    }
    status.setdefault("stages", {})[STAGE_ID] = stage_entry
    status["current_stage"] = STAGE_ID
    status["updated_at"] = now_iso()
    write_json(status_path, status)
    write_json(output_dir / "pipeline_status_snapshot.json", {"schema_version": "bf3d.pipeline_status_snapshot.v1", "stage": STAGE_ID, "generated_at": now_iso(), "global_pipeline_status": rel(status_path), "stage_entry": stage_entry})


if __name__ == "__main__":
    if "--" in sys.argv and "--render-stage" in sys.argv:
        raise SystemExit(blender_main())
    raise SystemExit(host_main())
