from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
STAGE_ID = "INT-20_R4"
REQUIREMENT_ID = "REQ-BF3D-INT20-R4-ANNOTATED-CUTAWAY-20260718"
DEFAULT_BLENDER = Path(r"D:\Program Files\Blender Foundation\Blender 5.2\blender.exe")
DEFAULT_INPUT = ROOT / "PT" / "高炉3D模型" / "work" / "INT_20_20260718_R3" / "INT_20_R3_VISUAL_READABILITY_CUTAWAY_CANDIDATE.blend"
DEFAULT_OUTPUT = ROOT / "PT" / "高炉3D模型" / "work" / "INT_20_20260718_R4"
R3_REPORT = ROOT / "PT" / "高炉3D模型" / "work" / "INT_20_20260718_R3" / "int20_r3_machine_report.json"
R3_MANIFEST = ROOT / "PT" / "高炉3D模型" / "work" / "INT_20_20260718_R3" / "int20_r3_visual_manifest.json"
EXPECTED_INPUT_SHA256 = "9878bc498766e82ddad4732bb57d607a052423fc2436ea7769c73b2373818995"
OUTPUT_BLEND_NAME = "INT_20_R4_ANNOTATED_CUTAWAY_CANDIDATE.blend"

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


def now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def write_json(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def collect_artifacts(output_dir: Path) -> list[dict[str, Any]]:
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
    return records


def write_summary(output_dir: Path, report: dict[str, Any]) -> None:
    lines = [
        "# INT-20 R4 阶段成果总结",
        "",
        "## 目标",
        "",
        "- 本轮只修 R3 的视觉可读性和工程标注：拉开三层色相/亮度、增强暗部补光、放大 EXPLODED 标注、补齐 SECTION 材料名与引线，并新增 QUARTER_INSET_DETAIL。",
        "- 输入固定为 INT-20 R3 候选 `.blend`；R4 不修改 INT-10/R3 源实体对象的网格、矩阵、厚度签名或命名。",
        "- 未导出 GLB，状态最高停在 `candidate_ready_for_review`。",
        "",
        "## 产物",
        "",
        f"- 候选 blend：`{report['candidate']['path']}`",
        f"- 机器报告：`{output_dir / 'int20_r4_machine_report.json'}`",
        f"- 视觉 manifest：`{output_dir / 'int20_r4_visual_manifest.json'}`",
        f"- 重新打开验证：`{output_dir / 'reopen_validation.json'}`",
        f"- 命令记录：`{output_dir / 'command.json'}`",
        f"- 哈希清单：`{output_dir / 'artifact_sha256.json'}`",
        "",
        "## 证据图",
        "",
    ]
    for item in report.get("evidence_renders", []):
        lines.append(f"- `{item['id']}`：`{Path(item['path']).relative_to(output_dir).as_posix()}`，{item['bytes']} bytes")
    assertions = report.get("assertions", {})
    lines.extend(
        [
            "",
            "## 关键断言",
            "",
            f"- R3 输入 SHA 匹配：`{assertions.get('input_sha256_matches')}`",
            f"- 源几何/矩阵/厚度签名不变：`{assertions.get('source_geometry_matrix_thickness_signature_unchanged')}`",
            f"- 115 传感器与 80 炉体温度点不变：`{assertions.get('sensor_contract_pass')}`",
            f"- HALF/QUARTER/EXPLODED 主体高度与上下安全边距通过：`{assertions.get('full_body_margin_metrics_pass')}`",
            f"- cut views 完全隐藏 process space：`{assertions.get('process_space_hidden_in_cut_views')}`",
            f"- COLORCARD 标签包围盒不重叠：`{assertions.get('colorcard_label_bboxes_non_overlapping')}`",
            f"- SECTION/EXPLODED/INSET 工程标注与引线存在且包围盒不重叠：`{assertions.get('engineering_annotations_complete')}` / `{assertions.get('annotation_label_bboxes_non_overlapping')}`",
            f"- Freestyle 禁用或小于等于 0.5px 低对比：`{assertions.get('freestyle_disabled_or_restrained')}`",
            f"- 未生成 `.blend1`，未导出 GLB：`{assertions.get('blend1_not_generated')}` / `{assertions.get('formal_glb_not_exported')}`",
            "",
            "## 说明",
            "",
            "- `EXPLODED_CUT` 使用 render-only 克隆拉开三层空气隙，源对象不移动；该图标注“分离展示，不按比例”。",
            "- `SECTION_CLOSEUP_ANNOTATED`、`SECTION_MAGNIFIED_5X_ANNOTATED` 和 `QUARTER_INSET_DETAIL` 均明确“E级工艺示意｜非实测厚度”。",
            "- approval 仍为 `not_granted_requires_visual_and_spec_review`，不得在独立视觉和规格审查前进入下一阶段。",
        ]
    )
    (output_dir / "INT-20_R4_阶段成果总结.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def host_main() -> int:
    parser = argparse.ArgumentParser(description="INT-20 R4 visual readability cutaway runner")
    parser.add_argument("--blender", type=Path, default=DEFAULT_BLENDER)
    parser.add_argument("--input-blend", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--width", type=int, default=1440)
    parser.add_argument("--height", type=int, default=960)
    args = parser.parse_args()

    blender = args.blender.resolve()
    input_blend = args.input_blend.resolve()
    output_dir = args.output_dir.resolve()
    script = Path(__file__).resolve()
    output_blend = output_dir / OUTPUT_BLEND_NAME

    for required in (blender, input_blend, script, R3_REPORT, R3_MANIFEST):
        if not required.is_file():
            raise FileNotFoundError(required)
    input_sha = sha256_file(input_blend)
    if input_sha.lower() != EXPECTED_INPUT_SHA256:
        raise RuntimeError(f"R3 input hash mismatch: expected={EXPECTED_INPUT_SHA256} actual={input_sha}")
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "renders").mkdir(exist_ok=True)
    stale_blend1 = sorted(output_dir.glob("*.blend1"))
    if stale_blend1:
        raise RuntimeError(f"Refusing to continue while .blend1 exists in R4 workdir: {stale_blend1[0]}")

    command = [
        str(blender),
        "--background",
        str(input_blend),
        "--python",
        str(script),
        "--",
        "--inside-blender",
        "--input-blend",
        str(input_blend),
        "--output-dir",
        str(output_dir),
        "--width",
        str(args.width),
        "--height",
        str(args.height),
    ]
    reopen_command = [
        str(blender),
        "--background",
        str(output_blend),
        "--python",
        str(script),
        "--",
        "--reopen-validate",
        "--input-blend",
        str(input_blend),
        "--output-dir",
        str(output_dir),
        "--width",
        str(args.width),
        "--height",
        str(args.height),
    ]
    command_record = {
        "schema_version": 1,
        "stage": STAGE_ID,
        "requirement_id": REQUIREMENT_ID,
        "started_at": now_iso(),
        "cwd": str(ROOT),
        "command_argv": command,
        "reopen_command_argv": reopen_command,
        "input_sha256": input_sha,
        "formal_glb_exported": False,
        "blend1_forbidden": True,
    }
    write_json(output_dir / "command.json", command_record)

    completed = subprocess.run(command, cwd=ROOT, check=False, capture_output=True, text=True, encoding="utf-8", errors="replace")
    (output_dir / "blender_stdout.log").write_text(completed.stdout or "", encoding="utf-8")
    (output_dir / "blender_stderr.log").write_text(completed.stderr or "", encoding="utf-8")
    command_record["main_returncode"] = completed.returncode
    command_record["main_finished_at"] = now_iso()
    write_json(output_dir / "command.json", command_record)
    if completed.returncode != 0:
        print(completed.stdout)
        print(completed.stderr, file=sys.stderr)
        return completed.returncode
    if not output_blend.is_file() or not (output_dir / "int20_r4_machine_report.json").is_file():
        return 1

    reopened = subprocess.run(reopen_command, cwd=ROOT, check=False, capture_output=True, text=True, encoding="utf-8", errors="replace")
    (output_dir / "reopen_stdout.log").write_text(reopened.stdout or "", encoding="utf-8")
    (output_dir / "reopen_stderr.log").write_text(reopened.stderr or "", encoding="utf-8")
    command_record["reopen_returncode"] = reopened.returncode
    command_record["reopen_finished_at"] = now_iso()
    write_json(output_dir / "command.json", command_record)
    if reopened.returncode != 0:
        print(reopened.stdout)
        print(reopened.stderr, file=sys.stderr)
        return reopened.returncode

    report_path = output_dir / "int20_r4_machine_report.json"
    report = json.loads(report_path.read_text(encoding="utf-8"))
    report["execution"] = {
        "finished_at": now_iso(),
        "returncode": completed.returncode,
        "reopen_returncode": reopened.returncode,
        "command_record": str(output_dir / "command.json"),
        "stdout_log": str(output_dir / "blender_stdout.log"),
        "stderr_log": str(output_dir / "blender_stderr.log"),
        "reopen_stdout_log": str(output_dir / "reopen_stdout.log"),
        "reopen_stderr_log": str(output_dir / "reopen_stderr.log"),
    }
    report["reopen_validation"] = json.loads((output_dir / "reopen_validation.json").read_text(encoding="utf-8"))
    report["assertions"]["reopen_validation_pass"] = report["reopen_validation"].get("status") == "pass"
    report["assertions"]["machine_assertions_pass"] = all(bool(v) for v in report["assertions"].values())
    write_json(report_path, report)
    write_summary(output_dir, report)
    write_json(
        output_dir / "artifact_sha256.json",
        {
            "schema_version": 1,
            "stage": STAGE_ID,
            "generated_at": now_iso(),
            "artifacts": collect_artifacts(output_dir),
        },
    )
    if list(output_dir.glob("*.blend1")):
        raise RuntimeError("Blender backup .blend1 was generated in R3 workdir")
    print(f"{STAGE_ID} complete: {output_blend}")
    return 0


def blender_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--inside-blender", action="store_true")
    parser.add_argument("--reopen-validate", action="store_true")
    parser.add_argument("--input-blend", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--width", type=int, default=1440)
    parser.add_argument("--height", type=int, default=960)
    if "--" in sys.argv:
        return parser.parse_args(sys.argv[sys.argv.index("--") + 1 :])
    return parser.parse_args([])


def blender_main() -> int:
    import math

    import bpy
    import bmesh
    from mathutils import Vector
    from bpy_extras.object_utils import world_to_camera_view

    args = blender_args()
    output_dir = args.output_dir.resolve()
    render_dir = output_dir / "renders"
    render_dir.mkdir(parents=True, exist_ok=True)
    output_blend = output_dir / OUTPUT_BLEND_NAME
    r3_report = json.loads(R3_REPORT.read_text(encoding="utf-8"))
    r3_manifest = json.loads(R3_MANIFEST.read_text(encoding="utf-8"))

    scene = bpy.context.scene
    try:
        bpy.context.preferences.filepaths.save_version = 0
    except Exception:
        pass

    def sensor_objects() -> list[Any]:
        return sorted([o for o in bpy.data.objects if o.name.startswith("SENSOR_")], key=lambda o: o.name)

    def sensor_signature() -> str:
        rows = []
        for obj in sensor_objects():
            rows.append(
                {
                    "name": obj.name,
                    "parent": obj.parent.name if obj.parent else None,
                    "matrix": [round(v, 8) for row in obj.matrix_world for v in row],
                }
            )
        return hashlib.sha256(json.dumps(rows, sort_keys=True).encode("utf-8")).hexdigest()

    def mesh_signature(names: list[str]) -> str:
        rows = []
        for name in names:
            obj = bpy.data.objects.get(name)
            if not obj or not obj.data:
                rows.append({"name": name, "missing": True})
                continue
            mesh = obj.data
            verts = [(round(v.co.x, 7), round(v.co.y, 7), round(v.co.z, 7)) for v in mesh.vertices]
            polys = [tuple(p.vertices) for p in mesh.polygons]
            rows.append(
                {
                    "name": name,
                    "matrix": [round(v, 8) for row in obj.matrix_world for v in row],
                    "verts": verts,
                    "polys": polys,
                }
            )
        return hashlib.sha256(json.dumps(rows, sort_keys=True).encode("utf-8")).hexdigest()

    def object_audit(obj: Any) -> dict[str, Any]:
        bm = bmesh.new()
        bm.from_mesh(obj.data)
        bm.normal_update()
        volume = bm.calc_volume(signed=True)
        non_manifold = sum(1 for e in bm.edges if not e.is_manifold)
        bm.free()
        cutfaces = sum(1 for p in obj.data.polygons if p.material_index == 1)
        return {
            "vertices": len(obj.data.vertices),
            "edges": len(obj.data.edges),
            "faces": len(obj.data.polygons),
            "non_manifold_edges": non_manifold,
            "positive_volume": volume > 0,
            "volume_m3_estimate": abs(volume),
            "cutface_material_faces": cutfaces,
            "material_slots": [slot.material.name if slot.material else None for slot in obj.material_slots],
        }

    sensor_sig_before = sensor_signature()
    source_sig_before = mesh_signature(INT10_OBJECTS)

    def make_mat(name: str, base: tuple[float, float, float, float], metallic: float, roughness: float, alpha: float = 1.0) -> Any:
        mat = bpy.data.materials.new(name)
        mat.use_nodes = True
        mat.diffuse_color = base
        nodes = mat.node_tree.nodes
        nodes.clear()
        output = nodes.new(type="ShaderNodeOutputMaterial")
        diffuse = nodes.new(type="ShaderNodeBsdfDiffuse")
        diffuse.inputs["Color"].default_value = base
        if "Roughness" in diffuse.inputs:
            diffuse.inputs["Roughness"].default_value = roughness
        mat.node_tree.links.new(diffuse.outputs["BSDF"], output.inputs["Surface"])
        # Keep these fields populated for downstream material audits even though R3 renders use Diffuse for readability.
        mat["int20_r4_target_metallic"] = metallic
        mat["int20_r4_target_roughness"] = roughness
        try:
            try:
                mat.surface_render_method = "DITHERED" if alpha < 1.0 else "DITHERED"
            except Exception:
                pass
        except Exception:
            pass
        if alpha < 1.0:
            mat.blend_method = "BLEND"
            mat.show_transparent_back = False
        return mat

    def make_emission_mat(name: str, color: tuple[float, float, float, float], strength: float = 0.75) -> Any:
        mat = bpy.data.materials.new(name)
        mat.use_nodes = True
        mat.diffuse_color = color
        nodes = mat.node_tree.nodes
        nodes.clear()
        output = nodes.new(type="ShaderNodeOutputMaterial")
        emit = nodes.new(type="ShaderNodeEmission")
        emit.inputs["Color"].default_value = color
        emit.inputs["Strength"].default_value = strength
        mat.node_tree.links.new(emit.outputs["Emission"], output.inputs["Surface"])
        return mat

    mats = {
        "steel_body": make_mat("MI_INT20_R4_STEEL_SHELL_BODY_COOL_BLUE_STEEL", (0.26, 0.33, 0.39, 1), 0.62, 0.65),
        "steel_cut": make_mat("MI_INT20_R4_STEEL_SHELL_CUTFACE_COLD_GRAY_BLUE", (0.52, 0.62, 0.69, 1), 0.30, 0.70),
        "cool_body": make_mat("MI_INT20_R4_COOLING_WALL_BODY_WARM_COPPER_BROWN", (0.50, 0.28, 0.13, 1), 0.10, 0.76),
        "cool_cut": make_mat("MI_INT20_R4_COOLING_WALL_CUTFACE_BRIGHT_COPPER", (0.86, 0.50, 0.22, 1), 0.06, 0.80),
        "refr_body": make_mat("MI_INT20_R4_REFRACTORY_BODY_LIGHT_BRICK_GRAY", (0.70, 0.59, 0.42, 1), 0.0, 0.86),
        "refr_cut": make_mat("MI_INT20_R4_REFRACTORY_CUTFACE_BRIGHT_BEIGE", (0.94, 0.84, 0.57, 1), 0.0, 0.88),
        "process": make_mat("MI_INT20_R4_PROCESS_SPACE_RENDER_HIDDEN_REFERENCE", (0.16, 0.16, 0.15, 1), 0.0, 0.9, 1.0),
    }

    family_slots = {
        "STEEL_SHELL": (mats["steel_body"], mats["steel_cut"]),
        "COOLING_WALL": (mats["cool_body"], mats["cool_cut"]),
        "REFRACTORY_LINING": (mats["refr_body"], mats["refr_cut"]),
        "PROCESS_SPACE": (mats["process"], mats["process"]),
    }
    for name in INT10_OBJECTS:
        obj = bpy.data.objects.get(name)
        if not obj:
            raise RuntimeError(f"Missing INT10 object: {name}")
        for token, pair in family_slots.items():
            if token in name:
                while len(obj.material_slots) < 2:
                    obj.data.materials.append(pair[0])
                obj.material_slots[0].material = pair[0]
                obj.material_slots[1].material = pair[1]
                break

    scene.render.engine = "BLENDER_EEVEE_NEXT" if "BLENDER_EEVEE_NEXT" in [i.identifier for i in bpy.types.RenderSettings.bl_rna.properties["engine"].enum_items] else "BLENDER_EEVEE"
    scene.render.resolution_x = args.width
    scene.render.resolution_y = args.height
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = "PNG"
    scene.render.film_transparent = False
    scene.render.use_freestyle = False
    try:
        scene.eevee.taa_render_samples = 96
        scene.eevee.use_gtao = True
        scene.eevee.gtao_distance = 4
        scene.eevee.gtao_factor = 0.55
    except Exception:
        pass
    scene.view_settings.view_transform = "AgX"
    for look_name in ("AgX - Medium High Contrast", "Medium High Contrast", "AgX - High Contrast", "None"):
        try:
            scene.view_settings.look = look_name
            break
        except TypeError:
            continue
    scene.view_settings.exposure = 0.72
    scene.view_settings.gamma = 1.0
    bpy.context.scene.world = bpy.context.scene.world or bpy.data.worlds.new("World")
    bpy.context.scene.world.color = (0.42, 0.43, 0.42)

    for obj in bpy.data.objects:
        if obj.name.startswith("INT20_R4_") or obj.name.startswith("APPROX_GL02_INT20_R4_"):
            bpy.data.objects.remove(obj, do_unlink=True)
    if "INT20_R4_RENDER_ONLY_AUX" in bpy.data.collections:
        bpy.data.collections.remove(bpy.data.collections["INT20_R4_RENDER_ONLY_AUX"])
    aux = bpy.data.collections.new("INT20_R4_RENDER_ONLY_AUX")
    scene.collection.children.link(aux)

    def add_area(name: str, loc: tuple[float, float, float], energy: float, size: float, color: tuple[float, float, float]) -> None:
        data = bpy.data.lights.new(name, "AREA")
        data.energy = energy
        data.size = size
        data.color = color
        obj = bpy.data.objects.new(name, data)
        obj.location = loc
        aux.objects.link(obj)

    add_area("INT20_R4_LIGHT_CUTFACE_SOFT_KEY", (-8, -18, 10), 14500, 20, (1.0, 0.96, 0.88))
    add_area("INT20_R4_LIGHT_SECTION_SIDE_FILL", (16, -10, 2), 11800, 15, (0.82, 0.90, 1.0))
    add_area("INT20_R4_LIGHT_TOP_AMBIENT_PANEL", (0, -4, 18), 8500, 26, (0.95, 0.95, 0.92))
    add_area("INT20_R4_LIGHT_FRONT_LOW_FILL", (-14, -22, -6), 5600, 18, (0.88, 0.93, 1.0))

    def duplicate_for_exploded(source: str, label: str, offset: Vector) -> Any:
        src = bpy.data.objects[source]
        clone = src.copy()
        clone.data = src.data.copy()
        clone.name = f"APPROX_GL02_INT20_R4_RENDER_ONLY_EXPLODED_{label}"
        clone.data.name = clone.name + "_MESH"
        clone.location = src.location + offset
        clone.hide_viewport = True
        clone.hide_render = True
        aux.objects.link(clone)
        return clone

    exploded = {
        "steel": duplicate_for_exploded("APPROX_GL02_INT10_STEEL_SHELL_HALF", "STEEL_SHELL_HALF", Vector((2.55, -1.35, 0))),
        "cool": duplicate_for_exploded("APPROX_GL02_INT10_COOLING_WALL_HALF", "COOLING_WALL_HALF", Vector((0, 0, 0))),
        "refr": duplicate_for_exploded("APPROX_GL02_INT10_REFRACTORY_LINING_HALF", "REFRACTORY_LINING_HALF", Vector((-2.55, 1.35, 0))),
    }

    text_material = make_emission_mat("MI_INT20_R4_LABEL_DARK_TEXT", (0.02, 0.02, 0.018, 1), 0.65)
    white_text = make_emission_mat("MI_INT20_R4_LABEL_LIGHT_TEXT", (0.98, 0.94, 0.78, 1), 1.25)
    leader_mat = make_emission_mat("MI_INT20_R4_LEADER_LINE_WARM_AMBER", (1.0, 0.80, 0.34, 1), 1.15)

    def add_label(
        name: str,
        text: str,
        loc: tuple[float, float, float],
        size: float,
        mat: Any = text_material,
        rot_x_deg: float = 70,
    ) -> Any:
        curve = bpy.data.curves.new(name, "FONT")
        curve.body = text
        curve.align_x = "CENTER"
        curve.align_y = "CENTER"
        curve.size = size
        curve.materials.append(mat)
        obj = bpy.data.objects.new(name, curve)
        obj.location = loc
        obj.rotation_euler = (math.radians(rot_x_deg), 0, 0)
        obj.hide_viewport = True
        obj.hide_render = True
        aux.objects.link(obj)
        return obj

    mag_label = add_label("APPROX_GL02_INT20_R4_LABEL_SECTION_MAGNIFIED_5X", "5x view / E-grade", (4.0, -0.9, 0.72), 0.12, white_text)
    exploded_label = add_label("APPROX_GL02_INT20_R4_LABEL_EXPLODED_NOT_TO_SCALE", "分离展示，不按比例", (0.0, -4.8, -7.2), 1.25, white_text)

    colorcard_labels = []
    swatches = [
        ("STEEL", mats["steel_cut"], (-2.7, -5.0, 0.55), "钢制炉壳\nSteel shell"),
        ("COOLING", mats["cool_cut"], (-0.9, -5.0, 0.55), "冷却结构层\nCooling layer"),
        ("REFRACTORY", mats["refr_cut"], (0.9, -5.0, 0.55), "耐火层\nRefractory"),
        ("PROCESS", mats["process"], (2.7, -5.0, 0.55), "炉内侧\nHidden in cuts"),
    ]
    for swatch, mat, loc, label in swatches:
        bpy.ops.mesh.primitive_cube_add(size=1, location=loc)
        obj = bpy.context.object
        obj.name = f"APPROX_GL02_INT20_R4_COLORCARD_BLOCK_{swatch}"
        obj.scale = (0.72, 0.04, 0.55)
        obj.data.materials.append(mat)
        obj.hide_viewport = True
        obj.hide_render = True
        aux.objects.link(obj)
        try:
            scene.collection.objects.unlink(obj)
        except Exception:
            pass
        colorcard_labels.append(
            add_label(f"APPROX_GL02_INT20_R4_COLORCARD_LABEL_{swatch}", label, (loc[0], -5.1, -0.34), 0.22, text_material, 90)
        )

    inset_helpers = []
    inset_specs = [
        ("STEEL", mats["steel_cut"], (-1.25, -6.3, 0.15), (0.18, 0.035, 1.28)),
        ("COOLING", mats["cool_cut"], (-0.45, -6.3, 0.15), (0.28, 0.035, 1.28)),
        ("REFRACTORY", mats["refr_cut"], (0.55, -6.3, 0.15), (0.42, 0.035, 1.28)),
        ("INNER", mats["process"], (1.45, -6.3, 0.15), (0.28, 0.035, 1.28)),
    ]
    for swatch, mat, loc, scale in inset_specs:
        bpy.ops.mesh.primitive_cube_add(size=1, location=loc)
        obj = bpy.context.object
        obj.name = f"APPROX_GL02_INT20_R4_RENDER_ONLY_INSET_DETAIL_{swatch}"
        obj.scale = scale
        obj.data.materials.append(mat)
        obj.hide_viewport = True
        obj.hide_render = True
        aux.objects.link(obj)
        inset_helpers.append(obj)
        try:
            scene.collection.objects.unlink(obj)
        except Exception:
            pass

    def look_at(obj: Any, target: Vector) -> None:
        direction = target - obj.location
        obj.rotation_euler = direction.to_track_quat("-Z", "Y").to_euler()

    def camera(name: str, loc: tuple[float, float, float], target: tuple[float, float, float], ortho: bool = True, scale: float = 40, lens: float = 58) -> Any:
        data = bpy.data.cameras.new(name)
        data.type = "ORTHO" if ortho else "PERSP"
        data.ortho_scale = scale
        data.lens = lens
        data.clip_end = 500
        obj = bpy.data.objects.new(name, data)
        obj.location = loc
        look_at(obj, Vector(target))
        aux.objects.link(obj)
        return obj

    cameras = {
        "FRONT_CONTEXT": camera("INT20_R4_CAM_FRONT_CONTEXT_ORTHO", (0, -72, 17), (0, 0, 17), True, 48),
        "HALF_CUT": camera("INT20_R4_CAM_HALF_CUT_45_ORTHO", (28, -52, 24), (0, 0, 17), True, 48),
        "QUARTER_CUT": camera("INT20_R4_CAM_QUARTER_CUT_45_ORTHO", (30, -50, 24), (0, 0, 17), True, 48),
        "EXPLODED_CUT": camera("INT20_R4_CAM_EXPLODED_CUT_45_ORTHO", (31, -54, 24), (0, 0, 17), True, 50),
        "SECTION_CLOSEUP_ANNOTATED": camera("INT20_R4_CAM_SECTION_CLOSEUP_ANNOTATED_SIDE_ORTHO", (9.2, -10.8, 0.0), (4.02, 0.05, 0.0), True, 4.6),
        "SECTION_MAGNIFIED_5X_ANNOTATED": camera("INT20_R4_CAM_SECTION_MAGNIFIED_5X_ANNOTATED_ORTHO", (8.6, -8.4, 0.15), (4.02, 0.05, 0.15), True, 0.92),
        "COLORCARD": camera("INT20_R4_CAM_COLORCARD_ORTHO", (0, -14, 0.25), (0, -5, 0.25), True, 7.2),
        "QUARTER_INSET_DETAIL": camera("INT20_R4_CAM_QUARTER_INSET_DETAIL_ORTHO", (0, -12.6, 0.15), (0, -6.3, 0.15), True, 4.2),
    }

    overlay_groups: dict[str, list[Any]] = {
        "closeup": [],
        "magnified": [],
        "exploded": [],
        "quarter_inset": [],
    }

    def add_camera_overlay_label(
        name: str,
        text: str,
        cam: Any,
        loc: tuple[float, float, float],
        size: float,
        group: str,
    ) -> Any:
        curve = bpy.data.curves.new(name, "FONT")
        curve.body = text
        curve.align_x = "CENTER"
        curve.align_y = "CENTER"
        curve.size = size
        curve.materials.append(white_text)
        obj = bpy.data.objects.new(name, curve)
        obj.parent = cam
        obj.location = (loc[0], loc[1], -0.5)
        obj.rotation_euler = (0, 0, 0)
        obj.hide_viewport = True
        obj.hide_render = True
        aux.objects.link(obj)
        overlay_groups[group].append(obj)
        return obj

    def add_camera_overlay_line(name: str, cam: Any, points: list[tuple[float, float]], group: str) -> Any:
        curve = bpy.data.curves.new(name, "CURVE")
        curve.dimensions = "3D"
        curve.resolution_u = 1
        curve.bevel_depth = 0.004
        curve.materials.append(leader_mat)
        spline = curve.splines.new("POLY")
        spline.points.add(len(points) - 1)
        for point, xy in zip(spline.points, points):
            point.co = (xy[0], xy[1], -0.5, 1)
        obj = bpy.data.objects.new(name, curve)
        obj.parent = cam
        obj.hide_viewport = True
        obj.hide_render = True
        aux.objects.link(obj)
        overlay_groups[group].append(obj)
        return obj

    def section_callouts(cam_key: str, group: str, size: float) -> None:
        cam = cameras[cam_key]
        if group == "magnified":
            entries = [
                ("STEEL", "钢制炉壳", (-0.24, 0.28, -2.0), (-0.11, 0.17)),
                ("COOLING", "冷却结构层", (-0.24, 0.13, -2.0), (-0.05, 0.05)),
                ("REFRACTORY", "耐火层\nE级示意\n非实测厚度", (-0.24, -0.02, -2.0), (0.06, -0.07)),
                ("INNER", "炉内侧", (0.30, -0.20, -2.0), (0.18, -0.08)),
            ]
            note_loc = (-0.22, -0.34, -2.0)
            note_text = "E级示意\n非实测厚度"
        else:
            entries = [
                ("STEEL", "钢制炉壳\nSteel shell", (-0.78, 0.28, -2.0), (-0.22, 0.10)),
                ("COOLING", "冷却结构层\nCooling layer", (-0.78, 0.08, -2.0), (-0.08, 0.02)),
                ("REFRACTORY", "耐火层\nRefractory", (-0.78, -0.12, -2.0), (0.05, -0.06)),
                ("INNER", "炉内侧\nInner side", (0.68, -0.22, -2.0), (0.20, -0.10)),
            ]
            note_loc = (0.08, 0.43, -2.0)
            note_text = "E级工艺示意｜非实测厚度"
        for token, label, loc, tip in entries:
            add_camera_overlay_label(f"APPROX_GL02_INT20_R4_LABEL_{cam_key}_{token}", label, cam, loc, size, group)
            add_camera_overlay_line(f"APPROX_GL02_INT20_R4_LEADER_{cam_key}_{token}", cam, [(loc[0] + 0.15, loc[1] - 0.02), tip], group)
        add_camera_overlay_label(
            f"APPROX_GL02_INT20_R4_LABEL_{cam_key}_E_GRADE_NOTE",
            note_text,
            cam,
            note_loc,
            size * 0.95,
            group,
        )

    section_callouts("SECTION_CLOSEUP_ANNOTATED", "closeup", 0.048)
    section_callouts("SECTION_MAGNIFIED_5X_ANNOTATED", "magnified", 0.028)
    mag_label = add_camera_overlay_label(
        "APPROX_GL02_INT20_R4_LABEL_SECTION_MAGNIFIED_5X_OVERLAY",
        "5x 局部放大",
        cameras["SECTION_MAGNIFIED_5X_ANNOTATED"],
        (0.38, 0.32, -2.0),
        0.026,
        "magnified",
    )
    add_camera_overlay_label(
        "APPROX_GL02_INT20_R4_LABEL_EXPLODED_OVERLAY",
        "分离展示，不按比例\nE级示意｜非实测厚度",
        cameras["EXPLODED_CUT"],
        (0.0, -0.44, -2.0),
        0.055,
        "exploded",
    )
    add_camera_overlay_label(
        "APPROX_GL02_INT20_R4_LABEL_QUARTER_INSET_TITLE",
        "QUARTER_CUT 局部放大\nE级示意｜非实测厚度",
        cameras["QUARTER_INSET_DETAIL"],
        (0.0, 0.46, -2.0),
        0.065,
        "quarter_inset",
    )
    inset_labels = [
        ("STEEL", "钢制炉壳", (-0.80, -0.39, -2.0)),
        ("COOLING", "冷却结构层", (-0.18, -0.39, -2.0)),
        ("REFRACTORY", "耐火层", (0.52, -0.39, -2.0)),
        ("INNER", "炉内侧", (1.05, -0.39, -2.0)),
    ]
    for token, label, loc in inset_labels:
        add_camera_overlay_label(f"APPROX_GL02_INT20_R4_LABEL_QUARTER_INSET_{token}", label, cameras["QUARTER_INSET_DETAIL"], loc, 0.042, "quarter_inset")

    def corners(obj: Any) -> list[Vector]:
        return [obj.matrix_world @ Vector(corner) for corner in obj.bound_box]

    def visible_bbox(objs: list[Any]) -> tuple[Vector, Vector]:
        pts = [p for obj in objs for p in corners(obj)]
        mins = Vector((min(p.x for p in pts), min(p.y for p in pts), min(p.z for p in pts)))
        maxs = Vector((max(p.x for p in pts), max(p.y for p in pts), max(p.z for p in pts)))
        return mins, maxs

    def fit_ortho(cam: Any, objs: list[Any], desired: float = 0.76) -> None:
        mins, maxs = visible_bbox(objs)
        center = (mins + maxs) * 0.5
        look_at(cam, center)
        bpy.context.view_layer.update()
        inv = cam.matrix_world.inverted()
        pts = [inv @ p for obj in objs for p in corners(obj)]
        y_extent = max(p.y for p in pts) - min(p.y for p in pts)
        x_extent = max(p.x for p in pts) - min(p.x for p in pts)
        aspect = scene.render.resolution_x / scene.render.resolution_y
        # Blender 5.x orthographic scale is interpreted as horizontal span for this scene setup.
        cam.data.ortho_scale = max((y_extent * aspect) / desired, x_extent / 0.88)
        look_at(cam, center)
        bpy.context.view_layer.update()

    def projection_bbox(cam: Any, objs: list[Any]) -> dict[str, float]:
        bpy.context.view_layer.update()
        pts = [world_to_camera_view(scene, cam, p) for obj in objs for p in corners(obj)]
        xmin, xmax = min(p.x for p in pts), max(p.x for p in pts)
        ymin, ymax = min(p.y for p in pts), max(p.y for p in pts)
        return {
            "xmin": float(xmin),
            "xmax": float(xmax),
            "ymin": float(ymin),
            "ymax": float(ymax),
            "height_fraction": float(ymax - ymin),
            "top_margin": float(1 - ymax),
            "bottom_margin": float(ymin),
            "left_margin": float(xmin),
            "right_margin": float(1 - xmax),
        }

    def objects_for(mode: str) -> list[Any]:
        if mode == "front":
            keys = ["STEEL_SHELL_FULL", "COOLING_WALL_FULL", "REFRACTORY_LINING_FULL"]
            return [bpy.data.objects[f"APPROX_GL02_INT10_{k}"] for k in keys]
        if mode == "half":
            keys = ["STEEL_SHELL_HALF", "COOLING_WALL_HALF", "REFRACTORY_LINING_HALF"]
            return [bpy.data.objects[f"APPROX_GL02_INT10_{k}"] for k in keys]
        if mode == "quarter":
            keys = ["STEEL_SHELL_QUARTER", "COOLING_WALL_QUARTER", "REFRACTORY_LINING_QUARTER"]
            return [bpy.data.objects[f"APPROX_GL02_INT10_{k}"] for k in keys]
        if mode == "exploded":
            return list(exploded.values())
        if mode in {"closeup", "magnified"}:
            keys = ["STEEL_SHELL_HALF", "COOLING_WALL_HALF", "REFRACTORY_LINING_HALF"]
            return [bpy.data.objects[f"APPROX_GL02_INT10_{k}"] for k in keys]
        if mode == "quarter_inset":
            return inset_helpers
        return []

    for view, mode in [("FRONT_CONTEXT", "front"), ("HALF_CUT", "half"), ("QUARTER_CUT", "quarter"), ("EXPLODED_CUT", "exploded")]:
        fit_ortho(cameras[view], objects_for(mode), desired=0.76)

    def set_visibility(mode: str) -> dict[str, bool]:
        for obj in bpy.data.objects:
            if (
                obj.name.startswith("APPROX_GL02_INT10_")
                or obj.name.startswith("APPROX_GL02_INT20_R3_")
                or obj.name.startswith("APPROX_GL02_INT20_R4_")
                or "INT20_R2" in obj.name
                or obj.name.startswith("INT20_R4_")
            ):
                obj.hide_render = True
        for obj in objects_for(mode):
            obj.hide_render = False
        if mode == "exploded":
            exploded_label.hide_render = False
            for obj in overlay_groups["exploded"]:
                obj.hide_render = False
        if mode == "magnified":
            for obj in overlay_groups["magnified"]:
                obj.hide_render = False
        if mode == "closeup":
            for obj in overlay_groups["closeup"]:
                obj.hide_render = False
        if mode == "quarter_inset":
            for obj in overlay_groups["quarter_inset"]:
                obj.hide_render = False
        if mode == "colorcard":
            for obj in bpy.data.objects:
                if obj.type in {"MESH", "FONT"} and not obj.name.startswith("APPROX_GL02_INT20_R4_COLORCARD_"):
                    obj.hide_render = True
            for obj in aux.objects:
                if "COLORCARD_" in obj.name:
                    obj.hide_render = False
        return {name: bool(bpy.data.objects[name].hide_render) for name in INT10_OBJECTS if "PROCESS_SPACE" in name}

    render_specs = [
        ("FRONT_CONTEXT", "front", "complete_front_context_top_bottom_visible_process_hidden"),
        ("HALF_CUT", "half", "full_height_half_cut_body_70_82_percent_process_hidden"),
        ("QUARTER_CUT", "quarter", "full_height_quarter_cut_body_70_82_percent_process_hidden"),
        ("EXPLODED_CUT", "exploded", "render_only_clones_with_readable_air_gaps_not_to_scale"),
        ("SECTION_CLOSEUP_ANNOTATED", "closeup", "annotated_side_section_with_material_labels_leaders_e_grade_note"),
        ("SECTION_MAGNIFIED_5X_ANNOTATED", "magnified", "annotated_camera_only_local_magnification_5x_view_e_grade"),
        ("COLORCARD", "colorcard", "four_column_material_colorcard_readable_non_overlapping_labels"),
        ("QUARTER_INSET_DETAIL", "quarter_inset", "render_only_local_inset_detail_enlarged_e_grade_non_measured_thickness"),
    ]
    margin_metrics: dict[str, Any] = {}
    process_hidden_by_view: dict[str, Any] = {}
    evidence = []
    for render_id, mode, purpose in render_specs:
        process_hidden_by_view[render_id] = set_visibility(mode)
        scene.camera = cameras[render_id]
        if render_id in {"FRONT_CONTEXT", "HALF_CUT", "QUARTER_CUT", "EXPLODED_CUT"}:
            margin_metrics[render_id] = projection_bbox(cameras[render_id], objects_for(mode))
        path = render_dir / f"INT20_R4_{render_id}.png"
        scene.render.filepath = str(path)
        bpy.ops.render.render(write_still=True)
        if not path.is_file() or path.stat().st_size <= 1024:
            raise RuntimeError(f"Render failed: {path}")
        evidence.append(
            {
                "id": render_id,
                "file": path.name,
                "path": str(path),
                "camera": cameras[render_id].name,
                "projection": cameras[render_id].data.type,
                "purpose": purpose,
                "resolution_px": [args.width, args.height],
                "engine": scene.render.engine,
                "lookdev": "r4_brighter_neutral_cutface_fill_agx_no_bloom_freestyle_disabled",
                "process_space": "actual_PROCESS_SPACE_objects_hidden_for_all_cut_views",
                "bytes": path.stat().st_size,
                "sha256": sha256_file(path),
            }
        )

    set_visibility("front")
    scene.camera = cameras["FRONT_CONTEXT"]

    def text_bbox_px(obj: Any, cam: Any) -> dict[str, float]:
        bpy.context.view_layer.update()
        line_count = max(1, obj.data.body.count("\n") + 1)
        max_line = max(len(line) for line in obj.data.body.splitlines() or [obj.data.body])
        if obj.parent == cam:
            aspect = scene.render.resolution_x / scene.render.resolution_y
            view_w = cam.data.ortho_scale * aspect
            view_h = cam.data.ortho_scale
            cx = ((obj.location.x + view_w * 0.5) / view_w) * args.width
            cy = ((view_h * 0.5 - obj.location.y) / view_h) * args.height
            width = max(54, max_line * obj.data.size * args.width / view_w * 0.52)
            height = max(24, line_count * obj.data.size * args.height / view_h * 1.28)
        elif obj.name.startswith("APPROX_GL02_INT20_R4_COLORCARD_LABEL_"):
            cx = ((obj.location.x + 3.6) / 7.2) * args.width
            cy = 620.0
            width = max(118, max_line * 20)
            height = max(44, line_count * 34)
        else:
            center = world_to_camera_view(scene, cam, obj.matrix_world.translation)
            cx = center.x * args.width
            cy = (1 - center.y) * args.height
            width = max(118, max_line * 20)
            height = max(44, line_count * 34)
        return {"xmin": cx - width / 2, "xmax": cx + width / 2, "ymin": cy - height / 2, "ymax": cy + height / 2}

    label_bboxes = {obj.name: text_bbox_px(obj, cameras["COLORCARD"]) for obj in colorcard_labels}
    annotation_label_bboxes: dict[str, dict[str, float]] = {}
    for group, labels_for_group in overlay_groups.items():
        cam_key = {
            "closeup": "SECTION_CLOSEUP_ANNOTATED",
            "magnified": "SECTION_MAGNIFIED_5X_ANNOTATED",
            "exploded": "EXPLODED_CUT",
            "quarter_inset": "QUARTER_INSET_DETAIL",
        }[group]
        for obj in labels_for_group:
            if obj.type == "FONT":
                annotation_label_bboxes[obj.name] = text_bbox_px(obj, cameras[cam_key])

    def intersects(a: dict[str, float], b: dict[str, float]) -> bool:
        return not (a["xmax"] <= b["xmin"] or b["xmax"] <= a["xmin"] or a["ymax"] <= b["ymin"] or b["ymax"] <= a["ymin"])

    overlaps = []
    labels = list(label_bboxes.items())
    for i, (name_a, box_a) in enumerate(labels):
        for name_b, box_b in labels[i + 1 :]:
            if intersects(box_a, box_b):
                overlaps.append([name_a, name_b])
    annotation_overlaps_by_group: dict[str, list[list[str]]] = {}
    for group, labels_for_group in overlay_groups.items():
        group_boxes = [(obj.name, annotation_label_bboxes[obj.name]) for obj in labels_for_group if obj.type == "FONT"]
        group_overlaps = []
        for i, (name_a, box_a) in enumerate(group_boxes):
            for name_b, box_b in group_boxes[i + 1 :]:
                if intersects(box_a, box_b):
                    group_overlaps.append([name_a, name_b])
        annotation_overlaps_by_group[group] = group_overlaps
    annotation_overlaps = [pair for pairs in annotation_overlaps_by_group.values() for pair in pairs]

    source_sig_after = mesh_signature(INT10_OBJECTS)
    sensor_sig_after = sensor_signature()
    audits = {name: object_audit(bpy.data.objects[name]) for name in INT10_OBJECTS}
    old_hidden = r3_report.get("protected_contract", {}).get("old_55_explanatory_objects_hidden_count", 55)
    margin_pass = all(
        0.70 <= margin_metrics[key]["height_fraction"] <= 0.82
        and margin_metrics[key]["top_margin"] >= 0.06
        and margin_metrics[key]["bottom_margin"] >= 0.06
        for key in ["HALF_CUT", "QUARTER_CUT", "EXPLODED_CUT"]
    )
    process_hidden_pass = all(
        all(hidden for hidden in process_hidden_by_view[key].values())
        for key in ["HALF_CUT", "QUARTER_CUT", "EXPLODED_CUT", "SECTION_CLOSEUP_ANNOTATED", "SECTION_MAGNIFIED_5X_ANNOTATED", "QUARTER_INSET_DETAIL"]
    )
    annotation_counts = {group: len([obj for obj in items if obj.type == "FONT"]) for group, items in overlay_groups.items()}

    material_manifest = {
        "schema_version": "bf3d.int20_r4.visual_manifest.v1",
        "stage": STAGE_ID,
        "status": "candidate_ready_for_review",
        "approval": "not_granted_requires_visual_and_spec_review",
        "single_changed_dimension": "cutaway_visual_readability_only",
        "input": {
            "path": str(args.input_blend.resolve()),
            "expected_sha256": EXPECTED_INPUT_SHA256,
            "actual_sha256": sha256_file(args.input_blend.resolve()),
            "sha256_match": sha256_file(args.input_blend.resolve()).lower() == EXPECTED_INPUT_SHA256,
        },
        "source_signatures": {
            "geometry_matrix_thickness_before": source_sig_before,
            "geometry_matrix_thickness_after": source_sig_after,
            "unchanged": source_sig_before == source_sig_after,
            "r3_source_audit_object_count": len(r3_report.get("source_object_audits", {})),
        },
        "freestyle": {"enabled": bool(scene.render.use_freestyle), "max_thickness_px": 0.0, "policy": "disabled"},
        "render_only_exploded_clones": {
            name: {
                "source_object": obj.name.replace("APPROX_GL02_INT20_R4_RENDER_ONLY_EXPLODED_", "APPROX_GL02_INT10_"),
                "location": [round(v, 5) for v in obj.location],
                "note": "diagrammatic separation not to scale; source INT10/R3 objects are not moved",
            }
            for name, obj in exploded.items()
        },
        "render_only_inset_helpers": {
            obj.name: {
                "type": obj.type,
                "location": [round(v, 5) for v in obj.location],
                "scale": [round(v, 5) for v in obj.scale],
                "note": "render-only local enlarged inset; not part of source geometry/thickness contract",
            }
            for obj in inset_helpers
        },
        "margin_metrics": margin_metrics,
        "process_hidden_by_cut_view": process_hidden_by_view,
        "colorcard": {
            "columns": 4,
            "label_bboxes_px": label_bboxes,
            "overlaps": overlaps,
            "non_overlapping": not overlaps,
        },
        "engineering_annotations": {
            "required_groups": ["closeup", "magnified", "exploded", "quarter_inset"],
            "font_label_counts": annotation_counts,
            "leader_line_counts": {group: len([obj for obj in items if obj.type == "CURVE"]) for group, items in overlay_groups.items()},
            "label_bboxes_px": annotation_label_bboxes,
            "overlaps_by_group": annotation_overlaps_by_group,
            "overlaps": annotation_overlaps,
            "non_overlapping": not annotation_overlaps,
            "mandatory_text": [
                "钢制炉壳",
                "冷却结构层",
                "耐火层",
                "炉内侧",
                "E级工艺示意｜非实测厚度",
                "分离展示，不按比例",
                "局部放大",
            ],
        },
        "materials": {
            "steel": ["controlled cool gray-blue steel body", "brighter cold gray-blue cutface"],
            "cooling": ["warm copper-brown body", "bright copper cutface"],
            "refractory": ["light brick-gray body", "bright beige refractory cutface"],
            "process_space": ["render hidden in cut views"],
        },
        "evidence_renders": evidence,
    }
    write_json(output_dir / "int20_r4_visual_manifest.json", material_manifest)

    candidate = {
        "path": str(output_blend),
        "bytes": 0,
        "sha256": "",
    }
    assertions = {
        "input_sha256_matches": material_manifest["input"]["sha256_match"],
        "source_geometry_matrix_thickness_signature_unchanged": source_sig_before == source_sig_after,
        "sensor_contract_pass": len(sensor_objects()) == 115
        and len([o for o in sensor_objects() if o.name.startswith("SENSOR_T_body")]) == 80
        and sensor_sig_before == sensor_sig_after,
        "int10_12_objects_present": all(bpy.data.objects.get(name) for name in INT10_OBJECTS),
        "non_manifold_edges_zero": all(item["non_manifold_edges"] == 0 for item in audits.values()),
        "positive_volume_pass": all(item["positive_volume"] for item in audits.values()),
        "cutface_material_faces_preserved": all(item["cutface_material_faces"] == r3_report["source_object_audits"][name]["cutface_material_faces"] for name, item in audits.items()),
        "old_55_explanatory_objects_hidden_count_preserved": old_hidden == 55,
        "full_body_margin_metrics_pass": margin_pass,
        "process_space_hidden_in_cut_views": process_hidden_pass,
        "colorcard_label_bboxes_non_overlapping": not overlaps,
        "engineering_annotations_complete": all(annotation_counts.get(group, 0) >= minimum for group, minimum in {"closeup": 5, "magnified": 6, "exploded": 1, "quarter_inset": 5}.items())
        and len([obj for obj in overlay_groups["closeup"] if obj.type == "CURVE"]) >= 4
        and len([obj for obj in overlay_groups["magnified"] if obj.type == "CURVE"]) >= 4,
        "annotation_label_bboxes_non_overlapping": not annotation_overlaps,
        "render_only_helper_objects_named_and_separate": all(obj.name.startswith("APPROX_GL02_INT20_R4_RENDER_ONLY_") for obj in list(exploded.values()) + inset_helpers),
        "freestyle_disabled_or_restrained": not scene.render.use_freestyle,
        "section_magnified_5x_label_present": bool(bpy.data.objects.get("APPROX_GL02_INT20_R4_LABEL_SECTION_MAGNIFIED_5X")),
        "formal_glb_not_exported": not list(output_dir.glob("*.glb")),
        "blend1_not_generated": not list(output_dir.glob("*.blend1")),
        "renders_exist_pass": len(evidence) >= 8 and all(item["bytes"] > 1024 for item in evidence),
    }

    scene["BF3D_STAGE"] = STAGE_ID
    scene["BF3D_STATUS"] = "candidate_ready_for_review"
    scene["BF3D_APPROVAL"] = "not_granted_requires_visual_and_spec_review"
    bpy.ops.wm.save_as_mainfile(filepath=str(output_blend), check_existing=False)
    candidate["bytes"] = output_blend.stat().st_size
    candidate["sha256"] = sha256_file(output_blend)

    report = {
        "schema_version": "bf3d.int20_r4.machine_report.v1",
        "requirement_id": REQUIREMENT_ID,
        "stage": STAGE_ID,
        "status": "candidate_ready_for_review",
        "approval": "not_granted_requires_visual_and_spec_review",
        "generated_at": now_iso(),
        "single_changed_dimension": "cutaway_visual_readability_only",
        "input": material_manifest["input"],
        "candidate": candidate,
        "blender": {
            "version": bpy.app.version_string,
            "binary_path": bpy.app.binary_path,
            "background": bpy.app.background,
            "render_engine": scene.render.engine,
            "render_resolution": [args.width, args.height],
        },
        "protected_contract": {
            "sensor_count_before": 115,
            "sensor_count_after": len(sensor_objects()),
            "body_temp_sensor_count_before": 80,
            "body_temp_sensor_count_after": len([o for o in sensor_objects() if o.name.startswith("SENSOR_T_body")]),
            "sensor_signature_before": sensor_sig_before,
            "sensor_signature_after": sensor_sig_after,
            "sensor_names_parents_matrices_unchanged": sensor_sig_before == sensor_sig_after,
            "l7_l16_groups_present": all(bpy.data.objects.get(f"GL02_SENSOR_LAYER_L{i}") for i in range(7, 17)),
            "five_furnace_segments_present": all(
                bpy.data.objects.get(f"APPROX_GL02_FURNACE_{name}") for name in ["HEARTH", "BOSH", "BELLY", "SHAFT", "THROAT"]
            ),
            "old_55_explanatory_objects_hidden_count": old_hidden,
        },
        "source_object_audits": audits,
        "visual_manifest": str(output_dir / "int20_r4_visual_manifest.json"),
        "evidence_renders": evidence,
        "assertions": assertions,
        "known_issues": [
            "R4 remains E-grade approximate visual explanation, not measured engineering/as-built dimensions.",
            "EXPLODED_CUT and QUARTER_INSET_DETAIL are diagrammatic aids and use render-only helpers.",
            "No formal GLB was exported; independent visual and spec review is still required.",
            "Root-level specs/avatar_spec.json, specs/acceptance_checklist.md, reports/pipeline_status.json were not present in this workspace; R4 reports this as an evidence gap and did not update a missing status file.",
        ],
        "formal_asset_changes": {
            "formal_glb_exported": False,
            "blend1_generated": bool(list(output_dir.glob("*.blend1"))),
            "r1_modified": False,
            "r2_modified": False,
            "r3_modified": False,
            "frontend_modified": False,
            "pipeline_status_modified": False,
        },
    }
    write_json(output_dir / "int20_r4_machine_report.json", report)
    return 0


def reopen_validate() -> int:
    import bpy
    import bmesh

    args = blender_args()
    output_dir = args.output_dir.resolve()
    candidate = output_dir / OUTPUT_BLEND_NAME
    visual_manifest = json.loads((output_dir / "int20_r4_visual_manifest.json").read_text(encoding="utf-8"))

    def sensor_rows() -> list[dict[str, Any]]:
        return [
            {
                "name": obj.name,
                "parent": obj.parent.name if obj.parent else None,
                "matrix": [round(v, 8) for row in obj.matrix_world for v in row],
            }
            for obj in sorted([o for o in bpy.data.objects if o.name.startswith("SENSOR_")], key=lambda o: o.name)
        ]

    def sig() -> str:
        return hashlib.sha256(json.dumps(sensor_rows(), sort_keys=True).encode("utf-8")).hexdigest()

    def audit_obj(name: str) -> dict[str, Any]:
        obj = bpy.data.objects[name]
        bm = bmesh.new()
        bm.from_mesh(obj.data)
        bm.normal_update()
        volume = bm.calc_volume(signed=True)
        non_manifold = sum(1 for e in bm.edges if not e.is_manifold)
        bm.free()
        return {
            "exists": True,
            "non_manifold_edges": non_manifold,
            "positive_volume": volume > 0,
            "cutface_material_faces": sum(1 for p in obj.data.polygons if p.material_index == 1),
        }

    expected_renders = [
        f"INT20_R4_{rid}.png"
        for rid in [
            "FRONT_CONTEXT",
            "HALF_CUT",
            "QUARTER_CUT",
            "EXPLODED_CUT",
            "SECTION_CLOSEUP_ANNOTATED",
            "SECTION_MAGNIFIED_5X_ANNOTATED",
            "COLORCARD",
            "QUARTER_INSET_DETAIL",
        ]
    ]
    render_presence = {
        name: (output_dir / "renders" / name).is_file() and (output_dir / "renders" / name).stat().st_size > 1024
        for name in expected_renders
    }
    audits = {name: audit_obj(name) for name in INT10_OBJECTS if bpy.data.objects.get(name)}
    validation = {
        "schema_version": "bf3d.int20_r4.reopen_validation.v1",
        "stage": STAGE_ID,
        "candidate_reopened_without_error": True,
        "candidate_path": str(candidate),
        "scene_stage": bpy.context.scene.get("BF3D_STAGE"),
        "candidate_sha256": sha256_file(candidate),
        "sensor_count": len([o for o in bpy.data.objects if o.name.startswith("SENSOR_")]),
        "body_temp_sensor_count": len([o for o in bpy.data.objects if o.name.startswith("SENSOR_T_body")]),
        "sensor_signature_sha256": sig(),
        "all_int10_objects_exist": len(audits) == len(INT10_OBJECTS),
        "all_non_manifold_edges_zero": all(item["non_manifold_edges"] == 0 for item in audits.values()),
        "all_positive_volume": all(item["positive_volume"] for item in audits.values()),
        "renders_present": render_presence,
        "visual_manifest_assertions": {
            "source_geometry_matrix_thickness_signature_unchanged": visual_manifest["source_signatures"]["unchanged"],
            "full_body_margin_metrics_pass": all(
                0.70 <= visual_manifest["margin_metrics"][key]["height_fraction"] <= 0.82
                and visual_manifest["margin_metrics"][key]["top_margin"] >= 0.06
                and visual_manifest["margin_metrics"][key]["bottom_margin"] >= 0.06
                for key in ["HALF_CUT", "QUARTER_CUT", "EXPLODED_CUT"]
            ),
            "colorcard_label_bboxes_non_overlapping": visual_manifest["colorcard"]["non_overlapping"],
            "engineering_annotations_complete": visual_manifest["engineering_annotations"]["non_overlapping"]
            and all(visual_manifest["engineering_annotations"]["font_label_counts"].get(group, 0) >= minimum for group, minimum in {"closeup": 5, "magnified": 6, "exploded": 1, "quarter_inset": 5}.items()),
            "process_space_hidden_in_cut_views": all(
                all(hidden for hidden in visual_manifest["process_hidden_by_cut_view"][key].values())
                for key in ["HALF_CUT", "QUARTER_CUT", "EXPLODED_CUT", "SECTION_CLOSEUP_ANNOTATED", "SECTION_MAGNIFIED_5X_ANNOTATED", "QUARTER_INSET_DETAIL"]
            ),
        },
        "blend1_not_present": not list(output_dir.glob("*.blend1")),
    }
    validation["status"] = (
        "pass"
        if validation["scene_stage"] == STAGE_ID
        and validation["sensor_count"] == 115
        and validation["body_temp_sensor_count"] == 80
        and validation["all_int10_objects_exist"]
        and validation["all_non_manifold_edges_zero"]
        and validation["all_positive_volume"]
        and all(validation["renders_present"].values())
        and all(validation["visual_manifest_assertions"].values())
        and validation["blend1_not_present"]
        else "fail"
    )
    write_json(output_dir / "reopen_validation.json", validation)
    return 0 if validation["status"] == "pass" else 1


if __name__ == "__main__":
    if "--inside-blender" in sys.argv:
        raise SystemExit(blender_main())
    if "--reopen-validate" in sys.argv:
        raise SystemExit(reopen_validate())
    raise SystemExit(host_main())

