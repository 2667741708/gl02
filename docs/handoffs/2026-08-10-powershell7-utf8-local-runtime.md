# 2026-08-10 本机 PowerShell 7 UTF-8 运行时交接

## 需求

`REQ-OPS-POWERSHELL7-UTF8-20260810`：本机项目不再使用Windows PowerShell 5.1作为运行时，统一使用最新稳定版PowerShell 7并保证中文/UTF-8稳定。

## 已完成

- WinGet安装`Microsoft.PowerShell 7.6.4.0`，实际程序为`C:\Program Files\PowerShell\7\pwsh.exe`。
- AGENTS增加PowerShell 7强制规则、UTF-8模板、禁止回退和远端迁移边界。
- `start_v3_full.ps1`拒绝5.1并使用`pwsh.exe`启动子脚本。
- `tools/run_hidden_ps1.vbs`固定调用PowerShell 7，找不到时退出3。
- Windows Terminal默认配置切换到PowerShell 7；Windows PowerShell配置隐藏但不删除。修改前备份位于Terminal LocalState目录，文件名为`settings.before-pwsh7.20260810_020907.json`。
- 新增真实UTF-8运行时验证器和静态合同测试。

## 验证证据

```powershell
pwsh.exe -NoLogo -NoProfile -File .\tools\verify_pwsh7_utf8.ps1
```

结果：`ok=true`、`ps_version=7.6.4`、`ps_edition=Core`，Console输入、输出和管道输出均为`utf-8`，中文项目路径与中文临时文件回环通过。

```powershell
python -B -m pytest -q tests\test_pwsh7_runtime_contract.py
```

结果：`4 passed`。

## 边界与待办

- 没有删除`C:\Windows\System32\WindowsPowerShell`。微软把5.1定义为Windows自带产品并让7与之并存，删除系统文件会破坏Windows或依赖模块。
- 本机非本项目任务仍可能显式调用5.1，本轮没有越权修改其他项目。
- 220.12现有守卫、计划任务和远端脚本仍有5.1历史合同；后续若要求远端也只使用7，必须在220.12单独安装、迁移、重启和逐任务验收。
