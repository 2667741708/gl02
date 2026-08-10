from __future__ import annotations

import importlib.util
from pathlib import Path


MODULE_PATH = Path(__file__).resolve().parents[1] / "tools" / "patch_22012_nginx_imes_report.py"
SPEC = importlib.util.spec_from_file_location("patch_22012_nginx_imes_report", MODULE_PATH)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
SPEC.loader.exec_module(MODULE)


BASE = """http {
    server {
        listen 18080;
        location / { root html; }
    }
    server {
        listen 18082;
        location / { root F:/blast_furnace_frontend; }
    }
}
"""


def test_patch_adds_dedicated_report_proxy_and_preserves_existing_servers() -> None:
    patched, changed = MODULE.patch_nginx_config(BASE)

    assert changed is True
    assert "listen 18084;" in patched
    assert "proxy_pass http://10.10.181.205:8080;" in patched
    assert "sub_filter_once off;" in patched
    assert "http://10.30.220.12:18084" in patched
    assert "listen 18080;" in patched
    assert "listen 18082;" in patched


def test_patch_is_idempotent() -> None:
    first, first_changed = MODULE.patch_nginx_config(BASE)
    second, second_changed = MODULE.patch_nginx_config(first)

    assert first_changed is True
    assert second_changed is False
    assert second == first
    assert second.count(MODULE.MARKER) == 1


def test_patch_rejects_existing_18081_listener() -> None:
    duplicate = BASE.replace("listen 18082;", "listen 18084;")

    try:
        MODULE.patch_nginx_config(duplicate)
    except ValueError as exc:
        assert "18084" in str(exc)
    else:
        raise AssertionError("expected ValueError")
