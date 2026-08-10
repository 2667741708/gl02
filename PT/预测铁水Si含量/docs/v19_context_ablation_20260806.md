# 平均 Si V19 上下文特征消融实验记录

需求标识：`REQ-SI-V19-CONTEXT-ABLATION-20260806`。本轮为 `experimental_offline`，不替换 V9/V13、不改生产接口、不写 220.12 业务数据。

## 数据与合同

- 目标为每炉 `target__Si_mean` 算术平均值，时间顺序切分为训练 1603、验证 344、测试 344。
- `history_mean__Si_lag_1..5` 只使用严格更早炉次，且 `label_available_ts <= prediction_cutoff_ts`；当前炉目标列在合并后删除。
- 喷煤优先读取 `PCI_current_hour`/`PCI_previous_hour`；本次正式点位覆盖为 0，因此使用分钟 `PCI_rate` 严格按当前小时和上一完整小时积分/平均，缺失保留 NaN，不以 0 填补。
- IMES 使用预测截止前已发布的 JS1/JS2 时间背景统计，覆盖 TFe、FeO、SiO2、Al2O3、CaO、MgO、P、S、TiO2、Mn、Zn、Cr、R2、Mg/Al、Al/Si、QD；化学批次到料仓、投料、炉次谱系未建立，`lineage_confidence=0`，超过 48 小时标记陈旧。

## 消融结果

测试集固定权重/重搜索结果和配对 bootstrap 位于 [metrics.json](../reports/experiments/EXP-SI-V19-CONTEXT-ABLATION-20260806/training/metrics.json) 与 [ablation_comparison.csv](../reports/experiments/EXP-SI-V19-CONTEXT-ABLATION-20260806/training/ablation_comparison.csv)。重搜索的测试 MAE：baseline 0.043695、history 0.043551、PCI 0.043518、chemistry 0.043948、all_context 0.043644；对应 ±0.05 命中率分别为 66.57%、66.86%、67.15%、67.44%、66.28%。

按 4 月、5 月滚动折和 6 月验证选择出的候选是 `chemistry`，但它在冻结测试 MAE 上没有优于 V9；相对 baseline 的 bootstrap 平均 MAE 差为 +0.000253，95% 区间 [-0.000453, +0.000944]，跨过 0。因此没有标记为影子候选。

## 回放与复现

- 最近半个月（2026-07-22 12:31 至 2026-08-06 12:00）共 220 炉，曲线见 [si_mean_actual_vs_prediction_v19.png](../reports/experiments/EXP-SI-V19-CONTEXT-ABLATION-20260806/recent_replay/si_mean_actual_vs_prediction_v19.png)，逐炉数据见同目录 CSV；MAE 0.040601、RMSE 0.055351、±0.05 命中率 73.18%、Pearson 0.4287。
- V19 特征合同测试 5 项连续两次通过；训练汇总与候选模型保存产物共 344 炉逐炉预测比较，最大数值差 0.0。

实现入口：[v19_context_features.py](../src/si_semantic_engine/v19_context_features.py)、[train_v19.py](../src/si_semantic_engine/train_v19.py)、[extract_v19_context_v2.py](../../../tools/extract_v19_context_v2.py)、[replay_v19_si_context_v2.py](../../../tools/replay_v19_si_context_v2.py)、[test_v19_context_features.py](../tests/test_v19_context_features.py)。
