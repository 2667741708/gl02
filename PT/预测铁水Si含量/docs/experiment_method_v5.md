# V4/V5 语义神经元持续迭代方法

需求编号：`REQ-SI-TEMPORAL-SEMANTIC-V5-20260727`

## 目标

在不修改 V3 正式炉次数据、不使用预测截止之后信息的前提下，尝试将代表 Si
误差从约 `0.05% Si` 向 `0.02% Si` 收缩，并明确区分：

- `MAE <= 0.02`；
- 单炉绝对误差 `<= 0.02` 的命中率；
- 固定时间外测试与滚动月份稳定性。

只有三者都稳定改善才可称为真正收缩；不能用单次命中率代替 MAE。

## 特征层

1. V3 的 133 点当前值、60/120 分钟变化量与斜率；
2. 仅使用当前开铁截止前已发布更早炉次的 1/3/6/12/24 炉 Si 历史；
3. 风压—顶压、压差分配、A～F 三高度静压力、L7～L16 炉身温度等
   确定性物理组合；
4. 从 220.12 PostgreSQL 只读提取 133 点开铁前 30/60/120/240 分钟
   count/mean/std/min/max/slope，并在本地派生 coverage/range/cv；
5. 仅在训练段进行覆盖率、方差、Spearman 或 ExtraTrees 重要性筛选。

## 选择与评估

- 固定切分仍为 1,603/344/344 炉；
- 特征集、树深和筛选数只看 validation；
- 锁定 test 在选择完成后读取；
- 滚动月回测在每一折内重新建立训练段神经元排序；
- 所有产物保持 `experimental_offline`，不接 MCP。

## 标签稳定性诊断

对同炉多试样执行：

- 任意两次试样绝对差；
- 留一试样后整炉中位数变化；
- 每炉试样 bootstrap 中位数标准差。

这些指标用于判断标签稳定尺度，不等同于严格不可约误差下界。

## 固定命令

```powershell
$env:PYTHONPATH = 'src'
python -m si_semantic_engine.extract_v4_temporal_stats `
  --dataset data/processed/formal_v3_20260726/formal_heat_training_dataset.csv `
  --output-dir data/processed/formal_v4_temporal_stats_20260726 `
  --chunk-size 20

python -m si_semantic_engine.train_v5 `
  --dataset data/processed/formal_v3_20260726/formal_heat_training_dataset.csv `
  --heat-targets data/processed/formal_v3_20260726/formal_heat_targets.csv `
  --samples data/processed/formal_v3_20260726/formal_samples.csv `
  --sensor-catalog ../高炉3D模型/docs/GL02传感器点位清单.v1.json `
  --temporal-dir data/processed/formal_v4_temporal_stats_20260726 `
  --output-dir reports/experiments/EXP-SI-V5-TEMPORAL-SEMANTIC-001_20260727
```

