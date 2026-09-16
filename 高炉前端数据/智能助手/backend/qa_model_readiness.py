"""Bounded read-only readiness; never load tags, switch models or replay chat."""
from __future__ import annotations

import time
from typing import Any

VERSION = "qa-model-readiness-v1"


class ModelUnavailable(RuntimeError):
    code = "approved_model_not_ready"
    retryable = True


def public_error_fields(error: BaseException) -> dict[str, Any]:
    if not isinstance(error, ModelUnavailable):
        return {}
    return {"code": error.code, "retryable": True, "automatic_replay": False,
            "terminal_state": "dependency_blocked"}


def resolve_resident(fetch: Any, *, allowed: tuple[str, ...], default: str = "", checkpoint: Any = lambda: None,
                     timeout: float = 6, clock: Any = time.monotonic, sleep: Any = time.sleep) -> str:
    if not allowed or (default and default not in allowed):
        raise RuntimeError("生产模型允许清单或固定模型配置无效")
    deadline = clock() + timeout
    for attempt in range(3):
        checkpoint()
        remaining = deadline - clock()
        if remaining <= 0:
            break
        try:
            payload = fetch(min(2.0, remaining))
            rows = payload.get("models") if isinstance(payload, dict) else None
            names = [str(row.get("name") or row.get("model") or "").strip() for row in rows if isinstance(row, dict)] if isinstance(rows, list) else []
        except Exception:
            names = []
        candidates = (default,) if default else allowed
        if clock() <= deadline:
            for name in candidates:
                if name in names:
                    return name
        if attempt < 2 and deadline - clock() > 0.2:
            checkpoint()
            sleep(0.2)
    raise ModelUnavailable("允许的生产问答模型暂未就绪；本次没有重发模型请求，请稍后手动发送。")
