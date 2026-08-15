from __future__ import annotations

import importlib.util
import sys
from datetime import datetime
from pathlib import Path

import pandas as pd
import pytest


ROOT = Path(__file__).resolve().parents[1]
BACKEND_PATH = ROOT / "高炉前端数据" / "智能助手" / "backend" / "hcz_expert_label.py"
SERVER_PATH = ROOT / "tools" / "soft_zone_replay_server.py"


def load_path(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def base_payload() -> dict[str, object]:
    return {
        "idempotency_key": "hcz-ui:20260810:12345678",
        "observed_at": "2026-08-10T10:30:00+08:00",
        "source_window_start": "2026-08-10T09:00:00+08:00",
        "source_window_end": "2026-08-10T10:30:00+08:00",
        "root_level_label": "normal",
        "movement_label": "stable",
        "center_height_m": "23.5",
        "thickness_m": "2.4",
        "eccentric_sector": "none",
        "confidence_grade": 4,
        "evidence_codes": ["temperature_pattern", "pressure_permeability"],
        "operator_name": "GL02-甲班",
        "note": "温度环带及压差走势平稳",
    }


def measured_frame() -> pd.DataFrame:
    index = pd.date_range("2026-08-10 09:00", "2026-08-10 10:30", freq="5min")
    return pd.DataFrame(
        {
            "T_body_L7_A": [310.0 + number for number in range(len(index))],
            "P_static_lower_A": [18.0 + number / 10 for number in range(len(index))],
        },
        index=index,
    )


def test_payload_is_explicitly_weak_label_and_rejects_model_output() -> None:
    module = load_path("hcz_expert_label_test", BACKEND_PATH)
    validated = module.validate_label_payload(base_payload())

    assert validated["furnace_id"] == "GL02"
    assert validated["root_level_label"] == "normal"
    assert validated["center_height_m"] == 23.5

    unsafe = {**base_payload(), "model_prediction": {"root_height_m": 24.1}}
    with pytest.raises(module.HczLabelValidationError, match="不得包含"):
        module.validate_label_payload(unsafe)


def test_uncertain_pair_requires_a_reason() -> None:
    module = load_path("hcz_expert_label_uncertain_test", BACKEND_PATH)
    payload = {
        **base_payload(),
        "root_level_label": "uncertain",
        "movement_label": "uncertain",
        "note": "",
    }
    with pytest.raises(module.HczLabelValidationError, match="说明原因"):
        module.validate_label_payload(payload)


def test_source_context_is_deterministic_blind_and_knowledge_time_aware() -> None:
    module = load_path("hcz_expert_label_context_test", BACKEND_PATH)
    kwargs = {
        "observed_at": "2026-08-10T10:00:00+08:00",
        "window_start": "2026-08-10T09:00:00+08:00",
        "window_end": "2026-08-10T10:30:00+08:00",
        "primary_variables": ("T_body_L7_A", "P_static_lower_A"),
    }
    first = module.build_source_context(measured_frame(), **kwargs)
    second = module.build_source_context(measured_frame(), **kwargs)

    assert first["source_data_hash"] == second["source_data_hash"]
    assert len(first["source_data_hash"]) == 64
    assert first["blind_to_model"] is True
    assert first["model_outputs_included"] is False
    assert first["context_mode"] == "retrospective_with_post_observation_evidence"
    assert first["uses_post_observation_data"] is True


class FakeRepository:
    def latest_timestamp(self) -> datetime:
        return datetime(2026, 8, 10, 10, 30)

    def read_window(self, start: datetime, end: datetime):
        assert start < end
        return {}, measured_frame()


class FakeStore:
    def __init__(self):
        self.saved = None

    def save(self, label, context, identity, *, client_address=""):
        self.saved = (label, context, identity, client_address)
        return {
            "id": 1,
            "reference_id": "HCZ-test",
            "created": True,
            "source_data_hash": context["source_data_hash"],
        }

    def list_labels(self, **_kwargs):
        return []


def review_config(module):
    return module.ReviewConfig(
        enabled=True,
        test_mode=False,
        require_login=False,
        anonymous_username="现场标注席",
        anonymous_role="blast_furnace_operator",
        pg_host="127.0.0.1",
        pg_port=5432,
        pg_database="bf_trend",
        pg_user="writer",
        pg_password="not-used-by-fake",
        pg_schema="bf_assistant",
        allowed_roles=("blast_furnace_operator",),
        session_ttl_seconds=28800,
    )


def test_service_rebuilds_measured_context_and_uses_server_identity() -> None:
    module = load_path("soft_zone_hcz_service_test", SERVER_PATH)
    store = FakeStore()
    service = module.ReplayService(FakeRepository(), store, review_config(module))
    payload = base_payload()
    context = service.label_context(
        {
            "observed_at": [str(payload["observed_at"])],
            "start": [str(payload["source_window_start"])],
            "end": [str(payload["source_window_end"])],
        },
        "",
    )
    payload["source_data_hash"] = context["source_data_hash"]

    result = service.submit_label(payload, "", client_address="127.0.0.1")

    assert result["ok"] is True
    assert store.saved is not None
    saved_label, saved_context, identity, client = store.saved
    assert saved_label["operator_name"] == "GL02-甲班"
    assert saved_context["model_outputs_included"] is False
    assert identity["sub"] == "现场标注席"
    assert client == "127.0.0.1"


def test_schema_contract_is_append_only_and_has_knowledge_times() -> None:
    ddl = (BACKEND_PATH.parent / "schema" / "postgresql_hcz_expert_label.sql").read_text(encoding="utf-8")

    assert "hcz_expert_label_events" in ddl
    assert "observed_at TIMESTAMPTZ NOT NULL" in ddl
    assert "available_at TIMESTAMPTZ NOT NULL" in ddl
    assert "blind_to_model BOOLEAN NOT NULL CHECK (blind_to_model)" in ddl
    assert "UPDATE " not in ddl.upper()
    assert "DELETE " not in ddl.upper()


def test_labeling_page_embeds_forced_blind_replay() -> None:
    frontend = ROOT / "高炉前端数据" / "soft_zone_replay"
    html = (frontend / "hcz-labeling.html").read_text(encoding="utf-8")
    script = (frontend / "soft-zone-replay.js").read_text(encoding="utf-8")

    assert 'src="/?labeling_blind=1"' in html
    assert "只显示炉体温度、静压力等实测证据" in html
    assert "BLIND_LABEL_MODE ? \"0\"" in script
    assert "model_outputs_included: false" in script
