"""Reconcile frozen collection and final semantic judgments without any model calls.

REQ-QA-FULL-ISSUE-INVENTORY-20260916. Outputs contain IDs, safe source references,
counts and hashes, never original prompts, responses, identities or production data.
"""
import csv
import hashlib
import io
import json
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "tests/qa_regression"
INPUT_BYTES = {}
SEMANTIC_MAPPING = {
    "DIRECTION-CONSISTENCY": ("趋势方向自相矛盾", ["QAOPT-E04", "QAOPT-E06"]),
    "MISSING-SUBTASK": ("遗漏用户子任务", ["QAOPT-R01", "QAOPT-E05"]),
    "CV-DOMAIN": ("变异系数适用范围错误", ["QAOPT-E03", "QAOPT-E04"]),
    "UNVERIFIED-REALTIME": ("未经证据核实的实时断言", ["QAOPT-E02", "QAOPT-E03"]),
    "CONCEPT-SCOPE": ("业务概念或适用范围错误", ["QAOPT-R01", "QAOPT-E06"]),
    "OBJECT-MISMATCH": ("回答对象不匹配", ["QAOPT-R03", "QAOPT-E02"]),
    "GROUNDING-GUARD": ("事实守卫误拒或校验错误", ["QAOPT-E03"]),
    "STAT-SIGNIFICANCE": ("统计显著性判断无依据", ["QAOPT-E04", "QAOPT-E06"]),
    "UNRESOLVED-MAPPING": ("点位语义未解析", ["QAOPT-R03"]),
    "AMBIGUOUS-INPUT": ("歧义输入处理不当", ["QAOPT-R01"]),
    "ERROR-DETAIL": ("错误说明缺少可定位信息", ["QAOPT-O02", "QAOPT-O04"]),
    "SAFETY-REFUSAL": ("正常任务被安全策略误拒", ["QAOPT-R08"]),
    "UNSUPPORTED-INTERNAL-RULE": ("内部制度主张缺少依据", ["QAOPT-K04"]),
    "KNOWLEDGE-ORIGINAL-MISSING": ("缺少所需知识原文", ["QAOPT-K01", "QAOPT-K03"]),
    "UNSUPPORTED-LIVE-CLAIM": ("现场断言超出数据支持", ["QAOPT-E02", "QAOPT-E03"]),
    "KNOWLEDGE-ORIGINAL-PARAPHRASE": ("原文请求被改写", ["QAOPT-K03", "QAOPT-E05"]),
    "KNOWLEDGE-TRUNCATED": ("知识原文被截断", ["QAOPT-K03", "QAOPT-E05"]),
    "KNOWLEDGE-ANSWER-QUALITY": ("知识答案质量或针对性不足", ["QAOPT-K01", "QAOPT-K03", "QAOPT-E05"]),
    "MISSING-UNIT": ("数值缺单位", ["QAOPT-E02", "QAOPT-E03"]),
    "ANSWER-CONTRACT": ("最终答案不满足要求", ["QAOPT-E05"]),
}


def read(name):
    data = (OUT / name).read_bytes()
    INPUT_BYTES[name] = data
    return json.loads(data.decode("utf-8-sig"))


def write(name, content):
    (OUT / name).write_bytes(content.encode("utf-8"))


def main():
    semantic = read("initial_semantic_summary_20260917.json")
    original = read("question_ledger_20260916.json")
    historic = read("issue_statistics_20260916.json")
    execution = read("optimization_execution_ledger_20260916.json")
    catalog = read("optimization_issue_catalog_20260916.json")
    runtime = read("runtime_readonly_snapshot_20260917.json")
    by_id = {row["case_id"]: row for row in semantic["rows"]}
    assert len(by_id) == len(semantic["rows"]) == semantic["valid_collected"] == 1233
    assert len({row["case_id"] for row in original["rows"]}) == len(original["rows"]) == 1418
    counts = Counter(row["status"] for row in by_id.values())
    assert dict(counts) == semantic["counts"]
    assert sum(counts.values()) == 1233 == 1259 - 26
    assert counts["passed"] + counts["partial"] + counts["failed"] == 1091
    assert counts["partial"] + counts["failed"] == 822
    assert counts["oracle_blocked"] + counts["insufficient_evidence"] == 142
    categories = {}
    for category in semantic["category_counts"]:
        actual = Counter(r["status"] for r in by_id.values() if r["category"] == category)
        assert dict(actual) == semantic["category_counts"][category]
        categories[category] = dict(actual)
    issue_ids = {r["issue_id"] for r in execution["rows"]}
    assert len(issue_ids) == 33 == len(catalog["issues"])
    extra_tags = Counter(tag for r in by_id.values() for tag in r["issue_ids"] if tag not in issue_ids)
    review_tags = []
    for tag, count in extra_tags.items():
        key = tag.removeprefix("BUG-QA-SEM-").rsplit("-", 1)[0]
        title, mapping = SEMANTIC_MAPPING[key]
        affected = [r for r in by_id.values() if tag in r["issue_ids"]]
        review_tags.append({"tag": tag, "title": title, "cases": count,
                            "counts": dict(Counter(r["status"] for r in affected)),
                            "proposed_issue_ids": mapping,
                            "case_ids": [r["case_id"] for r in affected]})
    rows = []
    for source in original["rows"]:
        reviewed = by_id.get(source["case_id"])
        if reviewed:
            assert source["collection_status"] == "collected"
            assert source["result_sha256"] == reviewed["original_result_sha256"]
        final_state = reviewed["status"] if reviewed else source["answer_review_status"]
        if not reviewed and source["collection_status"] != "collected":
            final_state = "not_scored_" + source["collection_status"]
        rows.append({
            "case_id": source["case_id"], "source_path": source["source_path"],
            "source_line": source["source_line"], "category": source["category"],
            "source_status": source["source_status"], "collection_status": source["collection_status"],
            "final_initial_judgment": final_state, "duplicate_of": source.get("duplicate_of"),
            "issue_ids": reviewed["issue_ids"] if reviewed else source.get("issue_ids", []),
            "result_sha256": source.get("result_sha256"),
            "original_prompt_sha256": reviewed.get("original_prompt_sha256") if reviewed else None,
        })
    unknown = [r["case_id"] for r in rows if r["collection_status"] == "interrupted_unknown"]
    assert unknown == semantic["sent_unknown_never_replay"]
    assert sum(r["final_initial_judgment"] == "oracle_invalid_structural_line" for r in rows) == 26
    missing_mapping = [r["case_id"] for r in by_id.values()
                       if r["status"] in {"failed", "partial"} and not r["issue_ids"]]
    issues = []
    for row in execution["rows"]:
        linked = [r for r in by_id.values() if row["issue_id"] in r["issue_ids"]]
        issues.append({"issue_id": row["issue_id"], "priority": row["priority"], "title": row["title"],
                       "ledger_state": row["state"], "initial_linked_counts": dict(Counter(r["status"] for r in linked)),
                       "linked_case_count": len(linked), "next_gate": row["next_gate"]})
    inputs = ["initial_semantic_summary_20260917.json", "question_ledger_20260916.json",
              "issue_statistics_20260916.json", "optimization_execution_ledger_20260916.json",
              "optimization_issue_catalog_20260916.json", "runtime_readonly_snapshot_20260917.json"]
    summary = {
        "schema": "bf.qa.verified-inventory.v1", "checked_date": "2026-09-17",
        "requirement_id": semantic["requirement_id"],
        "input_sha256": {f: hashlib.sha256(INPUT_BYTES[f]).hexdigest() for f in inputs},
        "source_files": historic["source_files"], "source_rows": len(rows),
        "source_status": historic["source_status"], "collection": historic["collection"],
        "valid_collected": len(by_id), "counts": dict(counts), "category_counts": categories,
        "issue_states_from_execution_ledger": dict(Counter(r["state"] for r in execution["rows"])),
        "priorities": dict(Counter(r["priority"] for r in execution["rows"])),
        "failed_or_partial_without_issue_mapping": missing_mapping,
        "semantic_review_tags": review_tags,
        "semantic_mapping_status": "proposed_triage_mapping_not_causal_attribution",
        "issue_links_are_not_root_cause_attribution": True,
        "latest_runtime": runtime, "issues": issues, "rows": rows,
    }
    assert all((OUT/f).read_bytes() == INPUT_BYTES[f] for f in inputs), "Input changed during reconciliation"
    write("verified_inventory_20260917.json", json.dumps(summary, ensure_ascii=False, indent=2)+"\n")
    buffer = io.StringIO(newline="")
    writer = csv.DictWriter(buffer, fieldnames=list(rows[0]), lineterminator="\n")
    writer.writeheader()
    for row in rows:
        record = dict(row)
        record["issue_ids"] = ";".join(record["issue_ids"])
        writer.writerow({k: ("'"+v if isinstance(v, str) and v[:1] in "=+-@" else v)
                         for k,v in record.items()})
    write("verified_question_ledger_20260917.csv", buffer.getvalue())
    lines = ["# 逐项问题与执行验收补充清单", "", "状态：2026-09-17 核对版；不是修复完成证明。",
             "权威来源：最终首次语义统计、33 项机器目录、执行台账和当日只读运行快照。",
             "本文件由 tools/build_qa_verified_inventory_20260917.py 生成。所有计数是可重叠关联，不是根因贡献。",
             "当前生产 V26 复测发送 0；下列状态按输入台账快照保留，不自动升级为全量通过。",
             "", f"失败或部分正确但尚无问题编号映射：{len(missing_mapping)} 题；须先补根因归类，不能按已分类直接销项。", ""]
    plans = {r["id"]: r for r in catalog["issues"]}
    for issue, runtime_row in zip(issues, execution["rows"]):
        plan = plans[issue["issue_id"]]
        actions = list(plan["required_changes"])
        checks = list(plan["acceptance_checks"])
        tests = list(plan["regression_tests"])
        if issue["issue_id"] == "QAOPT-O01":
            actions = ["批准的模型版本以 digest 固定；问答与模型管理共享租约，防止健康检查后被切换。",
                       "只在确需生成时检查模型；确定性已有数据路径仍能回答。",
                       "维持全服务独占，不排队；身份变化后停止下一发送，不重放当前请求。"]
            tests = ["健康探测后模型卸载或 alias 改变；预取成功后生成失败；确定性路径无模型。"]
        if issue["issue_id"] == "QAOPT-O05":
            actions = ["全服务只允许一个问答 owner；并发请求立即 409，不排队。",
                       "只有实际任务结束才释放独占；断开读取不等于后台取消。",
                       "保留 guest/operator/admin 能力差异、owner 隔离和同源校验。"]
            checks = ["真实双角色同时发送：一个被接纳，另一个 409；没有隐式重试。",
                      "取消后确认工具/生成已停止，再允许下一请求；跨 owner 数据泄漏为 0。"]
            tests = ["双角色并发、同会话多窗口、认证过期、取消中断、异常清理。"]
        if issue["issue_id"] == "QAOPT-R03":
            actions += ["对象在路由、工具、图表、最终答案四层核对；18 个点不得静默缩为 16 个。"]
        if issue["issue_id"] in {"QAOPT-E01", "QAOPT-E05", "QAOPT-O03"}:
            checks += ["完整 JSON 与模型摘要分开，工具成功后连接清理失败仍返回已验证数据和可用图表。"]
        if issue["issue_id"] == "QAOPT-T04":
            actions = ["保留首次 1233 题最终判定；822 个失败/部分题做新版配对复测。",
                       "269 个首次正确题作为防退化集合；142 个未定题先补依据。",
                       "持出集与关键 pass^5 使用独立评估 ID；不得冒充断线后的自动重发。"]
        lines += [f"## {issue['issue_id']} · {issue['title']}", "",
                  f"- 优先级：{issue['priority']}；台账状态：`{issue['ledger_state']}`。",
                  f"- 首次关联判定：`{json.dumps(issue['initial_linked_counts'], ensure_ascii=False)}`；空值表示尚无关联统计，不表示没有风险。",
                  f"- 已有证据：{runtime_row['evidence']}",
                  f"- 下一验收关口：{runtime_row['next_gate']}",
                  f"- 依赖：{', '.join(runtime_row['depends_on']) or '无'}。", "", "实施核对：", ""]
        lines += [f"- [ ] {action}" for action in actions]
        lines += ["", "验收核对：", ""] + [f"- [ ] {check}" for check in checks]
        lines += ["", "回归场景：", ""] + [f"- {test}" for test in tests]
        lines += ["", "销项材料：", "", "- [ ] 原失败 case_id、输入/输出 hash、错误步骤和根因。",
                  "- [ ] 修改 commit、实际 Prompt/tool schema/数据快照版本和影响范围。",
                  "- [ ] 正常例、反例、缺数/超时例；独立最终答案检查与数值复算。",
                  "- [ ] 线上同版本证据或明确待验收；不能仅凭非空、单测或部署记录销项。", ""]
    write("verified_optimization_checklist_20260917.md", "\n".join(lines))
    tag_lines = ["# 全题核对与补充语义问题统计", "", "状态：2026-09-17 冻结输入派生统计；多标签不能相加。",
                 "来源：initial_semantic_summary_20260917.json；输入哈希见 verified_inventory_20260917.json。",
                 "语义审核标签是答案缺陷，不代表已经证明其底层代码根因；映射仅作为后续排查入口。", "",
                 "|语义标签|问题|关联题数|判定分布|建议对应整改项|", "|---|---|---:|---|---|"]
    for tag in review_tags:
        tag_lines.append(f"|{tag['tag']}|{tag['title']}|{tag['cases']}|{json.dumps(tag['counts'], ensure_ascii=False)}|{', '.join(tag['proposed_issue_ids'])}|")
    tag_lines += ["", "## 尚缺根因标签的失败/部分题", "",
                  "以下题已有语义判定，但无问题标签；保留未归类状态，不擅自推断根因。", "",
                  "|case_id|类别|判定|来源行|", "|---|---|---|---|"]
    for case_id in missing_mapping:
        row = by_id[case_id]
        tag_lines.append(f"|{case_id}|{row['category']}|{row['status']}|{row['source_path']}:{row['source_line']}|")
    write("semantic_issue_crosswalk_20260917.md", "\n".join(tag_lines)+"\n")
    print(json.dumps({"ok": True, "rows": len(rows), "valid": len(by_id), "counts": counts,
                      "unmapped_failed_or_partial": len(missing_mapping),
                      "priorities": summary["priorities"], "issue_states": summary["issue_states_from_execution_ledger"],
                      "review_tags": [{k:v for k,v in r.items() if k!='case_ids'} for r in review_tags]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
