# 220.12 IMESRealtime 一分钟调度部署记录

追踪编号：`OPS-IMES-REALTIME-1MIN-20260809`

## 结果

- 计划任务：`\GL02SensorSync\IMESRealtime`
- 调度周期：`PT5M` → `PT1M`
- 重叠策略：`IgnoreNew`，上一轮未结束时跳过重复实例，不并发访问 IMES。
- 原任务 Action、Principal 保持不变。
- 部署器远端固定路径：`F:\高炉炼铁项目-real-sensor-v2_V4_8093_PREVIEW\tools\set_22012_imes_realtime_1min.ps1`
- 本机与远端部署器 SHA-256：`E21BCAEACE48D89AE517738B16832F727402560059B33E1243464704853B13BF`
- 原任务 XML 备份：`F:\高炉炼铁项目-real-sensor-v2_V4_8093_PREVIEW\logs\deploy_backups\IMESRealtime_1min_20260809_194236\IMESRealtime.before.xml`
- 原任务 XML SHA-256：`0C28B9CE818F7F1CDB22F3692EE6FFDAD7C527DDB49476E8A4D19C8704CB889B`
- 部署时间：`2026-08-09 19:42:38 +08:00`；`rollback_applied=false`。

## 验收证据

- 部署器主动启动验证轮：`2026-08-09 19:42:42 +08:00`。
- 独立复核：`2026-08-09 19:44:45 +08:00`，任务仍为 `PT1M + IgnoreNew`，下一次计划时间为 `19:45:45`。
- `bf_imes.raw_rows` 的 `bf2_output_list_cond_data` 已更新到 `19:44:39`，正式炉次上限为 `2#20260809-126`。
- 第二次独立复核：`19:47:27` 时任务已按一分钟触发推进到 `LastRunTime=19:46:46`、`NextRunTime=19:47:47`；镜像三个目标数据集分别推进到 `19:44:39`、`19:44:40`、`19:44:48`。任务处于 `Running` 时显示的 `0x800710E0` 不作为完成轮失败证据，完成性以同步日志和镜像时间前进为准。
- 部署前后受保护 PID 完全一致：8093=`7256`、8768=`12816`、8094=`13748`、8770=`3732`。
- 未停止或重启 8093、8768、8094、8770，也未修改其服务配置。

## 运行边界

`IMESRealtime` 单轮实测可能超过两分钟。现在的“每一分钟”表示任务调度器每分钟尝试触发；由于 `IgnoreNew`，运行中的上一轮不会被重叠启动。因此当前能降低原来固定五分钟等待，但不能保证每个自然分钟都完成一次全量同步。若需稳定的一分钟端到端时延，应继续拆分/增量化 IMES 数据集同步。

下游 `\BlastFurnaceServices\HeatPerformanceQualitySync` 本次仍保持每五分钟执行；本次没有把炉次质量汇总链路整体改成一分钟。

## 本地验证

- PowerShell 语法：通过。
- 部署合同：`tests/test_set_22012_imes_realtime_1min.py` 通过。
- 部署器包含任务 XML 备份、失败回滚、只读 PostgreSQL 新鲜度核验和受保护 PID 核验。
