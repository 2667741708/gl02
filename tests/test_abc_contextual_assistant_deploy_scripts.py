from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DEPLOY = ROOT / "tools" / "remote_deploy_abc33_contextual_assistant_8093.ps1"
ACCEPT = ROOT / "tools" / "remote_accept_abc33_contextual_assistant.ps1"
STAGE = ROOT / "tools" / "stage_abc33_contextual_assistant_8093_package.ps1"
MIGRATION = (
    ROOT
    / "高炉前端数据"
    / "智能助手"
    / "backend"
    / "schema"
    / "20260811_abc_contextual_assistant.sql"
)


def test_guarded_deployer_preserves_required_safety_contract() -> None:
    text = DEPLOY.read_text(encoding="utf-8")
    assert "Global\\BFV4PreviewProxy8093Deployment" in text
    assert "$ProtectedPorts = @(8094, 8768, 8770, 5432, 11434)" in text
    assert "Start-Sleep -Seconds 15" in text
    assert "Stop-8093" in text
    assert "Start-8093" in text
    assert "Install-FileAtomically" in text
    assert "rollback_applied" in text
    assert "finally" in text
    assert "remote_accept_abc33_contextual_assistant.ps1" in text
    assert "$ExpectedRequestCount = if ($SkipModelSse) { 0 } elseif ($GuestSharedAcceptance) { 1 } else { 2 }" in text
    assert "[switch]$SkipModelSse" in text
    assert "ExpectedDeltaRelativePaths" in text
    assert "Files.Count -gt $ExpectedDeltaRelativePaths.Count" in text
    assert "Delta plan exceeds" in text
    assert "ExpectedTargets.ContainsKey" in text
    assert "Stage/target mapping differs" in text
    assert "[IO.Path]::GetFileName($RelativePath)" in text
    expected_targets = (
        "高炉前端数据\\frontend_dashboard_v3.server.html",
        "高炉前端数据\\assets\\abc-furnace-rules-production.js",
        "高炉前端数据\\assets\\bf-abc33-assistant-dialog.css",
        "高炉前端数据\\assets\\bf-abc33-assistant-dialog.js",
        "高炉前端数据\\智能助手\\backend\\assistant_pg.py",
        "高炉前端数据\\智能助手\\backend\\ollama_proxy_server.py",
        "高炉前端数据\\智能助手\\backend\\abc_rule_assistant_analysis.py",
        "高炉前端数据\\智能助手\\backend\\schema\\postgresql_assistant.sql",
        "高炉前端数据\\智能助手\\backend\\schema\\20260811_abc_contextual_assistant.sql",
        "tools\\service_configs\\22012_BFV4PreviewProxy8093.json",
    )
    for target in expected_targets:
        assert f"'{target}'" in text
    assert "execution_id = $ExecutionId" in text
    assert "manifest_sha256 = $ManifestSha256" in text
    assert "'application_files_only'" in text
    assert "additive_migration_retained = $MigrationApplied" in text
    assert "powershell.exe" not in text.lower()


def test_acceptance_uses_exactly_one_initial_and_optional_one_followup_sse() -> None:
    text = ACCEPT.read_text(encoding="utf-8")
    assert text.count("$RequestCount++") == 3
    assert "if ($GuestShared)" in text
    assert "shared_conversation_verified = $true" in text
    assert "analysis_mode = 'initial_context_explanation'" in text
    assert "preparing', 'prepared', 'delta', 'final', 'done" in text
    assert "EventName -eq 'start'" in text
    assert "Payload.stage -in @('preparing', 'prepared')" in text
    assert "$LogicalEvents += $LogicalName" in text
    assert "$DataLines -join \"`n\"" in text
    assert "[regex]::Split($Response.Content, '\\r?\\n\\r?\\n')" in text
    assert "$Block -split '\\r?\\n'" in text
    assert "event = $LogicalName; payload = $Payload" in text
    assert "$_.event -eq 'prepared'" in text
    assert "$_.event -eq 'final'" in text
    assert "ContentType 'application/json; charset=utf-8'" in text
    assert "Anonymous deterministic B4 explanation failed" in text
    assert "anonymous_explanation_ok" in text
    assert "[switch]$SkipModelSse" in text
    assert "model_sse_skipped = [bool]$SkipModelSse" in text
    assert "Headers @{ Origin = $Origin" in text
    assert "$LoginBaseUri = $BaseUri" in text
    assert "-BaseOverride $LoginBaseUri -OriginOverride $LoginBaseUri" in text
    assert "TargetPidAfter -ne $TargetPidBefore" in text
    assert "powershell.exe" not in text.lower()


def test_stager_binds_controller_execution_and_manifest_identity() -> None:
    text = STAGE.read_text(encoding="utf-8")
    assert "[string]$ExecutionId" in text
    assert "[string]$ExpectedManifestSha256" in text
    assert "controller-sealed value" in text
    assert "execution_id = $ExecutionId" in text
    assert "manifest_sha256 = $ManifestSha256" in text
    assert "uncertain_execution" not in text


def test_additive_migration_is_complete_for_legacy_qa_and_claim_columns() -> None:
    text = MIGRATION.read_text(encoding="utf-8")
    required_fragments = (
        "qa_conversations\n    ADD COLUMN IF NOT EXISTS owner_subject text",
        "qa_conversations\n    ADD COLUMN IF NOT EXISTS owner_role text",
        "ADD COLUMN IF NOT EXISTS context_type text",
        "ADD COLUMN IF NOT EXISTS context_key text",
        "ADD COLUMN IF NOT EXISTS schema_version text",
        "ADD COLUMN IF NOT EXISTS source_ref_id text",
        "ADD COLUMN IF NOT EXISTS payload_json text",
        "ADD COLUMN IF NOT EXISTS payload_size_bytes bigint",
        "ADD COLUMN IF NOT EXISTS usage_kind text",
        "ADD COLUMN IF NOT EXISTS claim_token text",
        "ADD COLUMN IF NOT EXISTS lease_expires_at text",
        "uq_qa_context_snapshots_context_hash",
        "uq_qa_message_context_snapshots_usage",
        "uq_abc_rule_ai_explanations_cache",
    )
    for fragment in required_fragments:
        assert fragment in text
    assert text.strip().endswith("COMMIT;")
