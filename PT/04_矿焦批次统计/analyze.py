from __future__ import annotations
import argparse,csv,json
from collections import defaultdict
from pathlib import Path
HERE=Path(__file__).resolve().parent
def n(v):
    try:return float(v)
    except (TypeError,ValueError):return 0.0
def main():
    cfg=json.loads((HERE/"config.json").read_text(encoding="utf-8"));p=argparse.ArgumentParser(description="矿焦批次统计")
    p.add_argument("--input",required=True);p.add_argument("--furnace",default=cfg["furnace"]);p.add_argument("--output-dir",default=str(HERE/"results"));a=p.parse_args()
    rows=list(csv.DictReader(open(a.input,encoding="utf-8-sig",newline="")));rows=[r for r in rows if r.get("prodcentercode")==a.furnace]
    agg=defaultdict(lambda:{"矿批_count":0,"矿批_sum":0.0,"焦批_count":0,"焦批_sum":0.0})
    for r in rows:
        day=r.get(cfg["date_column"],"")[:10]; label=r.get(cfg["charge_column"]); value=n(r.get(cfg["value_column"]))
        if label in (cfg["ore_label"],cfg["coke_label"]):agg[day][f"{label}_count"]+=1;agg[day][f"{label}_sum"]+=value
    output=[]
    for day,x in sorted(agg.items()):
        coke=x["焦批_sum"];output.append({"date":day,**{k:round(v,6) for k,v in x.items()},"ore_coke_ratio":round(x["矿批_sum"]/coke,6) if coke else None})
    out=Path(a.output_dir);out.mkdir(parents=True,exist_ok=True)
    with open(out/"daily_batch_statistics.csv","w",encoding="utf-8-sig",newline="") as f:
        fields=["date","矿批_count","矿批_sum","焦批_count","焦批_sum","ore_coke_ratio"];w=csv.DictWriter(f,fieldnames=fields);w.writeheader();w.writerows(output)
    report={"furnace":a.furnace,"source_rows":len(rows),"days":len(output),"unit":"源系统单位待确认","channel_policy":"value_01...24不得当化学成分"}
    (out/"summary.json").write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding="utf-8");print(json.dumps(report,ensure_ascii=False))
if __name__=="__main__":main()
