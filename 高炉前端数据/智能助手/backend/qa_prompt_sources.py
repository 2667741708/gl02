"""Build non-live prompts from the task's allowed evidence sources."""
from __future__ import annotations
import re
import qa_evidence_policy
import qa_task_plan

VERSION = "qa-prompt-sources-v1"
GOALS = "你是高炉智能助手。完成普通问答、工艺原理解释及基于用户给定数据的分析；事实、推断和建议分开说明，结论完整、简洁。来源不足时指出缺口并回答能够确认的部分。"
DOCUMENT_RULES = "正式制度只能引用本轮核验的对应文档原文。聊天、报表、现场快照和通用经验不能补写条款；摘录不是全文，未展示的章节不得声称已完整读取。"


def build_source_messages(question, history=(), knowledge_context="", analysis_mode=""):
    if analysis_mode == "initial_context_explanation":
        return None
    plan = qa_task_plan.build_task_plan(question)
    if plan.get("allow_prefetch") or plan.get("allow_mcp_tools"):
        return None
    sources = set(plan.get("allowed_sources") or [])
    blocks = [qa_evidence_policy.PROMPT, GOALS]
    if "document_knowledge" in plan.get("intents", []):
        blocks.append(DOCUMENT_RULES)
    if "knowledge_base" in sources and knowledge_context:
        blocks.append("【本轮知识证据】\n" + knowledge_context)
    if "user_supplied_data" in plan.get("intents", []):
        blocks.append("仅以本轮用户给出的数据作计算和判断，不注入现场快照、报表或旧回答中的数值。")
    blocks.append("未核验本轮生产数据库；不得把历史消息中的当前数值、状态或因果断言当作本轮事实。")
    # New topics do not carry old assistant claims. Explicit pronoun follow-ups
    # can keep bounded conversational wording without treating it as evidence.
    followup = bool(re.match(r"^(?:那|这个|上述|刚才|继续|再解释|为什么这样)", question.strip()))
    prior = []
    if followup and "user_supplied_data" not in plan.get("intents", []):
        prior = [{"role": row["role"], "content": str(row.get("content") or "")[:500]}
                 for row in list(history)[-4:] if row.get("role") in {"user", "assistant"}]
    return [{"role": "system", "content": "\n\n".join(blocks)}, *prior,
            {"role": "user", "content": question}]
