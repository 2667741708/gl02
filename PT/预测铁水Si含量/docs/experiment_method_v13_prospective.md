# V13 非重叠时延波动、严格历史与前瞻回放方法

## 1. 本轮目的

本轮同时处理两个问题：

1. 消除同一 `prediction_cutoff_ts` 炉次按排序先后进入历史特征的时间歧义；
2. 在五个非重叠时延带均值之外，增加波动、能量和标准化冲击神经元。

模型仍只使用预测截止时刻以前可见的数据。2026年7月历史段已被多轮读取，只作
历史比较；候选选择仍限定在4月、5月扩展折和固定6月验证折。

## 2. 严格历史合同

某前炉只有同时满足以下条件才能进入当前炉历史：

```text
prior.prediction_cutoff_ts < current.prediction_cutoff_ts
prior.label_available_ts <= current.prediction_cutoff_ts
```

注意第一项是严格小于，不允许同一预测时点的炉次因 `meltno` 排序先后互相可见。
从原2,291炉快照审计出6个受影响炉次。修复不改变炉次、传感器、标签或切分。

历史Si浮点特征在持久化和在线推理前统一保留12位小数。原因不是统计调参，而是
消除CSV解析造成的约 `1e-16` 差异跨越LightGBM分裂阈值的问题。

权威修复快照：

- [manifest.json](../data/processed/formal_v3_historyfix_r12_20260727/manifest.json)

## 3. 非重叠时延矩恢复

数据库已保存嵌套窗口的样本数 \(n\)、均值 \(\bar{x}\) 和样本标准差 \(s\)。
累计平方和可恢复为：

```text
sum(x²) = (n - 1) s² + n x̄²
```

用长窗口累计量减去短窗口累计量，可恢复30–60、60–120、120–240和
240–480分钟等非重叠带的计数、和与平方和。V13据此形成：

- 时延带标准差、均方根、绝对变异系数和有效点数；
- 近期带相对远期带的合并标准差Z分数；
- 近期/远期波动比；
- 波动剖面朝预测时点的斜率、范围和近期波动放大率。

共新增4,123个候选神经元。所有相关性和树重要性筛选均在每个训练折内重建。

## 4. 选择与评价

V13比较V10参考、时延矩相关性100/250、时延矩重要性250以及全部新特征重要性
350配方；每个配方比较三个Huber LightGBM规格。主排序为：

```text
mean(fold MAE) + 0.5 × std(fold MAE)
```

距最优稳健分数不超过0.00015的候选进入Pareto池，再按预测试
`±0.02% Si`命中率选择。7月历史结果不参与候选选择。

两个模型的历史比较必须按相同炉次做配对bootstrap；MAE差使用
`|e_B|-|e_A|`，负值有利于B；窄带命中差使用 `hit_B-hit_A`，正值有利于B。

## 5. 无目标前瞻回放

前瞻推理先删除当前炉所有 `target__*` 和持久化历史字段，再从截止时刻以前的
传感器、已发布前炉标签和已发布化验重建特征。回放必须满足：

- 当前炉目标字段使用数为0；
- V9、V10、V13逐炉预测与训练实验产物最大绝对差不超过 `1e-10`；
- 冻结模型文件SHA-256与协议一致；
- 预测账本只追加，预测写入时刻严格早于标签可见时刻；
- 至少300炉且覆盖30天后才能正式结算。

当前协议：

- [prospective_blind_protocol.v4.json](../configs/prospective_blind_protocol.v4.json)
- [回放结果](../reports/prospective_replay_v4_lagmoment_20260727.json)

## 6. 复现命令

```powershell
$env:PYTHONPATH='src'
python -m si_semantic_engine.train_v13 `
  --dataset data/processed/formal_v3_historyfix_r12_20260727/formal_heat_training_dataset.csv `
  --heat-targets data/processed/formal_v3_historyfix_r12_20260727/formal_heat_targets.csv `
  --samples data/processed/formal_v3_historyfix_r12_20260727/formal_samples.csv `
  --sensor-catalog ../高炉3D模型/docs/GL02传感器点位清单.v1.json `
  --temporal-dir data/processed/formal_v6_temporal_stats_8h_20260727 `
  --output-dir reports/experiments/EXP-SI-V13-LAG-MOMENT-HISTORYFIXR12-001_20260727
```

## 7. 发布边界

V13仍是离线候选。真实铁水温度标签为空，不能把出铁口温度代理当作铁水温度，
也不能用当前结果宣称已实现温度/热状态多任务模型或生产MCP能力。

