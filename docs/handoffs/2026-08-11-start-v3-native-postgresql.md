# start_v3_full 原生 PostgreSQL 同步交接（2026-08-11）

追踪编号：`REQ-OPS-LOCAL-NATIVE-POSTGRES-START-20260811`

## 目标

将本机主启动入口从历史 Docker PostgreSQL `15432` 默认值收敛到本机原生
PostgreSQL 16，同时保持助手、前端、诊断、实时桥接、同步循环、端口和进程管理逻辑不变。

## 实现

- [start_v3_full.ps1](../../start_v3_full.ps1) 默认建立
  `local-native -> 127.0.0.1:18000/bf_trend` 主连接。
- 本机非敏感默认值使用 `GL02_LOCAL_PGHOST/PORT/DATABASE/USER`；密码只读取
  `GL02_LOCAL_PGPASSWORD`，脚本内不保存密码。
- 默认模式把 `GL02_LOCAL_PG*` 复制给 `GL02_PG*`，从而覆盖当前用户级环境中可能指向
  220.12 的主连接，避免远端只读账号污染本机启动。
- `BF_USE_EXISTING_PG_ENV=1/true/yes` 仍是显式兼容开关；只影响助手、诊断和实时桥接的
  主连接，本地同步目标继续使用 `GL02_LOCAL_PG*`。
- 缺少相应凭据时，正常启动立即失败；dry-run 跳过依赖数据库的组件并警告。
- 未改 `tools/start_local_pg_sync_loop.ps1`；父启动器通过继承环境覆盖其旧默认值，满足本次
  “尽量保持其他程序一致”的范围要求。

## 保持不变

- 助手端口 `8092`、前端端口 `8093`、WebSocket 端口 `8767` 和同步间隔 `30s`。
- `-Restart`、全部 `-Skip*` 参数及精确 PID/端口归属逻辑。
- Ollama、模型、前端资源、诊断规则、数据库 schema 和生产/远端服务。
- 未启动任何本机业务服务，未连接或修改 220.12，未执行数据库写入。

## 现场只读探测

- Windows 服务 `postgresql-x64-16=Running`、启动类型 `Automatic`。
- `127.0.0.1:18000` 正在监听。
- 当前用户级 `GL02_PGHOST/PORT` 指向 220.12；主启动 dry-run 已证明默认模式将其覆盖为
  `127.0.0.1:18000/bf_trend`。
- 当前进程未设置 `GL02_LOCAL_PGPASSWORD`，因此未做本机 SQL 登录验证，也未实际启动依赖
  数据库的服务。密码仍从受控配置人工注入，不能复制到本交接或脚本。

## 验证

```powershell
python -B -m pytest -q .\tests\test_pwsh7_runtime_contract.py
pwsh.exe -NoLogo -NoProfile -File .\tools\verify_pwsh7_utf8.ps1
pwsh.exe -NoLogo -NoProfile -File .\start_v3_full.ps1 -DryRun `
  -SkipAssistant -SkipFrontend -SkipDiagnosis -SkipRealtimeBridge -SkipLocalSyncLoop
```

结果：

- `5 passed`。
- PowerShell 运行时验证 `ok=true`、`PSEdition=Core`、`ps_version=7.6.4`、三项编码均为
  `utf-8`，`start_v3_full.ps1` 语法解析通过。
- dry-run 输出：`mode=local-native target=127.0.0.1:18000/bf_trend user=postgres`，
  两个密码状态均为 `False`，未输出密码值。
- 脚本中不存在 `15432`、`gl02_sync` 或 `gl02_local_sync`。

## 实际启动前

```powershell
$env:GL02_LOCAL_PGUSER = 'postgres'
$env:GL02_LOCAL_PGPASSWORD = '<从受控配置输入>'
pwsh.exe -NoLogo -NoProfile -File .\start_v3_full.ps1
```

启动前还应使用本机受控凭据执行 `SELECT current_user, current_database(), version()`，并确认
所需 schema 已迁移到原生实例；本轮没有把“服务监听”冒充成“业务库登录与 schema 验收”。
