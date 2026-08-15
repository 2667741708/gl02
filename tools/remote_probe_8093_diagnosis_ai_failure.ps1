[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
if ($PSVersionTable.PSEdition -ne 'Core' -or $PSVersionTable.PSVersion.Major -lt 7) {
    throw 'PowerShell 7 Core or later is required.'
}
$Utf8NoBom = [Text.UTF8Encoding]::new($false)
[Console]::InputEncoding = $Utf8NoBom
[Console]::OutputEncoding = $Utf8NoBom
$OutputEncoding = $Utf8NoBom
$PSDefaultParameterValues['*:Encoding'] = 'utf8'

$Root = 'F:\高炉炼铁项目-real-sensor-v2_V4_8093_PREVIEW'
$LogRoot = Join-Path $Root 'logs'
$BackupRoot = Join-Path $Root 'backups'
$LogFiles = @(Get-ChildItem -LiteralPath $LogRoot -File -ErrorAction Stop |
    Where-Object { $_.Name -like 'proxy_8093*' })
$LogSummary = @($LogFiles | ForEach-Object {
    $Matches = @(Get-Content -LiteralPath $_.FullName -Tail 600 -Encoding UTF8 -ErrorAction SilentlyContinue |
        Where-Object {
            $_ -like '*five-minute diagnosis AI analysis failed*' -or
            $_ -like '*TypeError*' -or
            $_ -like '*starting service=*'
        } | Select-Object -Last 30)
    [ordered]@{
        path = $_.FullName
        size = $_.Length
        modified = $_.LastWriteTime.ToString('o')
        matches = $Matches
    }
})
$Backups = @(Get-ChildItem -LiteralPath $BackupRoot -Directory -ErrorAction SilentlyContinue |
    Where-Object { $_.Name -like 'diagnosis_ai_json_fix_8093_*' } |
    Sort-Object LastWriteTime -Descending |
    Select-Object -First 3 |
    ForEach-Object {
        [ordered]@{ path = $_.FullName; modified = $_.LastWriteTime.ToString('o') }
    })
$AnalysisResponse = Invoke-RestMethod -Uri 'http://127.0.0.1:8093/api/diagnosis-ai-analysis?label=normal&probe=failure-state' -TimeoutSec 45

[ordered]@{
    schema = 'ops.8093.diagnosis-ai-json-fix.failure-evidence.v1'
    logs = $LogSummary
    backups = $Backups
    analysis = $AnalysisResponse.analysis
} | ConvertTo-Json -Depth 7
