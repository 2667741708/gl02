# 本机原生 PostgreSQL 与 220.12 同步验证

状态：部分通过；端到端一致性被本机认证与同步进程状态阻断  
最后核对日期：2026-08-14  
事项编号：`OPS-LOCAL-22012-SYNC-VERIFY-20260814`

## 结论

- 220.12 的 pSpace → PostgreSQL 实时采集链路健康：最近数据延迟约 1.65 分钟，最近
  10 分钟覆盖 151 个点，最近 8 个 `sync_runs` 均为 `tags_ok=151`、`tags_error=0`。
- 本机 PostgreSQL 16 服务和 `127.0.0.1:18000` 监听正常，但没有运行
  `start_local_pg_sync_loop.ps1` / `sync_22012_pg_to_local.py`，也没有本机同步日志或对应计划任务。
- 受控账号文档中记录的本机 `postgres` 密码和同步脚本中的旧 `gl02_sync` 回退密码均无法通过
  当前本机 PostgreSQL 的 SCRAM 认证。因此未能只读查询本机表，不能完成两端行数、最新时间和
  样本值逐项对比；不得把本次结果表述为“同步一致”。
- 220.12 外部只读账号可以连接 `10.30.220.12:5432/bf_trend`，同步器覆盖的 8 张源表均存在。

## 只读验证证据

### 220.12

- 持久 SSH 会话正常复用，`ssh_authenticated=true`，没有上传、服务停启或远端写入。
- `BlastFurnaceV3PgContinuousSync30s` 与 `Watchdog` 为 Ready；旧 `Realtime` 为 Disabled。
- 当前只有一条 `run_realtime_sync_pg_bg.ps1` 包装进程；上游 `10.22.181.243:8889` 可达。
- `bf_sensor.one_minute_values`：
  - `max(ts)=2026-08-14 08:32:00`
  - 查询时 `lag_min=1.647`
  - 最近 10 分钟点位数为 151
  - 最近 24 小时 `PS_RAW_AVERAGE=147116` 行、`PS_STATE_HOLD=66205` 行
- `bf_sensor.raw_5s_values` 最新到 `2026-08-14 08:32:36`，覆盖 151 个点。
- 最近日志截至 `2026-08-14 08:37:56`，`failed_chunks=0`。

### 本机

- 服务 `postgresql-x64-16`：Running / Automatic。
- `127.0.0.1:18000`：Listening。
- 没有 8092、8767、8890 本机监听，也没有本地同步循环进程或同步日志。
- `pg_hba.conf` 对本机 TCP 使用 `scram-sha-256`；两套已记录凭据均认证失败后停止尝试，未重置
  账号、未修改 `pg_hba.conf`、未停止数据库服务。

## 程序与配置一致性

本机与 220.12 的以下 6 个关键文件 SHA-256 一致：

- `schema/postgresql_required_points.sql`
- `src/sync_from_243_pg.py`
- `src/pg_store.py`
- `run_realtime_sync_pg_bg.ps1`
- `run_22012_continuous_sync.ps1`
- `src/sync_watchdog.py`

`config/sync_config.json` 不一致：本机未提交版本将顶部压力变量改为
`P_top_A/B/C/D`，220.12 仍为 `P_top_gas_A/B/C/D`；220.12 当前
`bf_sensor.sensor_registry` 也只登记并启用了 `P_top_gas_A/B/C/D`。该分叉在本次验证前已经存在，
本次没有覆盖任一版本。

## 实现入口

- [本机主启动数据库选择](../../start_v3_full.ps1#L35-L81)
- [本地同步循环旧回退值](../../tools/start_local_pg_sync_loop.ps1#L17-L31)
- [220.12 → 本机同步器](../../tools/sync_22012_pg_to_local.py#L127-L160)
- [远端分钟同步审计探针](../../tools/remote_audit_pspace_minute_semantics.ps1)
- [远端进程与哈希探针](../../tools/remote_probe_pspace_sync_processes.ps1)

## 后续最小闭环

1. 由用户提供或恢复当前本机原生 PostgreSQL 的有效受控账号，并只通过进程环境变量注入；同步更新
   `docs/数据库账号配置说明.md`，不得把密码复制到本 handoff。
2. 先只读查询本机 `bf_sensor.one_minute_values`、`sensor_registry`、诊断和质量表的最新时间与计数。
3. 明确 `P_top_A/B/C/D` 与生产 `P_top_gas_A/B/C/D` 的权威命名后，再决定是否同步配置；未经确认
   不覆盖远端配置。
4. 如需恢复自动同步，单独授权启动本地同步循环；启动后对两端相同时间窗执行计数、主键和样本值对比。

## 影响边界

本轮只有只读探测和本交接记录；没有写数据库、启动同步、修改计划任务、上传文件、停止服务或修改
220.12 生产文件。
