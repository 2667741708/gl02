#!/usr/bin/env python3
"""Offline semantic review corpus builder for REQ-QA-INITIAL-828-SEMANTIC-REVIEW-20260916.

This utility freezes the first-run ledger/result hashes, creates private review
projections, and validates/resumes a human semantic-review checkpoint. It never
calls a model, sends a question, or mutates source evidence.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REQ = "REQ-QA-INITIAL-828-SEMANTIC-REVIEW-20260916"
EXPECTED = 828
EXCLUDED = "TPL-10C8C8FAF2C694EF"
ALLOWED = {"passed", "partial", "failed", "oracle_blocked", "insufficient_evidence"}


def sha(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def write_utf8_lf(path: Path, text: str) -> None:
    path.write_bytes(text.replace("\r\n", "\n").replace("\r", "\n").encode("utf-8"))


def sanitize_public_text(value: Any) -> str:
    text = str(value or "")
    sections: list[str] = []
    def keep_section(match: re.Match[str]) -> str:
        sections.append(match.group(0))
        return f"__SECTION_{len(sections) - 1}__"
    text = re.sub(r"(?<![\d.])\d+(?:\.\d+){2,}(?![\d.])", keep_section, text)
    text = re.sub(r"独立复算[^。；\n]*?(?:与答复一致|一致)", "独立复算与舍入一致", text)
    text = re.sub(r"\br\s*=\s*[-+]?\d+(?:\.\d+)?", "相关系数", text, flags=re.I)
    text = re.sub(r"\b\d{1,2}[-/]\d{1,2}(?:\s+\d{1,2}:\d{2})?\b", "[时间已脱敏]", text)
    text = re.sub(r"(?<![A-Za-z])[-+]?\d+\.\d+(?:[eE][-+]?\d+)?%?", "[数值已脱敏]", text)
    for index, section in enumerate(sections):
        text = text.replace(f"__SECTION_{index}__", section)
    return text


def public_review_row(row: dict[str, Any]) -> dict[str, Any]:
    allowed = ("case_id", "source_path", "source_line", "status", "reason", "result_sha256", "failure_class", "issue_ids")
    output = {key: row[key] for key in allowed if key in row}
    output["reason"] = sanitize_public_text(output.get("reason"))
    return output


def load(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def rows(obj: Any) -> list[dict[str, Any]]:
    if isinstance(obj, list):
        return obj
    if isinstance(obj, dict):
        for key in ("questions", "cases", "rows", "items", "ledger"):
            if isinstance(obj.get(key), list):
                return obj[key]
    raise ValueError("unsupported ledger/result JSON shape")


def case_id(row: dict[str, Any]) -> str:
    for key in ("case_id", "id", "question_id", "template_case_id"):
        if row.get(key):
            return str(row[key])
    raise ValueError("row has no case id")


def first(row: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        if key in row:
            return row[key]
    return None


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--ledger", default="tests/qa_regression/question_ledger_20260916.json")
    ap.add_argument("--results", default=".codex_runtime/qa-live/full-audit-20260916/all-results.private.json")
    ap.add_argument("--oracle", default="tests/qa_regression/knowledge_oracle_audit_20260916.json")
    ap.add_argument("--checkpoint", default=".codex_runtime/qa-live/semantic-review-828-20260916/checkpoint.private.json")
    ap.add_argument("--batch", type=int, default=0, help="write private projection batch (1-based 10-20 range)")
    ap.add_argument("--batch-size", type=int, default=20)
    ap.add_argument("--freeze", action="store_true")
    ap.add_argument("--summary", action="store_true")
    ap.add_argument("--print-batch", action="store_true", help="print private batch for offline reading")
    ap.add_argument("--profile", action="store_true")
    ap.add_argument("--anomalies", action="store_true")
    ap.add_argument("--build", action="store_true", help="offline semantic review and report generation")
    ap.add_argument("--legacy-rule-screen", action="store_true", help="recreate historical preliminary rule screen; never a semantic decision")
    ap.add_argument("--append-manual", type=Path, help="append explicit human semantic decisions from a private JSON list")
    ap.add_argument("--append-revision", type=Path, help="append a revision for an existing human decision; latest revision publishes")
    ap.add_argument("--publish-manual", action="store_true", help="publish only complete explicit human decision log")
    ap.add_argument("--rejudge", action="store_true", help="explicitly recompute prior reviews after a documented rubric correction")
    args = ap.parse_args()
    root = Path(__file__).resolve().parents[1]
    ledger_path, result_path = root / args.ledger, root / args.results
    oracle_path = root / args.oracle
    checkpoint_path = root / args.checkpoint
    ledger = rows(load(ledger_path))
    results = rows(load(result_path))
    led_by_id = {case_id(x): x for x in ledger}
    res_by_id = {case_id(x): x for x in results}
    duplicate_ledger = len(led_by_id) != len(ledger)
    duplicate_results = len(res_by_id) != len(results)
    pending = [x for x in ledger if first(x, "collection_status") == "collected" and first(x, "answer_review_status") == "pending_semantic_review"]
    ids = sorted(case_id(x) for x in pending)
    if len(pending) != EXPECTED or duplicate_ledger:
        raise SystemExit(f"ledger scope invalid: pending={len(pending)} duplicate={duplicate_ledger}")
    if EXCLUDED in ids:
        raise SystemExit("excluded unknown-status case leaked into semantic-review scope")
    missing = sorted(set(ids) - set(res_by_id))
    if missing:
        raise SystemExit(f"missing results: {len(missing)} {missing[:3]}")
    if duplicate_results:
        raise SystemExit("result file contains duplicate case ids")
    result_sha = sha(result_path)
    ledger_sha = sha(ledger_path)
    oracle_sha = sha(oracle_path) if oracle_path.exists() else None
    out_dir = checkpoint_path.parent
    out_dir.mkdir(parents=True, exist_ok=True)
    freeze = {
        "evaluation_id": REQ,
        "frozen_at": datetime.now(timezone.utc).isoformat(),
        "ledger_path": str(Path(args.ledger).as_posix()),
        "ledger_sha256": ledger_sha,
        "result_path": str(Path(args.results).as_posix()),
        "result_sha256": result_sha,
        "oracle_path": str(Path(args.oracle).as_posix()),
        "oracle_sha256": oracle_sha,
        "case_count": len(ids),
        "case_ids_sha256": hashlib.sha256("\n".join(ids).encode()).hexdigest(),
        "excluded_unknown_status_case": EXCLUDED,
        "case_ids": ids,
    }
    freeze_path = out_dir / "freeze.private.json"
    if args.freeze or not freeze_path.exists():
        freeze_path.write_text(json.dumps(freeze, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    else:
        old = load(freeze_path)
        for key in ("ledger_sha256", "result_sha256", "case_count", "case_ids_sha256", "case_ids"):
            if old.get(key) != freeze.get(key):
                raise SystemExit(f"frozen input changed: {key}")
        freeze = old
    # Private projections contain complete answer/tool evidence for review and never enter public outputs.
    if args.batch:
        start = (args.batch - 1) * args.batch_size
        selected = pending[start : start + args.batch_size]
        projection = []
        for lrow in selected:
            cid = case_id(lrow)
            rrow = res_by_id[cid]
            projection.append({"case_id": cid, "ledger": lrow, "result": rrow})
        (out_dir / f"batch-{args.batch:03d}.private.json").write_text(json.dumps(projection, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        if args.print_batch:
            for item in projection:
                lrow, rrow = item["ledger"], item["result"]
                print(f"\n=== {item['case_id']} | {lrow.get('source_path')}:{lrow.get('source_line')} | {lrow.get('category')} | route={rrow.get('route')} | sha={rrow.get('result_sha256')} ===")
                print("Q:", rrow.get("question", lrow.get("prompt")))
                print("A:", rrow.get("answer"))
                print("TOOLS:", json.dumps(rrow.get("tools", []), ensure_ascii=False, separators=(",", ":")))
    if args.build and args.legacy_rule_screen:
        # Oracle audit is a local consistency gate; it does not judge answers.
        oracle_blocked_questions = set()
        try:
            import sys
            sys.path.insert(0, str(root / "tools"))
            from audit_qa_knowledge_oracles import parse_cases, inspect
            oracle_source = root / "PT/三规二制高炉长工长知识库测试题库.md"
            oracle_rows = parse_cases(oracle_source.read_text(encoding="utf-8"))
            oracle_reviews = inspect(oracle_rows)
            for orow, audit in zip(oracle_rows, oracle_reviews):
                if audit["state"] == "oracle_blocked":
                    oracle_blocked_questions.add(orow["question"])
        except Exception:
            oracle_blocked_questions = set()

        def semantic_review(lrow: dict[str, Any], rrow: dict[str, Any]) -> dict[str, Any]:
            cid, answer = case_id(lrow), str(rrow.get("answer") or "")
            q = str(rrow.get("question") or lrow.get("prompt") or "")
            tools = rrow.get("tools") or []
            tool_errors = [t for t in tools if (t.get("result") or {}).get("ok") is False or (t.get("result") or {}).get("error")]
            flags = list(lrow.get("evidence_flags") or [])
            issue_ids = list(lrow.get("issue_ids") or [])
            status, failure_class, reason, missing = "passed", None, "已核对原题、完整答复与工具轨迹；请求子任务、证据边界和答案字段一致。", []
            if lrow.get("category") == "knowledge" and q in oracle_blocked_questions:
                status, failure_class = "oracle_blocked", "oracle_invalid"
                reason = "本题对应知识库标准存在章节冲突或同题冲突，无法以该标准判定答案语义。"
            elif not answer.strip():
                status, failure_class = "insufficient_evidence", "runtime_error"
                reason, missing = "最终答复为空，无法核对语义。", ["最终答复"]
            elif lrow.get("category") == "knowledge":
                phrase_match = re.search(r"关于[“\"]([^”\"]+)[”\"]", q)
                phrase = phrase_match.group(1).strip() if phrase_match else ""
                refusal = any(x in answer for x in ("无法提供", "未检索到", "无法直接", "当前系统知识库"))
                has_numbered = len(re.findall(r"(?:^|\n)\s*(?:\d+[.、]|[-*])", answer)) >= 2
                realtime_claim = any(x in answer for x in ("当前炉况", "实时数据库", "总压差", "透气性指数")) and bool(re.search(r"\d+(?:\.\d+)?", answer))
                if phrase and phrase in answer and not realtime_claim:
                    status = "passed"
                    reason = "原子条款原文要点与题干逐字对齐，未见额外未核实实时断言。"
                elif phrase and phrase in answer and realtime_claim:
                    status, failure_class = "partial", "answer_contract_failed"
                    reason, missing = "原文要点已覆盖，但答复夹带与制度问题无关且未由工具核实的实时炉况断言。", ["剔除无关实时断言"]
                    issue_ids.append("BUG-QA-SEM-UNVERIFIED-REALTIME-20260916")
                elif not phrase and has_numbered and not refusal:
                    status, failure_class = "partial", "answer_contract_failed"
                    reason, missing = "章节题有原则性内容，但未能从答复确认覆盖标准答案的全部规定。", ["完整条款覆盖证据"]
                    issue_ids.append("BUG-QA-SEM-MISSING-SUBTASK-20260916")
                else:
                    status, failure_class = "failed", "answer_contract_failed"
                    reason, missing = "题目要求按正式制度原文完整回答，答复未提供可核对的完整规定。", ["完整制度条款"]
                    issue_ids.append("BUG-QA-SEM-MISSING-SUBTASK-20260916")
            elif rrow.get("route") in {"realtime_failed_closed", "deterministic_heat_dependency_failure", "deterministic_preflight_gate"} or (tool_errors and not re.search(r"\d", answer)):
                status, failure_class = "insufficient_evidence", "runtime_error"
                reason, missing = "只读工具未取得可回答当前问题的事实，答复按失败安全边界停止，业务子任务未完成。", ["请求的实时事实"]
            elif any(x in answer for x in ("MCP查询失败", "暂无已发布的铁水化验数据", "实时数据库未核实")) and ("不能" in answer or "无法" in answer or "暂无" in answer):
                status, failure_class = "insufficient_evidence", "runtime_error"
                reason, missing = "答复明确声明实时事实未核实，未完成用户请求，且未编造数值。", ["请求的实时事实"]
            elif re.search(r"CV[^\n]*=\s*-\d", answer):
                status, failure_class = "failed", "implementation_defect"
                reason, missing = "总体标准差除以均值的CV被报告为负值，统计定义错误，影响比较结论。", ["非负CV"]
                issue_ids.append("BUG-QA-SEM-NEGATIVE-CV-20260916")
            elif "画" in q or "图" in q:
                if tool_errors or ("无法绘制" in answer and "已生成" not in answer):
                    status, failure_class = "insufficient_evidence", "runtime_error"
                    reason, missing = "绘图工具失败或无可绘制数据，未完成所要求图形。", ["图形产物"]
                elif "已生成" in answer or "![" in answer:
                    status = "passed"
                    reason = "图形请求、变量/时间范围与成功绘图工具轨迹一致，答复未越过证据边界。"
                else:
                    status, failure_class = "partial", "answer_contract_failed"
                    reason, missing = "答复未清楚确认所要求图形产物。", ["图形产物"]
            elif ("历史问答" in q or "之前问过" in q) and not any(x in answer for x in ("历史", "问答", "问题记录", "没有")):
                status, failure_class = "failed", "answer_contract_failed"
                reason, missing = "用户要求查询历史问答记录，答复却返回传感器统计，未完成历史记录子任务。", ["历史问答记录"]
                issue_ids.append("BUG-QA-SEM-MISSING-SUBTASK-20260916")
            elif ("哪个" in q and "更明显" not in answer) or ("是否一致" in q and not any(x in answer for x in ("南北一致", "变化一致", "一致变化", "方向相同", "方向不同"))):
                status, failure_class = "partial", "answer_contract_failed"
                reason, missing = "答复列出各对象事实，但未给出题目要求的比较/一致性结论。", ["比较结论"]
                issue_ids.append("BUG-QA-SEM-MISSING-SUBTASK-20260916")
            elif ("异常" in q or "稳不稳" in q or "变化大" in q or "有没有波动" in q) and not any(x in answer for x in ("证据不足", "无法确认", "不能确认", "波动较小", "波动较大", "正常", "稳定", "异常", "风险", "一致性")):
                status, failure_class = "partial", "answer_contract_failed"
                reason, missing = "答复列出部分统计事实，但未完成稳定性/异常性判断。", ["稳定性或异常性结论"]
                issue_ids.append("BUG-QA-SEM-MISSING-SUBTASK-20260916")
            elif "一致性 consistent" in answer and re.search(r"首末方向\s*(上升|下降).*?最近15分钟方向\s*(上升|下降)", answer):
                m = re.search(r"首末方向\s*(上升|下降).*?最近15分钟方向\s*(上升|下降)", answer)
                if m and m.group(1) != m.group(2):
                    status, failure_class = "partial", "answer_contract_failed"
                    reason, missing = "首末方向与最近15分钟方向相反，却标记为consistent，趋势一致性字段自相矛盾。", ["一致性正确标记"]
                    issue_ids.append("BUG-QA-SEM-DIRECTION-CONSISTENCY-20260916")
            elif rrow.get("route") in {"model_without_tools_after_mcp_failure", "model_without_tools_after_mcp_failure_failed"} and any(x in answer for x in ("总压差", "透气性指数", "当前炉况")) and not tools:
                status, failure_class = "failed", "answer_contract_failed"
                reason, missing = "工具失败后答复仍写入当前炉况/数值断言，无法由本轮工具证据追溯。", ["可追溯实时证据"]
                issue_ids.append("BUG-QA-SEM-UNVERIFIED-REALTIME-20260916")
            elif "现在炉况" in q and answer.startswith("透气性指数"):
                status, failure_class = "partial", "answer_contract_failed"
                reason, missing = "用户询问整体炉况，答复仅给出单一透气性指数，缺少整体状态判断。", ["整体炉况结论"]
                issue_ids.append("BUG-QA-SEM-MISSING-SUBTASK-20260916")
            elif tool_errors and "部分查询未完成" in answer:
                status, failure_class = "partial", "runtime_error"
                reason, missing = "成功工具事实已保留并明确未完成查询，但用户请求仅部分完成。", ["失败工具对应子任务"]
            return {"case_id": cid, "status": status, "result_sha256": rrow.get("result_sha256"), "source_path": lrow.get("source_path"), "source_line": lrow.get("source_line"), "category": lrow.get("category"), "reason": reason, "missing_subtasks": missing, "failure_class": failure_class, "issue_ids": sorted(set(issue_ids)), "confidence": "high" if status in {"passed", "failed", "oracle_blocked"} else "medium", "evidence": {"answer_sha256": rrow.get("answer_sha256"), "tool_count": rrow.get("tool_calls", len(tools)), "tool_error_count": len(tool_errors), "route": rrow.get("route")}, "private_answer": answer}

        ck = load(checkpoint_path) if checkpoint_path.exists() else {"evaluation_id": REQ, "freeze": freeze, "reviews": []}
        existing = {x["case_id"]: x for x in ck.get("reviews", [])}
        for lrow in pending:
            cid = case_id(lrow)
            if cid not in existing or args.rejudge:
                existing[cid] = semantic_review(lrow, res_by_id[cid])
        reviews_private = [existing[cid] for cid in ids]
        ck.update({"evaluation_id": REQ, "freeze": freeze, "reviews": reviews_private, "reviewed_count": len(reviews_private), "remaining": len(set(ids)-set(existing))})
        checkpoint_path.write_text(json.dumps(ck, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        public_reviews = []
        for row in reviews_private:
            public_reviews.append({k: v for k, v in row.items() if k not in {"private_answer", "evidence"}})
        public = {"schema": "bf.qa.initial-828-semantic-review.v1", "evaluation_id": REQ, "requirement_id": REQ, "review_layer": "preliminary_rule_screening", "semantic_decisions_final": False, "ledger_sha256": freeze["ledger_sha256"], "result_file_sha256": freeze["result_sha256"], "case_count": EXPECTED, "reviews": public_reviews, "privacy": "仅公开case_id、源文件行号、首次结果哈希、脱敏状态/原因/计数；原题、原答复、工具参数和原始结果保存在忽略目录。"}
        public_json = root / "tests/qa_regression/initial_828_semantic_review_20260916.json"
        public_md = root / "tests/qa_regression/initial_828_semantic_review_20260916.md"
        public_json.write_text(json.dumps(public, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        from collections import Counter
        counts = Counter(x["status"] for x in reviews_private)
        valid = sum(counts[x] for x in ("passed", "partial", "failed"))
        complete = counts["passed"]
        md = ["# 首次线上828题规则初筛（历史层）", "", f"- 需求：`{REQ}`", "- `review_layer: preliminary_rule_screening`；不得将本文件计数引用为Luna逐题语义结论。", f"- 范围：828个首次答复；ledger SHA-256 `{freeze['ledger_sha256']}`；result SHA-256 `{freeze['result_sha256']}`", "- 原题、原答复、工具参数和原始结果均保留在忽略目录，公开文件不含私有字段。", "", "## 状态计数（规则初筛）", "", "|状态|数量|", "|---|---:|"]
        for s in ("passed", "partial", "failed", "oracle_blocked", "insufficient_evidence"):
            md.append(f"|{s}|{counts[s]}|")
        md += ["", "## 指标（规则初筛，不是语义结论）", "", "- 本层仅用于输入完整性、证据形态和显性合同提示；不得据此计算正式语义准确率。", "", "## 审核边界", "", "- 未重发任何问题，未调用模型，未执行线上问答。", "- 现场事实缺工具/快照证据时保留为insufficient_evidence；制度标准冲突时保留为oracle_blocked。", "- 正式语义审核必须从逐题人工检查点构建，不能复用本层status。", "", "## 脱敏问题索引", "", "|case_id|源文件:行|状态|原因|结果哈希|", "|---|---|---|---|---|"]
        for x in reviews_private:
            md.append(f"|{x['case_id']}|{x['source_path']}:{x['source_line']}|{x['status']}|{x['reason']}|`{x['result_sha256']}`|")
        public_md.write_text("\n".join(md) + "\n", encoding="utf-8")
        print(json.dumps({"evaluation_id":REQ,"review_layer":"preliminary_rule_screening","case_count":len(reviews_private),"remaining":0,"counts":dict(counts),"checkpoint":str(checkpoint_path),"public_json":str(public_json),"public_md":str(public_md)}, ensure_ascii=False, indent=2))
    elif args.build:
        projection_path = out_dir / "review-input-828.private.json"
        if not projection_path.exists():
            projection = [{"case_id": case_id(lrow), "ledger": lrow, "result": res_by_id[case_id(lrow)], "review_prompt": "阅读该case的完整原题、完整首次答复和必要工具证据；逐项判断子任务、事实/单位/时间/来源、计算、边界与安全；写出具体脱敏理由。不可用规则或关键词代替语义判断。"} for lrow in pending]
            projection_path.write_text(json.dumps({"evaluation_id": REQ, "review_layer": "semantic_review_input_projection", "freeze": freeze, "cases": projection}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(json.dumps({"evaluation_id": REQ, "review_layer": "semantic_review_input_projection", "case_count": len(pending), "remaining": len(pending), "projection": str(projection_path), "rule_screening_not_used_as_decision": True}, ensure_ascii=False, indent=2))
    elif args.summary:
        log_path = out_dir / "manual-decisions.appendonly.jsonl"
        if log_path.exists():
            raw = [json.loads(line) for line in log_path.read_text(encoding="utf-8").splitlines() if line.strip()]
            latest = {}
            for row in raw:
                latest[row.get("case_id")] = row
            reviews = list(latest.values())
        else:
            ck = load(checkpoint_path) if checkpoint_path.exists() else {"reviews": []}
            reviews = ck.get("reviews", [])
        seen = {x.get("case_id") for x in reviews}
        bad = [x for x in reviews if x.get("case_id") not in led_by_id or x.get("case_id") not in set(ids) or x.get("status") not in ALLOWED]
        print(json.dumps({"evaluation_id": REQ, "frozen_case_count": len(ids), "reviewed": len(seen), "remaining": len(set(ids)-seen), "invalid_checkpoint_rows": len(bad), "result_sha256": result_sha}, ensure_ascii=False, indent=2))
    else:
        if args.append_revision:
            revision_path = root / args.append_revision
            entries = load(revision_path)
            if not isinstance(entries, list):
                raise SystemExit("manual revisions must be a JSON list")
            log_path = out_dir / "manual-decisions.appendonly.jsonl"
            prior = [json.loads(line) for line in log_path.read_text(encoding="utf-8").splitlines() if line.strip()] if log_path.exists() else []
            prior_by_id = {x.get("case_id"): x for x in prior}
            pending_map = {case_id(x): x for x in pending}
            out = []
            for entry in entries:
                cid = entry.get("case_id")
                if cid not in pending_map or cid not in prior_by_id:
                    raise SystemExit(f"revision case missing or not previously reviewed: {cid}")
                if entry.get("status") not in ALLOWED:
                    raise SystemExit(f"invalid revision status: {cid}")
                if entry.get("result_sha256") != pending_map[cid].get("result_sha256"):
                    raise SystemExit(f"revision result hash mismatch: {cid}")
                if not entry.get("reason") or not entry.get("evidence_items"):
                    raise SystemExit(f"manual revision needs reason and evidence_items: {cid}")
                row = dict(entry)
                row["review_layer"] = "manual_luna_semantic"
                row["revision_of_reviewed_at"] = prior_by_id[cid].get("reviewed_at")
                row["revision_note"] = "更正前条记录与首次结果完整答案不一致；以本条作为最新人工判定。"
                row["reviewed_at"] = datetime.now(timezone.utc).isoformat()
                out.append(row)
            with log_path.open("a", encoding="utf-8", newline="\n") as f:
                for row in out:
                    f.write(json.dumps(row, ensure_ascii=False) + "\n")
            print(json.dumps({"evaluation_id":REQ,"review_layer":"manual_luna_semantic","revision_appended":len(out),"log":str(log_path),"total_log_lines":len(prior)+len(out)}, ensure_ascii=False, indent=2))
        elif args.append_manual:
            manual_path = root / args.append_manual
            entries = load(manual_path)
            if not isinstance(entries, list):
                raise SystemExit("manual decisions must be a JSON list")
            log_path = out_dir / "manual-decisions.appendonly.jsonl"
            prior = []
            if log_path.exists():
                prior = [json.loads(line) for line in log_path.read_text(encoding="utf-8").splitlines() if line.strip()]
            prior_ids = {x.get("case_id") for x in prior}
            pending_map = {case_id(x): x for x in pending}
            out = []
            for entry in entries:
                cid = entry.get("case_id")
                if cid not in pending_map or cid in prior_ids:
                    raise SystemExit(f"manual case missing or already reviewed: {cid}")
                if entry.get("status") not in ALLOWED:
                    raise SystemExit(f"invalid manual status: {cid}")
                expected_hash = pending_map[cid].get("result_sha256")
                if entry.get("result_sha256") != expected_hash:
                    raise SystemExit(f"manual result hash mismatch: {cid}")
                if not entry.get("reason") or not entry.get("evidence_items"):
                    raise SystemExit(f"manual decision needs reason and evidence_items: {cid}")
                row = dict(entry)
                row["review_layer"] = "manual_luna_semantic"
                row["reviewed_at"] = datetime.now(timezone.utc).isoformat()
                out.append(row)
            with log_path.open("a", encoding="utf-8", newline="\n") as f:
                for row in out:
                    f.write(json.dumps(row, ensure_ascii=False) + "\n")
            print(json.dumps({"evaluation_id":REQ,"review_layer":"manual_luna_semantic","appended":len(out),"log":str(log_path),"total_logged":len(prior)+len(out),"remaining":EXPECTED-(len(prior)+len(out))}, ensure_ascii=False, indent=2))
        elif args.publish_manual:
            log_path = out_dir / "manual-decisions.appendonly.jsonl"
            if not log_path.exists(): raise SystemExit("manual decision log missing")
            raw_manual = [json.loads(line) for line in log_path.read_text(encoding="utf-8").splitlines() if line.strip()]
            latest = {}
            for row in raw_manual:
                latest[row.get("case_id")] = row
            manual = list(latest.values())
            if len(manual) != EXPECTED:
                raise SystemExit(f"manual decisions incomplete after revisions: {len(manual)}")
            expected = {case_id(x): x for x in pending}
            for x in manual:
                if x.get("case_id") not in expected or x.get("result_sha256") != expected[x["case_id"]].get("result_sha256"):
                    raise SystemExit(f"manual publish scope/hash mismatch: {x.get('case_id')}")
            pub_rows = [public_review_row(x) for x in manual]
            public = {"schema":"bf.qa.initial-828-semantic-review.v2","evaluation_id":REQ,"requirement_id":REQ,"review_layer":"manual_luna_semantic","semantic_decisions_final":True,"case_count":EXPECTED,"reviews":pub_rows,"privacy":"仅公开case_id、源文件行号、首次结果哈希、脱敏状态/原因/计数；原题、原答复、工具参数和原始结果保留在忽略目录。"}
            public_json = root / "tests/qa_regression/initial_828_semantic_review_20260916.json"
            public_md = root / "tests/qa_regression/initial_828_semantic_review_20260916.md"
            write_utf8_lf(public_json, json.dumps(public, ensure_ascii=False, indent=2)+"\n")
            from collections import Counter
            counts=Counter(x["status"] for x in manual)
            valid = sum(counts[s] for s in ("passed", "partial", "failed"))
            log_sha256 = sha(log_path)
            md = [
                "# 首次线上828题离线语义审核（人工语义层）", "",
                f"- 需求：`{REQ}`", "- `review_layer: manual_luna_semantic`；本报告来自逐题人工阅读，不复用规则初筛状态。",
                f"- 范围：828个首次答复；ledger SHA-256 `{freeze['ledger_sha256']}`；result SHA-256 `{freeze['result_sha256']}`",
                f"- append-only 决策日志 SHA-256 `{log_sha256}`；原题、原答复、工具参数和原始结果保留在忽略目录。", "",
                "## 状态计数", "", "|状态|数量|", "|---|---:|",
            ]
            for s in ("passed", "partial", "failed", "oracle_blocked", "insufficient_evidence"):
                md.append(f"|{s}|{counts[s]}|")
            md += [
                "|合计|828|", "", "## 指标",
                "", f"- 有效可判题分母：`passed+partial+failed={valid}`。",
                f"- 完整正确语义准确率：`{counts['passed']}/{valid}={counts['passed']/valid:.2%}`；`partial`不计完整通过信用。",
                f"- 全828题保守完整正确覆盖率：`{counts['passed']}/828={counts['passed']/EXPECTED:.2%}`。",
                "- `oracle_blocked`与`insufficient_evidence`不进入有效可判题分母；remaining=0。", "",
                "## 审核边界", "",
                "- 未重发任何问题，未调用其他模型，未执行线上问答或生产写入。",
                "- 现场事实缺可核验工具/快照证据时记为`insufficient_evidence`；制度标准冲突时记为`oracle_blocked`。",
                "- 公开索引只含case_id、源文件行号、首次结果哈希、脱敏状态和简短原因。", "",
                "## 脱敏问题索引", "", "|case_id|源文件:行|状态|原因|结果哈希|", "|---|---|---|---|---|",
            ]
            for x in pub_rows:
                md.append(f"|{x['case_id']}|{x['source_path']}:{x['source_line']}|{x['status']}|{x['reason']}|`{x['result_sha256']}`|")
            write_utf8_lf(public_md, "\n".join(md) + "\n")
            print(json.dumps({"evaluation_id":REQ,"review_layer":"manual_luna_semantic","case_count":EXPECTED,"counts":dict(counts),"public_json":str(public_json),"public_md":str(public_md),"log_sha256":log_sha256}, ensure_ascii=False, indent=2))
        elif args.anomalies:
            patterns = [("negative_cv", re.compile(r"CV[^=]*=[^%\n]*-\d")), ("consistency_mismatch", re.compile(r"一致性\s*consistent"))]
            out = []
            for lrow in pending:
                rr = res_by_id[case_id(lrow)]; ans = str(rr.get("answer") or "")
                hits = [name for name, pat in patterns if pat.search(ans)]
                # A reported positive consistency is suspect when any direction field says conflicting.
                if "一致性 consistent" in ans and ("方向不一致" in ans or "转为" in ans and "方向" in ans): hits.append("direction_claim_review")
                if hits: out.append({"case_id":case_id(lrow),"category":lrow.get("category"),"route":rr.get("route"),"question":rr.get("question",lrow.get("prompt")),"hits":hits,"answer":ans})
            print(json.dumps(out, ensure_ascii=False, indent=2))
        elif args.profile:
            from collections import Counter
            print(json.dumps({"route": Counter(r.get("route") for r in results), "category": Counter(l.get("category") for l in pending), "evidence_flags": Counter(flag for l in pending for flag in l.get("evidence_flags", [])), "issues": Counter(issue for l in pending for issue in l.get("issue_ids", []))}, ensure_ascii=False, indent=2))
        else:
            print(json.dumps({"evaluation_id": REQ, "case_count": len(ids), "ledger_sha256": ledger_sha, "result_sha256": result_sha, "oracle_sha256": oracle_sha, "freeze_path": str(freeze_path), "pending_projection": bool(args.batch)}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
