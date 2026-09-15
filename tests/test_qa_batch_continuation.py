import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

SCRIPT=Path(__file__).resolve().parents[1]/'tools/prepare_qa_batch_continuation.py'
class ContinuationTests(unittest.TestCase):
    def run_case(self,recovery,group=False):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            cases=[{'case_id':'claimed','prompt':'一'},{'case_id':'new','prompt':'二'}]
            if group: cases[0]['conversation_group']='g'
            (root/'plan.json').write_text(json.dumps({'cases':cases}),encoding='utf-8')
            (root/'recovery.json').write_text(json.dumps(recovery),encoding='utf-8')
            result=subprocess.run([sys.executable,str(SCRIPT),'--plan',str(root/'plan.json'),
                '--claimed',str(root/'recovery.json'),'--output',str(root/'out.json')],capture_output=True,text=True)
            return result.returncode,json.loads((root/'out.json').read_text(encoding='utf-8')) if (root/'out.json').exists() else None
    def test_never_replays_claimed_row(self):
        code,result=self.run_case({'previous_processes_absent':True,'automatic_replay':False,'claimed_case_ids':['claimed']})
        self.assertEqual(code,0); self.assertEqual([c['case_id'] for c in result['cases']],['new'])
    def test_missing_recovery_is_blocked(self):
        code,result=self.run_case({'claimed_case_ids':['claimed']})
        self.assertNotEqual(code,0); self.assertIsNone(result)
    def test_multiturn_requires_recovered_conversation(self):
        code,result=self.run_case({'previous_processes_absent':True,'automatic_replay':False,'claimed_case_ids':['claimed']},True)
        self.assertNotEqual(code,0); self.assertIsNone(result)
if __name__=='__main__': unittest.main()
