"""Verify the IMES FastMCP stdio tool schemas without querying the database."""

from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path
import sys

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


ROOT = Path(__file__).resolve().parents[1]
SERVER = (
    ROOT / "高炉前端数据" / "智能助手" / "mcp" / "imes_relay_mcp_server.py"
)
REQUIRED_TOOLS = {
    "list_imes_database_profiles",
    "list_imes_business_objects",
    "query_imes_variables",
    "query_imes_readonly_sql",
}


async def run() -> dict[str, object]:
    env = dict(os.environ)
    env.update({"PYTHONUTF8": "1", "MCP_TRANSPORT": "stdio"})
    params = StdioServerParameters(
        command=sys.executable,
        args=["-X", "utf8", str(SERVER)],
        env=env,
    )
    async with stdio_client(params) as streams:
        async with ClientSession(*streams) as session:
            await session.initialize()
            response = await session.list_tools()
            tools = {tool.name: tool for tool in response.tools}
            missing = sorted(REQUIRED_TOOLS - set(tools))
            variable_schema = tools["query_imes_variables"].inputSchema
            sql_schema = tools["query_imes_readonly_sql"].inputSchema
            profile_schema = tools["list_imes_business_objects"].inputSchema
            result = {
                "ok": not missing,
                "server": str(SERVER),
                "tool_count": len(tools),
                "required_tools": sorted(REQUIRED_TOOLS),
                "missing_tools": missing,
                "schemas": {
                    "query_imes_variables_has_account_profile": (
                        "account_profile"
                        in variable_schema.get("properties", {})
                    ),
                    "query_imes_variables_has_time_window": all(
                        key in variable_schema.get("properties", {})
                        for key in ("time_column", "start_time", "end_time")
                    ),
                    "query_imes_readonly_sql_has_parameters": (
                        "parameters" in sql_schema.get("properties", {})
                    ),
                    "query_imes_readonly_sql_has_row_limit": (
                        "row_limit" in sql_schema.get("properties", {})
                    ),
                    "list_objects_has_account_profile": (
                        "account_profile"
                        in profile_schema.get("properties", {})
                    ),
                },
            }
            result["ok"] = bool(result["ok"]) and all(
                result["schemas"].values()
            )
            return result


def main() -> int:
    result = asyncio.run(run())
    output = ROOT / "logs" / "imes_mcp_stdio_schema_smoke_20260727.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(result, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(json.dumps({**result, "output": str(output)}, ensure_ascii=False))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
