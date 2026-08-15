from __future__ import annotations

import importlib
import json
import math
import sys
from contextlib import asynccontextmanager
from datetime import datetime, timedelta
from pathlib import Path
from types import SimpleNamespace


ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "高炉前端数据" / "智能助手" / "backend"
MCP_DIR = ROOT / "高炉前端数据" / "智能助手" / "mcp"
for path in (BACKEND, MCP_DIR):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))


def _proxy():
    return importlib.import_module("ollama_proxy_server")


def _extended():
    return importlib.import_module("bf_data_extended_mcp_server")


def test_spoken_layer_statistics_selects_extended_mcp_service() -> None:
    from mcp_host.domain_router import select_mcp_servers
    from mcp_host.server_registry import McpServerConfig, McpServerRegistry

    registry = McpServerRegistry(
        version=1,
        servers=(
            McpServerConfig(
                server_id="gl02-data",
                display_name="GL02",
                domains=("sensor", "chart", "report", "catalog"),
                script_path=Path("gl02.py"),
                default=True,
            ),
            McpServerConfig(
                server_id="gl02-extended",
                display_name="GL02 Extended",
                domains=("body_temperature",),
                script_path=Path("extended.py"),
                default=False,
            ),
        ),
    )
    prompts = (
        "查询最近一小时第7层到第13层各层A到H的平均温度和总体标准差。",
        "查询最近30分钟第12层A到H各方位温度和最大温差。",
    )
    for prompt in prompts:
        selection = select_mcp_servers(prompt, registry)
        assert "gl02-extended" in selection.server_ids


def test_spoken_layer_range_expands_every_layer_and_position() -> None:
    variables = _proxy().qa_mcp_body_temperature_variables(
        "请查询第7层到第13层A到H各点温度，并按每一层计算平均值和标准差"
    )
    assert len(variables) == 7 * 8
    assert variables[0] == "T_body_L7_A"
    assert variables[-1] == "T_body_L13_H"


def test_chinese_numeral_layer_range_resolves_without_machine_ids() -> None:
    variables = _proxy().qa_mcp_body_temperature_variables(
        "请查最近一小时第七层到第十三层各层A到H的平均温度和总体标准差"
    )
    assert len(variables) == 7 * 8
    assert variables[0] == "T_body_L7_A"
    assert variables[-1] == "T_body_L13_H"


def test_body_statistics_plan_is_one_composite_call_with_explicit_clock_range() -> None:
    plan = _proxy().qa_mcp_sensor_query_plan(
        "请查询2026年8月14日上午8点到9点第7层到第13层A到H各点温度，逐层计算平均值、极差和总体标准差"
    )
    assert plan is not None
    assert plan["tool"] == "gl02ext__query_body_temperature_statistics"
    assert plan["arguments"]["start_layer"] == 7
    assert plan["arguments"]["end_layer"] == 13
    assert plan["arguments"]["positions"] == list("ABCDEFGH")
    assert plan["arguments"]["start_time"].startswith("2026-08-14T08:00:00")
    assert plan["arguments"]["end_time"].startswith("2026-08-14T09:00:00")


def test_total_window_is_not_replaced_by_rolling_window() -> None:
    plan = _proxy().qa_mcp_sensor_query_plan(
        "请查询最近一小时炉体第7层到第13层A到H温度，逐层计算平均值和15分钟滚动标准差"
    )
    assert plan is not None
    start = datetime.fromisoformat(plan["arguments"]["start_time"])
    end = datetime.fromisoformat(plan["arguments"]["end_time"])
    assert end - start == timedelta(minutes=60)
    assert plan["arguments"]["rolling_window_minutes"] == 15


def test_production_spoken_layer_prompts_use_one_composite_tool() -> None:
    questions = (
        "查询最近一小时第7层到第13层各层A到H的平均温度、总体标准差、最高、最低和极差，并比较15分钟滚动标准差是增大还是减小。",
        "比较最近两小时第7层到第13层每层平均温度的波动，列出各层覆盖率、极差、变化量、斜率和变异系数。",
        "查询今天8点到9点第7层到第13层各层平均温度，指出哪一层波动最大，并列出判断依据。",
    )
    for question in questions:
        plan = _proxy().qa_mcp_sensor_query_plan(question)
        assert plan is not None, question
        assert plan["tool"] == "gl02ext__query_body_temperature_statistics", question
        assert plan["arguments"]["start_layer"] == 7
        assert plan["arguments"]["end_layer"] == 13
        assert plan["arguments"]["positions"] == list("ABCDEFGH")


def test_layer_all_position_prompt_requests_point_statistics() -> None:
    plan = _proxy().qa_mcp_sensor_query_plan(
        "查询最近30分钟第12层A到H各方位温度，并给出第12层的空间平均温度和最大温差。"
    )
    assert plan is not None
    assert plan["tool"] == "gl02ext__query_body_temperature_statistics"
    assert plan["arguments"]["include_point_statistics"] is True


def test_batch_tool_calculates_complete_layer_and_point_statistics(monkeypatch) -> None:
    module = _extended()
    calls = []

    def variable(layer: int, position: str):
        return {
            "variable_name": f"T_body_L{layer}_{position}",
            "tag_long_name": f"tag-{layer}-{position}",
        }

    start = datetime(2026, 8, 14, 8, 0)
    rows = []
    for minute, (left, right) in enumerate(((10.0, 20.0), (12.0, 22.0), (14.0, 24.0))):
        ts = start + timedelta(minutes=minute)
        rows.extend([
            {"tag_long_name": "tag-7-A", "ts": ts, "value": left, "quality": "Good"},
            {"tag_long_name": "tag-7-B", "ts": ts, "value": right, "quality": "Good"},
        ])

    monkeypatch.setattr(module, "_body_temperature_variable", variable)
    def query_once(*args):
        calls.append(args)
        return rows

    monkeypatch.setattr(module, "_query_body_temperature_batch", query_once)
    payload = module.query_body_temperature_statistics(
        start_layer=7,
        end_layer=7,
        start_time="2026-08-14T08:00:00+08:00",
        end_time="2026-08-14T08:02:00+08:00",
        positions=["A", "B"],
        include_point_statistics=True,
    )

    assert payload["ok"] is True
    assert payload["data_quality"]["raw_row_count"] == 6
    assert len(calls) == 1
    assert payload["data_quality"]["missing_row_count"] == 0
    layer = payload["layer_statistics"][0]
    assert layer["aligned_complete_count"] == 3
    assert layer["statistics"]["avg"] == 17.0
    assert layer["statistics"]["range"] == 4.0
    assert layer["statistics"]["delta"] == 4.0
    assert math.isclose(layer["statistics"]["stddev_pop"], math.sqrt(8 / 3), rel_tol=1e-12)
    assert len(payload["point_statistics"]) == 2


def test_public_trace_is_operator_readable_and_credential_free() -> None:
    module = _proxy()
    arguments = {
        "start_layer": 7,
        "end_layer": 13,
        "positions": list("ABCDEFGH"),
        "start_time": "2026-08-14T08:00:00+08:00",
        "end_time": "2026-08-14T09:00:00+08:00",
    }
    started = module.qa_mcp_public_trace(
        "tool_start",
        {
            "tool": "gl02ext__query_body_temperature_statistics",
            "arguments": arguments,
            "round": 0,
        },
    )
    completed = module.qa_mcp_public_trace(
        "tool_result",
        {
            "tool": "gl02ext__query_body_temperature_statistics",
            "arguments": arguments,
            "round": 0,
            "elapsed_ms": 2520.9,
            "result": {
                "ok": True,
                "layers": list(range(7, 14)),
                "positions": list("ABCDEFGH"),
                "data_quality": {
                    "queried_point_count": 56,
                    "raw_row_count": 3248,
                    "expected_rows": 3416,
                    "missing_row_count": 168,
                },
                "source": {"schema": "bf_sensor", "object": "one_minute_values"},
            },
        },
    )
    assert started["status"] == "running"
    assert "56个点位" in started["detail"]
    assert completed["status"] == "succeeded"
    assert completed["row_count"] == 3248
    assert completed["source"] == "bf_sensor.one_minute_values"
    serialized = json.dumps([started, completed], ensure_ascii=False).lower()
    for forbidden in ("password", "postgresql://", "dsn", "select ", "d:\\"):
        assert forbidden not in serialized


def test_model_explanation_rejects_new_numbers_and_preserves_facts(monkeypatch) -> None:
    module = _proxy()
    facts = "第7层：平均 100℃，总体标准差 2℃。"
    monkeypatch.setattr(
        module,
        "call_ollama_chat_obj",
        lambda *args, **kwargs: {"message": {"content": "该层波动较小，可继续结合压差观察。"}},
    )
    accepted, status = module.qa_body_temperature_model_explanation("解释波动", facts)
    assert status == "succeeded"
    assert accepted

    monkeypatch.setattr(
        module,
        "call_ollama_chat_obj",
        lambda *args, **kwargs: {"message": {"content": "模型推测温度将升到 999℃。"}},
    )
    rejected, status = module.qa_body_temperature_model_explanation("解释波动", facts)
    assert rejected == ""
    assert status == "rejected_ungrounded_numbers"


def test_end_to_end_route_uses_one_composite_mcp_call_and_emits_trace(monkeypatch) -> None:
    module = _proxy()
    question = "查询最近一小时第七层到第十三层各层A到H的平均温度和总体标准差"
    payload = {
        "ok": True,
        "layers": list(range(7, 14)),
        "positions": list("ABCDEFGH"),
        "start_time": "2026-08-14T08:00:00+08:00",
        "end_time": "2026-08-14T09:00:00+08:00",
        "unit": "℃",
        "layer_statistics": [
            {
                "layer": layer,
                "expected_minute_count": 61,
                "coverage_ratio": 1.0,
                "statistics": {
                    "count": 61,
                    "avg": 40 + layer,
                    "stddev_pop": 1,
                    "min": 39 + layer,
                    "max": 41 + layer,
                    "range": 2,
                    "cv_percent": 2,
                    "delta": 0.2,
                    "slope_per_min": 0.01,
                },
                "rolling_variation": {},
            }
            for layer in range(7, 14)
        ],
        "point_statistics": [],
        "data_quality": {
            "queried_point_count": 56,
            "raw_row_count": 3416,
            "expected_rows": 3416,
            "missing_row_count": 0,
            "nonfinite_count": 0,
            "zero_count": 0,
        },
        "source": {"schema": "bf_sensor", "object": "one_minute_values"},
    }
    schema = {
        "type": "object",
        "required": ["start_layer", "end_layer", "start_time", "end_time", "positions"],
        "properties": {
            "start_layer": {"type": "integer"},
            "end_layer": {"type": "integer"},
            "start_time": {"type": "string"},
            "end_time": {"type": "string"},
            "positions": {"type": "array", "items": {"type": "string"}},
            "rolling_window_minutes": {"type": "integer"},
            "require_all_positions": {"type": "boolean"},
            "include_point_statistics": {"type": "boolean"},
        },
    }

    class FakeManager:
        instance = None

        def __init__(self, *args, **kwargs):
            self.call_count = 0
            FakeManager.instance = self

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return None

        async def attach(self, server_ids):
            return (
                SimpleNamespace(
                    exposed_name="gl02ext__query_body_temperature_statistics",
                    input_schema=schema,
                    server_id="gl02-extended",
                ),
            )

        @asynccontextmanager
        async def execution_scope(self):
            yield self

        def ollama_tools(self):
            return [{
                "type": "function",
                "function": {
                    "name": "gl02ext__query_body_temperature_statistics",
                    "description": "batch body temperature statistics",
                    "parameters": schema,
                },
            }]

        async def call_tool(self, name, arguments):
            self.call_count += 1
            assert name == "gl02ext__query_body_temperature_statistics"
            assert arguments["start_layer"] == 7
            assert arguments["end_layer"] == 13
            assert arguments["positions"] == list("ABCDEFGH")
            return SimpleNamespace(structuredContent=payload)

    selection = SimpleNamespace(
        server_ids=("gl02-extended",),
        matched_domains=("body_temperature",),
        reasons=("命中炉体温度语义",),
    )
    monkeypatch.setattr(module, "McpClientManager", FakeManager)
    monkeypatch.setattr(module, "qa_mcp_server_registry", lambda: object())
    monkeypatch.setattr(module, "select_mcp_servers", lambda *args: selection)
    monkeypatch.setattr(module, "qa_mcp_tool_cache_get", lambda *args: None)
    monkeypatch.setattr(module, "qa_mcp_tool_cache_put", lambda *args: None)
    monkeypatch.setattr(
        module,
        "qa_body_temperature_model_explanation",
        lambda *args: ("各层统计结果已按相同口径完成，可结合覆盖率和波动方向继续复核。", "succeeded"),
    )
    events = []
    result = module.run_qa_mcp_tool_loop(
        [{"role": "user", "content": question}],
        emit=lambda name, data: events.append((name, data)),
        routing_question=question,
    )

    assert result["ok"] is True
    assert result["answer_route"] == "deterministic_formatter_with_grounded_model_explanation"
    assert result["model_request_count"] == 1
    assert FakeManager.instance.call_count == 1
    assert [name for name, _ in events] == [
        "trace",
        "trace",
        "tool_start",
        "tool_result",
        "analysis_start",
        "analysis_result",
    ]
    assert all(data.get("public_trace") for _, data in events)


def test_authoritative_body_temperature_tags_are_unique_by_position() -> None:
    module = _extended()
    variables = [module._body_temperature_variable(12, position) for position in "ABCDEFGH"]
    assert len({item["tag_long_name"] for item in variables}) == 8
    assert [item["variable_name"] for item in variables] == [f"T_body_L12_{position}" for position in "ABCDEFGH"]


def test_composite_structured_result_can_bypass_generic_text_truncation() -> None:
    module = _proxy()
    payload = {"ok": True, "layer_statistics": [], "padding": "x" * (module.QA_MCP_MAX_RESULT_CHARS + 100)}
    result = SimpleNamespace(structuredContent=payload)
    truncated = module.mcp_result_to_text(result)
    complete = module.mcp_result_to_text(result, max_chars=None)
    assert "工具结果过长，已截断" in truncated
    assert json.loads(complete) == payload


def test_deterministic_formatter_preserves_layer_evidence_contract() -> None:
    payload = {
        "ok": True,
        "start_time": "2026-08-14T08:00:00+08:00",
        "end_time": "2026-08-14T09:00:00+08:00",
        "unit": "℃",
        "positions": list("ABCDEFGH"),
        "layer_statistics": [{
            "layer": 7,
            "expected_minute_count": 61,
            "statistics": {"count": 61, "avg": 100, "stddev_pop": 2, "range": 8, "delta": 3, "slope_per_min": 0.05},
            "rolling_variation": {
                "window_minutes": 15,
                "start": {"stddev_pop": 0, "range": 0},
                "end": {"stddev_pop": 1.5, "range": 5},
                "stddev_delta": 1.5,
                "range_delta": 5,
            },
        }],
        "point_statistics": [],
        "data_quality": {"raw_row_count": 488, "expected_rows": 488, "missing_row_count": 0, "nonfinite_count": 0, "zero_count": 0},
        "source": {"service": "blast-furnace-gl02-extended-mcp", "schema": "bf_sensor", "object": "one_minute_values"},
    }
    answer = _proxy().deterministic_mcp_answer(
        "gl02ext__query_body_temperature_statistics",
        json.dumps(payload, ensure_ascii=False),
    )
    for token in (
        "第7层", "完整对齐样本 61/61", "层平均 100℃", "总体标准差 2℃",
        "极差 8℃", "首末变化量 3℃", "15分钟滚动标准差", "未插值、未静默过滤",
        "bf_sensor.one_minute_values",
    ):
        assert token in answer


def test_deterministic_formatter_keeps_distinct_position_statistics() -> None:
    payload = {
        "ok": True,
        "start_time": "2026-08-14T16:00:00+08:00",
        "end_time": "2026-08-14T16:30:00+08:00",
        "unit": "℃",
        "positions": list("AB"),
        "layer_statistics": [{
            "layer": 12,
            "expected_minute_count": 31,
            "statistics": {"count": 30, "avg": 45, "range": 2},
        }],
        "point_statistics": [
            {
                "layer": 12,
                "position": "A",
                "expected_minute_count": 31,
                "coverage_ratio": 30 / 31,
                "statistics": {"count": 30, "avg": 44, "stddev_pop": 1, "min": 42, "max": 46, "range": 4},
            },
            {
                "layer": 12,
                "position": "B",
                "expected_minute_count": 31,
                "coverage_ratio": 29 / 31,
                "statistics": {"count": 29, "avg": 46, "stddev_pop": 2, "min": 41, "max": 49, "range": 8},
            },
        ],
        "data_quality": {"raw_row_count": 59, "expected_rows": 62, "missing_row_count": 3},
        "source": {"service": "blast-furnace-gl02-extended-mcp", "schema": "bf_sensor", "object": "one_minute_values"},
    }
    answer = _proxy().deterministic_mcp_answer(
        "gl02ext__query_body_temperature_statistics",
        json.dumps({"result": payload}, ensure_ascii=False),
    )
    assert "第12层A方位：样本 30/31" in answer
    assert "平均 44℃" in answer
    assert "第12层B方位：样本 29/31" in answer
    assert "平均 46℃" in answer
    assert "第12层空间平均" in answer
