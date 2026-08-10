# V21 传感器窗口预聚合缓存实验（2026-08-08）

追踪编号：`REQ-SI-V21-SENSOR-CACHE-20260808`

> 2026-08-08 用户决策：不再使用全集上下文；当前一键预测和推荐口径回到之前的
> V19 August holdout 默认模型。V21 的 core28/process133/all151 缓存只保留为离线
> 研究资产，不作为默认训练、默认预测或影子候选。

## 目标

把 V20 的 `133点/核心28点 × 30/60/120/240/360/480/720分钟窗口` 从数据库端
`样本 × 窗口 × 点位` 聚合，改成本机预聚合缓存，降低 220.12 查询压力，并重新回放开口前
60 分钟平均 Si 预测。

本轮仍为 `experimental_offline`：不替换生产模型、不写 220.12 业务表、不调整生产设定值。

## 新增入口

- `tools/build_v20_sensor_window_cache.py`
  - 只读 220.12 的 `bf_sensor.sensor_registry` 和 `bf_sensor.one_minute_values`；
  - 按每个点位拉取分钟值，在本机用前缀统计计算窗口；
  - 严格使用 `[prediction_cutoff_ts - window, prediction_cutoff_ts)`，不读 cutoff 之后的数据；
  - 过滤非有限原始值，不用 0 填补缺失；
  - 输出宽表缓存 CSV 和 audit JSON。
- `tools/materialize_v21_dataset_from_sensor_cache.py`
  - 本机合并工具；
  - 从已有 V20 基础数据集删除旧 `v20_sensor__` 列，再按 `v20_sample_id` 合并缓存；
  - 支持从 process133 缓存按 audit 里的 `variable_name` 切出 core28。
- `tools/build_open_minus_si_dataset_v20.py`
  - 新增 `--sensor-window-cache`；
  - 新增 `--sensor-name-scope process133`，排除 `EQ_` 开头质量/设备点位。
- `tools/train_open_minus_si_v20.py`
  - 新增候选模型进度日志；
  - 新增 `--candidate-names`，用于高维缓存实验跳过过重候选。

## 数据口径

- 炉次范围：`2026-03-01` 至 `2026-08-07`；
- 样本：2268 行，均为开口前 60 分钟；
- 目标：`target__Si_mean`，来自 220.12 修复后的炉次质量汇总平均 Si；
- 切分：训练截至 `2026-07-31`，验证 `2026-08-01~2026-08-05`，确认 `2026-08-06~2026-08-07`；
- 严格 133 点：当前 registry 中启用且非派生为 151 点，其中 `EQ_` 前缀 18 点排除后为 133 个工艺点；
- 核心28点：从 process133 audit 的 `variable_name` 中匹配固定 28 个核心变量。

## 运行命令

构建严格 process133 缓存：

```powershell
python .\tools\build_v20_sensor_window_cache.py --date-from 2026-03-01 --date-to 2026-08-07 --limit 5000 --lead-minutes-list 60 --sensor-name-scope process133 --sensor-windows-minutes 30,60,120,240,360,480,720 --statement-timeout-ms 300000 --local-tunnel-port 15451 --output-dir 'PT\预测铁水Si含量\reports\experiments\EXP-SI-V21-SENSOR-CACHE-20260808\cache_process133_2026'
```

把缓存合并成 process133 训练数据：

```powershell
python .\tools\materialize_v21_dataset_from_sensor_cache.py --base-dataset 'PT\预测铁水Si含量\reports\experiments\EXP-SI-V21-SENSOR-CACHE-20260808\dataset_core28_60\v20_open_minus_dataset.csv' --sensor-cache 'PT\预测铁水Si含量\reports\experiments\EXP-SI-V21-SENSOR-CACHE-20260808\cache_process133_2026\v21_sensor_window_cache_process133_lead60.csv' --sensor-audit 'PT\预测铁水Si含量\reports\experiments\EXP-SI-V21-SENSOR-CACHE-20260808\cache_process133_2026\v21_sensor_window_cache_process133_lead60.audit.json' --sensor-variable-scope all --output-dir 'PT\预测铁水Si含量\reports\experiments\EXP-SI-V21-SENSOR-CACHE-20260808\dataset_process133_60'
```

从同一缓存切出 core28 数据：

```powershell
python .\tools\materialize_v21_dataset_from_sensor_cache.py --base-dataset 'PT\预测铁水Si含量\reports\experiments\EXP-SI-V21-SENSOR-CACHE-20260808\dataset_core28_60\v20_open_minus_dataset.csv' --sensor-cache 'PT\预测铁水Si含量\reports\experiments\EXP-SI-V21-SENSOR-CACHE-20260808\cache_process133_2026\v21_sensor_window_cache_process133_lead60.csv' --sensor-audit 'PT\预测铁水Si含量\reports\experiments\EXP-SI-V21-SENSOR-CACHE-20260808\cache_process133_2026\v21_sensor_window_cache_process133_lead60.audit.json' --sensor-variable-scope core28 --output-dir 'PT\预测铁水Si含量\reports\experiments\EXP-SI-V21-SENSOR-CACHE-20260808\dataset_core28_60_finite'
```

训练 core28 完整候选：

```powershell
python .\tools\train_open_minus_si_v20.py --dataset 'PT\预测铁水Si含量\reports\experiments\EXP-SI-V21-SENSOR-CACHE-20260808\dataset_core28_60_finite\v20_open_minus_dataset.csv' --lead-minutes 60 --output-dir 'PT\预测铁水Si含量\reports\experiments\EXP-SI-V21-SENSOR-CACHE-20260808\training_core28_60_finite' --allow-ablation-selection
```

训练 process133 高维候选子集：

```powershell
python .\tools\train_open_minus_si_v20.py --dataset 'PT\预测铁水Si含量\reports\experiments\EXP-SI-V21-SENSOR-CACHE-20260808\dataset_process133_60\v20_open_minus_dataset.csv' --lead-minutes 60 --output-dir 'PT\预测铁水Si含量\reports\experiments\EXP-SI-V21-SENSOR-CACHE-20260808\training_process133_60_lightgbm' --allow-ablation-selection --candidate-names 'history_lag1_baseline,v20_lightgbm_huber,v20_hit_weighted_lightgbm,ablation_history,ablation_history_pci,ablation_long_windows'
```

## 结果摘要

确认集为 `2026-08-06~2026-08-07`，共 31 炉。

| 版本 | 候选 | 验证±0.05 | 确认±0.05 | 确认MAE | 结论 |
|---|---|---:|---:|---:|---|
| V21 core28 finite | `v20_lightgbm_huber` | 73.33% | 54.84% | 0.05525 | 验证好，确认未过 60% |
| V21 process133 | `v20_lightgbm_huber` | 72.00% | 51.61% | 0.05724 | 高维 133 未改善确认 |
| 同数据消融 | `ablation_history` | 70.67% | 58.06% | 0.04972 | 当前最稳，但仍未达 60% |
| 同数据消融 | `ablation_history_pci` | 65.33% | 51.61% | 0.05503 | PCI 未带来确认集提升 |

完整对比表：

- `PT/预测铁水Si含量/reports/experiments/EXP-SI-V21-SENSOR-CACHE-20260808/v21_core28_process133_metric_summary.csv`

核心结论：预聚合缓存技术路线有效，但“直接把核心28/133点多窗口全集塞入模型”没有提升
`2026-08-06~2026-08-07` 确认集命中率。当前不能把 V21 标记为影子候选；按用户
决策，后续默认回到 V19 August holdout，不再使用全集上下文。

## 关键发现

1. 旧 V20 直接 SQL 聚合在 133 点上容易超时；本机缓存可解决这一瓶颈。
2. 不指定 `--date-from` 时，`ORDER BY open_ts LIMIT 5000` 可能截到 2024/2025 老炉次，造成当前传感器覆盖为 0；V21 命令固定显式日期范围。
3. 当前 `sensor_registry` 中 `all enabled non-derived` 为 151 点；严格工艺 133 点需要排除 `EQ_` 前缀。
4. 少数传感器原始值含非有限值；缓存器已过滤，修正版 process133 stderr 为空。
5. process133 全候选模型过重；首次全候选训练在 CPU 累计 10000 秒左右仍未落盘，已停止该单一训练进程。高维版本本轮改用候选子集完成评估。
6. 8月6~7日确认集仍存在明显时间漂移；更多物理窗口并没有自动带来泛化提升。下一步应做覆盖率过滤、TopN 特征选择、按班/日滚动验证，而不是继续扩大“全集上下文”。

## 输出位置

- process133 缓存：`PT/预测铁水Si含量/reports/experiments/EXP-SI-V21-SENSOR-CACHE-20260808/cache_process133_2026/`
- core28 数据集：`PT/预测铁水Si含量/reports/experiments/EXP-SI-V21-SENSOR-CACHE-20260808/dataset_core28_60_finite/`
- process133 数据集：`PT/预测铁水Si含量/reports/experiments/EXP-SI-V21-SENSOR-CACHE-20260808/dataset_process133_60/`
- core28 训练：`PT/预测铁水Si含量/reports/experiments/EXP-SI-V21-SENSOR-CACHE-20260808/training_core28_60_finite/`
- process133 训练：`PT/预测铁水Si含量/reports/experiments/EXP-SI-V21-SENSOR-CACHE-20260808/training_process133_60_lightgbm/`

## 状态

`experimental_offline_paused_reverted_to_v19_default`。
