"""Owner and completion counterexamples for mixed history/current requests."""
from pathlib import Path
import sqlite3
import sys
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / '高炉前端数据/智能助手/backend'))
import qa_history_compound as compound
import qa_task_plan


@pytest.fixture
def connection():
    conn = sqlite3.connect(':memory:')
    conn.row_factory = sqlite3.Row
    conn.executescript('''CREATE TABLE qa_conversations(id INTEGER, owner_subject TEXT);
        CREATE TABLE qa_messages(id INTEGER, conversation_id INTEGER, role TEXT, content TEXT, created_at TEXT);
        INSERT INTO qa_conversations VALUES(1,'owner-a'),(2,'owner-b');
        INSERT INTO qa_messages VALUES(1,1,'assistant','炉顶压力历史回答','2026-09-01'),
            (2,2,'assistant','炉顶压力他人私有回答','2026-09-02'),
            (10,1,'user','炉顶压力本轮复合提问','2026-09-03');''')
    yield conn
    conn.close()


def request():
    question = '历史问答里关于炉顶压力的回答；再查询现在炉顶压力的最新值是多少'
    plan = qa_task_plan.build_task_plan(question)
    assert plan['intents'] == ['conversation_history', 'live_data']
    return compound.split_request(question, plan)


def test_mixed_history_has_separate_present_question_and_owner_cutoff(connection):
    pack = compound.execute(request(), connection, owner='owner-a', before_message_id=10, selection={'mode': 'auto'})
    answer = pack['outcomes'][0]['answer']
    assert '历史回答' in answer and '他人私有' not in answer and '本轮复合提问' not in answer
    assert '历史' not in pack['remainder_question']
    assert qa_task_plan.build_task_plan(pack['remainder_question'])['intents'] == ['live_data']


@pytest.mark.parametrize('owner,cutoff', [('',10),('owner-a',0),('owner-a',True),('owner-a','10')])
def test_no_valid_server_authority_blocks_only_history(connection, owner, cutoff):
    pack = compound.execute(request(), connection, owner=owner, before_message_id=cutoff, selection={'mode': 'auto'})
    answer, result = compound.compose('当前核验事实', {'completion': {'terminal_state': 'completed', 'complete': True}}, {'history_compound': pack})
    assert '当前核验事实' in answer and '他人私有' not in answer
    assert result['completion']['terminal_state'] == 'partial'


@pytest.mark.parametrize('selection', [{'mode':'none'}, {'mode':'required','tools':['query_gl02_sensors']}])
def test_explicit_tool_selection_cannot_authorize_unrequested_history(connection, selection):
    pack = compound.execute(request(), connection, owner='owner-a', before_message_id=10, selection=selection)
    assert pack['outcomes'][0]['completion']['reason'] == 'history_tool_selection_blocked'


def test_required_history_tool_removed_from_data_selection():
    result = compound.data_tool_selection({'mode':'required','tools':['search_qa_messages','query_gl02_sensors']}, request())
    assert result['tools'] == ['query_gl02_sensors'] and result['mode'] == 'required'
    assert compound.data_tool_selection({'mode':'required','tools':['search_qa_messages']}, request())['mode'] == 'none'


def test_historical_answers_and_prior_chat_never_enter_current_model(connection):
    pack = compound.execute(request(), connection, owner='owner-a', before_message_id=10, selection={'mode':'auto'})
    messages = compound.model_messages([{'role':'system','content':'服务器规则'}, {'role':'assistant','content':'旧的私有历史答案'}, {'role':'user','content':'原始复合问题'}], {'history_compound':pack})
    assert all('旧的私有历史答案' not in message['content'] for message in messages)
    assert messages[-1] == {'role':'user','content':pack['remainder_question']}


@pytest.mark.parametrize('data_state,complete', [('completed',True),('partial',False),('dependency_blocked',False),('answered_pending_review',None)])
def test_history_cannot_upgrade_failed_or_unreviewed_present_task(connection, data_state, complete):
    pack = compound.execute(request(), connection, owner='owner-a', before_message_id=10, selection={'mode':'auto'})
    answer, result = compound.compose('非历史答案', {'completion':{'terminal_state':data_state,'complete':complete}}, {'history_compound':pack})
    assert result['completion']['terminal_state'] == ('completed' if complete is True else 'partial')
    assert answer.startswith('在当前会话身份可访问的历史中')


def test_generated_compound_history_does_not_reenter_history(connection):
    pack = compound.execute(request(), connection, owner='owner-a', before_message_id=10, selection={'mode':'auto'})
    answer, _ = compound.compose('当前结果', {'completion':{'terminal_state':'completed','complete':True}}, {'history_compound':pack})
    connection.execute('INSERT INTO qa_messages VALUES(3,1,\'assistant\',?,\'2026-09-04\')', (answer,))
    next_pack = compound.execute(request(), connection, owner='owner-a', before_message_id=10, selection={'mode':'auto'})
    assert '本轮复合回答如下' not in next_pack['outcomes'][0]['answer']


def test_no_match_is_completed_query_not_a_fabricated_answer(connection):
    connection.execute('DELETE FROM qa_messages WHERE id < 10')
    pack = compound.execute(request(), connection, owner='owner-a', before_message_id=10, selection={'mode':'auto'})
    assert pack['outcomes'][0]['completion']['history_status'] == 'no_match'
    assert pack['outcomes'][0]['completion']['complete'] is True
    assert '未找到' in pack['outcomes'][0]['answer']


def test_query_exception_has_safe_failure_and_retains_data():
    class Broken:
        def execute(self, *args): raise RuntimeError('secret dsn raw error')
    pack = compound.execute(request(), Broken(), owner='owner-a', before_message_id=10, selection={'mode':'auto'})
    answer, result = compound.compose('当前成功事实', {'completion':{'terminal_state':'completed','complete':True}}, {'history_compound':pack})
    assert 'secret' not in answer and '当前成功事实' in answer
    assert result['completion']['missing_history_subtasks'] == ['history_query_failed']


def test_global_explicit_tool_prohibition_survives_source_split(connection):
    pack = dict(request(), tools_disabled=True)
    child = compound.execution_plan(pack['remainder_question'], pack)
    assert child['allow_prefetch'] is False and child['allow_mcp_tools'] is False
    assert compound.data_tool_selection({'mode':'auto'}, pack)['mode'] == 'none'
    history = compound.execute(pack, connection, owner='owner-a', before_message_id=10, selection={'mode':'auto'})
    assert history['outcomes'][0]['completion']['reason'] == 'history_tool_selection_blocked'


def test_inseparable_history_and_current_request_is_clarified_not_given_to_model():
    question = '根据历史问答分析现在炉顶压力是否正常'
    pack = compound.split_request(question, qa_task_plan.build_task_plan(question))
    assert pack['blocked'] == ['history_clause_scope_ambiguous']
    assert pack['history_questions'] == []
    assert '炉顶压力' not in pack['remainder_question']


def test_history_limits_preserve_data_without_silent_history_omission():
    question = '；'.join(['历史问答里关于炉顶压力的回答'] * 5 + ['查询现在炉顶压力的最新值是多少'])
    pack = compound.split_request(question, qa_task_plan.build_task_plan(question))
    assert pack['history_questions'] == [] and pack['blocked'] == ['history_subtask_limit']
    assert '最新值' in pack['remainder_question']
