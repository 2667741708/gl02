# V14～V15 语义压缩与最佳响应时延实验方法

需求：

- `REQ-SI-SEMANTIC-LATENT-STATE-V14-20260727`
- `REQ-SI-BEST-RESPONSE-LAG-V15-20260727`

## 1. 共同数据合同

- 固定数据快照：
  `data/processed/formal_v3_historyfix_r12_20260727/`；
- 传感器统计严格早于 MES `prediction_cutoff_ts`；
- 同一预测截止时刻的其他炉次不得作为历史；
- 4月、5月采用扩展训练折，6月使用固定验证折；
- 7月只报告历史比较，不参与特征、模型或阈值选择；
- 出铁口温度只能称为代理变量；真实铁水温度标签仍为0行。

## 2. V14：业务组潜在热状态

V14把传感器及其时序派生量划分为热量输入、煤气利用、透气性、料面运动、
出铁口温度代理、三高度静压力场和7～16层炉体热场。

每个训练折内先按相关性保留每组最多80项，再用历史Si基线残差监督PLS潜因子。
每组测试1～3个分量，后端比较Ridge、ExtraTrees、XGBoost和LightGBM。

结果选择`latent_c3__extra_leaf10`，预测试稳健分数`0.059846`，历史7月
MAE `0.049303`，`±0.02=26.16%`。它弱于V13，说明把大量空间点和响应时延
压缩成少数组级分量会丢失局部状态信息。

## 3. V15：训练折内最佳响应时延

V15不直接对完整Si标签选择窗口。每一折先计算：

```text
Si残差 = 本炉代表Si - 预测时刻已经发布的历史Si基线
```

再按“物理变量×响应族”从五个非重叠时段中保留绝对Spearman相关最高的一项。
响应族包括时段均值、标准差、均方根、绝对变异系数、标准化均值冲击、波动比和
近期与较早时段的均值差。

时段中心为15、45、90、180和360分钟。最终训练折对115个具备完整时序统计的
变量选出802个“变量×响应族”神经元。三个折完全选择相同特征的项目为335项，
稳定率`41.77%`，说明最佳滞后随月份漂移明显。

V15紧凑模型最佳预测试稳健分数为`0.059067`；把前200个最佳时延加入V13也没有
改善。全体候选最终仍选择V13参考模型，历史7月预测与V13逐炉完全一致：

- MAE `0.047108`；
- `±0.02=29.36%`；
- 配对MAE差`0`，95%区间`[0, 0]`。

## 4. 解释边界

V14、V15都是有价值的负结果：

- 热状态不是少数静态组分量可以完整表达；
- 同一传感器的多个时标可能同时携带互补信息；
- 单个“最佳滞后”只有约42%跨折完全稳定，不能固化成生产阈值；
- PI、压差、喷煤、风压和风量的冲击/均值差在最终训练段排名靠前，但相关性不等于
  因果性，也不能替代真实铁水温度标签。

两版均不进入V4前瞻协议，不修改MCP或生产数据库。

## 5. 复现命令

```powershell
$env:PYTHONPATH='src'
python -m si_semantic_engine.train_v15 `
  --dataset data/processed/formal_v3_historyfix_r12_20260727/formal_heat_training_dataset.csv `
  --heat-targets data/processed/formal_v3_historyfix_r12_20260727/formal_heat_targets.csv `
  --samples data/processed/formal_v3_historyfix_r12_20260727/formal_samples.csv `
  --sensor-catalog ../高炉3D模型/docs/GL02传感器点位清单.v1.json `
  --temporal-dir data/processed/formal_v6_temporal_stats_8h_20260727 `
  --output-dir reports/experiments/EXP-SI-V15-BEST-RESPONSE-LAG-HISTORYFIXR12-001_20260727
```
