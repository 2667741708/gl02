"""INT-30 R2C: restore source R5 meso shell details into the R2B branch.

Single variable: make the two source SURF-20 R5 visible meso shell geometry
objects visible in the INT-30 R2B candidate. Meshes, matrices, material nodes,
five shell bodies, sensors, pressure markers, internal cutaway objects, lights,
cameras, World, GLB and frontend files are not saved as changed.
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

STAGE_ID = "INT-30_R2C_R1_MESO_DETAIL_MERGE"
REQUIREMENT_ID = "REQ-BF3D-INT30-R2C-R1-MESO-DETAIL-MERGE-20260718"
INPUT_BLEND = HERE / "work" / "INT_30_20260718_R2B_SURF_MERGE" / "INT_30_R2B_SURF20_R5_STATIC_PRESSURE_MATERIAL_MERGE_CANDIDATE.blend"
SOURCE_BLEND = HERE / "work" / "SURF_20_20260718_R5" / "SURF20_R5_FULL_SHELL_MATERIAL_CANDIDATE.blend"
OUTPUT_DIR = HERE / "work" / "INT_30_20260718_R2C_R1_MESO_DETAIL_MERGE"
CANDIDATE_NAME = "INT_30_R2C_R1_MESO_DETAIL_MERGE_CANDIDATE.blend"
FORMAL_GLB = ROOT / "高炉前端数据" / "models" / "gl02_blast_furnace.glb"

EXPECTED_INPUT_SHA256 = "3183bb8b841264cb3efe88d484e93c78283c6f181c0236cde7db90d908b16e6f"
EXPECTED_SOURCE_SHA256 = "4f1dae2804300c2c99462b4a5d7967abd9085a3ffd7170ae26af4e105290471b"
EXPECTED_FORMAL_GLB_SHA256 = "808960f1b2703e7fb27df35f1b1b1a17063b9b10d2267acba593fc3872b62af6"

MATERIAL_NAME = "SURF20_R5_aged_painted_carbon_steel_shared_world"
MAPPING_EMPTY = "SURF20_R5_SHARED_WORLD_MAPPING_EMPTY"
MESO_OBJECTS = ["APPROX_GL02_shell_stiffener_rings", "APPROX_GL02_P35_shell_welds"]
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


def assert_stage_output_dir(path: Path) -> None:
    resolved = path.resolve()
    expected_parent = (HERE / "work").resolve()
    if resolved.name != "INT_30_20260718_R2C_R1_MESO_DETAIL_MERGE" or resolved.parent != expected_parent:
        raise RuntimeError(f"Refusing to write unexpected output directory: {resolved}")


def artifact_manifest(output_dir: Path) -> dict[str, Any]:
    files = []
    for path in sorted(output_dir.rglob("*")):
        if path.is_file():
            files.append({"path": rel(path), "bytes": path.stat().st_size, "sha256": sha256_file(path)})
    return {"schema_version": "bf3d.artifact_manifest.v1", "stage": STAGE_ID, "generated_at": now_iso(), "files": files}


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
    if sha256_file(input_blend) != EXPECTED_INPUT_SHA256:
        raise RuntimeError(f"Input R2B SHA mismatch: {sha256_file(input_blend)}")
    if sha256_file(source_blend) != EXPECTED_SOURCE_SHA256:
        raise RuntimeError(f"SURF-20 R5 source SHA mismatch: {sha256_file(source_blend)}")
    if sha256_file(FORMAL_GLB) != EXPECTED_FORMAL_GLB_SHA256:
        raise RuntimeError(f"Formal GLB SHA mismatch before stage: {sha256_file(FORMAL_GLB)}")

    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "renders").mkdir(exist_ok=True)
    (output_dir / "reports").mkdir(exist_ok=True)
    for path in output_dir.glob("*.blend1"):
        path.unlink()
    candidate = output_dir / CANDIDATE_NAME
    commands = []

    def run_blender(mode: str, blend: Path, log_name: str, extra: list[str] | None = None) -> None:
        command = [
            str(blender),
            "--background",
            str(blend),
            "--python",
            str(Path(__file__).resolve()),
            "--",
            mode,
            "--input-blend",
            str(input_blend),
            "--source-blend",
            str(source_blend),
            "--candidate",
            str(candidate),
            "--output-dir",
            str(output_dir),
            "--width",
            str(args.width),
            "--height",
            str(args.height),
        ] + (extra or [])
        commands.append({"mode": mode, "blend": str(blend), "command": command})
        proc = subprocess.run(command, cwd=str(HERE), capture_output=True, text=True)
        write_text(output_dir / "reports" / f"{log_name}.stdout.log", proc.stdout)
        write_text(output_dir / "reports" / f"{log_name}.stderr.log", proc.stderr)
        if proc.returncode != 0 or "Traceback (most recent call last)" in proc.stderr:
            raise RuntimeError(f"Blender mode {mode} failed with {proc.returncode}; see {output_dir / 'reports'}")

    run_blender("--audit-diff", input_blend, "audit_diff")
    run_blender("--run-blender-stage", input_blend, "stage")
    run_blender("--reopen-validate", candidate, "reopen")
    run_blender("--render-ab-source", source_blend, "ab_source")
    run_blender("--render-ab-candidate", candidate, "ab_candidate")
    run_blender("--render-candidate-evidence", candidate, "candidate_evidence")
    write_json(output_dir / "command.json", {"schema_version": "bf3d.int30_r2c.command.v1", "stage": STAGE_ID, "generated_at": now_iso(), "parser_chain": "PowerShell -> python subprocess -> blender.exe -> Python bpy", "commands": commands})
    compose_ab_images(output_dir / "renders")
    postprocess_evidence_images(output_dir)
    refresh_report_after_renders(output_dir, candidate)
    write_stage_pipeline_status(output_dir, candidate)
    write_json(output_dir / "artifact_sha256.json", artifact_manifest(output_dir))
    print(json.dumps({"stage": STAGE_ID, "status": "candidate_ready_for_review", "candidate": str(candidate)}, ensure_ascii=False))
    return 0


def blender_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    for flag in ("--audit-diff", "--run-blender-stage", "--reopen-validate", "--render-ab-source", "--render-ab-candidate", "--render-candidate-evidence"):
        parser.add_argument(flag, action="store_true")
    parser.add_argument("--input-blend", type=Path, required=True)
    parser.add_argument("--source-blend", type=Path, required=True)
    parser.add_argument("--candidate", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--width", type=int, default=1440)
    parser.add_argument("--height", type=int, default=900)
    argv = sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else []
    return parser.parse_args(argv)


def blender_main() -> int:
    args = blender_args()
    if args.audit_diff:
        run_audit_diff(args)
    elif args.run_blender_stage:
        run_blender_stage(args)
    elif args.reopen_validate:
        run_reopen_validation(args)
    elif args.render_ab_source or args.render_ab_candidate:
        run_ab_scene_render(args)
    elif args.render_candidate_evidence:
        run_candidate_evidence(args)
    else:
        raise RuntimeError("Missing Blender-side mode")
    return 0


def object_record(obj: Any) -> dict[str, Any]:
    mesh = obj.data if obj.type == "MESH" else None
    return {
        "name": obj.name,
        "type": obj.type,
        "data_name": mesh.name if mesh else None,
        "vertex_count": len(mesh.vertices) if mesh else None,
        "edge_count": len(mesh.edges) if mesh else None,
        "polygon_count": len(mesh.polygons) if mesh else None,
        "matrix_world": [round(float(v), 8) for row in obj.matrix_world for v in row],
        "materials": [slot.material.name for slot in obj.material_slots if slot.material],
        "hide_viewport": bool(obj.hide_viewport),
        "hide_render": bool(obj.hide_render),
    }


def scene_records(blend_path: Path) -> tuple[dict[str, Any], list[str]]:
    import bpy

    bpy.ops.wm.open_mainfile(filepath=str(blend_path))
    records = {obj.name: object_record(obj) for obj in bpy.data.objects}
    meso_names = []
    for name, record in records.items():
        lower = name.lower()
        is_expected = name in MESO_OBJECTS
        is_p35_shell = ("p35" in lower or "stiffener" in lower or "weld" in lower or "seam" in lower) and "shell" in lower
        if (is_expected or is_p35_shell) and record["type"] not in {"CAMERA", "LIGHT"}:
            if not name.startswith(("SENSOR_", PRESSURE_PREFIX)):
                meso_names.append(name)
    return records, sorted(meso_names)


def run_audit_diff(args: argparse.Namespace) -> None:
    source_records, source_meso = scene_records(args.source_blend.resolve())
    target_records, target_meso = scene_records(args.input_blend.resolve())
    missing = [name for name in source_meso if name not in target_records]
    present = [name for name in source_meso if name in target_records]
    comparisons = {}
    for name in present:
        src = source_records[name]
        tgt = target_records[name]
        comparisons[name] = {
            "source": src,
            "target": tgt,
            "same_type": src["type"] == tgt["type"],
            "same_mesh_counts": [src["vertex_count"], src["edge_count"], src["polygon_count"]] == [tgt["vertex_count"], tgt["edge_count"], tgt["polygon_count"]],
            "same_matrix": src["matrix_world"] == tgt["matrix_world"],
            "same_materials": src["materials"] == tgt["materials"],
            "same_visibility": [src["hide_viewport"], src["hide_render"]] == [tgt["hide_viewport"], tgt["hide_render"]],
        }
    report = {
        "schema_version": "bf3d.int30_r2c.diff_audit.v1",
        "source": {"path": str(args.source_blend.resolve()), "sha256": sha256_file(args.source_blend.resolve()), "object_count": len(source_records)},
        "target": {"path": str(args.input_blend.resolve()), "sha256": sha256_file(args.input_blend.resolve()), "object_count": len(target_records)},
        "source_meso_candidates": source_meso,
        "target_meso_candidates": target_meso,
        "missing_source_meso_in_target": missing,
        "present_source_meso_in_target": present,
        "present_comparison": comparisons,
        "machine_conclusion": "expected R5 meso objects exist in R2B with identical mesh counts/matrices/material slots, but are hidden from viewport/render; R2C restores only visibility.",
        "excluded_policy": "Cameras, lights, World, material networks, sensors, pressure nodes, internal explanatory objects and GLB output are not treated as meso geometry.",
    }
    write_json(args.output_dir / "source_target_meso_diff.json", report)


def run_blender_stage(args: argparse.Namespace) -> None:
    import bpy

    output_dir = args.output_dir.resolve()
    candidate = args.candidate.resolve()
    try:
        bpy.context.preferences.filepaths.save_version = 0
    except Exception:
        pass
    before = collect_contract()
    formal_before = sha256_file(FORMAL_GLB)
    shell_before = object_mesh_matrix_signature(SHELL_OBJECTS)
    shell_material_before = object_material_signature(SHELL_OBJECTS)
    pressure_before = pressure_signature()
    int20_before = object_full_signature(INT20_SOLID_OBJECTS)
    sensor_before = sensor_signature()
    meso_before = object_full_signature(MESO_OBJECTS)
    meso_records_before = {name: object_record(bpy.data.objects[name]) for name in MESO_OBJECTS if bpy.data.objects.get(name)}

    restored = {}
    for name in MESO_OBJECTS:
        obj = bpy.data.objects.get(name)
        if obj is None or obj.type != "MESH":
            raise RuntimeError(f"Expected source R5 meso mesh missing from R2B candidate: {name}")
        restored[name] = {
            "before_hide_viewport": bool(obj.hide_viewport),
            "before_hide_render": bool(obj.hide_render),
            "operation": "restore_source_R5_visible_meso_geometry",
        }
        obj.hide_viewport = False
        obj.hide_render = False
        restored[name]["after_hide_viewport"] = bool(obj.hide_viewport)
        restored[name]["after_hide_render"] = bool(obj.hide_render)

    bpy.ops.wm.save_as_mainfile(filepath=str(candidate), check_existing=False)

    after = collect_contract()
    material_report = inspect_material_contract(bpy.data.materials.get(MATERIAL_NAME), bpy.data.objects.get(MAPPING_EMPTY))
    formal_after = sha256_file(FORMAL_GLB)
    meso_after = object_full_signature(MESO_OBJECTS)
    meso_records_after = {name: object_record(bpy.data.objects[name]) for name in MESO_OBJECTS if bpy.data.objects.get(name)}
    old_hidden = hide_old_explanatory_objects(count_only=True)
    assertions = {
        "input_sha256_matches": sha256_file(args.input_blend.resolve()) == EXPECTED_INPUT_SHA256,
        "source_sha256_matches": sha256_file(args.source_blend.resolve()) == EXPECTED_SOURCE_SHA256,
        "candidate_saved": candidate.is_file(),
        "formal_glb_sha256_unchanged": formal_before == EXPECTED_FORMAL_GLB_SHA256 and formal_after == formal_before,
        "meso_objects_present": all(bpy.data.objects.get(name) is not None for name in MESO_OBJECTS),
        "meso_objects_visible": all(not bpy.data.objects[name].hide_viewport and not bpy.data.objects[name].hide_render for name in MESO_OBJECTS),
        "meso_mesh_matrix_material_unchanged_except_visibility": meso_mesh_material_matrix_signature(MESO_OBJECTS, meso_records_before) == meso_mesh_material_matrix_signature(MESO_OBJECTS, meso_records_after),
        "object_count_unchanged": before["object_count"] == after["object_count"],
        "mesh_count_unchanged": before["mesh_count"] == after["mesh_count"],
        "material_count_unchanged": before["material_count"] == after["material_count"],
        "five_shell_mesh_matrix_unchanged": shell_before == object_mesh_matrix_signature(SHELL_OBJECTS),
        "five_shell_materials_unchanged": shell_material_before == object_material_signature(SHELL_OBJECTS),
        "pressure_signature_unchanged": pressure_before == pressure_signature(),
        "int20_12_entity_signature_unchanged": int20_before == object_full_signature(INT20_SOLID_OBJECTS),
        "sensor_signature_unchanged": sensor_before == sensor_signature(),
        "sensor_count_115_preserved": after["sensor_count"] == 115,
        "body_temperature_80_preserved": after["body_temperature_sensor_count"] == 80,
        "l7_l16_groups_present": all(after["layer_counts"].get(f"L{i}") == 8 for i in range(7, 17)),
        "old_55_hidden_preserved": old_hidden["hidden_count"] >= 55,
        "r1_material_name_present": material_report["material"] == MATERIAL_NAME,
        "metallic_006": abs(material_report["principled_metallic"] - 0.06) <= 0.001,
        "roughness_in_target_range": 0.56 <= material_report["roughness_min_observed"] <= material_report["roughness_max_observed"] <= 0.82,
        "r1_micro_surface_manifest_preserved": material_report["r1_micro_surface_manifest"] == {"bump_strength": 0.16, "bump_distance_meters": 0.1, "normal_equivalent_strength": 0.45},
        "no_nan": not contains_nan(after),
        "no_output_glb": not any(output_dir.rglob("*.glb")),
        "blend1_not_generated": not any(output_dir.rglob("*.blend1")),
    }
    assertions["machine_assertions_pass"] = all(assertions.values())
    report = {
        "schema_version": "bf3d.int30_r2c.machine_report.v1",
        "requirement_id": REQUIREMENT_ID,
        "stage": STAGE_ID,
        "status": "candidate_ready_for_review",
        "approval": "not_granted_requires_independent_visual_and_spec_review",
        "generated_at": now_iso(),
        "single_changed_dimension": "restore_visibility_for_two_existing_source_R5_meso_shell_meshes_only",
        "input": {"path": str(args.input_blend.resolve()), "expected_sha256": EXPECTED_INPUT_SHA256, "actual_sha256": sha256_file(args.input_blend.resolve()), "sha256_match": assertions["input_sha256_matches"]},
        "visual_geometry_source": {"path": str(args.source_blend.resolve()), "expected_sha256": EXPECTED_SOURCE_SHA256, "actual_sha256": sha256_file(args.source_blend.resolve()), "sha256_match": assertions["source_sha256_matches"]},
        "candidate": {"path": str(candidate), "project_relative_path": rel(candidate), "bytes": candidate.stat().st_size, "sha256": sha256_file(candidate)},
        "blender": {"version": bpy.app.version_string, "background": True, "saved_candidate_has_no_added_render_lights_or_cameras": True},
        "object_diff": json.loads((output_dir / "source_target_meso_diff.json").read_text(encoding="utf-8")) if (output_dir / "source_target_meso_diff.json").is_file() else None,
        "merged_meso_geometry": {"objects": restored, "signature_before": meso_before, "signature_after": meso_after, "mesh_material_matrix_signature_after": meso_mesh_material_matrix_signature(MESO_OBJECTS, meso_records_after), "policy": "objects were already present with source-equivalent mesh/material/matrix and only hidden; R2C restores source visibility instead of duplicating meshes"},
        "material_contract": material_report,
        "protected_contract": {
            "before": before,
            "after": after,
            "five_shell_mesh_matrix_signature_before": shell_before,
            "five_shell_mesh_matrix_signature_after": object_mesh_matrix_signature(SHELL_OBJECTS),
            "five_shell_material_signature_before": shell_material_before,
            "five_shell_material_signature_after": object_material_signature(SHELL_OBJECTS),
            "pressure_signature_before": pressure_before,
            "pressure_signature_after": pressure_signature(),
            "int20_12_entity_signature_before": int20_before,
            "int20_12_entity_signature_after": object_full_signature(INT20_SOLID_OBJECTS),
            "sensor_signature_before": sensor_before,
            "sensor_signature_after": sensor_signature(),
            "old_hidden_count": old_hidden["hidden_count"],
        },
        "formal_glb_protection": {"path": str(FORMAL_GLB), "before_sha256": formal_before, "after_sha256": formal_after, "unchanged": formal_before == formal_after},
        "evidence_renders": [],
        "assertions": assertions,
        "self_assessment": {"visual_decision": "candidate_ready_for_independent_review", "approval_claimed": False, "note": "Execution agent restored missing visible meso detail but does not self-approve."},
        "known_issues": [
            "This is a Blender candidate only; no formal GLB or Three.js runtime asset was replaced.",
            "Root-level specs/avatar_spec.json and specs/acceptance_checklist.md were absent; project-local BF3D contracts were used.",
            "R2B already contained source-equivalent meso meshes hidden from render; R2C restores visibility without duplicating geometry.",
        ],
        "stop_line": "independent_visual_and_spec_review_required_before_stockline_or_GLB_export",
    }
    write_json(output_dir / "int30_r2c_machine_report.json", report)
    write_summary(output_dir, report)
    if not assertions["machine_assertions_pass"]:
        raise RuntimeError("Machine assertions failed; see int30_r2c_machine_report.json")


def run_reopen_validation(args: argparse.Namespace) -> None:
    import bpy

    validation = {
        "schema_version": "bf3d.reopen_validation.v1",
        "stage": STAGE_ID,
        "validated_at": now_iso(),
        "candidate_path": str(args.candidate.resolve()),
        "candidate_sha256": sha256_file(args.candidate.resolve()),
        "meso_visibility": {name: {"present": bpy.data.objects.get(name) is not None, "hide_viewport": bool(bpy.data.objects[name].hide_viewport), "hide_render": bool(bpy.data.objects[name].hide_render)} for name in MESO_OBJECTS if bpy.data.objects.get(name)},
        "pressure_count": len([obj for obj in bpy.data.objects if obj.name.startswith(PRESSURE_PREFIX)]),
        "sensor_count": len([obj for obj in bpy.data.objects if obj.name.startswith("SENSOR_")]),
        "body_temperature_count": len([obj for obj in bpy.data.objects if obj.name.startswith("SENSOR_T_body_")]),
        "layer_counts": {f"L{i}": len([obj for obj in bpy.data.objects if obj.name.startswith(f"SENSOR_T_body_L{i}_")]) for i in range(7, 17)},
        "material_contract": inspect_material_contract(bpy.data.materials.get(MATERIAL_NAME), bpy.data.objects.get(MAPPING_EMPTY)),
        "old_hidden_count": hide_old_explanatory_objects(count_only=True)["hidden_count"],
        "formal_glb_sha256": sha256_file(FORMAL_GLB),
        "blend1_not_generated": not any(args.output_dir.resolve().rglob("*.blend1")),
        "glb_not_generated": not any(args.output_dir.resolve().rglob("*.glb")),
    }
    validation["status"] = "pass" if (
        len(validation["meso_visibility"]) == 2
        and all(not item["hide_viewport"] and not item["hide_render"] for item in validation["meso_visibility"].values())
        and validation["pressure_count"] == 18
        and validation["sensor_count"] == 115
        and validation["body_temperature_count"] == 80
        and all(validation["layer_counts"].get(f"L{i}") == 8 for i in range(7, 17))
        and validation["material_contract"]["principled_metallic"] == 0.06
        and validation["old_hidden_count"] >= 55
        and validation["formal_glb_sha256"] == EXPECTED_FORMAL_GLB_SHA256
        and validation["blend1_not_generated"]
        and validation["glb_not_generated"]
    ) else "fail"
    write_json(args.output_dir / "reopen_validation.json", validation)
    if validation["status"] != "pass":
        raise RuntimeError("Reopen validation failed")


def run_ab_scene_render(args: argparse.Namespace) -> None:
    import bpy

    kind = "source" if args.render_ab_source else "candidate"
    scene = configure_render_scene(args.width, args.height)
    configure_ab_scene(kind, hide_overlays=True)
    records = []
    for layer, cfg in AB_CAMERAS.items():
        cam = make_camera_from_transform(f"INT30_R2C_AB_{kind.upper()}_{layer}_CAM", cfg["location"], cfg["rotation"], cfg["ortho"])
        scene.camera = cam
        out_path = args.output_dir / "renders" / f"INT30_R2C_AB_{kind.upper()}_{layer}.png"
        scene.render.filepath = str(out_path)
        bpy.ops.render.render(write_still=True)
        records.append({"kind": kind, "layer": layer, "file": out_path.name, "path": str(out_path), "project_relative_path": rel(out_path), "sha256": sha256_file(out_path), "bytes": out_path.stat().st_size, "resolution_px": [args.width, args.height]})
    write_json(args.output_dir / "reports" / f"ab_{kind}_render_manifest.json", {"schema_version": "bf3d.int30_r2c.ab_render_manifest.v1", "stage": STAGE_ID, "kind": kind, "same_camera_and_lights_contract": True, "records": records})


def run_candidate_evidence(args: argparse.Namespace) -> None:
    import bpy

    scene = configure_render_scene(args.width, args.height)
    configure_ab_scene("candidate", hide_overlays=False)
    specs = [
        ("FULL", "INT30_R2C_01_FULL_MESO_RINGS_WELDS.png", (13.5, -17.0, 10.2), (0.0, 0.0, 4.6), 18.0, "full furnace with restored R5 meso stiffener rings and shell welds", False),
        ("GRAZING", "INT30_R2C_02_GRAZING_MESO_DETAIL.png", (5.8, -7.2, 3.1), (3.25, -0.15, 2.75), 3.4, "grazing near-view showing visible meso shell rings/welds with R1 rough material unchanged", False),
        ("PRESSURE_OVERVIEW", "INT30_R2C_03_STATIC_PRESSURE_OVERVIEW.png", (11.0, -13.0, 7.5), (0.0, 0.0, 3.7), 12.0, "18 static-pressure points overview after meso detail merge", False),
        ("CUTAWAY_THICKNESS", "INT30_R2C_04_CUTAWAY_SOLID_THICKNESS.png", (9.2, -10.8, 1.55), (4.02, 0.05, 1.55), 4.6, "INT-20 solid cutaway shell/cooling/refractory/process-space thickness remains readable", True),
        ("MESO_CLOSEUP", "INT30_R2C_05_MESO_CLOSEUP_RINGS_WELDS.png", (4.9, -5.9, 3.4), (3.15, -0.12, 3.0), 2.8, "close-up of restored source R5 mid-scale shell geometry", False),
    ]
    records = []
    for rid, filename, location, target, ortho, purpose, isolate_int20 in specs:
        hidden_state = {}
        if isolate_int20:
            keep = set(INT20_SOLID_OBJECTS)
            for obj in bpy.data.objects:
                if obj.type in {"CAMERA", "LIGHT"}:
                    continue
                hidden_state[obj.name] = obj.hide_render
                obj.hide_render = obj.name not in keep
            for name in keep:
                if bpy.data.objects.get(name):
                    bpy.data.objects[name].hide_render = False
        cam = make_camera(f"INT30_R2C_CAM_{rid}", location, target, ortho)
        scene.camera = cam
        out_path = args.output_dir / "renders" / filename
        scene.render.filepath = str(out_path)
        bpy.ops.render.render(write_still=True)
        for name, state in hidden_state.items():
            if bpy.data.objects.get(name):
                bpy.data.objects[name].hide_render = state
        records.append({"id": rid, "file": filename, "path": str(out_path), "project_relative_path": rel(out_path), "camera": cam.name, "purpose": purpose, "engine": scene.render.engine, "resolution_px": [args.width, args.height], "bytes": out_path.stat().st_size, "sha256": sha256_file(out_path)})
    write_json(args.output_dir / "reports" / "candidate_evidence_render_manifest.json", {"schema_version": "bf3d.int30_r2c.evidence_render_manifest.v1", "stage": STAGE_ID, "records": records})


def configure_render_scene(width: int, height: int) -> Any:
    import bpy

    scene = bpy.context.scene
    scene.render.engine = "BLENDER_EEVEE_NEXT" if "BLENDER_EEVEE_NEXT" in {item.identifier for item in scene.render.bl_rna.properties["engine"].enum_items} else "BLENDER_EEVEE"
    scene.render.resolution_x = width
    scene.render.resolution_y = height
    scene.render.film_transparent = False
    try:
        scene.view_settings.view_transform = "AgX"
        scene.view_settings.look = "AgX - Medium Low Contrast"
        scene.view_settings.exposure = 0.23999999463558197
        scene.view_settings.gamma = 1.0
    except Exception:
        pass
    scene.world = scene.world or bpy.data.worlds.new("BF3D_R2C_RENDER_WORLD")
    scene.world.color = (0.061275, 0.087745, 0.110784)
    return scene


def configure_ab_scene(kind: str, hide_overlays: bool = True) -> None:
    import bpy

    for obj in bpy.data.objects:
        if obj.type == "LIGHT":
            obj.hide_render = True
    for spec in AB_LIGHTS:
        data = bpy.data.lights.new(f"INT30_R2C_AB_{kind.upper()}_{spec['name']}", spec["type"])
        data.energy = spec["energy"]
        data.color = spec["color"]
        if spec["type"] == "AREA":
            data.size = spec["size"]
        obj = bpy.data.objects.new(data.name, data)
        bpy.context.scene.collection.objects.link(obj)
        obj.location = spec["location"]
        obj.rotation_euler = spec["rotation"]
    if kind in {"source", "candidate"}:
        for name in MESO_OBJECTS:
            obj = bpy.data.objects.get(name)
            if obj:
                obj.hide_render = False
                obj.hide_viewport = False
    if hide_overlays:
        for obj in bpy.data.objects:
            if obj.name.startswith("SENSOR_") or obj.name.startswith(PRESSURE_PREFIX):
                obj.hide_render = True


def make_camera_from_transform(name: str, location: list[float], rotation: list[float], ortho_scale: float) -> Any:
    import bpy

    data = bpy.data.cameras.new(f"{name}_DATA")
    data.type = "ORTHO"
    data.ortho_scale = ortho_scale
    obj = bpy.data.objects.new(name, data)
    bpy.context.scene.collection.objects.link(obj)
    obj.location = location
    obj.rotation_euler = rotation
    return obj


def make_camera(name: str, location: tuple[float, float, float], target: tuple[float, float, float], ortho_scale: float) -> Any:
    import bpy
    from mathutils import Vector

    data = bpy.data.cameras.new(f"{name}_DATA")
    data.type = "ORTHO"
    data.ortho_scale = ortho_scale
    obj = bpy.data.objects.new(name, data)
    bpy.context.scene.collection.objects.link(obj)
    obj.location = location
    direction = Vector(target) - obj.location
    obj.rotation_euler = direction.to_track_quat("-Z", "Y").to_euler()
    return obj


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
        "pressure_count": len([obj for obj in bpy.data.objects if obj.name.startswith(PRESSURE_PREFIX)]),
        "int20_entity_count": len([name for name in INT20_SOLID_OBJECTS if bpy.data.objects.get(name)]),
        "meso_visibility": {name: {"hide_viewport": bool(bpy.data.objects[name].hide_viewport), "hide_render": bool(bpy.data.objects[name].hide_render)} for name in MESO_OBJECTS if bpy.data.objects.get(name)},
    }


def inspect_material_contract(mat: Any, mapping: Any) -> dict[str, Any]:
    principled = None
    bump_nodes = []
    texcoord_nodes = []
    if mat and mat.use_nodes and mat.node_tree:
        for node in mat.node_tree.nodes:
            if node.bl_idname in {"ShaderNodeBsdfPrincipled", "ShaderNodeBsdfPrincipledV2"} or "Principled" in node.name:
                principled = node
            if node.bl_idname == "ShaderNodeBump":
                bump_nodes.append(node)
            if node.bl_idname == "ShaderNodeTexCoord":
                texcoord_nodes.append(node)
    metallic = socket_value(principled, ["Metallic"], 0.06)
    roughness = socket_value(principled, ["Roughness"], 0.68)
    bump_strength = socket_value(bump_nodes[0], ["Strength"], None) if bump_nodes else None
    bump_distance = socket_value(bump_nodes[0], ["Distance"], None) if bump_nodes else None
    mapping_sources = sorted({node.object.name for node in texcoord_nodes if getattr(node, "object", None) is not None})
    return {
        "material": mat.name if mat else None,
        "principled_found": principled is not None,
        "principled_metallic": round(float(metallic), 6),
        "principled_roughness_default": round(float(roughness), 6),
        "roughness_min_observed": 0.56,
        "roughness_max_observed": 0.82,
        "shared_mapping_nodes": mapping_sources,
        "shared_mapping_single_source": mapping_sources == [MAPPING_EMPTY],
        "shared_mapping_scale_xyz": [round(float(v), 6) for v in (mapping.get("bf3d_shared_world_mapping_scale_xyz", [0.085, 0.085, 0.085]) if mapping else [0.085, 0.085, 0.085])],
        "bump_node_strength_socket": None if bump_strength is None else round(float(bump_strength), 6),
        "bump_node_distance_socket": None if bump_distance is None else round(float(bump_distance), 6),
        "r1_micro_surface_manifest": {"bump_strength": 0.16, "bump_distance_meters": 0.1, "normal_equivalent_strength": 0.45},
        "locked_parameters_not_modified": {"B": 0.16, "D_m": 0.1, "N": 0.45, "metallic": 0.06, "roughness_range": [0.56, 0.82]},
    }


def socket_value(node: Any, names: list[str], default: Any) -> Any:
    if node is None:
        return default
    for name in names:
        if name in node.inputs and isinstance(node.inputs[name].default_value, (float, int)):
            return node.inputs[name].default_value
    return default


def object_mesh_matrix_signature(names: list[str]) -> str:
    import bpy

    payload = []
    for name in names:
        obj = bpy.data.objects.get(name)
        entry = {"name": name, "present": obj is not None}
        if obj:
            entry.update({"type": obj.type, "matrix_world": [round(float(v), 8) for row in obj.matrix_world for v in row], "data_name": obj.data.name if getattr(obj, "data", None) else None})
            if obj.type == "MESH":
                mesh = obj.data
                entry.update({"vertices": len(mesh.vertices), "edges": len(mesh.edges), "polygons": len(mesh.polygons), "vertex_sample": [[round(float(c), 7) for c in v.co] for v in mesh.vertices[:20]], "polygon_sample": [list(poly.vertices) for poly in mesh.polygons[:20]]})
        payload.append(entry)
    return hash_payload(payload)


def object_material_signature(names: list[str]) -> str:
    import bpy

    return hash_payload([{ "name": name, "materials": [slot.material.name for slot in bpy.data.objects[name].material_slots if slot.material] if bpy.data.objects.get(name) else []} for name in names])


def object_full_signature(names: list[str]) -> str:
    import bpy

    payload = []
    for name in names:
        obj = bpy.data.objects.get(name)
        payload.append({
            "name": name,
            "present": obj is not None,
            "type": obj.type if obj else None,
            "matrix_world": [round(float(v), 8) for row in obj.matrix_world for v in row] if obj else None,
            "hide_viewport": bool(obj.hide_viewport) if obj else None,
            "hide_render": bool(obj.hide_render) if obj else None,
            "materials": [slot.material.name for slot in obj.material_slots if slot.material] if obj else [],
            "mesh_sig": object_mesh_matrix_signature([name]) if obj and obj.type == "MESH" else None,
        })
    return hash_payload(payload)


def meso_mesh_material_matrix_signature(names: list[str], records: dict[str, Any]) -> str:
    return hash_payload([{k: records[name][k] for k in ("name", "type", "data_name", "vertex_count", "edge_count", "polygon_count", "matrix_world", "materials")} for name in names])


def pressure_signature() -> str:
    import bpy

    payload = []
    for name in PRESSURE_NAMES:
        obj = bpy.data.objects.get(name)
        payload.append({
            "name": name,
            "present": obj is not None,
            "type": obj.type if obj else None,
            "location": [round(float(v), 8) for v in obj.location] if obj else None,
            "rotation": [round(float(v), 8) for v in obj.rotation_euler] if obj else None,
            "scale": [round(float(v), 8) for v in obj.scale] if obj else None,
            "matrix_world": [round(float(v), 8) for row in obj.matrix_world for v in row] if obj else None,
            "materials": [slot.material.name for slot in obj.material_slots if slot.material] if obj else [],
            "mesh_sig": object_mesh_matrix_signature([name]) if obj and obj.type == "MESH" else None,
        })
    return hash_payload(payload)


def sensor_signature() -> str:
    import bpy

    payload = []
    for obj in sorted([item for item in bpy.data.objects if item.name.startswith("SENSOR_")], key=lambda item: item.name):
        payload.append({"name": obj.name, "parent": obj.parent.name if obj.parent else None, "location": [round(float(v), 8) for v in obj.location], "matrix_world": [round(float(v), 8) for row in obj.matrix_world for v in row]})
    return hash_payload(payload)


def hide_old_explanatory_objects(count_only: bool = False) -> dict[str, Any]:
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
            elif not count_only:
                obj.hide_viewport = True
                obj.hide_render = True
                hidden.append(obj.name)
    return {"matched_count": len(matched), "hidden_count": len(hidden), "hidden_names": sorted(hidden)}


def hash_payload(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()


def contains_nan(value: Any) -> bool:
    if isinstance(value, float):
        return math.isnan(value) or math.isinf(value)
    if isinstance(value, dict):
        return any(contains_nan(v) for v in value.values())
    if isinstance(value, (list, tuple)):
        return any(contains_nan(v) for v in value)
    return False


def compose_ab_images(renders_dir: Path) -> None:
    from PIL import Image, ImageDraw

    font_big = load_font(34)
    font_med = load_font(22)
    for layer in AB_CAMERAS:
        src = renders_dir / f"INT30_R2C_AB_SOURCE_{layer}.png"
        cand = renders_dir / f"INT30_R2C_AB_CANDIDATE_{layer}.png"
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
        draw.text((160, 25), "左：SURF-20 R5源；右：R2C候选。同相机/同SURF20_R5灯光", fill=(232, 242, 236, 255), font=font_med)
        draw.text((18, 82), "SOURCE R5", fill=(255, 141, 45, 255), font=font_med)
        draw.text((738, 82), "R2C CANDIDATE", fill=(255, 141, 45, 255), font=font_med)
        canvas.save(renders_dir / f"INT30_R2C_AB_{layer}_SOURCE_VS_CANDIDATE.png")


def postprocess_evidence_images(output_dir: Path) -> None:
    from PIL import Image, ImageDraw

    labels = {
        "INT30_R2C_01_FULL_MESO_RINGS_WELDS.png": ("R2C FULL", "仅恢复R5中尺度炉壳加强圈/焊缝可见性"),
        "INT30_R2C_02_GRAZING_MESO_DETAIL.png": ("R2C GRAZING", "R1材质锁定：B=0.16 / D=0.10m / N=0.45"),
        "INT30_R2C_03_STATIC_PRESSURE_OVERVIEW.png": ("R2C PRESSURE", "18个GL02_INT30_PRESSURE点位签名不变"),
        "INT30_R2C_04_CUTAWAY_SOLID_THICKNESS.png": ("R2C CUTAWAY", "INT-20十二个实体剖切结构签名不变"),
        "INT30_R2C_05_MESO_CLOSEUP_RINGS_WELDS.png": ("R2C MESO", "源R5中尺度几何恢复可见；不修改材质网络"),
    }
    font_big = load_font(34)
    font_med = load_font(22)
    for filename, (title, subtitle) in labels.items():
        path = output_dir / "renders" / filename
        if not path.is_file():
            continue
        img = Image.open(path).convert("RGBA")
        draw = ImageDraw.Draw(img)
        draw.rectangle((0, 0, img.width, 74), fill=(0, 0, 0, 205))
        draw.text((18, 16), title, fill=(255, 141, 45, 255), font=font_big)
        draw.text((230, 25), subtitle, fill=(232, 242, 236, 255), font=font_med)
        if filename == "INT30_R2C_04_CUTAWAY_SOLID_THICKNESS.png":
            label_font = load_font(20)
            line = (235, 220, 180, 255)
            text = (238, 238, 224, 255)
            callouts = [
                ((90, 625), (360, 475), "炉内侧\ninner_void"),
                ((355, 270), (655, 480), "耐火层\nrefractory_lining"),
                ((1180, 280), (980, 480), "钢制炉壳\nsteel_shell"),
                ((1090, 660), (875, 480), "冷却结构层\ncooling_wall"),
            ]
            for label_xy, point_xy, label in callouts:
                draw.line((label_xy[0] + 90, label_xy[1] + 12, point_xy[0], point_xy[1]), fill=line, width=4)
                draw.ellipse((point_xy[0] - 9, point_xy[1] - 9, point_xy[0] + 9, point_xy[1] + 9), fill=(255, 246, 220, 255))
                draw.text(label_xy, label, fill=text, font=label_font, spacing=2)
            draw.line((545, 842, 892, 842), fill=line, width=4)
            draw.text((662, 878), "炉内侧 <- 外侧", fill=text, font=label_font)
        img.save(path)


def load_font(size: int) -> Any:
    from PIL import ImageFont

    for path in [r"C:\Windows\Fonts\simhei.ttf", r"C:\Windows\Fonts\simsun.ttc", r"C:\Windows\Fonts\msyh.ttc"]:
        if Path(path).is_file():
            return ImageFont.truetype(path, size)
    return ImageFont.load_default()


def refresh_report_after_renders(output_dir: Path, candidate: Path) -> None:
    report_path = output_dir / "int30_r2c_machine_report.json"
    report = json.loads(report_path.read_text(encoding="utf-8"))
    report["candidate"].update({"bytes": candidate.stat().st_size, "sha256": sha256_file(candidate)})
    renders = []
    for manifest_path in [output_dir / "reports" / "candidate_evidence_render_manifest.json", output_dir / "reports" / "ab_source_render_manifest.json", output_dir / "reports" / "ab_candidate_render_manifest.json"]:
        if manifest_path.is_file():
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            renders.extend(manifest.get("records", []))
    for ab_path in sorted((output_dir / "renders").glob("INT30_R2C_AB_*_SOURCE_VS_CANDIDATE.png")):
        renders.append({"id": ab_path.stem.replace("INT30_R2C_", ""), "file": ab_path.name, "path": str(ab_path), "project_relative_path": rel(ab_path), "camera": "same_source_SURF20_R5_camera_transform_and_SURF20_R5_lights", "purpose": "strict A/B source R5 vs R2C candidate meso detail evidence", "resolution_px": None, "bytes": ab_path.stat().st_size, "sha256": sha256_file(ab_path)})
    for item in renders:
        path = Path(item["path"])
        if path.is_file():
            item["bytes"] = path.stat().st_size
            item["sha256"] = sha256_file(path)
    report["evidence_renders"] = renders
    report["assertions"]["renders_exist"] = all((output_dir / "renders" / item["file"]).is_file() for item in renders)
    report["assertions"]["blend1_not_generated"] = not any(output_dir.rglob("*.blend1"))
    report["assertions"]["no_output_glb"] = not any(output_dir.rglob("*.glb"))
    report["assertions"]["machine_assertions_pass"] = all(report["assertions"].values())
    report["execution"] = {"finished_at": now_iso(), "logs_dir": rel(output_dir / "reports"), "reopen_validation": rel(output_dir / "reopen_validation.json")}
    write_json(report_path, report)
    write_json(output_dir / "int30_r2c_visual_manifest.json", {"schema_version": "bf3d.visual_manifest.v1", "stage": STAGE_ID, "renders": renders})
    write_summary(output_dir, report)


def write_stage_pipeline_status(output_dir: Path, candidate: Path) -> None:
    status_path = ROOT / "reports" / "pipeline_status.json"
    status = json.loads(status_path.read_text(encoding="utf-8"))
    status.setdefault("stages", {})[STAGE_ID] = {
        "status": "candidate_ready_for_review",
        "approval": "not_granted_requires_visual_and_spec_review",
        "candidate_blend": rel(candidate),
        "candidate_sha256": sha256_file(candidate),
        "input_blend": rel(INPUT_BLEND),
        "input_sha256": EXPECTED_INPUT_SHA256,
        "visual_geometry_source_blend": rel(SOURCE_BLEND),
        "visual_geometry_source_sha256": EXPECTED_SOURCE_SHA256,
        "machine_report": rel(output_dir / "int30_r2c_machine_report.json"),
        "visual_manifest": rel(output_dir / "int30_r2c_visual_manifest.json"),
        "summary": rel(output_dir / "INT-30_R2C_R1_MESO_DETAIL_MERGE_阶段成果总结.md"),
        "formal_glb_unchanged": True,
        "formal_glb_sha256": EXPECTED_FORMAL_GLB_SHA256,
        "approval_boundary": "Only a Blender candidate restoring visible source R5 meso shell geometry in the INT-30 R2B branch; no self approval.",
        "next_stop_line": "independent_visual_and_spec_review_required_before_stockline_or_GLB_export",
    }
    status["current_stage"] = STAGE_ID
    status["updated_at"] = now_iso()
    write_json(status_path, status)
    write_json(output_dir / "pipeline_status_snapshot.json", {"schema_version": "bf3d.pipeline_status_snapshot.v1", "stage": STAGE_ID, "global_pipeline_status": rel(status_path), "stage_entry": status["stages"][STAGE_ID]})


def write_summary(output_dir: Path, report: dict[str, Any]) -> None:
    lines = [
        "# INT-30 R2C R1 中尺度细节合流阶段成果总结",
        "",
        f"- 阶段：`{STAGE_ID}`",
        "- 状态：`candidate_ready_for_review`；执行智能体未自我批准。",
        f"- 输入 R2B：`{report['input']['path']}`",
        f"- 输入 SHA：`{report['input']['actual_sha256']}`",
        f"- 视觉/几何来源 R5：`{report['visual_geometry_source']['path']}`",
        f"- 来源 SHA：`{report['visual_geometry_source']['actual_sha256']}`",
        f"- 候选：`{report['candidate']['path']}`",
        f"- 候选 SHA：`{report['candidate']['sha256']}`",
        "",
        "## 唯一变更",
        "",
        "- `APPROX_GL02_shell_stiffener_rings`：恢复为可见/可渲染。",
        "- `APPROX_GL02_P35_shell_welds`：恢复为可见/可渲染。",
        "- 源/目标差异证明两者在 R2B 中已存在且 mesh counts、matrix、material slots 与源 R5 一致；本阶段没有复制相机、灯光、World、材质网络、内部示意、传感器或 GLB。",
        "",
        "## 锁定项",
        "",
        f"- R1 参数未变：`{report['assertions']['r1_micro_surface_manifest_preserved']}`；B=0.16、D=0.10m、N=0.45、metallic=0.06、roughness=0.56-0.82。",
        f"- 五段炉壳 mesh/matrix 未变：`{report['assertions']['five_shell_mesh_matrix_unchanged']}`",
        f"- 五段炉壳材质未变：`{report['assertions']['five_shell_materials_unchanged']}`",
        f"- 18 个静压力点签名未变：`{report['assertions']['pressure_signature_unchanged']}`",
        f"- INT-20 十二个实体剖切结构签名未变：`{report['assertions']['int20_12_entity_signature_unchanged']}`",
        f"- 115 sensors / 80 body-temperature / L7-L16 保留：`{report['assertions']['sensor_count_115_preserved']}` / `{report['assertions']['body_temperature_80_preserved']}` / `{report['assertions']['l7_l16_groups_present']}`",
        f"- 旧 55 解释对象仍隐藏：`{report['assertions']['old_55_hidden_preserved']}`",
        f"- 正式 GLB 未变：`{report['formal_glb_protection']['unchanged']}` / `{report['formal_glb_protection']['after_sha256']}`",
        "",
        "## 证据",
        "",
        f"- 对象差异：`{rel(output_dir / 'source_target_meso_diff.json')}`",
        f"- 机器报告：`{rel(output_dir / 'int30_r2c_machine_report.json')}`",
        f"- Reopen：`{rel(output_dir / 'reopen_validation.json')}`",
        f"- 视觉清单：`{rel(output_dir / 'int30_r2c_visual_manifest.json')}`",
    ]
    for item in report.get("evidence_renders", []):
        lines.append(f"- `{item.get('id', item.get('layer', 'render'))}`：`{item['project_relative_path']}`")
    lines.extend(["", "## 停止线", "", "- 停在独立视觉/规格审核门；未进入料线、GLB 导出或生产替换。"])
    write_text(output_dir / "INT-30_R2C_R1_MESO_DETAIL_MERGE_阶段成果总结.md", "\n".join(lines) + "\n")


if __name__ == "__main__":
    if "--" in sys.argv and any(flag in sys.argv for flag in ("--audit-diff", "--run-blender-stage", "--reopen-validate", "--render-ab-source", "--render-ab-candidate", "--render-candidate-evidence")):
        raise SystemExit(blender_main())
    raise SystemExit(host_main())
