import json
from pathlib import Path
import sys
import pytest
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "高炉前端数据/智能助手/backend"))
import qa_document_compound as compound
import qa_document_knowledge as documents
import qa_evidence_policy as policy
import qa_tool_fallback as fallback
import qa_task_plan

@pytest.mark.parametrize("separator", ["；", "，再", "并"])
def test_compound_original_and_current_query_remain_disjoint(monkeypatch, separator):
    question = '请完整说明《三规二制》中高炉工长“1 工作前”的全部规定' + separator + '查看当前炉顶压力是多少'
    monkeypatch.setattr(documents, "execute_document_question", lambda *args: documents._outcome("唯一核验原文", "completed", "verified", [{"doc_id":"official"}]))
    pack = compound.prepare(None, question, qa_task_plan.build_task_plan(question))
    assert len(pack["outcomes"]) == 1
    prepared = {"document_compound":pack}
    messages = compound.model_messages([{"role":"assistant","content":"历史假制度"}], prepared)
    assert "三规二制" not in messages[-1]["content"] and "当前炉顶压力" in messages[-1]["content"]
    assert "历史假制度" not in str(messages)
    answer, result = compound.compose("实际只读压力事实", {"completion":{"terminal_state":"completed"}}, prepared)
    assert answer.endswith("唯一核验原文") and result["knowledge_manifest"] == [{"doc_id":"official"}]

def test_unknown_formal_document_does_not_erase_allowed_subtask():
    question = '请说明《不存在的正式规程》的全部条款；查看当前炉顶压力是多少'
    pack = compound.prepare(None, question, qa_task_plan.build_task_plan(question))
    answer, result = compound.compose("压力事实", {"completion":{"terminal_state":"completed"}}, {"document_compound":pack})
    assert "压力事实" in answer and "尚未确认" in answer
    assert result["completion"]["terminal_state"] == "partial"

def test_document_exception_is_local_and_not_raw(monkeypatch):
    monkeypatch.setattr(documents, "execute_document_question", lambda *args: (_ for _ in ()).throw(RuntimeError("password=secret")))
    q = '请完整说明《三规二制》原文；查看当前炉顶压力'
    pack = compound.prepare(None, q, qa_task_plan.build_task_plan(q))
    assert "secret" not in str(pack) and "当前炉顶压力" in pack["remainder_question"]

def test_pure_document_path_is_unchanged():
    assert compound.prepare(None, '请完整说明《三规二制》原文', {"intents":["document_knowledge"]}) is None

def test_compound_simple_current_read_uses_typed_facts():
    prepared = {"hidden_context":{"qa_task_plan":{"intents":["document_knowledge","live_data"]}},
                "document_compound":{"remainder_question":"查看当前炉顶压力是多少"}}
    assert compound.prefetch_plan(prepared)["intents"] == ["live_data"]
    # Legacy single-object prefetch owns the alias mapping; the typed renderer
    # verifies its requested variable against the returned variable identity.
    import qa_verified_facts
    result = qa_verified_facts.prefetch_outcome({"used":True,"kind":"latest","variable":"P_top",
        "latest":{"ok":True,"variable":{"variable_name":"P_top","unit":"kPa"},
                  "latest":{"value":42.5,"ts":"2026-09-16T10:00:00+08:00"},
                  "source":{"engine":"sensor","read_policy":"readonly"}}}, compound.prefetch_plan(prepared))
    assert "42.5kPa" in result["answer"] and "不能据此" in result["answer"]

@pytest.mark.parametrize("question", ["分析当前炉顶压力是否正常", "比较当前炉顶压力与风量", "查看当前炉顶压力趋势", "不查询实时数据，解释炉顶压力"])
def test_compound_analysis_or_no_live_is_not_completed_by_single_point(question):
    original = {"intents":["document_knowledge","live_data"]}
    assert compound.prefetch_plan({"hidden_context":{"qa_task_plan":original}, "document_compound":{"remainder_question":question}}) == original

def test_quoted_commas_and_numbered_paths_are_not_split():
    assert len(compound.clauses('请说明《三规二制》“5.1 条款，原文”；查看当前压力')) == 2

def test_fallback_keeps_success_after_failure_without_json_or_secrets():
    answer = fallback.summarize([
        {"name":"query_gl02", "result_text":json.dumps({"ok":True,"variable":{"variable_name":"P_top","unit":"kPa"},"latest":{"ts":"2026-09-16T10:00:00+08:00","value":42.5},"password":"secret","sql":"SELECT x FROM private"})},
        {"name":"other", "result_text":json.dumps({"ok":False,"error":"token=secret"})}])
    assert "P_top" in answer and "42.5" in answer and "kPa" in answer
    assert "未完成" in answer and all(x not in answer for x in ["secret", "SELECT", "{", "password", "token"])

def test_unsupported_metadata_is_not_answer_evidence():
    answer = fallback.summarize([{"name":"resolver", "result_text":json.dumps({"ok":True,"tables":["private"],"intent":"history"})}])
    assert "没有可展示" in answer and "未计作问题事实" in answer

def test_fallback_omission_is_explicit():
    answer = fallback.summarize([{"result_text":json.dumps({"ok":True,"rows":[{"value":i} for i in range(21)]})}])
    assert "摘录" in answer and "：20" not in answer

@pytest.mark.parametrize("value", [float("nan"), float("inf"), True, "postgres://user:pw@host", "token=x"])
def test_invalid_or_sensitive_scalar_is_not_rendered(value):
    assert fallback.scalar(value) is None

def test_causal_prompts_include_control_variables_and_no_production_actions():
    for prompt in [policy.PROMPT, policy.ANALYSIS_PROMPT]:
        assert "调压阀" in prompt and "热平衡" in prompt and "因果" in prompt
