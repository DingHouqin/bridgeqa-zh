"""Versioned skill pilot: identical payloads/contracts, generic vs routed skills.

Historical diagnostics are disclosed development regressions. Only the new
independently constructed fixtures are forward tests. No prior run is replaced.
"""
from __future__ import annotations
import argparse
import concurrent.futures
import copy
import getpass
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import random
import sys

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(HERE.parent / 'deletion_review_v2'))
_spec = importlib.util.spec_from_file_location('_quality_v2_runtime', HERE.parent/'deletion_review_v2/experiment.py')
V2 = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(V2)
from review import project_member, ordered_proof_check, review_gate, REVIEW_SCHEMA, GENERIC_REVIEW_PROMPT
from scoring import assess_structural, semantic_payload, validate_semantic_review, SEMANTIC_SCHEMA, SEMANTIC_BASELINE_PROMPT
from skill_loader import load_skills, snapshot

read, save, digest, CORE = V2.read, V2.save_new_or_same, V2.digest, V2.CORE
WORK = ROOT/'workspace/quality-v3'
BATCH = ROOT/'artifacts/quality-v3/run-002'
OLD = ROOT/'artifacts/deletion-review-v2/batch-001'
OLD_RUNTIME = ROOT/'workspace/harness-prototype/runs/deletion-review-v2-20261022'
RUN = ROOT/'workspace/harness-prototype/runs/quality-v3-20261022-r2'

EVIDENCE = {'type':'object','properties':{'context_id':{'type':'string'},'quote':{'type':'string','minLength':1}},'required':['context_id','quote'],'additionalProperties':False}
INVENTORY_SCHEMA = {'type':'object','properties':{
    'facts':{'type':'array','items':{'type':'object','properties':{
        'parent':{'type':'string'},'child':{'type':'string'},'role':{'enum':['father','mother','parent']},
        'scope':{'type':'string'},'support_groups':{'type':'array','items':{'type':'array','items':EVIDENCE,'minItems':1}}},
        'required':['parent','child','role','scope','support_groups'],'additionalProperties':False}},
    'proof_paths':{'type':'array','items':{'type':'array','items':{'type':'string'}}},
    'repeated_support':{'enum':['present','not_found','unresolved']},
    'alternative_proof':{'enum':['present','not_found','unresolved']},
    'coverage_status':{'enum':['constructed','not_constructed','not_applicable','unresolved']},
    'reason':{'type':'string'}},
    'required':['facts','proof_paths','repeated_support','alternative_proof','coverage_status','reason'],'additionalProperties':False}
INVENTORY_PROMPT = '只根据当前来源材料登记查询所需父母事实的支持组和完整两步路径，判断重复支持及不同完整证明是否存在；明确覆盖状态，不补百科事实。每条引文必须逐字定位。输出所给JSON合同。'


def prepare():
    held = read(WORK/'heldout-cases.json')
    h_refs = read(WORK/'heldout-references-v3.json')
    cases = []; refs = {}
    old_cases = read(OLD/'cases.frozen.json'); old_refs = read(OLD/'references.frozen.json')
    for c in old_cases:
        if c['track'] != 'source' and c['case_id'] not in ('K1016','K1017','K1004','K1005'):
            continue
        candidate = copy.deepcopy(c['candidate']); ref = old_refs[c['case_id']]
        if c['track'] == 'source':
            condition = ref.get('evidence', {}).get('condition', 'base')
            index = next(i for i,v in enumerate(candidate['variants']) if v['condition']==condition)
        else:
            index = None
            # These two disclosed diagnostic pairs have an explicit father/father
            # question. Do not infer the query from their potentially bad proof.
            suffix = '8' if c['case_id'] in ('K1016','K1017') else '2'
            candidate['query']={'operation':'parent_chain','start':'丙'+suffix,'steps':['father','father'],'scope':'虚构档案'}
        cid='DEV-'+c['case_id']
        cases.append({'case_id':cid,'kind':'review','split':'diagnostic_development',
                      'payload':project_member(candidate,index)})
        refs[cid]={'expected_valid':ref['expected_verdict']=='pass',
                   'defect_category':ref['defect_category'],'reference_state':'GPT独立审核（旧版参考的单成员投影）',
                   'parent_case_id':c['case_id']}
    for c in held['review_cases']:
        cid=c['case_id']
        cases.append({'case_id':cid,'kind':'review','split':'independent_forward',
                      'payload':project_member(c['candidate'])})
        refs[cid]=copy.deepcopy(h_refs['review_references'][cid])
    families={f['family_id']:f for f in read(OLD/'families.frozen.json')}
    audit={digest(r['job']):r for r in read(OLD/'post-audit/audit-blind-records.json')}
    for path in sorted((OLD_RUNTIME/'locked-blind/results').glob('*.json')):
        result=read(path); job=result['job']; family=families[job['family_id']]
        row=(family['variants'][job['variant_index']] if job['variant_index'] is not None else
             {'materials':[],'gold':CORE.solve(family['query'],[])})
        original_payload=CORE.project(row,family['question'],V2.SCHEMAS['blind-solver'])
        inputs={'answer':result['answer'],'payload':original_payload,'row':row,
                'origin':family['origin'],'query':family['query']}
        cid='SCORE-DEV-'+digest(job)[:16]; ref=audit[digest(job)]
        cases.append({'case_id':cid,'kind':'scoring','split':'diagnostic_development',
                      'payload':semantic_payload(**inputs),'structural':assess_structural(**inputs),
                      'parent_job':job})
        refs[cid]={'expected_valid':ref['semantic_task_success'],
                   'status_correct':ref['status_correct'],
                   'final_answer_correct':ref['final_answer_semantically_correct'],
                   'proof_supported_by_actual_member':ref['proof_supported_by_actual_member'],
                   'reference_state':'GPT独立审核（旧盲解语义审核）'}
    for c in held['score_cases']:
        inputs={k:c[k] for k in ('answer','payload','row','origin','query')}
        cid=c['case_id']
        cases.append({'case_id':cid,'kind':'scoring','split':'independent_forward',
                      'payload':semantic_payload(**inputs),'structural':assess_structural(**inputs)})
        refs[cid]=copy.deepcopy(h_refs['score_references'][cid])
    for fid in ('HLM-V2-02','HLM-V2-04'):
        family=families[fid]; base=next(v for v in family['variants'] if v['condition']=='base')
        cid='INVENTORY-'+fid
        cases.append({'case_id':cid,'kind':'inventory','split':'exploratory_source',
                      'payload':{'question':family['question'],'query':family['query'],
                                 'contexts':[{'context_id':u['unit_id'],'text':u['text']} for u in base['materials']]}})
        refs[cid]={'status':'exploratory_not_in_accuracy_denominators','reference_state':'待独立审核实际支持登记'}
    jobs=[]
    for case in cases:
        for arm in ('generic','skills'):
            for repeat in range(1,4) if case['kind']=='review' else (1,):
                jobs.append({'case_id':case['case_id'],'kind':case['kind'],'arm':arm,'repeat':repeat})
    random.Random(2026102203).shuffle(jobs)
    files={p.relative_to(ROOT).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in [HERE/name for name in ('experiment.py','review.py','scoring.py','skill_loader.py')]}
    protocol={'version':'quality-skills-v0.3','seed':2026102203,'workers':4,'review_repeats':3,'scoring_repeats':1,
              'skills':snapshot(),'code_sha256':files,'generic_prompts':{'review':GENERIC_REVIEW_PROMPT,'scoring':SEMANTIC_BASELINE_PROMPT,'inventory':INVENTORY_PROMPT},
              'schemas':{'review':REVIEW_SCHEMA,'scoring':SEMANTIC_SCHEMA,'inventory':INVENTORY_SCHEMA},
              'comparison':'Same per-item payload, output schema and deterministic gates; skills arm appends only routed skill instructions.',
              'old_diagnostics_are_heldout':False,'formal_release':False}
    contracts={}
    for job in jobs:
        case=next(c for c in cases if c['case_id']==job['case_id']);kind=job['kind']
        prompt=protocol['generic_prompts'][kind]
        if job['arm']=='skills':prompt+='\n\n'+load_skills(kind,protocol['skills'][kind])['text']
        contracts[digest(job)[:24]]={'job':job,'split':case['split'],'role':kind,
            'input':case['payload'],'output_schema':protocol['schemas'][kind],'skill':prompt,
            'selected_skill_files':protocol['skills'][kind] if job['arm']=='skills' else {}}
    save(BATCH/'request-contracts.frozen.json',contracts)
    for name,value in [('cases.frozen.json',cases),('references.frozen.json',refs),('jobs.frozen.json',jobs),('protocol.frozen.json',protocol)]:save(BATCH/name,value)
    manifest={'version':'quality-skills-v0.3','cases_sha256':digest(cases),'references_sha256':digest(refs),
              'jobs_sha256':digest(jobs),'protocol_sha256':digest(protocol),'request_contracts_sha256':digest(contracts),'cases':len(cases),'jobs':len(jobs),'formal_release':False}
    save(BATCH/'manifest.json',manifest)
    return manifest


def verify():
    cases,refs,jobs,protocol,manifest=(read(BATCH/name) for name in ('cases.frozen.json','references.frozen.json','jobs.frozen.json','protocol.frozen.json','manifest.json'))
    for key,value in [('cases_sha256',cases),('references_sha256',refs),('jobs_sha256',jobs),('protocol_sha256',protocol)]:
        if manifest[key]!=digest(value):raise ValueError('Frozen '+key+' mismatch')
    if digest(read(BATCH/'request-contracts.frozen.json'))!=manifest['request_contracts_sha256']:raise ValueError('Frozen request contracts changed')
    for role,expected in protocol['skills'].items():load_skills(role,expected)
    for relative,sha in protocol['code_sha256'].items():
        if hashlib.sha256((ROOT/relative).read_bytes()).hexdigest()!=sha:raise ValueError('Frozen code changed: '+relative)
    gate=read(BATCH/'reference_review.json')
    if gate.get('status')!='approved' or gate.get('reviewer_kind')!='independent_gpt_subagent':raise ValueError('Independent pre-audit required')
    for k in ('cases_sha256','references_sha256','jobs_sha256','protocol_sha256','request_contracts_sha256'):
        if gate.get(k)!=manifest[k]:raise ValueError('Pre-audit '+k+' mismatch')
    return cases,refs,jobs,protocol


def run(key):
    cases,refs,jobs,protocol=verify(); indexed={c['case_id']:c for c in cases}
    contracts=read(BATCH/'request-contracts.frozen.json')
    def worker(number):
        with V2.HarnessCaller(key,RUN/('worker-'+str(number)),worker_id='quality-v3-'+str(number),max_tokens=8000) as caller:
            for job in jobs[number::4]:
                jid=digest(job)[:24]; dest=RUN/'results'/(jid+'.json')
                if dest.exists():
                    if read(dest)['job']!=job:raise ValueError('Resume identity mismatch')
                    continue
                case=indexed[job['case_id']]; kind=job['kind']; payload=case['payload']
                prompt=protocol['generic_prompts'][kind]
                if job['arm']=='skills':prompt+='\n\n'+load_skills(kind,protocol['skills'][kind])['text']
                frozen=contracts[jid]
                if frozen['job']!=job or digest(payload)!=digest(frozen['input']) or prompt!=frozen['skill']:raise ValueError('Resolved contract changed')
                response=None
                try:
                    response=caller.call('quality-'+jid,kind,payload,protocol['schemas'][kind],prompt)
                    row={'job':job,'status':'completed','answer':response,'input_hash':digest(payload)}
                    if kind=='review':
                        row['gate']=review_gate(response,payload)
                        if not row['gate']['protocol_valid']:row['status']='protocol_failure'
                    elif kind=='scoring':validate_semantic_review(response,payload)
                    else:
                        texts={c['context_id']:c['text'] for c in payload['contexts']}
                        for fact in response['facts']:
                            for group in fact['support_groups']:
                                for q in group:
                                    if not q['quote'] or q['context_id'] not in texts or q['quote'] not in texts[q['context_id']]:raise ValueError('Inventory quote outside actual material')
                except Exception as exc:
                    row={'job':job,'status':'protocol_failure' if response is not None or 'Protocol failure' in str(exc) else 'technical_failure',
                         'error_type':type(exc).__name__,'message':str(exc).replace(key,'[REDACTED]')[:1000]}
                    if response is not None:row['answer']=response
                save(dest,row,key)
                print(json.dumps({'finished':len(list((RUN/'results').glob('*.json'))),'job':job,'status':row['status']}),flush=True)
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:list(pool.map(worker,range(4)))


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('command',choices=['prepare','run','verify']);args=parser.parse_args()
    if args.command=='prepare':print(json.dumps(prepare()))
    elif args.command=='verify':print({'cases':len(verify()[0]),'verified':True})
    else:
        key=os.environ.get('DEEPSEEK_API_KEY') or getpass.getpass('DeepSeek runtime credential (hidden): ').strip()
        if not key:raise ValueError('Missing credential')
        run(key)
