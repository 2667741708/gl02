"""Run the Blender P30 shell material candidate."""

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
SCRIPT = HERE / "skills" / "bf3d-industrial-materials" / "scripts" / "p30_shell_material_candidate.py"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input-blend", required=True, type=Path)
    parser.add_argument("--blender", type=Path, default=BLENDER)
    parser.add_argument("--source-glb", type=Path, default=SOURCE)
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--resolution", type=int, default=768)
    args = parser.parse_args()
    input_blend = args.input_blend.resolve()
    blender = args.blender.resolve()
    source = args.source_glb.resolve()
    for path in (input_blend, blender, source, SCRIPT):
        if not path.is_file():
            raise FileNotFoundError(path)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output = (args.output_dir or HERE / "work" / f"P30_SHELL_MATERIAL_{stamp}").resolve()
    output.mkdir(parents=True, exist_ok=False)
    command = [
        str(blender),
        "--background",
        str(input_blend),
        "--python",
        str(SCRIPT),
        "--",
        "--source-glb",
        str(source),
        "--output-dir",
        str(output),
        "--resolution",
        str(args.resolution),
    ]
    print(json.dumps({"command": command, "output_dir": str(output)}, ensure_ascii=False, indent=2))
    completed = subprocess.run(command, cwd=ROOT, check=False)
    report_path = output / "p30_shell_material_candidate.json"
    if report_path.is_file():
        report = json.loads(report_path.read_text(encoding="utf-8"))
        print(json.dumps({"status": report.get("status"), "report": str(report_path), "candidate": report.get("candidate"), "approval": report.get("approval")}, ensure_ascii=False, indent=2))
    return completed.returncode


if __name__ == "__main__":
    sys.exit(main())
