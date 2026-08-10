# 8093 炉次生产实绩与铁水质量交接记录

追踪编号：`REQ-8093-HEAT-PERFORMANCE-QUALITY-20260806`

## 目标与数据口径

- PostgreSQL新增 `bf_assistant.heat_performance_quality_summary`，正式 `meltno` 一炉一行。
- IMES原始炉次、称量和铁水试样仍为权威源；聚合表不覆盖原始化验。
- 每炉保存生产实绩、矿批/称量证据、C/Si/Mn/P/S算术平均值、Si中位数/最小/最大/极差、样本数和原始试样JSON。
- `quality_summary`只描述数据完整性、Si 0.20%–0.40%目标带及实际样本范围，不代表正式质量合格判定。
- 首次全量回填，之后每5分钟回看最近3天并按 `meltno` 幂等更新。

## 本机实现与验证

- 本机工作区是唯一发布源；远端部署不得反向覆盖本机文件。
- `py_compile`通过。
- `node --check 高炉前端数据/assets/bf-heat-performance-quality-8093.js`通过。
- 专项、MES炉次和跨源MCP回归合计66项通过。
- 生产部署器：[remote_guarded_deploy_8093_heat_performance_quality.ps1](../../tools/remote_guarded_deploy_8093_heat_performance_quality.ps1)。

## 生产状态

2026-08-06 14:42 已完成受控上线：

- 首次全量扫描同步 `9622` 炉，时间范围为 `2024-08-05 14:51:00` 至 `2026-08-06 10:15:00`；随后最近3天增量刷新 `43` 炉，使用 `meltno` 幂等 upsert。
- 全量第40批出现两次 PostgreSQL `ConnectionTimeout`，新增仅针对 `OperationalError` 的5次有限重试（1/2/4/8秒退避）后恢复并完成全量。
- 新建计划任务 `\BlastFurnaceServices\HeatPerformanceQualitySync`，每5分钟回看最近3天；部署结束时任务状态为 `Running`。
- 仅 `BFV4PreviewProxy8093` 被受控重启：PID `16864 -> 12752`；8093守护暂停并恢复成功。
- 受保护端口在成功部署前后保持不变：8768 `5988 -> 5988`、8094 `13608 -> 13608`、8770 `6848 -> 6848`。
- 备份目录：`F:\高炉炼铁项目-real-sensor-v2_V4_8093_PREVIEW\logs\deploy_backups\8093_heat_performance_20260806_143906`。
- 220.12本机页面 HTTP `200`；`/api/heat-performance-quality?limit=1` 返回 `ok=true`、`read_only=true`。
- 最新事实为 `2#20260806-082`：实绩铁量 `488.95 t`、3个铁水试样、Si `0.30%/0.24%/0.43%`，表内算术平均值 `0.32333%`，与独立复算一致；C/Mn/P/S平均值分别为 `4.84333%/0.26333%/0.16267%/0.019%`。
- 浏览器从本机经VPN访问 `10.30.220.12:8093` 时出现 `ERR_EMPTY_RESPONSE`；同一时段220.12服务器本机页面与API均正常。该项记录为VPN外部链路复验未通过，不影响服务器内部上线结论，但不能表述为跨VPN浏览器验收完成。

实施中修复了两个真实API缺陷：psycopg `dict_row` 被错误使用数字下标导致 `KeyError(0)`，以及 `date.isoformat()` 被传入 `sep` 参数。两项均新增回归测试；数据库数值统一转换为JSON number。

当前本机发布文件SHA-256：

| 文件 | SHA-256 |
|---|---|
| `ollama_proxy_server.py` | `8F7F17B3CBC9B3F481714488BAC6A991A384F67D67974082FF153879D342AFF5` |
| `heat_performance_quality.py` | `DE481F17731F1FCAED5C0DC28AC087705C7B92716A82E09ABD0246154D1CC0EB` |
| `frontend_dashboard_v3.server.html` | `2A1E34BA326FCA2AABCC7F55231B0DD0ECD13654684132481BBB22A747BF40CC` |
| `bf-heat-performance-quality-8093.js` | `9ACC31494E3D79A50EF251B999BBBB5F674E1E0186F55E223E58E7C1D221A7A3` |
| `sync_22012_heat_performance_quality.py` | `BEF01456E57877A4842FB28C316D67C1C7E463A688F982192791D8431B6A48CB` |
| `run_22012_heat_performance_sync.ps1` | `970DAE922E75379E1F978DF6BC286F01F251A297A6BBB7F6C696D7168CA932A8` |
