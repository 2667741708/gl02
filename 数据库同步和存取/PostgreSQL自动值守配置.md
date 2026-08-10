# 220.12 PostgreSQL 自动值守落地方案

## Summary

- 以 `10.30.220.12:5432 / bf_trend / bf_sensor` 为生产主库，243 pSpace 只作为只读数据源。
- 首次补齐：243 -> 220.12 PostgreSQL 回填 90 天 1min 数据；再回填最近 60 天每日 30 天 rolling 基线和 5 分钟炉况诊断。
- 常驻运行：每 5 分钟自动同步、质量检查、补漏、炉况诊断、队列维护；每天自动计算当天历史基线。
- 外部访问：开放 PostgreSQL 直连端口，只允许指定客户端 IP/CIDR 使用只读账号访问。

## Key Changes

- 统一运行环境：固定使用项目 `.venv\Scripts\python.exe`，补齐 `pandas/numpy/PyYAML/psycopg/requests/websockets/openpyxl/python-docx` 等依赖，所有计划任务显式读取机器级环境变量。
- PostgreSQL 服务收口：把当前 5432 监听进程纳入 `postgresql-x64-16` Windows 服务管理，设为自动启动；写入并验证 `bf_sensor` 传感器表、诊断表、基线表、队列表。
- pSpace 同步常驻：安装 `\GL02SensorSync\Watchdog`，每 5 分钟检查同步进程、最近数据延迟、90 天窗口缺口；发现断档自动重启实时同步并小块回填。
- 自动诊断常驻：新增/调整一个幂等的 `run_auto_diagnosis_once.ps1`，由 `\GL02AutoDiagnosis\RunOnce` 每 5 分钟运行一次；每次补齐遗漏诊断点，保证停机后可追赶。
- 查询脚本：新增统一脚本 `query_22012_history.py`，支持按任意 `--start/--end` 查询传感器、炉况诊断、每日基线、质量状态，输出 `json/csv/xlsx`。
- 外部只读访问：创建 `gl02_reader`，仅授予 `bf_trend.bf_sensor` 的 `SELECT`；`pg_hba.conf` 和 Windows 防火墙只允许 `DB_CLIENT_CIDR=<你的客户端IP>/32` 访问 5432。

## Interfaces

- 核心环境变量：`GL02_PGHOST=127.0.0.1`、`GL02_PGPORT=5432`、`GL02_PGDATABASE=bf_trend`、`GL02_PGUSER=gl02_sync`、`GL02_PGPASSWORD`、`PSPACE_SERVER=10.22.181.243`、`PSPACE_PORT=8889`。
- 外部连接示例：`psql -h 10.30.220.12 -p 5432 -U gl02_reader -d bf_trend`。
- 查询示例：`python auto_diagnosis_service\query_22012_history.py --start "2026-03-12 00:00" --end "2026-05-12 00:00" --include sensor,diagnosis,baseline --variables PI,DP_total,T_top --format xlsx --out report.xlsx`。

## Test Plan

- 依赖验收：`.venv` 中能导入全部运行依赖，计划任务均使用同一个 Python。
- 数据同步验收：`sensor_registry` 物理点位为 115；`one_minute_values` 覆盖最近 90 天；最新数据延迟小于 10 分钟。
- 基线验收：最近 60 天每天都有 `daily_baselines`，每条记录带 `baseline_window_start/end`、样本数和覆盖率。
- 炉况验收：最近 60 天每 5 分钟一条 `diagnosis_snapshots`，断点数为 0；低覆盖窗口写入 `data_quality_low`，不误判正常。
- 外部访问验收：本机只读账号可查 `bf_sensor` 任意表；写入、删除、访问其他库均失败。
- 自愈验收：手动停止实时同步后，Watchdog 能在下一轮重启；缺口会进入回填流程并入库记录。

## Assumptions

- 生产诊断频率按你选择的现有口径保留为每 5 分钟一次。
- 首次只保证最近 60 天炉况和基线可任意查询；原始传感器保留 90 天作为前置窗口，后续按 3 年分区保留策略持续增长。
- 243 pSpace 只读，不修改 243/244 配置、服务或生产数据。
- 外部数据库端口不做全网开放；实施时必须提供 `DB_CLIENT_CIDR`，否则安装脚本拒绝放行 5432。
