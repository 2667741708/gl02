# 可解释语义神经元铁水 Si 预测项目

需求编号：`REQ-SI-SEMANTIC-NEURON-ENGINE-20260726`

## 1. 项目目标

本目录用于长期保存 2# 高炉铁水 Si 预测相关的：

- 专家想法与假设；
- 可解释语义神经元模型代码；
- 配置、训练与回测方案；
- 项目报告和评审结论；
- 论文索引与合法取得的研究资料；
- 原始、过渡、训练和验证数据说明；
- 后续 MCP 工具及口语调用合同。

核心思想是把现有炉况规则引擎中的“有工艺意义的规则项”推广为有明确输入、
阈值、平滑尺度、方向约束和贡献值的**语义神经元**。模型不只输出一个 Si
点值，还要输出预测分布、目标区间概率、各神经元贡献和数据质量状态。

## 2. 当前状态

当前已完成第一轮 `experimental_v1_proxy_alignment` 实验：

- 已建立项目结构、第一版架构、需求追踪和论文索引；
- 已实现纯 Python 的语义神经元推理内核；
- 已实现未标定配置拒绝预测、分布概率和贡献追踪测试；
- 已将5,699份试样归并为1,669个临时炉次组；
- 已固定1,168/250/251炉次的训练/验证/测试时间切分；
- 已完成6种模型的首轮训练和残差区间校准；
- 首轮按验证MAE选择 `full_extra_trees`，测试MAE为 `0.0498% Si`；
- 语义神经元测试MAE为 `0.0551% Si`；
- 低Si和高Si召回仍接近0，当前模型不得进入生产预警、MCP正式回答或操作建议。

已完成第二轮 `experimental_v2_expanded_neurons` 代理实验：

- 主验收容差从`±0.10`收紧为`±0.05个Si百分点`；
- 148个规则特征从6个宽神经元拆分为21个工艺语义神经元；
- 21神经元模型测试MAE为`0.0500% Si`，`±0.05`命中率为`60.2%`；
- 当前最佳260特征模型测试MAE为`0.0498% Si`，`±0.05`命中率为`62.2%`；
- 已实现130点长表的30/60/120/240分钟时序微神经元派生器；
- V2的本机代理数据仍不是正式炉次标签，不能接生产。

已完成第三轮 `experimental_v3_formal_meltno` 正式标签实验：

- 已改用 MES 正式 `t_qpes_inner_batch.heatno -> t_ipes_cond.meltno`，不再从
  试样号推断炉次；
- 已将“整炉代表Si”“下一次试样Si”“整炉Si分布”拆成三个独立目标合同；
- 已确认当前 `takesampletime` 为0条、可信铁口编号为0条，因此下一试样任务
  被合同阻止，结果时间不再冒充取样时间；
- PostgreSQL历史相交范围取得5,936条正式试样、2,366个正式炉次；
- 剔除66炉“完整标签在截止前已可见”的非前瞻样本后，2,291炉通过标签与
  至少100个开铁前有效物理点门禁，固定切分为1,603/344/344；
- 133个物理点生成当前值、60/120分钟变化量与斜率共665个候选时序特征，
  训练段门禁后使用579个；
- 正式代表值 ExtraTrees 测试MAE为`0.0489% Si`，`±0.05`命中率为
  `64.5%`；
- 分布P50测试MAE为`0.0483% Si`，但预测分布带完整覆盖实际P10-P90仅
  `23.5%`，当前仍不能接生产。

已完成 V4/V5 `experimental_offline_v5` 持续迭代：

- 从220.12 PostgreSQL以只读事务提取2,291炉×133点、30/60/120/240分钟
  多窗口统计，共304,703行；
- 新增44个无泄漏前炉历史神经元、490个物理/空间动态神经元、18个耦合神经元、
  4,788个点位窗口候选和1,472个空间汇总候选；
- 固定验证选择后的V5测试MAE为`0.047882% Si`，`±0.02`命中率为`31.10%`；
- 2026-04至07滚动月MAE为`0.075529/0.043577/0.060526/0.049776`，
  跨月稳定性未通过；
- 留一试样后整炉中位数平均变化`0.035541% Si`，当前`0.02`目标仍未达到；
- 所有新模型保持离线实验状态，未修改8093、MCP或生产数据库。

设计配置仍保持 `design_only_unfitted`；首轮训练产生的实验配置为
`calibrated_experimental`，只能离线研究。

## 3. 目录

| 目录 | 用途 |
|---|---|
| [ideas](ideas/) | 用户想法、专家假设、待验证问题 |
| [docs](docs/) | 架构、需求、数据与评估合同 |
| [src](src/) | 可运行代码 |
| [configs](configs/) | 神经元拓扑与标定参数 |
| [tests](tests/) | 单元测试和后续回归测试 |
| [data](data/) | 数据分层说明；实际敏感数据默认不入库 |
| [models](models/) | 模型清单、参数版本和校准产物说明 |
| [reports](reports/) | 回测、评审、阶段报告 |
| [papers](papers/) | 论文书目、笔记和授权资料 |
| [notebooks](notebooks/) | 探索分析说明和后续笔记本 |

## 4. 与现有工程的连接点

- 历史标签和无未来泄漏基线：
  [build_hot_metal_si_dataset.py](../../tools/build_hot_metal_si_dataset.py)
- 炉次级宽表：
  [build_model_feature_row](../../db_dashboard/heat_service.py#L980)
- 现有炉况诊断：
  [AutoDiagnosisScheduler](../../自动诊断服务/diagnosis_scheduler.py#L102)
- 铁水、炉渣、烧结矿和炉次数据边界：
  [mes数据集](../../docs/mes数据集.md)

## 5. 本地验证

在本目录执行：

```powershell
python -m unittest discover -s tests -v
python -m src.si_semantic_engine.cli --help
```

设计配置会拒绝预测，这是预期行为：

```powershell
python -m src.si_semantic_engine.cli `
  --config configs/semantic_neurons.design.json `
  --features tests/fixtures/example_features.json
```

只有经过时间切分回测、分布校准、专家复核并把
`model_status` 更新为允许推理的状态后，才可进入影子运行。

首轮固定方法与结果：

- [实验方法](docs/experiment_method_v1.md)
- [首轮结论](reports/2026-07-26_首轮V1训练结论.md)
- [可复现实验产物](reports/experiments/EXP-SI-V1-SEMANTIC-001_20260726_REPRO_A/)

扩展神经元方法与结果：

- [V2实验方法](docs/experiment_method_v2.md)
- [高延迟时序想法](ideas/002_高延迟时序微神经元扩展.md)
- [V2训练结论](reports/2026-07-26_V2扩展神经元训练结论.md)
- [V2可复现实验产物](reports/experiments/EXP-SI-V2-EXPANDED-001_20260726_REPRO_A/)

正式炉次 V3 方法与结果：

- [正式标签合同](docs/data_contract.md)
- [V3实验方法](docs/experiment_method_v3.md)
- [机器可读标签合同](configs/si_label_contract.v3.json)
- [V3数据清单](data/processed/formal_v3_20260726/manifest.json)
- [V3阶段结论](reports/2026-07-26_V3正式标签合同与训练结论.md)
- [V3实验产物](reports/experiments/EXP-SI-V3-FORMAL-001_20260726_222525/)
- [三轮实验总结与混合网络路线](docs/experiment_summary_and_hybrid_roadmap.md)
- [V4/V5实验方法](docs/experiment_method_v5.md)
- [V4/V5阶段报告](reports/2026-07-27_V4_V5持续迭代与0.02目标评估.md)
- [V5可复现实验](reports/experiments/EXP-SI-V5-TEMPORAL-SEMANTIC-001_20260727/)
- [问题追踪](docs/question_traceability.md)

V6～V9 热状态软测量与稳健模型：

- [V6～V9实验方法](docs/experiment_method_v6_v9.md)
- [V6～V9阶段报告](reports/2026-07-27_V6_V9热状态软测量持续实验.md)
- [8小时多窗口数据清单](data/processed/formal_v6_temporal_stats_8h_20260727/manifest.json)
- [V9当前最低点MAE实验](reports/experiments/EXP-SI-V9-MULTIMODEL-PARETO-8H-002_20260727/report.md)

当前历史测试最低点MAE为`0.047098%`，相对V5改善约`1.64%`；`±0.02%`
最高命中仍为`31.10%`，目标尚未达到。真实铁水温度标签非空数为0，温度回归和
热状态概率头均被合同阻止；全部模型继续保持离线实验状态。

V10～V12继续迭代：

- [V10～V12实验方法](docs/experiment_method_v10_v12.md)
- [V10～V12阶段报告](reports/2026-07-27_V10_V12时延场与标签可靠性实验.md)
- [V10时延/空间场实验](reports/experiments/EXP-SI-V10-LAG-FIELD-8H-001_20260727/report.md)
- [V11标签可靠性实验](reports/experiments/EXP-SI-V11-LABEL-RELIABILITY-8H-001_20260727/report.md)
- [V12专家集成实验](reports/experiments/EXP-SI-V12-LAG-FIELD-ENSEMBLE-8H-001_20260727/report.md)

V10新增2,660个非重叠时延带特征和1,390个空间场模态，预测试稳健分数小幅
改善；但历史7月MAE为`0.048049%`，与V9差异的配对bootstrap区间跨0。V11
选择回原始中位Si与均匀权重，V12退化为100% V10专家，均未刷新权威最低MAE。

V1冻结协议保留为历史记录；严格历史和浮点回放审计后，当前有效协议已升级为
[V4前瞻盲测协议](configs/prospective_blind_protocol.v4.json)，冻结
V9/V10/V13。只有2026-07-27之后、预测先于标签写入、累计不少于300炉且覆盖
至少30天的新数据，才能进行下一次正式模型比较。

严格历史修复与V13新增进展：

- [V13与前瞻方法](docs/experiment_method_v13_prospective.md)
- [严格历史/V13阶段报告](reports/2026-07-27_严格历史回放与V13时延波动实验.md)
- [严格历史12位量化快照](data/processed/formal_v3_historyfix_r12_20260727/manifest.json)
- [V13实验](reports/experiments/EXP-SI-V13-LAG-MOMENT-HISTORYFIXR12-001_20260727/report.md)
- [当前V4前瞻协议](configs/prospective_blind_protocol.v4.json)
- [无目标回放证据](reports/prospective_replay_v4_lagmoment_20260727.json)

旧历史合同中有6炉存在同一预测时点排序可见歧义，现已修正；历史Si浮点神经元
统一保留12位小数。V13新增4,123个非重叠时延波动/冲击特征，预测试稳健分数
为`0.057979`，历史MAE`0.047108`、`±0.02=29.36%`。其MAE相对V9没有
统计显著改善，因此当前最低历史点MAE仍以V9修复版`0.047081`记录。

V9/V10/V13均已在删除当前炉全部目标字段后完成344炉逐点回放，最大差异不超过
`1.67e-16`。模型仍为离线候选；真实铁水温度标签为0行，不能宣称已训练铁水
温度或热状态联合头。

V14～V15新增进展：

- [V14～V15实验方法](docs/experiment_method_v14_v15.md)
- [V14～V15阶段报告](reports/2026-07-27_V14_V15语义压缩与响应时延实验.md)
- [V15实验](reports/experiments/EXP-SI-V15-BEST-RESPONSE-LAG-HISTORYFIXR12-001_20260727/report.md)

V14七业务组潜因子和V15单一最佳响应时延均未超过V13。V15最终退回V13参考，
344炉逐炉预测完全一致；802项变量×响应族最佳时延中仅335项跨三折完全稳定。
因此V4前瞻协议保持不变，不新增V14/V15冻结模型。当前62项单元测试及源码编译
通过。

V16～V18继续验证了残差对齐选择和CatBoost：

- V16专属最佳稳健分数`0.058597`，最终退回V13；
- V17 Ordered CatBoost两次在1004秒超时；
- V18 Plain CatBoost稳健分数`0.060185`、历史MAE`0.049539`，弱于V13；
- [当前最优正式Word报告](reports/当前最优铁水Si预测实验报告_20260727.docx)。

当前推荐主方法仍为V13；V9只保留“单一历史段点MAE最低”的对照身份。
当前全量回归为68项通过，源码、测试和正式报告生成脚本编译通过。

## 6. 安全边界

- 模型只做只读预测与决策辅助，不写生产设定值。
- 大模型只负责意图解析和结果表达，不负责计算预测数值。
- 每条建议必须包含预测时域、置信度、证据、风险和复核项。
- 未取得精确“原料检验批次 → 料仓 → 投料批次 → 炉次”谱系前，烧结矿化验
  只能作为低置信度时间背景。
- 正式页面使用“热制度上行/热制度下行”，内部数据库键可继续保留
  `hot/cold`。
