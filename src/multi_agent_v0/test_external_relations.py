"""Approval, comparison and isolation regressions; no model or network calls."""
import copy
import json
import tempfile
import unittest
from types import SimpleNamespace
from pathlib import Path

from core import project, solve, validate_projection
from contracts import SCHEMAS
from external_relations import ROOT, APPROVAL, SNAPSHOT, load_approved_libraries, compare_origin


class ExternalRelationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.bundle = load_approved_libraries()
        cls.origin = json.loads((ROOT/'artifacts/multi-agent-v0/milestone-007/facts.gpt-adjudicated.json').read_text(encoding='utf-8'))

    def test_only_approved_candidates_loaded(self):
        self.assertEqual({x['id'] for x in self.bundle['libraries']}, {'C01', 'C02'})

    def test_real_five_facts_static_match_and_inputs_unchanged(self):
        original = copy.deepcopy(self.origin)
        report = compare_origin(self.origin, self.bundle)
        self.assertEqual(len(report['facts']), 5)
        self.assertTrue(all(f['comparisons'][0]['status'] == 'static_compatible_hint' for f in report['facts']))
        self.assertEqual(self.origin, original)
        self.assertFalse(report['auto_accept'])
        self.assertTrue(all(not f['scope_and_time_verified'] for f in report['facts']))

    def test_c02_never_provides_positive_match_or_omission(self):
        report = compare_origin(self.origin, self.bundle)
        self.assertTrue(all(not c['matches'] for f in report['facts'] for c in f['comparisons'] if c['library']=='C02'))
        self.assertTrue(all(o['library']=='C01' for o in report['potential_omissions']))

    def test_son_does_not_verify_father_role(self):
        report = compare_origin(self.origin, self.bundle)
        matches = [r for f in report['facts'] for c in f['comparisons'] for r in c['matches'] if r['raw'][2] == 'son']
        self.assertTrue(matches)
        self.assertTrue(all(not r['role_verified'] for r in matches))

    def test_absence_is_not_rejection(self):
        origin = copy.deepcopy(self.origin)
        for e in origin['entities']:
            e['name'] = '不存在于库的'+e['id']; e['aliases']=[]
        report = compare_origin(origin, self.bundle)
        self.assertTrue(all(f['comparisons'][0]['status']=='not_covered' for f in report['facts']))
        self.assertFalse(report['auto_accept'])

    def test_temporal_and_counterfactual_not_compared(self):
        origin=copy.deepcopy(self.origin)
        origin['facts'][0]['event_id']='later-event'
        report=compare_origin(origin,self.bundle)
        self.assertTrue(all(c['status'].startswith('not_comparable') for c in report['facts'][0]['comparisons']))
        self.assertEqual(report['potential_omissions'],[])
        self.assertEqual(compare_origin(self.origin,self.bundle,track='counterfactual')['status'],'not_comparable_non_source_track')

    def test_alias_collision_cannot_merge_people(self):
        origin=copy.deepcopy(self.origin)
        origin['entities'].append({'id':'other','name':'另一个人','aliases':['贾蓉']})
        report=compare_origin(origin,self.bundle)
        f=next(f for f in report['facts'] if f['child']=='贾蓉')
        self.assertTrue(all(c['status'].startswith('not_comparable') for c in f['comparisons']))

    def test_known_faulty_c02_rows_are_flagged_and_excluded(self):
        origin={'entities':[{'id':n,'name':n,'aliases':[]} for n in ['贾珍','贾惜春']],
                'facts':[{'id':'fictional-negative-test','parent':'贾珍','child':'贾惜春','parent_role':'father','scope':'test'}]}
        report=compare_origin(origin,self.bundle)
        c=next(c for c in report['facts'][0]['comparisons'] if c['library']=='C02')
        self.assertIn(20,c['known_issue_rows'])
        self.assertEqual(c['matches'],[])
        self.assertTrue(report['known_library_issues'])
        self.assertTrue(all(r['excluded_from_comparison'] for r in report['known_library_issues']))

    def test_c02_different_father_is_only_a_hint(self):
        origin=copy.deepcopy(self.origin)
        f=next(f for f in origin['facts'] if f['child']=='JIA-RONG')
        f['parent']='JIA-JING'
        report=compare_origin(origin,self.bundle)
        item=next(x for x in report['facts'] if x['fact_id']==f['id'])
        c=next(c for c in item['comparisons'] if c['library']=='C02')
        self.assertEqual(c['status'],'conflict_hint')
        self.assertFalse(report['gold_modified'])

    def test_omission_hints_are_bounded_not_auto_facts(self):
        origin=copy.deepcopy(self.origin)
        origin['facts']=[f for f in origin['facts'] if f['id']!='F4']
        report=compare_origin(origin,self.bundle)
        hints=[h for h in report['potential_omissions'] if h['parent']=='贾珍' and h['child']=='贾蓉']
        self.assertTrue(hints)
        self.assertTrue(all(h['requires_local_source_evidence'] for h in hints))
        self.assertFalse(any(f['id']=='F4' for f in origin['facts']))

    def test_hints_do_not_enter_solver_or_rescue_deleted_evidence(self):
        family=json.loads((ROOT/'artifacts/multi-agent-v0/milestone-007/family.internal.json').read_text(encoding='utf-8'))
        row=next(v for v in family['variants'] if v['gold']['status']=='insufficient_evidence')
        row=copy.deepcopy(row)
        row['external_relation_hints']=compare_origin(self.origin,self.bundle)
        payload=project(row,family['question'],SCHEMAS['blind-solver'])
        validate_projection(payload)
        self.assertNotIn('external_relation_hints',payload)
        self.assertEqual(row['gold']['status'],'insufficient_evidence')
        self.assertEqual(solve(family['query'],[])['status'],'insufficient_evidence')

    def test_runner_passes_hints_only_to_source_reviewer(self):
        from runner import Pipeline
        calls=[]; saved={}
        def role(stage, role_name, payload):
            calls.append((role_name,copy.deepcopy(payload)))
            if role_name=='origin':return copy.deepcopy(self.origin)
            return {'verdict':'pass','checks':[{'name':'evidence_support','passed':True}],
                    'issues':[],'required_changes':[]}
        fake=SimpleNamespace(materials=[],external_libraries=self.bundle,role=role,
                             save=lambda name,data:saved.update({name:copy.deepcopy(data)}))
        facts,_,_=Pipeline.reviewed(fake,'origin','origin',{'materials':[]},lambda draft:{},['evidence_support'])
        self.assertNotIn('external_relation_hints',calls[0][1])
        self.assertIn('external_relation_hints',calls[1][1])
        self.assertEqual(calls[1][0],'supervisor')
        self.assertEqual(facts,self.origin)
        self.assertIn('external-relations/origin-0.frozen.json',saved)

    def test_approval_and_hash_guards_fail_closed(self):
        original=json.loads((ROOT/APPROVAL).read_text(encoding='utf-8'))
        for mutation in ('pending','solver','scope','extra','tamper'):
            workspace=(ROOT/'workspace/relation-library-audit').resolve()
            with self.subTest(mutation=mutation), tempfile.TemporaryDirectory(dir=workspace) as tmp:
                root=Path(tmp).resolve()
                self.assertTrue(root.is_relative_to(workspace))
                policy=copy.deepcopy(original)
                if mutation=='pending':policy['user_approval']='pending'
                if mutation=='solver':policy['solver_access_allowed']=True
                if mutation=='scope':policy['candidates'][0]['approved_scope']='unlimited'
                if mutation=='extra':policy['candidates'][2]['enabled']=True
                path=root/APPROVAL;path.parent.mkdir(parents=True);path.write_text(json.dumps(policy),encoding='utf-8')
                for candidate in policy['candidates'][:2]:
                    source=ROOT/SNAPSHOT/candidate['approved_file'];target=root/SNAPSHOT/candidate['approved_file']
                    target.parent.mkdir(parents=True,exist_ok=True)
                    target.write_bytes(source.read_bytes()+(b'changed' if mutation=='tamper' else b''))
                with self.assertRaises(ValueError):load_approved_libraries(root)


if __name__=='__main__':unittest.main()
