"""REQ-QA-SINGLE-BASE-MODEL-20260917: one immutable base, no approved-model fallback."""
from __future__ import annotations

import time
from typing import Any

from qa_model_readiness import ModelUnavailable

VERSION = 'qa-fixed-model-identity-v1'
MODEL_NAME = 'chiqiongblastfuenace:latest'
# The actually resident base and V26 frozen resident identity, not the mutable alias.
MODEL_DIGEST = 'e4ad74c41d68de1c8004419d8141a2b2df2275fa08f0dcf326ca0e63fb6d8124'


class FixedModelUnavailable(ModelUnavailable):
    code = 'fixed_model_identity_not_ready'


def _alias(rows: Any, name: str, digest: str) -> bool:
    if not isinstance(rows, list):
        return False
    matches = [r for r in rows if isinstance(r, dict) and (r.get('name') or r.get('model')) == name]
    return len(matches) == 1 and matches[0].get('digest') == digest


def _resident(rows: Any, digest: str) -> bool:
    return isinstance(rows, list) and len(rows) == 1 and isinstance(rows[0], dict) and rows[0].get('digest') == digest


def resolve(fetch_tags: Any, fetch_resident: Any, *, checkpoint: Any = lambda: None,
            timeout: float = 6, clock: Any = time.monotonic, sleep: Any = time.sleep,
            name: str = MODEL_NAME, digest: str = MODEL_DIGEST) -> str:
    """GET tags -> ps -> tags with one total budget; never load or choose another base."""
    deadline = clock() + timeout

    def fetch(callback):
        checkpoint()
        remaining = deadline - clock()
        if remaining <= 0:
            raise TimeoutError('Fixed identity GET budget expired')
        payload = callback(min(2.0, remaining))
        if clock() > deadline:
            raise TimeoutError('Fixed identity GET budget expired')
        return payload.get('models') if isinstance(payload, dict) else None

    for attempt in range(3):
        try:
            if _alias(fetch(fetch_tags), name, digest) and _resident(fetch(fetch_resident), digest) and _alias(fetch(fetch_tags), name, digest):
                return name
        except (OSError, TimeoutError, ValueError, TypeError, KeyError):
            pass
        # Cancellation exceptions propagate; no next request is sent.
        if attempt < 2 and deadline - clock() > 0.2:
            checkpoint()
            sleep(0.2)
        else:
            break
    raise FixedModelUnavailable('固定问答底座身份不一致或尚未驻留；本次没有切换模型或重发请求。')
