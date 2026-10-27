"""Root-approved, file-bound adjudications and frozen-v15 metrics; [usage](README.md).

This is a serialization step after actual independent reviews and Root
acceptance. It does not evaluate answer strings or invent reviewer identities.
"""
import argparse,copy,json
from pathlib import Path
import analyze_delivery as A
S=A.S;ROOT=A.ROOT;WORK=A.WORK
PHASES=('current_r2','novel_r1','revised_r1','bounds_r1')

def ref(p):return A.file_ref(p)
def save(p,value):
 assert not p.exists(),str(p)
 p.parent.mkdir(parents=True,exist_ok=True)
 p.write_text(json.dumps(value,ensure_ascii=False,indent=2,allow_nan=False)+'\n',encoding='utf-8',newline='\n')

def main():
 parser=argparse.ArgumentParser();parser.add_argument('--current-luna-registration',required=True,type=Path);a=parser.parse_args()
 registration=a.current_luna_registration.resolve();registered=S.read(registration)
 # The named evidence must be an actual review artifact, not an alias for the
 # unregistered full reader. Root authorizes this run after inspecting it.
 assert 'hop_shortcuts_v15' in json.dumps(registered,ensure_ascii=False)
 assert 'review-revised-luna-cross-r1.json' in json.dumps(registered,ensure_ascii=False)
 assert registered['reviewers']==['hop_shortcuts_v15'] and registered['decision']=='accept_evidence_for_root_final_adjudication'
 report_names={('current_r2','gpt-6-luna'):'root-current-luna-proposed-r1.json',('current_r2','gpt-6.1-sol'):'review-current-sol-r2.json',('novel_r1','gpt-6-luna'):'review-novel-luna-r1.json',('novel_r1','gpt-6.1-sol'):'review-novel-sol-r1.json',('revised_r1','gpt-6-luna'):'review-revised-luna-r1.json',('revised_r1','gpt-6.1-sol'):'review-revised-sol-r1.json',('bounds_r1','gpt-6-luna'):'review-bounds-live-r1.json',('bounds_r1','gpt-6.1-sol'):'review-bounds-live-r1.json'}
 plans=[(phase,WORK/'runs'/(phase+'-'+model)/'plan.json') for phase in PHASES for model in A.MODELS]
 plan_by_key={}
 for phase,pp in plans:
  plan=S.read(pp);plan_by_key[(phase,plan['configuration']['model'])]=(pp,plan)
 grid,bindings=A.load_grid(plans);assert len(grid)==504
 reports={key:(WORK/name,S.read(WORK/name)) for key,name in report_names.items()}
 lookups={}
 for key,(path,doc) in reports.items():
  assert len({r['trial_id'] for r in doc['records']})==len(doc['records']),'Duplicate review row'
  if key!=('current_r2','gpt-6-luna'):assert doc['reviewers']==['hop_shortcuts_v15'],'Unexpected actual peer reviewer'
  actual={r['trial_id'] for r in doc['records']}
  expected={g['trial_id'] for g in grid if reports[(g['phase'],g['model'])][0]==path}
  assert actual==expected,'Missing or extra peer review rows'
  lookups[key]={r['trial_id']:r for r in doc['records']}
 assert len({r['trial_id'] for r in registered['records']})==len(registered['records']),'Duplicate registered row'
 registered_rows={r['trial_id']:r for r in registered['records']}
 proposed=lookups[('current_r2','gpt-6-luna')];assert set(registered_rows)==set(proposed)
 for tid,row in proposed.items():
  assert all(row[k]==registered_rows[tid][k] for k in ['case_id','input_sha256','response_sha256','verdicts'])
 for doc in [registered]+[d for _,d in reports.values()]:
  for source in doc.get('sources',[]):
   bound=(ROOT/source['path']).resolve();assert bound.is_relative_to(ROOT) and S.file_sha(bound)==source['sha256']
 sampler=WORK/'review-sampling-qualification-r2.json';sample=S.read(sampler);assert sample['n']==504 and 'hop_shortcuts_v15' in sample['reviewers']
 target_replay=WORK/'root-public-target-replay-r1.json';assert S.read(target_replay)['status']=='root_replay_completed'
 full_reader=WORK/'review-revised-luna-cross-r1.json';cross=S.read(full_reader)
 assert cross['root_new_proposal_sha256']==S.file_sha(WORK/'root-current-luna-proposed-r1.json')
 root_evidence=[ref(target_replay),ref(registration),ref(full_reader),ref(WORK/'target-ambiguity-qualification-r1.json'),ref(WORK/'review-analysis-helper-r1.json')]
 records=[];adjudications=[]
 for frozen in grid:
  key=(frozen['phase'],frozen['model']);path,report=reports[key];row=lookups[key][frozen['trial_id']]
  assert row['case_id']==frozen['case_id'] and row['input_sha256']==frozen['input_sha256']
  response_sha=row.get('response_sha256') or row['response']['sha256'];assert response_sha==frozen['response_sha256']
  verdicts=row['verdicts'];assert set(verdicts)==set(S.DIMENSIONS)
  if 'rationale' in row:reason=row['rationale']
  else:reason='；'.join(d+': '+str(v) for d,v in row.get('reasons',{}).items())
  assert reason
  support=[ref(path)]
  if key==('current_r2','gpt-6-luna'):support.extend([ref(full_reader),ref(registration)])
  grade={k:frozen[k] for k in ['phase','model','case_id','trial_id','response_sha256']}
  actual_peer=registered['reviewers'] if key==('current_r2','gpt-6-luna') else report['reviewers']
  grade.update(input_sha256=frozen['input_sha256'],verdicts=verdicts,rationale=reason,reviewers=actual_peer+['root'],approval={'status':'accepted','approved_by':'root','independent_review':True},review_evidence=support,root_acceptance_evidence=root_evidence,
   review_scope=('Root and a strong independent reader read all 202 substantive answers. Registered reviewer audited their evidence, disputed labels and bindings; that registered reviewer does not claim a third full reread.' if key==('current_r2','gpt-6-luna') else 'Independent registered reviewer read every substantive response; Root replayed public targets, checked bindings, equivalences/disputes and representative explanations. Root read all Luna novel/revised/bounds and all eight bounds outputs.'))
  A.check_grade(grade,frozen);records.append(grade)
  if verdicts['output_contract']=='pass':
   import jsonschema
   request=S.read(ROOT/frozen['response']['path'].replace('.response.json','.request.json'))
   raw=S.read(ROOT/frozen['response']['path']);parsed=json.loads(raw['final_response'],object_pairs_hook=S.no_duplicates,parse_constant=lambda x:(_ for _ in ()).throw(ValueError(x)))
   jsonschema.validate(parsed,request['output_schema'])
  pp,plan=plan_by_key[key];case=next(c for c in plan['cases'] if c['id']==frozen['case_id'])
  adj={k:grade[k] for k in ['trial_id','case_id','input_sha256','response_sha256','verdicts','rationale','reviewers','review_evidence','review_scope']}
  adj.update(gold_sha256=case['gold_sha256'],configuration_sha256=plan['configuration_sha256'],rubric_sha256=plan['rubric_sha256'],plan_sha256=S.file_sha(pp),status='accepted',approved_by='root',independent_review=True)
  dest=WORK/'adjudications-r1'/(S.digest(frozen['trial_id'])[:24]+'.json');adjudications.append((frozen,adj,dest))
 # No writes precede all supplied label/binding/provenance validation.
 assert not (WORK/'final-grade-map-r1.json').exists()
 for _,adj,p in adjudications:save(p,adj)
 save(WORK/'final-grade-map-r1.json',{'version':'root-accepted-semantic-grade-map-v16-r1','status':'accepted_with_explicit_U','approved_by':'root','records':records,'scope':'504 actual initial slots. Accepted adjudication can contain U; U is never success. No internal reasoning or global no-shortcut certification.'})
 outputs=[]
 for phase,pp in plans:
  plan=S.read(pp);model=plan['configuration']['model'];original=S.read(pp.parent/'records-initial.json');scored=copy.deepcopy(original)
  by={f['trial_id']:dest for f,_,dest in adjudications if f['phase']==phase and f['model']==model}
  for row in scored:row['adjudication']=ref(by[row['trial_id']])
  rp=WORK/'scored-records-r1'/(phase+'-'+model+'.json');save(rp,scored)
  # The audit of raw ingress binds initial records. This explicit equality
  # connects it to scored records; only an adjudication reference was added.
  assert [{k:v for k,v in x.items() if k!='adjudication'} for x in scored]==original
  qual={'version':'bridgeqa-sampling-qualification-v15','status':'accepted','decision':'protocol_qualified_under_iid_assumption','configuration_sha256':plan['configuration_sha256'],'plan':ref(pp),'records':ref(rp),'evidence':[ref(sampler),ref(WORK/'review-runner-r2.json'),ref(target_replay)],'reviewers':['hop_shortcuts_v15','root'],'approved_by':'root','independent_review':True,'rationale':'Independent audit binds all 504 predeclared request/stdin/receipt/native stdout/process/session records and ten rejected tamper controls. Scored records equal original records with only bound adjudication references added. Root accepts fixed local ingress under explicit stable provider/default and conditional iid assumptions. Provider internals, exact signed weights, environment values and stochastic independence were not attested.','independence_scope':'conditional_iid_assumption_not_proven','provider_independence_proven':False}
  qp=WORK/'sampling-qualifications-r1'/(phase+'-'+model+'.json');save(qp,qual)
  result=S.aggregate(plan,scored,root=ROOT,plan_sha=S.file_sha(pp),sampling_qualification=ref(qp));result['records_file_sha256']=S.file_sha(rp)
  op=WORK/'metrics-r1'/(phase+'-'+model+'.json');save(op,result);outputs.append({'phase':phase,'model':model,'report':ref(op),'sampling_qualification':ref(qp),'scored_records':ref(rp)})
 save(WORK/'root-final-acceptance-r1.json',{'status':'development_completed_with_preserved_review_items','approved_by':'root','grade_map':ref(WORK/'final-grade-map-r1.json'),'evidence':root_evidence+[ref(sampler)],'outputs':outputs,'completed_first_slots':504,'technical_failures':0,'models':list(A.MODELS),'attempts_per_question_model':1,'formal_dataset_release':False,'global_no_shortcut_certified':0,'assumptions':'Local protocol qualification is conditional and does not prove provider iid. All U remain U; all pass@5/pass^5 remain unavailable.'})
 print(json.dumps({'accepted_adjudications':len(records),'v15_aggregate_reports':len(outputs),'completed_initial_slots':len(grid),'source_sha256':S.file_sha(__file__)},ensure_ascii=False))

if __name__=='__main__':main()
