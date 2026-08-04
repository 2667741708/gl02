$ErrorActionPreference = "Stop"

$profilePrefix = "F:\bf8093_near_plane_accept_20260801"
$testProcesses = Get-CimInstance -ClassName Win32_Process |
    Where-Object { $_.CommandLine -and $_.CommandLine.Contains($profilePrefix) }
$processIds = @($testProcesses | ForEach-Object { $_.ProcessId })
foreach ($processId in $processIds) {
    Stop-Process -Id $processId -Force -ErrorAction SilentlyContinue
}

$removedProfiles = @()
$profiles = Get-ChildItem -LiteralPath "F:\" -Directory -Filter "bf8093_near_plane_accept_20260801*" -ErrorAction SilentlyContinue
foreach ($profile in $profiles) {
    $resolved = (Resolve-Path -LiteralPath $profile.FullName).Path
    if ($profile.Parent.FullName -eq "F:\" -and $profile.Name.StartsWith("bf8093_near_plane_accept_20260801")) {
        Remove-Item -LiteralPath $resolved -Recurse -Force -ErrorAction SilentlyContinue
        $removedProfiles += $resolved
    }
}

[ordered]@{
    stopped_process_ids = $processIds
    removed_profiles = $removedProfiles
    remaining_process_count = @(
        Get-CimInstance -ClassName Win32_Process |
            Where-Object { $_.CommandLine -and $_.CommandLine.Contains($profilePrefix) }
    ).Count
} | ConvertTo-Json -Depth 4
