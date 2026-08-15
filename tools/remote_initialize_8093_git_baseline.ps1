[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [ValidatePattern('^[A-Za-z0-9._-]+$')]
    [string]$ExecutionId,
    [string]$Root = 'F:\高炉炼铁项目-real-sensor-v2_V4_8093_PREVIEW',
    [string]$GitExe = 'F:\Tools\PortableGit\cmd\git.exe',
    [string]$GitDir = 'F:\BF_Git\V4_8093_PREVIEW.git',
    [string]$RequirementId = 'OPS-22012-GIT-BASELINE-20260814'
)

$ErrorActionPreference = 'Stop'
if ($PSVersionTable.PSEdition -ne 'Core' -or $PSVersionTable.PSVersion.Major -lt 7) {
    throw 'PowerShell 7 Core or later is required.'
}
$Utf8NoBom = [Text.UTF8Encoding]::new($false)
[Console]::InputEncoding = $Utf8NoBom
[Console]::OutputEncoding = $Utf8NoBom
$OutputEncoding = $Utf8NoBom
$Mutex = $null
$LockTaken = $false
$AllowedExtensions = @('.py', '.ps1', '.js', '.css', '.html', '.sql', '.json', '.yaml', '.yml', '.md')
$AllowedRoots = @('高炉前端数据\智能助手', '高炉前端数据\assets', '自动诊断服务', 'tools')
$ExcludedSegments = @(
    '\logs\', '\backups\', '\__pycache__\', '\.git\', '\data\', '\node_modules\',
    '\.pytest_', '\archive\', '\runtime\', '\service_configs\'
)
$ExcludedNamePattern = '(?i)(\.env$|password|passwd|credential|cookie|token|secret|private.?key|storage.?state)'
$RequiredTrackedPaths = @(
    '高炉前端数据\智能助手\backend\ollama_proxy_server.py',
    '高炉前端数据\智能助手\backend\mcp_host\client_manager.py',
    '高炉前端数据\智能助手\backend\mcp_host\cross_source_executor.py'
)

function Get-PortPid {
    param([int]$Port)
    $Row = Get-NetTCPConnection -State Listen -LocalPort $Port -ErrorAction SilentlyContinue |
        Sort-Object OwningProcess |
        Select-Object -First 1
    if ($Row) { return [int]$Row.OwningProcess }
    return $null
}

function Get-RuntimeSnapshot {
    $Rows = [ordered]@{}
    foreach ($Port in @(8093, 8094, 8768, 8770, 5432, 11434)) {
        $Rows[[string]$Port] = Get-PortPid -Port $Port
    }
    return $Rows
}

function Invoke-Git {
    param([Parameter(ValueFromRemainingArguments = $true)][string[]]$Arguments)
    $Output = & $GitExe @Arguments 2>&1
    if ($LASTEXITCODE -ne 0) {
        throw "git $($Arguments -join ' ') failed: $($Output | Out-String)"
    }
    return ($Output | Out-String).Trim()
}

function Get-SensitiveRuleIds {
    param([string]$Content)
    $Rules = [Collections.Generic.HashSet[string]]::new([StringComparer]::Ordinal)
    if ($Content -match '-----BEGIN (?:RSA |EC |OPENSSH |DSA )?PRIVATE KEY-----') {
        [void]$Rules.Add('private_key_pem')
    }
    if ($Content -match '(?i)(?:postgres(?:ql)?|mysql|mongodb(?:\+srv)?|redis|https?)://[^/\s:@]+:[^@\s/]+@') {
        [void]$Rules.Add('credentialed_uri')
    }
    if ($Content -match '(?im)\b(?:password|passwd|pwd|token|secret|api[_-]?key|apikey)\b\s*[:=]\s*["''][^"''\r\n]{4,}["'']') {
        [void]$Rules.Add('literal_secret_assignment')
    }
    if ($Content -match '(?im)\b(?:password|pwd)\s*=\s*(?!\{|\$|%|str\(|os\.|env\b)[^;\r\n]{4,};') {
        [void]$Rules.Add('connection_string_password')
    }
    if ($Content -match '(?im)\bAuthorization\s*[:=]\s*["'']?Bearer\s+[A-Za-z0-9._~-]{16,}') {
        [void]$Rules.Add('bearer_token')
    }
    return @($Rules | Sort-Object)
}

try {
    if (-not (Test-Path -LiteralPath $Root -PathType Container)) {
        throw "Production root not found: $Root"
    }
    if (-not (Test-Path -LiteralPath $GitExe -PathType Leaf)) {
        throw "Portable Git not found: $GitExe"
    }
    $GitVersion = (& $GitExe --version 2>&1 | Out-String).Trim()
    if ($GitVersion -notmatch '^git version ') {
        throw "Invalid Git runtime: $GitVersion"
    }
    $Before = Get-RuntimeSnapshot
    foreach ($Port in @(8093, 8094, 8768, 8770, 5432, 11434)) {
        if (-not $Before[[string]$Port]) {
            throw "Required listener missing before baseline: $Port"
        }
    }

    $Mutex = [Threading.Mutex]::new($false, 'Global\BFV4PreviewProxy8093Deployment')
    try {
        $LockTaken = $Mutex.WaitOne(0)
    } catch [Threading.AbandonedMutexException] {
        $LockTaken = $true
    }
    if (-not $LockTaken) {
        throw 'Another 8093 deployment or production maintenance operation owns the global mutex.'
    }

    $GitPointer = Join-Path $Root '.git'
    if ((Test-Path -LiteralPath $GitPointer) -or (Test-Path -LiteralPath $GitDir)) {
        if (-not ((Test-Path -LiteralPath $GitPointer) -and (Test-Path -LiteralPath $GitDir))) {
            throw 'Partial Git baseline state detected; refusing to overwrite it.'
        }
        $Head = Invoke-Git -C $Root rev-parse HEAD
        $AfterExisting = Get-RuntimeSnapshot
        [ordered]@{
            ok = $true
            schema = 'bf.8093-production-git-baseline.v1'
            requirement_id = $RequirementId
            execution_id = $ExecutionId
            git_version = $GitVersion
            git_dir = $GitDir
            head = $Head
            changed = $false
            runtime_before = $Before
            runtime_after = $AfterExisting
            service_restart_performed = $false
        } | ConvertTo-Json -Depth 6
        return
    }

    $Candidates = [Collections.Generic.List[object]]::new()
    foreach ($AllowedRoot in $AllowedRoots) {
        $Path = Join-Path $Root $AllowedRoot
        if (-not (Test-Path -LiteralPath $Path -PathType Container)) { continue }
        foreach ($File in Get-ChildItem -LiteralPath $Path -Recurse -File -ErrorAction SilentlyContinue) {
            $Full = $File.FullName
            $Relative = $Full.Substring($Root.TrimEnd('\').Length + 1)
            $Excluded = $File.Length -gt 5MB
            foreach ($Segment in $ExcludedSegments) {
                if ($Full.IndexOf($Segment, [StringComparison]::OrdinalIgnoreCase) -ge 0) {
                    $Excluded = $true
                    break
                }
            }
            if ($Excluded) { continue }
            if ($AllowedExtensions -notcontains $File.Extension.ToLowerInvariant()) { continue }
            if ($Relative -match $ExcludedNamePattern) { continue }
            $Candidates.Add([pscustomobject]@{ Full = $Full; Relative = $Relative; Length = [long]$File.Length })
        }
    }

    $Safe = [Collections.Generic.List[object]]::new()
    $ExcludedSensitive = [Collections.Generic.List[object]]::new()
    foreach ($Candidate in ($Candidates | Sort-Object Relative -Unique)) {
        try {
            $Content = Get-Content -LiteralPath $Candidate.Full -Raw -Encoding utf8
            $RuleIds = @(Get-SensitiveRuleIds -Content $Content)
        } catch {
            $RuleIds = @('read_error')
        }
        if ($RuleIds.Count -gt 0) {
            $ExcludedSensitive.Add([ordered]@{ path = $Candidate.Relative; rule_ids = $RuleIds })
            continue
        }
        $Safe.Add([ordered]@{
            path = $Candidate.Relative
            length = $Candidate.Length
            sha256 = (Get-FileHash -LiteralPath $Candidate.Full -Algorithm SHA256).Hash
        })
    }
    foreach ($RequiredPath in $RequiredTrackedPaths) {
        if (-not ($Safe | Where-Object { $_['path'] -eq $RequiredPath })) {
            throw "Required 8093 deployment target did not pass the sensitive baseline scan: $RequiredPath"
        }
    }
    if ($Safe.Count -lt 10) {
        throw "Safe baseline is unexpectedly small: $($Safe.Count) files"
    }

    $GitParent = Split-Path -Parent $GitDir
    New-Item -ItemType Directory -Path $GitParent -Force | Out-Null
    Invoke-Git init "--separate-git-dir=$GitDir" --initial-branch=production-8093 $Root | Out-Null
    Invoke-Git -C $Root config user.name '220.12 Production Baseline' | Out-Null
    Invoke-Git -C $Root config user.email 'production-baseline@local.invalid' | Out-Null
    Invoke-Git -C $Root config core.autocrlf false | Out-Null
    Invoke-Git -C $Root config core.quotepath false | Out-Null
    Invoke-Git -C $Root config core.longpaths true | Out-Null

    $InfoExclude = Join-Path $GitDir 'info\exclude'
    $ExcludeText = @(
        'logs/', 'backups/', '__pycache__/', '*.pyc', '*.pyo', 'node_modules/',
        'data/', '*.env', '*.local.env', '*storage*state*', '*credential*', '*password*', '*secret*'
    ) -join "`n"
    [IO.File]::WriteAllText($InfoExclude, $ExcludeText + "`n", $Utf8NoBom)

    $PathspecFile = Join-Path $GitParent "baseline-paths-$ExecutionId.nul"
    $PathspecText = (($Safe | ForEach-Object { [string]$_['path'] -replace '\\', '/' }) -join [char]0) + [char]0
    [IO.File]::WriteAllBytes($PathspecFile, $Utf8NoBom.GetBytes($PathspecText))
    Invoke-Git -C $Root add "--pathspec-from-file=$PathspecFile" --pathspec-file-nul | Out-Null
    Invoke-Git -C $Root diff --cached --check | Out-Null
    $StagedCountText = Invoke-Git -C $Root diff --cached --name-only
    $StagedCount = @($StagedCountText -split "`r?`n" | Where-Object { $_ }).Count
    if ($StagedCount -ne $Safe.Count) {
        throw "Staged path count mismatch: expected=$($Safe.Count) actual=$StagedCount"
    }
    $CommitMessage = "baseline: reviewed 220.12 production source [$RequirementId] [$ExecutionId]"
    Invoke-Git -C $Root commit -m $CommitMessage | Out-Null
    $Head = Invoke-Git -C $Root rev-parse HEAD
    $Tag = "prod-8093/20260814-initial-$($Head.Substring(0, 12))"
    Invoke-Git -C $Root tag -a $Tag -m "Reviewed 220.12 production baseline $ExecutionId" | Out-Null

    $ManifestPath = Join-Path $GitParent "V4_8093_PREVIEW.baseline.$ExecutionId.json"
    $Manifest = [ordered]@{
        schema = 'bf.8093-production-git-baseline-manifest.v1'
        requirement_id = $RequirementId
        execution_id = $ExecutionId
        created_at = (Get-Date).ToString('o')
        root = $Root
        git_dir = $GitDir
        head = $Head
        tag = $Tag
        git_version = $GitVersion
        candidate_count = $Candidates.Count
        tracked_count = $Safe.Count
        excluded_sensitive_count = $ExcludedSensitive.Count
        excluded_sensitive = $ExcludedSensitive
        tracked_files = $Safe
        sensitive_values_recorded = $false
    }
    [IO.File]::WriteAllText($ManifestPath, ($Manifest | ConvertTo-Json -Depth 8), $Utf8NoBom)
    Remove-Item -LiteralPath $PathspecFile -Force

    $After = Get-RuntimeSnapshot
    foreach ($Port in @(8093, 8094, 8768, 8770, 5432, 11434)) {
        if ($Before[[string]$Port] -ne $After[[string]$Port]) {
            throw "Runtime PID changed while creating Git baseline: port=$Port before=$($Before[[string]$Port]) after=$($After[[string]$Port])"
        }
    }
    [ordered]@{
        ok = $true
        schema = 'bf.8093-production-git-baseline.v1'
        requirement_id = $RequirementId
        execution_id = $ExecutionId
        git_version = $GitVersion
        root = $Root
        git_dir = $GitDir
        head = $Head
        tag = $Tag
        candidate_count = $Candidates.Count
        tracked_count = $Safe.Count
        excluded_sensitive_count = $ExcludedSensitive.Count
        excluded_sensitive = $ExcludedSensitive
        manifest_path = $ManifestPath
        runtime_before = $Before
        runtime_after = $After
        service_restart_performed = $false
    } | ConvertTo-Json -Depth 7
} finally {
    if ($LockTaken -and $Mutex) {
        $Mutex.ReleaseMutex()
    }
    if ($Mutex) {
        $Mutex.Dispose()
    }
}
