from __future__ import annotations

import argparse
import json
import re
import time
import urllib.error
import urllib.request
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_TESTSET = ROOT / "智能助手" / "tests" / "bf_rag_100_questions.json"
DEFAULT_JSON = ROOT / "智能助手" / "tests" / "bf_dialog_eval_100_results.json"
DEFAULT_MD = ROOT / "智能助手" / "docs" / "高炉向量库对话框评测报告_100条.md"
DEFAULT_CHAT_URL = "http://10.30.220.12:8092/api/qa/chat"
DEFAULT_CONVERSATIONS_URL = "http://10.30.220.12:8092/api/qa/conversations"


DOC_POINTS: dict[str, dict[str, Any]] = {
    "01-高炉输入输出与主要物流.docx": {
        "answer": "高炉输入侧主要包括含铁炉料、焦炭、喷煤、热风、富氧等，输出侧主要包括铁水、炉渣、高炉煤气和粉尘等。回答应体现物料、热量和还原气体共同构成高炉运行基础。",
        "keywords": ["输入", "输出", "铁水", "炉渣", "煤气", "焦炭", "喷煤", "热风"],
    },
    "02-高炉作为逆流反应器的本质.docx": {
        "answer": "高炉可理解为逆流反应器：炉料自上而下，煤气自下而上，二者进行传热、还原和传质。回答应强调逆流接触提高热量和还原气利用效率。",
        "keywords": ["逆流", "炉料下降", "煤气上升", "传热", "还原", "利用效率"],
    },
    "03-回旋区的作用与工程意义.docx": {
        "answer": "回旋区是风口前焦炭燃烧和煤粉燃烧的重要区域，提供热量和还原性气体，影响下部活跃程度、煤气流初始分布和炉缸热状态。",
        "keywords": ["回旋区", "风口", "燃烧", "热量", "还原气体", "炉缸"],
    },
    "04-高炉内部主要区域及功能.docx": {
        "answer": "高炉内部可按炉身、软熔带、滴落带、炉缸等区域理解，各区域分别承担预热还原、软熔成渣、液滴下行和储铁排渣等功能。",
        "keywords": ["炉身", "软熔带", "滴落带", "炉缸", "还原", "储铁"],
    },
    "05-内部层状结构中焦层与矿层的作用.docx": {
        "answer": "焦层主要承担骨架支撑、透气通道和供热供碳作用，矿层主要完成预热、还原和软熔。焦层与矿层的层状结构会影响煤气分布和顺行。",
        "keywords": ["焦层", "矿层", "骨架", "透气", "还原", "煤气分布"],
    },
    "06-黏结带是什么及其对顺行的影响.docx": {
        "answer": "黏结带是炉料软化、熔融并形成煤气通道约束的区域。其位置和形态会影响透气性、煤气流分布和炉况顺行。",
        "keywords": ["黏结带", "软化", "熔融", "透气性", "煤气流", "顺行"],
    },
    "07-活性焦炭带与死焦堆的区别.docx": {
        "answer": "活性焦炭带参与燃烧、气化和液滴通行，死焦堆更多体现炉缸支撑、液流通道和炉缸状态。二者都影响下部透气、透液和热状态。",
        "keywords": ["活性焦炭带", "死焦堆", "炉缸", "支撑", "透气", "透液"],
    },
    "08-炉内温度分布与传热主导逻辑.docx": {
        "answer": "炉内温度分布受煤气流、炉料下降、传热还原、燃烧供热和液态产物流动共同影响。不能只用单一温度点代表整体热状态。",
        "keywords": ["温度分布", "传热", "煤气流", "炉料", "热状态", "单一"],
    },
    "09-炉料下降与煤气上升的耦合关系.docx": {
        "answer": "炉料下降与煤气上升相互耦合：料柱结构决定煤气通过阻力，煤气分布又会影响加热、还原和料速稳定性。异常时需结合压差、料速和顶温判断。",
        "keywords": ["炉料下降", "煤气上升", "耦合", "料柱", "料速", "压差"],
    },
    "10-透气性变差时的典型信号组合.docx": {
        "answer": "透气性变差通常表现为压差升高、风量下降或波动、料速变慢、炉顶温度分布异常等组合信号。单一信号不足以确定唯一原因。",
        "keywords": ["透气性", "压差升高", "风量下降", "料速", "炉顶温度", "组合"],
    },
    "11-压差、风量、透气性之间的关系.docx": {
        "answer": "压差反映煤气通过料柱的阻力，风量反映送风和通过能力。压差升高并伴随风量受限时，更应关注透气性和顺行状态，但仍需结合趋势判断。",
        "keywords": ["压差", "风量", "透气性", "阻力", "顺行", "趋势"],
    },
    "12-炉顶温度分布与煤气流判读.docx": {
        "answer": "炉顶温度分布可作为煤气流分布的间接信号。偏散或局部偏高提示煤气流可能不均，但不能单独认定偏行或管道。",
        "keywords": ["炉顶温度", "煤气流", "分布", "偏散", "偏行", "间接"],
    },
    "13-边缘气流与中心气流的工程解释.docx": {
        "answer": "边缘气流和中心气流反映煤气在炉内径向分布。两者需要保持相对协调，过强或过弱都可能影响热量利用、顺行和炉墙状态。",
        "keywords": ["边缘气流", "中心气流", "径向", "协调", "顺行", "炉墙"],
    },
    "14-炉凉趋势的判读逻辑.docx": {
        "answer": "炉凉是热状态不足的趋势性描述，应结合铁水硅、铁水温度、风温、喷煤、富氧、料速和压差等综合判断，不能仅凭单项指标下结论。",
        "keywords": ["炉凉", "热状态", "铁水硅", "铁水温度", "风温", "综合判断"],
    },
    "15-热制度波动与铁水成分变化的关系.docx": {
        "answer": "铁水硅和铁水温度可反映热制度变化，但具有滞后性和综合性。连续升高可能提示热状态偏富余，波动偏大需结合煤气流、负荷和操作变化分析。",
        "keywords": ["热制度", "铁水硅", "铁水温度", "滞后", "波动", "偏富余"],
    },
    "16-管道与偏行的稳健解释.docx": {
        "answer": "管道和偏行属于煤气流异常风险描述，判断需依赖多信号组合，如顶温分布、压差、料速、炉墙温度等。证据不足时只能作可能性分析。",
        "keywords": ["管道", "偏行", "煤气流", "多信号", "证据不足", "可能"],
    },
    "17-异常工况下应优先补充哪些信息.docx": {
        "answer": "异常工况下应优先补充时间范围、压差和风量趋势、料速、顶温分布、铁水成分、装料制度、原燃料变化和设备状态，避免在信息不足时武断归因。",
        "keywords": ["补充", "时间范围", "趋势", "料速", "原燃料", "设备状态"],
    },
    "18-提高喷煤量前应先核查哪些因素.docx": {
        "answer": "提高喷煤前应先核查炉况顺行、透气性、压差、风量、热制度、风温富氧配合和焦炭质量。建议应体现条件性，不能直接给操作幅度。",
        "keywords": ["提高喷煤", "核查", "顺行", "透气性", "热制度", "风温"],
    },
    "19-风温、富氧与喷煤的协同逻辑.docx": {
        "answer": "风温、富氧和喷煤是耦合变量：风温和富氧影响热量与燃烧条件，喷煤影响焦比、煤气量和下部热状态。优化需协同观察，不能单参数调整。",
        "keywords": ["风温", "富氧", "喷煤", "协同", "耦合", "单参数"],
    },
    "20-稳顺行与降燃料比之间的权衡.docx": {
        "answer": "降低燃料比应以稳定顺行为前提，需综合关注透气性、热制度、原燃料质量和煤气利用，不能为了降耗牺牲炉况稳定。",
        "keywords": ["燃料比", "顺行", "降耗", "透气性", "热制度", "稳定"],
    },
    "21-提产条件下的透气性边界管理.docx": {
        "answer": "提产会增加炉内气固负荷，应重点管理透气性边界，跟踪压差、风量、料速、顶温和煤气流分布，避免在边界不清时盲目加负荷。",
        "keywords": ["提产", "透气性边界", "负荷", "压差", "风量", "盲目"],
    },
    "22-焦炭质量变化对顺行和热制度的影响.docx": {
        "answer": "焦炭质量会影响料柱骨架、透气性、炉缸活跃和热制度。质量变差时应防止压差上升、料速异常和热状态波动。",
        "keywords": ["焦炭质量", "骨架", "透气性", "炉缸", "热制度", "压差"],
    },
    "23-高炉班报的标准结构.docx": {
        "answer": "班报应按运行概况、主要变化与异常、原因初判、后续关注事项组织，突出本班事实和趋势，不补充未提供数据。",
        "keywords": ["班报", "运行概况", "主要变化", "原因初判", "后续关注", "不补充"],
    },
    "24-高炉日报的标准结构.docx": {
        "answer": "日报应概括当日总体运行、关键指标变化、异常与处理、初步原因和后续关注。表述应稳健，不编造数值或持续时间。",
        "keywords": ["日报", "总体运行", "关键指标", "异常", "原因", "不编造"],
    },
    "25-适合领导汇报的简洁表达模板.docx": {
        "answer": "领导汇报应简洁说明运行状态、主要异常、风险和后续关注，避免过多技术细节，也不能把可能原因写成确定结论。",
        "keywords": ["领导汇报", "简洁", "运行状态", "风险", "后续关注", "确定结论"],
    },
    "26-运行分析中“原因初判”和“后续关注”的写法边界.docx": {
        "answer": "原因初判应使用可能、倾向于、需结合等稳健表述；后续关注应列出需跟踪的指标和现象。报告不得补充用户未提供的数值。",
        "keywords": ["原因初判", "后续关注", "可能", "需结合", "不得补充", "数值"],
    },
}


GROUP_DEFAULTS: dict[str, dict[str, Any]] = {
    "process_qa": {
        "answer": "标准回答应以概念和机理解释为主，优先使用知识库定义，避免把通用工艺解释直接扩展成当前炉况结论。",
        "keywords": ["概念", "机理", "知识库", "定义", "工程理解"],
    },
    "condition_diagnosis": {
        "answer": "标准回答应先做趋势性初判，再列依据、可能原因和需补充信息。证据不足时不得认定唯一主因。",
        "keywords": ["初判", "依据", "可能原因", "补充信息", "不得认定"],
    },
    "parameter_optimization": {
        "answer": "标准回答应先说明目标和边界，再列核查因素、建议方向、风险和监测项，不直接下操作指令或给未经支持的幅度。",
        "keywords": ["目标", "核查", "建议方向", "风险", "监测", "不直接"],
    },
    "operation_report": {
        "answer": "标准回答应形成可用于班报、日报或汇报的结构化文字，基于用户提供事实，不补充未提供的数值、时间和检测结果。",
        "keywords": ["运行概况", "主要变化", "原因初判", "后续关注", "不补充"],
    },
    "fuzzy_oral": {
        "answer": "标准回答应把口语化说法转换成规范工艺术语，再按诊断或优化任务给出稳健分析和需补充信息。",
        "keywords": ["口语", "规范术语", "稳健", "补充信息", "可能"],
    },
    "case_analysis": {
        "answer": "标准回答应说明当前案例库尚未结构化时只能类比相近知识，按相似点、差异点、原因复盘、整改防范和适用边界组织。",
        "keywords": ["案例", "相似点", "差异点", "复盘", "适用边界"],
    },
}


FORBIDDEN_WORDS = ["一定是", "确定是", "必须立即", "直接调整到", "报警线为", "唯一主因就是"]


def load_cases(path: Path, limit: int) -> list[dict[str, Any]]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, list):
        raise ValueError("testset must be a JSON array")
    return data[:limit]


def build_standard_answer(case: dict[str, Any]) -> tuple[str, list[str]]:
    pieces: list[str] = []
    keywords: list[str] = []
    for source in case.get("expected_sources") or []:
        item = DOC_POINTS.get(source)
        if item:
            pieces.append(str(item["answer"]))
            keywords.extend(item["keywords"])
    group_item = GROUP_DEFAULTS.get(str(case.get("group") or ""))
    if group_item:
        pieces.append(str(group_item["answer"]))
        keywords.extend(group_item["keywords"])
    if not pieces:
        pieces.append("标准回答应围绕高炉知识库证据作答，明确适用边界，避免编造现场数据、阈值或唯一原因。")
        keywords.extend(["知识库", "边界", "不编造", "可能", "补充"])
    uniq_keywords = list(dict.fromkeys(str(k) for k in keywords))
    return " ".join(dict.fromkeys(pieces)), uniq_keywords


def build_dialog_question(question: str) -> str:
    return f"请结合当前炉况执行引擎和向量知识库，控制在150字以内回答：{question}"


def post_json(url: str, payload: dict[str, Any], timeout: int) -> dict[str, Any]:
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=body,
        headers={"Content-Type": "application/json; charset=utf-8"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8", errors="replace"))


def create_dialog_conversation(url: str, title: str, timeout: int) -> str:
    data = post_json(url, {"title": title}, timeout)
    if not data.get("ok"):
        raise RuntimeError(f"create conversation failed: {data}")
    conversation = data.get("conversation") or {}
    conversation_id = str(conversation.get("id") or "")
    if not conversation_id:
        raise RuntimeError(f"create conversation returned no id: {data}")
    return conversation_id


def call_chat(
    url: str,
    question: str,
    timeout: int,
    conversation_id: str | None = None,
    mcp_enabled: bool | None = None,
) -> tuple[bool, str, float]:
    payload: dict[str, Any] = {"message": question, "stream": False}
    if conversation_id:
        payload["conversation_id"] = conversation_id
    if mcp_enabled is not None:
        payload["mcp_enabled"] = mcp_enabled
    start = time.perf_counter()
    try:
        data = post_json(url, payload, timeout)
    except (urllib.error.URLError, TimeoutError) as exc:
        elapsed = round((time.perf_counter() - start) * 1000, 1)
        return False, f"调用失败：{exc}", elapsed
    elapsed = round((time.perf_counter() - start) * 1000, 1)
    if not data.get("ok"):
        return False, str(data.get("error") or data), elapsed
    return True, str(data.get("answer") or ""), elapsed


def score_answer(answer: str, keywords: list[str], group: str) -> tuple[int, str]:
    normalized = re.sub(r"\s+", "", answer)
    matched = [kw for kw in keywords if kw and kw in normalized]
    keyword_score = round(min(50, 50 * len(set(matched)) / max(4, min(10, len(set(keywords)) or 4))))

    forbidden_hits = [word for word in FORBIDDEN_WORDS if word in normalized]
    boundary_score = 20 if not forbidden_hits else 5
    cautious_terms = ["可能", "建议", "需", "关注", "结合", "不宜", "不足以", "不能"]
    if group in {"condition_diagnosis", "parameter_optimization", "operation_report", "fuzzy_oral", "case_analysis"}:
        boundary_score += 10 if any(term in normalized for term in cautious_terms) else 0
    else:
        boundary_score += 10
    boundary_score = min(boundary_score, 30)

    current_terms = ["当前", "炉况", "执行引擎", "实时", "DP", "PI", "压差", "透气性", "数据", "快照"]
    if group in {"condition_diagnosis", "parameter_optimization", "operation_report", "fuzzy_oral", "case_analysis"}:
        context_score = 20 if any(term in normalized for term in current_terms) else 8
    else:
        context_score = 20

    total = max(0, min(100, keyword_score + boundary_score + context_score))
    notes = []
    notes.append(f"命中关键词 {len(set(matched))}/{len(set(keywords))}")
    if forbidden_hits:
        notes.append("含高风险绝对化表述：" + "、".join(forbidden_hits))
    if context_score < 20:
        notes.append("当前炉况/执行引擎结合偏弱")
    return total, "；".join(notes)


def markdown_escape(text: str) -> str:
    return text.replace("\r\n", "\n").replace("\r", "\n").strip()


def build_markdown(rows: list[dict[str, Any]], meta: dict[str, Any]) -> str:
    group_names = {
        "process_qa": "A. 工艺知识问答",
        "condition_diagnosis": "B. 工况诊断分析",
        "parameter_optimization": "C. 参数优化建议",
        "operation_report": "D. 运行报告表达",
        "fuzzy_oral": "E. 口语化/模糊问法",
        "case_analysis": "F. 类案例与复盘问法",
    }
    group_counter = Counter(row["group"] for row in rows)
    avg_score = round(sum(row["score"] for row in rows) / len(rows), 1) if rows else 0
    ok_rate = round(sum(1 for row in rows if row["score"] >= 75) / len(rows) * 100, 1) if rows else 0
    lines = [
        "# 高炉向量库对话框评测报告 100 条",
        "",
        f"生成时间：{meta['generated_at']}",
        "",
        "## 1. 测试说明",
        "",
        "本报告用于人工核查 8092 智能助手对话框中“炉况执行引擎 + 向量知识库”的实际回答效果。每条问题均通过 `POST /api/qa/chat` 调用 `220.12` 上的实际对话服务生成模型答案。",
        "",
        f"- 对话标题：{meta.get('conversation_title') or '未指定'}",
        f"- 对话 ID：`{meta.get('conversation_id') or '未指定'}`",
        "",
        "注意：自动评分只用于初筛，最终仍以现场专家和本地逐条核查为准。",
        "",
        "## 2. 汇总结果",
        "",
        f"- 测试问题数：{len(rows)}",
        f"- 平均自动评分：{avg_score}",
        f"- 评分不低于 75 分比例：{ok_rate}%",
        f"- 平均模型耗时：{meta['avg_elapsed_ms']} ms",
        f"- 最大模型耗时：{meta['max_elapsed_ms']} ms",
        "",
        "| 类型 | 数量 | 平均评分 |",
        "|---|---:|---:|",
    ]
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[row["group"]].append(row)
    for group, count in group_counter.items():
        items = grouped[group]
        group_avg = round(sum(item["score"] for item in items) / len(items), 1)
        lines.append(f"| {group_names.get(group, group)} | {count} | {group_avg} |")
    lines.extend(["", "## 3. 逐题结果", ""])
    for group, items in grouped.items():
        lines.extend([f"### {group_names.get(group, group)}", ""])
        for item in items:
            lines.extend(
                [
                    f"#### {item['id']}  {item['question']}",
                    "",
                    f"- 对话框提问：{item['dialog_question']}",
                    f"- 预期意图：`{item.get('expected_intent')}`",
                    f"- 预期知识类别：`{', '.join(item.get('expected_categories') or [])}`",
                    f"- 预期来源：`{', '.join(item.get('expected_sources') or []) or '未指定'}`",
                    f"- 自动评分：`{item['score']}/100`",
                    f"- 评分说明：{item['score_note']}",
                    f"- 调用状态：{'成功' if item['ok'] else '失败'}，耗时 `{item['elapsed_ms']} ms`",
                    "",
                    "理论标准答案方案：",
                    "",
                    markdown_escape(item["standard_answer"]),
                    "",
                    "220.12 实际模型回答：",
                    "",
                    markdown_escape(item["actual_answer"]),
                    "",
                ]
            )
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run 100 dialog-box RAG evaluation cases against 8092.")
    parser.add_argument("--testset", default=str(DEFAULT_TESTSET))
    parser.add_argument("--chat-url", default=DEFAULT_CHAT_URL)
    parser.add_argument("--conversations-url", default=DEFAULT_CONVERSATIONS_URL)
    parser.add_argument("--conversation-id", default="")
    parser.add_argument("--conversation-title", default="")
    parser.add_argument("--dedicated-conversation", action="store_true")
    parser.add_argument("--mcp-enabled", choices=["default", "true", "false"], default="default")
    parser.add_argument("--json-output", default=str(DEFAULT_JSON))
    parser.add_argument("--md-output", default=str(DEFAULT_MD))
    parser.add_argument("--limit", type=int, default=100)
    parser.add_argument("--timeout", type=int, default=120)
    parser.add_argument("--sleep", type=float, default=0.2)
    parser.add_argument("--resume", action="store_true")
    args = parser.parse_args()

    cases = load_cases(Path(args.testset), args.limit)
    conversation_id = str(args.conversation_id or "").strip()
    conversation_title = args.conversation_title or f"向量库测试对话_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    if args.dedicated_conversation and not conversation_id:
        conversation_id = create_dialog_conversation(args.conversations_url, conversation_title, args.timeout)
        print(f"Created conversation: {conversation_id} ({conversation_title})")
    mcp_enabled: bool | None
    if args.mcp_enabled == "true":
        mcp_enabled = True
    elif args.mcp_enabled == "false":
        mcp_enabled = False
    else:
        mcp_enabled = None

    json_output = Path(args.json_output)
    existing: dict[str, dict[str, Any]] = {}
    if args.resume and json_output.exists():
        prior = json.loads(json_output.read_text(encoding="utf-8"))
        for row in prior.get("rows", []):
            existing[str(row.get("id"))] = row

    rows: list[dict[str, Any]] = []
    for index, case in enumerate(cases, start=1):
        case_id = str(case.get("id"))
        if case_id in existing:
            rows.append(existing[case_id])
            continue
        standard_answer, keywords = build_standard_answer(case)
        dialog_question = build_dialog_question(str(case["question"]))
        ok, actual_answer, elapsed_ms = call_chat(
            args.chat_url,
            dialog_question,
            args.timeout,
            conversation_id=conversation_id,
            mcp_enabled=mcp_enabled,
        )
        score, score_note = score_answer(actual_answer, keywords, str(case.get("group") or ""))
        row = {
            **case,
            "dialog_question": dialog_question,
            "standard_answer": standard_answer,
            "standard_keywords": keywords,
            "actual_answer": actual_answer,
            "ok": ok,
            "elapsed_ms": elapsed_ms,
            "conversation_id": conversation_id,
            "score": score if ok else 0,
            "score_note": score_note if ok else "调用失败，未评分",
        }
        rows.append(row)
        print(f"[{index}/{len(cases)}] {case_id} score={row['score']} elapsed_ms={elapsed_ms}")
        json_output.parent.mkdir(parents=True, exist_ok=True)
        meta = {
            "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "chat_url": args.chat_url,
            "conversation_id": conversation_id,
            "conversation_title": conversation_title if conversation_id else "",
            "total": len(rows),
            "avg_elapsed_ms": round(sum(item["elapsed_ms"] for item in rows) / len(rows), 1),
            "max_elapsed_ms": max((item["elapsed_ms"] for item in rows), default=0),
        }
        json_output.write_text(json.dumps({"meta": meta, "rows": rows}, ensure_ascii=False, indent=2), encoding="utf-8")
        if args.sleep:
            time.sleep(args.sleep)

    meta = {
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "chat_url": args.chat_url,
        "conversation_id": conversation_id,
        "conversation_title": conversation_title if conversation_id else "",
        "total": len(rows),
        "avg_elapsed_ms": round(sum(item["elapsed_ms"] for item in rows) / len(rows), 1) if rows else 0,
        "max_elapsed_ms": max((item["elapsed_ms"] for item in rows), default=0),
    }
    json_output.write_text(json.dumps({"meta": meta, "rows": rows}, ensure_ascii=False, indent=2), encoding="utf-8")
    md_output = Path(args.md_output)
    md_output.parent.mkdir(parents=True, exist_ok=True)
    md_output.write_text(build_markdown(rows, meta), encoding="utf-8")
    print(f"Wrote {json_output}")
    print(f"Wrote {md_output}")


if __name__ == "__main__":
    main()
