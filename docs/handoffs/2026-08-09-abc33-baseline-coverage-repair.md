# ABC33 全量 30 天基线覆盖修复与生产核验

追踪编号：`OPS-ABC33-BASELINE-COVERAGE-20260809`

## 结论

- 修复前并非缺少基线行，而是 `83` 项已有基线低于 `75%` 有效覆盖门禁。
- 完成 pSpace 逐日原始数据回填、采样语义修订和 30 天基线重建后，生产严格校验为：`required=137`、`available=137`、`missing=0`、`below_coverage=0`、`invalid_statistics=0`。
- 本次不重启 8093、8094、8768、8770 或数据库服务；只部署基线程序并执行一次性重建。
- 基线全部合格后，本机实数回放仍只有 `8/33` 条规则完整可算。剩余缺口属于实时派生因子、现场批准阈值和复合规则接线，不再属于 30 天基线覆盖不足。

## 修复前 83 项低覆盖基线

### 冷却系统（1）

- `P_soft_water`

### 料线（2）

- `L_north`
- `L_south`

### 四点顶温（1）

- `T_top_B`

### 派生特征（1）

- `T_top`

### 新增工长点位（4）

- `BlastEnergy`
- `Hopper_weight`
- `P_N2`
- `Q_N2`

### 炉体温度（74）

- `T_body_L7_A`、`T_body_L7_B`、`T_body_L7_C`、`T_body_L7_D`、`T_body_L7_E`、`T_body_L7_F`、`T_body_L7_G`、`T_body_L7_H`
- `T_body_L8_A`、`T_body_L8_B`、`T_body_L8_C`、`T_body_L8_D`、`T_body_L8_E`、`T_body_L8_F`、`T_body_L8_G`、`T_body_L8_H`
- `T_body_L9_A`、`T_body_L9_B`、`T_body_L9_C`、`T_body_L9_D`、`T_body_L9_E`、`T_body_L9_F`、`T_body_L9_G`、`T_body_L9_H`
- `T_body_L10_A`、`T_body_L10_B`、`T_body_L10_C`、`T_body_L10_D`、`T_body_L10_E`、`T_body_L10_F`、`T_body_L10_G`、`T_body_L10_H`
- `T_body_L11_A`、`T_body_L11_C`、`T_body_L11_D`、`T_body_L11_E`、`T_body_L11_G`、`T_body_L11_H`
- `T_body_L12_A`、`T_body_L12_C`、`T_body_L12_D`、`T_body_L12_G`、`T_body_L12_H`
- `T_body_L13_A`、`T_body_L13_B`、`T_body_L13_C`、`T_body_L13_D`、`T_body_L13_F`、`T_body_L13_G`、`T_body_L13_H`
- `T_body_L14_A`、`T_body_L14_B`、`T_body_L14_C`、`T_body_L14_D`、`T_body_L14_E`、`T_body_L14_F`、`T_body_L14_G`、`T_body_L14_H`
- `T_body_L15_A`、`T_body_L15_B`、`T_body_L15_C`、`T_body_L15_D`、`T_body_L15_E`、`T_body_L15_F`、`T_body_L15_G`、`T_body_L15_H`
- `T_body_L16_A`、`T_body_L16_B`、`T_body_L16_C`、`T_body_L16_D`、`T_body_L16_E`、`T_body_L16_F`、`T_body_L16_G`、`T_body_L16_H`

说明：80 个炉体温度点中有 74 个低于旧门禁。它们属于变化触发或非逐分钟满报的状态量，不能把“没有新报文”直接解释为“没有状态”。

## 处理策略

1. 对 11 个短历史或接近门禁的原始变量按自然日从 pSpace 读取，并按日立即 upsert 到 `bf_sensor.one_minute_values`，不是全部读取完再统一入库。
2. 普通状态量的基线覆盖采用最多 5 分钟的有界前向保持；炉体温度最多 15 分钟。
3. 有界保持只用于表达状态型传感器的有效持续时间，不跨越长时间断档，不补零。
4. `T_top` 先对 A/B/C/D 四点分别做最多 5 分钟有界保持，再要求四点齐全后求同分钟均值。
5. `T_taphole_mean` 保持两个铁口同分钟严格对齐，不做保持。
6. `ExpansionTankLevel` 保持“观测分钟均值 → 小时均值 → 日均值 → 30 个日均值的分位数”独立口径。
7. `P_static_*` 个别点位允许真实 `IQR=0`；规则使用同一时刻截面极差，不用单点 z 标准化，因而不把真实常量点误判为统计无效。

## 生产程序

- 历史重建：[run_abc33_baseline_rebuild.ps1](../../tools/run_abc33_baseline_rebuild.ps1)
- 每日维护：[run_v4_daily_baseline.ps1](../../tools/run_v4_daily_baseline.ps1)
- 基线计算：[baseline_maintainer.py](../../自动诊断服务/baseline_maintainer.py)
- 严格门禁：[verify_abc33_baseline_coverage.py](../../tools/verify_abc33_baseline_coverage.py)
- 低覆盖审计：[report_abc33_baseline_coverage.py](../../tools/report_abc33_baseline_coverage.py)

计划任务 `\BlastFurnace8093DailyBaseline20d` 的名称保留历史兼容，但动作已指向 V4 的全量 30 天入口。每日任务一次计算全部原始、派生、冷却和炉体基线，随后执行严格门禁；任何必需基线缺失、有效覆盖低于 75% 或统计无效都会使任务失败关闭，禁止静默通过。

## 验证证据

- 生产重建日志：`F:\高炉炼铁项目-real-sensor-v2_V4_8093_PREVIEW\logs\abc33_baseline_rebuild_20260809_234917.json`
- 生产备份：`F:\高炉炼铁项目-real-sensor-v2_V4_8093_PREVIEW\backups\abc33_baseline_repair\20260809_234916`
- 修复前逐项清单：[abc33_baselines_below_75.md](../../data/abc33_22012_snapshot_20260809/audit/abc33_baselines_below_75.md)
- 修复后逐项清单：[abc33_baselines_below_75.md](../../data/abc33_22012_snapshot_20260809_after_baseline_repair/audit/abc33_baselines_below_75.md)，结果为 `0` 项。
- 修复后 33 项规则实数审计：[abc33_rule_audit.md](../../data/abc33_22012_snapshot_20260809_after_baseline_repair/audit/abc33_rule_audit.md)
- 本机回归：`95 passed`，覆盖日基线四分位、通用因子与规则引擎。

## 当前仍未完整计算的规则因子

基线已不是阻断项。剩余主要为：`TopTempRange`、`high/low/absSlope_Ttop`、`CoolingRisk`、`BodyHotRisk`、`BodyColdRisk`、`BodyTempRange`、`slopeBodyMax`、`StaticPressRange`、`LineLoss`、`LineLossDuration`、`EconomicIntensityEdge` 和 `C2CompositeGate`。这些应在下一阶段分别完成实时窗口有界对齐、现场批准阈值配置和复合规则接线，再重新开放真实分数及 B/C 告警。
