"""Compare locked R2R Blender Eevee/Cycles captures numerically.

The comparison consumes the pre-registered contract and Blender capture
manifest, evaluates every required shot/repeat/material ROI without
averaging away failures, writes visual diffs, and fails closed whenever a
required metric cannot be evaluated.

Requirement:
    REQ-BF3D-R2R-BLENDER-RENDERER-NUMERIC-AB-20260719
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import traceback
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image
from scipy import ndimage
from skimage import color
from skimage.metrics import structural_similarity


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_STAGE = (
    ROOT
    / "PT"
    / "高炉3D模型"
    / "work"
    / "WEB_60_20260719_R2R_RENDERER_NUMERIC_AB_GATE"
)
DEFAULT_CONTRACT = DEFAULT_STAGE / "capture_contract.json"
DEFAULT_CAPTURE_MANIFEST = DEFAULT_STAGE / "capture_manifest.json"
REPORT_SCHEMA = "bf3d.r2r.numeric_ab_report.v1"
ARTIFACT_SCHEMA = "bf3d.r2r.artifact_manifest.v1"
REQUIREMENT_ID = "REQ-BF3D-R2R-BLENDER-RENDERER-NUMERIC-AB-20260719"
SHOT_IDS = (
    "standard_ortho_section_1x",
    "local_layer_closeup_1x",
    "six_family_material_board_with_midgray",
)
ENGINE_IDS = ("eevee", "cycles")
PRIMARY_FAMILIES = (
    "steel_inner",
    "backfill",
    "cast_iron",
    "copper",
    "hotface",
    "refractory",
)
THRESHOLD_KEYS = {
    "silhouette_iou_min",
    "symmetric_edge_distance_p95_px_max",
    "camera_matrix_and_projection_abs_max",
    "light_position_direction_color_abs_max",
    "projection_control_point_error_px_max",
    "midgray_median_delta_e_00_max",
    "material_family_roi_median_delta_e_00_max",
    "material_family_roi_p95_delta_e_00_max",
    "material_family_roi_median_relative_luminance_diff_max",
    "material_board_luminance_ssim_min",
    "structural_internal_roi_luminance_ssim_min",
    "repeatability_changed_pixel_threshold",
    "repeatability_changed_pixel_ratio_max",
}


class ComparisonError(RuntimeError):
    """A fail-closed comparison input or metric error."""


def utc_now() -> str:
    """Return an ISO UTC timestamp."""

    return datetime.now(timezone.utc).isoformat()


def sha256(path: Path) -> str:
    """Hash a file incrementally."""

    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def rel(path: Path) -> str:
    """Return a repository-relative POSIX path."""

    return path.resolve().relative_to(ROOT.resolve()).as_posix()


def artifact(path: Path) -> dict[str, Any]:
    """Describe an existing artifact."""

    return {
        "path": rel(path),
        "bytes": path.stat().st_size,
        "sha256": sha256(path),
    }


def write_json(path: Path, value: Any) -> None:
    """Write deterministic UTF-8 JSON."""

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def parse_args() -> argparse.Namespace:
    """Parse the standalone comparison CLI."""

    parser = argparse.ArgumentParser(
        description="Compare pre-registered Blender Eevee/Cycles renderer evidence."
    )
    parser.add_argument("--contract", type=Path, default=DEFAULT_CONTRACT)
    parser.add_argument(
        "--capture-manifest",
        type=Path,
        default=DEFAULT_CAPTURE_MANIFEST,
    )
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_STAGE)
    return parser.parse_args()


def require(condition: bool, message: str) -> None:
    """Raise a comparison error when a fail-closed precondition is false."""

    if not condition:
        raise ComparisonError(message)


def load_inputs(
    contract_path: Path,
    manifest_path: Path,
    output_dir: Path,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Load and validate contract/manifest identity before metrics."""

    require(contract_path.is_file(), f"contract missing: {contract_path}")
    require(manifest_path.is_file(), f"capture manifest missing: {manifest_path}")
    require(
        output_dir.resolve().is_relative_to(ROOT.resolve()),
        "output directory must remain inside the repository",
    )
    contract = json.loads(contract_path.read_text(encoding="utf-8"))
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    require(
        contract.get("schema_version") == "bf3d.r2r.capture_contract.v1",
        "unsupported capture contract schema",
    )
    require(contract.get("requirement_id") == REQUIREMENT_ID, "contract requirement drift")
    require(
        manifest.get("schema_version") == "bf3d.r2r.capture_manifest.v1",
        "unsupported capture manifest schema",
    )
    require(manifest.get("requirement_id") == REQUIREMENT_ID, "manifest requirement drift")
    recorded_contract = manifest.get("contract") or {}
    require(
        recorded_contract.get("sha256") == sha256(contract_path),
        "capture manifest was not made from the current pre-registered contract",
    )
    thresholds = (contract.get("comparison_contract") or {}).get("thresholds") or {}
    missing = sorted(THRESHOLD_KEYS.difference(thresholds))
    require(not missing, f"required thresholds missing: {missing}")
    require(
        contract["comparison_contract"].get("aggregation")
        == "every applicable shot, every material-family ROI and every repeatability check must pass; no averaging may hide a failed shot or family",
        "aggregation policy drifted",
    )
    require(
        contract["comparison_contract"].get("not_evaluated_policy")
        == "any required threshold marked not_evaluated prevents a complete A/B PASS",
        "not-evaluated policy drifted",
    )
    require(
        contract["comparison_contract"].get("missing_or_invalid_input_policy")
        == "fail_closed",
        "missing-input policy drifted",
    )
    return contract, manifest


def lock_snapshot(contract: dict[str, Any]) -> dict[str, Any]:
    """Re-verify all registered read-only inputs at comparison time."""

    records: list[dict[str, Any]] = []
    for item in contract.get("input_locks", []):
        path = ROOT / item["path"]
        exists = path.is_file()
        actual_bytes = path.stat().st_size if exists else None
        actual_sha = sha256(path) if exists else None
        passed = (
            exists
            and actual_bytes == item.get("bytes")
            and actual_sha == item.get("sha256")
        )
        records.append(
            {
                "id": item.get("id"),
                "path": item.get("path"),
                "expected_bytes": item.get("bytes"),
                "actual_bytes": actual_bytes,
                "expected_sha256": item.get("sha256"),
                "actual_sha256": actual_sha,
                "required": item.get("required") is True,
                "passed": passed,
            }
        )
    required_records = [record for record in records if record["required"]]
    return {
        "records": records,
        "required_count": len(required_records),
        "passed": bool(required_records) and all(record["passed"] for record in required_records),
    }


def resolve_artifact(record: dict[str, Any]) -> Path:
    """Resolve and validate a manifest artifact path/hash/size."""

    path = (ROOT / record["path"]).resolve()
    require(path.is_relative_to(ROOT.resolve()), "artifact path escaped repository")
    require(path.is_file(), f"artifact missing: {path}")
    require(path.stat().st_size == record.get("bytes"), f"artifact size drift: {path}")
    require(sha256(path) == record.get("sha256"), f"artifact hash drift: {path}")
    return path


def capture_index(manifest: dict[str, Any], repeat_count: int) -> dict[tuple[str, int, str], dict[str, Any]]:
    """Index captures and reject missing, duplicate, or extra records."""

    index: dict[tuple[str, int, str], dict[str, Any]] = {}
    for record in manifest.get("captures", []):
        key = (
            str(record.get("engine_id")),
            int(record.get("repeat_index", -1)),
            str(record.get("shot_id")),
        )
        require(key not in index, f"duplicate capture record: {key}")
        index[key] = record
    expected = {
        (engine, repeat, shot)
        for engine in ENGINE_IDS
        for repeat in range(1, repeat_count + 1)
        for shot in SHOT_IDS
    }
    require(set(index) == expected, f"capture set mismatch; missing={sorted(expected-set(index))}")
    return index


def load_capture(record: dict[str, Any], resolution: tuple[int, int]) -> dict[str, Any]:
    """Load one RGBA beauty and its derived mask with strict validation."""

    beauty_path = resolve_artifact(record["beauty"])
    mask_path = resolve_artifact(record["mask"])
    with Image.open(beauty_path) as image:
        original_mode = image.mode
        rgba_u8 = np.asarray(image.convert("RGBA"), dtype=np.uint8)
    with Image.open(mask_path) as image:
        mask_u8 = np.asarray(image.convert("L"), dtype=np.uint8)
    height, width = rgba_u8.shape[:2]
    require(original_mode == "RGBA", f"beauty is not stored as RGBA: {beauty_path}")
    require((width, height) == resolution, f"beauty resolution drift: {beauty_path}")
    require(mask_u8.shape == (height, width), f"mask resolution drift: {mask_path}")
    rgba = rgba_u8.astype(np.float32) / 255.0
    mask = mask_u8.astype(np.float32) / 255.0 >= 0.5
    alpha_mask = rgba[..., 3] >= 0.5
    mismatch = int(np.count_nonzero(mask != alpha_mask))
    require(mismatch == 0, f"mask does not match beauty alpha: {mask_path}")
    require(np.any(mask), f"empty alpha mask: {mask_path}")
    return {
        "rgba": rgba,
        "rgb": rgba[..., :3],
        "mask": mask,
        "beauty_path": beauty_path,
        "mask_path": mask_path,
        "alpha_mask_mismatch_pixels": mismatch,
    }


def erode(mask: np.ndarray, pixels: int) -> np.ndarray:
    """Erode a binary mask using the registered pixel count."""

    if pixels <= 0:
        return mask.copy()
    return ndimage.binary_erosion(
        mask,
        structure=np.ones((3, 3), dtype=bool),
        iterations=pixels,
        border_value=0,
    )


def silhouette_iou(first: np.ndarray, second: np.ndarray) -> float:
    """Compute binary silhouette intersection over union."""

    union = first | second
    require(np.any(union), "silhouette union is empty")
    return float(np.count_nonzero(first & second) / np.count_nonzero(union))


def edge_p95(first: np.ndarray, second: np.ndarray) -> float:
    """Compute symmetric 95th-percentile binary edge distance in pixels."""

    first_edge = first ^ ndimage.binary_erosion(first, structure=np.ones((3, 3), bool))
    second_edge = second ^ ndimage.binary_erosion(second, structure=np.ones((3, 3), bool))
    require(np.any(first_edge) and np.any(second_edge), "silhouette edge is empty")
    distance_to_second = ndimage.distance_transform_edt(~second_edge)
    distance_to_first = ndimage.distance_transform_edt(~first_edge)
    distances = np.concatenate(
        (distance_to_second[first_edge], distance_to_first[second_edge])
    )
    return float(np.percentile(distances, 95.0))


def srgb_luminance(rgb: np.ndarray) -> np.ndarray:
    """Convert decoded sRGB floats to IEC linear relative luminance."""

    linear = np.where(
        rgb <= 0.04045,
        rgb / 12.92,
        ((rgb + 0.055) / 1.055) ** 2.4,
    )
    return (
        0.2126 * linear[..., 0]
        + 0.7152 * linear[..., 1]
        + 0.0722 * linear[..., 2]
    )


def mask_bbox(mask: np.ndarray) -> tuple[int, int, int, int]:
    """Return a tight x0,y0,x1,y1 bounding box for a non-empty mask."""

    ys, xs = np.nonzero(mask)
    require(len(xs) > 0, "metric ROI is empty")
    return int(xs.min()), int(ys.min()), int(xs.max()) + 1, int(ys.max()) + 1


def masked_ssim(first: np.ndarray, second: np.ndarray, mask: np.ndarray) -> float:
    """Compute local luminance SSIM and average only the registered ROI."""

    x0, y0, x1, y1 = mask_bbox(mask)
    first_crop = first[y0:y1, x0:x1]
    second_crop = second[y0:y1, x0:x1]
    mask_crop = mask[y0:y1, x0:x1]
    require(min(first_crop.shape) >= 11, "SSIM ROI is smaller than the 11px window")
    _global, ssim_map = structural_similarity(
        first_crop,
        second_crop,
        data_range=1.0,
        gaussian_weights=True,
        sigma=1.5,
        use_sample_covariance=False,
        win_size=11,
        full=True,
    )
    values = ssim_map[mask_crop]
    require(values.size > 0 and np.all(np.isfinite(values)), "SSIM values invalid")
    return float(np.mean(values))


def rectangular_mask(shape: tuple[int, int], bbox: list[int]) -> np.ndarray:
    """Create a clamped mask from x0,y0,x1,y1 capture metadata."""

    height, width = shape
    require(isinstance(bbox, list) and len(bbox) == 4, "invalid ROI bbox metadata")
    x0, y0, x1, y1 = [int(value) for value in bbox]
    x0, x1 = max(0, x0), min(width, x1)
    y0, y1 = max(0, y0), min(height, y1)
    require(x1 > x0 and y1 > y0, "ROI bbox is empty after clamping")
    result = np.zeros(shape, dtype=bool)
    result[y0:y1, x0:x1] = True
    return result


def delta_e_values(
    first_rgb: np.ndarray,
    second_rgb: np.ndarray,
    mask: np.ndarray,
) -> np.ndarray:
    """Return CIEDE2000 values in a tight D65 Lab ROI."""

    x0, y0, x1, y1 = mask_bbox(mask)
    local_mask = mask[y0:y1, x0:x1]
    first_lab = color.rgb2lab(first_rgb[y0:y1, x0:x1], illuminant="D65")
    second_lab = color.rgb2lab(second_rgb[y0:y1, x0:x1], illuminant="D65")
    values = color.deltaE_ciede2000(first_lab, second_lab)[local_mask]
    require(values.size > 0 and np.all(np.isfinite(values)), "DeltaE00 values invalid")
    return values


def symmetric_relative_luminance(
    first: np.ndarray,
    second: np.ndarray,
    mask: np.ndarray,
) -> np.ndarray:
    """Return engine-neutral symmetric relative luminance differences."""

    denominator = np.maximum(0.5 * (first + second), 1.0e-6)
    values = (np.abs(first - second) / denominator)[mask]
    require(values.size > 0 and np.all(np.isfinite(values)), "luminance values invalid")
    return values


def max_abs(first: list[float], second: list[float]) -> float:
    """Return maximum absolute difference for equal-length numeric vectors."""

    require(len(first) == len(second), "numeric vector length mismatch")
    require(bool(first), "numeric vector is empty")
    return float(np.max(np.abs(np.asarray(first, float) - np.asarray(second, float))))


def camera_difference(first: dict[str, Any], second: dict[str, Any]) -> float:
    """Compare camera world/view/projection matrices and projection parameters."""

    require(first.get("object") == second.get("object"), "camera object mismatch")
    require(first.get("type") == second.get("type") == "ORTHO", "camera type mismatch")
    differences = [
        max_abs(first[key], second[key])
        for key in ("matrix_world", "view_matrix", "projection_matrix", "location", "rotation_quaternion")
    ]
    differences.extend(
        abs(float(first[key]) - float(second[key]))
        for key in ("ortho_scale", "clip_start", "clip_end")
    )
    return float(max(differences))


def light_difference(first: list[dict[str, Any]], second: list[dict[str, Any]]) -> float:
    """Compare registered light position, direction, and color fields."""

    first_map = {item["name"]: item for item in first}
    second_map = {item["name"]: item for item in second}
    require(first_map.keys() == second_map.keys(), "light name set mismatch")
    differences: list[float] = []
    for name in sorted(first_map):
        require(first_map[name]["type"] == second_map[name]["type"], f"light type mismatch: {name}")
        for key in ("location", "direction", "color"):
            differences.append(max_abs(first_map[name][key], second_map[name][key]))
    return float(max(differences))


def control_point_error(first: dict[str, list[float]], second: dict[str, list[float]]) -> float:
    """Return maximum projected 2D control-point error in pixels."""

    require(first.keys() == second.keys(), "projection control-point set mismatch")
    errors = [
        math.hypot(
            float(first[key][0]) - float(second[key][0]),
            float(first[key][1]) - float(second[key][1]),
        )
        for key in first
    ]
    require(bool(errors), "projection control-point set is empty")
    return float(max(errors))


def add_check(
    checks: list[dict[str, Any]],
    check_id: str,
    metric: str,
    value: float,
    operator: str,
    threshold: float,
    context: dict[str, Any],
) -> dict[str, Any]:
    """Append one evaluated threshold result."""

    if operator == ">=":
        passed = value >= threshold
    elif operator == "<=":
        passed = value <= threshold
    else:
        raise ComparisonError(f"unsupported comparison operator: {operator}")
    result = {
        "id": check_id,
        "metric": metric,
        "status": "pass" if passed else "fail",
        "value": float(value),
        "operator": operator,
        "threshold": float(threshold),
        "passed": bool(passed),
        **context,
    }
    checks.append(result)
    return result


def add_not_evaluated(
    checks: list[dict[str, Any]],
    check_id: str,
    metric: str,
    operator: str,
    threshold: float,
    context: dict[str, Any],
    reason: str,
) -> None:
    """Append a required but unavailable metric, which prevents PASS."""

    checks.append(
        {
            "id": check_id,
            "metric": metric,
            "status": "not_evaluated",
            "value": None,
            "operator": operator,
            "threshold": float(threshold),
            "passed": False,
            "reason": reason,
            **context,
        }
    )


def required_ab_specs(shot_id: str, thresholds: dict[str, float]) -> list[tuple[str, str, str, float]]:
    """List every required A/B metric for one shot."""

    specs = [
        ("silhouette_iou", "silhouette_iou", ">=", thresholds["silhouette_iou_min"]),
        (
            "edge_p95_px",
            "symmetric_edge_distance_p95_px",
            "<=",
            thresholds["symmetric_edge_distance_p95_px_max"],
        ),
        (
            "camera_abs_max",
            "camera_matrix_and_projection_abs_max",
            "<=",
            thresholds["camera_matrix_and_projection_abs_max"],
        ),
        (
            "light_abs_max",
            "light_position_direction_color_abs_max",
            "<=",
            thresholds["light_position_direction_color_abs_max"],
        ),
        (
            "control_point_error_px",
            "projection_control_point_error_px_max",
            "<=",
            thresholds["projection_control_point_error_px_max"],
        ),
    ]
    if shot_id == "six_family_material_board_with_midgray":
        specs.extend(
            [
                (
                    "midgray_delta_e00_median",
                    "midgray_median_delta_e_00",
                    "<=",
                    thresholds["midgray_median_delta_e_00_max"],
                ),
                (
                    "material_board_ssim",
                    "material_board_luminance_ssim",
                    ">=",
                    thresholds["material_board_luminance_ssim_min"],
                ),
            ]
        )
        for family in PRIMARY_FAMILIES:
            specs.extend(
                [
                    (
                        f"{family}.delta_e00_median",
                        "material_family_roi_median_delta_e_00",
                        "<=",
                        thresholds["material_family_roi_median_delta_e_00_max"],
                    ),
                    (
                        f"{family}.delta_e00_p95",
                        "material_family_roi_p95_delta_e_00",
                        "<=",
                        thresholds["material_family_roi_p95_delta_e_00_max"],
                    ),
                    (
                        f"{family}.relative_luminance_median",
                        "material_family_roi_median_relative_luminance_diff",
                        "<=",
                        thresholds[
                            "material_family_roi_median_relative_luminance_diff_max"
                        ],
                    ),
                ]
            )
    else:
        specs.append(
            (
                "structural_ssim",
                "structural_internal_roi_luminance_ssim",
                ">=",
                thresholds["structural_internal_roi_luminance_ssim_min"],
            )
        )
    return specs


def save_ab_diffs(
    output_dir: Path,
    shot_id: str,
    repeat: int,
    first: dict[str, Any],
    second: dict[str, Any],
) -> list[dict[str, Any]]:
    """Write amplified RGB and silhouette-XOR visual evidence."""

    directory = output_dir / "diffs" / "ab"
    directory.mkdir(parents=True, exist_ok=True)
    union = first["mask"] | second["mask"]
    difference = np.abs(first["rgb"] - second["rgb"])
    display = np.clip(difference * 4.0, 0.0, 1.0)
    display[~union] = 0.0
    diff_path = directory / f"repeat_{repeat:02d}_{shot_id}_absdiff_x4.png"
    Image.fromarray(np.round(display * 255.0).astype(np.uint8), "RGB").save(diff_path)

    xor = first["mask"] ^ second["mask"]
    mask_display = np.zeros((*xor.shape, 3), dtype=np.uint8)
    mask_display[first["mask"] & ~second["mask"]] = (255, 180, 0)
    mask_display[second["mask"] & ~first["mask"]] = (0, 210, 255)
    mask_path = directory / f"repeat_{repeat:02d}_{shot_id}_mask_xor.png"
    Image.fromarray(mask_display, "RGB").save(mask_path)
    return [
        {**artifact(diff_path), "display_scale": 4.0, "kind": "absolute_rgb_difference"},
        {**artifact(mask_path), "kind": "silhouette_xor"},
    ]


def compare_ab_pair(
    checks: list[dict[str, Any]],
    summaries: list[dict[str, Any]],
    diffs: list[dict[str, Any]],
    output_dir: Path,
    thresholds: dict[str, float],
    resolution: tuple[int, int],
    erosion_pixels: int,
    repeat: int,
    shot_id: str,
    eevee_record: dict[str, Any],
    cycles_record: dict[str, Any],
) -> None:
    """Evaluate every required A/B metric for a shot/repeat pair."""

    context = {"repeat_index": repeat, "shot_id": shot_id, "comparison": "eevee_vs_cycles"}
    specs = required_ab_specs(shot_id, thresholds)
    prefix = f"ab.repeat_{repeat:02d}.{shot_id}"
    try:
        require(
            eevee_record.get("object_material_roles")
            == cycles_record.get("object_material_roles"),
            "object/material role contract differs between engines",
        )
        first = load_capture(eevee_record, resolution)
        second = load_capture(cycles_record, resolution)
        iou = silhouette_iou(first["mask"], second["mask"])
        edge = edge_p95(first["mask"], second["mask"])
        camera = camera_difference(eevee_record["camera"], cycles_record["camera"])
        light = light_difference(eevee_record["lights"], cycles_record["lights"])
        controls = control_point_error(
            eevee_record["camera"]["control_points_px"],
            cycles_record["camera"]["control_points_px"],
        )
        values: dict[str, float] = {
            "silhouette_iou": iou,
            "edge_p95_px": edge,
            "camera_abs_max": camera,
            "light_abs_max": light,
            "control_point_error_px": controls,
        }
        common_interior = erode(first["mask"], erosion_pixels) & erode(
            second["mask"], erosion_pixels
        )
        first_luminance = srgb_luminance(first["rgb"])
        second_luminance = srgb_luminance(second["rgb"])
        if shot_id == "six_family_material_board_with_midgray":
            values["material_board_ssim"] = masked_ssim(
                first_luminance,
                second_luminance,
                common_interior,
            )
            first_rois = eevee_record["camera"].get("material_rois_px")
            second_rois = cycles_record["camera"].get("material_rois_px")
            require(
                isinstance(first_rois, dict) and isinstance(second_rois, dict),
                "material ROI metadata missing",
            )
            require(first_rois.keys() == second_rois.keys(), "material ROI family set mismatch")
            midgray_first = eevee_record["camera"].get("midgray_roi_px")
            midgray_second = cycles_record["camera"].get("midgray_roi_px")
            require(midgray_first is not None and midgray_second is not None, "midgray ROI missing")
            midgray_rect = rectangular_mask(first["mask"].shape, midgray_first) & rectangular_mask(
                second["mask"].shape, midgray_second
            )
            midgray_mask = common_interior & midgray_rect
            midgray_delta = delta_e_values(first["rgb"], second["rgb"], midgray_mask)
            values["midgray_delta_e00_median"] = float(np.median(midgray_delta))
            for family in PRIMARY_FAMILIES:
                family_rect = rectangular_mask(
                    first["mask"].shape, first_rois[family]
                ) & rectangular_mask(second["mask"].shape, second_rois[family])
                family_mask = common_interior & family_rect
                delta = delta_e_values(first["rgb"], second["rgb"], family_mask)
                relative_luminance = symmetric_relative_luminance(
                    first_luminance,
                    second_luminance,
                    family_mask,
                )
                values[f"{family}.delta_e00_median"] = float(np.median(delta))
                values[f"{family}.delta_e00_p95"] = float(np.percentile(delta, 95.0))
                values[f"{family}.relative_luminance_median"] = float(
                    np.median(relative_luminance)
                )
        else:
            values["structural_ssim"] = masked_ssim(
                first_luminance,
                second_luminance,
                common_interior,
            )
        for suffix, metric, operator, threshold in specs:
            require(suffix in values, f"required metric was not computed: {suffix}")
            add_check(
                checks,
                f"{prefix}.{suffix}",
                metric,
                values[suffix],
                operator,
                threshold,
                context,
            )
        pair_diffs = save_ab_diffs(output_dir, shot_id, repeat, first, second)
        diffs.extend(pair_diffs)
        summaries.append(
            {
                **context,
                "metrics": values,
                "diffs": pair_diffs,
                "evaluated": True,
            }
        )
    except Exception as exc:
        reason = f"{type(exc).__name__}: {exc}"
        for suffix, metric, operator, threshold in specs:
            add_not_evaluated(
                checks,
                f"{prefix}.{suffix}",
                metric,
                operator,
                threshold,
                context,
                reason,
            )
        summaries.append({**context, "evaluated": False, "reason": reason})


def save_repeat_diff(
    output_dir: Path,
    engine: str,
    shot_id: str,
    first: dict[str, Any],
    second: dict[str, Any],
    changed: np.ndarray,
) -> dict[str, Any]:
    """Write a repeatability changed-pixel map."""

    directory = output_dir / "diffs" / "repeatability"
    directory.mkdir(parents=True, exist_ok=True)
    display = np.zeros((*changed.shape, 3), dtype=np.uint8)
    display[changed] = (255, 40, 70)
    path = directory / f"{engine}_{shot_id}_repeat_01_vs_02.png"
    Image.fromarray(display, "RGB").save(path)
    return {**artifact(path), "kind": "repeatability_changed_pixels"}


def compare_repeatability(
    checks: list[dict[str, Any]],
    summaries: list[dict[str, Any]],
    diffs: list[dict[str, Any]],
    output_dir: Path,
    thresholds: dict[str, float],
    resolution: tuple[int, int],
    engine: str,
    shot_id: str,
    first_record: dict[str, Any],
    second_record: dict[str, Any],
) -> None:
    """Evaluate required changed-pixel repeatability for one engine/shot."""

    context = {"engine_id": engine, "shot_id": shot_id, "comparison": "repeat_01_vs_02"}
    check_id = f"repeatability.{engine}.{shot_id}.changed_pixel_ratio"
    threshold = thresholds["repeatability_changed_pixel_ratio_max"]
    try:
        first = load_capture(first_record, resolution)
        second = load_capture(second_record, resolution)
        union = first["mask"] | second["mask"]
        require(np.any(union), "repeatability foreground union is empty")
        absolute = np.max(np.abs(first["rgba"] - second["rgba"]), axis=2)
        changed = (absolute > thresholds["repeatability_changed_pixel_threshold"]) & union
        ratio = float(np.count_nonzero(changed) / np.count_nonzero(union))
        result = add_check(
            checks,
            check_id,
            "repeatability_changed_pixel_ratio",
            ratio,
            "<=",
            threshold,
            context,
        )
        repeat_diff = save_repeat_diff(
            output_dir,
            engine,
            shot_id,
            first,
            second,
            changed,
        )
        diffs.append(repeat_diff)
        summaries.append(
            {
                **context,
                "evaluated": True,
                "changed_pixel_threshold": thresholds[
                    "repeatability_changed_pixel_threshold"
                ],
                "changed_pixel_count": int(np.count_nonzero(changed)),
                "foreground_union_pixels": int(np.count_nonzero(union)),
                "changed_pixel_ratio": ratio,
                "max_channel_abs_difference": float(np.max(absolute[union])),
                "mask_iou": silhouette_iou(first["mask"], second["mask"]),
                "diff": repeat_diff,
                "passed": result["passed"],
            }
        )
    except Exception as exc:
        reason = f"{type(exc).__name__}: {exc}"
        add_not_evaluated(
            checks,
            check_id,
            "repeatability_changed_pixel_ratio",
            "<=",
            threshold,
            context,
            reason,
        )
        summaries.append({**context, "evaluated": False, "reason": reason})


def add_all_not_evaluated(
    checks: list[dict[str, Any]],
    thresholds: dict[str, float],
    repeat_count: int,
    reason: str,
) -> None:
    """Materialize every missing required metric for a blocked capture run."""

    for repeat in range(1, repeat_count + 1):
        for shot_id in SHOT_IDS:
            context = {
                "repeat_index": repeat,
                "shot_id": shot_id,
                "comparison": "eevee_vs_cycles",
            }
            prefix = f"ab.repeat_{repeat:02d}.{shot_id}"
            for suffix, metric, operator, threshold in required_ab_specs(
                shot_id, thresholds
            ):
                add_not_evaluated(
                    checks,
                    f"{prefix}.{suffix}",
                    metric,
                    operator,
                    threshold,
                    context,
                    reason,
                )
    for engine in ENGINE_IDS:
        for shot_id in SHOT_IDS:
            add_not_evaluated(
                checks,
                f"repeatability.{engine}.{shot_id}.changed_pixel_ratio",
                "repeatability_changed_pixel_ratio",
                "<=",
                thresholds["repeatability_changed_pixel_ratio_max"],
                {"engine_id": engine, "shot_id": shot_id, "comparison": "repeat_01_vs_02"},
                reason,
            )


def comparison_markdown(report: dict[str, Any]) -> str:
    """Render the numeric gate report as concise Markdown."""

    lines = [
        "# WEB-60 R2R Blender renderer numeric A/B gate",
        "",
        f"- Status: **{report['status']}**",
        f"- Requirement: `{report['requirement_id']}`",
        f"- Required metrics: {report['aggregation']['required_metric_count']}",
        f"- Passed: {report['aggregation']['passed_count']}",
        f"- Failed: {report['aggregation']['failed_count']}",
        f"- Not evaluated: {report['aggregation']['not_evaluated_count']}",
        f"- Source/GLB locks unchanged: {report['input_locks_current']['passed']}",
        f"- Approval granted: {report['approval_granted']}",
        f"- Evidence class: `{report['evidence_class']}`; reference: `{report['reference_status']}`",
        "",
        "## Required metric failures",
        "",
        "| Check | Status | Value | Gate |",
        "|---|---|---:|---|",
    ]
    failures = [
        item for item in report["checks"] if item["status"] != "pass"
    ]
    if failures:
        for item in failures:
            value = (
                "N/E"
                if item["value"] is None
                else f"{float(item['value']):.8g}"
            )
            reason = f"; {item.get('reason')}" if item.get("reason") else ""
            lines.append(
                f"| `{item['id']}` | {item['status']}{reason} | {value} | "
                f"{item['operator']} {float(item['threshold']):.8g} |"
            )
    else:
        lines.append("| — | all pass | — | — |")
    lines.extend(
        [
            "",
            "## Per-shot A/B summary",
            "",
            "| Repeat | Shot | IoU | Edge P95 px | Luminance SSIM |",
            "|---:|---|---:|---:|---:|",
        ]
    )
    for item in report["ab_pairs"]:
        metrics = item.get("metrics", {})
        ssim = metrics.get("structural_ssim", metrics.get("material_board_ssim"))
        lines.append(
            f"| {item.get('repeat_index', '—')} | `{item['shot_id']}` | "
            f"{metrics.get('silhouette_iou', float('nan')):.6f} | "
            f"{metrics.get('edge_p95_px', float('nan')):.4f} | "
            f"{ssim if ssim is not None else float('nan'):.6f} |"
        )
    lines.extend(
        [
            "",
            "The gate is fail-closed: any required `not_evaluated` metric prevents PASS, "
            "and no shot/family result is averaged into another.",
            "",
        ]
    )
    return "\n".join(lines)


def write_artifact_manifest(
    output_dir: Path,
    contract_path: Path,
    capture_manifest_path: Path,
) -> None:
    """Index generated evidence and implementation scripts."""

    manifest_path = output_dir / "artifact_manifest.json"
    generated: list[dict[str, Any]] = []
    for path in sorted(output_dir.rglob("*")):
        if not path.is_file() or path == manifest_path:
            continue
        generated.append(artifact(path))
    value = {
        "schema_version": ARTIFACT_SCHEMA,
        "requirement_id": REQUIREMENT_ID,
        "generated_at": utc_now(),
        "implementation": [
            artifact(ROOT / "tools" / "render_bf3d_r2q_ab_blender.py"),
            artifact(ROOT / "tools" / "compare_bf3d_r2q_ab.py"),
        ],
        "contract": artifact(contract_path),
        "capture_manifest": artifact(capture_manifest_path),
        "generated_artifacts": generated,
    }
    write_json(manifest_path, value)


def main() -> int:
    """Run all numeric comparisons and write JSON/Markdown/diff evidence."""

    args = parse_args()
    contract_path = args.contract.resolve()
    capture_manifest_path = args.capture_manifest.resolve()
    output_dir = args.output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    report: dict[str, Any] = {
        "schema_version": REPORT_SCHEMA,
        "requirement_id": REQUIREMENT_ID,
        "started_at": utc_now(),
        "status": "INITIALIZING",
        "checks": [],
        "ab_pairs": [],
        "repeatability": [],
        "diffs": [],
    }
    try:
        contract, capture_manifest = load_inputs(
            contract_path,
            capture_manifest_path,
            output_dir,
        )
        comparison = contract["comparison_contract"]
        thresholds = comparison["thresholds"]
        repeat_count = int(contract["capture_contract"]["repeat_count"])
        resolution = tuple(int(value) for value in contract["scene_contract"]["resolution"])
        erosion_pixels = int(comparison["interior_erosion_pixels"])
        report.update(
            {
                "contract": artifact(contract_path),
                "capture_manifest": artifact(capture_manifest_path),
                "evidence_class": contract["evidence_class"],
                "reference_status": contract["reference_status"],
                "not_for_construction": contract["not_for_construction"],
                "approval_granted": contract["approval_granted"],
                "thresholds": thresholds,
                "methods": {
                    "mask_threshold": comparison["mask_threshold"],
                    "interior_erosion_pixels": erosion_pixels,
                    "color_space": comparison["comparison_color_space"],
                    "edge_distance": "symmetric Euclidean distance-transform P95 of 1px binary boundaries",
                    "relative_luminance": "absolute symmetric difference divided by mean luminance",
                    "ssim": "11px Gaussian local luminance SSIM averaged only over the common eroded foreground ROI",
                    "repeatability_denominator": "union of repeat-01/repeat-02 alpha masks",
                },
                "input_locks_current": lock_snapshot(contract),
                "capture_status": capture_manifest.get("status"),
            }
        )
        if capture_manifest.get("status") == "blocked":
            reason = capture_manifest.get("reason", "capture manifest is blocked")
            add_all_not_evaluated(report["checks"], thresholds, repeat_count, reason)
            report["status"] = "BLOCKED"
        elif capture_manifest.get("status") != "captured":
            reason = f"capture manifest status is {capture_manifest.get('status')!r}"
            add_all_not_evaluated(report["checks"], thresholds, repeat_count, reason)
            report["status"] = "FAIL"
        else:
            index = capture_index(capture_manifest, repeat_count)
            require(
                report["input_locks_current"]["passed"],
                "one or more registered inputs drifted before comparison",
            )
            require(
                capture_manifest.get("input_locks_before", {}).get("passed") is True
                and capture_manifest.get("input_locks_after", {}).get("passed") is True
                and capture_manifest.get("source_mutation_detected") is False,
                "capture did not prove read-only input stability",
            )
            for repeat in range(1, repeat_count + 1):
                for shot_id in SHOT_IDS:
                    compare_ab_pair(
                        report["checks"],
                        report["ab_pairs"],
                        report["diffs"],
                        output_dir,
                        thresholds,
                        resolution,
                        erosion_pixels,
                        repeat,
                        shot_id,
                        index[("eevee", repeat, shot_id)],
                        index[("cycles", repeat, shot_id)],
                    )
            for engine in ENGINE_IDS:
                for shot_id in SHOT_IDS:
                    compare_repeatability(
                        report["checks"],
                        report["repeatability"],
                        report["diffs"],
                        output_dir,
                        thresholds,
                        resolution,
                        engine,
                        shot_id,
                        index[(engine, 1, shot_id)],
                        index[(engine, 2, shot_id)],
                    )
            report["status"] = "PASS" if all(
                item["status"] == "pass" for item in report["checks"]
            ) else "FAIL"
        report["completed_at"] = utc_now()
        report["aggregation"] = {
            "policy": comparison["aggregation"],
            "not_evaluated_policy": comparison["not_evaluated_policy"],
            "required_metric_count": len(report["checks"]),
            "passed_count": sum(item["status"] == "pass" for item in report["checks"]),
            "failed_count": sum(item["status"] == "fail" for item in report["checks"]),
            "not_evaluated_count": sum(
                item["status"] == "not_evaluated" for item in report["checks"]
            ),
            "numeric_ab_pass": report["status"] == "PASS",
        }
        write_json(output_dir / "comparison_report.json", report)
        (output_dir / "comparison_report.md").write_text(
            comparison_markdown(report),
            encoding="utf-8",
        )
        write_artifact_manifest(output_dir, contract_path, capture_manifest_path)
        print(
            "BF3D_R2R_COMPARISON="
            + json.dumps(
                {
                    "status": report["status"],
                    **report["aggregation"],
                    "report": rel(output_dir / "comparison_report.json"),
                },
                ensure_ascii=False,
            )
        )
        return 0 if report["status"] == "PASS" else 2
    except Exception as exc:
        report["status"] = "FAIL"
        report["completed_at"] = utc_now()
        report["fatal_error"] = f"{type(exc).__name__}: {exc}"
        report["traceback"] = traceback.format_exc()
        report["aggregation"] = {
            "required_metric_count": len(report["checks"]),
            "passed_count": sum(item["status"] == "pass" for item in report["checks"]),
            "failed_count": sum(item["status"] == "fail" for item in report["checks"]),
            "not_evaluated_count": sum(
                item["status"] == "not_evaluated" for item in report["checks"]
            ),
            "numeric_ab_pass": False,
        }
        write_json(output_dir / "comparison_report.json", report)
        print("BF3D_R2R_COMPARISON_FAILED=" + report["fatal_error"])
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
