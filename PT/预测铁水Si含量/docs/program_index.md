# 程序索引

## `src/si_semantic_engine/engine.py`

职责：加载版本化配置、计算语义神经元、合成Si中心值和概率分布。

| 符号 | 说明 |
|---|---|
| [`SemanticNeuron`](../src/si_semantic_engine/engine.py#L58) | 单个有意义神经元 |
| [`SemanticNeuron.evaluate`](../src/si_semantic_engine/engine.py#L100) | 输入校验、响应、激活和贡献 |
| [`SemanticSiEngine`](../src/si_semantic_engine/engine.py#L133) | 模型合同与状态 |
| [`SemanticSiEngine.predict`](../src/si_semantic_engine/engine.py#L180) | 分布、目标带概率和贡献输出 |

修改风险：改变激活、中心化或概率计算会影响所有模型版本，必须增加兼容性测试。

## `src/si_semantic_engine/cli.py`

职责：从JSON加载已标定配置和单炉特征，返回JSON结果或结构化错误。

| 符号 | 说明 |
|---|---|
| [`build_parser`](../src/si_semantic_engine/cli.py#L27) | CLI参数 |
| [`main`](../src/si_semantic_engine/cli.py#L41) | 推理和错误边界 |

## `configs/semantic_neurons.design.json`

职责：保存第一版神经元拓扑和字段合同。状态为未标定，所有贡献系数是结构占位，
禁止用于预测。

## `tests/test_engine.py`

职责：验证状态门、输入校验、概率守恒、贡献可见性和正向神经元行为。

## `src/si_semantic_engine/experiment_data.py`

| 符号 | 说明 |
|---|---|
| [`assign_chronological_splits`](../src/si_semantic_engine/experiment_data.py#L176) | 固定70/15/15时间切分 |
| [`build_heat_level_dataset`](../src/si_semantic_engine/experiment_data.py#L203) | 试样归炉、标签聚合和前序炉可用性 |
| [`write_prepared_dataset`](../src/si_semantic_engine/experiment_data.py#L241) | 保存公共处理层、切分与哈希 |

## `src/si_semantic_engine/train_v1.py`

| 符号 | 说明 |
|---|---|
| [`regression_metrics`](../src/si_semantic_engine/train_v1.py#L57) | MAE、命中、区间和异常召回 |
| [`semantic_feature_groups`](../src/si_semantic_engine/train_v1.py#L226) | 六个有意义神经元的字段分组 |
| [`fit_semantic_model`](../src/si_semantic_engine/train_v1.py#L311) | 时间序列交叉拟合神经元 |
| [`export_semantic_engine`](../src/si_semantic_engine/train_v1.py#L379) | 导出可审计实验配置和标准化合同 |
| [`run_experiment`](../src/si_semantic_engine/train_v1.py#L519) | 六模型训练、选择、校准和产物哈希 |

## `src/si_semantic_engine/temporal_features.py`

职责：从`ts/sensor_id/value/quality`长表提取无未来泄漏的多窗口时序微神经元。

| 符号 | 说明 |
|---|---|
| [`TemporalFeatureConfig`](../src/si_semantic_engine/temporal_features.py#L28) | 窗口、频率、最少点数和尖峰阈值合同 |
| [`derive_temporal_micro_neurons`](../src/si_semantic_engine/temporal_features.py#L204) | 30/60/120/240分钟水平、趋势、波动、记忆和质量特征 |
| [`temporal_feature_names`](../src/si_semantic_engine/temporal_features.py#L279) | 不读取数据即可生成确定性字段合同 |

## `src/si_semantic_engine/expanded_neurons.py`

职责：通过
[`expanded_semantic_feature_groups`](../src/si_semantic_engine/expanded_neurons.py#L139)
将148个V1规则特征唯一拆分为21个工艺语义神经元，并固定`±0.05`主容差。

## `src/si_semantic_engine/physics_neurons.py`

职责：由
[`derive_physics_composite_neurons`](../src/si_semantic_engine/physics_neurons.py#L54)
计算风压—顶压裕度、压差分配、南北料线差、顶温/顶压离散、18点静压力
纵向梯度、炉身7～16层圆周离散和纵向温度梯度；缺失输入不得静默补0。

## `src/si_semantic_engine/train_v2.py`

职责：由[`run_experiment`](../src/si_semantic_engine/train_v2.py#L228)
比较6组与21组神经元、260特征模型，按验证集`±0.05`命中率选择模型，
输出逐神经元中性消融、配置、预测、报告和哈希。

## `src/si_semantic_engine/formal_labels.py`

职责：强制MES正式meltno身份，保留真实取样时间缺失，计算铁罐/铁口/出铁阶段
状态，并分别生成整炉代表Si、下一试样Si和整炉Si分布目标。

| 符号 | 说明 |
|---|---|
| `normalize_formal_samples` | 严格过滤正式炉次与有效Si，不做试样号修复 |
| `build_heat_targets` | 一炉一行代表值及min/P10/P50/P90/max/std/spread |
| `build_next_sample_targets` | 只按真实取样时间生成下一试样标签 |
| `validate_training_task` | 数据源不满足目标合同时拒绝训练 |

## `src/si_semantic_engine/formal_dataset.py`

职责：把正式炉次目标与严格早于开铁时刻的传感器特征连接，附加当时已发布的
前序炉Si，并做按正式meltno互斥的70/15/15时间切分及SHA-256清单。

## `tools/build_formal_si_dataset_v3.py`

职责：只读连接MES与220.12 PostgreSQL，精确连接
`heatno/meltno/batchno/thankno`，并为133物理点提取开铁前当前、60分钟和120分钟
特征。只写本机实验产物，不写生产数据库。

## `src/si_semantic_engine/train_v3.py`

职责：比较前序炉基线、岭回归和ExtraTrees，训练正式代表Si；用多输出
ExtraTrees训练整炉P10/P50/P90；用验证集split-conformal校准代表值80%区间；
对缺少真实取样时间的下一试样任务保持阻止状态。

## 混合网络规划文档

- [experiment_summary_and_hybrid_roadmap.md](experiment_summary_and_hybrid_roadmap.md)：
  V1～V3证据总结、概念瓶颈/NAM/ResTCN/PatchTST混合架构、实验矩阵和阶段门。
- [question_traceability.md](question_traceability.md)：
  用户关于有意义神经元与Transformer/ResNet联合的结论、证据和后续实现面。

当前只有方案，没有新增深度模型代码；状态不得写成已训练或可用。

## V4/V5 持续迭代

- `v4_features.py`：133点语义映射、44个可见前炉历史神经元、物理组合动态重建；
- `train_v4.py`：固定验证候选选择、`±0.02`指标和锁定测试；
- `extract_v4_temporal_stats.py`：只读提取30/60/120/240分钟统计，分片Parquet、
  断点续跑和SHA-256清单；
- `v5_features.py`：多窗口长表转炉次宽表、空间汇总和训练段Spearman筛选；
- `train_v5.py`：固定验证选择、滚动月份回测、标签稳定性分析和实验产物。

V4/V5没有实现深度模型，也没有生产推理入口。

## V6～V9 热状态软测量

- `extract_v4_temporal_stats.py`：窗口参数化，默认保持30/60/120/240分钟兼容，
  V6调用增加480分钟，数据库回看范围自动取最大窗口；
- `v5_features.py`：从清单动态识别完整窗口，逐分片校验SHA-256后才加载；
- `v6_features.py`：构造多尺度差异、热输入、煤气利用、透气性、料线、静压力场、
  炉体热场、出铁口温度代理和前炉化验历史特征；
- `train_v6.py`：直接/残差目标、样本时间衰减、跨月稳健选择及Si分布头；
- `train_v7.py`：三分量非负集成和重拟合对照；
- `train_v8.py`：LightGBM Huber/L1稳健模型、Pareto窄带次目标和分位数头；
- `train_v9.py`：五分量非负单纯形集成。

所有训练入口都会审计真实铁水温度标签。当前非空温度为0，因此温度回归与热状态
概率头保持阻止，不存在生产推理入口。

## V10～V12 时延场与标签实验

- `v10_features.py`：从嵌套累计统计恢复0–30、30–60、60–120、120–240、
  240–480分钟非重叠时延带；计算A～F静压力和A～H炉体温度圆周一/二阶模态、
  三高度梯度与7～16层纵向相干性；
- `train_v10.py`：逐折重建新特征相关性/ExtraTrees重要性排序，比较旧特征参考、
  新时延场和混合配方；
- `train_v11.py`：比较训练期中位数—均值平滑目标及按试样数/炉内标准差构造的
  标签可靠性权重；
- `train_v12.py`：用0.05步长非负单纯形组合直接、热状态和时延场四个专家。

V10～V12均只输出离线实验模型，不修改MCP或生产数据库。

## 前瞻盲测冻结

`configs/prospective_blind_protocol.v1.json`固定V9/V10候选模型哈希、未来数据
边界、最小炉次数/日历跨度、指标和禁止中途选模规则；
`tests/test_prospective_protocol.py`重新计算冻结模型SHA-256并检查未来边界严格
晚于历史数据最大截止时刻。

## 严格历史、V13与前瞻运行

- `repair_v3_history_snapshot.py`：从完整正式炉次目标重算严格更早且已发布的前炉
  Si历史，生成不覆盖旧数据的新快照与SHA-256清单；
- `v13_features.py`：用累计一阶/二阶矩相减恢复非重叠时延带波动、均方根、
  标准化冲击和波动剖面；
- `train_v13.py`：在4/5/6月折内重建相关性和重要性选择，训练V13点预测及
  P10/P50/P90；
- `compare_predictions.py`：对不可变逐炉预测执行配对bootstrap；
- `prospective.py`：校验冻结模型哈希、重建无目标特征、追加预测账本并延迟结算；
- `replay_validate_prospective.py`：将V9/V10/V13无目标推理与实验产物逐炉比对。

当前权威前瞻协议为`configs/prospective_blind_protocol.v4.json`。V1保留为历史
冻结记录，V2因回放不一致标记失效，V3为V9/V10量化修复版，V4增加V13。

## V14～V15 语义压缩与响应时延

- `train_v14.py`：折内按七类业务对象筛选特征，用PLS把历史Si残差压缩为组级
  潜因子并比较Ridge/ExtraTrees/XGBoost/LightGBM；
- `train_v15.py`：解析非重叠均值、波动、能量和冲击特征，按变量×响应族相对
  历史Si残差选择单一最佳时延；
- `compare_predictions.py`：同名预测列在配对合并前重命名为内部A/B列，避免
  pandas后缀导致`KeyError`。

V14/V15均为离线负结果，不进入`prospective_blind_protocol.v4.json`。

## V16～V18 残差选择与CatBoost

- `train_v16.py`：以已发布历史Si基线残差为折内重要性目标；
- `train_v17.py`：校验V13输入哈希和选择审计后重建配方，提供CatBoost训练
  公共实现；Ordered实验两次超时；
- `train_v18.py`：限制为200轮Plain MAE/RMSE残差对照；
- `tools/generate_current_best_experiment_report.py`：生成黑体标题、宋体小四正文
  的V9～V18正式Word报告。
- `tools/generate_algorithm_flowchart.py`：确定性绘制中文多任务热状态算法流程图，
  用实线/虚线区分当前Si分支和待真实标签的温度/热状态分支。

V16/V18为负结果；V17无完整模型结果。CatBoost不加入生产运行依赖。
