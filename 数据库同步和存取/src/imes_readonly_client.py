from __future__ import annotations

import argparse
import csv
import json
import os
import re
import sqlite3
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime
from html.parser import HTMLParser
from pathlib import Path
from typing import Any
from urllib.parse import parse_qsl, urlencode, urljoin, urlparse, urlunparse

import requests


MODULE_DIR = Path(__file__).resolve().parent
ROOT_DIR = MODULE_DIR.parents[0]
WORKSPACE_ROOT = ROOT_DIR.parents[0]
DEFAULT_BASE_URL = "http://10.10.181.209:8080/imes.web/"
DEFAULT_ENV_FILE = WORKSPACE_ROOT / ".env.imes.local"
DEFAULT_EXPORT_DIR = ROOT_DIR / "imes_exports"
DEFAULT_SQLITE = ROOT_DIR / "data" / "imes_readonly.db"

FORBIDDEN_PATH_RE = re.compile(
    r"(^|/|_)(add|audit|approve|cancel|change|clear|close|create|del|delete|edit|import|insert|"
    r"modify|remove|save|submit|update|upload)(\.do|/|_|$)",
    re.IGNORECASE,
)
SAFE_POST_PATH_RE = re.compile(
    r"(^|/)(login|.*(?:list|page|query|search|find|get).*)\.do$",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class DatasetDef:
    key: str
    label: str
    endpoint: str
    table_name: str
    default_params: dict[str, str] = field(default_factory=dict)
    columns: tuple[tuple[str, str], ...] = ()
    notes: str = ""


@dataclass(frozen=True)
class PageDef:
    key: str
    label: str
    path: str
    notes: str = ""


KNOWN_PAGES: dict[str, PageDef] = {
    "bf2_bin": PageDef("bf2_bin", "2#高炉料仓维护管理", "mes/ipes/pesBin/list.do?prodCenterCode=2D012"),
    "bf2_bin_material": PageDef("bf2_bin_material", "2#高炉料仓变料管理", "mes/ipes/pesBinMaterial/list.do?prodCenterCode=2D012"),
    "bf2_plan_month": PageDef("bf2_plan_month", "2#高炉生产计划管理", "mes/cpes/productionPlanMonth/list.do?sinteringMachineCode=2D012"),
    "bf2_dosing_scheme": PageDef("bf2_dosing_scheme", "2#高炉配料方案", "mes/ipes/dosingScheme/listB.do?prodCenterCode=2D012"),
    "bf2_input": PageDef("bf2_input", "2#高炉原料投入管理", "mes/ipes/input/list.do?prodCenterCode=2D012"),
    "bf2_batch_input_detail": PageDef("bf2_batch_input_detail", "2#高炉批次投料详情", "mes/ipes/input/list2.do?prodCenterCode=2D012"),
    "bf2_output": PageDef("bf2_output", "2#高炉生产实绩", "mes/ipes/outputM/list.do?prodCenterCode=2D012"),
    "bf2_heat_lab": PageDef("bf2_heat_lab", "2#高炉次化验结果", "mes/ipes/outputM/listavg2.do?prodCenterCode=2D012"),
    "bf2_slag_lab": PageDef("bf2_slag_lab", "炉渣检验结果", "mes/qpes/productManage/listlz2.do?prodCenterCode=JLZ2"),
    "bf2_heat_lab_all": PageDef("bf2_heat_lab_all", "2#炉次化验结果全", "mes/ipes/outputM/listavg2New.do?prodCenterCode=2D012"),
}

MINING_COLUMNS: tuple[tuple[str, str], ...] = (
    ("workdate2", "批次下料开始时间"),
    ("value_01", "1#料仓"),
    ("value_02", "2#料仓"),
    ("value_03", "3#料仓"),
    ("value_04", "4#料仓"),
    ("value_06", "6#料仓"),
    ("value_08", "8#料仓"),
    ("value_10", "10#料仓"),
    ("value_12", "12#料仓"),
    ("value_14", "14#料仓"),
    ("value_16", "16#料仓"),
    ("value_17", "17#料仓"),
    ("value_18", "18#料仓"),
    ("value_19", "19#料仓"),
    ("value_20", "20#料仓"),
    ("value_21", "21#料仓"),
    ("value_22", "22#料仓"),
    ("value_23", "23#料仓"),
    ("value_24", "24#料仓"),
    ("mining_batch_sum", "矿批总量"),
)

COKE_COLUMNS: tuple[tuple[str, str], ...] = (
    ("workdate2", "批次下料开始时间"),
    ("value_05", "5#料仓"),
    ("value_07", "7#料仓"),
    ("value_09", "9#料仓"),
    ("value_11", "11#料仓"),
    ("value_13", "13#料仓"),
    ("value_15", "15#料仓"),
    ("coke_charge_sum", "焦批总量"),
)

BATCH_ALL_COLUMNS: tuple[tuple[str, str], ...] = (
    ("workdate2", "批次下料开始时间"),
    ("charge", "批别"),
    ("lot", "批次"),
    ("value_01", "1#料仓"),
    ("value_02", "2#料仓"),
    ("value_03", "3#料仓"),
    ("value_04", "4#料仓"),
    ("value_05", "5#料仓"),
    ("value_06", "6#料仓"),
    ("value_07", "7#料仓"),
    ("value_08", "8#料仓"),
    ("value_09", "9#料仓"),
    ("value_10", "10#料仓"),
    ("value_11", "11#料仓"),
    ("value_12", "12#料仓"),
    ("value_13", "13#料仓"),
    ("value_14", "14#料仓"),
    ("value_15", "15#料仓"),
    ("value_16", "16#料仓"),
    ("value_17", "17#料仓"),
    ("value_18", "18#料仓"),
    ("value_19", "19#料仓"),
    ("value_20", "20#料仓"),
    ("value_21", "21#料仓"),
    ("value_22", "22#料仓"),
    ("value_23", "23#料仓"),
    ("value_24", "24#料仓"),
    ("value_sum", "本批总量"),
    ("mining_batch_sum", "矿批总量"),
    ("coke_charge_sum", "焦批总量"),
)

KNOWN_DATASETS: dict[str, DatasetDef] = {
    "bf2_operation_log_report": DatasetDef(
        key="bf2_operation_log_report",
        label="2#高炉冀南新区高炉作业日志（报表查询结果）",
        endpoint="demo/reportServlet?action=8;demo/reportJsp/queryInput.jsp",
        table_name="imes_bf2_operation_log_report",
        default_params={"prodcentercode": "2D012"},
        columns=(
            ("report_row_number", "报表行号"),
            ("report_id", "报表ID"),
            ("report_time_raw", "报表时间/ID原值"),
            ("report_batch_count", "批数（D列）"),
            ("report_coal_ratio", "煤比（报表公式重算）"),
            ("report_fuel_ratio", "燃料比（报表公式重算）"),
            ("material_rate", "料速（语义待确认）"),
            ("cells", "全部报表单元格（JSON）"),
        ),
        notes="Raqsoft 报表两段 POST 结果；D列为批数，燃料比按页面公式重算，料速不从批数强行推断。",
    ),
    "bf2_batch_all_rows": DatasetDef(
        key="bf2_batch_all_rows",
        label="2#高炉批次投料详情-矿批焦批合并明细",
        endpoint="mes/ipes/input/listPageData2.do",
        table_name="imes_bf2_batch_all_rows",
        default_params={"prodCenterCode": "2D012"},
        columns=BATCH_ALL_COLUMNS,
        notes="来自页面 2#高炉批次投料详情的合并明细表，矿批和焦批在同一结果集中。",
    ),
    "bf2_batch_mining": DatasetDef(
        key="bf2_batch_mining",
        label="2#高炉批次投料详情-矿批",
        endpoint="mes/ipes/input/listPageData3.do",
        table_name="imes_bf2_batch_mining",
        default_params={"prodCenterCode": "2D012"},
        columns=MINING_COLUMNS,
        notes="来自页面 2#高炉批次投料详情的矿批表格。",
    ),
    "bf2_batch_coke": DatasetDef(
        key="bf2_batch_coke",
        label="2#高炉批次投料详情-焦批",
        endpoint="mes/ipes/input/listPageData4.do",
        table_name="imes_bf2_batch_coke",
        default_params={"prodCenterCode": "2D012"},
        columns=COKE_COLUMNS,
        notes="来自页面 2#高炉批次投料详情的焦批表格。",
    ),
}

DATASET_GROUPS: dict[str, tuple[str, ...]] = {
    "bf2_reports": ("bf2_operation_log_report",),
    "bf2_batch_input_detail": ("bf2_batch_all_rows", "bf2_batch_mining", "bf2_batch_coke"),
    "all": tuple(KNOWN_DATASETS.keys()),
}

DYNAMIC_PAGE_GROUPS = {"imes_10_pages", "bf2_10_pages", "all_10_pages"}


class LinkParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.links: list[dict[str, str]] = []
        self._current_href: str | None = None
        self._current_text: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() != "a":
            return
        data = {key: value or "" for key, value in attrs}
        href = data.get("href") or data.get("data-url") or data.get("url")
        if href:
            self._current_href = href
            self._current_text = []

    def handle_data(self, data: str) -> None:
        if self._current_href:
            text = data.strip()
            if text:
                self._current_text.append(text)

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() == "a" and self._current_href:
            self.links.append({"href": self._current_href, "text": "".join(self._current_text).strip()})
            self._current_href = None
            self._current_text = []


def now_text() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def today_text() -> str:
    return datetime.now().strftime("%Y-%m-%d")


def read_text_best_effort(path: Path) -> str:
    for encoding in ("utf-8", "gbk", "utf-8-sig"):
        try:
            return path.read_text(encoding=encoding)
        except UnicodeDecodeError:
            continue
    return path.read_text(encoding="utf-8", errors="replace")


def load_env_file(path: Path) -> None:
    if not path.exists():
        return
    for raw_line in read_text_best_effort(path).splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


def json_dumps(data: Any) -> str:
    return json.dumps(data, ensure_ascii=False, indent=2)


def parse_kv_pairs(items: list[str]) -> dict[str, str]:
    values: dict[str, str] = {}
    for item in items:
        if "=" not in item:
            raise argparse.ArgumentTypeError(f"参数必须是 KEY=VALUE 格式: {item}")
        key, value = item.split("=", 1)
        key = key.strip()
        if not key:
            raise argparse.ArgumentTypeError(f"参数名不能为空: {item}")
        values[key] = value
    return values


def _html_attr(tag: str, attr: str) -> str:
    match = re.search(r"\b" + re.escape(attr) + r"=[\"']([^\"']*)", tag, flags=re.IGNORECASE)
    return match.group(1) if match else ""


def extract_page_params(html: str, path: str) -> dict[str, str]:
    params = dict(parse_qsl(urlparse(path).query))
    for match in re.finditer(r"<input\b[^>]*>", html, flags=re.IGNORECASE):
        tag = match.group(0)
        input_type = _html_attr(tag, "type").lower()
        if input_type in {"button", "submit", "reset", "file"}:
            continue
        name = _html_attr(tag, "name") or _html_attr(tag, "id")
        if name:
            params.setdefault(name, _html_attr(tag, "value").strip())
    for match in re.finditer(r"<select\b[^>]*>", html, flags=re.IGNORECASE):
        tag = match.group(0)
        name = _html_attr(tag, "name") or _html_attr(tag, "id")
        if name:
            params.setdefault(name, "")
    return params


def extract_page_columns(html: str) -> list[dict[str, str]]:
    columns: list[dict[str, str]] = []
    for match in re.finditer(r"field\s*:\s*['\"]([^'\"]+)['\"][\s\S]{0,260}?title\s*:\s*['\"]([^'\"]+)['\"]", html):
        title = re.sub(r"<[^>]+>", "", match.group(2)).strip()
        item = {"field": match.group(1), "title": title}
        if item not in columns:
            columns.append(item)
    return columns


def snake_name(value: str) -> str:
    text = re.sub(r"\.do(?:\?.*)?$", "", value.strip(), flags=re.IGNORECASE)
    text = text.strip("/").split("/")[-1]
    text = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", text)
    text = re.sub(r"[^A-Za-z0-9]+", "_", text).strip("_").lower()
    return text or "data"


def normalize_endpoint(endpoint: str) -> str:
    value = endpoint.replace("${ctx}", "").strip()
    if value.startswith("/imes.web/"):
        return value
    if value.startswith("/"):
        return "/imes.web" + value if not value.startswith("/imes.web/") else value
    return "/imes.web/" + value.lstrip("/")


def sanitize_sql_identifier(value: str) -> str:
    if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", value):
        raise ValueError(f"Unsafe SQL identifier: {value}")
    return value


def quote_ident(value: str) -> str:
    return f'"{sanitize_sql_identifier(value)}"'


def is_readonly_sql(sql: str) -> bool:
    compact = re.sub(r"\s+", " ", sql.strip().rstrip(";")).lower()
    if not compact:
        return False
    return compact.startswith("select ") or compact.startswith("with ")


class IMESReadOnlyClient:
    def __init__(self, base_url: str, username: str, password: str, timeout: float = 30.0) -> None:
        if not username or not password:
            raise ValueError("IMES_USERNAME/IMES_PASSWORD 未设置，无法登录。")
        self.base_url = base_url.rstrip("/") + "/"
        self.username = username
        self.password = password
        self.timeout = timeout
        self.session = requests.Session()
        self.session.headers.update(
            {
                "User-Agent": "bf-imes-readonly-client/1.0",
                "Accept": "application/json,text/plain,text/html,*/*",
            }
        )

    def build_url(self, path: str) -> str:
        parsed = urlparse(path)
        if parsed.scheme or parsed.netloc:
            base = urlparse(self.base_url)
            if parsed.scheme != base.scheme or parsed.netloc != base.netloc:
                raise ValueError(f"外部地址不允许访问: {path}")
            if not parsed.path.startswith(base.path.rstrip("/") + "/"):
                raise ValueError(f"地址不在 IMES base path 下: {path}")
            return path
        if path.startswith("/"):
            base = urlparse(self.base_url)
            base_path = base.path.rstrip("/")
            if parsed.path.startswith(base_path + "/"):
                return urlunparse((base.scheme, base.netloc, parsed.path, parsed.params, parsed.query, parsed.fragment))
        return urljoin(self.base_url, path.lstrip("/"))

    def _path_for_check(self, path: str) -> str:
        parsed = urlparse(self.build_url(path))
        base = urlparse(self.base_url)
        rel = parsed.path
        if rel.startswith(base.path):
            rel = rel[len(base.path) :].lstrip("/")
        return rel

    def assert_readonly(self, method: str, path: str) -> None:
        method = method.upper()
        if method not in {"GET", "POST"}:
            raise PermissionError(f"只允许 GET/POST 读取，拒绝 {method}")
        rel_path = self._path_for_check(path)
        clean_path = urlparse(rel_path).path
        if FORBIDDEN_PATH_RE.search(clean_path):
            raise PermissionError(f"接口名疑似修改/删除类接口，已拒绝: {rel_path}")
        if method == "POST" and not SAFE_POST_PATH_RE.search(clean_path):
            raise PermissionError(f"POST 只允许登录、查询、列表类接口，已拒绝: {rel_path}")

    def get(self, path: str, params: dict[str, str] | None = None) -> requests.Response:
        self.assert_readonly("GET", path)
        response = self.session.get(self.build_url(path), params=params, timeout=self.timeout)
        response.raise_for_status()
        return response

    def post(self, path: str, data: dict[str, Any] | None = None) -> requests.Response:
        self.assert_readonly("POST", path)
        response = self.session.post(self.build_url(path), data=data or {}, timeout=self.timeout)
        response.raise_for_status()
        return response

    def login(self) -> None:
        response = self.post(
            "login.do",
            {
                "username": self.username,
                "password": self.password,
                # 这个 IMES 版本的验证码在前端生成，服务端当前未校验固定值。
                "captchaInput": "0000",
            },
        )
        if response.text.strip() != "success":
            raise RuntimeError(f"IMES 登录失败，状态={response.status_code}，响应={response.text[:80]!r}")

    def login_check(self) -> dict[str, Any]:
        self.login()
        response = self.get("mes/desktop.do")
        ok = "冀南iMES管理系统" in response.text or "炼铁生产执行系统" in response.text
        return {
            "ok": ok,
            "base_url": self.base_url,
            "desktop_status": response.status_code,
            "cookies": sorted(self.session.cookies.keys()),
        }

    def desktop_menus(self) -> list[dict[str, str]]:
        self.login()
        response = self.get("mes/desktop.do")
        parser = LinkParser()
        parser.feed(response.text)
        rows: list[dict[str, str]] = []
        seen: set[str] = set()
        for item in parser.links:
            href = item["href"].strip()
            if not href or href.startswith("javascript:") or href in seen:
                continue
            seen.add(href)
            rows.append({"title": item["text"], "href": href})
        return rows

    def discover_page(self, path: str) -> dict[str, Any]:
        self.login()
        response = self.get(path)
        html = response.text
        endpoints = sorted(set(re.findall(r"['\"]([^'\"]*(?:list|page|query|get|find|search)[^'\"]*?\.do)['\"]", html, flags=re.IGNORECASE)))
        table_refs = []
        for match in re.finditer(r"new\s+Table\s*\(\s*['\"]([^'\"]+)['\"]\s*,\s*['\"]([^'\"]+)['\"]", html):
            table_refs.append({"table_id": match.group(1), "endpoint": match.group(2)})
        columns = []
        for match in re.finditer(r"field\s*:\s*['\"]([^'\"]+)['\"][\s\S]{0,180}?title\s*:\s*['\"]([^'\"]+)['\"]", html):
            columns.append({"field": match.group(1), "title": match.group(2)})
        return {
            "ok": True,
            "path": path,
            "status": response.status_code,
            "table_refs": table_refs,
            "endpoints": endpoints,
            "columns": columns,
        }

    def discover_page_datasets(self, page: PageDef) -> list[DatasetDef]:
        self.login()
        response = self.get(page.path)
        html = response.text
        params = extract_page_params(html, page.path)
        columns = extract_page_columns(html)
        ref_by_endpoint: dict[str, str] = {}
        for match in re.finditer(r"new\s+Table\s*\(\s*['\"]([^'\"]+)['\"]\s*,\s*['\"]([^'\"]+)['\"]", html):
            ref_by_endpoint[normalize_endpoint(match.group(2))] = match.group(1)

        endpoints: set[str] = set(ref_by_endpoint)
        for match in re.finditer(r"['\"]([^'\"]*Data[^'\"]*\.do(?:\?[^'\"]*)?)['\"]", html, flags=re.IGNORECASE):
            endpoints.add(normalize_endpoint(match.group(1)))

        datasets: list[DatasetDef] = []
        for endpoint in sorted(endpoints):
            rel_endpoint = endpoint.removeprefix("/imes.web/").lstrip("/")
            try:
                self.assert_readonly("POST", endpoint)
            except PermissionError:
                continue
            suffix = snake_name(rel_endpoint)
            table_id = ref_by_endpoint.get(endpoint, "")
            key = f"{page.key}_{suffix}"
            label = f"{page.label}-{table_id or suffix}"
            datasets.append(
                DatasetDef(
                    key=key,
                    label=label,
                    endpoint=rel_endpoint,
                    table_name=f"imes_{key}",
                    default_params=params,
                    columns=tuple((item["field"], item["title"]) for item in columns),
                    notes=f"动态发现自页面 {page.label} ({page.path})，接口 {rel_endpoint}。",
                )
            )
        return datasets

    def discover_known_page_datasets(self) -> list[DatasetDef]:
        datasets: list[DatasetDef] = []
        seen: set[str] = set()
        for page in KNOWN_PAGES.values():
            for dataset in self.discover_page_datasets(page):
                if dataset.key in seen:
                    continue
                seen.add(dataset.key)
                datasets.append(dataset)
        return datasets

    def fetch_bootstrap_table(
        self,
        dataset: DatasetDef,
        params: dict[str, str],
        page_size: int = 100,
        max_rows: int = 0,
        delay_seconds: float = 0.05,
    ) -> dict[str, Any]:
        self.login()
        if page_size <= 0:
            raise ValueError("--page-size 必须大于 0")
        rows: list[dict[str, Any]] = []
        offset = 0
        total: int | None = None
        fetched_at = now_text()
        while True:
            request_params = dict(dataset.default_params)
            request_params.update(params)
            request_params["_size"] = str(page_size)
            request_params["_index"] = str(offset)
            response = self.post(dataset.endpoint, request_params)
            try:
                payload = response.json()
            except json.JSONDecodeError as exc:
                raise RuntimeError(f"接口未返回 JSON: {dataset.endpoint}, 响应片段={response.text[:200]!r}") from exc
            is_list_payload = isinstance(payload, list)
            if isinstance(payload, dict):
                chunk = payload.get("rows", [])
            elif is_list_payload:
                chunk = payload
            else:
                chunk = []
            if not isinstance(chunk, list):
                raise RuntimeError(f"接口 rows 字段不是列表: {dataset.endpoint}")
            if total is None:
                raw_total = payload.get("total") if isinstance(payload, dict) else None
                try:
                    total = int(raw_total) if raw_total is not None else None
                except (TypeError, ValueError):
                    total = None
            for row in chunk:
                if isinstance(row, dict):
                    enriched = dict(row)
                    enriched["_dataset_key"] = dataset.key
                    enriched["_dataset_label"] = dataset.label
                    enriched["_source_endpoint"] = dataset.endpoint
                    enriched["_fetched_at"] = fetched_at
                    rows.append(enriched)
            offset += len(chunk)
            if not chunk:
                break
            if max_rows and len(rows) >= max_rows:
                rows = rows[:max_rows]
                break
            if is_list_payload:
                break
            if total is not None and offset >= total:
                break
            time.sleep(delay_seconds)
        return {
            "ok": True,
            "dataset": dataset.key,
            "label": dataset.label,
            "endpoint": dataset.endpoint,
            "params": params,
            "total": total,
            "rows_count": len(rows),
            "columns": [{"field": field, "title": title} for field, title in dataset.columns],
            "rows": rows,
        }

    def fetch_endpoint(
        self,
        endpoint: str,
        params: dict[str, str],
        table_name: str,
        page_size: int = 100,
        max_rows: int = 0,
        delay_seconds: float = 0.05,
    ) -> dict[str, Any]:
        dataset = DatasetDef(
            key=table_name,
            label=table_name,
            endpoint=endpoint,
            table_name=table_name,
            default_params={},
            columns=(),
            notes="手工指定的只读列表接口。",
        )
        return self.fetch_bootstrap_table(dataset, params, page_size=page_size, max_rows=max_rows, delay_seconds=delay_seconds)


def all_fieldnames(rows: list[dict[str, Any]], preferred: list[str] | None = None) -> list[str]:
    fields: list[str] = []
    seen: set[str] = set()
    for field_name in preferred or []:
        if field_name not in seen:
            fields.append(field_name)
            seen.add(field_name)
    for row in rows:
        for key in row.keys():
            if key not in seen:
                fields.append(key)
                seen.add(key)
    return fields


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json_dumps(payload) + "\n", encoding="utf-8")


def write_csv(path: Path, rows: list[dict[str, Any]], columns: tuple[tuple[str, str], ...] = ()) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    preferred = [field for field, _ in columns]
    fields = all_fieldnames(rows, preferred=preferred)
    with path.open("w", encoding="utf-8-sig", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def write_sqlite(db_path: Path, dataset: DatasetDef, payload: dict[str, Any]) -> None:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    table = quote_ident(dataset.table_name)
    rows: list[dict[str, Any]] = payload.get("rows", [])
    fields = all_fieldnames(rows, preferred=[field for field, _ in dataset.columns])
    conn = sqlite3.connect(db_path)
    try:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS imes_fetch_runs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                created_at TEXT NOT NULL,
                dataset_key TEXT NOT NULL,
                dataset_label TEXT NOT NULL,
                endpoint TEXT NOT NULL,
                params_json TEXT NOT NULL,
                rows_count INTEGER NOT NULL,
                total INTEGER
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS imes_dataset_catalog (
                dataset_key TEXT PRIMARY KEY,
                dataset_label TEXT NOT NULL,
                endpoint TEXT NOT NULL,
                table_name TEXT NOT NULL,
                columns_json TEXT NOT NULL,
                notes TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            INSERT INTO imes_dataset_catalog (
                dataset_key, dataset_label, endpoint, table_name, columns_json, notes, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(dataset_key) DO UPDATE SET
                dataset_label=excluded.dataset_label,
                endpoint=excluded.endpoint,
                table_name=excluded.table_name,
                columns_json=excluded.columns_json,
                notes=excluded.notes,
                updated_at=excluded.updated_at
            """,
            (
                dataset.key,
                dataset.label,
                dataset.endpoint,
                dataset.table_name,
                json.dumps([{"field": field, "title": title} for field, title in dataset.columns], ensure_ascii=False),
                dataset.notes,
                now_text(),
            ),
        )
        conn.execute(
            """
            INSERT INTO imes_fetch_runs (
                created_at, dataset_key, dataset_label, endpoint, params_json, rows_count, total
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                now_text(),
                dataset.key,
                dataset.label,
                dataset.endpoint,
                json.dumps(payload.get("params", {}), ensure_ascii=False),
                int(payload.get("rows_count") or 0),
                payload.get("total"),
            ),
        )
        if fields:
            existing_cols = {
                row[1]
                for row in conn.execute(f"PRAGMA table_info({table})").fetchall()
            }
            if not existing_cols:
                cols_sql = ", ".join(f"{quote_ident(field)} TEXT" for field in fields)
                conn.execute(f"CREATE TABLE IF NOT EXISTS {table} ({cols_sql})")
                existing_cols = set(fields)
            for field_name in fields:
                if field_name not in existing_cols:
                    conn.execute(f"ALTER TABLE {table} ADD COLUMN {quote_ident(field_name)} TEXT")
                    existing_cols.add(field_name)
            insert_cols = [field for field in fields if field in existing_cols]
            placeholders = ", ".join("?" for _ in insert_cols)
            col_sql = ", ".join(quote_ident(field) for field in insert_cols)
            values = [[None if row.get(field) is None else str(row.get(field)) for field in insert_cols] for row in rows]
            if values:
                conn.executemany(f"INSERT INTO {table} ({col_sql}) VALUES ({placeholders})", values)
        conn.commit()
    finally:
        conn.close()


def output_fetch_result(
    payload: dict[str, Any],
    dataset: DatasetDef,
    out_dir: Path,
    formats: set[str],
    sqlite_db: Path,
) -> dict[str, str]:
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    base_name = f"{dataset.key}_{stamp}"
    written: dict[str, str] = {}
    if "json" in formats:
        path = out_dir / f"{base_name}.json"
        write_json(path, payload)
        written["json"] = str(path)
    if "csv" in formats:
        path = out_dir / f"{base_name}.csv"
        write_csv(path, payload.get("rows", []), dataset.columns)
        written["csv"] = str(path)
    if "sqlite" in formats:
        write_sqlite(sqlite_db, dataset, payload)
        written["sqlite"] = str(sqlite_db)
    return written


def resolve_datasets(value: str) -> list[DatasetDef]:
    if value in KNOWN_DATASETS:
        return [KNOWN_DATASETS[value]]
    if value in DATASET_GROUPS:
        return [KNOWN_DATASETS[key] for key in DATASET_GROUPS[value]]
    raise KeyError(f"未知数据集: {value}")


def get_credentials(args: argparse.Namespace) -> tuple[str, str, str]:
    base_url = args.base_url or os.environ.get("IMES_BASE_URL") or DEFAULT_BASE_URL
    username = args.username or os.environ.get("IMES_USERNAME") or ""
    password = args.password or os.environ.get("IMES_PASSWORD") or ""
    return base_url, username, password


def add_common_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--env-file", default=str(DEFAULT_ENV_FILE), help="本机私有 env 文件，默认 .env.imes.local")
    parser.add_argument("--base-url", default="", help="IMES base URL；默认读取 IMES_BASE_URL 或内置地址")
    parser.add_argument("--username", default="", help="IMES 用户名；默认读取 IMES_USERNAME")
    parser.add_argument("--password", default="", help="IMES 密码；默认读取 IMES_PASSWORD，不建议命令行明文传入")
    parser.add_argument("--timeout", type=float, default=30.0)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="IMES 只读采集、保存和本地查询工具。")
    add_common_args(parser)
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("list-datasets", help="列出已确认的只读数据集和页面。")
    sub.add_parser("login-check", help="只读登录检查。")

    menus = sub.add_parser("menus", help="读取登录后的菜单链接。")
    menus.add_argument("--out", default="", help="保存 JSON 到指定文件。")

    discover = sub.add_parser("discover-page", help="读取页面 HTML 并发现表格接口。")
    page_group = discover.add_mutually_exclusive_group(required=True)
    page_group.add_argument("--page-key", choices=sorted(KNOWN_PAGES.keys()))
    page_group.add_argument("--path", help="相对路径，例如 mes/ipes/input/list2.do?prodCenterCode=2D012")
    discover.add_argument("--out", default="", help="保存 JSON 到指定文件。")

    fetch = sub.add_parser("fetch", help="分页读取已确认数据集并保存。")
    fetch.add_argument("--dataset", required=True, help="数据集 key，支持 bf2_batch_input_detail 或 all")
    fetch.add_argument("--date", default=today_text(), help="workdate，默认今天。")
    fetch.add_argument("--lot", default="", help="批次筛选，可为空。")
    fetch.add_argument("--prod-center-code", default="", help="覆盖 prodCenterCode，默认使用数据集定义。")
    fetch.add_argument("--page-size", type=int, default=100)
    fetch.add_argument("--max-rows", type=int, default=0, help="0 表示不限制。")
    fetch.add_argument("--delay-seconds", type=float, default=0.05)
    fetch.add_argument("--formats", default="json,csv,sqlite", help="逗号分隔：json,csv,sqlite")
    fetch.add_argument("--out-dir", default=str(DEFAULT_EXPORT_DIR))
    fetch.add_argument("--sqlite-db", default=str(DEFAULT_SQLITE))

    fetch_endpoint = sub.add_parser("fetch-endpoint", help="读取手工指定的列表/查询类接口。")
    fetch_endpoint.add_argument("--endpoint", required=True)
    fetch_endpoint.add_argument("--table-name", required=True, help="保存 SQLite 时使用的表名，只允许英文数字下划线。")
    fetch_endpoint.add_argument("--param", action="append", default=[], help="接口参数 KEY=VALUE，可重复。")
    fetch_endpoint.add_argument("--page-size", type=int, default=100)
    fetch_endpoint.add_argument("--max-rows", type=int, default=0)
    fetch_endpoint.add_argument("--delay-seconds", type=float, default=0.05)
    fetch_endpoint.add_argument("--formats", default="json,csv,sqlite")
    fetch_endpoint.add_argument("--out-dir", default=str(DEFAULT_EXPORT_DIR))
    fetch_endpoint.add_argument("--sqlite-db", default=str(DEFAULT_SQLITE))

    query = sub.add_parser("sqlite-query", help="只读查询本地 SQLite 保存结果。")
    query.add_argument("--db", default=str(DEFAULT_SQLITE))
    query.add_argument("--sql", required=True, help="仅允许 SELECT 或 WITH 查询。")
    query.add_argument("--format", choices=["json", "csv"], default="json")
    query.add_argument("--out", default="")
    return parser


def command_list_datasets() -> dict[str, Any]:
    return {
        "ok": True,
        "pages": [page.__dict__ for page in KNOWN_PAGES.values()],
        "datasets": [
            {
                "key": dataset.key,
                "label": dataset.label,
                "endpoint": dataset.endpoint,
                "table_name": dataset.table_name,
                "default_params": dataset.default_params,
                "columns": [{"field": field, "title": title} for field, title in dataset.columns],
                "notes": dataset.notes,
            }
            for dataset in KNOWN_DATASETS.values()
        ],
        "groups": DATASET_GROUPS,
        "dynamic_groups": sorted(DYNAMIC_PAGE_GROUPS),
    }


def command_sqlite_query(args: argparse.Namespace) -> dict[str, Any] | None:
    if not is_readonly_sql(args.sql):
        raise PermissionError("sqlite-query 只允许 SELECT 或 WITH 查询。")
    conn = sqlite3.connect(args.db)
    conn.row_factory = sqlite3.Row
    try:
        rows = [dict(row) for row in conn.execute(args.sql).fetchall()]
    finally:
        conn.close()
    if args.format == "csv":
        target = Path(args.out) if args.out else None
        fields = all_fieldnames(rows)
        fh = target.open("w", encoding="utf-8-sig", newline="") if target else sys.stdout
        writer = csv.DictWriter(fh, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
        if target:
            fh.close()
        return None
    return {"ok": True, "rows_count": len(rows), "rows": rows}


def print_or_write(payload: dict[str, Any], out: str = "") -> None:
    text = json_dumps(payload)
    if out:
        write_json(Path(out), payload)
        print(f"已保存: {out}")
    else:
        print(text)


def execute(args: argparse.Namespace) -> int:
    if args.command == "list-datasets":
        print(json_dumps(command_list_datasets()))
        return 0

    if args.command == "sqlite-query":
        payload = command_sqlite_query(args)
        if payload is not None:
            print_or_write(payload, args.out)
        return 0

    base_url, username, password = get_credentials(args)
    client = IMESReadOnlyClient(base_url=base_url, username=username, password=password, timeout=args.timeout)

    if args.command == "login-check":
        print_or_write(client.login_check())
        return 0
    if args.command == "menus":
        print_or_write({"ok": True, "menus": client.desktop_menus()}, args.out)
        return 0
    if args.command == "discover-page":
        path = KNOWN_PAGES[args.page_key].path if args.page_key else args.path
        print_or_write(client.discover_page(path), args.out)
        return 0
    if args.command == "fetch":
        params = {"workdate": args.date, "lot": args.lot}
        if args.prod_center_code:
            params["prodCenterCode"] = args.prod_center_code
        formats = {item.strip().lower() for item in args.formats.split(",") if item.strip()}
        out_dir = Path(args.out_dir)
        sqlite_db = Path(args.sqlite_db)
        outputs = []
        for dataset in resolve_datasets(args.dataset):
            payload = client.fetch_bootstrap_table(
                dataset,
                params=params,
                page_size=args.page_size,
                max_rows=args.max_rows,
                delay_seconds=args.delay_seconds,
            )
            outputs.append(
                {
                    "dataset": dataset.key,
                    "rows_count": payload["rows_count"],
                    "total": payload["total"],
                    "written": output_fetch_result(payload, dataset, out_dir, formats, sqlite_db),
                }
            )
        print(json_dumps({"ok": True, "outputs": outputs}))
        return 0
    if args.command == "fetch-endpoint":
        table_name = sanitize_sql_identifier(args.table_name)
        params = parse_kv_pairs(args.param)
        formats = {item.strip().lower() for item in args.formats.split(",") if item.strip()}
        payload = client.fetch_endpoint(
            args.endpoint,
            params=params,
            table_name=table_name,
            page_size=args.page_size,
            max_rows=args.max_rows,
            delay_seconds=args.delay_seconds,
        )
        dataset = DatasetDef(
            key=table_name,
            label=table_name,
            endpoint=args.endpoint,
            table_name=table_name,
            default_params={},
            columns=(),
            notes="手工指定的只读列表接口。",
        )
        print(
            json_dumps(
                {
                    "ok": True,
                    "dataset": table_name,
                    "rows_count": payload["rows_count"],
                    "total": payload["total"],
                    "written": output_fetch_result(payload, dataset, Path(args.out_dir), formats, Path(args.sqlite_db)),
                }
            )
        )
        return 0
    raise RuntimeError(f"Unknown command: {args.command}")


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    try:
        load_env_file(Path(args.env_file))
        return execute(args)
    except (PermissionError, ValueError, RuntimeError, requests.RequestException, sqlite3.Error) as exc:
        print(json_dumps({"ok": False, "error": str(exc)}), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
