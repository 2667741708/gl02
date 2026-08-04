from __future__ import annotations

import json
from pathlib import Path
from typing import Any


SERVICE_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SERVICE_DIR.parent
DEFAULT_CONFIG = SERVICE_DIR / "config.yaml"


def _simple_yaml(text: str) -> dict[str, Any]:
    """Small YAML subset parser used only if PyYAML is unavailable."""
    result: dict[str, Any] = {}
    stack: list[tuple[int, Any]] = [(-1, result)]
    last_key_at_indent: dict[int, str] = {}
    for raw in text.splitlines():
        if not raw.strip() or raw.lstrip().startswith("#"):
            continue
        indent = len(raw) - len(raw.lstrip(" "))
        line = raw.strip()
        while stack and indent <= stack[-1][0]:
            stack.pop()
        parent = stack[-1][1]
        if line.startswith("- "):
            value = line[2:].strip()
            if not isinstance(parent, list):
                raise ValueError("Unsupported YAML list placement")
            parent.append(_coerce(value))
            continue
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        key = key.strip()
        value = value.strip()
        if value == "":
            container: dict[str, Any] | list[Any]
            next_container: dict[str, Any] = {}
            parent[key] = next_container
            last_key_at_indent[indent] = key
            stack.append((indent, next_container))
        else:
            parent[key] = _coerce(value)

    # This fallback is intentionally conservative; config.yaml is normally read by PyYAML.
    return result


def _coerce(value: str) -> Any:
    if value in {"true", "True"}:
        return True
    if value in {"false", "False"}:
        return False
    try:
        return int(value)
    except ValueError:
        pass
    try:
        return float(value)
    except ValueError:
        return value.strip('"').strip("'")


def load_config(path: str | Path = DEFAULT_CONFIG) -> dict[str, Any]:
    path = Path(path)
    text = path.read_text(encoding="utf-8")
    if path.suffix.lower() == ".json":
        return json.loads(text)
    try:
        import yaml

        return yaml.safe_load(text) or {}
    except Exception:
        return _simple_yaml(text)


def project_path(value: str | Path) -> Path:
    path = Path(value)
    if path.is_absolute():
        return path
    return PROJECT_ROOT / path
