"""Measure foreground-only P30 channel preview statistics."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
from PIL import Image


CHANNELS = {
    "base_color": "base_color/P30_BASE_COLOR_front.png",
    "roughness": "roughness/P30_ROUGHNESS_front.png",
    "metallic": "metallic/P30_METALLIC_front.png",
    "exposed_mask": "exposed_mask/P30_EXPOSED_MASK_front.png",
    "oxidation_mask": "oxidation_mask/P30_OXIDATION_MASK_front.png",
    "dust_mask": "dust_mask/P30_DUST_MASK_front.png",
    "water_mask": "water_mask/P30_WATER_MASK_front.png",
}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--renders-dir", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    report: dict[str, object] = {"schema_version": 1, "channels": {}}
    foreground = None
    arrays: dict[str, np.ndarray] = {}
    for name, relative in CHANNELS.items():
        path = args.renders_dir / relative
        rgba = np.asarray(Image.open(path).convert("RGBA"), dtype=np.float32) / 255.0
        arrays[name] = rgba
        current = rgba[..., 3] > 0.5
        foreground = current if foreground is None else foreground | current
    if foreground is None or not np.any(foreground):
        raise RuntimeError("No foreground pixels found")
    for name, rgba in arrays.items():
        rgb = rgba[..., :3][foreground]
        linear_rgb = np.where(rgb <= 0.04045, rgb / 12.92, ((rgb + 0.055) / 1.055) ** 2.4)
        analysis_rgb = rgb if name == "base_color" else linear_rgb
        first = analysis_rgb[:, 0]
        report["channels"][name] = {
            "path": str((args.renders_dir / CHANNELS[name]).resolve()),
            "foreground_pixels": int(rgb.shape[0]),
            "rgb_mean": [round(float(value), 6) for value in np.mean(rgb, axis=0)],
            "rgb_p05": [round(float(value), 6) for value in np.quantile(rgb, 0.05, axis=0)],
            "rgb_p50": [round(float(value), 6) for value in np.quantile(rgb, 0.50, axis=0)],
            "rgb_p95": [round(float(value), 6) for value in np.quantile(rgb, 0.95, axis=0)],
            "linear_mean": [round(float(value), 6) for value in np.mean(linear_rgb, axis=0)],
            "linear_p50": [round(float(value), 6) for value in np.quantile(linear_rgb, 0.50, axis=0)],
            "first_channel_above_0_5_ratio": round(float(np.mean(first > 0.5)), 6),
            "first_channel_above_0_1_ratio": round(float(np.mean(first > 0.1)), 6),
        }
    metrics = report["channels"]
    report["targets"] = {
        "exposed_coverage_12_to_22_percent": 0.12 <= metrics["exposed_mask"]["first_channel_above_0_5_ratio"] <= 0.22,
        "metallic_coverage_15_to_25_percent": 0.15 <= metrics["metallic"]["first_channel_above_0_5_ratio"] <= 0.25,
        "metallic_mean_0_20_to_0_32": 0.20 <= metrics["metallic"]["linear_mean"][0] <= 0.32,
        "oxidation_effective_3_to_8_percent": 0.03 <= metrics["oxidation_mask"]["first_channel_above_0_1_ratio"] <= 0.08,
        "roughness_median_0_70_to_0_78": 0.70 <= metrics["roughness"]["linear_p50"][0] <= 0.78,
    }
    report["status"] = "pass" if all(report["targets"].values()) else "tune_required"
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["status"] == "pass" else 2


if __name__ == "__main__":
    raise SystemExit(main())
