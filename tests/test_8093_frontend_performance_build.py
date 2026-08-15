from __future__ import annotations

import gzip
import importlib.util
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
FRONTEND = ROOT / "高炉前端数据"
BUILD_ROOT = FRONTEND / "dashboard_build"
COMPRESSION_MODULE = FRONTEND / "智能助手" / "backend" / "http_static_compression.py"


def load_compression_module():
    spec = importlib.util.spec_from_file_location("http_static_compression_test", COMPRESSION_MODULE)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_build_contract_uses_vite_react_18_and_no_model_compression() -> None:
    package = json.loads((BUILD_ROOT / "package.json").read_text(encoding="utf-8"))
    assert package["dependencies"]["vite"] == "6.4.2"
    assert package["dependencies"]["react"] == "18.3.1"
    assert package["dependencies"]["react-dom"] == "18.3.1"
    script = (BUILD_ROOT / "scripts" / "build-dashboard.mjs").read_text(encoding="utf-8")
    assert 'import * as ReactDOMClient from "react-dom/client";' in script
    assert 'import { createPortal } from "react-dom";' in script
    assert "Object.freeze({ ...ReactDOMClient, createPortal })" in script
    assert "browserBabelRemoved" in script
    assert "developmentReactRemoved" in script
    assert "GL02_FURNACE_BODY_R1.glb?v=20260806-static-stability-r1" in script
    assert "draco" not in script.lower()
    assert "meshopt" not in script.lower()
    assert "ktx2" not in script.lower()


def test_overview_loader_has_no_static_three_import_and_is_route_gated() -> None:
    loader = (BUILD_ROOT / "src" / "overview-route-loader.js").read_text(encoding="utf-8")
    assert 'activeRoute() !== "overview"' in loader
    assert "import(/* @vite-ignore */ url)" in loader
    assert "three.module.js" not in loader
    assert "GL02_FURNACE_BODY_R1.glb" not in loader
    assert loader.index("bf-core-metrics-pspace-live-8093.js") < loader.index(
        "bf3d-furnace-body-billboard-adapter.js"
    )


def test_shared_scheduler_pauses_when_page_is_hidden() -> None:
    source = (FRONTEND / "assets" / "bf-shared-runtime-scheduler.js").read_text(encoding="utf-8")
    assert "if (document.hidden)" in source
    assert 'document.addEventListener("visibilitychange"' in source
    assert 'schema: "bf.shared-runtime-scheduler.v1"' in source


def test_8770_consumers_share_one_frame_event() -> None:
    core = (FRONTEND / "assets" / "bf-core-metrics-pspace-live-8093.js").read_text(
        encoding="utf-8"
    )
    billboard = (FRONTEND / "assets" / "bf3d-furnace-body-billboard-adapter.js").read_text(
        encoding="utf-8"
    )
    assert 'const FRAME_EVENT_NAME = "bf:pspace-frame"' in core
    assert "new CustomEvent(FRAME_EVENT_NAME" in core
    assert 'window.addEventListener("bf:pspace-frame"' in billboard
    assert "if (attachSharedTransport()) return" in billboard


def test_gzip_negotiation_round_trip() -> None:
    module = load_compression_module()
    payload = ("高炉生产大屏" * 1000).encode("utf-8")
    compressed, encoding = module.compress_static_payload(
        payload,
        "text/html; charset=utf-8",
        "gzip",
    )
    assert encoding == "gzip"
    assert len(compressed) < len(payload)
    assert gzip.decompress(compressed) == payload


def test_brotli_is_preferred_when_runtime_is_available() -> None:
    module = load_compression_module()
    payload = b"dashboard-production-build" * 1000
    compressed, encoding = module.compress_static_payload(
        payload,
        "application/javascript; charset=utf-8",
        "gzip;q=0.8, br;q=1.0",
    )
    if module.brotli_available():
        assert encoding == "br"
        assert module.brotli.decompress(compressed) == payload
    else:
        assert encoding == "gzip"
        assert gzip.decompress(compressed) == payload


def test_binary_and_small_payloads_are_not_compressed() -> None:
    module = load_compression_module()
    assert module.compress_static_payload(b"short", "text/html", "gzip") == (b"short", None)
    binary = b"x" * (module.MIN_BYTES + 1)
    assert module.compress_static_payload(binary, "model/gltf-binary", "br, gzip") == (
        binary,
        None,
    )
