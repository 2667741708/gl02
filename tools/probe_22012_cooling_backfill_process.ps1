$OutputEncoding = [Console]::OutputEncoding = [Text.UTF8Encoding]::new($false)
Get-CimInstance Win32_Process |
    Where-Object { $_.CommandLine -like "*sync_from_243_pg.py*" -and $_.CommandLine -like "*Q_soft_water*" } |
    ForEach-Object {
        $process = Get-Process -Id $_.ProcessId -ErrorAction SilentlyContinue
        [ordered]@{
            pid = $_.ProcessId
            parent_pid = $_.ParentProcessId
            created = $_.CreationDate
            cpu_seconds = if ($process) { $process.CPU } else { $null }
            working_set = if ($process) { $process.WorkingSet64 } else { $null }
        } | ConvertTo-Json -Compress
    }
