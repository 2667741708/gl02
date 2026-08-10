$ErrorActionPreference='Stop'
$OutputEncoding=[Console]::OutputEncoding=[Text.UTF8Encoding]::new($false)
$response=Invoke-RestMethod -Uri 'http://127.0.0.1:8094/api/furnace-rules/latest' -Method Get -TimeoutSec 15
$rules=@($response.rules)
Write-Output ("ok="+$response.ok)
Write-Output ("state="+$response.state)
Write-Output ("evaluation_ts="+$response.evaluation_ts)
Write-Output ("rules="+$rules.Count)
Write-Output ("calculable="+@($rules|Where-Object {$_.status -ne 'needs_data'}).Count)
Write-Output ("needs_data="+@($rules|Where-Object {$_.status -eq 'needs_data'}).Count)
Write-Output ("rule_fields="+(@($rules[0].PSObject.Properties.Name)-join','))
foreach($rule in $rules){
  $missing=@($rule.missing_sensors)-join','
  Write-Output ($rule.rule_id+'|'+$rule.status+'|score='+$rule.score+'|confidence='+$rule.confidence+'|missing='+$missing)
}
