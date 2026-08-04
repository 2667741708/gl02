"""Promote a visually reviewed Blender candidate to a named immutable checkpoint."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import bpy


def main() -> int:
    argv = sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else []
    parser = argparse.ArgumentParser()
    parser.add_argument("--expected-stage", required=True)
    parser.add_argument("--new-stage", required=True)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--review", required=True, type=Path)
    args = parser.parse_args(argv)
    scene = bpy.context.scene
    actual = str(scene.get("bf3d_stage", ""))
    if actual != args.expected_stage:
        raise RuntimeError(f"Expected stage {args.expected_stage!r}, got {actual!r}")
    if not args.review.resolve().is_file():
        raise FileNotFoundError(args.review.resolve())
    scene["bf3d_promoted_from_stage"] = actual
    scene["bf3d_stage"] = args.new_stage
    scene["bf3d_visual_review"] = str(args.review.resolve())
    scene["bf3d_visual_review_decision"] = "approve"
    output = args.output.resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    bpy.ops.wm.save_as_mainfile(filepath=str(output), check_existing=False)
    print(json.dumps({"status": "promoted", "from": actual, "to": args.new_stage, "output": str(output), "review": str(args.review.resolve())}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
