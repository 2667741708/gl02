"""Draft/publish/rollback helper for the ABC numeric JSON configuration."""
from __future__ import annotations

import hashlib
import json
import os
import tempfile
from pathlib import Path
from typing import Any, Mapping

from abc_rule_engine import validate_config


def config_hash(config: Mapping[str, Any]) -> str:
    data = json.dumps(config, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(data).hexdigest()


def load_draft(path: str | Path) -> dict[str, Any]:
    target = Path(path)
    value = json.loads(target.read_text(encoding="utf-8"))
    validate_config(value)
    return value


def publish_atomic(config: Mapping[str, Any], path: str | Path, *, reason: str, actor: str) -> dict[str, Any]:
    if not reason.strip() or not actor.strip():
        raise ValueError("publish requires change reason and actor")
    validate_config(config)
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    payload = dict(config)
    payload["config_hash"] = config_hash(config)
    payload["published_by"] = actor
    payload["change_reason"] = reason
    fd, temp_name = tempfile.mkstemp(prefix=target.name + ".", suffix=".tmp", dir=str(target.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_name, target)
    finally:
        if os.path.exists(temp_name):
            os.unlink(temp_name)
    return {"config_version": payload.get("config_version"), "config_hash": payload["config_hash"], "published_by": actor, "change_reason": reason}

