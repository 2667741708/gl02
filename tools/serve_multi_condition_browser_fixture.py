#!/usr/bin/env python3
"""Serve the V3 page with a synthetic WebSocket fixture for browser checks."""

from __future__ import annotations

import argparse
import json
import time
from datetime import datetime, timedelta
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_WEB_ROOT = ROOT / "高炉前端数据"
FIXTURE_PATH = ROOT / "tests" / "fixtures" / "multi_condition_browser_fixture.js"
TARGET_PAGE = "/frontend_dashboard_v3.server.html"

CORE_FIXTURE_VARIABLES = (
    ("P_top_gas_A", "顶压A点", "kPa", 178.2, 0.4, 177.0),
    ("P_top_gas_B", "顶压B点", "kPa", 179.1, 0.5, 177.5),
    ("P_top_gas_C", "顶压C点", "kPa", 177.8, -0.2, 177.0),
    ("P_top_gas_D", "顶压D点", "kPa", 178.5, 0.1, 177.2),
    ("T_top_A", "顶温A点", "℃", 153.0, -5.0, 162.0),
    ("T_top_B", "顶温B点", "℃", 155.0, -4.0, 161.0),
    ("T_top_C", "顶温C点", "℃", 156.0, -3.0, 160.0),
    ("T_top_D", "顶温D点", "℃", 157.0, -4.0, 161.0),
    ("P_top", "综合顶压", "kPa", 180.0, 0.8, 178.0),
    ("T_top", "综合顶温", "℃", 155.25, -4.0, 161.0),
    ("Q_blast", "冷风流量", "m³/min", 3650.0, 30.0, 3600.0),
    ("P_blast_cold", "冷风压力", "kPa", 390.0, 3.0, 388.0),
    ("P_blast", "热风压力", "kPa", 380.0, -2.0, 385.0),
    ("T_blast", "热风温度", "℃", 1168.0, -6.0, 1185.0),
    ("PI", "透气性指数", "m³/(min·kPa)", 1.24, 0.04, 1.11),
    ("DP_total", "全炉压差", "kPa", 163.0, 3.0, 158.0),
    ("DP_upper", "上部压差", "kPa", 75.0, 1.2, 72.0),
    ("DP_lower", "下部压差", "kPa", 88.0, 1.8, 86.0),
    ("GasUtil", "煤气利用率", "%", 47.2, -0.9, 50.0),
)


def build_core_fixture_evidence() -> list[dict[str, Any]]:
    """Return 19 deterministic read-only series for browser layout checks."""
    end = datetime.fromisoformat("2026-08-05T13:05:00+08:00")
    selected = {"T_top_A", "T_top_B", "P_blast", "GasUtil"}
    rows: list[dict[str, Any]] = []
    for variable, display_name, unit, current, delta, baseline in CORE_FIXTURE_VARIABLES:
        series = [
            {
                "ts": (end - timedelta(minutes=(12 - index) * 5)).isoformat(),
                "value": round(current - delta * ((12 - index) / 3), 4),
            }
            for index in range(13)
        ]
        values = [float(point["value"]) for point in series]
        rows.append(
            {
                "id": variable,
                "display_name": display_name,
                "unit": unit,
                "current_value": current,
                "delta_5m": delta,
                "delta_5m_pct": round(delta / abs(current - delta) * 100, 2),
                "direction_5m": "rising" if delta > 0 else "falling" if delta < 0 else "stable",
                "mean_60m": round(sum(values) / len(values), 4),
                "min_60m": min(values),
                "max_60m": max(values),
                "baseline_median_30d": baseline,
                "sample_count_60m": len(series),
                "series_60m": series,
                "series_window_minutes": 60,
                "value_source": "derived_mean_T_top_A_D" if variable == "T_top" else "direct_sensor",
                "selected_rule_evidence": variable in selected,
                "read_only": True,
            }
        )
    return rows


class FixtureHandler(SimpleHTTPRequestHandler):
    def __init__(self, *args: Any, directory: str, page_source: Path | None = None, **kwargs: Any) -> None:
        self.page_source = page_source
        super().__init__(*args, directory=directory, **kwargs)

    def do_GET(self) -> None:  # noqa: N802
        path = self.path.split("?", 1)[0]
        if path == "/favicon.ico":
            self.send_response(204)
            self.end_headers()
            return
        if path == "/api/automation/status":
            self.send_json({"ok": True, "database_ok": True, "fixture": True})
            return
        if path == "/api/short-window/summaries":
            self.send_json({"ok": True, "items": [], "fixture": True})
            return
        if path == "/api/short-window/conversations":
            self.send_json({"ok": True, "items": [], "fixture": True})
            return
        if path == "/api/diagnosis-review-context":
            self.send_json(
                {
                    "ok": True,
                    "enabled": True,
                    "context": {
                        "available": True,
                        "snapshot_id": "browser-fixture-1305",
                        "snapshot_source": "local_fixture",
                        "diagnosis_ts": "2026-08-05T13:05:00+08:00",
                        "main_label": "cold",
                        "main_display_label": "热制度下行",
                        "raw_scores": {
                            "normal": 42,
                            "lowline": 72,
                            "edge": 68,
                            "center": 31,
                            "channel": 46,
                            "cold": 84,
                            "hot": 19,
                            "column": 38,
                        },
                    },
                    "auth": {
                        "authenticated": False,
                        "can_submit": True,
                        "login_required": False,
                        "identity_mode": "onsite_anonymous",
                    },
                    "review_storage": {"configured": True, "writable": True},
                }
            )
            return
        if path == "/api/diagnosis-core-evidence":
            from urllib.parse import parse_qs, urlparse

            label = str(
                (parse_qs(urlparse(self.path).query).get("label") or ["cold"])[0]
            )
            rows = build_core_fixture_evidence()
            self.send_json(
                {
                    "ok": True,
                    "enabled": True,
                    "evidence": {
                        "schema_version": "diagnosis_core_evidence.v1",
                        "state": "available",
                        "target_label": label,
                        "diagnosis_ts": "2026-08-05T13:05:00+08:00",
                        "bucket_ts": "2026-08-05T13:05:00+08:00",
                        "bucket_minutes": 5,
                        "core_variable_count": 19,
                        "core_series_window_minutes": 60,
                        "core_variable_evidence": rows,
                        "read_only": True,
                    },
                }
            )
            return
        if path == "/api/diagnosis-ai-analysis":
            from urllib.parse import parse_qs, urlparse

            label = str((parse_qs(urlparse(self.path).query).get("label") or ["cold"])[0])
            names = {
                "normal": "正常顺行", "lowline": "低料线", "edge": "边缘煤气流发展",
                "center": "边缘不足/中心过吹", "channel": "管道行程",
                "cold": "热制度下行", "hot": "热制度上行", "column": "崩滑料/悬料",
            }
            scores = {"normal": 42, "lowline": 72, "edge": 68, "center": 31, "channel": 46, "cold": 84, "hot": 19, "column": 38}
            self.send_json(
                {
                    "ok": True,
                    "enabled": True,
                    "analysis": {
                        "schema_version": "diagnosis_ai_analysis.v4",
                        "state": "completed",
                        "target_label": label,
                        "target_display_name": names.get(label, label),
                        "diagnosis_ts": "2026-08-05T13:05:00+08:00",
                        "bucket_ts": "2026-08-05T13:05:00+08:00",
                        "bucket_minutes": 5,
                        "main_label": "cold",
                        "main_display_name": "热制度下行",
                        "rule_score": scores.get(label, 0),
                        "analysis": {
                            "label": label,
                            "display_name": names.get(label, label),
                            "verdict": "supported" if label == "cold" else "possible",
                            "model_support_score": 91 if label == "cold" else 74,
                            "summary": f"智能助手对{names.get(label, label)}的当前5分钟判断：规则分与最近趋势基本一致。",
                            "score_explanation": "炉顶温度当前153℃，近5分钟比前5分钟下降5℃，30天基线中位数162℃；热风压力也低于基线，这些信号共同把热制度下行分数推高。",
                            "supporting_evidence": ["当前规则符合度与诊断证据方向一致"],
                            "contradicting_evidence": [] if label == "cold" else ["该炉况不是当前主诊断"],
                            "attention_items": ["下一5分钟继续观察压差与煤气利用率"],
                            "data_limits": ["本页为浏览器固定场景，不代表生产数据"],
                            "guidance_summary": "先核对顶温、风压和煤气利用率是否继续同向变化，再按小幅、分步、观察反馈原则处理。",
                            "variable_evidence": [
                                {
                                    "driver_id": "cold.top-temperature-down",
                                    "name": "顶温下降趋势",
                                    "signal_state": "supporting",
                                    "configured_weight": 20,
                                    "colloquial_evidence": "炉顶温度当前153℃；近5分钟比前5分钟下降5℃；30天基线中位数162℃；规则特征已进入支持区间。",
                                    "variables": [
                                        {
                                            "display_name": "炉顶温度A",
                                            "unit": "℃",
                                            "current_value": 153,
                                            "delta_5m": -5,
                                            "baseline_median_30d": 162,
                                        }
                                    ],
                                }
                            ],
                            "core_variable_count": 19,
                            "core_series_window_minutes": 60,
                            "core_variable_evidence": build_core_fixture_evidence(),
                            "recommendation_basis": {
                                "available": True,
                                "goal": "先稳定炉况，再核对热量输入。",
                                "scope": "active" if label == "cold" else "hypothetical",
                                "safety_gate_passed": True,
                                "actions": [
                                    {
                                        "id": "FIXTURE-COLD-OBSERVE",
                                        "name": "核对热量输入并分步观察",
                                        "text": "先核对风温、喷煤和富氧条件，任何调整均须现场确认。",
                                        "status": "manual_confirm",
                                        "delta": None,
                                        "observation_window": {"min_minutes": 5, "max_minutes": 10, "basis": "观察顶温、压差和料速"},
                                        "blocking_reasons": [],
                                        "missing_inputs": [],
                                        "source_refs": ["5.3.5"],
                                    }
                                ],
                            },
                            "knowledge_basis": {
                                "available": True,
                                "evidence": [
                                    {
                                        "title": "三规二制热制度调剂依据",
                                        "knowledge_category": "工艺制度",
                                        "content": "热制度变化需要结合顺行、热量输入和观察窗口综合判断，调剂应小幅、分步并观察反馈。",
                                    }
                                ],
                            },
                            "risk_change": "stable",
                        },
                        "read_only": True,
                    },
                }
            )
            return
        if self.path.split("?", 1)[0] == TARGET_PAGE:
            page_path = self.page_source or (Path(self.directory) / TARGET_PAGE.lstrip("/"))
            html = page_path.read_text(encoding="utf-8")
            fixture = FIXTURE_PATH.read_text(encoding="utf-8")
            assets = (
                '<link rel="stylesheet" href="/assets/bf-diagnosis-manual-score-local.css">'
                '<script defer src="/assets/bf-diagnosis-manual-score-local.js"></script>'
            )
            injected = html.replace(
                "</head>", f"<script>{fixture}</script>{assets}</head>", 1
            )
            payload = injected.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(payload)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(payload)
            return
        super().do_GET()

    def do_POST(self) -> None:  # noqa: N802
        path = self.path.split("?", 1)[0]
        if path == "/api/diagnosis-manual-scores":
            self.send_json({"ok": True, "created": True, "fixture": True})
            return
        if path == "/api/diagnosis-ai-analysis/retry":
            self.send_json({"ok": True, "queued": True}, status=202)
            return
        if path != "/api/diagnosis/model-review":
            self.send_error(404)
            return
        size = int(self.headers.get("Content-Length", "0") or 0)
        try:
            request_body = json.loads(self.rfile.read(size) or b"{}")
        except json.JSONDecodeError:
            request_body = {}
        time.sleep(0.35)
        label = str(request_body.get("reviewed_label") or "cold")
        score_map = {"normal": 42, "edge": 68, "center": 31, "channel": 46, "cold": 84, "hot": 19, "lowline": 72, "column": 38}
        response = {
            "ok": True,
            "model_review": {
                "schema_version": "diagnosis_model_review.v1",
                "state": "completed",
                "reviewed_label": label,
                "verdict": "agree" if label == "cold" else "partial_agree",
                "rule_score": score_map.get(label, 0),
                "model_support_score": 91 if label == "cold" else 74,
                "summary": "模型复核认为规则分数与关键趋势基本一致；该结论只用于解释和人工复核，不改写规则分数、动作幅度、安全门禁或审批要求。",
                "supporting_evidence": ["所选炉况分数位于当前风险排序前列", "关键历史曲线与规则方向一致"],
                "contradicting_evidence": [] if label == "cold" else ["该炉况并非当前主炉况，只能作为条件预案"],
                "missing_data": ["北料线最新校验状态待确认"],
                "attention_items": ["继续观察15～30分钟", "复核压差和煤气利用率是否同向响应"],
                "manual_review_recommended": label != "cold",
                "model_meta": {
                    "public_model_name": "高炉大模型服务",
                    "cache_hit": False,
                    "read_only": True,
                    "snapshot_hash": "browser-fixture",
                },
            },
        }
        payload = json.dumps(response, ensure_ascii=False).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(payload)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(payload)

    def send_json(self, value: dict[str, Any], status: int = 200) -> None:
        payload = json.dumps(value, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(payload)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(payload)

    def log_message(self, fmt: str, *args: Any) -> None:
        return


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=18093)
    parser.add_argument("--web-root", type=Path, default=DEFAULT_WEB_ROOT)
    parser.add_argument(
        "--page-source",
        type=Path,
        help="Serve this exact HTML payload at the fixture page route while retaining local assets.",
    )
    args = parser.parse_args()
    page_source = args.page_source.resolve() if args.page_source else None
    handler = lambda *handler_args, **handler_kwargs: FixtureHandler(  # noqa: E731
        *handler_args,
        directory=str(args.web_root.resolve()),
        page_source=page_source,
        **handler_kwargs,
    )
    server = ThreadingHTTPServer((args.host, args.port), handler)
    server.serve_forever()


if __name__ == "__main__":
    main()
