$ErrorActionPreference = "Continue"
$runner = "F:\高炉炼铁项目-real-sensor-v2_V4_8093_PREVIEW\tools\run_22012_8095_preview.ps1"
$job = Start-Job -ScriptBlock { param($path) & powershell.exe -NoProfile -ExecutionPolicy Bypass -File $path } -ArgumentList $runner
Start-Sleep -Seconds 5
$output = Receive-Job -Job $job -Keep 2>&1 | Out-String
Stop-Job -Job $job -ErrorAction SilentlyContinue
Remove-Job -Job $job -Force -ErrorAction SilentlyContinue
[ordered]@{ output = $output; log_exists = (Test-Path -LiteralPath "F:\高炉炼铁项目-real-sensor-v2_V4_8093_PREVIEW\logs\preview_proxy_8095.log") } | ConvertTo-Json -Depth 5
