from __future__ import annotations

import argparse
from pathlib import Path

from huggingface_hub import snapshot_download


def main() -> int:
    parser = argparse.ArgumentParser(description="Download an auditable Hugging Face model snapshot for offline deployment.")
    parser.add_argument("--repo-id", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--revision", default="main")
    parser.add_argument("--max-workers", type=int, default=4)
    args = parser.parse_args()
    output = Path(args.output).resolve()
    output.mkdir(parents=True, exist_ok=True)
    path = snapshot_download(
        repo_id=args.repo_id,
        revision=args.revision,
        local_dir=str(output),
        max_workers=args.max_workers,
    )
    files = [item for item in output.rglob("*") if item.is_file()]
    total_bytes = sum(item.stat().st_size for item in files)
    print(f"SNAPSHOT {path} files={len(files)} bytes={total_bytes}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
