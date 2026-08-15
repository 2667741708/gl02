import json
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "tools" / "verify_abc_contextual_assistant_viewports.cjs"


def test_verifier_declares_exact_full_matrix_and_required_routes():
    source = SCRIPT.read_text(encoding="utf-8")
    assert 'const ROUTES = ["overview", "diagnosis", "optimization", "trend", "qa"]' in source
    assert "[1546, 864]" in source
    assert "[375, 667]" in source
    assert 'expected_full_matrix: 85' in source
    assert 'page.on("pageerror"' in source
    assert 'message.type() !== "error"' in source
    assert "consoleErrors" in source
    assert "consoleNotes" in source
    assert "code generator has deoptimised the styling" in source
    assert "horizontalOverflow" in source
    assert "mainEndsAboveNav" in source
    assert "routeEndsAboveNav" in source
    assert "dismissAutomaticDiagnosisReview" in source
    assert '#bf-abc33-assistant-dialog' in source
    assert "transientCombinationFailure" in source
    assert "retry_count" in source
    assert "first_failure" in source
    assert "data_state" in source
    assert "screenshot" in source


def test_matrix_listing_is_85_and_model_sse_is_mocked():
    completed = subprocess.run(
        ["node", str(SCRIPT), "--list-matrix"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    payload = json.loads(completed.stdout)
    assert payload["total"] == 85
    assert {item["engine"] for item in payload["matrix"]} == {"chromium", "firefox", "webkit"}
    assert {item["route"] for item in payload["matrix"]} == {"overview", "diagnosis", "optimization", "trend", "qa"}

    source = SCRIPT.read_text(encoding="utf-8")
    assert 'acceptsEventStream' in source
    assert 'pathname === "/api/qa/chat"' in source
    assert 'pathname === "/v1/chat/completions"' in source
    assert 'real_sent: 0' in source


def test_cli_exposes_base_url_auth_and_focused_filters():
    source = SCRIPT.read_text(encoding="utf-8")
    for token in (
        "ABC_VIEWPORT_BASE_URL",
        "ABC_VIEWPORT_AUTHORIZATION",
        "ABC_VIEWPORT_BASIC_USER",
        "ABC_VIEWPORT_BASIC_PASSWORD",
        "ABC_VIEWPORT_STORAGE_STATE",
        '"--base-url"',
        '"--engine"',
        '"--route"',
        '"--viewport"',
        '"--retry-failed"',
    ):
        assert token in source
