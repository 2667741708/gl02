from __future__ import annotations

import importlib.util
from pathlib import Path


MODULE_PATH = Path(__file__).resolve().parents[1] / "tools" / "patch_22012_nginx_imes_web.py"
SPEC = importlib.util.spec_from_file_location("patch_22012_nginx_imes_web", MODULE_PATH)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
SPEC.loader.exec_module(MODULE)


BASE = """http {
    server {
        listen 18080;
        server_name 0.0.0.0;

        location / {
            root   html;
            index  g13.html;
        }
    }
    server {
        listen 18082;
        location / { root F:/blast_furnace_frontend; }
    }
}
"""


def test_patch_adds_root_redirect_and_imes_proxy_without_removing_g13() -> None:
    patched, changed = MODULE.patch_nginx_config(BASE)

    assert changed is True
    assert "return 302 /imes.web/;" in patched
    assert "location ^~ /imes.web/" in patched
    assert "proxy_pass http://10.10.181.209:8080;" in patched
    assert "index  g13.html;" in patched
    assert "listen 18082;" in patched


def test_patch_is_idempotent() -> None:
    first, first_changed = MODULE.patch_nginx_config(BASE)
    second, second_changed = MODULE.patch_nginx_config(first)

    assert first_changed is True
    assert second_changed is False
    assert second == first
    assert second.count(MODULE.MARKER) == 1


def test_patch_rejects_ambiguous_18080_servers() -> None:
    duplicate = BASE.replace("listen 18082;", "listen 18080;")

    try:
        MODULE.patch_nginx_config(duplicate)
    except ValueError as exc:
        assert "只能包含一个" in str(exc)
    else:
        raise AssertionError("expected ValueError")
