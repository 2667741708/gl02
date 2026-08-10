# 2026-08-07 MES 089/090 同步链路核查

追踪编号：`Q-MES-HEAT-089-090-SYNC-20260807`

## 结论

- 用户截图中的 89/90 是 `2#20260806-089` 与 `2#20260806-090`，不是 `2#20260807-089/090`。
- 220.12 的 `HeatPerformanceQualitySync` 计划任务存在，最近运行结果为 `0`，同步日志显示增量任务持续成功运行。
- MES/Vastbase 源库里已经有 `2#20260806-089` 与 `2#20260806-090` 的炉次、生产实绩和铁水化验数据。
- 当前 220.12 PostgreSQL 镜像里，`2#20260806-089` 已进入 `bf_imes.raw_rows` 与派生 IMES 镜像表，但关键时间、铁量和 Si 字段为空，因此不会形成有效质量汇总。
- 当前 220.12 PostgreSQL 镜像里未查到 `2#20260806-090` 的镜像记录。
- 8093 质量页读取的是 `bf_assistant.heat_performance_quality_summary`；该表当前没有 `2#20260806-089/090` 汇总行。
- 根因：同步脚本为了防止读未来炉次，调用 `heat_service._fetch_heat_rows()` 时设置 `max_open_time = datetime.now() + 5min`。但 MES 源库中 `2#20260806-089/090` 的 `opentime` 被写成 `2026-08-07 22:50:00` 与 `2026-08-07 23:33:00`，在当前上午运行时属于未来时间，因此被增量同步主动排除。

## 当前链路

220.12 到 MES/Vastbase 的正式数据库链路为：

```text
220.12 -> 10.10.181.195:5432/vastbase
```

生产运行脚本为 [run_22012_heat_performance_sync.ps1](../../tools/run_22012_heat_performance_sync.ps1)，它设置：

- `IMES_OPS_DB_HOST=10.10.181.195`
- `IMES_OPS_DB_PORT=5432`
- `IMES_LAB_DB_HOST=10.10.181.195`
- `IMES_LAB_DB_PORT=5432`

同步入口为 [sync_22012_heat_performance_quality.py](../../tools/sync_22012_heat_performance_quality.py)，流程是：

1. `heat_service._fetch_heat_rows()` 从 Vastbase `public.t_ipes_cond` 取 2# 炉次主记录，要求 `opentime IS NOT NULL`。
2. `heat_service._attach_outputs()` 从 `public.t_ipes_out_put` 关联出铁实绩。
3. `heat_service._fetch_lab_rows_for_heats()` 从 `public.t_qpes_inner_batch + public.inner_batch_insp_bb` 取铁水化验。
4. `build_summary_row()` 聚合每炉均值。
5. `HeatPerformanceQualityStore.upsert_rows()` 写入 `bf_assistant.heat_performance_quality_summary`，冲突键为 `meltno`。

## 已执行只读核查

本机只读脚本：[audit_heat_20260806_089_090_22012.py](../../tools/audit_heat_20260806_089_090_22012.py)

核查对象：

- `bf_assistant.heat_performance_quality_summary`
- `bf_imes.imes_bf2_output_list_cond_data`
- `bf_imes.imes_bf2_heat_lab_list_cond_data_avg2`
- `bf_imes.raw_rows`

结果摘要：

| 对象 | `2#20260806-089` | `2#20260806-090` |
| --- | --- | --- |
| `bf_assistant.heat_performance_quality_summary` | 无汇总行 | 无汇总行 |
| `bf_imes.imes_bf2_output_list_cond_data` | 1 行，但关键字段为空 | 0 行 |
| `bf_imes.imes_bf2_heat_lab_list_cond_data_avg2` | 1 行，但 Si 为空 | 0 行 |
| `bf_imes.raw_rows` | 4 行，`fetched_at` 约为 `2026-08-07 00:01`，关键字段为空 | 0 行 |

## MES/Vastbase 源库直接核查

远端只读探针：[remote_probe_vastbase_20260806_089_090.py](../../tools/remote_probe_vastbase_20260806_089_090.py)

远端运行脚本：[remote_run_probe_vastbase_20260806_089_090.ps1](../../tools/remote_run_probe_vastbase_20260806_089_090.ps1)

220.12 使用 `10.10.181.195:5432/vastbase` 直连源库后返回：

| 源表 | `2#20260806-089` | `2#20260806-090` |
| --- | --- | --- |
| `public.t_ipes_cond` | 存在；`opentime=2026-08-07 22:50:00`，`closetime=2026-08-07 23:33:00` | 存在；`opentime=2026-08-07 23:33:00`，`closetime=2026-08-07 00:30:00`，`tappingtime=-1383.00` |
| `public.t_ipes_out_put` | 2 行，铁量 `61.400 + 115.050` | 3 行，铁量 `108.950 + 13.150 + 178.250` |
| `public.t_qpes_inner_batch + public.inner_batch_insp_bb` | 1 个 Si 样本：`0.48` | 2 个 Si 样本：`0.37, 0.27`，平均 `0.32` |

其中 090 的 `closetime` 早于 `opentime`，是跨日时间拼接异常；089/090 的 `opentime` 相对核查时刻处于未来，是本次同步漏掉的直接触发条件。

## 远端状态

只读检查 `\BlastFurnaceServices\HeatPerformanceQualitySync`：

- `State=3`，即 Ready。
- `LastTaskResult=0`。
- 日志尾部持续返回 `ok=true`，最近同步窗口最新开口时间达到 `2026-08-07T07:40:00`，说明任务未停。

## 待确认

## 已实施：IMES 回看核验同步

2026-08-07 已在 [sync_22012_heat_performance_quality.py](../../tools/sync_22012_heat_performance_quality.py) 增加 IMES 回看核验同步：

1. 增量同步保持现有防未来过滤，避免错误提前发布尚未开始炉次。
2. 新增按 `workdate` 和 `meltno` 的回看核验任务，不只依赖 `opentime < now()`。
3. 对 `opentime` 未来、`closetime < opentime`、`tappingtime < 0` 的炉次打异常标记，但仍允许进入待核验队列。
4. 当同一炉号在 `t_ipes_out_put` 或铁水化验表已有真实记录时，允许用 `meltno` 精确补同步汇总，并在 `source_status` 中标记 `time_anomaly_repaired`，不能静默当正常时间使用。
5. 对修复炉次的出铁实绩 `workdate/weight_time` 也按修复后开口日期重基准；时分秒小于开口时分秒时滚到第二天，避免 `source_updated_at` 被原始未来日期污染。
6. 每次回看输出缺口清单：源库有、镜像无；源库有字段、镜像为空；汇总表缺失；化验样本数变化。

> 2026-08-07 后续核验修正：上述第6项在当时的远端脚本中只有文档声明，没有真实程序输出。本机现已在 [闭环增强](2026-08-07-heat-quality-repair-closed-loop.md) 中实现三层审计、结构化原因、未来隔离和状态优先级；该增强尚未部署 220.12，因此不能把远端状态表述为已闭环。

已上传到 220.12：

- `F:\高炉炼铁项目-real-sensor-v2_V4_8093_PREVIEW\standalone_heat_dashboard_8891\tools\sync_22012_heat_performance_quality.py`

执行 dry-run 后返回 `repair_candidates=4`、`repaired=4`；正式执行后写入 4 炉修复汇总。`HeatPerformanceQualitySync` 计划任务仍保持启用，最近 `LastTaskResult=0`。

已验证 8093 API：

| 炉次 | 修复后开口/堵口 | 平均 Si | 状态 |
| --- | --- | ---: | --- |
| `2#20260806-089` | `2026-08-06 22:50:00` / `2026-08-06 23:33:00` | `0.48000` | `time_anomaly_repaired`；`source_updated_at=2026-08-07 00:36:20` |
| `2#20260806-090` | `2026-08-06 23:33:00` / `2026-08-07 00:30:00` | `0.32000` | `time_anomaly_repaired`；`source_updated_at=2026-08-07 01:32:40` |

验证命令：

```powershell
python .\tools\remote_22012_exec.py --allow-agents-password --no-profile --timeout 180 --workdir "F:\高炉炼铁项目-real-sensor-v2_V4_8093_PREVIEW\standalone_heat_dashboard_8891" --script "tools\remote_dry_run_heat_performance_repair.ps1"
python .\tools\remote_22012_exec.py --allow-agents-password --no-profile --timeout 180 --workdir "F:\高炉炼铁项目-real-sensor-v2_V4_8093_PREVIEW\standalone_heat_dashboard_8891" --script "tools\remote_run_heat_performance_repair_once.ps1"
Invoke-WebRequest -UseBasicParsing -Uri 'http://10.30.220.12:8093/api/heat-performance-quality?meltno=2%2320260806-089&limit=2'
Invoke-WebRequest -UseBasicParsing -Uri 'http://10.30.220.12:8093/api/heat-performance-quality?meltno=2%2320260806-090&limit=2'
```
