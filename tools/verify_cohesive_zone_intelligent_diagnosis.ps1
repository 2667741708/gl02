[CmdletBinding()]
param(
    [string]$PythonExecutable = 'python'
)

if ($PSVersionTable.PSEdition -ne 'Core' -or $PSVersionTable.PSVersion.Major -lt 7) {
    throw 'PowerShell 7 Core is required.'
}

$utf8 = [Text.UTF8Encoding]::new($false)
[Console]::InputEncoding = $utf8
[Console]::OutputEncoding = $utf8
$OutputEncoding = $utf8
$PSDefaultParameterValues['*:Encoding'] = 'utf8'

$pythonCommand = Get-Command -Name $PythonExecutable -ErrorAction Stop
$python = $pythonCommand.Source

& $python -m py_compile `
    '.\炉况规则引擎\features\cohesive_zone_intelligent_diagnosis.py' `
    '.\tools\run_cohesive_zone_intelligent_diagnosis.py' `
    '.\tests\test_cohesive_zone_intelligent_diagnosis.py'
if ($LASTEXITCODE -ne 0) {
    throw "py_compile failed with exit code $LASTEXITCODE"
}

& $python -m pytest `
    '.\tests\test_cohesive_zone_intelligent_diagnosis.py' `
    '.\tests\test_cohesive_zone_estimator.py' `
    --basetemp '.\.tmp_pytest_cohesive_zone_intelligent_diagnosis' `
    -q
if ($LASTEXITCODE -ne 0) {
    throw "pytest failed with exit code $LASTEXITCODE"
}

& $python '.\tools\run_cohesive_zone_intelligent_diagnosis.py' --help
if ($LASTEXITCODE -ne 0) {
    throw "CLI help failed with exit code $LASTEXITCODE"
}

Write-Output 'cohesive_zone_intelligent_diagnosis_ok=true'
