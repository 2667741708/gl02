from __future__ import annotations

import argparse
from pathlib import Path


MARKER = "REQ-CORE-IQR-BANDS-NEG1-POS1-20260715"

REPLACEMENTS = {
    "if(z>0.5)return{label:'偏高',tone:'warn',level:'high'};":
        "if(z>1)return{label:'偏高',tone:'warn',level:'high'};",
    "if(z<-0.5)return{label:'偏低',tone:'warn',level:'low'};":
        "if(z<-1)return{label:'偏低',tone:'warn',level:'low'};",
    ":a>0.5?{label:z>0?'偏高':'偏低',tone:'text-warn'}:":
        ":a>1?{label:z>0?'偏高':'偏低',tone:'text-warn'}:",
}


def patch(path: Path) -> bool:
    text = path.read_text(encoding="utf-8")
    changed = False
    for old, new in REPLACEMENTS.items():
        if new in text:
            continue
        count = text.count(old)
        if count != 1:
            raise RuntimeError(f"Expected one occurrence, found {count}: {old}")
        text = text.replace(old, new, 1)
        changed = True

    if MARKER not in text:
        anchor = '<script type="text/babel" data-presets="typescript,react">'
        if anchor not in text:
            raise RuntimeError("React script anchor not found")
        text = text.replace(anchor, anchor + f"\n/* {MARKER} */", 1)
        changed = True

    if changed:
        path.write_text(text, encoding="utf-8", newline="")

    verified = path.read_text(encoding="utf-8")
    checks = [MARKER, "if(z>1)return{label:'偏高'", "if(z<-1)return{label:'偏低'", ":a>1?{label:z>0?'偏高':'偏低'"]
    missing = [item for item in checks if item not in verified]
    if missing:
        raise RuntimeError(f"Verification failed: {missing}")
    return changed


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("path", type=Path)
    args = parser.parse_args()
    changed = patch(args.path)
    print(f"changed={str(changed).lower()}")
    print(f"marker={MARKER}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
