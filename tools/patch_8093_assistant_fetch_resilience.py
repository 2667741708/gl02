"""Patch the 8093 page to handle transient service restart fetch failures safely."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


MARKER = "OPS-8093-QA-FETCH-RESILIENCE-20260806"
OLD_JSON = "    async function qaServerJson(url, options = {}) { const res = await fetch(url, { headers: { 'Content-Type': 'application/json', ...(options.headers || {}) }, ...options }); let data = null; try { data = await res.json() } catch (e) { } if (!res.ok || data?.ok === false) { throw new Error(data?.error || `接口 HTTP ${res.status}`) } return data }"
NEW_JSON = """    /* OPS-8093-QA-FETCH-RESILIENCE-20260806: retry GET only; never replay a question POST. */
    function qaFriendlyFetchError(error, requestStarted = false) { const raw = String(error?.message || error || '').trim(); if (/failed to fetch|networkerror|network request failed|load failed/i.test(raw)) return requestStarted ? '智能助手服务连接中断，可能正在受控重启。本次提问不会自动重发，以免重复请求；请约30秒后手动重试。' : '智能助手服务正在受控重启或暂不可达，系统会自动重试只读请求；请约30秒后再试。'; return raw || '智能助手接口请求失败' }
    function qaRetryDelay(ms) { return new Promise(resolve => setTimeout(resolve, ms)) }
    async function qaServerJson(url, options = {}) { const method = String(options.method || 'GET').toUpperCase(), attempts = method === 'GET' ? 3 : 1; let res = null; for (let attempt = 1; attempt <= attempts; attempt += 1) { try { res = await fetch(url, { headers: { 'Content-Type': 'application/json', ...(options.headers || {}) }, ...options }); break } catch (error) { if (attempt >= attempts) throw new Error(qaFriendlyFetchError(error, method !== 'GET')); await qaRetryDelay(attempt * 1500) } } let data = null; try { data = await res.json() } catch (e) { } if (!res.ok || data?.ok === false) { throw new Error(data?.error || `接口 HTTP ${res.status}`) } return data }"""
OLD_CHAT_FETCH = "      const res = await fetch('/api/qa/chat', { method: 'POST', headers: { 'Content-Type': 'application/json', 'Accept': 'text/event-stream' }, body: JSON.stringify({ ...payload, stream: true }) });"
NEW_CHAT_FETCH = "      let res; try { res = await fetch('/api/qa/chat', { method: 'POST', headers: { 'Content-Type': 'application/json', 'Accept': 'text/event-stream' }, body: JSON.stringify({ ...payload, stream: true }) }) } catch (error) { throw new Error(qaFriendlyFetchError(error, true)) }"
OLD_READER = "      while (true) { const part = await reader.read(); if (part.done) break; buffer += decoder.decode(part.value, { stream: true }); const lines = buffer.split(/\\r?\\n/); buffer = lines.pop() || ''; for (const line of lines) { if (line === '') { dispatch(); continue } if (line.startsWith('event:')) eventName = line.slice(6).trim() || 'message'; else if (line.startsWith('data:')) dataLines.push(line.slice(5).trimStart()) } }"
NEW_READER = "      while (true) { let part; try { part = await reader.read() } catch (error) { throw new Error(qaFriendlyFetchError(error, true)) } if (part.done) break; buffer += decoder.decode(part.value, { stream: true }); const lines = buffer.split(/\\r?\\n/); buffer = lines.pop() || ''; for (const line of lines) { if (line === '') { dispatch(); continue } if (line.startsWith('event:')) eventName = line.slice(6).trim() || 'message'; else if (line.startsWith('data:')) dataLines.push(line.slice(5).trimStart()) } }"


def validate(text: str) -> None:
    required = (
        MARKER,
        "attempts = method === 'GET' ? 3 : 1",
        "本次提问不会自动重发",
        NEW_CHAT_FETCH.strip(),
        NEW_READER.strip(),
    )
    missing = [item for item in required if item not in text]
    if missing:
        raise ValueError("fetch resilience contract is incomplete: " + ", ".join(missing))


def patch_text(text: str) -> tuple[str, bool]:
    if MARKER in text:
        validate(text)
        return text, False
    replacements = (
        (OLD_JSON, NEW_JSON),
        (OLD_CHAT_FETCH, NEW_CHAT_FETCH),
        (OLD_READER, NEW_READER),
    )
    updated = text
    for old, new in replacements:
        if updated.count(old) != 1:
            raise ValueError(f"expected exactly one approved patch anchor, found {updated.count(old)}")
        updated = updated.replace(old, new, 1)
    validate(updated)
    return updated, True


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--target", type=Path, required=True)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    original = args.target.read_text(encoding="utf-8-sig")
    updated, changed = patch_text(original)
    if args.check and changed:
        print(json.dumps({"ok": True, "applicable": True, "changed": False}))
        return 0
    if changed:
        args.target.write_text(updated, encoding="utf-8", newline="")
    print(json.dumps({"ok": True, "changed": changed, "marker": MARKER}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
