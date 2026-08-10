$ErrorActionPreference = 'Stop'
$utf8NoBom = [System.Text.UTF8Encoding]::new($false)
[Console]::InputEncoding = $utf8NoBom
[Console]::OutputEncoding = $utf8NoBom
$OutputEncoding = $utf8NoBom
$PSDefaultParameterValues['*:Encoding'] = 'utf8'

$failures = [System.Collections.Generic.List[string]]::new()
if ($PSVersionTable.PSEdition -ne 'Core') {
    $failures.Add("PSEdition=$($PSVersionTable.PSEdition)")
}
if ($PSVersionTable.PSVersion -lt [Version]'7.6.4') {
    $failures.Add("PSVersion=$($PSVersionTable.PSVersion)")
}
if ([Environment]::ProcessPath -notlike '*\pwsh.exe') {
    $failures.Add("ProcessPath=$([Environment]::ProcessPath)")
}

$projectRoot = 'F:\高炉炼铁项目-real-sensor-v2_V4_8093_PREVIEW'
if (-not (Test-Path -LiteralPath $projectRoot -PathType Container)) {
    $failures.Add("ProjectRootMissing=$projectRoot")
}

$probePath = Join-Path $env:TEMP '冀南钢铁_22012_pwsh7_utf8_probe.txt'
$probeText = '冀南钢铁 PowerShell 7 UTF-8：硅含量预测'
try {
    [IO.File]::WriteAllText($probePath, $probeText, $utf8NoBom)
    $roundTrip = [IO.File]::ReadAllText($probePath, [Text.Encoding]::UTF8)
    if ($roundTrip -cne $probeText) {
        $failures.Add('Utf8RoundTripMismatch')
    }
}
finally {
    if (Test-Path -LiteralPath $probePath) {
        Remove-Item -LiteralPath $probePath -Force
    }
}

$parseTargets = @(
    (Join-Path $projectRoot 'tools\run_22012_si_v20_strict_hourly.ps1'),
    (Join-Path $projectRoot 'tools\run_22012_si_v20_schedule_dispatcher.ps1'),
    (Join-Path $projectRoot 'tools\run_22012_8094_preview.ps1'),
    (Join-Path $projectRoot 'tools\manage_22012_managed_services.ps1'),
    (Join-Path $projectRoot 'tools\check_managed_nssm_service_health.ps1'),
    (Join-Path $projectRoot 'standalone_heat_dashboard_8891\tools\run_22012_heat_performance_sync.ps1')
)
$parseResults = @()
foreach ($target in $parseTargets) {
    if (-not (Test-Path -LiteralPath $target -PathType Leaf)) {
        $parseResults += [ordered]@{ path = $target; exists = $false; syntax_ok = $false; errors = @('missing') }
        $failures.Add("ParseTargetMissing=$target")
        continue
    }
    $tokens = $null
    $errors = $null
    [void][Management.Automation.Language.Parser]::ParseFile($target, [ref]$tokens, [ref]$errors)
    $parseResults += [ordered]@{
        path = $target
        exists = $true
        syntax_ok = ($errors.Count -eq 0)
        errors = @($errors | ForEach-Object { $_.Message })
    }
    if ($errors.Count -ne 0) {
        $failures.Add("ParseFailed=$target")
    }
}

[ordered]@{
    schema = 'bf.remote.pwsh7.verify.v1'
    ok = ($failures.Count -eq 0)
    executable = [Environment]::ProcessPath
    ps_version = $PSVersionTable.PSVersion.ToString()
    ps_edition = $PSVersionTable.PSEdition
    console_input_encoding = [Console]::InputEncoding.WebName
    console_output_encoding = [Console]::OutputEncoding.WebName
    output_encoding = $OutputEncoding.WebName
    project_root = $projectRoot
    utf8_probe = $probeText
    parse_results = $parseResults
    failures = @($failures)
} | ConvertTo-Json -Depth 8

if ($failures.Count -ne 0) {
    exit 2
}
