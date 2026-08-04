param(
    [string[]]$Targets = @("10.10.181.209:8080", "10.10.181.195:5432"),
    [string]$OutFile = ""
)

$ErrorActionPreference = "Stop"
$OutputEncoding = [Console]::OutputEncoding = [Text.UTF8Encoding]::new($false)

function Get-TargetRoute {
    param([string]$Address, [int]$Port)

    $routeRows = @(Find-NetRoute -RemoteIPAddress $Address -ErrorAction Stop)
    $route = $routeRows | Where-Object { $_.DestinationPrefix } | Select-Object -First 1
    if (-not $route) {
        $route = $routeRows | Select-Object -Last 1
    }
    $tcp = Test-NetConnection -ComputerName $Address -Port $Port -InformationLevel Quiet -WarningAction SilentlyContinue
    [ordered]@{
        address = $Address
        port = $Port
        tcp_ok = [bool]$tcp
        interface_alias = $route.InterfaceAlias
        interface_index = $route.InterfaceIndex
        destination_prefix = $route.DestinationPrefix
        next_hop = $route.NextHop
        route_metric = $route.RouteMetric
        source_address = ($routeRows | Where-Object { $_.IPAddress } | Select-Object -First 1).IPAddress
        specific_vpn_route = [bool]($route.DestinationPrefix -and $route.DestinationPrefix -ne "0.0.0.0/0" -and $route.InterfaceAlias -notmatch "WLAN|Wi-Fi|Ethernet")
    }
}

$internet = Get-ItemProperty -LiteralPath "HKCU:\Software\Microsoft\Windows\CurrentVersion\Internet Settings"
$proxyOverride = [string]$internet.ProxyOverride
$targetResults = @()
foreach ($target in $Targets) {
    if ($target -notmatch "^(?<address>[^:]+):(?<port>\d+)$") {
        throw "Invalid target '$target'; expected IP:PORT"
    }
    $targetResults += Get-TargetRoute -Address $Matches.address -Port ([int]$Matches.port)
}

$vpnAdapters = @(Get-NetAdapter -IncludeHidden -ErrorAction SilentlyContinue |
    Where-Object { $_.InterfaceDescription -match "VPN|SSL|Sangfor|EasyConnect|TAP|TUN" -or $_.Name -match "VPN|SSL|Sangfor|EasyConnect" } |
    Select-Object Name, InterfaceDescription, Status, ifIndex)
$vpnProcesses = @(Get-Process -ErrorAction SilentlyContinue |
    Where-Object { $_.ProcessName -match "vpn|ssl|sangfor|easyconnect" } |
    Select-Object ProcessName, Id, Path)
$clashProcesses = @(Get-Process -ErrorAction SilentlyContinue |
    Where-Object { $_.ProcessName -match "clash|mihomo" } |
    Select-Object ProcessName, Id, Path)

$result = [ordered]@{
    checked_at = (Get-Date).ToString("o")
    targets = $targetResults
    system_proxy = [ordered]@{
        enabled = [bool]$internet.ProxyEnable
        server = [string]$internet.ProxyServer
        override = $proxyOverride
        private_10_bypassed = [bool]($proxyOverride -match "(^|;)10\.\*(;|$)")
    }
    clash_processes = $clashProcesses
    vpn_adapters = $vpnAdapters
    vpn_processes = $vpnProcesses
    diagnosis = if (($targetResults | Where-Object { $_.specific_vpn_route }).Count -eq 0) {
        "No target has a specific VPN route; traffic is following the ordinary/default route."
    } else {
        "A specific VPN route exists; continue with firewall/server/credential checks."
    }
}

$json = $result | ConvertTo-Json -Depth 8
if ($OutFile) {
    $parent = Split-Path -Parent $OutFile
    if ($parent -and -not (Test-Path -LiteralPath $parent)) {
        New-Item -ItemType Directory -Path $parent | Out-Null
    }
    Set-Content -LiteralPath $OutFile -Value $json -Encoding utf8
}
$json
