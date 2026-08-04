# EXP-SI-V2-EXPANDED-001 实验方法

需求编号：`REQ-SI-TEMPORAL-NEURONS-V2-20260726`  
状态：代理快照实验已执行；真实130点多窗口物化待执行

## 1. 变化

- 主验收从`±0.10`收紧为`±0.05个Si百分点`；
- `±0.10`只保留为历史诊断，不参与主验收；
- 模型选择先最大化验证集`hit_rate_abs_le_005`，再最小化验证MAE；
- 原6个宽神经元拆分为21个工艺神经元；
- 新增130点长表时序派生器和30/60/120/240分钟合同。

## 2. 时序派生合同

输入长表字段：

```text
ts, sensor_id, value, quality(optional)
```

窗口固定为`(cutoff-window, cutoff]`，任何晚于`cutoff`的数据必须在派生前剔除。
同一点同一分钟多值取中位数；质量为`Good/0/192`的值参与数值统计。

每点每窗口生成：

- 水平与分位：latest、mean、median、min、max、range；
- 稳定性：std、IQR、MAD；
- 趋势：slope、delta、early_late_delta；
- 动态：diff_mean、diff_std、total_variation、sign_change_rate；
- 记忆/异常：acf1、spike_rate、上下偏离比例；
- 数据质量：count、coverage、最长缺测段、末值年龄。

完整合同见
[temporal_neuron_catalog.v2.json](../configs/temporal_neuron_catalog.v2.json)。

## 3. 扩展语义神经元

当前148个规则特征唯一归入21组：

1. 燃料与富氧输入；
2. 鼓风与出铁热状态；
3. 透气性与压差水平；
4. 透气性与压差稳定性；
5. 炉顶压力控制；
6. 煤气利用状态；
7. 炉顶温度状态；
8. 炉体分层热状态；
9. 炉体分层热稳定性；
10. 炉体纵向温度梯度；
11. 炉体圆周均匀性；
12. 炉体方位煤气流分布；
13. 料线空间状态；
14. 装料与料线动态；
15. 热制度诊断；
16. 煤气流诊断；
17. 顺行状态诊断；
18. 诊断置信度；
19. 输入数据可信度；
20. 前序炉Si水平惯性；
21. 前序炉Si变化趋势。

## 4. 当前代理实验结果

固定切分仍为训练/验证/测试`1168/250/251`炉：

| 模型 | 验证±0.05 | 测试±0.05 | 测试MAE | 测试R² |
|---|---:|---:|---:|---:|
| 6神经元 | 51.6% | 60.2% | 0.0551 | -0.1166 |
| 21神经元 | 52.8% | 60.2% | 0.0500 | 0.1202 |
| 260特征ExtraTrees | 53.6% | 62.2% | 0.0498 | 0.1266 |

21神经元显著缩小了与260特征模型的MAE差距，但没有提高测试`±0.05`命中率，
因此当前最佳模型仍是`full_extra_trees`。

验证和测试消融方向同时为正的候选神经元包括：

- 透气性与压差水平；
- 炉顶压力控制；
- 炉顶温度状态；
- 前序炉Si水平与趋势；
- 燃料与富氧输入；
- 装料与料线动态；
- 输入数据可信度；
- 炉体圆周均匀性。

这些只表示两个时间段上的稳定关联，不表示生产调节因果关系。

## 5. 未完成边界

2026-07-26核查本机PostgreSQL 16监听`127.0.0.1:18000`，但仍无
`bf_sensor` schema。因此本轮不能物化130点的完整多窗口数据，只完成：

- 长表时序派生代码；
- 合成数据无未来泄漏测试；
- 当前代理特征的21组训练和消融；
- 两次确定性复现。

完成`bf_sensor.one_minute_values`受控同步后，必须重新生成炉次×窗口特征并做
滚动月份回测，不能把本报告视作真实130点模型结果。

## 6. 复现

```powershell
python -m PT.预测铁水Si含量.src.si_semantic_engine.train_v2 `
  --dataset PT/预测铁水Si含量/data/processed/v1_proxy_20260726/heat_level_dataset.csv `
  --prepared-manifest PT/预测铁水Si含量/data/processed/v1_proxy_20260726/manifest.json `
  --output-dir PT/预测铁水Si含量/reports/experiments/EXP-SI-V2-EXPANDED-001_20260726_REPRO_A
```

两次复现的`metrics.json` SHA-256均为：

```text
4735783056A399B76A24B217A4ED5D2346121F557131ACCA565B7961E95276CC
```
