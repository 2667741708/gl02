"""Finalize the WEB-60 R2V V5 static material/section review checkpoint.

This command is intentionally fail-closed.  It does not rebuild or mutate any
GLB/Blend asset.  It only reads the completed R2V validation evidence, verifies
the locked outputs and protected historical assets, then writes the controlled
manifest, stage status, artifact inventory and root pipeline entry.

Run:
    python tools/finalize_bf3d_review_v5.py
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Callable


ROOT = Path(__file__).resolve().parents[1]
STAGE = (
    ROOT
    / "PT"
    / "高炉3D模型"
    / "work"
    / "WEB_60_20260720_R2V_GLTF_PORTABILITY_TANGENT_BUDGET"
)
REPORT_DIR = STAGE / "reports"
PREVIEW_DIR = STAGE / "preview"
RENDER_DIR = STAGE / "renders"
MODEL_DIR = ROOT / "高炉前端数据" / "models"

MAIN_GLB = MODEL_DIR / "gl02_blast_furnace_review.v5.glb"
MATERIAL_GLB = MODEL_DIR / "gl02_blast_furnace_material_review.v5.glb"
STRUCTURAL_GLB = MODEL_DIR / "gl02_blast_furnace_structural_review.v5.glb"
REVIEW_BLEND = MODEL_DIR / "gl02_blast_furnace_review.v5.blend"
MODEL_MANIFEST = MODEL_DIR / "gl02_blast_furnace_review.v5.manifest.json"
FORMAL_GLB = MODEL_DIR / "gl02_blast_furnace.glb"

REQUIREMENT_ID = "REQ-BF3D-R2V-GLTF-PORTABILITY-TANGENT-BUDGET-20260720"
WEB_REQUIREMENT_ID = "REQ-BF3D-R2V-ISOLATED-WEB-REVIEW-20260720"
STAGE_ID = "WEB_60_20260720_R2V_GLTF_PORTABILITY_TANGENT_BUDGET"
ASSET_ID = "GL02_GLTF_PORTABLE_TANGENT_COMPLETE_V5"
STATUS = "r2v_static_review_scope_passed_release_gates_pending"
FORMAL_SHA256 = "808960f1b2703e7fb27df35f1b1b1a17063b9b10d2267acba593fc3872b62af6"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def rel(path: Path) -> str:
    return path.resolve().relative_to(ROOT.resolve()).as_posix()


def artifact(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise RuntimeError(f"Required artifact is missing: {path}")
    return {
        "path": rel(path),
        "bytes": path.stat().st_size,
        "sha256": sha256(path),
    }


def load_json(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise RuntimeError(f"Required JSON is missing: {path}")
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise RuntimeError(f"Expected JSON object: {path}")
    return value


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def passed(value: dict[str, Any]) -> bool:
    return value.get("passed") is True


REPORT_RULES: dict[str, Callable[[dict[str, Any]], bool]] = {
    "input_gate_validation.json": passed,
    "scene_provenance_sanitization.json": passed,
    "geometry_equivalence_validation.json": passed,
    "tangent_preflight_validation.json": passed,
    "glb_tangent_vector_sanitization.json": passed,
    "section_topology_validation.json": passed,
    "section_cap_overlap_validation.json": passed,
    "material_identity_validation.json": passed,
    "glb_portability_export_validation.json": passed,
    "build_report.json": passed,
    "visual_manifest.json": passed,
    "blend_reopen_validation.json": passed,
    "factory_import_validation.json": passed,
    "derived_glb_factory_import_validation.json": passed,
    "khronos_gltf_validator_v5.json": passed,
    "web_review_build_report.json": passed,
    "v5_portability_audit.json": lambda value: value.get("release_ready") is True,
    "bf3d_review_v5_preview_report.json": lambda value: (
        value.get("overall_status") == "full_matrix_passed_illustrative_only"
        and value.get("stability_gate_passed") is True
        and value.get("total_viewport_runs") == 34
        and value.get("total_passed_runs") == 34
        and value.get("total_failed_runs") == 0
        and value.get("total_screenshot_captures") == 102
        and value.get("protected_files_unchanged") is True
        and all(
            value.get("error_totals", {}).get(name) == 0
            for name in (
                "console",
                "page",
                "http",
                "external",
                "request_failed",
            )
        )
    ),
    "independent_review_decisions.json": lambda value: (
        value.get("overall_decision")
        == "R2V_V5_ISOLATED_STATIC_REVIEW_ACCEPTED_RELEASE_GATES_BLOCKED"
    ),
}


def validate_reports() -> dict[str, dict[str, Any]]:
    reports: dict[str, dict[str, Any]] = {}
    for name, rule in REPORT_RULES.items():
        value = load_json(REPORT_DIR / name)
        require(
            value.get("requirement_id")
            in (None, REQUIREMENT_ID, WEB_REQUIREMENT_ID),
            f"Requirement ID mismatch in {name}",
        )
        require(rule(value), f"Required R2V report did not pass: {name}")
        reports[name] = value
    return reports


def validate_outputs(build: dict[str, Any]) -> dict[str, dict[str, Any]]:
    paths = {
        "main_glb": MAIN_GLB,
        "material_glb": MATERIAL_GLB,
        "structural_glb": STRUCTURAL_GLB,
        "direct_open_blend": REVIEW_BLEND,
    }
    current = {name: artifact(path) for name, path in paths.items()}
    require(
        build.get("outputs") == current,
        "Current V5 outputs do not match the locked build report",
    )
    require(
        artifact(FORMAL_GLB)["sha256"] == FORMAL_SHA256,
        "Formal GLB changed during R2V",
    )
    return current


def validate_protected_assets() -> None:
    lock = load_json(STAGE / "input_lock.json")
    before = lock.get("protected_assets_before_build", {})
    require(isinstance(before, dict) and before, "Protected asset lock is empty")
    for relative_path, expected in before.items():
        current = artifact(ROOT / relative_path)
        require(
            current == expected,
            f"Protected asset changed after R2V: {relative_path}",
        )


def build_core(
    reports: dict[str, dict[str, Any]],
    outputs: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    portability = reports["v5_portability_audit.json"]["summary"]
    preview = reports["bf3d_review_v5_preview_report.json"]
    tangents = reports["glb_tangent_vector_sanitization.json"]["assets"]
    main_tangent = tangents["main"]
    material_tangent = tangents["material"]
    structural_tangent = tangents["structural"]
    geometry = reports["geometry_equivalence_validation.json"]
    topology = reports["section_topology_validation.json"]
    overlap = reports["section_cap_overlap_validation.json"]
    khronos = reports["khronos_gltf_validator_v5.json"]

    require(len(geometry.get("objects", [])) == 10, "Geometry equivalence must cover 10 objects")
    require(len(topology.get("objects", [])) == 10, "Topology report must cover 10 objects")
    require(not overlap.get("overlap_pairs"), "Section overlap pairs are not zero")
    require(
        main_tangent.get("zero_length_fallbacks") == 3
        and structural_tangent.get("zero_length_fallbacks") == 3
        and material_tangent.get("zero_length_fallbacks") == 0,
        "Unexpected V5 zero-tangent fallback count",
    )
    require(
        sum(
            item.get("non_unit_renormalized", 0)
            for item in (main_tangent, material_tangent, structural_tangent)
        )
        == 0,
        "V5 must not renormalize valid non-zero tangent vectors",
    )
    require(
        all(
            asset.get("issue_counts", {}).get("errors") == 0
            and asset.get("issue_counts", {}).get("warnings") == 0
            for asset in khronos.get("assets", [])
        ),
        "Khronos issue counts are not 0/0 for every V5 GLB",
    )

    validation_reports = {
        name: artifact(REPORT_DIR / name) for name in REPORT_RULES
    }
    return {
        "schema_version": "bf3d.r2v.gltf_portability_tangent_budget.v5",
        "requirement_id": REQUIREMENT_ID,
        "stage_id": STAGE_ID,
        "asset_id": ASSET_ID,
        "status": STATUS,
        "r2v_scope_passed": True,
        "next_controlled_work_allowed": True,
        "next_release_stage_allowed": False,
        "approval_granted": False,
        "production_integration_allowed": False,
        "evidence": "E/illustrative",
        "reference_status": "REF-PENDING",
        "not_for_construction": True,
        "scope": {
            "material_group": "5 R2J complete shell objects",
            "section_group": "10 R2J/R2K closed physical half-section objects",
            "review_modes": ["纯材质审查", "结构剖面"],
            "material_subviews": ["外表面", "内部层近景"],
            "forbidden_review_content": [
                "传感器",
                "数据引线",
                "黄色轮廓",
                "工艺粒子",
                "旧固定圆环",
                "装饰性竖线或流线",
            ],
            "controlled_changes": [
                "10 section meshes deterministically triangulated",
                "4 local absolute provenance values converted to relative POSIX paths",
                "3 undefined tangent vertices repaired in each affected GLB using the exported normal",
            ],
            "explicit_non_changes": [
                "V4 vertex positions, bounds, material slots and UV bounds",
                "V4 embedded image payloads and material contracts",
                "formal production GLB",
                "P50/P60/P70/QA70 approval state",
            ],
        },
        "outputs": outputs,
        "hard_gates": {
            "material_objects": 5,
            "section_objects": 10,
            "all_sections_closed_positive": True,
            "boundary_edge_count_total": 0,
            "non_manifold_edge_count_total": 0,
            "cross_object_cap_overlap_pairs": 0,
            "cross_object_cap_overlap_area_m2": 0.0,
            "geometry_equivalence_objects": 10,
            "absolute_path_count": portability["local_absolute_path_count"],
            "normal_mapped_primitives_without_tangent": portability[
                "normal_mapped_primitives_without_tangent"
            ],
            "invalid_explicit_tangent_accessors": portability[
                "invalid_explicit_tangent_accessors"
            ],
            "unique_undefined_tangent_vertices": 3,
            "glb_tangent_vector_writes": 6,
            "nonzero_tangent_vectors_renormalized": 0,
            "khronos_errors": 0,
            "khronos_warnings": 0,
            "factory_import_three_glbs": True,
            "protected_assets_unchanged": True,
        },
        "web_matrix": {
            "engines": ["chromium", "firefox", "webkit"],
            "stability_iterations": preview["stability_iterations_completed"],
            "total_viewport_runs": preview["total_viewport_runs"],
            "passed_viewport_runs": preview["total_passed_runs"],
            "failed_viewport_runs": preview["total_failed_runs"],
            "total_screenshot_captures": preview["total_screenshot_captures"],
            "error_totals": preview["error_totals"],
            "protected_files_unchanged": preview["protected_files_unchanged"],
            "status": preview["overall_status"],
        },
        "texture_memory_boundary": {
            "decoded_rgba8_mib_all_three_assets": portability["decoded_rgba8_mib"],
            "decoded_rgba8_full_mips_mib_all_three_assets": portability[
                "decoded_rgba8_with_full_mips_mib"
            ],
            "disposition": "measured_not_optimized_mobile_and_field_performance_pending",
        },
        "independent_review": {
            "visual_blender": "CONDITIONAL_PASS_R2V_ONLY",
            "visual_threejs": "PASS_R2V_ONLY",
            "spec": "CONDITIONAL_R2V_PASS_RELEASE_BLOCKED",
            "frontend": "PASS_IN_ISOLATED_V5_SCOPE_RELEASE_BLOCKED",
            "root": "R2V_V5_ISOLATED_STATIC_REVIEW_ACCEPTED_RELEASE_GATES_BLOCKED",
        },
        "validation_reports": validation_reports,
        "pending": {
            "exterior_ao_consumption_and_p50": "pending",
            "p60": "pending",
            "p70": "pending",
            "qa70": "pending",
            "three_blender_photometric_equivalence": "pending_not_approved",
            "production_8092_integration": "pending_not_approved",
            "field_edge_and_mobile_memory_performance": "pending",
        },
        "historical_assets_overwritten": False,
        "formal_glb": artifact(FORMAL_GLB),
    }


def write_summary(core: dict[str, Any]) -> Path:
    path = STAGE / "WEB-60_R2V_阶段成果总结.md"
    outputs = core["outputs"]
    text = f"""# WEB-60 R2V V5 可移植静态审查资产

- R2V 范围结论：`PASS`；发布门结论：`BLOCKED`。
- 边界：`E/illustrative`、`REF-PENDING`、`not_for_construction=true`。
- 受控资产：5 个 R2J 完整炉壳、10 个 R2J/R2K 闭合物理半剖；纯材质审查隐藏传感器、数据引线、黄色轮廓、工艺粒子、旧圆环和装饰性竖线。
- V5 GLB：绝对路径 `0`、缺失切线风险 `0`、无效切线 accessor `0`；Khronos 三资产均 `0 errors / 0 warnings`。
- 切线最小修复：同一 3 个未定义顶点分别出现在统一 GLB 与结构 GLB，共写入 6 个向量；有效非零切线未被重归一化。
- Three.js：Chromium/Firefox/WebKit 连续两轮共 `34/34` 视口运行、`102` 次截图，五类错误均为 `0`。
- 统一 GLB：`{outputs["main_glb"]["sha256"]}`。
- Blender 直接打开文件：`{outputs["direct_open_blend"]["path"]}`。
- 未批准：正式 8092 替换、P50/P60/P70/QA-70、现场 Edge、移动端内存/性能、Blender/Three 数值光度等价。
"""
    path.write_text(text, encoding="utf-8")
    return path


def write_root_conclusion(core: dict[str, Any]) -> Path:
    path = STAGE / "WEB-60_R2V_根审查结论.md"
    outputs = core["outputs"]
    text = f"""# WEB-60 R2V V5 根审查结论

结论：V5 已在隔离静态审查范围内通过。它解决了 V4 的本机绝对路径和运行时生成切线警告，
并保留 R5/R2J 外表面、R2J 五区实体和 R2K 内部层材质。它不是生产或施工资产，
`approval_granted=false`、`production_integration_allowed=false`。

## 1. 为什么此前看不到材质

用户截图仍停留在 Blender 的 glTF 导入窗口，右下角“导入 glTF 2.0”尚未执行；选中的还是
历史 `structural_review.v1.glb`。即使完成导入，Solid/实体视图也不会显示完整 PBR 贴图，
需要切换到“材质预览”或“渲染”。历史 V1 还包含依赖网页控制器隐藏的圆环、竖线、传感器
与工艺对象，Blender 导入器不会执行 Three.js 控制器，所以会再次显示。

## 2. 当前应打开的文件

- Blender 首选：`{outputs["direct_open_blend"]["path"]}`
- 统一 Web GLB：`{outputs["main_glb"]["path"]}`
- 仅外表面材质：`{outputs["material_glb"]["path"]}`
- 仅结构剖面：`{outputs["structural_glb"]["path"]}`

V5 Blend 已通过重开验证，默认显示结构剖面、隐藏完整外壳集合，Layout/Modeling 均固定为
材质预览，主要贴图已打包。受控 GLB 中不含传感器、数据引线、黄色轮廓、工艺粒子、
旧固定圆环或装饰性竖向流线。

## 3. 可见材质与结构

纯材质审查提供“外表面”和“内部层近景”；结构剖面显示 10 个闭合物理 Section。
内部层包括内侧钢、背衬填料、铸铁/铜冷却壁、热面层与残余耐火层。当前颜色、粗糙度和
Normal/ORM 可见，但属于 `E/illustrative`；没有现场材质牌号、真实磨损厚度或施工尺寸时，
不得把它解释成真实炉衬测量结果。

## 4. 验证结果

- V4 到 V5 的 10 个 Section 顶点位置、包围盒、材质槽和 UV 边界保持；三角化后仍为
  `10/10` 闭合正体积，boundary/non-manifold 与跨对象封口重叠均为 `0`。
- 三份 V5 GLB 的本机绝对路径、缺失切线风险和无效切线 accessor 均为 `0`。
- 只对 3 个未定义几何切线顶点做法线正交回退；统一 GLB 和结构 GLB 各写 3 个向量，
  有效非零切线未被改写。
- Khronos Validator：三份资产均 `0 errors / 0 warnings`。
- Blender 重开、三份 GLB factory import、Three.js GLTFLoader 均通过。
- Chromium/Firefox/WebKit 两轮矩阵共 `34/34` 视口运行、`102` 次截图；console、page、
  HTTP、external 与 request-failed 均为 `0`。

## 5. 仍未解除的停止线

- 三资产同时解码约 `720 MiB` RGBA8，完整 mip 估算约 `960 MiB`；这是测量结果，
  不是移动端或现场主机性能批准。
- `EXT_texture_webp` 对旧浏览器/受限运行时仍是条件兼容项。
- R5 外表面 AO 消费、P50、P60、P70、QA-70、现场 Edge、长稳、100 次模式切换以及
  Blender/Three 数值光度等价仍未完成。
- 正式 `gl02_blast_furnace.glb` 未替换，SHA-256 仍为 `{FORMAL_SHA256}`。

机器可读结论见 `reports/independent_review_decisions.json` 与
`reports/bf3d_review_v5_preview_report.json`。
"""
    path.write_text(text, encoding="utf-8")
    return path


def update_root_pipeline(core: dict[str, Any], summary: Path) -> None:
    path = ROOT / "reports" / "pipeline_status.json"
    if not path.is_file():
        return
    value = load_json(path)
    value["current_stage"] = STAGE_ID
    value["updated_at"] = "2026-07-20T18:20:00+08:00"
    value.setdefault("stages", {})[STAGE_ID] = {
        "status": STATUS,
        "r2v_scope_passed": True,
        "approval": "isolated_static_review_passed_release_not_granted",
        "approval_boundary": (
            "E/illustrative isolated V5 material/section review only; no "
            "production, P50/P60/P70/QA70 or photometric-equivalence approval."
        ),
        "input_lock": rel(STAGE / "input_lock.json"),
        "candidate_blend": rel(REVIEW_BLEND),
        "candidate_sha256": artifact(REVIEW_BLEND)["sha256"],
        "main_glb": rel(MAIN_GLB),
        "main_glb_sha256": artifact(MAIN_GLB)["sha256"],
        "material_glb": rel(MATERIAL_GLB),
        "material_glb_sha256": artifact(MATERIAL_GLB)["sha256"],
        "structural_glb": rel(STRUCTURAL_GLB),
        "structural_glb_sha256": artifact(STRUCTURAL_GLB)["sha256"],
        "formal_glb_sha256": artifact(FORMAL_GLB)["sha256"],
        "formal_glb_unchanged": True,
        "portability_report": rel(REPORT_DIR / "v5_portability_audit.json"),
        "khronos_report": rel(REPORT_DIR / "khronos_gltf_validator_v5.json"),
        "web_matrix_report": rel(REPORT_DIR / "bf3d_review_v5_preview_report.json"),
        "independent_review": rel(REPORT_DIR / "independent_review_decisions.json"),
        "summary": rel(summary),
        "next_stop_line": (
            "P50/P60/P70/QA70, field Edge, memory/performance and numerical "
            "photometric equivalence remain blocked"
        ),
    }
    write_json(path, value)


def write_artifact_manifest(
    core: dict[str, Any],
    summary: Path,
    conclusion: Path,
) -> None:
    paths = [
        Path(__file__).resolve(),
        ROOT / "tools" / "export_bf3d_structural_review_v5.py",
        ROOT / "tools" / "audit_bf3d_glb_portability.py",
        ROOT / "tools" / "diagnose_bf3d_v4_tangent_uv.py",
        ROOT / "tools" / "validate_bf3d_glb_khronos.cjs",
        ROOT / "tools" / "build_bf3d_review_v5_web.py",
        ROOT / "tools" / "serve_bf3d_review_v5.py",
        ROOT / "tools" / "verify_bf3d_review_v5_preview.cjs",
        ROOT / "高炉前端数据" / "bf3d_review_v5.server.html",
        ROOT / "高炉前端数据" / "assets" / "bf3d-review-renderer-v5.js",
        MAIN_GLB,
        MATERIAL_GLB,
        STRUCTURAL_GLB,
        REVIEW_BLEND,
        MODEL_MANIFEST,
        STAGE / "input_lock.json",
        STAGE / "pipeline_status.json",
        STAGE / "WEB-60_R2V_阶段验收合同.md",
        summary,
        conclusion,
        *sorted(REPORT_DIR.glob("*")),
        *sorted(RENDER_DIR.glob("*.png")),
        *sorted(PREVIEW_DIR.glob("*.json")),
        *sorted((PREVIEW_DIR / "screenshots").glob("*.png")),
    ]
    unique: dict[str, Path] = {}
    for path in paths:
        if path.is_file():
            unique[rel(path)] = path
    manifest = {
        "schema_version": "bf3d.r2v.artifact_manifest.v5",
        "requirement_id": REQUIREMENT_ID,
        "status": STATUS,
        "r2v_scope_passed": True,
        "next_release_stage_allowed": False,
        "artifact_count": len(unique),
        "artifacts": [artifact(unique[name]) for name in sorted(unique)],
    }
    write_json(STAGE / "artifact_manifest.json", manifest)


def main() -> int:
    reports = validate_reports()
    outputs = validate_outputs(reports["build_report.json"])
    validate_protected_assets()
    core = build_core(reports, outputs)
    write_json(MODEL_MANIFEST, core)
    write_json(STAGE / "pipeline_status.json", core)
    summary = write_summary(core)
    conclusion = write_root_conclusion(core)
    update_root_pipeline(core, summary)
    write_artifact_manifest(core, summary, conclusion)
    print(
        json.dumps(
            {
                "ok": True,
                "status": STATUS,
                "r2v_scope_passed": True,
                "next_release_stage_allowed": False,
                "model_manifest": rel(MODEL_MANIFEST),
                "pipeline_status": rel(STAGE / "pipeline_status.json"),
                "artifact_manifest": rel(STAGE / "artifact_manifest.json"),
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
