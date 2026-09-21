import importlib.util
import sys
from pathlib import Path
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tools'))
from prepare_qa_batch_resume_review import build,mode_for,PROVEN_UNSENT
from import_qa_prompt_sources import disposition

class ResumeReviewTests(unittest.TestCase):
    def inputs(self):
        cases=[dict(case_id=c,prompt='查PI',prompt_mode='spoken') for c in ('done','unknown',PROVEN_UNSENT,'new')]
        inv={'rows':[dict(c,kind='user_prompt',source_path='test',source_line=1) for c in cases]}
        claims=[dict(case_id='done',state='completed',conversation_id='conv'),
                dict(case_id='unknown',state='unknown'),
                dict(case_id=PROVEN_UNSENT,state='unknown',error_tail='line 74, in run\noracle_invalid: internal catalog ID in prompt')]
        recovery={'batches':[dict(alive=False,claims=claims)],'collectors':[],'object_ids':['PI','L','TFT'],'catalog_sha256':'catalog'}
        return {'cases':cases},inv,recovery
    def test_full_catalog_ununderscored_ids(self):
        for value in ('PI','L','TFT','P_top'):
            self.assertEqual(mode_for('查询 '+value,['PI','L','TFT','P_top']),'structured')
        self.assertEqual(mode_for('顶温 A 点',['PI','L','TFT']),'spoken')
        self.assertEqual(mode_for('PLEASE',['L']),'spoken')
    def test_completed_and_unknown_never_replayed(self):
        plan,inv,recovery=self.inputs()
        out,audit=build(plan,inv,recovery)
        self.assertEqual([x['case_id'] for x in out['cases']],[PROVEN_UNSENT,'new'])
        self.assertEqual(audit['counts'],{'retain_prior_result':2,'execute':2})
    def test_unsent_claim_requires_exact_proof(self):
        plan,inv,recovery=self.inputs()
        recovery['batches'][0]['claims'][-1]['error_tail']='timeout'
        out,_=build(plan,inv,recovery)
        self.assertEqual([x['case_id'] for x in out['cases']],['new'])
    def test_active_process_blocks_resume(self):
        plan,inv,recovery=self.inputs();recovery['collectors']=[{'pid':1}]
        with self.assertRaises(ValueError):build(plan,inv,recovery)
    def test_partial_group_keeps_conversation(self):
        plan,inv,recovery=self.inputs()
        plan['cases'][0].update(conversation_group='g',turn_index=0)
        plan['cases'][-1].update(conversation_group='g',turn_index=1)
        out,_=build(plan,inv,recovery)
        self.assertEqual(out['initial_conversations'],{'g':'conv'})
    def test_unknown_group_blocks_dependent_only(self):
        plan,inv,recovery=self.inputs()
        plan['cases'][1].update(conversation_group='g',turn_index=0)
        plan['cases'][-1].update(conversation_group='g',turn_index=1)
        out,audit=build(plan,inv,recovery)
        self.assertEqual([x['case_id'] for x in out['cases']],[PROVEN_UNSENT])
        self.assertEqual(audit['counts']['blocked_dependency'],1)
    def test_structure_and_paths_not_questions(self):
        for text in ('→ 当前问题','用户口语问题','F:/程序/backend.py','F:\\程序\\backend.py'):
            self.assertEqual(disposition(text,'user_prompt')[0],'contract_only')
        self.assertEqual(disposition('请给我解释当前问题','user_prompt')[0],'ready')
if __name__=='__main__':unittest.main()

