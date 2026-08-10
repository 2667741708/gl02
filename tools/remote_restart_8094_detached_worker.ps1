$ErrorActionPreference = 'Stop'
$OutputEncoding = [Console]::OutputEncoding = [Text.UTF8Encoding]::new($false)
$ProjectRoot = (Get-Location).Path
$RunId = Get-Date -Format 'yyyyMMdd_HHmmss'
$restart = Join-Path $ProjectRoot 'tools\restart_22012_8094_preview.ps1'
$resultRoot = Join-Path $ProjectRoot 'logs\deployment\si_v20_8094_restart'
$outputPath = Join-Path $resultRoot "$RunId.output.txt"
$statusPath = Join-Path $resultRoot "$RunId.status.json"
New-Item -ItemType Directory -Path $resultRoot -Force | Out-Null
$status = [ordered]@{ run_id = $RunId; started_at = (Get-Date).ToString('o'); completed = $false; ok = $false; error = $null }
try {
    $output = & powershell.exe -NoProfile -ExecutionPolicy Bypass -File $restart 2>&1
    $output | Out-File -LiteralPath $outputPath -Encoding UTF8
    if ($LASTEXITCODE -ne 0) { throw "8094 restart exited with code $LASTEXITCODE" }
    $status.ok = $true
} catch {
    $_ | Out-String | Out-File -LiteralPath $outputPath -Encoding UTF8 -Append
    $status.error = $_.Exception.Message
} finally {
    $status.completed = $true
    $status.completed_at = (Get-Date).ToString('o')
    $status.output_path = $outputPath
    $status | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath $statusPath -Encoding UTF8
}
if (-not $status.ok) { exit 1 }
