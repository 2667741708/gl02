from __future__ import annotations
import argparse, csv, json
from datetime import datetime, timedelta
from pathlib import Path

HERE = Path(__file__).resolve().parent
def dt(v): return datetime.fromisoformat(v.replace("T"," ")) if v else None
def num(v):
    try: return float(v)
    except (TypeError, ValueError): return None

def main():
    p=argparse.ArgumentParser(description="构建并审计炉次级数据集")
    p.add_argument("--input",required=True); p.add_argument("--output-dir",default=str(HERE/"results"))
    a=p.parse_args(); out=Path(a.output_dir); out.mkdir(parents=True,exist_ok=True)
    cfg=json.loads((HERE/"config.json").read_text(encoding="utf-8"))
    rows=list(csv.DictReader(open(a.input,encoding="utf-8-sig",newline="")))
    seen=set(); clean=[]; issues=[]; now=datetime.now()
    for r in rows:
        key=r.get("meltno","").strip(); op=dt(r.get("open_ts","")); cl=dt(r.get("close_ts",""))
        reasons=[]
        if not key: reasons.append("missing_meltno")
        if key in seen: reasons.append("duplicate_meltno")
        seen.add(key)
        if not op: reasons.append("missing_open_ts")
        if not cl: reasons.append("missing_close_ts")
        duration=(cl-op).total_seconds()/60 if op and cl else None
        if duration is not None and duration < 0: reasons.append("negative_duration")
        if duration is not None and duration > cfg["max_duration_minutes"]: reasons.append("duration_too_long")
        if op and op > now+timedelta(minutes=cfg["future_tolerance_minutes"]): reasons.append("future_open_ts")
        item={**r,"duration_minutes":round(duration,2) if duration is not None else ""}
        clean.append(item)
        if reasons: issues.append({"meltno":key,"reasons":";".join(reasons)})
    fields=list(clean[0]) if clean else ["meltno"]
    with open(out/"heat_dataset.csv","w",encoding="utf-8-sig",newline="") as f:
        w=csv.DictWriter(f,fieldnames=fields); w.writeheader(); w.writerows(clean)
    with open(out/"quality_issues.csv","w",encoding="utf-8-sig",newline="") as f:
        w=csv.DictWriter(f,fieldnames=["meltno","reasons"]); w.writeheader(); w.writerows(issues)
    iron=[num(r.get("actual_iron_qty")) for r in clean]; iron=[x for x in iron if x is not None]
    summary={"rows":len(clean),"unique_heats":len(seen),"issue_rows":len(issues),"iron_total":round(sum(iron),3)}
    (out/"summary.json").write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding="utf-8")
    print(json.dumps(summary,ensure_ascii=False))
if __name__=="__main__": main()
