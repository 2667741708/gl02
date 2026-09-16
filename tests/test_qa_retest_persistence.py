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


def test_only_deterministic_document_tasks_can_skip_model_dependency():
    assert not runner.model_required('完整列出高炉工长安全操作规程原文')
    assert not runner.model_required('高炉工长在“1 工作前”中，关于“上班前必须佩戴好劳保用品”需要记住什么？请按原文回答。')
    assert runner.model_required('解释顶压升高的常见原因，不要查询实时数据')
    assert not runner.model_required('列出《三规二制》原文并查询当前炉顶压力')
    assert not runner.model_required('列出《不存在的正式规程》原文；查看当前炉顶压力是多少。')
    assert runner.model_required('列出《三规二制》原文；分析当前炉顶压力是否正常。')
    assert runner.model_required('列出《三规二制》原文；仅根据我提供的数值10、20、30计算平均值，不查询实时数据。')


def test_document_readiness_does_not_require_model_but_still_requires_proxy(monkeypatch):
    class Response:
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def read(self, *args): return json.dumps({'proxy_ok': True, 'model_ok': False}).encode()
    monkeypatch.setattr(runner, 'urlopen', lambda *args, **kwargs: Response())
    monkeypatch.setattr(runner.time, 'sleep', lambda *args: None)
    assert runner.status_ready('http://local/status', 1, [], False)
    assert not runner.status_ready('http://local/status', 1, [], True)
