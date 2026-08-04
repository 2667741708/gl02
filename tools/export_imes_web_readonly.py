# -*- coding: utf-8 -*-
"""Export authorized IMES Web query data without calling write endpoints.

Requirement: OPS-IMES-VASTBASE-20260715
Documentation: docs/imes.md

Credentials are accepted only through environment variables:
IMES_WEB_USER, IMES_WEB_PASSWORD and IMES_WEB_CAPTCHA.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Iterable
from urllib.parse import urljoin

import requests


DEFAULT_BASE_URL = "http://10.10.181.209:8080/imes.web/"
DEFAULT_TIMEOUT_SECONDS = 20


@dataclass(frozen=True)
class DatasetSpec:
    """One explicitly approved IMES read endpoint."""

    label: str
    path: str
    fixed_params: dict[str, str]
    date_mode: str = "none"  # none | range | workdate
    paged: bool = True
    time_field: str | None = None


DATASETS: dict[str, DatasetSpec] = {
    "pes_bin": DatasetSpec(
        "2#高炉料仓",
        "mes/ipes/pesBin/listPageData.do",
        {"prodCenterCode": "2D012"},
        time_field=None,
    ),
    "pes_bin_material": DatasetSpec(
        "2#高炉料仓变料",
        "mes/ipes/pesBinMaterial/listPageData.do",
        {"prodCenterCode": "2D012"},
        "range",
        time_field="businessDate",
    ),
    "production_month_plan": DatasetSpec(
        "2#高炉生产月计划",
        "mes/cpes/productionPlanMonth/listMonthData.do",
        {"sinteringMachineCode": "2D012"},
        paged=False,
        time_field="planMonth",
    ),
    "dosing_scheme": DatasetSpec(
        "2#高炉配料方案",
        "mes/ipes/dosingScheme/listPageData.do",
        {"prodCenterCode": "2D012"},
        "range",
        time_field="businessDate",
    ),
    "input": DatasetSpec(
        "2#高炉原料投入",
        "mes/ipes/input/listPageData.do",
        {"prodCenterCode": "2D012"},
        "range",
        time_field="workDate",
    ),
    "batch_all": DatasetSpec(
        "2#高炉批次投料合并",
        "mes/ipes/input/listPageData2.do",
        {"prodCenterCode": "2D012", "lot": ""},
        "workdate",
        time_field="workdate",
    ),
    "batch_mining": DatasetSpec(
        "2#高炉批次投料矿批",
        "mes/ipes/input/listPageData3.do",
        {"prodCenterCode": "2D012", "lot": ""},
        "workdate",
        time_field="workdate",
    ),
    "batch_coke": DatasetSpec(
        "2#高炉批次投料焦批",
        "mes/ipes/input/listPageData4.do",
        {"prodCenterCode": "2D012", "lot": ""},
        "workdate",
        time_field="workdate",
    ),
    "output": DatasetSpec(
        "2#高炉生产实绩",
        "mes/ipes/outputM/listCondData.do",
        {"prodCenterCode": "2D012", "meltNo": ""},
        "range",
        time_field="workDate",
    ),
    "heat_lab": DatasetSpec(
        "2#高炉炉次化验",
        "mes/ipes/outputM/listCondDataAvg2.do",
        {"prodCenterCode": "2D012", "meltNo": ""},
        "range",
        time_field="workDate",
    ),
    "slag_lab": DatasetSpec(
        "炉渣检验",
        "mes/qpes/productManage/listInspData3.do",
        {"prodCenterCode": "JLZ2", "meltNo": ""},
        "range",
        time_field="publishtime/workDate",
    ),
    "heat_lab_all": DatasetSpec(
        "2#高炉炉次化验全量",
        "mes/ipes/outputM/listCondDataAvg2New.do",
        {"prodCenterCode": "2D012", "meltNo": ""},
        "range",
        paged=False,
        time_field="workDate/createTime",
    ),
}


def parse_iso_date(value: str) -> str:
    """Validate an ISO date and return its canonical value."""

    return date.fromisoformat(value).isoformat()


def normalize_payload(payload: Any) -> tuple[list[dict[str, Any]], int]:
    """Normalize bootstrap-table and plain-array responses."""

    if isinstance(payload, dict) and isinstance(payload.get("rows"), list):
        rows = payload["rows"]
        total = int(payload.get("total", len(rows)))
    elif isinstance(payload, list):
        rows = payload
        total = len(rows)
    else:
        raise ValueError("unsupported IMES response shape")
    if not all(isinstance(row, dict) for row in rows):
        raise ValueError("IMES response contains a non-object row")
    return rows, total


def login(
    session: requests.Session,
    base_url: str,
    username: str,
    password: str,
    captcha: str,
    timeout: int,
) -> None:
    """Create an authorized IMES JSESSIONID session."""

    response = session.post(
        urljoin(base_url, "login.do"),
        data={"username": username, "password": password, "captchaInput": captcha},
        timeout=timeout,
    )
    response.raise_for_status()
    result = response.text.strip()
    if result != "success":
        raise RuntimeError(f"IMES login failed: {result or 'empty response'}")


def build_query_params(
    spec: DatasetSpec,
    start_date: str,
    end_date: str,
    workdate: str | None,
) -> dict[str, str]:
    """Build only the query parameters observed in the authorized UI."""

    params = dict(spec.fixed_params)
    if spec.date_mode == "range":
        params.update({"startDate": start_date, "endDate": end_date})
    elif spec.date_mode == "workdate":
        if not workdate:
            raise ValueError(f"dataset {spec.label} requires workdate")
        params["workdate"] = workdate
    return params


def iter_iso_days(start_date: str, end_date: str) -> Iterable[str]:
    """Yield every ISO business day in an inclusive date range."""

    current = date.fromisoformat(start_date)
    end = date.fromisoformat(end_date)
    while current <= end:
        yield current.isoformat()
        current += timedelta(days=1)


def build_query_windows(
    spec: DatasetSpec,
    start_date: str,
    end_date: str,
    workdate: str | None,
) -> list[dict[str, str]]:
    """Build one range query or inclusive per-day workdate queries."""

    if spec.date_mode == "workdate":
        days = [workdate] if workdate else list(iter_iso_days(start_date, end_date))
        return [build_query_params(spec, start_date, end_date, day) for day in days]
    return [build_query_params(spec, start_date, end_date, workdate)]


def fetch_dataset(
    session: requests.Session,
    base_url: str,
    spec: DatasetSpec,
    query_params: dict[str, str],
    page_size: int,
    max_pages: int,
    timeout: int,
) -> Iterable[dict[str, Any]]:
    """Yield rows from one allowlisted read endpoint."""

    endpoint = urljoin(base_url, spec.path)
    offset = 0
    for _page_no in range(max_pages):
        params: dict[str, Any] = dict(query_params)
        if spec.paged:
            params.update({"_size": page_size, "_index": offset})
        response = session.post(endpoint, data=params, timeout=timeout)
        response.raise_for_status()
        rows, total = normalize_payload(response.json())
        yield from rows
        if not spec.paged or not rows or offset + len(rows) >= total:
            return
        offset += len(rows)
    raise RuntimeError(
        f"dataset {spec.label} exceeded --max-pages={max_pages}; "
        "narrow the date range before retrying"
    )


def query_dataset(
    session: requests.Session,
    base_url: str,
    key: str,
    start_date: str,
    end_date: str,
    workdate: str | None = None,
    page_size: int = 50,
    max_pages: int = 1000,
    timeout: int = DEFAULT_TIMEOUT_SECONDS,
) -> Iterable[dict[str, Any]]:
    """Query any allowlisted dataset over its supported time model."""

    if key not in DATASETS:
        raise KeyError(f"unknown IMES dataset: {key}")
    spec = DATASETS[key]
    for params in build_query_windows(spec, start_date, end_date, workdate):
        yield from fetch_dataset(
            session,
            base_url,
            spec,
            params,
            page_size,
            max_pages,
            timeout,
        )


def export_one(
    session: requests.Session,
    base_url: str,
    key: str,
    output_dir: Path,
    start_date: str,
    end_date: str,
    workdate: str | None,
    page_size: int,
    max_pages: int,
    timeout: int,
) -> dict[str, Any]:
    """Export one dataset as UTF-8 JSON Lines and return its manifest row."""

    spec = DATASETS[key]
    query_windows = build_query_windows(spec, start_date, end_date, workdate)
    target = output_dir / f"{key}.jsonl"
    row_count = 0
    field_names: set[str] = set()
    with target.open("w", encoding="utf-8", newline="\n") as handle:
        for row in query_dataset(
            session,
            base_url,
            key,
            start_date,
            end_date,
            workdate,
            page_size,
            max_pages,
            timeout,
        ):
            field_names.update(row)
            handle.write(json.dumps(row, ensure_ascii=False, default=str) + "\n")
            row_count += 1
    return {
        "dataset": key,
        "label": spec.label,
        "endpoint": spec.path,
        "date_mode": spec.date_mode,
        "time_field": spec.time_field,
        "queries": query_windows,
        "rows": row_count,
        "fields": sorted(field_names),
        "file": target.name,
    }


def build_parser() -> argparse.ArgumentParser:
    """Build the command-line parser."""

    today = date.today()
    parser = argparse.ArgumentParser(
        description="只读导出已授权 IMES Web 查询接口，输出 JSON Lines。"
    )
    parser.add_argument(
        "--list-datasets",
        action="store_true",
        help="列出允许读取的数据集，不登录、不访问业务接口。",
    )
    parser.add_argument(
        "--dataset",
        action="append",
        choices=sorted(DATASETS),
        help="要导出的数据集；可重复。未指定时拒绝运行。",
    )
    parser.add_argument(
        "--all-datasets",
        action="store_true",
        help="导出全部 12 个白名单数据集。",
    )
    parser.add_argument(
        "--start-date",
        type=parse_iso_date,
        default=(today - timedelta(days=1)).isoformat(),
        help="范围查询开始日，默认昨天。",
    )
    parser.add_argument(
        "--end-date",
        type=parse_iso_date,
        default=today.isoformat(),
        help="范围查询结束日，默认今天。",
    )
    parser.add_argument(
        "--workdate",
        type=parse_iso_date,
        default=None,
        help="只查询一个批次投料业务日；不指定时按开始日至结束日逐日查询。",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("exports") / f"imes_web_{datetime.now():%Y%m%d_%H%M%S}",
        help="导出目录；默认 exports/imes_web_<时间戳>。",
    )
    parser.add_argument(
        "--page-size",
        type=int,
        default=50,
        choices=range(1, 51),
        metavar="1..50",
        help="每页行数，最大 50，默认 50。",
    )
    parser.add_argument(
        "--max-pages",
        type=int,
        default=1000,
        help="单数据集最大页数，默认 1000。",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=DEFAULT_TIMEOUT_SECONDS,
        help="单次 HTTP 请求超时秒数，默认 20。",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    """CLI entry point for OPS-IMES-VASTBASE-20260715."""

    parser = build_parser()
    args = parser.parse_args(argv)
    if args.list_datasets:
        for key, spec in DATASETS.items():
            print(
                f"{key}\t{spec.label}\t{spec.date_mode}\t"
                f"{spec.time_field or '-'}\t{spec.path}"
            )
        return 0
    if not args.dataset and not args.all_datasets:
        parser.error("至少指定一个 --dataset/--all-datasets，或使用 --list-datasets")
    if args.start_date > args.end_date:
        parser.error("--start-date 不能晚于 --end-date")
    if args.max_pages < 1:
        parser.error("--max-pages 必须大于 0")
    if args.timeout < 1:
        parser.error("--timeout 必须大于 0")

    username = os.environ.get("IMES_WEB_USER")
    password = os.environ.get("IMES_WEB_PASSWORD")
    captcha = os.environ.get("IMES_WEB_CAPTCHA")
    missing = [
        name
        for name, value in (
            ("IMES_WEB_USER", username),
            ("IMES_WEB_PASSWORD", password),
            ("IMES_WEB_CAPTCHA", captcha),
        )
        if not value
    ]
    if missing:
        parser.error("缺少环境变量：" + ", ".join(missing))

    base_url = os.environ.get("IMES_WEB_URL", DEFAULT_BASE_URL).rstrip("/") + "/"
    output_dir: Path = args.output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    session = requests.Session()
    session.headers.update({"User-Agent": "JNBF-IMES-Readonly-Exporter/1.0"})

    try:
        login(session, base_url, username, password, captcha, args.timeout)
        selected_datasets = (
            list(DATASETS)
            if args.all_datasets
            else list(dict.fromkeys(args.dataset or []))
        )
        exported = [
            export_one(
                session,
                base_url,
                key,
                output_dir,
                args.start_date,
                args.end_date,
                args.workdate,
                args.page_size,
                args.max_pages,
                args.timeout,
            )
            for key in selected_datasets
        ]
    finally:
        session.close()

    manifest = {
        "exported_at": datetime.now().astimezone().isoformat(),
        "source": base_url,
        "read_only": True,
        "datasets": exported,
    }
    manifest_path = output_dir / "manifest.json"
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(
        json.dumps(
            {
                "ok": True,
                "output_dir": str(output_dir),
                "manifest": str(manifest_path),
                "rows": sum(item["rows"] for item in exported),
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (requests.RequestException, RuntimeError, ValueError) as exc:
        print(f"IMES query error: {exc}", file=sys.stderr)
        raise SystemExit(2)
