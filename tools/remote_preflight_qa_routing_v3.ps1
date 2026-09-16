[CmdletBinding()]
param([ValidateSet('V3','V4','V5','V6','V7','V8','V9','V10','V11','V12','V13','V14','V15')][string]$Version = 'V3')

$ErrorActionPreference = 'Stop'
if ($PSVersionTable.PSEdition -ne 'Core' -or $PSVersionTable.PSVersion.Major -lt 7) {
    throw 'PowerShell 7 Core or later is required.'
}
$Utf8NoBom = [Text.UTF8Encoding]::new($false)
[Console]::InputEncoding = $Utf8NoBom
[Console]::OutputEncoding = $Utf8NoBom
$OutputEncoding = $Utf8NoBom
$PSDefaultParameterValues['*:Encoding'] = 'utf8'
$env:PYTHONUTF8 = '1'
$env:PYTHONIOENCODING = 'utf-8'

$StageRoot = 'C:\Users\Administrator\AppData\Local\Temp\qa-routing-v3-20260916-r1'
if ($Version -eq 'V4') { $StageRoot = 'C:\Users\Administrator\AppData\Local\Temp\qa-routing-v4-20260916-r1' }
if ($Version -eq 'V5') { $StageRoot = 'C:\Users\Administrator\AppData\Local\Temp\qa-routing-v5-20260916-r1' }
if ($Version -eq 'V6') { $StageRoot = 'C:\Users\Administrator\AppData\Local\Temp\qa-routing-v6-20260916-r1' }
if ($Version -eq 'V7') { $StageRoot = 'C:\Users\Administrator\AppData\Local\Temp\qa-routing-v7-20260916-r1' }
if ($Version -eq 'V8') { $StageRoot = 'C:\Users\Administrator\AppData\Local\Temp\qa-routing-v8-20260916-r1' }
if ($Version -eq 'V9') { $StageRoot = 'C:\Users\Administrator\AppData\Local\Temp\qa-routing-v9-20260916-r1' }
if ($Version -eq 'V10') { $StageRoot = 'C:\Users\Administrator\AppData\Local\Temp\qa-routing-v10-20260916-r1' }
if ($Version -eq 'V11') { $StageRoot = 'C:\Users\Administrator\AppData\Local\Temp\qa-routing-v11-20260916-r1' }
if ($Version -eq 'V12') { $StageRoot = 'C:\Users\Administrator\AppData\Local\Temp\qa-routing-v12-20260916-r1' }
if ($Version -eq 'V13') { $StageRoot = 'C:\Users\Administrator\AppData\Local\Temp\qa-routing-v13-20260916-r1' }
if ($Version -eq 'V14') { $StageRoot = 'C:/Users/Administrator/AppData/Local/Temp/qa-routing-v14-20260916-r1' }
if ($Version -eq 'V15') { $StageRoot = 'C:/Users/Administrator/AppData/Local/Temp/qa-routing-v15-20260916-r1' }
$Python = 'C:\Program Files\Python311\python.exe'
$Guard = Join-Path $StageRoot 'git_record_guard.py'
$Expectation = Join-Path $StageRoot 'recordability-expectation.json'
$Output = Join-Path $StageRoot 'git-recordability.json'

foreach ($Path in @($Python, $Guard, $Expectation)) {
    if (-not (Test-Path -LiteralPath $Path)) { throw "Missing preflight input: $Path" }
}
$Lines = @(& $Python -X utf8 $Guard preflight-candidate --expectation $Expectation)
if ($LASTEXITCODE -ne 0) { throw "Git recordability preflight failed: $($Lines -join ' ')" }
$Text = ($Lines -join "`n").Trim()
$Evidence = $Text | ConvertFrom-Json
if (-not $Evidence.ok -or $Evidence.action -ne 'recordable') {
    throw "Git recordability action is not recordable: $($Evidence.action)"
}
[IO.File]::WriteAllText($Output, $Text + "`n", $Utf8NoBom)
$Evidence | ConvertTo-Json -Depth 12
