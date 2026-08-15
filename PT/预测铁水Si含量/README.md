# 可解释铁水 Si 预测项目

> - 需求：`REQ-SI-SEMANTIC-NEURON-ENGINE-20260726`
> - 状态：离线研究 / 只读候选；不得自动写生产设定值
> - 当前默认研究基线：V19 August holdout
> - 最后核对：2026-08-11

## 当前结论

本目录研究 2# 高炉铁水 Si 的点预测、概率分布、原因解释和只读决策辅助。模型把有工艺
意义的规则与时间窗口组织为可解释“语义神经元”，但预测数值、置信区间和贡献解释仍必须
经过数据合同、无泄漏检查、时间外回测、概率校准和专家复核。

- V19 的 7 月训练 / 8 月时间外测试仍是当前默认研究基线；它没有晋级为自动生产模型。
- V21 证明传感器窗口预聚合缓存可降低查询压力，但核心 28 点和工艺 133 点的高维上下文
  没有改善确认集；V21 已暂停并回退到 V19 默认。
- 当前所有版本保持离线研究或只读边界，不修改 8093、MCP、生产数据库或生产设定值。
- 历史最低点 MAE、单一窗口冠军和测试集后验表现不能单独用作上线依据。

权威状态：

- [V19 7 月训练 / 8 月时间外测试](docs/v19_august_holdout_20260807.md)
- [V21 传感器缓存与回退结论](docs/v21_sensor_cache_20260808.md)
- [数据合同](docs/data_contract.md)
- [需求追踪](docs/requirements_traceability.md)
- [测试索引](docs/test_reference.md)

## 阅读顺序

1. [本目录协作规则](AGENTS.md)
2. [项目上手](docs/project_onboarding.md)
3. [系统架构](docs/architecture.md)
4. [数据合同](docs/data_contract.md)
5. [当前状态：V19](docs/v19_august_holdout_20260807.md) 与
   [V21 回退](docs/v21_sensor_cache_20260808.md)
6. [程序索引](docs/program_index.md)、[测试索引](docs/test_reference.md)、
   [排障](docs/troubleshooting.md)

## 目录

| 路径 | 职责 |
|---|---|
| [ideas](ideas/) | 专家假设、反例和验证方案；不是已确认知识 |
| [docs](docs/) | 架构、需求、数据合同、方法与当前状态 |
| [src](src/) | 数据集、训练、推理和 CLI 代码 |
| [configs](configs/) | 标签合同、协议、神经元拓扑与状态门 |
| [tests](tests/) | 单元、合同和无泄漏回归 |
| [data](data/) | 数据分层与可复现清单；敏感原始数据默认不入库 |
| [models](models/) | 模型清单、参数版本和校准产物 |
| [reports](reports/) | 阶段报告、实验快照和正式输出 |
| [papers](papers/) | 论文索引、笔记和合法取得的资料 |

## 当前状态门

| 状态 | 是否允许预测 | 用途 |
|---|---|---|
| `design_only_unfitted` | 否 | 仅设计与结构验证 |
| `retired` | 否 | 历史复现，不再作为候选 |
| `experimental_offline*` | 仅离线 | 研究、回测、消融 |
| `shadow_validated` | 只读影子 | 通过约定验证后的旁路观察 |
| `approved_readonly` | 只读 | 经明确批准的正式只读回答 |

配置中的实际状态优先于文件名或报告标题。不得把 `calibrated_experimental`、单次测试表现
或旧“最佳模型”描述自动解释为 `shadow_validated`。

## 历史实验索引

README 不再逐轮复述全部指标，避免 V1～V21 的阶段结论互相覆盖。历史方法与结论从下表进入：

| 阶段 | 重点 | 方法 / 状态文档 |
|---|---|---|
| V1 | 首轮代理标签与语义神经元 | [V1 方法](docs/experiment_method_v1.md) |
| V2 | 21 个扩展神经元与高延迟时序想法 | [V2 方法](docs/experiment_method_v2.md) |
| V3 | 正式 `meltno` 标签与独立目标合同 | [V3 方法](docs/experiment_method_v3.md) |
| V4～V5 | 多窗口与持续迭代 | [V5 方法](docs/experiment_method_v5.md) |
| V6～V9 | 热状态软测量与稳健模型 | [V6～V9 方法](docs/experiment_method_v6_v9.md) |
| V10～V12 | 时延场、标签可靠性与专家集成 | [V10～V12 方法](docs/experiment_method_v10_v12.md) |
| V13 | 严格历史修复与前瞻协议 | [V13 方法](docs/experiment_method_v13_prospective.md) |
| V14～V15 | 语义压缩与响应时延 | [V14～V15 方法](docs/experiment_method_v14_v15.md) |
| V16～V18 | 残差对齐与 CatBoost | [V16～V18 方法](docs/experiment_method_v16_v18.md) |
| V19 | 上下文消融与 8 月时间外测试 | [V19 状态](docs/v19_august_holdout_20260807.md) |
| V20 | 开口前多提前量与命中率实验 | [V20 状态](docs/v20_open_minus_hitrate_20260807.md) |
| V21 | 传感器窗口缓存、高维上下文与回退 | [V21 状态](docs/v21_sensor_cache_20260808.md) |

冻结报告和 `reports/experiments/` 目录为可复现证据，不因 README 收敛而删除。

## 本地验证

在本目录执行：

```powershell
python -m unittest discover -s tests -v
python -m src.si_semantic_engine.cli --help
```

设计配置拒绝预测是预期行为：

```powershell
python -m src.si_semantic_engine.cli `
  --config configs/semantic_neurons.design.json `
  --features tests/fixtures/example_features.json
```

数据、模型或配置变更还必须运行对应需求与测试索引列出的专项命令；不能用 README 中的冒烟
代替时间外回测、泄漏检查、概率校准或前瞻协议验收。

## 与主工程的连接

- 历史标签和无未来泄漏基线：
  [build_hot_metal_si_dataset.py](../../tools/build_hot_metal_si_dataset.py)
- 炉次级宽表：
  [build_model_feature_row](../../db_dashboard/heat_service.py#L980)
- 自动诊断：
  [AutoDiagnosisScheduler](../../自动诊断服务/diagnosis_scheduler.py#L102)
- MES 数据边界：
  [MES 数据集](../../docs/mes数据集.md)

## 安全边界

- 模型只做只读预测和决策辅助，不写生产设定值。
- 大模型只负责意图解析和结果表达，不负责临时训练或随意生成预测数值。
- 每条建议必须说明预测时域、置信度、证据、风险和复核项。
- 未取得“原料检验批次 → 料仓 → 投料批次 → 炉次”可信谱系前，原料化验只能作为低置信度背景。
- 铁口测温不得冒充铁水温度；相关性贡献不得直接翻译成生产调节量。
- 正式页面使用“热制度上行/热制度下行”；内部兼容键可保留 `hot/cold`。
