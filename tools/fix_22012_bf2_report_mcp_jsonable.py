from __future__ import annotations

import shutil
from pathlib import Path


def main() -> int:
    path = next(Path.cwd().rglob("bf_data_mcp_server.py"))
    text = path.read_text(encoding="utf-8")
    old = "{key: plain(value) for key, value in dict(row).items()}"
    new = "{key: jsonable(value) for key, value in dict(row).items()}"
    if old not in text:
        print("already_fixed_or_marker_missing")
        return 0
    backup = path.with_name(path.name + ".bak_report_mcp_jsonable_20260808")
    shutil.copy2(path, backup)
    path.write_text(text.replace(old, new, 1), encoding="utf-8")
    print(f"fixed={path}")
    print(f"backup={backup}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

