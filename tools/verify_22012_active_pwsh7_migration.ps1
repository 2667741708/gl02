[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
if ($PSVersionTable.PSEdition -ne 'Core' -or $PSVersionTable.PSVersion.ToString() -ne '7.6.4') {
    throw 'Verification requires PowerShell 7.6.4 Core.'
}
$Utf8NoBom = [Text.UTF8Encoding]::new($false)
[Console]::InputEncoding = $Utf8NoBom
[Console]::OutputEncoding = $Utf8NoBom
$OutputEncoding = $Utf8NoBom
$PSDefaultParameterValues['*:Encoding'] = 'utf8'

$ProjectRoot = Split-Path -Parent $PSScriptRoot
$Files = @(
    'tools\remote_audit_22012_project_powershell_runtime.ps1',
    'tools\remote_migrate_22012_active_tasks_pwsh7.ps1',
    'tools\remote_migrate_22012_active_services_pwsh7.ps1',
    'tools\remote_migrate_22012_realtime_sync_pwsh7.ps1',
    'tools\remote_archive_22012_stale_legacy_powershell.ps1',
    'tools\remote_migrate_22012_8095_preview_pwsh7.ps1',
    'tools\remote_migrate_22012_residual_definitions_pwsh7.ps1',
    'tools\remote_install_22012_pwsh7_migration_toolkit.ps1',
    'tools\run_22012_8094_preview.ps1',
    'tools\run_22012_8095_preview.ps1',
    '自动诊断服务\run_auto_diagnosis_once.ps1',
    '数据库同步和存取\run_sync_watchdog.ps1',
    '数据库同步和存取\run_realtime_sync_pg_bg.ps1'
)
$Failures = [Collections.Generic.List[string]]::new()
$Records = [Collections.Generic.List[object]]::new()

foreach ($relative in $Files) {
    $path = Join-Path $ProjectRoot $relative
    if (-not (Test-Path -LiteralPath $path -PathType Leaf)) {
        $Failures.Add("missing=$relative")
        continue
    }
    $bytes = [IO.File]::ReadAllBytes($path)
    $hasBom = $bytes.Length -ge 3 -and $bytes[0] -eq 0xEF -and $bytes[1] -eq 0xBB -and $bytes[2] -eq 0xBF
    $tokens = $null
    $errors = $null
    [void][Management.Automation.Language.Parser]::ParseFile($path, [ref]$tokens, [ref]$errors)
    if ($hasBom) { $Failures.Add("utf8_bom=$relative") }
    if ($errors.Count -ne 0) { $Failures.Add("parse=${relative}:$($errors[0].Message)") }
    $Records.Add([ordered]@{
        path = $relative
        sha256 = (Get-FileHash -LiteralPath $path -Algorithm SHA256).Hash
        utf8_bom = $hasBom
        parse_errors = $errors.Count
    })
}

[ordered]@{
    schema = 'ops.22012.active-pwsh7-migration.local-verification.v1'
    ok = $Failures.Count -eq 0
    ps_edition = $PSVersionTable.PSEdition
    ps_version = $PSVersionTable.PSVersion.ToString()
    files = @($Records)
    failures = @($Failures)
} | ConvertTo-Json -Depth 6

if ($Failures.Count -ne 0) { exit 2 }
