[CmdletBinding()]
param(
    [string]$Root = 'F:\高炉炼铁项目-real-sensor-v2_V4_8093_PREVIEW',
    [string]$ExpectedConfigSha256 = 'A04517D8244F3B6E1E67B3D0CA42AADB86C9E0F65A149A316EDF195DD3630EE3'
)

$ErrorActionPreference = 'Stop'
if ($PSVersionTable.PSEdition -ne 'Core' -or $PSVersionTable.PSVersion.Major -lt 7) {
    throw 'PowerShell 7 Core is required.'
}
$Utf8NoBom = [Text.UTF8Encoding]::new($false)
[Console]::InputEncoding = $Utf8NoBom
[Console]::OutputEncoding = $Utf8NoBom
$OutputEncoding = $Utf8NoBom
$PSDefaultParameterValues['*:Encoding'] = 'utf8'

$ServiceName = 'BFV4PreviewProxy8093'
$Manager = Join-Path $Root 'tools\manage_22012_managed_services.ps1'
$ConfigPath = Join-Path $Root 'tools\service_configs\22012_BFV4PreviewProxy8093.json'
$ProtectedPorts = @(8094, 8768, 8770, 5432, 11434)
$Required = [ordered]@{
    BF_QA_GUEST_ENABLED = '1'
    BF_QA_KNOWLEDGE_SEARCH_MODE = 'keyword'
    BF_QA_MCP_MAX_TOOL_ROUNDS = '5'
    BF_QA_MCP_MAX_TOOL_CALLS = '5'
    BF_QA_MCP_PARALLEL_TOOL_CALLS = '1'
    BF_QA_MCP_MAX_PARALLEL_TOOL_CALLS = '5'
}

function Get-ListenerPid([int]$Port) {
    $Listener = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue |
        Select-Object -First 1
    if ($Listener) { return [int]$Listener.OwningProcess }
    return $null
}

function Get-ProtectedMap {
    $Map = [ordered]@{}
    foreach ($Port in $ProtectedPorts) { $Map[[string]$Port] = Get-ListenerPid $Port }
    return $Map
}

function Wait-Running([int]$Seconds = 90) {
    $Deadline = (Get-Date).AddSeconds($Seconds)
    do {
        $Service = (Get-Service $ServiceName).Status.ToString()
        $ListenerPid = Get-ListenerPid 8093
        if ($Service -eq 'Running' -and $ListenerPid) { return $ListenerPid }
        Start-Sleep -Milliseconds 500
    } while ((Get-Date) -lt $Deadline)
    throw '8093 did not return to Running/listening state.'
}

$ActualHash = (Get-FileHash -LiteralPath $ConfigPath -Algorithm SHA256).Hash
if ($ActualHash -ne $ExpectedConfigSha256.ToUpperInvariant()) {
    throw "Live service config baseline mismatch: $ActualHash"
}
$Before = Get-ProtectedMap
$OldPid = Get-ListenerPid 8093
$Stamp = Get-Date -Format 'yyyyMMdd_HHmmss'
$Backup = Join-Path $Root "backups\8093_guest_mcp_runtime_config_$Stamp.json"
Copy-Item -LiteralPath $ConfigPath -Destination $Backup
$Config = Get-Content -LiteralPath $ConfigPath -Raw -Encoding UTF8 | ConvertFrom-Json
foreach ($Entry in $Required.GetEnumerator()) {
    if ($null -eq $Config.env.PSObject.Properties[$Entry.Key]) {
        $Config.env | Add-Member -NotePropertyName $Entry.Key -NotePropertyValue $Entry.Value
    }
    else {
        $Config.env.($Entry.Key) = $Entry.Value
    }
}
$TempPath = "$ConfigPath.new"
[IO.File]::WriteAllText($TempPath, ($Config | ConvertTo-Json -Depth 12), $Utf8NoBom)
$GuardRestored = $false
$Rollback = $false
$NewPid = $null
try {
    & 'C:\Program Files\PowerShell\7\pwsh.exe' -NoLogo -NoProfile -File $Manager -Action stop -ConfigPath $ConfigPath | Out-Null
    Move-Item -LiteralPath $TempPath -Destination $ConfigPath -Force
    & 'C:\Program Files\PowerShell\7\pwsh.exe' -NoLogo -NoProfile -File $Manager -Action start -ConfigPath $ConfigPath | Out-Null
    $NewPid = Wait-Running
    $GuardRestored = $true
    $Status = Invoke-RestMethod -Uri 'http://127.0.0.1:8093/api/ollama/status' -TimeoutSec 30
    if (-not $Status.ok) { throw 'Ollama proxy status failed.' }
    $Bootstrap = Invoke-RestMethod -Uri 'http://127.0.0.1:8093/api/qa/bootstrap' -TimeoutSec 30
    if ($Bootstrap.access_mode -ne 'guest_shared') { throw 'Shared guest bootstrap contract failed.' }
    $After = Get-ProtectedMap
    foreach ($Port in $ProtectedPorts) {
        if ([int]$Before[[string]$Port] -ne [int]$After[[string]$Port]) {
            throw "Protected listener changed on port $Port."
        }
    }
    [ordered]@{
        ok = $true
        schema = 'bf.8093-guest-mcp-runtime-config-deploy.v1'
        backup = $Backup
        old_8093_pid = $OldPid
        new_8093_pid = $NewPid
        config_sha256 = (Get-FileHash -LiteralPath $ConfigPath -Algorithm SHA256).Hash
        guard_restored = $GuardRestored
        rollback_applied = $Rollback
        protected_before = $Before
        protected_after = $After
        access_mode = $Bootstrap.access_mode
        model_request_count = 0
    } | ConvertTo-Json -Depth 7
}
catch {
    $Failure = $_.Exception.Message
    $Rollback = $true
    Copy-Item -LiteralPath $Backup -Destination $ConfigPath -Force
    & 'C:\Program Files\PowerShell\7\pwsh.exe' -NoLogo -NoProfile -File $Manager -Action start -ConfigPath $ConfigPath | Out-Null
    $NewPid = Wait-Running
    $GuardRestored = $true
    [ordered]@{
        ok = $false
        schema = 'bf.8093-guest-mcp-runtime-config-deploy.v1'
        failure = $Failure
        backup = $Backup
        listener_8093 = $NewPid
        guard_restored = $GuardRestored
        rollback_applied = $Rollback
    } | ConvertTo-Json -Depth 5
    throw $Failure
}
finally {
    if (-not $GuardRestored) {
        & 'C:\Program Files\PowerShell\7\pwsh.exe' -NoLogo -NoProfile -File $Manager -Action start -ConfigPath $ConfigPath | Out-Null
        Wait-Running | Out-Null
    }
    Remove-Item -LiteralPath $TempPath -Force -ErrorAction SilentlyContinue
}
