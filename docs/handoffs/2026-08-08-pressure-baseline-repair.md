# 220.12 压力基线修复回执（2026-08-08）

## 已完成

1. 生产计划任务 `BlastFurnace8093DailyBaseline20d` 已切换为 V4 包装入口：
   `F:\高炉炼铁项目-real-sensor-v2_V4_8093_PREVIEW\tools\run_v4_daily_baseline.ps1`
2. 包装入口使用 V4 `baseline_maintainer.py` 的30天窗口，不再使用旧的20天脚本。
3. 原计划任务 XML 和动作已备份到：
   `F:\高炉炼铁项目-real-sensor-v2_V4_8093_PREVIEW\backups\baseline_task_switch_20260808_093853`
4. 从 `bf_sensor.one_minute_values` 重新计算并提交 p25/p75：
   - `P_blast_cold`：138条
   - `P_blast`：138条
   - 总计：276条
   - 使用现有零值审计策略和每分钟聚合；重算样本数与原基线样本数一致。

## 数据结果

修复后，30天基线共140天的两类压力记录均完整：

| 变量 | 总行数 | p25/p75完整 | 缺失 |
|---|---:|---:|---:|
| `P_blast_cold` | 140 | 140 | 0 |
| `P_blast` | 140 | 140 | 0 |

最新 `P_blast_cold`（基线日 `2026-08-08`）：

- p25：`449.392364`
- p75：`458.506927`
- 样本数：`42747`
- 覆盖率：`0.989514`

## 计划任务实跑验证

修复后的计划任务已手动触发一次并成功完成：

- `LastTaskResult=0`
- `LastRunTime=2026-08-08 10:03:03`
- V4 维护器写入 `152` 个变量基线行

## 建议链路验收

- 8768 WebSocket：返回当前建议批次；`P_blast_cold` 的 `needs_data` 数量为 `0`，存在正常的 `eligible` 压力动作。
- 喷煤仍可能因煤质化验字段缺失返回 `needs_data`，这与压力基线无关。
- 8094 HTTP：200。
- 8094 `/api/furnace-rules/latest`：200，33项规则完整（A9/B13/C11）。
- 8094 普通接口未发现公式、权重、阈值、归一化值或贡献字段泄露。

本次只修复基线派生字段和基线任务入口，没有向生产设备下发控制指令。
