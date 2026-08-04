# -*- coding: utf-8 -*-
"""Read-only runtime probe before deploying the IMES MCP to 220.12."""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path


PROJECTS = (
    Path(r"F:\高炉炼铁项目-real-sensor-v2_V4_8093_PREVIEW"),
    Path(r"F:\高炉炼铁项目-real-sensor-v2_V3"),
)


def main() -> int:
    payload = {
        "python": sys.executable,
        "projects": [
            {
                "path": str(project),
                "exists": project.is_dir(),
                "assistant_dir": str(project / "高炉前端数据" / "智能助手"),
                "mcp_dir": str(project / "高炉前端数据" / "智能助手" / "mcp"),
                "mcp_exists": (project / "高炉前端数据" / "智能助手" / "mcp").is_dir(),
            }
            for project in PROJECTS
        ],
        "dependencies": {
            name: importlib.util.find_spec(name) is not None
            for name in ("mcp", "paramiko", "psycopg")
        },
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
