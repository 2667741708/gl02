#!/usr/bin/env python3
"""Run remote_22012_exec.py with the repository-local dependency bundle."""

from __future__ import annotations

import runpy
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
LOCAL_DEPS = ROOT / ".tmp_pylibs"
if LOCAL_DEPS.is_dir():
    sys.path.insert(0, str(LOCAL_DEPS))


def pop_local_log_argument() -> Path | None:
    if "--local-log" not in sys.argv:
        return None
    index = sys.argv.index("--local-log")
    try:
        value = sys.argv[index + 1]
    except IndexError as exc:
        raise SystemExit("--local-log requires a repository-relative path") from exc
    del sys.argv[index : index + 2]
    target = (ROOT / value).resolve()
    if ROOT.resolve() not in target.parents:
        raise SystemExit("--local-log must stay inside the repository")
    return target


local_log = pop_local_log_argument()
stream = None
if local_log is not None:
    local_log.parent.mkdir(parents=True, exist_ok=True)
    stream = local_log.open("w", encoding="utf-8")
    sys.stdout = stream
    sys.stderr = stream

try:
    runpy.run_path(str(ROOT / "tools" / "remote_22012_exec.py"), run_name="__main__")
finally:
    if stream is not None:
        stream.flush()
        stream.close()
