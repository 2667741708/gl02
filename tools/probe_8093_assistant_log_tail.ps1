$ErrorActionPreference = "Stop"
$OutputEncoding = [Console]::OutputEncoding = [Text.UTF8Encoding]::new($false)

$logDirectory = "F:\高炉炼铁项目-real-sensor-v2_V4_8093_PREVIEW\logs"
$outLog = Join-Path $logDirectory "proxy_8093.service.out.log"
$errLog = Join-Path $logDirectory "proxy_8093.service.err.log"
$runnerLog = Join-Path $logDirectory "proxy_8093.service.runner.log"
$healthLog = Join-Path $logDirectory "proxy_8093.health.log"
$errorPattern = "Timeout|timed out|BrokenPipe|ConnectionReset|RemoteDisconnected|URLError|HTTPError|embedding|nomic|psycopg|OperationalError|RuntimeError|Traceback|KeyboardInterrupt"

$outTail = @(Get-Content -LiteralPath $outLog -Tail 1200 -Encoding UTF8)
$errTail = @(Get-Content -LiteralPath $errLog -Tail 800 -Encoding UTF8)

[pscustomobject]@{
    schema = "ops.8093.assistant-log-tail.readonly.v1"
    collected_at = (Get-Date).ToString("yyyy-MM-dd HH:mm:ss zzz")
    qa_requests = @(
        $outTail |
            Select-String -SimpleMatch "POST /api/qa/chat" |
            Select-Object -Last 40 |
            ForEach-Object { $_.Line }
    )
    error_matches = @(
        $errTail |
            Select-String -Pattern $errorPattern |
            Select-Object -Last 80 |
            ForEach-Object { $_.Line }
    )
    runner_tail = @(
        Get-Content -LiteralPath $runnerLog -Tail 30 -Encoding UTF8 |
            ForEach-Object { [string]$_ }
    )
    health_tail = @(
        Get-Content -LiteralPath $healthLog -Tail 60 -Encoding UTF8 |
            ForEach-Object { [string]$_ }
    )
} | ConvertTo-Json -Depth 5
