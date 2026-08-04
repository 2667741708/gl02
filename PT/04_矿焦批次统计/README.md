# 矿焦批次统计

读取 IMES `batch_input` 导出，按日期与矿批/焦批统计批次数、总量、均值，并计算
矿焦质量比。`value_01...24` 保留为通道量，在取得料仓字典前不解释为物料成分。

```powershell
python PT/04_矿焦批次统计/analyze.py --input <batch_input.csv> --furnace 2D012
```
