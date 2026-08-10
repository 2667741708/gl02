# 工长燃料比法与 V20 历史 Si 法同炉次并列评估（2026-08-08）

追踪编号：`REQ-SI-FUELRATIO-V20-SIDE-BY-SIDE-20260808`

## 结论

使用炉号和开口时间双键，将 MES Web“冀南新区高炉作业日志”中可解析的炉前块，
与 V20 开口前 60 分钟逐炉预测对齐。主比较只保留 V20 的验证集和确认集共同炉次，
训练段不参与排名；实际值统一使用 220.12
`bf_assistant.heat_performance_quality_summary.si_avg` 对应的每炉有效 Si 算术平均值。

| 方法 | 共同炉次 | MAE | ±0.05命中率 | ±0.02命中率 |
|---|---:|---:|---:|---:|
| 工长燃料比法，固定基准Si=0.30 | 7 | 0.7358 | 0.00% | 0.00% |
| 工长燃料比法，前两日报表Si作基准 | 7 | 0.6987 | 0.00% | 0.00% |
| V20历史Si法 | 7 | 0.0580 | 57.14% | 28.57% |

共同样本只有 7 炉，不能把 57.14% 当成稳定总体命中率。V20 完整协议结果仍应使用
75 炉验证集的 `69.33%` 和 27 炉确认集的 `59.26%`。工长公式在共同样本中产生
负 Si 或超过 0.8% 的无约束外推，主因是报表燃料比差达到约 `-102~+28 kg/t`，
而固定换算 `每5 kg/t → Si 0.10%` 被直接线性放大。因此当前证据只支持把燃料比差
作为趋势解释/模型特征，不支持把该无约束公式直接作为平均 Si 绝对预测器。

## V19 历史背景

当前一键入口默认加载 V19 August holdout bundle；协议预选候选为 `pci`，训练 2291 炉、
8 月时间外测试 158 炉，MAE `0.04165`、±0.05 命中率 `67.72%`。这个结果不是严格的
“开口前 1 小时”共同样本，因此不能与上表直接排名。V19 `all_context` 在同一 8 月测试
达到 `70.89%`，但它是测试结果较优、不是协议预选候选，而且用户已决定不再使用全集
上下文，所以一键默认没有切换到它。

## 公式与边界

工长经验公式按现有报表复现：

```text
预测Si = 基准Si + (开口前4个完整小时燃料比 - 前两日全天燃料比均值) / 5 × 0.1
```

- 固定版基准 Si 为 `0.30%`；并列报告同时给出“前两日报表 Si 均值”变体。
- V20 截止时间严格为 `open_ts - 60min`，只读取截止前已发布的历史平均 Si。
- MES Web 当前每个日报 HTML 只直接暴露一个炉前块，因此仅获得每日一个共同样本；
  需要定位全炉次枚举入口后才能扩大工长法样本。
- 15 个全部共同炉次中，报表 Si 与 220.12 逐炉平均 Si 有 7 个完全一致，最大差值
  `0.005`；本报告统一以 220.12 平均 Si 为评估标签。

## 复现

```powershell
python .\tools\compare_foreman_fuel_vs_v20_history.py
```

产物：

- `reports/experiments/EXP-SI-FUELRATIO-V20-COMPARE-20260808/side_by_side_predictions.csv`
- `reports/experiments/EXP-SI-FUELRATIO-V20-COMPARE-20260808/side_by_side_metrics.json`
- `reports/experiments/EXP-SI-FUELRATIO-V20-COMPARE-20260808/side_by_side_actual_vs_prediction.png`
- `reports/experiments/EXP-SI-FUELRATIO-V20-COMPARE-20260808/side_by_side_report.md`

状态：`completed_offline_small_common_sample_not_promoted`；未写 220.12 业务表，未改变
生产模型或 8093 页面。
