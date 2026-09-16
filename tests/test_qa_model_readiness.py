import sys
from pathlib import Path
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "高炉前端数据" / "智能助手" / "backend"))
import qa_model_readiness as ready


def test_transient_empty_ps_is_rechecked_without_model_generation():
    calls = []
    responses = iter([{"models": []}, {"models": [{"name": "approved"}]}])
    def fetch(timeout):
        calls.append(timeout)
        return next(responses)
    assert ready.resolve_resident(fetch, allowed=("approved",), sleep=lambda _: None) == "approved"
    assert len(calls) == 2 and max(calls) <= 2


def test_other_installed_or_loaded_model_is_never_forwarded():
    calls = []
    def fetch(timeout):
        calls.append(timeout)
        return {"models": [{"name": "unapproved"}]}
    with pytest.raises(ready.ModelUnavailable) as error:
        ready.resolve_resident(fetch, allowed=("approved",), sleep=lambda _: None)
    assert len(calls) == 3 and error.value.retryable
    assert error.value.code == "approved_model_not_ready"


def test_invalid_default_fails_without_upstream_request():
    with pytest.raises(RuntimeError):
        ready.resolve_resident(lambda _: pytest.fail("must not query"), allowed=("approved",), default="unapproved")


def test_deadline_and_cancellation_do_not_return_late_ready_model():
    now = [0.0]
    def fetch(timeout):
        now[0] += 7
        return {"models": [{"name": "approved"}]}
    with pytest.raises(ready.ModelUnavailable):
        ready.resolve_resident(fetch, allowed=("approved",), clock=lambda: now[0], sleep=lambda _: None)
    class Cancelled(BaseException):
        pass
    def cancel():
        raise Cancelled()
    with pytest.raises(Cancelled):
        ready.resolve_resident(lambda _: pytest.fail("must not query"), allowed=("approved",), checkpoint=cancel)
