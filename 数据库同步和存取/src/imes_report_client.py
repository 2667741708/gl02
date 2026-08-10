"""Read-only client for the 2# blast-furnace Raqsoft operation-log report.

The report is not a normal IMES ``*Data.do`` JSON endpoint.  It uses a
two-step POST flow: the first request creates a report query, and the second
request returns the rendered HTML grid.  This module keeps the protocol and
the report's calculated columns explicit so callers never confuse report
formula values with raw IMES database fields.
"""
from __future__ import annotations

import html
import math
import re
from datetime import date, datetime
from html.parser import HTMLParser
from typing import Any
from urllib.parse import urljoin

import requests

from imes_readonly_client import DatasetDef


REPORT_DATASET = DatasetDef(
    key="bf2_operation_log_report",
    label="2#高炉冀南新区高炉作业日志（报表查询结果）",
    endpoint="demo/reportServlet?action=8;demo/reportJsp/queryInput.jsp",
    table_name="imes_bf2_operation_log_report",
    default_params={"prodcentercode": "2D012"},
    notes=(
        "Raqsoft 报表两段 POST 结果；保留全部返回单元格。D列为报表批数，"
        "燃料比按页面公式重算；料速未按批数强行推断。"
    ),
)


REPORT_COLUMN_LETTERS = (
    "A", "B", "C", "D", "E", "F", "G", "H", "I", "J", "K", "L", "M", "N",
    "O", "P", "Q", "R", "S", "T", "U", "V", "W", "X", "Y", "Z", "AA", "AB",
    "AC", "AD", "AE", "AF", "AG", "AH", "AI", "AJ", "AK", "AL", "AM", "AN",
    "AO", "AP", "AQ", "AR", "AS", "AT", "AU", "AV", "AW", "AX", "AY", "AZ",
    "BA", "BB", "BC", "BD", "BE", "BF", "BG", "BH", "BI", "BJ", "BK", "BL",
    "BM", "BN", "BO", "BP", "BQ",
)


def _clean_text(value: str) -> str:
    return re.sub(r"\s+", " ", html.unescape(value or "")).strip()


def _number(value: Any) -> float | None:
    text = _clean_text(str(value or "")).replace(",", "")
    if not text or text in {"-", "—", "null", "None"}:
        return None
    try:
        number = float(text)
        return number if math.isfinite(number) else None
    except ValueError:
        return None


class _ReportGridParser(HTMLParser):
    """Parse only the ``sg2130`` grid and preserve raw/display cell values."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.rows: list[dict[str, Any]] = []
        self._row: dict[str, Any] | None = None
        self._cell: dict[str, Any] | None = None
        self._cell_text: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        data = {key.lower(): value or "" for key, value in attrs}
        element_id = data.get("id", "")
        if tag.lower() == "tr" and element_id.startswith("sg2130_row"):
            match = re.search(r"row(\d+)$", element_id)
            self._row = {
                "row_number": int(match.group(1)) if match else None,
                "header": data.get("header", "") == "1",
                "cells": {},
            }
            return
        if tag.lower() == "td" and self._row is not None and element_id.startswith("sg2130_"):
            match = re.search(r"sg2130_([A-Z]+)(\d+)$", element_id)
            if not match:
                return
            self._cell = {
                "column": match.group(1),
                "col_no": int(data.get("colno") or 0) or None,
                "raw_value": data.get("value", ""),
                "display_text": "",
            }
            self._cell_text = []

    def handle_data(self, data: str) -> None:
        if self._cell is not None:
            self._cell_text.append(data)

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        if tag == "td" and self._cell is not None and self._row is not None:
            self._cell["display_text"] = _clean_text("".join(self._cell_text))
            column = str(self._cell.pop("column"))
            self._row["cells"][column] = self._cell
            self._cell = None
            self._cell_text = []
        elif tag == "tr" and self._row is not None:
            self.rows.append(self._row)
            self._row = None


def _header_map(rows: list[dict[str, Any]]) -> dict[str, str]:
    headers: dict[str, str] = {}
    by_number = {int(row["row_number"]): row for row in rows if row.get("row_number") is not None}
    for number in (5, 6):
        row = by_number.get(number, {})
        for column, cell in row.get("cells", {}).items():
            title = _clean_text(str(cell.get("raw_value") or cell.get("display_text") or ""))
            if title and column not in headers:
                headers[column] = title
            elif title and number == 6:
                headers[column] = title
    return headers


def _calculate_report_metrics(cells: dict[str, Any], headers: dict[str, str]) -> dict[str, Any]:
    values = {column: _number(cell.get("raw_value")) for column, cell in cells.items()}
    batch_count = values.get("D")
    ore_batch = values.get("F")
    coke_batch = values.get("G")
    coke_breeze = values.get("H")
    moisture = values.get("I")
    pulverized_coal = values.get("J")
    # Header constants are represented by row 5 cells; callers pass their
    # numeric values in the header map with private keys.
    fe_grade = _number(headers.get("__fe_grade")) or 0.555
    fe_element = _number(headers.get("__fe_element")) or 0.945
    coal_ratio: float | None = None
    fuel_ratio: float | None = None
    if all(value is not None for value in (batch_count, ore_batch, pulverized_coal, fe_grade, fe_element)) and batch_count:
        denominator = ore_batch * fe_grade / fe_element * 0.995
        if denominator:
            coal_ratio = (pulverized_coal / 1000 / batch_count) / denominator * 1000
    if all(value is not None for value in (coke_batch, coke_breeze, moisture, ore_batch, fe_grade, fe_element, coal_ratio)):
        denominator = ore_batch * fe_grade / fe_element * 0.995 / 1000
        if denominator:
            fuel_ratio = (coke_batch * (1 - moisture) + coke_breeze * (1 - moisture)) / denominator + coal_ratio
    return {
        "report_batch_count": batch_count,
        "report_ore_batch": ore_batch,
        "report_coke_batch": coke_batch,
        "report_coke_breeze": coke_breeze,
        "report_moisture": moisture,
        "report_pulverized_coal": pulverized_coal,
        "report_coal_ratio": coal_ratio,
        "report_fuel_ratio": fuel_ratio,
        "material_rate": None,
        "material_rate_status": "semantic_unconfirmed",
        "material_rate_note": "报表D列语义为批数；未将批数直接当作料速。",
        "metric_source": "report_formula_recomputed",
    }


def parse_operation_log_html(html_text: str, workdate: date | str, max_rows: int = 0) -> dict[str, Any]:
    parser = _ReportGridParser()
    parser.feed(html_text)
    headers = _header_map(parser.rows)
    by_number = {int(row["row_number"]): row for row in parser.rows if row.get("row_number") is not None}
    header5 = by_number.get(5, {}).get("cells", {})
    headers["__fe_grade"] = str(header5.get("G", {}).get("raw_value") or "0.555")
    headers["__fe_element"] = str(header5.get("I", {}).get("raw_value") or "0.945")
    rows: list[dict[str, Any]] = []
    for row in parser.rows:
        row_number = row.get("row_number")
        cells = row.get("cells") or {}
        if not isinstance(row_number, int) or row_number < 7:
            continue
        # Rows after the main table contain shift/material sub-sections. Main
        # operation rows always have numeric sequence A and report ID B.
        if _number(cells.get("A", {}).get("raw_value")) is None or not _clean_text(str(cells.get("B", {}).get("raw_value") or "")):
            continue
        metrics = _calculate_report_metrics(cells, headers)
        row_json = {
            "_dataset_key": REPORT_DATASET.key,
            "_dataset_label": REPORT_DATASET.label,
            "_source_endpoint": REPORT_DATASET.endpoint,
            "_fetched_at": datetime.now().replace(microsecond=0).strftime("%Y-%m-%d %H:%M:%S"),
            "workdate": str(workdate),
            "prodcentercode": "2D012",
            "report_row_number": row_number,
            "report_id": cells.get("A", {}).get("raw_value", ""),
            "report_time_raw": cells.get("B", {}).get("raw_value", ""),
            "report_time_display": cells.get("B", {}).get("display_text", ""),
            "headers": {key: value for key, value in headers.items() if not key.startswith("__")},
            "cells": cells,
            **metrics,
        }
        row_json["_row_key"] = f"{REPORT_DATASET.key}|{workdate}|{row_number}"
        rows.append(row_json)
        if max_rows and len(rows) >= max_rows:
            break
    return {
        "ok": True,
        "dataset": REPORT_DATASET.key,
        "label": REPORT_DATASET.label,
        "endpoint": REPORT_DATASET.endpoint,
        "workdate": str(workdate),
        "prodcentercode": "2D012",
        "columns": [{"field": f"cell_{column}", "title": headers.get(column, "")} for column in REPORT_COLUMN_LETTERS],
        "rows_count": len(rows),
        "total": len(rows),
        "rows": rows,
        "formula_notes": {
            "report_coal_ratio": "按 Raqsoft 页面 K 列公式重算",
            "report_fuel_ratio": "按 Raqsoft 页面 M 列公式重算；原始 M 列常为空",
            "material_rate": "未从批数推断；需现场确认料速字段/公式",
        },
    }


class RaqsoftReportClient:
    def __init__(self, base_url: str, timeout: float = 30.0) -> None:
        self.base_url = base_url.rstrip("/") + "/"
        self.timeout = timeout
        self.session = requests.Session()

    def fetch_operation_log(
        self,
        workdate: date | str,
        prodcentercode: str = "2D012",
        max_rows: int = 0,
    ) -> dict[str, Any]:
        day = workdate.isoformat() if isinstance(workdate, date) else str(workdate)
        show_url = urljoin(self.base_url, "demo/reportJsp/showInput.jsp?sht=mes/jn_ts_glbb_tb.sht")
        first_url = urljoin(self.base_url, "demo/reportServlet?action=8")
        first_payload = {
            "time1": day,
            "prodcentercode": prodcentercode,
            "hiddenParams": "sht=mes/jn_ts_glbb_tb.sht;",
            "resultContainer": "reportContainer",
            "resultPage": "queryInput.jsp?sht=mes%2Fjn_ts_glbb_tb.sht&adp=&dataFile=&fileType=json&sgid=sg213",
        }
        first = self.session.post(first_url, data=first_payload, timeout=self.timeout)
        first.raise_for_status()
        query_spec = first.text.strip()
        if "|||" not in query_spec:
            raise RuntimeError(f"IMES 报表首段响应缺少查询分隔符: {query_spec[:200]!r}")
        query_path, query_body = query_spec.split("|||", 1)
        query_url = urljoin(show_url, query_path.strip())
        second = self.session.post(
            query_url,
            data=query_body,
            headers={"Content-Type": "application/x-www-form-urlencoded; charset=UTF-8"},
            timeout=self.timeout,
        )
        second.raise_for_status()
        payload = parse_operation_log_html(second.text, day, max_rows=max_rows)
        payload["request"] = {"show_url": show_url, "query_url": query_url, "prodcentercode": prodcentercode}
        return payload
