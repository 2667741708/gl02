# 220.12 项目运行时 PowerShell 7.6.4 完整迁移交接

日期：2026-08-11

## 结果

220.12 上纳入项目范围的 PowerShell 任务、NSSM 服务和运行进程已统一到 `C:\Program Files\PowerShell\7\pwsh.exe`（PowerShell 7.6.4 Core）。最终只读审计结果：

- 计划任务：`AlreadyPwsh7=54`，`LegacyPS5=0`。
- NSSM 服务：`AlreadyPwsh7=7`，`LegacyPS5=0`。
- 运行进程：`AlreadyPwsh7=17`，`LegacyPS5=0`。
- 不使用 PowerShell 包装层的项目任务为 4 个，保持原实现，不计入 5.1 遗留。
- 8093、8094、8095 最终 HTTP 状态均为 200。

最终审计证据为 `logs/pwsh7_runtime_audit_22012_final.json`，远端审计 SHA-256 为 `8422B603EBF1329B68D21E04BD91FD6D675DE06EB2D3453DD4F7441C995335C8`。

## 已迁移运行链

- 自动诊断、同步 watchdog、V4 8094、8095 和 PostgreSQL 实时同步计划任务。
- `BFV4PreviewWs8768`、`BFOllama11434`、`BFChronos8777`、`BFV3AutoPreviewWs8767`、`BFBaselineProxy8096` 及其健康任务。
- 41 个休眠/Ready/Disabled 项目任务定义及漏检补迁的 `\BlastFurnaceV3Pspace8768`；这些任务只替换 Action，没有启动。
- 已禁用的 `BFBaselineProxy8092` 只迁移 NSSM Application，没有启动。
- 6 个 2026 年 5 月遗留、无监听的只读 PowerShell 5.1 日志查询进程已受控停止并保存证据。

8094 已按用户授权受控重启，监听 PID 从 18628 切换为 17432，HTTP 200；8093、8768、8770 等受保护端口在该重启步骤中保持不变。8095 迁移后监听 PID 为 10656，HTTP 200。

## 备份与回滚证据

远端备份根目录：

`F:\高炉炼铁项目-real-sensor-v2_V4_8093_PREVIEW\logs\deploy_backups\pwsh7_all_active`

关键批次：

- `20260811_173932-tasks`
- `20260811_174031-services`
- `20260811_175501-realtime-sync`
- `20260811_180745-8095`
- `20260811_180844-stale-log-query-archive`
- `20260811_181341-residual-definitions`
- `20260811_181653-residual-definitions`

计划任务迁移前 XML、NSSM 注册表值、运行源码和监听快照均保存在相应批次目录。两次 8095 初始切换未通过子进程身份验收时均已自动回滚，最终修订后才切换成功。

## 远端不可变工具包

安装路径：

`F:\高炉炼铁项目-real-sensor-v2_V4_8093_PREVIEW\tools\pwsh7_migration\2026.08.11-pwsh7.6.4`

工具包包含 24 个迁移、审计、探针、安装/清理工具及实际运行源码快照。`runtime_sources` 仅用于追踪和恢复，生产服务继续从正式目录运行。工具包 `manifest.json` SHA-256：

`9F867FD015DC43501C55E957301F60B7EABE3861D40EE1FE2DB907C0AAB76A2C`

本机镜像证据为 `logs/pwsh7_migration_toolkit_20260811_manifest.json`。安装时 11 个受保护端口 PID 前后完全一致，预暂存目录安装后已删除。

## SSH 复用与耗时观察

最终阶段复用同一会话 `f4670484e71541419b9febe651ac2cfb` 和连接 `c3ce13fb7baa47f0b69bcfcb5cde8105`，`reconnect_count=0`。普通远端 HTTP 命令的实际执行约 0.60–0.65 秒；部分请求出现 3–36 秒 broker lock wait，说明当前主要额外耗时来自同一 broker 内的请求排队，而不是 SSH 重新认证。

服务迁移曾因健康任务 `LastRunTime` 与毫秒墙钟比较而每项等待下一分钟，约增加 300 秒。后续应改为比较迁移前捕获的 `LastRunTime` 基线，确认其递增即可，避免固定等待分钟边界。

## 本地验证

```powershell
pwsh.exe -NoLogo -NoProfile -File .\tools\verify_22012_active_pwsh7_migration.ps1
```

结果为 PowerShell 7.6.4 Core、所有受控 `.ps1` UTF-8 无 BOM、PowerShell 解析错误为 0。
