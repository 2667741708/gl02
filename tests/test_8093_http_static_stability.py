from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "高炉前端数据" / "智能助手" / "backend" / "ollama_proxy_server.py"
PAGE = ROOT / "高炉前端数据" / "frontend_dashboard_v3.server.html"
PROBE = ROOT / "tools" / "probe_8093_http_stability.py"


def test_http_server_has_browser_burst_capacity_contract():
    text = BACKEND.read_text(encoding="utf-8")
    assert "OPS-8093-HTTP-STATIC-STABILITY-20260806-R1" in text
    assert "class BlastFurnaceThreadingHTTPServer(ThreadingHTTPServer)" in text
    assert 'BF_8093_HTTP_REQUEST_QUEUE_SIZE", "128"' in text
    assert "daemon_threads = True" in text
    assert "block_on_close = False" in text
    assert "server = BlastFurnaceThreadingHTTPServer((HOST, PORT), Handler)" in text


def test_versioned_static_assets_are_cacheable_and_support_etag():
    text = BACKEND.read_text(encoding="utf-8")
    assert "self.serve_static(parsed.path, parsed.query)" in text
    assert 'any(key in parse_qs(request_query) for key in ("v", "release"))' in text
    assert '"public, max-age=31536000, immutable"' in text
    assert 'self.headers.get("If-None-Match") == etag' in text
    assert 'self.send_response(304)' in text


def test_glb_uses_stable_release_url_in_all_call_sites():
    text = PAGE.read_text(encoding="utf-8")
    assert "GL02_FURNACE_BODY_R1.glb?t=${Date.now()}" not in text
    assert text.count("GL02_FURNACE_BODY_R1.glb?v=20260806-static-stability-r1") == 2


def test_probe_uses_real_billboard_adapter_path():
    text = PROBE.read_text(encoding="utf-8")
    assert "/assets/bf3d-furnace-body-billboard-adapter.js?v=20260806-local-133-r1" in text
    assert "/assets/bf3d-billboard-adapter.js" not in text
