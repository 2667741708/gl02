[CmdletBinding()]
param(
    [string]$OutputDirectory = '.tmp\hcz-rule-sensitivity-20260811'
)

$ErrorActionPreference = 'Stop'
if ($PSVersionTable.PSEdition -ne 'Core' -or $PSVersionTable.PSVersion.Major -lt 7) {
    throw 'This preparation requires PowerShell 7 Core or later.'
}
$Utf8NoBom = [Text.UTF8Encoding]::new($false)
[Console]::InputEncoding = $Utf8NoBom
[Console]::OutputEncoding = $Utf8NoBom
$OutputEncoding = $Utf8NoBom
$PSDefaultParameterValues['*:Encoding'] = 'utf8'

$RequirementId = 'REQ-HCZ-RULE-SENSITIVITY-20260811'
$Root = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '..')).Path
$OutputDirectory = Join-Path $Root $OutputDirectory
$SpecPath = Join-Path $OutputDirectory 'release-spec.json'
$ManifestPath = Join-Path $OutputDirectory 'prepared-release.json'
$ManifestTool = Join-Path $Root '.codex\skills\deploy-8093-guarded-update\scripts\release_manifest.py'
$RemoteRoot = 'F:\高炉炼铁项目-real-sensor-v2_V4_8093_PREVIEW'
$RemoteStage = 'C:\Users\Administrator\AppData\Local\Temp\hcz_rule_sensitivity_20260811'
$Python = (Get-Command -Name python -ErrorAction Stop).Source

New-Item -ItemType Directory -Path $OutputDirectory -Force | Out-Null

Push-Location -LiteralPath $Root
try {
    & $Python -m pytest -q -p no:cacheprovider tests\test_hcz_upward_expert_rule.py tests\test_hcz_upward_rule_api.py
    if ($LASTEXITCODE -ne 0) { throw 'Focused HCZ tests failed.' }

    & $Python -m ruff check '炉况规则引擎\features\hcz_upward_expert_rule.py' '高炉前端数据\智能助手\backend\hcz_upward_rule_api.py' tests\test_hcz_upward_expert_rule.py tests\test_hcz_upward_rule_api.py
    if ($LASTEXITCODE -ne 0) { throw 'Ruff validation failed.' }

    & $Python -m py_compile '炉况规则引擎\features\hcz_upward_expert_rule.py' '高炉前端数据\智能助手\backend\hcz_upward_rule_api.py' '高炉前端数据\智能助手\backend\ollama_proxy_server.py'
    if ($LASTEXITCODE -ne 0) { throw 'Python syntax validation failed.' }

    & node --check '高炉前端数据\assets\hcz-upward-rule.js'
    if ($LASTEXITCODE -ne 0) { throw 'Browser JavaScript syntax validation failed.' }
    & node --check 'tools\verify_hcz_upward_rule_ui.cjs'
    if ($LASTEXITCODE -ne 0) { throw 'Browser verifier syntax validation failed.' }

    $PreviousPlaywrightPackage = $env:PLAYWRIGHT_NODE_PACKAGE
    if (-not $PreviousPlaywrightPackage) {
        $BundledPlaywright = 'C:\Users\hmw20\AppData\Roaming\Python\Python313\site-packages\playwright\driver\package'
        if (Test-Path -LiteralPath $BundledPlaywright -PathType Container) {
            $env:PLAYWRIGHT_NODE_PACKAGE = $BundledPlaywright
        }
    }
    try {
        & node 'tools\verify_hcz_upward_rule_ui.cjs'
        if ($LASTEXITCODE -ne 0) { throw 'Standard 17-combination browser validation failed.' }
    }
    finally {
        $env:PLAYWRIGHT_NODE_PACKAGE = $PreviousPlaywrightPackage
    }

    $Artifacts = @(
        [ordered]@{
            local_path = (Resolve-Path -LiteralPath '炉况规则引擎\features\hcz_upward_expert_rule.py').Path
            stage = "$RemoteStage\hcz_upward_expert_rule.py"
            target = "$RemoteRoot\炉况规则引擎\features\hcz_upward_expert_rule.py"
            baseline_sha256 = @('58CF0632BA26A4E8314E8867B598D9285E5235D7F733DEC5BF9722D36EEEEF25')
            allow_create = $false
            markers = @('gl02.hcz-rule-sensitivity.v1', 'evaluate_hcz_rule_sensitivity')
        },
        [ordered]@{
            local_path = (Resolve-Path -LiteralPath '高炉前端数据\智能助手\backend\hcz_upward_rule_api.py').Path
            stage = "$RemoteStage\hcz_upward_rule_api.py"
            target = "$RemoteRoot\高炉前端数据\智能助手\backend\hcz_upward_rule_api.py"
            baseline_sha256 = @('D9F8D8EE6E4649136FC2053664B543C9D3FDFB9582937B0B4CC76DB0544855BB')
            allow_create = $false
            markers = @('/api/hcz-rule-sensitivity', 'gas_utilisation_normalised')
        },
        [ordered]@{
            local_path = (Resolve-Path -LiteralPath '高炉前端数据\智能助手\backend\ollama_proxy_server.py').Path
            stage = "$RemoteStage\ollama_proxy_server.py"
            target = "$RemoteRoot\高炉前端数据\智能助手\backend\ollama_proxy_server.py"
            baseline_sha256 = @('083BA652DD9AEB84BF736A6CA9DCA45ECB1C25C84743E8152AB6E5364E80E0D9')
            allow_create = $false
            markers = @('/api/hcz-rule-sensitivity', 'handle_hcz_rule_sensitivity')
        },
        [ordered]@{
            local_path = (Resolve-Path -LiteralPath '高炉前端数据\hcz_upward_rule.html').Path
            stage = "$RemoteStage\hcz_upward_rule.html"
            target = "$RemoteRoot\高炉前端数据\hcz_upward_rule.html"
            baseline_sha256 = @('56411A656AB0787E0887EAFE3611224D7B64D9F2D3AFDF46A5FCD347FF809F0C')
            allow_create = $false
            markers = @('REQ-HCZ-RULE-SENSITIVITY-20260811', '20260811-sensitivity-r1')
        },
        [ordered]@{
            local_path = (Resolve-Path -LiteralPath '高炉前端数据\assets\hcz-upward-rule.js').Path
            stage = "$RemoteStage\hcz-upward-rule.js"
            target = "$RemoteRoot\高炉前端数据\assets\hcz-upward-rule.js"
            baseline_sha256 = @('DFF9F31E8AAC1BE72AA975FF3CD1C984FD80BE03305DA67A6410E1846EA58138')
            allow_create = $false
            markers = @('/api/hcz-rule-sensitivity', 'valueUnitText', '个百分点')
        },
        [ordered]@{
            local_path = (Resolve-Path -LiteralPath '高炉前端数据\assets\hcz-upward-rule.css').Path
            stage = "$RemoteStage\hcz-upward-rule.css"
            target = "$RemoteRoot\高炉前端数据\assets\hcz-upward-rule.css"
            baseline_sha256 = @('38C5317EE3D780902E01F59F044B90EFAB4F34F1BCCFE08FF5F3C99D6F6A60C9')
            allow_create = $false
            markers = @('REQ-HCZ-RULE-SENSITIVITY-20260811')
        }
    )

    $SourcePaths = @(
        '炉况规则引擎\features\hcz_upward_expert_rule.py',
        '高炉前端数据\智能助手\backend\hcz_upward_rule_api.py',
        '高炉前端数据\智能助手\backend\ollama_proxy_server.py',
        '高炉前端数据\hcz_upward_rule.html',
        '高炉前端数据\assets\hcz-upward-rule.js',
        '高炉前端数据\assets\hcz-upward-rule.css',
        'tests\test_hcz_upward_expert_rule.py',
        'tests\test_hcz_upward_rule_api.py',
        'tools\verify_hcz_upward_rule_ui.cjs',
        'tools\remote_probe_hcz_rule_sensitivity_8093.ps1',
        'tools\remote_guarded_deploy_hcz_rule_sensitivity_8093.ps1',
        'tools\deploy_hcz_rule_sensitivity_22012.ps1',
        'tools\prepare_hcz_rule_sensitivity_8093_release.ps1'
    ) | ForEach-Object { (Resolve-Path -LiteralPath $_).Path }

    $Spec = [ordered]@{
        schema = 'bf.deploy.release-spec.v1'
        requirement_id = $RequirementId
        validation_tier = 'standard'
        production_root = $RemoteRoot
        sources = $SourcePaths
        artifacts = $Artifacts
        validations = @(
            [ordered]@{ id = 'focused-tests'; kind = 'deterministic'; status = 'passed'; evidence = '15 focused tests passed' },
            [ordered]@{ id = 'lint-and-syntax'; kind = 'deterministic'; status = 'passed'; evidence = 'ruff, py_compile, and node --check passed' },
            [ordered]@{ id = 'standard-browser-matrix'; kind = 'deterministic'; status = 'passed'; evidence = '17 browser/viewport combinations passed, including GasUtil percent display' },
            [ordered]@{ id = 'luna-diff-review'; kind = 'semantic'; status = 'passed'; model = 'gpt-5.6-luna'; reasoning_effort = 'low'; evidence = 'read-only bounded review PASS' },
            [ordered]@{ id = 'remote-readonly-preflight'; kind = 'readonly_remote'; status = 'passed'; evidence = 'service, page, six baselines, current API, and protected PIDs verified' }
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
        validation_tier = 'standard'
        artifact_count = $Artifacts.Count
        spec = $SpecPath
        manifest = $ManifestPath
    } | ConvertTo-Json -Depth 4
}
finally {
    Pop-Location
}
