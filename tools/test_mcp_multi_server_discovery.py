"""List the tools exposed by the same on-demand multi-MCP host used by QA."""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BACKEND_DIR = ROOT / "高炉前端数据" / "智能助手" / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from mcp_host import McpClientManager, load_server_registry, select_mcp_servers  # noqa: E402


DEFAULT_REGISTRY = BACKEND_DIR / "mcp_host" / "server_registry.json"


async def discover(
    question: str, registry_path: Path, all_servers: bool = False
) -> dict[str, object]:
    registry = load_server_registry(registry_path)
    selection = select_mcp_servers(question, registry)
    if all_servers:
        selection = type(selection)(
            tuple(item.server_id for item in registry.enabled_servers()),
            ("all_enabled",),
            ("命令行显式要求加载全部启用MCP服务",),
        )
    manager = McpClientManager(registry, sys.executable)
    async with manager:
        bindings = await manager.attach(selection.server_ids)
        return {
            "ok": not manager.errors,
            "question": question,
            "selected_servers": list(selection.server_ids),
            "matched_domains": list(selection.matched_domains),
            "reasons": list(selection.reasons),
            "server_errors": manager.errors,
            "tool_count": len(bindings),
            "tools": [
                {
                    "exposed_name": item.exposed_name,
                    "native_name": item.native_name,
                    "server_id": item.server_id,
                    "required_arguments": list(item.input_schema.get("required") or []),
                }
                for item in bindings
            ],
        }


def main() -> int:
    parser = argparse.ArgumentParser(description="验证8093按需多MCP服务选择和工具命名空间。")
    parser.add_argument(
        "--question",
        default="当前属于第几个炉次？上一个炉次铁水的硅含量平均值是多少？",
    )
    parser.add_argument("--registry", type=Path, default=DEFAULT_REGISTRY)
    parser.add_argument("--all", action="store_true", help="加载注册表中全部启用的MCP服务")
    args = parser.parse_args()
    result = asyncio.run(discover(args.question, args.registry.resolve(), args.all))
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
