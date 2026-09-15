import importlib.util
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
def module(name):
    spec=importlib.util.spec_from_file_location(name,ROOT/'tools'/(name+'.py'))
    m=importlib.util.module_from_spec(spec); spec.loader.exec_module(m); return m
inventory=module('import_qa_prompt_sources')
prepare=module('prepare_qa_template_batch')
batch=module('run_qa_template_batch')

class InventoryTests(unittest.TestCase):
    def test_reference_answers_never_enter_run_plan(self):
        row=dict(case_id='TPL-1',prompt='查顶压',prompt_mode='spoken',source_status='ready',
            reference_answer='SECRET_ORACLE',gold_contract={'answer':'SECRET_ORACLE'})
        p=prepare.build({'rows':[row]},b'collector',{'proxy':'sha'})
        self.assertNotIn('SECRET_ORACLE',str(p))
        self.assertEqual(p['cases'][0]['prompt'],'查顶压')
    def test_system_and_protocol_are_not_user_messages(self):
        for kind in ('system_template','code_block'):
            self.assertEqual(inventory.disposition('查询实时数据',kind)[0],'contract_only')
    def test_placeholder_and_assistant_are_explicit_skips(self):
        self.assertEqual(inventory.disposition('查{点位}','user_prompt')[0],'skipped')
        self.assertEqual(inventory.disposition('助手：数值为0','user_prompt')[0],'skipped')
    def test_multiturn_is_not_collapsed_with_single_turn_duplicate(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp); (root/'PT').mkdir()
            (root/'PT/test.md').write_text('# 例子\n```text\n查顶压\n查顶压\n用户：查顶压\n用户：画出来\n```\n',encoding='utf-8')
            with patch.object(inventory,'DOCS',['PT/test.md']): _,rows=inventory.collect(root)
            self.assertEqual([r['source_status'] for r in rows],['ready','duplicate','ready','ready'])
            self.assertEqual(rows[-1]['turn_index'],1)
    def test_public_scrubber(self):
        result=inventory.sanitized('入口http://192.168.1.1:80 token=abc')
        self.assertNotIn('192.168',result); self.assertNotIn('abc',result)
        self.assertEqual(inventory.sanitized('请解释5.3.3.1条'),'请解释5.3.3.1条')
        self.assertNotIn('2#20260716-101',inventory.sanitized('查询2#20260716-101'))
    def test_batch_refuses_changed_runtime_before_request(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp); collector=root/'collector.py'; collector.write_text('pass',encoding='utf-8')
            with self.assertRaisesRegex(RuntimeError,'collector hash changed'):
                batch.verify({'collector_sha256':'wrong','runtime_hashes':{}},root,collector)
    def test_batch_health_requires_model_not_just_http(self):
        import io
        with patch.object(batch.urllib.request,'urlopen',return_value=io.BytesIO(b'{"ok":true,"proxy_ok":true,"ollama_ok":true,"model_ok":false}')):
            self.assertFalse(batch.model_ready())
    def test_fixture_and_duplicate_rows_are_not_sent(self):
        rows=[dict(case_id=str(i),prompt='x',source_status=status) for i,status in enumerate(('ready','duplicate','fixture_only','contract_only','skipped'))]
        self.assertEqual(len(prepare.build({'rows':rows},b'x',{})['cases']),1)

if __name__=='__main__': unittest.main()
