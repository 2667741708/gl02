from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path


TARGET_CODES = {"T0040", "T0043", "T0064", "T0067", "T0068", "T0069", "T0070", "T0072"}
PARENTS = (r"\冀南钢铁\SIO\GL02\LD", r"\冀南二期\SIO\GL02\LD")
PROPS = ("PS_TAG_PROP_NAME", "PS_TAG_PROP_LONGNAME", "PS_TAG_PROP_DESCRIPTION")


def _clean(raw: str) -> str:
    value = raw.split("#", 1)[0].strip()
    if len(value) >= 2 and value[0] in "'\"" and value[-1] == value[0]:
        return value[1:-1]
    return value


def _read_config(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.exists():
        return values
    in_pspace = False
    for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        if re.match(r"^pspace\s*:\s*$", line):
            in_pspace = True
            continue
        if in_pspace and line.strip() and not line[:1].isspace():
            break
        if not in_pspace or ":" not in line:
            continue
        key, raw = line.strip().split(":", 1)
        if key.strip() in {"ip", "port", "username", "password"}:
            values[key.strip()] = _clean(raw)
    return values


def _numeric_items(mapping: object):
    if not isinstance(mapping, dict):
        return
    rows = []
    for key, value in mapping.items():
        try:
            rows.append((int(key), value))
        except Exception:
            continue
    for _, value in sorted(rows):
        yield value


def main() -> int:
    root = Path(sys.argv[1]) if len(sys.argv) > 1 else Path.cwd()
    sys.path.insert(0, str(root / "pythonSDK(1)"))
    from PythonAPI.PsServer import PsObject  # type: ignore
    from PythonAPI import Type as T  # type: ignore

    cfg = _read_config(root / "ghsc" / "src" / "main" / "resources" / "application-prod.yml")
    conn = {
        T.ServerDict: os.getenv("PSPACE_SERVER") or cfg.get("ip") or "10.22.181.243",
        T.ServerPortDict: os.getenv("PSPACE_PORT") or cfg.get("port") or "8889",
        T.UserDict: os.getenv("PSPACE_USER") or cfg.get("username") or "",
        T.PassDict: os.getenv("PSPACE_PASSWORD") or cfg.get("password") or "",
    }
    pspace = PsObject()
    output: dict[str, object] = {
        "schema": "bf.pspace-top-point-authority.v1",
        "server": conn[T.ServerDict],
        "port": str(conn[T.ServerPortDict]),
        "parents": [],
        "points": [],
    }
    try:
        connected = pspace.Connect(conn)
        if connected.get(T.Return) != 0:
            raise RuntimeError(f"connect failed: {connected.get(T.Return)} {connected.get(T.Error)}")
        found: list[str] = []
        parent_results = []
        for parent in PARENTS:
            raw = pspace.QueryTag({T.QueryTagLongName: parent})
            children = []
            for item in _numeric_items(raw):
                if not isinstance(item, dict):
                    continue
                long_name = str(item.get(T.QueryTagPropName, "") or "")
                if long_name:
                    children.append(long_name)
                    if any(code in long_name.upper() for code in TARGET_CODES):
                        found.append(long_name)
            parent_results.append(
                {
                    "parent": parent,
                    "return": raw.get(T.Return) if isinstance(raw, dict) else None,
                    "child_count": len(children),
                    "target_children": [x for x in children if any(code in x.upper() for code in TARGET_CODES)],
                }
            )
        output["parents"] = parent_results
        points = []
        for long_name in sorted(set(found)):
            raw = pspace.GetTagProps(
                {
                    T.GetTagPropsTagLongName: long_name,
                    T.GetTagPropsPropIdsList: list(PROPS),
                }
            )
            values = []
            for item in _numeric_items(raw):
                if isinstance(item, dict):
                    values.append(item.get(T.GetTagPropsValues))
            point = {
                "queried_long_name": long_name,
                "property_name": values[0] if len(values) > 0 else None,
                "property_long_name": values[1] if len(values) > 1 else None,
                "property_description": values[2] if len(values) > 2 else None,
                "return": raw.get(T.Return) if isinstance(raw, dict) else None,
            }
            points.append(point)
        output["points"] = points
        print(json.dumps(output, ensure_ascii=False, indent=2, default=str))
        return 0
    finally:
        try:
            pspace.CloseConnect()
        except Exception:
            pass


if __name__ == "__main__":
    raise SystemExit(main())
