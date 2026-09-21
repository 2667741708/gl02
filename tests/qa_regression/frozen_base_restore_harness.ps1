param([string]$Controller,[string]$Mode)
$ErrorActionPreference='Stop'
$Utf8=[Text.UTF8Encoding]::new($false)
[Console]::OutputEncoding=$Utf8
$OutputEncoding=$Utf8
$Tokens=$null
$Errors=$null
$Ast=[Management.Automation.Language.Parser]::ParseFile($Controller,[ref]$Tokens,[ref]$Errors)
if ($Errors.Count) { throw 'parse_failed' }
$Nodes=@($Ast.FindAll({param($Node) $Node -is [Management.Automation.Language.FunctionDefinitionAst] -and $Node.Name -cin @('Assert-RestoreBoundary','Wait-RestoreEmpty')},$true))
if ($Nodes.Count -ne 2) { throw 'function_inventory_invalid' }
foreach ($Node in $Nodes) { . ([scriptblock]::Create($Node.Extent.Text)) }
$Good='e4ad74c41d68de1c8004419d8141a2b2df2275fa08f0dcf326ca0e63fb6d8124'
$Wrong='9111be230d48e53a385a28930fb8cf6972767c83e93c0db51f6b331a534e30fb'
$Tags=@([pscustomobject]@{name='chiqiongblastfuenace:1';digest=$Good},[pscustomobject]@{name='chiqiongblastfuenace:latest';digest=$Wrong})
$Loaded=@([pscustomobject]@{name='chiqiongblastfuenace:latest';digest=$Wrong})
$Enabled=$false
$State='1'
$script:Samples=0
$script:Pauses=0
$Failed=$false
try {
 switch ($Mode) {
  'healthy_numeric' {}
  'healthy_disabled' { $State='Disabled' }
  'enabled' { $Enabled=$true }
  'enabled_string' { $Enabled='false' }
  'running' { $State='4' }
  'unknown' { $State='0' }
  'invalid_numeric' { $State='01' }
  'wrong_source' { $Tags[0].digest=$Wrong }
  'multiple_resident' { $Loaded+=@($Loaded[0]) }
  'unknown_resident' { $Loaded=$null }
  'wait_empty' { Wait-RestoreEmpty -Observe { $script:Samples++;return ,@() } -Pause { $script:Pauses++ } -MaximumSamples 3 }
  'wait_delayed' { Wait-RestoreEmpty -Observe { $script:Samples++;if ($script:Samples -ge 3) { return ,@() };return ,$Loaded } -Pause { $script:Pauses++ } -MaximumSamples 3 }
  'wait_busy' { Wait-RestoreEmpty -Observe { $script:Samples++;return ,$Loaded } -Pause { $script:Pauses++ } -MaximumSamples 3 }
  'wait_unknown' { Wait-RestoreEmpty -Observe { $script:Samples++;return $null } -Pause { $script:Pauses++ } -MaximumSamples 3 }
  'wait_changed' { $Loaded[0].digest=$Good;Wait-RestoreEmpty -Observe { $script:Samples++;return ,$Loaded } -Pause { $script:Pauses++ } -MaximumSamples 3 }
  default { throw 'unknown_mode' }
 }
 if ($Mode -notlike 'wait_*') { Assert-RestoreBoundary $Tags $Loaded $Enabled $State }
} catch { $Failed=$true }
@{failed=$Failed;samples=$script:Samples;pauses=$script:Pauses;model_posts=0;top_level_executed=$false} | ConvertTo-Json -Compress
