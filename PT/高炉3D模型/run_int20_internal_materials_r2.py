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
STAGE_ID = "INT-20_R2"
REQUIREMENT_ID = "REQ-BF3D-INT20-R2-SOLID-CUTAWAY-20260718"
DEFAULT_BLENDER = Path(r"D:\Program Files\Blender Foundation\Blender 5.2\blender.exe")
DEFAULT_INPUT = ROOT / "PT" / "高炉3D模型" / "work" / "INT_10_20260718_R1" / "INT_10_INTERNAL_GRAYBOX_CANDIDATE.blend"
DEFAULT_OUTPUT = ROOT / "PT" / "高炉3D模型" / "work" / "INT_20_20260718_R2"
INT10_MANIFEST = ROOT / "PT" / "高炉3D模型" / "work" / "INT_10_20260718_R1" / "int10_structure_manifest.json"
INT10_REPORT = ROOT / "PT" / "高炉3D模型" / "work" / "INT_10_20260718_R1" / "int10_internal_graybox_report.json"
EXPECTED_INPUT_SHA256 = "ee8387959d26612d2f03d2ff05651419fbdcb087cb546f4a8293d957233553fe"
OUTPUT_BLEND_NAME = "INT_20_R2_SOLID_THICKNESS_CUTAWAY_CANDIDATE.blend"


def utc_now_iso() -> str:
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
    manifest = json.loads((output_dir / "int20_r2_solid_thickness_manifest.json").read_text(encoding="utf-8"))
    renders = report.get("evidence_renders", [])
    assertions = report.get("assertions", {})
    lines = [
        "# INT-20 R2 阶段成果总结",
        "",
        "## 目标",
        "",
        "- 对 INT-20 R1 的半剖/四分之一剖过暗、相机过近、中央工艺空间压黑、层次像细线的问题做实体厚度剖切返工。",
        "- 输入固定为已批准 INT-10 R1 候选 `.blend`，本阶段不推进 GLB，不修改 R1 或正式前端资产。",
        "",
        "## 实体厚度口径",
        "",
        "- 12 个 INT-10 对象的命名、矩阵和网格几何签名保持不变；R2 仅重分配材质槽、剖面材质和可视化证据。",
        "- 钢壳厚度沿用 E 级估算 45-65 mm；冷却壁、耐火层沿用 INT-10 manifest 的 E 级估算值。",
        "- 这些值只用于说明性可视化，不是实测工程尺寸、施工尺寸或 as-built 资产。",
        "",
        "## 实际修改",
        "",
        f"- 候选 blend：`{report['candidate']['path']}`",
        f"- 机器报告：`{output_dir / 'int20_r2_machine_report.json'}`",
        f"- 实体厚度 manifest：`{output_dir / 'int20_r2_solid_thickness_manifest.json'}`",
        f"- 重新打开验证：`{output_dir / 'reopen_validation.json'}`",
        f"- 命令记录：`{output_dir / 'command.json'}`",
        f"- 哈希清单：`{output_dir / 'artifact_sha256.json'}`",
        "",
        "## 证据",
        "",
    ]
    for item in renders:
        lines.append(f"- `{item['id']}`：`{Path(item['path']).relative_to(output_dir).as_posix()}`，{item['projection']}，{item['bytes']} bytes")
    lines.extend(
        [
            "",
            "## 断言",
            "",
            f"- 输入 SHA 匹配：`{assertions.get('input_sha256_matches')}`",
            f"- 受保护对象未漂移：`{assertions.get('protected_contract_pass')}`",
            f"- INT-10 12 对象命名/矩阵/几何签名保持：`{assertions.get('int10_12_names_matrices_geometry_preserved')}`",
            f"- 每个主剖切对象非流形边为 0：`{assertions.get('non_manifold_edges_zero')}`",
            f"- 钢壳/冷却壁/耐火层全部具备内外表面、剖面盖片和正体积：`{assertions.get('solid_surface_cap_volume_pass')}`",
            f"- 重新打开验证通过：`{assertions.get('reopen_validation_pass')}`",
            "",
            "## 已知问题",
            "",
        ]
    )
    for item in report.get("known_issues", []):
        lines.append(f"- {item}")
    lines.extend(
        [
            "",
            "## 下一停止线",
            "",
            "- 状态最高停在 `candidate_ready_for_review`，`approval=not_granted_requires_visual_and_spec_review`。",
            "- 未经视觉质量审查和规格复核，不得进入下一阶段，不得导出正式 GLB。",
            "- 若视觉审查认为剖切仍像线稿，下一轮只能继续在 INT-20 R3 修剖切表达，不得跳到后续阶段。",
            "",
            "## 关键统计",
            "",
            f"- 被审计对象数：`{len(manifest.get('object_audits', {}))}`",
            f"- 渲染数量：`{len(renders)}`",
            f"- 候选 SHA-256：`{report['candidate']['sha256']}`",
        ]
    )
    (output_dir / "INT-20_R2_阶段成果总结.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def host_main() -> int:
    parser = argparse.ArgumentParser(description="INT-20 R2 solid-thickness cutaway repaint/review runner")
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

    for required in (blender, input_blend, script, INT10_MANIFEST, INT10_REPORT):
        if not required.is_file():
            raise FileNotFoundError(required)
    actual_input_sha256 = sha256_file(input_blend)
    if actual_input_sha256.lower() != EXPECTED_INPUT_SHA256:
        raise RuntimeError(f"INT-10 input hash mismatch: expected={EXPECTED_INPUT_SHA256} actual={actual_input_sha256}")
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "renders").mkdir(exist_ok=True)
    for stale_blend_backup in output_dir.glob("*.blend1"):
        raise RuntimeError(f"Refusing to continue while .blend1 exists in R2 workdir: {stale_blend_backup}")

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
        "requirement_id": REQUIREMENT_ID,
        "stage": STAGE_ID,
        "started_at": utc_now_iso(),
        "cwd": str(ROOT),
        "command_argv": command,
        "reopen_command_argv": reopen_command,
        "input_sha256": actual_input_sha256,
        "formal_glb_exported": False,
        "blend1_forbidden": True,
    }
    write_json(output_dir / "command.json", command_record)

    completed = subprocess.run(command, cwd=ROOT, check=False, capture_output=True, text=True, encoding="utf-8", errors="replace")
    (output_dir / "blender_stdout.log").write_text(completed.stdout or "", encoding="utf-8")
    (output_dir / "blender_stderr.log").write_text(completed.stderr or "", encoding="utf-8")
    command_record["main_returncode"] = completed.returncode
    command_record["main_finished_at"] = utc_now_iso()
    write_json(output_dir / "command.json", command_record)
    if completed.returncode != 0:
        write_json(output_dir / "execution_failed.json", {**command_record, "status": "failed"})
        print(completed.stdout)
        print(completed.stderr, file=sys.stderr)
        return completed.returncode
    main_report_path = output_dir / "int20_r2_machine_report.json"
    if not output_blend.is_file() or not main_report_path.is_file():
        write_json(
            output_dir / "execution_failed.json",
            {
                **command_record,
                "status": "failed",
                "reason": "Blender process returned zero but did not write candidate blend and report",
                "candidate_exists": output_blend.is_file(),
                "report_exists": main_report_path.is_file(),
            },
        )
        return 1

    reopened = subprocess.run(reopen_command, cwd=ROOT, check=False, capture_output=True, text=True, encoding="utf-8", errors="replace")
    (output_dir / "reopen_stdout.log").write_text(reopened.stdout or "", encoding="utf-8")
    (output_dir / "reopen_stderr.log").write_text(reopened.stderr or "", encoding="utf-8")
    command_record["reopen_returncode"] = reopened.returncode
    command_record["reopen_finished_at"] = utc_now_iso()
    write_json(output_dir / "command.json", command_record)
    if reopened.returncode != 0:
        print(reopened.stdout)
        print(reopened.stderr, file=sys.stderr)
        return reopened.returncode

    report_path = output_dir / "int20_r2_machine_report.json"
    if not report_path.is_file():
        raise FileNotFoundError(report_path)
    report = json.loads(report_path.read_text(encoding="utf-8"))
    reopen_validation = json.loads((output_dir / "reopen_validation.json").read_text(encoding="utf-8"))
    report["execution"] = {
        "finished_at": utc_now_iso(),
        "returncode": completed.returncode,
        "reopen_returncode": reopened.returncode,
        "command_record": str(output_dir / "command.json"),
        "stdout_log": str(output_dir / "blender_stdout.log"),
        "stderr_log": str(output_dir / "blender_stderr.log"),
        "reopen_stdout_log": str(output_dir / "reopen_stdout.log"),
        "reopen_stderr_log": str(output_dir / "reopen_stderr.log"),
    }
    report["reopen_validation"] = reopen_validation
    report.setdefault("assertions", {})["reopen_validation_pass"] = reopen_validation.get("status") == "pass"
    report["assertions"]["machine_assertions_pass"] = all(bool(value) for value in report["assertions"].values())
    write_json(report_path, report)
    write_summary(output_dir, report)

    artifact_records = collect_artifacts(output_dir)
    write_json(
        output_dir / "artifact_sha256.json",
        {
            "schema_version": 1,
            "requirement_id": REQUIREMENT_ID,
            "stage": STAGE_ID,
            "generated_at": utc_now_iso(),
            "artifacts": artifact_records,
        },
    )
    if list(output_dir.glob("*.blend1")):
        raise RuntimeError(".blend1 backup was generated despite save_version=0")
    print(
        json.dumps(
            {
                "status": report["status"],
                "approval": report["approval"],
                "candidate": report["candidate"],
                "report": str(report_path),
                "render_count": len(report["evidence_renders"]),
                "machine_assertions_pass": report["assertions"]["machine_assertions_pass"],
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


def blender_args() -> argparse.Namespace:
    argv = sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else []
    parser = argparse.ArgumentParser()
    parser.add_argument("--inside-blender", action="store_true")
    parser.add_argument("--reopen-validate", action="store_true")
    parser.add_argument("--input-blend", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--width", required=True, type=int)
    parser.add_argument("--height", required=True, type=int)
    return parser.parse_args(argv)


def blender_main() -> int:
    import math

    import bmesh
    import bpy
    from mathutils import Vector

    args = blender_args()
    output_dir = args.output_dir.resolve()
    render_dir = output_dir / "renders"
    render_dir.mkdir(parents=True, exist_ok=True)
    input_blend = args.input_blend.resolve()
    output_blend = output_dir / OUTPUT_BLEND_NAME
    int10_manifest = json.loads(INT10_MANIFEST.read_text(encoding="utf-8"))
    int10_report = json.loads(INT10_REPORT.read_text(encoding="utf-8"))

    if sha256_file(input_blend).lower() != EXPECTED_INPUT_SHA256:
        raise RuntimeError("INT-10 hash changed between host and Blender launch")
    if Path(bpy.data.filepath).resolve() != input_blend:
        raise RuntimeError(f"Blender opened unexpected input: {bpy.data.filepath}")
    bpy.context.preferences.filepaths.save_version = 0

    def matrix_values(obj: Any) -> list[float]:
        return [round(float(value), 9) for row in obj.matrix_world for value in row]

    def mesh_geometry_sha256(obj: Any) -> str | None:
        if obj.type != "MESH" or not obj.data:
            return None
        h = hashlib.sha256()
        mesh = obj.data
        h.update(f"{len(mesh.vertices)}:{len(mesh.edges)}:{len(mesh.polygons)}|".encode("utf-8"))
        for vertex in mesh.vertices:
            h.update(f"{vertex.co.x:.9f},{vertex.co.y:.9f},{vertex.co.z:.9f};".encode("utf-8"))
        for poly in mesh.polygons:
            h.update((",".join(str(index) for index in poly.vertices) + ";").encode("utf-8"))
        return h.hexdigest()

    def object_signature(names: list[str]) -> dict[str, Any]:
        payload = {}
        for name in sorted(names):
            obj = bpy.data.objects.get(name)
            payload[name] = None if obj is None else {
                "type": obj.type,
                "parent": obj.parent.name if obj.parent else None,
                "matrix": matrix_values(obj),
                "mesh_geometry_sha256": mesh_geometry_sha256(obj),
            }
        return payload

    def protected_snapshot() -> dict[str, Any]:
        sensors = sorted((obj for obj in bpy.data.objects if obj.name.startswith("SENSOR_")), key=lambda obj: obj.name)
        body_temp = [obj for obj in sensors if obj.name.startswith("SENSOR_T_body_")]
        layer_groups = sorted(
            set(obj.name for obj in bpy.data.objects if obj.name.startswith("GL02_SENSOR_LAYER_L"))
            | set(coll.name for coll in bpy.data.collections if coll.name.startswith("GL02_SENSOR_LAYER_L"))
        )
        segments = sorted(obj.name for obj in bpy.data.objects if obj.name.startswith("APPROX_GL02_FURNACE_"))
        payload = {
            "sensor_count": len(sensors),
            "body_temp_sensor_count": len(body_temp),
            "layer_groups": layer_groups,
            "furnace_segments": segments,
            "sensor_records": {
                obj.name: {"parent": obj.parent.name if obj.parent else None, "matrix": matrix_values(obj)}
                for obj in sensors
            },
        }
        payload["sensor_signature_sha256"] = hashlib.sha256(
            json.dumps(payload["sensor_records"], ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()
        return payload

    all_int10_names = []
    layer_object_names = {}
    for layer in int10_manifest["layers"]:
        names = list(layer["objects"].values())
        layer_object_names[layer["layer_id"]] = names
        all_int10_names.extend(names)

    before_protected = protected_snapshot()
    before_int10_signature = object_signature(all_int10_names)
    if before_protected["sensor_count"] != 115 or before_protected["body_temp_sensor_count"] != 80:
        raise RuntimeError(f"Protected sensor contract failed before edit: {before_protected}")
    if any(before_int10_signature[name] is None for name in all_int10_names):
        raise RuntimeError("One or more INT-10 graybox objects are missing")

    for name in int10_report.get("hidden_explanatory_objects", []):
        obj = bpy.data.objects.get(name)
        if obj:
            obj.hide_viewport = True
            obj.hide_render = True
            obj["bf3d_int20_r2_protected_hidden_only"] = True

    scene = bpy.context.scene
    scene.render.engine = "BLENDER_EEVEE_NEXT" if "BLENDER_EEVEE_NEXT" in [item.identifier for item in bpy.types.RenderSettings.bl_rna.properties["engine"].enum_items] else "BLENDER_EEVEE"
    scene.render.resolution_x = args.width
    scene.render.resolution_y = args.height
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = "PNG"
    scene.render.film_transparent = False
    scene.view_settings.view_transform = "AgX"
    scene.view_settings.look = "AgX - Medium Low Contrast"
    scene.view_settings.exposure = 0.35
    scene.world = scene.world or bpy.data.worlds.new("INT20_R2_WORLD")
    scene.world.color = (0.73, 0.75, 0.74)
    try:
        scene.eevee.taa_render_samples = 64
    except Exception:
        pass
    try:
        scene.render.use_freestyle = True
        scene.view_layers[0].freestyle_settings.linesets[0].linestyle.color = (0.78, 0.92, 0.95)
        scene.view_layers[0].freestyle_settings.linesets[0].linestyle.thickness = 0.8
    except Exception:
        pass

    def look_at(obj: Any, target: tuple[float, float, float]) -> None:
        direction = Vector(target) - Vector(obj.location)
        obj.rotation_euler = direction.to_track_quat("-Z", "Y").to_euler()

    def ensure_area_light(name: str, location: tuple[float, float, float], power: float, size: float, target=(0.0, 0.0, 0.0)) -> Any:
        obj = bpy.data.objects.get(name)
        if obj is None:
            data = bpy.data.lights.new(name + "_DATA", "AREA")
            obj = bpy.data.objects.new(name, data)
            bpy.context.scene.collection.objects.link(obj)
        obj.location = location
        obj.data.energy = power
        obj.data.size = size
        obj.hide_render = False
        obj.hide_viewport = False
        look_at(obj, target)
        return obj

    for obj in bpy.data.objects:
        if obj.type == "LIGHT":
            obj.hide_render = True
            obj.hide_viewport = True
    ensure_area_light("INT20_R2_LARGE_SOFTBOX_FRONT_LEFT", (-8.0, -12.0, 14.0), 820.0, 11.0)
    ensure_area_light("INT20_R2_FILL_SOFTBOX_RIGHT", (9.0, 8.0, 8.0), 340.0, 13.0)
    ensure_area_light("INT20_R2_CYAN_SECTION_RIM", (10.0, -7.0, 5.0), 130.0, 7.0)

    def make_principled(name: str, base: tuple[float, float, float, float], metallic: float, roughness: float, alpha: float = 1.0) -> Any:
        mat = bpy.data.materials.get(name) or bpy.data.materials.new(name)
        mat.use_nodes = True
        mat.diffuse_color = base
        mat["bf3d_stage"] = STAGE_ID
        mat["confidence"] = "E"
        mat["derivation"] = "illustrative_visual_bible_cutaway"
        mat["not_as_built"] = True
        if alpha < 1.0:
            mat.blend_method = "BLEND"
            mat.show_transparent_back = True
            try:
                mat.surface_render_method = "BLENDED"
            except Exception:
                pass
        nodes = mat.node_tree.nodes
        bsdf = nodes.get("Principled BSDF") or next((node for node in nodes if node.type == "BSDF_PRINCIPLED"), None)
        if bsdf:
            for key, value in {
                "Base Color": base,
                "Metallic": metallic,
                "Roughness": roughness,
                "Alpha": alpha,
            }.items():
                if key in bsdf.inputs:
                    bsdf.inputs[key].default_value = value
        return mat

    material_families = {
        "steel_shell": {
            "body": make_principled("MI_INT20_R2_STEEL_SHELL_BODY_DARK_GRAPHITE", (0.18, 0.19, 0.185, 1.0), 0.62, 0.72),
            "cut": make_principled("MI_INT20_R2_STEEL_SHELL_CUTFACE_METAL_DEEP_GRAY", (0.32, 0.34, 0.335, 1.0), 0.72, 0.55),
            "label": "steel shell E estimate 45-65mm",
        },
        "cooling_wall": {
            "body": make_principled("MI_INT20_R2_COOLING_WALL_BODY_DARK_OXIDE_COPPER", (0.31, 0.15, 0.08, 1.0), 0.32, 0.76),
            "cut": make_principled("MI_INT20_R2_COOLING_WALL_CUTFACE_DARK_COPPER_BROWN", (0.54, 0.25, 0.12, 1.0), 0.28, 0.62),
            "label": "cooling wall E estimate from INT-10 manifest",
        },
        "refractory_lining": {
            "body": make_principled("MI_INT20_R2_REFRACTORY_BODY_WARM_GRAY_BRICK", (0.45, 0.39, 0.30, 1.0), 0.02, 0.92),
            "cut": make_principled("MI_INT20_R2_REFRACTORY_CUTFACE_WARM_GRAY_BRICK", (0.64, 0.57, 0.45, 1.0), 0.0, 0.95),
            "label": "refractory lining E estimate from INT-10 manifest",
        },
        "process_space": {
            "body": make_principled("MI_INT20_R2_PROCESS_SPACE_LOW_OCCLUSION_TRANSLUCENT", (0.05, 0.065, 0.07, 0.14), 0.0, 0.83, 0.14),
            "cut": make_principled("MI_INT20_R2_PROCESS_SPACE_CUTFACE_HIDDEN_LOW_ALPHA", (0.08, 0.10, 0.105, 0.10), 0.0, 0.9, 0.10),
            "label": "process space hidden or low alpha to avoid blocking solid layers",
        },
    }

    profile = int10_manifest["analytic_profiles"]
    profile_by_layer = {
        "steel_shell": ("steel_outer_r_m", "steel_inner_r_m"),
        "cooling_wall": ("cooling_outer_r_m", "cooling_inner_r_m"),
        "refractory_lining": ("refractory_outer_r_m", "refractory_inner_r_m"),
        "process_space": ("process_outer_r_m", None),
    }

    def interp_radius(z: float, key: str) -> float:
        pts = sorted((float(item["z_blender_m"]), float(item[key])) for item in profile)
        if z <= pts[0][0]:
            return pts[0][1]
        if z >= pts[-1][0]:
            return pts[-1][1]
        for (z0, r0), (z1, r1) in zip(pts, pts[1:]):
            if z0 <= z <= z1:
                t = (z - z0) / (z1 - z0)
                return r0 + (r1 - r0) * t
        return pts[-1][1]

    def classify_and_assign_cutfaces(obj: Any, layer_id: str, variant_name: str) -> dict[str, int | float | bool]:
        obj.data.materials.clear()
        obj.data.materials.append(material_families[layer_id]["body"])
        obj.data.materials.append(material_families[layer_id]["cut"])
        variant = int10_manifest["variants"][variant_name]
        full = math.isclose(float(variant["angle_coverage_deg"]), 360.0)
        start = math.radians(float(variant["angle_start_deg"]))
        end = start + math.radians(float(variant["angle_coverage_deg"]))
        z_min = min(float(item["z_blender_m"]) for item in profile)
        z_max = max(float(item["z_blender_m"]) for item in profile)
        outer_key, inner_key = profile_by_layer[layer_id]
        counts = {
            "outer_surface_faces": 0,
            "inner_surface_faces": 0,
            "top_bottom_cap_faces": 0,
            "angular_cut_cap_faces": 0,
            "cutface_material_faces": 0,
        }
        for poly in obj.data.polygons:
            coords = [obj.data.vertices[index].co for index in poly.vertices]
            center = poly.center
            radial = math.hypot(center.x, center.y)
            outer_r = interp_radius(center.z, outer_key)
            inner_r = interp_radius(center.z, inner_key) if inner_key else 0.0
            is_top_bottom = all(abs(v.z - z_min) < 1e-5 for v in coords) or all(abs(v.z - z_max) < 1e-5 for v in coords)
            is_angular_cap = False
            if not full:
                for angle in (start, end):
                    distances = [abs(-math.sin(angle) * v.x + math.cos(angle) * v.y) for v in coords]
                    if max(distances) < 1e-4:
                        is_angular_cap = True
                        break
            if is_top_bottom:
                counts["top_bottom_cap_faces"] += 1
            if is_angular_cap:
                counts["angular_cut_cap_faces"] += 1
            if abs(radial - outer_r) < 0.08:
                counts["outer_surface_faces"] += 1
            if inner_key and abs(radial - inner_r) < 0.08:
                counts["inner_surface_faces"] += 1
            if is_top_bottom or is_angular_cap:
                poly.material_index = 1
                counts["cutface_material_faces"] += 1
            else:
                poly.material_index = 0
        obj.data.update()
        counts["has_outer_surface"] = counts["outer_surface_faces"] > 0
        counts["has_inner_surface"] = True if layer_id == "process_space" else counts["inner_surface_faces"] > 0
        counts["has_cut_caps"] = counts["top_bottom_cap_faces"] > 0 and (full or counts["angular_cut_cap_faces"] > 0)
        return counts

    def mesh_audit(obj: Any, layer_id: str, variant_name: str) -> dict[str, Any]:
        bm = bmesh.new()
        bm.from_mesh(obj.data)
        bm.normal_update()
        non_manifold_edges = sum(1 for edge in bm.edges if not edge.is_manifold)
        volume = abs(float(bm.calc_volume()))
        bm.free()
        cut_counts = classify_and_assign_cutfaces(obj, layer_id, variant_name)
        return {
            "vertices": len(obj.data.vertices),
            "edges": len(obj.data.edges),
            "faces": len(obj.data.polygons),
            "non_manifold_edges": non_manifold_edges,
            "positive_volume": volume > 1e-6,
            "volume_m3_estimate": volume,
            "layer_id": layer_id,
            "variant": variant_name,
            "materials": [slot.material.name if slot.material else None for slot in obj.material_slots],
            **cut_counts,
        }

    object_audits = {}
    for layer_id, names_by_variant in layer_object_names.items():
        for variant_name, obj_name in zip(("full", "half", "quarter"), names_by_variant):
            obj = bpy.data.objects[obj_name]
            obj["bf3d_stage"] = STAGE_ID
            obj["bf3d_int20_r2_layer_id"] = layer_id
            obj["bf3d_int20_r2_variant"] = variant_name
            obj["confidence"] = "E"
            obj["derivation"] = "illustrative_solid_thickness_cutaway"
            obj["not_as_built"] = True
            obj["thickness_claim"] = "E_estimate_only_not_engineering_dimension"
            object_audits[obj_name] = mesh_audit(obj, layer_id, variant_name)

    aux_collection = bpy.data.collections.new("INT20_R2_SECTION_LABELS_AND_COLORCARD")
    scene.collection.children.link(aux_collection)
    aux_collection["bf3d_stage"] = STAGE_ID
    aux_collection["diagnostic_only"] = True
    label_mat = make_principled("MI_INT20_R2_LABEL_OFFWHITE", (0.92, 0.95, 0.92, 1.0), 0.0, 0.65)
    guide_mat = make_principled("MI_INT20_R2_CYAN_SECTION_GUIDE_RESTRAINED", (0.48, 0.82, 0.86, 1.0), 0.0, 0.58)
    aux_objects = []

    def link_aux(obj: Any) -> None:
        aux_collection.objects.link(obj)
        try:
            bpy.context.scene.collection.objects.unlink(obj)
        except Exception:
            pass
        obj["bf3d_stage"] = STAGE_ID
        obj["confidence"] = "E"
        obj["derivation"] = "illustrative_visual_label_or_guide"
        obj["not_as_built"] = True
        aux_objects.append(obj.name)

    def add_label(name: str, body: str, location: tuple[float, float, float], size: float = 0.32) -> Any:
        curve = bpy.data.curves.new(name + "_CURVE", "FONT")
        curve.body = body
        curve.align_x = "CENTER"
        curve.align_y = "CENTER"
        curve.size = size
        obj = bpy.data.objects.new(name, curve)
        obj.location = location
        obj.rotation_euler = (math.radians(68), 0.0, math.radians(0))
        obj.data.materials.append(label_mat)
        bpy.context.scene.collection.objects.link(obj)
        link_aux(obj)
        obj.hide_render = True
        obj.hide_viewport = True
        return obj

    def add_polyline(name: str, points: list[tuple[float, float, float]], mat: Any, bevel: float = 0.012) -> Any:
        curve = bpy.data.curves.new(name + "_CURVE", "CURVE")
        curve.dimensions = "3D"
        curve.resolution_u = 2
        curve.bevel_depth = bevel
        curve.bevel_resolution = 2
        spl = curve.splines.new("POLY")
        spl.points.add(len(points) - 1)
        for point, co in zip(spl.points, points):
            point.co = (co[0], co[1], co[2], 1.0)
        obj = bpy.data.objects.new(name, curve)
        obj.data.materials.append(mat)
        bpy.context.scene.collection.objects.link(obj)
        link_aux(obj)
        obj.hide_render = True
        obj.hide_viewport = True
        return obj

    cut_angle = math.radians(float(int10_manifest["variants"]["half"]["angle_start_deg"]))
    for layer_id in ("steel_shell", "cooling_wall", "refractory_lining"):
        outer_key, inner_key = profile_by_layer[layer_id]
        for key, suffix in ((outer_key, "OUTER"), (inner_key, "INNER")):
            points = [(interp_radius(float(item["z_blender_m"]), key) * math.cos(cut_angle), interp_radius(float(item["z_blender_m"]), key) * math.sin(cut_angle), float(item["z_blender_m"])) for item in profile]
            add_polyline(f"APPROX_GL02_INT20_R2_SECTION_GUIDE_{layer_id.upper()}_{suffix}", points, guide_mat, 0.01)
    add_label("APPROX_GL02_INT20_R2_LABEL_STEEL", "Steel shell E 45-65mm", (5.4, -0.55, 4.0), 0.28)
    add_label("APPROX_GL02_INT20_R2_LABEL_COOLING", "Cooling wall E estimate", (4.9, -0.25, 2.8), 0.26)
    add_label("APPROX_GL02_INT20_R2_LABEL_REFRACTORY", "Refractory E estimate", (4.3, 0.05, 1.6), 0.26)

    swatch_specs = [
        ("STEEL_BODY", material_families["steel_shell"]["body"], (-2.7, 0.0, 0.55)),
        ("STEEL_CUT", material_families["steel_shell"]["cut"], (-1.8, 0.0, 0.55)),
        ("COOLING_CUT", material_families["cooling_wall"]["cut"], (-0.9, 0.0, 0.55)),
        ("REFRACTORY_CUT", material_families["refractory_lining"]["cut"], (0.0, 0.0, 0.55)),
        ("PROCESS_LOW_ALPHA", material_families["process_space"]["body"], (0.9, 0.0, 0.55)),
    ]
    for swatch_name, mat, loc in swatch_specs:
        bpy.ops.mesh.primitive_cube_add(size=0.62, location=loc)
        obj = bpy.context.object
        obj.name = f"APPROX_GL02_INT20_R2_COLORCARD_{swatch_name}"
        obj.data.name = obj.name + "_MESH"
        obj.data.materials.append(mat)
        link_aux(obj)
        obj.hide_render = True
        obj.hide_viewport = True
        add_label(f"APPROX_GL02_INT20_R2_COLORCARD_LABEL_{swatch_name}", swatch_name.replace("_", " "), (loc[0], -0.68, 0.12), 0.13)

    def ensure_camera(name: str, location: tuple[float, float, float], target: tuple[float, float, float], projection: str, lens: float = 58.0, ortho_scale: float = 12.0) -> Any:
        cam = bpy.data.objects.get(name)
        if cam is None:
            data = bpy.data.cameras.new(name + "_DATA")
            cam = bpy.data.objects.new(name, data)
            bpy.context.scene.collection.objects.link(cam)
        cam.location = location
        cam.data.type = projection
        cam.data.lens = lens
        cam.data.ortho_scale = ortho_scale
        cam.data.clip_end = 300.0
        look_at(cam, target)
        return cam

    cameras = {
        "FRONT_CONTEXT": ensure_camera("INT20_R2_CAM_FRONT_CONTEXT_ORTHO", (0.0, -30.0, 2.2), (0.0, 0.0, 0.0), "ORTHO", ortho_scale=48.0),
        "HALF_CUT": ensure_camera("INT20_R2_CAM_HALF_CUT_45_ORTHO", (11.5, -18.0, 5.5), (0.0, 0.0, -0.5), "ORTHO", ortho_scale=72.0),
        "QUARTER_CUT": ensure_camera("INT20_R2_CAM_QUARTER_CUT_45_ORTHO", (15.0, -17.0, 6.4), (0.0, 0.0, -0.5), "ORTHO", ortho_scale=72.0),
        "EXPLODED_CUT": ensure_camera("INT20_R2_CAM_EXPLODED_CUT_45_ORTHO", (13.0, -18.5, 6.0), (0.3, 0.0, -0.2), "ORTHO", ortho_scale=72.0),
        "SECTION_CLOSEUP": ensure_camera("INT20_R2_CAM_SECTION_CLOSEUP_PERSP", (5.5, -16.0, -2.2), (1.0, 0.0, -2.8), "PERSP", lens=52.0, ortho_scale=7.0),
        "COLORCARD": ensure_camera("INT20_R2_CAM_COLORCARD_PERSP", (0.0, -6.2, 1.1), (0.0, 0.0, 0.45), "PERSP", lens=54.0, ortho_scale=4.0),
    }

    def set_visible(mode: str) -> None:
        for name in all_int10_names + aux_objects:
            obj = bpy.data.objects.get(name)
            if obj:
                obj.hide_render = True
                obj.hide_viewport = True
        visible_layers = ("steel_shell", "cooling_wall", "refractory_lining")
        if mode == "front":
            for name in layer_object_names["steel_shell"]:
                if name.endswith("_FULL"):
                    bpy.data.objects[name].hide_render = False
                    bpy.data.objects[name].hide_viewport = False
        elif mode in ("half", "exploded", "closeup"):
            for layer_id in visible_layers:
                for name in layer_object_names[layer_id]:
                    if name.endswith("_HALF"):
                        bpy.data.objects[name].hide_render = False
                        bpy.data.objects[name].hide_viewport = False
            for name in aux_objects:
                if "COLORCARD" not in name and (mode == "closeup" or "SECTION_GUIDE" in name):
                    bpy.data.objects[name].hide_render = False
                    bpy.data.objects[name].hide_viewport = False
        elif mode == "quarter":
            for layer_id in visible_layers:
                for name in layer_object_names[layer_id]:
                    if name.endswith("_QUARTER"):
                        bpy.data.objects[name].hide_render = False
                        bpy.data.objects[name].hide_viewport = False
            for name in aux_objects:
                if "SECTION_GUIDE" in name:
                    bpy.data.objects[name].hide_render = False
                    bpy.data.objects[name].hide_viewport = False
        elif mode == "colorcard":
            for name in aux_objects:
                if "COLORCARD" in name:
                    bpy.data.objects[name].hide_render = False
                    bpy.data.objects[name].hide_viewport = False

    def apply_exploded_offsets(enable: bool) -> None:
        offsets = {
            "steel_shell": Vector((-0.62, -0.08, 0.0)),
            "cooling_wall": Vector((0.0, 0.0, 0.0)),
            "refractory_lining": Vector((0.62, 0.08, 0.0)),
        }
        for layer_id, offset in offsets.items():
            for obj_name in layer_object_names[layer_id]:
                if obj_name.endswith("_HALF"):
                    bpy.data.objects[obj_name].location = offset if enable else Vector((0.0, 0.0, 0.0))

    render_specs = [
        ("FRONT_CONTEXT", "front", "complete_outer_context_with_old_process_content_hidden", "ORTHO"),
        ("HALF_CUT", "half", "bright_45_degree_half_cut_solid_thickness", "ORTHO"),
        ("QUARTER_CUT", "quarter", "bright_45_degree_quarter_cut_solid_thickness", "ORTHO"),
        ("EXPLODED_CUT", "exploded", "render_only_air_gaps_between_shell_cooling_refractory", "ORTHO"),
        ("SECTION_CLOSEUP", "closeup", "perspective_closeup_of_actual_cutface_materials", "PERSP"),
        ("COLORCARD", "colorcard", "material_colorcard_for_body_and_cutface_families", "PERSP"),
    ]
    evidence_renders = []
    for render_id, mode, purpose, projection in render_specs:
        set_visible(mode)
        apply_exploded_offsets(mode == "exploded")
        scene.camera = cameras[render_id]
        render_path = render_dir / f"INT20_R2_{render_id}.png"
        scene.render.filepath = str(render_path)
        bpy.ops.render.render(write_still=True)
        apply_exploded_offsets(False)
        if not render_path.is_file() or render_path.stat().st_size <= 1024:
            raise RuntimeError(f"Render failed: {render_path}")
        evidence_renders.append(
            {
                "id": render_id,
                "file": render_path.name,
                "path": str(render_path),
                "camera": scene.camera.name,
                "projection": projection,
                "purpose": purpose,
                "resolution_px": [args.width, args.height],
                "engine": scene.render.engine,
                "lookdev": "bright_neutral_softbox_agx_no_bloom_freestyle_restrained",
                "process_space": "hidden_for_cut_views_or_low_alpha_material_only",
                "bytes": render_path.stat().st_size,
                "sha256": sha256_file(render_path),
            }
        )

    apply_exploded_offsets(False)
    set_visible("quarter")
    for name in int10_report.get("hidden_explanatory_objects", []):
        obj = bpy.data.objects.get(name)
        if obj:
            obj.hide_viewport = True
            obj.hide_render = True

    after_protected = protected_snapshot()
    after_int10_signature = object_signature(all_int10_names)
    int10_preserved = before_int10_signature == after_int10_signature
    protected_contract = {
        "sensor_count_before": before_protected["sensor_count"],
        "sensor_count_after": after_protected["sensor_count"],
        "body_temp_sensor_count_before": before_protected["body_temp_sensor_count"],
        "body_temp_sensor_count_after": after_protected["body_temp_sensor_count"],
        "sensor_signature_before": before_protected["sensor_signature_sha256"],
        "sensor_signature_after": after_protected["sensor_signature_sha256"],
        "sensor_names_parents_matrices_unchanged": before_protected["sensor_signature_sha256"] == after_protected["sensor_signature_sha256"],
        "l7_l16_groups_present": all(f"GL02_SENSOR_LAYER_L{i}" in after_protected["layer_groups"] for i in range(7, 17)),
        "five_furnace_segments_present": len(after_protected["furnace_segments"]) >= 5,
        "old_55_explanatory_objects_hidden_count": len([name for name in int10_report.get("hidden_explanatory_objects", []) if bpy.data.objects.get(name) and bpy.data.objects[name].hide_render]),
        "old_55_explanatory_objects_expected_count": len(int10_report.get("hidden_explanatory_objects", [])),
    }

    shell_audits = {
        name: audit
        for name, audit in object_audits.items()
        if audit["layer_id"] in ("steel_shell", "cooling_wall", "refractory_lining")
    }
    solid_pass = all(
        audit["has_outer_surface"]
        and audit["has_inner_surface"]
        and audit["has_cut_caps"]
        and audit["positive_volume"]
        and audit["cutface_material_faces"] > 0
        for audit in shell_audits.values()
    )
    manifest = {
        "schema_version": "bf3d.int20_r2.solid_thickness.v1",
        "requirement_id": REQUIREMENT_ID,
        "stage": STAGE_ID,
        "status": "candidate_ready_for_review",
        "approval": "not_granted_requires_visual_and_spec_review",
        "input": {
            "path": str(input_blend),
            "expected_sha256": EXPECTED_INPUT_SHA256,
            "actual_sha256": sha256_file(input_blend),
            "sha256_match": sha256_file(input_blend).lower() == EXPECTED_INPUT_SHA256,
        },
        "thickness_assumptions": {
            "confidence": "E",
            "engineering_dimensions_claimed": False,
            "steel_shell_m": {
                "range_m": [0.045, 0.065],
                "range_mm": [45, 65],
                "source": "INT-10 manifest E-grade shell estimate",
            },
            "cooling_wall_m": {
                "source": "INT-10 manifest E-grade values, zone dependent",
                "values_from_manifest": int10_manifest["thickness_assumptions"]["cooling_wall_m"],
            },
            "refractory_lining_m": {
                "source": "INT-10 manifest E-grade values, zone dependent",
                "values_from_manifest": int10_manifest["thickness_assumptions"]["refractory_lining_m"],
            },
        },
        "visual_bible_hard_gate": {
            "zero_thickness_sections_forbidden": True,
            "primary_layers_required_closed_visible_solids": ["steel_shell", "cooling_wall", "refractory_lining"],
            "process_space_low_occlusion_or_hidden": True,
            "cutface_materials_separate_from_body": True,
            "glb_exported": False,
            "blend1_generated": False,
        },
        "int10_object_contract": {
            "object_count": len(all_int10_names),
            "names": sorted(all_int10_names),
            "names_matrices_geometry_preserved": int10_preserved,
        },
        "material_families": {
            layer_id: {"body": mats["body"].name, "cutface": mats["cut"].name, "label": mats["label"]}
            for layer_id, mats in material_families.items()
        },
        "object_audits": object_audits,
        "auxiliary_guides_and_labels": sorted(aux_objects),
        "protected_contract": protected_contract,
    }
    write_json(output_dir / "int20_r2_solid_thickness_manifest.json", manifest)

    scene["bf3d_stage"] = "INT_20_R2_SOLID_THICKNESS_CUTAWAY_CANDIDATE"
    scene["bf3d_requirement_id"] = REQUIREMENT_ID
    scene["bf3d_status"] = "candidate_ready_for_review"
    scene["bf3d_approval"] = "not_granted_requires_visual_and_spec_review"
    scene["bf3d_input_sha256"] = EXPECTED_INPUT_SHA256
    scene["bf3d_formal_glb_exported"] = False
    scene.camera = cameras["QUARTER_CUT"]
    bpy.ops.wm.save_as_mainfile(filepath=str(output_blend))
    if list(output_dir.glob("*.blend1")):
        raise RuntimeError(".blend1 backup generated; save_version=0 contract failed")

    candidate_sha = sha256_file(output_blend)
    assertions = {
        "input_sha256_matches": sha256_file(input_blend).lower() == EXPECTED_INPUT_SHA256,
        "protected_contract_pass": protected_contract["sensor_count_after"] == 115
        and protected_contract["body_temp_sensor_count_after"] == 80
        and protected_contract["sensor_names_parents_matrices_unchanged"]
        and protected_contract["l7_l16_groups_present"]
        and protected_contract["five_furnace_segments_present"]
        and protected_contract["old_55_explanatory_objects_hidden_count"] == protected_contract["old_55_explanatory_objects_expected_count"],
        "int10_12_names_matrices_geometry_preserved": int10_preserved,
        "non_manifold_edges_zero": all(audit["non_manifold_edges"] == 0 for audit in object_audits.values()),
        "solid_surface_cap_volume_pass": solid_pass,
        "cutface_material_assignment_pass": all(audit["cutface_material_faces"] > 0 for audit in object_audits.values()),
        "renders_exist_pass": len(evidence_renders) == 6 and all(item["bytes"] > 1024 for item in evidence_renders),
        "formal_glb_not_exported": True,
        "blend1_not_generated": not list(output_dir.glob("*.blend1")),
    }
    report = {
        "schema_version": "bf3d.int20_r2.machine_report.v1",
        "requirement_id": REQUIREMENT_ID,
        "stage": STAGE_ID,
        "status": "candidate_ready_for_review",
        "approval": "not_granted_requires_visual_and_spec_review",
        "generated_at": utc_now_iso(),
        "single_changed_dimension": "solid_thickness_cutaway_material_readability_only",
        "input": manifest["input"],
        "candidate": {
            "path": str(output_blend),
            "bytes": output_blend.stat().st_size,
            "sha256": candidate_sha,
        },
        "blender": {
            "version": bpy.app.version_string,
            "binary_path": bpy.app.binary_path,
            "background": bpy.app.background,
            "render_engine": scene.render.engine,
            "render_resolution": [args.width, args.height],
        },
        "protected_contract": protected_contract,
        "int10_object_contract": manifest["int10_object_contract"],
        "solid_thickness_manifest": str(output_dir / "int20_r2_solid_thickness_manifest.json"),
        "evidence_renders": evidence_renders,
        "assertions": assertions,
        "known_issues": [
            "R2 keeps INT-10 E-grade approximate geometry and does not claim measured engineering dimensions.",
            "Steel shell 45-65mm, cooling wall and refractory thicknesses are manifest-derived E estimates only.",
            "No formal GLB was exported; visual/spec review is still required before any next stage.",
        ],
        "stop_lines": [
            "Do not proceed beyond candidate_ready_for_review without independent visual and spec review.",
            "Do not export a formal GLB from INT-20 R2.",
            "Stop if any protected SENSOR, BODY_TEMP, L7-L16 group, five furnace segment, or old explanatory object visibility contract changes.",
        ],
        "formal_asset_changes": {
            "formal_glb_exported": False,
            "r1_modified": False,
            "frontend_modified": False,
            "pipeline_status_modified": False,
        },
    }
    write_json(output_dir / "int20_r2_machine_report.json", report)
    print(
        json.dumps(
            {
                "status": report["status"],
                "approval": report["approval"],
                "candidate": report["candidate"],
                "renders": len(evidence_renders),
                "assertions_pass_before_reopen": all(assertions.values()),
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


def reopen_validate() -> int:
    import bmesh
    import bpy

    args = blender_args()
    output_dir = args.output_dir.resolve()
    output_blend = output_dir / OUTPUT_BLEND_NAME
    manifest_path = output_dir / "int20_r2_solid_thickness_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

    def matrix_values(obj: Any) -> list[float]:
        return [round(float(value), 9) for row in obj.matrix_world for value in row]

    sensors = sorted((obj for obj in bpy.data.objects if obj.name.startswith("SENSOR_")), key=lambda obj: obj.name)
    body_temp = [obj for obj in sensors if obj.name.startswith("SENSOR_T_body_")]
    sensor_records = {obj.name: {"parent": obj.parent.name if obj.parent else None, "matrix": matrix_values(obj)} for obj in sensors}
    sensor_sig = hashlib.sha256(json.dumps(sensor_records, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()

    object_recheck = {}
    for obj_name, original in manifest["object_audits"].items():
        obj = bpy.data.objects.get(obj_name)
        if obj is None or obj.type != "MESH":
            object_recheck[obj_name] = {"exists": False}
            continue
        bm = bmesh.new()
        bm.from_mesh(obj.data)
        bm.normal_update()
        non_manifold_edges = sum(1 for edge in bm.edges if not edge.is_manifold)
        volume = abs(float(bm.calc_volume()))
        bm.free()
        cutface_faces = sum(1 for poly in obj.data.polygons if poly.material_index == 1)
        object_recheck[obj_name] = {
            "exists": True,
            "non_manifold_edges": non_manifold_edges,
            "positive_volume": volume > 1e-6,
            "cutface_material_faces": cutface_faces,
            "material_slots": [slot.material.name if slot.material else None for slot in obj.material_slots],
            "matches_manifest_non_manifold_zero": non_manifold_edges == original["non_manifold_edges"] == 0,
        }

    expected_renders = [
        "INT20_R2_FRONT_CONTEXT.png",
        "INT20_R2_HALF_CUT.png",
        "INT20_R2_QUARTER_CUT.png",
        "INT20_R2_EXPLODED_CUT.png",
        "INT20_R2_SECTION_CLOSEUP.png",
        "INT20_R2_COLORCARD.png",
    ]
    render_presence = {
        name: (output_dir / "renders" / name).is_file() and (output_dir / "renders" / name).stat().st_size > 1024
        for name in expected_renders
    }
    validation = {
        "schema_version": "bf3d.int20_r2.reopen_validation.v1",
        "stage": STAGE_ID,
        "candidate_reopened_without_error": True,
        "candidate_path": str(output_blend),
        "scene_stage": bpy.context.scene.get("bf3d_stage"),
        "candidate_sha256": sha256_file(output_blend),
        "sensor_count": len(sensors),
        "body_temp_sensor_count": len(body_temp),
        "sensor_signature_sha256": sensor_sig,
        "object_recheck": object_recheck,
        "all_int10_objects_exist": all(item.get("exists") for item in object_recheck.values()),
        "all_non_manifold_edges_zero": all(item.get("non_manifold_edges") == 0 for item in object_recheck.values()),
        "all_positive_volume": all(item.get("positive_volume") for item in object_recheck.values()),
        "all_cutface_materials_present": all(item.get("cutface_material_faces", 0) > 0 for item in object_recheck.values()),
        "renders_present": render_presence,
        "blend1_not_present": not list(output_dir.glob("*.blend1")),
    }
    validation["status"] = "pass" if (
        validation["sensor_count"] == 115
        and validation["body_temp_sensor_count"] == 80
        and validation["all_int10_objects_exist"]
        and validation["all_non_manifold_edges_zero"]
        and validation["all_positive_volume"]
        and validation["all_cutface_materials_present"]
        and all(validation["renders_present"].values())
        and validation["blend1_not_present"]
    ) else "fail"
    write_json(output_dir / "reopen_validation.json", validation)
    print(json.dumps(validation, ensure_ascii=False, indent=2))
    return 0 if validation["status"] == "pass" else 1


if __name__ == "__main__":
    if "--inside-blender" in sys.argv:
        sys.exit(blender_main())
    if "--reopen-validate" in sys.argv:
        sys.exit(reopen_validate())
    sys.exit(host_main())
