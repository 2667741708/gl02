"""Build a public per-source QA ledger from private read-only snapshots.
No answers, tool arguments, server identities or production values are exported.
"""
from __future__ import annotations
import argparse,base64,csv,hashlib,io,json,math,re,zlib
from collections import Counter
from pathlib import Path

UNKNOWN="TPL-10C8C8FAF2C694EF"
ISSUE_MAP={
 "lifecycle_error":["QAOPT-E01","QAOPT-O02"],
 "no_answer":["QAOPT-O01"],
 "no_code_response":["QAOPT-R08"],
 "realtime_refusal":["QAOPT-K01"],
 "knowledge_history_tool":["QAOPT-K02"],
 "knowledge_test_marker_search":["QAOPT-K02","QAOPT-T02"],
 "knowledge_report_tool":["QAOPT-K05"],
 "knowledge_report_directory_answer":["QAOPT-K05"],
 "knowledge_sensor_or_chart_tool":["QAOPT-R01","QAOPT-K01"],
 "knowledge_no_document_capability":["QAOPT-R09"],
 "success_then_lifecycle_error":["QAOPT-E01"],
 "tool_timeout":["QAOPT-O02"],
 "tool_error":["QAOPT-O02"],
 "fallback_failed_route":["QAOPT-E01"],
 "guard_rejected_route":["QAOPT-E03"],
 "structural_arrow":["QAOPT-T02"],
 "incomplete_json":["QAOPT-E05"],
}
NEW_REVIEWS={
"TPL-DFBF6ECA9F77E4A1":["QAOPT-E01","QAOPT-K01"],
"TPL-312365E3836A63CF":["QAOPT-E01","QAOPT-K01"],
"TPL-2941ED6E73448D66":["QAOPT-K02","QAOPT-T02"],
"TPL-B1DDFC78E40D26DD":["QAOPT-K03"],
"TPL-48827B99541672E2":["QAOPT-K01"],
"TPL-9AB9414BFC82E504":["QAOPT-K01"],
"TPL-11F6C2E3DDD207BC":["QAOPT-R01"],
"TPL-DE3A348E8836BC03":["QAOPT-R01"],
"TPL-740647EE648698B0":["QAOPT-K04"],
"TPL-00D19D36ED184B7C":["QAOPT-R09"],
"TPL-3FE672D48EEF6AA0":["QAOPT-K04"],
"TPL-81261F34B14214DC":["QAOPT-K03","QAOPT-K04"],
"TPL-0EDF300C940987EB":["QAOPT-K05"],
}
def json_read(path):return json.loads(path.read_text(encoding="utf-8"))
def write_json(path,data):path.write_bytes((json.dumps(data,ensure_ascii=False,indent=2)+"\n").encode())
def percentile(values,q):return sorted(values)[max(0,math.ceil(len(values)*q)-1)] if values else None
def flags(row,source):
    answer=row.get("answer") or ""
    tools=row.get("tool_starts") or []
    names={t.get("tool","") for t in tools}
    knowledge=source.get("category")=="knowledge"
    out=[]
    if not answer:out.append("no_answer")
    if answer=="数据库查询失败：MCP请求生命周期异常":out.append("lifecycle_error")
    if answer.startswith("当前暂不提供代码"):out.append("no_code_response")
    if answer.startswith("实时数据库未核实："):out.append("realtime_refusal")
    if row.get("route")=="model_without_tools_after_mcp_failure_failed":out.append("fallback_failed_route")
    if row.get("route")=="grounding_guard_rejected":out.append("guard_rejected_route")
    if source.get("prompt","").startswith("→"):out.append("structural_arrow")
    error_text=json.dumps([t.get("result") for t in row.get("tools",[])],ensure_ascii=False)
    if "TimeoutError" in error_text:out.append("tool_timeout")
    if any(t.get("result",{}).get("error") or t.get("result",{}).get("error_type") or t.get("result",{}).get("ok") is False for t in row.get("tools",[])):out.append("tool_error")
    if "lifecycle_error" in out and any(t.get("result",{}).get("ok") is True for t in row.get("tools",[])):out.append("success_then_lifecycle_error")
    if answer.lstrip().startswith("{"):
        try:json.loads(answer)
        except json.JSONDecodeError:out.append("incomplete_json")
    if knowledge:
        if "search_qa_messages" in names:out.append("knowledge_history_tool")
        if any(t.get("tool")=="search_qa_messages" and ("回归基线" in json.dumps(t.get("arguments"),ensure_ascii=False) or "TPL-" in json.dumps(t.get("arguments"),ensure_ascii=False)) for t in tools):out.append("knowledge_test_marker_search")
        if names & {"list_recent_reports","read_report_excerpt"}:out.append("knowledge_report_tool")
        if answer.startswith("受控报表目录"):out.append("knowledge_report_directory_answer")
        if any(n.startswith(("query_gl02","get_latest_gl02","plot_gl02","imes__")) or n=="get_latest_furnace_snapshot" for n in names):out.append("knowledge_sensor_or_chart_tool")
        if "没有该文档" in answer or "没有文档" in answer or "没有该文件" in answer:out.append("knowledge_no_document_capability")
    return out

def build(root,private_dir,output):
    parts=[json.loads(zlib.decompress(base64.b64decode(p.read_bytes()))) for p in sorted(private_dir.glob("chunk-*.b64"))]
    assert parts,"No snapshots"
    rows=[r for p in parts for r in p["rows"]]
    by_result={r["case_id"]:r for r in rows}
    assert len(rows)==len(by_result),"Duplicate results"
    assert [p["offset"] for p in parts]==list(range(0,parts[-1]["offset"]+1,100)),"Snapshot gap"
    assert len(rows)==parts[-1]["available"],"Incomplete snapshot extraction"
    assert all(len(p["rows"])==100 for p in parts[:-1]),"Short middle chunk"
    inventory=json_read(root/"tests/qa_regression/templates.v1.json")
    sources=inventory["rows"]
    by_source={r["case_id"]:r for r in sources}
    assert len(sources)==len(by_source)
    assert set(by_result)<=set(by_source)
    assert all(by_source[k]["source_status"]=="ready" for k in by_result)
    assert all(r.get("automatic_retries")==0 for r in rows)
    assert all(r.get("request_count")==1 for r in rows)
    assert all(r.get("terminated") for r in rows)
    assert UNKNOWN not in by_result
    reviews=json_read(root/"tests/qa_regression/routing_failures_20260915.json")["reviews"]
    guard_reviews=json_read(root/"tests/qa_regression/no_code_review_20260916.json")["reviews"]
    for review in guard_reviews:
        assert by_result[review["case_id"]]["answer_sha256"]==review["answer_sha256"],"Reviewed answer changed"
    manual={r["case_id"] for r in reviews} | set(NEW_REVIEWS) | {r["case_id"] for r in guard_reviews}
    catalog=json_read(root/"tests/qa_regression/optimization_issue_catalog_20260916.json")
    issue_ids={i["id"] for i in catalog["issues"]}
    assert all(set(i["depends_on"])<=issue_ids for i in catalog["issues"])
    case_issues={}
    for issue in catalog["issues"]:
        for case in issue["case_ids"]:
            assert case in by_source
            case_issues.setdefault(case,set()).add(issue["id"])
    for case,ids in NEW_REVIEWS.items():case_issues.setdefault(case,set()).update(ids)
    for review in guard_reviews:case_issues.setdefault(review["case_id"],set()).update(review["issue_ids"])
    ledger=[]
    for src in sources:
        cid=src["case_id"];r=by_result.get(cid)
        signals=flags(r,src) if r else []
        if r:collection="collected"
        elif cid==UNKNOWN:collection="interrupted_unknown"
        elif src["source_status"]=="ready":collection="pending_collection"
        else:collection=src["source_status"]
        detected_failure=bool(r) and ("lifecycle_error" in signals or "no_answer" in signals or (src.get("category")=="knowledge" and ("no_code_response" in signals or ("realtime_refusal" in signals and len(r.get("answer") or "")<260))))
        if "structural_arrow" in signals:review="oracle_invalid_structural_line"
        elif cid in manual:review="confirmed_failed_manual"
        elif detected_failure:review="confirmed_failed_fixed_response"
        elif r:review="pending_semantic_review"
        else:review="not_reviewed"
        ids=set(case_issues.get(cid,set()))
        for flag in signals:
            for issue in ISSUE_MAP.get(flag,[]):
                if flag!="realtime_refusal" or src.get("category")=="knowledge":ids.add(issue)
        item={k:src.get(k) for k in ("case_id","source_path","source_line","prompt","kind","source_status","category","duplicate_of","skip_reason")}
        item.update(category=src.get("category","other"),collection_status=collection,answer_review_status=review,
                    route=r.get("route") if r else None,seconds=r.get("seconds") if r else None,
                    tool_call_count=r.get("tool_calls",0) if r else None,
                    actual_tools=sorted({t.get("tool") for t in r.get("tool_starts",[])}) if r else [],
                    answer_chars=len(r.get("answer") or "") if r else None,
                    result_sha256=r.get("result_sha256") if r else None,
                    evidence_flags=signals,issue_ids=sorted(ids))
        ledger.append(item)
    by_case={r["case_id"]:r for r in ledger}
    for r in ledger:
        if r["duplicate_of"]:
            assert r["duplicate_of"] in by_case
            r["reuses_collection_status"]=by_case[r["duplicate_of"]]["collection_status"]
            r["reuses_review_status"]=by_case[r["duplicate_of"]]["answer_review_status"]
    counts=Counter(r["collection_status"] for r in ledger)
    assert sum(counts.values())==len(sources)==1418
    assert counts["collected"]+counts["pending_collection"]+counts["interrupted_unknown"]==inventory["counts"]["ready"]
    groups={}
    for key in ("knowledge","nonknowledge"):
        group=[r for r in ledger if (r["category"]=="knowledge")== (key=="knowledge")]
        done=[r for r in group if r["collection_status"]=="collected"]
        vals=[r["seconds"] for r in done]
        groups[key]={"source_rows":len(group),"source_status":dict(Counter(r["source_status"] for r in group)),
                     "collection":dict(Counter(r["collection_status"] for r in group)),
                     "review":dict(Counter(r["answer_review_status"] for r in done)),
                     "routes":dict(Counter(r["route"] or "no_final_route" for r in done)),
                     "tool_cases":sum(r["tool_call_count"]>0 for r in done),
                     "tool_calls":sum(r["tool_call_count"] for r in done),
                     "flags":dict(Counter(f for r in done for f in r["evidence_flags"])),
                     "latency":{"p50":percentile(vals,.5),"p95":percentile(vals,.95),"max":max(vals) if vals else None}}
    vals=[r["seconds"] for r in rows]
    tool_errors=Counter()
    for r in rows:
        for t in r["tools"]:
            result=t["result"]
            err=result.get("error_type") or result.get("error")
            if err:tool_errors[str(err) if isinstance(err,str) and re.fullmatch(r"[A-Za-z_][A-Za-z_0-9]{0,70}",err) else "OTHER_ERROR"]+=1
    summary={"schema":"bf.qa.full-inventory.v1","requirement_id":"REQ-QA-FULL-ISSUE-INVENTORY-20260916",
        "checked_at":parts[-1]["checked_at"],"status":"collection_in_progress" if counts["pending_collection"] else "collection_accounted_pending_answer_review",
        "source_rows":len(sources),"source_files":len(inventory["sources"]),
        "source_status":inventory["counts"],"collection":dict(counts),
        "contract_only_kinds":dict(Counter(r["kind"] for r in sources if r["source_status"]=="contract_only")),
        "review":dict(Counter(r["answer_review_status"] for r in ledger)),
        "collected":len(rows),"nonempty":sum(bool(r["answer"]) for r in rows),
        "overall_accuracy":None,"groups":groups,
        "routes":dict(Counter(r.get("route") or "no_final_route" for r in rows)),
        "flags":dict(Counter(f for r in ledger for f in r["evidence_flags"])),
        "tool_calls":sum(r["tool_calls"] for r in rows),
        "tool_name_counts":dict(Counter(t["tool"] for r in rows for t in r["tool_starts"])),
        "tool_error_counts":dict(tool_errors),
        "latency":{"p50":percentile(vals,.5),"p95":percentile(vals,.95),"max":max(vals)},
        "latency_scope":"raw collection including structural oracle-invalid rows; not cleaned valid-task performance",
        "manual_failure_cases":sorted(manual),
        "missing_sources":[s["path"] for s in inventory["sources"] if s["status"]=="missing"],
        "issue_coverage":[{"id":i["id"],"priority":i["priority"],"evidence_state":i["evidence_state"],"title":i["title"],
                           "linked_cases":sum(i["id"] in r["issue_ids"] for r in ledger),
                           "confirmed_failed_cases":sum(i["id"] in r["issue_ids"] and r["answer_review_status"].startswith("confirmed_failed") for r in ledger)}
                          for i in catalog["issues"]],
        "unmeasured":["whole-answer semantic accuracy","knowledge original-text coverage","all claims fidelity","tool/parameter exact-match with reviewed gold","pass^5","six-user concurrency","guest/operator/admin parity","TTFT and token cost","all raw-series independent statistics"],
        "private_input_sha256":hashlib.sha256(json.dumps(rows,ensure_ascii=False,sort_keys=True).encode()).hexdigest(),
        "counting_rules":["counts are not accuracy","flags overlap","tool errors count calls, not cases","duplicate sources do not generate requests","fixed-response failures do not determine underlying root cause","other collected cases require semantic review"]}
    output.mkdir(parents=True,exist_ok=True)
    write_json(output/"issue_statistics_20260916.json",summary)
    write_json(output/"question_ledger_20260916.json",{"schema":"bf.qa.question-ledger.v1","checked_at":summary["checked_at"],"rows":ledger})
    buf=io.StringIO(newline="")
    fields=list(ledger[0])
    fields+=["reuses_collection_status","reuses_review_status"]
    writer=csv.DictWriter(buf,fieldnames=fields,lineterminator="\n");writer.writeheader()
    for row in ledger:
        rendered={k:(";".join(v) if isinstance(v,list) else v) for k,v in row.items()}
        for k,v in rendered.items():
            if isinstance(v,str) and v.startswith(("=","+","-","@")):rendered[k]="'"+v
        writer.writerow(rendered)
    (output/"question_ledger_20260916.csv").write_bytes(buf.getvalue().encode("utf-8"))
    write_json(private_dir/"all-results.private.json",rows)
    report=render_report(summary,catalog,ledger)
    (output/"issue_statistics_20260916.md").write_bytes(report.encode())
    print(json.dumps({k:v for k,v in summary.items() if k not in ("manual_failure_cases","tool_name_counts","issue_coverage","groups")},ensure_ascii=False))
    return summary,ledger

def render_report(s,catalog,ledger):
    lines=["# 全来源问题统计与逐题台账","",
      "- 状态："+s["status"]+"；仅统计与方案，未修改生产路由。",
      "- 核对时间："+s["checked_at"]+"（Asia/Shanghai）。",
      "- 需求：REQ-QA-FULL-ISSUE-INVENTORY-20260916。",
      "- 权威来源：只读提取的线上结果、模板索引及定向答案审阅；原始回答与参数留在私有目录。",
      "- [逐题CSV](question_ledger_20260916.csv) / [逐题JSON](question_ledger_20260916.json) / [统计JSON](issue_statistics_20260916.json) / [逐项整改方案](optimization_checklist_20260916.md)。",
      "- [运行版本与批次结束核验](audit_runtime_20260916.json)、[48条正常问题被禁代码误拒审阅](no_code_review_20260916.json)。","",
      "## 分母与完成状态","",
      "|项目|数量|","|---|---:|",f"|来源文件登记|{s['source_files']}|",f"|来源条目|{s['source_rows']}|"]
    for k,v in s["source_status"].items():lines.append(f"|来源状态 {k}|{v}|")
    for k,v in s["collection"].items():lines.append(f"|收集状态 {k}|{v}|")
    lines+=["","知识来源833行=818条独立ready题+15条重复来源。1260是导入ready数，包含结构说明误导入；不是清洗后有效问题分母。84条contract_only包括31条用户输入合同、40个代码块、13个系统模板，不能全部按普通用户问题发送。","",
       "## 内容审阅状态","",
       "|状态|数量|","|---|---:|"]
    for k,v in s["review"].items():lines.append(f"|{k}|{v}|")
    lines+=["","confirmed_failed_manual来自定向独立审阅；confirmed_failed_fixed_response来自明确无答案/生命周期固定错误/知识题误拒。两者互斥。其他已收集结果仍待全文语义审阅，绝不能计为通过。oracle_invalid_structural_line从正式正确率分母排除，但保留执行事实；本表延迟仍为包含误导入行的原始采集耗时，不是清洗后有效任务性能。","",
      "## 知识与其他题分别统计","",
      "|分组|来源条目|已收集|含工具题数|工具调用次数|p50秒|p95秒|","|---|---:|---:|---:|---:|---:|---:|"]
    for k,g in s["groups"].items():lines.append(f"|{k}|{g['source_rows']}|{g['collection'].get('collected',0)}|{g['tool_cases']}|{g['tool_calls']}|{g['latency']['p50']}|{g['latency']['p95']}|")
    lines+=["","## 可复算的诊断信号（可重叠，不是互斥失败分类）","","这些信号也包含合理拒绝等情况，不全部代表错误；具体失败看独立审阅和任务合同。","","|信号|题数|","|---|---:|"]
    for k,v in s["flags"].items():lines.append(f"|{k}|{v}|")
    lines+=["","## 工具错误（按调用计数）","","|错误|次数|","|---|---:|"]
    for k,v in s["tool_error_counts"].items():lines.append(f"|{k}|{v}|")
    lines+=["","## 路由分布（不能直接当通过率）","","|路由|总计|知识|其他|","|---|---:|---:|---:|"]
    for k,v in s["routes"].items():lines.append(f"|{k}|{v}|{s['groups']['knowledge']['routes'].get(k,0)}|{s['groups']['nonknowledge']['routes'].get(k,0)}|")
    lines+=["","## 整改事项覆盖","","linked_cases包括确认缺陷、风险信号和回归范围，不能解释为该根因已确认影响的数量。","",
      "|编号|优先级|事项|证据状态|关联题数|关联已确认失败|","|---|---|---|---|---:|---:|"]
    for i in s["issue_coverage"]:lines.append(f"|{i['id']}|{i['priority']}|{i['title']}|{i['evidence_state']}|{i['linked_cases']}|{i['confirmed_failed_cases']}|")
    pending=[r for r in ledger if r["collection_status"] in ("pending_collection","interrupted_unknown")]
    lines+=["","## 未完成及未知状态逐项","","|问题ID|状态|来源行|","|---|---|---|"]
    for r in pending:lines.append(f"|{r['case_id']}|{r['collection_status']}|{r['source_path']}:{r['source_line']}|")
    lines+=["","## 未测项与依赖阻断",""]
    lines += ["- "+x for x in s["unmeasured"]]
    lines += ["- 缺失来源："+x for x in s["missing_sources"]]
    lines+=["- 13个系统模板仍需按真实入口绑定；7条fixture_only需隔离候选执行；不把结构验证称为线上通过。","",
      "## 复现与校验","",
      "先通过Reliable SSH只读执行 tools/collect_qa_audit_snapshot.py，每100条保存一个私有压缩片段；不上传远端脚本，不发送问答。",
      "本机运行：python -X utf8 tools/build_qa_issue_inventory.py --private-dir .codex_runtime/qa-live/full-audit-20260916。",
      "生成器验证无重复结果、片段连续、来源映射、每题一次请求、无重放、分母恒等式、重复指向及事项依赖。","",
      "原始证据未修改；路由/模型/服务未改变。统计快照不是最终答案审阅冻结。",""]
    return "\n".join(lines)

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--root",type=Path,default=Path(__file__).resolve().parents[1])
    p.add_argument("--private-dir",type=Path,required=True)
    a=p.parse_args()
    build(a.root,a.private_dir,a.root/"tests/qa_regression")
if __name__=="__main__":main()
