"""Contracts for five-minute, eight-condition diagnosis AI analysis."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "高炉前端数据" / "智能助手" / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

import diagnosis_ai_analysis_api  # noqa: E402
import diag_ai_evidence  # noqa: E402
import diagnosis_model_review  # noqa: E402


def canonical_context() -> dict:
    return {
        "available": True,
        "furnace_id": "BF",
        "snapshot_id": "987",
        "snapshot_source": "live_readonly",
        "diagnosis_ts": "2026-08-05T13:07:23+08:00",
        "main_label": "cold",
        "main_score": 76,
        "secondary": [{"label": "edge", "score": 48}],
        "raw_scores": {
            "normal": 22,
            "lowline": 31,
            "edge": 48,
            "center": 18,
            "channel": 12,
            "cold": 76,
            "hot": 9,
            "column": 14,
        },
        "evidence": ["顶温连续下降", "煤气利用率下降"],
        "feature_snapshot": {
            "z30_T_top_slope": -0.62,
            "z60_T_body_lower": -1.08,
            "z60_P_blast": -0.91,
            "z60_PI": 0.94,
            "z60_GasUtil": -0.73,
        },
        "data_coverage": {"available": 27, "total": 28, "ratio": 0.964},
    }


def valid_model_payload() -> str:
    analyses = []
    for index, label in enumerate(diagnosis_model_review.DIAGNOSIS_LABELS):
        analyses.append(
            {
                "label": label,
                "verdict": "supported" if label == "cold" else "possible",
                "model_support_score": 80 - index,
                "summary": f"{diagnosis_model_review.DISPLAY_NAMES[label]}分析",
                "score_explanation": "依据输入中的规则变量、近5分钟变化和30天基线说明分数。",
                "key_driver_ids": [],
                "supporting_evidence": ["规则分与证据一致"],
                "contradicting_evidence": [],
                "attention_items": ["继续观察"],
                "data_limits": ["缺少炉次化验"],
                "guidance_summary": "只引用既有调剂动作和知识依据，现场确认后分步观察。",
                "recommendation_action_ids": [],
                "knowledge_chunk_ids": [],
                "risk_change": "stable",
            }
        )
    return json.dumps({"analyses": analyses}, ensure_ascii=False)


def test_context_is_server_owned_and_bucketed_to_five_minutes() -> None:
    context = diagnosis_model_review.normalize_five_minute_context(
        canonical_context(), [], bucket_minutes=5
    )
    assert context["bucket_ts"] == "2026-08-05T13:05:00+08:00"
    assert context["snapshot_id"] == "987"
    assert context["scores"]["cold"] == 76
    assert set(context["scores"]) == set(diagnosis_model_review.DIAGNOSIS_LABELS)


def test_one_prompt_requires_all_eight_conditions_and_forbids_rule_rewrite() -> None:
    context = diagnosis_model_review.normalize_five_minute_context(
        canonical_context(), [], bucket_minutes=5
    )
    messages = diagnosis_model_review.build_five_minute_analysis_messages(context)
    assert "同时分析固定的8类炉况" in messages[0]["content"]
    assert "不能替换规则分" in messages[0]["content"]
    assert "不是概率" in messages[0]["content"]
    assert "模型文字要简洁" in messages[0]["content"]
    assert "整批JSON不要附加解释文字" in messages[1]["content"]
    assert all(label in messages[1]["content"] for label in diagnosis_model_review.DIAGNOSIS_LABELS)


def test_production_prompt_calls_model_for_only_the_selected_condition() -> None:
    context = diagnosis_model_review.normalize_five_minute_context(
        canonical_context(), [], bucket_minutes=5
    )
    context.update(diag_ai_evidence.build_fixture_enrichment(context))
    messages = diagnosis_model_review.build_single_condition_analysis_messages(
        context, "cold"
    )
    assert "本次只分析用户点击的一种炉况" in messages[0]["content"]
    assert "只分析热制度下行（cold）" in messages[1]["content"]
    assert '"target_label": "cold"' in messages[1]["content"]
    assert '"rule_score": 76.0' in messages[1]["content"]
    assert '"conditions"' not in messages[1]["content"]
    payload = json.loads(valid_model_payload())["analyses"][5]
    parsed = diagnosis_model_review.parse_single_condition_analysis_payload(
        json.dumps({"analysis": payload}, ensure_ascii=False), "cold", context
    )
    assert parsed["analysis"]["label"] == "cold"
    assert diagnosis_model_review.single_condition_prompt_version("cold").endswith(
        ".cold"
    )


def test_model_payload_requires_exactly_eight_unique_labels() -> None:
    parsed = diagnosis_model_review.parse_five_minute_analysis_payload(
        valid_model_payload()
    )
    assert len(parsed["analyses"]) == 8
    assert parsed["analyses"][5]["display_name"] == "热制度下行"
    broken = json.loads(valid_model_payload())
    broken["analyses"].pop()
    with pytest.raises(diagnosis_model_review.ModelReviewValidationError):
        diagnosis_model_review.parse_five_minute_analysis_payload(
            json.dumps(broken, ensure_ascii=False)
        )


def test_fixture_batch_is_complete_and_read_only() -> None:
    batch = diagnosis_model_review.build_fixture_five_minute_analysis(
        canonical_context()
    )
    assert batch["state"] == "completed"
    assert batch["read_only"] is True
    assert len(batch["analyses"]) == 8
    assert batch["score_semantics"].endswith("均不是概率")
    assert batch["analyses"][5]["variable_evidence"]
    assert batch["analyses"][5]["recommendation_basis"]["available"] is True
    assert batch["analyses"][5]["knowledge_basis"]["available"] is True


def test_variable_stats_and_rule_drivers_keep_exact_data_provenance() -> None:
    sensor_rows = [
        {"variable_name": "P_blast", "ts": "2026-08-05T12:59:00", "value": 401},
        {"variable_name": "P_blast", "ts": "2026-08-05T13:04:00", "value": 384},
    ]
    baseline_rows = [
        {
            "variable_name": "P_blast",
            "baseline_day": "2026-08-05",
            "median_ref": 400,
            "iqr_ref": 20,
        }
    ]
    stats = diag_ai_evidence.build_variable_stats(
        sensor_rows, baseline_rows, "2026-08-05T13:05:00"
    )
    assert stats["P_blast"]["current_value"] == 384
    assert stats["P_blast"]["delta_5m"] == -17
    assert stats["P_blast"]["baseline_median_30d"] == 400
    drivers = diag_ai_evidence.build_rule_driver_context(
        {"z60_P_blast": -0.91}, stats
    )
    cold = next(row for row in drivers["cold"] if row["driver_id"] == "cold.low-blast-pressure")
    assert cold["signal_state"] == "supporting"
    assert "当前384kPa" in cold["colloquial_evidence"]
    assert cold["source"] == "diagnosis_snapshot.feature_snapshot"


def test_core_19_variables_include_series_and_derived_combined_top_temperature() -> None:
    top_values = {
        "T_top_A": (140, 144),
        "T_top_B": (142, 146),
        "T_top_C": (144, 148),
        "T_top_D": (146, 150),
    }
    sensor_rows = []
    baseline_rows = []
    for variable, (previous, current) in top_values.items():
        sensor_rows.extend(
            [
                {"variable_name": variable, "ts": "2026-08-05T12:59:00", "value": previous},
                {"variable_name": variable, "ts": "2026-08-05T13:04:00", "value": current},
            ]
        )
        baseline_rows.append(
            {
                "variable_name": variable,
                "baseline_day": "2026-08-05",
                "median_ref": current + 2,
                "iqr_ref": 10,
            }
        )
    stats = diag_ai_evidence.build_variable_stats(
        sensor_rows, baseline_rows, "2026-08-05T13:05:00"
    )
    core = diag_ai_evidence.build_core_variable_evidence(
        stats,
        [{"variables": [{"id": "T_top_A"}, {"id": "T_top_B"}]}],
    )
    assert tuple(row["id"] for row in core) == diag_ai_evidence.CORE_EVIDENCE_VARIABLES
    assert len(core) == 19
    combined = next(row for row in core if row["id"] == "T_top")
    assert combined["current_value"] == 147
    assert len(combined["series_60m"]) == 2
    assert combined["value_source"] == "derived_mean_T_top_A_D"
    assert combined["source"].startswith("derived AVG")
    assert next(row for row in core if row["id"] == "T_top_A")[
        "selected_rule_evidence"
    ] is True
    assert next(row for row in core if row["id"] == "P_top")[
        "selected_rule_evidence"
    ] is False


def test_truthful_data_limits_ignore_sparse_but_usable_sensor_series() -> None:
    stats = {
        name: {
            "current_value": 1.0,
            "series_60m": [{"ts": "2026-08-08T14:40:00", "value": 1.0}],
        }
        for name in (
            "L_north",
            "L_south",
            "T_top_A",
            "T_top_B",
            "T_top_C",
            "T_top_D",
        )
    }
    drivers = [
        {
            "name": "南北料线同步",
            "feature_value": None,
            "variables": [{"id": "L_north"}, {"id": "L_south"}],
        },
        {
            "name": "顶温离散稳定",
            "feature_value": None,
            "variables": [{"id": name} for name in ("T_top_A", "T_top_B", "T_top_C", "T_top_D")],
        },
    ]
    assert diag_ai_evidence.build_truthful_data_limits("normal", drivers, stats) == []

    missing = dict(stats)
    missing["L_south"] = {"current_value": None, "series_60m": []}
    limits = diag_ai_evidence.build_truthful_data_limits("normal", drivers, missing)
    assert limits
    assert "南探尺料线" in limits[0]


def test_completed_analysis_exposes_all_19_core_variables_without_prompt_bloat() -> None:
    context = diagnosis_model_review.normalize_five_minute_context(
        canonical_context(), [], bucket_minutes=5
    )
    context.update(diag_ai_evidence.build_fixture_enrichment(context))
    payload = json.loads(valid_model_payload())
    payload["analyses"] = [payload["analyses"][5]]
    completed = diagnosis_model_review.build_completed_five_minute_analysis(
        context,
        payload,
        public_model_name="test-model",
        snapshot_hash="fixture-hash",
    )
    analysis = completed["analyses"][0]
    assert completed["schema_version"] == "diagnosis_ai_analysis.v4"
    assert analysis["core_variable_count"] == 19
    assert len(analysis["core_variable_evidence"]) == 19
    assert all("series_60m" in row for row in analysis["core_variable_evidence"])
    prompt = diagnosis_model_review.build_single_condition_analysis_messages(
        context, "cold"
    )
    assert "series_60m" not in prompt[1]["content"]


def test_model_cannot_reference_unknown_driver_action_or_knowledge_ids() -> None:
    enriched = diagnosis_model_review.normalize_five_minute_context(
        canonical_context(), [], bucket_minutes=5
    )
    enriched.update(diag_ai_evidence.build_fixture_enrichment(enriched))
    payload = json.loads(valid_model_payload())
    payload["analyses"][5]["key_driver_ids"] = ["invented-driver"]
    with pytest.raises(diagnosis_model_review.ModelReviewValidationError):
        diagnosis_model_review.parse_five_minute_analysis_payload(
            json.dumps(payload, ensure_ascii=False), context=enriched
        )


def test_existing_recommendation_engine_is_reused_as_read_only_guidance() -> None:
    bundle = diag_ai_evidence.load_recommendation_bundle(
        {
            "timestamp": "2026-08-05T13:05:00",
            "main_label": "cold",
            "main_score": 76,
            "secondary_label": None,
            "raw_scores": canonical_context()["raw_scores"],
            "feature_snapshot": canonical_context()["feature_snapshot"],
        },
        {"P_blast": 384, "Q_blast": 3560, "T_blast": 1168},
    )
    assert bundle["available"] is True
    assert bundle["read_only"] is True
    assert set(bundle["conditions"]) == set(diagnosis_model_review.DIAGNOSIS_LABELS)
    assert all(
        action["read_only"] is True
        for condition in bundle["conditions"].values()
        for action in condition["actions"]
    )


def test_foreman_knowledge_source_is_read_only_and_has_sensor_controls() -> None:
    stats = {
        "P_top": {
            "display_name": "综合顶压",
            "unit": "kPa",
            "current_value": 101.0,
            "delta_5m": 2.0,
            "baseline_median_30d": 100.0,
            "baseline_z_60m": 0.4,
            "sample_count_60m": 5,
        }
    }
    bundle = diag_ai_evidence.build_foreman_knowledge_recommendation_bundle(
        {
            "main_label": "normal",
            "raw_scores": {"normal": 82},
        },
        {"P_top": 101.0},
        {
            "enabled": True,
            "retrieval_mode": "keyword",
            "evidence": [
                {
                    "doc_id": diag_ai_evidence.FOREMAN_KNOWLEDGE_DOC_ID,
                    "chunk_id": "bf_foreman_ops_v1_chunk_0002",
                    "title": "正常顺行炉况——现象与维护",
                    "content": "仅作测试依据",
                }
            ],
        },
        stats,
        target_label="normal",
    )
    assert bundle["source_mode"] == "foreman_knowledge_only"
    assert bundle["engine_meta"]["source_doc_id"] == diag_ai_evidence.FOREMAN_KNOWLEDGE_DOC_ID
    assert bundle["conditions"]["normal"]["actions"][0]["status"] == "manual_confirm"
    assert bundle["sensor_deviation_summary"]["score_gap_to_100"] == 18.0
    assert {
        "KB-CONTROL-PCI-INCREASE",
        "KB-CONTROL-PCI-DECREASE",
        "KB-CONTROL-COLD-BLAST-PRESSURE-INCREASE",
        "KB-CONTROL-COLD-BLAST-PRESSURE-DECREASE",
    } == {item["id"] for item in bundle["control_candidates"]}


def test_api_routes_store_schema_and_combined_dialog_contracts() -> None:
    proxy = (BACKEND / "ollama_proxy_server.py").read_text(encoding="utf-8")
    api = (BACKEND / "diagnosis_ai_analysis_api.py").read_text(encoding="utf-8")
    review_store = (BACKEND / "diagnosis_review.py").read_text(encoding="utf-8")
    frontend = (
        ROOT / "高炉前端数据" / "assets" / "bf-diagnosis-manual-score-local.js"
    ).read_text(encoding="utf-8")
    css = (
        ROOT / "高炉前端数据" / "assets" / "bf-diagnosis-manual-score-local.css"
    ).read_text(encoding="utf-8")
    assert 'parsed.path == "/api/diagnosis-ai-analysis"' in proxy
    assert 'parsed.path == "/api/diagnosis-ai-analysis/retry"' in proxy
    assert 'parsed.path == "/api/diagnosis-core-evidence"' in proxy
    assert "install_handler(Handler, globals())" in proxy
    assert "bf-diagnosis-manual-score-local.js?v=20260806-core19-r10-foreman-knowledge" in proxy
    assert '<script src="/assets/bf-diagnosis-manual-score-local.js?v=20260806-core19-r10-foreman-knowledge"></script>' in proxy
    assert "canonical_review_context" in api
    assert "diagnosis_ai_analysis_snapshots" in review_store
    assert "UNIQUE (furnace_id, bucket_ts, prompt_version)" in review_store
    assert "def read_latest_diagnosis_rows" in review_store
    assert "DiagnosisReviewStore().read_latest_diagnosis_rows" in proxy
    assert "build_single_condition_analysis_messages" in proxy
    assert "parse_single_condition_analysis_payload" in proxy
    assert "max_tokens=1200" in proxy
    assert "build_five_minute_analysis_messages(context)" not in proxy
    assert '"core_variable_evidence": core_variable_evidence' in proxy
    assert '"core_series_window_minutes": 60' in proxy
    assert "/api/diagnosis-ai-analysis?" in frontend
    assert "/api/diagnosis-ai-analysis/retry" in frontend
    assert "/api/diagnosis-core-evidence?label=" in frontend
    assert "bfdms-ai-core-early" in frontend
    assert "bootWhenBodyReady" in frontend
    assert "result.core_variable_evidence" in frontend
    assert 'renderAi({state:"failed"});state.analysisTimer=setTimeout(loadAiAnalysis,3000)' in frontend
    assert "智能分析与人工评分" in frontend
    assert "为什么得到这个分数" in frontend
    assert "64主题知识库候选建议" in frontend
    assert "查看知识依据正文" in frontend
    assert "传感器逐项变化与正常偏离" in frontend
    assert "row.content||""" not in frontend
    assert "点击查看智能分析/评分" in css


def test_api_module_installs_both_handler_methods() -> None:
    class Dummy:
        pass

    diagnosis_ai_analysis_api.install_handler(Dummy, {})
    assert callable(Dummy.handle_diagnosis_ai_analysis_get)
    assert callable(Dummy.handle_diagnosis_core_evidence_get)
    assert callable(Dummy.handle_diagnosis_ai_analysis_retry)


def test_guarded_8093_deploy_enables_five_minute_analysis_for_8093_only() -> None:
    deploy = (
        ROOT / "tools" / "remote_guarded_deploy_8093_diagnosis_review.ps1"
    ).read_text(encoding="utf-8")
    assert "diagnosis_model_review.py" in deploy
    assert "diag_ai_evidence.py" in deploy
    assert "diagnosis_ai_analysis_api.py" in deploy
    assert "mcp_conversation_context.py" not in deploy
    assert "BF_DIAGNOSIS_AI_ANALYSIS_ENABLED = '1'" in deploy
    assert "BF_DIAGNOSIS_AI_ANALYSIS_BUCKET_MINUTES = '5'" in deploy
    assert "Wait-DiagnosisAiAnalysis -Label $analysisTargetLabel -TimeoutSeconds 300" not in deploy
    assert "BFV4PreviewProxy8093" in deploy
    assert "ai_analysis_runtime_async = $true" in deploy
    assert "diagnosis_ai_analysis.v4" in deploy
    assert "manual_score_renders_core_chart" in deploy
    assert "manual_score_core_available_while_preparing" in deploy
    assert "manual_score_loads_lightweight_core_endpoint" in deploy
    assert "core_endpoint_schema_v1" in deploy
    assert "lightweight_core_endpoint_series_count" in deploy
    assert "$manager -Action stop -ConfigPath $configPath" in deploy
    assert "$manager -Action start -ConfigPath $configPath" in deploy
    assert "Stop-Service -Name 'BFV4PreviewWs8768'" not in deploy
    assert "Stop-Service -Name 'V3AutoPreviewProxy8094'" not in deploy
    assert "8094" not in deploy


def test_guarded_8094_enable_reuses_current_shared_proxy_and_8768() -> None:
    deploy = (
        ROOT / "tools" / "remote_guarded_enable_8094_diagnosis_ai.ps1"
    ).read_text(encoding="utf-8")
    assert "REQ-8093-8094-DIAGNOSIS-REVIEW-AI-20260806" in deploy
    assert "ollama_proxy_server.py" in deploy
    assert "BF_DIAGNOSIS_REVIEW_ENABLED" in deploy
    assert "BF_DIAG_REVIEW_REQUIRE_LOGIN" in deploy
    assert "BF_DIAGNOSIS_MODEL_REVIEW_ENABLED" in deploy
    assert "BF_DIAGNOSIS_AI_ANALYSIS_ENABLED" in deploy
    assert "api/diagnosis-ai-analysis?label=$Label" in deploy
    assert "api/diagnosis-manual-scores" in deploy
    assert "bf-diagnosis-manual-score-local.js" in deploy
    assert "20260806-core19-r10-foreman-knowledge" in deploy
    assert "diagnosis_ai_analysis.v4" in deploy
    assert '$analysis = Wait-Analysis "normal" 180' not in deploy
    assert 'analysisVerificationMode = "runtime_async"' in deploy
    assert "coreVariableCount" in deploy
    assert "coreVariableIdsMatch" in deploy
    assert "coreTrendChartUi" in deploy
    assert "coreAvailableWhilePreparing" in deploy
    assert "lightweightCoreEndpoint" in deploy
    assert "function Restart-8094Preview" in deploy
    assert "Stop-ScheduledTask -TaskPath $taskPath -TaskName $taskName" in deploy
    assert "Start-ScheduledTask -TaskPath $taskPath -TaskName $taskName" in deploy
    assert "ollama_proxy_server_8094.py" in deploy
    assert "8769" in deploy
    assert "refusing to enable diagnosis features on an obsolete isolated 8094 runner" in deploy
    assert "pid8093Unchanged" in deploy
    assert "pid8768Unchanged" in deploy
    assert "pid11434Unchanged" in deploy
