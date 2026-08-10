"""Verify the active 220.12 GL02 MCP exposes and can call the report tool."""
from __future__ import annotations

import asyncio
import importlib.util
import json
import sys
from pathlib import Path


def main() -> int:
    root = Path.cwd()
    mcp_dir = next(root.rglob("bf_data_mcp_server.py"))
    sys.path.insert(0, str(mcp_dir.parent))
    backend = next(path for path in root.rglob("assistant_pg.py") if "backend" in path.parts)
    sys.path.insert(0, str(backend.parent))
    spec = importlib.util.spec_from_file_location("bf_data_mcp_runtime", mcp_dir)
    if not spec or not spec.loader:
        raise RuntimeError("cannot load GL02 MCP module")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    tools = asyncio.run(module.mcp.list_tools())
    names = [tool.name for tool in tools]
    result = module.query_bf2_operation_log_report("2026-08-08", 2)
    print(json.dumps({"ok": result.get("ok"), "tool_present": "query_bf2_operation_log_report" in names, "rows_count": result.get("rows_count"), "tool_count": len(names), "result": result}, ensure_ascii=False, default=str))
    if not result.get("ok") or "query_bf2_operation_log_report" not in names:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
