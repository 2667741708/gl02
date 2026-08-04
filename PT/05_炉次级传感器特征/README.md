# 炉次级传感器特征

把炉次窗口内的分钟传感器长表转换为“一炉×变量”统计特征。输入至少包含
`meltno,variable_name,ts,value`，可选 `window_start,window_end_exclusive`。

```powershell
python PT/05_炉次级传感器特征/analyze.py --input <sensor_minute_values.csv>
```

输出均值、最小、最大、标准差、首末值、每分钟斜率、样本数和覆盖率。窗口必须
使用左闭右开 `[start,end)`，避免跨炉和未来数据泄漏。
