"""Run the Blender P36 non-destructive L7-L16 segmentation candidate."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
BLENDER = Path(r"D:\Program Files\Blender Foundation\Blender 5.2\blender.exe")
SOURCE = ROOT / "高炉前端数据" / "models" / "gl02_blast_furnace.glb"
PROFILE = Path(r"D:\文件\pythonCAD\input\furnace_profile.gl02.yaml")
SENSOR_LAYOUT = Path(r"D:\文件\pythonCAD\input\sensor_layout.gl02.115.yaml")
SCRIPT = HERE / "skills" / "bf3d-geometry-audit" / "scripts" / "p36_layer_segmentation_candidate.py"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input-blend", required=True, type=Path)
    parser.add_argument("--blender", type=Path, default=BLENDER)
    parser.add_argument("--source-glb", type=Path, default=SOURCE)
    parser.add_argument("--profile-yaml", type=Path, default=PROFILE)
    parser.add_argument("--sensor-layout-yaml", type=Path, default=SENSOR_LAYOUT)
    parser.add_argument("--segments", type=int, default=64)
    parser.add_argument("--offset-m", type=float, default=0.06)
    parser.add_argument("--preview-resolution", type=int, default=960)
    parser.add_argument("--skip-preview", action="store_true")
    parser.add_argument("--output-dir", type=Path)
    args = parser.parse_args()

    paths = {
        "input_blend": args.input_blend.resolve(),
        "blender": args.blender.resolve(),
        "source_glb": args.source_glb.resolve(),
        "profile_yaml": args.profile_yaml.resolve(),
        "sensor_layout_yaml": args.sensor_layout_yaml.resolve(),
        "script": SCRIPT.resolve(),
    }
    for label, path in paths.items():
        if not path.is_file():
            raise FileNotFoundError(f"{label}: {path}")
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output = (
        args.output_dir or HERE / "work" / f"P36_LAYER_SEGMENTATION_{stamp}"
    ).resolve()
    output.mkdir(parents=True, exist_ok=False)
    command = [
        str(paths["blender"]),
        "--background",
        str(paths["input_blend"]),
        "--python",
        str(paths["script"]),
        "--",
        "--source-glb",
        str(paths["source_glb"]),
        "--profile-yaml",
        str(paths["profile_yaml"]),
        "--sensor-layout-yaml",
        str(paths["sensor_layout_yaml"]),
        "--output-dir",
        str(output),
        "--segments",
        str(args.segments),
        "--offset-m",
        str(args.offset_m),
        "--preview-resolution",
        str(args.preview_resolution),
    ]
    if args.skip_preview:
        command.append("--skip-preview")
    print(json.dumps({"command": command, "output_dir": str(output)}, ensure_ascii=False, indent=2))
    completed = subprocess.run(command, cwd=ROOT, check=False)
    report = output / "p36_layer_segmentation_candidate.json"
    if report.is_file():
        data = json.loads(report.read_text(encoding="utf-8"))
        print(
            json.dumps(
                {
                    "status": data.get("status"),
                    "report": str(report),
                    "candidate": data.get("candidate"),
                    "structural_smoke_glb": data.get("structural_smoke_glb"),
                    "review": data.get("review"),
                    "performance": data.get("performance"),
                },
                ensure_ascii=False,
                indent=2,
            )
        )
    return completed.returncode


if __name__ == "__main__":
    sys.exit(main())
