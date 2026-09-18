[CmdletBinding()]
param()
$ErrorActionPreference = 'Stop'
if ($PSVersionTable.PSEdition -ne 'Core' -or $PSVersionTable.PSVersion.Major -lt 7) {
    throw 'PowerShell 7 Core required.'
}
$Utf8 = [Text.UTF8Encoding]::new($false)
[Console]::InputEncoding = $Utf8
[Console]::OutputEncoding = $Utf8
$OutputEncoding = $Utf8
$PSDefaultParameterValues['*:Encoding'] = 'utf8'
$env:PYTHONUTF8 = '1'
$env:PYTHONIOENCODING = 'utf-8'
$Root = 'F:/高炉炼铁项目-real-sensor-v2_V4_8093_PREVIEW'
$Stage = 'C:/Users/Administrator/AppData/Local/Temp/qa-paired-v21-20260916-r2'
$Starter = Join-Path $Stage 'start_qa_batch_independent.ps1'
$Output = Join-Path $Root 'logs/qa_paired_v21_20260916_r2'
$PlanHash = '8F54088673A5B9B5D6C156C0ABF536704008184A029CE252AC80D1042FA9AAC2'
$BatchHash = '6CE94C62DA0487376223DACDBB72D0075812208FE5194D958F5CF65C2667F9D6'
$StarterHash = '80849AF1C05240A9EB7A0441B28AE2261D33DF9CDEF5A41BF534DC037AD23DF3'
if ((Get-FileHash -LiteralPath $Starter -Algorithm SHA256).Hash -ne $StarterHash) {
    throw 'Independent starter hash changed.'
}
$Pwsh = 'C:/Program Files/PowerShell/7/pwsh.exe'
& $Pwsh -NoLogo -NoProfile -File $Starter -Root $Root -Stage $Stage -Output $Output -PlanHash $PlanHash -BatchHash $BatchHash
if ($LASTEXITCODE -ne 0) { throw 'Batch launch failed; inspect evidence before any retry.' }
