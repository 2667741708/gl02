import importlib.util
import json
from pathlib import Path
import sys

path = Path(__file__).resolve().parents[1] / 'tools/run_qa_failed_retest_once.py'
spec = importlib.util.spec_from_file_location('retest_persistence', path)
runner = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runner)


def test_missing_review_metadata_cannot_erase_a_sent_production_result(tmp_path, monkeypatch):
    cases = tmp_path / 'cases.json'
    cases.write_text(json.dumps({'reviews': [{'case_id': 'case-1', 'question': 'normal question'}]}), encoding='utf-8')
    output = tmp_path / 'output'
    calls = []
    monkeypatch.setattr(sys, 'argv', ['runner', '--failures', str(cases), '--output', str(output), '--execute'])
    monkeypatch.setattr(runner, 'status_ready', lambda *args: True)
    def request(*args):
        calls.append(args)
        return {'answer': 'Complete answer.', 'determinate': True, 'terminated': True, 'final': {}, 'http_status': 200}
    monkeypatch.setattr(runner, 'request_once', request)
    assert runner.main() == 0 and len(calls) == 1
    saved = json.loads((output / 'case-1.json').read_text(encoding='utf-8'))
    assert saved['answer'] == 'Complete answer.' and saved['request_count'] == 1
    assert (output / 'case-1.claim').exists()
