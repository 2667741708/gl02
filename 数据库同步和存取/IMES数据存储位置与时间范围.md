# IMES 数据存储位置与时间范围

本文档记录 IMES 只读同步模块当前的读取范围、落库位置和代码位置。IMES 账号密码只允许放在服务器环境变量或本机私有 `.env.imes.local`，不要写入仓库文件。

## 当前有效时间范围

IMES 同步范围现在与 220.12 上已落库的 GL02 PostgreSQL 传感器数据范围对齐：

- 对齐来源：`bf_trend.bf_sensor.one_minute_values`
- 传感器库已确认下限：`2026-02-08 19:06:00`
- IMES 有效读取下限：`2026-02-08`
- IMES 有效读取上限：使用 `bf_sensor.one_minute_values` 当前最大 `ts` 所在日期

程序 `从IMES数据库同步.py` 每次运行都会查询 `bf_sensor.one_minute_values` 的 `MIN(ts)` 和 `MAX(ts)`：

- 请求日期早于传感器库下限时，跳过 IMES 读取。
- IMES 返回行的业务日期早于传感器库下限时，不写入 PostgreSQL。
- 源端 IMES 里确实存在更早的数据，例如部分接口可追溯到 2024 年，但本项目当前不再读取或写入这些更早数据。

说明：料仓维护等静态配置页面的 `createTimes/updateTimes` 只作为元数据，不作为业务历史日期；这类当前有效配置按同步日记录。

## IMES 可读清单

清单文件：

```text
数据库同步和存取\config\IMES可读数据清单.tsv
```

该 TSV 只记录 IMES 10 个页面发现到的只读表格接口，不包含 GL02 pSpace 传感器点位。字段包括页面、数据集、只读接口、PostgreSQL 宽表、源端已探测范围、当前有效读取范围和时间字段口径。

## PostgreSQL 存储位置

220.12 PostgreSQL：

```text
主机：10.30.220.12
实例监听：127.0.0.1:5432
数据库：bf_trend
IMES schema：bf_imes
传感器 schema：bf_sensor
```

IMES 主要表：

```text
bf_imes.dataset_catalog       数据集目录和字段清单
bf_imes.fetch_runs            每次 IMES 同步运行记录
bf_imes.raw_rows              统一 JSONB 明细表，按 dataset_key + row_key 幂等更新
bf_imes.imes_*                每个 IMES 接口对应的便捷宽表
bf_imes.v_bf2_batch_input_detail 批次投料详情统一视图
```

GL02 传感器主要表：

```text
bf_sensor.sensor_registry     115 个物理点和派生变量注册表
bf_sensor.one_minute_values   1min 均值，按月分区
bf_sensor.sync_state          pSpace 同步状态
bf_sensor.sync_runs           pSpace 同步运行记录
```

## 项目文件位置

本机工作目录：

```text
D:\文件\服务器实际运行版\数据库同步和存取
```

220.12 已同步的两个目录：

```text
F:\高炉炼铁项目-real-sensor-v2_V3\数据库同步和存取
F:\高炉炼铁项目-real-sensor-v2_8093\数据库同步和存取
```

IMES 同步核心文件：

```text
src\imes_readonly_client.py        IMES 登录、页面发现、只读分页读取、安全拦截
src\imes_pg_store.py               IMES PostgreSQL 落库
schema\postgresql_imes.sql         bf_imes schema
从IMES数据库同步.py                IMES 到 PostgreSQL 同步入口
run_22012_从IMES数据库同步.ps1     220.12 定时任务入口
config\IMES可读数据清单.tsv        IMES 可读页面/接口清单
```

GL02 传感器同步核心文件：

```text
config\点位清单.tsv                115 个物理点位和 T_top 派生变量清单
config\sync_config.json            PostgreSQL 和 pSpace 同步配置
src\sync_from_243_pg.py            从 243 pSpace 同步 1min 均值
src\query_history_pg.py            查询 PostgreSQL 历史传感器数据
schema\postgresql_required_points.sql bf_sensor schema
```

日志位置：

```text
F:\高炉炼铁项目-real-sensor-v2_V3\数据库同步和存取\logs\imes_sync_*.log
F:\高炉炼铁项目-real-sensor-v2_8093\数据库同步和存取\logs\imes_sync_*.log
```

## 定时任务

当前 220.12 上 IMES 定时同步任务：

```text
\GL02SensorSync\IMESRealtime
```

任务入口使用 V3 目录下的 `run_22012_从IMES数据库同步.ps1`，默认每次同步 `imes_10_pages`，即左侧 10 个 2#高炉页面动态发现到的只读表格接口。

## 手工查询示例

查看 IMES 总体落库范围：

```powershell
psql -d bf_trend -c "SELECT COUNT(*) rows_count, COUNT(DISTINCT dataset_key) datasets, MIN(workdate), MAX(workdate) FROM bf_imes.raw_rows;"
```

查看可读数据集目录：

```powershell
psql -d bf_trend -c "SELECT dataset_key, dataset_label, endpoint, table_name, updated_at FROM bf_imes.dataset_catalog ORDER BY dataset_key;"
```

查看 GL02 传感器库时间范围：

```powershell
psql -d bf_trend -c "SELECT COUNT(DISTINCT tag_long_name) tags, MIN(ts), MAX(ts) FROM bf_sensor.one_minute_values;"
```
