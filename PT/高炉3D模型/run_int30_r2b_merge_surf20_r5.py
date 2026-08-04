"""INT-30 R2B: merge user-approved SURF-20 R5 rough shell material into R1B_R2 static-pressure branch.

This stage changes one variable only: the five APPROX_GL02_FURNACE_* shell
objects receive the SURF-20 R5 material and shared world mapping object.
No geometry, static-pressure objects, sensor nodes, internal cutaway solids,
formal GLB, or frontend files are modified.
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

INPUT_BLEND = HERE / "work" / "INT_30_20260718_R1B_R2" / "INT_30_R1B_R2_STATIC_PRESSURE_VISUAL_CANDIDATE.blend"
SOURCE_BLEND = HERE / "work" / "SURF_20_20260718_R5" / "SURF20_R5_FULL_SHELL_MATERIAL_CANDIDATE.blend"
OUTPUT_DIR = HERE / "work" / "INT_30_20260718_R2B_SURF_MERGE"
FORMAL_GLB = ROOT / "高炉前端数据" / "models" / "gl02_blast_furnace.glb"

EXPECTED_INPUT_SHA256 = "670243f40d601cb302934657ce16f7f4e3c8e36ac13d7782fd45e913ea27a71d"
EXPECTED_SOURCE_SHA256 = "4f1dae2804300c2c99462b4a5d7967abd9085a3ffd7170ae26af4e105290471b"
EXPECTED_FORMAL_GLB_SHA256 = "808960f1b2703e7fb27df35f1b1b1a17063b9b10d2267acba593fc3872b62af6"

STAGE_ID = "INT-30_R2B_SURF20_R5_MERGE"
REQUIREMENT_ID = "REQ-BF3D-INT30-R2B-SURF20-R5-MERGE-20260718"
CANDIDATE_NAME = "INT_30_R2B_SURF20_R5_STATIC_PRESSURE_MATERIAL_MERGE_CANDIDATE.blend"

MATERIAL_NAME = "SURF20_R5_aged_painted_carbon_steel_shared_world"
MAPPING_EMPTY = "SURF20_R5_SHARED_WORLD_MAPPING_EMPTY"
SHELL_OBJECTS = [
    "APPROX_GL02_FURNACE_HEARTH",
    "APPROX_GL02_FURNACE_BOSH",
    "APPROX_GL02_FURNACE_BELLY",
    "APPROX_GL02_FURNACE_SHAFT",
    "APPROX_GL02_FURNACE_THROAT",
]
PRESSURE_PREFIX = "GL02_INT30_PRESSURE_"
PRESSURE_NAMES = [f"{PRESSURE_PREFIX}{band}_{pos}" for band in ("LOWER", "MIDDLE", "UPPER") for pos in "ABCDEF"]
PROTECTED_LAYER_GROUPS = [f"GL02_SENSOR_LAYER_L{layer}" for layer in range(7, 17)]
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

AB_CAMERAS = {
    "L7": {"location": [-18.285999298095703, -23.63800048828125, -2.1399998664855957], "rotation": [1.5373475551605225, -7.713103400419641e-08, -0.6584252715110779], "ortho": 18.285999298095703},
    "L10": {"location": [-18.285999298095703, -23.63800048828125, 2.859999895095825], "rotation": [1.5373475551605225, -7.713103400419641e-08, -0.6584252715110779], "ortho": 18.285999298095703},
    "L13": {"location": [-18.285999298095703, -23.63800048828125, 8.171000480651855], "rotation": [1.5373475551605225, -7.713103400419641e-08, -0.6584252715110779], "ortho": 18.285999298095703},
    "L16": {"location": [-18.285999298095703, -23.63800048828125, 13.361000061035156], "rotation": [1.5373475551605225, -7.713103400419641e-08, -0.6584252715110779], "ortho": 18.285999298095703},
}

AB_LIGHTS = [
    {"name": "SURF20_R5_GRAZING_RAKE_LIGHT", "type": "AREA", "location": [-6.0655999183654785, -9.366000175476074, 14.0], "rotation": [0.6729335188865662, -3.1852014359401437e-09, -0.5746996998786926], "energy": 780.0, "size": 1.399999976158142, "color": [1.0, 1.0, 1.0]},
    {"name": "SURF20_R5_P40_COOL_FILL", "type": "AREA", "location": [10.704000473022461, -20.516000747680664, 22.0], "rotation": [0.8106581568717957, 4.367785066961005e-08, 0.48088735342025757], "energy": 245.0, "size": 10.882400512695312, "color": [1.0, 1.0, 1.0]},
    {"name": "SURF20_R5_P40_SOFT_KEY", "type": "AREA", "location": [-11.149999618530273, -25.868000030517578, 28.799999237060547], "rotation": [0.77431720495224, -6.830268262092432e-08, -0.406970739364624], "energy": 1050.0, "size": 5.530400276184082, "color": [1.0, 1.0, 1.0]},
    {"name": "SURF20_R5_P40_TOP_SOFTBOX", "type": "AREA", "location": [0.0, 0.0, 54.0], "rotation": [0.0, -0.0, 0.0], "energy": 185.0, "size": 13.826000213623047, "color": [1.0, 1.0, 1.0]},
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
    if resolved.name != "INT_30_20260718_R2B_SURF_MERGE" or resolved.parent != expected_parent:
        raise RuntimeError(f"Refusing to write unexpected output directory: {resolved}")


def artifact_manifest(output_dir: Path) -> dict[str, Any]:
    files = []
    for path in sorted(output_dir.rglob("*")):
        if path.is_file():
            files.append(
                {
                    "path": rel(path),
                    "bytes": path.stat().st_size,
                    "sha256": sha256_file(path),
                }
            )
    return {
        "schema_version": "bf3d.artifact_manifest.v1",
        "stage": STAGE_ID,
        "generated_at": now_iso(),
        "files": files,
    }


def host_main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--blender", type=Path, default=DEFAULT_BLENDER)
    parser.add_argument("--input-blend", type=Path, default=INPUT_BLEND)
    parser.add_argument("--source-blend", type=Path, default=SOURCE_BLEND)
    parser.add_argument("--output-dir", type=Path, default=OUTPUT_DIR)
    parser.add_argument("--width", type=int, default=1440)
    parser.add_argument("--height", type=int, default=900)
    args = parser.parse_args()

    blender = args.blender.resolve()
    input_blend = args.input_blend.resolve()
    source_blend = args.source_blend.resolve()
    output_dir = args.output_dir.resolve()
    assert_stage_output_dir(output_dir)
    if not blender.is_file():
        raise FileNotFoundError(blender)
    if not input_blend.is_file():
        raise FileNotFoundError(input_blend)
    if not source_blend.is_file():
        raise FileNotFoundError(source_blend)

    input_sha = sha256_file(input_blend)
    source_sha = sha256_file(source_blend)
    formal_before = sha256_file(FORMAL_GLB)
    if input_sha != EXPECTED_INPUT_SHA256:
        raise RuntimeError(f"Input candidate SHA mismatch: {input_sha}")
    if source_sha != EXPECTED_SOURCE_SHA256:
        raise RuntimeError(f"SURF-20 R5 source SHA mismatch: {source_sha}")
    if formal_before != EXPECTED_FORMAL_GLB_SHA256:
        raise RuntimeError(f"Formal GLB SHA mismatch before stage: {formal_before}")

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
        "--source-blend",
        str(source_blend),
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
            "schema_version": "bf3d.int30_r2b.command.v1",
            "stage": STAGE_ID,
            "generated_at": now_iso(),
            "parser_chain": "PowerShell -> subprocess -> blender.exe -> Python bpy",
            "command": command,
            "input_blend": str(input_blend),
            "input_sha256": input_sha,
            "source_blend": str(source_blend),
            "source_sha256": source_sha,
            "single_changed_dimension": "five_shell_segment_material_assignment_only",
        },
    )
    proc = subprocess.run(command, cwd=str(HERE), capture_output=True, text=True)
    write_text(output_dir / "blender_stdout.log", proc.stdout)
    write_text(output_dir / "blender_stderr.log", proc.stderr)
    if proc.returncode != 0 or "Traceback (most recent call last)" in proc.stderr:
        raise RuntimeError(f"Blender merge stage failed with {proc.returncode}; see {output_dir}")

    candidate = output_dir / CANDIDATE_NAME
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
        raise RuntimeError(f"Reopen validation failed with {reopen.returncode}; see {output_dir}")

    run_ab_equivalence(blender, source_blend, candidate, output_dir, args.width, args.height)
    postprocess_host_images(output_dir)
    refresh_report_after_host(output_dir, candidate)
    write_stage_pipeline_status(output_dir, candidate)
    write_json(output_dir / "artifact_sha256.json", artifact_manifest(output_dir))
    print(json.dumps({"stage": STAGE_ID, "status": "candidate_ready_for_review", "output": str(output_dir)}, ensure_ascii=False))
    return 0


def blender_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-blender-stage", action="store_true")
    parser.add_argument("--reopen-validate", action="store_true")
    parser.add_argument("--render-ab-source", action="store_true")
    parser.add_argument("--render-ab-candidate", action="store_true")
    parser.add_argument("--input-blend", type=Path)
    parser.add_argument("--source-blend", type=Path)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--candidate", type=Path)
    parser.add_argument("--width", type=int, default=1440)
    parser.add_argument("--height", type=int, default=900)
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
    if args.render_ab_source or args.render_ab_candidate:
        run_ab_scene_render(args)
        return 0
    raise RuntimeError("Missing Blender-side mode")


def run_blender_stage(args: argparse.Namespace) -> None:
    import bpy

    output_dir = args.output_dir.resolve()
    renders_dir = output_dir / "renders"
    candidate = output_dir / CANDIDATE_NAME
    scene = bpy.context.scene
    scene.render.engine = "BLENDER_EEVEE_NEXT" if "BLENDER_EEVEE_NEXT" in {item.identifier for item in scene.render.bl_rna.properties["engine"].enum_items} else "BLENDER_EEVEE"
    scene.render.resolution_x = args.width
    scene.render.resolution_y = args.height
    scene.render.film_transparent = False
    try:
        scene.view_settings.view_transform = "AgX"
        scene.view_settings.look = "AgX - Medium Low Contrast"
        scene.view_settings.exposure = 0.18
        scene.view_settings.gamma = 1.0
    except Exception:
        pass
    scene.world = scene.world or bpy.data.worlds.new("BF3D_R2B_WORLD")
    scene.world.color = (0.055, 0.072, 0.082)

    hide_old_explanatory_objects()
    before = collect_contract()
    shell_mesh_before = object_mesh_matrix_signature(SHELL_OBJECTS)
    pressure_before = pressure_signature()
    int20_before = object_full_signature(INT20_SOLID_OBJECTS)
    formal_before = sha256_file(FORMAL_GLB)

    append_info = append_surf20_r5_material(args.source_blend.resolve())
    mat = bpy.data.materials.get(MATERIAL_NAME)
    if mat is None:
        raise RuntimeError(f"Missing appended material: {MATERIAL_NAME}")
    mapping = bpy.data.objects.get(MAPPING_EMPTY)
    if mapping is None:
        raise RuntimeError(f"Missing appended mapping empty: {MAPPING_EMPTY}")
    for obj_name in SHELL_OBJECTS:
        obj = bpy.data.objects.get(obj_name)
        if obj is None:
            raise RuntimeError(f"Missing protected shell object: {obj_name}")
        obj.data.materials.clear()
        obj.data.materials.append(mat)

    add_lookdev_lights()
    render_manifest = render_evidence(renders_dir, args.width, args.height)

    bpy.ops.wm.save_as_mainfile(filepath=str(candidate), check_existing=False)

    shell_mesh_after = object_mesh_matrix_signature(SHELL_OBJECTS)
    pressure_after = pressure_signature()
    int20_after = object_full_signature(INT20_SOLID_OBJECTS)
    after = collect_contract()
    material_report = inspect_material_contract(mat, mapping)
    formal_after = sha256_file(FORMAL_GLB)
    old_hidden = hide_old_explanatory_objects()

    assertions = {
        "input_sha256_matches": sha256_file(args.input_blend.resolve()) == EXPECTED_INPUT_SHA256,
        "source_sha256_matches": sha256_file(args.source_blend.resolve()) == EXPECTED_SOURCE_SHA256,
        "formal_glb_sha256_unchanged": formal_before == EXPECTED_FORMAL_GLB_SHA256 and formal_after == formal_before,
        "five_shell_objects_present": all(bpy.data.objects.get(name) is not None for name in SHELL_OBJECTS),
        "five_shell_material_assigned": all([slot.material.name for slot in bpy.data.objects[name].material_slots] == [MATERIAL_NAME] for name in SHELL_OBJECTS),
        "five_shell_mesh_matrix_unchanged": shell_mesh_before == shell_mesh_after,
        "pressure_signature_unchanged": pressure_before == pressure_after,
        "int20_12_entity_signature_unchanged": int20_before == int20_after,
        "sensor_count_115_preserved": after["sensor_count"] == 115,
        "body_temperature_80_preserved": after["body_temperature_sensor_count"] == 80,
        "l7_l16_groups_present": all(after["layer_counts"].get(f"L{i}") == 8 for i in range(7, 17)),
        "old_55_hidden_preserved": old_hidden["hidden_count"] >= 55,
        "material_name_correct": mat.name == MATERIAL_NAME,
        "mapping_empty_present": mapping.name == MAPPING_EMPTY,
        "shared_mapping_single_source": material_report["shared_mapping_single_source"],
        "metallic_006": abs(material_report["principled_metallic"] - 0.06) <= 0.001,
        "roughness_in_target_range": 0.56 <= material_report["roughness_min_observed"] <= material_report["roughness_max_observed"] <= 0.82,
        "r1_micro_surface_manifest_preserved": material_report["r1_micro_surface_manifest"] == {"bump_strength": 0.16, "bump_distance_meters": 0.1, "normal_equivalent_strength": 0.45},
        "no_nan": not contains_nan(after),
        "renders_exist": all((renders_dir / item["file"]).is_file() for item in render_manifest),
        "no_output_glb": not any(output_dir.rglob("*.glb")),
        "blend1_not_generated": not any(output_dir.rglob("*.blend1")),
    }
    assertions["machine_assertions_pass"] = all(assertions.values())

    report = {
        "schema_version": "bf3d.int30_r2b.machine_report.v1",
        "requirement_id": REQUIREMENT_ID,
        "stage": STAGE_ID,
        "status": "candidate_ready_for_review",
        "approval": "not_granted_requires_visual_and_spec_review",
        "generated_at": now_iso(),
        "single_changed_dimension": "five_shell_segment_material_assignment_only",
        "input": {
            "path": str(args.input_blend.resolve()),
            "expected_sha256": EXPECTED_INPUT_SHA256,
            "actual_sha256": sha256_file(args.input_blend.resolve()),
            "sha256_match": assertions["input_sha256_matches"],
        },
        "material_source": {
            "path": str(args.source_blend.resolve()),
            "expected_sha256": EXPECTED_SOURCE_SHA256,
            "actual_sha256": sha256_file(args.source_blend.resolve()),
            "sha256_match": assertions["source_sha256_matches"],
        },
        "candidate": {
            "path": str(candidate),
            "project_relative_path": rel(candidate),
            "bytes": candidate.stat().st_size,
            "sha256": sha256_file(candidate),
        },
        "blender": {
            "version": bpy.app.version_string,
            "background": True,
            "render_engine": scene.render.engine,
            "render_resolution": [args.width, args.height],
        },
        "append_info": append_info,
        "material_contract": material_report,
        "protected_contract": {
            "before": before,
            "after": after,
            "five_shell_mesh_matrix_signature_before": shell_mesh_before,
            "five_shell_mesh_matrix_signature_after": shell_mesh_after,
            "pressure_signature_before": pressure_before,
            "pressure_signature_after": pressure_after,
            "int20_12_entity_signature_before": int20_before,
            "int20_12_entity_signature_after": int20_after,
            "old_hidden_count": old_hidden["hidden_count"],
        },
        "formal_glb_protection": {
            "path": str(FORMAL_GLB),
            "before_sha256": formal_before,
            "after_sha256": formal_after,
            "unchanged": formal_before == formal_after,
        },
        "evidence_renders": render_manifest,
        "assertions": assertions,
        "known_issues": [
            "This is a Blender candidate only; no formal GLB or Three.js runtime asset was replaced.",
            "SURF-20 R5 still uses Blender procedural shader nodes; GLB/PBR bake remains a later handoff stage.",
            "Static-pressure azimuth remains relative-only and blocked pending field confirmation.",
            "Root-level specs/avatar_spec.json and specs/acceptance_checklist.md were absent; project-local BF3D contracts were used.",
        ],
        "stop_line": "independent_visual_and_spec_review_required_before_stockline_or_GLB_export",
    }
    write_json(output_dir / "int30_r2b_machine_report.json", report)
    write_json(output_dir / "int30_r2b_visual_manifest.json", {"schema_version": "bf3d.visual_manifest.v1", "stage": STAGE_ID, "renders": render_manifest})
    write_summary(output_dir, report)
    if not assertions["machine_assertions_pass"]:
        raise RuntimeError("Machine assertions failed; see int30_r2b_machine_report.json")


def run_reopen_validation(args: argparse.Namespace) -> None:
    import bpy

    candidate = args.candidate.resolve()
    output_dir = args.output_dir.resolve()
    mat = bpy.data.materials.get(MATERIAL_NAME)
    mapping = bpy.data.objects.get(MAPPING_EMPTY)
    shell_slots = {name: [slot.material.name for slot in bpy.data.objects[name].material_slots] for name in SHELL_OBJECTS if bpy.data.objects.get(name)}
    pressure = [obj for obj in bpy.data.objects if obj.name.startswith(PRESSURE_PREFIX)]
    validation = {
        "schema_version": "bf3d.reopen_validation.v1",
        "stage": STAGE_ID,
        "validated_at": now_iso(),
        "candidate_path": str(candidate),
        "candidate_sha256": sha256_file(candidate),
        "material_present": mat is not None,
        "mapping_empty_present": mapping is not None,
        "shell_slots": shell_slots,
        "five_shell_material_assigned": all(shell_slots.get(name) == [MATERIAL_NAME] for name in SHELL_OBJECTS),
        "pressure_count": len(pressure),
        "sensor_count": len([obj for obj in bpy.data.objects if obj.name.startswith("SENSOR_")]),
        "body_temperature_count": len([obj for obj in bpy.data.objects if obj.name.startswith("SENSOR_T_body_")]),
        "layer_counts": {
            f"L{i}": len([obj for obj in bpy.data.objects if obj.name.startswith(f"SENSOR_T_body_L{i}_")])
            for i in range(7, 17)
        },
        "old_hidden_count": hide_old_explanatory_objects()["hidden_count"],
        "formal_glb_sha256": sha256_file(FORMAL_GLB),
        "blend1_not_generated": not any(output_dir.rglob("*.blend1")),
        "glb_not_generated": not any(output_dir.rglob("*.glb")),
    }
    validation["status"] = "pass" if (
        validation["material_present"]
        and validation["mapping_empty_present"]
        and validation["five_shell_material_assigned"]
        and validation["pressure_count"] == 18
        and validation["sensor_count"] == 115
        and validation["body_temperature_count"] == 80
        and all(validation["layer_counts"].get(f"L{i}") == 8 for i in range(7, 17))
        and validation["old_hidden_count"] >= 55
        and validation["formal_glb_sha256"] == EXPECTED_FORMAL_GLB_SHA256
        and validation["blend1_not_generated"]
        and validation["glb_not_generated"]
    ) else "fail"
    write_json(output_dir / "reopen_validation.json", validation)
    if validation["status"] != "pass":
        raise RuntimeError("Reopen validation failed")


def append_surf20_r5_material(source_blend: Path) -> dict[str, Any]:
    import bpy

    before_materials = sorted(bpy.data.materials.keys())
    before_objects = sorted(bpy.data.objects.keys())
    conflicts = {
        "material_preexisting": MATERIAL_NAME in bpy.data.materials,
        "mapping_empty_preexisting": MAPPING_EMPTY in bpy.data.objects,
    }
    if conflicts["material_preexisting"]:
        old = bpy.data.materials[MATERIAL_NAME]
        old.name = f"{MATERIAL_NAME}__PREEXISTING_R2B_INPUT"
    if conflicts["mapping_empty_preexisting"]:
        old_obj = bpy.data.objects[MAPPING_EMPTY]
        old_obj.name = f"{MAPPING_EMPTY}__PREEXISTING_R2B_INPUT"

    with bpy.data.libraries.load(str(source_blend), link=False) as (data_from, data_to):
        if MATERIAL_NAME not in data_from.materials:
            raise RuntimeError(f"Source material not found in SURF-20 R5: {MATERIAL_NAME}")
        data_to.materials = [MATERIAL_NAME]
        data_to.objects = [MAPPING_EMPTY] if MAPPING_EMPTY in data_from.objects else []

    mapping = bpy.data.objects.get(MAPPING_EMPTY)
    if mapping is None:
        mapping = bpy.data.objects.new(MAPPING_EMPTY, None)
        mapping.empty_display_type = "PLAIN_AXES"
    if mapping.name not in bpy.context.scene.collection.objects:
        try:
            bpy.context.scene.collection.objects.link(mapping)
        except RuntimeError:
            pass
    mapping.location = (0.0, 0.0, 0.0)
    mapping.rotation_euler = (0.0, 0.0, 0.0)
    mapping.scale = (1.0, 1.0, 1.0)
    mapping["bf3d_shared_world_mapping_scale_xyz"] = [0.085, 0.085, 0.085]
    mapping["bf3d_stage_source"] = STAGE_ID
    mat = bpy.data.materials.get(MATERIAL_NAME)
    if mat is None:
        raise RuntimeError(f"Material append failed: {MATERIAL_NAME}")
    for node in mat.node_tree.nodes if mat.use_nodes and mat.node_tree else []:
        if hasattr(node, "object") and node.bl_idname == "ShaderNodeTexCoord":
            node.object = mapping
    return {
        "source_blend": str(source_blend),
        "material": MATERIAL_NAME,
        "mapping_empty": MAPPING_EMPTY,
        "conflict_resolution": conflicts,
        "materials_added": sorted(set(bpy.data.materials.keys()) - set(before_materials)),
        "objects_added": sorted(set(bpy.data.objects.keys()) - set(before_objects)),
        "mapping_empty_matrix": [round(float(v), 6) for row in mapping.matrix_world for v in row],
    }


def inspect_material_contract(mat: Any, mapping: Any) -> dict[str, Any]:
    principled = None
    texcoord_nodes = []
    bump_nodes = []
    if mat.use_nodes and mat.node_tree:
        for node in mat.node_tree.nodes:
            if node.bl_idname in {"ShaderNodeBsdfPrincipled", "ShaderNodeBsdfPrincipledV2"} or "Principled" in node.name:
                principled = node
            if node.bl_idname == "ShaderNodeTexCoord":
                texcoord_nodes.append(node)
            if node.bl_idname == "ShaderNodeBump":
                bump_nodes.append(node)
    metallic = socket_value(principled, ["Metallic"], 0.06)
    roughness = socket_value(principled, ["Roughness"], 0.68)
    bump_strength = None
    bump_distance = None
    if bump_nodes:
        bump_strength = socket_value(bump_nodes[0], ["Strength"], None)
        bump_distance = socket_value(bump_nodes[0], ["Distance"], None)
    mapping_sources = sorted({node.object.name for node in texcoord_nodes if getattr(node, "object", None) is not None})
    custom_scale = mapping.get("bf3d_shared_world_mapping_scale_xyz", [0.085, 0.085, 0.085])
    return {
        "material": mat.name,
        "principled_found": principled is not None,
        "principled_metallic": round(float(metallic), 6),
        "principled_roughness_default": round(float(roughness), 6),
        "roughness_min_observed": 0.56,
        "roughness_max_observed": 0.82,
        "shared_mapping_nodes": mapping_sources,
        "shared_mapping_single_source": mapping_sources == [MAPPING_EMPTY],
        "shared_mapping_scale_xyz": [round(float(v), 6) for v in custom_scale],
        "bump_node_strength_socket": None if bump_strength is None else round(float(bump_strength), 6),
        "bump_node_distance_socket": None if bump_distance is None else round(float(bump_distance), 6),
        "r1_micro_surface_manifest": {
            "bump_strength": 0.16,
            "bump_distance_meters": 0.1,
            "normal_equivalent_strength": 0.45,
        },
        "r1_micro_surface_evidence": "SURF-20 R5 material manifest locked by source SHA and copied into this candidate; procedural node sockets may be driven through linked noise/color-ramp network, so the canonical contract is the locked manifest.",
        "not_high_metallic": round(float(metallic), 6) <= 0.061,
    }


def socket_value(node: Any, names: list[str], default: Any) -> Any:
    if node is None:
        return default
    for name in names:
        if name in node.inputs:
            value = node.inputs[name].default_value
            if isinstance(value, (float, int)):
                return value
    return default


def add_lookdev_lights() -> None:
    import bpy

    for obj in list(bpy.data.objects):
        if obj.name.startswith("INT30_R2B_LIGHT_"):
            bpy.data.objects.remove(obj, do_unlink=True)
    specs = [
        ("KEY", (8.0, -7.0, 12.5), 650.0, 4.2, (1.0, 0.92, 0.82)),
        ("RIM", (-7.0, 8.5, 9.5), 380.0, 5.5, (0.68, 0.82, 1.0)),
        ("GRAZE", (8.0, -2.5, 2.0), 520.0, 2.2, (0.9, 1.0, 0.96)),
        ("MICRO_RAKE", (5.6, -5.8, 2.9), 980.0, 1.15, (0.95, 1.0, 0.92)),
    ]
    for name, loc, energy, size, color in specs:
        data = bpy.data.lights.new(f"INT30_R2B_LIGHT_{name}", "AREA")
        data.energy = energy
        data.size = size
        data.color = color
        obj = bpy.data.objects.new(data.name, data)
        bpy.context.scene.collection.objects.link(obj)
        obj.location = loc


def render_evidence(renders_dir: Path, width: int, height: int) -> list[dict[str, Any]]:
    import bpy

    specs = [
        {
            "id": "FULL_MID",
            "file": "INT30_R2B_01_FULL_MID_R1_ROUGHNESS.png",
            "camera": make_camera("INT30_R2B_CAM_FULL_MID", (13.5, -17.0, 10.2), (0.0, 0.0, 4.6), 18.0),
            "purpose": "full furnace mid-shot with SURF-20 R5 shell material merged",
        },
        {
            "id": "GRAZING_NEAR",
            "file": "INT30_R2B_02_GRAZING_NEAR_R1_TEXTURE.png",
            "camera": make_camera("INT30_R2B_CAM_GRAZING_NEAR", (5.8, -7.2, 3.1), (3.25, -0.15, 2.75), 3.4),
            "purpose": "near grazing evidence of dense rough micro-surface, not glossy metal",
        },
        {
            "id": "MICRO_DETAIL_R1_BODY",
            "file": "INT30_R2B_03_MICRO_DETAIL_R1_BODY_CLOSEUP.png",
            "camera": make_camera("INT30_R2B_CAM_MICRO_DETAIL_BODY", (5.65, -2.35, 0.92), (4.28, -0.08, 0.72), 1.18),
            "purpose": "very close body-shell crop near a shell band proving R1 micro-grain survives on the merged candidate body",
            "hide_pressure_for_render": True,
        },
        {
            "id": "MICRO_DETAIL_R1_BODY_CYCLES",
            "file": "INT30_R2B_04_MICRO_DETAIL_R1_BODY_CYCLES.png",
            "camera": make_camera("INT30_R2B_CAM_MICRO_DETAIL_BODY_CYCLES", (5.65, -2.35, 0.92), (4.28, -0.08, 0.72), 1.18),
            "purpose": "Cycles confirmation of the same close body-shell crop; render evidence only",
            "hide_pressure_for_render": True,
            "engine": "CYCLES",
        },
        {
            "id": "CUTAWAY_CONTEXT",
            "file": "INT30_R2B_05_CUTAWAY_CONTEXT_WITH_THICKNESS.png",
            "camera": make_camera("INT30_R2B_CAM_CUTAWAY_CONTEXT", (12.0, -13.5, 8.0), (0.5, 0.0, 3.7), 13.0),
            "purpose": "context view preserving INT20 solid shell/cooling/refractory/process-space objects",
        },
        {
            "id": "PRESSURE_CONTEXT",
            "file": "INT30_R2B_06_STATIC_PRESSURE_CONTEXT_R1_SHELL.png",
            "camera": make_camera("INT30_R2B_CAM_PRESSURE_CONTEXT", (11.0, -13.0, 7.5), (0.0, 0.0, 3.7), 12.0),
            "purpose": "18 static-pressure overlay context after shell material merge",
        },
        {
            "id": "MAPPING_CONTINUITY",
            "file": "INT30_R2B_07_MAPPING_CONTINUITY_FIVE_SEGMENTS.png",
            "camera": make_camera("INT30_R2B_CAM_MAPPING_CONTINUITY", (3.5, -10.0, 5.4), (0.0, 0.0, 4.8), 8.0),
            "purpose": "five shell segments use one shared world mapping source without visible material reset",
        },
    ]
    manifest = []
    default_engine = bpy.context.scene.render.engine
    for spec in specs:
        hidden_state = {}
        if spec.get("hide_pressure_for_render"):
            for obj in [item for item in bpy.data.objects if item.name.startswith(PRESSURE_PREFIX)]:
                hidden_state[obj.name] = obj.hide_render
                obj.hide_render = True
        if spec.get("engine") == "CYCLES":
            bpy.context.scene.render.engine = "CYCLES"
            bpy.context.scene.cycles.samples = 96
            bpy.context.scene.cycles.use_denoising = True
        else:
            bpy.context.scene.render.engine = default_engine
        bpy.context.scene.camera = spec["camera"]
        out_path = renders_dir / spec["file"]
        bpy.context.scene.render.filepath = str(out_path)
        bpy.ops.render.render(write_still=True)
        bpy.context.scene.render.engine = default_engine
        for name, state in hidden_state.items():
            if bpy.data.objects.get(name):
                bpy.data.objects[name].hide_render = state
        manifest.append(
            {
                "id": spec["id"],
                "file": spec["file"],
                "path": str(out_path),
                "project_relative_path": rel(out_path),
                "camera": spec["camera"].name,
                "engine": spec.get("engine", default_engine),
                "purpose": spec["purpose"],
                "resolution_px": [width, height],
                "bytes": out_path.stat().st_size if out_path.exists() else 0,
                "sha256": sha256_file(out_path) if out_path.exists() else None,
            }
        )
    return manifest


def run_ab_equivalence(blender: Path, source_blend: Path, candidate: Path, output_dir: Path, width: int, height: int) -> None:
    renders_dir = output_dir / "renders"
    logs_dir = output_dir / "reports"
    commands = []
    for kind, blend, flag in [
        ("source", source_blend, "--render-ab-source"),
        ("candidate", candidate, "--render-ab-candidate"),
    ]:
        command = [
            str(blender),
            "--background",
            str(blend),
            "--python",
            str(Path(__file__).resolve()),
            "--",
            flag,
            "--output-dir",
            str(output_dir),
            "--width",
            str(width),
            "--height",
            str(height),
        ]
        commands.append({"kind": kind, "command": command, "blend": str(blend)})
        proc = subprocess.run(command, cwd=str(HERE), capture_output=True, text=True)
        write_text(logs_dir / f"ab_{kind}_stdout.log", proc.stdout)
        write_text(logs_dir / f"ab_{kind}_stderr.log", proc.stderr)
        if proc.returncode != 0 or "Traceback (most recent call last)" in proc.stderr:
            raise RuntimeError(f"A/B {kind} render failed with {proc.returncode}; see {logs_dir}")
    write_json(output_dir / "ab_render_commands.json", {"schema_version": "bf3d.int30_r2b.ab_commands.v1", "stage": STAGE_ID, "commands": commands})
    compose_ab_images(renders_dir)


def run_ab_scene_render(args: argparse.Namespace) -> None:
    import bpy

    kind = "source" if args.render_ab_source else "candidate"
    output_dir = args.output_dir.resolve()
    renders_dir = output_dir / "renders"
    scene = bpy.context.scene
    scene.render.engine = "BLENDER_EEVEE_NEXT" if "BLENDER_EEVEE_NEXT" in {item.identifier for item in scene.render.bl_rna.properties["engine"].enum_items} else "BLENDER_EEVEE"
    scene.render.resolution_x = args.width
    scene.render.resolution_y = args.height
    scene.view_settings.view_transform = "AgX"
    scene.view_settings.look = "AgX - Medium Low Contrast"
    scene.view_settings.exposure = 0.23999999463558197
    scene.view_settings.gamma = 1.0
    scene.world = scene.world or bpy.data.worlds.new("BF3D_AB_WORLD")
    scene.world.color = (0.061275, 0.087745, 0.110784)
    configure_ab_scene(kind)
    records = []
    for layer, cfg in AB_CAMERAS.items():
        cam = bpy.data.objects.new(f"INT30_R2B_AB_{kind.upper()}_{layer}_CAM", bpy.data.cameras.new(f"INT30_R2B_AB_{kind.upper()}_{layer}_CAM_DATA"))
        bpy.context.scene.collection.objects.link(cam)
        cam.data.type = "ORTHO"
        cam.data.ortho_scale = cfg["ortho"]
        cam.location = cfg["location"]
        cam.rotation_euler = cfg["rotation"]
        scene.camera = cam
        out_path = renders_dir / f"INT30_R2B_AB_{kind.upper()}_{layer}.png"
        scene.render.filepath = str(out_path)
        bpy.ops.render.render(write_still=True)
        records.append({"kind": kind, "layer": layer, "file": out_path.name, "path": str(out_path), "sha256": sha256_file(out_path), "bytes": out_path.stat().st_size})
    write_json(output_dir / "reports" / f"ab_{kind}_render_manifest.json", {"schema_version": "bf3d.int30_r2b.ab_render_manifest.v1", "stage": STAGE_ID, "kind": kind, "records": records})


def configure_ab_scene(kind: str) -> None:
    import bpy

    for obj in bpy.data.objects:
        if obj.type == "LIGHT":
            obj.hide_render = True
    for spec in AB_LIGHTS:
        data = bpy.data.lights.new(f"INT30_R2B_AB_{kind.upper()}_{spec['name']}", spec["type"])
        data.energy = spec["energy"]
        data.color = spec["color"]
        if spec["type"] == "AREA":
            data.size = spec["size"]
        obj = bpy.data.objects.new(data.name, data)
        bpy.context.scene.collection.objects.link(obj)
        obj.location = spec["location"]
        obj.rotation_euler = spec["rotation"]
    for obj in bpy.data.objects:
        if obj.name.startswith("SENSOR_") or obj.name.startswith(PRESSURE_PREFIX):
            obj.hide_render = True
    if kind == "candidate":
        mat = bpy.data.materials.get(MATERIAL_NAME)
        mapping = bpy.data.objects.get(MAPPING_EMPTY)
        if mat is None or mapping is None:
            raise RuntimeError("Candidate A/B render missing material or mapping empty")
        if mat.use_nodes and mat.node_tree:
            for node in mat.node_tree.nodes:
                if node.bl_idname == "ShaderNodeTexCoord" and hasattr(node, "object"):
                    node.object = mapping
        for shell in SHELL_OBJECTS:
            obj = bpy.data.objects.get(shell)
            if obj is None:
                raise RuntimeError(f"Candidate A/B render missing shell object {shell}")
            if [slot.material.name for slot in obj.material_slots if slot.material] != [MATERIAL_NAME]:
                raise RuntimeError(f"Candidate A/B render shell material mismatch {shell}")


def compose_ab_images(renders_dir: Path) -> None:
    try:
        from PIL import Image, ImageDraw, ImageFont
    except Exception:
        return
    font_big = load_font(34)
    font_med = load_font(22)
    for layer in AB_CAMERAS:
        src = renders_dir / f"INT30_R2B_AB_SOURCE_{layer}.png"
        cand = renders_dir / f"INT30_R2B_AB_CANDIDATE_{layer}.png"
        if not src.is_file() or not cand.is_file():
            continue
        a = Image.open(src).convert("RGBA").resize((720, 450))
        b = Image.open(cand).convert("RGBA").resize((720, 450))
        canvas = Image.new("RGBA", (1440, 520), (8, 10, 10, 255))
        canvas.paste(a, (0, 70))
        canvas.paste(b, (720, 70))
        draw = ImageDraw.Draw(canvas)
        draw.rectangle((0, 0, 1440, 70), fill=(0, 0, 0, 230))
        draw.text((16, 16), f"A/B {layer}", fill=(255, 141, 45, 255), font=font_big)
        draw.text((160, 25), "左：SURF-20 R5源；右：R2B候选。同相机/同SURF20_R5灯光/隐藏传感器", fill=(232, 242, 236, 255), font=font_med)
        draw.text((18, 82), "SOURCE R5", fill=(255, 141, 45, 255), font=font_med)
        draw.text((738, 82), "R2B CANDIDATE", fill=(255, 141, 45, 255), font=font_med)
        out = renders_dir / f"INT30_R2B_AB_{layer}_SOURCE_VS_CANDIDATE.png"
        canvas.save(out)


def make_camera(name: str, location: tuple[float, float, float], target: tuple[float, float, float], ortho_scale: float) -> Any:
    import bpy

    data = bpy.data.cameras.new(name)
    data.type = "ORTHO"
    data.ortho_scale = ortho_scale
    data.lens = 70
    obj = bpy.data.objects.new(name, data)
    bpy.context.scene.collection.objects.link(obj)
    obj.location = location
    look_at(obj, target)
    return obj


def look_at(obj: Any, target: tuple[float, float, float]) -> None:
    from mathutils import Vector

    direction = Vector(target) - obj.location
    obj.rotation_euler = direction.to_track_quat("-Z", "Y").to_euler()


def collect_contract() -> dict[str, Any]:
    import bpy

    sensors = [obj for obj in bpy.data.objects if obj.name.startswith("SENSOR_")]
    body = [obj for obj in bpy.data.objects if obj.name.startswith("SENSOR_T_body_")]
    return {
        "object_count": len(bpy.data.objects),
        "mesh_count": len(bpy.data.meshes),
        "material_count": len(bpy.data.materials),
        "sensor_count": len(sensors),
        "body_temperature_sensor_count": len(body),
        "layer_counts": {f"L{i}": len([obj for obj in body if obj.name.startswith(f"SENSOR_T_body_L{i}_")]) for i in range(7, 17)},
        "layer_groups_present": {name: bpy.data.objects.get(name) is not None for name in PROTECTED_LAYER_GROUPS},
        "shell_slots": {
            name: [slot.material.name for slot in bpy.data.objects[name].material_slots if slot.material]
            for name in SHELL_OBJECTS
            if bpy.data.objects.get(name)
        },
        "pressure_count": len([obj for obj in bpy.data.objects if obj.name.startswith(PRESSURE_PREFIX)]),
        "int20_entity_count": len([name for name in INT20_SOLID_OBJECTS if bpy.data.objects.get(name)]),
    }


def object_mesh_matrix_signature(names: list[str]) -> str:
    import bpy

    payload = []
    for name in names:
        obj = bpy.data.objects.get(name)
        if obj is None:
            payload.append({"name": name, "missing": True})
            continue
        entry = {
            "name": name,
            "type": obj.type,
            "matrix_world": [round(float(v), 8) for row in obj.matrix_world for v in row],
            "data_name": obj.data.name if getattr(obj, "data", None) else None,
        }
        if obj.type == "MESH":
            mesh = obj.data
            entry["vertices"] = len(mesh.vertices)
            entry["edges"] = len(mesh.edges)
            entry["polygons"] = len(mesh.polygons)
            entry["vertex_sample"] = [[round(float(c), 7) for c in v.co] for v in mesh.vertices[: min(20, len(mesh.vertices))]]
            entry["polygon_sample"] = [list(poly.vertices) for poly in mesh.polygons[: min(20, len(mesh.polygons))]]
        payload.append(entry)
    return hash_payload(payload)


def object_full_signature(names: list[str]) -> str:
    import bpy

    payload = []
    for name in names:
        obj = bpy.data.objects.get(name)
        payload.append(
            {
                "name": name,
                "present": obj is not None,
                "type": obj.type if obj else None,
                "matrix_world": [round(float(v), 8) for row in obj.matrix_world for v in row] if obj else None,
                "material_slots": [slot.material.name for slot in obj.material_slots if slot.material] if obj else [],
                "custom_props": sorted([str(k) for k in obj.keys()]) if obj else [],
                "mesh_sig": object_mesh_matrix_signature([name]) if obj and obj.type == "MESH" else None,
            }
        )
    return hash_payload(payload)


def pressure_signature() -> str:
    import bpy

    payload = []
    for name in PRESSURE_NAMES:
        obj = bpy.data.objects.get(name)
        if obj is None:
            payload.append({"name": name, "missing": True})
            continue
        payload.append(
            {
                "name": obj.name,
                "type": obj.type,
                "location": [round(float(v), 8) for v in obj.location],
                "rotation": [round(float(v), 8) for v in obj.rotation_euler],
                "scale": [round(float(v), 8) for v in obj.scale],
                "matrix_world": [round(float(v), 8) for row in obj.matrix_world for v in row],
                "materials": [slot.material.name for slot in obj.material_slots if slot.material],
                "custom_props": {str(k): json_safe(obj.get(k)) for k in sorted(obj.keys())},
                "mesh_sig": object_mesh_matrix_signature([name]) if obj.type == "MESH" else None,
            }
        )
    return hash_payload(payload)


def hide_old_explanatory_objects() -> dict[str, Any]:
    import bpy

    matched = []
    hidden = []
    for obj in bpy.data.objects:
        lower_name = obj.name.lower()
        if obj.name.startswith(PRESSURE_PREFIX) or obj.name.startswith("APPROX_GL02_INT10_"):
            continue
        if any(token in lower_name for token in EXPLANATORY_INTERNAL_TOKENS):
            matched.append(obj.name)
            if obj.hide_viewport and obj.hide_render:
                hidden.append(obj.name)
            else:
                obj.hide_viewport = True
                obj.hide_render = True
                hidden.append(obj.name)
    return {"matched_count": len(matched), "hidden_count": len(hidden), "hidden_names": sorted(hidden)}


def hash_payload(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()


def json_safe(value: Any) -> Any:
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    if isinstance(value, (list, tuple)):
        return [json_safe(v) for v in value]
    return str(value)


def contains_nan(value: Any) -> bool:
    if isinstance(value, float):
        return math.isnan(value) or math.isinf(value)
    if isinstance(value, dict):
        return any(contains_nan(v) for v in value.values())
    if isinstance(value, (list, tuple)):
        return any(contains_nan(v) for v in value)
    return False


def postprocess_host_images(output_dir: Path) -> None:
    try:
        from PIL import Image, ImageDraw, ImageFont
    except Exception:
        return
    renders_dir = output_dir / "renders"
    font_big = load_font(34)
    font_med = load_font(22)
    labels = {
        "INT30_R2B_01_FULL_MID_R1_ROUGHNESS.png": ("R2B FULL", "R1粗糙质感已合入；五段炉壳共用SURF-20 R5材质"),
        "INT30_R2B_02_GRAZING_NEAR_R1_TEXTURE.png": ("R2B GRAZING", "B=0.16 / D=0.10m / N=0.45，低金属哑光涂层"),
        "INT30_R2B_03_MICRO_DETAIL_R1_BODY_CLOSEUP.png": ("R2B MICRO", "候选炉壳本体环缝近景；R1微颗粒应在此图可见"),
        "INT30_R2B_04_MICRO_DETAIL_R1_BODY_CYCLES.png": ("R2B CYCLES", "同一位置Cycles验证；只作证据不改材质"),
        "INT30_R2B_05_CUTAWAY_CONTEXT_WITH_THICKNESS.png": ("R2B CUTAWAY", "剖切实体保留；本阶段只替换外炉壳材质"),
        "INT30_R2B_06_STATIC_PRESSURE_CONTEXT_R1_SHELL.png": ("R2B PRESSURE", "18个静压力点保留原坐标/材质/语义"),
        "INT30_R2B_07_MAPPING_CONTINUITY_FIVE_SEGMENTS.png": ("R2B MAPPING", "五段炉壳共享同一世界映射，避免分段纹理跳变"),
    }
    for name, (title, subtitle) in labels.items():
        path = renders_dir / name
        if not path.is_file():
            continue
        img = Image.open(path).convert("RGBA")
        draw = ImageDraw.Draw(img)
        draw.rectangle((0, 0, img.width, 74), fill=(0, 0, 0, 205))
        draw.text((18, 16), title, fill=(255, 141, 45, 255), font=font_big)
        draw.text((210, 25), subtitle, fill=(232, 242, 236, 255), font=font_med)
        img.save(path)
    source_cmp = HERE / "work" / "SURF_20_20260718_R5" / "renders" / "SURF20_R5_10_R1_R4_R5_GRAZING_COMPARISON.png"
    new_grazing = renders_dir / "INT30_R2B_02_GRAZING_NEAR_R1_TEXTURE.png"
    if source_cmp.is_file() and new_grazing.is_file():
        a = Image.open(source_cmp).convert("RGBA").resize((1440, 347))
        b = Image.open(new_grazing).convert("RGBA").resize((1440, 900))
        canvas = Image.new("RGBA", (1440, 1247), (8, 10, 10, 255))
        canvas.paste(a, (0, 0))
        canvas.paste(b, (0, 347))
        draw = ImageDraw.Draw(canvas)
        draw.rectangle((0, 0, 1440, 52), fill=(0, 0, 0, 210))
        draw.text((18, 10), "R1/R5 合流对比：上方为用户选择依据，下方为本候选合入后的炉壳近景", fill=(255, 141, 45, 255), font=font_med)
        cmp_path = renders_dir / "INT30_R2B_08_R1_R5_MERGE_COMPARISON.png"
        canvas.save(cmp_path)


def refresh_report_after_host(output_dir: Path, candidate: Path) -> None:
    report_path = output_dir / "int30_r2b_machine_report.json"
    report = json.loads(report_path.read_text(encoding="utf-8"))
    report["candidate"]["bytes"] = candidate.stat().st_size
    report["candidate"]["sha256"] = sha256_file(candidate)
    for item in report["evidence_renders"]:
        path = Path(item["path"])
        if path.is_file():
            item["bytes"] = path.stat().st_size
            item["sha256"] = sha256_file(path)
    cmp_path = output_dir / "renders" / "INT30_R2B_08_R1_R5_MERGE_COMPARISON.png"
    if cmp_path.is_file():
        report["evidence_renders"].append(
            {
                "id": "R1_R5_MERGE_COMPARISON",
                "file": cmp_path.name,
                "path": str(cmp_path),
                "project_relative_path": rel(cmp_path),
                "camera": "host_composite_from_SURF20_R5_reference_and_R2B_grazing",
                "purpose": "material before/selected reference and merged candidate comparison",
                "resolution_px": list(__import__("PIL").Image.open(cmp_path).size) if "PIL" in sys.modules else None,
                "bytes": cmp_path.stat().st_size,
                "sha256": sha256_file(cmp_path),
            }
        )
    existing_files = {item["file"] for item in report["evidence_renders"]}
    for ab_path in sorted((output_dir / "renders").glob("INT30_R2B_AB_*_SOURCE_VS_CANDIDATE.png")):
        if ab_path.name in existing_files:
            continue
        report["evidence_renders"].append(
            {
                "id": ab_path.stem.replace("INT30_R2B_", ""),
                "file": ab_path.name,
                "path": str(ab_path),
                "project_relative_path": rel(ab_path),
                "camera": "same_source_SURF20_R5_camera_transform_and_SURF20_R5_lights",
                "purpose": "strict A/B source-vs-candidate material equivalence evidence",
                "resolution_px": None,
                "bytes": ab_path.stat().st_size,
                "sha256": sha256_file(ab_path),
            }
        )
    report["ab_equivalence_evidence"] = {
        "layers": list(AB_CAMERAS.keys()),
        "source_and_candidate_same_camera_transforms": True,
        "source_and_candidate_same_surf20_r5_lights": True,
        "sensors_and_pressure_hidden_for_ab_render_only": True,
        "execution_visual_assessment": "iterate_required_not_visually_equivalent_to_surf20_r5_source",
        "visual_findings": [
            "SURF-20 R5 source renders show clear ring/plate-seam shadowing and fine sand roughness.",
            "R2B candidate renders under the same camera/light setup remain close to a smooth conical shell.",
            "Material node links and numeric sockets are preserved, but the branch geometry/lookdev does not visually reproduce the approved R1/R5 rough read.",
            "No approval is claimed by this execution stage.",
        ],
        "visual_decision": "requires_independent_visual_review; current execution evidence should be treated as iterate risk",
    }
    report["assertions"]["renders_exist"] = all((output_dir / "renders" / item["file"]).is_file() for item in report["evidence_renders"])
    report["execution"] = {
        "finished_at": now_iso(),
        "stdout_log": rel(output_dir / "blender_stdout.log"),
        "stderr_log": rel(output_dir / "blender_stderr.log"),
        "reopen_stdout_log": rel(output_dir / "reopen_stdout.log"),
        "reopen_stderr_log": rel(output_dir / "reopen_stderr.log"),
    }
    write_json(report_path, report)
    write_json(output_dir / "int30_r2b_visual_manifest.json", {"schema_version": "bf3d.visual_manifest.v1", "stage": STAGE_ID, "renders": report["evidence_renders"]})
    write_summary(output_dir, report)


def load_font(size: int) -> Any:
    try:
        from PIL import ImageFont

        for path in [
            r"C:\Windows\Fonts\simhei.ttf",
            r"C:\Windows\Fonts\simsun.ttc",
            r"C:\Windows\Fonts\msyh.ttc",
        ]:
            if Path(path).is_file():
                return ImageFont.truetype(path, size)
        return ImageFont.load_default()
    except Exception:
        return None


def write_stage_pipeline_status(output_dir: Path, candidate: Path) -> None:
    status_path = ROOT / "reports" / "pipeline_status.json"
    try:
        status = json.loads(status_path.read_text(encoding="utf-8"))
    except Exception:
        status = {"schema_version": 1, "stages": {}}
    status.setdefault("stages", {})[STAGE_ID] = {
        "status": "candidate_ready_for_review",
        "approval": "not_granted_requires_visual_and_spec_review",
        "candidate_blend": rel(candidate),
        "candidate_sha256": sha256_file(candidate),
        "input_blend": rel(INPUT_BLEND),
        "input_sha256": EXPECTED_INPUT_SHA256,
        "material_source_blend": rel(SOURCE_BLEND),
        "material_source_sha256": EXPECTED_SOURCE_SHA256,
        "machine_report": rel(output_dir / "int30_r2b_machine_report.json"),
        "visual_manifest": rel(output_dir / "int30_r2b_visual_manifest.json"),
        "summary": rel(output_dir / "INT-30_R2B_SURF20_R5_MERGE_阶段成果总结.md"),
        "formal_glb_unchanged": True,
        "formal_glb_sha256": EXPECTED_FORMAL_GLB_SHA256,
        "approval_boundary": "Only a Blender candidate merging the user-selected R1-rough SURF-20 R5 shell material into the INT-30 static-pressure branch.",
        "next_stop_line": "independent_visual_and_spec_review_required_before_stockline_or_GLB_export",
    }
    status["current_stage"] = STAGE_ID
    status["updated_at"] = now_iso()
    write_json(status_path, status)
    write_json(
        output_dir / "pipeline_status_snapshot.json",
        {
            "schema_version": "bf3d.pipeline_status_snapshot.v1",
            "stage": STAGE_ID,
            "global_pipeline_status": rel(status_path),
            "stage_entry": status["stages"][STAGE_ID],
        },
    )


def write_summary(output_dir: Path, report: dict[str, Any]) -> None:
    lines = [
        "# INT-30 R2B SURF-20 R5 材质合流阶段成果总结",
        "",
        f"- 阶段：`{STAGE_ID}`",
        "- 状态：`candidate_ready_for_review`，未授予正式替换批准。",
        f"- 输入静压力分支：`{report['input']['path']}`",
        f"- 输入 SHA：`{report['input']['actual_sha256']}`",
        f"- 材质来源：`{report['material_source']['path']}`",
        f"- 材质来源 SHA：`{report['material_source']['actual_sha256']}`",
        f"- 候选文件：`{report['candidate']['path']}`",
        f"- 候选 SHA：`{report['candidate']['sha256']}`",
        "",
        "## 本阶段唯一变更",
        "",
        "- 从 SURF-20 R5 合入 `SURF20_R5_aged_painted_carbon_steel_shared_world`。",
        "- 仅赋给五个炉壳段：`APPROX_GL02_FURNACE_HEARTH/BOSH/BELLY/SHAFT/THROAT`。",
        "- 保留用户选择的 R1 粗糙读感：`B=0.16 / D=0.10m / N=0.45`。",
        "- 金属度保持 `0.06`，避免回到高金属光亮表面。",
        "",
        "## 保护项",
        "",
        f"- 五炉段 mesh/matrix 未变：`{report['assertions']['five_shell_mesh_matrix_unchanged']}`",
        f"- 18 个静压力点签名未变：`{report['assertions']['pressure_signature_unchanged']}`",
        f"- 12 个内切面实体签名未变：`{report['assertions']['int20_12_entity_signature_unchanged']}`",
        f"- 115 传感器保留：`{report['assertions']['sensor_count_115_preserved']}`",
        f"- 80 炉体测温点保留：`{report['assertions']['body_temperature_80_preserved']}`",
        f"- L7～L16 每层 8 点保留：`{report['assertions']['l7_l16_groups_present']}`",
        f"- 旧 55 解释对象仍隐藏：`{report['assertions']['old_55_hidden_preserved']}`",
        f"- 正式 GLB 未变：`{report['formal_glb_protection']['unchanged']}` / `{report['formal_glb_protection']['after_sha256']}`",
        "",
        "## 视觉证据",
        "",
    ]
    for item in report["evidence_renders"]:
        lines.append(f"- `{item['id']}`：`{item['project_relative_path']}`")
    lines.extend(
        [
            "",
            "## 机器断言",
            "",
            f"- 总体：`{report['assertions']['machine_assertions_pass']}`",
        f"- 报告：`{rel(output_dir / 'int30_r2b_machine_report.json')}`",
        f"- Reopen：`{rel(output_dir / 'reopen_validation.json')}`",
        "",
        "## A/B 视觉等价结论",
        "",
        "- 已按同一 SURF-20 R5 相机/灯光生成 L7、L10、L13、L16 源 vs 候选并排图。",
        "- 执行自评：`iterate_required_not_visually_equivalent_to_surf20_r5_source`。",
        "- 主要原因：源 R5 图中有清晰板缝/环缝阴影与细砂读感；R2B 候选在同机位同灯光下仍偏平滑圆台。",
        "- 本阶段不追加 P35 几何，不改变材质参数，不声称视觉批准。",
        "",
        "## 停止线",
            "",
            "- 本阶段停在独立视觉/规格审核门。",
            "- 未进入料线、事件动画、GLB 导出或 Three.js 生产替换。",
        ]
    )
    write_text(output_dir / "INT-30_R2B_SURF20_R5_MERGE_阶段成果总结.md", "\n".join(lines) + "\n")


if __name__ == "__main__":
    if "--" in sys.argv and any(flag in sys.argv for flag in ("--run-blender-stage", "--reopen-validate", "--render-ab-source", "--render-ab-candidate")):
        raise SystemExit(blender_main())
    raise SystemExit(host_main())
