from __future__ import annotations
import argparse,csv,json,math,statistics
from collections import defaultdict
from datetime import datetime
from pathlib import Path
HERE=Path(__file__).resolve().parent
def n(v):
    try:return float(v)
    except (TypeError,ValueError):return None
def main():
    p=argparse.ArgumentParser(description="构建炉次级传感器窗口特征");p.add_argument("--input",required=True);p.add_argument("--output-dir",default=str(HERE/"results"));a=p.parse_args()
    rows=list(csv.DictReader(open(a.input,encoding="utf-8-sig",newline="")));groups=defaultdict(list)
    for r in rows:
        val=n(r.get("value"))
        if r.get("meltno") and r.get("variable_name") and val is not None:groups[(r["meltno"],r["variable_name"])].append((datetime.fromisoformat(r["ts"].replace("T"," ")),val,r))
    output=[]
    for (heat,var),items in sorted(groups.items()):
        items.sort(); vals=[x[1] for x in items]; elapsed=(items[-1][0]-items[0][0]).total_seconds()/60 if len(items)>1 else 0
        slope=(vals[-1]-vals[0])/elapsed if elapsed else 0.0; sample=items[0][2]
        start=sample.get("window_start");end=sample.get("window_end_exclusive");expected=None
        if start and end:expected=max(1,round((datetime.fromisoformat(end.replace("T"," "))-datetime.fromisoformat(start.replace("T"," "))).total_seconds()/60))
        output.append({"meltno":heat,"variable_name":var,"sample_count":len(vals),"expected_minutes":expected or "","coverage_ratio":round(min(1,len(vals)/expected),4) if expected else "","mean":statistics.mean(vals),"min":min(vals),"max":max(vals),"std":statistics.pstdev(vals),"first":vals[0],"latest":vals[-1],"slope_per_minute":slope})
    out=Path(a.output_dir);out.mkdir(parents=True,exist_ok=True);fields=list(output[0]) if output else ["meltno","variable_name"]
    with open(out/"heat_sensor_features.csv","w",encoding="utf-8-sig",newline="") as f:w=csv.DictWriter(f,fieldnames=fields);w.writeheader();w.writerows(output)
    report={"source_rows":len(rows),"feature_rows":len(output),"heat_count":len({x[0] for x in groups}),"window_boundary":"[start,end)"}
    (out/"summary.json").write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding="utf-8");print(json.dumps(report,ensure_ascii=False))
if __name__=="__main__":main()
