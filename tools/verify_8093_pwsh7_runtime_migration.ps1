[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
if ($PSVersionTable.PSEdition -ne 'Core' -or $PSVersionTable.PSVersion.Major -lt 7) {
    throw 'This verifier requires PowerShell 7 Core or later.'
}
$Utf8NoBom = [Text.UTF8Encoding]::new($false)
[Console]::InputEncoding = $Utf8NoBom
[Console]::OutputEncoding = $Utf8NoBom
$OutputEncoding = $Utf8NoBom
$PSDefaultParameterValues['*:Encoding'] = 'utf8'

$Root = Split-Path -Parent $PSScriptRoot
$Scripts = @(
    (Join-Path $Root 'tools\run_managed_nssm_process.ps1'),
    (Join-Path $Root 'tools\check_managed_nssm_service_health.ps1'),
    (Join-Path $Root 'tools\run_v4_daily_baseline.ps1'),
    (Join-Path $Root 'tools\probe_eventlog_service.ps1'),
    (Join-Path $Root 'tools\remote_probe_8093_pwsh7_runtime_migration.ps1'),
    (Join-Path $Root 'tools\remote_migrate_8093_runtime_to_pwsh7.ps1'),
    (Join-Path $Root 'tools\remote_guarded_deploy_8093_remove_throat_restore_query.ps1'),
    (Join-Path $Root 'tools\remote_probe_22012_ollama_api.ps1'),
    (Join-Path $Root 'tools\remote_probe_22012_ollama_chat.ps1'),
    (Join-Path $Root 'tools\remote_probe_22012_autoguard_runtime.ps1'),
    (Join-Path $Root 'tools\remote_deploy_22012_autoguard_llm_fallback.ps1'),
    (Join-Path $Root 'tools\remote_cleanup_8093_dashboard_build_assets.ps1'),
    (Join-Path $Root 'tools\remote_probe_8093_migration_operation.ps1')
)
$Failures = [System.Collections.Generic.List[string]]::new()

foreach ($path in $Scripts) {
    if (-not (Test-Path -LiteralPath $path -PathType Leaf)) {
        $Failures.Add("missing=$path")
        continue
    }
    $bytes = [IO.File]::ReadAllBytes($path)
    if ($bytes.Length -ge 3 -and $bytes[0] -eq 0xEF -and $bytes[1] -eq 0xBB -and $bytes[2] -eq 0xBF) {
        $Failures.Add("utf8_bom_forbidden=$path")
    }
    $tokens = $null
    $errors = $null
    [void][Management.Automation.Language.Parser]::ParseFile($path, [ref]$tokens, [ref]$errors)
    foreach ($parseError in @($errors)) {
        $Failures.Add("parse_error=$path line=$($parseError.Extent.StartLineNumber) message=$($parseError.Message)")
    }
    $text = [IO.File]::ReadAllText($path, [Text.Encoding]::UTF8)
    if ($text -notmatch "PSEdition -ne 'Core'" -or $text -notmatch 'PSVersion\.Major -lt 7') {
        $Failures.Add("pwsh7_gate_missing=$path")
    }
    if ($text -notmatch "UTF8Encoding\]::new\(\`$false\)") {
        $Failures.Add("utf8_no_bom_runtime_missing=$path")
    }
}

$MigrationPath = Join-Path $Root 'tools\remote_migrate_8093_runtime_to_pwsh7.ps1'
$Migration = [IO.File]::ReadAllText($MigrationPath, [Text.Encoding]::UTF8)
foreach ($marker in @(
    'Global\BFV4PreviewProxy8093Deployment',
    'ExpectedTargetSha256',
    'ExpectedStagedSha256',
    'ops.8093.pwsh7-runtime-migration.operation.v1',
    'Export-ScheduledTask',
    'Register-ScheduledTask',
    'Rollback',
    'run_proxy_8093.ps1',
    'run_proxy_8093_db.ps1',
    "task_name = 'BlastFurnace8093DailyBaseline20d'",
    "task_name = 'BFV4PreviewProxy8093HealthCheck'",
    'C:\Program Files\PowerShell\7\pwsh.exe',
    'protected_before',
    'protected_after'
)) {
    if (-not $Migration.Contains($marker)) { $Failures.Add("migration_marker_missing=$marker") }
}

$ProbePath = Join-Path $Root 'tools\remote_probe_8093_pwsh7_runtime_migration.ps1'
$Probe = [IO.File]::ReadAllText($ProbePath, [Text.Encoding]::UTF8)
foreach ($forbidden in @('Disable-ScheduledTask', 'Set-ScheduledTask', 'Register-ScheduledTask', 'Stop-Service', 'Start-Service', 'Restart-Service', 'Remove-Item')) {
    if ($Probe.Contains($forbidden)) { $Failures.Add("readonly_probe_contains_mutation=$forbidden") }
}

$ConfigPath = Join-Path $Root 'tools\service_configs\22012_BFV4PreviewProxy8093.json'
try {
    $Config = [IO.File]::ReadAllText($ConfigPath, [Text.Encoding]::UTF8) | ConvertFrom-Json
    if ([string]$Config.serviceName -ne 'BFV4PreviewProxy8093') { $Failures.Add('config_service_identity_mismatch') }
    if ([string]$Config.runnerShell -ne 'C:/Program Files/PowerShell/7/pwsh.exe') { $Failures.Add('config_runner_shell_mismatch') }
    if (-not [bool]$Config.migrationPolicy.doNotOverwriteProductionConfig) { $Failures.Add('config_live_patch_policy_missing') }
    $legacy = @($Config.legacyTasks)
    if (@($legacy | Where-Object { $_.path -eq '\' -and $_.name -eq 'BlastFurnaceV3Proxy8093' }).Count -ne 1) {
        $Failures.Add('config_legacy_v3_identity_missing')
    }
    if (@($legacy | Where-Object { $_.path -eq '\' -and $_.name -eq 'BlastFurnace8093Proxy_NewProject' }).Count -ne 1) {
        $Failures.Add('config_legacy_new_project_identity_missing')
    }
} catch {
    $Failures.Add("config_parse_failed=$($_.Exception.Message)")
}

[ordered]@{
    schema = 'ops.8093.pwsh7-runtime-migration.local-verification.v1'
    ok = $Failures.Count -eq 0
    ps_edition = $PSVersionTable.PSEdition
    ps_version = $PSVersionTable.PSVersion.ToString()
    scripts = $Scripts
    failures = @($Failures)
} | ConvertTo-Json -Depth 6

if ($Failures.Count -ne 0) { exit 2 }
