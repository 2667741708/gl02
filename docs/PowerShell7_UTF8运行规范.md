# PowerShell 7 UTF-8 运行规范

需求编号：`REQ-OPS-POWERSHELL7-UTF8-20260810`

## 结论

本机项目统一使用 PowerShell 7 Core，不再把 Windows PowerShell 5.1 作为项目运行时。2026-08-10 已通过 WinGet 安装最新稳定版 `7.6.4`，路径为 `C:\Program Files\PowerShell\7\pwsh.exe`。

Windows PowerShell 5.1 是 Windows 自带组件，PowerShell 7 使用独立路径和独立可执行文件并与其并存。因此这里的“撤掉 5.1”采用可验证且可恢复的工程口径：本项目入口、任务和新命令禁止调用 5.1；不删除 Windows 系统文件，不影响非本项目任务。

## 强制命令口径

项目根目录下执行脚本：

```powershell
pwsh.exe -NoLogo -NoProfile -File .\tools\verify_pwsh7_utf8.ps1
pwsh.exe -NoLogo -NoProfile -File .\start_v3_full.ps1
```

禁止新增：

```text
powershell.exe ...
C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe ...
```

禁止通过 `powershell -Command`、嵌套 `ScriptBlock` 或多层引号传输复杂脚本。复杂流程写入 `.ps1`，再使用一条短的 `pwsh.exe -File` 命令执行。

## UTF-8 入口模板

新增或修改的本机脚本在参数块后使用：

```powershell
$ErrorActionPreference = 'Stop'
if ($PSVersionTable.PSEdition -ne 'Core' -or $PSVersionTable.PSVersion.Major -lt 7) {
    throw '该脚本只允许 PowerShell 7 Core。'
}
$utf8NoBom = [Text.UTF8Encoding]::new($false)
[Console]::InputEncoding = $utf8NoBom
[Console]::OutputEncoding = $utf8NoBom
$OutputEncoding = $utf8NoBom
$PSDefaultParameterValues['*:Encoding'] = 'utf8'
```

文件路径含中文、空格或通配符字符时继续使用 `-LiteralPath`。

## 迁移边界

- 本机核心启动脚本 `start_v3_full.ps1` 已增加 PowerShell 7 版本门，并把子 PowerShell 改为 `pwsh.exe`。
- 本机隐藏任务包装 `tools/run_hidden_ps1.vbs` 已固定调用 `C:\Program Files\PowerShell\7\pwsh.exe`，找不到时返回退出码 `3`，不回退到 5.1。
- Windows Terminal默认配置由`tools/set_windows_terminal_pwsh7_default.ps1`切换为PowerShell 7；原Windows PowerShell配置仅隐藏，修改前配置保存同目录时间戳备份。
- 220.12 是独立主机。远端现有任务和守卫脚本仍有 Windows PowerShell 5.1 历史合同；必须先在 220.12 安装 PowerShell 7、逐项验证计划任务和服务后再迁移，不能用本机安装结果替代远端验收。
- 本机存在非本项目计划任务仍调用 5.1；本轮不修改其他项目的任务，避免跨项目破坏。

## 验证

```powershell
pwsh.exe -NoLogo -NoProfile -File .\tools\verify_pwsh7_utf8.ps1
pwsh.exe -NoLogo -NoProfile -File .\tools\set_windows_terminal_pwsh7_default.ps1
python -m pytest -q tests\test_pwsh7_runtime_contract.py
```

成功信号：

- `ok=true`；
- `ps_edition=Core`；
- `ps_version` 主版本不低于 7；
- 三个编码字段均为 `utf-8`；
- 中文临时文件写入、读取和清理无错误；
- 本机核心入口没有 `powershell.exe` 回退。

## 升级

后续升级稳定版：

```powershell
winget upgrade --id Microsoft.PowerShell --exact --source winget
pwsh.exe -NoLogo -NoProfile -File .\tools\verify_pwsh7_utf8.ps1
```

不得安装 Preview 包作为项目默认运行时。

## 220.12运行状态

- 操作系统：Windows Server 2016 Standard。
- PowerShell 7：`7.6.4 Core`，路径`C:\Program Files\PowerShell\7\pwsh.exe`。
- 安装来源：本机WinGet官方源下载的Microsoft签名MSI；服务器自身无WinGet。
- 远程命令：`tools/remote_22012_exec.py`默认将UTF-8脚本暂存后使用短`pwsh.exe -File`执行，不再默认使用5.1或`EncodedCommand`。
- 中文验证：`冀南钢铁：远端中文执行正常`及中文临时文件写入/读取均通过。
- 保护结果：8093、8094、8768、8770和5432安装前后均监听且PID不变；无重启要求。
- 计划任务：保持原Action不变，后续按任务单独迁移，禁止全量替换。
