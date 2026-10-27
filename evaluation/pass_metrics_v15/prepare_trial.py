"""Freeze a fresh initial-completion grid; [protocol](README.md). No API calls."""
import argparse,copy,dataclasses,json,random,re,sys
from pathlib import Path
from scorer import ROOT,ContractError,digest,file_sha,read,require,validate_plan

SRC=ROOT/'src/obstacle_v14';sys.path.insert(0,str(SRC))
from freeze import PROMPT,ANSWER_SCHEMA
from protocol_diagnostics import SUFFIX,last_schema

WORK=ROOT/'workspace/hop-audit-v15'
DEFAULT_IDS=['LIT-3A-base','HIS-3B-key_rewire','SCI-4A-base','LOG-4B-base']

def frozen(path,value):
    def sdk_json(v):
        if dataclasses.is_dataclass(v):return dataclasses.asdict(v)
        if hasattr(v,'model_dump'):return v.model_dump(mode='json')
        raise TypeError('Unsupported artifact value: '+type(v).__name__)
    raw=json.dumps(value,ensure_ascii=False,indent=2,default=sdk_json,allow_nan=False)+'\n';path=Path(path)
    # Preserve existing bytes (including schema property order). Dict insertion
    # order in a resumed ledger is not a change of its semantic record values.
    if path.exists():
        require(digest(read(path))==digest(json.loads(raw)),'Frozen artifact differs: '+str(path));return
    path.parent.mkdir(parents=True,exist_ok=True);path.write_text(raw,encoding='utf-8',newline='\n')

def prepare(label,model,trials=5,ids=None):
    require(re.fullmatch(r'[A-Za-z][A-Za-z0-9_-]{0,40}',label) is not None,'Unsafe experiment label')
    require(type(trials) is int and trials>=1,'Positive predeclared trial count required')
    require(model in {'deepseek-flash','gpt-6-luna'},'Unsupported runtime')
    qual_file=WORK/'input-qualification-root-r1.json';qualification=read(qual_file);qby={c['id']:c for c in qualification['records']}
    data=ROOT/'data/obstacle_hops_v14';manifest=read(data/'manifest.json');cases=[]
    for name in ['benchmark.jsonl','independent-nodes.jsonl','controls.jsonl']:
        require(file_sha(data/name)==manifest['files_sha256'][name],'Dataset bytes changed')
        cases.extend(json.loads(l) for l in (data/name).read_text(encoding='utf-8').splitlines() if l.strip())
    by={c['id']:c for c in cases};ids=DEFAULT_IDS if ids is None else ids
    require(ids and len(set(ids))==len(ids),'Unique case IDs required')
    selected=[by[cid] for cid in ids]
    require(all(qby[c['id']]['gold_status']=='accepted' and qby[c['id']]['input_sha256']==c['input_sha256'] for c in selected),'A quarantined/stale input cannot enter a new scored trial')
    run=WORK/'initial-trials'/(label+'-'+model)
    require(not (run/'plan.json').exists(),'Use a new trial label; old plans cannot be resampled adaptively')
    # Exact known current runtime snapshot; the runner rechecks local CLI/SDK,
    # patch hashes and actual invocation before any paid inference starts.
    previous='obstacle-v14-revised-luna-002' if model=='gpt-6-luna' else 'obstacle-v14-revised-deepseek-002'
    sample=next((ROOT/'workspace/harness-prototype/runs'/previous/'calls').rglob('*.input.json'))
    runtime=read(sample)['runtime_contract']
    schema=copy.deepcopy(ANSWER_SCHEMA);schema['properties']['proofs']={'type':'array','items':{'type':'array','items':{'type':'string'}}}
    schema['required'].append('proofs');schema=last_schema(schema)
    config={'model':model,'runtime_contract':runtime,'model_identity_limit':'Requested alias and local process/SDK evidence, not provider-signed snapshot or independence attestation.'}
    rubric={'trusted_reviewers':['semantic_gold_v15','hop_shortcuts_v15','root'],'approver':'root',
      'criteria':{'answer':'Entire final answer set and outer status follow the complete current input. An explicitly wrong header is not replaced by a later correct brief. Uncertain equivalence remains needs_review.',
        'logical_proof':'Final target correct and a semantically sufficient truthful observable derivation. Accept valid shorter proofs, bounds, pruning and alternatives. Do not demand the reference path or all nondecisive paths. No explicit false operation is allowed.',
        'output_contract':'Answer and logical proof pass, direct raw JSON satisfies the frozen schema and all requested exact identifiers, candidate-path enumeration, continuous citations and consistency requirements. This is distinct from logical sufficiency.'},
      'alternative_valid_proofs':'accept_without_matching_reference_path','uncertainty_policy':'needs_review'}
    plan={'version':'bridgeqa-pass-plan-v15','label':label,'configuration':config,'configuration_sha256':digest(config),'rubric':rubric,'rubric_sha256':digest(rubric),
      'input_qualification':{'path':qual_file.relative_to(ROOT).as_posix(),'sha256':file_sha(qual_file)},
      'sampling':{'unit':'single_first_completion','selection':'all_predeclared_slots','format_repairs':0,'iid_assumption':True,
        'independence_limit':'One fresh isolated session per slot, same full input and fixed configuration, no old answers or judgment feedback; provider stochastic stream independence cannot be attested.'},'cases':[],
      'scope':'Small predeclared integration experiment across four structures unless other IDs explicitly supplied. Not a representative full-benchmark estimate.'}
    for c in selected:
        request={'role':'node-solver' if c['partition']=='node' else 'blind-solver','skill':PROMPT+SUFFIX,'input':c['clean_input'],'output_schema':schema,'model':model,'runtime_contract':runtime}
        contract={k:v for k,v in request.items() if k!='input'};slots=[]
        for i in range(trials):
            prefix=run/'calls'/f'trial-{i:03d}'/c['partition']/c['clean_input']['id']
            request_path=Path(str(prefix)+'.attempt-0.request.json');response_path=Path(str(prefix)+'.attempt-0.response.json')
            frozen(request_path,request)
            slots.append({'trial_id':label+'/'+model+'/'+c['clean_input']['id']+f'/{i:03d}','ordinal':i,
              'request_path':request_path.relative_to(ROOT).as_posix(),'response_path':response_path.relative_to(ROOT).as_posix(),'request_sha256':file_sha(request_path)})
        q=qby[c['id']]
        plan['cases'].append({'id':c['id'],'family_id':c['family_id'],'partition':c['partition'],'input_sha256':c['input_sha256'],'gold_sha256':q['gold_sha256'],'request_contract_sha256':digest(contract),'slots':slots})
    validate_plan(plan);frozen(run/'plan.json',plan)
    order=[s['trial_id'] for c in plan['cases'] for s in c['slots']];random.Random(202610270015).shuffle(order)
    frozen(run/'execution-order.json',{'plan_sha256':file_sha(run/'plan.json'),'trial_ids':order})
    print(json.dumps({'plan':str(run/'plan.json'),'questions':len(selected),'initial_completions':len(order),'model_calls':0},ensure_ascii=False));return run/'plan.json'

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--label',required=True);p.add_argument('--model',required=True);p.add_argument('--trials',type=int,default=5);p.add_argument('--cases',nargs='+');a=p.parse_args();prepare(a.label,a.model,a.trials,a.cases)
