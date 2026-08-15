from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DEPLOY = ROOT / "tools" / "remote_guarded_deploy_8093_mcp_gold.ps1"
PREPARE = ROOT / "tools" / "prepare_8093_mcp_gold_release.ps1"
PREPARE_GOLD003 = ROOT / "tools" / "prepare_8093_mcp_gold003_release.ps1"
PREPARE_BODY_STATS = ROOT / "tools" / "prepare_8093_body_temperature_statistics_release.ps1"
RECORD_VERSION = ROOT / "tools" / "remote_record_8093_mcp_gold_git_version.ps1"


def test_mcp_gold_deployer_has_exact_target_allowlist_and_sealed_subset() -> None:
    source = DEPLOY.read_text(encoding="utf-8")

    assert "ollama_proxy_server.py' = 'ollama_proxy_server.py'" in source
    assert "client_manager.py' = 'client_manager.py'" in source
    assert "cross_source_executor.py' = 'cross_source_executor.py'" in source
    assert "domain_router.py' = 'domain_router.py'" in source
    assert "MCP gold delta must contain 1-$($AllowedMap.Count) exact-allowlist files" in source
    assert "Stage/target mapping mismatch" in source
    assert "Duplicate delta target" in source


def test_mcp_gold_deployer_enforces_manifest_git_and_pwsh7_gates() -> None:
    source = DEPLOY.read_text(encoding="utf-8")

    assert "ExpectedManifestSha256" in source
    assert "ExpectedGitHead" in source
    assert "Controller manifest SHA-256 mismatch" in source
    assert "Production Git HEAD changed" in source
    assert "Deployment target differs from Git HEAD before deploy" in source
    assert "C:\\Program Files\\PowerShell\\7\\pwsh.exe" in source
    assert "powershell.exe" not in source.lower()


def test_mcp_gold_deployer_preserves_protected_services_and_rolls_back() -> None:
    source = DEPLOY.read_text(encoding="utf-8")

    assert "$ProtectedPorts = @(8094, 8768, 8770, 5432, 11434, 8892)" in source
    assert "Global\\BFV4PreviewProxy8093Deployment" in source
    assert "Disable-ScheduledTask" in source
    assert "Enable-ScheduledTask" in source
    assert "Start-Sleep -Seconds 15" in source
    assert "for ($Attempt = 1; $Attempt -le 2; $Attempt++)" in source
    assert "function Wait-GuardCompleted" in source
    assert "$LastResult -eq 267009" in source
    assert "GuardStartRequestedAt" in source
    assert "Default keyword knowledge search failed" in source
    assert "RollbackApplied = $true" in source
    assert "$ModelRequestCount = [int]$Acceptance.model_request_count" in source
    assert "$ModelRequestCount = $null" in source
    assert "did not return structured JSON" in source
    assert "verify_8093_mcp_gold_sse_once.py" in source
    assert "Single MCP SSE request contract failed" in source
    assert "'guest_conversation_recovery'" in source
    assert "--require-bootstrap-conversation-rebind" in source
    assert "Guest recovery acceptance did not bind the bootstrap shared conversation" in source
    assert "GOLD-005 must call only the upstream heat resolver once" in source
    assert "GOLD-003 missing required MCP service" in source
    assert "Security boundary acceptance unexpectedly called a tool" in source
    assert "$Acceptance.sse.mcp_tool_trace" in source
    assert '"$($Previous.Count)_application_files"' in source
    assert "bf_data_extended_mcp_server.py' = 'bf_data_extended_mcp_server.py'" in source
    assert "calculation_tools.json' = 'calculation_tools.json'" in source
    assert "$StagedPythonFiles" in source
    assert "查询最近一小时第7层到第13层各层A到H的平均温度" in source
    assert "查询最近30分钟第12层A到H各方位温度" in source
    assert "查询今天8点到9点第7层到第13层各层平均温度" in source
    assert "PositionAverageMatches.Count -ne 8" in source
    assert "PositionAverages.Count -lt 2" in source
    assert "Body-temperature layer acceptance must use exactly one tool call" in source


def test_mcp_gold_deployer_waits_past_transient_guard_start_collision() -> None:
    source = DEPLOY.read_text(encoding="utf-8")

    assert "$LastResult = [long]$Info.LastTaskResult" in source
    assert "$StartRefusedByActiveInstance = $LastResult -eq 2147946720" in source
    assert "-not $StartRefusedByActiveInstance" in source


def test_mcp_gold_release_is_sealed_to_remote_baselines() -> None:
    source = PREPARE.read_text(encoding="utf-8")

    for digest in (
        "89B262CA125916E25CF5D6375543E26AB89BA888371DD448A8E9B9BEACD42F79",
        "6B5366C177091604FEE30ED73DDBCE3A384A4D5B73CB91DDF616F59725856DD9",
        "2273F1619871F88B2AF49FE6518BCB8E6D60AEAB013D9DF1BF58CF4CD2DECD06",
    ):
        assert digest in source
    assert "release_manifest.py" in source
    assert "prepare --spec" in source
    assert "verify --manifest" in source


def test_gold003_release_is_sealed_to_the_clean_domain_router_baseline() -> None:
    source = PREPARE_GOLD003.read_text(encoding="utf-8")

    assert "BUG-MCP-GOLD003-MISSING-PTOP-20260814" in source
    assert "1EEA98F9DBD639AE7D22EE6BF53A08FDF5167729FCBD29C9D1DF2BE728AA3DBC" in source
    assert "E64CCDA2FAF7DA1BDAD21FD56CDCFD00F7BC0B0E9DBD02494A7C4D8622B0C9C6" in source
    assert "domain_router.py" in source
    assert "cross_source_executor.py" in source
    assert "artifact_count = 2" in source
    assert "release_manifest.py" in source


def test_body_temperature_release_is_sealed_to_four_live_baselines() -> None:
    source = PREPARE_BODY_STATS.read_text(encoding="utf-8")

    for digest in (
        "B0FD19BFAFD403B7A37A62CC7FDC743185A2F20EBEF03075D99923163F8BEBD4",
        "F042842B56782B99B2707805841EE0C4382106ED184D4C26EBBD1C5F48629181",
        "2B0AA1656F5AEA1C884006D73F5268FB914FFC2C7877711F9AEFABE048173C00",
        "71949288EC5622BFC10995B07D97D2292342A6BA8AE1911F11ED25397A78B9D3",
    ):
        assert digest in source
    assert "REQ-MCP-BODY-LAYER-STATISTICS-20260814" in source
    assert "artifact_count = $Artifacts.Count" in source
    assert "release_manifest.py" in source


def test_composite_body_statistics_precedes_generic_cross_source_dag() -> None:
    proxy = (
        ROOT / "高炉前端数据" / "智能助手" / "backend" / "ollama_proxy_server.py"
    ).read_text(encoding="utf-8")
    body_plan = proxy.index(
        "body_statistics_plan = qa_mcp_body_temperature_statistics_plan(question)"
    )
    cross_plan = proxy.index("cross_source_plan = (", body_plan)
    sensor_plan = proxy.index(
        "sensor_plan = body_statistics_plan or qa_mcp_sensor_query_plan(question)",
        cross_plan,
    )
    assert body_plan < cross_plan < sensor_plan
    assert "if body_statistics_plan is not None" in proxy[body_plan:sensor_plan]


def test_git_version_is_saved_only_from_exact_reviewed_paths() -> None:
    source = RECORD_VERSION.read_text(encoding="utf-8")

    assert "ExpectedParentHead" in source
    assert "ExpectedProxySha256" in source
    assert "ExpectedClientManagerSha256" in source
    assert "ExpectedCrossSourceSha256" in source
    assert "ExpectedDomainRouterSha256" in source
    assert "[ValidateSet('mcp_gold', 'gold003', 'boundary', 'proxy_only', 'body_stats', 'body_trace')]" in source
    assert "$RequiredPaths = @(if ($Profile -eq 'gold003')" in source
    assert "Global\\BFV4PreviewProxy8093Deployment" in source
    assert "Unreviewed production change blocks Git version save" in source
    assert "Staged path set does not exactly match the reviewed change set" in source
    assert "foreach ($Path in $RequiredPaths)" in source
    assert "$ExpectedRemaining" in source
    assert "8892" in source
    assert "Sensitive scan rejected reviewed path" in source
    assert "git add ." not in source
    assert "service_restart_performed = $false" in source
    assert "ExpectedExtendedSha256" in source
    assert "ExpectedCalculationCatalogSha256" in source
    assert "$Profile -eq 'body_stats'" in source
    assert "$Profile -eq 'body_trace'" in source
    assert "ExpectedFrontendSha256" in source
    assert "$Remaining = @(Get-ChangedPaths)" in source
