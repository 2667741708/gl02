from __future__ import annotations

import importlib.util
from unittest import mock
import sys
import unittest
from pathlib import Path


MODULE_PATH = Path(__file__).parents[1] / "高炉前端数据" / "智能助手" / "mcp" / "imes_relay_mcp_server.py"
SPEC = importlib.util.spec_from_file_location("imes_relay_mcp_server_tests", MODULE_PATH)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


class ImesRelayMcpTests(unittest.TestCase):
    def test_connection_target_only_allows_relay_loopback_or_fixed_22012_target(self):
        original = (MODULE.CONNECTION_MODE, MODULE.RELAY_HOST, MODULE.RELAY_PORT)
        try:
            MODULE.CONNECTION_MODE, MODULE.RELAY_HOST, MODULE.RELAY_PORT = "relay", "127.0.0.1", 15433
            MODULE.validate_connection_target()
            MODULE.CONNECTION_MODE, MODULE.RELAY_HOST, MODULE.RELAY_PORT = "direct_22012", "10.10.181.195", 5432
            MODULE.validate_connection_target()
            MODULE.RELAY_HOST = "10.10.181.209"
            with self.assertRaisesRegex(RuntimeError, "unsupported"):
                MODULE.validate_connection_target()
        finally:
            MODULE.CONNECTION_MODE, MODULE.RELAY_HOST, MODULE.RELAY_PORT = original

    def test_direct_mode_removes_range_and_row_caps(self):
        original = MODULE.CONNECTION_MODE
        try:
            MODULE.CONNECTION_MODE = "direct_22012"
            self.assertEqual(MODULE.bounded_range("2024-01-01", "2026-07-16"), ("2024-01-01", "2026-07-16"))
            self.assertEqual(MODULE.bounded_limit(None), 0)
            self.assertEqual(MODULE.bounded_limit(50000), 50000)
        finally:
            MODULE.CONNECTION_MODE = original

    def test_readonly_sql_validator_blocks_writes_and_multi_statement_escape(self):
        self.assertEqual(MODULE.validate_readonly_sql("SELECT 1;"), "SELECT 1")
        with self.assertRaisesRegex(ValueError, "read-only"):
            MODULE.validate_readonly_sql("DELETE FROM public.batch_input")
        with self.assertRaisesRegex(ValueError, "exactly one"):
            MODULE.validate_readonly_sql("SELECT 1; SELECT 2")

    def test_semantic_search_resolves_hot_metal_silicon(self):
        matches = MODULE.semantic_matches("查一下铁水硅含量")
        self.assertEqual(matches[0]["object"], "public.inner_batch_insp_bb")
        self.assertEqual(matches[0]["field"], "value_02")
        self.assertEqual(matches[0]["confidence"], "confirmed")

    def test_generated_semantic_catalog_covers_all_actual_variables(self):
        catalog = MODULE.full_variable_catalog()
        self.assertEqual(catalog["object_count"], 11)
        self.assertEqual(catalog["entry_count"], 315)
        self.assertEqual(len(catalog["entries"]), 315)
        self.assertEqual(
            len({item["object"] for item in catalog["entries"]}),
            11,
        )

    def test_semantic_search_understands_colloquial_examples_across_objects(self):
        cases = {
            "看看24号料仓投料": (
                "operations",
                "public.batch_input",
                "value_24",
                "workdate",
            ),
            "烧结矿QD强度是多少": (
                "laboratory",
                "public.v_qpes_sinter_machine_sample_insp_final",
                "qdvalue",
                "业务日期",
            ),
            "查一下炼钢钨含量": (
                "laboratory",
                "public.v_qpes_steel_final",
                "wmdvalue",
                "businessdate",
            ),
            "这个炉次铁口深度多少": (
                "operations",
                "public.t_ipes_cond",
                "depth",
                "workdate",
            ),
        }
        for question, expected in cases.items():
            with self.subTest(question=question):
                match = MODULE.semantic_matches(question)[0]
                self.assertEqual(
                    (
                        match["account_profile"],
                        match["object"],
                        match["field"],
                        match["time_field"],
                    ),
                    expected,
                )
                self.assertTrue(match["speech_example"])

    def test_semantic_resolver_returns_variable_query_arguments(self):
        result = MODULE.resolve_semantic_intent("看看24号料仓投料")
        self.assertEqual(result["recommended_tool"], "query_imes_variables")
        self.assertEqual(
            result["next_arguments"],
            {
                "account_profile": "operations",
                "object_name": "public.batch_input",
                "variables": ["value_24"],
                "time_column": "workdate",
            },
        )

    def test_semantic_resolver_understands_colloquial_bf2_iron_output(self):
        result = MODULE.resolve_semantic_intent("看看2号炉昨天每炉出了多少铁")
        self.assertEqual(result["resolved_object"], "public.t_ipes_out_put")
        self.assertEqual(result["furnace_filter"], "2#")

    def test_semantic_resolver_routes_new_chemistry_intents(self):
        cases = {
            "查2#20260716-101炉次的硅和锰": "query_heat_chemistry",
            "这一炉的炉渣成分怎么样": "query_blast_furnace_slag_by_heat",
            "看看今天2号烧结机来料化学成分": "query_sinter_feed_chemistry",
        }
        for question, expected in cases.items():
            with self.subTest(question=question):
                self.assertEqual(MODULE.resolve_semantic_intent(question)["recommended_tool"], expected)

    def test_business_identifier_validation(self):
        self.assertEqual(MODULE._required_text(" 2#20260716-101 ", "heat_no"), "2#20260716-101")
        with self.assertRaises(ValueError):
            MODULE._required_text("", "heat_no")

    def test_unknown_slag_indicator_is_not_guessed(self):
        result = MODULE.explain_imes_variable("public.slag_inspection", "value_01")
        self.assertEqual(result["confidence"], "unknown")

    def test_bounded_range_rejects_reverse_and_excessive_ranges(self):
        with self.assertRaises(ValueError):
            MODULE.bounded_range("2026-07-16", "2026-07-15")
        with self.assertRaises(ValueError):
            MODULE.bounded_range("2025-01-01", "2026-07-16")

    def test_bounded_limit_is_clamped(self):
        self.assertEqual(MODULE.bounded_limit(1), 1)
        self.assertEqual(MODULE.bounded_limit(99999), MODULE.MAX_ROWS)
        with self.assertRaises(ValueError):
            MODULE.bounded_limit(0)

    def test_plain_serializes_dates(self):
        self.assertEqual(MODULE.plain(__import__("datetime").date(2026, 7, 16)), "2026-07-16")
        self.assertEqual(MODULE.plain(0.24), 0.24)

    def test_multi_account_profiles_have_distinct_purposes(self):
        profiles = MODULE.database_profiles()
        self.assertEqual(set(profiles), {"operations", "laboratory"})
        self.assertIn("炉次作业", profiles["operations"]["purpose"])
        self.assertIn("最终化验视图", profiles["laboratory"]["purpose"])
        self.assertEqual(MODULE.normalize_profile("LABORATORY"), "laboratory")
        with self.assertRaisesRegex(ValueError, "unknown account_profile"):
            MODULE.normalize_profile("administrator")

    def test_local_common_vastbase_account_is_used_for_both_profiles(self):
        with mock.patch.dict(
            MODULE.os.environ,
            {"IMES_DB_USER": "lg_fq_test", "IMES_DB_PASSWORD": "secret"},
            clear=True,
        ):
            profiles = MODULE.database_profiles()
        self.assertEqual(profiles["operations"]["user"], "lg_fq_test")
        self.assertEqual(profiles["laboratory"]["user"], "lg_fq_test")

    def test_chemistry_tools_use_configured_profile(self):
        calls = []

        class Cursor:
            description = [("heatno",), ("batchno",), ("si",)]

            def execute(self, query, params):
                self.query = query
                self.params = params

            def fetchall(self):
                return [("2#20260805-065", "B065", "0.23")]

            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

        class Connection:
            def cursor(self):
                return Cursor()

            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

        def fake_connection(profile="operations"):
            calls.append(profile)
            return Connection()

        with mock.patch.object(MODULE, "connection", fake_connection):
            result = MODULE.query_hot_metal_chemistry_by_heat("2#20260805-065")
        # The chemistry result is followed by a read-only operations lookup
        # to attach the official heat time window.
        self.assertEqual(calls, [MODULE.CHEMISTRY_ACCOUNT_PROFILE, "operations"])
        self.assertEqual(result["account_profile"], MODULE.CHEMISTRY_ACCOUNT_PROFILE)
        self.assertFalse(result["missing"])

        calls.clear()
        with mock.patch.object(MODULE, "connection", fake_connection):
            ranged = MODULE.query_hot_metal_silicon("2026-08-05", "2026-08-05")
        self.assertEqual(calls, [MODULE.CHEMISTRY_ACCOUNT_PROFILE])
        self.assertEqual(ranged["account_profile"], MODULE.CHEMISTRY_ACCOUNT_PROFILE)

    def test_profile_summary_never_returns_password(self):
        config = {
            "purpose": "test",
            "host": "127.0.0.1",
            "port": 15433,
            "dbname": "vastbase",
            "user": "reader",
            "password": "plaintext-secret",
        }
        summary = MODULE.safe_profile_summary("test", config)
        self.assertNotIn("password", summary)
        self.assertFalse(summary["password_exposed"])

    def test_any_query_limit_is_bounded(self):
        self.assertEqual(MODULE.bounded_any_query_limit(None), 500)
        self.assertEqual(
            MODULE.bounded_any_query_limit(MODULE.ANY_QUERY_MAX_ROWS + 1),
            MODULE.ANY_QUERY_MAX_ROWS,
        )
        with self.assertRaises(ValueError):
            MODULE.bounded_any_query_limit(0)

    def test_variable_query_rejects_unknown_column_before_database_access(self):
        item = MODULE.vastbase.DbObject(
            schema="public",
            name="demo",
            object_type="VIEW",
            category="其他",
            columns=("workdate", "value_01"),
            date_column="workdate",
            selectable=True,
        )
        original = MODULE.object_by_name
        try:
            MODULE.object_by_name = lambda object_name, account_profile="operations": item
            with self.assertRaisesRegex(ValueError, "unknown variables"):
                MODULE.query_imes_variables(
                    "public.demo",
                    ["not_a_column"],
                    account_profile="operations",
                )
        finally:
            MODULE.object_by_name = original

    def test_object_lookup_rejects_unapproved_objects(self):
        MODULE.selectable_mes_objects.cache_clear()
        old = MODULE.selectable_mes_objects
        try:
            MODULE.selectable_mes_objects = lambda account_profile="operations": ()
            with self.assertRaises(ValueError):
                MODULE.object_by_name("public_history.vb_login_info")
        finally:
            MODULE.selectable_mes_objects = old


if __name__ == "__main__":
    unittest.main()
