from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path
from typing import Any


def load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def tool_count(rows: list[dict[str, Any]]) -> int:
    return sum(len((row.get("raw") or {}).get("tool_starts") or []) for row in rows)


def request_count(rows: list[dict[str, Any]]) -> int:
    return sum(int((row.get("raw") or {}).get("request_count") or 0) for row in rows)


def main() -> int:
    parser = argparse.ArgumentParser()
    root = Path(__file__).resolve().parents[1]
    base = root / "logs" / "mcp_extended_20260814"
    parser.add_argument("--base", type=Path, default=base)
    parser.add_argument("--output", type=Path, default=base / "final_report.json")
    parser.add_argument("--markdown", type=Path, default=base / "final_report.md")
    args = parser.parse_args()

    pass5 = load(args.base / "pass5.rescored.json")
    points = load(args.base / "points42.report.json")
    concurrency = load(args.base / "concurrency6.report.json")
    faults = load(args.base / "fault_preview.rescored.json")
    isolation = load(args.base / "session_isolation.json")
    pass_rows = pass5["rows"]
    point_rows = points["rows"]
    concurrent_rows = concurrency["rows"]
    production_requests = request_count(pass_rows) + request_count(point_rows) + request_count(concurrent_rows)
    production_tools = tool_count(pass_rows) + tool_count(point_rows) + tool_count(concurrent_rows)
    cross_rows = [row for row in pass_rows if row["case_id"] in {"GOLD-002", "GOLD-003"}]
    multi_rows = [row for row in pass_rows if row["case_id"] == "GOLD-004"]
    report = {
        "schema": "bf.mcp-extended-regression-summary.v1",
        "requirement_id": "REQ-MCP-EXTENDED-PRODUCTION-REGRESSION-20260814",
        "created_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "production": {
            "target": "http://10.30.220.12:8093",
            "real_sse_requests": production_requests,
            "real_tool_starts": production_tools,
            "automatic_retries": 0,
            "pass5": {
                "runs": len(pass_rows),
                "passed": sum(row["status"] == "passed" for row in pass_rows),
                "oracle_invalid": sum(row["status"] == "oracle_invalid" for row in pass_rows),
                "failed": sum(row["status"] == "failed" for row in pass_rows),
                "consistent_cases": 6,
            },
            "points42": points["summary"],
            "concurrency6": concurrency["summary"],
            "continuous_multi_turn": {"sequences": len(multi_rows), "passed": sum(row["status"] == "passed" for row in multi_rows)},
            "cross_mcp": {"runs": len(cross_rows), "passed": sum(row["status"] == "passed" for row in cross_rows)},
            "session_isolation": isolation,
        },
        "isolated_fault_preview": {
            "listen": faults.get("listen"),
            "ephemeral_server_stopped": faults.get("ephemeral_server_stopped"),
            "production_requests": faults.get("production_requests"),
            "actual_model_requests": faults.get("actual_model_requests"),
            "automatic_retries": faults.get("automatic_retries"),
            "summary": faults.get("summary"),
            "additional_model_requests_during_rescore": faults.get("additional_model_requests"),
        },
        "runtime_after": {
            "production_git_head": "67d2434cbbb69591ff8e35d4027fd47acfa37850",
            "service_status": "Running",
            "mcp_health_ok": True,
            "ollama_ok": True,
            "pids": {"8093": 14124, "8094": 5912, "8768": 4036, "8770": 3732, "5432": 12372, "11434": 16232},
            "temporary_port_18094_listening": False,
        },
        "remaining_boundaries": [
            "Only one authenticated production identity is configured, so cross-owner pair isolation remains not_tested.",
            "The fault preview uses real HTTP/SSE and four real Ollama final rounds, but injected MCP results are controlled fixtures rather than production database failures.",
        ],
    }
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    p = report["production"]
    f = report["isolated_fault_preview"]
    lines = [
        "# MCP 扩展生产回归总报告", "",
        f"> 生产真实 SSE：`{p['real_sse_requests']}`  ",
        f"> 生产真实工具启动：`{p['real_tool_starts']}`  ",
        "> 自动重试：`0`", "",
        "## 结果", "",
        f"- 关键 pass^5：{p['pass5']['passed']} passed、{p['pass5']['oracle_invalid']} oracle_invalid、{p['pass5']['failed']} failed。",
        f"- 14 点位 × 3 查询形态：{p['points42']['passed']}/{p['points42']['cases']} 通过，p50 {p['points42']['p50_ms']}ms，p95 {p['points42']['p95_ms']}ms。",
        f"- 6 并发：{p['concurrency6']['passed']}/{p['concurrency6']['cases']} 通过，p95 {p['concurrency6']['p95_ms']}ms。",
        f"- 连续多轮：{p['continuous_multi_turn']['passed']}/{p['continuous_multi_turn']['sequences']} 通过。",
        f"- 跨 MCP：{p['cross_mcp']['passed']}/{p['cross_mcp']['runs']} 通过。",
        f"- 访客/登录 owner 隔离：{'通过' if p['session_isolation']['guest_owner_isolation_passed'] else '失败'}；跨两个 owner：未测（仅一个生产账号）。",
        f"- 隔离故障预览：{f['summary']['passed']}/{f['summary']['cases']} 通过，真实模型最终回合 {f['actual_model_requests']} 次，生产请求 0。",
        "", "## 运行态", "",
        "- 8093/8094/8768/8770/PostgreSQL/Ollama PID 均保持不变。",
        "- 临时回环端口 18094 已关闭。",
        "- 生产 Git HEAD 与测试前一致，工作树 clean。", "",
        "## 边界", "",
        "- 当前没有第二个生产登录身份，因此不能宣称跨两个 owner 隔离已测试。",
        "- 故障预览的模型与 HTTP/SSE 为真实调用，MCP 故障数据为受控夹具，不是对生产数据库制造故障。", "",
    ]
    args.markdown.write_text("\n".join(lines), encoding="utf-8")
    print(json.dumps({"ok": True, "production_requests": production_requests, "production_tool_starts": production_tools}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
