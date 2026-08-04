# -*- coding: utf-8 -*-
from __future__ import annotations

import argparse
import unittest

from tools.audit_imes_granted_views import (
    choose_latest_column,
    quote_ident,
    summarize_samples,
    validate_args,
)


class AuditImesGrantedViewsTests(unittest.TestCase):
    def test_quote_ident_supports_unicode_and_escapes_quotes(self) -> None:
        self.assertEqual(quote_ident("试样号"), '"试样号"')
        self.assertEqual(quote_ident('a"b'), '"a""b"')

    def test_summarize_samples_handles_nulls_and_distinct_values(self) -> None:
        summary = summarize_samples(["元素"], [("0.20",), (None,), ("0.20",), ("0.21",)], 5)
        self.assertEqual(summary["元素"]["non_null"], 3)
        self.assertEqual(summary["元素"]["nulls"], 1)
        self.assertEqual(summary["元素"]["distinct_in_sample"], 2)
        self.assertEqual(summary["元素"]["examples"], ["0.20", "0.21"])

    def test_choose_latest_column_uses_publish_time_priority(self) -> None:
        columns = [{"name": "业务日期"}, {"name": "发布时间"}]
        self.assertEqual(choose_latest_column(columns), "发布时间")

    def test_validate_args_rejects_unsafe_view_name(self) -> None:
        args = argparse.Namespace(
            views=["v_ok; DROP TABLE x"],
            sample_limit=50,
            example_limit=5,
            statement_timeout_ms=30000,
        )
        with self.assertRaises(ValueError):
            validate_args(args)


if __name__ == "__main__":
    unittest.main()

