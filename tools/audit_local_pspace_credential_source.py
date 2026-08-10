from __future__ import annotations

import re
from pathlib import Path


SAFE_TOKEN = re.compile(
    r"^(?:PSPACE_[A-Z0-9_]+|BF_[A-Z0-9_]+|[A-Za-z0-9_.\\/:-]+\.(?:env|ps1|py|yml|yaml|json)|"
    r"[A-Za-z]:\\|10\.\d+\.\d+\.\d+(?::\d+)?|Registry::|HKLM|HKCU)",
    re.IGNORECASE,
)


def sanitize_inline_code(line: str) -> str:
    def replace(match: re.Match[str]) -> str:
        token = match.group(1)
        return f"`{token}`" if SAFE_TOKEN.search(token) else "`<redacted>`"

    return re.sub(r"`([^`]*)`", replace, line)


def main() -> int:
    path = Path("AGENTS.md")
    patterns = re.compile(r"PSPACE_|pSpace.*(?:账号|密码|凭据|环境变量|配置)", re.IGNORECASE)
    for number, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not patterns.search(raw):
            continue
        safe = sanitize_inline_code(raw)
        safe = re.sub(r"(?i)((?:密码|password)\s*[:=：]\s*)([^\s,，;；]+)", r"\1<redacted>", safe)
        safe = re.sub(r"(?i)((?:账号|user(?:name)?)\s*[:=：]\s*)([^\s,，;；]+)", r"\1<redacted>", safe)
        print(f"{number}: {safe}")
        if "pSpace/PythonAPI 示例账号" in raw:
            tokens = re.findall(r"`([^`]*)`", raw)
            print(f"{number}: credential_token_count={len(tokens)} lengths={[len(token) for token in tokens]}")
            index = 0

            def placeholder(match: re.Match[str]) -> str:
                nonlocal index
                index += 1
                return f"<token{index}:len={len(match.group(1))}>"

            print(f"{number}: template={re.sub(r'`([^`]*)`', placeholder, raw)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
