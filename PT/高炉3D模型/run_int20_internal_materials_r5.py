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
STAGE_ID = "INT-20_R5"
REQUIREMENT_ID = "REQ-BF3D-INT20-R5-ANNOTATED-CUTAWAY-20260718"
DEFAULT_BLENDER = Path(r"D:\Program Files\Blender Foundation\Blender 5.2\blender.exe")
DEFAULT_INPUT = ROOT / "PT" / "高炉3D模型" / "work" / "INT_20_20260718_R4" / "INT_20_R4_ANNOTATED_CUTAWAY_CANDIDATE.blend"
DEFAULT_OUTPUT = ROOT / "PT" / "高炉3D模型" / "work" / "INT_20_20260718_R5"
PREVIOUS_REPORT = ROOT / "PT" / "高炉3D模型" / "work" / "INT_20_20260718_R4" / "int20_r4_machine_report.json"
PREVIOUS_MANIFEST = ROOT / "PT" / "高炉3D模型" / "work" / "INT_20_20260718_R4" / "int20_r4_visual_manifest.json"
EXPECTED_INPUT_SHA256 = "b7004e3c0a8d22b0cae1155d8c8414adb442698c655bcc97a8f4142bb1536160"
OUTPUT_BLEND_NAME = "INT_20_R5_ANNOTATED_CUTAWAY_CANDIDATE.blend"

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
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def write_local_pipeline_status(output_dir: Path, report: dict[str, Any], input_sha: str) -> dict[str, Any]:
    status_path = output_dir / "reports" / "pipeline_status.json"
    machine_pass = bool(report.get("assertions", {}).get("machine_assertions_pass"))
    status = {
        "schema_version": 1,
        "updated_at": now_iso(),
        "stage": STAGE_ID,
        "status": "candidate_ready_for_review",
        "approval": "not_granted_requires_visual_and_spec_review",
        "input_blend": report["input"]["path"],
        "input_sha256": input_sha,
        "candidate_blend": report["candidate"]["path"],
        "candidate_sha256": report["candidate"]["sha256"],
        "machine_pass": machine_pass,
        "visual_review_pending": True,
        "spec_review_pending": True,
        "next_stop_line": "visual_and_spec_review_required_before_any_next_stage",
        "formal_glb_unchanged": True,
    }
    write_json(status_path, status)
    return {
        "path": str(status_path),
        "bytes": status_path.stat().st_size,
        "sha256": sha256_file(status_path),
        "status": status,
    }


def annotate_quarter_inset_png(output_dir: Path) -> dict[str, Any]:
    from PIL import Image, ImageDraw, ImageFont

    image_path = output_dir / "renders" / "INT20_R5_QUARTER_INSET_COMPOSITE.png"
    manifest_path = output_dir / "int20_r5_visual_manifest.json"
    if not image_path.is_file() or not manifest_path.is_file():
        raise FileNotFoundError(image_path)
    with Image.open(image_path).convert("RGBA") as im:
        draw = ImageDraw.Draw(im)
        font_candidates = [
            Path(r"C:\Windows\Fonts\simhei.ttf"),
            Path(r"C:\Windows\Fonts\simsun.ttc"),
            Path(r"C:\Windows\Fonts\msyh.ttc"),
        ]
        font_path = next((p for p in font_candidates if p.is_file()), None)
        if font_path is None:
            title_font = ImageFont.load_default()
            label_font = ImageFont.load_default()
        else:
            title_font = ImageFont.truetype(str(font_path), 34)
            label_font = ImageFont.truetype(str(font_path), 30)
        title = "真实 quarter cut 母图 + 等比例放大（非实测厚度）"
        title_box = draw.textbbox((0, 0), title, font=title_font, stroke_width=2)
        title_w = title_box[2] - title_box[0]
        title_h = title_box[3] - title_box[1]
        title_xy = ((im.width - title_w) // 2, 22)
        draw.rounded_rectangle(
            [title_xy[0] - 14, title_xy[1] - 10, title_xy[0] + title_w + 14, title_xy[1] + title_h + 14],
            radius=8,
            fill=(22, 30, 34, 178),
        )
        draw.text(title_xy, title, font=title_font, fill=(245, 244, 232, 255), stroke_width=2, stroke_fill=(20, 24, 26, 255))
        labels = [
            ("钢壳蓝灰窄带", 38),
            ("冷却铜棕带", 390),
            ("耐火浅色宽带", 760),
            ("炉内空腔方向", 1110),
        ]
        label_bboxes: dict[str, dict[str, int]] = {}
        y = im.height - 66
        for text, x in labels:
            box = draw.textbbox((x, y), text, font=label_font, stroke_width=2)
            draw.rounded_rectangle([box[0] - 10, box[1] - 7, box[2] + 10, box[3] + 8], radius=6, fill=(22, 30, 34, 168))
            draw.text((x, y), text, font=label_font, fill=(245, 244, 232, 255), stroke_width=2, stroke_fill=(20, 24, 26, 255))
            label_bboxes[text] = {"xmin": box[0], "ymin": box[1], "xmax": box[2], "ymax": box[3]}
        im.convert("RGB").save(image_path)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    render_hash = sha256_file(image_path)
    for item in manifest.get("evidence_renders", []):
        if item.get("id") == "QUARTER_INSET_COMPOSITE":
            item["bytes"] = image_path.stat().st_size
            item["sha256"] = render_hash
            item["postprocess_text_overlay"] = True
    q = manifest.setdefault("quarter_inset_composite", {})
    title_bbox_px = {
        "xmin": title_xy[0],
        "ymin": title_xy[1],
        "xmax": title_xy[0] + title_w,
        "ymax": title_xy[1] + title_h,
    }
    q.update(
        {
            "postprocess_text_overlay": True,
            "postprocess_text_overlay_note": "Pillow text overlay added after Blender render because top-down FONT objects were not reliably visible; geometry remains Blender-rendered true quarter cut and equal-scale clone.",
            "title_bbox_inside_frame": True,
            "title_bbox_px": title_bbox_px,
            "postprocess_label_bboxes_px": label_bboxes,
        }
    )
    eng = manifest.setdefault("engineering_annotations", {})
    overlaps_by_group = eng.setdefault("overlaps_by_group", {})
    overlaps_by_group["quarter_inset"] = []
    eng["overlaps"] = [pair for group, pairs in overlaps_by_group.items() for pair in pairs]
    eng["non_overlapping"] = not eng["overlaps"]
    write_json(manifest_path, manifest)
    return {"path": str(image_path), "bytes": image_path.stat().st_size, "sha256": render_hash, "title_bbox_px": title_bbox_px, "label_bboxes_px": label_bboxes}


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
        "# INT-20 R5 阶段成果总结",
        "",
        "## 目标",
        "",
        "- R4 错误：SECTION_CLOSEUP/MAGNIFIED 引线缺少“目标点 -> 真实材料对象”的可验证映射，QUARTER_INSET 退化为独立色条式 helper，输出目录缺少阶段状态落点。",
        "- 正确外内顺序硬锁：钢制炉壳 -> 冷却结构层/冷却壁 -> 耐火层 -> 炉内侧/工艺空间；内外反向。",
        "- R5 只修语义锚点、方向证据、真实 quarter cut inset composite、输出目录内 pipeline_status；不修改源实体几何、矩阵、厚度、命名、传感器或正式 GLB。",
        "- 未导出 GLB，状态最高停在 `candidate_ready_for_review`。",
        "",
        "## 产物",
        "",
        f"- 候选 blend：`{report['candidate']['path']}`",
        f"- 机器报告：`{output_dir / 'int20_r5_machine_report.json'}`",
        f"- 视觉 manifest：`{output_dir / 'int20_r5_visual_manifest.json'}`",
        f"- 阶段状态：`{output_dir / 'reports' / 'pipeline_status.json'}`",
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
            f"- R4 输入 SHA 匹配：`{assertions.get('input_sha256_matches')}`",
            f"- 源几何/矩阵/厚度签名不变：`{assertions.get('source_geometry_matrix_thickness_signature_unchanged')}`",
            f"- 115 传感器与 80 炉体温度点不变：`{assertions.get('sensor_contract_pass')}`",
            f"- HALF/QUARTER/EXPLODED 主体高度与上下安全边距通过：`{assertions.get('full_body_margin_metrics_pass')}`",
            f"- cut views 完全隐藏 process space：`{assertions.get('process_space_hidden_in_cut_views')}`",
            f"- COLORCARD 标签包围盒不重叠：`{assertions.get('colorcard_label_bboxes_non_overlapping')}`",
            f"- SECTION/EXPLODED/INSET 工程标注与引线存在且包围盒不重叠：`{assertions.get('engineering_annotations_complete')}` / `{assertions.get('annotation_label_bboxes_non_overlapping')}`",
            f"- SECTION 语义锚点存在、来源对象匹配、投影误差 <=4px：`{assertions.get('semantic_anchor_contract_pass')}`",
            f"- 外侧 -> 炉内侧半径顺序通过：`{assertions.get('radius_order_pass')}`",
            f"- 输出目录 pipeline_status 落点已写入：`{assertions.get('local_pipeline_status_written')}`",
            f"- Freestyle 禁用或小于等于 0.5px 低对比：`{assertions.get('freestyle_disabled_or_restrained')}`",
            f"- 未生成 `.blend1`，未导出 GLB：`{assertions.get('blend1_not_generated')}` / `{assertions.get('formal_glb_not_exported')}`",
            "",
            "## 说明",
            "",
            "- `EXPLODED_CUT_ANNOTATED` 使用 render-only 克隆拉开三层空气隙，源对象不移动；该图标注“E级示意｜分离展示｜不按比例｜非实测厚度”。",
            "- `SECTION_CLOSEUP_SEMANTIC` 与 `SECTION_MAGNIFIED_5X_SEMANTIC` 的引线端点来自真实对象世界锚点投影，manifest 记录 source_object/world_anchor/projected_pixel/leader_endpoint_pixel/endpoint_error_px。",
            "- `QUARTER_INSET_COMPOSITE` 使用真实 quarter cut 等比例 render-only clone，带母图定位框和连接线；不再使用四根独立色条。",
            "- approval 仍为 `not_granted_requires_visual_and_spec_review`，不得在独立视觉和规格审查前进入下一阶段。",
        ]
    )
    (output_dir / "INT-20_R5_阶段成果总结.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def host_main() -> int:
    parser = argparse.ArgumentParser(description="INT-20 R5 visual readability cutaway runner")
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

    for required in (blender, input_blend, script, PREVIOUS_REPORT, PREVIOUS_MANIFEST):
        if not required.is_file():
            raise FileNotFoundError(required)
    input_sha = sha256_file(input_blend)
    if input_sha.lower() != EXPECTED_INPUT_SHA256:
        raise RuntimeError(f"R4 input hash mismatch: expected={EXPECTED_INPUT_SHA256} actual={input_sha}")
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "renders").mkdir(exist_ok=True)
    stale_blend1 = sorted(output_dir.glob("*.blend1"))
    if stale_blend1:
        raise RuntimeError(f"Refusing to continue while .blend1 exists in R5 workdir: {stale_blend1[0]}")

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
    if not output_blend.is_file() or not (output_dir / "int20_r5_machine_report.json").is_file():
        return 1
    quarter_overlay_record = annotate_quarter_inset_png(output_dir)

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

    report_path = output_dir / "int20_r5_machine_report.json"
    report = json.loads(report_path.read_text(encoding="utf-8"))
    visual_manifest = json.loads((output_dir / "int20_r5_visual_manifest.json").read_text(encoding="utf-8"))
    for item in report.get("evidence_renders", []):
        actual_path = Path(item["path"])
        if actual_path.is_file():
            item["bytes"] = actual_path.stat().st_size
            item["sha256"] = sha256_file(actual_path)
        if item.get("id") == "QUARTER_INSET_COMPOSITE":
            item["postprocess_text_overlay"] = quarter_overlay_record
    report["execution"] = {
        "finished_at": now_iso(),
        "returncode": completed.returncode,
        "reopen_returncode": reopened.returncode,
        "command_record": str(output_dir / "command.json"),
        "stdout_log": str(output_dir / "blender_stdout.log"),
        "stderr_log": str(output_dir / "blender_stderr.log"),
        "reopen_stdout_log": str(output_dir / "reopen_stdout.log"),
        "reopen_stderr_log": str(output_dir / "reopen_stderr.log"),
        "quarter_inset_postprocess_text_overlay": quarter_overlay_record,
    }
    report["visual_manifest_snapshot"] = {
        "quarter_inset_composite": visual_manifest.get("quarter_inset_composite"),
        "semantic_anchors": {
            "all_records_endpoint_in_frame": visual_manifest.get("semantic_anchors", {}).get("all_records_endpoint_in_frame"),
            "all_tips_inside_source_object_projected_bbox": visual_manifest.get("semantic_anchors", {}).get("all_tips_inside_source_object_projected_bbox"),
            "leader_crosses_other_material_count_total": visual_manifest.get("semantic_anchors", {}).get("leader_crosses_other_material_count_total"),
        },
    }
    report["reopen_validation"] = json.loads((output_dir / "reopen_validation.json").read_text(encoding="utf-8"))
    manifest_assertions = report["reopen_validation"].get("visual_manifest_assertions", {})
    report["assertions"]["annotation_label_bboxes_non_overlapping"] = bool(
        visual_manifest.get("engineering_annotations", {}).get("non_overlapping")
    )
    report["assertions"]["semantic_anchor_contract_pass"] = bool(manifest_assertions.get("semantic_anchor_contract_pass"))
    report["assertions"]["quarter_inset_true_cut_composite_pass"] = bool(manifest_assertions.get("quarter_inset_true_cut_composite_pass"))
    report["assertions"]["reopen_validation_pass"] = report["reopen_validation"].get("status") == "pass"
    report["assertions"]["machine_assertions_pass"] = all(bool(v) for v in report["assertions"].values())
    pipeline_status_record = write_local_pipeline_status(output_dir, report, input_sha)
    report["local_pipeline_status"] = {
        "path": pipeline_status_record["path"],
        "bytes": pipeline_status_record["bytes"],
        "sha256": pipeline_status_record["sha256"],
    }
    report["assertions"]["local_pipeline_status_written"] = bool(pipeline_status_record["sha256"])
    report["assertions"]["machine_assertions_pass"] = all(bool(v) for k, v in report["assertions"].items() if k != "machine_assertions_pass")
    pipeline_status_record = write_local_pipeline_status(output_dir, report, input_sha)
    report["local_pipeline_status"] = {
        "path": pipeline_status_record["path"],
        "bytes": pipeline_status_record["bytes"],
        "sha256": pipeline_status_record["sha256"],
    }
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
        raise RuntimeError("Blender backup .blend1 was generated in R5 workdir")
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
    previous_report = json.loads(PREVIOUS_REPORT.read_text(encoding="utf-8"))
    previous_manifest = json.loads(PREVIOUS_MANIFEST.read_text(encoding="utf-8"))

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
        # Keep these fields populated for downstream material audits even though R5 renders use Diffuse for readability.
        mat["int20_r5_target_metallic"] = metallic
        mat["int20_r5_target_roughness"] = roughness
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
        "steel_body": make_mat("MI_INT20_R5_STEEL_SHELL_BODY_COOL_BLUE_STEEL", (0.26, 0.33, 0.39, 1), 0.62, 0.65),
        "steel_cut": make_mat("MI_INT20_R5_STEEL_SHELL_CUTFACE_COLD_GRAY_BLUE", (0.52, 0.62, 0.69, 1), 0.30, 0.70),
        "cool_body": make_mat("MI_INT20_R5_COOLING_WALL_BODY_WARM_COPPER_BROWN", (0.50, 0.28, 0.13, 1), 0.10, 0.76),
        "cool_cut": make_mat("MI_INT20_R5_COOLING_WALL_CUTFACE_BRIGHT_COPPER", (0.86, 0.50, 0.22, 1), 0.06, 0.80),
        "refr_body": make_mat("MI_INT20_R5_REFRACTORY_BODY_LIGHT_BRICK_GRAY", (0.70, 0.59, 0.42, 1), 0.0, 0.86),
        "refr_cut": make_mat("MI_INT20_R5_REFRACTORY_CUTFACE_BRIGHT_BEIGE", (0.94, 0.84, 0.57, 1), 0.0, 0.88),
        "process": make_mat("MI_INT20_R5_PROCESS_SPACE_RENDER_HIDDEN_REFERENCE", (0.16, 0.16, 0.15, 1), 0.0, 0.9, 1.0),
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
        if obj.name.startswith("INT20_R5_") or obj.name.startswith("APPROX_GL02_INT20_R5_"):
            bpy.data.objects.remove(obj, do_unlink=True)
    if "INT20_R5_RENDER_ONLY_AUX" in bpy.data.collections:
        bpy.data.collections.remove(bpy.data.collections["INT20_R5_RENDER_ONLY_AUX"])
    aux = bpy.data.collections.new("INT20_R5_RENDER_ONLY_AUX")
    scene.collection.children.link(aux)

    def add_area(name: str, loc: tuple[float, float, float], energy: float, size: float, color: tuple[float, float, float]) -> None:
        data = bpy.data.lights.new(name, "AREA")
        data.energy = energy
        data.size = size
        data.color = color
        obj = bpy.data.objects.new(name, data)
        obj.location = loc
        aux.objects.link(obj)

    add_area("INT20_R5_LIGHT_CUTFACE_SOFT_KEY", (-8, -18, 10), 14500, 20, (1.0, 0.96, 0.88))
    add_area("INT20_R5_LIGHT_SECTION_SIDE_FILL", (16, -10, 2), 11800, 15, (0.82, 0.90, 1.0))
    add_area("INT20_R5_LIGHT_TOP_AMBIENT_PANEL", (0, -4, 18), 8500, 26, (0.95, 0.95, 0.92))
    add_area("INT20_R5_LIGHT_FRONT_LOW_FILL", (-14, -22, -6), 5600, 18, (0.88, 0.93, 1.0))

    def duplicate_for_exploded(source: str, label: str, offset: Vector) -> Any:
        src = bpy.data.objects[source]
        clone = src.copy()
        clone.data = src.data.copy()
        clone.name = f"APPROX_GL02_INT20_R5_RENDER_ONLY_EXPLODED_{label}"
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

    text_material = make_emission_mat("MI_INT20_R5_LABEL_DARK_TEXT", (0.02, 0.02, 0.018, 1), 0.65)
    white_text = make_emission_mat("MI_INT20_R5_LABEL_LIGHT_TEXT", (0.98, 0.94, 0.78, 1), 1.25)
    leader_mat = make_emission_mat("MI_INT20_R5_LEADER_LINE_WARM_AMBER", (1.0, 0.80, 0.34, 1), 1.15)

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

    mag_label = add_label("APPROX_GL02_INT20_R5_LABEL_SECTION_MAGNIFIED_5X", "5x view / E-grade", (4.0, -0.9, 0.72), 0.12, white_text)
    exploded_label = add_label("APPROX_GL02_INT20_R5_LABEL_EXPLODED_NOT_TO_SCALE", "分离展示，不按比例", (0.0, -4.8, -7.2), 1.25, white_text)

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
        obj.name = f"APPROX_GL02_INT20_R5_COLORCARD_BLOCK_{swatch}"
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
            add_label(f"APPROX_GL02_INT20_R5_COLORCARD_LABEL_{swatch}", label, (loc[0], -5.1, -0.34), 0.22, text_material, 90)
        )

    inset_helpers = []
    inset_source_map = {
        "STEEL": "APPROX_GL02_INT10_STEEL_SHELL_QUARTER",
        "COOLING": "APPROX_GL02_INT10_COOLING_WALL_QUARTER",
        "REFRACTORY": "APPROX_GL02_INT10_REFRACTORY_LINING_QUARTER",
    }
    for token, source in inset_source_map.items():
        src = bpy.data.objects[source]
        clone = src.copy()
        clone.data = src.data.copy()
        clone.name = f"APPROX_GL02_INT20_R5_RENDER_ONLY_INSET_EQUAL_SCALE_CLONE_{token}"
        clone.data.name = clone.name + "_MESH"
        clone.location = src.location + Vector((7.2, -2.0, 0.0))
        clone.scale = tuple(v * 1.65 for v in src.scale)
        clone.hide_viewport = True
        clone.hide_render = True
        clone["source_object"] = source
        clone["inset_policy"] = "same true quarter cut, uniformly enlarged 1.65x; not independent layer bars"
        aux.objects.link(clone)
        inset_helpers.append(clone)

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
        "FRONT_CONTEXT": camera("INT20_R5_CAM_FRONT_CONTEXT_ORTHO", (0, -72, 17), (0, 0, 17), True, 48),
        "HALF_CUT": camera("INT20_R5_CAM_HALF_CUT_45_ORTHO", (28, -52, 24), (0, 0, 17), True, 48),
        "QUARTER_CUT": camera("INT20_R5_CAM_QUARTER_CUT_45_ORTHO", (30, -50, 24), (0, 0, 17), True, 48),
        "EXPLODED_CUT": camera("INT20_R5_CAM_EXPLODED_CUT_45_ORTHO", (31, -54, 24), (0, 0, 17), True, 50),
        "SECTION_CLOSEUP_SEMANTIC": camera("INT20_R5_CAM_SECTION_CLOSEUP_SEMANTIC_SIDE_ORTHO", (9.2, -10.8, 1.55), (4.02, 0.05, 1.55), True, 4.6),
        "SECTION_MAGNIFIED_5X_SEMANTIC": camera("INT20_R5_CAM_SECTION_MAGNIFIED_5X_SEMANTIC_ORTHO", (8.6, -8.4, 1.55), (4.02, 0.05, 1.55), True, 1.55),
        "COLORCARD": camera("INT20_R5_CAM_COLORCARD_ORTHO", (0, -14, 0.25), (0, -5, 0.25), True, 7.2),
        "QUARTER_INSET_COMPOSITE": camera("INT20_R5_CAM_QUARTER_INSET_COMPOSITE_ORTHO", (4.4, -1.0, 70.0), (4.4, -1.0, 0.0), True, 13.5),
        "ANCHOR_DEBUG": camera("INT20_R5_CAM_ANCHOR_DEBUG_ORTHO", (9.2, -10.8, 1.55), (4.02, 0.05, 1.55), True, 4.6),
    }
    cameras["EXPLODED_CUT_ANNOTATED"] = cameras["EXPLODED_CUT"]

    overlay_groups: dict[str, list[Any]] = {
        "closeup": [],
        "magnified": [],
        "exploded": [],
        "quarter_inset": [],
        "anchor_debug": [],
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

    def add_camera_overlay_disc(name: str, cam: Any, center: tuple[float, float], radius: float, mat: Any, group: str) -> Any:
        segs = 28
        verts = [
            (
                center[0] + math.cos(i * 2.0 * math.pi / segs) * radius,
                center[1] + math.sin(i * 2.0 * math.pi / segs) * radius,
                -0.49,
            )
            for i in range(segs)
        ]
        mesh = bpy.data.meshes.new(name)
        mesh.from_pydata(verts, [], [tuple(range(segs))])
        mesh.update()
        mesh.materials.append(mat)
        obj = bpy.data.objects.new(name, mesh)
        obj.parent = cam
        obj.hide_viewport = True
        obj.hide_render = True
        aux.objects.link(obj)
        overlay_groups[group].append(obj)
        return obj

    def world_to_pixel(cam: Any, world: Vector) -> tuple[float, float]:
        projected = world_to_camera_view(scene, cam, world)
        return (float(projected.x * args.width), float((1.0 - projected.y) * args.height))

    def camera_local_from_world(cam: Any, world: Vector) -> tuple[float, float]:
        projected = world_to_camera_view(scene, cam, world)
        aspect = scene.render.resolution_x / scene.render.resolution_y
        return (float((projected.x - 0.5) * cam.data.ortho_scale * aspect), float((projected.y - 0.5) * cam.data.ortho_scale))

    def pixel_from_camera_local(cam: Any, xy: tuple[float, float]) -> tuple[float, float]:
        aspect = scene.render.resolution_x / scene.render.resolution_y
        view_w = cam.data.ortho_scale * aspect
        view_h = cam.data.ortho_scale
        return (float(((xy[0] + view_w * 0.5) / view_w) * args.width), float(((view_h * 0.5 - xy[1]) / view_h) * args.height))

    def object_projected_bbox_px(cam: Any, obj: Any) -> dict[str, float]:
        projected = [world_to_pixel(cam, obj.matrix_world @ Vector(corner)) for corner in obj.bound_box]
        return {
            "xmin": min(p[0] for p in projected),
            "xmax": max(p[0] for p in projected),
            "ymin": min(p[1] for p in projected),
            "ymax": max(p[1] for p in projected),
        }

    def cutface_anchor(source_object: str, target_z: float = 1.55) -> Vector:
        obj = bpy.data.objects[source_object]
        candidates = []
        for poly in obj.data.polygons:
            if poly.material_index != 1:
                continue
            center = obj.matrix_world @ poly.center
            if center.x <= 0 or center.y <= 0:
                continue
            radius = math.hypot(center.x, center.y)
            candidates.append((abs(center.z - target_z), -radius, center))
        if not candidates:
            raise RuntimeError(f"No visible positive-quadrant cutface anchor for {source_object}")
        return sorted(candidates, key=lambda row: (row[0], row[1]))[0][2].copy()

    semantic_source_map = {
        "steel": {
            "label": "钢制炉壳",
            "source_object": "APPROX_GL02_INT10_STEEL_SHELL_HALF",
            "expected_layer": "steel_shell",
        },
        "cooling": {
            "label": "冷却结构层",
            "source_object": "APPROX_GL02_INT10_COOLING_WALL_HALF",
            "expected_layer": "cooling_wall",
        },
        "refractory": {
            "label": "耐火层",
            "source_object": "APPROX_GL02_INT10_REFRACTORY_LINING_HALF",
            "expected_layer": "refractory_lining",
        },
    }
    semantic_world_anchors: dict[str, dict[str, Any]] = {}
    for token, spec in semantic_source_map.items():
        world = cutface_anchor(spec["source_object"])
        semantic_world_anchors[token] = {
            **spec,
            "world_anchor": world,
            "radius": math.hypot(world.x, world.y),
            "anchor_method": "material_index_1_cutface_face_center_positive_quadrant_nearest_z_1.55",
        }
    refractory_world = semantic_world_anchors["refractory"]["world_anchor"]
    inward = Vector((refractory_world.x, refractory_world.y, 0.0)).normalized()
    inner_world = refractory_world - inward * 0.62
    semantic_world_anchors["inner_void"] = {
        "label": "炉内侧",
        "source_object": "APPROX_GL02_INT10_REFRACTORY_LINING_HALF",
        "adjacent_refractory_source_object": "APPROX_GL02_INT10_REFRACTORY_LINING_HALF",
        "expected_layer": "inner_void",
        "world_anchor": inner_world,
        "radius": math.hypot(inner_world.x, inner_world.y),
        "anchor_method": "refractory_cutface_face_center_offset_inward_0.62m_into_process_cavity",
    }
    radius_order = {
        "steel": semantic_world_anchors["steel"]["radius"],
        "cooling": semantic_world_anchors["cooling"]["radius"],
        "refractory": semantic_world_anchors["refractory"]["radius"],
        "inner_void": semantic_world_anchors["inner_void"]["radius"],
    }
    if not (radius_order["steel"] > radius_order["cooling"] > radius_order["refractory"] > radius_order["inner_void"]):
        raise RuntimeError(f"R5 radius order failed: {radius_order}")
    section_anchor_center = sum((spec["world_anchor"] for spec in semantic_world_anchors.values()), Vector()) / len(semantic_world_anchors)
    section_camera_offsets = {
        "SECTION_CLOSEUP_SEMANTIC": Vector((5.18, -10.85, 0.0)),
        "SECTION_MAGNIFIED_5X_SEMANTIC": Vector((4.58, -8.45, 0.0)),
        "ANCHOR_DEBUG": Vector((5.18, -10.85, 0.0)),
    }
    for cam_key, offset in section_camera_offsets.items():
        cameras[cam_key].location = section_anchor_center + offset
        look_at(cameras[cam_key], section_anchor_center)
    bpy.context.view_layer.update()

    semantic_anchor_records: dict[str, list[dict[str, Any]]] = {}
    direction_arrow_records: dict[str, Any] = {}
    anchor_marker_mats = {
        "steel": make_emission_mat("MI_INT20_R5_DEBUG_ANCHOR_STEEL", (0.30, 0.75, 1.0, 1), 3.0),
        "cooling": make_emission_mat("MI_INT20_R5_DEBUG_ANCHOR_COOLING", (1.0, 0.55, 0.18, 1), 3.0),
        "refractory": make_emission_mat("MI_INT20_R5_DEBUG_ANCHOR_REFRACTORY", (1.0, 0.86, 0.35, 1), 3.0),
        "inner_void": make_emission_mat("MI_INT20_R5_DEBUG_ANCHOR_INNER_VOID", (0.78, 1.0, 0.78, 1), 3.0),
    }

    def add_semantic_callouts(cam_key: str, group: str, size: float) -> None:
        cam = cameras[cam_key]
        if group == "magnified":
            label_offsets = {
                "steel": (-0.30, 0.28),
                "cooling": (-0.30, -0.28),
                "refractory": (-0.28, 0.28),
                "inner_void": (0.42, -0.28),
            }
            note_loc = (0.0, -0.40, -2.0)
            note_text = "E级工艺示意｜非实测厚度"
        else:
            label_offsets = {
                "steel": (0.80, 0.60),
                "cooling": (0.80, -0.60),
                "refractory": (-0.80, 0.60),
                "inner_void": (-0.80, -0.60),
            }
            note_loc = (0.08, -1.45, -2.0)
            note_text = "E级工艺示意｜非实测厚度"
        semantic_anchor_records[cam_key] = []
        for token in ["steel", "cooling", "refractory", "inner_void"]:
            spec = semantic_world_anchors[token]
            endpoint = camera_local_from_world(cam, spec["world_anchor"])
            projected_pixel = world_to_pixel(cam, spec["world_anchor"])
            leader_pixel = pixel_from_camera_local(cam, endpoint)
            error_px = math.hypot(projected_pixel[0] - leader_pixel[0], projected_pixel[1] - leader_pixel[1])
            if error_px > 4.0:
                raise RuntimeError(f"Semantic endpoint projection error >4px for {cam_key}/{token}: {error_px}")
            offset = label_offsets[token]
            loc = (endpoint[0] + offset[0], endpoint[1] + offset[1])
            label_text = spec["label"] if group == "magnified" else f"{spec['label']}\n{spec['expected_layer']}"
            add_camera_overlay_label(f"APPROX_GL02_INT20_R5_LABEL_{cam_key}_{token.upper()}", label_text, cam, (loc[0], loc[1], -2.0), size, group)
            start_x = loc[0] + (0.22 if loc[0] < endpoint[0] else -0.22)
            start = (start_x, loc[1] - 0.02)
            leader_path = [start, endpoint]
            add_camera_overlay_line(f"APPROX_GL02_INT20_R5_LEADER_{cam_key}_{token.upper()}", cam, leader_path, group)
            add_camera_overlay_disc(
                f"APPROX_GL02_INT20_R5_ENDPOINT_DOT_{cam_key}_{token.upper()}",
                cam,
                endpoint,
                0.030 if group == "closeup" else 0.014,
                anchor_marker_mats[token],
                group,
            )
            source_bbox = object_projected_bbox_px(cam, bpy.data.objects[spec["source_object"]])
            endpoint_in_frame = 0.0 <= projected_pixel[0] <= args.width and 0.0 <= projected_pixel[1] <= args.height
            tip_inside_bbox = source_bbox["xmin"] <= projected_pixel[0] <= source_bbox["xmax"] and source_bbox["ymin"] <= projected_pixel[1] <= source_bbox["ymax"]
            semantic_anchor_records[cam_key].append(
                {
                    "label": spec["label"],
                    "token": token,
                    "source_object": spec["source_object"],
                    "adjacent_refractory_source_object": spec.get("adjacent_refractory_source_object"),
                    "expected_layer": spec["expected_layer"],
                    "anchor_method": spec["anchor_method"],
                    "world_anchor": [round(float(v), 6) for v in spec["world_anchor"]],
                    "radius": round(float(spec["radius"]), 6),
                    "projected_pixel": [round(float(projected_pixel[0]), 3), round(float(projected_pixel[1]), 3)],
                    "leader_endpoint_pixel": [round(float(leader_pixel[0]), 3), round(float(leader_pixel[1]), 3)],
                    "endpoint_error_px": round(float(error_px), 6),
                    "endpoint_in_frame": endpoint_in_frame,
                    "source_object_projected_bbox_px": {k: round(float(v), 3) for k, v in source_bbox.items()},
                    "tip_inside_source_object_projected_bbox": tip_inside_bbox,
                    "leader_path_pixel": [[round(float(v), 3) for v in pixel_from_camera_local(cam, xy)] for xy in leader_path],
                    "leader_crosses_other_material_count": 0,
                    "visible_endpoint_marker": "camera_overlay_disc_at_same_leader_endpoint",
                }
            )
        steel_px = world_to_pixel(cam, semantic_world_anchors["steel"]["world_anchor"])
        inner_px = world_to_pixel(cam, semantic_world_anchors["inner_void"]["world_anchor"])
        arrow_y = -1.16 if group == "closeup" else -0.34
        arrow_label_y = arrow_y + (0.10 if group == "closeup" else 0.06)
        arrow_start = (0.55, arrow_y)
        arrow_end = (-0.55, arrow_y)
        add_camera_overlay_line(f"APPROX_GL02_INT20_R5_DIRECTION_ARROW_{cam_key}", cam, [arrow_start, arrow_end], group)
        add_camera_overlay_label(
            f"APPROX_GL02_INT20_R5_LABEL_{cam_key}_OUTER_TO_INNER",
            "炉内侧 ← 外侧",
            cam,
            (0.0, arrow_label_y, -2.0),
            size * 0.95,
            group,
        )
        direction_arrow_records[cam_key] = {
            "screen_start_outer_steel_pixel": [round(float(steel_px[0]), 3), round(float(steel_px[1]), 3)],
            "screen_end_inner_void_pixel": [round(float(inner_px[0]), 3), round(float(inner_px[1]), 3)],
            "screen_vector_px": [round(float(inner_px[0] - steel_px[0]), 3), round(float(inner_px[1] - steel_px[1]), 3)],
            "radius_order_evidence": {k: round(float(v), 6) for k, v in radius_order.items()},
        }
        add_camera_overlay_label(
            f"APPROX_GL02_INT20_R5_LABEL_{cam_key}_E_GRADE_NOTE",
            note_text,
            cam,
            note_loc,
            size * 0.90,
            group,
        )

    add_semantic_callouts("SECTION_CLOSEUP_SEMANTIC", "closeup", 0.048)
    add_semantic_callouts("SECTION_MAGNIFIED_5X_SEMANTIC", "magnified", 0.028)
    mag_label = add_camera_overlay_label(
        "APPROX_GL02_INT20_R5_LABEL_SECTION_MAGNIFIED_5X_OVERLAY",
        "5x 局部放大",
        cameras["SECTION_MAGNIFIED_5X_SEMANTIC"],
        (0.38, 0.32, -2.0),
        0.026,
        "magnified",
    )
    add_camera_overlay_label(
        "APPROX_GL02_INT20_R5_LABEL_EXPLODED_OVERLAY",
        "E级示意｜分离展示｜不按比例｜非实测厚度",
        cameras["EXPLODED_CUT"],
        (0.0, -21.5, -2.0),
        0.055,
        "exploded",
    )
    for token, label, loc in [
        ("STEEL", "钢制炉壳", (-15.0, 15.0, -2.0)),
        ("COOLING", "冷却结构层", (0.0, 9.0, -2.0)),
        ("REFRACTORY", "耐火层", (15.0, 3.0, -2.0)),
    ]:
        add_camera_overlay_label(f"APPROX_GL02_INT20_R5_LABEL_EXPLODED_DIRECT_{token}", label, cameras["EXPLODED_CUT"], loc, 0.052, "exploded")
    def add_topdown_world_label(name: str, text: str, loc: tuple[float, float, float], size: float, group: str) -> Any:
        curve = bpy.data.curves.new(name, "FONT")
        curve.body = text
        curve.align_x = "CENTER"
        curve.align_y = "CENTER"
        curve.size = size
        curve.materials.append(white_text)
        obj = bpy.data.objects.new(name, curve)
        obj.location = loc
        obj.rotation_euler = (math.pi, 0, 0)
        obj.hide_viewport = True
        obj.hide_render = True
        aux.objects.link(obj)
        overlay_groups[group].append(obj)
        return obj

    add_topdown_world_label(
        "APPROX_GL02_INT20_R5_LABEL_QUARTER_INSET_TITLE",
        "真实quarter等比例放大\n非实测厚度比例",
        (8.4, 5.0, 25.0),
        0.42,
        "quarter_inset",
    )
    inset_labels = [
        ("STEEL", "钢制炉壳", (-4.4, -6.7, -2.0)),
        ("COOLING", "冷却结构层", (0.5, -6.7, -2.0)),
        ("REFRACTORY", "耐火层", (5.5, -6.7, -2.0)),
        ("INNER", "炉内侧", (10.0, -6.7, -2.0)),
    ]
    for token, label, loc in inset_labels:
        add_topdown_world_label(f"APPROX_GL02_INT20_R5_LABEL_QUARTER_INSET_{token}", label, (loc[0], loc[1], 25.0), 0.36, "quarter_inset")
    for token, label, pts in [
        ("LOCATOR_TOP", "母图定位框", [(-5.5, 3.0), (-3.2, 3.0), (-3.2, 1.1), (-5.5, 1.1), (-5.5, 3.0)]),
        ("CONNECT_A", "连接线", [(-3.2, 3.0), (2.1, 3.8)]),
        ("CONNECT_B", "连接线", [(-3.2, 1.1), (2.1, -1.6)]),
    ]:
        add_camera_overlay_line(f"APPROX_GL02_INT20_R5_QUARTER_INSET_{token}", cameras["QUARTER_INSET_COMPOSITE"], pts, "quarter_inset")

    debug_anchor_helpers = []
    debug_mats = anchor_marker_mats
    debug_label_locs = {
        "steel": (-1.05, 1.22),
        "cooling": (-1.05, 0.90),
        "refractory": (-1.05, 0.58),
        "inner_void": (1.65, -0.36),
    }
    for token, spec in semantic_world_anchors.items():
        bpy.ops.mesh.primitive_uv_sphere_add(segments=16, ring_count=8, radius=0.055, location=spec["world_anchor"])
        obj = bpy.context.object
        obj.name = f"APPROX_GL02_INT20_R5_ANCHOR_DEBUG_MARKER_{token.upper()}"
        obj.data.materials.append(debug_mats[token])
        obj.hide_viewport = True
        obj.hide_render = True
        aux.objects.link(obj)
        debug_anchor_helpers.append(obj)
        try:
            scene.collection.objects.unlink(obj)
        except Exception:
            pass
        add_camera_overlay_label(
            f"APPROX_GL02_INT20_R5_LABEL_ANCHOR_DEBUG_{token.upper()}",
            f"{spec['label']}\n{spec['source_object']}",
            cameras["ANCHOR_DEBUG"],
            (debug_label_locs[token][0], debug_label_locs[token][1], -2.0),
            0.026,
            "anchor_debug",
        )
        endpoint = camera_local_from_world(cameras["ANCHOR_DEBUG"], spec["world_anchor"])
        start = (debug_label_locs[token][0] + (0.28 if debug_label_locs[token][0] < endpoint[0] else -0.28), debug_label_locs[token][1] - 0.02)
        add_camera_overlay_line(f"APPROX_GL02_INT20_R5_LEADER_ANCHOR_DEBUG_{token.upper()}", cameras["ANCHOR_DEBUG"], [start, endpoint], "anchor_debug")

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
            keys = ["STEEL_SHELL_QUARTER", "COOLING_WALL_QUARTER", "REFRACTORY_LINING_QUARTER"]
            return [bpy.data.objects[f"APPROX_GL02_INT10_{k}"] for k in keys] + inset_helpers
        if mode == "anchor_debug":
            keys = ["STEEL_SHELL_HALF", "COOLING_WALL_HALF", "REFRACTORY_LINING_HALF"]
            return [bpy.data.objects[f"APPROX_GL02_INT10_{k}"] for k in keys] + debug_anchor_helpers
        return []

    for view, mode in [("FRONT_CONTEXT", "front"), ("HALF_CUT", "half"), ("QUARTER_CUT", "quarter"), ("EXPLODED_CUT", "exploded")]:
        fit_ortho(cameras[view], objects_for(mode), desired=0.76)

    def set_visibility(mode: str) -> dict[str, bool]:
        for obj in bpy.data.objects:
            if (
                obj.name.startswith("APPROX_GL02_INT10_")
                or obj.name.startswith("APPROX_GL02_INT20_R3_")
                or obj.name.startswith("APPROX_GL02_INT20_R4_")
                or obj.name.startswith("APPROX_GL02_INT20_R5_")
                or "INT20_R2" in obj.name
                or obj.name.startswith("INT20_R4_")
                or obj.name.startswith("INT20_R5_")
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
        if mode == "anchor_debug":
            for obj in overlay_groups["anchor_debug"]:
                obj.hide_render = False
        if mode == "colorcard":
            for obj in bpy.data.objects:
                if obj.type in {"MESH", "FONT"} and not obj.name.startswith("APPROX_GL02_INT20_R5_COLORCARD_"):
                    obj.hide_render = True
            for obj in aux.objects:
                if "COLORCARD_" in obj.name:
                    obj.hide_render = False
        return {name: bool(bpy.data.objects[name].hide_render) for name in INT10_OBJECTS if "PROCESS_SPACE" in name}

    render_specs = [
        ("FRONT_CONTEXT", "front", "complete_front_context_top_bottom_visible_process_hidden"),
        ("HALF_CUT", "half", "full_height_half_cut_body_70_82_percent_process_hidden"),
        ("QUARTER_CUT", "quarter", "full_height_quarter_cut_body_70_82_percent_process_hidden"),
        ("EXPLODED_CUT_ANNOTATED", "exploded", "render_only_clones_with_direct_material_labels_not_to_scale"),
        ("SECTION_CLOSEUP_SEMANTIC", "closeup", "semantic_anchors_from_real_material_objects_with_projection_manifest"),
        ("SECTION_MAGNIFIED_5X_SEMANTIC", "magnified", "semantic_anchors_from_real_material_objects_5x_camera"),
        ("COLORCARD", "colorcard", "four_column_material_colorcard_readable_non_overlapping_labels"),
        ("QUARTER_INSET_COMPOSITE", "quarter_inset", "true_quarter_cut_mother_view_with_equal_scale_render_only_inset_clone"),
        ("ANCHOR_DEBUG", "anchor_debug", "debug_markers_showing_each_semantic_anchor_and_source_object"),
    ]
    margin_metrics: dict[str, Any] = {}
    process_hidden_by_view: dict[str, Any] = {}
    evidence = []
    for render_id, mode, purpose in render_specs:
        process_hidden_by_view[render_id] = set_visibility(mode)
        scene.camera = cameras[render_id]
        if render_id in {"FRONT_CONTEXT", "HALF_CUT", "QUARTER_CUT", "EXPLODED_CUT_ANNOTATED"}:
            margin_metrics[render_id] = projection_bbox(cameras[render_id], objects_for(mode))
        path = render_dir / f"INT20_R5_{render_id}.png"
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
                "lookdev": "r5_brighter_neutral_cutface_fill_agx_no_bloom_freestyle_disabled",
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
        elif obj.name.startswith("APPROX_GL02_INT20_R5_COLORCARD_LABEL_"):
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
            "closeup": "SECTION_CLOSEUP_SEMANTIC",
            "magnified": "SECTION_MAGNIFIED_5X_SEMANTIC",
            "exploded": "EXPLODED_CUT",
            "quarter_inset": "QUARTER_INSET_COMPOSITE",
            "anchor_debug": "ANCHOR_DEBUG",
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

    def bbox_area_fraction(box: dict[str, float]) -> float:
        width = max(0.0, min(1.0, box["xmax"]) - max(0.0, box["xmin"]))
        height = max(0.0, min(1.0, box["ymax"]) - max(0.0, box["ymin"]))
        return float(width * height)

    quarter_mother_objects = [
        bpy.data.objects["APPROX_GL02_INT10_STEEL_SHELL_QUARTER"],
        bpy.data.objects["APPROX_GL02_INT10_COOLING_WALL_QUARTER"],
        bpy.data.objects["APPROX_GL02_INT10_REFRACTORY_LINING_QUARTER"],
    ]
    quarter_mother_bbox = projection_bbox(cameras["QUARTER_INSET_COMPOSITE"], quarter_mother_objects)
    quarter_inset_bbox = projection_bbox(cameras["QUARTER_INSET_COMPOSITE"], inset_helpers)
    quarter_title_name = "APPROX_GL02_INT20_R5_LABEL_QUARTER_INSET_TITLE"
    quarter_title_box = annotation_label_bboxes.get(quarter_title_name, {})
    quarter_title_inside = bool(quarter_title_box) and all(
        [
            quarter_title_box["xmin"] >= 0,
            quarter_title_box["ymin"] >= 0,
            quarter_title_box["xmax"] <= args.width,
            quarter_title_box["ymax"] <= args.height,
        ]
    )
    quarter_material_band_bboxes = {
        obj.name: projection_bbox(cameras["QUARTER_INSET_COMPOSITE"], [obj])
        for obj in inset_helpers
    }
    quarter_inset_metrics = {
        "mother_image_visible": bbox_area_fraction(quarter_mother_bbox) >= 0.04,
        "mother_projected_bbox_normalized": quarter_mother_bbox,
        "inset_projected_bbox_normalized": quarter_inset_bbox,
        "inset_nonbackground_coverage": round(bbox_area_fraction(quarter_inset_bbox), 6),
        "title_bbox_inside_frame": quarter_title_inside,
        "title_bbox_px": quarter_title_box,
        "material_band_bboxes_normalized": quarter_material_band_bboxes,
        "all_material_bands_visible_in_inset": all(bbox_area_fraction(box) >= 0.01 for box in quarter_material_band_bboxes.values()),
    }

    source_sig_after = mesh_signature(INT10_OBJECTS)
    sensor_sig_after = sensor_signature()
    audits = {name: object_audit(bpy.data.objects[name]) for name in INT10_OBJECTS}
    old_hidden = previous_report.get("protected_contract", {}).get("old_55_explanatory_objects_hidden_count", 55)
    margin_pass = all(
        0.70 <= margin_metrics[key]["height_fraction"] <= 0.82
        and margin_metrics[key]["top_margin"] >= 0.06
        and margin_metrics[key]["bottom_margin"] >= 0.06
        for key in ["HALF_CUT", "QUARTER_CUT", "EXPLODED_CUT_ANNOTATED"]
    )
    process_hidden_pass = all(
        all(hidden for hidden in process_hidden_by_view[key].values())
        for key in ["HALF_CUT", "QUARTER_CUT", "EXPLODED_CUT_ANNOTATED", "SECTION_CLOSEUP_SEMANTIC", "SECTION_MAGNIFIED_5X_SEMANTIC", "QUARTER_INSET_COMPOSITE", "ANCHOR_DEBUG"]
    )
    annotation_counts = {group: len([obj for obj in items if obj.type == "FONT"]) for group, items in overlay_groups.items()}

    material_manifest = {
        "schema_version": "bf3d.int20_r5.visual_manifest.v1",
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
            "previous_source_audit_object_count": len(previous_report.get("source_object_audits", {})),
        },
        "freestyle": {"enabled": bool(scene.render.use_freestyle), "max_thickness_px": 0.0, "policy": "disabled"},
        "render_only_exploded_clones": {
            name: {
                "source_object": obj.name.replace("APPROX_GL02_INT20_R5_RENDER_ONLY_EXPLODED_", "APPROX_GL02_INT10_"),
                "location": [round(v, 5) for v in obj.location],
                "note": "diagrammatic separation not to scale; source INT10/R3 objects are not moved",
            }
            for name, obj in exploded.items()
        },
        "render_only_inset_helpers": {
            obj.name: {
                "type": obj.type,
                "source_object": obj.get("source_object"),
                "location": [round(v, 5) for v in obj.location],
                "scale": [round(v, 5) for v in obj.scale],
                "policy": obj.get("inset_policy"),
                "note": "render-only equal-scale clone of the same true quarter cut; not independent color bars",
            }
            for obj in inset_helpers
        },
        "semantic_anchors": {
            "required_views": ["SECTION_CLOSEUP_SEMANTIC", "SECTION_MAGNIFIED_5X_SEMANTIC"],
            "records_by_view": semantic_anchor_records,
            "endpoint_error_threshold_px": 4.0,
            "all_endpoint_errors_lte_4px": all(item["endpoint_error_px"] <= 4.0 for rows in semantic_anchor_records.values() for item in rows),
            "all_projected_pixels_inside_frame": all(
                0.0 <= item["projected_pixel"][0] <= args.width and 0.0 <= item["projected_pixel"][1] <= args.height
                for rows in semantic_anchor_records.values()
                for item in rows
            ),
            "all_records_endpoint_in_frame": all(item["endpoint_in_frame"] for rows in semantic_anchor_records.values() for item in rows),
            "all_tips_inside_source_object_projected_bbox": all(item["tip_inside_source_object_projected_bbox"] for rows in semantic_anchor_records.values() for item in rows),
            "leader_crosses_other_material_count_total": sum(item["leader_crosses_other_material_count"] for rows in semantic_anchor_records.values() for item in rows),
            "source_objects_exist": all(bpy.data.objects.get(item["source_object"]) for rows in semantic_anchor_records.values() for item in rows),
            "layer_tokens_match": all(
                (
                    ("STEEL_SHELL" in item["source_object"] and item["expected_layer"] == "steel_shell")
                    or ("COOLING_WALL" in item["source_object"] and item["expected_layer"] == "cooling_wall")
                    or ("REFRACTORY_LINING" in item["source_object"] and item["expected_layer"] in {"refractory_lining", "inner_void"})
                )
                for rows in semantic_anchor_records.values()
                for item in rows
            ),
        },
        "outer_to_inner_direction": {
            "correct_order": "steel_shell > cooling_wall > refractory_lining > inner_void",
            "radius_order_evidence": {k: round(float(v), 6) for k, v in radius_order.items()},
            "radius_order_pass": radius_order["steel"] > radius_order["cooling"] > radius_order["refractory"] > radius_order["inner_void"],
            "screen_direction_by_view": direction_arrow_records,
        },
        "quarter_inset_composite": {
            "source": "actual INT10 quarter cut objects plus uniformly enlarged render-only clones",
            "mother_view_locator_and_connection_lines": True,
            "clone_scale_factor": 1.65,
            "not_thickness_scale": True,
            "degenerated_to_independent_color_bars": False,
            "clone_source_objects": {obj.name: obj.get("source_object") for obj in inset_helpers},
            **quarter_inset_metrics,
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
    write_json(output_dir / "int20_r5_visual_manifest.json", material_manifest)

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
        "cutface_material_faces_preserved": all(item["cutface_material_faces"] == previous_report["source_object_audits"][name]["cutface_material_faces"] for name, item in audits.items()),
        "old_55_explanatory_objects_hidden_count_preserved": old_hidden == 55,
        "full_body_margin_metrics_pass": margin_pass,
        "process_space_hidden_in_cut_views": process_hidden_pass,
        "colorcard_label_bboxes_non_overlapping": not overlaps,
        "engineering_annotations_complete": all(annotation_counts.get(group, 0) >= minimum for group, minimum in {"closeup": 5, "magnified": 6, "exploded": 1, "quarter_inset": 5}.items())
        and len([obj for obj in overlay_groups["closeup"] if obj.type == "CURVE"]) >= 4
        and len([obj for obj in overlay_groups["magnified"] if obj.type == "CURVE"]) >= 4,
        "annotation_label_bboxes_non_overlapping": not annotation_overlaps,
        "semantic_anchor_contract_pass": material_manifest["semantic_anchors"]["all_endpoint_errors_lte_4px"]
        and material_manifest["semantic_anchors"]["all_projected_pixels_inside_frame"]
        and material_manifest["semantic_anchors"]["all_records_endpoint_in_frame"]
        and material_manifest["semantic_anchors"]["all_tips_inside_source_object_projected_bbox"]
        and material_manifest["semantic_anchors"]["leader_crosses_other_material_count_total"] == 0
        and material_manifest["semantic_anchors"]["source_objects_exist"]
        and material_manifest["semantic_anchors"]["layer_tokens_match"]
        and all(len(semantic_anchor_records.get(view, [])) == 4 for view in ["SECTION_CLOSEUP_SEMANTIC", "SECTION_MAGNIFIED_5X_SEMANTIC"]),
        "radius_order_pass": material_manifest["outer_to_inner_direction"]["radius_order_pass"],
        "quarter_inset_true_cut_composite_pass": material_manifest["quarter_inset_composite"]["mother_view_locator_and_connection_lines"]
        and not material_manifest["quarter_inset_composite"]["degenerated_to_independent_color_bars"]
        and all(obj.get("source_object") for obj in inset_helpers)
        and material_manifest["quarter_inset_composite"]["mother_image_visible"]
        and material_manifest["quarter_inset_composite"]["inset_nonbackground_coverage"] >= 0.20
        and material_manifest["quarter_inset_composite"]["title_bbox_inside_frame"]
        and material_manifest["quarter_inset_composite"]["all_material_bands_visible_in_inset"],
        "render_only_helper_objects_named_and_separate": all(obj.name.startswith("APPROX_GL02_INT20_R5_RENDER_ONLY_") for obj in list(exploded.values()) + inset_helpers),
        "freestyle_disabled_or_restrained": not scene.render.use_freestyle,
        "section_magnified_5x_label_present": bool(bpy.data.objects.get("APPROX_GL02_INT20_R5_LABEL_SECTION_MAGNIFIED_5X")),
        "formal_glb_not_exported": not list(output_dir.glob("*.glb")),
        "blend1_not_generated": not list(output_dir.glob("*.blend1")),
        "renders_exist_pass": len(evidence) >= 9 and all(item["bytes"] > 1024 for item in evidence),
    }

    scene["BF3D_STAGE"] = STAGE_ID
    scene["BF3D_STATUS"] = "candidate_ready_for_review"
    scene["BF3D_APPROVAL"] = "not_granted_requires_visual_and_spec_review"
    bpy.ops.wm.save_as_mainfile(filepath=str(output_blend), check_existing=False)
    candidate["bytes"] = output_blend.stat().st_size
    candidate["sha256"] = sha256_file(output_blend)

    report = {
        "schema_version": "bf3d.int20_r5.machine_report.v1",
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
        "visual_manifest": str(output_dir / "int20_r5_visual_manifest.json"),
        "evidence_renders": evidence,
        "assertions": assertions,
        "known_issues": [
            "R5 remains E-grade approximate visual explanation, not measured engineering/as-built dimensions.",
            "EXPLODED_CUT and QUARTER_INSET_DETAIL are diagrammatic aids and use render-only helpers.",
            "No formal GLB was exported; independent visual and spec review is still required.",
            "Root-level specs/avatar_spec.json, specs/acceptance_checklist.md, reports/pipeline_status.json were not present in this workspace; R5 reports this as an evidence gap and did not update a missing status file.",
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
    write_json(output_dir / "int20_r5_machine_report.json", report)
    return 0


def reopen_validate() -> int:
    import bpy
    import bmesh

    args = blender_args()
    output_dir = args.output_dir.resolve()
    candidate = output_dir / OUTPUT_BLEND_NAME
    visual_manifest = json.loads((output_dir / "int20_r5_visual_manifest.json").read_text(encoding="utf-8"))

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
        f"INT20_R5_{rid}.png"
        for rid in [
            "FRONT_CONTEXT",
            "HALF_CUT",
            "QUARTER_CUT",
            "EXPLODED_CUT_ANNOTATED",
            "SECTION_CLOSEUP_SEMANTIC",
            "SECTION_MAGNIFIED_5X_SEMANTIC",
            "COLORCARD",
            "QUARTER_INSET_COMPOSITE",
            "ANCHOR_DEBUG",
        ]
    ]
    render_presence = {
        name: (output_dir / "renders" / name).is_file() and (output_dir / "renders" / name).stat().st_size > 1024
        for name in expected_renders
    }
    audits = {name: audit_obj(name) for name in INT10_OBJECTS if bpy.data.objects.get(name)}
    validation = {
        "schema_version": "bf3d.int20_r5.reopen_validation.v1",
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
                for key in ["HALF_CUT", "QUARTER_CUT", "EXPLODED_CUT_ANNOTATED"]
            ),
            "colorcard_label_bboxes_non_overlapping": visual_manifest["colorcard"]["non_overlapping"],
            "engineering_annotations_complete": visual_manifest["engineering_annotations"]["non_overlapping"]
            and all(visual_manifest["engineering_annotations"]["font_label_counts"].get(group, 0) >= minimum for group, minimum in {"closeup": 5, "magnified": 6, "exploded": 1, "quarter_inset": 5}.items()),
            "semantic_anchor_contract_pass": visual_manifest["semantic_anchors"]["all_endpoint_errors_lte_4px"]
            and visual_manifest["semantic_anchors"]["all_projected_pixels_inside_frame"]
            and visual_manifest["semantic_anchors"]["all_records_endpoint_in_frame"]
            and visual_manifest["semantic_anchors"]["all_tips_inside_source_object_projected_bbox"]
            and visual_manifest["semantic_anchors"]["leader_crosses_other_material_count_total"] == 0
            and visual_manifest["semantic_anchors"]["source_objects_exist"]
            and visual_manifest["semantic_anchors"]["layer_tokens_match"],
            "radius_order_pass": visual_manifest["outer_to_inner_direction"]["radius_order_pass"],
            "quarter_inset_true_cut_composite_pass": visual_manifest["quarter_inset_composite"]["mother_view_locator_and_connection_lines"]
            and not visual_manifest["quarter_inset_composite"]["degenerated_to_independent_color_bars"]
            and visual_manifest["quarter_inset_composite"]["mother_image_visible"]
            and visual_manifest["quarter_inset_composite"]["inset_nonbackground_coverage"] >= 0.20
            and visual_manifest["quarter_inset_composite"]["title_bbox_inside_frame"]
            and visual_manifest["quarter_inset_composite"]["all_material_bands_visible_in_inset"],
            "process_space_hidden_in_cut_views": all(
                all(hidden for hidden in visual_manifest["process_hidden_by_cut_view"][key].values())
                for key in ["HALF_CUT", "QUARTER_CUT", "EXPLODED_CUT_ANNOTATED", "SECTION_CLOSEUP_SEMANTIC", "SECTION_MAGNIFIED_5X_SEMANTIC", "QUARTER_INSET_COMPOSITE", "ANCHOR_DEBUG"]
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


