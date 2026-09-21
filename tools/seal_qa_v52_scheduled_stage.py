"""Seal the private V52 scheduled retest stage with an exact file allowlist."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


EXPECTED_FILES = ("worker.py", "batch.py", "collector.py", "plan.private.json", "summary.py", "start.ps1")


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stage", type=Path, required=True)
    args = parser.parse_args()
    stage = args.stage.resolve()
    missing = [name for name in EXPECTED_FILES if not (stage / name).is_file()]
    if missing:
        raise FileNotFoundError("missing sealed stage files: " + ", ".join(missing))
    manifest = {
        "schema": "bf.qa.v52-scheduled-stage-manifest.v1",
        "files": {name: sha(stage / name) for name in EXPECTED_FILES},
    }
    output = stage / "manifest.private.json"
    with output.open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(manifest, stream, ensure_ascii=False, indent=2)
        stream.write("\n")
    print(json.dumps({"ok": True, "manifest_sha256": sha(output), "file_count": len(EXPECTED_FILES)}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
