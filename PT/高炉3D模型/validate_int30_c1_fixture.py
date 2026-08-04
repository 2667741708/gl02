from __future__ import annotations

import json
from pathlib import Path

from build_int30_c1_fixture import (
    FIXTURE_PATH,
    REPORT_PATH,
    canonical_bytes,
    sha256_bytes,
    validate_fixture,
    write_json,
)


def main() -> int:
    fixture = json.loads(Path(FIXTURE_PATH).read_text(encoding="utf-8"))
    report = validate_fixture(fixture)
    report["fixture_sha256"] = sha256_bytes(canonical_bytes(fixture))
    write_json(REPORT_PATH, report)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
