"""INT-30 R2F: promote existing P36 L7-L16 overlays to runtime-ready metadata.

Single changed dimension:
- reuse the ten canonical P36 temperature-layer band meshes already present in
  the approved R2C candidate;
- add explicit embedded-runtime metadata and a scene/collection contract;
- keep every band hidden by default.

This stage never duplicates or edits band geometry, never cuts the five shell
meshes, never changes the locked R1 material, and never exports/replaces GLB.
Review renders temporarily reveal bands in a separate Blender process and are
not saved into the candidate.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import shutil
import struct
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))
BLENDER = Path(r"D:\Program Files\Blender Foundation\Blender 5.2\blender.exe")
INPUT_BLEND = (
    HERE
    / "work"
    / "INT_30_20260718_R2C_R1_MESO_DETAIL_MERGE"
    / "INT_30_R2C_R1_MESO_DETAIL_MERGE_CANDIDATE.blend"
)
P36_BLEND = (
    HERE
    / "work"
    / "P36_LAYER_SEGMENTATION_20260717_P35_INTEGRATED"
    / "P36_LAYER_SEGMENTATION_CANDIDATE.blend"
)
OUTPUT_DIR = HERE / "work" / "INT_30_20260718_R2F_LAYER_OVERLAY_RUNTIME_READY"
CANDIDATE_NAME = "INT_30_R2F_LAYER_OVERLAY_RUNTIME_READY_CANDIDATE.blend"
FORMAL_GLB = ROOT / "高炉前端数据" / "models" / "gl02_blast_furnace.glb"

STAGE_ID = "INT-30_R2F_LAYER_OVERLAY_RUNTIME_READY"
REQUIREMENT_ID = "REQ-BF3D-INT30-R2F-LAYER-OVERLAY-RUNTIME-READY-20260718"
EXPECTED_INPUT_SHA = "d1278f85713aaa4af9753fd121b2a889d3086165a03d29790b0f20934c92cbd8"
EXPECTED_P36_SHA = "29b9f43802fe8e360c78fe2f106c2f193a3b735c78183cbc41530b1f3eb792c8"
EXPECTED_FORMAL_GLB_SHA = "808960f1b2703e7fb27df35f1b1b1a17063b9b10d2267acba593fc3872b62af6"

R1_MATERIAL = "SURF20_R5_aged_painted_carbon_steel_shared_world"
R1_MAPPING = "SURF20_R5_SHARED_WORLD_MAPPING_EMPTY"
R1_NODE_GRAPH_HASH = "6bf8bd2fcf7712081d1ad2620c3133a984ada8c9b3927b59aa86131ba3b134a6"
R1_DECISION = "VB-DEC-MAT-001"
FRONTEND_REGEX = r"^APPROX_GL02_TEMP_LAYER_BAND_(L(?:[7-9]|1[0-6]))$"
RUNTIME_MODULE = "gl02-layer-highlight-material-v2"
OVERLAY_COLLECTION = "BF3D_TEMPERATURE_LAYER_OVERLAYS"

LAYER_HEIGHTS = {
    "L7": 16.860,
    "L8": 18.335,
    "L9": 20.125,
    "L10": 21.860,
    "L11": 23.711,
    "L12": 25.441,
    "L13": 27.171,
    "L14": 28.901,
    "L15": 30.631,
    "L16": 32.361,
}
LAYER_BOUNDARIES = {
    "L7": (16.1225, 17.5975),
    "L8": (17.5975, 19.2300),
    "L9": (19.2300, 20.9925),
    "L10": (20.9925, 22.7855),
    "L11": (22.7855, 24.5760),
    "L12": (24.5760, 26.3060),
    "L13": (26.3060, 28.0360),
    "L14": (28.0360, 29.7660),
    "L15": (29.7660, 31.4960),
    "L16": (31.4960, 33.2260),
}
BAND_NAMES = [f"APPROX_GL02_TEMP_LAYER_BAND_L{i}" for i in range(7, 17)]
GROUP_NAMES = [f"GL02_FURNACE_TEMP_LAYER_L{i}" for i in range(7, 17)]
MATERIAL_NAMES = [f"BF3D_TEMP_LAYER_HIGHLIGHT_L{i}" for i in range(7, 17)]
SHELL_OBJECTS = [
    "APPROX_GL02_FURNACE_HEARTH",
    "APPROX_GL02_FURNACE_BOSH",
    "APPROX_GL02_FURNACE_BELLY",
    "APPROX_GL02_FURNACE_SHAFT",
    "APPROX_GL02_FURNACE_THROAT",
]
MESO_OBJECTS = [
    "APPROX_GL02_shell_stiffener_rings",
    "APPROX_GL02_P35_shell_welds",
]
PRESSURE_NAMES = [
    f"GL02_INT30_PRESSURE_{band}_{position}"
    for band in ("LOWER", "MIDDLE", "UPPER")
    for position in "ABCDEF"
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

EXPECTED_SHELL_MESH_SIGNATURE = "7a698badb678fecd147211ae07fec50de372a0020853cf7f6d45be8953e4c27b"
EXPECTED_SHELL_MATERIAL_SIGNATURE = "9f837c7cfad7e82f3a8c165502c62657eca7a70108c724099e1e82b4b7c9fab0"
EXPECTED_PRESSURE_SIGNATURE = "495e692cb0a6ac6cb14e0cd370d11272712eea82cf01fe7c8ba068dc593004c1"
EXPECTED_INT20_SIGNATURE = "da8de0ed3971689f2643b571487254d1266c3b281de458f123ac066497c930c1"
EXPECTED_SENSOR_SIGNATURE = "2dc73331ca30e9960c528c6cd082efc0cb303280f31d0bf873856ae8457f8066"

RENDER_SPECS = [
    {
        "id": "STACKED_ALL",
        "file": "INT30_R2F_01_L7_L16_STACKED_REVIEW.png",
        "layers": list(LAYER_HEIGHTS),
        "location": (13.5, -17.0, 10.2),
        "target": (0.0, 0.0, 5.3),
        "ortho": 18.0,
        "purpose": "review-only stacked overview of all ten canonical overlays",
    },
    {
        "id": "SELECT_L7",
        "file": "INT30_R2F_02_L7_SELECTED.png",
        "layers": ["L7"],
        "location": (10.8, -13.2, -0.2),
        "target": (0.0, 0.0, -3.14),
        "ortho": 10.0,
        "purpose": "L7 selected overlay with eight A-H body-temperature points",
    },
    {
        "id": "SELECT_L10",
        "file": "INT30_R2F_03_L10_SELECTED.png",
        "layers": ["L10"],
        "location": (10.8, -13.2, 5.2),
        "target": (0.0, 0.0, 1.86),
        "ortho": 10.0,
        "purpose": "L10 selected overlay with eight A-H body-temperature points",
    },
    {
        "id": "SELECT_L13",
        "file": "INT30_R2F_04_L13_SELECTED.png",
        "layers": ["L13"],
        "location": (10.8, -13.2, 10.2),
        "target": (0.0, 0.0, 7.171),
        "ortho": 10.0,
        "purpose": "L13 selected overlay with eight A-H body-temperature points",
    },
    {
        "id": "SELECT_L16",
        "file": "INT30_R2F_05_L16_SELECTED.png",
        "layers": ["L16"],
        "location": (10.8, -13.2, 15.3),
        "target": (0.0, 0.0, 12.361),
        "ortho": 10.0,
        "purpose": "L16 selected overlay with eight A-H body-temperature points",
    },
    {
        "id": "R1_GRAZING_LOCK",
        "file": "INT30_R2F_06_R1_GRAZING_SURFACE_LOCK.png",
        "layers": [],
        "location": (5.8, -7.2, 3.1),
        "target": (3.25, -0.15, 2.75),
        "ortho": 3.4,
        "purpose": "grazing close-up proving R1 dense rough micro-surface remains readable",
    },
]


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def hash_payload(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()


def now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def rel(path: Path) -> str:
    try:
        return path.resolve().relative_to(ROOT.resolve()).as_posix()
    except ValueError:
        return str(path.resolve())


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def write_text(path: Path, value: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(value, encoding="utf-8")


def assert_output_dir(path: Path) -> None:
    expected = OUTPUT_DIR.resolve()
    if path.resolve() != expected:
        raise RuntimeError(f"Refusing unexpected output directory: {path.resolve()}")


def run_blender(
    blender: Path,
    blend: Path,
    mode: str,
    candidate: Path,
    output_dir: Path,
    width: int,
    height: int,
) -> dict[str, Any]:
    command = [
        str(blender),
        "--background",
        str(blend),
        "--python",
        str(Path(__file__).resolve()),
        "--",
        mode,
        "--candidate",
        str(candidate),
        "--output-dir",
        str(output_dir),
        "--width",
        str(width),
        "--height",
        str(height),
    ]
    proc = subprocess.run(command, cwd=str(HERE), capture_output=True, text=True)
    label = mode.removeprefix("--")
    write_text(output_dir / "reports" / f"{label}.stdout.log", proc.stdout)
    write_text(output_dir / "reports" / f"{label}.stderr.log", proc.stderr)
    if proc.returncode != 0 or "Traceback (most recent call last)" in proc.stderr:
        raise RuntimeError(
            f"Blender {mode} failed with {proc.returncode}; see "
            f"{output_dir / 'reports'}"
        )
    return {
        "mode": mode,
        "blend": str(blend),
        "command": command,
        "returncode": proc.returncode,
    }


def compose_montages(output_dir: Path) -> list[dict[str, Any]]:
    try:
        from PIL import Image, ImageDraw, ImageFont
    except ImportError:
        return []

    def font(size: int) -> Any:
        for item in (
            Path(r"C:\Windows\Fonts\msyh.ttc"),
            Path(r"C:\Windows\Fonts\simhei.ttf"),
            Path(r"C:\Windows\Fonts\simsun.ttc"),
        ):
            if item.is_file():
                return ImageFont.truetype(str(item), size)
        return ImageFont.load_default()

    renders = output_dir / "renders"
    records: list[dict[str, Any]] = []
    specs = [
        (
            "INT30_R2F_07_SELECTED_LAYER_MATRIX.png",
            [renders / spec["file"] for spec in RENDER_SPECS[1:5]],
            "L7 / L10 / L13 / L16 单层选择矩阵",
        ),
        (
            "INT30_R2F_08_STACKED_AND_R1_LOCK.png",
            [
                renders / RENDER_SPECS[0]["file"],
                renders / RENDER_SPECS[5]["file"],
            ],
            "十层覆盖总览与 R1 粗糙表面硬锁",
        ),
    ]
    title_font = font(30)
    label_font = font(20)
    for filename, sources, title in specs:
        if not all(source.is_file() for source in sources):
            continue
        opened = [Image.open(source).convert("RGB") for source in sources]
        thumb_w = 720 if len(opened) == 2 else 600
        thumb_h = 450 if len(opened) == 2 else 375
        cols = 2
        rows = math.ceil(len(opened) / cols)
        canvas = Image.new("RGB", (thumb_w * cols, 72 + thumb_h * rows), (5, 9, 12))
        draw = ImageDraw.Draw(canvas)
        draw.text((18, 16), title, fill=(255, 157, 59), font=title_font)
        for index, (image, source) in enumerate(zip(opened, sources)):
            image.thumbnail((thumb_w, thumb_h))
            x = (index % cols) * thumb_w
            y = 72 + (index // cols) * thumb_h
            canvas.paste(image, (x, y))
            draw.rectangle((x, y, x + thumb_w, y + 28), fill=(0, 0, 0))
            draw.text((x + 8, y + 3), source.stem, fill=(235, 244, 239), font=label_font)
        path = renders / filename
        canvas.save(path)
        records.append(
            {
                "id": path.stem,
                "file": path.name,
                "path": str(path),
                "project_relative_path": rel(path),
                "source_files": [source.name for source in sources],
                "bytes": path.stat().st_size,
                "sha256": sha256_file(path),
            }
        )
    return records


def artifact_manifest(output_dir: Path) -> dict[str, Any]:
    files = []
    for path in sorted(output_dir.rglob("*")):
        if not path.is_file() or path.name == "artifact_sha256.json":
            continue
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
        "excluded_self": "artifact_sha256.json",
        "files": files,
    }


def write_stage_summary(
    output_dir: Path,
    candidate: Path,
    machine: dict[str, Any],
) -> None:
    renders = machine["renders"]
    lines = [
        "# INT-30 R2F L7～L16 分层覆盖运行时就绪阶段成果总结",
        "",
        f"> 阶段状态：`{machine['status']}`  ",
        "> 批准边界：执行者未自批，等待独立视觉与规范审核。  ",
        f"> 用户外观决策：`{R1_DECISION}`（R1 粗糙读感硬锁）。",
        "",
        "## 1. 本阶段唯一变化",
        "",
        "- 直接复用 R2C 中已经存在且与批准 P36 几何逐层同 hash 的十个 canonical 覆盖网格。",
        "- 未复制、未重建、未切割炉壳；只增加 embedded runtime 元数据和场景/集合合同。",
        "- L7～L16 仍默认隐藏，运行时只能显示当前选中层。",
        "",
        "## 2. 候选",
        "",
        f"- Blend：`{rel(candidate)}`",
        f"- SHA256：`{machine['candidate']['sha256']}`",
        f"- 生成分支：`{machine['reuse_decision']}`",
        "- 正式 GLB 未导出、未替换。",
        "",
        "## 3. R1 粗糙表面保护",
        "",
        "- 固定 B=0.16、D=0.10m、N=0.45、metallic=0.06、roughness=0.56～0.82、mapping=0.085。",
        f"- R1 节点图 hash：`{machine['r1_contract']['node_graph_hash']}`。",
        "- 分层假色只覆盖选中层，不能替代或照平 R1 炉壳材质。",
        "",
        "## 4. 保护门禁",
        "",
    ]
    for key, value in machine["assertions"].items():
        lines.append(f"- `{key}`：`{value}`")
    lines.extend(
        [
            "",
            "## 5. 审阅图",
            "",
        ]
    )
    for record in renders:
        lines.append(
            f"- `{record['id']}`：`{record['project_relative_path']}` — "
            f"{record.get('purpose', '审阅合成图')}"
        )
    lines.extend(
        [
            "",
            "## 6. 明确边界",
            "",
            "- 这些网格是诊断覆盖层，不是炉壳实体分段、真实厚度或机械膨胀。",
            "- 本阶段没有解锁料线数据门禁。",
            "- 本阶段没有导出生产 GLB，也没有改变 Three.js 正式资产。",
            "- 独立视觉与规格审核通过前，不得宣称 R2F 已批准。",
            "",
        ]
    )
    write_text(
        output_dir / "INT-30_R2F_LAYER_OVERLAY_RUNTIME_READY_阶段成果总结.md",
        "\n".join(lines),
    )


def host_main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--blender", type=Path, default=BLENDER)
    parser.add_argument("--input-blend", type=Path, default=INPUT_BLEND)
    parser.add_argument("--p36-blend", type=Path, default=P36_BLEND)
    parser.add_argument("--output-dir", type=Path, default=OUTPUT_DIR)
    parser.add_argument("--width", type=int, default=1440)
    parser.add_argument("--height", type=int, default=900)
    parser.add_argument("--refresh-metadata-only", action="store_true")
    args = parser.parse_args()

    blender = args.blender.resolve()
    input_blend = args.input_blend.resolve()
    p36_blend = args.p36_blend.resolve()
    output_dir = args.output_dir.resolve()
    assert_output_dir(output_dir)
    candidate = output_dir / CANDIDATE_NAME

    if args.refresh_metadata_only:
        if not candidate.is_file():
            raise FileNotFoundError(candidate)
        candidate_sha = sha256_file(candidate)
        if candidate_sha != "1d292e8cc6ad5f845827cdd4c5f18b7e6eda496703870816caaef181af9fb3e5":
            raise RuntimeError(
                f"R2F candidate SHA changed before metadata refresh: {candidate_sha}"
            )
        formal_sha = sha256_file(FORMAL_GLB)
        if formal_sha != EXPECTED_FORMAL_GLB_SHA:
            raise RuntimeError(
                f"Formal GLB SHA changed before metadata refresh: {formal_sha}"
            )
        write_json(output_dir / "artifact_sha256.json", artifact_manifest(output_dir))
        print(
            json.dumps(
                {
                    "stage": STAGE_ID,
                    "status": "metadata_refreshed_only",
                    "candidate_sha256": candidate_sha,
                    "formal_glb_sha256": formal_sha,
                },
                ensure_ascii=False,
            )
        )
        return 0

    for path in (blender, input_blend, p36_blend, FORMAL_GLB):
        if not path.is_file():
            raise FileNotFoundError(path)
    input_sha = sha256_file(input_blend)
    p36_sha = sha256_file(p36_blend)
    formal_before = sha256_file(FORMAL_GLB)
    if input_sha != EXPECTED_INPUT_SHA:
        raise RuntimeError(f"R2C input SHA mismatch: {input_sha}")
    if p36_sha != EXPECTED_P36_SHA:
        raise RuntimeError(f"P36 SHA mismatch: {p36_sha}")
    if formal_before != EXPECTED_FORMAL_GLB_SHA:
        raise RuntimeError(f"Formal GLB SHA mismatch: {formal_before}")

    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "renders").mkdir(exist_ok=True)
    (output_dir / "reports").mkdir(exist_ok=True)
    for path in output_dir.glob("*.blend1"):
        path.unlink()
    for path in (candidate,):
        if path.exists():
            path.unlink()

    commands = [
        run_blender(
            blender,
            input_blend,
            "--run-stage",
            candidate,
            output_dir,
            args.width,
            args.height,
        ),
        run_blender(
            blender,
            candidate,
            "--reopen-validate",
            candidate,
            output_dir,
            args.width,
            args.height,
        ),
        run_blender(
            blender,
            candidate,
            "--render-evidence",
            candidate,
            output_dir,
            args.width,
            args.height,
        ),
    ]
    write_json(
        output_dir / "command.json",
        {
            "schema_version": "bf3d.int30.r2f.command.v1",
            "stage": STAGE_ID,
            "generated_at": now_iso(),
            "parser_chain": "PowerShell -> python subprocess -> blender.exe -> Python bpy",
            "commands": commands,
        },
    )
    montage_records = compose_montages(output_dir)
    render_manifest_path = output_dir / "reports" / "render_manifest.json"
    render_manifest = json.loads(render_manifest_path.read_text(encoding="utf-8"))
    render_manifest["records"].extend(montage_records)
    write_json(render_manifest_path, render_manifest)

    stage_report = json.loads(
        (output_dir / "reports" / "stage_internal_report.json").read_text(encoding="utf-8")
    )
    reopen = json.loads(
        (output_dir / "reports" / "reopen_validation.json").read_text(encoding="utf-8")
    )
    p36_preflight = json.loads(
        (output_dir / "R2F_APPROVED_P36_BAND_PREFLIGHT.json").read_text(encoding="utf-8")
    )
    current_preflight = json.loads(
        (output_dir / "R2F_CURRENT_R2C_BAND_PREFLIGHT.json").read_text(encoding="utf-8")
    )
    band_hash_equal = all(
        left["mesh_hash"] == right["mesh_hash"]
        and left["matrix_world"] == right["matrix_world"]
        and left["materials"] == right["materials"]
        for left, right in zip(current_preflight["bands"], p36_preflight["bands"])
    )
    formal_after = sha256_file(FORMAL_GLB)
    candidate_sha = sha256_file(candidate)
    assertions = dict(reopen["assertions"])
    assertions.update(
        {
            "input_sha256_matches": input_sha == EXPECTED_INPUT_SHA,
            "approved_p36_sha256_matches": p36_sha == EXPECTED_P36_SHA,
            "current_bands_exact_p36_geometry_matrix_material": band_hash_equal,
            "reuse_without_append_or_duplicate": stage_report["reuse_decision"]
            == "reuse_existing_exact_p36_bands_no_append",
            "formal_glb_sha256_unchanged": formal_before
            == formal_after
            == EXPECTED_FORMAL_GLB_SHA,
            "renders_exist": all(
                (output_dir / "renders" / spec["file"]).is_file()
                for spec in RENDER_SPECS
            ),
            "no_output_glb": not list(output_dir.rglob("*.glb")),
            "blend1_not_generated": not list(output_dir.rglob("*.blend1")),
        }
    )
    machine_assertions_pass = all(assertions.values())
    assertions["machine_assertions_pass"] = machine_assertions_pass
    machine = {
        "schema_version": "bf3d.int30.r2f.machine_report.v1",
        "requirement_id": REQUIREMENT_ID,
        "stage": STAGE_ID,
        "status": "candidate_ready_for_review"
        if machine_assertions_pass
        else "candidate_failed_machine_gates",
        "approval": "not_granted_requires_independent_visual_and_spec_review",
        "generated_at": now_iso(),
        "single_changed_dimension": "promote_existing_exact_P36_L7_L16_bands_to_embedded_runtime_ready_metadata_only",
        "user_visual_lock": {
            "decision_id": R1_DECISION,
            "selection": "R1 dense rough matte micro-surface",
            "carrier": "SURF-20 R5",
        },
        "input": {
            "path": str(input_blend),
            "sha256": input_sha,
            "expected_sha256": EXPECTED_INPUT_SHA,
        },
        "approved_p36": {
            "path": str(p36_blend),
            "sha256": p36_sha,
            "expected_sha256": EXPECTED_P36_SHA,
        },
        "candidate": {
            "path": str(candidate),
            "project_relative_path": rel(candidate),
            "bytes": candidate.stat().st_size,
            "sha256": candidate_sha,
        },
        "reuse_decision": stage_report["reuse_decision"],
        "runtime_contract": stage_report["runtime_contract"],
        "r1_contract": reopen["r1_contract"],
        "protected_contract": reopen["protected_contract"],
        "band_contract": reopen["band_contract"],
        "renders": render_manifest["records"],
        "assertions": assertions,
        "self_assessment": {
            "approval_claimed": False,
            "decision": "candidate_ready_for_independent_review"
            if machine_assertions_pass
            else "machine_gate_failure",
        },
        "known_boundaries": [
            "diagnostic overlay only; not physical shell segmentation or measured thickness",
            "formal GLB and Three.js production asset remain unchanged",
            "stockline data gate remains blocked",
        ],
        "stop_line": "independent_visual_and_spec_review_required_before_controller_approval_or_GLB_export",
    }
    write_json(output_dir / "int30_r2f_machine_report.json", machine)
    write_stage_summary(output_dir, candidate, machine)
    write_json(output_dir / "artifact_sha256.json", artifact_manifest(output_dir))
    print(
        json.dumps(
            {
                "stage": STAGE_ID,
                "status": machine["status"],
                "candidate": str(candidate),
                "sha256": candidate_sha,
                "reuse_decision": machine["reuse_decision"],
            },
            ensure_ascii=False,
        )
    )
    return 0 if machine_assertions_pass else 2


def blender_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-stage", action="store_true")
    parser.add_argument("--reopen-validate", action="store_true")
    parser.add_argument("--render-evidence", action="store_true")
    parser.add_argument("--candidate", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--width", type=int, default=1440)
    parser.add_argument("--height", type=int, default=900)
    argv = sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else []
    return parser.parse_args(argv)


def serializable_socket_value(value: Any) -> Any:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return float(value) if isinstance(value, float) else value
    try:
        values = list(value)
    except TypeError:
        return None
    if all(isinstance(item, (int, float, bool)) for item in values):
        return [
            round(float(item), 8) if isinstance(item, float) else item
            for item in values
        ]
    return None


def material_node_graph(material: Any) -> dict[str, Any]:
    if material is None or not material.use_nodes or material.node_tree is None:
        return {"material": material.name if material else None, "hash": None}
    nodes = []
    for node in sorted(material.node_tree.nodes, key=lambda item: item.name):
        inputs = {}
        for socket in node.inputs:
            if node.bl_idname == "ShaderNodeMapping" and socket.name != "Vector":
                continue
            if not hasattr(socket, "default_value"):
                continue
            value = serializable_socket_value(socket.default_value)
            if value is not None:
                inputs[socket.name] = value
        nodes.append(
            {
                "name": node.name,
                "bl_idname": node.bl_idname,
                "label": node.label,
                "inputs": inputs,
                "object": node.object.name
                if hasattr(node, "object") and node.object is not None
                else None,
            }
        )
    links = sorted(
        [
            {
                "from": f"{link.from_node.name}.{link.from_socket.name}",
                "to": f"{link.to_node.name}.{link.to_socket.name}",
            }
            for link in material.node_tree.links
        ],
        key=lambda item: (item["from"], item["to"]),
    )
    payload = {"nodes": nodes, "links": links}
    return {
        "material": material.name,
        "hash": hash_payload(payload),
        "node_count": len(nodes),
        "link_count": len(links),
        "payload": payload,
    }


def mesh_hash(mesh: Any) -> str:
    digest = hashlib.sha256()
    digest.update(mesh.name.encode("utf-8"))
    digest.update(struct.pack("<III", len(mesh.vertices), len(mesh.edges), len(mesh.polygons)))
    for vertex in mesh.vertices:
        digest.update(struct.pack("<3d", *(round(float(v), 9) for v in vertex.co)))
    for polygon in mesh.polygons:
        digest.update(struct.pack("<I", len(polygon.vertices)))
        for index in polygon.vertices:
            digest.update(struct.pack("<I", int(index)))
    return digest.hexdigest()


def custom_props(owner: Any) -> dict[str, Any]:
    result = {}
    for key in sorted(owner.keys()):
        if key == "_RNA_UI":
            continue
        value = owner[key]
        if isinstance(value, (str, int, float, bool)) or value is None:
            result[key] = value
        elif hasattr(value, "to_list"):
            result[key] = value.to_list()
        else:
            try:
                result[key] = list(value)
            except TypeError:
                result[key] = str(value)
    return result


def band_record(layer: str) -> dict[str, Any]:
    import bpy

    name = f"APPROX_GL02_TEMP_LAYER_BAND_{layer}"
    obj = bpy.data.objects.get(name)
    if obj is None:
        return {"layer": layer, "name": name, "exists": False}
    mesh = obj.data if obj.type == "MESH" else None
    sensors = sorted(
        item.name
        for item in bpy.data.objects
        if item.name.startswith(f"SENSOR_T_body_{layer}_")
    )
    return {
        "layer": layer,
        "name": name,
        "exists": True,
        "type": obj.type,
        "mesh": mesh.name if mesh else None,
        "mesh_hash": mesh_hash(mesh) if mesh else None,
        "vertices": len(mesh.vertices) if mesh else None,
        "polygons": len(mesh.polygons) if mesh else None,
        "matrix_world": [round(float(v), 9) for row in obj.matrix_world for v in row],
        "parent": obj.parent.name if obj.parent else None,
        "collections": sorted(collection.name for collection in obj.users_collection),
        "materials": [slot.material.name for slot in obj.material_slots if slot.material],
        "hide_viewport": bool(obj.hide_viewport),
        "hide_render": bool(obj.hide_render),
        "custom_properties": custom_props(obj),
        "sensors": sensors,
    }


def protected_contract() -> dict[str, Any]:
    import bpy
    import run_int30_r2c_merge_r1_meso_details as r2c

    sensors = [obj for obj in bpy.data.objects if obj.name.startswith("SENSOR_")]
    body = [obj for obj in bpy.data.objects if obj.name.startswith("SENSOR_T_body_")]
    return {
        "object_count": len(bpy.data.objects),
        "mesh_count": len(bpy.data.meshes),
        "material_count": len(bpy.data.materials),
        "sensor_count": len(sensors),
        "body_temperature_sensor_count": len(body),
        "layer_sensor_counts": {
            f"L{index}": len(
                [
                    obj
                    for obj in body
                    if obj.name.startswith(f"SENSOR_T_body_L{index}_")
                ]
            )
            for index in range(7, 17)
        },
        "pressure_count": len(
            [obj for obj in bpy.data.objects if obj.name.startswith("GL02_INT30_PRESSURE_")]
        ),
        "int20_entity_count": sum(
            1 for name in INT20_SOLID_OBJECTS if bpy.data.objects.get(name)
        ),
        "shell_mesh_matrix_signature": r2c.object_mesh_matrix_signature(SHELL_OBJECTS),
        "shell_material_signature": r2c.object_material_signature(SHELL_OBJECTS),
        "pressure_signature": r2c.pressure_signature(),
        "int20_signature": r2c.object_full_signature(INT20_SOLID_OBJECTS),
        "sensor_signature": r2c.sensor_signature(),
        "meso_mesh_matrix_signature": r2c.object_mesh_matrix_signature(MESO_OBJECTS),
        "meso_material_signature": r2c.object_material_signature(MESO_OBJECTS),
        "meso_visible": all(
            bpy.data.objects.get(name)
            and not bpy.data.objects[name].hide_viewport
            and not bpy.data.objects[name].hide_render
            for name in MESO_OBJECTS
        ),
    }


def r1_contract() -> dict[str, Any]:
    import bpy
    import run_int30_r2c_merge_r1_meso_details as r2c

    material = bpy.data.materials.get(R1_MATERIAL)
    mapping = bpy.data.objects.get(R1_MAPPING)
    result = r2c.inspect_material_contract(material, mapping)
    graph = material_node_graph(material)
    result["node_graph_hash"] = graph["hash"]
    result["node_count"] = graph.get("node_count")
    result["link_count"] = graph.get("link_count")
    result["node_graph_payload"] = graph.get("payload")
    return result


def runtime_contract() -> dict[str, Any]:
    return {
        "contract_version": "bf3d.gl02.temperature_layer_overlay.v2",
        "frontend_module": RUNTIME_MODULE,
        "frontend_regex": FRONTEND_REGEX,
        "layer_range": "L7-L16",
        "embedded_band_count": 10,
        "default_visible": False,
        "selected_layer_only": True,
        "interaction": "radial_scale_and_state_color",
        "overlay_only": True,
        "not_physical_shell_segmentation": True,
        "user_surface_lock": R1_DECISION,
    }


def validate_band_contract() -> dict[str, Any]:
    import bpy

    records = [band_record(layer) for layer in LAYER_HEIGHTS]
    duplicates = sorted(
        obj.name
        for obj in bpy.data.objects
        if obj.name.startswith("APPROX_GL02_TEMP_LAYER_BAND_")
        and obj.name not in BAND_NAMES
    )
    assertions = {
        "exactly_ten_canonical_bands": len(
            [record for record in records if record["exists"]]
        )
        == 10,
        "no_duplicate_suffix_bands": not duplicates,
        "all_meshes": all(record.get("type") == "MESH" for record in records),
        "all_default_hidden": all(
            record.get("hide_viewport")
            and record.get("hide_render")
            and record.get("custom_properties", {}).get("default_visible") is False
            for record in records
        ),
        "all_identity_world_transform": all(
            record.get("matrix_world")
            == [
                1.0,
                0.0,
                0.0,
                0.0,
                0.0,
                1.0,
                0.0,
                0.0,
                0.0,
                0.0,
                1.0,
                0.0,
                0.0,
                0.0,
                0.0,
                1.0,
            ]
            for record in records
        ),
        "all_heights_match": all(
            math.isclose(
                float(record.get("custom_properties", {}).get("height_m", -999)),
                LAYER_HEIGHTS[record["layer"]],
                abs_tol=1e-9,
            )
            for record in records
        ),
        "all_boundaries_match": all(
            math.isclose(
                float(
                    record.get("custom_properties", {}).get("band_lower_m", -999)
                ),
                LAYER_BOUNDARIES[record["layer"]][0],
                abs_tol=1e-9,
            )
            and math.isclose(
                float(
                    record.get("custom_properties", {}).get("band_upper_m", -999)
                ),
                LAYER_BOUNDARIES[record["layer"]][1],
                abs_tol=1e-9,
            )
            for record in records
        ),
        "all_offset_006": all(
            math.isclose(
                float(
                    record.get("custom_properties", {}).get("shell_offset_m", -999)
                ),
                0.06,
                abs_tol=1e-9,
            )
            for record in records
        ),
        "all_sensor_count_eight": all(
            len(record.get("sensors", [])) == 8 for record in records
        ),
        "all_runtime_ready": all(
            record.get("custom_properties", {}).get("bf3d_runtime_ready") is True
            and record.get("custom_properties", {}).get("runtime_source") == "embedded"
            and record.get("custom_properties", {}).get("overlay_only") is True
            and record.get("custom_properties", {}).get("runtime_selected_layer_only")
            is True
            for record in records
        ),
    }
    return {
        "records": records,
        "duplicates": duplicates,
        "assertions": assertions,
        "all_pass": all(assertions.values()),
    }


def promote_runtime_metadata() -> None:
    import bpy

    contract = runtime_contract()
    collection = bpy.data.collections.get(OVERLAY_COLLECTION)
    if collection is None:
        raise RuntimeError(f"Missing overlay collection: {OVERLAY_COLLECTION}")
    collection["bf3d_role"] = "temperature_layer_runtime_overlays"
    collection["bf3d_runtime_ready"] = True
    collection["runtime_contract_version"] = contract["contract_version"]
    collection["frontend_regex_contract"] = FRONTEND_REGEX
    collection["default_visible"] = False
    collection["selected_layer_only"] = True
    collection["overlay_only"] = True
    collection["user_surface_lock"] = R1_DECISION

    for layer, height in LAYER_HEIGHTS.items():
        band = bpy.data.objects.get(f"APPROX_GL02_TEMP_LAYER_BAND_{layer}")
        group = bpy.data.objects.get(f"GL02_FURNACE_TEMP_LAYER_{layer}")
        material = bpy.data.materials.get(f"BF3D_TEMP_LAYER_HIGHLIGHT_{layer}")
        if band is None or group is None or material is None:
            raise RuntimeError(
                f"Missing canonical P36 asset for {layer}: "
                f"band={band is not None}, group={group is not None}, "
                f"material={material is not None}"
            )
        band.hide_viewport = True
        band.hide_render = True
        band["bf3d_runtime_ready"] = True
        band["runtime_contract_version"] = contract["contract_version"]
        band["runtime_source"] = "embedded"
        band["frontend_regex_contract"] = FRONTEND_REGEX
        band["runtime_default_visible"] = False
        band["runtime_selected_layer_only"] = True
        band["overlay_only"] = True
        band["not_physical_shell_segmentation"] = True
        band["user_surface_lock"] = R1_DECISION
        band["height_m"] = height
        band["layer_id"] = layer
        group["bf3d_runtime_ready"] = True
        group["runtime_source"] = "embedded"
        group["layer_id"] = layer
        group["default_visible"] = False
        group["selected_layer_only"] = True
        group["overlay_only"] = True
        group["user_surface_lock"] = R1_DECISION
        material["bf3d_runtime_overlay_material"] = True
        material["runtime_layer_id"] = layer
        material["diagnostic_overlay_only"] = True
        material["does_not_replace_surface_material"] = True
        material["user_surface_lock"] = R1_DECISION

    scene = bpy.context.scene
    scene["bf3d_int30_r2f_stage"] = STAGE_ID
    scene["bf3d_single_changed_dimension"] = (
        "promote_existing_exact_p36_layer_bands_to_runtime_ready_metadata_only"
    )
    scene["bf3d_layer_overlay_contract"] = json.dumps(
        contract, ensure_ascii=False, sort_keys=True
    )
    scene["bf3d_layer_overlay_default_visible"] = False
    scene["bf3d_layer_overlay_selected_layer_only"] = True
    scene["bf3d_layer_overlay_count"] = 10
    scene["bf3d_user_surface_lock"] = R1_DECISION
    scene["bf3d_formal_glb_replaced"] = False


def run_stage(args: argparse.Namespace) -> None:
    import bpy

    before_protected = protected_contract()
    before_r1 = r1_contract()
    before_bands = [band_record(layer) for layer in LAYER_HEIGHTS]
    if len([record for record in before_bands if record["exists"]]) != 10:
        raise RuntimeError(
            "R2C is missing canonical bands; append branch is not permitted by "
            "this reuse-only runner."
        )
    promote_runtime_metadata()
    after_protected = protected_contract()
    after_r1 = r1_contract()
    after_bands = validate_band_contract()
    candidate = args.candidate.resolve()
    candidate.parent.mkdir(parents=True, exist_ok=True)
    bpy.ops.wm.save_as_mainfile(filepath=str(candidate), check_existing=False)
    report = {
        "schema_version": "bf3d.int30.r2f.stage_internal.v1",
        "stage": STAGE_ID,
        "generated_at": now_iso(),
        "reuse_decision": "reuse_existing_exact_p36_bands_no_append",
        "runtime_contract": runtime_contract(),
        "before_protected": before_protected,
        "after_protected": after_protected,
        "before_r1": before_r1,
        "after_r1": after_r1,
        "before_band_mesh_hashes": {
            record["layer"]: record["mesh_hash"] for record in before_bands
        },
        "after_band_mesh_hashes": {
            record["layer"]: record["mesh_hash"]
            for record in after_bands["records"]
        },
        "assertions": {
            "protected_contract_unchanged": before_protected == after_protected,
            "r1_contract_unchanged": before_r1 == after_r1,
            "band_mesh_hashes_unchanged": {
                record["layer"]: record["mesh_hash"] for record in before_bands
            }
            == {
                record["layer"]: record["mesh_hash"]
                for record in after_bands["records"]
            },
            "band_contract_pass": after_bands["all_pass"],
        },
    }
    write_json(args.output_dir / "reports" / "stage_internal_report.json", report)


def reopen_validate(args: argparse.Namespace) -> None:
    import bpy

    protected = protected_contract()
    r1 = r1_contract()
    bands = validate_band_contract()
    scene = bpy.context.scene
    scene_contract_raw = scene.get("bf3d_layer_overlay_contract", "")
    try:
        scene_contract = json.loads(scene_contract_raw)
    except (TypeError, json.JSONDecodeError):
        scene_contract = None
    assertions = {
        "candidate_filepath_matches": Path(bpy.data.filepath).resolve()
        == args.candidate.resolve(),
        "sensor_count_115_preserved": protected["sensor_count"] == 115,
        "body_temperature_80_preserved": protected[
            "body_temperature_sensor_count"
        ]
        == 80,
        "l7_l16_eight_sensors_each": all(
            count == 8 for count in protected["layer_sensor_counts"].values()
        ),
        "pressure_count_18_preserved": protected["pressure_count"] == 18,
        "int20_12_entities_preserved": protected["int20_entity_count"] == 12,
        "five_shell_mesh_matrix_signature_preserved": protected[
            "shell_mesh_matrix_signature"
        ]
        == EXPECTED_SHELL_MESH_SIGNATURE,
        "five_shell_material_signature_preserved": protected[
            "shell_material_signature"
        ]
        == EXPECTED_SHELL_MATERIAL_SIGNATURE,
        "pressure_signature_preserved": protected["pressure_signature"]
        == EXPECTED_PRESSURE_SIGNATURE,
        "int20_signature_preserved": protected["int20_signature"]
        == EXPECTED_INT20_SIGNATURE,
        "sensor_signature_preserved": protected["sensor_signature"]
        == EXPECTED_SENSOR_SIGNATURE,
        "meso_objects_visible": protected["meso_visible"],
        "r1_material_present": r1["material"] == R1_MATERIAL,
        "r1_node_graph_hash_preserved": r1["node_graph_hash"]
        == R1_NODE_GRAPH_HASH,
        "r1_metallic_006": math.isclose(
            float(r1["principled_metallic"]), 0.06, abs_tol=1e-6
        ),
        "r1_roughness_range_preserved": r1["roughness_min_observed"] == 0.56
        and r1["roughness_max_observed"] == 0.82,
        "r1_bump_manifest_preserved": r1["r1_micro_surface_manifest"]
        == {
            "bump_strength": 0.16,
            "bump_distance_meters": 0.1,
            "normal_equivalent_strength": 0.45,
        },
        "r1_shared_mapping_preserved": r1["shared_mapping_scale_xyz"]
        == [0.085, 0.085, 0.085],
        "ten_band_contract_pass": bands["all_pass"],
        "scene_runtime_contract_present": scene_contract == runtime_contract(),
        "all_bands_default_hidden_after_reopen": all(
            record["hide_viewport"] and record["hide_render"]
            for record in bands["records"]
        ),
        "no_duplicate_bands": not bands["duplicates"],
    }
    report = {
        "schema_version": "bf3d.int30.r2f.reopen_validation.v1",
        "stage": STAGE_ID,
        "generated_at": now_iso(),
        "protected_contract": protected,
        "r1_contract": r1,
        "band_contract": bands,
        "scene_runtime_contract": scene_contract,
        "assertions": assertions,
        "all_pass": all(assertions.values()),
    }
    write_json(args.output_dir / "reports" / "reopen_validation.json", report)
    if not report["all_pass"]:
        failed = [key for key, value in assertions.items() if not value]
        raise RuntimeError(f"R2F reopen validation failed: {failed}")


def add_area_light(
    name: str,
    location: tuple[float, float, float],
    energy: float,
    size: float,
    color: tuple[float, float, float],
) -> Any:
    import bpy

    data = bpy.data.lights.new(name, "AREA")
    data.energy = energy
    data.size = size
    data.color = color
    obj = bpy.data.objects.new(name, data)
    bpy.context.scene.collection.objects.link(obj)
    obj.location = location
    return obj


def make_camera(
    name: str,
    location: tuple[float, float, float],
    target: tuple[float, float, float],
    ortho: float,
) -> Any:
    import bpy
    from mathutils import Vector

    data = bpy.data.cameras.new(f"{name}_DATA")
    data.type = "ORTHO"
    data.ortho_scale = ortho
    data.clip_start = 0.05
    data.clip_end = 1000.0
    obj = bpy.data.objects.new(name, data)
    bpy.context.scene.collection.objects.link(obj)
    obj.location = location
    obj.rotation_euler = (Vector(target) - obj.location).to_track_quat("-Z", "Y").to_euler()
    return obj


def configure_render(width: int, height: int) -> Any:
    import bpy

    scene = bpy.context.scene
    enum_ids = {
        item.identifier
        for item in scene.render.bl_rna.properties["engine"].enum_items
    }
    scene.render.engine = (
        "BLENDER_EEVEE_NEXT"
        if "BLENDER_EEVEE_NEXT" in enum_ids
        else "BLENDER_EEVEE"
    )
    scene.render.resolution_x = width
    scene.render.resolution_y = height
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = "PNG"
    scene.render.film_transparent = False
    scene.view_settings.view_transform = "AgX"
    scene.view_settings.look = "AgX - Medium Low Contrast"
    scene.view_settings.exposure = 0.18
    scene.view_settings.gamma = 1.0
    scene.world = scene.world or bpy.data.worlds.new("INT30_R2F_REVIEW_WORLD")
    scene.world.use_nodes = True
    nodes = scene.world.node_tree.nodes
    background = next(
        (node for node in nodes if node.bl_idname == "ShaderNodeBackground"), None
    )
    if background is not None:
        background.inputs["Color"].default_value = (0.01, 0.015, 0.021, 1.0)
        background.inputs["Strength"].default_value = 0.48

    for obj in bpy.data.objects:
        if obj.type == "LIGHT":
            obj.hide_render = True
            obj.hide_viewport = True
    add_area_light(
        "INT30_R2F_KEY",
        (8.0, -7.0, 12.5),
        650.0,
        4.2,
        (1.0, 0.92, 0.82),
    )
    add_area_light(
        "INT30_R2F_RIM",
        (-7.0, 8.5, 9.5),
        380.0,
        5.5,
        (0.68, 0.82, 1.0),
    )
    add_area_light(
        "INT30_R2F_GRAZE",
        (8.0, -2.5, 2.0),
        520.0,
        2.2,
        (0.9, 1.0, 0.96),
    )
    add_area_light(
        "INT30_R2F_MICRO_RAKE",
        (5.6, -5.8, 2.9),
        980.0,
        1.15,
        (0.95, 1.0, 0.92),
    )
    return scene


def set_render_visibility(layers: list[str]) -> None:
    import bpy

    visible = set(SHELL_OBJECTS + MESO_OBJECTS)
    for layer in layers:
        visible.add(f"APPROX_GL02_TEMP_LAYER_BAND_{layer}")
        visible.update(
            obj.name
            for obj in bpy.data.objects
            if obj.name.startswith(f"SENSOR_T_body_{layer}_")
        )
    for obj in bpy.data.objects:
        if obj.type in {"LIGHT", "CAMERA"}:
            continue
        is_visible = obj.name in visible
        obj.hide_render = not is_visible
        obj.hide_viewport = not is_visible


def render_evidence(args: argparse.Namespace) -> None:
    import bpy

    scene = configure_render(args.width, args.height)
    records = []
    for spec in RENDER_SPECS:
        set_render_visibility(spec["layers"])
        camera = make_camera(
            f"INT30_R2F_CAM_{spec['id']}",
            spec["location"],
            spec["target"],
            spec["ortho"],
        )
        scene.camera = camera
        path = args.output_dir / "renders" / spec["file"]
        scene.render.filepath = str(path)
        bpy.ops.render.render(write_still=True)
        records.append(
            {
                "id": spec["id"],
                "file": spec["file"],
                "path": str(path),
                "project_relative_path": rel(path),
                "camera": camera.name,
                "selected_layers": spec["layers"],
                "purpose": spec["purpose"],
                "engine": scene.render.engine,
                "resolution_px": [args.width, args.height],
                "bytes": path.stat().st_size,
                "sha256": sha256_file(path),
            }
        )
    for name in BAND_NAMES:
        obj = bpy.data.objects.get(name)
        if obj:
            obj.hide_viewport = True
            obj.hide_render = True
    write_json(
        args.output_dir / "reports" / "render_manifest.json",
        {
            "schema_version": "bf3d.int30.r2f.render_manifest.v1",
            "stage": STAGE_ID,
            "generated_at": now_iso(),
            "render_process_does_not_save_blend": True,
            "records": records,
        },
    )


def blender_main() -> int:
    args = blender_args()
    if args.run_stage:
        run_stage(args)
    elif args.reopen_validate:
        reopen_validate(args)
    elif args.render_evidence:
        render_evidence(args)
    else:
        raise RuntimeError("Missing Blender mode")
    return 0


if __name__ == "__main__":
    if "--" in sys.argv:
        raise SystemExit(blender_main())
    raise SystemExit(host_main())
