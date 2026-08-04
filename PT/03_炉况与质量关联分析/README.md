# 炉况与质量关联分析

分析炉次级炉况分数与铁水 Si/S、炉渣 FeO/R2 等质量指标的统计关系，不把相关性
解释为因果关系。输入为一炉一行 CSV。

默认分析 `diagnosis__average_score` 与 `target__hot_metal_Si_median`，也可以通过
参数指定任意两个数值列。

```powershell
python PT/03_炉况与质量关联分析/analyze.py --input <rows.csv> --x diagnosis__average_score --y target__hot_metal_Si_median
```
