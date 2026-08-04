"""Run the single-variable GL02 P10 shell-normal candidate."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
DEFAULT_BLENDER = Path(r"D:\Program Files\Blender Foundation\Blender 5.2\blender.exe")
DEFAULT_SOURCE = ROOT / "高炉前端数据" / "models" / "gl02_blast_furnace.glb"
SCRIPT = HERE / "skills" / "bf3d-geometry-audit" / "scripts" / "p10_normals_candidate.py"


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description="Create and render a P10 shell-normal candidate.")
    result.add_argument("--blender", type=Path, default=DEFAULT_BLENDER)
    result.add_argument("--input-blend", required=True, type=Path)
    result.add_argument("--source-glb", type=Path, default=DEFAULT_SOURCE)
    result.add_argument("--output-dir", type=Path)
    result.add_argument("--resolution", type=int, default=768)
    return result


def main() -> int:
    args = parser().parse_args()
    blender = args.blender.resolve()
    input_blend = args.input_blend.resolve()
    source_glb = args.source_glb.resolve()
    for path in (blender, input_blend, source_glb, SCRIPT):
        if not path.is_file():
            raise FileNotFoundError(path)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_dir = (args.output_dir or HERE / "work" / f"P10_NORMALS_{stamp}").resolve()
    output_dir.mkdir(parents=True, exist_ok=False)
    command = [
        str(blender), "--background", str(input_blend), "--python", str(SCRIPT), "--",
        "--source-glb", str(source_glb), "--output-dir", str(output_dir), "--resolution", str(args.resolution),
    ]
    print(json.dumps({"command": command, "output_dir": str(output_dir)}, ensure_ascii=False, indent=2))
    completed = subprocess.run(command, cwd=ROOT, check=False)
    report_path = output_dir / "p10_normals_candidate.json"
    if report_path.is_file():
        report = json.loads(report_path.read_text(encoding="utf-8"))
        print(json.dumps({"status": report.get("status"), "report": str(report_path), "candidate": report.get("candidate"), "approval": report.get("approval")}, ensure_ascii=False, indent=2))
    return completed.returncode


if __name__ == "__main__":
    sys.exit(main())
