$ErrorActionPreference = "Stop"
[Console]::OutputEncoding = [Text.UTF8Encoding]::new($false)

$ports = @(
    [ordered]@{ name = "imes_db"; host = "10.10.181.195"; port = 5432 },
    [ordered]@{ name = "imes_web"; host = "10.10.181.209"; port = 8080 },
    [ordered]@{ name = "pspace"; host = "10.22.181.243"; port = 8889 }
)
$reachability = foreach ($item in $ports) {
    [ordered]@{
        name = $item.name
        host = $item.host
        port = $item.port
        reachable = [bool](Test-NetConnection $item.host -Port $item.port -InformationLevel Quiet)
    }
}

$envNames = @(
    "IMES_DB_HOST", "IMES_DB_PORT", "IMES_DB_NAME", "IMES_DB_USER", "IMES_DB_PASSWORD",
    "IMES_OPS_DB_HOST", "IMES_OPS_DB_PORT", "IMES_OPS_DB_NAME", "IMES_OPS_DB_USER", "IMES_OPS_DB_PASSWORD",
    "IMES_LAB_DB_HOST", "IMES_LAB_DB_PORT", "IMES_LAB_DB_NAME", "IMES_LAB_DB_USER", "IMES_LAB_DB_PASSWORD"
)
$envPresence = [ordered]@{}
foreach ($name in $envNames) {
    $envPresence[$name] = [bool](Get-Item -LiteralPath ("Env:" + $name) -ErrorAction SilentlyContinue)
}

$candidateFiles = @(
    "F:\高炉炼铁项目-real-sensor-v2_V4_8093_PREVIEW\PT\imes_vastbase.local.env",
    "F:\高炉炼铁项目-real-sensor-v2_V3\PT\imes_vastbase.local.env",
    "F:\高炉炼铁项目-real-sensor-v2_V4_8093_PREVIEW\tools\imes_vastbase.local.env",
    "F:\高炉炼铁项目-real-sensor-v2_V3\tools\imes_vastbase.local.env"
)
$files = foreach ($path in $candidateFiles) {
    [ordered]@{ path = $path; exists = Test-Path -LiteralPath $path }
}

$listeners = Get-NetTCPConnection -State Listen -LocalPort 8890,8891,15433,18889,18080 -ErrorAction SilentlyContinue |
    Select-Object LocalAddress, LocalPort, OwningProcess

[ordered]@{
    reachability = $reachability
    env_presence = $envPresence
    candidate_credential_files = $files
    listeners = $listeners
    python311 = Test-Path -LiteralPath "C:\Program Files\Python311\python.exe"
} | ConvertTo-Json -Depth 6
