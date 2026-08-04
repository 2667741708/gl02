# -*- coding: utf-8 -*-
"""Run a read-only IMES MCP smoke test inside the 220.12 8093 project."""
from __future__ import annotations

import importlib.util
import json
import os
import sys
from pathlib import Path


ROOT = Path(r"F:\高炉炼铁项目-real-sensor-v2_V4_8093_PREVIEW")
MODULE_PATH = ROOT / "高炉前端数据" / "智能助手" / "mcp" / "imes_relay_mcp_server.py"


def main() -> int:
    os.environ["IMES_MCP_CONNECTION_MODE"] = "direct_22012"
    os.environ["IMES_RELAY_DB_HOST"] = "10.10.181.195"
    os.environ["IMES_RELAY_DB_PORT"] = "5432"
    spec = importlib.util.spec_from_file_location("imes_22012_remote_mcp", MODULE_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    status = module.imes_relay_status()
    query = module.query_imes_object("public.t_ipes_out_put", "2026-05-01", "2026-05-01", 3)
    sql_query = module.query_imes_readonly_sql(
        "SELECT COUNT(*) AS row_count FROM public.t_ipes_out_put"
    )
    semantic = module.resolve_imes_natural_language("查一下2号炉昨天每炉出了多少铁")
    payload = {
        "status_ok": status.get("ok"),
        "connection_mode": status.get("connection_mode"),
        "catalog_objects": status.get("catalog_objects"),
        "query_ok": query.get("ok"),
        "object": query.get("object"),
        "row_count": len(query.get("rows", [])),
        "fields": list(query["rows"][0]) if query.get("rows") else [],
        "arbitrary_readonly_sql_ok": sql_query.get("ok"),
        "production_output_total_rows": sql_query.get("rows", [{}])[0].get("row_count"),
        "semantic_object": semantic.get("resolved_object"),
        "semantic_field": semantic.get("matched_fields", [{}])[0].get("field") if semantic.get("matched_fields") else None,
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0 if payload["status_ok"] and payload["query_ok"] and payload["arbitrary_readonly_sql_ok"] and payload["semantic_object"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
