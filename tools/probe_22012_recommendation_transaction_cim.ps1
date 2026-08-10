$ErrorActionPreference = "Stop"
$OutputEncoding = [Console]::OutputEncoding = [Text.UTF8Encoding]::new($false)

$root = Split-Path -Parent $PSScriptRoot
$agentsText = Get-Content -LiteralPath (Join-Path $root "AGENTS.md") -Raw -Encoding UTF8
$match = [regex]::Match($agentsText, 'SSH \u5bc6\u7801\uff1a([^\r\n]+)')
if (-not $match.Success) { throw "Controlled 220.12 credential is unavailable" }
$secure = ConvertTo-SecureString $match.Groups[1].Value.Trim() -AsPlainText -Force
$credential = [Management.Automation.PSCredential]::new("administrator", $secure)
$option = New-CimSessionOption -Protocol Dcom
$session = New-CimSession -ComputerName "10.30.220.12" -Credential $credential -SessionOption $option

try {
    $services = Get-CimInstance -CimSession $session -ClassName Win32_Service |
        Where-Object Name -In @("BFV4PreviewProxy8093", "BFV4PreviewWs8768") |
        Select-Object Name, State, ProcessId
    $processes = Get-CimInstance -CimSession $session -ClassName Win32_Process |
        Where-Object {
            $_.CommandLine -and (
                $_.CommandLine.Contains("remote_guarded_deploy_recommendation_audit") -or
                $_.CommandLine.Contains("verify_recommendation_audit_runtime") -or
                $_.CommandLine.Contains("local_pg_ws_bridge.py")
            )
        } |
        Select-Object ProcessId, ParentProcessId, Name, CommandLine
    $listeners = Get-CimInstance -CimSession $session -Namespace "root/StandardCimv2" -ClassName MSFT_NetTCPConnection |
        Where-Object { $_.State -eq 2 -and $_.LocalPort -In @(8093, 8094, 8768, 8770) } |
        Select-Object LocalPort, OwningProcess
    [ordered]@{
        ok = $true
        services = @($services)
        relevantProcesses = @($processes)
        listeners = @($listeners)
    } | ConvertTo-Json -Depth 8
}
finally {
    Remove-CimSession -CimSession $session -ErrorAction SilentlyContinue
}
