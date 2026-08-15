[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
if ($PSVersionTable.PSEdition -ne 'Core' -or $PSVersionTable.PSVersion.Major -lt 7) {
    throw 'This cleanup requires PowerShell 7 Core or later.'
}
$Utf8NoBom = [Text.UTF8Encoding]::new($false)
[Console]::InputEncoding = $Utf8NoBom
[Console]::OutputEncoding = $Utf8NoBom
$OutputEncoding = $Utf8NoBom
$PSDefaultParameterValues['*:Encoding'] = 'utf8'

$Root = 'F:\高炉炼铁项目-real-sensor-v2_V4_8093_PREVIEW'
$Python = 'C:\Program Files\Python311\python.exe'
$Tool = 'C:\Users\Administrator\AppData\Local\Temp\cleanup_8093_dashboard_build_assets.py'
$Html = Join-Path $Root '高炉前端数据\frontend_dashboard_v3.server.html'
$Build = Join-Path $Root '高炉前端数据\assets\build'
$Manifest = Join-Path $Root ("logs\deploy_backups\8093_build_cleanup_{0}.json" -f (Get-Date -Format 'yyyyMMdd_HHmmss'))
$ExpectedDelete = @(
    'dashboard-main-DaGlW2vU.js',
    'dashboard-main-BJmRbVTN.js',
    'dashboard-main-UDl4o6qp.js',
    'dashboard-main-v9ebK4cf.js'
) | Sort-Object

foreach ($Path in @($Python, $Tool, $Html, $Build)) {
    if (-not (Test-Path -LiteralPath $Path)) { throw "Cleanup input missing: $Path" }
}
$Mutex = [Threading.Mutex]::new($false, 'Global\BFV4PreviewProxy8093Deployment')
$LockTaken = $false
try {
    $LockTaken = $Mutex.WaitOne(0)
    if (-not $LockTaken) { throw 'Another 8093 deployment owns the deployment mutex.' }
    $DryRaw = @(& $Python -X utf8 $Tool --html $Html --build-dir $Build 2>&1) -join "`n"
    if ($LASTEXITCODE -ne 0) { throw "Cleanup dry-run failed: $DryRaw" }
    $Dry = $DryRaw | ConvertFrom-Json
    if (-not $Dry.ok -or $Dry.active_bundle -ne 'dashboard-main-GX_5dx5H.js' -or $Dry.rollback_bundle -ne 'dashboard-main-CcxwpZA4.js') {
        throw 'Cleanup keep-set identity mismatch.'
    }
    $ActualDelete = @($Dry.delete_candidates | ForEach-Object { [string]$_.name } | Sort-Object)
    if (($ActualDelete -join '|') -cne ($ExpectedDelete -join '|')) {
        throw "Cleanup candidate set mismatch: $($ActualDelete -join ',')"
    }
    $ApplyRaw = @(& $Python -X utf8 $Tool --html $Html --build-dir $Build --manifest-out $Manifest --apply 2>&1) -join "`n"
    if ($LASTEXITCODE -ne 0) { throw "Cleanup apply failed: $ApplyRaw" }
    $Apply = $ApplyRaw | ConvertFrom-Json
    $Remaining = @(Get-ChildItem -LiteralPath $Build -File -Filter 'dashboard-main-*.js' | Select-Object -ExpandProperty Name | Sort-Object)
    $ExpectedRemaining = @('dashboard-main-CcxwpZA4.js', 'dashboard-main-GX_5dx5H.js') | Sort-Object
    if (($Remaining -join '|') -cne ($ExpectedRemaining -join '|')) { throw "Unexpected remaining bundle set: $($Remaining -join ',')" }
    [ordered]@{
        ok = $true
        schema = 'bf.8093.dashboard-build-cleanup.production.v1'
        manifest = $Manifest
        active_bundle = $Apply.active_bundle
        rollback_bundle = $Apply.rollback_bundle
        removed = @($Apply.removed)
        remaining = $Remaining
        removed_bytes = [long]$Dry.delete_candidate_bytes
    } | ConvertTo-Json -Depth 6
}
finally {
    if ($LockTaken) { $Mutex.ReleaseMutex() }
    $Mutex.Dispose()
}
