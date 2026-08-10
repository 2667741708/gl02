# V20 开口前平均 Si 命中率优化实验说明

追踪编号：`REQ-SI-V20-OPEN-MINUS-HITRATE-20260807`

## 目标

V20 聚焦现场实际用法：在每炉开口前 1 小时预测该炉铁水平均 Si。上一轮按
2026-08-06 当日 15 炉回放，±0.05 命中率为 46.67%，本轮目标是在离线/影子条件
下验证是否能提升到至少 60%，同时 MAE 不恶化。

## 已实现程序

- `src/si_semantic_engine/v20_open_minus_features.py`
- `tools/build_open_minus_si_dataset_v20.py`
- `tools/train_open_minus_si_v20.py`
- `tools/predict_next_heat_si_v19.py` 的 V20 bundle 兼容分支
- `tests/test_v20_open_minus_features.py`

## 默认实验命令

构建数据集：

```powershell
python .\tools\build_open_minus_si_dataset_v20.py --date-from "2026-02-01" --date-to "2026-08-07"
```

训练开口前 60 分钟主模型：

```powershell
python .\tools\train_open_minus_si_v20.py --lead-minutes 60
```

使用 V20 影子模型做单炉预测：

```powershell
python .\tools\predict_next_heat_si_v19.py --target-meltno "2#20260807-095" --cutoff-ts "2026-08-07 06:40:00" --model "PT\预测铁水Si含量\reports\experiments\EXP-SI-V20-OPEN-MINUS-20260807\training\selected_v20_open_minus.joblib"
```

## 模型选择规则

候选模型只能根据验证集选择。默认切分：

- 训练：`<= 2026-07-31`
- 验证：`2026-08-01~2026-08-05`
- 最终确认：`2026-08-06~2026-08-07`

排序规则：

1. 验证集 `abs(prediction - actual) <= 0.05` 命中率；
2. 验证集 MAE；
3. 验证集逐日稳定性。

确认集只用于最终确认，不参与选型。

## 数据边界

- 当前炉的 `target__Si_mean` 永远不能进入当前输入；
- 前 1～5 炉 Si 是 5 个独立字段，只来自严格更早且已发布炉次；
- 如果最近一炉未化验，程序自动退回最近已发布炉次，并记录未化验炉次间隔；
- PCI 和传感器窗口均使用 `[cutoff-window, cutoff)`；
- 当前小时正式喷煤只有在 `data_until_ts <= cutoff` 时可用；
- IMES 烧结矿化学仅为低置信度时间背景，不代表该炉实际用料。

## 当前状态

代码和测试已实现；2026-08-07 21:47 在 VPN 恢复后已完成一轮 220.12 只读回放。

### 2026-08-07 快速回放结果

数据构建命令：

```powershell
python .\tools\build_open_minus_si_dataset_v20.py --date-from 2026-02-08 --date-to 2026-08-07 --limit 3000 --lead-minutes-list 60 --pci-windows-hours 1,2,4,6,8,12 --skip-sensor-windows --skip-chemistry --chunk-size 50 --statement-timeout-ms 300000 --local-tunnel-port 15446 --output-dir PT\预测铁水Si含量\reports\experiments\EXP-SI-V20-OPEN-MINUS-20260807\quick60_history_pci
```

结果：

- 样本：`2559` 炉，开口前 `60min` 单提前量；
- 特征：前 1～5 个已发布炉次平均 Si、未化验炉次间隔、最近化验年龄、1/2/4/6/8/12 小时 PCI 窗口、正式小时喷煤；
- 未加入：传感器滚动窗口、IMES 炉料化学背景；
- 默认候选选中：`two_stage_low_mid_high`，验证集 ±0.05 为 `65.33%`，确认集 ±0.05 为 `51.85%`，确认集 MAE `0.0526`；
- 允许消融入选后，最佳为 `ablation_history`，验证集 ±0.05 为 `69.33%`，确认集 ±0.05 为 `59.26%`，确认集 MAE `0.0491`。

`ablation_history` 只使用历史 Si 和未化验间隔特征，说明本轮喷煤窗口在确认集上没有带来稳定增益。
确认集距离 60% 硬目标只差 1 炉命中，但仍不能标记为正式影子候选。

### 传感器窗口边界

尝试直接在 220.12 PostgreSQL 分块计算 `30/60/120/240/360/480/720` 分钟传感器窗口时，
全量 133 点 SQL 会触发 statement timeout。新增 `--sensor-name-scope core28` 后，核心 28 点可开始返回，
但 10 炉首块接近 1 分钟，按全量估算不可接受；因此已停止该本机离线构建进程，未写 220.12。
后续需要改为本地缓存/远端预聚合/按小时预聚合后再训练。

当前状态维持 `experimental_offline_not_promoted`。
