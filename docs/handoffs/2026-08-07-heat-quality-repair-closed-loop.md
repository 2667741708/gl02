# 炉次质量时间回看闭环增强（2026-08-07）

追踪编号：`REQ-HEAT-QUALITY-REPAIR-CLOSED-LOOP-20260807`

## 结论

原有业务方向保留：常规增量继续防未来数据，异常回看使用正式 `meltno` 与 MES `workdate`，只有存在真实出铁或铁水化验证据才补写。089、090 的跨日期恢复口径没有被破坏。

本轮修复了五个缺口：修复谱系不再被普通同步覆盖；未来/日期锚点冲突进入隔离；缺口清单变成真实三层审计；异常原因结构化落库；扫描分页且指标名称精确。2026-08-09 又补齐默认本地镜像链路的“已有汇总差异复核”和“镜像行过期后的汇总血缘重算”，并已部署 220.12。

## 时间情况与处理矩阵

| 情况 | 判断 | 处理 |
|---|---|---|
| `meltno` 日期、`workdate`、原始开堵口日期一致 | 正常 | 走常规增量，不添加修复状态 |
| 原始开口日期错位，但 `meltno` 日期与 `workdate` 一致 | 可确定修复 | 使用 `workdate + 开口时分秒`，原因 `opentime_date_rebased_to_workdate` |
| 堵口时分秒小于开口时分秒 | 跨午夜 | 堵口日期使用 `workdate + 1 day`，原因 `closetime_rollover_next_day` |
| 原始堵口早于原始开口 | 原始异常 | 记录 `raw_closetime_before_opentime`，以修复后时间重算时长 |
| `tappingtime < 0` | 原始异常 | 记录 `negative_tappingtime`，不用负值作为有效出铁时长 |
| 当天 `workdate`，修复后开口晚于当前时间5分钟 | 尚未到时 | `future_pending=true`，默认 API 不展示 |
| `workdate >= tomorrow` | 未来日期 | 不进入回看结果，计入 `future_workdate_filtered` |
| 正式 `meltno` 日期与 `workdate` 不一致 | 双锚点冲突 | 不猜日期，记录 `meltno_workdate_date_mismatch` 并隔离为 `future_pending` |
| 异常炉次没有出铁且没有铁水化验 | 缺少业务证据 | 不写汇总，计入 `skipped_no_evidence` |
| 已修复炉次出现迟到化验/称量 | 新业务事实 | 更新化验、铁量和明细，但保留修复时间、状态、原因和核验时间 |
| 仅因未来时间进入 `future_pending`，且时间已到并获得有效记录 | 待核验解除 | 允许正常同步替换待核验状态，避免永久锁死 |
| `meltno/workdate` 日期冲突仍未修正 | 锚点冲突未解除 | 即使时间已到仍保持隔离，禁止普通增量静默覆盖 |
| 原始 `opentime` 为空 | 无法由时分秒修复 | 不用 `workdate 00:00` 冒充开口时间；等待真实时间或单独人工核验 |
| 扫描数量超过上限 | 容量边界 | 按页读取；达到最大行数返回 `repair_truncated=true`，不静默截断 |

## 程序变更

- [聚合表与写入合同](../../高炉前端数据/智能助手/backend/heat_performance_quality.py)：新增 `time_anomaly_reasons jsonb`、`repair_checked_at`、`future_pending`；upsert 对修复谱系设置优先级；API 默认过滤待核验记录；新增原始镜像/汇总缺口审计。
- [同步器](../../tools/sync_22012_heat_performance_quality.py)：未来日期上界、分页、双日期锚点检查、结构化原因、精确指标、真实三层缺口清单。
- [幂等迁移](../../tools/migrate_heat_quality_time_repair_columns_22012.py)：补齐新增列和迁移后审计查询。本轮未执行此写库工具。
- [8093 API](../../高炉前端数据/智能助手/backend/ollama_proxy_server.py)：支持显式 `include_future=1` 运维核验，默认仍隔离。

## 缺口审计合同

- `source_present_mirror_missing`：Vastbase 本轮有炉次事实，但 `bf_imes.raw_rows` 没有同一 `meltno`。
- `source_field_mirror_empty`：Vastbase 有开/堵口、出铁或 Si，而原始镜像对应字段为空。
- `summary_missing`：Vastbase 本轮有可聚合炉次，但 `heat_performance_quality_summary` 没有同一 `meltno`。
- `sample_count_changes`：本轮源化验样本数与现有汇总不同。
- `mirror_audit_available=false`：原始镜像表不可访问或不存在；这不是“零缺口”。

## 验证

```powershell
& 'D:\ProgramData\anaconda3\python.exe' -m pytest `
  'tests\test_heat_performance_quality.py' `
  'tests\test_heat_performance_quality_query.py' `
  'tests\test_heat_performance_quality_repair_loop.py' -q
```

2026-08-09 最终结果：相关测试集 `38 passed`。聚合存储、8093 代理、同步器、迁移器和 IMES MCP 服务 `py_compile` 通过。

## 生产上线状态（2026-08-09）

已按“备份 → 暂停同步任务/8093健康检查 → 只停止8093 → 原子部署 → 幂等DDL/同步 → 恢复8093与任务 → 精确炉号验收”执行。最终 089/090 均为 `time_anomaly_repaired`，计划任务最近结果为 0；8093、8768 正常监听，8094/8770 PID 未改变。远端备份、哈希、API 和具体炉次证据见[生产交接](2026-08-09-heat-quality-closed-loop-production.md)。
