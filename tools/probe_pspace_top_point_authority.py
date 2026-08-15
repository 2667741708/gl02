from __future__ import annotations

import inspect
import json
import sys
from pathlib import Path


def main() -> int:
    root = Path(sys.argv[1]) if len(sys.argv) > 1 else Path.cwd()
    sdk_root = root / "pythonSDK(1)"
    sys.path.insert(0, str(sdk_root))

    from PythonAPI.PsServer import PsObject  # type: ignore
    from PythonAPI import Type as T  # type: ignore

    method_rows = []
    method_sources = {}
    for name, value in inspect.getmembers(PsObject):
        if name.startswith("_") or not callable(value):
            continue
        lowered = name.lower()
        if any(token in lowered for token in ("tag", "point", "search", "find", "browse", "list")):
            try:
                signature = str(inspect.signature(value))
            except Exception:
                signature = ""
            method_rows.append({"name": name, "signature": signature})
            if name in {"QueryTag", "QueryCountTag", "GetTagProps", "GetTagListProps"}:
                try:
                    method_sources[name] = inspect.getsource(value)
                except Exception as exc:
                    method_sources[name] = f"unavailable: {type(exc).__name__}: {exc}"

    type_rows = []
    for name in dir(T):
        lowered = name.lower()
        if any(token in lowered for token in ("tag", "point", "search", "find", "browse", "list")):
            value = getattr(T, name)
            if isinstance(value, (str, int, float, bool)) or value is None:
                type_rows.append({"name": name, "value": value})

    print(
        json.dumps(
            {
                "schema": "bf.pspace-point-authority-capabilities.v1",
                "sdk_root": str(sdk_root),
                "methods": method_rows,
                "method_sources": method_sources,
                "type_constants": type_rows,
            },
            ensure_ascii=False,
            indent=2,
            default=str,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
