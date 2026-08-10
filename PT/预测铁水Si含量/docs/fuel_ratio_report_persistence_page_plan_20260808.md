# 工长燃料比经验法数据落库与页面方案检查（2026-08-08）

## 结论

可以把 MES Web 作业日志里的燃料比、煤比、喷煤、矿批/焦批等小时指标保存到 220.12 PostgreSQL，并基于这些数据单独建设“工长燃料比经验法”分析页面。

更准确地说：220.12 目前已经存在一条基础链路，正在把 2#高炉“冀南新区高炉作业日志”小时行同步到数据库：

- 宽表：`bf_imes.imes_bf2_operation_log_report`
- 视图：`bf_imes.v_bf2_operation_log_report`
- 已有行数：`4320`，即约 `180` 天 × `24` 小时
- 现有字段包括：
  - `workdate`
  - `report_row_number`
  - `report_id`
  - `report_pulverized_coal`
  - `report_coal_ratio`
  - `report_fuel_ratio`
  - `report_batch_count`
  - `report_ore_batch`
  - `report_coke_batch`
  - `report_coke_breeze`
  - `report_moisture`
  - `report_headers`
  - `report_cells`

但是目前还有三个边界：

1. 现有作业日志表只保存小时操作行 `7–32`，没有保存报表里“炉前出铁情况”块，因此没有直接保存报表内 Si。
2. `material_rate` 当前为空，并标记为 `semantic_unconfirmed`；同步脚本明确写明“D列为批数，未将批数直接当作料速”。如果现场说的“料速”就是该小时批数或由批数折算出的小时料速，需要工长确认公式后再启用。
3. 当前同步计划任务名 `IMESBF2OperationLogReport5m` 在只读探测中未查到注册状态；按关键词扫描计划任务也未发现明确的“作业日志报表同步”任务，只看到 `\GL02SensorSync\IMESRealtime`、`\BlastFurnaceServices\HeatPerformanceQualitySync` 等。远端同步入口文件存在，数据库也已有 4320 行，说明历史入库已执行过；后续上线前要补注册或确认实际调度入口，并验收最近日志。

## 已验证的数据源

### MES Web 作业日志报表

报表名称：`2#高炉冀南新区高炉作业日志（报表查询结果）`

远端同步脚本：

```text
F:\高炉炼铁项目-real-sensor-v2_V3\数据库同步和存取\sync_bf2_operation_log_report.py
F:\高炉炼铁项目-real-sensor-v2_V3\数据库同步和存取\src\imes_report_client.py
F:\高炉炼铁项目-real-sensor-v2_V3\数据库同步和存取\src\imes_pg_store.py
```

本机留档：

```text
PT\预测铁水Si含量\reports\experiments\EXP-SI-FUELRATIO-REPORT-20260808\db_surface_audit\
```

解析口径：

- Raqsoft 报表网格 id 会随会话变化，例如 `sg2130`、`sg2170`；后续解析炉前出铁块时必须通用识别 `sg\d+_列行`，不能硬编码某一个 grid id。
- 现有同步只解析小时行：
  - `7–14`：1–8 时
  - `16–23`：9–16 时
  - `25–32`：17–24 时
- 煤比按报表 K 列公式重算；
- 燃料比按报表 M 列公式重算；
- `material_rate` 未确认，不强行从 D 列“批数”推断。

### 逐炉实际 Si

现有逐炉质量汇总表：

```text
bf_assistant.heat_performance_quality_summary
```

已验证行数：`9647`

该表保存每炉平均 Si：

```text
meltno / furnace_no / work_date / open_ts / close_ts / si_avg / sample_details / source_status
```

这张表适合作为“实际 Si”权威标签。若用户明确要求“报表内炉前出铁块显示的 Si”，则应扩展作业日志同步，把报表第 38 行附近的炉前块另存为报表源事实表，并与 `heat_performance_quality_summary` 交叉核验。

## 推荐落库结构

### 已有表继续保留

`bf_imes.imes_bf2_operation_log_report`

用途：MES Web 作业日志小时行原始镜像和报表公式复算值。保留在 `bf_imes`，表示它是 IMES/MES 来源数据。

### 新增：炉前块源表

建议新增：

```text
bf_imes.imes_bf2_operation_log_heat_block
```

一行对应一个作业日志日报里的“炉前出铁情况”块。

建议字段：

| 字段 | 含义 |
|---|---|
| `_row_key` | 幂等键，例如 `bf2_operation_log_heat_block|2026-08-07|2D012|91` |
| `workdate` | 报表日期 |
| `prodcentercode` | `2D012` |
| `report_heat_no` | 报表炉次短号，例如 `91` |
| `report_open_ts` | 报表开口时间 |
| `report_close_ts` | 报表堵口时间 |
| `report_duration_minutes` | 报表出铁时长 |
| `report_batch_between_taps` | 铁间批料 |
| `report_theory_iron` | 理铁 |
| `report_south_taphole_iron` | 南铁口 |
| `report_north_taphole_iron` | 北铁口 |
| `report_c` / `report_si` / `report_mn` / `report_p` / `report_s` / `report_ti` | 报表炉前成分 |
| `report_can_numbers` | 罐号 |
| `report_cells` | 原始单元格 JSONB |
| `metric_source` | `report_cell_extracted` |
| `fetched_at` / `updated_at` | 同步时间 |

### 新增：面向页面的分析特征表

建议新增：

```text
bf_assistant.foreman_fuel_ratio_si_features
```

一行对应一个目标炉次和一个计算 cutoff，例如开口前 1 小时或当前时刻。

建议字段：

| 字段 | 含义 |
|---|---|
| `id` | 自增主键 |
| `furnace_no` | 高炉号 |
| `target_meltno` | 目标炉号 |
| `target_open_ts` | 目标炉开口时间 |
| `cutoff_ts` | 预测/计算截止时刻 |
| `baseline_days` | 基准天数，默认 2 |
| `baseline_fuel_ratio` | 前几日平均燃料比 |
| `baseline_si` | 基准 Si，可为固定 0.30 或前几日实际均值 |
| `current_4h_fuel_ratio` | 当前前 4 小时燃料比 |
| `current_4h_batch_count` | 当前前 4 小时批数/待确认料速 |
| `fuel_ratio_delta` | 当前燃料比 - 基准燃料比 |
| `rule_si_delta` | 按工长系数折算的 Si 变化 |
| `rule_predicted_si` | 工长经验法预测 Si |
| `actual_si_avg` | 实际每炉平均 Si，来自质量汇总 |
| `abs_error` | 预测误差 |
| `hit_005` / `hit_002` | 命中标志 |
| `calc_params` | 公式参数 JSONB |
| `source_context` | 使用的小时行、炉次、数据状态 JSONB |
| `source_status` | `experimental_offline` / `shadow` |
| `created_at` / `updated_at` | 生成时间 |

### 新增：公式版本表

建议新增：

```text
bf_assistant.foreman_fuel_ratio_rule_versions
```

用途：把工长提供的公式、系数和假设完整记录下来，避免以后口径漂移。

建议字段：

| 字段 | 含义 |
|---|---|
| `rule_version` | 例如 `foreman-fuel-ratio-v1` |
| `baseline_days` | 默认 2 |
| `fuel_kg_per_0p1_si` | 默认 `5` |
| `default_baseline_si` | 默认 `0.30` |
| `current_window_hours` | 默认 `4` |
| `formula_text` | 中文公式说明 |
| `status` | `draft/active/retired` |
| `source_note` | 来源说明 |
| `created_at` | 创建时间 |

## 页面设计建议

页面名称建议：

```text
工长燃料比 Si 预判
```

页面必须同时展示两类结果：

1. 工长经验法：
   - 前几日平均燃料比；
   - 当前前 4 小时燃料比；
   - 燃料比差值；
   - `5 kg/t -> 0.1% Si` 的折算；
   - 预测 Si；
   - 实际 Si；
   - ±0.05/±0.02 是否命中。

2. 我们自己的模型：
   - V19/V20 当前最佳影子预测；
   - 预测区间；
   - 实际 Si；
   - ±0.05/±0.02 是否命中。

交互控件：

- 基准天数：`1/2/3/7` 天；
- 当前窗口：`4/6/8/12` 小时；
- 系数：默认 `5 kg/t -> 0.1% Si`，允许临时调参；
- 基准 Si：固定 `0.30` 或选择“前 N 日平均 Si”；
- 目标炉次或当前时刻；
- 只读导出 CSV/PNG/报告。

页面边界：

- 初期页面必须标记为 `experimental_offline` 或 `shadow`；
- 不替换生产模型；
- 不写生产设定值；
- 公式参数调整只影响页面计算，不直接影响生产控制。

## 验收标准

1. 数据层：
   - 作业日志小时表连续性：每天 24 行；
   - 燃料比字段覆盖率；
   - 炉前块 `report_si` 与 `heat_performance_quality_summary.si_avg` 差异审计；
   - `material_rate` 口径经现场确认后才从 `semantic_unconfirmed` 改为正式。

2. 计算层：
   - 同一炉次、同一 cutoff 重复计算结果一致；
   - 公式版本固定可追溯；
   - 支持 ±0.05/±0.02 命中率、MAE、RMSE、bias。

3. 页面层：
   - 工长公式必须逐项展开；
   - 预测 Si 和实际 Si 同屏对比；
   - 曲线、表格、导出报告可用；
   - 明确区分“工长经验法”和“机器学习模型”。

4. 文档层：
   - 保留公式来源、参数、样本区间、命中率；
   - 每次对外展示都有可复现的 CSV/JSON/图。

## 当前建议的下一步

1. 先不要新建 `bf_imes.mes_operation_log_report_raw`，因为 220.12 已有 `bf_imes.imes_bf2_operation_log_report`。
2. 优先扩展现有 `sync_bf2_operation_log_report.py`，新增炉前出铁块解析和 `report_si` 入库。
3. 建立 `bf_assistant.foreman_fuel_ratio_si_features`，作为页面和评估的唯一读取表。
4. 先做离线回填 `2026-07-22~2026-08-08`，验证报表炉前 Si 与现有平均 Si 的差异，再决定页面默认使用哪个实际 Si 标签。
5. 页面先做只读 shadow 版，用于展示和比对，不参与生产控制。
6. 正式启用前补上作业日志同步计划任务验收：任务名称、运行账号、5分钟触发器、最近运行结果、日志路径和 24 行/日连续性检查。
