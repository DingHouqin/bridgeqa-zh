"""Independent projection acceptance; [contract](../specs/09_第二版数据集发布.md)."""
import hashlib
import json
import sys
import unittest
from collections import Counter
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from site_data import PROJECT, load_bundle

DATA = PROJECT / 'data/multi_agent_hongloumeng_v2'

def lines(name):
    return [json.loads(x) for x in (DATA/name).read_text(encoding='utf-8').splitlines() if x.strip()]

class DatasetV2Test(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.bundle = load_bundle('multi_agent_hongloumeng_v2')
        cls.families = json.loads((DATA/'families.frozen.json').read_text(encoding='utf-8'))
        cls.rows = cls.bundle['records']

    def test_scope_and_review_are_explicit(self):
        self.assertEqual(len(self.rows),57)
        self.assertEqual(len({r['id'] for r in self.rows}),57)
        self.assertEqual(len({r['family_id'] for r in self.rows}),10)
        self.assertEqual(Counter(r['gold']['status'] for r in self.rows),{'answerable':40,'insufficient':17})
        self.assertEqual(Counter(r['variant'] for r in self.rows),{'base':10,'main_distractor':10,'irrelevant_addition':10,'necessary_support_deleted_name_retained':10,'irrelevant_deleted':10,'name_absent_deleted':7})
        self.assertEqual(self.bundle['summary']['oracle_tasks'],0)
        self.assertFalse(self.bundle['publication']['formal_release'])
        for r in self.rows:
            self.assertEqual(r['review']['status'],'requires_strong_review')
            self.assertFalse(r['review']['independent_human_review'])
            self.assertTrue(r['review']['model_run'])

    def test_every_question_context_answer_and_proof_matches_frozen_family(self):
        families = {f['family_id']:f for f in self.families}
        for row in self.rows:
            f = families[row['family_id']]
            v = f['variants'][row['source_member']['variant_index']]
            self.assertEqual(row['input']['question'],f['question'])
            self.assertEqual([d['text'] for d in row['input']['documents']],[m['text'] for m in v['materials']])
            self.assertEqual(row['gold']['answers'],v['gold']['answer_ids'])
            self.assertEqual([x['fact_id'] for x in row['facts']],v['active_fact_ids'])
            self.assertEqual(row['source_member']['deletion_log'],v['deletion_log'])
            self.assertEqual(row['review']['formal_release'],f['formal_release'])
            self.assertEqual(len(row['gold']['proofs']),len(v['gold']['proofs']))
            for actual, expected in zip(row['gold']['proofs'],v['gold']['proofs']):
                self.assertEqual([n['expected_value'] for n in actual],expected['entities'][1:])
                self.assertEqual([n['support_fact_ids'][0] for n in actual],expected['facts'])
                self.assertEqual([n['upstream'] for n in actual],expected['entities'][:-1])
            if v['gold']['status']=='insufficient_evidence':self.assertEqual(row['gold']['proofs'],[])

    def test_clean_input_has_no_labels_or_answers_and_diagnostics_are_separate(self):
        inputs = lines('inputs.jsonl')
        self.assertEqual(len(inputs),57)
        byid = {r['id']:r for r in self.rows}
        for payload in inputs:
            self.assertEqual(set(payload),{'id','question','contexts','output_contract'})
            row = byid[payload['id']]
            self.assertEqual(payload['question'],row['input']['question'])
            self.assertEqual(payload['contexts'],[{'context_id':d['id'],'text':d['text']} for d in row['input']['documents']])
            for c in payload['contexts']:self.assertEqual(set(c),{'context_id','text'})
        diagnostic = lines('no_material_inputs.jsonl')
        self.assertEqual(len(diagnostic),10)
        self.assertTrue(all(d['contexts']==[] for d in diagnostic))
        self.assertTrue({d['id'] for d in diagnostic}.isdisjoint(byid))

    def test_model_observations_are_bound_to_member_and_actual_quotes(self):
        success = old_strict = discrepancy = 0
        for row in self.rows:
            a = row['model_observation']
            self.assertEqual(a['job'],{'family_id':row['family_id'],'variant_index':row['source_member']['variant_index']})
            self.assertEqual(a['condition'],row['variant'])
            text = {d['id']:d['text'] for d in row['input']['documents']}
            for step in a['observed_steps']:
                for e in step['evidence']:
                    self.assertIn(e['context_id'],text)
                    if a['all_quotes_located']:self.assertIn(e['quote'],text[e['context_id']])
            success += a['semantic_task_success']
            old_strict += a['machine_checks_unchanged']['strict_structural_success']
            discrepancy += a['semantic_task_success'] and not a['machine_checks_unchanged']['strict_structural_success']
        self.assertEqual((success,old_strict,discrepancy),(46,24,22))
        audit = json.loads((DATA/'blind-audit.json').read_text(encoding='utf-8'))
        self.assertEqual(len(audit),67)
        diagnostic = [a for a in audit if a['condition']=='no_material_diagnostic']
        self.assertEqual(len(diagnostic),10)
        self.assertTrue(all(a['semantic_task_success'] for a in diagnostic))

    def test_snapshot_hash_and_pairing(self):
        p=self.bundle['publication']
        self.assertEqual(hashlib.sha256((DATA/'families.frozen.json').read_bytes()).hexdigest(),p['frozen_family_sha256'])
        ids={r['id'] for r in self.rows}
        for row in self.rows:
            self.assertIn(row['control_id'],ids)
            self.assertIn(row['challenge_id'],ids)
            if row['paired_changes']:self.assertIn(row['paired_changes']['parent_id'],ids)

if __name__=='__main__':unittest.main()
