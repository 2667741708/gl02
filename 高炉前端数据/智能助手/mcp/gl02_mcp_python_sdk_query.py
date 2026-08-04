from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import importlib.util


SCRIPT_DIR = Path(__file__).resolve().parent
MCP_SERVER_PATH = SCRIPT_DIR / "bf_data_mcp_server.py"


def load_mcp_module() -> Any:
    spec = importlib.util.spec_from_file_location("bf_data_mcp_server_cli", MCP_SERVER_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Cannot load MCP server module: {MCP_SERVER_PATH}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def print_json(payload: Any) -> None:
    print(json.dumps(payload, ensure_ascii=False, indent=2, default=str))


def main() -> None:
    parser = argparse.ArgumentParser(description="GL02 MCP local Python query helper.")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("latest", help="Query latest GL02 value.")
    p.add_argument("--variable", required=True)

    p = sub.add_parser("info", help="Query GL02 variable metadata.")
    p.add_argument("--variable", required=True)

    p = sub.add_parser("search", help="Search GL02 variables.")
    p.add_argument("--keyword", required=True)
    p.add_argument("--limit", default=10)

    p = sub.add_parser("history", help="Query GL02 1min history.")
    p.add_argument("--variable", required=True)
    p.add_argument("--start", required=True)
    p.add_argument("--end", required=True)
    p.add_argument("--limit", default=500)

    p = sub.add_parser("stats", help="Query GL02 statistics.")
    p.add_argument("--variable", required=True)
    p.add_argument("--start", required=True)
    p.add_argument("--end", required=True)
    p.add_argument("--agg", default="avg")

    p = sub.add_parser("features", help="Query GL02 feature statistics with baseline and Z metrics.")
    p.add_argument("--variable", required=True)
    p.add_argument("--start", required=True)
    p.add_argument("--end", required=True)
    p.add_argument("--baseline-day", default="")
    p.add_argument("--baseline-days", default=30)
    p.add_argument("--max-points", default=5000)

    p = sub.add_parser("reports", help="List reports.")
    p.add_argument("--report-type", default="")
    p.add_argument("--start-date", default="")
    p.add_argument("--end-date", default="")
    p.add_argument("--limit", default=20)

    p = sub.add_parser("read-report", help="Read report excerpt.")
    p.add_argument("--report-path", required=True)
    p.add_argument("--mode", default="excerpt")
    p.add_argument("--max-chars", default=1000)

    p = sub.add_parser("search-qa", help="Search QA messages.")
    p.add_argument("--keyword", required=True)
    p.add_argument("--limit", default=20)

    p = sub.add_parser("snapshot", help="Get latest furnace snapshot.")

    args = parser.parse_args()
    mcp = load_mcp_module()

    if args.command == "latest":
        result = mcp.get_latest_gl02_value(args.variable)
    elif args.command == "info":
        result = mcp.get_gl02_variable_info(args.variable)
    elif args.command == "search":
        result = mcp.find_gl02_variables(args.keyword, args.limit)
    elif args.command == "history":
        result = mcp.query_gl02_history(args.variable, args.start, args.end, args.limit)
    elif args.command == "stats":
        result = mcp.query_gl02_statistics(args.variable, args.start, args.end, args.agg)
    elif args.command == "features":
        result = mcp.query_gl02_feature_statistics(
            args.variable,
            args.start,
            args.end,
            baseline_day=args.baseline_day,
            baseline_days=int(args.baseline_days),
            max_points=int(args.max_points),
        )
    elif args.command == "reports":
        result = mcp.list_recent_reports(args.report_type, args.start_date, args.end_date, args.limit)
    elif args.command == "read-report":
        result = mcp.read_report_excerpt(args.report_path, args.mode, args.max_chars)
    elif args.command == "search-qa":
        result = mcp.search_qa_messages(args.keyword, args.limit)
    elif args.command == "snapshot":
        result = mcp.get_latest_furnace_snapshot()
    else:
        raise RuntimeError(f"Unhandled command: {args.command}")

    print_json(result)


if __name__ == "__main__":
    main()
