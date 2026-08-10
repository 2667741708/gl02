# 铁水 Si 正式标签与数据合同 V3

需求编号：`REQ-SI-FORMAL-LABEL-CONTRACT-V3-20260726`

## 1. 为什么先修标签

旧 V1/V2 实验从试样号前缀构造临时炉次，并用化验结果时间减去固定安全滞后
作为特征截止时刻。该做法适合验证建模管道，但不能作为生产标签金标准。

V3 固定以下原则：

1. 炉次只接受 MES 正式 `t_qpes_inner_batch.heatno`，并精确连接
   `t_ipes_cond.meltno`；
2. `takesampletime` 为空时保持为空，禁止用 `judgetime/publishtime` 替代；
3. 铁罐号只通过 `batchno -> v_qpes_mat_final.thankno` 精确连接；
4. 当前权限面没有可信铁口编号，必须记录为 `missing_source`，不能从
   `T_taphole_1/T_taphole_2` 测温曲线猜测；
5. 出铁阶段只在真实取样时间与开堵口时间同时存在时计算。

机器可读合同见
[si_label_contract.v3.json](../configs/si_label_contract.v3.json)。

## 2. 三个目标是三个独立任务

### 2.1 整炉代表 Si

- 粒度：一行一个 MES 正式 `meltno`；
- 目标：同一正式炉次所有有效 Si 试样的中位数；
- 截止时刻：`t_ipes_cond.opentime`；
- 用途：回答“这一炉的代表 Si 可能是多少”。

同时保留均值、样本数、原始试样明细，绝不以中位数覆盖原始值。

### 2.2 下一次试样 Si

- 粒度：同炉次内“当前真实试样 → 下一真实试样”；
- 目标：按真实 `takesampletime` 排序后的下一试样 Si；
- 截止时刻：当前试样的真实取样时间；
- 门禁：当前和下一试样必须都有真实取样时间。

截至 2026-07-26，2#正式记录的 `takesampletime` 可用数为 0，因此当前任务
必须拒绝训练。结果/审核时间即使存在，也不能解除该门禁。

### 2.3 整炉 Si 分布

- 粒度：一行一个 MES 正式 `meltno`；
- 目标：`min/P10/P50/P90/max/std/spread`；
- 最少试样：2；
- 截止时刻：`t_ipes_cond.opentime`；
- 用途：回答“这一炉不同铁罐/试样的 Si 可能分布在哪里”。

## 3. 2026-07-26只读核查

全历史正式权限面：

| 项目 | 结果 |
|---|---:|
| 2#正式化验记录 | 24,821 |
| 正式炉次 | 9,337 |
| 可连接炉次主表的正式化验 | 24,705（99.53%） |
| 真实 `takesampletime` | 0 |
| 取样地点 | 0 |
| 可通过 `batchno`连接铁罐号 | 16,400（66.07%） |
| 可用可信铁口编号 | 0 |

与 PostgreSQL 传感器历史 `2026-02-08 19:06` 至 `2026-07-26 22:20`
相交后：

| 项目 | 结果 |
|---|---:|
| 正式试样 | 5,936 |
| 正式炉次 | 2,366 |
| 精确铁罐号覆盖 | 5,936（100%） |
| 至少2个Si试样且完整标签在截止后的炉次 | 1,969 |
| 完整标签在开铁截止前已全部可见的排除炉次 | 66 |
| 通过标签与至少100个开铁前有效传感器点门禁的训练炉次 | 2,291 |

覆盖率是所选时间范围的事实，不得外推为整个 MES 历史永久 100%。

## 4. 特征时间边界

每炉预测截止时刻是正式 `opentime`。传感器 SQL 使用严格小于：

```text
sensor_ts < prediction_cutoff_ts
```

每个133物理点构造：

- 截止前最近值；
- 相对60分钟前参考值的变化量和每分钟斜率；
- 相对120分钟前参考值的变化量和每分钟斜率。

候选共665列。训练段覆盖率与方差门禁后本次使用579列。前序炉 Si 还必须同时
满足“正式炉次更早”和“化验结果时刻不晚于当前截止时刻”，当前炉标签永远
不能进入自己的输入。

若某炉`label_available_ts <= prediction_cutoff_ts`，说明完整目标在预测发起前
已经可见，该炉不再是前瞻预测样本，V3训练层直接排除。当前共排除66炉。

### 前炉历史可见性补充（2026-07-27）

前炉Si历史必须同时满足：

```text
prior.prediction_cutoff_ts < current.prediction_cutoff_ts
prior.label_available_ts <= current.prediction_cutoff_ts
```

相同 `prediction_cutoff_ts` 的两个炉次不能因 `meltno` 排序先后互相进入历史。
历史Si连续字段在持久化和推理前统一保留12位小数，避免CSV浮点解析差异改变树
模型分裂路径。修复快照见
[manifest.json](../data/processed/formal_v3_historyfix_r12_20260727/manifest.json)。

## 5. 文件与程序

- 标签合同：
  [formal_labels.py](../src/si_semantic_engine/formal_labels.py)
- 数据拼装：
  [formal_dataset.py](../src/si_semantic_engine/formal_dataset.py)

## 6. V20 开口前 1 小时平均 Si 合同（2026-08-07）

追踪编号：`REQ-SI-V20-OPEN-MINUS-HITRATE-20260807`

V20 是独立离线/影子实验，不修改 V9/V13/V19 冻结特征合同，不替换生产模型。

- 主目标：`target__Si_mean = bf_assistant.heat_performance_quality_summary.si_avg`，即同一炉次所有有效 Si 试样的算术平均值。
- 主场景：`prediction_cutoff_ts = open_ts - 60min`，同时保留 `120/90/60/30/15/0min` 对照样本。
- 前炉 Si：`history_mean__Si_lag_1` 到 `history_mean__Si_lag_5` 分别表示最近第 1、2、3、4、5 个“已发布且严格更早炉次”的平均 Si；不把五炉先合并成一个均值。`history_mean__Si_mean_3/5` 和 `history_mean__Si_slope_5` 只是额外摘要。
- 未化验间隔：记录最近可见化验距当前炉的炉次数、小时数和最近 5 炉未发布数量，用于 94 炉无化验而 95 炉已开口这类现场情况。
- 喷煤：`v20_pci__8h_*`、`v20_pci__12h_*` 等窗口严格使用 `[cutoff-window, cutoff)`；上一完整小时优先正式小时视图，当前小时只有 `data_until_ts <= cutoff` 才接受正式小时值，否则依赖 `PCI_rate` 分钟积分。
- 传感器：`v20_sensor__*__30/60/120/240/360/480/720m_*` 严格使用 `[cutoff-window, cutoff)`。
- 炉料化学：若接入 `public.v_qpes_sinter_machine_sample_insp_final`，仅作为 JS1/JS2 烧结矿化学发布时间背景，`lineage_confidence=0`；不得表述为该炉实际用料成分。

V20 默认训练切分：训练到 `2026-07-31`，验证 `2026-08-01~2026-08-05`，最终确认 `2026-08-06~2026-08-07`。确认集只用于最终报告，不能参与候选模型选择。

### 6.1 V21 传感器窗口缓存补充合同（2026-08-08）

追踪编号：`REQ-SI-V21-SENSOR-CACHE-20260808`

- 缓存键：必须包含 `official_meltno` 和 `v20_sample_id`；多提前量样本合并时以 `v20_sample_id` 为准。
- 时间边界：传感器窗口仍为 `[prediction_cutoff_ts - window, prediction_cutoff_ts)`；缓存不得读 cutoff 时刻及之后分钟值。
- 缺失策略：不得用 0 填充缺失；窗口覆盖分钟数和覆盖率作为独立特征保存。
- 非有限值：原始分钟值中的 `NaN/inf/-inf` 在本机统计前过滤。
- 点位口径：
  - `core28`：固定 28 个核心工艺变量；
  - `process133`：当前 220.12 `sensor_registry` 中启用且非派生点位排除 `EQ_` 前缀后的 133 个工艺点；
  - `all`：当前启用且非派生全量点位，2026-08-08 实测为 151 个，其中 18 个 `EQ_` 点不属于严格 133 工艺分钟序列。
- 特征命名：`v20_sensor__{short_name}__{window}m_{stat}`，`stat` 包括 `mean/std/min/max/last/delta/coverage_minutes/coverage_ratio/slope_per_hour`。

V21 缓存是离线实验数据资产，不写 220.12 业务表，不改变 V20/V19 生产预测入口默认行为。
2026-08-08 用户决策后，全集上下文不再作为默认或推荐输入；一键预测默认继续使用
V19 August holdout。`process133/all` 只能显式用于离线研究，V20 数据构建器默认
传感器口径为 `core28`。
- 只读抽取：
  [build_formal_si_dataset_v3.py](../../../tools/build_formal_si_dataset_v3.py)
- 正式训练：
  [train_v3.py](../src/si_semantic_engine/train_v3.py)
- 数据快照：
  [formal_v3_20260726](../data/processed/formal_v3_20260726/)

所有产物记录 SHA-256。模型状态保持
`experimental_offline_formal_contract`，不得接生产 MCP。

## 6. 铁水温度与热状态联合标签合同

铁水温度必须来自真实测温，不得用以下字段替代：

- 出铁口温度 `T_taphole_1/2`；
- 炉身热电偶；
- 炉顶温度；
- Si预测值或人为划分的Si区间。

每条合格温度标签至少包含：

```text
official_meltno
temperature_value_c
measurement_ts
taphole_id
ladle_or_torpedo_id
tapping_stage
source_record_id
quality_status
```

若同炉有多次测温，必须保留明细并显式定义目标是“下一次测温”“整炉代表温度”
还是“整炉温度分布”。`measurement_ts`不可用结果录入时间替代。

截至2026-07-27，MES `tappingtemp` 相关2#历史行数为9,373，但非空真实温度
为0。因此温度回归和热状态概率任务状态固定为
`blocked_no_true_hot_metal_temperature_label`。只有标签合同满足后，才能分析
Si与真实铁水温度的相关性并训练联合模型。

## REQ-SI-V19-CONTEXT-ABLATION-20260806

Offline ablation for prior 1-5 heat mean-Si, current/lagged PCI, and IMES sinter chemistry time-background; V9/V13 and production interfaces remain frozen; chronological split is 1603/344/344.

Implementation: v19_context_features.py, train_v19.py, extract_v19_context_v2.py, replay_v19_si_context_v2.py, test_v19_context_features.py.

Result: chemistry ranked first on April/May/June pre-test selection, but frozen-test MAE did not beat V9 and paired bootstrap crossed zero; no shadow promotion. Status remains experimental_offline. Chemistry is time-background only; batch-to-bin-to-charge-to-heat lineage is unverified.

Status: completed_offline_not_promoted.


## REQ-SI-V19-AUGUST-HOLDOUT-20260807

V19 rolling update: July data is included in offline training through 2026-07-26 19:02:00; 158 new August heats are held out as time-out evaluation. Original V19 artifacts remain frozen.

Implementation: train_v19_august_holdout.py and train_v19_august_holdout_v2.py. Results: EXP-SI-V19-AUGUST-HOLDOUT-20260807.

The protocol-selected candidate is pci; all_context is promising on this single August window but cannot be selected from the test result. No production promotion.

Status: completed_offline_time_out_validation.

## V20 8093/8094 影子预测合同（2026-08-08）

追踪编号：`REQ-SI-V20-8093-8094-SHADOW-WORKBENCH-20260808`

- 目标：运行时读取 220.12 本机 PostgreSQL 的 `heat_performance_quality_summary.si_avg`，即同一炉次全部有效铁水 Si 试样的算术平均。该字段的上游原始来源是 IMES 炉次铁水化验数据，由既有同步链路实时/回看下载到220.12后汇总生成；V20请求本身不直连IMES。
- 特征：严格更早炉次且 `source_updated_at <= prediction_cutoff_ts` 的已发布平均 Si；前 1～5 炉为五个独立字段，当前炉目标永远删除。
- 推荐口径：`target_open_ts - 60min`。允许当前点击或显式历史时刻，但偏离训练提前量超过 20 分钟必须返回告警。
- 输出：点预测、P10/P50/P90、模型/特征快照、预测时刻可见实际值；随后实际值通过炉号动态关联，不回写原预测。
- 写边界：只追加 `bf_assistant.si_v20_prediction_audit`；不修改炉次质量、传感器、喷煤、生产设定或模型选择表。
- 状态：`experimental_shadow`；模型仅含 14 项历史 Si/发布间隔特征，不使用已暂停的全集上下文。

