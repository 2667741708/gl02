# MES 作业日志燃料比经验法核验（2026-08-08）

## 结论摘要

按用户指定，本轮只读取 MES Web 端“冀南新区高炉作业日志”报表源记，未使用 pSpace 数据库，未写入 220.12 业务表。

从 220.12 跳板只读下载 2#高炉 `2026-07-22` 至 `2026-08-08` 的作业日志源 HTML 后，复现报表内客户端公式计算煤比/燃料比，并按现场口径测试：

- 前两日全天燃料比均值作为燃料比基准；
- 当前炉开口前 4 个完整小时燃料比作为实时燃料比；
- 固定基准 Si = `0.30%`；
- `燃料比每 +5 kg/t，对应 Si +0.10%`。

在当前可直接解析的 15 个日报炉前块样本上，这个无约束经验公式表现不稳定：

| 方法 | 样本数 | MAE | RMSE | ±0.05 命中率 | ±0.02 命中率 |
|---|---:|---:|---:|---:|---:|
| 燃料比经验法，固定 Si=0.30 | 15 | 0.4284 | 0.6608 | 13.33% | 6.67% |
| 燃料比经验法，前两日报表 Si 均值 | 15 | 0.4261 | 0.6419 | 20.00% | 0.00% |
| 恒定 0.30 基线 | 15 | 0.0593 | 0.0740 | 60.00% | 13.33% |
| 前两日报表 Si 均值基线 | 15 | 0.0607 | 0.0731 | 60.00% | 20.00% |

诊断性线性拟合显示，开口前 4 小时燃料比差与实际 Si 在这批样本里的线性相关性很弱：

- 相关系数：`0.0318`；
- 全样本拟合 ±0.05：`60.00%`，但留一法降至 `40.00%`；
- 拟合斜率折算为 `0.1% Si ≈ 1352 kg/t`，与现场经验 `0.1% Si ≈ 5 kg/t` 不在同一量级。

因此，本轮证据支持的判断是：燃料比经验法可以作为趋势解释或模型特征，但不能直接作为单变量、无约束的平均 Si 绝对值预测器。

## 数据源与边界

报表入口：

```text
http://10.10.181.205:8080/demo/reportJsp/showInput.jsp?sht=mes/jn_ts_glbb_tb.sht
```

筛选参数：

- `prodcentercode=2D012`，即 2#高炉；
- `time1=YYYY-MM-DD 00:00:00`；
- 通过 220.12 访问 MES Web，下载报表 HTML 后本机离线解析。

重要边界：

- 当前入口按日期返回的是作业日志日报，HTML 中第 38 行为一个“炉前出铁情况”块；未在该入口直接拿到当天全部炉次清单。
- 因此本轮是“日报炉前块”的快速核验，不等同于 220.12 修复后炉次质量汇总表的全炉次核验。
- 若要做全炉次结论，需要继续定位 MES Web 里作业日志的记录枚举/翻页入口，或者在用户允许下用 220.12 修复后的炉次质量汇总表做实际 Si 标签对齐。

## 程序入口

只读抓取 MES Web 报表：

```powershell
python .\tools\remote_22012_exec.py --allow-agents-password --no-profile --timeout 300 --script '.\tools\remote_fetch_imes_report_2d012_recent_days.ps1' --download 'C:\Users\Administrator\AppData\Local\Temp\imes_report_2d012_recent_days=PT\预测铁水Si含量\reports\experiments\EXP-SI-FUELRATIO-REPORT-20260808\source_probe\imes_report_2d012_recent_days'
```

本机离线核验：

```powershell
python .\tools\evaluate_imes_fuel_ratio_rule.py
```

输出：

```text
PT\预测铁水Si含量\reports\experiments\EXP-SI-FUELRATIO-REPORT-20260808\fuel_ratio_rule_eval\fuel_ratio_rule_predictions.csv
PT\预测铁水Si含量\reports\experiments\EXP-SI-FUELRATIO-REPORT-20260808\fuel_ratio_rule_eval\fuel_ratio_rule_metrics.json
PT\预测铁水Si含量\reports\experiments\EXP-SI-FUELRATIO-REPORT-20260808\fuel_ratio_rule_eval\fuel_ratio_rule_actual_vs_pred.png
PT\预测铁水Si含量\reports\experiments\EXP-SI-FUELRATIO-REPORT-20260808\fuel_ratio_rule_eval\fuel_ratio_rule_zoomed.png
```

## 与 V20 指标的关系

“验证 0.05”指模型选择阶段的验证集 ±0.05 命中率。V20 当前协议中，验证集主要用于选择候选模型和权重。

“确认 0.05”指候选确定后，在最终确认集上只读评估的 ±0.05 命中率。确认集不能反过来参与选型，否则就是用测试结果挑模型。

此前约 `73%` 的命中率来自 V19 最近半个月回放曲线，预测截止口径和样本窗口与“开口前 1 小时预测”不同。当前 V20 的 `62.96%` 是更严格的开口前预测场景中的确认表现，且确认样本只有约几十炉，受单日波动和高 Si 炉次影响更明显。两者不能直接横向比较。

## 后续建议

1. 继续查 MES Web 作业日志的记录枚举/翻页入口，补齐当天全部炉次对应的作业日志块。
2. 将报表复算出的燃料比差、前 4 小时喷煤/料批/风量/压差等作为 V20/V21 的解释特征，而不是单独预测器。
3. 如果用于现场看板，可对经验法输出加上“趋势参考/低置信度”标识和合理区间限制，避免显示负 Si 或远超生产目标带的值。
4. 大样本最终评估仍应以修复后的逐炉平均 Si 标签为准，并保持开口前 cutoff 防泄漏。
