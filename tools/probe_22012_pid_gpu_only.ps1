$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"
$OutputEncoding = [Console]::OutputEncoding = [Text.UTF8Encoding]::new($false)

$nvidiaSmi = (Get-Command nvidia-smi.exe -ErrorAction SilentlyContinue).Source
if (-not $nvidiaSmi) {
    $candidate = "C:\Program Files\NVIDIA Corporation\NVSMI\nvidia-smi.exe"
    if (Test-Path -LiteralPath $candidate) {
        $nvidiaSmi = $candidate
    }
}

$allProcesses = @(Get-CimInstance Win32_Process)
$processByPid = @{}
foreach ($process in $allProcesses) {
    $processByPid[[int]$process.ProcessId] = $process
}

$relevantProcesses = @()
foreach ($process in $allProcesses) {
    $text = "$($process.Name) $($process.ExecutablePath) $($process.CommandLine)"
    if ($text -notmatch '(?i)ollama|ollama_proxy_server|start_v3_8092_python|run_22012_8094_preview') {
        continue
    }
    $parent = $processByPid[[int]$process.ParentProcessId]
    $runtime = Get-Process -Id $process.ProcessId -ErrorAction SilentlyContinue
    $relevantProcesses += [pscustomobject]@{
        pid = $process.ProcessId
        parent_pid = $process.ParentProcessId
        parent_exists = ($null -ne $parent)
        name = $process.Name
        command_line = $process.CommandLine
        creation_date = $process.CreationDate
        parent_name = if ($parent) { $parent.Name } else { $null }
        parent_command_line = if ($parent) { $parent.CommandLine } else { $null }
        cpu_seconds = if ($runtime) { [math]::Round([double]$runtime.CPU, 2) } else { $null }
        working_set_mb = if ($runtime) { [math]::Round($runtime.WorkingSet64 / 1MB, 1) } else { $null }
        private_memory_mb = if ($runtime) { [math]::Round($runtime.PrivateMemorySize64 / 1MB, 1) } else { $null }
        thread_count = if ($runtime) { $runtime.Threads.Count } else { $null }
        handle_count = if ($runtime) { $runtime.HandleCount } else { $null }
    }
}

$listeners = @()
foreach ($connection in @(Get-NetTCPConnection -State Listen -ErrorAction SilentlyContinue)) {
    if ($connection.LocalPort -notin @(8092, 8093, 8094, 11434)) {
        continue
    }
    $owner = $processByPid[[int]$connection.OwningProcess]
    $listeners += [pscustomobject]@{
        address = $connection.LocalAddress
        port = $connection.LocalPort
        pid = $connection.OwningProcess
        process_name = if ($owner) { $owner.Name } else { $null }
        command_line = if ($owner) { $owner.CommandLine } else { $null }
    }
}

$relevantPorts = @(8092, 8093, 8094, 11434)
foreach ($process in $relevantProcesses) {
    $match = [regex]::Match([string]$process.command_line, '(?i)--port\s+(\d+)')
    if ($match.Success) {
        $relevantPorts += [int]$match.Groups[1].Value
    }
}
$relevantPorts = @($relevantPorts | Sort-Object -Unique)

$connections = @()
foreach ($connection in @(Get-NetTCPConnection -ErrorAction SilentlyContinue)) {
    if (
        $connection.LocalPort -notin $relevantPorts -and
        $connection.RemotePort -notin $relevantPorts
    ) {
        continue
    }
    $owner = $processByPid[[int]$connection.OwningProcess]
    $connections += [pscustomobject]@{
        state = [string]$connection.State
        local_address = $connection.LocalAddress
        local_port = $connection.LocalPort
        remote_address = $connection.RemoteAddress
        remote_port = $connection.RemotePort
        pid = $connection.OwningProcess
        process_name = if ($owner) { $owner.Name } else { $null }
        command_line = if ($owner) { $owner.CommandLine } else { $null }
    }
}

$gpuSamples = @()
$computeApps = @()
$pmon = @()
if ($nvidiaSmi) {
    for ($sampleIndex = 0; $sampleIndex -lt 3; $sampleIndex++) {
        $gpuSamples += [pscustomobject]@{
            sampled_at = (Get-Date).ToString("yyyy-MM-dd HH:mm:ss.fff")
            csv = @(
                & $nvidiaSmi `
                    --query-gpu=index,name,temperature.gpu,utilization.gpu,utilization.memory,memory.total,memory.used,memory.free,power.draw,pstate `
                    --format=csv,noheader,nounits 2>&1
            )
        }
        if ($sampleIndex -lt 2) {
            Start-Sleep -Seconds 1
        }
    }
    $computeApps = @(
        & $nvidiaSmi `
            --query-compute-apps=pid,process_name,used_gpu_memory `
            --format=csv,noheader,nounits 2>&1
    )
    $pmon = @(& $nvidiaSmi pmon -c 1 2>&1)
}

$ollamaPs = $null
try {
    $ollamaPs = Invoke-RestMethod -Method Get -Uri "http://127.0.0.1:11434/api/ps" -TimeoutSec 2
} catch {
    $ollamaPs = [pscustomobject]@{ error = $_.Exception.Message }
}

[pscustomobject]@{
    collected_at = (Get-Date).ToString("yyyy-MM-dd HH:mm:ss zzz")
    computer_name = $env:COMPUTERNAME
    nvidia_smi = $nvidiaSmi
    gpu_samples = $gpuSamples
    compute_apps = $computeApps
    pmon = $pmon
    listeners = $listeners
    connections = $connections
    processes = $relevantProcesses
    ollama_ps = $ollamaPs
} | ConvertTo-Json -Depth 15
