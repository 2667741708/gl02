"""Contract tests for the cross-source MCP plan, executor, and snapshot.

Requirement: REQ-8093-CROSS-SOURCE-MCP-20260805

These tests validate the frozen dataclass contracts, plan-building rules,
and snapshot state-machine invariants BEFORE any database calls are made.
"""

from __future__ import annotations

import asyncio
import json
import sys
import time
from dataclasses import asdict
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# Ensure the backend package is importable
ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "高炉前端数据" / "智能助手" / "backend"
MCP_DIR = ROOT / "高炉前端数据" / "智能助手" / "mcp"
sys.path.insert(0, str(BACKEND))
sys.path.insert(0, str(MCP_DIR))

from mcp_host.cross_source_plan import (  # noqa: E402
    CrossSourceFact,
    CrossSourcePlan,
    CrossSourceSnapshot,
    CrossSourceStep,
    failed_snapshot,
    partial_snapshot,
    success_snapshot,
)


def _selection(*server_ids):
    from mcp_host.domain_router import DomainSelection
    return DomainSelection(
        server_ids=tuple(server_ids),
        matched_domains=("heat", "sensor"),
        reasons=("test",),
    )


class _McpResult:
    def __init__(self, payload):
        self.content = [type("Text", (), {"text": json.dumps(payload, ensure_ascii=False)})()]


class _FakeSession:
    def __init__(self, payloads=None, delay=0.0):
        self.payloads = payloads or {}
        self.delay = delay
        self.calls = []

    async def call_tool(self, name, arguments):
        self.calls.append((name, arguments))
        if self.delay:
            await asyncio.sleep(self.delay)
        payload = self.payloads.get(name, {"ok": True, "value": 1})
        return _McpResult(payload)


def _schema_map(*names):
    properties = {
        key: {"type": "array", "items": {"type": "string"}}
        for key in ("variables", "positions")
    }
    properties.update({
        key: {"type": "string"}
        for key in ("query_type", "start_time", "end_time", "heat_no", "heat_reference", "title")
    })
    properties.update({
        key: {"type": "integer"}
        for key in ("layer", "window_minutes", "limit")
    })
    properties["include_history"] = {"type": "boolean"}
    return {name: {"type": "object", "properties": properties} for name in names}

# ==========================================================================
# Phase 1 — Data-contract invariants
# ==========================================================================


class TestCrossSourceStepValidation:
    def test_minimal_step(self):
        step = CrossSourceStep(
            step_id="s1",
            server_id="imes-readonly",
            source_domain="imes",
            tool="imes__get_current_heat_context",
            arguments={},
        )
        assert step.step_id == "s1"
        assert step.depends_on == ()
        assert step.argument_bindings == {}
        assert step.required_for_answer is True

    def test_rejects_empty_step_id(self):
        with pytest.raises(ValueError, match="step_id"):
            CrossSourceStep(
                step_id="  ",
                server_id="imes-readonly",
                source_domain="imes",
                tool="t",
                arguments={},
            )

    def test_rejects_invalid_source_domain(self):
        with pytest.raises(ValueError, match="source_domain"):
            CrossSourceStep(
                step_id="s1",
                server_id="s",
                source_domain="unknown",
                tool="t",
                arguments={},
            )

    def test_rejects_bad_argument_binding_path(self):
        with pytest.raises(ValueError, match="argument_binding"):
            CrossSourceStep(
                step_id="s2",
                server_id="gl02-data",
                source_domain="gl02",
                tool="query_gl02_sensors",
                arguments={},
                depends_on=("s1",),
                argument_bindings={"start_time": "bad_path_without_steps_prefix"},
            )

    def test_valid_argument_binding_path(self):
        step = CrossSourceStep(
            step_id="s2",
            server_id="gl02-data",
            source_domain="gl02",
            tool="query_gl02_sensors",
            arguments={},
            depends_on=("s1",),
            argument_bindings={
                "start_time": "steps.heat_context.heat_time_window.start",
                "end_time": "steps.heat_context.heat_time_window.end",
            },
        )
        assert len(step.argument_bindings) == 2

    def test_argument_binding_reads_decoded_upstream_mcp_payload(self):
        from mcp_host import cross_source_executor as ops
        step = CrossSourceStep(
            step_id="chemistry",
            server_id="imes-readonly",
            source_domain="imes",
            tool="imes__query_hot_metal_chemistry_by_heat",
            arguments={"heat_no": "072"},
            depends_on=("resolve",),
            argument_bindings={"heat_no": "steps.resolve.resolved_heat_no"},
        )
        resolved = ops._resolve_argument_bindings(
            step,
            {"resolve": {"ok": True, "result_text": '{"ok": true, "resolved_heat_no": "2#20260805-072"}'}},
        )
        assert resolved["heat_no"] == "2#20260805-072"

        fallback = ops._resolve_argument_bindings(
            step,
            {"resolve": {"ok": True, "result_text": '{"ok": false, "resolved_heat_no": null}'}},
        )
        assert fallback["heat_no"] == "072"


class TestCrossSourcePlanValidation:
    def test_empty_plan(self):
        plan = CrossSourcePlan()
        assert plan.steps == ()
        assert plan.server_ids == ()
        assert plan.source_count == 0

    def test_rejects_duplicate_step_ids(self):
        with pytest.raises(ValueError, match="Duplicate step_id"):
            CrossSourcePlan(
                steps=(
                    CrossSourceStep(
                        step_id="s1",
                        server_id="imes-readonly",
                        source_domain="imes",
                        tool="t1",
                        arguments={},
                    ),
                    CrossSourceStep(
                        step_id="s1",
                        server_id="gl02-data",
                        source_domain="gl02",
                        tool="t2",
                        arguments={},
                    ),
                ),
            )

    def test_rejects_unknown_dependency(self):
        with pytest.raises(ValueError, match="depends on unknown step"):
            CrossSourcePlan(
                steps=(
                    CrossSourceStep(
                        step_id="s1",
                        server_id="imes-readonly",
                        source_domain="imes",
                        tool="t1",
                        arguments={},
                        depends_on=("ghost",),
                    ),
                ),
            )

    def test_rejects_duplicate_fact_ids(self):
        with pytest.raises(ValueError, match="Duplicate fact_ids"):
            CrossSourcePlan(
                steps=(
                    CrossSourceStep(
                        step_id="s1",
                        server_id="imes-readonly",
                        source_domain="imes",
                        tool="t1",
                        arguments={},
                        produces_fact_ids=("si_value",),
                    ),
                    CrossSourceStep(
                        step_id="s2",
                        server_id="gl02-data",
                        source_domain="gl02",
                        tool="t2",
                        arguments={},
                        produces_fact_ids=("si_value",),
                    ),
                ),
            )

    def test_server_ids_dedup(self):
        plan = CrossSourcePlan(
            steps=(
                CrossSourceStep(
                    step_id="s1",
                    server_id="gl02-data",
                    source_domain="gl02",
                    tool="t1",
                    arguments={},
                ),
                CrossSourceStep(
                    step_id="s2",
                    server_id="gl02-data",
                    source_domain="gl02",
                    tool="t2",
                    arguments={},
                ),
            ),
        )
        assert plan.server_ids == ("gl02-data",)
        assert plan.source_count == 1


class TestCrossSourceFactValidation:
    def test_minimal_fact(self):
        fact = CrossSourceFact(fact_id="si_value", label="Si", value=0.45)
        assert fact.unit is None
        assert fact.missing is False
        assert fact.source_service == ""

    def test_missing_fact_auto_sets_error_code(self):
        fact = CrossSourceFact(
            fact_id="si_value", label="Si", value=None, missing=True
        )
        assert fact.error_code == "DATA_MISSING"

    def test_rejects_empty_fact_id(self):
        with pytest.raises(ValueError, match="fact_id"):
            CrossSourceFact(fact_id="", label="X", value=0)


class TestCrossSourceSnapshotStateMachine:
    def test_success_snapshot(self):
        facts = (
            CrossSourceFact(
                fact_id="si_value", label="Si", value=0.45, unit="%",
                source_service="imes-readonly",
            ),
        )
        snap = success_snapshot(facts, (), total_elapsed_ms=1.2)
        assert snap.ok is True
        assert snap.complete is True
        assert snap.partial is False
        assert snap.analysis_allowed is True
        assert len(snap.missing_fact_ids) == 0

    def test_partial_snapshot_analysis_blocked(self):
        facts = (
            CrossSourceFact(
                fact_id="si_value", label="Si", value=0.45, unit="%",
                source_service="imes-readonly",
            ),
        )
        snap = partial_snapshot(
            facts,
            missing_fact_ids=("p_top", "p_blast"),
            source_status=(),
            analysis_allowed=False,
        )
        assert snap.ok is True
        assert snap.complete is False
        assert snap.partial is True
        assert snap.analysis_allowed is False
        assert "p_top" in snap.missing_fact_ids

    def test_partial_snapshot_analysis_allowed_optional_only(self):
        """When only optional/display steps fail, analysis is still allowed."""
        facts = (
            CrossSourceFact(
                fact_id="si_value", label="Si", value=0.45, unit="%",
                source_service="imes-readonly",
            ),
            CrossSourceFact(
                fact_id="p_top", label="顶压", value=238.0, unit="kPa",
                source_service="gl02-data",
            ),
        )
        snap = partial_snapshot(
            facts,
            missing_fact_ids=("chart_image",),  # only a display fact missing
            source_status=(),
            analysis_allowed=True,
        )
        assert snap.analysis_allowed is True

    def test_partial_requires_at_least_one_fact(self):
        with pytest.raises(ValueError, match="at least one fact"):
            partial_snapshot((), ("x",), ())

    def test_failed_snapshot(self):
        snap = failed_snapshot("SOURCE_SERVER_UNAVAILABLE")
        assert snap.ok is False
        assert snap.complete is False
        assert snap.analysis_allowed is False
        assert len(snap.facts) == 0

    def test_complete_and_partial_mutually_exclusive(self):
        with pytest.raises(ValueError, match="mutually exclusive"):
            CrossSourceSnapshot(
                ok=True, complete=True, partial=True,
                facts=(CrossSourceFact(fact_id="x", label="X", value=1),),
                missing_fact_ids=(),
            )

    def test_complete_with_missing_facts_invalid(self):
        with pytest.raises(ValueError, match="complete=true but missing_fact_ids"):
            CrossSourceSnapshot(
                ok=True, complete=True,
                facts=(CrossSourceFact(fact_id="x", label="X", value=1),),
                missing_fact_ids=("y",),
            )

    def test_ok_true_requires_facts(self):
        with pytest.raises(ValueError, match="ok=true requires at least one fact"):
            CrossSourceSnapshot(ok=True, facts=())


# ==========================================================================
# Phase 2 — Build cross-source plans
# ==========================================================================


# We import from ollama_proxy_server after the backend path is set up.
# These tests exercise the plan-building logic in isolation.

def _import_plan_builder():
    """Lazy import to avoid polluting module-level state."""
    import importlib
    import ollama_proxy_server as ops
    # Force reload in case the module caches state
    return ops


def _import_imes():
    import imes_relay_mcp_server as imes
    return imes


class TestBuildCrossSourcePlans:
    """Test build_cross_source_plans() with real question strings."""

    def test_pure_mes_returns_none(self):
        """Single-source MES question → None (fast path)."""
        ops = _import_plan_builder()
        from mcp_host.domain_router import DomainSelection
        sel = DomainSelection(
            server_ids=("imes-readonly",),
            matched_domains=("heat",),
            reasons=("命中炉次语义",),
        )
        plan = ops.build_cross_source_plans("当前第几炉", sel)
        assert plan is None

    def test_pure_gl02_returns_none(self):
        """Single-source GL02 question → None (fast path)."""
        ops = _import_plan_builder()
        plan = ops.build_cross_source_plans(
            "当前炉顶压力是多少？", _selection("gl02-data")
        )
        assert plan is None

    def test_mes_plus_gl02_returns_plan(self):
        """'上一炉Si + 顶压/冷风压力/富氧率' → 2 concurrent steps."""
        ops = _import_plan_builder()
        plan = ops.build_cross_source_plans(
            "上一炉 Si 多少，当前顶压、冷风压力和富氧率是多少？",
            _selection("imes-readonly", "gl02-data"),
        )
        assert plan is not None
        assert set(plan.server_ids) == {"imes-readonly", "gl02-data"}
        assert "imes_result" not in plan.requested_fact_ids
        assert {"P_top", "P_blast_cold", "O2_rate"}.issubset(plan.requested_fact_ids)

    def test_spoken_heat_with_multi_db(self):
        """'072硅锰 + 13层C点 + 顶压' → heat resolution + 2 sources."""
        ops = _import_plan_builder()
        plan = ops.build_cross_source_plans(
            "072这炉硅锰多少，顺便看13层C点和顶压",
            _selection("imes-readonly", "gl02-data"),
        )
        assert plan is not None
        assert "imes-readonly" in plan.server_ids
        assert any(step.tool == "imes__resolve_spoken_heat_reference" for step in plan.steps)
        assert any("P_top" in step.produces_fact_ids for step in plan.steps)

    def test_body_temperature_uses_extended_capability_and_keeps_p_top_on_sensor_service(self):
        ops = _import_plan_builder()
        plan = ops.build_cross_source_plans(
            "072这炉硅锰多少，顺便看13层C点和顶压",
            _selection("imes-readonly", "gl02-data", "gl02-extended"),
        )
        assert plan is not None
        body = [step for step in plan.steps if step.tool == "gl02ext__query_body_temperature"]
        sensors = [step for step in plan.steps if step.tool == "query_gl02_sensors"]
        assert body and body[0].server_id == "gl02-extended"
        assert body[0].arguments == {"layer": 13, "position": "C", "include_history": False}
        assert sensors and sensors[0].server_id == "gl02-data"
        assert sensors[0].produces_fact_ids == ("P_top",)

    def test_exact_heat_no_preserved(self):
        """2#20260805-072 must NOT be altered by the planner."""
        ops = _import_plan_builder()
        plan = ops.build_cross_source_plans(
            "2#20260805-072这炉硅含量，当前顶压",
            _selection("imes-readonly", "gl02-data"),
        )
        assert plan is not None
        assert plan.requested_heat_reference == "2#20260805-072"
        chemistry = [s for s in plan.steps if "chemistry" in s.step_id]
        assert chemistry and chemistry[0].arguments["heat_no"] == "2#20260805-072"

    def test_p_top_stays_in_sensors_not_history(self):
        """P_top routes to query_gl02_sensors, never to query_gl02_history."""
        ops = _import_plan_builder()
        plan = ops.build_cross_source_plans(
            "上一炉Si和当前P_top是多少？", _selection("imes-readonly", "gl02-data")
        )
        assert plan is not None
        assert all("query_gl02_history" not in s.tool for s in plan.steps)
        assert any(s.tool == "query_gl02_sensors" and "P_top" in s.produces_fact_ids for s in plan.steps)

    def test_no_find_gl02_variables_in_cross_source_path(self):
        """find_gl02_variables must not appear in cross-source plans."""
        ops = _import_plan_builder()
        plan = ops.build_cross_source_plans(
            "上一炉Si和当前顶压是多少？", _selection("imes-readonly", "gl02-data")
        )
        assert plan is not None
        assert all("find_gl02_variables" not in s.tool for s in plan.steps)

    def test_chart_priority_over_sensor_in_gl02(self):
        """When both chart and sensor plans match, only the chart step is kept."""
        ops = _import_plan_builder()
        plan = ops.build_cross_source_plans(
            "上一炉Si，画最近一小时顶压曲线", _selection("imes-readonly", "gl02-data")
        )
        assert plan is not None
        assert any(s.tool == "plot_gl02_trends" for s in plan.steps)
        assert not any(s.tool == "query_gl02_sensors" for s in plan.steps)


# ==========================================================================
# Phase 3 — DAG executor
# ==========================================================================


class TestDagTopology:
    """Test topological sort and concurrent / serial grouping."""

    def test_independent_steps_are_concurrent(self):
        from mcp_host.cross_source_executor import _topological_layers
        steps = (
            CrossSourceStep("a", "imes-readonly", "imes", "t1", {}),
            CrossSourceStep("b", "gl02-data", "gl02", "t2", {}),
        )
        assert [[s.step_id for s in layer] for layer in _topological_layers(steps)] == [["a", "b"]]

    def test_dependent_steps_run_in_order(self):
        from mcp_host.cross_source_executor import _topological_layers
        steps = (
            CrossSourceStep("a", "imes-readonly", "imes", "t1", {}),
            CrossSourceStep("b", "gl02-data", "gl02", "t2", {}, depends_on=("a",)),
        )
        assert [[s.step_id for s in layer] for layer in _topological_layers(steps)] == [["a"], ["b"]]

    def test_cycle_detection(self):
        """Cyclic depends_on must be rejected at plan-build time."""
        from mcp_host.cross_source_executor import _topological_layers
        steps = (
            CrossSourceStep("a", "imes-readonly", "imes", "t1", {}, depends_on=("b",)),
            CrossSourceStep("b", "gl02-data", "gl02", "t2", {}, depends_on=("a",)),
        )
        with pytest.raises(ValueError, match="Cyclic dependency"):
            _topological_layers(steps)

    def test_same_server_serial(self):
        """Two steps on the same server_id run serially."""
        from mcp_host.cross_source_executor import _topological_layers
        steps = (
            CrossSourceStep("a", "gl02-data", "gl02", "t1", {}),
            CrossSourceStep("b", "gl02-data", "gl02", "t2", {}),
        )
        assert len(_topological_layers(steps)) == 1

    def test_different_servers_concurrent(self):
        """Steps on different server_ids run concurrently."""
        from mcp_host.cross_source_executor import _topological_layers
        steps = (
            CrossSourceStep("a", "imes-readonly", "imes", "t1", {}),
            CrossSourceStep("b", "gl02-data", "gl02", "t2", {}),
        )
        assert len(_topological_layers(steps)[0]) == 2


class TestDagExecution:
    def _run(self, plan, session, tool_names):
        from mcp_tool_policy import ToolPolicyLimits
        from mcp_host.cross_source_executor import execute_cross_source_plan
        cache = {}

        async def run():
            return await execute_cross_source_plan(
                plan=plan,
                manager=None,
                session=session,
                tool_schemas=_schema_map(*tool_names),
                tool_servers={},
                policy_limits=ToolPolicyLimits(),
                tool_cache_get=lambda name, args: cache.get((name, json.dumps(args, sort_keys=True))),
                tool_cache_put=lambda name, args, value: cache.__setitem__((name, json.dumps(args, sort_keys=True)), value),
                execution_started=time.monotonic(),
                budget_seconds=5,
                child_timeout_seconds=2,
            )
        return asyncio.run(run())

    def test_different_servers_are_concurrent(self):
        session = _FakeSession(delay=0.12)
        plan = CrossSourcePlan(steps=(
            CrossSourceStep("a", "imes-readonly", "imes", "t1", {}),
            CrossSourceStep("b", "gl02-data", "gl02", "t2", {}),
        ))
        started = time.monotonic()
        self._run(plan, session, ("t1", "t2"))
        assert time.monotonic() - started < 0.22

    def test_same_server_steps_are_serial(self):
        session = _FakeSession(delay=0.08)
        plan = CrossSourcePlan(steps=(
            CrossSourceStep("a", "gl02-data", "gl02", "t1", {}),
            CrossSourceStep("b", "gl02-data", "gl02", "t2", {}),
        ))
        started = time.monotonic()
        self._run(plan, session, ("t1", "t2"))
        assert time.monotonic() - started >= 0.14

    def test_per_sensor_failure_becomes_missing_fact(self):
        session = _FakeSession(payloads={
            "query_gl02_sensors": {
                "ok": True,
                "items": [
                    {"requested_variable": "P_top", "ok": True,
                     "variable": {"unit": "kPa"}, "latest": {"value": 238.1, "ts": "2026-08-05T12:00:00"}},
                    {"requested_variable": "P_blast", "ok": False, "error": "NO_DATA"},
                ],
            }
        })
        plan = CrossSourcePlan(steps=(CrossSourceStep(
            "s", "gl02-data", "gl02", "query_gl02_sensors",
            {"variables": ["P_top", "P_blast"]},
            produces_fact_ids=("P_top", "P_blast"),
        ),))
        snapshot = self._run(plan, session, ("query_gl02_sensors",))
        assert snapshot.partial is True
        assert "P_blast" in snapshot.missing_fact_ids
        assert any(f.fact_id == "P_top" and not f.missing for f in snapshot.facts)

    def test_empty_sensor_items_are_not_success(self):
        session = _FakeSession(payloads={"query_gl02_sensors": {"ok": True, "items": []}})
        plan = CrossSourcePlan(steps=(CrossSourceStep(
            "s", "gl02-data", "gl02", "query_gl02_sensors", {},
            produces_fact_ids=("P_top",),
        ),))
        snapshot = self._run(plan, session, ("query_gl02_sensors",))
        assert snapshot.ok is False


# ==========================================================================
# Phase 5 — Heat-number resolution
# ==========================================================================


class TestHeatReferenceResolution:
    """Test resolve_spoken_heat_reference() parsing rules."""

    def test_exact_full_format(self):
        """2#20260805-072 → exact match."""
        ops = _import_imes()
        result = ops._resolve_spoken_heat_reference_core("2#20260805-072")
        assert result["resolved_heat_no"] == "2#20260805-072"
        assert result["resolution_policy"] == "exact"

    def test_date_prefix_without_furnace(self):
        """20260805-072 → add 2# prefix, exact match."""
        ops = _import_imes()
        result = ops._resolve_spoken_heat_reference_core("20260805-072")
        assert result["resolved_heat_no"] == "2#20260805-072"
        assert result["resolution_policy"] == "exact_with_prefix"

    def test_spoken_short_unique(self):
        """072 → 72h lookup, unique → resolved."""
        ops = _import_imes()

        class Cursor:
            def execute(self, query, params):
                self.rows = [("2#20260805-072", None, None, None)]
            def fetchall(self): return self.rows
            def __enter__(self): return self
            def __exit__(self, *args): return False

        class Conn:
            def cursor(self): return Cursor()
            def __enter__(self): return self
            def __exit__(self, *args): return False

        with patch.object(ops, "connection", lambda *_args, **_kwargs: Conn()):
            result = ops._resolve_spoken_heat_reference_core("072")
        assert result["resolved_heat_no"] == "2#20260805-072"
        assert result["resolution_policy"] == "spoken_72h_unique_match"

    def test_spoken_short_not_found(self):
        """999 → 72h lookup, 0 rows → HEAT_REFERENCE_NOT_FOUND."""
        ops = _import_imes()

        class Cursor:
            def execute(self, query, params): self.rows = []
            def fetchall(self): return self.rows
            def __enter__(self): return self
            def __exit__(self, *args): return False
        class Conn:
            def cursor(self): return Cursor()
            def __enter__(self): return self
            def __exit__(self, *args): return False
        with patch.object(ops, "connection", lambda *_args, **_kwargs: Conn()):
            result = ops._resolve_spoken_heat_reference_core("999")
        assert result["error_code"] == "HEAT_REFERENCE_NOT_FOUND"
        assert result["resolved_heat_no"] is None

    def test_spoken_short_ambiguous(self):
        """001 → 72h lookup, multiple → HEAT_REFERENCE_AMBIGUOUS."""
        ops = _import_imes()

        class Cursor:
            def execute(self, query, params):
                self.rows = [("2#20260805-001", None, None, None), ("2#20260804-001", None, None, None)]
            def fetchall(self): return self.rows
            def __enter__(self): return self
            def __exit__(self, *args): return False
        class Conn:
            def cursor(self): return Cursor()
            def __enter__(self): return self
            def __exit__(self, *args): return False
        with patch.object(ops, "connection", lambda *_args, **_kwargs: Conn()):
            result = ops._resolve_spoken_heat_reference_core("001")
        assert result["error_code"] == "HEAT_REFERENCE_AMBIGUOUS"
        assert result["resolved_heat_no"] is None

    def test_never_guess_todays_heat(self):
        """When 072 not found, must NOT fabricate 2#20260805-072."""
        ops = _import_imes()

        class Cursor:
            def execute(self, query, params): self.rows = []
            def fetchall(self): return self.rows
            def __enter__(self): return self
            def __exit__(self, *args): return False
        class Conn:
            def cursor(self): return Cursor()
            def __enter__(self): return self
            def __exit__(self, *args): return False
        with patch.object(ops, "connection", lambda *_args, **_kwargs: Conn()):
            result = ops._resolve_spoken_heat_reference_core("072")
        assert result["resolved_heat_no"] is None
        assert "20260805-072" not in str(result)


# ==========================================================================
# Phase 6 — Answer formatting
# ==========================================================================


class TestFormatCrossSourceAnswer:
    """Test format_cross_source_answer() deterministic output."""

    def test_complete_facts_no_model_call(self):
        ops = _import_plan_builder()
        snapshot = success_snapshot(
            (CrossSourceFact("p_top", "炉顶压力", 238.1, "kPa", "2026-08-05T12:00:00", source_service="gl02-data"),),
            (),
        )
        answer = ops.format_cross_source_answer(snapshot)
        assert "炉顶压力" in answer
        assert "238.1" in answer
        assert "完整结果" in answer

    def test_partial_facts_no_model_call(self):
        """Partial data → deterministic formatter, model skipped entirely."""
        ops = _import_plan_builder()
        snapshot = partial_snapshot(
            (CrossSourceFact("si_avg", "上一炉Si", 0.29, "%", source_service="imes-readonly"),),
            ("P_top",), (), analysis_allowed=False,
        )
        answer = ops.format_cross_source_answer(snapshot, "不应出现的分析")
        assert "上一炉Si" in answer
        assert "P_top" in answer
        assert "已跳过分析" in answer
        assert "不应出现的分析" not in answer

    def test_analysis_only_when_all_evidence_present(self):
        """Model called ONLY when all evidence facts are present AND user asked for analysis."""
        ops = _import_plan_builder()
        complete = success_snapshot((CrossSourceFact("x", "X", 1),), ())
        partial = partial_snapshot((CrossSourceFact("x", "X", 1),), ("y",), (), False)
        assert "分析文本" in ops.format_cross_source_answer(complete, "分析文本")
        assert "分析文本" not in ops.format_cross_source_answer(partial, "分析文本")

    def test_facts_listed_before_any_analysis(self):
        """Fact table always precedes model-generated interpretation."""
        ops = _import_plan_builder()
        snapshot = success_snapshot((CrossSourceFact("x", "X", 1),), ())
        answer = ops.format_cross_source_answer(snapshot, "分析文本")
        assert answer.index("查询项") < answer.index("分析文本")


# ==========================================================================
# Integration smoke tests
# ==========================================================================


class TestSnapshotRoundTrip:
    """Snapshot serialisation / deserialisation round-trip."""

    def test_snapshot_asdict_is_json_serializable(self):
        snap = success_snapshot(
            facts=(
                CrossSourceFact(
                    fact_id="si_value", label="Si", value=0.45, unit="%",
                    data_time="2026-08-05T14:00:00", quality="official",
                    source_service="imes-readonly",
                    source_object="public.t_qpes_inner_batch",
                ),
            ),
            source_status=(
                {
                    "server_id": "imes-readonly",
                    "tool": "imes__get_current_previous_heat_si_summary",
                    "elapsed_ms": 234.5,
                    "cache_hit": False,
                    "ok": True,
                },
            ),
            heat_reference={
                "requested_heat_no": "072",
                "resolved_heat_no": "2#20260805-072",
                "resolution_policy": "spoken_72h_unique_match",
            },
            total_elapsed_ms=500.0,
        )
        d = asdict(snap)
        text = json.dumps(d, ensure_ascii=False, default=str)
        assert len(text) > 0
        roundtrip = json.loads(text)
        assert roundtrip["ok"] is True
        assert roundtrip["complete"] is True
        assert len(roundtrip["facts"]) == 1
        assert roundtrip["facts"][0]["fact_id"] == "si_value"
        assert roundtrip["heat_reference"]["resolved_heat_no"] == "2#20260805-072"
