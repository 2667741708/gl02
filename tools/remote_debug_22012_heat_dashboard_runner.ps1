$ErrorActionPreference = "Continue"
[Console]::OutputEncoding = [Text.UTF8Encoding]::new($false)
$root = "F:\高炉炼铁项目-real-sensor-v2_V4_8093_PREVIEW\standalone_heat_dashboard_8891"
$runner = "$root\run_22012_heat_dashboard_8891.ps1"
$out = "$root\logs\runner_debug_stdout.txt"
$err = "$root\logs\runner_debug_stderr.txt"
New-Item -ItemType Directory -Force -Path "$root\logs" | Out-Null
Remove-Item -LiteralPath $out,$err -Force -ErrorAction SilentlyContinue
$proc = Start-Process -FilePath "C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe" -ArgumentList @("-NoProfile", "-ExecutionPolicy", "Bypass", "-File", $runner) -RedirectStandardOutput $out -RedirectStandardError $err -PassThru -WindowStyle Hidden
Start-Sleep -Seconds 5
$running = [bool](Get-Process -Id $proc.Id -ErrorAction SilentlyContinue)
if ($running) { Stop-Process -Id $proc.Id -Force -ErrorAction SilentlyContinue }
[ordered]@{
    process_id = $proc.Id
    running_after_5s = $running
    process_exit_code = $proc.ExitCode
    stdout = if (Test-Path -LiteralPath $out) { Get-Content -LiteralPath $out -Raw } else { "" }
    stderr = if (Test-Path -LiteralPath $err) { Get-Content -LiteralPath $err -Raw } else { "" }
    dashboard_log = if (Test-Path -LiteralPath "$root\logs\heat_dashboard_8891.log") { Get-Content -LiteralPath "$root\logs\heat_dashboard_8891.log" -Tail 40 } else { @() }
} | ConvertTo-Json -Depth 8
