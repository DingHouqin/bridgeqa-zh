"""Offline experiment isolation, sealing, resume and denominator regressions."""
import copy
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from experiment import ROOT, HarnessCaller, SCHEMAS, make_jobs, run_reviews, summarize
from review_cases import digest, freeze_batch, project_review, verify_reference_gate


def case():
    return {'case_id':'case1','family_id':'family1','track':'source','rationale':'generator claims correct',
            'external_relation_hints':{'facts':[{'x':'hint'}]},
            'reference':{'secret':'DO_NOT_SEND'},
            'candidate':{'question':'谁？','query':{'start':'乙'},'origin':{'entities':[],'facts':[],'warnings':['hidden rationale']},
                         'validation_status':'passed','reference_review':'approved',
                         'variants':[{'condition':'base','materials':[{'unit_id':'u','text':'甲是乙的父亲。','source_path':'hidden'}],
                                      'gold':{'status':'answerable','answer_ids':['甲'],'proofs':[],'world_semantics':'program'},
                                      'requires_text_review':True}]}}


def answer(verdict='pass'):
    return {'verdict':verdict,'checks':[{'name':n,'passed':True,'evidence':'原文'} for n in ['source_support','query_alignment','proof_validity','deletion_validity','family_invariants']],
            'issues':[],'required_changes':[]}


class ExperimentTests(unittest.TestCase):
    def setUp(self):
        parent=ROOT/'workspace/deletion-review-v2'
        parent.mkdir(parents=True,exist_ok=True)
        self.tmp=tempfile.TemporaryDirectory(dir=parent)
        self.path=Path(self.tmp.name).resolve()
        self.assertTrue(self.path.is_relative_to(parent.resolve()))
    def tearDown(self):self.tmp.cleanup()

    def test_projection_differences_and_hidden_fields(self):
        original=case(); before=copy.deepcopy(original)
        a,b,c=[project_review(original,x) for x in 'ABC']
        self.assertNotIn('generator_explanation',a)
        self.assertNotIn('external_relation_hints',b)
        self.assertEqual({k:v for k,v in b.items() if k!='generator_explanation'},a)
        self.assertEqual({k:v for k,v in c.items() if k not in ('external_relation_hints','external_hint_policy')},b)
        encoded=json.dumps(c)
        for hidden in ['DO_NOT_SEND','source_path','validation_status','reference_review','world_semantics','warnings']:
            self.assertNotIn(hidden,encoded)
        self.assertEqual(before,original)

    def test_synthetic_has_no_external_facts(self):
        c=case();c['track']='synthetic'
        self.assertEqual(project_review(c,'C')['external_relation_hints']['facts'],[])

    def test_freeze_and_gate_detect_change(self):
        cases=[case()];refs={'case1':{'expected_verdict':'pass','status':'gpt_reviewed'}}
        m=freeze_batch(cases,refs,self.path)
        with self.assertRaises(ValueError):verify_reference_gate(self.path,{'status':'pending'})
        review={'status':'approved','reviewer_kind':'independent_gpt_subagent',**{k:m[k] for k in ('cases_sha256','references_sha256')}}
        self.assertEqual(verify_reference_gate(self.path,review)[0],cases)
        changed=copy.deepcopy(cases);changed[0]['rationale']='changed'
        with self.assertRaises(ValueError):freeze_batch(changed,refs,self.path)

    def test_job_seed_and_432_count(self):
        cases=[{**case(),'case_id':'case'+str(i)} for i in range(48)]
        jobs=make_jobs(cases)
        self.assertEqual(len(jobs),432)
        self.assertEqual(jobs,make_jobs(cases))
        self.assertEqual(len({digest(j) for j in jobs}),432)

    def test_caller_retries_new_sessions_then_cache(self):
        calls=[]
        def transport(req,sid):
            calls.append(sid)
            return SimpleNamespace(session_id=sid,finish_reason='completed',final_response='invalid' if len(calls)==1 else json.dumps(answer()),events=[],notifications=[])
        with HarnessCaller('',self.path,transport=transport) as caller:
            x=caller.call('stage','supervisor',{},SCHEMAS['supervisor'],'prompt')
            self.assertEqual(x['verdict'],'pass')
            caller.call('stage','supervisor',{},SCHEMAS['supervisor'],'prompt')
            self.assertEqual(len(calls),2)
            self.assertNotEqual(calls[0],calls[1])
            with self.assertRaises(ValueError):caller.call('stage','supervisor',{'changed':True},SCHEMAS['supervisor'],'prompt')
            with self.assertRaises(ValueError):caller.call('/escape','supervisor',{},SCHEMAS['supervisor'],'prompt')

    def test_protocol_failures_not_reject(self):
        def transport(req,sid):return SimpleNamespace(session_id=sid,finish_reason='completed',final_response='invalid',events=[],notifications=[])
        with HarnessCaller('',self.path,transport=transport) as caller:
            with self.assertRaisesRegex(ValueError,'Protocol failure'):caller.call('bad','supervisor',{},SCHEMAS['supervisor'],'prompt')
        self.assertEqual(len(list((self.path/'calls').glob('*.request.json'))),3)

    def test_review_resume_no_additional_calls(self):
        calls=[]
        class Fake:
            def __init__(self,*args,**kwargs):pass
            def call(self,name,*args):calls.append(name);return answer()
            def close(self):pass
        cases=[case()];review={'status':'approved','reviewer_kind':'independent_gpt_subagent','cases_sha256':digest(cases)}
        rows=run_reviews(cases,self.path,'',workers=2,reference_review=review,caller_factory=Fake)
        self.assertEqual(len(rows),9)
        run_reviews(cases,self.path,'',workers=2,reference_review=review,caller_factory=Fake)
        self.assertEqual(len(calls),9)

    def test_denominators_include_missing_and_failure(self):
        cases=[case()];refs={'case1':{'expected_verdict':'pass','status':'gpt_reviewed'}}
        jobs=make_jobs(cases)
        rows=[{'job':jobs[0],'status':'technical_failure'}]
        result=summarize(cases,refs,rows)
        self.assertEqual(sum(m['scheduled'] for m in result['metrics'].values()),9)
        self.assertEqual(sum(m.get('not_run',0) for m in result['metrics'].values()),8)
        self.assertEqual(sum(m['valid_trials'] for m in result['metrics'].values()),9)

    def test_paired_error_changes(self):
        cases=[case()];refs={'case1':{'expected_verdict':'pass','status':'gpt_reviewed'}}
        rows=[{'job':j,'status':'completed','answer':answer('revise' if j['condition']=='A' else 'pass')} for j in make_jobs(cases)]
        s=summarize(cases,refs,rows)
        self.assertEqual(sum(x['correction'] for x in s['paired_changes']),3)
        self.assertTrue(all(x['all_three_same'] for x in s['stability']))

    def test_inconsistent_pass_is_protocol_failure(self):
        class Fake:
            def __init__(self,*args,**kwargs):pass
            def call(self,*args):
                result=answer();result['checks'][0]['passed']=False;return result
            def close(self):pass
        cases=[case()];review={'status':'approved','reviewer_kind':'independent_gpt_subagent','cases_sha256':digest(cases)}
        rows=run_reviews(cases,self.path,'',workers=1,reference_review=review,caller_factory=Fake)
        self.assertTrue(all(r['status']=='protocol_failure' for r in rows))

    def test_minor_errors_not_counted_as_major_unsafe_accept(self):
        cases=[case()];refs={'case1':{'expected_verdict':'revise','major_defect':False,'status':'gpt_reviewed'}}
        rows=[{'job':j,'status':'completed','answer':answer()} for j in make_jobs(cases)]
        result=summarize(cases,refs,rows)
        self.assertEqual(sum(m.get('unsafe_accept',0) for m in result['metrics'].values()),0)
        self.assertEqual(sum(m['incorrect_minor_disposition'] for m in result['metrics'].values()),9)

    def test_undecided_references_are_excluded_and_reported(self):
        result=summarize([case()],{'case1':{'expected_verdict':'pass','status':'disputed'}},[])
        self.assertEqual(sum(m['unadjudicated'] for m in result['metrics'].values()),9)
        self.assertTrue(all(r['unsafe_accept']['denominator']==0 for r in result['rates'].values()))


if __name__=='__main__':unittest.main()
