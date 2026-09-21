"""Exact resident/alias digest is required even when another model was approved."""
import importlib.util
from pathlib import Path
import sys

import pytest

BACKEND = Path(__file__).resolve().parents[1] / '高炉前端数据/智能助手/backend'
sys.path.insert(0, str(BACKEND))
spec = importlib.util.spec_from_file_location('fixed_identity', BACKEND / 'qa_fixed_model_identity.py')
fixed = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fixed)
PIN = fixed.MODEL_DIGEST
OTHER = '9111be230d48e53a385a28930fb8cf6972767c83e93c0db51f6b331a534e30fb'


def payload(digest, name=fixed.MODEL_NAME):
    return {'models': [{'name': name, 'digest': digest}]}


def test_exact_base_accepts_version_tag_residency_for_same_weights():
    assert fixed.resolve(lambda _: payload(PIN), lambda _: payload(PIN, 'same-weights:version'), sleep=lambda _: None) == fixed.MODEL_NAME


@pytest.mark.parametrize('alias,resident', [(OTHER, OTHER), (OTHER, PIN), (PIN, OTHER)])
def test_approved_alternative_or_alias_resident_mismatch_never_accepted(alias, resident):
    with pytest.raises(fixed.FixedModelUnavailable):
        fixed.resolve(lambda _: payload(alias), lambda _: payload(resident), sleep=lambda _: None)


@pytest.mark.parametrize('rows', [[], [{'digest': PIN}, {'digest': PIN}], [{'digest': PIN}, {'digest': OTHER}], None])
def test_no_or_multiple_residents_block(rows):
    with pytest.raises(fixed.FixedModelUnavailable):
        fixed.resolve(lambda _: payload(PIN), lambda _: {'models': rows}, sleep=lambda _: None)


def test_alias_changes_after_resident_read_blocks():
    calls = []
    def tags(_):
        calls.append('GET')
        return payload(PIN if len(calls) % 2 else OTHER)
    with pytest.raises(fixed.FixedModelUnavailable):
        fixed.resolve(tags, lambda _: payload(PIN), sleep=lambda _: None)
    assert len(calls) == 6


def test_one_total_get_budget_cannot_be_extended_by_attempts():
    now = [0.0]
    def tags(timeout):
        assert timeout <= 2
        now[0] += 7
        return payload(PIN)
    with pytest.raises(fixed.FixedModelUnavailable):
        fixed.resolve(tags, lambda _: pytest.fail('No GET after budget expires'), clock=lambda: now[0], sleep=lambda _: None)
    assert now[0] == 7


def test_cancellation_is_not_retried():
    def checkpoint():
        raise RuntimeError('cancelled')
    with pytest.raises(RuntimeError, match='cancelled'):
        fixed.resolve(lambda _: pytest.fail('No GET'), lambda _: pytest.fail('No GET'), checkpoint=checkpoint)


@pytest.mark.parametrize('name,digest', [
    ('alternative:latest', OTHER),
    (fixed.MODEL_NAME, OTHER),
    ('alternative:latest', PIN),
    (None, PIN),
    (fixed.MODEL_NAME, None),
])
def test_callers_cannot_override_immutable_identity_even_if_both_gets_agree(name, digest):
    calls = []
    def fetch(_):
        calls.append('GET')
        return payload(digest, name)
    with pytest.raises(fixed.FixedModelUnavailable):
        fixed.resolve(fetch, fetch, name=name, digest=digest, sleep=lambda _: None)
    assert calls == [], 'Foreign identity must be rejected before any upstream operation'


def test_explicit_exact_pin_is_compatible():
    assert fixed.resolve(lambda _: payload(PIN), lambda _: payload(PIN),
                         name=fixed.MODEL_NAME, digest=PIN, sleep=lambda _: None) == fixed.MODEL_NAME
