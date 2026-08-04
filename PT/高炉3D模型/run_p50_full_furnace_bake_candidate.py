"""Run the guarded P50 full-furnace UV and texture-bake candidate."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from datetime import datetime
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
BLENDER = Path(r"D:\Program Files\Blender Foundation\Blender 5.2\blender.exe")
DEFAULT_INPUT = (
    HERE
    / "work"
    / "P40_FIXED_LOOKDEV_20260717_P36_FINAL"
    / "P40_LOOKDEV_APPROVED.blend"
)
SOURCE = ROOT / "高炉前端数据" / "models" / "gl02_blast_furnace.glb"
SCRIPT = (
    HERE
    / "skills"
    / "bf3d-uv-bake"
    / "scripts"
    / "p50_full_furnace_bake_candidate.py"
)
EXPECTED_INPUT_SHA256 = "03635cf6608a54c4a671fb4d84adcb9451a36fe47cea7b564af2d4d3b69b2256"


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input-blend", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--blender", type=Path, default=BLENDER)
    parser.add_argument("--source-glb", type=Path, default=SOURCE)
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--texture-size", type=int, default=256)
    parser.add_argument("--margin", type=int, default=4)
    parser.add_argument("--samples", type=int, default=8)
    parser.add_argument("--render-size", type=int, default=640)
    parser.add_argument("--skip-render", action="store_true")
    args = parser.parse_args()
    input_blend = args.input_blend.resolve()
    blender = args.blender.resolve()
    source = args.source_glb.resolve()
    for path in (input_blend, blender, source, SCRIPT):
        if not path.is_file():
            raise FileNotFoundError(path)
    input_sha256 = sha256_file(input_blend)
    if input_sha256 != EXPECTED_INPUT_SHA256:
        raise RuntimeError(
            f"P50 input checkpoint lock mismatch: expected {EXPECTED_INPUT_SHA256}, got {input_sha256}"
        )
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output = (
        args.output_dir
        or HERE / "work" / f"P50_FULL_FURNACE_BAKE_{stamp}"
    ).resolve()
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
        "--texture-size",
        str(args.texture_size),
        "--margin",
        str(args.margin),
        "--samples",
        str(args.samples),
        "--render-size",
        str(args.render_size),
    ]
    if args.skip_render:
        command.append("--skip-render")
    print(
        json.dumps(
            {
                "command": command,
                "output_dir": str(output),
                "input_checkpoint_sha256": input_sha256,
                "production_glb_is_read_only": str(source),
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    completed = subprocess.run(command, cwd=ROOT, check=False)
    report_path = output / "p50_full_furnace_bake_candidate.json"
    if report_path.is_file():
        report = json.loads(report_path.read_text(encoding="utf-8"))
        print(
            json.dumps(
                {
                    "status": report.get("status"),
                    "report": str(report_path),
                    "candidate": report.get("candidate"),
                    "approval": report.get("approval"),
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        if report.get("status") != "candidate_ready_for_visual_review":
            return completed.returncode or 2
        return completed.returncode
    print(
        json.dumps(
            {
                "status": "fail",
                "reason": "Blender did not produce the required P50 report.",
                "blender_returncode": completed.returncode,
                "expected_report": str(report_path),
            },
            ensure_ascii=False,
            indent=2,
        ),
        file=sys.stderr,
    )
    return completed.returncode or 3


if __name__ == "__main__":
    sys.exit(main())
