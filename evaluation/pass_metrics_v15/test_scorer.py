"""Independent subset/completion oracles and evidence-contract counterexamples."""
import copy,importlib.util,itertools,json,subprocess,sys,tempfile,unittest
from fractions import Fraction
from pathlib import Path
from scorer import (ContractError,aggregate,average_metrics,canonical,digest,estimate,
                    family_average,file_sha,metric,read_ref,task_metrics,validate_plan)

def frac(item):return None if item is None else Fraction(item['numerator'],item['denominator'])

def subset_oracle(values,k,kind):
    subsets=list(itertools.combinations(values,k))
    if not subsets:return None
    function=all if kind=='all' else any
    return Fraction(sum(function(s) for s in subsets),len(subsets))

class ArithmeticTests(unittest.TestCase):
    def test_all_counts_against_explicit_subsets(self):
        for n in range(1,13):
            for c in range(n+1):
                for k in [1,5]:
                    for kind in ['any','all']:
                        with self.subTest(n=n,c=c,k=k,kind=kind):
                            self.assertEqual(estimate(n,c,k,kind),subset_oracle([True]*c+[False]*(n-c),k,kind))

    def test_all_five_slot_ternary_patterns_against_every_completion(self):
        for values in itertools.product(['pass','fail','needs_review'],repeat=5):
            indexes=[i for i,v in enumerate(values) if v=='needs_review']
            for kind in ['any','all']:
                possible=[]
                for bits in itertools.product([False,True],repeat=len(indexes)):
                    complete=[v=='pass' for v in values]
                    for i,bit in zip(indexes,bits):complete[i]=bit
                    possible.append(subset_oracle(complete,5,kind))
                result=metric(values,5,kind)
                self.assertEqual(frac(result['identification_bounds']['lower']),min(possible))
                self.assertEqual(frac(result['identification_bounds']['upper']),max(possible))
                self.assertEqual(result['point_estimate'] is None,bool(indexes))

    def test_general_unknown_bounds_n6_to10(self):
        for n in range(6,11):
            for c in range(n+1):
                for u in range(n-c+1):
                    outcomes=['pass']*c+['fail']*(n-c-u)+['needs_review']*u
                    for kind in ['any','all']:
                        possible=[subset_oracle([True]*c+[False]*(n-c-u)+list(bits),5,kind) for bits in itertools.product([False,True],repeat=u)]
                        result=metric(outcomes,5,kind)['identification_bounds']
                        self.assertEqual(frac(result['lower']),min(possible));self.assertEqual(frac(result['upper']),max(possible))

    def test_four_of_five_is_not_point8_to_power5(self):
        values=['pass']*4+['fail'];r=task_metrics(values)
        self.assertEqual(frac(r['pass@1']['point_estimate']),Fraction(4,5))
        self.assertEqual(frac(r['pass@5']['point_estimate']),1)
        self.assertEqual(frac(r['pass^5']['point_estimate']),0)

    def test_n10_requires_both_combinatorial_estimators(self):
        self.assertEqual(estimate(10,5,5,'all'),Fraction(1,252))
        self.assertEqual(estimate(10,5,5,'any'),Fraction(251,252))

    def test_less_than_five_not_extrapolated(self):
        for n in [1,2,3,4]:
            r=task_metrics(['pass']*n)
            self.assertEqual(frac(r['pass@1']['point_estimate']),1)
            for name in ['pass@5','pass^5']:
                self.assertIsNone(r[name]['point_estimate']);self.assertIsNone(r[name]['identification_bounds'])

    def test_one_success_four_missing_not_reported_as_measured_pass5(self):
        r=metric(['pass']+['needs_review']*4,5,'any')
        self.assertEqual(frac(r['identification_bounds']['lower']),1)
        self.assertEqual(frac(r['identification_bounds']['upper']),1)
        self.assertIsNone(r['point_estimate']);self.assertEqual(r['status'],'pending_outcomes')

    def test_question_macro_not_pooling_responses(self):
        rows=[{'family_id':'A','metrics':task_metrics(['pass']*5)},{'family_id':'B','metrics':task_metrics(['fail']*10)}]
        self.assertEqual(frac(average_metrics(rows)['pass@1']['point_estimate']),Fraction(1,2))

    def test_family_macro_does_not_overweight_more_variants(self):
        rows=[{'family_id':'A','metrics':task_metrics(['pass']*5)} for _ in range(3)]+[{'family_id':'B','metrics':task_metrics(['fail']*5)}]
        self.assertEqual(frac(average_metrics(rows)['pass@1']['point_estimate']),Fraction(3,4))
        self.assertEqual(frac(family_average(rows)['family_macro']['pass@1']['point_estimate']),Fraction(1,2))

    def test_incomplete_task_never_disappears_from_official_denominator(self):
        rows=[{'family_id':'A','metrics':task_metrics(['pass']*5)},{'family_id':'B','metrics':task_metrics(['needs_review']*5)}]
        r=average_metrics(rows)['pass@1']
        self.assertIsNone(r['point_estimate']);self.assertEqual(r['eligible_questions'],2)
        self.assertEqual(r['complete_case_supplement']['denominator'],1)
        self.assertEqual(frac(r['identification_bounds']['lower']),Fraction(1,2))

    def test_invalid_integer_arguments_and_unknown_labels(self):
        for args in [(True,0,1,'any'),(5,6,5,'all'),(5,-1,5,'any'),(5,1,0,'all'),(5,1,1,'unknown')]:
            with self.assertRaises(ContractError):estimate(*args)
        with self.assertRaises(ContractError):metric(['unknown'],1,'any')

class BoundFixture:
    def __init__(self,root,n=5,successes=4):
        self.root=Path(root);self.n=n;self.records=[]
        self.payload={'id':'Qunit','question':'Synthetic known target1','contexts':[]}
        self.gold={'status':'answerable','answers':[1]}
        self.request={'input':self.payload,'role':'blind-solver','skill':'same frozen prompt','output_schema':{'type':'object','required':['status','answers']},
          'model':'synthetic-offline-model','runtime_contract':{'transport':'offline_test','temperature':0.7,'max_tokens':1000}}
        contract={k:v for k,v in self.request.items() if k!='input'}
        self.qual={'records':[{'id':'case','family_id':'family','partition':'primary','input_sha256':digest(self.payload),'gold_sha256':digest(self.gold),'gold_status':'accepted','hop_claim_status':'local_dependency_only','declared_hops':3}]}
        self.write('qualification.json',self.qual)
        request_bytes=(json.dumps(self.request,ensure_ascii=False,indent=2)+'\n').encode('utf-8')
        import hashlib
        planned_request_sha=hashlib.sha256(request_bytes).hexdigest()
        slots=[{'trial_id':f'trial{i}','ordinal':i,'request_path':f't{i}/Qunit.attempt-0.request.json','response_path':f't{i}/Qunit.attempt-0.response.json','request_sha256':planned_request_sha} for i in range(n)]
        self.plan={'version':'bridgeqa-pass-plan-v15','configuration':{'model':'synthetic-offline-model','temperature':0.7,'runtime_contract':copy.deepcopy(self.request['runtime_contract'])},
          'rubric':{'trusted_reviewers':['independent','root'],'approver':'root',
            'criteria':{'answer':'Entire synthetic target/status correct','logical_proof':'Sufficient truthful derivation, all valid alternatives allowed','output_contract':'Correct target/proof and required raw output schema'},
            'alternative_valid_proofs':'accept_without_matching_reference_path','uncertainty_policy':'needs_review'},'input_qualification':self.ref('qualification.json'),
          'sampling':{'unit':'single_first_completion','selection':'all_predeclared_slots','format_repairs':0,'iid_assumption':True,'independence_limit':'Synthetic fixture, not a model run'},
          'cases':[{'id':'case','family_id':'family','partition':'primary','input_sha256':digest(self.payload),'gold_sha256':digest(self.gold),'request_contract_sha256':digest(contract),'slots':slots}]}
        self.plan['configuration_sha256']=digest(self.plan['configuration']);self.plan['rubric_sha256']=digest(self.plan['rubric'])
        self.write('plan.json',self.plan);self.plan_sha=file_sha(self.root/'plan.json')
        for i,slot in enumerate(slots):
            self.write(slot['request_path'],self.request)
            answer=1 if i<successes else 0
            response={'request_hash':digest(self.request),'selected_model':'synthetic-offline-model','finish_reason':'completed','session_id':f'session{i}',
              'final_response':canonical({'status':'answerable','answers':[answer]})}
            self.write(slot['response_path'],response)
            verdict='pass' if i<successes else 'fail'
            review={'trial_id':slot['trial_id'],'case_id':'case','input_sha256':digest(self.payload),'gold_sha256':digest(self.gold),
              'configuration_sha256':self.plan['configuration_sha256'],'rubric_sha256':self.plan['rubric_sha256'],'plan_sha256':self.plan_sha,
              'response_sha256':self.ref(slot['response_path'])['sha256'],'status':'accepted','reviewers':['independent','root'],'approved_by':'root','independent_review':True,
              'rationale':'Offline synthetic known ground truth; no real model or semantic-review success claim','verdicts':{d:verdict for d in ['answer','logical_proof','output_contract']}}
            self.write(f'review{i}.json',review)
            self.records.append({'trial_id':slot['trial_id'],'case_id':'case','input_sha256':digest(self.payload),'configuration_sha256':self.plan['configuration_sha256'],
              'rubric_sha256':self.plan['rubric_sha256'],'plan_sha256':self.plan_sha,'status':'completed','initial_attempt':True,'attempt_ordinal':0,
              'request':self.ref(slot['request_path']),'response':self.ref(slot['response_path']),'adjudication':self.ref(f'review{i}.json')})

    def write(self,name,value):
        p=self.root/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n',encoding='utf-8',newline='\n')
    def ref(self,name):return {'path':name,'sha256':file_sha(self.root/name)}
    def replace(self,record_index,field,mutator):
        ref=self.records[record_index][field];value=json.loads((self.root/ref['path']).read_text(encoding='utf-8'));mutator(value);self.write(ref['path'],value);self.records[record_index][field]=self.ref(ref['path'])
    def sampling_review(self,decision='protocol_qualified_under_iid_assumption'):
        self.write('scored-records.json',self.records)
        self.write('sampling-evidence.json',{'scope':'Offline synthetic fixture; conditional iid is stipulated only for arithmetic and gate tests.'})
        qualification={'version':'bridgeqa-sampling-qualification-v15','status':'accepted','decision':decision,
          'plan':self.ref('plan.json'),'configuration_sha256':self.plan['configuration_sha256'],'records':self.ref('scored-records.json'),
          'evidence':[self.ref('sampling-evidence.json')],'reviewers':['independent','root'],'approved_by':'root','independent_review':True,
          'rationale':'Synthetic offline independent protocol review; not a claim about a real provider.',
          'independence_scope':'conditional_iid_assumption_not_proven','provider_independence_proven':False}
        self.write('sampling-review.json',qualification);return self.ref('sampling-review.json')
    def run(self,sampling=True):
        qualification=self.sampling_review() if sampling else None
        return aggregate(self.plan,self.records,root=self.root,plan_sha=self.plan_sha,sampling_qualification=qualification)

class BindingTests(unittest.TestCase):
    def setUp(self):
        base=(Path(__file__).resolve().parents[2]/'workspace/hop-audit-v15/test-temp').resolve();base.mkdir(parents=True,exist_ok=True)
        self.temp=tempfile.TemporaryDirectory(dir=base)
        if not Path(self.temp.name).resolve().is_relative_to(base):raise AssertionError('Unsafe temporary cleanup target')
        self.addCleanup(self.temp.cleanup);self.fx=BoundFixture(self.temp.name)
    def test_complete_fixture_and_separate_dimensions(self):
        result=self.fx.run();s=result['summary']['primary']['answer']['question_macro']
        self.assertEqual(frac(s['pass@1']['point_estimate']),Fraction(4,5));self.assertEqual(frac(s['pass^5']['point_estimate']),0)
        self.assertEqual(result['summary']['primary']['answer']['certified_hop_subgroups']['3']['pass@1']['eligible_questions'],0)

    def test_missing_record_is_an_unknown_prescheduled_slot(self):
        self.fx.records=self.fx.records[:1];r=self.fx.run();row=r['rows'][0]
        self.assertEqual(row['missing_slots'],4);self.assertIsNone(row['metrics']['pass@5']['point_estimate'])

    def test_no_review_no_success(self):
        for r in self.fx.records:r.pop('adjudication')
        row=self.fx.run()['rows'][0];self.assertEqual(row['trial_verdicts'],['needs_review']*5)

    def test_same_text_fresh_sessions_is_not_deduplicated(self):
        self.fx=BoundFixture(self.temp.name,successes=5)
        self.assertEqual(frac(self.fx.run()['rows'][0]['metrics']['pass^5']['point_estimate']),1)

    def test_duplicate_trial_and_unplanned_record_rejected(self):
        self.fx.records.append(copy.deepcopy(self.fx.records[0]))
        with self.assertRaises(ContractError):self.fx.run()
        self.fx.records[-1]['trial_id']='unplanned'
        with self.assertRaises(ContractError):self.fx.run()

    def test_raw_changed_after_review_rejected(self):
        self.fx.replace(0,'response',lambda r:r.update(final_response='different answer'))
        with self.assertRaises(ContractError):self.fx.run()

    def test_reused_session_rejected_even_with_distinct_raw(self):
        self.fx.replace(1,'response',lambda r:r.update(session_id='session0'))
        newsha=self.fx.records[1]['response']['sha256'];self.fx.replace(1,'adjudication',lambda r:r.update(response_sha256=newsha))
        with self.assertRaises(ContractError):self.fx.run()

    def test_mixed_config_or_rubric_rejected(self):
        self.fx.records[1]['configuration_sha256']='0'*64
        with self.assertRaises(ContractError):self.fx.run()

    def test_selected_format_repair_is_not_a_fresh_sample(self):
        self.fx.replace(0,'request',lambda r:r.update(format_repair='fix JSON'))
        with self.assertRaises(ContractError):self.fx.run()

    def test_later_raw_substitution_is_rejected(self):
        self.fx.records[0]['response']['path']='t0/Qunit.attempt-1.response.json'
        with self.assertRaises(ContractError):self.fx.run()

    def test_wrong_question_input_rejected(self):
        self.fx.replace(0,'request',lambda r:r['input'].update(question='new material'))
        with self.assertRaises(ContractError):self.fx.run()

    def test_single_self_judge_does_not_authorize_pass(self):
        self.fx.replace(0,'adjudication',lambda r:r.update(reviewers=['root']))
        with self.assertRaises(ContractError):self.fx.run()

    def test_inconsistent_proof_success_rejected(self):
        self.fx.replace(0,'adjudication',lambda r:r['verdicts'].update(answer='fail',logical_proof='pass'))
        with self.assertRaises(ContractError):self.fx.run()

    def test_invalid_gold_not_a_model_failure(self):
        self.fx.qual['records'][0]['gold_status']='requires_review';self.fx.write('qualification.json',self.fx.qual)
        self.fx.plan['input_qualification']=self.fx.ref('qualification.json');self.fx.write('plan.json',self.fx.plan);self.fx.plan_sha=file_sha(self.fx.root/'plan.json')
        for i,r in enumerate(self.fx.records):
            r['plan_sha256']=self.fx.plan_sha;self.fx.replace(i,'adjudication',lambda a:a.update(plan_sha256=self.fx.plan_sha))
        result=self.fx.run();row=result['rows'][0];self.assertFalse(row['eligible']);self.assertTrue(all(v=='needs_review' for v in row['trial_verdicts']))
        self.assertIsNone(row['metrics']['pass@1']['point_estimate'])
        self.assertEqual(result['summary']['primary']['answer']['eligible_gold_questions'],0)

    def test_pending_review_never_passes(self):
        self.fx.replace(0,'adjudication',lambda r:r.update(status='pending'))
        self.assertEqual(self.fx.run()['rows'][0]['trial_verdicts'][0],'needs_review')

    def test_path_escape_and_bool_counts_rejected(self):
        with self.assertRaises(ContractError):read_ref({'path':'../outside.json','sha256':'0'*64},self.fx.root)
        self.fx.plan['sampling']['format_repairs']=False
        with self.assertRaises(ContractError):validate_plan(self.fx.plan)

    def test_no_confidence_interval_claim(self):
        self.assertFalse(self.fx.run()['rows'][0]['metrics']['pass@1']['bounds_are_confidence_intervals'])

class SamplingQualificationTests(unittest.TestCase):
    def setUp(self):
        base=(Path(__file__).resolve().parents[2]/'workspace/hop-audit-v15/test-temp').resolve();base.mkdir(parents=True,exist_ok=True)
        self.temp=tempfile.TemporaryDirectory(dir=base)
        if not Path(self.temp.name).resolve().is_relative_to(base):raise AssertionError('Unsafe temporary cleanup target')
        self.addCleanup(self.temp.cleanup);self.fx=BoundFixture(self.temp.name)

    def approved(self,decision='protocol_qualified_under_iid_assumption',mutator=None):
        reference=self.fx.sampling_review(decision)
        if mutator:
            value=json.loads((self.fx.root/reference['path']).read_text(encoding='utf-8'));mutator(value)
            self.fx.write(reference['path'],value);reference=self.fx.ref(reference['path'])
        return reference

    def score(self,reference):
        return aggregate(self.fx.plan,self.fx.records,root=self.fx.root,plan_sha=self.fx.plan_sha,sampling_qualification=reference)

    def assert_no_official_points(self,value):
        if isinstance(value,list):
            for child in value:self.assert_no_official_points(child)
        elif isinstance(value,dict):
            if 'point_estimate' in value:
                self.assertIsNone(value['point_estimate']);self.assertIsNone(value['identification_bounds'])
            if 'complete_case_supplement' in value:self.assertIsNone(value['complete_case_supplement']['estimate'])
            if 'first_attempt_accuracy' in value:self.assertIsNone(value['first_attempt_accuracy'])
            for child in value.values():self.assert_no_official_points(child)

    def test_default_missing_qualification_blocks_every_official_location(self):
        result=self.score(None);self.assert_no_official_points(result['rows']);self.assert_no_official_points(result['summary'])
        self.assertFalse(result['sampling_qualification']['official_iid_points_enabled'])
        descriptive=result['descriptive_cohort']['summary']['primary']['answer']['question_macro']
        self.assertEqual(frac(descriptive['pass@1']['observed_combination_statistic']),Fraction(4,5))
        self.assertEqual(frac(descriptive['pass@5']['observed_combination_statistic']),1)
        self.assertEqual(frac(descriptive['pass^5']['observed_combination_statistic']),0)
        self.assertEqual(result['descriptive_cohort']['rows'][0]['observed_first_slot_success'],1)

    def test_qualified_uses_same_numbers_and_never_proves_provider_independence(self):
        result=self.score(self.approved());summary=result['summary']['primary']['answer']['question_macro']
        self.assertEqual(frac(summary['pass@1']['point_estimate']),Fraction(4,5))
        self.assertEqual(frac(summary['pass@5']['point_estimate']),1);self.assertEqual(frac(summary['pass^5']['point_estimate']),0)
        self.assertTrue(result['sampling_qualification']['official_iid_points_enabled']);self.assertFalse(result['sampling_qualification']['provider_independence_proven'])

    def test_fixed_and_review_decisions_do_not_leak_points_through_groups(self):
        for decision in ['fixed_cohort_only','needs_review']:
            with self.subTest(decision=decision):
                result=self.score(self.approved(decision));self.assert_no_official_points(result['rows']);self.assert_no_official_points(result['summary'])
                self.assertEqual(frac(result['descriptive_cohort']['rows'][0]['metrics']['pass@1']['observed_combination_statistic']),Fraction(4,5))

    def test_unknown_or_unaccepted_decision_rejected(self):
        for mutation in [lambda q:q.update(decision='whatever'),lambda q:q.update(decision=[]),lambda q:q.update(status='pending')]:
            with self.assertRaises(ContractError):self.score(self.approved(mutator=mutation))

    def test_wrong_plan_bytes_and_wrong_configuration_rejected(self):
        for mutation in [lambda q:q['plan'].update(sha256='0'*64),lambda q:q.update(configuration_sha256='0'*64)]:
            with self.assertRaises(ContractError):self.score(self.approved(mutator=mutation))
        reference=self.approved()
        with self.assertRaises(ContractError):aggregate(self.fx.plan,self.fx.records,root=self.fx.root,plan_sha=digest(self.fx.plan),sampling_qualification=reference)

    def test_missing_or_cross_batch_records_file_rejected(self):
        reference=self.approved();(self.fx.root/'scored-records.json').unlink()
        with self.assertRaises(ContractError):self.score(reference)
        def different_batch(q):
            self.fx.write('wrong-batch.json',self.fx.records[:4]);q['records']=self.fx.ref('wrong-batch.json')
        with self.assertRaises(ContractError):self.score(self.approved(mutator=different_batch))

    def test_missing_or_changed_evidence_or_self_reference_rejected(self):
        for mutation in [lambda q:q.update(evidence=[]),lambda q:q['evidence'][0].update(sha256='0'*64),lambda q:q.update(evidence=[q['plan']]),lambda q:q.update(evidence=[q['records']])]:
            with self.assertRaises(ContractError):self.score(self.approved(mutator=mutation))
        reference=self.approved();(self.fx.root/'sampling-evidence.json').unlink()
        with self.assertRaises(ContractError):self.score(reference)

    def test_review_registry_root_and_independence_scope_fail_closed(self):
        mutations=[lambda q:q.update(reviewers=['root']),lambda q:q.update(reviewers=['unregistered','root']),lambda q:q.update(reviewers=['independent','root','root']),
          lambda q:q.update(approved_by='independent'),lambda q:q.update(independent_review=False),lambda q:q.update(rationale=' '),
          lambda q:q.update(independence_scope='proven'),lambda q:q.update(provider_independence_proven=True)]
        for mutation in mutations:
            with self.assertRaises(ContractError):self.score(self.approved(mutator=mutation))

    def test_qualification_cannot_resolve_unknown_or_invent_five_trials(self):
        self.fx.records=self.fx.records[:1];result=self.score(self.approved());row=result['rows'][0]
        self.assertEqual(row['trial_verdicts'],['pass']+['needs_review']*4)
        self.assertIsNone(row['metrics']['pass@5']['point_estimate']);self.assertEqual(frac(row['metrics']['pass@5']['identification_bounds']['lower']),1)
        self.fx=BoundFixture(self.temp.name,n=4,successes=4);result=self.score(self.approved());row=result['rows'][0]
        self.assertIsNone(row['metrics']['pass@5']['point_estimate']);self.assertIsNone(row['metrics']['pass^5']['identification_bounds'])
        self.assertEqual(frac(row['metrics']['pass@1']['point_estimate']),1)

    def test_conditional_qualified_numeric_values_match_frozen_pre_gate_scorer(self):
        old_source=Path(__file__).resolve().parents[2]/'workspace/hop-audit-v15/metric-scorer-pre-sampling-gate-3fdb923.py'
        self.assertEqual(file_sha(old_source),'3fdb923dfd360b941904532fd44004b13465ba321e8391966ed8ab80fba8add0')
        spec=importlib.util.spec_from_file_location('metric_pre_gate_reference',old_source);old=importlib.util.module_from_spec(spec);spec.loader.exec_module(old)
        prior=old.aggregate(self.fx.plan,self.fx.records,root=self.fx.root,plan_sha=self.fx.plan_sha);current=self.score(self.approved())
        def compare(previous,now):
            if isinstance(previous,list):
                self.assertEqual(len(previous),len(now))
                for a,b in zip(previous,now):compare(a,b)
            elif isinstance(previous,dict):
                for key,value in previous.items():compare(value,now[key])
            else:self.assertEqual(previous,now)
        compare(prior['rows'],current['rows']);compare(prior['summary'],current['summary'])

    def test_cli_uses_bound_qualification_option(self):
        reference=self.approved();script=Path(__file__).with_name('scorer.py');output=self.fx.root/'qualified-report.json'
        process=subprocess.run([sys.executable,str(script),'--plan',str(self.fx.root/'plan.json'),'--records',str(self.fx.root/'scored-records.json'),
          '--sampling-qualification',str(self.fx.root/reference['path']),'--root',str(self.fx.root),'--output',str(output)],capture_output=True,text=True,
          creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
        self.assertEqual(process.returncode,0,process.stderr)
        result=json.loads(output.read_text(encoding='utf-8'));self.assertTrue(result['sampling_qualification']['official_iid_points_enabled'])

if __name__=='__main__':unittest.main()
