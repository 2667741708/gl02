# 炉次数据集

以 `meltno` 为主键构建炉次级主数据，检查开堵口、出铁时长、铁量、铁水和炉渣覆盖。

输入：UTF-8 CSV，至少包含 `meltno,open_ts,close_ts`；可选
`actual_iron_qty,hot_metal_sample_count,slag_sample_count`。

运行：

```powershell
python PT/01_炉次数据集/analyze.py --input <heats.csv>
```

输出到 `results/`：清洗后的炉次表、质量问题表和汇总 JSON。未来接入
`t_ipes_cond/t_ipes_out_put` 时仍保持同一字段合同。
