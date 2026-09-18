[CmdletBinding()]
param([Parameter(Mandatory)][string]$Installer,[Parameter(Mandatory)][string]$Workdir,
      [Parameter(Mandatory)][string]$Mode)
$ErrorActionPreference='Stop'
if ($PSVersionTable.PSEdition -ne 'Core' -or $PSVersionTable.PSVersion.Major -lt 7) { throw 'PowerShell 7 required' }
$Utf8=[Text.UTF8Encoding]::new($false,$true)
[Console]::InputEncoding=$Utf8
[Console]::OutputEncoding=$Utf8
$OutputEncoding=$Utf8
$PSDefaultParameterValues['*:Encoding']='utf8'
$Tokens=$null
$Errors=$null
$Ast=[Management.Automation.Language.Parser]::ParseFile($Installer,[ref]$Tokens,[ref]$Errors)
if ($Errors.Count) { throw 'Actual installer parse failed' }
$Functions=@($Ast.FindAll({param($Node) $Node -is [Management.Automation.Language.FunctionDefinitionAst] -and $Node.Name -ceq 'Invoke-ManagerAtomicReplace'},$true))
if ($Functions.Count -ne 1) { throw 'Actual atomic helper inventory changed' }
# Only this exact helper is loaded; installer top-level code, credentials and callbacks never execute.
. ([scriptblock]::Create($Functions[0].Extent.Text))
$Source=Join-Path $Workdir 'synthetic-new-manager.txt'
$Destination=Join-Path $Workdir 'synthetic-installed-manager.txt'
$Backup=Join-Path $Workdir 'synthetic-before-manager.txt'
$FailedCandidate=Join-Path $Workdir 'synthetic-failed-candidate.txt'
$State=Join-Path $Workdir 'synthetic-audit-state.txt'
if ($Mode -ne 'missing_source') { [IO.File]::WriteAllText($Source,'synthetic-new-manager-v5',$Utf8) }
if ($Mode -ne 'missing_destination') { [IO.File]::WriteAllText($Destination,'synthetic-old-manager',$Utf8) }
[IO.File]::WriteAllText($State,'synthetic-state-not-completed',$Utf8)
if ($Mode -eq 'existing_backup') { [IO.File]::WriteAllText($Backup,'synthetic-existing-backup',$Utf8) }
if ($Mode -eq 'backup_parent_missing') { $Backup=Join-Path (Join-Path $Workdir 'synthetic-missing-parent') 'backup.txt' }
if ($Mode -eq 'backup_directory') { New-Item -ItemType Directory -Path $Backup | Out-Null }
function Get-SyntheticHash {
    param([string]$Path)
    if ([IO.File]::Exists($Path)) { return (Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash.ToLowerInvariant() }
    return $null
}
$Before=@{source=Get-SyntheticHash $Source;destination=Get-SyntheticHash $Destination;backup=Get-SyntheticHash $Backup;state=Get-SyntheticHash $State}
$Failed=$false
$Completed=$false
$ErrorType=$null
$InnerType=$null
$Install=$null
try {
    switch ($Mode) {
        'old_null' { [IO.File]::Replace($Source,$Destination,$null) }
        'null_backup' { Invoke-ManagerAtomicReplace -Source $Source -Destination $Destination -DestinationBackup $null }
        'empty_backup' { Invoke-ManagerAtomicReplace -Source $Source -Destination $Destination -DestinationBackup '' }
        'whitespace_backup' { Invoke-ManagerAtomicReplace -Source $Source -Destination $Destination -DestinationBackup ' ' }
        default { Invoke-ManagerAtomicReplace -Source $Source -Destination $Destination -DestinationBackup $Backup }
    }
    $Install=@{source=Get-SyntheticHash $Source;destination=Get-SyntheticHash $Destination;backup=Get-SyntheticHash $Backup}
    if ($Mode -eq 'rollback') {
        Invoke-ManagerAtomicReplace -Source $Backup -Destination $Destination -DestinationBackup $FailedCandidate
    }
    $Completed=$true
} catch {
    $Failed=$true
    $ErrorType=$_.Exception.GetType().FullName
    if ($null -ne $_.Exception.InnerException) { $InnerType=$_.Exception.InnerException.GetType().FullName }
}
$After=@{source=Get-SyntheticHash $Source;destination=Get-SyntheticHash $Destination;backup=Get-SyntheticHash $Backup;
    failed_candidate=Get-SyntheticHash $FailedCandidate;state=Get-SyntheticHash $State}
@{failed=$Failed;completed=$Completed;error_type=$ErrorType;inner_error_type=$InnerType;before=$Before;install=$Install;after=$After;
    extracted_functions=@($Functions[0].Name);top_level_executed=$false;model_operations=0;remote_operations=0} | ConvertTo-Json -Depth 8
