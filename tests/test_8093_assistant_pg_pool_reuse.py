"""Regression contracts for the 8093 nested PostgreSQL pool lease fix.

ERR-8093-ASSISTANT-PG-POOL-NESTED-LEASE-20260805
"""

from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "高炉前端数据" / "智能助手" / "backend"
RAG_PATH = BACKEND / "bf_knowledge_rag.py"
PROXY_PATH = BACKEND / "ollama_proxy_server.py"
PATCHER_PATH = ROOT / "tools" / "patch_8093_assistant_pg_pool_reuse.py"
DEPLOYER_PATH = ROOT / "tools" / "remote_guarded_deploy_8093_pg_pool_reuse.ps1"


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def powershell_51_copy(source: Path, destination: Path) -> Path:
    payload = source.read_bytes()
    if payload.startswith(b"\xef\xbb\xbf"):
        payload = payload[3:]
    destination.write_bytes(b"\xef\xbb\xbf" + payload)
    return destination


def test_search_knowledge_reuses_caller_connection(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.syspath_prepend(str(BACKEND))
    rag = load_module("bf_knowledge_rag_pool_reuse_test", RAG_PATH)
    fake_connection = object()
    observed: list[object] = []

    def fail_nested_lease():
        raise AssertionError("raw_pg_connect must not be called for a caller-owned lease")

    monkeypatch.setattr(rag, "raw_pg_connect", fail_nested_lease)
    monkeypatch.setattr(rag, "ensure_schema", lambda conn: observed.append(conn))
    monkeypatch.setattr(rag, "query_keyword_candidates", lambda conn, expanded: [])
    monkeypatch.setattr(rag, "query_fallback_candidates", lambda conn: [])

    result = rag.search_knowledge("高炉透气性为什么会变差", mode="keyword", connection=fake_connection)

    assert result["enabled"] is True
    assert result["retrieval_mode"] == "keyword"
    assert observed == [fake_connection]


def test_prepare_qa_chat_passes_active_lease_to_knowledge_search() -> None:
    source = PROXY_PATH.read_text(encoding="utf-8")

    assert "connection: Any | None = None" in source
    assert "connection=connection" in source
    assert "connection=conn" in source
    assert "qa_search_knowledge(question, mcp_prefetch=mcp_prefetch)" not in source


def test_patcher_is_idempotent_on_current_sources() -> None:
    patcher = load_module("patch_8093_assistant_pg_pool_reuse_test", PATCHER_PATH)

    result = patcher.apply(ROOT, check_only=True)

    assert result["patch_id"] == "ERR-8093-ASSISTANT-PG-POOL-NESTED-LEASE-20260805"
    assert all(row["changed"] is False for row in result["files"])


def test_patcher_scopes_connection_context_to_search_knowledge(tmp_path: Path) -> None:
    patcher = load_module("patch_8093_assistant_pg_pool_reuse_scope_test", PATCHER_PATH)
    rag = RAG_PATH.read_text(encoding="utf-8")
    proxy = PROXY_PATH.read_text(encoding="utf-8")
    rag = rag.replace("from contextlib import nullcontext\n", "", 1)
    rag = rag.replace(
        "    mode: str | None = None,\n    connection: Any | None = None,\n    source_doc_ids: Sequence[str] | None = None,\n) -> dict[str, Any]:",
        "    mode: str | None = None,\n) -> dict[str, Any]:",
        1,
    )
    rag = rag.replace(
        "    try:\n        connection_context = nullcontext(connection) if connection is not None else raw_pg_connect()\n"
        "        with connection_context as conn:\n            ensure_schema(conn)\n"
        "            if search_mode in {\"keyword\", \"hybrid\"}:\n"
        "                lexical_rows = (\n"
        "                    query_keyword_candidates(conn, expanded, source_scope)\n"
        "                    if source_scope\n"
        "                    else query_keyword_candidates(conn, expanded)\n"
        "                )\n"
        "                if not lexical_rows:\n"
        "                    lexical_rows = (\n"
        "                        query_fallback_candidates(conn, source_scope)\n"
        "                        if source_scope\n"
        "                        else query_fallback_candidates(conn)\n"
        "                    )\n"
        "            if search_mode in {\"vector\", \"hybrid\"}:\n"
        "                vector_pack = query_pgvector_candidates(\n"
        "                    conn, expanded, max(60, top_k * 12), source_scope\n"
        "                )",
        "    try:\n        with raw_pg_connect() as conn:\n            ensure_schema(conn)\n"
        "            if search_mode in {\"keyword\", \"hybrid\"}:",
        1,
    )
    proxy = proxy.replace(
        "def qa_search_knowledge(\n    question: str,\n    mode: str | None = None,\n"
        "    mcp_prefetch: dict[str, Any] | None = None,\n    connection: Any | None = None,\n) -> dict[str, Any]:",
        "def qa_search_knowledge(question: str, mode: str | None = None, mcp_prefetch: dict[str, Any] | None = None) -> dict[str, Any]:",
        1,
    )
    proxy = proxy.replace(
        "        mode=mode or QA_KNOWLEDGE_SEARCH_MODE,\n        connection=connection,\n    )",
        "        mode=mode or QA_KNOWLEDGE_SEARCH_MODE,\n    )",
        1,
    )
    proxy = proxy.replace(
        "            knowledge_pack = qa_search_knowledge(\n                question,\n"
        "                mcp_prefetch=mcp_prefetch,\n                connection=conn,\n            )",
        "            knowledge_pack = qa_search_knowledge(question, mcp_prefetch=mcp_prefetch)",
        1,
    )
    rag_target = tmp_path / patcher.RAG_RELATIVE
    proxy_target = tmp_path / patcher.PROXY_RELATIVE
    rag_target.parent.mkdir(parents=True)
    rag_target.write_text(rag, encoding="utf-8", newline="\n")
    proxy_target.write_text(proxy, encoding="utf-8", newline="\n")

    assert rag.count("with raw_pg_connect() as conn:\n            ensure_schema(conn)") >= 3
    result = patcher.apply(tmp_path, check_only=True)

    assert all(row["changed"] is True for row in result["files"])


@pytest.mark.skipif(sys.platform != "win32", reason="Windows PowerShell 5.1 syntax contract")
def test_deployer_parses_in_windows_powershell_51(tmp_path: Path) -> None:
    script = powershell_51_copy(DEPLOYER_PATH, tmp_path / DEPLOYER_PATH.name)
    probe = tmp_path / "parse-deployer.ps1"
    probe.write_bytes(
        b"\xef\xbb\xbf"
        + (
            "$tokens=$null; $errors=$null; "
            f"[System.Management.Automation.Language.Parser]::ParseFile('{script}',[ref]$tokens,[ref]$errors)|Out-Null; "
            "if($errors.Count -gt 0){$errors|ForEach-Object{$_.Message}; exit 1}; 'parse_ok'"
        ).encode("utf-8")
    )
    completed = subprocess.run(
        ["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(probe)],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=30,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr or completed.stdout
    assert "parse_ok" in completed.stdout


def test_deployer_is_hash_bounded_and_isolated() -> None:
    source = DEPLOYER_PATH.read_text(encoding="utf-8")

    assert "8F38DA0286791A95722520D7278AE2A37544E3D4EB255D8A5950FC3CAD50EFD0" in source
    assert "C42CA839CD83541F679D348B6652B0BFFC1AAB2EE72D96C3B08395A70E6289AA" in source
    assert "8768, 8094, 8770, 11434" in source
    assert "rollbackApplied" in source
    assert "default keyword knowledge search did not recover" in source
    assert "Start-ManagedServiceWithRetry" in source
    assert "Start-Sleep -Seconds 15" in source
