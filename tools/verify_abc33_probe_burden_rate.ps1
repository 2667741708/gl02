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

python -m pytest -q tests/test_abc_burden_rate.py tests/test_abc_rule_engine.py tests/test_abc_public_review_labels.py
if ($LASTEXITCODE -ne 0) { throw "ABC33 probe burden-rate tests failed: $LASTEXITCODE" }
python -m py_compile '自动诊断服务/abc_burden_rate.py' '自动诊断服务/abc_public_review.py' '自动诊断服务/abc_feature_builder.py'
if ($LASTEXITCODE -ne 0) { throw "ABC33 probe burden-rate compile failed: $LASTEXITCODE" }
python -m json.tool '自动诊断服务/config/abc_furnace_rules.v1.json' *> $null
if ($LASTEXITCODE -ne 0) { throw "ABC33 probe burden-rate config JSON failed: $LASTEXITCODE" }
python tools/audit_8093_probe_burden_rate_http.py
if ($LASTEXITCODE -ne 0) { throw "ABC33 live probe burden-rate audit failed: $LASTEXITCODE" }
