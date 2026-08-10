# 数据库同步和存取

本目录用于把备份数采服务器 `10.22.181.243:8889` 中指定点位同步到 220.12 PostgreSQL，并提供按变量和任意历史范围查询的程序。历史回填默认读取 pSpace 1min processed 均值；实时增量默认读取 5s raw 并为每分钟选择一个有效 sample 值。当前策略是持续保留 3 年数据，超出 3 年的月份分区自动删除。

## IMES 只读采集

已新增 `src/imes_readonly_client.py`，用于通过 IMES Web 系统只读读取 2#高炉页面数据，支持登录检查、页面接口发现、分页读取、保存 JSON/CSV/SQLite，以及本地 SQLite 只读查询。凭证只从环境变量或本机 `.env.imes.local` 读取，不写入仓库；程序会拒绝疑似新增、修改、删除、上传、导入等接口。

已新增 `从IMES数据库同步.py` 和 PostgreSQL schema `schema/postgresql_imes.sql`，用于把 IMES 只读数据同步到 220.12 `bf_trend.bf_imes`。当前支持左侧 10 个 2#高炉页面的动态只读表格接口发现与同步；读取日期会自动对齐 `bf_sensor.one_minute_values` 已有时间范围，早于 GL02 传感器库下限的数据不再读取或写入。220.12 上可运行 `run_22012_从IMES数据库同步.ps1` 执行当天同步。详细用法见 `IMES只读采集说明.md`，可读清单见 `config/IMES可读数据清单.tsv`，存储位置说明见 `IMES数据存储位置与时间范围.md`。

### 2# 高炉作业日志报表

“报表管理 → 冀南高炉报表 → 冀南新区高炉作业日志”是 Raqsoft 两段 POST 的 HTML 报表，不是普通 `*Data.do` JSON 接口。解析器为 `src/imes_report_client.py`，入口为 `sync_bf2_operation_log_report.py`，目标表为 `bf_imes.raw_rows`（数据集 `bf2_operation_log_report`）及自动生成宽表 `bf_imes.imes_bf2_operation_log_report`，查询视图为 `bf_imes.v_bf2_operation_log_report`。

220.12 已通过 Nginx `18084` 代理访问报表源站 `10.10.181.205:8080`：

```text
http://10.30.220.12:18084/demo/reportJsp/showInput.jsp?sht=mes/jn_ts_glbb_tb.sht
```

报表每行保留全部单元格原值和显示值；M 列燃料比按页面公式重算并标记 `metric_source=report_formula_recomputed`。D 列语义是“批数”，不能直接当作料速；`material_rate` 当前为空并带 `semantic_unconfirmed` 状态。220.12 计划任务 `IMESBF2OperationLogReport5m` 每 5 分钟读取当天报表并幂等更新，历史回填范围为 2026-02-09 至 2026-08-08。

## 点位范围

只同步 `config/点位清单.tsv` 和 `config/sync_config.json` 中列出的点位：

- 用户明确列出的普通变量。
- 炉体温度 `T_body_L7_A` 至 `T_body_L16_H` 80 个单点。
- `T_top` 为派生量，默认查询时由 `T_top_A-D` 平均计算，不重复入库。
- 不额外加入其它变量。

当前口径是 116 个逻辑变量、115 个物理采集点。

## PostgreSQL 初始化

默认目标：

```text
host=10.30.220.12 port=5432 database=bf_trend schema=bf_sensor
```

账号密码不写入仓库，运行前用环境变量注入：

```powershell
$env:GL02_PGHOST = "10.30.220.12"
$env:GL02_PGPORT = "5432"
$env:GL02_PGDATABASE = "bf_trend"
$env:GL02_PGUSER = "<postgres_user>"
$env:GL02_PGPASSWORD = "<postgres_password>"
```

初始化 PostgreSQL：

```powershell
python 数据库同步和存取\src\init_pg.py
```

如果 `bf_trend` 数据库尚未创建，可先由数据库管理员在维护库中执行 `schema/create_database_postgresql.sql`，再执行初始化脚本。

初始化会写入：

- 点位注册表 `bf_sensor.sensor_registry`
- 用户明确指令表 `bf_sensor.user_instructions`
- 每分钟一行按月分区表 `bf_sensor.one_minute_values`
- 同步状态表 `bf_sensor.sync_state`
- 同步运行记录表 `bf_sensor.sync_runs`
- 3 年保留清理函数 `bf_sensor.drop_1min_partitions_older_than`

## 同步历史数据

同步最近 90 天：

```powershell
python 数据库同步和存取\src\sync_from_243_pg.py --days 90 --chunk-hours 12 --batch-size 115 --max-workers 1 --source-mode processed
```

同步指定时间范围：

```powershell
python 数据库同步和存取\src\sync_from_243_pg.py --start-time 2026-02-09T00:00:00 --end-time 2026-05-09T00:00:00 --source-mode processed
```

## 持续实时增量

```powershell
python 数据库同步和存取\src\sync_from_243_pg.py --continuous --poll-seconds 30 --lookback-minutes 10 --source-mode raw --source-interval-seconds 5 --source-aggregate sample --target-aggregate PS_RAW_SAMPLE
```

历史回填和持续实时增量可以开两个进程并行运行。写入使用 `(tag_long_name, ts)` 幂等 upsert，重叠时间窗不会重复制造数据。`--source-mode raw --source-aggregate sample` 会先读取 pSpace `HisReadRaw` 约 5 秒原始样本，再为每分钟选择最后一个有效 raw 值写入 `bf_sensor.one_minute_values`；它不把 5 秒明细直接写入当前主表。

## 5s raw 明细批量入库

2026-05-14 已新增 5s raw 明细表 `bf_sensor.raw_5s_values`，用于短期保存 pSpace `HisReadRaw` 返回的原始样本，方便排查 1min 聚合缺口、核对现场 5s 更新和后续高频趋势。该表按天分区，默认保留 30 天，不替代长期诊断主表 `bf_sensor.one_minute_values`。

一次性批量读取最近 10 分钟 115 个物理点：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File 数据库同步和存取\run_raw_5s_sync_pg_once.ps1 `
  -Minutes 10 `
  -BatchSize 115 `
  -MaxWorkers 1
```

对应 Python 入口：

```powershell
python 数据库同步和存取\src\sync_raw_5s_from_243_pg.py --minutes 10 --batch-size 115 --max-workers 1
```

关键口径：

- `batch-size=115` 表示一次把 115 个物理点位长名作为数组传给 pSpace `HisReadRaw`，不是逐点位顺序读取。
- `max-workers=1` 表示只建 1 个 SDK 连接，降低 pSpace 客户端连接数压力。
- 如果 115 点一批在现场返回包过大或 SDK 报错，可临时降到 `-BatchSize 20` 或 `-BatchSize 50`，仍然是批量数组读取，只是拆成多个批次。
- 写库使用 `(tag_long_name, ts)` 幂等 upsert，重复读取同一时间窗不会产生重复 raw 行。

## 近实时延迟口径与修改路径

本模块的“实时”分两段看：

- `243 pSpace/数采 -> 220.12 PostgreSQL`：在 220.12 本机库 `bf_trend.bf_sensor.one_minute_values` 中看 `localtimestamp - max(ts)`。此前约 2.91 分钟延迟属于这一段。
- `220.12 PostgreSQL -> 本地 Docker PostgreSQL`：比较 220.12 与本地 `127.0.0.1:15432` 的 `one_minute_values.max(ts)`。这段只影响本地 8092/8767 页面可见时间，不代表 220.12 生产库没同步。

当前主表 `bf_sensor.one_minute_values` 每个测点每分钟最多一行，所以近实时目标是把 220.12 最新分钟稳定压到约 1-2 分钟内。若业务需要 5 秒级或秒级展示，应新增 `latest/raw/realtime` 表，走 `RealReadList` 或 `HisReadRaw` 5 秒明细链路；不要把 5 秒明细直接写入当前 1min 主表。

已验证成功的可执行修改路径：

- `run_realtime_sync_pg_bg.ps1`：默认保持 `PollSeconds=30`、`LookbackMinutes=10`、`BatchSize=115`、`SourceMode=raw`、`SourceAggregate=sample`，并传 `--target-aggregate PS_RAW_SAMPLE`；读取结束时间使用当前 `Get-Date`，不要再使用 `Get-Date.AddMinutes(-1)`。`BatchSize=115` 表示 115 个物理点同一时间窗整批传给 pSpace `HisReadRaw`，避免每批 4 点造成批次间分钟窗口漂移。
- `run_22012_continuous_sync.ps1`：持续同步入口必须传 `--source-mode raw --source-interval-seconds 5 --source-aggregate sample --target-aggregate PS_RAW_SAMPLE`。
- `config/sync_config.json`：运维默认值必须同步为 `continuous_poll_seconds=30`、`batch_size=115`、`max_workers=1`、`source_mode=raw`、`source_interval_seconds=5`、`source_aggregate=sample`、`target_aggregate=PS_RAW_SAMPLE`。
- `src/sync_from_243_pg.py`：同步日志必须能看到 `source_mode/source_aggregate/target_aggregate/tags_ok/tags_error`，用于确认当前轮次是否真的走 raw sample。
- `..\趋势分析\trend_backend\pspace_history.py`：`sample/last/latest/any` 表示每分钟选择最后一个有效 5 秒 raw 样本；`first/average/median` 只在明确需要时使用。
- `src/sync_watchdog.py`：实时进程识别只能认 `-File ...run_realtime_sync_pg_bg.ps1`，防止把 Watchdog 自身的 `powershell -Command` 查询进程误判成实时同步外壳。
- `..\自动诊断服务\zero_value_auditor.py`：零值审计必须读取本模块 `config/sync_config.json`，并按同一 raw sample 口径核验 0 值。
- `..\tools\start_local_pg_sync_loop.ps1` 与 `..\start_v3_full.ps1`：本地 Docker 镜像 220.12 的默认间隔保持 30 秒；如果 `127.0.0.1:15432` 不可达，先恢复本地 Docker PostgreSQL。

进一步压延迟的试验路径：可把 `run_realtime_sync_pg_bg.ps1` 的 `PollSeconds` 临时降到 10-15 秒，并把 `LookbackMinutes` 控制在 3-5 分钟；观察 243 pSpace 负载、最新 `sync_runs.tags_error` 和同步耗时后再决定是否固化。历史大窗口补漏不得抢占近实时同步，90 天小时级空洞只在显式启用历史回填时处理。

生产验收 SQL：

```sql
SELECT
  max(ts) AS max_ts,
  localtimestamp AS db_now,
  round(extract(epoch FROM (localtimestamp - max(ts)))::numeric / 60, 3) AS lag_min,
  count(DISTINCT tag_long_name) FILTER (
    WHERE ts >= (SELECT max(ts) - interval '10 minutes' FROM bf_sensor.one_minute_values)
  ) AS tags_latest_10m
FROM bf_sensor.one_minute_values;
```

合格信号：`lag_min` 稳定约 1-2，`tags_latest_10m=115`，最近 `bf_sensor.sync_runs.tags_error=0`，最新实时日志显示 `source_aggregate=sample`、`target_aggregate=PS_RAW_SAMPLE`、`--batch-size 115`。`Watchdog` 的 Windows 计划任务最近结果为 `0` 只代表脚本正常退出，不等于数据完整，仍要结合上述 SQL、`sync_runs` 和日志一起判断。若要确认逐分钟覆盖率，用 `GROUP BY ts` 统计最近 60 分钟每分钟 `count(distinct tag_long_name)`，不只看 10/60 分钟窗口内是否出现过 115 个点。

## 生产自动值守安装

项目根目录新增统一安装入口：

```powershell
powershell -ExecutionPolicy Bypass -File install_22012_autoguard.ps1
```

安装内容：

- 固定 `PYTHON_EXE` 为项目 `.venv\Scripts\python.exe`。
- 初始化 `bf_sensor` 传感器表和自动诊断表。
- 安装 `\GL02SensorSync\Watchdog`，每 5 分钟检查并修复 pSpace -> PostgreSQL 同步。
- 安装 `\GL02AutoDiagnosis\RunOnce`，每 5 分钟补齐基线、炉况诊断和最近 1 小时诊断队列。

首次上线推荐顺序：

```powershell
powershell -ExecutionPolicy Bypass -File install_22012_autoguard.ps1 -RunHistory90d
# 等 90 天传感器回填完成后：
powershell -ExecutionPolicy Bypass -File 自动诊断服务\run_initial_backfill_60d.ps1
```

如需同时配置外部只读直连，必须提供精确客户端 CIDR：

```powershell
$env:DB_CLIENT_CIDR="192.168.43.140/32"
powershell -ExecutionPolicy Bypass -File install_22012_autoguard.ps1 -InstallExternalReadOnly
```

只读账号默认为 `gl02_reader`，密码保存在 220.12 机器级环境变量 `GL02_READER_PASSWORD`。

## 查询历史数据

查询最近 8 小时：

```powershell
python 数据库同步和存取\src\query_history_pg.py --variables PI,T_top,GasUtil --hours 8
```

查询指定时间范围并导出 CSV：

```powershell
python 数据库同步和存取\src\query_history_pg.py --variables PI,DP_total,T_body_L7_A --start 2026-05-01T00:00:00 --end 2026-05-08T18:24:00 --format csv --out output.csv
```

## 3 年保留策略

`bf_sensor.one_minute_values` 按月分区。每次初始化或同步结束都会调用 3 年保留清理函数，删除早于 3 年保留窗口的整月分区。这样长期运行时空间增长会稳定在约 3 年窗口内。

## SQLite 回退演示

旧的 SQLite 演示脚本仍保留：

```powershell
python 数据库同步和存取\src\init_db.py
python 数据库同步和存取\src\sync_from_243.py --hours 1 --max-tags 3
python 数据库同步和存取\src\query_history.py --variables PI,T_top,GasUtil --hours 8
```

SQLite 只作为本机演示回退，不作为长期 3 年数据保留方案。

## 220.12 部署

当前已通过共享目录部署到：

```text
\\10.30.220.12\F$\高炉炼铁项目-real-sensor-v2_V3\数据库同步和存取
```

220.12 上可直接运行：

```powershell
powershell -ExecutionPolicy Bypass -File F:\高炉炼铁项目-real-sensor-v2_V3\数据库同步和存取\run_22012_init.ps1
powershell -ExecutionPolicy Bypass -File F:\高炉炼铁项目-real-sensor-v2_V3\数据库同步和存取\run_22012_history_sync_90d.ps1
powershell -ExecutionPolicy Bypass -File F:\高炉炼铁项目-real-sensor-v2_V3\数据库同步和存取\run_22012_continuous_sync.ps1
```

说明：PostgreSQL 版需要先确认 220.12 上的数据库实例、库名和账号可用。模型和页面优先读取 220.12 PostgreSQL，避免每次向 243 发起历史查询。

## 当前部署状态

2026-05-09 已在 220.12 使用官方 PostgreSQL 16 Windows 二进制包完成部署：

- PostgreSQL 根目录：`F:\PostgreSQL\16`
- 数据目录：`F:\PostgreSQL\16\data`
- 服务名：`postgresql-x64-16`
- 监听地址：`127.0.0.1:5432`
- 业务库：`bf_trend`
- 业务 schema：`bf_sensor`
- 业务用户：由机器级环境变量 `GL02_PGUSER` 指定
- 业务密码：由机器级环境变量 `GL02_PGPASSWORD` 指定

已创建并维护以下 Windows 计划任务：

- `\GL02SensorSync\History90d`：一次性回填 243 最近 90 天历史 1min 均值。
- `\GL02SensorSync\Watchdog`：每 5 分钟检查实时同步外壳、最新数据延迟和缺口，必要时重启同步并小窗口补漏。
- `\GL02AutoDiagnosis\RunOnce`：每 5 分钟执行自动值守单轮，补齐质量检查、30 天基线、5 分钟炉况诊断、短时队列和 LLM 摘要。
- `\GL02SensorSync\Realtime`：旧实时任务，当前应保持禁用，避免和 Watchdog 双重连续采集。

当前整批读取与频次策略：

- 历史回填：`batch-size=115`、`max-workers=1`。
- 实时同步：`poll-seconds=30`、`lookback-minutes=10`、`source-mode=raw`、`source-interval-seconds=5`、`source-aggregate=sample`、`target-aggregate=PS_RAW_SAMPLE`、`batch-size=115`、`max-workers=1`。
- Watchdog：`--stale-minutes 6`、单轮最多回补 3 段、最多 1 小时、锁陈旧阈值 30 分钟。

这样每轮只建立 1 个 SDK 连接，并把 115 个物理点作为同一个数组、同一读取窗口传给 pSpace，避免小批次轮询导致逐分钟覆盖稀疏。

说明：生产主表 `bf_sensor.one_minute_values` 仍只保存每分钟一行。实时 raw sample 模式是“读取 5 秒 raw -> 每分钟选择最后一个有效 sample -> 幂等写主表”，不是把 5 秒 raw 明细写入长表；若以后要保存 5 秒明细，仍应另建 raw/real-time 表。
