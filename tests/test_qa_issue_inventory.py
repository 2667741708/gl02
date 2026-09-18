"""Checks for the audit classifier using synthetic, non-production inputs."""
import importlib.util
from pathlib import Path
SPEC=importlib.util.spec_from_file_location("qa_inventory",Path(__file__).resolve().parents[1]/"tools/build_qa_issue_inventory.py")
audit=importlib.util.module_from_spec(SPEC);SPEC.loader.exec_module(audit)
def row(answer="正常解释",**kwargs):
    return dict(answer=answer,tool_starts=[],tools=[],route="general_model")|kwargs

def test_no_tools_normal_answer_is_not_failure_signal():
    assert audit.flags(row(),{"prompt":"解释概念"})==[]

def test_lifecycle_after_success_has_distinct_signal():
    r=row("数据库查询失败：MCP请求生命周期异常",tools=[{"result":{"ok":True}}])
    f=audit.flags(r,{"prompt":"查询数据"})
    assert "lifecycle_error" in f and "success_then_lifecycle_error" in f

def test_history_tool_only_marks_knowledge_misrouting():
    r=row(tool_starts=[{"tool":"search_qa_messages","arguments":{"keyword":"制度"}}])
    assert "knowledge_history_tool" in audit.flags(r,{"category":"knowledge"})
    assert "knowledge_history_tool" not in audit.flags(r,{"category":"history"})

def test_regression_marker_is_separate_from_ordinary_history_search():
    r=row(tool_starts=[{"tool":"search_qa_messages","arguments":{"keyword":"回归基线 TPL-TEST"}}])
    assert "knowledge_test_marker_search" in audit.flags(r,{"category":"knowledge"})

def test_tool_timeout_counts_once_per_case_with_multiple_calls():
    r=row(tools=[{"result":{"error":"TimeoutError"}},{"result":{"error":"TimeoutError"}}])
    assert audit.flags(r,{}).count("tool_timeout")==1

def test_json_completeness_does_not_mark_normal_text_or_valid_json():
    assert "incomplete_json" in audit.flags(row('{"x":'),{})
    assert "incomplete_json" not in audit.flags(row('{"x":1}'),{})
    assert "incomplete_json" not in audit.flags(row("文字说明"),{})

def test_report_tool_signal_requires_knowledge_question():
    r=row(tool_starts=[{"tool":"list_recent_reports"}])
    assert "knowledge_report_tool" in audit.flags(r,{"category":"knowledge"})
    assert "knowledge_report_tool" not in audit.flags(r,{"category":"report"})

def test_percentiles_nearest_rank_and_empty():
    assert audit.percentile([1,2,3,4,5],.5)==3
    assert audit.percentile([1,2,3,4,5],.95)==5
    assert audit.percentile([],.95) is None
