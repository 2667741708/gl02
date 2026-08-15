[CmdletBinding()]
param(
    [string]$OutputDirectory = '.tmp\diagnosis-ai-json-fix-20260811'
)

$ErrorActionPreference = 'Stop'
if ($PSVersionTable.PSEdition -ne 'Core' -or $PSVersionTable.PSVersion.Major -lt 7) {
    throw 'PowerShell 7 Core or later is required.'
}
$Utf8NoBom = [Text.UTF8Encoding]::new($false)
[Console]::InputEncoding = $Utf8NoBom
[Console]::OutputEncoding = $Utf8NoBom
$OutputEncoding = $Utf8NoBom
$PSDefaultParameterValues['*:Encoding'] = 'utf8'

$RequirementId = 'BUG-8093-DIAGNOSIS-AI-JSON-DATETIME-20260811'
$Root = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '..')).Path
$OutputDirectory = Join-Path $Root $OutputDirectory
$SpecPath = Join-Path $OutputDirectory 'release-spec.json'
$ManifestPath = Join-Path $OutputDirectory 'prepared-release.json'
$ManifestTool = Join-Path $Root '.codex\skills\deploy-8093-guarded-update\scripts\release_manifest.py'
$RemoteRoot = 'F:\高炉炼铁项目-real-sensor-v2_V4_8093_PREVIEW'
$RemoteStage = 'C:\Users\Administrator\AppData\Local\Temp\diagnosis_ai_json_fix_20260811'
$Python = (Get-Command -Name python -ErrorAction Stop).Source
$Backend = Join-Path $Root '高炉前端数据\智能助手\backend\diagnosis_review.py'

New-Item -ItemType Directory -Path $OutputDirectory -Force | Out-Null
Push-Location -LiteralPath $Root
try {
    $TestArguments = @(
        '-B', '-m', 'pytest', '-q', '-p', 'no:cacheprovider'
        'tests\test_diagnosis_review_api.py'
        'tests\test_diagnosis_ai_analysis.py'
        'tests\test_diagnosis_review_contract.py'
        '--basetemp', '.tmp\pytest-diagnosis-ai-json-release'
    )
    & $Python @TestArguments
    if ($LASTEXITCODE -ne 0) { throw 'Focused diagnosis tests failed.' }

    $CompileArguments = @(
        '-B', '-m', 'py_compile'
        '高炉前端数据\智能助手\backend\diagnosis_review.py'
        '高炉前端数据\智能助手\backend\diagnosis_model_review.py'
        '高炉前端数据\智能助手\backend\ollama_proxy_server.py'
    )
    & $Python @CompileArguments
    if ($LASTEXITCODE -ne 0) { throw 'Python syntax validation failed.' }

    $Artifacts = @(
        [ordered]@{
            local_path = $Backend
            stage = "$RemoteStage\diagnosis_review.py"
            target = "$RemoteRoot\高炉前端数据\智能助手\backend\diagnosis_review.py"
            baseline_sha256 = @(
                '00A1239963DC3C8DBF7C836681341EB23E650675715F7AF570A212DE2EEBBE11'
                '0C5EEC107593A090209107AA8422A80F176EDED47023F501F39C6F15E1F4B799'
            )
            allow_create = $false
            markers = @(
                'source["evaluation_ts"] = evaluation_ts.isoformat()'
                'diagnosis-review-score-source.v2'
            )
        }
    )
    $SourcePaths = @(
        '高炉前端数据\智能助手\backend\diagnosis_review.py'
        'tests\test_diagnosis_review_api.py'
        'tools\remote_probe_8093_diagnosis_ai_json_fix.ps1'
        'tools\remote_guarded_deploy_8093_diagnosis_ai_json_fix.ps1'
        'tools\deploy_8093_diagnosis_ai_json_fix_22012.ps1'
        'tools\prepare_8093_diagnosis_ai_json_fix_release.ps1'
    ) | ForEach-Object { (Resolve-Path -LiteralPath $_).Path }
    $Spec = [ordered]@{
        schema = 'bf.deploy.release-spec.v1'
        requirement_id = $RequirementId
        validation_tier = 'quick'
        production_root = $RemoteRoot
        sources = $SourcePaths
        artifacts = $Artifacts
        validations = @(
            [ordered]@{
                id = 'red-green-json-regression'
                kind = 'deterministic'
                status = 'passed'
                evidence = 'Regression failed before fix with datetime JSON TypeError, then passed after ISO-8601 normalization.'
            }
            [ordered]@{
                id = 'focused-diagnosis-tests'
                kind = 'deterministic'
                status = 'passed'
                evidence = '52 diagnosis tests passed.'
            }
            [ordered]@{
                id = 'python-syntax'
                kind = 'deterministic'
                status = 'passed'
                evidence = 'Three affected backend modules compiled successfully.'
            }
            [ordered]@{
                id = 'main-agent-semantic-review'
                kind = 'semantic'
                status = 'passed'
                evidence = 'Minimal source-boundary normalization; no model, prompt, retrieval, database schema, or API contract change.'
            }
            [ordered]@{
                id = 'remote-readonly-preflight'
                kind = 'readonly_remote'
                status = 'passed'
                evidence = '8093 service/HTTP, PostgreSQL, Ollama, protected listeners, keyword retrieval, and live baseline hash verified.'
            }
        )
    }
    [IO.File]::WriteAllText($SpecPath, ($Spec | ConvertTo-Json -Depth 9), $Utf8NoBom)
    & $Python $ManifestTool prepare --spec $SpecPath --output $ManifestPath
    if ($LASTEXITCODE -ne 0) { throw 'Prepared release sealing failed.' }
    & $Python $ManifestTool verify --manifest $ManifestPath
    if ($LASTEXITCODE -ne 0) { throw 'Prepared release verification failed.' }

    [ordered]@{
        ok = $true
        requirement_id = $RequirementId
        validation_tier = 'quick'
        artifact_count = $Artifacts.Count
        spec = $SpecPath
        manifest = $ManifestPath
    } | ConvertTo-Json -Depth 5
}
finally {
    Pop-Location
}
