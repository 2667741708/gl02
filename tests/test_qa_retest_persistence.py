import importlib.util
import hashlib
import json
from pathlib import Path
import sys
import pytest

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


def test_followup_uses_only_completed_server_conversation_without_replay(tmp_path, monkeypatch):
    cases = tmp_path / 'cases.json'
    cases.write_text(json.dumps({'reviews': [{'case_id':'seed','question':'查询顶压'},
        {'case_id':'follow','question':'它现在是多少','conversation_from':'seed'}]}), encoding='utf-8')
    output = tmp_path / 'output'
    monkeypatch.setattr(sys, 'argv', ['runner','--failures',str(cases),'--output',str(output),'--execute'])
    monkeypatch.setattr(runner, 'status_ready', lambda *args: True)
    calls = []
    def request(*args):
        calls.append(args)
        return {'answer':'test','determinate':True,'terminated':True,'http_status':200,
                'final':{'ok':True,'conversation':{'id':'server-room'}}}
    monkeypatch.setattr(runner,'request_once',request)
    assert runner.main() == 0 and len(calls) == 2
    assert calls[0][-1] is None and calls[1][-1] == 'server-room'
    assert (output/'seed.claim').exists() and (output/'follow.claim').exists()


def test_failed_prior_turn_blocks_followup_before_its_claim(tmp_path, monkeypatch):
    cases = tmp_path/'cases.json'
    cases.write_text(json.dumps({'reviews':[{'case_id':'seed','question':'查询顶压'},
        {'case_id':'follow','question':'继续看','conversation_from':'seed'}]}), encoding='utf-8')
    output = tmp_path/'output'
    monkeypatch.setattr(sys,'argv',['runner','--failures',str(cases),'--output',str(output),'--execute'])
    monkeypatch.setattr(runner,'status_ready',lambda *args: True)
    calls=[]
    def request(*args):
        calls.append(args)
        return {'answer':'','determinate':True,'terminated':False,'http_status':401,'final':{}}
    monkeypatch.setattr(runner,'request_once',request)
    assert runner.main() == 1 and len(calls) == 1
    assert not (output/'follow.claim').exists()
    assert json.loads((output/'progress.json').read_text())['requests'] == 1


@pytest.mark.parametrize('replay', [False, True])
def test_continuation_reuses_completed_dependency_and_rejects_any_existing_claim(tmp_path, monkeypatch, replay):
    cases = tmp_path/'cases.json'
    cases.write_text(json.dumps({'reviews':[{'case_id':'seed','question':'查询顶压'},
        {'case_id':'follow','question':'它现在是多少','conversation_from':'seed'}]}), encoding='utf-8')
    prior = tmp_path/'prior'
    prior.mkdir()
    (prior/'progress.json').write_text(json.dumps({'source_sha256':hashlib.sha256(cases.read_bytes()).hexdigest(),
        'automatic_retries':0,'requests':1}), encoding='utf-8')
    (prior/'seed.claim').write_text(json.dumps({'prompt_sha256':hashlib.sha256('查询顶压'.encode()).hexdigest()}), encoding='utf-8')
    (prior/'seed.json').write_text(json.dumps({'case_id':'seed','request_count':1,'determinate':True,
        'terminated':True,'final':{'ok':True,'conversation':{'id':'server-room'}}}), encoding='utf-8')
    argv=['runner','--failures',str(cases),'--output',str(tmp_path/'output'),'--prior-round',str(prior),'--execute']
    if not replay: argv.extend(['--skip-case','seed'])
    monkeypatch.setattr(sys,'argv',argv)
    monkeypatch.setattr(runner,'status_ready',lambda *args: True)
    calls=[]
    def request(*args):
        calls.append(args)
        return {'answer':'test','determinate':True,'terminated':True,'http_status':200,
            'final':{'ok':True,'conversation':{'id':'server-room'}}}
    monkeypatch.setattr(runner,'request_once',request)
    if replay:
        with pytest.raises(RuntimeError, match='existing POST claim'): runner.main()
        assert not calls and not (tmp_path/'output').exists()
    else:
        assert runner.main()==0 and len(calls)==1 and calls[0][-1]=='server-room'
        assert not (tmp_path/'output/seed.claim').exists()
