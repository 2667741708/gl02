$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"
$OutputEncoding = [Console]::OutputEncoding = [Text.UTF8Encoding]::new($false)

$ProjectRoot = if ($env:BF_8095_PROJECT_ROOT) {
    $env:BF_8095_PROJECT_ROOT
} else {
    "F:\高炉炼铁项目-real-sensor-v2_V4_8093_PREVIEW"
}
$StageRoot = if ($env:BF_8095_FOCUS_STAGE_ROOT) {
    $env:BF_8095_FOCUS_STAGE_ROOT
} else {
    "$env:LOCALAPPDATA\Temp\bf3d_8095_focus_guard"
}

$frontendRoot = Join-Path $ProjectRoot "高炉前端数据"
$target8095 = Join-Path $frontendRoot "frontend_dashboard_v3.8095_preview.server.html"
$target8094 = Join-Path $frontendRoot "frontend_dashboard_v3.8094_preview.server.html"
$stageGuard = Join-Path $StageRoot "bf3d-billboard-focus-guard-8095.js"
$targetGuard = Join-Path $frontendRoot "assets\bf3d-billboard-focus-guard-8095.js"
$sharedAdapter = Join-Path $frontendRoot "assets\bf3d-furnace-body-billboard-adapter.js"
$stamp = Get-Date -Format "yyyyMMdd_HHmmss"
$cacheVersion = "8095-focus-guard-r1-$stamp"
$backupRoot = Join-Path $ProjectRoot "backups\8095_billboard_focus_guard_$stamp"
$resultPath = Join-Path $backupRoot "deployment_result.json"

function Get-ListenerPid {
    param([int]$Port)
    $listener = Get-NetTCPConnection -State Listen -LocalPort $Port -ErrorAction SilentlyContinue |
        Select-Object -First 1
    if ($listener) { return [int]$listener.OwningProcess }
    return 0
}

function Write-Result {
    param([hashtable]$Result)
    New-Item -ItemType Directory -Path $backupRoot -Force | Out-Null
    $Result | ConvertTo-Json -Depth 12 |
        Set-Content -LiteralPath $resultPath -Encoding UTF8
}

foreach ($path in @($target8095, $target8094, $stageGuard, $sharedAdapter)) {
    if (-not (Test-Path -LiteralPath $path -PathType Leaf)) {
        throw "Required file is missing: $path"
    }
}

$guardText = Get-Content -LiteralPath $stageGuard -Raw -Encoding UTF8
foreach ($marker in @(
    "__BF3D_BILLBOARD_FOCUS_GUARD_8095__",
    "focusById",
    "firstShellHit",
    "constrainCameraMove",
    "exitFocus",
    "IMG2THREEJS_FITTED_GL02_SHELL"
)) {
    if (-not $guardText.Contains($marker)) {
        throw "Focus guard marker is missing: $marker"
    }
}

$pid8094Before = Get-ListenerPid 8094
$pid8095Before = Get-ListenerPid 8095
if (-not $pid8094Before -or -not $pid8095Before) {
    throw "8094 and 8095 must both be listening before this frontend-only deployment"
}
$hash8094Before = (Get-FileHash -LiteralPath $target8094 -Algorithm SHA256).Hash

New-Item -ItemType Directory -Path $backupRoot -Force | Out-Null
Copy-Item -LiteralPath $target8095 -Destination (Join-Path $backupRoot "frontend_dashboard_v3.8095_preview.server.html") -Force
if (Test-Path -LiteralPath $targetGuard) {
    Copy-Item -LiteralPath $targetGuard -Destination (Join-Path $backupRoot "bf3d-billboard-focus-guard-8095.js") -Force
}

$result = [ordered]@{
    ok = $false
    requirement_id = "REQ-BF3D-8095-BILLBOARD-FOCUS-GUARD-20260726"
    started_at = (Get-Date).ToString("o")
    backup_root = $backupRoot
    target_8095 = $target8095
    target_guard = $targetGuard
    cache_version = $cacheVersion
    pid_8094_before = $pid8094Before
    pid_8095_before = $pid8095Before
    pid_8094_after = 0
    pid_8095_after = 0
    hash_8094_before = $hash8094Before
    hash_8094_after = ""
    http_8095 = 0
    http_guard = 0
    rolled_back = $false
    error = ""
}

try {
    Copy-Item -LiteralPath $stageGuard -Destination $targetGuard -Force
    $html = Get-Content -LiteralPath $target8095 -Raw -Encoding UTF8
    $sharedReference = "assets/bf3d-furnace-body-billboard-adapter.js?v=$cacheVersion"
    $guardReference = "assets/bf3d-billboard-focus-guard-8095.js?v=$cacheVersion"

    $html = [regex]::Replace(
        $html,
        "\s*<script\s+type=[`"']module[`"']\s+src=[`"']assets/bf3d-furnace-body-billboard-adapter\.js(?:\?v=[^`"']*)?[`"']></script>",
        "",
        [Text.RegularExpressions.RegexOptions]::IgnoreCase
    )
    $html = [regex]::Replace(
        $html,
        "\s*<script\s+type=[`"']module[`"']\s+src=[`"']assets/bf3d-billboard-focus-guard-8095\.js(?:\?v=[^`"']*)?[`"']></script>",
        "",
        [Text.RegularExpressions.RegexOptions]::IgnoreCase
    )
    $html = [regex]::Replace(
        $html,
        "\s*<script\s+id=[`"']bf3d-8095-model-route[`"']>.*?</script>",
        "",
        [Text.RegularExpressions.RegexOptions]::IgnoreCase -bor
            [Text.RegularExpressions.RegexOptions]::Singleline
    )
    $modelRoute = @"
  <script id="bf3d-8095-model-route">
    (() => {
      const missingModel = "models/gl02_blast_furnace_structural_review.v1.glb";
      const stableModel = "models/gl02_blast_furnace.glb";
      const rewriteModelUrl = value => String(value).includes(missingModel)
        ? String(value).replace(missingModel, stableModel)
        : value;
      const nativeFetch = window.fetch?.bind(window);
      if (nativeFetch) {
        window.fetch = (input, init) => {
          if (typeof input === "string" || input instanceof URL) {
            return nativeFetch(rewriteModelUrl(input), init);
          }
          if (input instanceof Request && input.url.includes(missingModel)) {
            return nativeFetch(new Request(rewriteModelUrl(input.url), input), init);
          }
          return nativeFetch(input, init);
        };
      }
      const nativeOpen = XMLHttpRequest.prototype.open;
      XMLHttpRequest.prototype.open = function (method, url, ...rest) {
        return nativeOpen.call(this, method, rewriteModelUrl(url), ...rest);
      };
      window.__BF3D_8095_MODEL_ROUTE__ = {
        schema: "bf3d.model-route.8095.v1",
        requested: missingModel,
        resolved: stableModel,
      };
    })();
  </script>
"@
    $babelPattern = "<script type=`"text/babel`" data-presets=`"typescript,react`">"
    if ($html -notmatch [regex]::Escape($babelPattern)) {
        throw "8095 HTML is missing the React bootstrap script"
    }
    $html = $html.Replace($babelPattern, "$modelRoute`r`n  $babelPattern")
    $injection = @"
  <script type="module" src="$sharedReference"></script>
  <script type="module" src="$guardReference"></script>
"@
    if ($html -notmatch "</body>") {
        throw "8095 HTML is missing </body>"
    }
    $html = $html -replace "</body>", "$injection`r`n</body>"
    [IO.File]::WriteAllText($target8095, $html, [Text.UTF8Encoding]::new($false))

    $page = Invoke-WebRequest -UseBasicParsing -Uri "http://127.0.0.1:8095/?focus_guard=$stamp" -TimeoutSec 3
    $guard = Invoke-WebRequest -UseBasicParsing -Uri "http://127.0.0.1:8095/$guardReference" -TimeoutSec 3
    $result.http_8095 = [int]$page.StatusCode
    $result.http_guard = [int]$guard.StatusCode
    if (
        $page.StatusCode -ne 200 -or
        $page.Content -notmatch [regex]::Escape("bf3d-8095-model-route") -or
        $page.Content -notmatch [regex]::Escape("models/gl02_blast_furnace.glb") -or
        $page.Content -notmatch [regex]::Escape($sharedReference) -or
        $page.Content -notmatch [regex]::Escape($guardReference) -or
        $guard.Content -notmatch [regex]::Escape("__BF3D_BILLBOARD_FOCUS_GUARD_8095__")
    ) {
        throw "8095 did not serve the focus-guard contract"
    }

    $result.pid_8094_after = Get-ListenerPid 8094
    $result.pid_8095_after = Get-ListenerPid 8095
    $result.hash_8094_after = (Get-FileHash -LiteralPath $target8094 -Algorithm SHA256).Hash
    if (
        $result.pid_8094_after -ne $pid8094Before -or
        $result.pid_8095_after -ne $pid8095Before -or
        $result.hash_8094_after -ne $hash8094Before
    ) {
        throw "Frontend-only deployment changed an existing listener or the 8094 HTML"
    }

    $result.ok = $true
    $result.finished_at = (Get-Date).ToString("o")
    Write-Result $result
    $result | ConvertTo-Json -Depth 12
}
catch {
    $result.error = $_.Exception.Message
    $result.rolled_back = $true
    Copy-Item -LiteralPath (Join-Path $backupRoot "frontend_dashboard_v3.8095_preview.server.html") -Destination $target8095 -Force
    $guardBackup = Join-Path $backupRoot "bf3d-billboard-focus-guard-8095.js"
    if (Test-Path -LiteralPath $guardBackup) {
        Copy-Item -LiteralPath $guardBackup -Destination $targetGuard -Force
    }
    elseif (Test-Path -LiteralPath $targetGuard) {
        Remove-Item -LiteralPath $targetGuard -Force
    }
    $result.finished_at = (Get-Date).ToString("o")
    Write-Result $result
    throw
}
