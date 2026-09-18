"""One active QA request across roles, including cancellation and crash cleanup."""
from contextlib import contextmanager
import importlib.util
from pathlib import Path
import threading
import uuid
import pytest

SOURCE=Path(__file__).resolve().parents[1]/'高炉前端数据/智能助手/backend/qa_request_control.py'


def runtime(original):
    spec=importlib.util.spec_from_file_location('exclusive_'+uuid.uuid4().hex,SOURCE)
    module=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    class Handler:
        def __init__(self): self.responses=[]
        def send_json(self,payload,status=200): self.responses.append((status,payload))
        def write_qa_event(self,*args): return True
        def handle_qa_chat_stream(self,payload,question): original(self,payload,question)
        def handle_qa_chat_json(self,payload,question): original(self,payload,question)
        def do_GET(self): pass
        def do_POST(self): pass
    @contextmanager
    def database(): yield object()
    namespace={'urlopen':lambda *a,**k:object(),'db_connect':database,
        'guest_room_generation_lock':lambda owner:threading.Lock()}
    module.install(Handler,namespace)
    return module,Handler


def payload(role,owner='one'):
    return {'client_request_id':uuid.uuid4().hex,'conversation_id':'synthetic-'+owner,
        '_qa_owner_subject':owner,'_qa_access_mode':'guest_shared' if role=='guest' else 'private'}


@pytest.mark.parametrize('first,second',[('guest','guest'),('guest','operator'),('guest','admin'),
    ('operator','operator'),('operator','admin'),('admin','guest')])
def test_second_role_cannot_enter_generation_and_can_send_after_first_finishes(first,second):
    entered,released=threading.Event(),threading.Event()
    calls=[]
    def original(handler,p,q):
        calls.append(p['_qa_owner_subject'])
        entered.set()
        assert released.wait(3)
    module,Handler=runtime(original)
    worker=threading.Thread(target=Handler().handle_qa_chat_json,args=(payload(first),'first'))
    worker.start()
    assert entered.wait(2)
    blocked=Handler()
    try:
        blocked.handle_qa_chat_stream(payload(second,'two'),'second')
        status,response=blocked.responses[-1]
        assert status==409 and response['error']=='assistant_in_use'
        assert response['automatic_replay'] is False and 'request_id' not in response
        assert calls==['one'] and len(module._requests)==1
    finally:
        released.set()
        worker.join(3)
    assert not worker.is_alive()
    accepted=Handler()
    accepted.handle_qa_chat_json(payload(second,'two'),'manual new submission')
    assert calls==['one','two'] and not accepted.responses


def test_cancel_keeps_slot_until_the_actual_request_has_stopped():
    entered,released=threading.Event(),threading.Event()
    def original(handler,p,q):
        entered.set()
        assert released.wait(3)
    module,Handler=runtime(original)
    first=payload('operator')
    worker=threading.Thread(target=Handler().handle_qa_chat_stream,args=(first,'first'))
    worker.start()
    assert entered.wait(2)
    state=module._requests[first['client_request_id']]
    state.stop()
    blocked=Handler()
    try:
        blocked.handle_qa_chat_json(payload('admin','two'),'second')
        assert blocked.responses[-1][1]['error']=='assistant_in_use'
        assert not state.finished.is_set()
    finally:
        released.set()
        worker.join(3)
    assert state.finished.is_set() and state.state=='cancelled'
    Handler().handle_qa_chat_json(payload('admin','two'),'manual after cancellation')


def test_failure_releases_slot_without_replaying_failed_request():
    calls=[]
    def original(handler,p,q):
        calls.append(q)
        if q=='fail': raise RuntimeError('synthetic failure')
    module,Handler=runtime(original)
    first=payload('operator')
    with pytest.raises(RuntimeError,match='synthetic failure'):
        Handler().handle_qa_chat_json(first,'fail')
    assert module._requests[first['client_request_id']].finished.is_set()
    Handler().handle_qa_chat_json(payload('guest','two'),'new')
    assert calls==['fail','new']


def test_simultaneous_registration_has_only_one_winner():
    entered,released=threading.Event(),threading.Event()
    barrier=threading.Barrier(3)
    calls=[]
    def original(handler,p,q):
        calls.append(q)
        entered.set()
        assert released.wait(3)
    module,Handler=runtime(original)
    handlers=[Handler(),Handler()]
    def run(index):
        barrier.wait(2)
        handlers[index].handle_qa_chat_json(payload('operator',str(index)),str(index))
    workers=[threading.Thread(target=run,args=(index,)) for index in range(2)]
    for worker in workers: worker.start()
    barrier.wait(2)
    assert entered.wait(2)
    try:
        for worker in workers: worker.join(0.1)
        assert len(calls)==1
        responses=[response for handler in handlers for response in handler.responses]
        assert len(responses)==1 and responses[0][1]['error']=='assistant_in_use'
    finally:
        released.set()
        for worker in workers: worker.join(3)
    assert all(not worker.is_alive() for worker in workers)
