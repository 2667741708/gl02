from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DEPLOYER = ROOT / "tools" / "remote_guarded_deploy_8093_http_static_stability.ps1"
BACKEND = ROOT / "高炉前端数据" / "智能助手" / "backend" / "ollama_proxy_server.py"


def test_deployer_is_8093_only_and_has_no_mutex():
    text = DEPLOYER.read_text(encoding="utf-8")
    assert "$ServiceName = 'BFV4PreviewProxy8093'" in text
    assert "deployment_mutex_used = $false" in text
    assert "Global\\BFV4PreviewProxy8093Deployment" not in text
    assert "BFV4PreviewWs8768" not in text
    assert "Stop-Service" not in text


def test_deployer_protects_other_ports_and_rolls_back():
    text = DEPLOYER.read_text(encoding="utf-8")
    assert "@(8768, 8094, 8770)" in text
    assert "Copy-Item -LiteralPath $BackendTarget -Destination $backendBackup" in text
    assert "Install-Atomic $backendBackup $BackendTarget" in text
    assert "Enable-ScheduledTask" in text
    assert "finally" in text


def test_deployer_requires_internal_concurrency_smoke_and_cache_contract():
    text = DEPLOYER.read_text(encoding="utf-8")
    assert "--rounds 3 --concurrency 8 --timeout 15" in text
    assert "internal HTTP stability probe failed" in text
    assert "versioned adapter is not immutable-cacheable" in text
    assert "versioned adapter lacks ETag" in text


def test_backend_rewrites_random_glb_url_for_manifest_safe_deploy():
    text = BACKEND.read_text(encoding="utf-8")
    assert "OPS-8093-STABLE-GLB-URL-REWRITE-20260806-R1" in text
    assert '"models/GL02_FURNACE_BODY_R1.glb?t=${Date.now()}"' in text
    assert '"models/GL02_FURNACE_BODY_R1.glb?v=20260806-static-stability-r1"' in text
