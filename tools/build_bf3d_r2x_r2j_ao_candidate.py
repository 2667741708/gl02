"""Build and audit the WEB-60 R2X five-shell 1K AO smoke candidate.

Requirement:
    REQ-BF3D-R2X-R2J-AO-REBAKE-CONSUMPTION-20260720

This file is deliberately self-contained.  The normal Python entry point
launches the locked V5 Blend in Blender, while the ``--blender-child`` entry
points perform the controlled build and reopen validation.  No historical UV
builder is imported or called.

The stage is a smoke candidate only.  It never overwrites V5/formal assets and
never grants P50, production integration, or a next release stage.
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import math
import os
import shutil
import struct
import subprocess
import sys
import time
import traceback
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

try:
    import bpy  # type: ignore
    import numpy as np  # type: ignore
except ModuleNotFoundError:
    bpy = None
    np = None


ROOT = Path(__file__).resolve().parents[1]
STAGE = (
    ROOT
    / "PT"
    / "高炉3D模型"
    / "work"
    / "WEB_60_20260720_R2X_R2J_AO_REBAKE_CANDIDATE"
)
BLEND_DIR = STAGE / "blends"
TEXTURE_DIR = STAGE / "textures"
REPORT_DIR = STAGE / "reports"
GLB_DIR = STAGE / "glb"

INPUT_BLEND = (
    ROOT / "高炉前端数据" / "models" / "gl02_blast_furnace_review.v5.blend"
)
INPUT_MATERIAL_GLB = (
    ROOT
    / "高炉前端数据"
    / "models"
    / "gl02_blast_furnace_material_review.v5.glb"
)
OUTPUT_BLEND = BLEND_DIR / "gl02_blast_furnace_review.r2x-ao-smoke1k.blend"
OUTPUT_PNG = TEXTURE_DIR / "GL02_R2J_LOCAL_CONTACT_AO_1K.png"
OUTPUT_GLB = (
    GLB_DIR / "gl02_blast_furnace_material_review.r2x-ao-smoke1k.glb"
)
BUILD_REPORT = REPORT_DIR / "r2x_ao_smoke1k_build_report.json"
REOPEN_REPORT = REPORT_DIR / "r2x_ao_smoke1k_reopen_report.json"
BLENDER_LOG = REPORT_DIR / "r2x_ao_smoke1k_blender.log"
KHRONOS_REPORT = REPORT_DIR / "khronos_gltf_validator_r2x_ao_smoke1k.json"

DEFAULT_BLENDER = Path(
    r"D:\Program Files\Blender Foundation\Blender 5.2\blender.exe"
)
KHRONOS_MODULE = (
    ROOT
    / "PT"
    / "高炉3D模型"
    / "work"
    / "WEB_60_20260720_R2U_SECTION_CAP_CONTROLLED_V4"
    / "vendor"
    / "gltf-validator-runtime"
    / "node_modules"
    / "gltf-validator"
)

STAGE_ID = "WEB_60_20260720_R2X_R2J_AO_REBAKE_CANDIDATE"
REQUIREMENT_ID = "REQ-BF3D-R2X-R2J-AO-REBAKE-CONSUMPTION-20260720"
SCHEMA_VERSION = "bf3d.r2x.r2j_ao_smoke1k.build.v1"
UV0_NAME = "BF3D_R5_EXTERIOR_UV_1M"
UV1_NAME = "BF3D_INTERNAL_UV_1M"
UV2_NAME = "BF3D_R2X_AO_UV"
AO_IMAGE_NAME = "GL02_R2J_LOCAL_CONTACT_AO_1K"
TEXTURE_SIZE = 1024
BAKE_MARGIN_PX = 4
CELL_PADDING_PX = 8
CELL_GAP_PX = 12
AO_DISTANCE_M = 0.12
AO_STRENGTH = 0.28
AO_FLOOR = 0.78
AO_SAMPLES = 32

TARGETS = (
    "R2J_ASM_GL02_FURNACE_HEARTH_SHELL_65MM_E",
    "R2J_ASM_GL02_FURNACE_BOSH_SHELL_55MM_E",
    "R2J_ASM_GL02_FURNACE_BELLY_SHELL_55MM_E",
    "R2J_ASM_GL02_FURNACE_SHAFT_SHELL_45MM_E",
    "R2J_ASM_GL02_FURNACE_THROAT_SHELL_45MM_E",
)

# Pixel coordinates are bottom-left based.  The belly receives a full-width
# shallow shelf because its cylindrical unwrap is much wider than it is high.
# The remaining shells occupy a guarded 2x2 grid.  Each source UV0 rectangle is
# fit uniformly into its cell, so the mapping is deterministic and preserves
# orientation without using smart-project or any legacy R2J UV function.
ATLAS_CELLS_PX: dict[str, tuple[int, int, int, int]] = {
    "R2J_ASM_GL02_FURNACE_BELLY_SHELL_55MM_E": (8, 8, 1016, 88),
    "R2J_ASM_GL02_FURNACE_HEARTH_SHELL_65MM_E": (8, 100, 506, 552),
    "R2J_ASM_GL02_FURNACE_BOSH_SHELL_55MM_E": (518, 100, 1016, 552),
    "R2J_ASM_GL02_FURNACE_SHAFT_SHELL_45MM_E": (8, 564, 506, 1016),
    "R2J_ASM_GL02_FURNACE_THROAT_SHELL_45MM_E": (518, 564, 1016, 1016),
}

PROTECTED_INPUTS: dict[str, tuple[Path, str]] = {
    "v5_blend": (
        INPUT_BLEND,
        "3e6df5fb02d3734d14923d4432739a5918ac8249d6a3c8ad1415395429b27e3a",
    ),
    "v5_unified_glb": (
        ROOT
        / "高炉前端数据"
        / "models"
        / "gl02_blast_furnace_review.v5.glb",
        "0ac031e626c9eaa0b0cdd8192cf9fda712324af174a4285f563a97309451ed3c",
    ),
    "v5_material_glb": (
        INPUT_MATERIAL_GLB,
        "652be1b2c9147d5a7392497c7ae4964d19bdd7095b5435b87c105f9eb3fb66bc",
    ),
    "v5_structural_glb": (
        ROOT
        / "高炉前端数据"
        / "models"
        / "gl02_blast_furnace_structural_review.v5.glb",
        "e5c77d3834c631e2513209a690f6328d1c63dba2c8d489b2d2dbe17645465f71",
    ),
    "formal_glb": (
        ROOT / "高炉前端数据" / "models" / "gl02_blast_furnace.glb",
        "808960f1b2703e7fb27df35f1b1b1a17063b9b10d2267acba593fc3872b62af6",
    ),
    "current_orm_4k": (
        ROOT
        / "PT"
        / "高炉3D模型"
        / "work"
        / "INT_30_20260718_R2G_ISOLATED_GLB_WEB_PREVIEW"
        / "textures"
        / "final_4k"
        / "INT30_R2G_R1_LOCK_ORM_4K.png",
        "e3354cc5d793807ebb4f6b0d74593a7b6f09f18fcece8f9102e867f2c8570e17",
    ),
}

APPROVAL_STOP_LINES = {
    "approval_granted": False,
    "p50_approved": False,
    "production_integration_allowed": False,
    "next_release_stage_allowed": False,
}


class BuildError(RuntimeError):
    """Raised for a fail-closed R2X contract violation."""


def now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def stable_sha(value: Any) -> str:
    payload = json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def file_record(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {"path": str(path), "exists": False}
    return {
        "path": str(path),
        "exists": True,
        "bytes": path.stat().st_size,
        "sha256": sha256_file(path),
    }


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )


def ensure_stage_paths(output_root: Path) -> None:
    if output_root.resolve() != STAGE.resolve():
        raise BuildError(
            f"R2X outputs are restricted to the preregistered stage: {STAGE}"
        )
    for directory in (BLEND_DIR, TEXTURE_DIR, REPORT_DIR, GLB_DIR):
        directory.mkdir(parents=True, exist_ok=True)


def protected_snapshot() -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, (path, expected) in PROTECTED_INPUTS.items():
        record = file_record(path)
        record["expected_sha256"] = expected
        record["matches_expected"] = (
            record.get("exists") and record.get("sha256") == expected
        )
        result[key] = record
    return result


def assert_protected_snapshot(snapshot: dict[str, Any]) -> None:
    failed = [
        key for key, record in snapshot.items() if not record["matches_expected"]
    ]
    if failed:
        raise BuildError(f"Locked input hash gate failed: {failed}")


def hash_floats(values: Iterable[float]) -> str:
    digest = hashlib.sha256()
    for value in values:
        digest.update(struct.pack("<d", float(value)))
    return digest.hexdigest()


def uv_layer_record(mesh: Any, index: int) -> dict[str, Any]:
    layer = mesh.uv_layers[index]
    digest = hashlib.sha256()
    minimum_u = math.inf
    maximum_u = -math.inf
    minimum_v = math.inf
    maximum_v = -math.inf
    nonfinite = 0
    for loop_index, item in enumerate(layer.uv):
        u = float(item.vector.x)
        v = float(item.vector.y)
        digest.update(struct.pack("<Iff", loop_index, u, v))
        if not math.isfinite(u) or not math.isfinite(v):
            nonfinite += 1
        minimum_u = min(minimum_u, u)
        maximum_u = max(maximum_u, u)
        minimum_v = min(minimum_v, v)
        maximum_v = max(maximum_v, v)
    return {
        "index": index,
        "name": layer.name,
        "active": mesh.uv_layers.active_index == index,
        "active_render": bool(layer.active_render),
        "loop_count": len(layer.uv),
        "loop_sha256": digest.hexdigest(),
        "finite": nonfinite == 0,
        "nonfinite_count": nonfinite,
        "bounds": {
            "min_u": minimum_u,
            "max_u": maximum_u,
            "min_v": minimum_v,
            "max_v": maximum_v,
        },
    }


def mesh_topology_sha256(mesh: Any) -> str:
    digest = hashlib.sha256()
    digest.update(
        struct.pack(
            "<IIII",
            len(mesh.vertices),
            len(mesh.edges),
            len(mesh.polygons),
            len(mesh.loops),
        )
    )
    for vertex in mesh.vertices:
        digest.update(
            struct.pack(
                "<Ifff",
                vertex.index,
                float(vertex.co.x),
                float(vertex.co.y),
                float(vertex.co.z),
            )
        )
    for edge in mesh.edges:
        digest.update(
            struct.pack(
                "<III", edge.index, int(edge.vertices[0]), int(edge.vertices[1])
            )
        )
    for polygon in mesh.polygons:
        digest.update(
            struct.pack(
                "<IIII",
                polygon.index,
                polygon.loop_start,
                polygon.loop_total,
                len(polygon.vertices),
            )
        )
        for vertex_index in polygon.vertices:
            digest.update(struct.pack("<I", int(vertex_index)))
    for loop in mesh.loops:
        digest.update(
            struct.pack(
                "<III", loop.index, int(loop.vertex_index), int(loop.edge_index)
            )
        )
    return digest.hexdigest()


def polygon_material_index_sha256(mesh: Any) -> str:
    digest = hashlib.sha256()
    for polygon in mesh.polygons:
        digest.update(struct.pack("<II", polygon.index, polygon.material_index))
    return digest.hexdigest()


def matrix_record(matrix: Any) -> dict[str, Any]:
    values = [float(matrix[row][column]) for row in range(4) for column in range(4)]
    return {"values": values, "sha256": hash_floats(values)}


def object_snapshot(obj: Any) -> dict[str, Any]:
    mesh = obj.data
    return {
        "object_name": obj.name,
        "mesh_name": mesh.name,
        "mesh_counts": {
            "vertices": len(mesh.vertices),
            "edges": len(mesh.edges),
            "polygons": len(mesh.polygons),
            "loops": len(mesh.loops),
        },
        "mesh_topology_sha256": mesh_topology_sha256(mesh),
        "transform": {
            "matrix_world": matrix_record(obj.matrix_world),
            "location": [float(value) for value in obj.location],
            "rotation_euler": [float(value) for value in obj.rotation_euler],
            "scale": [float(value) for value in obj.scale],
        },
        "material_slot_count": len(obj.material_slots),
        "material_slots": [
            {
                "index": index,
                "name": slot.material.name if slot.material else None,
                "link": slot.link,
            }
            for index, slot in enumerate(obj.material_slots)
        ],
        "polygon_material_index_sha256": polygon_material_index_sha256(mesh),
        "polygon_material_index_counts": {
            str(index): count
            for index, count in sorted(
                Counter(poly.material_index for poly in mesh.polygons).items()
            )
        },
        "uv_layers": [
            uv_layer_record(mesh, index) for index in range(len(mesh.uv_layers))
        ],
    }


def get_targets(expect_uv2: bool = False) -> list[Any]:
    result = []
    expected_names = [UV0_NAME, UV1_NAME, UV2_NAME] if expect_uv2 else [
        UV0_NAME,
        UV1_NAME,
    ]
    for name in TARGETS:
        obj = bpy.data.objects.get(name)
        if obj is None or obj.type != "MESH":
            raise BuildError(f"Missing locked R2J shell target: {name}")
        if len(obj.data.uv_layers) != len(expected_names):
            raise BuildError(
                f"{name} UV layer count mismatch; expected {expected_names}, got "
                f"{[layer.name for layer in obj.data.uv_layers]}"
            )
        if [layer.name for layer in obj.data.uv_layers] != expected_names:
            raise BuildError(
                f"{name} UV order/name mismatch: "
                f"{[layer.name for layer in obj.data.uv_layers]}"
            )
        if len(obj.material_slots) != 3:
            raise BuildError(
                f"{name} must retain the locked three material slots"
            )
        result.append(obj)
    return result


def bounds_intersect(
    first: dict[str, float],
    second: dict[str, float],
    expansion: float = 0.0,
) -> bool:
    return (
        first["min_u"] - expansion < second["max_u"] + expansion
        and first["max_u"] + expansion > second["min_u"] - expansion
        and first["min_v"] - expansion < second["max_v"] + expansion
        and first["max_v"] + expansion > second["min_v"] - expansion
    )


def bounds_separation(first: dict[str, float], second: dict[str, float]) -> float:
    separation_u = max(
        second["min_u"] - first["max_u"],
        first["min_u"] - second["max_u"],
        0.0,
    )
    separation_v = max(
        second["min_v"] - first["max_v"],
        first["min_v"] - second["max_v"],
        0.0,
    )
    return max(separation_u, separation_v)


def append_deterministic_uv2(targets: list[Any]) -> dict[str, Any]:
    records: dict[str, Any] = {}
    actual_bounds: dict[str, dict[str, float]] = {}
    for obj in targets:
        mesh = obj.data
        original_active_index = mesh.uv_layers.active_index
        original_render = [bool(layer.active_render) for layer in mesh.uv_layers]
        source = mesh.uv_layers[UV0_NAME]
        source_values = [
            (float(item.vector.x), float(item.vector.y)) for item in source.uv
        ]
        if not source_values or any(
            not math.isfinite(value)
            for pair in source_values
            for value in pair
        ):
            raise BuildError(f"{obj.name} UV0 is empty or non-finite")
        source_bounds = {
            "min_u": min(item[0] for item in source_values),
            "max_u": max(item[0] for item in source_values),
            "min_v": min(item[1] for item in source_values),
            "max_v": max(item[1] for item in source_values),
        }
        source_width = source_bounds["max_u"] - source_bounds["min_u"]
        source_height = source_bounds["max_v"] - source_bounds["min_v"]
        if source_width <= 0.0 or source_height <= 0.0:
            raise BuildError(f"{obj.name} UV0 has a degenerate bounding rectangle")

        cell_px = ATLAS_CELLS_PX[obj.name]
        inner_px = (
            cell_px[0] + CELL_PADDING_PX,
            cell_px[1] + CELL_PADDING_PX,
            cell_px[2] - CELL_PADDING_PX,
            cell_px[3] - CELL_PADDING_PX,
        )
        available_width = (inner_px[2] - inner_px[0]) / TEXTURE_SIZE
        available_height = (inner_px[3] - inner_px[1]) / TEXTURE_SIZE
        scale = min(
            available_width / source_width,
            available_height / source_height,
        )
        packed_width = source_width * scale
        packed_height = source_height * scale
        center_u = (inner_px[0] + inner_px[2]) / (2.0 * TEXTURE_SIZE)
        center_v = (inner_px[1] + inner_px[3]) / (2.0 * TEXTURE_SIZE)
        source_center_u = (source_bounds["min_u"] + source_bounds["max_u"]) * 0.5
        source_center_v = (source_bounds["min_v"] + source_bounds["max_v"]) * 0.5

        layer = mesh.uv_layers.new(name=UV2_NAME, do_init=False)
        for loop_index, (source_u, source_v) in enumerate(source_values):
            layer.uv[loop_index].vector = (
                center_u + (source_u - source_center_u) * scale,
                center_v + (source_v - source_center_v) * scale,
            )
        mesh.uv_layers.active_index = original_active_index
        for index, active_render in enumerate(original_render):
            mesh.uv_layers[index].active_render = active_render
        layer.active_render = False
        mesh.update()

        record = uv_layer_record(mesh, 2)
        bounds = record["bounds"]
        actual_bounds[obj.name] = bounds
        cell_bounds = {
            "min_u": cell_px[0] / TEXTURE_SIZE,
            "max_u": cell_px[2] / TEXTURE_SIZE,
            "min_v": cell_px[1] / TEXTURE_SIZE,
            "max_v": cell_px[3] / TEXTURE_SIZE,
        }
        padding_values = [
            (bounds["min_u"] - cell_bounds["min_u"]) * TEXTURE_SIZE,
            (cell_bounds["max_u"] - bounds["max_u"]) * TEXTURE_SIZE,
            (bounds["min_v"] - cell_bounds["min_v"]) * TEXTURE_SIZE,
            (cell_bounds["max_v"] - bounds["max_v"]) * TEXTURE_SIZE,
        ]
        records[obj.name] = {
            "source_uv": UV0_NAME,
            "source_bounds": source_bounds,
            "cell_px": list(cell_px),
            "cell_bounds_uv": cell_bounds,
            "uniform_scale": scale,
            "bounds": bounds,
            "finite": record["finite"],
            "in_range": (
                bounds["min_u"] >= -1.0e-7
                and bounds["max_u"] <= 1.0 + 1.0e-7
                and bounds["min_v"] >= -1.0e-7
                and bounds["max_v"] <= 1.0 + 1.0e-7
            ),
            "padding_px": min(padding_values),
            "padding_uv": min(padding_values) / TEXTURE_SIZE,
            "padding_by_side_px": {
                "left": padding_values[0],
                "right": padding_values[1],
                "bottom": padding_values[2],
                "top": padding_values[3],
            },
            "uv2_loop_sha256": record["loop_sha256"],
            "loop_count": record["loop_count"],
        }

    overlap_pairs: list[list[str]] = []
    expanded_overlap_pairs: list[list[str]] = []
    separations = []
    expansion = BAKE_MARGIN_PX / TEXTURE_SIZE
    for index, first_name in enumerate(TARGETS):
        for second_name in TARGETS[index + 1 :]:
            first = actual_bounds[first_name]
            second = actual_bounds[second_name]
            separation = bounds_separation(first, second)
            separations.append(
                {
                    "first": first_name,
                    "second": second_name,
                    "separation_uv": separation,
                    "separation_px": separation * TEXTURE_SIZE,
                }
            )
            if bounds_intersect(first, second):
                overlap_pairs.append([first_name, second_name])
            if bounds_intersect(first, second, expansion=expansion):
                expanded_overlap_pairs.append([first_name, second_name])
    return {
        "layout_id": "r2x_fixed_belly_shelf_plus_2x2_v1",
        "derivation": "UV2 is an affine, orientation-preserving copy of locked UV0",
        "legacy_prepare_r2j_uv_called": False,
        "smart_project_called": False,
        "texture_size": TEXTURE_SIZE,
        "cell_padding_px": CELL_PADDING_PX,
        "cell_padding_uv": CELL_PADDING_PX / TEXTURE_SIZE,
        "cell_gap_px": CELL_GAP_PX,
        "cell_gap_uv": CELL_GAP_PX / TEXTURE_SIZE,
        "bake_margin_px": BAKE_MARGIN_PX,
        "bake_margin_uv": BAKE_MARGIN_PX / TEXTURE_SIZE,
        "objects": records,
        "overlap_pairs": overlap_pairs,
        "expanded_overlap_pairs": expanded_overlap_pairs,
        "pairwise_separations": separations,
        "minimum_pairwise_separation_px": min(
            item["separation_px"] for item in separations
        ),
        "finite": all(item["finite"] for item in records.values()),
        "in_range": all(item["in_range"] for item in records.values()),
        "all_cross_object_disjoint": not overlap_pairs,
        "all_bake_margin_expanded_disjoint": not expanded_overlap_pairs,
    }


def selection_snapshot() -> dict[str, Any]:
    active = bpy.context.view_layer.objects.active
    return {
        "selected": sorted(obj.name for obj in bpy.context.selected_objects),
        "active": active.name if active else None,
        "mode": active.mode if active else "OBJECT",
    }


def visibility_snapshot() -> dict[str, Any]:
    return {
        obj.name: {
            "hide_render": bool(obj.hide_render),
            "hide_viewport": bool(obj.hide_viewport),
            "hide_set": bool(obj.hide_get()),
        }
        for obj in bpy.data.objects
    }


def collection_visibility_snapshot() -> dict[str, Any]:
    return {
        collection.name: {
            "hide_render": bool(collection.hide_render),
            "hide_viewport": bool(collection.hide_viewport),
        }
        for collection in bpy.data.collections
    }


def restore_visibility(snapshot: dict[str, Any]) -> None:
    for name, state in snapshot.items():
        obj = bpy.data.objects.get(name)
        if obj is None:
            continue
        obj.hide_render = state["hide_render"]
        obj.hide_viewport = state["hide_viewport"]
        obj.hide_set(state["hide_set"])


def restore_collection_visibility(snapshot: dict[str, Any]) -> None:
    for name, state in snapshot.items():
        collection = bpy.data.collections.get(name)
        if collection is None:
            continue
        collection.hide_render = state["hide_render"]
        collection.hide_viewport = state["hide_viewport"]


def restore_selection(snapshot: dict[str, Any]) -> None:
    active = bpy.context.view_layer.objects.active
    if active is not None and active.mode != "OBJECT":
        bpy.ops.object.mode_set(mode="OBJECT")
    bpy.ops.object.select_all(action="DESELECT")
    for name in snapshot["selected"]:
        obj = bpy.context.view_layer.objects.get(name)
        if obj is not None:
            obj.select_set(True)
    active_name = snapshot["active"]
    bpy.context.view_layer.objects.active = (
        bpy.context.view_layer.objects.get(active_name) if active_name else None
    )


def render_snapshot() -> dict[str, Any]:
    scene = bpy.context.scene
    return {
        "engine": scene.render.engine,
        "cycles_samples": int(scene.cycles.samples),
        "cycles_use_denoising": bool(scene.cycles.use_denoising),
        "cycles_device": scene.cycles.device,
    }


def restore_render(snapshot: dict[str, Any]) -> None:
    scene = bpy.context.scene
    scene.render.engine = snapshot["engine"]
    scene.cycles.samples = snapshot["cycles_samples"]
    scene.cycles.use_denoising = snapshot["cycles_use_denoising"]
    scene.cycles.device = snapshot["cycles_device"]


def configure_cycles(samples: int) -> dict[str, Any]:
    scene = bpy.context.scene
    scene.render.engine = "CYCLES"
    scene.cycles.samples = samples
    scene.cycles.use_denoising = False
    device_record: dict[str, Any] = {
        "requested": "OPTIX_then_CUDA_then_CPU",
        "used": "CPU",
        "enabled_devices": [],
    }
    try:
        preferences = bpy.context.preferences.addons["cycles"].preferences
        for compute_type in ("OPTIX", "CUDA"):
            try:
                preferences.compute_device_type = compute_type
                preferences.get_devices()
                enabled = []
                for device in preferences.devices:
                    use = device.type == compute_type
                    device.use = use
                    if use:
                        enabled.append(
                            {
                                "name": device.name,
                                "type": device.type,
                                "id": device.id,
                            }
                        )
                if enabled:
                    scene.cycles.device = "GPU"
                    device_record["used"] = compute_type
                    device_record["enabled_devices"] = enabled
                    return device_record
            except Exception:
                continue
    except Exception as exc:
        device_record["configuration_error"] = str(exc)
    scene.cycles.device = "CPU"
    return device_record


def create_ao_image() -> Any:
    existing = bpy.data.images.get(AO_IMAGE_NAME)
    if existing is not None:
        bpy.data.images.remove(existing)
    image = bpy.data.images.new(
        AO_IMAGE_NAME,
        width=TEXTURE_SIZE,
        height=TEXTURE_SIZE,
        alpha=True,
        float_buffer=False,
        is_data=True,
    )
    image.generated_color = (1.0, 1.0, 1.0, 1.0)
    image.colorspace_settings.name = "Non-Color"
    pixels = np.ones(TEXTURE_SIZE * TEXTURE_SIZE * 4, dtype=np.float32)
    image.pixels.foreach_set(pixels)
    image.update()
    return image


def create_transient_ao_material(image: Any, samples: int) -> tuple[Any, dict[str, Any]]:
    material = bpy.data.materials.new("R2X_TEMP_AO_BAKE_MATERIAL")
    material.use_nodes = True
    nodes = material.node_tree.nodes
    links = material.node_tree.links
    nodes.clear()
    output = nodes.new("ShaderNodeOutputMaterial")
    output.name = "R2X_TEMP_OUTPUT"
    emission = nodes.new("ShaderNodeEmission")
    emission.name = "R2X_TEMP_EMISSION"
    ambient = nodes.new("ShaderNodeAmbientOcclusion")
    ambient.name = "R2X_TEMP_LOCAL_CONTACT_AO"
    ambient.samples = samples
    ambient.inside = False
    ambient.only_local = False
    ambient.inputs["Color"].default_value = (1.0, 1.0, 1.0, 1.0)
    ambient.inputs["Distance"].default_value = AO_DISTANCE_M
    remap = nodes.new("ShaderNodeMath")
    remap.name = "R2X_TEMP_AO_STRENGTH"
    remap.operation = "MULTIPLY_ADD"
    remap.inputs[1].default_value = AO_STRENGTH
    remap.inputs[2].default_value = 1.0 - AO_STRENGTH
    floor = nodes.new("ShaderNodeMath")
    floor.name = "R2X_TEMP_AO_FLOOR"
    floor.operation = "MAXIMUM"
    floor.inputs[1].default_value = AO_FLOOR
    target = nodes.new("ShaderNodeTexImage")
    target.name = "R2X_TEMP_ACTIVE_BAKE_TARGET"
    target.image = image
    uv = nodes.new("ShaderNodeUVMap")
    uv.name = "R2X_TEMP_EXPLICIT_UV2"
    uv.uv_map = UV2_NAME
    links.new(uv.outputs["UV"], target.inputs["Vector"])
    links.new(ambient.outputs["AO"], remap.inputs[0])
    links.new(remap.outputs[0], floor.inputs[0])
    links.new(floor.outputs[0], emission.inputs["Color"])
    links.new(emission.outputs["Emission"], output.inputs["Surface"])
    for node in nodes:
        node.select = False
    target.select = True
    nodes.active = target
    return material, {
        "material": material.name,
        "nodes": sorted(node.name for node in nodes),
        "distance_m": float(ambient.inputs["Distance"].default_value),
        "strength": float(remap.inputs[1].default_value),
        "floor": float(floor.inputs[1].default_value),
        "samples": int(ambient.samples),
        "inside": bool(ambient.inside),
        "only_local": bool(ambient.only_local),
    }


def image_metrics_from_blender(image: Any) -> dict[str, Any]:
    values = np.empty(len(image.pixels), dtype=np.float32)
    image.pixels.foreach_get(values)
    rgba = values.reshape((-1, 4))
    red = rgba[:, 0].astype(np.float64)
    percentiles = np.percentile(red, [0, 1, 5, 25, 50, 75, 95, 99, 100])
    return {
        "width": int(image.size[0]),
        "height": int(image.size[1]),
        "min": float(np.min(red)),
        "max": float(np.max(red)),
        "mean": float(np.mean(red)),
        "std": float(np.std(red)),
        "nonwhite_ratio": float(np.mean(red < (254.5 / 255.0))),
        "threshold_distribution": {
            f"lt_{threshold:.2f}": float(np.mean(red < threshold))
            for threshold in (0.80, 0.82, 0.90, 0.95, 0.98, 0.99, 1.00)
        },
        "percentiles": {
            label: float(value)
            for label, value in zip(
                ("p00", "p01", "p05", "p25", "p50", "p75", "p95", "p99", "p100"),
                percentiles,
            )
        },
        "unique_rounded_8bit_values": int(
            len(np.unique(np.clip(np.rint(red * 255.0), 0, 255).astype(np.uint8)))
        ),
    }


def bake_ao(targets: list[Any], samples: int) -> tuple[Any, dict[str, Any]]:
    image = create_ao_image()
    transient, graph = create_transient_ao_material(image, samples)
    visibility_before = visibility_snapshot()
    collection_visibility_before = collection_visibility_snapshot()
    selection_before = selection_snapshot()
    render_before = render_snapshot()
    source_slot0 = {obj.name: obj.material_slots[0].material for obj in targets}
    bake_entries: list[dict[str, Any]] = []
    device: dict[str, Any] = {}
    started = time.monotonic()
    try:
        device = configure_cycles(samples)
        allowed = set(TARGETS)
        for collection in bpy.data.collections:
            collection.hide_render = False
            collection.hide_viewport = False
        for obj in bpy.data.objects:
            obj.hide_render = obj.name not in allowed
            if obj.name in allowed:
                obj.hide_viewport = False
                obj.hide_set(False)
        visible_render_geometry = sorted(
            obj.name
            for obj in bpy.data.objects
            if obj.type
            in {"MESH", "CURVE", "SURFACE", "META", "FONT", "VOLUME"}
            and not obj.hide_render
        )
        if visible_render_geometry != sorted(TARGETS):
            raise BuildError(
                "AO render whitelist is not exact: "
                f"{visible_render_geometry}"
            )
        for obj in targets:
            obj.material_slots[0].material = transient
        for index, obj in enumerate(targets):
            bpy.ops.object.select_all(action="DESELECT")
            obj.select_set(True)
            bpy.context.view_layer.objects.active = obj
            if not obj.select_get() or bpy.context.view_layer.objects.active != obj:
                raise BuildError(
                    f"Blender bake context could not activate target {obj.name}"
                )
            before = time.monotonic()
            result = bpy.ops.object.bake(
                type="EMIT",
                margin=BAKE_MARGIN_PX,
                margin_type="EXTEND",
                use_selected_to_active=False,
                cage_extrusion=0.0,
                max_ray_distance=0.0,
                use_clear=False,
                target="IMAGE_TEXTURES",
                save_mode="INTERNAL",
                uv_layer=UV2_NAME,
            )
            if "FINISHED" not in result:
                raise BuildError(f"AO bake failed for {obj.name}: {result}")
            bake_entries.append(
                {
                    "target": obj.name,
                    "index": index,
                    "seconds": time.monotonic() - before,
                    "result": sorted(result),
                    "occluders": sorted(TARGETS),
                }
            )
        image.update()
    finally:
        for obj in targets:
            obj.material_slots[0].material = source_slot0[obj.name]
        restore_visibility(visibility_before)
        restore_collection_visibility(collection_visibility_before)
        restore_render(render_before)
        restore_selection(selection_before)
        if transient.users == 0:
            bpy.data.materials.remove(transient)

    visibility_after = visibility_snapshot()
    collection_visibility_after = collection_visibility_snapshot()
    selection_after = selection_snapshot()
    render_after = render_snapshot()
    temporary_material_absent = bpy.data.materials.get(
        "R2X_TEMP_AO_BAKE_MATERIAL"
    ) is None
    transaction = {
        "visible_mesh_whitelist": list(TARGETS),
        "allowed_target_count": len(TARGETS),
        "allowed_occluder_count": len(TARGETS),
        "excluded_geometry_policy": (
            "all non-target renderable geometry hide_render=true during bake"
        ),
        "entries": bake_entries,
        "device": device,
        "seconds": time.monotonic() - started,
        "visibility": {
            "object_before_sha256": stable_sha(visibility_before),
            "object_after_sha256": stable_sha(visibility_after),
            "collection_before_sha256": stable_sha(
                collection_visibility_before
            ),
            "collection_after_sha256": stable_sha(
                collection_visibility_after
            ),
            "restored": (
                visibility_before == visibility_after
                and collection_visibility_before
                == collection_visibility_after
            ),
        },
        "selection": {
            "before": selection_before,
            "after": selection_after,
            "restored": selection_before == selection_after,
        },
        "render_engine": {
            "before": render_before,
            "after": render_after,
            "restored": render_before == render_after,
        },
        "temporary_nodes": {
            "graph": graph,
            "material_absent_after_bake": temporary_material_absent,
            "restored": temporary_material_absent,
        },
    }
    if not all(
        (
            transaction["visibility"]["restored"],
            transaction["selection"]["restored"],
            transaction["render_engine"]["restored"],
            transaction["temporary_nodes"]["restored"],
        )
    ):
        raise BuildError(f"AO bake transaction did not restore state: {transaction}")
    return image, transaction


def save_ao_png(image: Any) -> dict[str, Any]:
    OUTPUT_PNG.parent.mkdir(parents=True, exist_ok=True)
    image.filepath_raw = str(OUTPUT_PNG)
    image.file_format = "PNG"
    image.save()
    if not OUTPUT_PNG.is_file():
        raise BuildError("AO PNG was not written")
    image.reload()
    image.pack()
    image.filepath = "//../textures/" + OUTPUT_PNG.name
    image.colorspace_settings.name = "Non-Color"
    record = file_record(OUTPUT_PNG)
    record.update(image_metrics_from_blender(image))
    record["colorspace"] = image.colorspace_settings.name
    record["decoded_bytes_rgba8"] = TEXTURE_SIZE * TEXTURE_SIZE * 4
    record["decoded_mib_rgba8"] = (
        TEXTURE_SIZE * TEXTURE_SIZE * 4 / (1024.0 * 1024.0)
    )
    record["decoded_mib_rgba8_with_mips_estimate"] = (
        TEXTURE_SIZE * TEXTURE_SIZE * 4 * 4.0 / 3.0 / (1024.0 * 1024.0)
    )
    record["nonwhite"] = (
        record["min"] < (254.5 / 255.0)
        and record["std"] > 0.0
        and record["nonwhite_ratio"] > 0.0
    )
    return record


def image_node_fingerprint(material: Any) -> list[dict[str, Any]]:
    result = []
    if material is None or material.node_tree is None:
        return result
    for node in material.node_tree.nodes:
        if node.bl_idname != "ShaderNodeTexImage":
            continue
        result.append(
            {
                "node": node.name,
                "label": node.label,
                "image": node.image.name if node.image else None,
                "colorspace": (
                    node.image.colorspace_settings.name if node.image else None
                ),
            }
        )
    return sorted(result, key=lambda item: item["node"])


def gltf_occlusion_group() -> Any:
    name = "glTF Material Output R2X AO"
    group = bpy.data.node_groups.get(name)
    if group is not None:
        return group
    group = bpy.data.node_groups.new(name, "ShaderNodeTree")
    group.interface.new_socket(
        name="Occlusion", in_out="INPUT", socket_type="NodeSocketFloat"
    )
    group.nodes.new("NodeGroupOutput")
    group.nodes.new("NodeGroupInput")
    return group


def candidate_material_name(object_name: str) -> str:
    zone = object_name.split("_FURNACE_", 1)[1].split("_SHELL_", 1)[0]
    return f"R2X_AO_GL02_{zone}_EXTERIOR_PBR_SMOKE1K"


def add_candidate_materials(
    targets: list[Any], image: Any
) -> dict[str, dict[str, Any]]:
    group = gltf_occlusion_group()
    records: dict[str, dict[str, Any]] = {}
    for obj in targets:
        source = obj.material_slots[0].material
        if source is None or source.node_tree is None:
            raise BuildError(f"{obj.name} slot0 source material is missing nodes")
        protected_before = image_node_fingerprint(source)
        clone = source.copy()
        clone.name = candidate_material_name(obj.name)
        clone["bf3d_stage"] = STAGE_ID
        clone["bf3d_requirement_id"] = REQUIREMENT_ID
        clone["bf3d_r2x_ao_smoke1k"] = True
        clone["bf3d_r2x_ao_uv"] = UV2_NAME
        clone["bf3d_r2x_ao_distance_m"] = AO_DISTANCE_M
        clone["bf3d_r2x_ao_strength"] = AO_STRENGTH
        clone["bf3d_r2x_ao_floor"] = AO_FLOOR
        clone["bf3d_approval_granted"] = False
        nodes = clone.node_tree.nodes
        links = clone.node_tree.links
        uv = nodes.new("ShaderNodeUVMap")
        uv.name = "R2X_AO_EXPLICIT_UV2"
        uv.label = "R2X AO UV2 / TEXCOORD_2"
        uv.uv_map = UV2_NAME
        texture = nodes.new("ShaderNodeTexImage")
        texture.name = "R2X_AO_IMAGE_R_NON_COLOR"
        texture.label = "R2X independent local contact AO"
        texture.image = image
        texture.extension = "CLIP"
        split = nodes.new("ShaderNodeSeparateColor")
        split.name = "R2X_AO_RED_CHANNEL"
        split.mode = "RGB"
        output = nodes.new("ShaderNodeGroup")
        output.name = "R2X_GLTF_MATERIAL_OUTPUT"
        output.label = "R2X glTF Occlusion / TEXCOORD_2"
        output.node_tree = group
        links.new(uv.outputs["UV"], texture.inputs["Vector"])
        links.new(texture.outputs["Color"], split.inputs["Color"])
        links.new(split.outputs["Red"], output.inputs["Occlusion"])
        obj.material_slots[0].material = clone
        protected_after = [
            item
            for item in image_node_fingerprint(clone)
            if item["node"] != "R2X_AO_IMAGE_R_NON_COLOR"
        ]
        records[obj.name] = {
            "slot": 0,
            "source_material": source.name,
            "candidate_material": clone.name,
            "protected_image_nodes_before": protected_before,
            "protected_image_nodes_after": protected_after,
            "basecolor_normal_existing_orm_images_unchanged": (
                protected_before == protected_after
            ),
            "ao_image": image.name,
            "uv_map_node": uv.name,
            "uv_map": uv.uv_map,
            "texture_node": texture.name,
            "red_channel_node": split.name,
            "gltf_output_node": output.name,
            "gltf_output_group": output.node_tree.name,
            "gltf_occlusion_connected": bool(
                output.inputs["Occlusion"].is_linked
            ),
        }
    return records


def section_ao_material_audit() -> dict[str, Any]:
    sections = sorted(
        obj.name
        for obj in bpy.data.objects
        if obj.type == "MESH" and obj.name.startswith("SECTION_")
    )
    bound = []
    for name in sections:
        obj = bpy.data.objects[name]
        for slot in obj.material_slots:
            material = slot.material
            if material is not None and bool(
                material.get("bf3d_r2x_ao_smoke1k", False)
            ):
                bound.append({"object": name, "material": material.name})
    return {
        "section_count": len(sections),
        "sections": sections,
        "r2x_ao_bindings": bound,
        "r2x_ao_binding_count": len(bound),
        "passed": len(sections) == 10 and not bound,
    }


def only_five_uv2_audit() -> dict[str, Any]:
    with_uv2 = sorted(
        obj.name
        for obj in bpy.data.objects
        if obj.type == "MESH" and UV2_NAME in obj.data.uv_layers
    )
    expected = sorted(TARGETS)
    return {
        "objects_with_uv2": with_uv2,
        "expected_objects": expected,
        "count": len(with_uv2),
        "passed": with_uv2 == expected,
    }


def compare_snapshots(
    before: dict[str, Any], after: dict[str, Any]
) -> dict[str, Any]:
    before_uv = before["uv_layers"]
    after_uv = after["uv_layers"]
    return {
        "mesh_counts_unchanged": before["mesh_counts"] == after["mesh_counts"],
        "mesh_topology_unchanged": (
            before["mesh_topology_sha256"] == after["mesh_topology_sha256"]
        ),
        "transform_unchanged": before["transform"] == after["transform"],
        "material_slot_count_unchanged": (
            before["material_slot_count"] == after["material_slot_count"]
        ),
        "slot1_slot2_unchanged": (
            before["material_slots"][1:] == after["material_slots"][1:]
        ),
        "polygon_material_index_unchanged": (
            before["polygon_material_index_sha256"]
            == after["polygon_material_index_sha256"]
            and before["polygon_material_index_counts"]
            == after["polygon_material_index_counts"]
        ),
        "uv_layer_count_is_three": len(after_uv) == 3,
        "uv0_name_order_active_render_unchanged": (
            before_uv[0]["index"] == after_uv[0]["index"] == 0
            and before_uv[0]["name"] == after_uv[0]["name"] == UV0_NAME
            and before_uv[0]["active"] == after_uv[0]["active"]
            and before_uv[0]["active_render"] == after_uv[0]["active_render"]
        ),
        "uv1_name_order_active_render_unchanged": (
            before_uv[1]["index"] == after_uv[1]["index"] == 1
            and before_uv[1]["name"] == after_uv[1]["name"] == UV1_NAME
            and before_uv[1]["active"] == after_uv[1]["active"]
            and before_uv[1]["active_render"] == after_uv[1]["active_render"]
        ),
        "uv0_loop_hash_unchanged": (
            before_uv[0]["loop_sha256"] == after_uv[0]["loop_sha256"]
        ),
        "uv1_loop_hash_unchanged": (
            before_uv[1]["loop_sha256"] == after_uv[1]["loop_sha256"]
        ),
        "uv2_is_third_named_inactive_nonrender": (
            len(after_uv) == 3
            and after_uv[2]["index"] == 2
            and after_uv[2]["name"] == UV2_NAME
            and not after_uv[2]["active"]
            and not after_uv[2]["active_render"]
        ),
    }


def save_candidate_blend() -> dict[str, Any]:
    scene = bpy.context.scene
    scene["bf3d_stage"] = STAGE_ID
    scene["bf3d_requirement_id"] = REQUIREMENT_ID
    scene["bf3d_candidate_kind"] = "r2x_ao_smoke1k"
    scene["bf3d_ao_uv"] = UV2_NAME
    scene["bf3d_ao_distance_m"] = AO_DISTANCE_M
    scene["bf3d_ao_strength"] = AO_STRENGTH
    scene["bf3d_ao_floor"] = AO_FLOOR
    scene["bf3d_approval_granted"] = False
    scene["bf3d_p50_approved"] = False
    scene["bf3d_production_integration_allowed"] = False
    scene["bf3d_next_release_stage_allowed"] = False
    OUTPUT_BLEND.parent.mkdir(parents=True, exist_ok=True)
    supported = {
        prop.identifier for prop in bpy.ops.wm.save_as_mainfile.get_rna_type().properties
    }
    requested = {
        "filepath": str(OUTPUT_BLEND),
        "check_existing": False,
        "compress": True,
        "relative_remap": False,
    }
    result = bpy.ops.wm.save_as_mainfile(
        **{key: value for key, value in requested.items() if key in supported}
    )
    if "FINISHED" not in result or not OUTPUT_BLEND.is_file():
        raise BuildError(f"Candidate Blend save failed: {result}")
    return {
        **file_record(OUTPUT_BLEND),
        "result": sorted(result),
        "used_options": {
            key: value for key, value in requested.items() if key in supported
        },
    }


def export_material_review_glb(targets: list[Any]) -> dict[str, Any]:
    selection_before = selection_snapshot()
    visibility_before = visibility_snapshot()
    collection_visibility_before = collection_visibility_snapshot()
    OUTPUT_GLB.parent.mkdir(parents=True, exist_ok=True)
    try:
        active = bpy.context.view_layer.objects.active
        if active is not None and active.mode != "OBJECT":
            bpy.ops.object.mode_set(mode="OBJECT")
        bpy.ops.object.select_all(action="DESELECT")
        for collection in bpy.data.collections:
            collection.hide_render = False
            collection.hide_viewport = False
        for obj in targets:
            obj.hide_set(False)
            obj.hide_viewport = False
            obj.select_set(True)
        bpy.context.view_layer.objects.active = targets[0]
        supported = {
            prop.identifier
            for prop in bpy.ops.export_scene.gltf.get_rna_type().properties
        }
        requested = {
            "filepath": str(OUTPUT_GLB),
            "export_format": "GLB",
            "use_selection": True,
            "export_extras": True,
            "export_cameras": False,
            "export_lights": False,
            "export_apply": False,
            "export_yup": True,
            "export_materials": "EXPORT",
            "export_image_format": "AUTO",
            "export_texcoords": True,
            "export_normals": True,
            "export_tangents": True,
            "export_attributes": False,
            "export_skins": False,
            "export_animations": False,
            "export_morph": False,
            "export_unused_images": False,
            "export_unused_textures": False,
            "export_draco_mesh_compression_enable": False,
            "export_meshopt_compression_enable": False,
        }
        used = {
            key: value for key, value in requested.items() if key in supported
        }
        result = bpy.ops.export_scene.gltf(**used)
        if "FINISHED" not in result or not OUTPUT_GLB.is_file():
            raise BuildError(f"Material-review GLB export failed: {result}")
        return {
            **file_record(OUTPUT_GLB),
            "result": sorted(result),
            "used_options": used,
            "selected_objects": sorted(obj.name for obj in targets),
        }
    finally:
        restore_visibility(visibility_before)
        restore_collection_visibility(collection_visibility_before)
        restore_selection(selection_before)


def base_report(status: str) -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "stage_id": STAGE_ID,
        "requirement_id": REQUIREMENT_ID,
        "generated_at": now_iso(),
        "status": status,
        "scope": {
            "resolution": "1K smoke only",
            "targets": list(TARGETS),
            "ao_target_and_occluder_scope": "the same five complete R2J shells only",
            "not_generated": ["2K", "4K"],
        },
        "approval_stop_lines": dict(APPROVAL_STOP_LINES),
        "parameters": {
            "texture_size": TEXTURE_SIZE,
            "bake_margin_px": BAKE_MARGIN_PX,
            "samples": AO_SAMPLES,
            "distance_m": AO_DISTANCE_M,
            "strength": AO_STRENGTH,
            "floor": AO_FLOOR,
        },
        "errors": [],
    }


def blender_build(samples: int) -> None:
    if bpy is None or np is None:
        raise BuildError("The build child must run inside Blender")
    ensure_stage_paths(STAGE)
    report = base_report("blender_build_in_progress")
    try:
        current_blend = Path(bpy.data.filepath).resolve()
        if current_blend != INPUT_BLEND.resolve():
            raise BuildError(
                f"Build child opened the wrong Blend: {current_blend}"
            )
        input_hash = sha256_file(current_blend)
        expected = PROTECTED_INPUTS["v5_blend"][1]
        if input_hash != expected:
            raise BuildError(
                f"V5 Blend lock mismatch: expected {expected}, got {input_hash}"
            )
        targets = get_targets()
        before = {obj.name: object_snapshot(obj) for obj in targets}
        uv2_atlas = append_deterministic_uv2(targets)
        after_uv = {obj.name: object_snapshot(obj) for obj in targets}
        for obj in targets:
            comparison = compare_snapshots(before[obj.name], after_uv[obj.name])
            protected_checks = [
                value
                for key, value in comparison.items()
                if key
                not in {
                    "material_slot_count_unchanged",
                    "slot1_slot2_unchanged",
                }
            ]
            if not all(protected_checks):
                raise BuildError(
                    f"UV2 append changed protected state for {obj.name}: "
                    f"{comparison}"
                )
        if not (
            uv2_atlas["finite"]
            and uv2_atlas["in_range"]
            and uv2_atlas["all_cross_object_disjoint"]
            and uv2_atlas["all_bake_margin_expanded_disjoint"]
        ):
            raise BuildError(f"UV2 atlas gate failed: {uv2_atlas}")

        image, transaction = bake_ao(targets, samples)
        ao_image = save_ao_png(image)
        if not ao_image["nonwhite"]:
            raise BuildError(f"AO bake is neutral/all-white: {ao_image}")
        materials = add_candidate_materials(targets, image)
        after = {obj.name: object_snapshot(obj) for obj in targets}
        target_records: dict[str, Any] = {}
        all_target_checks = []
        for obj in targets:
            comparison = compare_snapshots(before[obj.name], after[obj.name])
            comparison["slot0_is_candidate_copy"] = (
                after[obj.name]["material_slots"][0]["name"]
                == materials[obj.name]["candidate_material"]
            )
            target_records[obj.name] = {
                "before": before[obj.name],
                "after_uv2": after_uv[obj.name],
                "after": after[obj.name],
                "checks": comparison,
                "uv0_uv1_unchanged": all(
                    comparison[key]
                    for key in (
                        "uv0_name_order_active_render_unchanged",
                        "uv1_name_order_active_render_unchanged",
                        "uv0_loop_hash_unchanged",
                        "uv1_loop_hash_unchanged",
                    )
                ),
            }
            all_target_checks.extend(comparison.values())
        only_five = only_five_uv2_audit()
        sections = section_ao_material_audit()
        if not all(all_target_checks):
            raise BuildError("One or more per-target source preservation gates failed")
        if not only_five["passed"]:
            raise BuildError(f"UV2 scope gate failed: {only_five}")
        if not sections["passed"]:
            raise BuildError(f"Section material isolation gate failed: {sections}")

        report.update(
            {
                "status": "blender_build_passed_pending_reopen_gltf_validator",
                "input_lock": {
                    "path": str(current_blend),
                    "sha256": input_hash,
                    "expected_sha256": expected,
                    "matches": input_hash == expected,
                },
                "targets": target_records,
                "uv2_atlas": uv2_atlas,
                "bake_transaction": transaction,
                "ao_image": ao_image,
                "candidate_materials": materials,
                "only_five_shells_have_uv2": only_five,
                "section_ao_isolation": sections,
                "blender_internal_gates": {
                    "input_lock_matches": input_hash == expected,
                    "all_target_checks_passed": all(all_target_checks),
                    "only_five_shells_have_uv2": only_five["passed"],
                    "uv2_finite_in_range": (
                        uv2_atlas["finite"] and uv2_atlas["in_range"]
                    ),
                    "uv2_cross_object_overlap_zero": not uv2_atlas[
                        "overlap_pairs"
                    ],
                    "uv2_expanded_overlap_zero": not uv2_atlas[
                        "expanded_overlap_pairs"
                    ],
                    "ao_nonwhite": ao_image["nonwhite"],
                    "bake_transaction_restored": all(
                        transaction[key]["restored"]
                        for key in (
                            "visibility",
                            "selection",
                            "render_engine",
                            "temporary_nodes",
                        )
                    ),
                    "sections_not_bound": sections["passed"],
                },
            }
        )
        report["outputs"] = {
            "ao_png": file_record(OUTPUT_PNG),
        }
        write_json(BUILD_REPORT, report)
        report["outputs"]["candidate_blend"] = save_candidate_blend()
        report["outputs"]["candidate_glb"] = export_material_review_glb(targets)
        report["candidate_reopen_required"] = True
        write_json(BUILD_REPORT, report)
        print(
            "R2X_AO_BUILD="
            + json.dumps(
                {
                    "status": report["status"],
                    "blend": str(OUTPUT_BLEND),
                    "png": str(OUTPUT_PNG),
                    "glb": str(OUTPUT_GLB),
                },
                ensure_ascii=False,
            ),
            flush=True,
        )
    except Exception as exc:
        report["status"] = "failed_closed"
        report.setdefault("errors", []).append(
            {
                "phase": "blender_build",
                "type": type(exc).__name__,
                "message": str(exc),
                "traceback": traceback.format_exc(),
            }
        )
        write_json(BUILD_REPORT, report)
        raise


def material_reopen_audit(obj: Any) -> dict[str, Any]:
    material = obj.material_slots[0].material if obj.material_slots else None
    nodes = material.node_tree.nodes if material and material.node_tree else None
    uv = nodes.get("R2X_AO_EXPLICIT_UV2") if nodes else None
    texture = nodes.get("R2X_AO_IMAGE_R_NON_COLOR") if nodes else None
    split = nodes.get("R2X_AO_RED_CHANNEL") if nodes else None
    output = nodes.get("R2X_GLTF_MATERIAL_OUTPUT") if nodes else None
    return {
        "material": material.name if material else None,
        "candidate_property": bool(
            material and material.get("bf3d_r2x_ao_smoke1k", False)
        ),
        "uv_node_exists": uv is not None,
        "uv_map": uv.uv_map if uv else None,
        "texture_node_exists": texture is not None,
        "texture_image": (
            texture.image.name if texture is not None and texture.image else None
        ),
        "red_channel_node_exists": split is not None,
        "gltf_output_exists": output is not None,
        "gltf_output_group": (
            output.node_tree.name
            if output is not None and output.node_tree is not None
            else None
        ),
        "gltf_occlusion_connected": bool(
            output is not None and output.inputs["Occlusion"].is_linked
        ),
        "passed": (
            material is not None
            and bool(material.get("bf3d_r2x_ao_smoke1k", False))
            and uv is not None
            and uv.uv_map == UV2_NAME
            and texture is not None
            and texture.image is not None
            and texture.image.name == AO_IMAGE_NAME
            and split is not None
            and output is not None
            and output.node_tree is not None
            and output.node_tree.name.startswith("glTF Material Output")
            and output.inputs["Occlusion"].is_linked
        ),
    }


def blender_reopen() -> None:
    if bpy is None or np is None:
        raise BuildError("The reopen child must run inside Blender")
    ensure_stage_paths(STAGE)
    report: dict[str, Any] = {
        "schema_version": "bf3d.r2x.r2j_ao_smoke1k.reopen.v1",
        "stage_id": STAGE_ID,
        "requirement_id": REQUIREMENT_ID,
        "generated_at": now_iso(),
        "status": "reopen_in_progress",
        "approval_stop_lines": dict(APPROVAL_STOP_LINES),
        "checks": {},
        "errors": [],
    }
    try:
        if Path(bpy.data.filepath).resolve() != OUTPUT_BLEND.resolve():
            raise BuildError(
                f"Reopen child loaded the wrong Blend: {bpy.data.filepath}"
            )
        build = json.loads(BUILD_REPORT.read_text(encoding="utf-8"))
        targets = get_targets(expect_uv2=True)
        snapshots = {obj.name: object_snapshot(obj) for obj in targets}
        snapshot_matches = {
            name: snapshots[name] == build["targets"][name]["after"]
            for name in TARGETS
        }
        materials = {obj.name: material_reopen_audit(obj) for obj in targets}
        only_five = only_five_uv2_audit()
        sections = section_ao_material_audit()
        image = bpy.data.images.get(AO_IMAGE_NAME)
        if image is not None and not image.has_data:
            # Packed images are lazy after direct reopen.  Reading one pixel
            # asks Blender to decode the packed payload without mutating it.
            _ = image.pixels[0]
        image_record = (
            image_metrics_from_blender(image)
            if image is not None and image.has_data
            else {"present": False}
        )
        if image is not None:
            image_record.update(
                {
                    "present": True,
                    "packed": bool(image.packed_file),
                    "filepath": image.filepath,
                    "colorspace": image.colorspace_settings.name,
                }
            )
        checks = {
            "candidate_path_exact": (
                Path(bpy.data.filepath).resolve() == OUTPUT_BLEND.resolve()
            ),
            "all_target_snapshots_match_saved_build": all(
                snapshot_matches.values()
            ),
            "only_five_shells_have_uv2": only_five["passed"],
            "all_candidate_materials_reopen": all(
                item["passed"] for item in materials.values()
            ),
            "sections_not_bound_to_r2x_ao": sections["passed"],
            "ao_image_present_packed_noncolor": (
                image is not None
                and image.has_data
                and bool(image.packed_file)
                and image.colorspace_settings.name == "Non-Color"
            ),
            "ao_image_nonwhite_after_reopen": (
                bool(image_record.get("present"))
                and image_record.get("min", 1.0) < (254.5 / 255.0)
                and image_record.get("std", 0.0) > 0.0
            ),
            "temporary_material_absent": (
                bpy.data.materials.get("R2X_TEMP_AO_BAKE_MATERIAL") is None
            ),
            "approval_stop_lines_persist": all(
                not bool(bpy.context.scene.get(key, True))
                for key in (
                    "bf3d_approval_granted",
                    "bf3d_p50_approved",
                    "bf3d_production_integration_allowed",
                    "bf3d_next_release_stage_allowed",
                )
            ),
        }
        report.update(
            {
                "status": (
                    "reopen_passed" if all(checks.values()) else "failed_closed"
                ),
                "candidate_blend": file_record(OUTPUT_BLEND),
                "target_snapshot_matches": snapshot_matches,
                "target_snapshots": snapshots,
                "candidate_materials": materials,
                "only_five_shells_have_uv2": only_five,
                "section_ao_isolation": sections,
                "ao_image": image_record,
                "checks": checks,
                "passed": all(checks.values()),
            }
        )
        write_json(REOPEN_REPORT, report)
        if not report["passed"]:
            raise BuildError(f"Candidate reopen gates failed: {checks}")
        print(
            "R2X_AO_REOPEN="
            + json.dumps(
                {"status": report["status"], "report": str(REOPEN_REPORT)},
                ensure_ascii=False,
            ),
            flush=True,
        )
    except Exception as exc:
        report["status"] = "failed_closed"
        report["passed"] = False
        report.setdefault("errors", []).append(
            {
                "phase": "candidate_reopen",
                "type": type(exc).__name__,
                "message": str(exc),
                "traceback": traceback.format_exc(),
            }
        )
        write_json(REOPEN_REPORT, report)
        raise


def read_glb(path: Path) -> tuple[dict[str, Any], bytes]:
    data = path.read_bytes()
    if len(data) < 20:
        raise BuildError("GLB is too short")
    magic, version, total_length = struct.unpack_from("<4sII", data, 0)
    if magic != b"glTF" or version != 2 or total_length != len(data):
        raise BuildError(
            f"Invalid GLB header: magic={magic!r}, version={version}, "
            f"declared={total_length}, actual={len(data)}"
        )
    offset = 12
    json_payload: bytes | None = None
    binary = b""
    while offset < len(data):
        chunk_length, chunk_type = struct.unpack_from("<I4s", data, offset)
        offset += 8
        payload = data[offset : offset + chunk_length]
        offset += chunk_length
        if chunk_type == b"JSON":
            json_payload = payload.rstrip(b" \t\r\n\x00")
        elif chunk_type in {b"BIN\x00", b"BIN "}:
            binary = payload
    if json_payload is None:
        raise BuildError("GLB has no JSON chunk")
    return json.loads(json_payload.decode("utf-8")), binary


def buffer_view_payload(
    gltf: dict[str, Any], binary: bytes, index: int
) -> bytes:
    view = gltf["bufferViews"][index]
    offset = int(view.get("byteOffset", 0))
    length = int(view["byteLength"])
    return binary[offset : offset + length]


def texture_descriptor(
    gltf: dict[str, Any], binary: bytes, descriptor: Any
) -> dict[str, Any] | None:
    if not isinstance(descriptor, dict) or not isinstance(
        descriptor.get("index"), int
    ):
        return None
    texture_index = int(descriptor["index"])
    texture = gltf["textures"][texture_index]
    source_index = texture.get("source")
    if not isinstance(source_index, int):
        extension = texture.get("extensions", {}).get("EXT_texture_webp", {})
        source_index = extension.get("source")
    if not isinstance(source_index, int):
        return {
            "texture_index": texture_index,
            "texCoord": int(descriptor.get("texCoord", 0)),
            "source_index": None,
        }
    image = gltf["images"][source_index]
    payload = None
    if isinstance(image.get("bufferView"), int):
        payload = buffer_view_payload(gltf, binary, int(image["bufferView"]))
    return {
        "texture_index": texture_index,
        "texCoord": int(descriptor.get("texCoord", 0)),
        "source_index": source_index,
        "image_name": image.get("name"),
        "mimeType": image.get("mimeType"),
        "uri": image.get("uri"),
        "payload_bytes": len(payload) if payload is not None else None,
        "payload_sha256": (
            hashlib.sha256(payload).hexdigest() if payload is not None else None
        ),
        "_payload": payload,
    }


def recursive_uri_values(value: Any) -> list[str]:
    result: list[str] = []
    if isinstance(value, dict):
        for key, item in value.items():
            if key == "uri" and isinstance(item, str):
                result.append(item)
            result.extend(recursive_uri_values(item))
    elif isinstance(value, list):
        for item in value:
            result.extend(recursive_uri_values(item))
    return result


def is_absolute_resource(value: str) -> bool:
    text = value.replace("\\", "/")
    return (
        text.startswith("/")
        or text.startswith("file:")
        or (len(text) >= 3 and text[1:3] == ":/")
    )


def png_red_channel(payload: bytes) -> tuple[Any, dict[str, Any]]:
    from PIL import Image
    import numpy as system_numpy

    with Image.open(io.BytesIO(payload)) as image:
        rgba = system_numpy.asarray(image.convert("RGBA"))
    red = rgba[:, :, 0]
    return red, {
        "width": int(red.shape[1]),
        "height": int(red.shape[0]),
        "min": int(red.min()),
        "max": int(red.max()),
        "mean": float(red.mean()),
        "std": float(red.std()),
        "nonwhite_ratio": float(system_numpy.mean(red < 255)),
        "unique_values": int(len(system_numpy.unique(red))),
    }


def audit_glb(path: Path, ao_png: Path) -> dict[str, Any]:
    import numpy as system_numpy

    gltf, binary = read_glb(path)
    nodes = gltf.get("nodes", [])
    meshes = gltf.get("meshes", [])
    materials = gltf.get("materials", [])
    node_by_name = {node.get("name"): node for node in nodes}
    target_records: dict[str, Any] = {}
    embedded_payloads: list[bytes] = []
    for name in TARGETS:
        node = node_by_name.get(name)
        if not isinstance(node, dict) or not isinstance(node.get("mesh"), int):
            target_records[name] = {
                "present": False,
                "passed": False,
                "error": "target node/mesh missing",
            }
            continue
        mesh = meshes[int(node["mesh"])]
        primitive_records = []
        for primitive_index, primitive in enumerate(mesh.get("primitives", [])):
            material_index = primitive.get("material")
            material = (
                materials[int(material_index)]
                if isinstance(material_index, int)
                else {}
            )
            pbr = material.get("pbrMetallicRoughness", {})
            base = texture_descriptor(
                gltf, binary, pbr.get("baseColorTexture")
            )
            metallic_roughness = texture_descriptor(
                gltf, binary, pbr.get("metallicRoughnessTexture")
            )
            normal = texture_descriptor(
                gltf, binary, material.get("normalTexture")
            )
            occlusion = texture_descriptor(
                gltf, binary, material.get("occlusionTexture")
            )
            if occlusion is not None and occlusion.get("_payload") is not None:
                embedded_payloads.append(occlusion["_payload"])
            public_textures = {}
            for key, descriptor in (
                ("baseColorTexture", base),
                ("metallicRoughnessTexture", metallic_roughness),
                ("normalTexture", normal),
                ("occlusionTexture", occlusion),
            ):
                if descriptor is not None:
                    public_textures[key] = {
                        item_key: item_value
                        for item_key, item_value in descriptor.items()
                        if item_key != "_payload"
                    }
                else:
                    public_textures[key] = None
            attributes = sorted(primitive.get("attributes", {}).keys())
            primitive_passed = (
                all(
                    key in primitive.get("attributes", {})
                    for key in ("TEXCOORD_0", "TEXCOORD_1", "TEXCOORD_2")
                )
                and base is not None
                and base["texCoord"] == 0
                and metallic_roughness is not None
                and metallic_roughness["texCoord"] == 0
                and normal is not None
                and normal["texCoord"] == 0
                and occlusion is not None
                and occlusion["texCoord"] == 2
            )
            primitive_records.append(
                {
                    "primitive_index": primitive_index,
                    "attributes": attributes,
                    "material_index": material_index,
                    "material_name": material.get("name"),
                    "textures": public_textures,
                    "passed": primitive_passed,
                }
            )
        target_records[name] = {
            "present": True,
            "mesh_index": int(node["mesh"]),
            "mesh_name": mesh.get("name"),
            "primitive_count": len(primitive_records),
            "primitives": primitive_records,
            "passed": bool(primitive_records)
            and all(item["passed"] for item in primitive_records),
        }

    external_red, external_metrics = png_red_channel(ao_png.read_bytes())
    embedded_comparisons = []
    for payload in embedded_payloads:
        embedded_red, embedded_metrics = png_red_channel(payload)
        embedded_comparisons.append(
            {
                "payload_sha256": hashlib.sha256(payload).hexdigest(),
                "metrics": embedded_metrics,
                "shape_matches": embedded_red.shape == external_red.shape,
                "r_channel_exact_match": (
                    embedded_red.shape == external_red.shape
                    and bool(system_numpy.array_equal(embedded_red, external_red))
                ),
            }
        )
    uris = recursive_uri_values(gltf)
    absolute_uris = [value for value in uris if is_absolute_resource(value)]
    section_nodes = sorted(
        node.get("name")
        for node in nodes
        if isinstance(node.get("name"), str)
        and node["name"].startswith("SECTION_")
    )
    report = {
        "asset": gltf.get("asset"),
        "extensions_used": gltf.get("extensionsUsed", []),
        "extensions_required": gltf.get("extensionsRequired", []),
        "node_count": len(nodes),
        "mesh_count": len(meshes),
        "material_count": len(materials),
        "image_count": len(gltf.get("images", [])),
        "targets": target_records,
        "target_count": sum(
            1 for item in target_records.values() if item["present"]
        ),
        "all_target_primitives_contract_passed": all(
            item["passed"] for item in target_records.values()
        ),
        "occlusion_payload_count": len(embedded_payloads),
        "external_ao_png": {
            **file_record(ao_png),
            "r_channel": external_metrics,
        },
        "embedded_ao_r_channel_comparisons": embedded_comparisons,
        "all_embedded_ao_r_channels_exact_match": bool(embedded_comparisons)
        and all(
            item["r_channel_exact_match"] for item in embedded_comparisons
        ),
        "uris": uris,
        "external_uri_count": len(uris),
        "absolute_uris": absolute_uris,
        "absolute_uri_count": len(absolute_uris),
        "missing_external_resource_count": 0 if not uris else None,
        "section_nodes": section_nodes,
        "section_ao_binding_count": 0,
    }
    report["passed"] = (
        report["target_count"] == len(TARGETS)
        and report["all_target_primitives_contract_passed"]
        and report["all_embedded_ao_r_channels_exact_match"]
        and report["external_uri_count"] == 0
        and report["absolute_uri_count"] == 0
        and report["section_ao_binding_count"] == 0
    )
    return report


def run_khronos_validator(path: Path) -> dict[str, Any]:
    node = shutil.which("node")
    if node is None or not KHRONOS_MODULE.is_dir():
        return {
            "available": False,
            "status": "not_run",
            "node": node,
            "module": str(KHRONOS_MODULE),
            "errors": None,
            "warnings": None,
            "passed": False,
        }
    script = (
        "const fs=require('fs');"
        "const path=require('path');"
        "const validator=require(process.argv[1]);"
        "const file=process.argv[2];"
        "validator.validateBytes(new Uint8Array(fs.readFileSync(file)),"
        "{uri:path.basename(file),maxIssues:10000})"
        ".then(report=>process.stdout.write(JSON.stringify(report)))"
        ".catch(error=>{console.error(error&&error.stack||String(error));"
        "process.exit(2);});"
    )
    completed = subprocess.run(
        [node, "-e", script, str(KHRONOS_MODULE), str(path)],
        cwd=str(STAGE),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    if completed.returncode != 0:
        return {
            "available": True,
            "status": "failed_to_run",
            "node": node,
            "module": str(KHRONOS_MODULE),
            "returncode": completed.returncode,
            "stdout": completed.stdout,
            "stderr": completed.stderr,
            "errors": None,
            "warnings": None,
            "passed": False,
        }
    raw = json.loads(completed.stdout)
    write_json(KHRONOS_REPORT, raw)
    issues = raw.get("issues", {})
    errors = int(issues.get("numErrors", 0))
    warnings = int(issues.get("numWarnings", 0))
    return {
        "available": True,
        "status": "completed",
        "node": node,
        "module": str(KHRONOS_MODULE),
        "validator_version": raw.get("validatorVersion"),
        "errors": errors,
        "warnings": warnings,
        "infos": int(issues.get("numInfos", 0)),
        "hints": int(issues.get("numHints", 0)),
        "report": file_record(KHRONOS_REPORT),
        "passed": errors == 0 and warnings == 0,
    }


def run_logged(command: list[str], label: str) -> int:
    BLENDER_LOG.parent.mkdir(parents=True, exist_ok=True)
    with BLENDER_LOG.open("a", encoding="utf-8", newline="\n") as log:
        log.write(
            f"\n[{now_iso()}] {label}\n"
            + json.dumps(command, ensure_ascii=False)
            + "\n"
        )
        log.flush()
        process = subprocess.Popen(
            command,
            cwd=str(ROOT),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        assert process.stdout is not None
        for line in process.stdout:
            log.write(line)
            log.flush()
            print(line, end="", flush=True)
        return process.wait()


def clean_known_outputs() -> None:
    for path in (
        OUTPUT_BLEND,
        OUTPUT_PNG,
        OUTPUT_GLB,
        BUILD_REPORT,
        REOPEN_REPORT,
        BLENDER_LOG,
        KHRONOS_REPORT,
    ):
        if path.is_file():
            path.unlink()


def driver_main(args: argparse.Namespace) -> int:
    ensure_stage_paths(args.output_root)
    if args.input_blend.resolve() != INPUT_BLEND.resolve():
        raise BuildError(f"Only the locked V5 Blend is authorized: {INPUT_BLEND}")
    if not args.blender_exe.is_file():
        raise BuildError(f"Blender executable not found: {args.blender_exe}")
    clean_known_outputs()
    before = protected_snapshot()
    assert_protected_snapshot(before)
    driver_report = base_report("driver_in_progress")
    driver_report["input_lock"] = {"before": before}
    try:
        build_command = [
            str(args.blender_exe),
            "--background",
            str(INPUT_BLEND),
            "--python-exit-code",
            "1",
            "--python",
            str(Path(__file__).resolve()),
            "--",
            "--blender-child",
            "build",
            "--output-root",
            str(STAGE),
            "--samples",
            str(args.samples),
        ]
        build_code = run_logged(build_command, "Blender build")
        if build_code != 0:
            raise BuildError(
                f"Blender build exited with code {build_code}; see {BLENDER_LOG}"
            )
        if not BUILD_REPORT.is_file():
            raise BuildError("Blender build did not write its report")
        build = json.loads(BUILD_REPORT.read_text(encoding="utf-8"))
        if not OUTPUT_BLEND.is_file() or not OUTPUT_PNG.is_file() or not OUTPUT_GLB.is_file():
            raise BuildError("One or more required 1K candidate outputs are missing")

        gltf_audit = audit_glb(OUTPUT_GLB, OUTPUT_PNG)
        khronos = run_khronos_validator(OUTPUT_GLB)

        reopen_command = [
            str(args.blender_exe),
            "--background",
            str(OUTPUT_BLEND),
            "--python-exit-code",
            "1",
            "--python",
            str(Path(__file__).resolve()),
            "--",
            "--blender-child",
            "reopen",
            "--output-root",
            str(STAGE),
        ]
        reopen_code = run_logged(reopen_command, "Blender candidate reopen")
        if reopen_code != 0:
            raise BuildError(
                f"Blender reopen exited with code {reopen_code}; see {BLENDER_LOG}"
            )
        reopen = json.loads(REOPEN_REPORT.read_text(encoding="utf-8"))
        after = protected_snapshot()
        protected_unchanged = before == after
        png_record = file_record(OUTPUT_PNG)
        glb_record = file_record(OUTPUT_GLB)
        blend_record = file_record(OUTPUT_BLEND)
        glb_record["baseline_v5_material_glb_bytes"] = (
            INPUT_MATERIAL_GLB.stat().st_size
        )
        glb_record["increment_bytes"] = (
            OUTPUT_GLB.stat().st_size - INPUT_MATERIAL_GLB.stat().st_size
        )
        glb_record["increment_ratio"] = (
            OUTPUT_GLB.stat().st_size / INPUT_MATERIAL_GLB.stat().st_size - 1.0
        )
        gates = {
            "protected_inputs_match_expected_before": all(
                item["matches_expected"] for item in before.values()
            ),
            "protected_inputs_unchanged_after": protected_unchanged,
            "blender_internal_gates_passed": all(
                build["blender_internal_gates"].values()
            ),
            "candidate_reopen_passed": bool(reopen.get("passed")),
            "gltf_contract_passed": bool(gltf_audit.get("passed")),
            "khronos_validator_zero_errors_zero_warnings": bool(
                khronos.get("passed")
            ),
        }
        all_machine_gates = all(gates.values())
        build.update(
            {
                "generated_at": now_iso(),
                "status": (
                    "smoke1k_machine_gates_passed_pending_three_visual_and_independent_review"
                    if all_machine_gates
                    else "failed_closed"
                ),
                "input_lock": {
                    "before": before,
                    "after": after,
                    "unchanged": protected_unchanged,
                },
                "outputs": {
                    "candidate_blend": blend_record,
                    "ao_png": png_record,
                    "candidate_glb": glb_record,
                    "build_report": {
                        "path": str(BUILD_REPORT),
                        "exists": True,
                    },
                    "blender_log": file_record(BLENDER_LOG),
                    "reopen_report": file_record(REOPEN_REPORT),
                    "khronos_report": file_record(KHRONOS_REPORT),
                },
                "gltf_audit": gltf_audit,
                "khronos_validator": khronos,
                "candidate_reopen": reopen,
                "machine_gates": gates,
                "all_machine_gates_passed": all_machine_gates,
                "approval_stop_lines": dict(APPROVAL_STOP_LINES),
                "evidence_boundary": {
                    "candidate_only": True,
                    "resolution": "1K smoke",
                    "three_runtime_check": "not_in_this_blender_build",
                    "visual_review": "pending_independent_review",
                    "p50": "not_approved",
                    "production": "not_allowed",
                },
            }
        )
        write_json(BUILD_REPORT, build)
        if not all_machine_gates:
            failed = [key for key, value in gates.items() if not value]
            raise BuildError(f"R2X machine gates failed closed: {failed}")
        print(
            "R2X_AO_SMOKE1K_FINAL="
            + json.dumps(
                {
                    "status": build["status"],
                    "report": str(BUILD_REPORT),
                    "approval_stop_lines": APPROVAL_STOP_LINES,
                },
                ensure_ascii=False,
            ),
            flush=True,
        )
        return 0
    except Exception as exc:
        if BUILD_REPORT.is_file():
            try:
                driver_report = json.loads(
                    BUILD_REPORT.read_text(encoding="utf-8")
                )
            except Exception:
                pass
        driver_report["status"] = "failed_closed"
        driver_report["generated_at"] = now_iso()
        driver_report["approval_stop_lines"] = dict(APPROVAL_STOP_LINES)
        driver_report.setdefault("errors", []).append(
            {
                "phase": "driver",
                "type": type(exc).__name__,
                "message": str(exc),
                "traceback": traceback.format_exc(),
            }
        )
        after = protected_snapshot()
        driver_report["input_lock"] = {
            "before": before,
            "after": after,
            "unchanged": before == after,
        }
        driver_report.setdefault("outputs", {}).update(
            {
                "candidate_blend": file_record(OUTPUT_BLEND),
                "ao_png": file_record(OUTPUT_PNG),
                "candidate_glb": file_record(OUTPUT_GLB),
                "blender_log": file_record(BLENDER_LOG),
                "reopen_report": file_record(REOPEN_REPORT),
                "khronos_report": file_record(KHRONOS_REPORT),
            }
        )
        write_json(BUILD_REPORT, driver_report)
        print(f"R2X AO smoke failed closed: {exc}", file=sys.stderr, flush=True)
        return 1


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Build the locked WEB-60 R2X five-shell 1K independent AO smoke "
            "candidate, reopen it, audit its GLB, and run Khronos Validator."
        )
    )
    parser.add_argument(
        "--blender-exe", type=Path, default=DEFAULT_BLENDER
    )
    parser.add_argument("--input-blend", type=Path, default=INPUT_BLEND)
    parser.add_argument("--output-root", type=Path, default=STAGE)
    parser.add_argument("--samples", type=int, default=AO_SAMPLES)
    parser.add_argument(
        "--blender-child",
        choices=("build", "reopen"),
        help=argparse.SUPPRESS,
    )
    args = parser.parse_args(
        sys.argv[sys.argv.index("--") + 1 :]
        if bpy is not None and "--" in sys.argv
        else sys.argv[1:]
    )
    if args.samples < 1 or args.samples > 256:
        parser.error("--samples must be in [1, 256]")
    return args


def main() -> int:
    args = parse_args()
    if args.blender_child:
        ensure_stage_paths(args.output_root)
        if args.blender_child == "build":
            blender_build(args.samples)
        else:
            blender_reopen()
        return 0
    return driver_main(args)


if __name__ == "__main__":
    raise SystemExit(main())
