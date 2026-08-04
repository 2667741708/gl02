# 自动诊断服务程序索引

本目录是 V3 自动化炉况诊断流水线的后台中枢。所有程序都应支持 `--help`，先用 `--dry-run` 验证，再执行写库或修复动作。

## 环境变量

```powershell
$env:GL02_PGHOST="10.30.220.12"
$env:GL02_PGPORT="5432"
$env:GL02_PGDATABASE="bf_trend"
$env:GL02_PGUSER="..."
$env:GL02_PGPASSWORD="..."
```

## 已实现程序

### [diagnosis_scheduler.py](diagnosis_scheduler.py)

用途：基于 30 天基线和 60 分钟窗口执行炉况诊断，写入 `bf_sensor.diagnosis_snapshots`。

```powershell
python 自动诊断服务\diagnosis_scheduler.py --help
python 自动诊断服务\diagnosis_scheduler.py --once --dry-run
python 自动诊断服务\diagnosis_scheduler.py --start "2026-05-10 00:00" --end "2026-05-10 23:55"
python 自动诊断服务\diagnosis_scheduler.py --loop
```

### [data_quality_monitor.py](data_quality_monitor.py)

用途：检查最近 60 分钟、24 小时、30 天数据覆盖率和延迟。

```powershell
python 自动诊断服务\data_quality_monitor.py --help
python 自动诊断服务\data_quality_monitor.py
python 自动诊断服务\data_quality_monitor.py --write
```

### [backfill_missing.py](backfill_missing.py)

用途：根据质量检查结果生成缺口补漏任务。

```powershell
python 自动诊断服务\backfill_missing.py --help
python 自动诊断服务\backfill_missing.py
python 自动诊断服务\backfill_missing.py --write
```

### [pg_pspace_reconcile.py](pg_pspace_reconcile.py)

用途：低频对账本地 PostgreSQL 和 pSpace；普通诊断链路不调用。

```powershell
python 自动诊断服务\pg_pspace_reconcile.py --help
python 自动诊断服务\pg_pspace_reconcile.py --dry-run
```

### [run_service.py](run_service.py)

用途：统一运行自动化后台循环，串联质量检查、补漏任务、每日基线、5 分钟诊断、12 次队列、LLM 短时总结和 pipeline doctor。

```powershell
python 自动诊断服务\run_service.py --help
python 自动诊断服务\run_service.py --once --dry-run
python 自动诊断服务\run_service.py
```

### [auto_guard_once.py](auto_guard_once.py)

用途：生产计划任务入口。单次幂等运行，带锁，负责质量检查、缺口任务、每日基线、遗漏 5 分钟诊断补齐、最新 1 小时诊断队列维护。

```powershell
python 自动诊断服务\auto_guard_once.py --help
python 自动诊断服务\auto_guard_once.py --since-hours 24 --doctor
powershell -ExecutionPolicy Bypass -File 自动诊断服务\run_auto_diagnosis_once.ps1
powershell -ExecutionPolicy Bypass -File 自动诊断服务\install_auto_diagnosis_task.ps1
```

安装后计划任务为：

```text
\GL02AutoDiagnosis\RunOnce
```

### [initial_backfill_60d.py](initial_backfill_60d.py)

用途：在 90 天传感器数据回填完成后，一次性补齐最近 60 天每日 30 天历史基线和 5 分钟炉况诊断。

```powershell
python 自动诊断服务\initial_backfill_60d.py --days 60 --baseline-days 30
powershell -ExecutionPolicy Bypass -File 自动诊断服务\run_initial_backfill_60d.ps1
```

### [query_22012_history.py](query_22012_history.py)

用途：统一查询任意时间段传感器、炉况诊断、每日基线和数据质量结果，支持 JSON/CSV/XLSX。

```powershell
python 自动诊断服务\query_22012_history.py --start "2026-03-12 00:00" --end "2026-05-12 00:00" --include sensor,diagnosis,baseline --variables PI,DP_total,T_top --format xlsx --out report.xlsx
```

### [local_pg_ws_bridge.py](local_pg_ws_bridge.py)

用途：给前端提供本地 PostgreSQL WebSocket 数据流。

```powershell
$env:BF_WS_HOST="0.0.0.0"
$env:BF_WS_PORT="8767"
python 自动诊断服务\local_pg_ws_bridge.py
```

#### 软熔带 C2 根部实用估计（2026-07-19）

`local_pg_ws_bridge.py` 会在原有 `init/tick` 消息中追加
`bf3d_snapshot.v1`。其中 `estimated.cohesive_zone` 来自
[cohesive_zone_estimator.py](../炉况规则引擎/features/cohesive_zone_estimator.py)，
第一版只估计以下可观察状态：

- 炉墙侧软熔带根部上移、下移或稳定，以及 `m/h` 变化速度；
- 当前根部标高和未经校准的 15 分钟常速外推；
- 软熔带厚度；
- A～H 相对方位的偏心量、偏心角和八扇区根部高度。

输入使用 L7～L13 共 56 个炉体温度点、压差/透气性、三高度×A～F
静压力以及鼓风热状态辅助量。适配器严格限制 `ts <= knowledge_time`，
不使用未来样本回填。输入不足、陈旧、估计器异常或数据库不可用时，
`estimated.cohesive_zone` 为 `null`，不会生成看似合理的假几何，也不会
中断原有 8767 数据流。

该输出固定为：

```text
evidence=estimated
calibration_status=uncalibrated
control_use=prohibited
confidence<=0.45
root_definition=wall_thermal_activity_centroid
absolute_azimuth_status=unconfirmed
```

因此它是面向研判和 3D 可视化的低置信度状态估计，不是现场软熔带
实测值，也不得用于自动控制。正式提高置信度前，必须取得垂直探针、
TDR、停炉解剖或经核准物理模型等标定真值。

可配置项：

```text
BF_WS_COHESIVE_ZONE_ENABLED=1
BF_WS_COHESIVE_ZONE_HISTORY_MINUTES=480
BF_WS_COHESIVE_ZONE_COMPUTE_INTERVAL_SECONDS=60
BF_WS_COHESIVE_ZONE_STALE_AFTER_SECONDS=600
BF_WS_COHESIVE_ZONE_CONFIG_PATH=<可选 YAML 路径>
```

验证：

```powershell
python -m pytest tests/test_cohesive_zone_estimator.py tests/test_local_pg_ws_bridge_cohesive_zone.py -q
python tools/check_v3_ws_bridge_python.py --require-bf3d-snapshot
# 只有现场输入完整且模型可用时才增加：
python tools/check_v3_ws_bridge_python.py --require-bf3d-snapshot --require-cohesive-zone
```

## 自动化扩展程序

这些程序已经补齐业务逻辑，可直接通过 `--help` 查看参数。生产写库前建议先执行 `--dry-run`。

### [pspace_sync_watchdog.py](pspace_sync_watchdog.py)

```powershell
python 自动诊断服务\pspace_sync_watchdog.py --help
python 自动诊断服务\pspace_sync_watchdog.py --check --points 115 --minutes 60
python 自动诊断服务\pspace_sync_watchdog.py --reconcile --start "2026-05-10 00:00" --end "2026-05-10 06:00" --dry-run
```

### [baseline_maintainer.py](baseline_maintainer.py)

```powershell
python 自动诊断服务\baseline_maintainer.py --help
python 自动诊断服务\baseline_maintainer.py --build-day 2026-05-10 --baseline-days 30 --write
python 自动诊断服务\baseline_maintainer.py --query --day 2026-05-10 --variable PI
```

### [diagnosis_queue_service.py](diagnosis_queue_service.py)

```powershell
python 自动诊断服务\diagnosis_queue_service.py --help
python 自动诊断服务\diagnosis_queue_service.py --build-current --write
python 自动诊断服务\diagnosis_queue_service.py --query --queue-id dq_20260510_185000
```

### [llm_short_window_summarizer.py](llm_short_window_summarizer.py)

```powershell
python 自动诊断服务\llm_short_window_summarizer.py --help
python 自动诊断服务\llm_short_window_summarizer.py --latest --dry-run
python 自动诊断服务\llm_short_window_summarizer.py --queue-id dq_20260510_185000 --write --export-docx
```

### [conversation_delta_context.py](conversation_delta_context.py)

```powershell
python 自动诊断服务\conversation_delta_context.py --help
python 自动诊断服务\conversation_delta_context.py --conversation-id swc_001 --message-time "2026-05-10 19:03:00"
```

### [pipeline_doctor.py](pipeline_doctor.py)

```powershell
python 自动诊断服务\pipeline_doctor.py --help
python 自动诊断服务\pipeline_doctor.py --check-all
python 自动诊断服务\pipeline_doctor.py --check-all --repair --dry-run
```
