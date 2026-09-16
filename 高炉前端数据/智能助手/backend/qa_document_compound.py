"""Isolate formal original-text subtasks from tool/model answers (QAOPT-K02/K04/K05)."""
import re
import qa_document_knowledge as documents
import qa_task_plan

VERSION = "qa-document-compound-v2"


def clauses(text):
    # Only split outer instructions; commas inside quoted source clauses stay.
    stack, result, start = [], [], 0
    pairs = {"《":"》", "“":"”", "‘":"’", '"':'"'}
    for i, ch in enumerate(text):
        if stack and ch == stack[-1]: stack.pop()
        elif ch in pairs: stack.append(pairs[ch])
        elif not stack and ch in "，,；;。\n":
            if text[start:i].strip(): result.append(text[start:i].strip())
            start = i + 1
        elif not stack and i > start and re.match(r"(?:并|再|同时|然后)(?:查询|查看|分析|统计|计算|读取)", text[i:]):
            result.append(text[start:i].strip())
            start = i
    if text[start:].strip(): result.append(text[start:].strip())
    return result


def prepare(conn, question, plan):
    if "document_knowledge" not in plan.get("intents", []) or len(plan["intents"]) < 2:
        return None
    originals, remainder = [], []
    for clause in clauses(question):
        child = qa_task_plan.build_task_plan(clause)
        if "document_knowledge" not in child["intents"]:
            remainder.append(clause)
        elif child["intents"] == ["document_knowledge"]:
            try: originals.append(documents.execute_document_question(conn, clause, child))
            except Exception:
                originals.append(documents._outcome("制度原文查询暂不可用，未使用其他来源补写。", "dependency_blocked", "document_query_unavailable"))
        else:
            # An inseparable request is never sent to the model as a formal
            # clause. Ask for its scope while preserving separate valid tasks.
            originals.append(documents._outcome("制度引用与其他分析未能独立定位，请将书名/岗位/章节和数据问题分开说明。", "needs_clarification", "compound_document_scope_ambiguous"))
            remainder.append("这一复合要求缺少可独立确认的非制度子任务，请提示用户单独描述对象与时间窗，不猜测或调用工具。")
    if not originals:
        originals.append(documents._outcome("未独立确认制度子任务，请补充准确书名和章节。", "needs_clarification", "compound_document_scope_missing"))
    return {"version": VERSION, "outcomes": originals,
            "remainder_question": "；".join(remainder) or "说明非制度子任务还需要哪些信息，不引用或补写任何制度条款。"}


def model_messages(messages, prepared):
    pack = prepared.get("document_compound")
    if not pack: return messages
    # Shared history may contain formal clauses; it is not evidence for this
    # subtask. Keep server system instructions and exactly the data question.
    systems = [dict(m) for m in messages if m.get("role") == "system"]
    systems.append({"role":"system", "content":"制度子任务由独立核验原文执行器负责。只回答下列非制度问题，不引用、总结、生成或补写正式制度条款；历史聊天、报表与现场事实不能作为制度原文。"})
    return [*systems, {"role":"user", "content":pack["remainder_question"]}]


def prefetch_plan(prepared):
    """Simple current reads use typed facts even alongside document tasks."""
    original = prepared.get("hidden_context", {}).get("qa_task_plan") or {}
    pack = prepared.get("document_compound")
    if not pack: return original
    question = pack["remainder_question"]
    child = qa_task_plan.build_task_plan(question)
    # Analysis still needs its own completion/quality checks. Do not turn a
    # single-point reading into a completed risk or trend assessment.
    if (child.get("intents") == ["live_data"]
        and not re.search(r"分析|判断|是否|正常|异常|风险|趋势|变化|原因|为什么|匹配|对比|比较", question)):
        return child
    return original


def compose(answer, result, prepared):
    pack = prepared.get("document_compound")
    if not pack: return answer, result
    out = dict(result or {})
    originals = pack["outcomes"]
    answer = "【非制度子任务】\n" + str(answer or "") + "\n\n【制度原文子任务】\n" + "\n\n".join(item["answer"] for item in originals)
    contract = dict(out.get("completion") or {})
    failed = [item["completion"]["reason"] for item in originals if item["completion"]["terminal_state"] != "completed"]
    contract["document_subtasks"] = [item["completion"] for item in originals]
    contract["semantic_review_required"] = True
    if failed:
        contract.update(terminal_state="partial", complete=False, missing_document_subtasks=failed)
    out["completion"] = contract
    out["knowledge_manifest"] = [m for item in originals for m in item.get("knowledge_manifest", [])]
    out["answer_route"] = "isolated_document_compound"
    return answer, out
