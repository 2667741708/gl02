"""Run the Blender 5.2 GL02 P00 import audit in a repeatable work folder."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_BLENDER = Path(r"D:\Program Files\Blender Foundation\Blender 5.2\blender.exe")
DEFAULT_INPUT = ROOT / "高炉前端数据" / "models" / "gl02_blast_furnace.glb"
BLENDER_SCRIPT = Path(__file__).resolve().parent / "skills" / "bf3d-geometry-audit" / "scripts" / "p00_import_audit.py"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Create a non-destructive Blender P00 checkpoint and audit.")
    parser.add_argument("--blender", type=Path, default=DEFAULT_BLENDER)
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--resolution", type=int, default=768)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    blender = args.blender.resolve()
    input_path = args.input.resolve()
    if not blender.is_file():
        raise FileNotFoundError(f"Blender executable not found: {blender}")
    if not input_path.is_file():
        raise FileNotFoundError(f"Input GLB not found: {input_path}")
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_dir = (args.output_dir or (Path(__file__).resolve().parent / "work" / f"P00_{stamp}")).resolve()
    output_dir.mkdir(parents=True, exist_ok=False)
    command = [
        str(blender),
        "--background",
        "--factory-startup",
        "--python",
        str(BLENDER_SCRIPT),
        "--",
        "--input",
        str(input_path),
        "--output-dir",
        str(output_dir),
        "--resolution",
        str(args.resolution),
    ]
    print(json.dumps({"command": command, "output_dir": str(output_dir)}, ensure_ascii=False, indent=2))
    completed = subprocess.run(command, cwd=ROOT, check=False)
    report_path = output_dir / "p00_scene_audit.json"
    if report_path.is_file():
        report = json.loads(report_path.read_text(encoding="utf-8"))
        print(
            json.dumps(
                {
                    "status": report.get("status"),
                    "report": str(report_path),
                    "checkpoint": report.get("checkpoint"),
                    "sensor_count": report.get("import_contract", {}).get("sensor_count"),
                    "max_sensor_position_error_m": report.get("import_contract", {}).get("max_sensor_position_error_m"),
                    "renders": len(report.get("renders", [])),
                },
                ensure_ascii=False,
                indent=2,
            )
        )
    elif completed.returncode != 0:
        failure_path = output_dir / "p00_failed.json"
        failure_path.write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "stage": "P00_SOURCE_LOCKED",
                    "status": "failed_before_audit_report",
                    "return_code": completed.returncode,
                    "command": command,
                    "note": "Inspect the Blender console traceback; the source GLB was opened read-only and was not overwritten.",
                },
                ensure_ascii=False,
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        print(json.dumps({"status": "failed", "failure_report": str(failure_path)}, ensure_ascii=False, indent=2))
    return completed.returncode


if __name__ == "__main__":
    sys.exit(main())
