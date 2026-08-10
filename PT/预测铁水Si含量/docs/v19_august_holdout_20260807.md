# V19 7月训练、8月时间外测试

需求：`REQ-SI-V19-CONTEXT-ABLATION-20260806` 的滚动更新。原 V19 保持不变；本实验仍为 `experimental_offline`，未替换生产模型。

## 时间口径

- 原正式数据至 `2026-07-26 19:02:00`，共 2291 个可训练特征炉次。
- 7月数据不再作为冻结测试，而是并入训练集；8月新增 158 炉作为时间外测试。
- 4月、5月、6月和7月分别做时间顺序折内选择；最终训练使用截至7月26日的全部炉次。

## 结果

| 消融 | 8月测试 MAE | ±0.05命中率 | 相对 baseline 的 bootstrap 平均差 |
|---|---:|---:|---:|
| baseline | 0.041657 | 67.72% | 0 |
| 前1～5炉平均Si | 0.041499 | 68.99% | -0.000159，区间跨0 |
| PCI | 0.041647 | 67.72% | -0.000010，区间跨0 |
| 炉料化学背景 | 0.041545 | 68.99% | -0.000113，区间跨0 |
| 全部上下文 | 0.040573 | 70.89% | -0.001085，95%区间[-0.001927,-0.000225] |

按只使用4～7月验证结果的规则，预先选择候选为 `pci`；其8月 MAE 仅比 baseline 改善约0.000010，bootstrap 仍跨0，因此暂不晋级影子模型。`all_context` 在这一个8月窗口表现较好，但不能用测试集反选，需继续积累8月完整数据再复核。

产物：[metrics.json](../reports/experiments/EXP-SI-V19-AUGUST-HOLDOUT-20260807/metrics.json)、[消融对比](../reports/experiments/EXP-SI-V19-AUGUST-HOLDOUT-20260807/ablation_comparison.csv)、[逐炉预测](../reports/experiments/EXP-SI-V19-AUGUST-HOLDOUT-20260807/predictions_pci.csv)、[曲线](../reports/experiments/EXP-SI-V19-AUGUST-HOLDOUT-20260807/si_mean_actual_vs_prediction_august_holdout.png)。

实现：[train_v19_august_holdout.py](../src/si_semantic_engine/train_v19_august_holdout.py)、[train_v19_august_holdout_v2.py](../src/si_semantic_engine/train_v19_august_holdout_v2.py)。
