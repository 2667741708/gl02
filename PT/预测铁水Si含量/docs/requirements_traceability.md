# 需求追踪

## REQ-SI-SEMANTIC-NEURON-ENGINE-20260726

### 用户目标

延续现有炉况规则引擎“有意义规则项”的思想，建立使用传感器时间序列、炉料
化学背景、炉况诊断和铁水化验预测 Si 实际分布的精简可解释引擎。

### 输入

- 炉次和开堵口时间；
- 传感器窗口统计与趋势；
- 炉况规则特征、分数和诊断；
- 前序炉铁水化验；
- 炉渣化验；
- 经谱系确认的炉料化学成分。

### 输出

- Si预测中心值；
- P10/P50/P90；
- 低于0.20%、位于0.20%～0.40%、高于0.40%的概率；
- 每个语义神经元的激活、贡献和输入证据；
- 数据质量、模型状态和拒绝预测原因。

### 实现映射

| 类型 | 位置 | 说明 |
|---|---|---|
| 思想 | [ideas/001](../ideas/001_有意义神经元的Si预测思想.md) | 原始假设与拓展方向 |
| 架构 | [architecture.md](architecture.md) | 数学结构、数据和验证合同 |
| 内核 | [engine.py](../src/si_semantic_engine/engine.py) | 神经元计算和分布输出 |
| CLI | [cli.py](../src/si_semantic_engine/cli.py) | 配置与特征文件推理入口 |
| 设计配置 | [semantic_neurons.design.json](../configs/semantic_neurons.design.json) | 未标定拓扑，禁止生产预测 |
| 测试 | [test_engine.py](../tests/test_engine.py) | 状态门、概率和可解释性 |
| 现有数据构建 | [build_hot_metal_si_dataset.py](../../../tools/build_hot_metal_si_dataset.py#L519) | 标签、诊断和传感器对齐基线 |
| 现有炉次宽表 | [heat_service.py](../../../db_dashboard/heat_service.py#L980) | 全铁水/炉渣/传感器特征入口 |

### 验收标准

- 未标定配置必须拒绝输出预测；
- 缺少必需特征必须拒绝预测并列出字段；
- 三段概率之和在浮点容差内等于1；
- 输出包含每个神经元的原始响应、激活和贡献；
- 经过时间切分回测后才能升级为影子运行；
- 不新增任何生产写入动作。

### 当前状态

`foundation_created_design_only_unfitted`

## 后续需求

| 编号 | 内容 | 状态 |
|---|---|---|
| `REQ-SI-DATASET-V2` | 扩展为炉次级全铁水/炉渣/133点宽表 | 待执行 |
| `REQ-SI-LAG-CALIBRATION` | 标定30/60/120/240分钟和前序炉滞后 | 待执行 |
| `REQ-SI-NEURON-FIT` | 带方向约束地学习权重、阈值和尺度 | 待执行 |
| `REQ-SI-DISTRIBUTION-CALIBRATION` | 校准P10/P50/P90和三区间概率 | 待执行 |
| `REQ-SI-SHADOW-RUN` | 220.12只读影子运行与实际化验对账 | 待执行 |
| `REQ-SI-MCP` | MCP查询、解释、相似炉次和图表 | 待执行 |
| `REQ-SI-TEMPORAL-NEURONS-V2-20260726` | ±0.05主验收、21组语义神经元和130点多窗口派生 | 代理实验完成；V3已物化133点60/120分钟，30/240分钟待执行 |
| `REQ-SI-FORMAL-LABEL-CONTRACT-V3-20260726` | 正式meltno、真实取样时间门禁、铁罐/铁口/阶段与三目标拆分 | 已完成 |
| `REQ-SI-FORMAL-DATASET-V3-20260726` | 开铁前133物理点正式炉次数据集 | 已完成 |
| `REQ-SI-FORMAL-TRAINING-V3-20260726` | 正式代表Si和整炉Si分布离线训练 | 已完成实验，禁止生产 |
| `REQ-SI-HYBRID-SEMANTIC-DEEP-V4` | 语义概念主干、NAM/HONAM、小型时序编码器和有界残差融合 | 已完成方案，待分阶段实现 |

## REQ-SI-EXPERIMENT-V1-20260726

### 目标

固定可重复、无跨炉次和时间泄漏的V1实验方法，生成公共炉次级处理数据，并比较
历史基线、规则特征模型、全量快照模型和语义神经元模型。

### 实现

| 类型 | 位置 |
|---|---|
| 方法 | [experiment_method_v1.md](experiment_method_v1.md) |
| 数据准备 | [experiment_data.py](../src/si_semantic_engine/experiment_data.py) |
| 数据CLI | [prepare_v1.py](../src/si_semantic_engine/prepare_v1.py) |
| 训练CLI | [train_v1.py](../src/si_semantic_engine/train_v1.py) |
| 测试 | [test_experiment_v1.py](../tests/test_experiment_v1.py) |

### 状态

`completed_experimental_v1_not_for_production`

### 实验结果

- 公共炉次级数据：1,669行、310列；
- 时间切分：训练1,168、验证250、测试251；
- 6种模型完成；
- 验证MAE选择：`full_extra_trees`；
- 测试MAE：`0.0498% Si`；
- 语义神经元测试MAE：`0.0551% Si`；
- 当前低Si/高Si召回不足，阻止进入生产预警。

结果见
[EXP-SI-V1-SEMANTIC-001_20260726_REPRO_A](../reports/experiments/EXP-SI-V1-SEMANTIC-001_20260726_REPRO_A/report.md)。

## REQ-SI-TEMPORAL-NEURONS-V2-20260726

### 目标

将主预测容差收紧至`±0.05个Si百分点`，把6个过宽语义神经元拆分，并为130个
pSpace/PostgreSQL传感器建立无未来泄漏的多窗口时序派生合同。

### 实现映射

| 类型 | 位置 |
|---|---|
| 思想与反例 | [ideas/002](../ideas/002_高延迟时序微神经元扩展.md) |
| 方法 | [experiment_method_v2.md](experiment_method_v2.md) |
| 单点时序派生 | [temporal_features.py](../src/si_semantic_engine/temporal_features.py) |
| 21组语义映射 | [expanded_neurons.py](../src/si_semantic_engine/expanded_neurons.py) |
| 跨点物理派生 | [physics_neurons.py](../src/si_semantic_engine/physics_neurons.py) |
| 训练与消融 | [train_v2.py](../src/si_semantic_engine/train_v2.py) |
| 配置合同 | [temporal_neuron_catalog.v2.json](../configs/temporal_neuron_catalog.v2.json) |
| 测试 | [test_temporal_features.py](../tests/test_temporal_features.py) |
| 结果 | [V2 REPRO A](../reports/experiments/EXP-SI-V2-EXPANDED-001_20260726_REPRO_A/report.md) |

### 验收结果

- 16项单元测试通过；
- 148/148规则特征唯一归入21组；
- A/B两次指标与逐炉预测哈希一致；
- 21神经元测试MAE `0.0500`、`±0.05`命中`60.2%`；
- 260特征最佳模型测试MAE `0.0498`、`±0.05`命中`62.2%`；
- 本机无`bf_sensor`，真实130点多窗口物化仍待执行。

### 状态

`implemented_proxy_experiment_v3_partial_real_sensor_windows`

## REQ-SI-FORMAL-LABEL-CONTRACT-V3-20260726

### 目标

以MES正式炉次为唯一标签身份，不从试样号猜炉次，不用结果时间替代取样时间，
并把整炉代表Si、下一试样Si、整炉Si分布拆成三个独立任务。

### 实现映射

| 类型 | 位置 |
|---|---|
| 数据合同 | [data_contract.md](data_contract.md) |
| 机器合同 | [si_label_contract.v3.json](../configs/si_label_contract.v3.json) |
| 标签代码 | [formal_labels.py](../src/si_semantic_engine/formal_labels.py) |
| 测试 | [test_formal_v3.py](../tests/test_formal_v3.py) |

### 验收

- 24,821条2#正式化验、9,337个正式炉次完成只读审计；
- 正式化验到炉次主表精确连接24,705条；
- `takesampletime`为0条，不启动下一试样训练；
- 铁口编号缺源，不从铁口测温推断；
- 结果时间替代取样时间标志固定为`false`。

状态：`completed_strict_contract_next_sample_blocked_by_source`

## REQ-SI-FORMAL-DATASET-V3-20260726

### 目标与实现

以MES `opentime`作为整炉预测截止点，读取截止前133个物理点的最近值、
60/120分钟变化量和斜率，按正式meltno形成一炉一行数据。

| 类型 | 位置 |
|---|---|
| 数据拼装 | [formal_dataset.py](../src/si_semantic_engine/formal_dataset.py) |
| 只读抽取 | [build_formal_si_dataset_v3.py](../../../tools/build_formal_si_dataset_v3.py) |
| 数据清单 | [manifest.json](../data/processed/formal_v3_20260726/manifest.json) |

结果：5,936条正式试样、2,366个正式炉次；排除66炉完整标签在截止前已可见
的非前瞻样本后，得到2,291炉训练数据、705列；切分1,603/344/344，同一正式
meltno不跨段。

状态：`completed_experimental_v3_formal_dataset`

## REQ-SI-FORMAL-TRAINING-V3-20260726

### 实现与结果

| 类型 | 位置 |
|---|---|
| 方法 | [experiment_method_v3.md](experiment_method_v3.md) |
| 训练 | [train_v3.py](../src/si_semantic_engine/train_v3.py) |
| 结果 | [V3实验](../reports/experiments/EXP-SI-V3-FORMAL-001_20260726_222525/report.md) |

- 代表Si ExtraTrees测试MAE `0.048851%`，`±0.05`命中`64.53%`；
- 分布P50测试MAE `0.048312%`；
- 80%共形区间平均宽度`0.210311%`；
- 预测分布带完整覆盖实际P10-P90仅`23.55%`；
- 下一试样任务由标签合同阻止。

状态：`completed_experimental_offline_not_for_mcp`

## REQ-SI-HYBRID-SEMANTIC-DEEP-V4

### 目标

把有意义神经元实现为可监督、可干预、可消融的概念层，并与ResTCN/1D ResNet
或训练期自监督PatchTST组合；深度分支只学习语义主干遗漏的有界残差。

### 方案与边界

| 类型 | 位置 |
|---|---|
| 总结与路线 | [experiment_summary_and_hybrid_roadmap.md](experiment_summary_and_hybrid_roadmap.md) |
| 问题追踪 | [question_traceability.md](question_traceability.md) |
| 现有语义内核 | [engine.py](../src/si_semantic_engine/engine.py) |
| 现有时序派生 | [temporal_features.py](../src/si_semantic_engine/temporal_features.py) |
| 正式数据合同 | [data_contract.md](data_contract.md) |

实现前置条件：

1. 统一滚动月份评估器；
2. 真实取样时间、铁口/阶段及炉料谱系继续补齐；
3. NAM/HONAM可解释强基线；
4. 小型ResTCN证明时间外残差增益；
5. 大模型不得绕过概念层、数据质量门和模型状态门。

状态：`planned_gated_not_implemented`

## REQ-SI-TEMPORAL-SEMANTIC-V5-20260727

### 目标

在V3正式炉次合同上持续扩展可解释历史、物理、空间和多窗口神经元，严格评估
`0.02% Si`目标及跨月稳定性。

### 实现与数据

| 类型 | 位置 |
|---|---|
| 方法 | [experiment_method_v5.md](experiment_method_v5.md) |
| V4派生 | [v4_features.py](../src/si_semantic_engine/v4_features.py) |
| 只读窗口提取 | [extract_v4_temporal_stats.py](../src/si_semantic_engine/extract_v4_temporal_stats.py) |
| V5宽表与筛选 | [v5_features.py](../src/si_semantic_engine/v5_features.py) |
| 训练与滚动回测 | [train_v5.py](../src/si_semantic_engine/train_v5.py) |
| 结果 | [V5实验](../reports/experiments/EXP-SI-V5-TEMPORAL-SEMANTIC-001_20260727/report.md) |

- 220.12只读事务确认133个物理点，提取304,703行并生成115个哈希分片；
- 固定验证选择后的测试MAE `0.047882`、`±0.02=31.10%`；
- 4个滚动月MAE范围`0.043577～0.075529`，稳定性不通过；
- 留一试样中位数变化均值`0.035541`，bootstrap中位数标准差均值`0.042798`；
- `0.02`目标状态为`not_reached`。

状态：`completed_offline_iteration_goal_not_reached_not_for_mcp`

## REQ-SI-THERMAL-STATE-V6-20260727

### 目标与实现

在正式炉次截止时刻前构造多尺度热状态语义神经元，并接入当时已发布的前炉
Si/C/Mn/P/S 历史。

| 类型 | 位置 |
|---|---|
| 方法 | [experiment_method_v6_v9.md](experiment_method_v6_v9.md) |
| 特征 | [v6_features.py](../src/si_semantic_engine/v6_features.py) |
| 训练 | [train_v6.py](../src/si_semantic_engine/train_v6.py) |
| 结果 | [V6实验](../reports/experiments/EXP-SI-V6-THERMAL-CHEM-4H-002_20260727/report.md) |
| 测试 | [test_v6_features.py](../tests/test_v6_features.py) |

门禁：前炉化验必须来自不同且更早的正式炉次，结果时间不晚于当前开铁时刻；
`T_taphole_1/2`只作代理。V6历史测试MAE `0.047832`，`±0.02=25.29%`。

状态：`completed_offline_goal_not_reached_temperature_head_blocked`

## REQ-SI-ROBUST-ENSEMBLE-V7-20260727

比较直接回归、热状态残差回归与历史基线的跨月稳健非负集成。

| 类型 | 位置 |
|---|---|
| 训练 | [train_v7.py](../src/si_semantic_engine/train_v7.py) |
| 结果 | [V7实验](../reports/experiments/EXP-SI-V7-ROBUST-ENSEMBLE-001_20260727/report.md) |

结果：选择退化为100%热状态XGBoost；训练+验证重拟合使历史测试MAE恶化到
`0.051872`，确认近期概念漂移风险。

状态：`completed_negative_result_offline`

## REQ-SI-LGBM-ROBUST-V8-20260727

以LightGBM Huber/L1比较直接与前炉Si残差目标、叶子复杂度、90天衰减权重，
并输出Si P10/P50/P90。

| 类型 | 位置 |
|---|---|
| 训练 | [train_v8.py](../src/si_semantic_engine/train_v8.py) |
| 4小时结果 | [V8 4h](../reports/experiments/EXP-SI-V8-LGBM-ROBUST-001_20260727/report.md) |
| 8小时结果 | [V8 8h](../reports/experiments/EXP-SI-V8-LGBM-PARETO-8H-003_20260727/report.md) |
| 8小时数据 | [manifest.json](../data/processed/formal_v6_temporal_stats_8h_20260727/manifest.json) |

结果：4小时单模型历史测试MAE `0.047171`；8小时模型跨月稳健分数
`0.058052`，历史测试MAE `0.047777`、`±0.02=27.03%`。P10-P90覆盖率
`73.84%～75.87%`，尚未通过发布门。

状态：`completed_offline_distribution_not_calibrated`

## REQ-SI-MULTIMODEL-ENSEMBLE-V9-20260727

将直接ExtraTrees、热状态XGBoost、两种LightGBM和历史基线组成五分量非负
单纯形，在4/5/6月选择后读取历史7月测试。

| 类型 | 位置 |
|---|---|
| 训练 | [train_v9.py](../src/si_semantic_engine/train_v9.py) |
| 结果 | [V9 8h](../reports/experiments/EXP-SI-V9-MULTIMODEL-PARETO-8H-002_20260727/report.md) |
| 总结 | [V6～V9报告](../reports/2026-07-27_V6_V9热状态软测量持续实验.md) |

结果：历史测试MAE `0.047098`，相对V5改善约`1.64%`；`±0.02=25.00%`。
最高窄带命中仍是直接ExtraTrees分量的`31.10%`。历史7月已不再是新盲测。

状态：`completed_offline_best_point_mae_goal_not_reached_not_for_mcp`

## REQ-SI-LAG-FIELD-MODES-V10-20260727

### 目标与实现

将累计窗口拆成非重叠时延带，并把静压力、炉顶和炉身温度表示成可解释圆周
场模态。

| 类型 | 位置 |
|---|---|
| 方法 | [experiment_method_v10_v12.md](experiment_method_v10_v12.md) |
| 特征 | [v10_features.py](../src/si_semantic_engine/v10_features.py) |
| 训练 | [train_v10.py](../src/si_semantic_engine/train_v10.py) |
| 测试 | [test_v10_features.py](../tests/test_v10_features.py) |
| 结果 | [V10实验](../reports/experiments/EXP-SI-V10-LAG-FIELD-8H-001_20260727/report.md) |

新增2,660个时延带和1,390个空间场模态。预测试稳健分数`0.057910`，优于同模型
旧特征参考`0.058052`；历史测试MAE`0.048049`。与V9配对bootstrap的MAE差
95%区间为`-0.000083～+0.002016`，未形成显著差异。

状态：`completed_offline_pretest_gain_historical_not_significant`

## REQ-SI-LABEL-RELIABILITY-V11-20260727

比较整炉中位Si、均值混合训练目标，以及由试样数和炉内标准差构造的训练权重。
发布与评价目标始终保持正式整炉中位Si，标签统计不得进入推理特征。

| 类型 | 位置 |
|---|---|
| 训练 | [train_v11.py](../src/si_semantic_engine/train_v11.py) |
| 测试 | [test_v11_label_reliability.py](../tests/test_v11_label_reliability.py) |
| 结果 | [V11实验](../reports/experiments/EXP-SI-V11-LABEL-RELIABILITY-8H-001_20260727/report.md) |

结果选择回`median_uniform`，说明简单标签平滑和离散度降权未通过跨月验证。

状态：`completed_negative_result_offline`

## REQ-SI-LAG-FIELD-ENSEMBLE-V12-20260727

在4/5/6月用0.05步长非负单纯形组合直接ExtraTrees、热状态XGBoost、原热状态
LightGBM与V10时延场LightGBM。

| 类型 | 位置 |
|---|---|
| 训练 | [train_v12.py](../src/si_semantic_engine/train_v12.py) |
| 结果 | [V12实验](../reports/experiments/EXP-SI-V12-LAG-FIELD-ENSEMBLE-8H-001_20260727/report.md) |
| 总结 | [V10～V12报告](../reports/2026-07-27_V10_V12时延场与标签可靠性实验.md) |

结果权重退化为`lgbm_lag_field=1.0`，没有专家互补增益；历史MAE仍为`0.048049`。

状态：`completed_negative_ensemble_offline_goal_not_reached`

## REQ-SI-PROSPECTIVE-BLIND-V1-20260727

冻结V9历史点MAE模型与V10预测试稳定模型，禁止继续使用历史7月做候选选择。

| 类型 | 位置 |
|---|---|
| 协议 | [prospective_blind_protocol.v1.json](../configs/prospective_blind_protocol.v1.json) |
| 测试 | [test_prospective_protocol.py](../tests/test_prospective_protocol.py) |

准入条件：预测截止严格晚于2026-07-27 00:00，正式meltno存在，预测写入早于
标签可见时刻，至少300炉且覆盖30天；两个冻结模型的SHA-256由测试重新校验。

状态：`superseded_by_strict_history_protocol_v4`

## REQ-SI-STRICT-EARLIER-HISTORY-V3-20260727

修正前炉历史合同：只允许预测截止严格更早且标签已发布的炉次；历史Si浮点特征
统一保留12位小数，保证CSV持久化与在线重建一致。

| 类型 | 位置 |
|---|---|
| 实现 | [formal_dataset.py](../src/si_semantic_engine/formal_dataset.py) |
| 快照工具 | [repair_v3_history_snapshot.py](../src/si_semantic_engine/repair_v3_history_snapshot.py) |
| 修复快照 | [manifest.json](../data/processed/formal_v3_historyfix_r12_20260727/manifest.json) |
| 测试 | [test_formal_v3.py](../tests/test_formal_v3.py) |

结果：2,291炉身份、传感器、标签和切分不变，6炉历史字段被修正。

状态：`completed_immutable_history_contract_repair`

## REQ-SI-LAG-MOMENT-NEURONS-V13-20260727

从累计计数、均值和样本标准差恢复五个非重叠时延带的二阶矩，构造波动、均方根、
变异系数、标准化冲击和波动剖面。

| 类型 | 位置 |
|---|---|
| 方法 | [experiment_method_v13_prospective.md](experiment_method_v13_prospective.md) |
| 特征 | [v13_features.py](../src/si_semantic_engine/v13_features.py) |
| 训练 | [train_v13.py](../src/si_semantic_engine/train_v13.py) |
| 测试 | [test_v13_features.py](../tests/test_v13_features.py) |
| 结果 | [V13实验](../reports/experiments/EXP-SI-V13-LAG-MOMENT-HISTORYFIXR12-001_20260727/report.md) |

新增4,123个候选神经元。预测试稳健分数`0.057979`；历史MAE`0.047108`，
`±0.02=29.36%`。相对V9的MAE配对95%区间跨0，未达到`0.02`目标。

状态：`completed_offline_pretest_gain_historical_mae_not_significant`

## REQ-SI-PROSPECTIVE-RUNNER-V1-20260727

实现冻结模型哈希校验、当前炉目标删除、特征重建、只追加预测账本、延迟标签结算
和300炉/30天门禁。当前V4协议冻结V9/V10/V13。

| 类型 | 位置 |
|---|---|
| 实现 | [prospective.py](../src/si_semantic_engine/prospective.py) |
| 回放 | [replay_validate_prospective.py](../src/si_semantic_engine/replay_validate_prospective.py) |
| 协议 | [prospective_blind_protocol.v4.json](../configs/prospective_blind_protocol.v4.json) |
| 回放证据 | [prospective_replay_v4_lagmoment_20260727.json](../reports/prospective_replay_v4_lagmoment_20260727.json) |
| 测试 | [test_prospective_runner.py](../tests/test_prospective_runner.py) |

344炉无目标回放最大差异：V9 `1.67e-16`、V10/V13 `8.33e-17`，均通过
`1e-10`门槛。V2协议因未量化历史浮点导致V9回放失败，已明确标记失效。

状态：`implemented_frozen_waiting_for_future_heats`

## REQ-SI-SEMANTIC-LATENT-STATE-V14-20260727

在训练折内把热量输入、煤气利用、透气性、料面、出铁口代理、静压力场和炉体热场
压缩为监督PLS残差因子，再比较四类回归器。

| 类型 | 位置 |
|---|---|
| 方法 | [experiment_method_v14_v15.md](experiment_method_v14_v15.md) |
| 训练 | [train_v14.py](../src/si_semantic_engine/train_v14.py) |
| 测试 | [test_v14_latent_groups.py](../tests/test_v14_latent_groups.py) |
| 结果 | [V14实验](../reports/experiments/EXP-SI-V14-SEMANTIC-LATENT-HISTORYFIXR12-001_20260727/report.md) |

结果：预测试稳健分数`0.059846`、历史MAE`0.049303`，弱于V13，不进入前瞻
协议。

状态：`completed_negative_result_offline`

## REQ-SI-BEST-RESPONSE-LAG-V15-20260727

以“代表Si减已发布历史Si基线”的残差为折内选择目标，每个物理变量和响应族只
保留一个非重叠最佳时延。

| 类型 | 位置 |
|---|---|
| 方法 | [experiment_method_v14_v15.md](experiment_method_v14_v15.md) |
| 训练 | [train_v15.py](../src/si_semantic_engine/train_v15.py) |
| 测试 | [test_v15_best_response_lag.py](../tests/test_v15_best_response_lag.py) |
| 结果 | [V15实验](../reports/experiments/EXP-SI-V15-BEST-RESPONSE-LAG-HISTORYFIXR12-001_20260727/report.md) |
| 配对 | [v15_vs_v13_paired_20260727.json](../reports/v15_vs_v13_paired_20260727.json) |

结果：802项变量×响应族中仅335项跨三折完全稳定；紧凑候选稳健分数
`0.059067`，最终选模退回V13，逐炉预测差为0，不进入前瞻协议。

状态：`completed_negative_result_offline_reference_unchanged`

## REQ-SI-RESIDUAL-ALIGNED-SELECTION-V16-20260727

在每个训练折内用已发布历史Si基线残差，对8,173个新时延、空间场和波动神经元
重做ExtraTrees重要性选择。

| 类型 | 位置 |
|---|---|
| 方法 | [experiment_method_v16_v18.md](experiment_method_v16_v18.md) |
| 训练 | [train_v16.py](../src/si_semantic_engine/train_v16.py) |
| 测试 | [test_v16_residual_selection.py](../tests/test_v16_residual_selection.py) |
| 结果 | [V16实验](../reports/experiments/EXP-SI-V16-RESIDUAL-ALIGNED-HISTORYFIXR12-001_20260727/report.md) |

V16专属最佳稳健分数`0.058597`，最终退回V13。状态：
`completed_negative_result_offline_reference_unchanged`。

## REQ-SI-CATBOOST-ORDERED-V17-20260727

校验V13输入哈希、训练行数和配方数量后复用逐折选择审计，测试CatBoost Ordered
boosting。001、002两次均在1004秒超时，没有完整指标产物。

| 类型 | 位置 |
|---|---|
| 训练 | [train_v17.py](../src/si_semantic_engine/train_v17.py) |
| 测试 | [test_v17_catboost_cache.py](../tests/test_v17_catboost_cache.py) |
| 总结 | [V16～V18报告](../reports/2026-07-27_V16_V18残差选择与CatBoost实验.md) |

状态：`completed_runtime_negative_no_model_result`。

## REQ-SI-CATBOOST-PLAIN-V18-20260727

复用V13已验证配方，比较200轮Plain CatBoost MAE/RMSE残差模型。

| 类型 | 位置 |
|---|---|
| 训练 | [train_v18.py](../src/si_semantic_engine/train_v18.py) |
| 测试 | [test_v18_plain_specs.py](../tests/test_v18_plain_specs.py) |
| 结果 | [V18实验](../reports/experiments/EXP-SI-V18-CATBOOST-PLAIN-HISTORYFIXR12-001_20260727/report.md) |
| 正式报告 | [当前最优实验报告](../reports/当前最优铁水Si预测实验报告_20260727.docx) |

稳健分数`0.060185`、历史MAE`0.049539`，弱于V13。状态：
`completed_negative_result_offline`。

## REQ-SI-REPORT-ALGORITHM-FLOWCHART-20260727

把“输入数据→可解释热状态神经元→炉内潜在热状态→温度/Si/热状态三任务头”
绘制为确定性中文流程图并嵌入当前最优Word报告。已实现与待标签分支必须显式区分，
不得把真实温度和热状态概率写成已训练。

| 类型 | 位置 |
|---|---|
| 制图 | [generate_algorithm_flowchart.py](../tools/generate_algorithm_flowchart.py) |
| 报告生成 | [generate_current_best_experiment_report.py](../tools/generate_current_best_experiment_report.py) |
| PNG | [铁水Si联合热状态算法流程图](../reports/assets/铁水Si联合热状态算法流程图_20260727.png) |
| Word报告 | [当前最优实验报告](../reports/当前最优铁水Si预测实验报告_20260727.docx) |

验证：PNG为高分辨率图片；Word包含图1标题及嵌入图像；标题黑体、正文宋体小四。

状态：`completed_document_visualization`。

## REQ-SI-AVERAGE-CURVE-22012-20260806

从220.12读取最近15天每炉铁水Si算术平均值，使用平均Si目标的当前自适应权重
模型生成逐炉预测，并在同一张图比较真实和预测趋势；同时核查新增喷煤点位和
IMES炉料化学分析数据，为后续前5炉Si输入升级做准备。

| 类型 | 位置 |
|---|---|
| 平均值目标合同 | [formal_dataset.py](../src/si_semantic_engine/formal_dataset.py) |
| 220.12数据源审计 | [audit_22012_si_prediction_sources.py](../../../tools/audit_22012_si_prediction_sources.py) |
| IMES化学审计 | [audit_22012_imes_sinter_chemistry.py](../../../tools/audit_22012_imes_sinter_chemistry.py) |
| 曲线回放 | [run_22012_si_average_curve.py](../../../tools/run_22012_si_average_curve.py) |
| 测试 | [test_si_average_curve.py](../tests/test_si_average_curve.py) |
| 结果报告 | [最近15天平均Si曲线报告](../reports/2026-08-06_22012最近15天逐炉平均Si真实预测曲线.md) |

验收：220炉均有`si_avg`；全窗口MAE 0.04034、±0.05命中73.18%；严格时间外
155炉MAE 0.03848。逐炉方向一致率约50%，未达逐炉趋势标准。只读执行，未修改
220.12、生产模型或接口。

状态：`completed_offline_replay_not_production`。

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


## REQ-SI-V20-OPEN-MINUS-HITRATE-20260807

把目标场景固定为“每炉开口前 1 小时预测平均 Si”，验证能否把昨日样本
±0.05 命中率从 46.67% 提升到至少 60%，同时 MAE 不恶化。V20 保持离线/影子：
不替换生产模型、不写 220.12 业务表。

| 类型 | 位置 |
|---|---|
| 特征函数 | [v20_open_minus_features.py](../src/si_semantic_engine/v20_open_minus_features.py) |
| 数据集构建 | [build_open_minus_si_dataset_v20.py](../../../tools/build_open_minus_si_dataset_v20.py) |
| 训练评估 | [train_open_minus_si_v20.py](../../../tools/train_open_minus_si_v20.py) |
| 单炉影子预测兼容入口 | [predict_next_heat_si_v19.py](../../../tools/predict_next_heat_si_v19.py) |
| CLI手册 | [cli_usage.md](../../../docs/cli_usage.md#平均-si-v20-开口前命中率影子实验) |
| 数据合同 | [data_contract.md](data_contract.md#6-v20-开口前-1-小时平均-si-合同2026-08-07) |
| 测试 | [test_v20_open_minus_features.py](../tests/test_v20_open_minus_features.py) |

数据合同：`target__Si_mean` 使用修复后汇总表的 `si_avg` 算术平均；主 cutoff 为
`open_ts - 60min`，同时生成 `120/90/60/30/15/0min` 对照；前 1～5 炉 Si 是 5 个
独立字段，只使用严格更早且已发布的平均 Si；喷煤和传感器窗口均为
`[cutoff-window, cutoff)`，当前小时正式喷煤只有数据水位不超过 cutoff 才可用。
IMES烧结矿化学仅为低置信度时间背景。

验证：2026-08-07 已执行 V20 纯单元测试 `Ran 7 tests / OK`，并对三个 CLI 入口
执行 `--help` 加载检查。完整数据库回放和训练需在 VPN/220.12 可达时运行。

状态：`implemented_experimental_offline_not_promoted`。


## REQ-SI-V21-SENSOR-CACHE-20260808

把 V20 开口前平均 Si 预测中的核心28点和严格133点传感器窗口改为本机预聚合缓存，
减少 220.12 数据库聚合压力，并验证“直接加入更多物理窗口”是否能提升确认集
±0.05 命中率。

| 类型 | 位置 |
|---|---|
| 缓存构建 | [build_v20_sensor_window_cache.py](../../../tools/build_v20_sensor_window_cache.py) |
| 缓存合并数据集 | [materialize_v21_dataset_from_sensor_cache.py](../../../tools/materialize_v21_dataset_from_sensor_cache.py) |
| V20构建器缓存参数 | [build_open_minus_si_dataset_v20.py](../../../tools/build_open_minus_si_dataset_v20.py) |
| 训练候选过滤 | [train_open_minus_si_v20.py](../../../tools/train_open_minus_si_v20.py) |
| 单测 | [test_v21_sensor_window_cache.py](../tests/test_v21_sensor_window_cache.py) |
| 实验报告 | [v21_sensor_cache_20260808.md](v21_sensor_cache_20260808.md) |

数据合同：缓存按 `v20_sample_id` 对齐，窗口严格为
`[prediction_cutoff_ts - window, prediction_cutoff_ts)`；缺失保持缺失，覆盖率单独记录，
不使用 0 填充；原始分钟值中的非有限值被过滤；`process133` 排除 `EQ_` 前缀点位。

验证：2026-08-08 在 220.12 只读数据上生成 2268 行 process133 缓存，133 点、
8379 个窗口特征；同源切出 core28 的 1764 个窗口特征。core28 完整候选验证
±0.05 `73.33%`、确认 `54.84%`；process133 高维候选子集验证 `72.00%`、确认
`51.61%`。同数据历史消融确认 `58.06%` 最稳。结论为缓存有效但未提升确认集，
不晋升影子候选。2026-08-08 用户决策：不再使用全集上下文，默认回到 V19
August holdout；V20 构建器默认点位改为 `core28`，`process133/all` 必须显式
指定且仅用于离线研究。

状态：`experimental_offline_paused_reverted_to_v19_default`。


## REQ-SI-FUELRATIO-V20-SIDE-BY-SIDE-20260808

在相同炉号、相同开口时间和相同实际平均 Si 标签上，并列评估工长燃料比经验法与
V20 历史 Si 方法；V19 一键模型仅作为不同时间口径的历史背景，不参与直接排名。

| 类型 | 位置 |
|---|---|
| 并列评估程序 | [compare_foreman_fuel_vs_v20_history.py](../../../tools/compare_foreman_fuel_vs_v20_history.py) |
| 结果说明 | [fuel_ratio_v20_side_by_side_20260808.md](fuel_ratio_v20_side_by_side_20260808.md) |
| 指标 JSON | [side_by_side_metrics.json](../reports/experiments/EXP-SI-FUELRATIO-V20-COMPARE-20260808/side_by_side_metrics.json) |
| 逐炉 CSV | [side_by_side_predictions.csv](../reports/experiments/EXP-SI-FUELRATIO-V20-COMPARE-20260808/side_by_side_predictions.csv) |

结果：V20 验证+确认段可对齐 7 炉，历史 Si 法 ±0.05 为 `57.14%`、MAE `0.0580`；
工长固定 0.30 基准经验法为 `0.00%`、MAE `0.7358`。样本受 MES 日报单炉前块限制，
只作小样本证据，不替代 V20 完整 75 炉验证/27 炉确认指标。

状态：`completed_offline_small_common_sample_not_promoted`。

## REQ-SI-V20-8093-8094-SHADOW-WORKBENCH-20260808

把 V20 历史 Si 模型作为独立影子功能部署到 8093 与 8094，允许所有能够打开页面的用户：在当前时刻或指定截止时刻预测目标炉次平均 Si；按日期执行开口前 60 分钟历史回放；查看预测曲线、随后发布的实际平均 Si、误差和 ±0.05 命中状态。V20 本身不要求生产账号登录。

实现位置：`高炉前端数据/智能助手/backend/si_v20_shadow.py`、`高炉前端数据/assets/bf-si-v20-shadow-workbench.js`、`tools/patch_si_v20_shadow_workbench_surfaces.py`、`tools/remote_guarded_deploy_si_v20_shadow_workbench.ps1`。实际值固定读取 `bf_assistant.heat_performance_quality_summary.si_avg`；预测只写 `bf_assistant.si_v20_prediction_audit`，不写炉次事实表、不调整生产设定值。当前炉目标和截止时刻后发布的化验严格不进入特征。

2026-08-08 已部署：8093/8094 状态与历史 API 均为 HTTP 200，`require_login=false`；模型 `ablation_history`、14 项历史特征、训练提前量 60 分钟、模型 SHA-256 `FD31DB24EF9B4E9C81BAAE81A46693E5B9F2E539DBEC9C2B75AE95946055FC8C`；8093 守卫恢复，8768/8770/11434 PID 未变化。状态：`deployed_experimental_shadow_public_prediction`，不替换生产默认模型。

