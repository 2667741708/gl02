$ErrorActionPreference = 'Stop'
if ($PSVersionTable.PSEdition -ne 'Core' -or $PSVersionTable.PSVersion.Major -lt 7) {
    throw 'PowerShell 7 Core or later is required.'
}
$Candidates = @(
    'C:\Program Files\Git\cmd\git.exe',
    'C:\Program Files\Git\bin\git.exe',
    'C:\Program Files (x86)\Git\cmd\git.exe',
    'D:\Program Files\Git\cmd\git.exe',
    'C:\Users\Administrator\AppData\Local\Programs\Git\cmd\git.exe',
    'C:\ProgramData\chocolatey\bin\git.exe',
    'C:\Users\Administrator\scoop\apps\git\current\cmd\git.exe',
    'C:\ProgramData\anaconda3\Library\bin\git.exe',
    'D:\ProgramData\anaconda3\Library\bin\git.exe',
    'F:\tools\PortableGit\cmd\git.exe',
    'F:\PortableGit\cmd\git.exe'
)
$RegistryPaths = @(
    'HKLM:\SOFTWARE\GitForWindows',
    'HKLM:\SOFTWARE\WOW6432Node\GitForWindows',
    'HKCU:\SOFTWARE\GitForWindows'
)
foreach ($RegistryPath in $RegistryPaths) {
    $InstallPath = (Get-ItemProperty -LiteralPath $RegistryPath -ErrorAction SilentlyContinue).InstallPath
    if ($InstallPath) { $Candidates += (Join-Path $InstallPath 'cmd\git.exe') }
}
$Found = @($Candidates | Where-Object { Test-Path -LiteralPath $_ -PathType Leaf })
$UninstallRoots = @(
    'HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall',
    'HKLM:\SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall',
    'HKCU:\SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall'
)
$InstalledGitRecords = @(
    foreach ($Root in $UninstallRoots) {
        Get-ChildItem -LiteralPath $Root -ErrorAction SilentlyContinue | ForEach-Object {
            $Item = Get-ItemProperty -LiteralPath $_.PSPath -ErrorAction SilentlyContinue
            if ([string]$Item.DisplayName -match '(?i)\bgit\b') {
                [ordered]@{
                    display_name = [string]$Item.DisplayName
                    display_version = [string]$Item.DisplayVersion
                    install_location_exists = [bool]($Item.InstallLocation -and (Test-Path -LiteralPath $Item.InstallLocation))
                }
            }
        }
    }
)
$HistoryFiles = @(
    'C:\Users\Administrator\AppData\Roaming\Microsoft\Windows\PowerShell\PSReadLine\ConsoleHost_history.txt',
    'C:\Users\Administrator\AppData\Roaming\Microsoft\PowerShell\PSReadLine\ConsoleHost_history.txt'
)
$HistorySummary = [ordered]@{
    files_present = 0
    git_init_matches = 0
    git_install_matches = 0
    git_worktree_matches = 0
}
foreach ($HistoryFile in $HistoryFiles) {
    if (-not (Test-Path -LiteralPath $HistoryFile -PathType Leaf)) { continue }
    $HistorySummary.files_present++
    $HistoryText = Get-Content -LiteralPath $HistoryFile -Raw -ErrorAction SilentlyContinue
    $HistorySummary.git_init_matches += @([regex]::Matches($HistoryText, '(?im)^\s*git(?:\.exe)?\s+init(?:\s|$)')).Count
    $HistorySummary.git_install_matches += @([regex]::Matches($HistoryText, '(?im)^.*(?:winget|choco|scoop).*(?:install|add).*\bgit\b.*$')).Count
    $HistorySummary.git_worktree_matches += @([regex]::Matches($HistoryText, '(?im)^\s*git(?:\.exe)?\s+worktree(?:\s|$)')).Count
}
[ordered]@{
    schema = 'bf.remote-git-probe.v1'
    found = $Found
    path_command = [string](Get-Command git.exe -ErrorAction SilentlyContinue | Select-Object -ExpandProperty Source -First 1)
    dot_git_exists = Test-Path -LiteralPath 'F:\高炉炼铁项目-real-sensor-v2_V4_8093_PREVIEW\.git'
    parent_dot_git = @(
        'F:\.git',
        'F:\高炉炼铁项目-real-sensor-v2_V4_8093_PREVIEW\.git',
        'F:\高炉炼铁项目-real-sensor-v2_V4_8093_PREVIEW\.gitfile'
    ) | Where-Object { Test-Path -LiteralPath $_ }
    installed_git_records = $InstalledGitRecords
    history_summary = $HistorySummary
    write_performed = $false
} | ConvertTo-Json -Depth 4
