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

## 2026-08-06 220.12逐炉平均Si曲线

- `formal_dataset.py::prepare_training_target`：把训练目标显式切换为
  `target__Si_mean`，并用平均值重建前炉历史，避免目标和历史口径混用；
- `tools/audit_22012_si_prediction_sources.py`：只读核查平均Si表、传感器目录、
  新增物理/派生点和候选数据表；
- `tools/audit_22012_imes_sinter_chemistry.py`：经220.12只读转发审计烧结矿
  进料化学分析视图，不输出凭据；
- `tools/run_22012_si_average_curve.py`：提取最近15天炉次、传感器多窗口特征，
  以平均Si V9自适应权重模型生成逐炉预测、指标、CSV和PNG；
- `tools/rebuild_si_average_curve_from_cache.py`：从缓存重建预测和曲线；
- `tests/test_si_average_curve.py`：固定算术平均标签、图表指标和残差分量基线还原。

完整结论见[最近15天平均Si曲线报告](../reports/2026-08-06_22012最近15天逐炉平均Si真实预测曲线.md)。

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

V20 open-minus shadow experiment: optimize the operational scene “predict each heat mean Si before opening”, with main cutoff `open_ts - 60min` and lead-time comparisons at `120/90/60/30/15/0min`.

Implementation:

- `src/si_semantic_engine/v20_open_minus_features.py`：纯特征与指标函数，覆盖前 1～5 个已发布平均 Si、未化验炉次间隔、PCI 8/12h 窗口、传感器窗口透视和指标；
- `tools/build_open_minus_si_dataset_v20.py`：只读 220.12 修复后炉次质量、传感器和喷煤，构建 V20 数据集、标签 CSV、数据合同和泄漏审计；
- `tools/train_open_minus_si_v20.py`：按时间顺序训练 V20 候选模型，验证集按 ±0.05 命中率优先选型，并输出逐炉预测、曲线、误差分布、特征重要性和实验报告；
- `tools/predict_next_heat_si_v19.py`：保持默认 V19；当 `--model` 指向 V20 bundle 时，额外构建 V20 特征并输出 V20 影子预测；
- `tests/test_v20_open_minus_features.py`：验证 cutoff、当前炉目标不可见、未发布前炉跳过、未化验间隔和喷煤不读未来。

Status: implemented_experimental_offline; not deployed, not production default, no 220.12 business writes.

2026-08-07 run note: VPN restored and `quick60_history_pci` completed on 220.12 with 2559 open-minus-60 samples. Best selectable formal candidate reached validation ±0.05 `65.33%`, confirm `51.85%`; allowing ablation selection picked `ablation_history`, validation `69.33%`, confirm `59.26%`, confirm MAE `0.0491`. Added `--sensor-name-scope core28` for lighter physical-window experiments and `--allow-ablation-selection` for explicit ablation model selection. Direct full 133-point sensor windows hit remote statement-timeout; core28 began returning rows but remained too slow for full replay, so sensor-window training still requires local cache or remote pre-aggregation.


## REQ-SI-V21-SENSOR-CACHE-20260808

V21 sensor-window cache experiment: pre-aggregate core28/process133 minute windows locally, then feed cached features into the V20 open-minus training protocol.

Implementation:

- `tools/build_v20_sensor_window_cache.py`：只读 220.12 分钟值，按 `[cutoff-window, cutoff)` 在本机生成宽表缓存；支持 `core28`、`process133` 和 `all` 三种点位口径；
- `tools/materialize_v21_dataset_from_sensor_cache.py`：从已有 V20 基础数据集删除旧传感器列，再按 `v20_sample_id` 合并缓存；可从 process133 audit 中切 core28；
- `tools/build_open_minus_si_dataset_v20.py`：新增 `--sensor-window-cache` 和 `--sensor-name-scope process133`；
- `tools/train_open_minus_si_v20.py`：新增候选进度日志和 `--candidate-names`，防止高维候选黑盒长跑；
- `tests/test_v21_sensor_window_cache.py`：验证缓存窗口右边界不读 cutoff、缓存按 `v20_sample_id` 合并。

Result: `2026-03-01~2026-08-07` 共 2268 个开口前 60 分钟样本。core28 finite 完整候选最佳验证 ±0.05 `73.33%`、确认 `54.84%`；process133 高维候选子集最佳验证 `72.00%`、确认 `51.61%`。同数据消融 `ablation_history` 确认 `58.06%`、MAE `0.04972` 最稳。预聚合技术路线有效，但直接加入核心28/133全集窗口未提升确认集，未晋升影子候选。2026-08-08 用户决策：不再使用全集上下文，默认回到 V19 August holdout；V20 构建器的传感器点位默认已改为 `core28`，`process133/all` 只允许显式离线研究。

Report: [V21 传感器窗口预聚合缓存实验](v21_sensor_cache_20260808.md).

Status: experimental_offline_paused_reverted_to_v19_default.


## REQ-SI-FUELRATIO-MES-REPORT-AUDIT-20260808

只读核验现场“下达燃料比”经验法：通过 220.12 访问 MES Web 原始作业日志报表 `mes/jn_ts_glbb_tb.sht`，不使用 pSpace，不写 220.12 业务表。

Implementation:

- `tools/remote_probe_imes_report_source.ps1`：探测 MES Web 作业日志报表源、表单参数和关键词；
- `tools/remote_fetch_imes_report_2d012_recent_days.ps1`：下载 2#高炉最近半个月日报 HTML；
- `tools/remote_fetch_imes_report_2d012_hourly_20260807.ps1`：验证同一日期不同 `time1` 返回相同日报内容；
- `tools/evaluate_imes_fuel_ratio_rule.py`：离线解析 Raqsoft 报表格子，复现煤比/燃料比公式，按 ±0.05/±0.02、MAE/RMSE 核验经验 Si 估计。

Result: 当前 MES 作业日志入口每个日报 HTML 仅直接暴露一个炉前出铁块，15 个可评估样本上燃料比经验法固定 0.30 基准的 ±0.05 命中率为 `13.33%`、MAE `0.4284`；恒定 0.30 基线反而达到 ±0.05 `60.00%`、MAE `0.0593`。燃料比差与实际 Si 的线性相关系数仅 `0.0318`。结论：燃料比可作为 V20/V21 解释特征或低置信度趋势参考，不宜单独作为无约束平均 Si 绝对预测器。

Report: [MES 作业日志燃料比经验法核验](fuel_ratio_report_rule_audit_20260808.md).

Status: completed_offline_report_source_audit; not promoted, no production writes.


## REQ-SI-FUELRATIO-MES-REPORT-PERSISTENCE-20260808

检查是否可将 MES Web 作业日志里的燃料比、料速/批数和 Si 保存到 220.12 数据库，并建设“工长燃料比经验法”分析页面。

Implementation/audit:

- `tools/audit_22012_fuelratio_report_surfaces.py`：通过既有 SSH 隧道和只读账号审计 220.12 PostgreSQL schema、现有表、候选表名冲突和作业日志视图字段；
- `tools/remote_audit_fuelratio_pg_surfaces.ps1`：远端只读探测草稿，因远端 PostgreSQL 需密码未作为主审计路径；
- `tools/remote_probe_bf2_operation_log_report_sync.ps1`：只读探测远端作业日志同步入口与计划任务；
- 远端留档下载：`PT/预测铁水Si含量/reports/experiments/EXP-SI-FUELRATIO-REPORT-20260808/db_surface_audit/remote_sync_bf2_operation_log_report.py`、`remote_imes_report_client.py`、`remote_imes_pg_store.py`。

Findings: 220.12 已有 `bf_imes.imes_bf2_operation_log_report` 和 `bf_imes.v_bf2_operation_log_report`，保存 180 天 × 24 小时作业日志小时行，共 4320 行；`report_fuel_ratio`、`report_coal_ratio`、`report_pulverized_coal` 已由报表公式复算保存。当前未保存炉前出铁块 Si；`material_rate` 为 `semantic_unconfirmed`，不能把 D 列“批数”静默当料速。

Plan/report: [工长燃料比经验法数据落库与页面方案检查](fuel_ratio_report_persistence_page_plan_20260808.md).

Status: checked_feasible_not_migrated; no DDL, no production page, no 220.12 business writes in this turn.


## REQ-SI-FUELRATIO-V20-SIDE-BY-SIDE-20260808

同炉次比较工长燃料比经验法与 V20 历史 Si 法，并附带当前一键 V19 的不可直接比较
背景指标。

- `tools/compare_foreman_fuel_vs_v20_history.py`：以炉号+开口时间双键对齐 MES 报表
  炉前块与 V20 预测，使用 220.12 逐炉平均 Si 为统一标签，按训练/验证/确认段分别
  输出 MAE、RMSE、bias、±0.02/±0.05 和相关系数；
- 主排名只使用 validation+confirm 共同炉次，训练段仅供描述；
- 输出逐炉 CSV、指标 JSON、实际/预测曲线和 Markdown 摘要。

Result: 7 个时间前向共同样本中，V20 历史 Si 为 ±0.05 `57.14%`、MAE `0.0580`；
工长固定 0.30 基准经验法为 `0.00%`、MAE `0.7358`。当前一键 V19 的 158 炉时间外
测试为 `67.72%`、MAE `0.04165`，但不是开口前 1 小时共同样本，不参与排名。

Report: [工长燃料比法与 V20 历史 Si 法同炉次并列评估](fuel_ratio_v20_side_by_side_20260808.md).

Status: completed_offline_small_common_sample_not_promoted.

## REQ-SI-V20-8093-8094-SHADOW-WORKBENCH-20260808

- `高炉前端数据/智能助手/backend/si_v20_shadow.py`：纯 Python V20 ExtraTrees 推理、历史特征、预测审计、随后实际 Si 动态回填。
- `高炉前端数据/智能助手/backend/models/si_v20_history_portable_v1.json.gz`：可部署模型；导出等价误差小于 `3e-16`。
- `高炉前端数据/assets/bf-si-v20-shadow-workbench.js`：8093/8094 当前预测、历史曲线、批量回放抽屉。
- `tools/export_si_v20_portable_model.py`：从实验 joblib 导出无 sklearn 运行依赖的模型。
- `tools/patch_si_v20_shadow_workbench_surfaces.py`：对远端当前后端和两张页面做幂等外科式补丁。
- `tools/remote_guarded_deploy_si_v20_shadow_workbench.ps1`：迁移、暂存校验、8093 守卫停启、8094 受管重启、回滚和 API 验收。
- `tools/verify_si_v20_shadow_ui.cjs` / `tools/verify_si_v20_shadow_remote_ui.cjs`：本地跨引擎矩阵与远端双端口冒烟。

Status: deployed_experimental_shadow.
