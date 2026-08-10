$ErrorActionPreference = "Stop"
[Console]::OutputEncoding = [Text.UTF8Encoding]::new($false)

$listener = Get-NetTCPConnection -State Listen -LocalPort 18080 -ErrorAction Stop | Select-Object -First 1
$process = Get-CimInstance Win32_Process -Filter ("ProcessId=" + $listener.OwningProcess)
$parent = if ($process) {
    Get-CimInstance Win32_Process -Filter ("ProcessId=" + $process.ParentProcessId) -ErrorAction SilentlyContinue
} else { $null }
$processPath = if ($process) { $process.ExecutablePath } else { $null }
$processRoot = if ($processPath) { Split-Path -Parent $processPath } else { $null }

$candidateConfigs = @()
if ($processRoot) {
    $candidateConfigs += (Join-Path $processRoot "conf\nginx.conf")
    $candidateConfigs += (Join-Path $processRoot "nginx.conf")
}
foreach ($match in [regex]::Matches([string]$process.CommandLine, '(?:-c\s+)(?:"([^"]+)"|([^\s]+))')) {
    $candidate = if ($match.Groups[1].Success) { $match.Groups[1].Value } else { $match.Groups[2].Value }
    if ($candidate -and -not [IO.Path]::IsPathRooted($candidate) -and $processRoot) {
        $candidate = Join-Path $processRoot $candidate
    }
    $candidateConfigs += $candidate
}
$candidateConfigs = @($candidateConfigs | Where-Object { $_ } | Select-Object -Unique)

$configs = foreach ($path in $candidateConfigs) {
    if (Test-Path -LiteralPath $path) {
        $content = Get-Content -LiteralPath $path -Raw -Encoding UTF8
        [ordered]@{
            path = $path
            exists = $true
            sha256 = (Get-FileHash -LiteralPath $path -Algorithm SHA256).Hash
            listen_18080_lines = @(
                ($content -split "`r?`n") |
                    Select-String -Pattern "listen\s+.*18080|server_name|location\s+|proxy_pass" |
                    ForEach-Object { $_.Line.Trim() }
            )
            content = $content
        }
    } else {
        [ordered]@{ path = $path; exists = $false; sha256 = $null; listen_18080_lines = @(); content = $null }
    }
}

[ordered]@{
    checked_at = (Get-Date).ToString("s")
    listener = [ordered]@{ local_address = $listener.LocalAddress; local_port = $listener.LocalPort; pid = $listener.OwningProcess }
    process = if ($process) { [ordered]@{ pid = $process.ProcessId; name = $process.Name; executable_path = $process.ExecutablePath; command_line = $process.CommandLine; parent_pid = $process.ParentProcessId } } else { $null }
    parent = if ($parent) { [ordered]@{ pid = $parent.ProcessId; name = $parent.Name; executable_path = $parent.ExecutablePath; command_line = $parent.CommandLine; parent_pid = $parent.ParentProcessId } } else { $null }
    configs = $configs
} | ConvertTo-Json -Depth 10
