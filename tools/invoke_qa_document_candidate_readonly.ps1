[CmdletBinding()]
param([string]$StageRoot = 'C:/Users/Administrator/AppData/Local/Temp/qa-routing-v15-20260916-r1')
$ErrorActionPreference = 'Stop'
if ($PSVersionTable.PSEdition -ne 'Core' -or $PSVersionTable.PSVersion.Major -lt 7) { throw 'PowerShell 7 required' }
$Utf8NoBom = [Text.UTF8Encoding]::new($false)
[Console]::InputEncoding = $Utf8NoBom
[Console]::OutputEncoding = $Utf8NoBom
$OutputEncoding = $Utf8NoBom
$PSDefaultParameterValues['*:Encoding'] = 'utf8'
if ($StageRoot -notmatch '^C:/Users/Administrator/AppData/Local/Temp/qa-routing-v\d+-20260916-r1$') { throw 'Invalid reviewed candidate stage' }
$Python = 'C:/Program Files/Python311/python.exe'
$Root = 'F:/高炉炼铁项目-real-sensor-v2_V4_8093_PREVIEW'
$Checker = Join-Path $StageRoot 'check-knowledge.py'
$Candidate = Join-Path $StageRoot 'qa_document_knowledge.py'
$Cases = Join-Path $StageRoot 'knowledge-cases.json'
$ResultPath = Join-Path $StageRoot 'knowledge-readonly-result.json'
$Result = & $Python -X utf8 $Checker --root $Root --candidate-source $Candidate --cases $Cases
if ($LASTEXITCODE -ne 0) { throw 'Read-only candidate evaluation failed' }
$Json = ($Result -join "`n")
$Report = $Json | ConvertFrom-Json
if ($Report.question_posts -ne 0 -or $Report.database_writes -ne 0 -or $Report.model_calls -ne 0) { throw 'Read-only evaluation contract failed' }
[IO.File]::WriteAllText($ResultPath, $Json + "`n", $Utf8NoBom)
@{ok=$true;total=$Report.total;counts=$Report.counts;question_posts=0;model_calls=0;database_writes=0} | ConvertTo-Json -Depth 5
