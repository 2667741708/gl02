$ErrorActionPreference = "Stop"
[Console]::OutputEncoding = [Text.UTF8Encoding]::new($false)

$relayPorts = @(18080, 15433, 18889)
$protectedPorts = @(8093, 8768, 8094, 8770, 8891)
$targetSpecs = @(
    [ordered]@{ name = "imes_web"; host = "10.10.181.209"; port = 8080 },
    [ordered]@{ name = "imes_vastbase"; host = "10.10.181.195"; port = 5432 },
    [ordered]@{ name = "pspace"; host = "10.22.181.243"; port = 8889 }
)

function Get-ListenerSnapshot {
    param([int[]]$Ports)
    $rows = @(
        Get-NetTCPConnection -State Listen -LocalPort $Ports -ErrorAction SilentlyContinue |
            Sort-Object LocalPort, LocalAddress |
            Select-Object LocalAddress, LocalPort, OwningProcess
    )
    foreach ($row in $rows) {
        $proc = Get-CimInstance Win32_Process -Filter ("ProcessId=" + $row.OwningProcess) -ErrorAction SilentlyContinue
        [ordered]@{
            local_address = $row.LocalAddress
            local_port = [int]$row.LocalPort
            pid = [int]$row.OwningProcess
            process_name = if ($proc) { $proc.Name } else { $null }
            parent_pid = if ($proc) { [int]$proc.ParentProcessId } else { $null }
            command_line = if ($proc) { $proc.CommandLine } else { $null }
        }
    }
}

function Invoke-HttpProbe {
    param([string]$Url)
    try {
        $response = Invoke-WebRequest -UseBasicParsing -Uri $Url -TimeoutSec 15
        return [ordered]@{
            url = $Url
            ok = $true
            status = [int]$response.StatusCode
            final_uri = [string]$response.BaseResponse.ResponseUri
            content_type = [string]$response.Headers["Content-Type"]
            content_length = [int]$response.RawContentLength
            has_imes_marker = [bool]($response.Content -match "imes|iMES|冀南")
            error = $null
        }
    } catch {
        $status = $null
        if ($_.Exception.Response) {
            $status = [int]$_.Exception.Response.StatusCode
        }
        return [ordered]@{
            url = $Url
            ok = $false
            status = $status
            final_uri = $null
            content_type = $null
            content_length = 0
            has_imes_marker = $false
            error = $_.Exception.Message
        }
    }
}

$targets = foreach ($item in $targetSpecs) {
    [ordered]@{
        name = $item.name
        host = $item.host
        port = $item.port
        reachable = [bool](Test-NetConnection $item.host -Port $item.port -InformationLevel Quiet)
    }
}

$portProxyText = (& netsh.exe interface portproxy show all 2>&1 | Out-String).Trim()
$ipHelper = Get-Service -Name iphlpsvc -ErrorAction SilentlyContinue
$firewallRules = @(
    Get-NetFirewallRule -ErrorAction SilentlyContinue |
        Where-Object { $_.DisplayName -like "BF Source Relay*" -or $_.DisplayGroup -eq "BF Source Relays" } |
        Select-Object DisplayName, Enabled, Direction, Action, Profile
)

$sshConnection = [string]$env:SSH_CONNECTION
$sshClientAddress = $null
if ($sshConnection) {
    $sshClientAddress = ($sshConnection -split "\s+")[0]
}

[ordered]@{
    checked_at = (Get-Date).ToString("s")
    computer_name = $env:COMPUTERNAME
    ssh_connection_present = [bool]$sshConnection
    ssh_client_address = $sshClientAddress
    targets = $targets
    relay_listeners = @(Get-ListenerSnapshot -Ports $relayPorts)
    protected_listeners = @(Get-ListenerSnapshot -Ports $protectedPorts)
    portproxy = $portProxyText
    ip_helper = if ($ipHelper) {
        [ordered]@{ status = [string]$ipHelper.Status; start_type = [string]$ipHelper.StartType }
    } else { $null }
    firewall_rules = $firewallRules
    http_probes = @(
        Invoke-HttpProbe -Url "http://127.0.0.1:18080/imes.web/"
        Invoke-HttpProbe -Url "http://10.30.220.12:18080/imes.web/"
    )
} | ConvertTo-Json -Depth 8
