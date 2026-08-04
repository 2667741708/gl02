from __future__ import annotations

import importlib.util
import io
import json
import os
import sys
from pathlib import Path
from unittest import mock

import pytest


ROOT = Path(__file__).resolve().parents[1]
BACKEND_DIR = ROOT / "高炉前端数据" / "智能助手" / "backend"
MODULE_PATH = BACKEND_DIR / "ollama_proxy_server.py"


class _Response:
    def __init__(self, payload: dict) -> None:
        self._body = io.BytesIO(json.dumps(payload).encode("utf-8"))

    def __enter__(self) -> "_Response":
        return self

    def __exit__(self, *_args: object) -> None:
        return None

    def read(self) -> bytes:
        return self._body.read()


def _load_backend():
    sys.path.insert(0, str(BACKEND_DIR))
    spec = importlib.util.spec_from_file_location("ollama_proxy_loaded_policy_test", MODULE_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    with mock.patch.dict(
        os.environ,
        {
            "BF_LLM_MODEL": "",
            "BF_ALLOWED_LOADED_MODELS": (
                "chiqiong-blast-furnace:latest,"
                "chiqiong-blast-furnace:latest_s"
            ),
        },
        clear=False,
    ):
        spec.loader.exec_module(module)
    return module


def test_legacy_30b_request_is_ignored_when_27b_is_loaded() -> None:
    backend = _load_backend()
    called_urls: list[str] = []

    def fake_urlopen(request, timeout=0):
        del timeout
        called_urls.append(request.full_url)
        return _Response({"models": [{"name": "chiqiong-blast-furnace:latest"}]})

    with mock.patch.object(backend, "urlopen", side_effect=fake_urlopen):
        selected = backend.normalize_model("bf-diagnosis-runtime:v1")

    assert selected == "chiqiong-blast-furnace:latest"
    assert called_urls == [f"{backend.OLLAMA_BASE_URL}/api/ps"]


def test_proxy_does_not_fall_back_to_installed_30b_tag() -> None:
    backend = _load_backend()

    def fake_urlopen(request, timeout=0):
        del request, timeout
        return _Response({"models": [{"name": "bf-diagnosis-runtime:v1"}]})

    with mock.patch.object(backend, "urlopen", side_effect=fake_urlopen):
        with pytest.raises(RuntimeError, match="没有已驻留的生产问答模型"):
            backend.normalize_model("bf-diagnosis-runtime:v1")


def test_unapproved_configured_model_is_rejected() -> None:
    backend = _load_backend()
    backend.DEFAULT_MODEL = "bf-diagnosis-runtime:v1"

    def fake_urlopen(request, timeout=0):
        del request, timeout
        return _Response(
            {
                "models": [
                    {"name": "chiqiong-blast-furnace:latest"},
                    {"name": "bf-diagnosis-runtime:v1"},
                ]
            }
        )

    with mock.patch.object(backend, "urlopen", side_effect=fake_urlopen):
        with pytest.raises(RuntimeError, match="不在生产允许清单"):
            backend.resolve_upstream_model()
