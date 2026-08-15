[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)][string]$ExecutionId,
    [Parameter(Mandatory = $true)][string]$ExpectedScriptSha256,
    [string]$ExpectedDesiredSha256 = '',
    [switch]$DryRun
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

$RequirementId = 'REQ-QA-SESSION-LOGIN-BRIDGE-20260812'
$Root = 'F:\高炉炼铁项目-real-sensor-v2_V4_8093_PREVIEW'
$Target = Join-Path $Root '高炉前端数据\frontend_dashboard_v3.server.html'
$ServiceName = 'BFV4PreviewProxy8093'
$Manager = Join-Path $Root 'tools\manage_22012_managed_services.ps1'
$ConfigPath = Join-Path $Root 'tools\service_configs\22012_BFV4PreviewProxy8093.json'
$Pwsh = 'C:\Program Files\PowerShell\7\pwsh.exe'
$ScriptPath = $PSCommandPath
$ExpectedBaseline = '62FE1AEB042CC88EEE4976D5188DD6919DB6C0D48A27F8CAB7AA16683928EDB5'
$ProtectedPorts = @(8094, 8768, 8770, 5432, 11434)
$Stamp = Get-Date -Format 'yyyyMMdd_HHmmss'
$Backup = Join-Path $Root "backups\qa_session_login_bridge_8093_$Stamp\frontend_dashboard_v3.server.html"

function Replace-Once {
    param([string]$Text, [string]$Old, [string]$New, [string]$Label)
    $First = $Text.IndexOf($Old, [StringComparison]::Ordinal)
    if ($First -lt 0) { throw "Missing patch anchor: $Label" }
    $Second = $Text.IndexOf($Old, $First + $Old.Length, [StringComparison]::Ordinal)
    if ($Second -ge 0) { throw "Patch anchor is not unique: $Label" }
    return $Text.Substring(0, $First) + $New + $Text.Substring($First + $Old.Length)
}

function Get-ListenerPid {
    param([int]$Port)
    $Listener = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue |
        Select-Object -First 1
    if ($Listener) { return [int]$Listener.OwningProcess }
    return $null
}

function Get-ProtectedPortMap {
    $Map = [ordered]@{}
    foreach ($Port in $ProtectedPorts) { $Map[[string]$Port] = Get-ListenerPid -Port $Port }
    return $Map
}

function Wait-ServiceState {
    param([string]$Desired, [int]$TimeoutSeconds = 45)
    $Deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    do {
        if ((Get-Service -Name $ServiceName -ErrorAction Stop).Status.ToString() -eq $Desired) { return }
        Start-Sleep -Milliseconds 250
    } while ((Get-Date) -lt $Deadline)
    throw "$ServiceName did not reach $Desired."
}

function Wait-PortState {
    param([bool]$Listening, [int]$TimeoutSeconds = 45)
    $Deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    do {
        if ([bool](Get-ListenerPid -Port 8093) -eq $Listening) { return }
        Start-Sleep -Milliseconds 250
    } while ((Get-Date) -lt $Deadline)
    throw "Port 8093 did not reach listening=$Listening."
}

function Stop-8093 {
    & $Pwsh -NoLogo -NoProfile -File $Manager -Action stop -ConfigPath $ConfigPath | Out-Null
    Wait-ServiceState -Desired 'Stopped'
    Wait-PortState -Listening $false
}

function Start-8093 {
    & $Pwsh -NoLogo -NoProfile -File $Manager -Action start -ConfigPath $ConfigPath | Out-Null
    Wait-ServiceState -Desired 'Running'
    Wait-PortState -Listening $true
}

foreach ($Required in @($Target, $Manager, $ConfigPath, $Pwsh, $ScriptPath)) {
    if (-not (Test-Path -LiteralPath $Required -PathType Leaf)) { throw "Missing required file: $Required" }
}
$ActualScriptHash = (Get-FileHash -LiteralPath $ScriptPath -Algorithm SHA256).Hash
if ($ActualScriptHash -ne $ExpectedScriptSha256) { throw 'Deployment script SHA-256 mismatch.' }
$BaselineHash = (Get-FileHash -LiteralPath $Target -Algorithm SHA256).Hash
if ($BaselineHash -ne $ExpectedBaseline) { throw "Unreviewed production baseline: $BaselineHash" }

$Text = Get-Content -LiteralPath $Target -Raw -Encoding UTF8
if ($Text.Contains($RequirementId)) { throw 'Patch marker already exists; use a no-op verification path.' }

$OldJson = @'
    async function qaServerJson(url, options = {}) { const method = String(options.method || 'GET').toUpperCase(), attempts = method === 'GET' ? 3 : 1; let res = null; for (let attempt = 1; attempt <= attempts; attempt += 1) { try { res = await fetch(url, { headers: { 'Content-Type': 'application/json', ...(options.headers || {}) }, ...options }); break } catch (error) { if (attempt >= attempts) throw new Error(qaFriendlyFetchError(error, method !== 'GET')); await qaRetryDelay(attempt * 1500) } } let data = null; try { data = await res.json() } catch (e) { } if (!res.ok || data?.ok === false) { throw new Error(data?.error || `接口 HTTP ${res.status}`) } return data }
'@
$NewJson = @'
    function qaApiError(data, status, fallback = '') { const error = new Error(data?.message || data?.error || fallback || `接口 HTTP ${status}`); error.code = String(data?.error || ''); error.status = Number(status || 0); return error }
    function qaIsSessionRequired(error) { return error?.code === 'qa_session_required' || Number(error?.status) === 401 || Number(error?.status) === 403 }
    async function qaServerJson(url, options = {}) { const method = String(options.method || 'GET').toUpperCase(), attempts = method === 'GET' ? 3 : 1; let res = null; for (let attempt = 1; attempt <= attempts; attempt += 1) { try { res = await fetch(url, { credentials: 'same-origin', headers: { 'Content-Type': 'application/json', ...(options.headers || {}) }, ...options }); break } catch (error) { if (attempt >= attempts) throw new Error(qaFriendlyFetchError(error, method !== 'GET')); await qaRetryDelay(attempt * 1500) } } let data = null; try { data = await res.json() } catch (e) { } if (!res.ok || data?.ok === false) { throw qaApiError(data, res.status) } return data }
'@
$Text = Replace-Once $Text $OldJson.TrimEnd() $NewJson.TrimEnd() 'typed JSON errors'

$OldFetch = "      let res; try { res = await fetch('/api/qa/chat', { method: 'POST', headers: { 'Content-Type': 'application/json', 'Accept': 'text/event-stream' }, body: JSON.stringify({ ...payload, stream: true }) }) } catch (error) { throw new Error(qaFriendlyFetchError(error, true)) }"
$NewFetch = "      let res; try { res = await fetch('/api/qa/chat', { method: 'POST', credentials: 'same-origin', headers: { 'Content-Type': 'application/json', 'Accept': 'text/event-stream' }, body: JSON.stringify({ ...payload, stream: true }) }) } catch (error) { throw new Error(qaFriendlyFetchError(error, true)) }"
$Text = Replace-Once $Text $OldFetch $NewFetch 'SSE same-origin credentials'
$Text = Replace-Once $Text "      if (!res.ok) throw new Error(``接口 HTTP `${res.status}``);" "      if (!res.ok) { let data = null; try { data = await res.json() } catch (e) { } throw qaApiError(data, res.status) }" 'SSE HTTP error body'
$Text = Replace-Once $Text "if (errorData) throw new Error(errorData.error || '问答流式接口失败');" "if (errorData) throw qaApiError(errorData, errorData.status || 0, '问答流式接口失败');" 'SSE event error'

$LoginBridge = @'
    /* REQ-QA-SESSION-LOGIN-BRIDGE-20260812: keep QA protected while making session recovery explicit. */
    function qaEnsureSessionLoginStyle() { if (document.getElementById('qa-session-login-style')) return; const el = document.createElement('style'); el.id = 'qa-session-login-style'; el.textContent = `.qa-session-login-backdrop{position:absolute;inset:0;z-index:90;display:grid;place-items:center;padding:20px;background:rgba(1,10,22,.78);backdrop-filter:blur(5px)}.qa-session-login-card{width:min(430px,100%);display:grid;gap:14px;padding:22px;border:1px solid rgba(65,171,255,.55);border-radius:14px;background:#071c31;box-shadow:0 18px 60px rgba(0,0,0,.48);color:#dfefff}.qa-session-login-card h3{margin:0;color:#fff;font-size:20px}.qa-session-login-card p{margin:0;color:#9eb8d3;line-height:1.6}.qa-session-login-card label{display:grid;gap:6px;font-size:13px;color:#bdd2e7}.qa-session-login-card input{height:40px;border:1px solid rgba(93,162,220,.48);border-radius:8px;background:#031327;color:#fff;padding:0 11px;font-size:14px}.qa-session-login-card button{height:40px;border:1px solid #2c9aff;border-radius:8px;background:#1276c9;color:#fff;font-weight:800;cursor:pointer}.qa-session-login-card button:disabled{opacity:.55;cursor:not-allowed}.qa-session-login-error{color:#ff9d9d;line-height:1.5}.qa-session-login-note{font-size:12px;color:#83a5c5;line-height:1.5}`; document.head.appendChild(el) }
    function QaSessionLogin({ onAuthenticated }) { qaEnsureSessionLoginStyle(); const [username, setUsername] = useState(''), [password, setPassword] = useState(''), [busy, setBusy] = useState(false), [error, setError] = useState(''); const submit = async event => { event.preventDefault(); if (busy || !username.trim() || !password) return; setBusy(true); setError(''); try { const data = await qaServerJson('/api/auth/login', { method: 'POST', body: JSON.stringify({ username: username.trim(), password }) }); setPassword(''); if (!data?.ok) throw qaApiError(data, 401, '登录失败'); await onAuthenticated?.() } catch (e) { setPassword(''); setError(e.message || '登录失败，请检查账号和密码。') } finally { setBusy(false) } }; return <div className="qa-session-login-backdrop" role="dialog" aria-modal="true" aria-labelledby="qa-session-login-title"><form className="qa-session-login-card" onSubmit={submit}><h3 id="qa-session-login-title">登录后使用智能助手</h3><p>问答会话按操作人员隔离。当前页面没有有效登录会话，这不表示模型或代理离线。</p><label><span>账号</span><input value={username} onChange={e => setUsername(e.target.value)} autoComplete="username" autoFocus /></label><label><span>密码</span><input type="password" value={password} onChange={e => setPassword(e.target.value)} autoComplete="current-password" /></label>{error && <div className="qa-session-login-error" role="alert">{error}</div>}<button type="submit" disabled={busy || !username.trim() || !password}>{busy ? '正在登录…' : '登录并加载会话'}</button><div className="qa-session-login-note">登录凭据只提交到当前 8093 服务，不写入页面存储。登录成功后仅重新读取会话，不会自动重发之前的问题。</div></form></div> }
'@
$Text = Replace-Once $Text '    function QaProjectNavMenuV2(' ($LoginBridge.TrimEnd() + "`r`n    function QaProjectNavMenuV2(") 'login component insertion'

$TabStart = $Text.IndexOf('    function QaTab({ buf, diagnosis })', [StringComparison]::Ordinal)
$TabEnd = $Text.IndexOf('    function reportEnsureStyle()', $TabStart, [StringComparison]::Ordinal)
if ($TabStart -lt 0 -or $TabEnd -le $TabStart) { throw 'QaTab block boundaries are missing.' }
$Prefix = $Text.Substring(0, $TabStart)
$Block = $Text.Substring($TabStart, $TabEnd - $TabStart)
$Suffix = $Text.Substring($TabEnd)

$Block = Replace-Once $Block "[health, setHealth] = useState({ state: 'checking' }), [projects" "[health, setHealth] = useState({ state: 'checking' }), [authRequired, setAuthRequired] = useState(false), [projects" 'QA auth state'
$OldBootstrapCatch = 'setInput('''') } catch (e) { setErr(`代理不可达或问答服务未启动：${e.message || e}`) } finally { setBooting(false) }'
$NewBootstrapCatch = 'setInput(''''); setAuthRequired(false); return true } catch (e) { if (qaIsSessionRequired(e)) { setAuthRequired(true); setConversations([]); setActive(null); setMessages([]); setErr(''智能助手需要登录后使用。'') } else setErr(`代理不可达或问答服务未启动：${e.message || e}`); return false } finally { setBooting(false) }'
$Block = Replace-Once $Block $OldBootstrapCatch $NewBootstrapCatch 'bootstrap auth classification'
$Block = Replace-Once $Block 'loadBootstrap(false); checkHealth(); reloadProjects(); loadShortConversations(); loadPendingReport();' 'loadBootstrap(false); checkHealth(); loadShortConversations(); loadPendingReport();' 'avoid protected parallel project load'
$Block = Replace-Once $Block 'if (!text || loading) return;' 'if (!text || loading || authRequired) return;' 'block send while logged out'
$Block = Replace-Once $Block 'const now = new Date().toISOString(), pendingId = `pending_${Date.now()}`, optimistic = [...messages, { id: `local_user_${Date.now()}`' 'const now = new Date().toISOString(), stamp = Date.now(), userLocalId = `local_user_${stamp}`, pendingId = `pending_${stamp}`, optimistic = [...messages, { id: userLocalId' 'stable optimistic IDs'
$OldSendCatch = "} catch (e) { setErr(e.message || String(e)); setMessages(ms => ms.map(m => m.id === pendingId ? { ...m, content: '暂时无法连接高炉大模型服务。', streaming: false } : m)) } finally"
$NewSendCatch = "} catch (e) { if (qaIsSessionRequired(e)) { setAuthRequired(true); setInput(text); setMessages(ms => ms.filter(m => m.id !== pendingId && m.id !== userLocalId)); setErr('登录状态已过期，本次提问未发送；登录后请手动再次发送。') } else { setErr(e.message || String(e)); setMessages(ms => ms.map(m => m.id === pendingId ? { ...m, content: '暂时无法连接高炉大模型服务。', streaming: false } : m)) } } finally"
$Block = Replace-Once $Block $OldSendCatch $NewSendCatch 'expired session manual retry'
$ContextMenu = '<QaContextMenuV2 menu={menu} onClose={() => setMenu(null)} onProjectAction={runProjectAction} onConversationAction={runConversationAction} openAsset={openAsset} copyText={copyText} />'
$LoginRender = $ContextMenu + "{authRequired && <QaSessionLogin onAuthenticated={async () => { const ok = await loadBootstrap(false); if (!ok) throw new Error('当前账号没有智能助手操作权限。'); await reloadProjects(); await loadShortConversations(); setNotice('登录成功，智能助手会话已加载。') }} />}"
$Block = Replace-Once $Block $ContextMenu $LoginRender 'login dialog render'
$Block = Replace-Once $Block 'disabled={loading || !input.trim()}' 'disabled={loading || authRequired || !input.trim()}' 'send disabled while logged out'
$Text = $Prefix + $Block + $Suffix

$Temporary = "$Target.qa-session-login-$Stamp"
[IO.File]::WriteAllText($Temporary, $Text, $Utf8NoBom)
$DesiredHash = (Get-FileHash -LiteralPath $Temporary -Algorithm SHA256).Hash
if ($DryRun) {
    Remove-Item -LiteralPath $Temporary -Force
    [ordered]@{
        ok = $true
        dry_run = $true
        requirement_id = $RequirementId
        execution_id = $ExecutionId
        script_sha256 = $ActualScriptHash
        baseline_sha256 = $BaselineHash
        desired_sha256 = $DesiredHash
        production_write_performed = $false
    } | ConvertTo-Json -Depth 3
    return
}
if (-not $ExpectedDesiredSha256 -or $DesiredHash -ne $ExpectedDesiredSha256) {
    Remove-Item -LiteralPath $Temporary -Force
    throw "Prepared target hash mismatch: $DesiredHash"
}

$Mutex = [Threading.Mutex]::new($false, 'Global\BFV4PreviewProxy8093Deployment')
$MutexAcquired = $false
$GuardPaused = $false
$GuardRestored = $false
$RollbackApplied = $false
$Old8093Pid = $null
$New8093Pid = $null
$ProtectedBefore = $null
$ProtectedAfter = $null

try {
    $MutexAcquired = $Mutex.WaitOne(0)
    if (-not $MutexAcquired) { throw 'Another 8093 deployment owns the deployment mutex.' }
    $ProtectedBefore = Get-ProtectedPortMap
    foreach ($Key in $ProtectedBefore.Keys) {
        if (-not $ProtectedBefore[$Key]) { throw "Protected port $Key is not listening." }
    }
    if ((Get-Service -Name $ServiceName).Status -ne 'Running') { throw '8093 is not running.' }
    $Old8093Pid = Get-ListenerPid -Port 8093
    New-Item -ItemType Directory -Path (Split-Path -Parent $Backup) -Force | Out-Null
    Copy-Item -LiteralPath $Target -Destination $Backup -Force

    Stop-8093
    $GuardPaused = $true
    Move-Item -LiteralPath $Temporary -Destination $Target -Force
    if ((Get-FileHash -LiteralPath $Target -Algorithm SHA256).Hash -ne $ExpectedDesiredSha256) { throw 'Installed target hash mismatch.' }
    Start-8093
    $GuardRestored = $true
    $New8093Pid = Get-ListenerPid -Port 8093
    if (-not $New8093Pid -or $New8093Pid -eq $Old8093Pid) { throw '8093 listener PID did not change.' }

    $Page = Invoke-WebRequest -UseBasicParsing -Uri "http://127.0.0.1:8093/frontend_dashboard_v3.server.html?deploy=$Stamp#qa" -TimeoutSec 30
    if ($Page.StatusCode -ne 200 -or -not $Page.Content.Contains($RequirementId)) { throw '8093 page marker verification failed.' }
    $BootstrapStatus = 0
    $BootstrapBody = ''
    try {
        Invoke-WebRequest -UseBasicParsing -Uri 'http://127.0.0.1:8093/api/qa/bootstrap' -TimeoutSec 20 | Out-Null
        $BootstrapStatus = 200
    }
    catch {
        if (-not $_.Exception.Response) { throw }
        $BootstrapStatus = [int]$_.Exception.Response.StatusCode
        $BootstrapBody = $_.ErrorDetails.Message
    }
    if ($BootstrapStatus -ne 403 -or -not $BootstrapBody.Contains('qa_session_required')) { throw 'Anonymous QA session boundary changed unexpectedly.' }
    $ProtectedAfter = Get-ProtectedPortMap
    foreach ($Key in $ProtectedBefore.Keys) {
        if ($ProtectedAfter[$Key] -ne $ProtectedBefore[$Key]) { throw "Protected PID changed: $Key" }
    }

    [ordered]@{
        ok = $true
        requirement_id = $RequirementId
        execution_id = $ExecutionId
        script_sha256 = $ActualScriptHash
        baseline_sha256 = $BaselineHash
        installed_sha256 = $ExpectedDesiredSha256
        backup = $Backup
        old_8093_pid = $Old8093Pid
        new_8093_pid = $New8093Pid
        protected_before = $ProtectedBefore
        protected_after = $ProtectedAfter
        guard_paused = $GuardPaused
        guard_restored = $GuardRestored
        rollback_applied = $false
        http_8093 = [int]$Page.StatusCode
        anonymous_bootstrap_http = $BootstrapStatus
        sse_request_count = 0
    } | ConvertTo-Json -Depth 6
}
catch {
    $Failure = $_.Exception.Message
    try {
        if ($Old8093Pid -and (Get-Service -Name $ServiceName).Status -ne 'Stopped') { Stop-8093 }
        if (Test-Path -LiteralPath $Backup -PathType Leaf) {
            Copy-Item -LiteralPath $Backup -Destination $Target -Force
            $RollbackApplied = $true
        }
    }
    finally {
        if ($Old8093Pid) {
            Start-8093
            $GuardRestored = $true
        }
    }
    [ordered]@{
        ok = $false
        requirement_id = $RequirementId
        execution_id = $ExecutionId
        failure = $Failure
        guard_restored = $GuardRestored
        rollback_applied = $RollbackApplied
        listener_8093 = Get-ListenerPid -Port 8093
        sse_request_count = 0
    } | ConvertTo-Json -Depth 4 | Write-Output
    throw $Failure
}
finally {
    if (Test-Path -LiteralPath $Temporary -PathType Leaf) { Remove-Item -LiteralPath $Temporary -Force }
    if ($MutexAcquired) { $Mutex.ReleaseMutex() }
    $Mutex.Dispose()
}
