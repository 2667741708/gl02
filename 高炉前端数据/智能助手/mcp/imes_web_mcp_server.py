"""Read-only MCP adapter for the allowlisted IMES Web query endpoints.

The Web application and Vastbase are separate data paths. This adapter uses
the existing audited HTTP dataset client and never constructs arbitrary URLs
or write requests. A captcha or an already-authorized session cookie must be
provided through the current process environment; credentials are never part
of an MCP response.
"""

from __future__ import annotations

import os
import sys
from datetime import date
from pathlib import Path
from typing import Any

import requests
from mcp.server.fastmcp import FastMCP


ROOT = Path(__file__).resolve().parents[3]
TOOLS_DIR = ROOT / "tools"
if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))

from export_imes_web_readonly import (  # noqa: E402
    DATASETS,
    DEFAULT_BASE_URL,
    DEFAULT_TIMEOUT_SECONDS,
    login,
    query_dataset,
)


MCP_NAME = os.getenv("IMES_WEB_MCP_NAME", "imes-web-readonly-mcp")
mcp = FastMCP(MCP_NAME, json_response=True)
LOCAL_ENV_PATH = ROOT / "PT" / "imes_web.local.env"
ALLOWED_ENV_KEYS = (
    "IMES_WEB_URL",
    "IMES_WEB_USER",
    "IMES_WEB_PASSWORD",
    "IMES_WEB_CAPTCHA",
    "IMES_WEB_SESSION_COOKIE",
)


def _local_env() -> dict[str, str]:
    """Read only the ignored local IMES Web keys when process env is absent."""

    values: dict[str, str] = {}
    if not LOCAL_ENV_PATH.is_file():
        return values
    for line in LOCAL_ENV_PATH.read_text(encoding="utf-8").splitlines():
        text = line.strip()
        if not text or text.startswith("#") or "=" not in text:
            continue
        key, value = text.split("=", 1)
        if key.strip() in ALLOWED_ENV_KEYS:
            values[key.strip()] = value
    return values


def _settings() -> dict[str, str]:
    local = _local_env()
    return {key: os.getenv(key) or local.get(key, "") for key in ALLOWED_ENV_KEYS}


def _base_url(settings: dict[str, str]) -> str:
    return (settings.get("IMES_WEB_URL") or DEFAULT_BASE_URL).rstrip("/") + "/"


def _error(code: str, message: str) -> dict[str, Any]:
    return {"ok": False, "error": code, "message": message, "read_policy": "readonly"}


def _validated_date(value: str, name: str) -> str:
    try:
        return date.fromisoformat(str(value)).isoformat()
    except ValueError as exc:
        raise ValueError(f"{name} must be YYYY-MM-DD") from exc


def _authorized_session(
    settings: dict[str, str], timeout: int
) -> tuple[requests.Session | None, dict[str, Any] | None]:
    session = requests.Session()
    cookie = settings.get("IMES_WEB_SESSION_COOKIE")
    if cookie:
        session.headers.update({"Cookie": cookie})
        return session, None
    username = settings.get("IMES_WEB_USER")
    password = settings.get("IMES_WEB_PASSWORD")
    captcha = settings.get("IMES_WEB_CAPTCHA")
    if not username or not password:
        return None, _error(
            "IMES_WEB_CREDENTIALS_REQUIRED",
            "请在受控进程环境或 PT/imes_web.local.env 提供 IMES Web 账号。",
        )
    if not captcha:
        return None, _error(
            "IMES_WEB_CAPTCHA_REQUIRED",
            "IMES Web 登录需要验证码；请把本次验证码仅注入 IMES_WEB_CAPTCHA 后重试。",
        )
    try:
        login(session, _base_url(settings), username, password, captcha, timeout)
    except (requests.RequestException, RuntimeError) as exc:
        return None, _error("IMES_WEB_LOGIN_FAILED", f"IMES Web 登录失败：{exc}")
    return session, None


@mcp.tool()
def get_imes_web_status() -> dict[str, Any]:
    """Check the IMES Web HTTP endpoint without logging in or returning secrets."""

    settings = _settings()
    try:
        response = requests.get(_base_url(settings), timeout=DEFAULT_TIMEOUT_SECONDS)
        return {
            "ok": response.status_code < 500,
            "read_policy": "readonly",
            "http_status": response.status_code,
            "base_url": _base_url(settings),
            "login_required": True,
        }
    except requests.RequestException as exc:
        return _error("IMES_WEB_UNREACHABLE", f"IMES Web 不可达：{exc}")


@mcp.tool()
def list_imes_web_datasets() -> dict[str, Any]:
    """List the audited IMES Web read-only datasets and endpoint contracts."""

    return {
        "ok": True,
        "read_policy": "readonly",
        "source": "IMES Web HTTP allowlist",
        "datasets": [
            {
                "dataset": key,
                "label": spec.label,
                "date_mode": spec.date_mode,
                "paged": spec.paged,
                "time_field": spec.time_field,
            }
            for key, spec in DATASETS.items()
        ],
    }


@mcp.tool()
def query_imes_web_dataset(
    dataset: str,
    start_date: str,
    end_date: str,
    workdate: str | None = None,
    page_size: int = 50,
    max_pages: int = 20,
    timeout: int = DEFAULT_TIMEOUT_SECONDS,
) -> dict[str, Any]:
    """Query one allowlisted IMES Web dataset through its authorized HTTP endpoint."""

    if dataset not in DATASETS:
        return _error("UNKNOWN_IMES_WEB_DATASET", f"未知的IMES Web数据集：{dataset}")
    start = _validated_date(start_date, "start_date")
    end = _validated_date(end_date, "end_date")
    if start > end:
        return _error("INVALID_DATE_RANGE", "start_date 不能晚于 end_date")
    page_size = min(max(int(page_size), 1), 50)
    max_pages = min(max(int(max_pages), 1), 100)
    timeout = min(max(int(timeout), 1), 60)
    settings = _settings()
    session, error = _authorized_session(settings, timeout)
    if error:
        return error
    assert session is not None
    try:
        rows = list(
            query_dataset(
                session,
                _base_url(settings),
                dataset,
                start,
                end,
                workdate=workdate,
                page_size=page_size,
                max_pages=max_pages,
                timeout=timeout,
            )
        )
    except (requests.RequestException, RuntimeError, ValueError, KeyError) as exc:
        return _error("IMES_WEB_QUERY_FAILED", f"IMES Web查询失败：{exc}")
    finally:
        session.close()
    return {
        "ok": True,
        "read_policy": "readonly",
        "source": "IMES Web HTTP allowlist",
        "dataset": dataset,
        "start_date": start,
        "end_date": end,
        "row_count": len(rows),
        "rows": rows[:500],
        "truncated": len(rows) > 500,
        "time_field": DATASETS[dataset].time_field,
    }


if __name__ == "__main__":
    mcp.run(transport=os.getenv("MCP_TRANSPORT", "stdio"))
