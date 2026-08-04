"""Execute the GL02 BASE-00 source-lock stage without touching production assets.

The normal Python process:

1. hashes the controlled GLB/manifest, approved P40 Blend, P50/P60 evidence,
   LookDev/Golden contracts, and the locked generators/YAML files;
2. creates a byte-identical isolated copy named ``BASE00_SOURCE_LOCKED.blend``;
3. opens only that copy in Blender background mode for a read-only scene audit;
4. emits a machine report, lock manifest, fixed-camera index, and execution logs.

The same file is also invoked inside Blender with ``--blender-audit-child``.
That mode only inspects the already copied Blend and writes an audit JSON.  It
does not save the Blend or export a GLB.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import platform
import shutil
import struct
import subprocess
import sys
import traceback
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable


REQUIREMENT_ID = "REQ-BF3D-10STAGE-EXECUTION-20260718"
STAGE = "BASE-00"
REPORT_STATUS = "candidate_ready_for_review"
P50_BOUNDARY = "KEEP_P50_PENDING_NOT_APPROVED"
P60_BOUNDARY = "not_granted_preflight_only"
P40_BOUNDARY = "approved"
FORMAL_GLB_EXPECTED_SHA256 = "808960f1b2703e7fb27df35f1b1b1a17063b9b10d2267acba593fc3872b62af6"
P40_APPROVED_EXPECTED_SHA256 = "03635cf6608a54c4a671fb4d84adcb9451a36fe47cea7b564af2d4d3b69b2256"
EXPECTED_SENSOR_COUNT = 115
EXPECTED_BODY_SENSOR_COUNT = 80
EXPECTED_LAYERS = [f"GL02_SENSOR_LAYER_L{layer}" for layer in range(7, 17)]
EXPECTED_PROCESS_ZONES = [
    "APPROX_GL02_FURNACE_HEARTH",
    "APPROX_GL02_FURNACE_BOSH",
    "APPROX_GL02_FURNACE_BELLY",
    "APPROX_GL02_FURNACE_SHAFT",
    "APPROX_GL02_FURNACE_THROAT",
]
EXPECTED_CAMERAS = [
    "CAM_GLOBAL_FRONT",
    "CAM_GLOBAL_BACK",
    "CAM_GLOBAL_LEFT",
    "CAM_GLOBAL_RIGHT",
    "CAM_DETAIL_SHELL",
    "CAM_DETAIL_TUYERE",
    "CAM_DETAIL_TAPHOLE",
]
CAMERA_TOLERANCE = 1e-6
POSITION_TOLERANCE_M = 1e-5

SCRIPT_PATH = Path(__file__).resolve()
MODULE_ROOT = SCRIPT_PATH.parent
PROJECT_ROOT = SCRIPT_PATH.parents[2]
DEFAULT_OUTPUT_DIR = MODULE_ROOT / "work" / "BASE_00_20260718_R1"
DEFAULT_BLENDER = Path(r"D:\Program Files\Blender Foundation\Blender 5.2\blender.exe")
FORMAL_GLB = PROJECT_ROOT / "高炉前端数据" / "models" / "gl02_blast_furnace.glb"
FORMAL_MANIFEST = PROJECT_ROOT / "高炉前端数据" / "models" / "gl02_blast_furnace.manifest.json"
P40_DIR = MODULE_ROOT / "work" / "P40_FIXED_LOOKDEV_20260717_P36_FINAL"
P50_DIR = MODULE_ROOT / "work" / "P50_MASTER_4K_20260717_R1"
P60_DIR = MODULE_ROOT / "work" / "P60_PREFLIGHT_4K_20260717_R1"
LOOKDEV_PRESET = MODULE_ROOT / "web" / "presets" / "lookdev_camera_v1.json"
GOLDEN_VIEWS = MODULE_ROOT / "validation" / "golden-images" / "golden_views_v1.json"
VISUAL_BIBLE = MODULE_ROOT / "工业级高炉数字孪生视觉规范（Visual Bible）.md"
LOOKDEV_DOCUMENT = MODULE_ROOT / "docs" / "LookDev与相机固定参数.md"
SKILL_BUNDLE_MANIFEST = MODULE_ROOT / "skills" / "bundle-manifest.json"
SKILL_SOURCES_LOCK = MODULE_ROOT / "skills" / "sources.lock.json"
P40_APPROVED_BLEND = P40_DIR / "P40_LOOKDEV_APPROVED.blend"
LOCKED_BLEND_NAME = "BASE00_SOURCE_LOCKED.blend"


def now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def canonical_json_sha256(value: Any) -> str:
    payload = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"Expected a JSON object: {path}")
    return value


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=False, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    os.replace(temporary, path)


def relative_display(path: Path) -> str:
    resolved = path.resolve()
    try:
        return resolved.relative_to(PROJECT_ROOT.resolve()).as_posix()
    except ValueError:
        return resolved.as_posix()


class ExecutionLog:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text("", encoding="utf-8")

    def emit(self, event: str, **fields: Any) -> None:
        record = {"at": now_iso(), "event": event, **fields}
        with self.path.open("a", encoding="utf-8", newline="\n") as handle:
            handle.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")


def assertion(assertion_id: str, ok: bool, detail: Any) -> dict[str, Any]:
    return {"id": assertion_id, "ok": bool(ok), "detail": detail}


def lock_file(
    asset_id: str,
    role: str,
    path: Path,
    *,
    expected_sha256: str | None = None,
    expected_bytes: int | None = None,
    approval_state: str | None = None,
    required: bool = True,
) -> dict[str, Any]:
    resolved = path.resolve()
    exists = resolved.is_file()
    item: dict[str, Any] = {
        "asset_id": asset_id,
        "role": role,
        "path": resolved.as_posix(),
        "project_relative_path": relative_display(resolved),
        "required": required,
        "exists": exists,
        "approval_state": approval_state,
        "expected_bytes": expected_bytes,
        "expected_sha256": expected_sha256,
    }
    if exists:
        item["bytes"] = resolved.stat().st_size
        item["sha256"] = sha256_file(resolved)
        item["bytes_match_expected"] = expected_bytes is None or item["bytes"] == expected_bytes
        item["sha256_matches_expected"] = expected_sha256 is None or item["sha256"] == expected_sha256
    else:
        item["bytes"] = None
        item["sha256"] = None
        item["bytes_match_expected"] = not required and expected_bytes is None
        item["sha256_matches_expected"] = not required and expected_sha256 is None
    item["lock_ok"] = bool(
        (exists or not required)
        and item["bytes_match_expected"]
        and item["sha256_matches_expected"]
    )
    return item


def matrix_identity() -> list[list[float]]:
    return [
        [1.0, 0.0, 0.0, 0.0],
        [0.0, 1.0, 0.0, 0.0],
        [0.0, 0.0, 1.0, 0.0],
        [0.0, 0.0, 0.0, 1.0],
    ]


def matrix_multiply(left: list[list[float]], right: list[list[float]]) -> list[list[float]]:
    return [
        [sum(left[row][inner] * right[inner][column] for inner in range(4)) for column in range(4)]
        for row in range(4)
    ]


def node_local_matrix(node: dict[str, Any]) -> list[list[float]]:
    if "matrix" in node:
        values = [float(value) for value in node["matrix"]]
        if len(values) != 16:
            raise ValueError("glTF node matrix must have 16 values")
        return [[values[column * 4 + row] for column in range(4)] for row in range(4)]

    translation = [float(value) for value in node.get("translation", [0.0, 0.0, 0.0])]
    scale = [float(value) for value in node.get("scale", [1.0, 1.0, 1.0])]
    x, y, z, w = [float(value) for value in node.get("rotation", [0.0, 0.0, 0.0, 1.0])]
    length = math.sqrt(x * x + y * y + z * z + w * w)
    if length == 0.0:
        x, y, z, w = 0.0, 0.0, 0.0, 1.0
    else:
        x, y, z, w = x / length, y / length, z / length, w / length
    rotation = [
        [1.0 - 2.0 * (y * y + z * z), 2.0 * (x * y - z * w), 2.0 * (x * z + y * w), 0.0],
        [2.0 * (x * y + z * w), 1.0 - 2.0 * (x * x + z * z), 2.0 * (y * z - x * w), 0.0],
        [2.0 * (x * z - y * w), 2.0 * (y * z + x * w), 1.0 - 2.0 * (x * x + y * y), 0.0],
        [0.0, 0.0, 0.0, 1.0],
    ]
    scale_matrix = matrix_identity()
    scale_matrix[0][0], scale_matrix[1][1], scale_matrix[2][2] = scale
    local = matrix_multiply(rotation, scale_matrix)
    local[0][3], local[1][3], local[2][3] = translation
    return local


def read_glb_contract(path: Path) -> dict[str, Any]:
    with path.open("rb") as handle:
        header = handle.read(12)
        if len(header) != 12:
            raise ValueError(f"GLB header is incomplete: {path}")
        magic, version, total_length = struct.unpack("<4sII", header)
        if magic != b"glTF" or version != 2 or total_length != path.stat().st_size:
            raise ValueError(f"Invalid glTF 2.0 header: {path}")
        chunk_header = handle.read(8)
        if len(chunk_header) != 8:
            raise ValueError(f"GLB JSON chunk header is incomplete: {path}")
        json_length, chunk_type = struct.unpack("<II", chunk_header)
        if chunk_type != 0x4E4F534A:
            raise ValueError(f"First GLB chunk is not JSON: {path}")
        gltf = json.loads(handle.read(json_length).decode("utf-8"))

    nodes = gltf.get("nodes", [])
    parents: dict[int, int] = {}
    for parent_index, node in enumerate(nodes):
        for child_index in node.get("children", []):
            parents[int(child_index)] = parent_index
    world_cache: dict[int, list[list[float]]] = {}

    def world_matrix(index: int) -> list[list[float]]:
        if index not in world_cache:
            local = node_local_matrix(nodes[index])
            world_cache[index] = (
                matrix_multiply(world_matrix(parents[index]), local)
                if index in parents
                else local
            )
        return world_cache[index]

    name_to_index = {
        str(node.get("name", "")): index
        for index, node in enumerate(nodes)
        if node.get("name")
    }

    def record_for(index: int) -> dict[str, Any]:
        node = nodes[index]
        world = world_matrix(index)
        gltf_position = [world[axis][3] for axis in range(3)]
        blender_position = [gltf_position[0], -gltf_position[2], gltf_position[1]]
        parent_index = parents.get(index)
        return {
            "name": node.get("name", ""),
            "parent": nodes[parent_index].get("name", "") if parent_index is not None else None,
            "extras": node.get("extras", {}),
            "gltf_world_position_m": [round(value, 9) for value in gltf_position],
            "expected_blender_world_position_m": [round(value, 9) for value in blender_position],
        }

    sensors = [
        record_for(index)
        for index, node in enumerate(nodes)
        if str(node.get("name", "")).startswith("SENSOR_")
    ]
    body_sensors = [
        item
        for item in sensors
        if item["name"].startswith("SENSOR_T_body_")
        or item.get("extras", {}).get("group") == "BODY_TEMP"
    ]
    layers = {
        name: {
            "exists": name in name_to_index,
            "children": [
                nodes[int(index)].get("name", "")
                for index in nodes[name_to_index[name]].get("children", [])
            ]
            if name in name_to_index
            else [],
        }
        for name in EXPECTED_LAYERS
    }
    process_zones = {
        name: record_for(name_to_index[name]) if name in name_to_index else None
        for name in EXPECTED_PROCESS_ZONES
    }
    records_for_hash = [
        {
            "name": item["name"],
            "parent": item["parent"],
            "expected_blender_world_position_m": item["expected_blender_world_position_m"],
        }
        for item in sorted(sensors, key=lambda value: value["name"])
    ]
    return {
        "asset": gltf.get("asset", {}),
        "scene_index": gltf.get("scene"),
        "scene_count": len(gltf.get("scenes", [])),
        "node_count": len(nodes),
        "mesh_count": len(gltf.get("meshes", [])),
        "material_count": len(gltf.get("materials", [])),
        "texture_count": len(gltf.get("textures", [])),
        "image_count": len(gltf.get("images", [])),
        "sensor_count": len(sensors),
        "body_sensor_count": len({item["name"] for item in body_sensors}),
        "sensor_records": sorted(sensors, key=lambda value: value["name"]),
        "sensor_contract_sha256": canonical_json_sha256(records_for_hash),
        "layers": layers,
        "process_zones": process_zones,
    }


def vector_max_abs_difference(left: Iterable[float], right: Iterable[float]) -> float:
    left_values = [float(value) for value in left]
    right_values = [float(value) for value in right]
    if len(left_values) != len(right_values):
        return math.inf
    return max((abs(a - b) for a, b in zip(left_values, right_values)), default=0.0)


def resolve_reference(base_file: Path, reference: str) -> Path:
    candidate = Path(reference)
    if candidate.is_absolute():
        return candidate.resolve()
    return (base_file.parent / candidate).resolve()


def expected_local_source_map(source_lock: dict[str, Any]) -> dict[Path, dict[str, Any]]:
    results: dict[Path, dict[str, Any]] = {}
    for item in source_lock.get("local_sources", []):
        raw_path = Path(str(item["path"]))
        path = raw_path if raw_path.is_absolute() else PROJECT_ROOT / raw_path
        results[path.resolve()] = item
    return results


def build_input_locks(
    source_lock: dict[str, Any],
    lookdev: dict[str, Any],
    golden: dict[str, Any],
    p40_report: dict[str, Any],
    p50_review: dict[str, Any],
    p60_report: dict[str, Any],
) -> list[dict[str, Any]]:
    source_map = expected_local_source_map(source_lock)

    def source_expected(path: Path) -> tuple[str | None, int | None]:
        item = source_map.get(path.resolve(), {})
        return item.get("sha256"), item.get("bytes")

    formal_glb_sha, formal_glb_bytes = source_expected(FORMAL_GLB)
    formal_manifest_sha, formal_manifest_bytes = source_expected(FORMAL_MANIFEST)
    visual_glb = Path(r"D:\文件\pythonCAD\src\geometry\visual_glb.py")
    generator_entry = Path(r"D:\文件\pythonCAD\src\generate_gl02_cad.py")
    profile_yaml = Path(r"D:\文件\pythonCAD\input\furnace_profile.gl02.yaml")
    sensor_yaml = Path(r"D:\文件\pythonCAD\input\sensor_layout.gl02.115.yaml")
    p60_input = p60_report.get("input", {})
    p60_copy = p60_report.get("isolated_export_copy", {})
    p60_glb = p60_report.get("uncompressed_glb", {})
    p40_expected = (
        lookdev.get("approval_boundaries", {}).get("p40_approved_blend_sha256")
        or golden.get("asset_locks", {}).get("p40_approved_blend", {}).get("sha256")
    )
    items = [
        lock_file(
            "formal_glb",
            "read_only_production_glb",
            FORMAL_GLB,
            expected_sha256=formal_glb_sha or FORMAL_GLB_EXPECTED_SHA256,
            expected_bytes=formal_glb_bytes,
            approval_state="formal_current_not_replaced",
        ),
        lock_file(
            "formal_glb_manifest",
            "production_model_manifest",
            FORMAL_MANIFEST,
            expected_sha256=formal_manifest_sha,
            expected_bytes=formal_manifest_bytes,
            approval_state="formal_current",
        ),
        lock_file(
            "p36_input_checkpoint",
            "approved_geometry_input_recorded_by_p40",
            Path(p40_report.get("input_checkpoint", {}).get("path", "")),
            expected_sha256=p40_report.get("input_checkpoint", {}).get("sha256"),
            approval_state="approved_input_to_p40",
        ),
        lock_file(
            "p40_approved_blend",
            "source_for_isolated_base00_copy",
            P40_APPROVED_BLEND,
            expected_sha256=p40_expected or P40_APPROVED_EXPECTED_SHA256,
            approval_state=P40_BOUNDARY,
        ),
        lock_file(
            "p40_machine_report",
            "p40_camera_render_and_assertion_evidence",
            P40_DIR / "p40_fixed_lookdev_candidate.json",
            approval_state="evidence_for_approved_p40_scope",
        ),
        lock_file(
            "p40_human_review",
            "p40_human_approval_record",
            P40_DIR / "p40_visual_review.json",
            expected_sha256=next(
                (
                    item.get("sha256")
                    for item in lookdev.get("source_evidence", [])
                    if item.get("role") == "human_approval_record"
                ),
                None,
            ),
            approval_state=P40_BOUNDARY,
        ),
        lock_file(
            "p50_candidate_blend",
            "pending_p50_candidate_asset",
            P50_DIR / "P50_FULL_FURNACE_BAKE_CANDIDATE.blend",
            expected_sha256=p50_review.get("candidate_sha256") or p60_input.get("sha256"),
            expected_bytes=p60_input.get("bytes"),
            approval_state=P50_BOUNDARY,
        ),
        lock_file(
            "p50_machine_report",
            "p50_machine_bake_report",
            P50_DIR / "p50_full_furnace_bake_candidate.json",
            approval_state=P50_BOUNDARY,
        ),
        lock_file(
            "p50_visual_review",
            "p50_gate_decision",
            P50_DIR / "p50_master_4k_visual_review.json",
            approval_state=P50_BOUNDARY,
        ),
        lock_file(
            "p50_texture_manifest",
            "p50_texture_contract",
            P50_DIR / "p50_texture_manifest.json",
            approval_state=P50_BOUNDARY,
        ),
        lock_file(
            "p50_rotation_review",
            "p50_rotation_review_evidence",
            P50_DIR / "review" / "p50_rotation_review_evidence.json",
            approval_state=P50_BOUNDARY,
        ),
        lock_file(
            "p50_manual_observations",
            "p50_manual_visual_observations",
            P50_DIR / "review" / "p50_master_4k_manual_observations.json",
            approval_state=P50_BOUNDARY,
        ),
        lock_file(
            "p60_preflight_report",
            "p60_internal_preflight_report",
            P60_DIR / "p60_preflight_report.json",
            approval_state=P60_BOUNDARY,
        ),
        lock_file(
            "p60_preflight_manifest",
            "p60_internal_preflight_manifest",
            P60_DIR / "p60_preflight_manifest.json",
            approval_state=P60_BOUNDARY,
        ),
        lock_file(
            "p60_preflight_sha256",
            "p60_internal_preflight_hash_list",
            P60_DIR / "p60_preflight_sha256.json",
            approval_state=P60_BOUNDARY,
        ),
        lock_file(
            "p60_validator_status",
            "p60_validator_availability_record",
            P60_DIR / "gltf_validator_status.json",
            approval_state=P60_BOUNDARY,
        ),
        lock_file(
            "p60_isolated_export_copy",
            "p60_preflight_only_blend",
            P60_DIR / "P60_PREFLIGHT_EXPORT_COPY.blend",
            expected_sha256=p60_copy.get("sha256"),
            expected_bytes=p60_copy.get("bytes"),
            approval_state=P60_BOUNDARY,
        ),
        lock_file(
            "p60_uncompressed_glb",
            "p60_preflight_only_uncompressed_glb",
            P60_DIR / "P60_PREFLIGHT_4K_UNCOMPRESSED.glb",
            expected_sha256=p60_glb.get("sha256"),
            expected_bytes=p60_glb.get("bytes"),
            approval_state=P60_BOUNDARY,
        ),
        lock_file(
            "visual_bible_v1_1",
            "controlled_visual_ssot",
            VISUAL_BIBLE,
            approval_state="controlled_baseline",
        ),
        lock_file(
            "lookdev_document",
            "human_readable_lookdev_camera_contract",
            LOOKDEV_DOCUMENT,
            approval_state="controlled_parameter_baseline",
        ),
        lock_file(
            "lookdev_camera_preset",
            "machine_readable_lookdev_camera_contract",
            LOOKDEV_PRESET,
            approval_state="controlled_parameter_baseline",
        ),
        lock_file(
            "golden_views_parameters",
            "golden_view_parameter_contract",
            GOLDEN_VIEWS,
            approval_state="parameters_locked_baseline_images_not_approved",
        ),
        lock_file(
            "skill_bundle_manifest",
            "bf3d_skill_bundle_version",
            SKILL_BUNDLE_MANIFEST,
            approval_state="controlled_skill_bundle",
        ),
        lock_file(
            "skill_sources_lock",
            "bf3d_upstream_and_local_source_lock",
            SKILL_SOURCES_LOCK,
            approval_state="controlled_source_lock",
        ),
    ]
    for asset_id, role, path in [
        ("generator_visual_glb", "primary_visual_glb_generator", visual_glb),
        ("generator_entry", "gl02_cad_generator_entry", generator_entry),
        ("furnace_profile_yaml", "gl02_furnace_profile", profile_yaml),
        ("sensor_layout_yaml", "gl02_sensor_layout_115", sensor_yaml),
    ]:
        expected_sha, expected_size = source_expected(path)
        items.append(
            lock_file(
                asset_id,
                role,
                path,
                expected_sha256=expected_sha,
                expected_bytes=expected_size,
                approval_state="locked_by_skills_sources_lock",
            )
        )

    hdri = lookdev.get("environment_assets", {}).get("industrial_sunset_candidate", {})
    if hdri.get("path"):
        hdri_path = resolve_reference(LOOKDEV_PRESET, str(hdri["path"]))
        items.append(
            lock_file(
                "industrial_sunset_hdri_candidate",
                "registered_hdri_candidate_not_visual_approved",
                hdri_path,
                expected_sha256=hdri.get("sha256"),
                expected_bytes=hdri.get("bytes"),
                approval_state=hdri.get("status"),
            )
        )
    return items


def atomic_copy(source: Path, target: Path) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_name(target.name + ".copying")
    if temporary.exists():
        temporary.unlink()
    shutil.copy2(source, temporary)
    os.replace(temporary, target)


def child_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Blender child process for the BASE-00 read-only audit.")
    parser.add_argument("--blender-audit-child", action="store_true")
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--preset", required=True, type=Path)
    return parser


def blender_cli_args() -> list[str]:
    if "--" not in sys.argv:
        return []
    return sys.argv[sys.argv.index("--") + 1 :]


def bpy_json_value(value: Any) -> Any:
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    if isinstance(value, dict):
        return {str(key): bpy_json_value(item) for key, item in value.items()}
    if hasattr(value, "to_list"):
        return bpy_json_value(value.to_list())
    try:
        return [bpy_json_value(item) for item in value]
    except TypeError:
        return str(value)


def rounded_vector(values: Iterable[float], digits: int = 9) -> list[float]:
    return [round(float(value), digits) for value in values]


def blender_object_bounds(objects: Iterable[Any]) -> dict[str, Any] | None:
    from mathutils import Vector

    points = [
        obj.matrix_world @ Vector(corner)
        for obj in objects
        if obj.type == "MESH"
        for corner in obj.bound_box
    ]
    if not points:
        return None
    minimum = [min(float(point[axis]) for point in points) for axis in range(3)]
    maximum = [max(float(point[axis]) for point in points) for axis in range(3)]
    center = [(minimum[axis] + maximum[axis]) * 0.5 for axis in range(3)]
    size = [maximum[axis] - minimum[axis] for axis in range(3)]
    return {
        "minimum_m": rounded_vector(minimum),
        "maximum_m": rounded_vector(maximum),
        "center_m": rounded_vector(center),
        "size_m": rounded_vector(size),
    }


def run_blender_child() -> int:
    import bpy

    args = child_arg_parser().parse_args(blender_cli_args())
    output_dir = args.output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    report_path = output_dir / "base00_blender_scene_audit.json"
    preset = read_json(args.preset.resolve())
    started_at = now_iso()
    objects = list(bpy.data.objects)
    by_name = {obj.name: obj for obj in objects}
    object_counts = Counter(obj.type for obj in objects)
    sensors = sorted(
        (obj for obj in objects if obj.name.startswith("SENSOR_")),
        key=lambda obj: obj.name,
    )
    sensor_records = []
    for obj in sensors:
        custom_properties = {
            str(key): bpy_json_value(value)
            for key, value in obj.items()
            if not str(key).startswith("_")
        }
        sensor_records.append(
            {
                "name": obj.name,
                "parent": obj.parent.name if obj.parent else None,
                "type": obj.type,
                "location": rounded_vector(obj.location),
                "world_position_m": rounded_vector(obj.matrix_world.translation),
                "scale": rounded_vector(obj.scale),
                "world_matrix_row_major": [
                    round(float(obj.matrix_world[row][column]), 9)
                    for row in range(4)
                    for column in range(4)
                ],
                "custom_properties": custom_properties,
            }
        )
    body_by_name = [record for record in sensor_records if record["name"].startswith("SENSOR_T_body_")]
    body_by_group = [
        record
        for record in sensor_records
        if record["custom_properties"].get("group") == "BODY_TEMP"
    ]
    layers: dict[str, Any] = {}
    for name in EXPECTED_LAYERS:
        obj = by_name.get(name)
        children = sorted(child.name for child in obj.children) if obj else []
        layers[name] = {
            "exists": obj is not None,
            "type": obj.type if obj else None,
            "world_position_m": rounded_vector(obj.matrix_world.translation) if obj else None,
            "children": children,
            "child_count": len(children),
        }
    process_zones: dict[str, Any] = {}
    for name in EXPECTED_PROCESS_ZONES:
        obj = by_name.get(name)
        process_zones[name] = {
            "exists": obj is not None,
            "type": obj.type if obj else None,
            "parent": obj.parent.name if obj and obj.parent else None,
            "world_position_m": rounded_vector(obj.matrix_world.translation) if obj else None,
            "scale": rounded_vector(obj.scale) if obj else None,
            "dimensions_m": rounded_vector(obj.dimensions) if obj else None,
            "bounds": blender_object_bounds([obj]) if obj else None,
        }
    actual_cameras: dict[str, Any] = {}
    camera_assertions: list[dict[str, Any]] = []
    for camera_id in EXPECTED_CAMERAS:
        expected = preset.get("cameras", {}).get(camera_id, {})
        obj = by_name.get(camera_id)
        actual = None
        errors: dict[str, float] = {}
        if obj is not None and obj.type == "CAMERA":
            actual = {
                "type": obj.data.type,
                "location_m": rounded_vector(obj.location),
                "rotation_euler_rad": rounded_vector(obj.rotation_euler),
                "ortho_scale_m": round(float(obj.data.ortho_scale), 9),
                "clip_start_m": round(float(obj.data.clip_start), 9),
                "clip_end_m": round(float(obj.data.clip_end), 9),
            }
            errors = {
                "location_max_abs": vector_max_abs_difference(
                    actual["location_m"], expected.get("location_m", [])
                ),
                "rotation_max_abs": vector_max_abs_difference(
                    actual["rotation_euler_rad"], expected.get("rotation_euler_rad", [])
                ),
                "ortho_scale_abs": abs(
                    float(actual["ortho_scale_m"]) - float(expected.get("ortho_scale_m", math.inf))
                ),
                "clip_start_abs": abs(
                    float(actual["clip_start_m"]) - float(expected.get("clip_start_m", math.inf))
                ),
                "clip_end_abs": abs(
                    float(actual["clip_end_m"]) - float(expected.get("clip_end_m", math.inf))
                ),
            }
        camera_ok = bool(
            actual is not None
            and actual["type"] == "ORTHO"
            and all(error <= CAMERA_TOLERANCE for error in errors.values())
        )
        actual_cameras[camera_id] = {
            "exists": obj is not None,
            "expected": expected,
            "actual": actual,
            "numeric_errors": errors,
            "matches_preset": camera_ok,
        }
        camera_assertions.append(
            assertion(f"camera_{camera_id}_matches_controlled_preset", camera_ok, errors)
        )

    all_mesh_objects = [obj for obj in objects if obj.type == "MESH"]
    non_sensor_mesh_objects = [
        obj for obj in all_mesh_objects if not obj.name.startswith("SENSOR_")
    ]
    process_mesh_objects = [
        by_name[name]
        for name in EXPECTED_PROCESS_ZONES
        if name in by_name and by_name[name].type == "MESH"
    ]
    roots = sorted((obj for obj in objects if obj.parent is None), key=lambda obj: obj.name)
    scene = bpy.context.scene
    cycles_addon = bpy.context.preferences.addons.get("cycles")
    compute_device_type = None
    discovered_devices: list[dict[str, Any]] = []
    if cycles_addon is not None:
        preferences = cycles_addon.preferences
        compute_device_type = getattr(preferences, "compute_device_type", None)
        try:
            preferences.get_devices()
            discovered_devices = [
                {
                    "name": str(device.name),
                    "type": str(device.type),
                    "use": bool(device.use),
                }
                for device in getattr(preferences, "devices", [])
            ]
        except Exception as error:
            discovered_devices = [{"probe_error": f"{type(error).__name__}: {error}"}]

    sensor_contract_for_hash = [
        {
            "name": record["name"],
            "parent": record["parent"],
            "world_position_m": record["world_position_m"],
            "world_matrix_row_major": record["world_matrix_row_major"],
        }
        for record in sensor_records
    ]
    child_assertions = [
        assertion(
            "opened_file_is_base00_locked_copy",
            Path(bpy.data.filepath).resolve() == (output_dir / LOCKED_BLEND_NAME).resolve(),
            {
                "opened": Path(bpy.data.filepath).resolve().as_posix(),
                "expected": (output_dir / LOCKED_BLEND_NAME).resolve().as_posix(),
            },
        ),
        assertion("sensor_count_is_115", len(sensors) == EXPECTED_SENSOR_COUNT, len(sensors)),
        assertion(
            "body_sensor_name_count_is_80",
            len(body_by_name) == EXPECTED_BODY_SENSOR_COUNT,
            len(body_by_name),
        ),
        assertion(
            "body_sensor_group_count_is_80",
            len(body_by_group) == EXPECTED_BODY_SENSOR_COUNT,
            len(body_by_group),
        ),
        assertion(
            "body_sensor_name_and_group_sets_match",
            {item["name"] for item in body_by_name}
            == {item["name"] for item in body_by_group},
            {
                "name_only": sorted(
                    {item["name"] for item in body_by_name}
                    - {item["name"] for item in body_by_group}
                ),
                "group_only": sorted(
                    {item["name"] for item in body_by_group}
                    - {item["name"] for item in body_by_name}
                ),
            },
        ),
        assertion(
            "all_ten_layers_exist_with_eight_children",
            all(layers[name]["exists"] and layers[name]["child_count"] == 8 for name in EXPECTED_LAYERS),
            {name: layers[name]["child_count"] for name in EXPECTED_LAYERS},
        ),
        assertion(
            "all_five_process_zones_exist",
            all(process_zones[name]["exists"] for name in EXPECTED_PROCESS_ZONES),
            {name: process_zones[name]["exists"] for name in EXPECTED_PROCESS_ZONES},
        ),
        assertion(
            "all_five_process_zones_are_meshes",
            all(process_zones[name]["type"] == "MESH" for name in EXPECTED_PROCESS_ZONES),
            {name: process_zones[name]["type"] for name in EXPECTED_PROCESS_ZONES},
        ),
        assertion(
            "seven_controlled_cameras_exist",
            all(actual_cameras[name]["exists"] for name in EXPECTED_CAMERAS),
            {name: actual_cameras[name]["exists"] for name in EXPECTED_CAMERAS},
        ),
        *camera_assertions,
    ]
    child_ok = all(item["ok"] for item in child_assertions)
    report = {
        "schema_version": "bf3d.base00.blender_audit.v1",
        "requirement_id": REQUIREMENT_ID,
        "stage": STAGE,
        "status": "audit_passed" if child_ok else "audit_failed",
        "approval": "not_granted_read_only_machine_audit",
        "started_at": started_at,
        "completed_at": now_iso(),
        "read_only_contract": {
            "opened_copy": Path(bpy.data.filepath).resolve().as_posix(),
            "blend_saved_by_audit": False,
            "glb_exported_by_audit": False,
            "production_asset_opened": False,
        },
        "blender": {
            "version_string": bpy.app.version_string,
            "version": list(bpy.app.version),
            "build_branch": bpy.app.build_branch.decode("utf-8", errors="replace")
            if isinstance(bpy.app.build_branch, bytes)
            else str(bpy.app.build_branch),
            "build_hash": bpy.app.build_hash.decode("utf-8", errors="replace")
            if isinstance(bpy.app.build_hash, bytes)
            else str(bpy.app.build_hash),
            "binary_path": Path(bpy.app.binary_path).resolve().as_posix(),
            "background": bool(bpy.app.background),
            "audit_rendering_performed": False,
            "scene_render_engine": scene.render.engine,
            "scene_cycles_device": getattr(scene.cycles, "device", None),
            "cycles_compute_device_type": compute_device_type,
            "discovered_cycles_devices": discovered_devices,
            "p40_approved_render_device_from_review": "OPTIX",
        },
        "scene": {
            "filepath": Path(bpy.data.filepath).resolve().as_posix(),
            "scene_name": scene.name,
            "frame_current": scene.frame_current,
            "unit_settings": {
                "system": scene.unit_settings.system,
                "length_unit": scene.unit_settings.length_unit,
                "scale_length": float(scene.unit_settings.scale_length),
            },
            "color_management": {
                "view_transform": scene.view_settings.view_transform,
                "look": scene.view_settings.look,
                "exposure": float(scene.view_settings.exposure),
                "display_device": scene.display_settings.display_device,
                "sequencer_colorspace": scene.sequencer_colorspace_settings.name,
            },
            "world_origin_m": [0.0, 0.0, 0.0],
            "cursor_location_m": rounded_vector(scene.cursor.location),
            "root_objects": [
                {
                    "name": obj.name,
                    "type": obj.type,
                    "world_position_m": rounded_vector(obj.matrix_world.translation),
                }
                for obj in roots
            ],
            "counts": {
                "objects": len(objects),
                "objects_by_type": dict(sorted(object_counts.items())),
                "mesh_objects": len(all_mesh_objects),
                "mesh_datablocks": len(bpy.data.meshes),
                "materials": len(bpy.data.materials),
                "collections": len(bpy.data.collections),
                "cameras": len(bpy.data.cameras),
                "lights": len(bpy.data.lights),
                "images": len(bpy.data.images),
                "textures": len(bpy.data.textures),
            },
            "bounds": {
                "all_mesh_objects": blender_object_bounds(all_mesh_objects),
                "non_sensor_mesh_objects": blender_object_bounds(non_sensor_mesh_objects),
                "five_process_zone_meshes": blender_object_bounds(process_mesh_objects),
            },
        },
        "protected_contract": {
            "sensor_count": len(sensors),
            "body_sensor_count_by_name": len(body_by_name),
            "body_sensor_count_by_group": len(body_by_group),
            "sensor_contract_sha256": canonical_json_sha256(sensor_contract_for_hash),
            "sensor_records": sensor_records,
            "layers": layers,
            "process_zones": process_zones,
        },
        "fixed_cameras": actual_cameras,
        "assertions": child_assertions,
        "assertion_summary": {
            "total": len(child_assertions),
            "passed": sum(item["ok"] for item in child_assertions),
            "failed": sum(not item["ok"] for item in child_assertions),
        },
        "visual_capture": {
            "performed": False,
            "reason": (
                "BASE-00 is a byte-identical source lock. Existing approved-scope P40 fixed-camera "
                "evidence is indexed by the outer runner; no scene or image was changed."
            ),
        },
    }
    write_json(report_path, report)
    return 0 if child_ok else 3


def outer_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Execute the GL02 BASE-00 controlled source lock and read-only Blender audit. "
            "No production GLB, approved P40 source, P50/P60 evidence, or Web file is modified."
        )
    )
    parser.add_argument("--blender", type=Path, default=DEFAULT_BLENDER)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    return parser


def compare_formal_to_blender(
    formal_contract: dict[str, Any],
    blender_audit: dict[str, Any],
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    formal_sensors = {
        item["name"]: item for item in formal_contract.get("sensor_records", [])
    }
    blend_sensors = {
        item["name"]: item
        for item in blender_audit.get("protected_contract", {}).get("sensor_records", [])
    }
    missing = sorted(set(formal_sensors) - set(blend_sensors))
    unexpected = sorted(set(blend_sensors) - set(formal_sensors))
    parent_mismatches: list[dict[str, Any]] = []
    position_mismatches: list[dict[str, Any]] = []
    max_sensor_position_error = 0.0
    for name in sorted(set(formal_sensors) & set(blend_sensors)):
        expected = formal_sensors[name]
        actual = blend_sensors[name]
        if expected.get("parent") != actual.get("parent"):
            parent_mismatches.append(
                {
                    "name": name,
                    "expected": expected.get("parent"),
                    "actual": actual.get("parent"),
                }
            )
        error = vector_max_abs_difference(
            expected["expected_blender_world_position_m"],
            actual["world_position_m"],
        )
        max_sensor_position_error = max(max_sensor_position_error, error)
        if error > POSITION_TOLERANCE_M:
            position_mismatches.append(
                {
                    "name": name,
                    "expected_blender_world_position_m": expected[
                        "expected_blender_world_position_m"
                    ],
                    "actual_blender_world_position_m": actual["world_position_m"],
                    "max_abs_error_m": error,
                }
            )

    blend_zones = blender_audit.get("protected_contract", {}).get("process_zones", {})
    zone_position_mismatches: list[dict[str, Any]] = []
    max_zone_position_error = 0.0
    for name in EXPECTED_PROCESS_ZONES:
        formal_zone = formal_contract.get("process_zones", {}).get(name)
        blend_zone = blend_zones.get(name)
        if not formal_zone or not blend_zone or not blend_zone.get("exists"):
            zone_position_mismatches.append(
                {"name": name, "reason": "missing_in_formal_or_blender"}
            )
            continue
        error = vector_max_abs_difference(
            formal_zone["expected_blender_world_position_m"],
            blend_zone["world_position_m"],
        )
        max_zone_position_error = max(max_zone_position_error, error)
        if error > POSITION_TOLERANCE_M:
            zone_position_mismatches.append(
                {
                    "name": name,
                    "expected_blender_world_position_m": formal_zone[
                        "expected_blender_world_position_m"
                    ],
                    "actual_blender_world_position_m": blend_zone["world_position_m"],
                    "max_abs_error_m": error,
                }
            )

    comparison = {
        "sensor_names_missing_from_blend": missing,
        "sensor_names_unexpected_in_blend": unexpected,
        "sensor_parent_mismatches": parent_mismatches,
        "sensor_position_mismatches": position_mismatches,
        "max_sensor_position_error_m": max_sensor_position_error,
        "process_zone_position_mismatches": zone_position_mismatches,
        "max_process_zone_position_error_m": max_zone_position_error,
    }
    assertions = [
        assertion(
            "p40_sensor_names_match_formal_glb",
            not missing and not unexpected,
            {"missing": missing, "unexpected": unexpected},
        ),
        assertion(
            "p40_sensor_parents_match_formal_glb",
            not parent_mismatches,
            parent_mismatches,
        ),
        assertion(
            "p40_sensor_world_positions_match_formal_glb",
            not position_mismatches,
            {
                "tolerance_m": POSITION_TOLERANCE_M,
                "max_error_m": max_sensor_position_error,
                "mismatches": position_mismatches,
            },
        ),
        assertion(
            "p40_process_zone_origins_match_formal_glb",
            not zone_position_mismatches,
            {
                "tolerance_m": POSITION_TOLERANCE_M,
                "max_error_m": max_zone_position_error,
                "mismatches": zone_position_mismatches,
            },
        ),
    ]
    return assertions, comparison


def build_fixed_camera_index(
    lookdev: dict[str, Any],
    golden: dict[str, Any],
    blender_audit: dict[str, Any],
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    views_by_camera: dict[str, list[dict[str, Any]]] = {
        camera: [] for camera in EXPECTED_CAMERAS
    }
    web_blocked_views: list[dict[str, Any]] = []
    evidence_assertions: list[dict[str, Any]] = []
    for view in golden.get("views", []):
        indexed_view = {
            "view_id": view.get("id"),
            "lookdev": view.get("lookdev"),
            "capture_contract": view.get("capture_contract"),
            "purpose": view.get("purpose"),
            "evidence_image": view.get("evidence_image"),
            "expected_evidence_sha256": view.get("evidence_sha256"),
            "evidence_review_state": view.get("evidence_review_state"),
            "golden_baseline_state": view.get("golden_baseline_state"),
        }
        evidence_path = None
        if view.get("evidence_image"):
            evidence_path = resolve_reference(GOLDEN_VIEWS, str(view["evidence_image"]))
            indexed_view["resolved_evidence_path"] = evidence_path.as_posix()
            indexed_view["evidence_exists"] = evidence_path.is_file()
            indexed_view["bytes"] = evidence_path.stat().st_size if evidence_path.is_file() else None
            indexed_view["actual_evidence_sha256"] = (
                sha256_file(evidence_path) if evidence_path.is_file() else None
            )
            indexed_view["evidence_hash_matches"] = bool(
                evidence_path.is_file()
                and indexed_view["actual_evidence_sha256"] == view.get("evidence_sha256")
            )
            evidence_assertions.append(
                assertion(
                    f"golden_evidence_{view.get('id')}_hash_matches",
                    indexed_view["evidence_hash_matches"],
                    {
                        "path": evidence_path.as_posix(),
                        "expected": view.get("evidence_sha256"),
                        "actual": indexed_view["actual_evidence_sha256"],
                    },
                )
            )
        else:
            indexed_view["resolved_evidence_path"] = None
            indexed_view["evidence_exists"] = False
            indexed_view["bytes"] = None
            indexed_view["actual_evidence_sha256"] = None
            indexed_view["evidence_hash_matches"] = None
        camera_id = str(view.get("camera_id", ""))
        if camera_id in views_by_camera:
            views_by_camera[camera_id].append(indexed_view)
        if str(view.get("id", "")).startswith("GV-WEB-"):
            web_blocked_views.append(indexed_view)

    actual_cameras = blender_audit.get("fixed_cameras", {})
    cameras = []
    for camera_id in EXPECTED_CAMERAS:
        camera_audit = actual_cameras.get(camera_id, {})
        cameras.append(
            {
                "camera_id": camera_id,
                "preset": lookdev.get("cameras", {}).get(camera_id),
                "blender_actual": camera_audit.get("actual"),
                "numeric_errors": camera_audit.get("numeric_errors"),
                "matches_preset": camera_audit.get("matches_preset", False),
                "p40_and_golden_views": views_by_camera[camera_id],
            }
        )
    index = {
        "schema_version": "bf3d.base00.fixed_camera_index.v1",
        "requirement_id": REQUIREMENT_ID,
        "stage": STAGE,
        "status": REPORT_STATUS,
        "approval": "not_granted_requires_visual_and_spec_review",
        "p40_lookdev_scope": P40_BOUNDARY,
        "golden_suite_status": golden.get("suite_status"),
        "golden_images_approved": lookdev.get("approval_boundaries", {}).get(
            "golden_images_approved"
        ),
        "camera_numeric_tolerance": CAMERA_TOLERANCE,
        "cameras": cameras,
        "web_views_not_captured_expected_blockers": web_blocked_views,
        "visual_capture_policy": {
            "new_capture_performed": False,
            "reason": (
                "The BASE-00 copy is byte-identical to the approved P40 source. "
                "Fourteen existing P40 fixed-camera evidence images are hash-checked and indexed; "
                "they remain not promoted to automated Golden baselines."
            ),
        },
    }
    return index, evidence_assertions


def build_output_hashes(output_dir: Path) -> dict[str, Any]:
    excluded = {"base00_output_sha256.json"}
    files = []
    for path in sorted(output_dir.iterdir(), key=lambda item: item.name.lower()):
        if path.is_file() and path.name not in excluded:
            files.append(
                {
                    "path": path.resolve().as_posix(),
                    "name": path.name,
                    "bytes": path.stat().st_size,
                    "sha256": sha256_file(path),
                }
            )
    return {
        "schema_version": "bf3d.base00.output_hashes.v1",
        "requirement_id": REQUIREMENT_ID,
        "stage": STAGE,
        "status": REPORT_STATUS,
        "files": files,
    }


def run_outer() -> int:
    args = outer_arg_parser().parse_args()
    output_dir = args.output_dir.resolve()
    if output_dir != DEFAULT_OUTPUT_DIR.resolve():
        raise ValueError(
            f"BASE-00 ownership restricts output to {DEFAULT_OUTPUT_DIR.resolve()}, got {output_dir}"
        )
    output_dir.mkdir(parents=True, exist_ok=True)
    log = ExecutionLog(output_dir / "base00_execution.log")
    log.emit(
        "base00_started",
        requirement_id=REQUIREMENT_ID,
        stage=STAGE,
        output_dir=output_dir.as_posix(),
    )

    report_path = output_dir / "base00_machine_report.json"
    manifest_path = output_dir / "base00_locked_assets_manifest.json"
    camera_index_path = output_dir / "base00_fixed_camera_index.json"
    locked_copy = output_dir / LOCKED_BLEND_NAME
    started_at = now_iso()
    try:
        for required in [
            SKILL_SOURCES_LOCK,
            SKILL_BUNDLE_MANIFEST,
            VISUAL_BIBLE,
            LOOKDEV_DOCUMENT,
            LOOKDEV_PRESET,
            GOLDEN_VIEWS,
            FORMAL_GLB,
            FORMAL_MANIFEST,
            P40_APPROVED_BLEND,
        ]:
            if not required.is_file():
                raise FileNotFoundError(required)
        blender = args.blender.resolve()
        if not blender.is_file():
            raise FileNotFoundError(f"Blender executable not found: {blender}")

        source_lock = read_json(SKILL_SOURCES_LOCK)
        bundle_manifest = read_json(SKILL_BUNDLE_MANIFEST)
        lookdev = read_json(LOOKDEV_PRESET)
        golden = read_json(GOLDEN_VIEWS)
        formal_manifest = read_json(FORMAL_MANIFEST)
        p40_report = read_json(P40_DIR / "p40_fixed_lookdev_candidate.json")
        p40_review = read_json(P40_DIR / "p40_visual_review.json")
        p50_report = read_json(P50_DIR / "p50_full_furnace_bake_candidate.json")
        p50_review = read_json(P50_DIR / "p50_master_4k_visual_review.json")
        p60_report = read_json(P60_DIR / "p60_preflight_report.json")
        p60_manifest = read_json(P60_DIR / "p60_preflight_manifest.json")
        p60_validator = read_json(P60_DIR / "gltf_validator_status.json")
        formal_glb_contract = read_glb_contract(FORMAL_GLB)

        input_locks = build_input_locks(
            source_lock,
            lookdev,
            golden,
            p40_report,
            p50_review,
            p60_report,
        )
        lock_assertions = [
            assertion(
                f"asset_lock_{item['asset_id']}",
                item["lock_ok"],
                {
                    "path": item["path"],
                    "bytes": item["bytes"],
                    "sha256": item["sha256"],
                    "expected_bytes": item["expected_bytes"],
                    "expected_sha256": item["expected_sha256"],
                },
            )
            for item in input_locks
        ]
        if not all(item["ok"] for item in lock_assertions):
            manifest = {
                "schema_version": "bf3d.base00.lock_manifest.v1",
                "requirement_id": REQUIREMENT_ID,
                "stage": STAGE,
                "status": "blocked",
                "approval": "not_granted",
                "generated_at": now_iso(),
                "assets": input_locks,
                "assertions": lock_assertions,
            }
            write_json(manifest_path, manifest)
            raise RuntimeError("One or more controlled input locks failed before copying P40")

        formal_before = {
            "glb": {
                "bytes": FORMAL_GLB.stat().st_size,
                "sha256": sha256_file(FORMAL_GLB),
            },
            "manifest": {
                "bytes": FORMAL_MANIFEST.stat().st_size,
                "sha256": sha256_file(FORMAL_MANIFEST),
            },
            "p40_approved_source": {
                "bytes": P40_APPROVED_BLEND.stat().st_size,
                "sha256": sha256_file(P40_APPROVED_BLEND),
            },
        }
        atomic_copy(P40_APPROVED_BLEND, locked_copy)
        copy_before_blender = {
            "bytes": locked_copy.stat().st_size,
            "sha256": sha256_file(locked_copy),
        }
        log.emit(
            "p40_approved_blend_copied",
            source=P40_APPROVED_BLEND.resolve().as_posix(),
            target=locked_copy.as_posix(),
            source_sha256=formal_before["p40_approved_source"]["sha256"],
            copy_sha256=copy_before_blender["sha256"],
        )
        copy_assertion = assertion(
            "base00_locked_copy_is_byte_identical_to_p40_approved",
            (
                copy_before_blender["bytes"]
                == formal_before["p40_approved_source"]["bytes"]
                and copy_before_blender["sha256"]
                == formal_before["p40_approved_source"]["sha256"]
            ),
            {
                "source": formal_before["p40_approved_source"],
                "copy": copy_before_blender,
            },
        )
        if not copy_assertion["ok"]:
            raise RuntimeError("BASE00_SOURCE_LOCKED.blend is not byte-identical to P40 approved")

        command = [
            str(blender),
            "--background",
            str(locked_copy),
            "--python",
            str(SCRIPT_PATH),
            "--",
            "--blender-audit-child",
            "--output-dir",
            str(output_dir),
            "--preset",
            str(LOOKDEV_PRESET),
        ]
        command_record = {
            "schema_version": "bf3d.base00.command.v1",
            "requirement_id": REQUIREMENT_ID,
            "stage": STAGE,
            "started_at": now_iso(),
            "cwd": PROJECT_ROOT.resolve().as_posix(),
            "argv": command,
            "display_command": subprocess.list2cmdline(command),
            "python": {
                "executable": Path(sys.executable).resolve().as_posix(),
                "version": sys.version,
            },
            "platform": platform.platform(),
        }
        write_json(output_dir / "base00_execution_command.json", command_record)
        log.emit(
            "blender_audit_started",
            command=command_record["display_command"],
        )
        completed = subprocess.run(
            command,
            cwd=PROJECT_ROOT,
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        (output_dir / "blender_stdout.log").write_text(
            completed.stdout, encoding="utf-8", newline="\n"
        )
        (output_dir / "blender_stderr.log").write_text(
            completed.stderr, encoding="utf-8", newline="\n"
        )
        log.emit(
            "blender_audit_finished",
            return_code=completed.returncode,
            stdout_bytes=len(completed.stdout.encode("utf-8")),
            stderr_bytes=len(completed.stderr.encode("utf-8")),
        )
        command_record["completed_at"] = now_iso()
        command_record["return_code"] = completed.returncode
        command_record["stdout_log"] = (output_dir / "blender_stdout.log").as_posix()
        command_record["stderr_log"] = (output_dir / "blender_stderr.log").as_posix()
        write_json(output_dir / "base00_execution_command.json", command_record)

        copy_after_blender = {
            "bytes": locked_copy.stat().st_size,
            "sha256": sha256_file(locked_copy),
        }
        formal_after = {
            "glb": {
                "bytes": FORMAL_GLB.stat().st_size,
                "sha256": sha256_file(FORMAL_GLB),
            },
            "manifest": {
                "bytes": FORMAL_MANIFEST.stat().st_size,
                "sha256": sha256_file(FORMAL_MANIFEST),
            },
            "p40_approved_source": {
                "bytes": P40_APPROVED_BLEND.stat().st_size,
                "sha256": sha256_file(P40_APPROVED_BLEND),
            },
        }
        audit_path = output_dir / "base00_blender_scene_audit.json"
        if not audit_path.is_file():
            raise RuntimeError(
                f"Blender did not create the machine audit; return code={completed.returncode}"
            )
        blender_audit = read_json(audit_path)
        formal_comparison_assertions, formal_comparison = compare_formal_to_blender(
            formal_glb_contract, blender_audit
        )
        camera_index, evidence_assertions = build_fixed_camera_index(
            lookdev, golden, blender_audit
        )
        write_json(camera_index_path, camera_index)

        boundary_assertions = [
            assertion(
                "formal_glb_manifest_matches_current_file",
                (
                    formal_manifest.get("bytes") == formal_before["glb"]["bytes"]
                    and formal_manifest.get("sha256") == formal_before["glb"]["sha256"]
                    and formal_manifest.get("sensor_nodes") == EXPECTED_SENSOR_COUNT
                    and formal_manifest.get("body_sensor_nodes") == EXPECTED_BODY_SENSOR_COUNT
                ),
                {
                    "manifest_bytes": formal_manifest.get("bytes"),
                    "actual_bytes": formal_before["glb"]["bytes"],
                    "manifest_sha256": formal_manifest.get("sha256"),
                    "actual_sha256": formal_before["glb"]["sha256"],
                    "manifest_sensor_nodes": formal_manifest.get("sensor_nodes"),
                    "manifest_body_sensor_nodes": formal_manifest.get("body_sensor_nodes"),
                },
            ),
            assertion(
                "formal_glb_contract_has_115_sensors",
                formal_glb_contract.get("sensor_count") == EXPECTED_SENSOR_COUNT,
                formal_glb_contract.get("sensor_count"),
            ),
            assertion(
                "formal_glb_contract_has_80_body_sensors",
                formal_glb_contract.get("body_sensor_count") == EXPECTED_BODY_SENSOR_COUNT,
                formal_glb_contract.get("body_sensor_count"),
            ),
            assertion(
                "formal_glb_has_ten_layers_of_eight",
                all(
                    formal_glb_contract["layers"][name]["exists"]
                    and len(formal_glb_contract["layers"][name]["children"]) == 8
                    for name in EXPECTED_LAYERS
                ),
                {
                    name: len(formal_glb_contract["layers"][name]["children"])
                    for name in EXPECTED_LAYERS
                },
            ),
            assertion(
                "formal_glb_has_five_process_zones",
                all(
                    formal_glb_contract["process_zones"].get(name) is not None
                    for name in EXPECTED_PROCESS_ZONES
                ),
                {
                    name: formal_glb_contract["process_zones"].get(name) is not None
                    for name in EXPECTED_PROCESS_ZONES
                },
            ),
            assertion(
                "p40_human_review_is_approved",
                p40_review.get("decision") == "approve",
                p40_review.get("decision"),
            ),
            assertion(
                "p40_lookdev_boundary_is_approved",
                lookdev.get("approval_boundaries", {}).get("p40_lookdev") == P40_BOUNDARY,
                lookdev.get("approval_boundaries", {}).get("p40_lookdev"),
            ),
            assertion(
                "p50_boundary_remains_pending_not_approved",
                (
                    p50_review.get("decision") == P50_BOUNDARY
                    and lookdev.get("approval_boundaries", {}).get("p50_material")
                    == P50_BOUNDARY
                    and golden.get("asset_locks", {}).get("p50") == P50_BOUNDARY
                ),
                {
                    "p50_review": p50_review.get("decision"),
                    "lookdev": lookdev.get("approval_boundaries", {}).get("p50_material"),
                    "golden": golden.get("asset_locks", {}).get("p50"),
                    "p50_machine_status": p50_report.get("status"),
                    "p50_machine_approval": p50_report.get("approval"),
                },
            ),
            assertion(
                "p60_boundary_remains_preflight_only",
                (
                    p60_report.get("approval") == P60_BOUNDARY
                    and p60_manifest.get("approval") == P60_BOUNDARY
                    and lookdev.get("approval_boundaries", {}).get("p60_asset")
                    == P60_BOUNDARY
                    and golden.get("asset_locks", {}).get("p60") == P60_BOUNDARY
                    and p60_report.get("p60_approved") is False
                    and p60_report.get("p60_gate_ok") is False
                ),
                {
                    "p60_report": p60_report.get("approval"),
                    "p60_manifest": p60_manifest.get("approval"),
                    "lookdev": lookdev.get("approval_boundaries", {}).get("p60_asset"),
                    "golden": golden.get("asset_locks", {}).get("p60"),
                    "p60_approved": p60_report.get("p60_approved"),
                    "p60_gate_ok": p60_report.get("p60_gate_ok"),
                    "validator": p60_validator.get("status"),
                },
            ),
            assertion(
                "formal_glb_replacement_remains_false",
                (
                    lookdev.get("approval_boundaries", {}).get("formal_glb_replaced") is False
                    and golden.get("asset_locks", {})
                    .get("formal_glb", {})
                    .get("replaced_by_p50_or_p60")
                    is False
                ),
                {
                    "lookdev": lookdev.get("approval_boundaries", {}).get(
                        "formal_glb_replaced"
                    ),
                    "golden": golden.get("asset_locks", {})
                    .get("formal_glb", {})
                    .get("replaced_by_p50_or_p60"),
                },
            ),
            assertion(
                "formal_glb_unchanged_during_base00",
                formal_before["glb"] == formal_after["glb"],
                {"before": formal_before["glb"], "after": formal_after["glb"]},
            ),
            assertion(
                "formal_manifest_unchanged_during_base00",
                formal_before["manifest"] == formal_after["manifest"],
                {"before": formal_before["manifest"], "after": formal_after["manifest"]},
            ),
            assertion(
                "p40_approved_source_unchanged_during_base00",
                formal_before["p40_approved_source"] == formal_after["p40_approved_source"],
                {
                    "before": formal_before["p40_approved_source"],
                    "after": formal_after["p40_approved_source"],
                },
            ),
            assertion(
                "base00_locked_copy_unchanged_by_blender_audit",
                copy_before_blender == copy_after_blender,
                {"before": copy_before_blender, "after": copy_after_blender},
            ),
            assertion(
                "blender_child_returned_success",
                completed.returncode == 0,
                completed.returncode,
            ),
            assertion(
                "blender_machine_audit_passed",
                blender_audit.get("status") == "audit_passed",
                {
                    "status": blender_audit.get("status"),
                    "assertion_summary": blender_audit.get("assertion_summary"),
                },
            ),
            assertion(
                "blender_version_matches_controlled_lookdev",
                blender_audit.get("blender", {}).get("version_string")
                == lookdev.get("blender", {}).get("version"),
                {
                    "actual": blender_audit.get("blender", {}).get("version_string"),
                    "expected": lookdev.get("blender", {}).get("version"),
                },
            ),
            assertion(
                "skill_bundle_contains_required_workflow",
                (
                    bundle_manifest.get("entry_skill") == "bf3d-orchestrate"
                    and "bf3d-geometry-audit" in bundle_manifest.get("skills", [])
                ),
                {
                    "entry_skill": bundle_manifest.get("entry_skill"),
                    "skills": bundle_manifest.get("skills"),
                },
            ),
        ]
        all_assertions = [
            *lock_assertions,
            copy_assertion,
            *boundary_assertions,
            *formal_comparison_assertions,
            *blender_audit.get("assertions", []),
            *evidence_assertions,
        ]
        failures = [item for item in all_assertions if not item.get("ok")]
        status = REPORT_STATUS if not failures else "blocked"
        approval_boundaries = {
            "p40_lookdev": P40_BOUNDARY,
            "p50_material": P50_BOUNDARY,
            "p60_asset": P60_BOUNDARY,
            "formal_glb_replaced": False,
            "formal_glb_sha256": formal_after["glb"]["sha256"],
            "golden_images_approved": False,
            "base00_self_approval": "not_granted_requires_independent_review",
        }
        manifest = {
            "schema_version": "bf3d.base00.lock_manifest.v1",
            "requirement_id": REQUIREMENT_ID,
            "stage": STAGE,
            "status": status,
            "approval": "not_granted_requires_visual_and_spec_review",
            "generated_at": now_iso(),
            "source_lock": {
                "path": SKILL_SOURCES_LOCK.resolve().as_posix(),
                "locked_at": source_lock.get("locked_at"),
                "policy": source_lock.get("policy"),
            },
            "skill_bundle": {
                "path": SKILL_BUNDLE_MANIFEST.resolve().as_posix(),
                "bundle_id": bundle_manifest.get("bundle_id"),
                "pack_version": bundle_manifest.get("pack_version"),
                "entry_skill": bundle_manifest.get("entry_skill"),
            },
            "approval_boundaries": approval_boundaries,
            "isolated_checkpoint": {
                "source": P40_APPROVED_BLEND.resolve().as_posix(),
                "source_bytes": formal_before["p40_approved_source"]["bytes"],
                "source_sha256": formal_before["p40_approved_source"]["sha256"],
                "copy": locked_copy.as_posix(),
                "copy_bytes": copy_after_blender["bytes"],
                "copy_sha256": copy_after_blender["sha256"],
                "byte_identical": copy_assertion["ok"],
                "content_modified": False,
            },
            "assets": input_locks,
            "asset_summary": {
                "count": len(input_locks),
                "locked_ok": sum(item["lock_ok"] for item in input_locks),
                "failed": sum(not item["lock_ok"] for item in input_locks),
            },
        }
        write_json(manifest_path, manifest)

        report = {
            "schema_version": "bf3d.base00.machine_report.v1",
            "requirement_id": REQUIREMENT_ID,
            "stage": STAGE,
            "status": status,
            "approval": "not_granted_requires_visual_and_spec_review",
            "started_at": started_at,
            "completed_at": now_iso(),
            "single_changed_dimension": (
                "None. BASE-00 only locks and audits a byte-identical copy of the approved P40 scene."
            ),
            "scope": {
                "writes_allowed": [
                    SCRIPT_PATH.resolve().as_posix(),
                    output_dir.as_posix() + "/**",
                ],
                "production_glb_modified": False,
                "production_manifest_modified": False,
                "p40_approved_source_modified": False,
                "p50_or_p60_asset_modified": False,
                "web_modified": False,
                "database_modified": False,
                "new_render_performed": False,
            },
            "approval_boundaries": approval_boundaries,
            "commands": {
                "outer": subprocess.list2cmdline(
                    [str(Path(sys.executable).resolve()), str(SCRIPT_PATH)]
                ),
                "blender": command_record["display_command"],
                "blender_return_code": completed.returncode,
            },
            "artifacts": {
                "isolated_checkpoint": locked_copy.as_posix(),
                "lock_manifest": manifest_path.as_posix(),
                "blender_scene_audit": audit_path.as_posix(),
                "fixed_camera_index": camera_index_path.as_posix(),
                "execution_command": (
                    output_dir / "base00_execution_command.json"
                ).as_posix(),
                "execution_log": log.path.as_posix(),
                "blender_stdout": (output_dir / "blender_stdout.log").as_posix(),
                "blender_stderr": (output_dir / "blender_stderr.log").as_posix(),
            },
            "formal_glb_contract": formal_glb_contract,
            "formal_to_p40_comparison": formal_comparison,
            "blender_audit_summary": {
                "blender": blender_audit.get("blender"),
                "scene_counts": blender_audit.get("scene", {}).get("counts"),
                "unit_settings": blender_audit.get("scene", {}).get("unit_settings"),
                "world_origin_m": blender_audit.get("scene", {}).get("world_origin_m"),
                "cursor_location_m": blender_audit.get("scene", {}).get(
                    "cursor_location_m"
                ),
                "bounds": blender_audit.get("scene", {}).get("bounds"),
                "sensor_count": blender_audit.get("protected_contract", {}).get(
                    "sensor_count"
                ),
                "body_sensor_count": blender_audit.get("protected_contract", {}).get(
                    "body_sensor_count_by_group"
                ),
                "sensor_contract_sha256": blender_audit.get(
                    "protected_contract", {}
                ).get("sensor_contract_sha256"),
                "layers": blender_audit.get("protected_contract", {}).get("layers"),
                "process_zones": blender_audit.get("protected_contract", {}).get(
                    "process_zones"
                ),
                "fixed_camera_count": len(
                    [
                        camera
                        for camera in blender_audit.get("fixed_cameras", {}).values()
                        if camera.get("matches_preset")
                    ]
                ),
            },
            "assertions": all_assertions,
            "assertion_summary": {
                "total": len(all_assertions),
                "passed": len(all_assertions) - len(failures),
                "failed": len(failures),
                "failed_ids": [item.get("id") for item in failures],
            },
            "known_non_base00_blockers": [
                {
                    "id": "P50_PENDING",
                    "state": P50_BOUNDARY,
                    "impact": "P50 cannot be treated as approved or used to replace the formal GLB.",
                },
                {
                    "id": "P60_PREFLIGHT_ONLY",
                    "state": P60_BOUNDARY,
                    "impact": "P60 remains an isolated uncompressed preflight; Khronos Validator is unavailable.",
                },
                {
                    "id": "GOLDEN_NOT_PROMOTED",
                    "state": golden.get("suite_status"),
                    "impact": "Existing P40 PNGs are evidence for P40 scope, not signed automated Golden baselines.",
                },
                {
                    "id": "WEB_GOLDEN_NOT_CAPTURED",
                    "state": "blocked",
                    "impact": "Preset loading, camera-basis conversion, HDRI/PMREM, and Web cross-engine views remain future work.",
                },
                {
                    "id": "HDRI_NOT_VISUAL_APPROVED",
                    "state": lookdev.get("environment_assets", {})
                    .get("industrial_sunset_candidate", {})
                    .get("status"),
                    "impact": "The registered CC0 HDRI remains a candidate and was not used for P40 approval.",
                },
            ],
            "review_handoff": {
                "candidate_ready_for_review": not failures,
                "required_reviewers": [
                    "visual_quality_reviewer",
                    "spec_compliance_reviewer",
                ],
                "self_approved": False,
                "next_stage_authorized": False,
                "rule": (
                    "Only the root controller may promote BASE-00 after independent visual and "
                    "spec-compliance review. This runner never emits approved."
                ),
            },
            "rollback_point": {
                "path": locked_copy.as_posix(),
                "sha256": copy_after_blender["sha256"],
                "action": (
                    "Delete only work/BASE_00_20260718_R1 if the candidate is rejected; "
                    "all upstream and production assets remain unchanged."
                ),
            },
        }
        write_json(report_path, report)
        log.emit(
            "base00_checks_completed",
            status=status,
            assertion_total=len(all_assertions),
            assertion_failed=len(failures),
            failed_ids=[item.get("id") for item in failures],
        )
        output_hashes = build_output_hashes(output_dir)
        write_json(output_dir / "base00_output_sha256.json", output_hashes)
        log.emit(
            "base00_finished",
            status=status,
            report=report_path.as_posix(),
            manifest=manifest_path.as_posix(),
            fixed_camera_index=camera_index_path.as_posix(),
        )
        # Refresh the hash list after the final log entries. The hash list intentionally
        # excludes itself to avoid a self-referential checksum.
        write_json(output_dir / "base00_output_sha256.json", build_output_hashes(output_dir))
        print(
            json.dumps(
                {
                    "requirement_id": REQUIREMENT_ID,
                    "stage": STAGE,
                    "status": status,
                    "approval": report["approval"],
                    "output_dir": output_dir.as_posix(),
                    "assertions": report["assertion_summary"],
                    "p40": P40_BOUNDARY,
                    "p50": P50_BOUNDARY,
                    "p60": P60_BOUNDARY,
                    "formal_glb_replaced": False,
                    "formal_glb_sha256": formal_after["glb"]["sha256"],
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return 0 if status == REPORT_STATUS else 4
    except Exception as error:
        log.emit(
            "base00_failed",
            error_type=type(error).__name__,
            error=str(error),
            traceback=traceback.format_exc(),
        )
        failure = {
            "schema_version": "bf3d.base00.machine_report.v1",
            "requirement_id": REQUIREMENT_ID,
            "stage": STAGE,
            "status": "blocked",
            "approval": "not_granted",
            "started_at": started_at,
            "completed_at": now_iso(),
            "error": {
                "type": type(error).__name__,
                "message": str(error),
                "traceback": traceback.format_exc(),
            },
            "approval_boundaries": {
                "p40_lookdev": P40_BOUNDARY,
                "p50_material": P50_BOUNDARY,
                "p60_asset": P60_BOUNDARY,
                "formal_glb_replaced": False,
                "base00_self_approval": "not_granted",
            },
        }
        write_json(report_path, failure)
        write_json(output_dir / "base00_output_sha256.json", build_output_hashes(output_dir))
        print(json.dumps(failure, ensure_ascii=False, indent=2))
        return 5


def main() -> int:
    if "--blender-audit-child" in blender_cli_args():
        try:
            return run_blender_child()
        except Exception as error:
            args = child_arg_parser().parse_args(blender_cli_args())
            output_dir = args.output_dir.resolve()
            output_dir.mkdir(parents=True, exist_ok=True)
            write_json(
                output_dir / "base00_blender_scene_audit_failed.json",
                {
                    "schema_version": "bf3d.base00.blender_audit_failure.v1",
                    "requirement_id": REQUIREMENT_ID,
                    "stage": STAGE,
                    "status": "audit_failed",
                    "approval": "not_granted",
                    "error": {
                        "type": type(error).__name__,
                        "message": str(error),
                        "traceback": traceback.format_exc(),
                    },
                },
            )
            traceback.print_exc()
            return 6
    return run_outer()


if __name__ == "__main__":
    sys.exit(main())
