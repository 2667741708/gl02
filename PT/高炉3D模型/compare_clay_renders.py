"""Compare two fixed GL02 clay-render sets using simple image statistics."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from PIL import Image, ImageChops, ImageStat


VIEWS = ("front", "back", "left", "right", "top")


def percentile(histogram: list[int], fraction: float) -> int:
    target = sum(histogram) * fraction
    cumulative = 0
    for value, count in enumerate(histogram):
        cumulative += count
        if cumulative >= target:
            return value
    return 255


def metrics(path: Path) -> dict[str, float | int | str]:
    image = Image.open(path).convert("L")
    stat = ImageStat.Stat(image)
    histogram = image.histogram()
    return {
        "path": str(path.resolve()),
        "width": image.width,
        "height": image.height,
        "mean_luma": round(float(stat.mean[0]), 4),
        "stddev_luma": round(float(stat.stddev[0]), 4),
        "p05": percentile(histogram, 0.05),
        "p50": percentile(histogram, 0.50),
        "p95": percentile(histogram, 0.95),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--baseline-dir", required=True, type=Path)
    parser.add_argument("--baseline-prefix", default="P00")
    parser.add_argument("--candidate-dir", required=True, type=Path)
    parser.add_argument("--candidate-prefix", default="P10")
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    report: dict[str, object] = {"schema_version": 1, "views": {}}
    for view in VIEWS:
        baseline_path = args.baseline_dir / f"{args.baseline_prefix}_{view}.png"
        candidate_path = args.candidate_dir / f"{args.candidate_prefix}_{view}.png"
        baseline = Image.open(baseline_path).convert("L")
        candidate = Image.open(candidate_path).convert("L")
        if baseline.size != candidate.size:
            raise ValueError(f"Image sizes differ for {view}: {baseline.size} vs {candidate.size}")
        difference = ImageChops.difference(baseline, candidate)
        report["views"][view] = {
            "baseline": metrics(baseline_path),
            "candidate": metrics(candidate_path),
            "mean_absolute_luma_difference": round(float(ImageStat.Stat(difference).mean[0]), 4),
        }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
