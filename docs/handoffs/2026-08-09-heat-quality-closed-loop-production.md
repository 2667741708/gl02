# 8093 炉次质量时间血缘闭环生产交接（2026-08-09）

追踪编号：`REQ-HEAT-QUALITY-REPAIR-CLOSED-LOOP-20260807`

## 最终结论

本机代码与 220.12 运行副本现已一致，默认每 5 分钟任务可以按正式 `meltno` 日期、MES `work_date` 和原始开堵口时分秒自动修复错误日期。修复只更新时间血缘字段，不会用本地镜像中的炉次平均化验覆盖已有的罐次、试样或出铁明细。

首次审计发现远端处于“代理新版、业务存储旧版、同步器新版”的部分部署状态，8093 API 因 `list_rows(query=...)` 合同不匹配返回 503。两份业务存储模块、同步器和 SYSTEM 计划任务运行器已分段更新；运行器改为从 `$PSScriptRoot` 推导路径，避免 Windows PowerShell 5 对 UTF-8 无 BOM 中文路径字面量的错误解码。

## 自动修复链路

1. 先从 `bf_imes.raw_rows` 补齐缺失或缺少 Si 的正式炉次。
2. 对镜像仍保留的炉次比较源时间和已有汇总时间。
3. 镜像行过期时，从汇总表保留的 `raw_open_ts/raw_close_ts`，结合正式炉号日期和 `work_date` 重新计算。
4. 跨午夜堵口使用 `work_date + 1 day`；正式炉号日期和 `work_date` 冲突则进入 `future_pending`。
5. `apply_time_repairs()` 仅更新日期、开堵口时间、时长、状态、原因和核验时间，不更新化验/罐次/试样/出铁明细。
6. API 默认隐藏 `future_pending`；运维核验可显式传 `include_future=1`。

## 真实炉次验收

| 炉次 | 工作日期 | 修复后开口 | 修复后堵口 | 原始时间 | 状态与原因 |
|---|---|---|---|---|---|
| `2#20260806-089` | `2026-08-06` | `2026-08-06 22:50` | `2026-08-06 23:33` | 原记录日期为 `2026-08-07` | `time_anomaly_repaired`；`opentime_date_rebased_to_workdate`、`closetime_date_rebased_to_workdate` |
| `2#20260806-090` | `2026-08-06` | `2026-08-06 23:33` | `2026-08-07 00:30` | 原时分秒保留 | `time_anomaly_repaired`；`closetime_rollover_next_day` |

两炉均为 `future_pending=false`；089 `si_avg=0.48`，090 `si_avg=0.32`。这些化验值未因时间修复重新计算或覆盖。

## 生产运行证据

- `BFV4PreviewProxy8093=Running`，8093 PID `7920`。
- `BFV4PreviewWs8768=Running`，8768 PID `12816`。
- 8094 PID `13748`、8770 PID `3732`，本轮未重启。
- `\BlastFurnaceServices\HeatPerformanceQualitySync=Ready`，`LastTaskResult=0`。
- 8093 健康检查任务为 `Ready`。
- 业务存储（根目录与 standalone）SHA-256：`F4555D9D0EC6D14314194C8CE78C8DD0E40A248CCFAF7F5BD4E19771CC875CAB`。
- 同步器 SHA-256：`30D8A8E8FB8508EFF6787DD76CB4AC005984412564FCC6EF44F9F4727489CABE`。
- 计划任务运行器 SHA-256：`42428FD1BC35294FAA1D8B24F0BCF563EC02E212DFE3AAA2E3E8C03776105EBC`。
- 主部署备份：`logs/deploy_backups/heat_quality_closed_loop_20260809_184119`。
- 最终同步器备份：`logs/deploy_backups/heat_quality_sync_diff_fix_20260809_190550`。

## 验证

相关测试命令覆盖存储、查询、修复循环、IMES MCP 炉次汇总、罐次展示和映射合同，结果 `38 passed`。存储、代理、同步器、迁移器和 IMES MCP 服务均通过 `py_compile`。

远端最终只读审计入口为 [remote_final_audit_heat_quality_closed_loop_20260809.ps1](../../tools/remote_final_audit_heat_quality_closed_loop_20260809.ps1)。受控部署和分段修复入口分别为：

- [remote_guarded_deploy_heat_quality_closed_loop_20260809.ps1](../../tools/remote_guarded_deploy_heat_quality_closed_loop_20260809.ps1)
- [remote_deploy_heat_quality_sync_runner_20260809.ps1](../../tools/remote_deploy_heat_quality_sync_runner_20260809.ps1)
- [remote_deploy_heat_quality_sync_diff_fix_20260809.ps1](../../tools/remote_deploy_heat_quality_sync_diff_fix_20260809.ps1)
