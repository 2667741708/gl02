"""Read-only GL02 MCP catalog/data probe for top temperature/pressure A-D points."""
from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from pathlib import Path


PRESSURE = [f"P_top_{letter}" for letter in "ABCD"]
TEMPERATURE = [f"T_top_{letter}" for letter in "ABCD"]


def load_module(project_root: Path):
    mcp_dir = project_root / "高炉前端数据" / "智能助手" / "mcp"
    sys.path.insert(0, str(mcp_dir))
    module_path = mcp_dir / "bf_data_mcp_server.py"
    spec = importlib.util.spec_from_file_location("bf_data_mcp_server_probe", module_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Unable to load MCP module: {module_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", required=True)
    args = parser.parse_args()
    module = load_module(Path(args.root))

    searches = {
        term: module.search_variables(term, limit=4)
        for term in ("顶温A", "顶温A、B、C、D", "顶压A", "顶压A、B、C、D", "A点顶温", "A点顶压")
    }
    resolved = {}
    for term in ("顶温A", "顶压A", "A点顶温", "A点顶压"):
        try:
            item = module.resolve_variable(term)
            resolved[term] = {
                "ok": True,
                "variable_name": item.get("variable_name"),
                "point_id": item.get("point_id") or item.get("tag_long_name"),
            }
        except Exception as exc:  # noqa: BLE001
            resolved[term] = {"ok": False, "error": f"{type(exc).__name__}: {exc}"}

    query = module.query_gl02_sensors(PRESSURE + TEMPERATURE, query_type="latest", source_preference="database")
    compact_items = []
    for item in query.get("items") or []:
        variable = item.get("variable") or {}
        latest = item.get("latest") or {}
        compact_items.append(
            {
                "requested_variable": item.get("requested_variable"),
                "ok": item.get("ok"),
                "variable_name": variable.get("variable_name"),
                "point_id": variable.get("point_id") or variable.get("tag_long_name"),
                "value_present": latest.get("value") is not None,
                "data_time": latest.get("data_time") or latest.get("timestamp"),
                "error": item.get("error"),
            }
        )
    payload = {
        "ok": True,
        "searches": searches,
        "resolved": resolved,
        "query": {
            "ok": query.get("ok"),
            "variable_count": query.get("variable_count"),
            "items": compact_items,
        },
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
