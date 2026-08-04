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
