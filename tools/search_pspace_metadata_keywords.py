"""One-shot read-only pSpace metadata search for keywords under selected roots."""

from __future__ import annotations

import argparse
import ast
import json
import re
import sys
from pathlib import Path


def literal_assignment(source: str, name: str) -> str | None:
    match = re.search(rf"(?m)^\s*{re.escape(name)}\s*=\s*(.+?)\s*$", source)
    if not match:
        return None
    try:
        value = ast.literal_eval(match.group(1))
    except (SyntaxError, ValueError):
        return None
    return value if isinstance(value, str) and value else None


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--sdk-root", type=Path, required=True)
    parser.add_argument("--server", default="10.22.181.243")
    parser.add_argument("--port", default="8889")
    parser.add_argument("--root", action="append", required=True)
    parser.add_argument("--keyword", action="append", required=True)
    args = parser.parse_args()

    project_root = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(project_root / "tools"))
    from pspace_8092_realtime_bridge import (
        connect_pspace,
        get_tag_props,
        load_sdk,
        query_all_tag_names,
    )

    credential_source = args.sdk_root / "read_sensor_data.py"
    source = credential_source.read_text(encoding="utf-8-sig")
    user = literal_assignment(source, "DEFAULT_USER")
    password = literal_assignment(source, "DEFAULT_PASSWORD")
    if not user or not password:
        raise SystemExit("Site-local read-only pSpace credentials not found")

    class Args:
        pspace_server = args.server
        pspace_port = args.port
        pspace_user = user
        pspace_password = password

    PsObject, T = load_sdk(args.sdk_root)
    pspace = connect_pspace(PsObject, T, Args())
    roots = tuple(args.root)
    keywords = tuple(keyword.casefold() for keyword in args.keyword)
    tags = [tag for tag in query_all_tag_names(pspace, T) if tag.startswith(roots)]
    matches = []
    errors = []
    for tag in tags:
        try:
            props = get_tag_props(pspace, T, tag)
        except Exception as exc:  # metadata access must continue point-by-point
            errors.append({"tag": tag, "error": type(exc).__name__})
            continue
        searchable = " ".join(
            str(props.get(field, "")) for field in ("name", "description", "unit")
        ).casefold()
        searchable = f"{tag.casefold()} {searchable}"
        hit_keywords = [keyword for keyword in keywords if keyword in searchable]
        if hit_keywords:
            matches.append(
                {
                    "tag": tag,
                    "name": props.get("name", ""),
                    "description": props.get("description", ""),
                    "unit": props.get("unit", ""),
                    "keywords": hit_keywords,
                }
            )
    print(
        json.dumps(
            {
                "roots": roots,
                "keywords": keywords,
                "tag_count": len(tags),
                "match_count": len(matches),
                "metadata_error_count": len(errors),
                "matches": matches,
                "errors": errors[:20],
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
