[CmdletBinding()]
param(
    [Parameter(Mandatory)][string]$Baseline,
    [Parameter(Mandatory)][string]$Output,
    [ValidatePattern('^[a-fA-F0-9]{64}$')][string]$ExpectedBaselineHash='856f38b6edb088327e2138b88e68961db1a153b451aedb6709bea9fd2a8e99fa'
)
$ErrorActionPreference='Stop'
if ($PSVersionTable.PSEdition -ne 'Core' -or $PSVersionTable.PSVersion.Major -lt 7) { throw 'PowerShell 7 required' }
$Utf8=[Text.UTF8Encoding]::new($false)
[Console]::InputEncoding=$Utf8
[Console]::OutputEncoding=$Utf8
$OutputEncoding=$Utf8
$PSDefaultParameterValues['*:Encoding']='utf8'
if ((Get-FileHash -LiteralPath $Baseline -Algorithm SHA256).Hash -ne $ExpectedBaselineHash) { throw 'Read-only verified manager baseline changed' }
if (Test-Path -LiteralPath $Output) { throw 'Candidate exists; never overwrite a frozen candidate' }
$Before=[IO.File]::ReadAllText((Resolve-Path -LiteralPath $Baseline).Path, $Utf8)
$Tokens=$null
$Errors=$null
$Ast=[Management.Automation.Language.Parser]::ParseInput($Before,[ref]$Tokens,[ref]$Errors)
if ($Errors.Count) { throw 'Baseline parser failed' }
$Functions=@($Ast.FindAll({param($Node) $Node -is [Management.Automation.Language.FunctionDefinitionAst]},$true))
$Repair=@($Functions | Where-Object Name -eq 'Invoke-Repair')
$Resident=@($Functions | Where-Object Name -eq 'Test-PublicAliasResident')
$Switch=@($Functions | Where-Object Name -eq 'Invoke-Switch')
if ($Repair.Count -ne 1 -or $Resident.Count -ne 1 -or $Switch.Count -ne 1) { throw 'Unexpected function inventory' }
$Replacement=[IO.File]::ReadAllText((Join-Path $PSScriptRoot 'qa_model_repair_stable_function.ps1'),$Utf8)
$Policy=[IO.File]::ReadAllText((Join-Path $PSScriptRoot 'qa_model_repair_policy.ps1'),$Utf8)
$ResidentText=$Resident[0].Extent.Text.Replace('return @(', 'return $loaded.Count -eq 1 -and @(')
if ($ResidentText -eq $Resident[0].Extent.Text) { throw 'Residency contract shape changed' }
$SwitchText=[IO.File]::ReadAllText((Join-Path $PSScriptRoot 'qa_model_switch_stable_function.ps1'),$Utf8)
$Edits=@(
    @{Node=$Repair[0];Text=($Policy+"`n"+$Replacement)},
    @{Node=$Resident[0];Text=$ResidentText},
    @{Node=$Switch[0];Text=$SwitchText}
) | Sort-Object { $_.Node.Extent.StartOffset } -Descending
$Candidate=$Before
foreach ($Edit in $Edits) {
    $Span=$Edit.Node.Extent
    $Candidate=$Candidate.Substring(0,$Span.StartOffset)+$Edit.Text+$Candidate.Substring($Span.EndOffset)
}
$NewTokens=$null
$NewErrors=$null
$NewAst=[Management.Automation.Language.Parser]::ParseInput($Candidate,[ref]$NewTokens,[ref]$NewErrors)
if ($NewErrors.Count) { throw 'Candidate parser failed' }
$NewFunctions=@($NewAst.FindAll({param($Node) $Node -is [Management.Automation.Language.FunctionDefinitionAst]},$true))
$Changed=@('Invoke-Repair','Invoke-Switch','Test-PublicAliasResident')
$Protected=0
foreach ($Function in $Functions) {
    if ($Function.Name -in $Changed) { continue }
    $Match=@($NewFunctions | Where-Object Name -eq $Function.Name)
    if ($Match.Count -ne 1 -or $Match[0].Extent.Text -ne $Function.Extent.Text) { throw "Unrelated function changed: $($Function.Name)" }
    $Protected++
}
$TopBefore=@($Ast.EndBlock.Statements | Where-Object { $_ -isnot [Management.Automation.Language.FunctionDefinitionAst] } | ForEach-Object { $_.Extent.Text })
$TopAfter=@($NewAst.EndBlock.Statements | Where-Object { $_ -isnot [Management.Automation.Language.FunctionDefinitionAst] } | ForEach-Object { $_.Extent.Text })
if (($TopBefore | ConvertTo-Json -Compress) -ne ($TopAfter | ConvertTo-Json -Compress)) { throw 'Action dispatch, mutex or top-level behavior changed' }
$ResolvedOutput=[IO.Path]::GetFullPath($Output)
$Workspace=[IO.Path]::GetFullPath((Split-Path -Parent $PSScriptRoot))
if (-not $ResolvedOutput.StartsWith($Workspace+[IO.Path]::DirectorySeparatorChar,[StringComparison]::OrdinalIgnoreCase)) { throw 'Only local workspace candidate output allowed' }
$Parent=Split-Path -Parent $ResolvedOutput
New-Item -ItemType Directory -Path $Parent -Force | Out-Null
[IO.File]::WriteAllText($ResolvedOutput,$Candidate.Replace("`r`n","`n"),$Utf8)
@{ok=$true;baseline_sha256=$ExpectedBaselineHash;candidate_sha256=(Get-FileHash -LiteralPath $ResolvedOutput -Algorithm SHA256).Hash.ToLowerInvariant();protected_functions=$Protected;changed_functions=$Changed;new_policy_functions=4;remote_execution=$false} | ConvertTo-Json
