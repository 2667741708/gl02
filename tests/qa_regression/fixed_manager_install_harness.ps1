[CmdletBinding()]
param([Parameter(Mandatory)][string]$Mode)
$ErrorActionPreference='Stop'
if ($PSVersionTable.PSEdition -ne 'Core' -or $PSVersionTable.PSVersion.Major -lt 7) { throw 'PowerShell 7 required' }
$Utf8=[Text.UTF8Encoding]::new($false)
[Console]::InputEncoding=$Utf8
[Console]::OutputEncoding=$Utf8
$OutputEncoding=$Utf8
$PSDefaultParameterValues['*:Encoding']='utf8'
. (Join-Path $PSScriptRoot '../../tools/qa_fixed_manager_install_transaction.ps1')
$script:Actions=[Collections.Generic.List[string]]::new()
$script:Enabled=$Mode -ne 'original_disabled'
$Callbacks=@{
    ReadEnabled={ $script:Enabled }
    Disable={
        $script:Actions.Add('disable')
        $script:Enabled=$false
        if ($Mode -eq 'partial_disable' -and $script:Actions.Count -eq 1) { throw 'Partial disable' }
    }
    Drain={ $script:Actions.Add('drain');if ($Mode -eq 'drain_failed') { throw 'Drain failed' } }
    Preflight={ $script:Actions.Add('preflight');if ($Mode -eq 'baseline_drift') { throw 'Baseline drift' } }
    Backup={ $script:Actions.Add('backup');if ($Mode -eq 'backup_failed') { throw 'Backup failed' } }
    Install={ $script:Actions.Add('install');if ($Mode -eq 'install_failed') { throw 'Install failed' } }
    Verify={ $script:Actions.Add('verify');if ($Mode -eq 'verification_failed') { throw 'Verification failed' } }
    Rollback={ $script:Actions.Add('rollback');if ($Mode -eq 'rollback_failed') { throw 'Rollback failed' } }
    Enable={ $script:Actions.Add('enable');$script:Enabled=$true }
    Finish={param($Accepted,$Original);$script:Actions.Add('finish');$script:Accepted=$Accepted}
}
if ($Mode -eq 'rollback_failed') { $Callbacks.Verify={ $script:Actions.Add('verify');throw 'Verification failed' } }
$Failed=$false
try { Invoke-FixedManagerInstallTransaction -Callbacks $Callbacks }
catch { $Failed=$true }
@{failed=$Failed;enabled=$script:Enabled;accepted=$script:Accepted;actions=@($script:Actions)} | ConvertTo-Json -Compress
