$ErrorActionPreference = 'Stop'
$OutputEncoding = [Console]::OutputEncoding = [Text.UTF8Encoding]::new($false)

$python = 'C:\Program Files\Python311\python.exe'
$audit = 'C:\Users\Administrator\AppData\Local\Temp\remote_audit_imes_refresh_pipeline.py'
foreach ($name in @('GL02_PGHOST', 'GL02_PGPORT', 'GL02_PGDATABASE', 'GL02_PGUSER', 'GL02_PGPASSWORD')) {
    $value = [Environment]::GetEnvironmentVariable($name, 'Machine')
    if ($value) { Set-Item -Path "Env:$name" -Value $value }
}
$env:PYTHONUTF8 = '1'

$tasks = @(Get-ScheduledTask | Where-Object {
    $_.TaskName -match '(?i)(imes|mes|heatperformance|heat.*quality)'
} | ForEach-Object {
    $info = Get-ScheduledTaskInfo -TaskPath $_.TaskPath -TaskName $_.TaskName
    $actionItem = @($_.Actions) | Select-Object -First 1
    [pscustomobject]@{
        task_path = $_.TaskPath
        task_name = $_.TaskName
        state = $_.State.ToString()
        last_run_time = if ($info.LastRunTime) { $info.LastRunTime.ToString('o') } else { $null }
        last_result = $info.LastTaskResult
        next_run_time = if ($info.NextRunTime) { $info.NextRunTime.ToString('o') } else { $null }
        action = if ($actionItem) { $actionItem.Execute + ' ' + $actionItem.Arguments } else { $null }
    }
})
$database = & $python -X utf8 $audit | ConvertFrom-Json
if ($LASTEXITCODE -ne 0) { throw 'IMES refresh database audit failed' }

[ordered]@{
    audited_at = (Get-Date).ToString('o')
    tasks = $tasks
    database = $database
} | ConvertTo-Json -Depth 10
