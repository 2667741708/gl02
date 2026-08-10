[CmdletBinding()]
param(
    [switch]$SkipPolicyCheck
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$utf8NoBom = [System.Text.UTF8Encoding]::new($false)
[Console]::InputEncoding = $utf8NoBom
[Console]::OutputEncoding = $utf8NoBom
$OutputEncoding = $utf8NoBom
$PSDefaultParameterValues['*:Encoding'] = 'utf8'

$failures = [System.Collections.Generic.List[string]]::new()

if ($PSVersionTable.PSEdition -ne 'Core') {
    $failures.Add("PSEdition=$($PSVersionTable.PSEdition)，必须使用 PowerShell 7 Core。")
}
if ($PSVersionTable.PSVersion.Major -lt 7) {
    $failures.Add("PSVersion=$($PSVersionTable.PSVersion)，必须为 7.x 或更高版本。")
}
if ([System.Environment]::ProcessPath -notlike '*\pwsh.exe') {
    $failures.Add("当前进程不是 pwsh.exe：$([System.Environment]::ProcessPath)")
}

$projectRoot = Split-Path -Parent $PSScriptRoot
$agentsPath = Join-Path $projectRoot 'AGENTS.md'
if (-not (Test-Path -LiteralPath $agentsPath -PathType Leaf)) {
    $failures.Add("中文项目路径下缺少 AGENTS.md：$agentsPath")
}
elseif (-not $SkipPolicyCheck) {
    $agentsText = Get-Content -LiteralPath $agentsPath -Raw -Encoding utf8
    if ($agentsText -notmatch 'PowerShell 7 UTF-8 强制运行时') {
        $failures.Add('AGENTS.md 缺少 PowerShell 7 UTF-8 强制运行时约束。')
    }
}

$parsedScripts = @(
    (Join-Path $projectRoot 'start_v3_full.ps1'),
    (Join-Path $projectRoot 'tools\verify_pwsh7_utf8.ps1'),
    (Join-Path $projectRoot 'tools\set_windows_terminal_pwsh7_default.ps1'),
    (Join-Path $projectRoot 'tools\remote_probe_22012_pwsh7.ps1'),
    (Join-Path $projectRoot 'tools\remote_install_22012_pwsh7.ps1'),
    (Join-Path $projectRoot 'tools\remote_verify_22012_pwsh7.ps1'),
    (Join-Path $projectRoot 'tools\remote_smoke_22012_pwsh7.ps1'),
    (Join-Path $projectRoot 'tools\remote_cleanup_22012_pwsh7_installer.ps1'),
    (Join-Path $projectRoot 'tools\deploy_si_v20_strict_hourly_22012.ps1'),
    (Join-Path $projectRoot 'tools\remote_guarded_deploy_si_v20_strict_hourly.ps1'),
    (Join-Path $projectRoot 'tools\register_22012_si_v20_strict_hourly_task.ps1'),
    (Join-Path $projectRoot 'tools\run_22012_si_v20_strict_hourly.ps1'),
    (Join-Path $projectRoot 'tools\restart_22012_8094_preview.ps1')
)
foreach ($scriptPath in $parsedScripts) {
    $tokens = $null
    $parseErrors = $null
    [void][System.Management.Automation.Language.Parser]::ParseFile(
        $scriptPath,
        [ref]$tokens,
        [ref]$parseErrors
    )
    if ($parseErrors.Count -ne 0) {
        $failures.Add("PowerShell 7语法检查失败：$scriptPath；$($parseErrors[0].Message)")
    }
}

$probePath = Join-Path ([System.IO.Path]::GetTempPath()) '冀南钢铁_pwsh7_utf8_probe.txt'
$probeText = '冀南钢铁 PowerShell 7 UTF-8 验证：硅含量预测'
try {
    [System.IO.File]::WriteAllText($probePath, $probeText, $utf8NoBom)
    $roundTrip = [System.IO.File]::ReadAllText($probePath, [System.Text.Encoding]::UTF8)
    if ($roundTrip -cne $probeText) {
        $failures.Add('UTF-8 中文写入/读取回环不一致。')
    }
}
finally {
    if (Test-Path -LiteralPath $probePath) {
        Remove-Item -LiteralPath $probePath -Force
    }
}

$result = [ordered]@{
    schema = 'bf.pwsh7.utf8.runtime-check.v1'
    ok = ($failures.Count -eq 0)
    executable = [System.Environment]::ProcessPath
    ps_version = $PSVersionTable.PSVersion.ToString()
    ps_edition = $PSVersionTable.PSEdition
    console_input_encoding = [Console]::InputEncoding.WebName
    console_output_encoding = [Console]::OutputEncoding.WebName
    output_encoding = $OutputEncoding.WebName
    project_root = $projectRoot
    parsed_scripts = $parsedScripts
    failures = @($failures)
}

$result | ConvertTo-Json -Depth 4
if ($failures.Count -ne 0) {
    exit 2
}
