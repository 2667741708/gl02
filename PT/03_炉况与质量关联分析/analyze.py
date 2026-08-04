from __future__ import annotations
import argparse,csv,json,math,statistics
from pathlib import Path
HERE=Path(__file__).resolve().parent
def n(v):
    try:return float(v)
    except (TypeError,ValueError):return None
def pearson(xs,ys):
    if len(xs)<2:return None
    mx,my=statistics.mean(xs),statistics.mean(ys); dx=[x-mx for x in xs];dy=[y-my for y in ys]
    den=math.sqrt(sum(x*x for x in dx)*sum(y*y for y in dy))
    return sum(x*y for x,y in zip(dx,dy))/den if den else None
def main():
    cfg=json.loads((HERE/"config.json").read_text(encoding="utf-8"));p=argparse.ArgumentParser(description="炉况与质量关联分析")
    p.add_argument("--input",required=True);p.add_argument("--x",default=cfg["default_x"]);p.add_argument("--y",default=cfg["default_y"]);p.add_argument("--output-dir",default=str(HERE/"results"));a=p.parse_args()
    rows=list(csv.DictReader(open(a.input,encoding="utf-8-sig",newline=""))); pairs=[(r,n(r.get(a.x)),n(r.get(a.y))) for r in rows];pairs=[x for x in pairs if x[1] is not None and x[2] is not None]
    xs=[x[1] for x in pairs];ys=[x[2] for x in pairs];report={"x":a.x,"y":a.y,"pair_count":len(pairs),"pearson_r":pearson(xs,ys),"x_mean":statistics.mean(xs) if xs else None,"y_mean":statistics.mean(ys) if ys else None,"sufficient":len(pairs)>=cfg["minimum_pairs"],"boundary":"统计关联，不代表因果或生产控制阈值"}
    out=Path(a.output_dir);out.mkdir(parents=True,exist_ok=True);(out/"association.json").write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding="utf-8")
    with open(out/"paired_rows.csv","w",encoding="utf-8-sig",newline="") as f:
        w=csv.DictWriter(f,fieldnames=["meltno",a.x,a.y]);w.writeheader();w.writerows({"meltno":r.get("meltno"),a.x:x,a.y:y} for r,x,y in pairs)
    print(json.dumps(report,ensure_ascii=False))
if __name__=="__main__":main()
