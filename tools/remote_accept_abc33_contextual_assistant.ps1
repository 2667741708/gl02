[CmdletBinding()]
param(
    [ValidateRange(1024, 65535)]
    [int]$Port = 8094,
    [switch]$SendFollowup,
    [switch]$SkipModelSse,
    [switch]$GuestShared
)

$ErrorActionPreference = 'Stop'

if ($PSVersionTable.PSEdition -ne 'Core' -or $PSVersionTable.PSVersion.Major -lt 7) {
    throw 'PowerShell 7 Core is required.'
}

$Utf8NoBom = [Text.UTF8Encoding]::new($false)
[Console]::InputEncoding = $Utf8NoBom
[Console]::OutputEncoding = $Utf8NoBom
$OutputEncoding = $Utf8NoBom
$PSDefaultParameterValues['*:Encoding'] = 'utf8'

$Root = 'F:\高炉炼铁项目-real-sensor-v2_V4_8093_PREVIEW'
$ConfigPath = Join-Path $Root 'tools\service_configs\22012_BFV4PreviewProxy8093.json'
$BaseUri = "http://127.0.0.1:$Port"
$Origin = $BaseUri
$RuleId = 'B4'
$InitialQuestion = '请解释当前炉况规则的判断依据、形成过程与处置顺序。'
$FollowupQuestion = '请用现场人员易理解的语言说明，接下来应优先观察哪些指标？'
$ProtectedPorts = if ($Port -eq 8093) { @(8094, 8768, 8770, 5432, 11434) } else { @(8093, 8768, 8770, 5432, 11434) }

function Get-ListenerPid {
    param([int]$TargetPort)
    $Listener = Get-NetTCPConnection -LocalPort $TargetPort -State Listen -ErrorAction Stop |
        Select-Object -First 1
    return [int]$Listener.OwningProcess
}

function Get-ProtectedMap {
    $Map = [ordered]@{}
    foreach ($TargetPort in $ProtectedPorts) {
        $Map[[string]$TargetPort] = Get-ListenerPid -TargetPort $TargetPort
    }
    return $Map
}

function Invoke-JsonRequest {
    param(
        [string]$Method,
        [string]$Path,
        [object]$Body,
        [Microsoft.PowerShell.Commands.WebRequestSession]$Session,
        [string]$BaseOverride = $BaseUri,
        [string]$OriginOverride = $Origin
    )
    $Arguments = @{
        Uri = $BaseOverride + $Path
        Method = $Method
        WebSession = $Session
        Headers = @{ Origin = $OriginOverride; Accept = 'application/json' }
        TimeoutSec = 60
        UseBasicParsing = $true
    }
    if ($null -ne $Body) {
        $Arguments.ContentType = 'application/json; charset=utf-8'
        $Arguments.Body = $Body | ConvertTo-Json -Depth 12 -Compress
    }
    $Response = Invoke-WebRequest @Arguments
    if ($Response.StatusCode -lt 200 -or $Response.StatusCode -ge 300) {
        throw "HTTP request failed: $Method $Path status=$($Response.StatusCode)"
    }
    return $Response.Content | ConvertFrom-Json
}

function Invoke-SseRequest {
    param(
        [object]$Body,
        [Microsoft.PowerShell.Commands.WebRequestSession]$Session
    )
    $Response = Invoke-WebRequest -UseBasicParsing -Uri ($BaseUri + '/api/qa/chat') `
        -Method Post -WebSession $Session -Headers @{ Origin = $Origin; Accept = 'text/event-stream' } `
        -ContentType 'application/json; charset=utf-8' -Body ($Body | ConvertTo-Json -Depth 8 -Compress) `
        -TimeoutSec 360
    if ($Response.StatusCode -ne 200) { throw "SSE request failed with status $($Response.StatusCode)" }
    $EventBlocks = @([regex]::Split($Response.Content, '\r?\n\r?\n') | Where-Object { $_.Trim() })
    $LogicalEvents = @()
    $Records = @()
    foreach ($Block in $EventBlocks) {
        $EventName = ''
        $DataLines = @()
        foreach ($Line in ($Block -split '\r?\n')) {
            if ($Line.StartsWith('event:')) { $EventName = $Line.Substring(6).Trim() }
            if ($Line.StartsWith('data:')) { $DataLines += $Line.Substring(5).TrimStart() }
        }
        if (-not $EventName) { continue }
        $Payload = $null
        $Json = $DataLines -join "`n"
        if ($Json -and $Json -ne '[DONE]') {
            try { $Payload = $Json | ConvertFrom-Json } catch { throw "Invalid SSE JSON for event $EventName" }
        }
        $LogicalName = $EventName
        if ($EventName -eq 'start' -and $Payload.stage -in @('preparing', 'prepared')) {
            $LogicalName = [string]$Payload.stage
        }
        $LogicalEvents += $LogicalName
        $Records += [pscustomobject]@{ event = $LogicalName; payload = $Payload }
    }
    $Required = @('preparing', 'prepared', 'delta', 'final', 'done')
    $Cursor = -1
    foreach ($RequiredEvent in $Required) {
        $Next = [Array]::IndexOf($LogicalEvents, $RequiredEvent, $Cursor + 1)
        if ($Next -lt 0) { throw "SSE event sequence is missing $RequiredEvent" }
        $Cursor = $Next
    }
    $Prepared = ($Records | Where-Object { $_.event -eq 'prepared' } | Select-Object -Last 1).payload
    $Final = ($Records | Where-Object { $_.event -eq 'final' } | Select-Object -Last 1).payload
    $Answer = [string]($Final.answer ?? $Final.content ?? $Final.message ?? '')
    if ([string]::IsNullOrWhiteSpace($Answer)) { throw 'SSE final answer is empty.' }
    return [ordered]@{
        events = $LogicalEvents
        prepared_context_hash = [string]($Prepared.context_hash ?? '')
        prepared_conversation_id = [string]($Prepared.conversation_id ?? '')
        answer_chars = $Answer.Length
        cache_hit = [bool]($Final.cache_hit ?? $false)
    }
}

$Config = Get-Content -LiteralPath $ConfigPath -Raw -Encoding UTF8 | ConvertFrom-Json
$Environment = $Config.env
$Username = ([string]$Environment.BF_LOGIN_USERS -split ',')[0].Trim()
$PasswordProperty = $Environment.PSObject.Properties |
    Where-Object { $_.Name -like 'BF_LOGIN_*_PASSWORD' -and [string]$_.Value } |
    Select-Object -First 1
if (-not $Username -or -not $PasswordProperty) { throw 'A controlled login account is not configured.' }
$Session = [Microsoft.PowerShell.Commands.WebRequestSession]::new()
$Before = Get-ProtectedMap
$TargetPidBefore = Get-ListenerPid -TargetPort $Port
$RequestCount = 0

$AnonymousSession = [Microsoft.PowerShell.Commands.WebRequestSession]::new()
$AnonymousLatest = Invoke-JsonRequest -Method Get -Path '/api/furnace-rules/latest' -Body $null -Session $AnonymousSession
$AnonymousEvaluationId = [long]$AnonymousLatest.evaluation_id
if ($AnonymousEvaluationId -le 0) { throw 'Anonymous latest ABC evaluation_id is unavailable.' }
$AnonymousExplanation = Invoke-JsonRequest -Method Get -Path "/api/furnace-rules/$RuleId/explanation-context?evaluation_id=$AnonymousEvaluationId" -Body $null -Session $AnonymousSession
if (-not $AnonymousExplanation.ok -or -not $AnonymousExplanation.operator_explanation) {
    throw 'Anonymous deterministic B4 explanation failed.'
}

if ($GuestShared) {
    $GuestOne = Invoke-JsonRequest -Method Get -Path '/api/qa/bootstrap' -Body $null -Session $AnonymousSession
    $SecondGuestSession = [Microsoft.PowerShell.Commands.WebRequestSession]::new()
    $GuestTwo = Invoke-JsonRequest -Method Get -Path '/api/qa/bootstrap' -Body $null -Session $SecondGuestSession
    $GuestConversationId = [string]$GuestOne.conversation.id
    if ($GuestOne.access_mode -ne 'guest_shared' -or -not $GuestConversationId) {
        throw 'Shared guest bootstrap contract failed.'
    }
    if ([string]$GuestTwo.conversation.id -ne $GuestConversationId) {
        throw 'Independent LAN guest sessions did not resolve to the same conversation.'
    }
    if ([string]$Config.env.BF_QA_KNOWLEDGE_SEARCH_MODE -ne 'keyword') {
        throw '8093 keyword knowledge configuration drifted.'
    }
    $BackendPath = Join-Path $Root '高炉前端数据\智能助手\backend\ollama_proxy_server.py'
    $BackendText = Get-Content -LiteralPath $BackendPath -Raw -Encoding UTF8
    foreach ($Marker in @(
        'QA_MCP_MAX_TOOL_ROUNDS", "5"',
        'QA_MCP_MAX_TOOL_CALLS", "5"',
        'BF_QA_MCP_PARALLEL_TOOL_CALLS", "1"',
        'BF_QA_MCP_MAX_PARALLEL_TOOL_CALLS", "5"',
        'qa_mcp_execute_parallel_batch',
        'model_planner_parallel'
    )) {
        if (-not $BackendText.Contains($Marker)) { throw "MCP parallel source marker missing: $Marker" }
    }
    $GuestSse = $null
    if (-not $SkipModelSse) {
        $GuestSse = Invoke-SseRequest -Body @{
            conversation_id = $GuestConversationId
            message = '检查软熔带是否上升或下降；如果实时数据库工具没有返回，也请明确说明未核实，并基于一般高炉知识给出复核思路。'
            current_snapshot = @{
                captured_at = (Get-Date).ToString('o')
                source_page = 'qa'
            }
            stream = $true
        } -Session $AnonymousSession
        $RequestCount++
    }
    $GuestAfter = Invoke-JsonRequest -Method Get -Path "/api/qa/conversation?id=$GuestConversationId" -Body $null -Session $SecondGuestSession
    if (-not $GuestAfter.ok -or @($GuestAfter.messages).Count -lt 1) {
        throw 'Shared guest messages were not persisted for another LAN visitor.'
    }
    $After = Get-ProtectedMap
    $TargetPidAfter = Get-ListenerPid -TargetPort $Port
    foreach ($Key in $Before.Keys) {
        if ($After[$Key] -ne $Before[$Key]) { throw "Protected PID changed during guest acceptance: $Key" }
    }
    if ($TargetPidAfter -ne $TargetPidBefore) { throw "$Port PID changed during guest acceptance." }
    [ordered]@{
        ok = $true
        schema = 'bf.8093-mcp-parallel-guest-acceptance.v1'
        port = $Port
        access_mode = [string]$GuestOne.access_mode
        conversation_id = $GuestConversationId
        shared_conversation_verified = $true
        persisted_message_count = @($GuestAfter.messages).Count
        request_count = $RequestCount
        model_sse_skipped = [bool]$SkipModelSse
        guest_sse = $GuestSse
        target_pid_before = $TargetPidBefore
        target_pid_after = $TargetPidAfter
        protected_before = $Before
        protected_after = $After
    } | ConvertTo-Json -Depth 8
    return
}

$LoginBaseUri = $BaseUri
$Login = Invoke-JsonRequest -Method Post -Path '/api/auth/login' -Body @{
    username = $Username
    password = [string]$PasswordProperty.Value
} -Session $Session -BaseOverride $LoginBaseUri -OriginOverride $LoginBaseUri
if (-not $Login.ok) { throw 'Controlled login failed.' }

$Latest = Invoke-JsonRequest -Method Get -Path '/api/furnace-rules/latest' -Body $null -Session $Session
$EvaluationId = [long]$Latest.evaluation_id
if ($EvaluationId -le 0) { throw 'Latest ABC evaluation_id is unavailable.' }
$Detail = Invoke-JsonRequest -Method Get -Path "/api/furnace-rules/$RuleId/detail" -Body $null -Session $Session
if (-not $Detail.ok) { throw 'B4 public detail failed.' }
$Explanation = Invoke-JsonRequest -Method Get -Path "/api/furnace-rules/$RuleId/explanation-context?evaluation_id=$EvaluationId" -Body $null -Session $Session
if (-not $Explanation.ok -or -not $Explanation.context_hash) { throw 'B4 explanation context failed.' }
$Contextual = Invoke-JsonRequest -Method Post -Path '/api/qa/contextual-conversations' -Body @{
    source_type = 'abc_rule'
    source_page = 'optimization'
    rule_id = $RuleId
    evaluation_id = $EvaluationId
    reuse_policy = 'same_rule_active'
} -Session $Session
$ConversationId = [string]$Contextual.conversation.id
if (-not $ConversationId) { throw 'Contextual conversation was not created or reused.' }

$InitialSse = $null
if (-not $SkipModelSse) {
    $InitialSse = Invoke-SseRequest -Body @{
        conversation_id = $ConversationId
        message = $InitialQuestion
        analysis_mode = 'initial_context_explanation'
        stream = $true
    } -Session $Session
    $RequestCount++
}

$FollowupSse = $null
if ($SendFollowup -and -not $SkipModelSse) {
    $FollowupSse = Invoke-SseRequest -Body @{
        conversation_id = $ConversationId
        message = $FollowupQuestion
        stream = $true
    } -Session $Session
    $RequestCount++
}

$After = Get-ProtectedMap
$TargetPidAfter = Get-ListenerPid -TargetPort $Port
foreach ($Key in $Before.Keys) {
    if ($After[$Key] -ne $Before[$Key]) { throw "Protected PID changed during acceptance: $Key" }
}
if ($TargetPidAfter -ne $TargetPidBefore) { throw "$Port PID changed during acceptance." }

[ordered]@{
    ok = $true
    schema = 'bf.abc33.contextual-assistant-acceptance.v1'
    port = $Port
    evaluation_id = $EvaluationId
    rule_id = $RuleId
    conversation_id = $ConversationId
    context_hash = [string]$Explanation.context_hash
    request_count = $RequestCount
    model_sse_skipped = [bool]$SkipModelSse
    anonymous_explanation_ok = [bool]$AnonymousExplanation.ok
    initial = $InitialSse
    followup = $FollowupSse
    target_pid_before = $TargetPidBefore
    target_pid_after = $TargetPidAfter
    protected_before = $Before
    protected_after = $After
} | ConvertTo-Json -Depth 7
