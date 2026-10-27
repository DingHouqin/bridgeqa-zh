"""Evidence-bound tri-state pass metrics; [contract](README.md).

This module aggregates independently adjudicated outcomes. It does not pretend
to settle arbitrary natural-language proof validity by string matching. Unknown
outcomes keep a fixed planned denominator and identification bounds, not zeros.
"""
from __future__ import annotations
import argparse,collections,hashlib,json,math,re
from fractions import Fraction
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
DIMENSIONS=('answer','logical_proof','output_contract')
VERDICTS={'pass','fail','needs_review'}
STATUS={'completed','technical_failure','missing'}
HEX=re.compile(r'[0-9a-f]{64}\Z')
SAFE_CLI_EVENTS={'thread.started','turn.started','turn.completed','turn.failed','item.started','item.updated','item.completed','error'}
CONFIG_PARAMETERS={'temperature','effort','max_tokens','max_output_tokens','seed','top_p','tools','transport','sdk_version','cli_version'}

class ContractError(ValueError):pass

def require(condition,message):
    if not condition:raise ContractError(message)

def canonical(value):
    return json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(',',':'),allow_nan=False)

def digest(value):return hashlib.sha256(canonical(value).encode('utf-8')).hexdigest()
def file_sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def no_duplicates(pairs):
    result={}
    for key,value in pairs:
        require(key not in result,'Duplicate JSON object key: '+key);result[key]=value
    return result

def read(path):
    def bad_constant(value):raise ContractError('Nonstandard JSON constant')
    return json.loads(Path(path).read_text(encoding='utf-8'),object_pairs_hook=no_duplicates,parse_constant=bad_constant)

def read_ref(ref,root):
    require(isinstance(ref,dict) and set(ref)=={'path','sha256'},'A bound artifact needs path and sha256')
    require(isinstance(ref['path'],str) and isinstance(ref['sha256'],str) and HEX.fullmatch(ref['sha256']),'Malformed artifact reference')
    path=(Path(root)/ref['path']).resolve()
    require(path.is_relative_to(Path(root).resolve()),'Artifact escapes the evaluation workspace')
    require(path.is_file(),'Bound artifact missing: '+ref['path'])
    require(file_sha(path)==ref['sha256'],'Bound artifact hash changed: '+ref['path'])
    return read(path),path

def integer(value,name,minimum=0):
    require(type(value) is int and value>=minimum,name+' must be an integer >= '+str(minimum));return value

def estimate(n,c,k,kind):
    """Exact U-statistic; return None when the declared budget is insufficient."""
    integer(n,'n');integer(c,'c');integer(k,'k',1)
    require(c<=n,'c exceeds n');require(kind in {'any','all'},'Unknown metric kind')
    if n<k:return None
    denominator=math.comb(n,k)
    numerator=math.comb(c,k) if kind=='all' else denominator-math.comb(n-c,k)
    return Fraction(numerator,denominator)

def number(value):
    return None if value is None else {'value':float(value),'numerator':value.numerator,'denominator':value.denominator}

def metric(verdicts,k,kind):
    """Bounds describe unresolved finite-cohort labels, not confidence intervals.

    Even a collapsed interval is not reported as a completed point estimate
    while any of the preregistered trial outcomes remains unadjudicated.
    """
    require(isinstance(verdicts,(list,tuple)) and all(v in VERDICTS for v in verdicts),'Invalid tri-state outcomes')
    n=len(verdicts);success=verdicts.count('pass');failure=verdicts.count('fail');unknown=n-success-failure
    lower=estimate(n,success,k,kind);upper=estimate(n,success+unknown,k,kind)
    return {'planned_trials':n,'pass':success,'fail':failure,'needs_review_or_missing':unknown,
      'point_estimate':number(lower) if not unknown else None,
      'identification_bounds':None if lower is None else {'lower':number(lower),'upper':number(upper)},
      'status':'insufficient_planned_trials' if n<k else 'pending_outcomes' if unknown else 'complete',
      'bounds_are_confidence_intervals':False}

def task_metrics(verdicts):
    return {'pass@1':metric(verdicts,1,'any'),'pass@5':metric(verdicts,5,'any'),'pass^5':metric(verdicts,5,'all')}

def average_metrics(rows):
    output={}
    for name in ['pass@1','pass@5','pass^5']:
        selected=[r['metrics'][name] for r in rows];complete=[r for r in selected if r['status']=='complete']
        def value(item):return Fraction(item['numerator'],item['denominator'])
        full=bool(selected) and len(complete)==len(selected)
        bounded=bool(selected) and all(r['identification_bounds'] is not None for r in selected)
        point=sum((value(r['point_estimate']) for r in complete),Fraction(0))/len(complete) if full else None
        lo=sum((value(r['identification_bounds']['lower']) for r in selected),Fraction(0))/len(selected) if bounded else None
        hi=sum((value(r['identification_bounds']['upper']) for r in selected),Fraction(0))/len(selected) if bounded else None
        output[name]={'eligible_questions':len(selected),'fully_adjudicated_questions':len(complete),
          'underbudget_questions':sum(r['status']=='insufficient_planned_trials' for r in selected),
          'point_estimate':number(point),'identification_bounds':{'lower':number(lo),'upper':number(hi)} if bounded else None,
          'complete_case_supplement':{'denominator':len(complete),'estimate':number(sum((value(r['point_estimate']) for r in complete),Fraction(0))/len(complete)) if complete else None},
          'official_denominator_policy':'All eligible predeclared questions; incomplete/underbudget questions never silently disappear.'}
    return output

def family_average(rows):
    grouped=collections.defaultdict(list)
    for row in rows:grouped[row['family_id']].append(row)
    per_family={f:average_metrics(rs) for f,rs in grouped.items()};result={}
    for name in ['pass@1','pass@5','pass^5']:
        entries=[f[name] for f in per_family.values()]
        def frac(item):return Fraction(item['numerator'],item['denominator'])
        full=bool(entries) and all(e['point_estimate'] is not None for e in entries)
        bounded=bool(entries) and all(e['identification_bounds'] is not None for e in entries)
        result[name]={'eligible_families':len(entries),'point_estimate':number(sum((frac(e['point_estimate']) for e in entries),Fraction(0))/len(entries)) if full else None,
          'identification_bounds':{side:number(sum((frac(e['identification_bounds'][side]) for e in entries),Fraction(0))/len(entries)) for side in ['lower','upper']} if bounded else None}
    return {'family_macro':result,'family_denominators':{f:len(rs) for f,rs in grouped.items()}}

def validate_plan(plan):
    require(plan.get('version')=='bridgeqa-pass-plan-v15','Unknown sampling-plan version')
    config=plan.get('configuration');rubric=plan.get('rubric')
    require(isinstance(config,dict) and isinstance(rubric,dict),'Configuration and rubric must be explicit objects')
    require(plan.get('configuration_sha256')==digest(config),'Configuration hash mismatch')
    require(plan.get('rubric_sha256')==digest(rubric),'Rubric hash mismatch')
    require(isinstance(config.get('model'),str) and bool(config['model']),'Requested model missing')
    require(isinstance(config.get('runtime_contract'),dict) and bool(config['runtime_contract']),'An exact actual runtime contract is required; a descriptive model/effort label is insufficient')
    require(set(config)<={'model','runtime_contract','model_identity_limit'}|CONFIG_PARAMETERS,'Unknown configuration fields cannot silently escape binding')
    for field in CONFIG_PARAMETERS & set(config):
        require(field in config['runtime_contract'] and canonical(config[field])==canonical(config['runtime_contract'][field]),'Configuration label differs from its exact runtime contract: '+field)
    sampling=plan.get('sampling',{})
    require(sampling.get('unit')=='single_first_completion','Only a single initial completion per slot is implemented; episodes need a separate declared policy')
    require(sampling.get('selection')=='all_predeclared_slots','Adaptive/filtered sampling is not accepted')
    require(sampling.get('format_repairs')==0 and type(sampling.get('format_repairs')) is int,'Format repairs are not independent initial samples')
    require(sampling.get('iid_assumption') is True,'The iid assumption must be explicitly declared, not inferred from IDs')
    require(isinstance(sampling.get('independence_limit'),str) and bool(sampling['independence_limit']),'Independence evidence limit must be disclosed')
    reviewers=rubric.get('trusted_reviewers');approver=rubric.get('approver')
    criteria=rubric.get('criteria')
    require(isinstance(criteria,dict) and set(criteria)==set(DIMENSIONS) and all(isinstance(v,str) and bool(v.strip()) for v in criteria.values()),'Rubric must freeze a nonempty success criterion for every scoring dimension')
    require(rubric.get('alternative_valid_proofs')=='accept_without_matching_reference_path','A valid shorter/alternative proof must not fail merely for differing from the reference path')
    require(rubric.get('uncertainty_policy')=='needs_review','Uncertain semantic outcomes must remain unresolved')
    require(isinstance(reviewers,list) and len(set(reviewers))==len(reviewers) and all(isinstance(r,str) and r for r in reviewers),'Trusted reviewer registry required')
    require(isinstance(approver,str) and approver and approver in reviewers,'Root approver must be in trusted reviewers')
    cases=plan.get('cases');require(isinstance(cases,list) and cases,'Predeclared cases missing')
    allids=set();trials=set()
    planned_paths=set()
    for case in cases:
        require(isinstance(case.get('id'),str) and case['id'] not in allids,'Duplicate or invalid question ID');allids.add(case['id'])
        require(isinstance(case.get('family_id'),str) and bool(case['family_id']),'Family ID required')
        require(case.get('partition') in {'primary','node','control'},'Partitions must remain separate')
        require(all(isinstance(case.get(k),str) and HEX.fullmatch(case[k]) for k in ['input_sha256','gold_sha256','request_contract_sha256']),'Question contract hashes required')
        slots=case.get('slots');require(isinstance(slots,list) and slots,'Predeclared trial slots required')
        require([s.get('ordinal') for s in slots]==list(range(len(slots))) and all(type(s.get('ordinal')) is int for s in slots),'Slots must be consecutive and preordered, never selected after outcomes')
        for slot in slots:
            tid=slot.get('trial_id');require(isinstance(tid,str) and tid and tid not in trials,'Trial IDs must be globally unique');trials.add(tid)
            for field,suffix in [('request_path','.attempt-0.request.json'),('response_path','.attempt-0.response.json')]:
                path=slot.get(field);require(isinstance(path,str) and path.endswith(suffix) and path not in planned_paths,'Unique predeclared initial-attempt artifact paths are required');planned_paths.add(path)
            require(slot['request_path'].removesuffix('.request.json')==slot['response_path'].removesuffix('.response.json'),'Request and response must occupy the same predeclared initial slot')
            require(isinstance(slot.get('request_sha256'),str) and HEX.fullmatch(slot['request_sha256']),'Initial request bytes must be frozen before inference')
        require(len({s['request_sha256'] for s in slots})==1,'Same-question samples must use byte-identical initial requests, including schema order')
    return {s['trial_id']:(c,s) for c in cases for s in c['slots']}

def request_contract(request):
    # Input varies by question but is separately hashed. All other frozen fields,
    # including actual effort/budget/tool/retry metadata, must match the plan.
    return {k:v for k,v in request.items() if k!='input'}

def bind_completion(record,case,plan,root):
    request,rp=read_ref(record['request'],root);response,sp=read_ref(record['response'],root)
    require('format_repair' not in request,'A repair request cannot be scored as an independent first completion')
    require(digest(request.get('input'))==case['input_sha256'],'Response uses a different question/material')
    require(digest(request_contract(request))==case['request_contract_sha256'],'Mixed prompt/schema/settings or selected repair')
    require(canonical(request.get('runtime_contract'))==canonical(plan['configuration']['runtime_contract']),'Actual runtime/decoding settings differ from the declared configuration')
    require(response.get('request_hash')==digest(request),'Raw response is not bound to this request')
    require(request.get('model')==response.get('selected_model')==plan['configuration']['model'],'Mixed or unknown requested model')
    require(response.get('finish_reason')=='completed','Incomplete generation is not a completed trial')
    sid=response.get('session_id');require(isinstance(sid,str) and sid,'Fresh session identity missing')
    require(isinstance(response.get('final_response'),str),'Raw final response missing')
    transport=request.get('runtime_contract',{}).get('transport','')
    if transport.startswith('codex_cli'):
        require(type(response.get('tool_action_events')) is int and response['tool_action_events']==0,'CLI tool/action evidence is missing or nonzero')
        events=response.get('events');require(isinstance(events,list) and events,'CLI events required')
        require(all(isinstance(e,dict) and e.get('type') in SAFE_CLI_EVENTS for e in events),'Unknown/action top-level CLI event')
        starts=[e.get('thread_id') for e in events if e.get('type')=='thread.started']
        messages=[e['item'].get('text') for e in events if e.get('type')=='item.completed' and isinstance(e.get('item'),dict) and e['item'].get('type')=='agent_message']
        require(starts==[sid] and messages==[response['final_response']],'CLI message/session mismatch')
        require(sum(e.get('type')=='turn.completed' for e in events)==1 and not any(e.get('type')=='turn.failed' or 'rerout' in e.get('type','').lower() for e in events),'CLI turn did not finish independently')
        require(all(e.get('item',{}).get('type') in {'agent_message','reasoning','error'} for e in events if e.get('type','').startswith('item.')),'Unexpected CLI tool/action item')
        process,pp=read_ref(record['process'],root)
        observed=[json.loads(line,object_pairs_hook=no_duplicates) for line in process.get('stdout','').splitlines() if line.strip()]
        require(process.get('exit_code')==0 and canonical(observed)==canonical(events),'Saved CLI events differ from retained process stdout')
        argv=process.get('argv',[])
        require(isinstance(argv,list) and argv.count('-m')==1 and argv.index('-m')+1<len(argv) and argv[argv.index('-m')+1]==plan['configuration']['model'],'Retained CLI invocation requested a different or conflicting model')
        require(not any(isinstance(v,str) and (v=='--model' or v.startswith('--model=') or (v.startswith('-m') and v!='-m')) for v in argv),'Conflicting/unsupported CLI model alias')
        effort=request.get('runtime_contract',{}).get('effort')
        actual_efforts=[]
        positions=[]
        for i,arg in enumerate(argv[:-1]):
            value=argv[i+1]
            if arg=='-c' and isinstance(value,str) and value.startswith('model_reasoning_effort='):
                positions.append(i+1)
                try:actual_efforts.append(json.loads(value.split('=',1)[1]))
                except ValueError:actual_efforts.append(value.split('=',1)[1])
        require(effort is not None and actual_efforts==[effort],'CLI reasoning-effort argument differs from the declared actual runtime contract')
        require([i for i,v in enumerate(argv) if isinstance(v,str) and 'model_reasoning_effort=' in v]==positions,'Hidden/aliased CLI effort override')
    require(isinstance(record.get('initial_attempt'),bool) and record['initial_attempt'],'Only the initial attempt can occupy this slot')
    require(record.get('attempt_ordinal')==0 and type(record.get('attempt_ordinal')) is int,'A later selected attempt cannot replace an initial sample')
    return {'session_id':sid,'response_sha256':file_sha(sp),'request_path':str(rp),'response_path':str(sp)}

def adjudicated(record,case,plan,root,plan_sha):
    result={d:'needs_review' for d in DIMENSIONS}
    if 'adjudication' not in record:return result,'no_accepted_semantic_review'
    review,path=read_ref(record['adjudication'],root)
    expected={'trial_id':record['trial_id'],'case_id':case['id'],'input_sha256':case['input_sha256'],'gold_sha256':case['gold_sha256'],
      'configuration_sha256':plan['configuration_sha256'],'rubric_sha256':plan['rubric_sha256'],'response_sha256':record['response']['sha256'],'plan_sha256':plan_sha}
    require(all(review.get(k)==v for k,v in expected.items()),'Stale or cross-question/model/rubric adjudication')
    decisions=review.get('verdicts');require(isinstance(decisions,dict) and set(decisions)==set(DIMENSIONS) and all(v in VERDICTS for v in decisions.values()),'Each review dimension must be tri-state')
    if review.get('status')!='accepted':return result,'semantic_review_pending'
    reviewers=review.get('reviewers',[]);trusted=set(plan['rubric']['trusted_reviewers'])
    require(isinstance(reviewers,list) and len(set(reviewers))>=2 and set(reviewers)<=trusted,'Two distinct registered reviewers required')
    require(review.get('approved_by')==plan['rubric']['approver'] and review['approved_by'] in reviewers,'Independent adjudication needs explicit registered Root approval')
    require(review.get('independent_review') is True and isinstance(review.get('rationale'),str) and bool(review['rationale']),'Review provenance/rationale is missing')
    require(not(decisions['logical_proof']=='pass' and decisions['answer']!='pass'),'A successful whole proof requires a correct final target')
    require(not(decisions['output_contract']=='pass' and (decisions['logical_proof']!='pass' or decisions['answer']!='pass')),'Full output-contract pass requires target and logical proof')
    if decisions['output_contract']=='pass':
        # Strong review cannot override a mechanically false serialization claim.
        import jsonschema
        request,_=read_ref(record['request'],root);response,_=read_ref(record['response'],root)
        try:
            parsed=json.loads(response['final_response'],object_pairs_hook=no_duplicates,parse_constant=lambda x:(_ for _ in ()).throw(ValueError('nonstandard constant')))
            jsonschema.validate(parsed,request['output_schema'])
        except (ValueError,TypeError,jsonschema.ValidationError,jsonschema.SchemaError) as exc:
            raise ContractError('Accepted output-contract pass contradicts raw JSON/schema evidence') from exc
    return decisions,'accepted_independent_adjudication'

def aggregate(plan,records,*,root=ROOT,plan_sha=None):
    slots=validate_plan(plan);plan_sha=plan_sha or digest(plan)
    qualification,qpath=read_ref(plan['input_qualification'],root)
    qrows=qualification.get('records');require(isinstance(qrows,list),'Input qualification registry missing')
    qualified={r['id']:r for r in qrows};require(len(qualified)==len(qrows),'Duplicate input qualification')
    byid={};sessions={};raw_hashes={};artifact_paths={};issues=[]
    for record in records:
        tid=record.get('trial_id');require(tid in slots,'Unplanned trial ID');require(tid not in byid,'Duplicate trial record')
        case,slot=slots[tid]
        require(record.get('case_id')==case['id'] and record.get('input_sha256')==case['input_sha256'],'Trial/question input mismatch')
        require(record.get('configuration_sha256')==plan['configuration_sha256'] and record.get('rubric_sha256')==plan['rubric_sha256'],'Mixed configuration/rubric')
        require(record.get('plan_sha256')==plan_sha,'Trial is not bound to this exact frozen plan')
        status=record.get('status');require(status in STATUS,'Unknown execution status')
        if status=='completed':
            require(record.get('request',{}).get('path')==slot['request_path'] and record.get('response',{}).get('path')==slot['response_path'],'A later/unplanned response was substituted for the frozen first-attempt slot')
            require(record['request']['sha256']==slot['request_sha256'],'Initial request bytes differ from the preregistered slot')
            binding=bind_completion(record,case,plan,root)
            for key,registry in [('session_id',sessions),('response_sha256',raw_hashes),('response_path',artifact_paths)]:
                value=binding[key];require(value not in registry,'Raw/session reused across nominally independent slots: '+key);registry[value]=tid
            verdicts,reason=adjudicated(record,case,plan,root,plan_sha)
        else:
            require('adjudication' not in record,'A missing/technical-failure slot cannot carry a success adjudication')
            verdicts={d:'needs_review' for d in DIMENSIONS};reason=status
            if status=='technical_failure':
                failure,fp=read_ref(record['failure'],root)
                require(failure.get('trial_id')==tid and failure.get('plan_sha256')==plan_sha and isinstance(failure.get('reason'),str) and bool(failure['reason']),'Technical failure evidence is unbound')
        byid[tid]={'trial_id':tid,'case_id':case['id'],'ordinal':slot['ordinal'],'status':status,'verdicts':verdicts,'reason':reason}
    rows=[]
    for case in plan['cases']:
        qr=qualified.get(case['id']);require(qr is not None and qr['input_sha256']==case['input_sha256'] and qr['gold_sha256']==case['gold_sha256'],'Input/gold approval is missing or stale')
        require(qr.get('family_id')==case['family_id'] and qr.get('partition')==case['partition'],'Question/family/partition stratum differs from the input qualification registry')
        require(qr.get('gold_status') in {'accepted','requires_review','rejected'},'Invalid gold qualification status')
        require(qr.get('hop_claim_status') in {'local_dependency_only','certified_under_explicit_contract','requires_review','rejected','parent_only','not_applicable'},'Missing hop qualification scope')
        actual=[]
        for slot in case['slots']:
            actual.append(byid.get(slot['trial_id'],{'trial_id':slot['trial_id'],'case_id':case['id'],'ordinal':slot['ordinal'],'status':'missing','verdicts':{d:'needs_review' for d in DIMENSIONS},'reason':'unexecuted_predeclared_slot'}))
        for dimension in DIMENSIONS:
            verdicts=[r['verdicts'][dimension] for r in actual]
            submitted=list(verdicts)
            if qr['gold_status']!='accepted':verdicts=['needs_review']*len(actual)
            rows.append({'id':case['id'],'family_id':case['family_id'],'partition':case['partition'],'dimension':dimension,'input_sha256':case['input_sha256'],
              'eligible':qr['gold_status']=='accepted','input_gold_status':qr['gold_status'],'hop_claim_status':qr['hop_claim_status'],
              'declared_hops':qr.get('declared_hops'),'certified_hops':qr.get('declared_hops') if qr['hop_claim_status']=='certified_under_explicit_contract' else None,
              'local_dependency_hops':qr.get('declared_hops') if qr['hop_claim_status'] in {'local_dependency_only','certified_under_explicit_contract'} else None,
              'trial_verdicts':verdicts,'submitted_review_verdicts':submitted,'metrics':task_metrics(verdicts),'first_attempt_accuracy':None if verdicts[0]=='needs_review' else int(verdicts[0]=='pass'),
              'completed_response_slots':sum(r['status']=='completed' for r in actual),'technical_failure_slots':sum(r['status']=='technical_failure' for r in actual),'missing_slots':sum(r['status']=='missing' for r in actual)})
    groups={}
    for partition in ['primary','node','control']:
        groups[partition]={}
        for dimension in DIMENSIONS:
            allrows=[r for r in rows if r['partition']==partition and r['dimension']==dimension];eligible=[r for r in allrows if r['eligible']]
            groups[partition][dimension]={'planned_questions':len(allrows),'eligible_gold_questions':len(eligible),
              'input_requires_review':sum(r['input_gold_status']=='requires_review' for r in allrows),'input_rejected':sum(r['input_gold_status']=='rejected' for r in allrows),
              'question_macro':average_metrics(eligible),**family_average(eligible),
              'local_dependency_hop_subgroups':{str(h):average_metrics([r for r in eligible if r['local_dependency_hops']==h]) for h in [3,4]},
              'certified_hop_subgroups':{str(h):average_metrics([r for r in eligible if r['certified_hops']==h]) for h in [3,4]}}
    return {'version':'bridgeqa-pass-report-v15','implementation_sha256':file_sha(Path(__file__)),'plan_sha256':plan_sha,'configuration_sha256':plan['configuration_sha256'],'rubric_sha256':plan['rubric_sha256'],
      'input_qualification_sha256':file_sha(qpath),'records_supplied':len(records),'predeclared_slots':len(slots),'cases':len(plan['cases']),
      'rows':rows,'summary':groups,'actual_trials':byid,'issues':issues,
      'interpretation':'U-statistics for iid initial completions under the declared protocol; fresh session/hash evidence does not mathematically prove provider-level independence. Bounds are unresolved-label identification bounds, not confidence intervals. Semantic judgments come from explicitly approved independent reviews, not from metric arithmetic.',
      'no_automatic_hop_inference':'Gold correctness, logical proof success and certified hop depth are different. Shorter valid proofs may pass logic while invalidating the benchmark hop claim.'}

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--plan',required=True);p.add_argument('--records',required=True);p.add_argument('--output',required=True);p.add_argument('--root',default=str(ROOT));a=p.parse_args()
    plan_file=Path(a.plan);record_file=Path(a.records);plan=read(plan_file);data=read(record_file)
    require(isinstance(data,list),'Records must be a JSON array')
    result=aggregate(plan,data,root=Path(a.root),plan_sha=file_sha(plan_file));result['records_file_sha256']=file_sha(record_file)
    output=Path(a.output).resolve();require(output.is_relative_to(Path(a.root).resolve()),'Output escapes evaluation workspace')
    raw=json.dumps(result,ensure_ascii=False,indent=2)+'\n'
    require(not output.exists() or output.read_text(encoding='utf-8')==raw,'Refusing to overwrite a different report')
    output.parent.mkdir(parents=True,exist_ok=True);output.write_text(raw,encoding='utf-8',newline='\n')
    print(json.dumps({'output':str(output),'cases':result['cases'],'slots':result['predeclared_slots'],'records':result['records_supplied']},ensure_ascii=False))
