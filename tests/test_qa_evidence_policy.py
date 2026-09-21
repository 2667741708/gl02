"""Behavioral checks against the hash-bound local routing candidate."""
import ast
import importlib.util
import json
from pathlib import Path
import re
import unittest
from typing import Any, Mapping
from datetime import datetime, timedelta

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "高炉前端数据/智能助手/backend"
spec = importlib.util.spec_from_file_location("qa_evidence_policy", BACKEND / "qa_evidence_policy.py")
policy = importlib.util.module_from_spec(spec)
spec.loader.exec_module(policy)
SOURCE = (ROOT / ".codex_runtime/qa-routing-v3/candidate/ollama_proxy_server.py").read_text(encoding="utf-8")
TREE = ast.parse(SOURCE)
NODES = {n.name: n for n in TREE.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))}
def functions(names, **overrides):
    scope = dict(Any=Any, Mapping=Mapping, re=re, json=json, datetime=datetime, timedelta=timedelta,
                 qa_evidence_policy=policy, QA_RESPONSE_MODE_FLASH="flash",
                 QA_ANSWER_ROUTE_CODE="code_generation", QA_ANSWER_ROUTE_ANALYSIS="mcp_grounded_analysis",
                 QA_ANSWER_ROUTE_DIRECT="direct", QA_ANSWER_ROUTE_FACT="grounded_fact_only",
                 QA_ANSWER_ROUTE_QUERY="grounded_fact_only")
    scope.update(overrides)
    exec(compile(ast.Module(body=[NODES[n] for n in names], type_ignores=[]), "<candidate>", "exec"), scope)
    return scope

class PolicyTests(unittest.TestCase):
    def test_code_requests(self):
        for q in ("写一个 Python 函数", "请编写 Python 函数", "撰写一个脚本", "帮我写代码", "实现一段Python代码", "换成JS", "给出 SQL 示例", "运行这个脚本", "生成伪代码", "展示命令"):
            with self.subTest(q=q):
                r = policy.direct_result(q)
                self.assertEqual(r["answer_route"], "code_disabled")
                self.assertEqual(r["model_request_count"], 0)
                self.assertFalse(r["tool_used"])
        mixed = policy.direct_result("先计算2、4、6的平均值，再写Python代码")
        self.assertEqual(mixed, {})
        self.assertFalse(policy.code_request_only("先计算2、4、6的平均值，再写Python代码"))
    def test_math_not_code(self):
        for q in ("计算2、4、6的总体标准差，不要写程序", "解释Python是什么", "说明数学函数的含义", "计算均值，不需要代码"):
            with self.subTest(q=q):
                self.assertFalse(policy.code_requested(q))
    def test_no_lookup(self):
        for q in ("不需要查询实时数据", "不查现场数据", "不要调用工具", "只用我给出的三个数2、4、6", "你能帮我做什么？"):
            with self.subTest(q=q):
                self.assertTrue(policy.no_live_lookup(q))
    def test_live_query_still_allowed(self):
        for q in ("查询最近半小时的炉顶压力", "分析过去一小时可能出现什么问题"):
            self.assertFalse(policy.no_live_lookup(q))
    def test_output_guard(self):
        for a in ("```python\nprint(1)\n```", "def average(x):\n    return sum(x)/len(x)", "SELECT avg(x) FROM readings", "可以用 `print(1)`", "const x = 1;", "let result = 4", "Get-ChildItem .", "`curl https://example.invalid`", "DELETE FROM readings", "$value = 4"):
            self.assertEqual(policy.enforce_no_code(a), policy.NO_CODE)
        self.assertEqual(policy.enforce_no_code("均值=(2+4+6)/3=4；总体方差=8/3。"), "均值=(2+4+6)/3=4；总体方差=8/3。")
        json_answer = '```json\n{"平均值": 4, "样本数": 3}\n```'
        self.assertEqual(policy.enforce_no_code(json_answer), json_answer)
        markdown_answer = "```text\n事实：平均值为4。\n```"
        self.assertEqual(policy.enforce_no_code(markdown_answer), markdown_answer)
        mixed_answer = "均值为4。\n```python\nprint(4)\n```"
        guarded = policy.enforce_no_code(mixed_answer)
        self.assertIn("均值为4", guarded)
        self.assertIn(policy.NO_CODE, guarded)
        self.assertNotIn("print", guarded)

    def test_unified_prompt_keeps_analysis_and_readonly_sources_available(self):
        self.assertIn("信息充分时直接回答", policy.PROMPT)
        self.assertIn("检索已授权文档", policy.PROMPT)
        self.assertIn("只读工具返回的已核验事实", policy.PROMPT)
        self.assertNotIn("250字以内", policy.PROMPT)
        self.assertNotIn("本轮明确不查询现场数据", policy.PROMPT)
    def test_required_tool_conflict(self):
        r = policy.direct_result("不要调用工具", {"mode":"required"})
        self.assertEqual(r["answer_route"], "tool_policy_conflict")
        self.assertEqual(r["tool_trace"], [])
    def test_checkbox_cannot_override_user(self):
        scope = functions(["qa_mcp_should_use_tools"])
        self.assertFalse(scope["qa_mcp_should_use_tools"]("不查现场数据", {"use_mcp_tools":True}, {}))
    def test_prefetch_cannot_override_user(self):
        scope = functions(["qa_mcp_prefetch"])
        self.assertFalse(scope["qa_mcp_prefetch"]("只用我给出的三个数")["used"])
    def test_broad_hour_bundle(self):
        scope = functions(["qa_mcp_analysis_variables"], qa_mcp_variables=lambda _: [], normalize_spoken_question=lambda x:x,
                          qa_answer_route=lambda _:"mcp_grounded_analysis", QA_ANALYSIS_VARIABLE_BUNDLES=[])
        self.assertEqual(scope["qa_mcp_analysis_variables"]("根据最近一小时的数据分析可能出现什么问题"), ["P_top","T_top","DP_total","PI","Q_blast"])
    def test_exact_time_statistics_plan(self):
        scope = functions(["qa_mcp_sensor_query_plan"], qa_answer_route=lambda _: "mcp_grounded_analysis",
                          qa_mcp_body_temperature_statistics_plan=lambda _: None,
                          qa_mcp_analysis_variables=lambda _: ["P_top"], qa_mcp_duration_minutes=lambda _:30)
        plan = scope["qa_mcp_sensor_query_plan"]("最近半小时顶压统计")
        self.assertEqual(plan["arguments"]["query_type"], "statistics")
        a = plan["arguments"]
        self.assertEqual((datetime.fromisoformat(a["end_time"])-datetime.fromisoformat(a["start_time"])).total_seconds(),1800)
    def test_partial_evidence_excludes_failures_and_metadata(self):
        scope = functions(["qa_usable_tool_facts"],
                          tool_result_is_grounding_evidence=lambda name, _: name=="query_gl02_statistics",
                          deterministic_mcp_answer=lambda name, _: "有效均值 4")
        def message(payload, name="query_gl02_statistics"):
            return {"role":"tool", "name":name, "content":json.dumps(payload)}
        inputs = [message({"ok":True,"statistics":{"count":3,"avg":4}}),
                  message({"ok":False,"error":"timeout"}), message({"ok":True,"truncated":True}),
                  message({"ok":True}, "list_catalog"), message({"result":{"ok":False}}),
                  {"role":"tool","content":"partial invalid JSON"}]
        self.assertEqual(scope["qa_usable_tool_facts"](inputs), ["有效均值 4"])
    def test_partial_analysis_calls_final_model_once(self):
        calls=[]
        scope = functions(["qa_mcp_final_fallback"], last_user_question=lambda _:"分析趋势",
                          qa_answer_route=lambda _:"mcp_grounded_analysis", qa_usable_tool_facts=lambda _:["有效均值 4"],
                          qa_grounded_mcp_analysis=lambda *a,**k:(calls.append(a) or ("均值 4；缺少其他指标","verified",{})))
        result = scope["qa_mcp_final_fallback"]([], reason_code="BUDGET", reason_message="limit")
        self.assertEqual(len(calls),1)
        self.assertIn("均值 4",result["answer"])
        self.assertIn("未取得的指标不能确认",result["answer"])
    def test_no_evidence_does_not_invent(self):
        scope = functions(["qa_mcp_final_fallback"], last_user_question=lambda _:"分析趋势",
                          qa_answer_route=lambda _:"mcp_grounded_analysis", qa_usable_tool_facts=lambda _:[])
        result=scope["qa_mcp_final_fallback"]([],reason_code="TIMEOUT",reason_message="limit")
        self.assertIn("实时数据库未核实",result["answer"])
        self.assertEqual(result["model_request_count"],0)
    def test_public_terms_not_globally_corrupted(self):
        # The actual sanitizer must preserve general concept labels and English substrings.
        scope = functions(["sanitize_public_qa_answer", "clean_llm_output"], EMPTY_MODEL_ANSWER="模型未返回内容。")
        # Supply only pure dependencies used by this sanitizer.
        scope.update(strip_think_blocks=lambda t:t)
        self.assertEqual(scope["clean_llm_output"]("MCP 是 Model Context Protocol；RAG；averages"),"MCP 是 Model Context Protocol；RAG；averages")

    def test_intro_is_bounded_and_does_not_swallow_composite_question(self):
        r=policy.direct_result("你能帮我做什么？请介绍主要用途，不需要查询实时数据。")
        self.assertEqual(r["answer_route"], "capability_intro")
        self.assertLess(len(r["answer"]),160)
        self.assertEqual(r["model_request_count"],0)
        q="你能做什么？另外查询当前顶压"
        self.assertFalse(policy.capability_intro_only(q))
        self.assertFalse(policy.no_live_lookup(q))

    def test_snapshot_formatter_preserves_time_and_diagnosis_without_private_fields(self):
        obj={"ok":True,"snapshot":{"id":123,"source_time":"2030-01-01 10:00:00", "diagnosis":{"main_label":"normal","raw_scores":{"secret":999},"evidence":[{"text":"压差波动较小"}]}}}
        answer=policy.snapshot_facts(obj)
        self.assertIn("2030-01-01 10:00:00",answer)
        self.assertIn("主要判断：正常",answer)
        self.assertIn("之后的变化尚未核实",answer)
        self.assertNotIn("999",answer)
        self.assertEqual(policy.snapshot_facts({"ok":False,"snapshot":obj["snapshot"]}),"")
        scope=functions(["deterministic_mcp_answer"],try_load_json=json.loads)
        self.assertEqual(scope["deterministic_mcp_answer"]("get_latest_furnace_snapshot",json.dumps(obj)),answer)

    def test_current_snapshot_has_direct_readonly_plan(self):
        scope=functions(["qa_mcp_sensor_query_plan"],qa_answer_route=lambda _:"mcp_grounded_analysis",qa_mcp_variables=lambda _:[])
        self.assertEqual(scope["qa_mcp_sensor_query_plan"]("请解释当前炉况及依据"),{"tool":"get_latest_furnace_snapshot","arguments":{}})

    def test_synthesis_uses_compact_facts_without_planner_scaffolding(self):
        calls=[]
        scope=functions(["qa_grounded_mcp_analysis"],
                        call_ollama_chat_obj=lambda messages,**kwargs:(calls.append((messages,kwargs)) or {"message":{"content":"均值4，缺少其他指标。"}}),
                        clean_llm_output=lambda x:x,ollama_response_timing=lambda _: {},
                        llm_output_is_empty=lambda x:not x,answer_is_grounded=lambda *a:True)
        answer,status,_=scope["qa_grounded_mcp_analysis"]("分析", "已核验均值4", [{"role":"system","content":"OLD_PLANNER_ONLY"},{"role":"tool","content":"raw rows"}])
        self.assertEqual(status,"succeeded")
        self.assertIsNone(calls[0][1]["tools"])
        self.assertEqual(len(calls),1)
        self.assertNotIn("OLD_PLANNER_ONLY",json.dumps(calls[0][0]))
        self.assertIn("已核验均值4",json.dumps(calls[0][0],ensure_ascii=False))

    def test_synthesis_failure_has_sanitized_diagnostics(self):
        logs=[]
        def fail(*a,**k): raise ValueError("must not expose any payload")
        scope=functions(["qa_grounded_mcp_analysis"],call_ollama_chat_obj=fail,emit_host_log=lambda *a,**k:logs.append((a,k)))
        answer,status,timing=scope["qa_grounded_mcp_analysis"]("分析","已核验均值4",[])
        self.assertIn("已核验均值4",answer)
        self.assertEqual(timing["error_type"],"ValueError")
        self.assertNotIn("must not expose",str(logs))

if __name__=="__main__":
    unittest.main()
