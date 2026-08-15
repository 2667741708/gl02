$ErrorActionPreference = 'Stop'
if ($PSVersionTable.PSEdition -ne 'Core' -or $PSVersionTable.PSVersion.Major -lt 7) {
    throw 'This verification requires PowerShell 7 Core or later.'
}
$Utf8NoBom = [Text.UTF8Encoding]::new($false)
[Console]::InputEncoding = $Utf8NoBom
[Console]::OutputEncoding = $Utf8NoBom
$OutputEncoding = $Utf8NoBom
$PSDefaultParameterValues['*:Encoding'] = 'utf8'

$Scripts = @(
    'tools\prepare_abc33_overview_entry_8093_release.ps1'
    'tools\deploy_abc33_overview_entry_22012.ps1'
    'tools\remote_guarded_deploy_abc33_overview_entry_8093.ps1'
    'tools\remote_preflight_abc33_overview_entry_8093.ps1'
)
$Results = foreach ($Script in $Scripts) {
    $Tokens = $null
    $Errors = $null
    [Management.Automation.Language.Parser]::ParseFile(
        (Resolve-Path -LiteralPath $Script).Path,
        [ref]$Tokens,
        [ref]$Errors
    ) | Out-Null
    [ordered]@{script=$Script; ok=($Errors.Count -eq 0); errors=@($Errors | ForEach-Object Message)}
}
if (@($Results | Where-Object { -not $_.ok }).Count -gt 0) {
    $Results | ConvertTo-Json -Depth 5
    throw 'ABC33 overview-entry deployment script parsing failed.'
}
[ordered]@{ok=$true; scripts=$Results} | ConvertTo-Json -Depth 5
