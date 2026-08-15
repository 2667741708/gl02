from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
HTML = ROOT / "高炉前端数据" / "frontend_dashboard_v3.server.html"


def _source() -> str:
    return HTML.read_text(encoding="utf-8")


def test_sse_dispatches_public_execution_trace_events() -> None:
    source = _source()
    for event_name, callback in (
        ("trace", "onTrace"),
        ("tool_start", "onToolStart"),
        ("tool_result", "onToolResult"),
        ("analysis_start", "onAnalysisStart"),
        ("analysis_result", "onAnalysisResult"),
    ):
        assert f"eventName === '{event_name}'" in source
        assert f"{callback}?.(obj)" in source


def test_active_qa_tab_renders_trace_inside_pending_answer() -> None:
    source = _source()
    active_start = source.index("    function QaTab({ buf, diagnosis })")
    active_end = source.index("    function reportEnsureStyle()", active_start)
    active = source[active_start:active_end]
    assert "executionTraceRef = useRef([])" in active
    assert "onTrace: mergeTrace" in active
    assert "onToolStart: mergeTrace" in active
    assert "onToolResult: mergeTrace" in active
    assert "onAnalysisStart: mergeTrace" in active
    assert "onAnalysisResult: mergeTrace" in active
    assert "content: qaExecutionTracePayload(next)" in active
    assert "__BF_QA_EXEC_TRACE__:" in source
    assert "<QaExecutionTrace items={JSON.parse" in source


def test_trace_renderer_only_consumes_bounded_public_trace() -> None:
    source = _source()
    merge_start = source.index("function qaMergeExecutionTrace")
    merge_end = source.index("function qaExecutionTracePayload", merge_start)
    merge = source[merge_start:merge_end]
    assert "payload?.public_trace" in merge
    assert "payload?.arguments" not in merge
    assert "payload?.result" not in merge
    assert "password" not in merge.lower()
    assert "postgresql" not in merge.lower()


def test_remote_8768_loading_fix_is_preserved_during_trace_merge() -> None:
    source = _source()
    assert "BUG-8093-8768-CONTRACT-LOADING-20260814" in source
    assert "function preserveRecommendation8093(message)" in source
    assert "recommendation_delivery: { state: 'preserved'" in source
    assert "function BFRecommendationContractLoadingV1()" in source
    assert "if (!diagnosis) return <BFRecommendationContractLoadingV1 />" in source
    assert "abc33-20260814-bc-score-contribution-r1" in source
