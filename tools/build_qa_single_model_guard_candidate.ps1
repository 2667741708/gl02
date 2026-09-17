[CmdletBinding()]
param([Parameter(Mandatory)][string]$Baseline,[Parameter(Mandatory)][string]$Output,
      [ValidatePattern('^[a-fA-F0-9]{64}$')][string]$ExpectedBaselineHash='856f38b6edb088327e2138b88e68961db1a153b451aedb6709bea9fd2a8e99fa')
$ErrorActionPreference='Stop'
if ($PSVersionTable.PSEdition -ne 'Core' -or $PSVersionTable.PSVersion.Major -lt 7) { throw 'PowerShell 7 required' }
$Utf8=[Text.UTF8Encoding]::new($false)
[Console]::InputEncoding=$Utf8
[Console]::OutputEncoding=$Utf8
$OutputEncoding=$Utf8
$PSDefaultParameterValues['*:Encoding']='utf8'
if ((Get-FileHash -LiteralPath $Baseline -Algorithm SHA256).Hash -ne $ExpectedBaselineHash) { throw 'Verified manager baseline changed' }
if (Test-Path -LiteralPath $Output) { throw 'Frozen candidate exists; no overwrite' }
$Workspace=[IO.Path]::GetFullPath((Split-Path -Parent $PSScriptRoot))
$ResolvedOutput=[IO.Path]::GetFullPath($Output)
if (-not $ResolvedOutput.StartsWith($Workspace+[IO.Path]::DirectorySeparatorChar,[StringComparison]::OrdinalIgnoreCase)) { throw 'Only local workspace candidate output allowed' }
function Get-ParsedFunctions([string]$Text) {
    $Tokens=$null
    $Errors=$null
    $Ast=[Management.Automation.Language.Parser]::ParseInput($Text,[ref]$Tokens,[ref]$Errors)
    if ($Errors.Count) { throw 'PowerShell source parse failed' }
    return @{ast=$Ast;functions=@($Ast.FindAll({param($N) $N -is [Management.Automation.Language.FunctionDefinitionAst]},$true))}
}
$Before=[IO.File]::ReadAllText((Resolve-Path -LiteralPath $Baseline).Path,$Utf8)
$Parsed=Get-ParsedFunctions $Before
$Guard=[IO.File]::ReadAllText((Join-Path $PSScriptRoot 'qa_single_model_guard_functions.ps1'),$Utf8)
$GuardParsed=Get-ParsedFunctions $Guard
$Changed=@('Activate-Model','Initialize-State','Invoke-Switch','Invoke-Sanitize','Invoke-Repair')
$Old=@($Parsed.functions | Where-Object Name -in $Changed)
if ($Old.Count -ne $Changed.Count) { throw 'Unexpected old guard inventory' }
$Policy=@($GuardParsed.functions | Where-Object Name -notin $Changed)
if ($Policy.Count -ne 5 -or $GuardParsed.functions.Count -ne 10) { throw 'Unexpected fixed guard inventory' }
$Candidate=$Before
foreach ($Node in @($Old | Sort-Object { $_.Extent.StartOffset } -Descending)) {
    $Replacement=@($GuardParsed.functions | Where-Object Name -eq $Node.Name)
    if ($Replacement.Count -ne 1) { throw 'Replacement missing' }
    $Text=$Replacement[0].Extent.Text
    if ($Node.Name -eq 'Activate-Model') { $Text=($Policy | ForEach-Object {$_.Extent.Text}) -join "`n`n"; $Text+="`n`n"+$Replacement[0].Extent.Text }
    $Span=$Node.Extent
    $Candidate=$Candidate.Substring(0,$Span.StartOffset)+$Text+$Candidate.Substring($Span.EndOffset)
}
$After=Get-ParsedFunctions $Candidate
$Protected=0
foreach ($Function in $Parsed.functions) {
    if ($Function.Name -in $Changed) { continue }
    $Match=@($After.functions | Where-Object Name -eq $Function.Name)
    if ($Match.Count -ne 1 -or $Match[0].Extent.Text -ne $Function.Extent.Text) { throw "Unrelated function changed: $($Function.Name)" }
    $Protected++
}
$TopBefore=@($Parsed.ast.EndBlock.Statements | Where-Object {$_ -isnot [Management.Automation.Language.FunctionDefinitionAst]} | ForEach-Object {$_.Extent.Text})
$TopAfter=@($After.ast.EndBlock.Statements | Where-Object {$_ -isnot [Management.Automation.Language.FunctionDefinitionAst]} | ForEach-Object {$_.Extent.Text})
if (($TopBefore|ConvertTo-Json -Compress) -ne ($TopAfter|ConvertTo-Json -Compress)) { throw 'Top-level mutex or action dispatch changed' }
New-Item -ItemType Directory -Path (Split-Path -Parent $ResolvedOutput) -Force | Out-Null
[IO.File]::WriteAllText($ResolvedOutput,$Candidate.Replace("`r`n","`n"),$Utf8)
@{ok=$true;policy='one_identical_base_no_switch_no_fallback';base_digest='e4ad74c41d68de1c8004419d8141a2b2df2275fa08f0dcf326ca0e63fb6d8124';baseline_sha256=$ExpectedBaselineHash;candidate_sha256=(Get-FileHash -LiteralPath $ResolvedOutput -Algorithm SHA256).Hash.ToLowerInvariant();changed_functions=$Changed;protected_functions=$Protected;new_functions=5;remote_execution=$false} | ConvertTo-Json
