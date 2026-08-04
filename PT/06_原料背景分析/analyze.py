from __future__ import annotations
import argparse,csv,json,statistics
from datetime import datetime,timedelta
from pathlib import Path
HERE=Path(__file__).resolve().parent
def dt(v):return datetime.fromisoformat(v.replace("T"," "))
def n(v):
    try:return float(v)
    except (TypeError,ValueError):return None
def main():
    cfg=json.loads((HERE/"config.json").read_text(encoding="utf-8"));p=argparse.ArgumentParser(description="炉次原料时间背景分析")
    p.add_argument("--heats",required=True);p.add_argument("--sinter",required=True);p.add_argument("--lookback-hours",type=int,default=cfg["lookback_hours"]);p.add_argument("--output-dir",default=str(HERE/"results"));a=p.parse_args()
    heats=list(csv.DictReader(open(a.heats,encoding="utf-8-sig",newline="")));samples=list(csv.DictReader(open(a.sinter,encoding="utf-8-sig",newline="")))
    sample_pairs=[(dt(r["sample_ts"]),r) for r in samples if r.get("sample_ts")];output=[]
    for h in heats:
        if not h.get("open_ts"):continue
        end=dt(h["open_ts"]);start=end-timedelta(hours=a.lookback_hours);matched=[r for ts,r in sample_pairs if start<=ts<end]
        row={"meltno":h.get("meltno"),"open_ts":h["open_ts"],"window_start":start.isoformat(sep=" "),"sample_count":len(matched),"mapping_method":"time_context_only","confidence":"low"}
        for col in cfg["chemistry_columns"]:
            vals=[n(r.get(col)) for r in matched];vals=[x for x in vals if x is not None];row[f"{col}_median"]=statistics.median(vals) if vals else ""
        output.append(row)
    out=Path(a.output_dir);out.mkdir(parents=True,exist_ok=True);fields=list(output[0]) if output else ["meltno"]
    with open(out/"heat_raw_material_context.csv","w",encoding="utf-8-sig",newline="") as f:w=csv.DictWriter(f,fieldnames=fields);w.writeheader();w.writerows(output)
    report={"heat_rows":len(output),"sinter_rows":len(samples),"lookback_hours":a.lookback_hours,"boundary":"仅时间背景；未贯通料仓、批次和炉次谱系"}
    (out/"summary.json").write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding="utf-8");print(json.dumps(report,ensure_ascii=False))
if __name__=="__main__":main()
