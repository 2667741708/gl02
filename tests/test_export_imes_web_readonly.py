from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path
from typing import Any


MODULE_PATH = Path(__file__).parents[1] / "tools" / "export_imes_web_readonly.py"
SPEC = importlib.util.spec_from_file_location("export_imes_web_readonly", MODULE_PATH)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


class FakeResponse:
    def __init__(self, payload: Any, text: str = "success") -> None:
        self._payload = payload
        self.text = text

    def raise_for_status(self) -> None:
        return None

    def json(self) -> Any:
        return self._payload


class FakeSession:
    def __init__(self, responses: list[FakeResponse]) -> None:
        self.responses = list(responses)
        self.calls: list[dict[str, Any]] = []

    def post(self, url: str, data: dict[str, Any], timeout: int) -> FakeResponse:
        self.calls.append({"url": url, "data": dict(data), "timeout": timeout})
        return self.responses.pop(0)


class ImesReadonlyExportTests(unittest.TestCase):
    def test_normalize_bootstrap_table_payload(self) -> None:
        rows, total = MODULE.normalize_payload({"total": 2, "rows": [{"id": 1}]})
        self.assertEqual([{"id": 1}], rows)
        self.assertEqual(2, total)

    def test_normalize_plain_array_payload(self) -> None:
        rows, total = MODULE.normalize_payload([{"id": 1}, {"id": 2}])
        self.assertEqual(2, total)
        self.assertEqual(2, len(rows))

    def test_fetch_dataset_pages_with_size_and_offset(self) -> None:
        session = FakeSession(
            [
                FakeResponse({"total": 3, "rows": [{"id": 1}, {"id": 2}]}),
                FakeResponse({"total": 3, "rows": [{"id": 3}]}),
            ]
        )
        spec = MODULE.DATASETS["output"]
        rows = list(
            MODULE.fetch_dataset(
                session,
                MODULE.DEFAULT_BASE_URL,
                spec,
                {"prodCenterCode": "2D012"},
                page_size=2,
                max_pages=5,
                timeout=20,
            )
        )
        self.assertEqual([1, 2, 3], [row["id"] for row in rows])
        self.assertEqual([0, 2], [call["data"]["_index"] for call in session.calls])
        self.assertTrue(all(call["data"]["_size"] == 2 for call in session.calls))

    def test_workdate_range_expands_to_inclusive_daily_queries(self) -> None:
        spec = MODULE.DATASETS["batch_all"]
        windows = MODULE.build_query_windows(
            spec,
            "2026-07-13",
            "2026-07-15",
            workdate=None,
        )
        self.assertEqual(
            ["2026-07-13", "2026-07-14", "2026-07-15"],
            [window["workdate"] for window in windows],
        )

    def test_explicit_workdate_overrides_range(self) -> None:
        spec = MODULE.DATASETS["batch_coke"]
        windows = MODULE.build_query_windows(
            spec,
            "2026-07-01",
            "2026-07-15",
            workdate="2026-07-14",
        )
        self.assertEqual(1, len(windows))
        self.assertEqual("2026-07-14", windows[0]["workdate"])

    def test_export_one_combines_multiple_workdates(self) -> None:
        session = FakeSession(
            [
                FakeResponse({"total": 1, "rows": [{"workdate": "2026-07-13"}]}),
                FakeResponse({"total": 1, "rows": [{"workdate": "2026-07-14"}]}),
            ]
        )
        with tempfile.TemporaryDirectory() as temp_dir:
            result = MODULE.export_one(
                session,
                MODULE.DEFAULT_BASE_URL,
                "batch_mining",
                Path(temp_dir),
                "2026-07-13",
                "2026-07-14",
                workdate=None,
                page_size=50,
                max_pages=5,
                timeout=20,
            )
            self.assertEqual(2, result["rows"])
            self.assertEqual(2, len(result["queries"]))
            self.assertEqual("workdate", result["date_mode"])

    def test_query_dataset_rejects_unknown_key(self) -> None:
        session = FakeSession([])
        with self.assertRaises(KeyError):
            list(
                MODULE.query_dataset(
                    session,
                    MODULE.DEFAULT_BASE_URL,
                    "not_a_dataset",
                    "2026-07-13",
                    "2026-07-14",
                )
            )

    def test_allowlist_contains_no_obvious_write_endpoint(self) -> None:
        forbidden = ("/edit", "/delete", "/del.", "/add", "/save", "/send", "/examine")
        for key, spec in MODULE.DATASETS.items():
            lowered = spec.path.lower()
            self.assertFalse(
                any(token in lowered for token in forbidden),
                msg=f"{key} is not read-only: {spec.path}",
            )

    def test_manifest_data_is_json_serializable(self) -> None:
        sample = {"dataset": "output", "spec": asdict_for_test(MODULE.DATASETS["output"])}
        json.dumps(sample, ensure_ascii=False)


def asdict_for_test(spec: Any) -> dict[str, Any]:
    return {
        "label": spec.label,
        "path": spec.path,
        "fixed_params": spec.fixed_params,
        "date_mode": spec.date_mode,
        "paged": spec.paged,
        "time_field": spec.time_field,
    }


if __name__ == "__main__":
    unittest.main()
