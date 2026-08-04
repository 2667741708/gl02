from __future__ import annotations
import argparse,csv,json,math,statistics
from pathlib import Path
HERE=Path(__file__).resolve().parent
def f(v):
    try:return float(v)
    except (TypeError,ValueError):return None
def main():
    p=argparse.ArgumentParser(description="铁水Si时间切分基线实验");p.add_argument("--input",required=True);p.add_argument("--output-dir",default=str(HERE/"results"));a=p.parse_args()
    cfg=json.loads((HERE/"config.json").read_text(encoding="utf-8")); rows=list(csv.DictReader(open(a.input,encoding="utf-8-sig",newline="")))
    target=cfg["target_column"]; rows=[r for r in rows if f(r.get(target)) is not None]; rows.sort(key=lambda r:r.get(cfg["time_column"],""))
    cut=max(1,int(len(rows)*(1-cfg["test_ratio"]))); train,test=rows[:cut],rows[cut:]
    baseline=statistics.median(f(r[target]) for r in train) if train else None
    pred=[{"meltno":r.get("meltno"),"open_ts":r.get(cfg["time_column"]),"actual_si":f(r[target]),"predicted_si":baseline,"error":f(r[target])-baseline} for r in test] if baseline is not None else []
    mae=sum(abs(r["error"]) for r in pred)/len(pred) if pred else None; rmse=math.sqrt(sum(r["error"]**2 for r in pred)/len(pred)) if pred else None
    out=Path(a.output_dir);out.mkdir(parents=True,exist_ok=True)
    with open(out/"predictions.csv","w",encoding="utf-8-sig",newline="") as fh:
        w=csv.DictWriter(fh,fieldnames=["meltno","open_ts","actual_si","predicted_si","error"]);w.writeheader();w.writerows(pred)
    report={"rows":len(rows),"train_rows":len(train),"test_rows":len(test),"baseline_train_median":baseline,"mae":mae,"rmse":rmse,"leakage_policy":"仅允许炉前可得sensor__/context__特征"}
    (out/"metrics.json").write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding="utf-8");print(json.dumps(report,ensure_ascii=False))
if __name__=="__main__":main()
