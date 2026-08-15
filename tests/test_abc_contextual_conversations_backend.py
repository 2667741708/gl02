from __future__ import annotations

import importlib
import json
import re
import sys
from contextlib import contextmanager
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "高炉前端数据" / "智能助手" / "backend"
ABC_SERVICE = ROOT / "自动诊断服务"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))
if str(ABC_SERVICE) not in sys.path:
    sys.path.insert(0, str(ABC_SERVICE))


class _Cursor:
    def __init__(self, row):
        self.row = row

    def fetchone(self):
        return self.row


class _Connection:
    def __init__(self, row):
        self.row = row
        self.sql = ""
        self.params = None

    def execute(self, sql, params):
        self.sql = sql
        self.params = params
        return _Cursor(self.row)


def test_authoritative_loader_normalizes_real_pg_json_text() -> None:
    module = importlib.import_module("abc_rule_assistant_analysis")
    row = {
        "batch_id": 321,
        "rule_id": "B4",
        "score": 71.2,
        "confidence": 0.88,
        "status": "eligible",
        "weights": json.dumps({"burden_rate": 0.4}),
        "contributions": json.dumps([{"feature_key": "burden_rate", "contribution": 28.48}]),
        "normalized_values": json.dumps({"burden_rate": 0.712}),
        "missing_features": "[]",
        "public_detail": json.dumps({"risk_score": 71.2, "score_basis": "weighted_terms"}),
        "evaluation_ts": "2026-08-11T10:00:00+08:00",
        "catalog_version": "abc33.v1",
        "config_version": "v7",
        "config_hash": "cfg-sha",
        "source_snapshot_id": 9001,
        "furnace_id": "GL02",
    }
    conn = _Connection(row)

    result = module.load_authoritative_evaluation(conn, rule_id="B4", evaluation_id=321)

    assert result is not None
    assert result["evaluation_id"] == 321
    assert result["config_hash"] == "cfg-sha"
    assert result["source_snapshot_id"] == 9001
    assert result["furnace_id"] == "GL02"
    assert result["weights"] == {"burden_rate": 0.4}
    assert result["contributions"][0]["feature_key"] == "burden_rate"
    assert result["risk_score"] == 71.2
    assert conn.params == (321, "B4")


def test_context_summary_reads_nested_contract() -> None:
    module = importlib.import_module("abc_rule_assistant_analysis")
    summary = module.context_summary({
        "schema_version": "abc_rule_explanation_context.v1",
        "evaluation": {"evaluation_id": "321", "evaluation_ts": "2026-08-11T10:00:00+08:00"},
        "rule": {"rule_id": "B4", "display_name": "料批速度", "status": "eligible", "score": 71.2},
    })
    assert summary == {
        "schema_version": "abc_rule_explanation_context.v1",
        "rule_id": "B4",
        "evaluation_id": "321",
        "evaluation_ts": "2026-08-11T10:00:00+08:00",
        "display_name": "料批速度",
        "status": "eligible",
        "score": 71.2,
    }


def test_shared_contract_keeps_database_evaluation_identity() -> None:
    module = importlib.import_module("abc_rule_assistant_analysis")
    artifacts = module.build_context_artifacts({
        "evaluation_id": 321,
        "rule_id": "B4",
        "furnace_id": "GL02",
        "evaluation_ts": "2026-08-11T10:00:00+08:00",
        "catalog_version": "abc33.v1",
        "config_version": "v7",
        "config_hash": "cfg-sha",
        "source_snapshot_id": 9001,
        "score": 71.2,
        "confidence": 0.88,
        "status": "eligible",
        "weights": {},
        "contributions": [],
        "missing_features": [],
    })
    assert artifacts["operator_explanation"]["evaluation"]["evaluation_id"] == "321"
    assert artifacts["operator_explanation"]["evaluation"]["config_hash"] == "cfg-sha"
    assert artifacts["operator_explanation"]["furnace_id"] == "GL02"


def test_schema_contains_context_origin_message_and_ai_cache_contracts() -> None:
    schema = (BACKEND / "schema" / "postgresql_assistant.sql").read_text(encoding="utf-8")
    for table in (
        "qa_context_snapshots", "qa_conversation_origins",
        "qa_message_context_snapshots", "abc_rule_ai_explanations",
    ):
        assert f"CREATE TABLE IF NOT EXISTS bf_assistant.{table}" in schema
    assert "UNIQUE(message_id, context_snapshot_id, usage_kind)" in schema
    assert "UNIQUE(context_snapshot_id, prompt_version, model_name)" in schema


def test_explanation_get_is_read_only_and_chat_injects_bound_context() -> None:
    source = (BACKEND / "ollama_proxy_server.py").read_text(encoding="utf-8")
    get_start = source.index("    def handle_furnace_rule_explanation_context")
    get_end = source.index("    def handle_furnace_rule_detail", get_start)
    get_body = source[get_start:get_end]
    assert "_persist_abc_context" not in get_body
    assert "current_review_session" not in get_body
    assert "already public ABC33 latest/detail contract" in get_body
    contextual_start = source.index("    def handle_qa_contextual_conversation")
    contextual_end = source.index("    def ", contextual_start + 8)
    assert "explanation_permission_required" in source[contextual_start:contextual_end]
    assert "assistant_rule_context=bound_assistant_context" in source
    assert "qa_message_context_snapshots" in source
    assert 'prepared.get("analysis_mode") == "initial_context_explanation"' in source
    assert "cache_abc_rule_analysis(" in source


def test_changed_backend_sources_compile() -> None:
    for relative in ("assistant_pg.py", "abc_rule_assistant_analysis.py", "ollama_proxy_server.py"):
        path = BACKEND / relative
        compile(path.read_text(encoding="utf-8"), str(path), "exec")


def _assistant_context(category: str = "B") -> dict:
    return {
        "schema_version": "abc_rule_explanation_context.v1",
        "rule": {"rule_id": f"{category}4", "category": category, "score": 71.2},
        "evaluation": {"evaluation_id": "321"},
        "calculation": {
            "terms": [
                {"term_id": "burden_rate", "weight": 0.4, "normalized_score_0_100": 71.2, "weighted_points": 28.48}
            ]
        },
        "process_guidance": {"intervention_order": ["先核对料批与尺速", "再分步观察反馈"]},
        "data_quality": {},
        "sensor_review": {},
        "assistant_policy": {},
    }


def _valid_analysis() -> dict:
    return {
        "summary": "当前证据支持按公开规则解释。",
        "score_explanation": [{"term_id": "burden_rate", "explanation": "料批速度项已参与评分。"}],
        "process_interpretation": "需结合现场连续性复核。",
        "recommended_sequence": ["先核对料批与尺速", "再分步观察反馈"],
        "data_limits": ["仅解释当前评估快照。"],
        "safety_notes": ["操作前需现场确认。"],
        "suggested_questions": ["需要查看哪些一次仪表？"],
        "context_citations": ["/rule", "/calculation/terms/burden_rate", "/process_guidance"],
    }


def test_initial_analysis_strict_contract_accepts_only_authoritative_terms_and_order() -> None:
    module = importlib.import_module("abc_rule_assistant_analysis")
    validated = module.validate_initial_analysis(_valid_analysis(), _assistant_context())
    assert validated["score_explanation"][0]["term_id"] == "burden_rate"
    assert "建议顺序" in module.render_initial_analysis(validated)


def test_initial_analysis_rejects_unknown_term_changed_order_and_invented_number() -> None:
    module = importlib.import_module("abc_rule_assistant_analysis")
    invalid_term = _valid_analysis()
    invalid_term["score_explanation"] = [{"term_id": "unknown", "explanation": "无效。"}]
    import pytest
    with pytest.raises(module.InitialAnalysisValidationError):
        module.validate_initial_analysis(invalid_term, _assistant_context())
    invalid_order = _valid_analysis()
    invalid_order["recommended_sequence"] = list(reversed(invalid_order["recommended_sequence"]))
    with pytest.raises(module.InitialAnalysisValidationError):
        module.validate_initial_analysis(invalid_order, _assistant_context())
    invented = _valid_analysis()
    invented["summary"] = "建议调整123.45。"
    with pytest.raises(module.InitialAnalysisValidationError):
        module.validate_initial_analysis(invented, _assistant_context())


def test_c_category_initial_analysis_requires_safety_note() -> None:
    module = importlib.import_module("abc_rule_assistant_analysis")
    value = _valid_analysis()
    value["safety_notes"] = []
    import pytest
    with pytest.raises(module.InitialAnalysisValidationError):
        module.validate_initial_analysis(value, _assistant_context("C"))


def test_initial_analysis_schema_is_context_bound_and_closed() -> None:
    module = importlib.import_module("abc_rule_assistant_analysis")
    schema = module.initial_analysis_json_schema(_assistant_context("C"))
    assert schema["required"] == list(module.INITIAL_ANALYSIS_FIELDS)
    assert schema["additionalProperties"] is False
    item = schema["properties"]["score_explanation"]["items"]
    assert item["additionalProperties"] is False
    assert item["properties"]["term_id"]["enum"] == ["burden_rate"]
    assert schema["properties"]["recommended_sequence"]["const"] == [
        "先核对料批与尺速", "再分步观察反馈"
    ]
    assert schema["properties"]["safety_notes"]["minItems"] == 1


def test_ollama_strict_json_uses_context_derived_schema(monkeypatch) -> None:
    module = _proxy_module()
    captured = {}

    class Response:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def read(self):
            return json.dumps({"message": {"content": json.dumps(_valid_analysis(), ensure_ascii=False)}}).encode()

    def fake_urlopen(request, timeout):
        captured.update(json.loads(request.data.decode("utf-8")))
        return Response()

    monkeypatch.setattr(module, "normalize_model", lambda value: "resident-test-model")
    monkeypatch.setattr(module, "urlopen", fake_urlopen)
    module.call_ollama_chat_strict_json([{"role": "user", "content": "解释"}], _assistant_context())
    assert isinstance(captured["format"], dict)
    assert captured["format"]["additionalProperties"] is False
    assert captured["format"]["properties"]["score_explanation"]["items"]["properties"]["term_id"]["enum"] == ["burden_rate"]


def test_initial_analysis_first_failure_repairs_once_and_revalidates(monkeypatch) -> None:
    module = _proxy_module()
    invalid = _valid_analysis()
    invalid["score_explanation"] = [{"term_id": "unknown", "explanation": "无效"}]
    calls = []

    def fake_repair(messages, assistant_context, max_tokens=1200):
        calls.append(messages)
        return json.dumps(_valid_analysis(), ensure_ascii=False)

    monkeypatch.setattr(module, "call_ollama_chat_strict_json", fake_repair)
    answer, payload = module.validated_abc_initial_answer_with_repair(
        json.dumps(invalid, ensure_ascii=False),
        [{"role": "user", "content": "固定首问"}],
        _assistant_context(),
    )
    assert len(calls) == 1
    assert payload["score_explanation"][0]["term_id"] == "burden_rate"
    assert "建议顺序" in answer
    assert "校验错误" in calls[0][-1]["content"]
    assert "unknown" in calls[0][-2]["content"]


def test_valid_initial_analysis_never_calls_repair_model(monkeypatch) -> None:
    module = _proxy_module()

    def unexpected_repair(*args, **kwargs):
        raise AssertionError("valid first candidate must not trigger repair")

    monkeypatch.setattr(module, "call_ollama_chat_strict_json", unexpected_repair)
    answer, payload = module.validated_abc_initial_answer_with_repair(
        json.dumps(_valid_analysis(), ensure_ascii=False),
        [{"role": "user", "content": "固定首问"}],
        _assistant_context(),
    )
    assert payload["recommended_sequence"] == _valid_analysis()["recommended_sequence"]
    assert "建议顺序" in answer


def test_initial_analysis_repair_failure_is_not_downgraded(monkeypatch) -> None:
    module = _proxy_module()
    calls = []

    def invalid_repair(messages, assistant_context, max_tokens=1200):
        calls.append(messages)
        return '{"summary":"仍不完整"}'

    monkeypatch.setattr(module, "call_ollama_chat_strict_json", invalid_repair)
    with pytest.raises(module.abc_rule_assistant_analysis.InitialAnalysisValidationError):
        module.validated_abc_initial_answer_with_repair(
            "not-json",
            [{"role": "user", "content": "固定首问"}],
            _assistant_context(),
        )
    assert len(calls) == 1


def test_stream_repair_stays_inside_one_sse_response_sequence() -> None:
    source = (BACKEND / "ollama_proxy_server.py").read_text(encoding="utf-8")
    stream_start = source.index("    def handle_qa_chat_stream")
    stream_end = source.index("    def write_qa_event", stream_start)
    stream_body = source[stream_start:stream_end]
    repair_start = source.index("def validated_abc_initial_answer_with_repair")
    repair_end = source.index("def set_abc_rule_analysis_state", repair_start)
    repair_body = source[repair_start:repair_end]
    assert stream_body.count("self.send_response(200)") == 1
    assert "validated_abc_initial_answer_with_repair(" in stream_body
    assert "write_qa_event" not in repair_body
    assert "send_response" not in repair_body


def test_backend_exposes_flags_read_only_reference_and_strict_json_cache() -> None:
    source = (BACKEND / "ollama_proxy_server.py").read_text(encoding="utf-8")
    assert "BF_ABC_RULE_ASSISTANT_ENABLED" in source
    assert "BF_ABC_RULE_ASSISTANT_AUTO_ANALYSIS" in source
    assert "BF_ABC_RULE_ASSISTANT_RETRY_SECONDS" in source
    assert '"assistant_context_ref"' in source
    assert "validated_abc_initial_answer" in source
    assert "analysis_payload=analysis_payload" in source


def test_qa_endpoints_require_session_owner_and_fixed_initial_question() -> None:
    source = (BACKEND / "ollama_proxy_server.py").read_text(encoding="utf-8")
    assert "def qa_session_required" in source
    assert "def qa_conversation_owned" in source
    assert "WHERE id = ? AND owner_subject = ?" in source
    assert "owner_subject=str(session[\"sub\"])" in source
    assert "ABC_RULE_INITIAL_QUESTION" in source
    assert "invalid_initial_analysis_question" in source
    assert "abc_context_binding_required" in source
    schema = (BACKEND / "schema" / "postgresql_assistant.sql").read_text(encoding="utf-8")
    assert "owner_subject text" in schema
    assert "owner_role text" in schema


def test_abc33_dialog_initial_question_matches_backend_contract() -> None:
    backend_source = (BACKEND / "ollama_proxy_server.py").read_text(encoding="utf-8")
    dialog_source = (ROOT / "高炉前端数据" / "assets" / "bf-abc33-assistant-dialog.js").read_text(encoding="utf-8")
    match = re.search(r'^ABC_RULE_INITIAL_QUESTION = "([^"]+)"$', backend_source, re.MULTILINE)
    assert match is not None
    assert f"streamQuestion('{match.group(1)}',{{initial:true}})" in dialog_source


def test_initial_analysis_claim_is_database_atomic_and_cross_process_safe() -> None:
    source = (BACKEND / "ollama_proxy_server.py").read_text(encoding="utf-8")
    claim_start = source.index("def claim_abc_rule_initial_analysis")
    claim_end = source.index("def wait_for_abc_rule_initial_analysis", claim_start)
    claim = source[claim_start:claim_end]
    assert "ON CONFLICT(context_snapshot_id, prompt_version, model_name) DO NOTHING" in claim
    assert "RETURNING id" in claim
    assert "claim_token" in claim
    assert "lease_expires_at" in claim
    assert "generation_state <> 'completed'" in claim
    wait_start = claim_end
    wait_end = source.index("def finish_abc_rule_initial_analysis", wait_start)
    assert "_abc_rule_cached_analysis" in source[wait_start:wait_end]
    schema = (BACKEND / "schema" / "postgresql_assistant.sql").read_text(encoding="utf-8")
    assert "claim_token text" in schema
    assert "lease_expires_at text" in schema


def test_short_window_and_period_report_conversations_persist_origins() -> None:
    source = (BACKEND / "ollama_proxy_server.py").read_text(encoding="utf-8")
    assert 'source_type="short_window"' in source
    assert 'source_type="period_report"' in source
    assert "persist_non_abc_conversation_origin" in source
    assert "qa_conversation_origins" in source


def _proxy_module():
    return importlib.import_module("ollama_proxy_server")


def test_cached_initial_analysis_handler_receives_session_for_json_and_sse(monkeypatch) -> None:
    module = _proxy_module()

    class Dummy:
        def __init__(self):
            self.json = None
            self.events = []
            self.session_seen = None

        def qa_conversation_owned(self, conn, conversation_id, session):
            self.session_seen = session
            return session["sub"] == "alice" and conversation_id == "qa_owned"

        def send_json(self, payload, status=200, headers=None):
            self.json = (payload, status)

        def send_response(self, status):
            self.status = status

        def add_cors(self):
            return None

        def send_header(self, name, value):
            return None

        def end_headers(self):
            return None

        def write_qa_event(self, event, payload):
            self.events.append((event, payload))
            return True

    @contextmanager
    def fake_connect():
        yield object()

    monkeypatch.setattr(module, "db_connect", fake_connect)
    monkeypatch.setattr(module, "load_conversation_with_origin", lambda conn, cid: {"id": cid})
    monkeypatch.setattr(module, "load_messages", lambda conn, cid: [{"role": "assistant"}])
    cached = {"answer": "cached", "context_snapshot_id": 3, "context_hash": "sha", "prompt_version": "v1"}
    dummy = Dummy()
    module.Handler.send_cached_abc_initial_analysis(
        dummy, "qa_owned", cached, stream=False, session={"sub": "alice", "role": "operator"}
    )
    assert dummy.session_seen["sub"] == "alice"
    assert dummy.json[0]["cache_hit"] is True
    sse = Dummy()
    module.Handler.send_cached_abc_initial_analysis(
        sse, "qa_owned", cached, stream=True, session={"sub": "alice", "role": "operator"}
    )
    assert [event for event, _ in sse.events][-2:] == ["final", "done"]
    source = (BACKEND / "ollama_proxy_server.py").read_text(encoding="utf-8")
    assert source.count("stream=wants_stream, session=session") == 2


def test_qa_write_csrf_requires_json_and_exact_same_origin() -> None:
    module = _proxy_module()

    class Dummy:
        client_address = ("10.0.0.8", 4321)

        def __init__(self, headers):
            self.headers = headers
            self.result = None

        def send_json(self, payload, status=200, headers=None):
            self.result = (payload, status)

    same = Dummy({"Content-Type": "application/json", "Origin": "http://host:8093", "Host": "host:8093"})
    assert module.Handler.qa_write_request_allowed(same) is True
    other_port = Dummy({"Content-Type": "application/json", "Origin": "http://host:8094", "Host": "host:8093"})
    assert module.Handler.qa_write_request_allowed(other_port) is False
    assert other_port.result[1] == 403
    plain = Dummy({"Content-Type": "text/plain", "Origin": "http://host:8093", "Host": "host:8093"})
    assert module.Handler.qa_write_request_allowed(plain) is False
    assert plain.result[1] == 415
    missing = Dummy({"Content-Type": "application/json", "Host": "host:8093"})
    assert module.Handler.qa_write_request_allowed(missing) is False
    assert missing.result[0]["error"] == "qa_origin_required"


def test_originless_qa_write_requires_explicit_controlled_loopback(monkeypatch) -> None:
    module = _proxy_module()
    monkeypatch.setenv("BF_QA_ALLOW_ORIGINLESS_LOOPBACK_CONTROLLED", "1")

    class Dummy:
        client_address = ("127.0.0.1", 1234)
        headers = {"Content-Type": "application/json", "Host": "localhost:8094", "X-BF-Controlled-Client": "1"}

        def send_json(self, payload, status=200, headers=None):
            raise AssertionError("controlled loopback must be allowed")

    assert module.Handler.qa_write_request_allowed(Dummy()) is True


def test_sensitive_qa_cors_never_uses_wildcard_or_cross_port_origin() -> None:
    module = _proxy_module()

    class Dummy:
        path = "/api/qa/chat"

        def __init__(self, origin):
            self.headers = {"Origin": origin, "Host": "host:8093"}
            self.sent = []

        def send_header(self, name, value):
            self.sent.append((name, value))

    same = Dummy("http://host:8093")
    module.Handler.add_cors(same)
    assert ("Access-Control-Allow-Origin", "http://host:8093") in same.sent
    assert all(value != "*" for name, value in same.sent if name == "Access-Control-Allow-Origin")
    cross = Dummy("http://host:8094")
    module.Handler.add_cors(cross)
    assert all(name != "Access-Control-Allow-Origin" for name, _ in cross.sent)


def test_contextual_conversation_payload_uses_exact_allowlist() -> None:
    source = (BACKEND / "ollama_proxy_server.py").read_text(encoding="utf-8")
    assert 'allowed_fields = {"source_type", "source_page", "rule_id", "evaluation_id", "reuse_policy"}' in source
    assert "contextual_conversation_unknown_fields" in source
