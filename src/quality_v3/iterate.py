"""Successive skill revisions with accumulating regressions and fresh fixtures.

Each round compares generic versus that revision under the same public
scaffolds. Previous fresh fixtures become regressions, never remain held out.
"""
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

HERE=Path(__file__).resolve().parent; ROOT=HERE.parents[1]
spec=importlib.util.spec_from_file_location('_quality_first_pilot',HERE/'experiment.py')
BASE=importlib.util.module_from_spec(spec);spec.loader.exec_module(BASE)
from review import project_member, review_gate
from scoring import semantic_payload, assess_structural, validate_semantic_review
from skill_loader import ROUTES
from protocol_next import NEXT_REVIEW_SCHEMA, NEXT_REVIEW_PROMPT
from retrieval import edge_windows, query_and_proof_card

read,save,digest=BASE.read,BASE.save,BASE.digest


def paths(round_number):
    if round_number not in (2,3):raise ValueError('This bounded iteration covers rounds 2 and 3')
    return (ROOT/f'artifacts/quality-v3/round-{round_number}',
            ROOT/f'workspace/harness-prototype/runs/quality-v3-round-{round_number}')


def bundle(round_number,role):
    root=HERE/f'skill-revisions/r{round_number}'
    files={};texts=[]
    for name,_ in ROUTES[role]:
        folder=root/name
        for path in [folder/'SKILL.md']+sorted((folder/'references').glob('*.md')):
            data=path.read_bytes();relative=path.relative_to(root).as_posix()
            files[relative]=hashlib.sha256(data).hexdigest()
            texts.append('项目技能 '+relative+'\n'+data.decode('utf-8'))
    return {'files':files,'text':'\n\n'.join(texts)}


def scaffold_inventory(case):
    payload=case['payload']
    if 'requested_edges' not in payload:
        if 'candidate_edges' in payload:
            payload['requested_edges']=copy.deepcopy(payload.pop('candidate_edges'))
        else:
            fid=case['case_id'].removeprefix('INVENTORY-')
            family=next(f for f in read(BASE.OLD/'families.frozen.json') if f['family_id']==fid)
            base=next(v for v in family['variants'] if v['condition']=='base')
            ids={fid for p in base['gold']['proofs'] for fid in p['facts']}
            payload['requested_edges']=[{k:f[k] for k in ('id','parent','child','parent_role','scope')}
                for f in family['origin']['facts'] if f['id'] in ids]
            payload['entity_bindings']=copy.deepcopy(family['origin']['entities'])
    payload.setdefault('entity_bindings',[])
    payload['focus_windows']=edge_windows(payload['contexts'],payload['requested_edges'],payload['entity_bindings'])
    payload['task_state']='只生成支持登记提案，尚未执行或验收任何可选家族变体。requested_edges是待核声明，窗口不是事实或独立性结论。'


def prepare(round_number):
    batch,_=paths(round_number)
    parent=BASE.BATCH if round_number==2 else paths(2)[0]
    cases=copy.deepcopy(read(parent/'cases.frozen.json'));refs=copy.deepcopy(read(parent/'references.frozen.json'))
    for case in cases:
        case.setdefault('initial_split',case['split'])
        case.setdefault('first_seen_round',1)
        case['split']='exploratory_source' if case['kind']=='inventory' else f'regression_r{round_number-1}'
    new=read(ROOT/f'workspace/quality-v3/round-{round_number}/new-cases.json')
    newrefs=read(ROOT/f'workspace/quality-v3/round-{round_number}/new-references.json')
    for c in new['review_cases']:
        cases.append({'case_id':c['case_id'],'kind':'review','split':'independent_forward',
                      'first_seen_round':round_number,'initial_split':'independent_forward',
                      'payload':project_member(c['candidate'])})
        refs[c['case_id']]=copy.deepcopy(newrefs['review_references'][c['case_id']])
    for c in new['score_cases']:
        inputs={k:c[k] for k in ('answer','payload','row','origin','query')}
        cases.append({'case_id':c['case_id'],'kind':'scoring','split':'independent_forward',
                      'first_seen_round':round_number,'initial_split':'independent_forward',
                      'payload':semantic_payload(**inputs),'structural':assess_structural(**inputs)})
        refs[c['case_id']]=copy.deepcopy(newrefs['score_references'][c['case_id']])
    for c in new['inventory_cases']:
        cases.append({'case_id':c['case_id'],'kind':'inventory','split':'exploratory_source',
                      'first_seen_round':round_number,'initial_split':'independent_forward',
                      'payload':copy.deepcopy(c['payload'])})
        refs[c['case_id']]=copy.deepcopy(newrefs['inventory_references'][c['case_id']])
    if len({c['case_id'] for c in cases})!=len(cases):raise ValueError('Case ID collision')
    for case in cases:
        if case['kind']=='review':
            text=case['payload']['review_contract'].split('\n[共同查询与提交证明卡]')[0]
            case['payload']['review_contract']=text+'\n[共同查询与提交证明卡]\n'+query_and_proof_card(case['payload'])
        elif case['kind']=='inventory':scaffold_inventory(case)
    schema={'review':NEXT_REVIEW_SCHEMA,'scoring':BASE.SEMANTIC_SCHEMA,'inventory':BASE.INVENTORY_SCHEMA}
    generic={'review':NEXT_REVIEW_PROMPT,'scoring':BASE.SEMANTIC_BASELINE_PROMPT,
             'inventory':BASE.INVENTORY_PROMPT+'\n逐requested_edges登记，focus_windows只提供全部字面出现位置的线索；仍以完整contexts为准。coverage_status指可选家族成员是否已经执行构建，本输入尚未执行变体。'}
    bundles={role:bundle(round_number,role) for role in ('review','scoring','inventory')}
    jobs=[{'case_id':c['case_id'],'kind':c['kind'],'arm':arm,'repeat':r}
          for c in cases for arm in ('generic','skills')
          for r in (range(1,4) if c['kind']=='review' else (1,))]
    random.Random(2026102202+round_number).shuffle(jobs)
    files=[HERE/name for name in ('iterate.py','experiment.py','review.py','scoring.py','skill_loader.py','protocol_next.py','retrieval.py')]
    protocol={'version':f'quality-skills-iteration-{round_number}','round':round_number,'workers':4,'request_stage_prefix':f'r{round_number}-',
              'seed':2026102202+round_number,'review_repeats':3,'scoring_repeats':1,
              'skill_root':f'src/quality_v3/skill-revisions/r{round_number}',
              'skills':{role:b['files'] for role,b in bundles.items()},
              'generic_prompts':generic,'schemas':schema,
              'code_sha256':{p.relative_to(ROOT).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in files},
              'shared_scaffolds':['explicit_zero_based_step_contract','query_and_submitted_proof_card','inventory_literal_edge_windows'],
              'parent_batch':parent.relative_to(ROOT).as_posix(),'parent_case_sha256':digest(read(parent/'cases.frozen.json')),
              'policy':'Previous fresh fixtures are now regressions; no prior output is overwritten. Same payload/schema/guards in both arms.',
              'formal_release':False}
    contracts={}
    by_id={c['case_id']:c for c in cases}
    for job in jobs:
        c=by_id[job['case_id']];role=job['kind'];prompt=generic[role]
        if job['arm']=='skills':prompt+='\n\n'+bundles[role]['text']
        contracts[digest(job)[:24]]={'job':job,'split':c['split'],'role':role,'input':c['payload'],
             'output_schema':schema[role],'skill':prompt,
             'selected_skill_files':bundles[role]['files'] if job['arm']=='skills' else {}}
    manifest={'version':protocol['version'],'round':round_number,'cases':len(cases),'jobs':len(jobs),'formal_release':False}
    for name,obj,key in [('cases.frozen.json',cases,'cases_sha256'),('references.frozen.json',refs,'references_sha256'),
                         ('jobs.frozen.json',jobs,'jobs_sha256'),('protocol.frozen.json',protocol,'protocol_sha256'),
                         ('request-contracts.frozen.json',contracts,'request_contracts_sha256')]:
        save(batch/name,obj);manifest[key]=digest(obj)
    save(batch/'manifest.json',manifest)
    return manifest


def verify(round_number):
    batch,runtime=paths(round_number);m=read(batch/'manifest.json')
    objs={name:read(batch/file) for name,file in [('cases','cases.frozen.json'),('refs','references.frozen.json'),
          ('jobs','jobs.frozen.json'),('protocol','protocol.frozen.json'),('contracts','request-contracts.frozen.json')]}
    for name,key in [('cases','cases_sha256'),('refs','references_sha256'),('jobs','jobs_sha256'),
                     ('protocol','protocol_sha256'),('contracts','request_contracts_sha256')]:
        if digest(objs[name])!=m[key]:raise ValueError('Frozen '+key+' changed')
    gate=read(batch/'reference_review.json')
    if gate.get('status')!='approved' or gate.get('reviewer_kind')!='independent_gpt_subagent':raise ValueError('Independent pre-audit required')
    for key in ('cases_sha256','references_sha256','jobs_sha256','protocol_sha256','request_contracts_sha256'):
        if gate.get(key)!=m[key]:raise ValueError('Pre-audit '+key+' mismatch')
    for path,sha in objs['protocol']['code_sha256'].items():
        if hashlib.sha256((ROOT/path).read_bytes()).hexdigest()!=sha:raise ValueError('Frozen model code changed')
    for role,files in objs['protocol']['skills'].items():
        if bundle(round_number,role)['files']!=files:raise ValueError('Skill revision changed')
    return objs


def run(round_number,key):
    objects=verify(round_number);batch,runtime=paths(round_number)
    jobs=objects['jobs'];cases={c['case_id']:c for c in objects['cases']};contracts=objects['contracts']
    def worker(n):
        with BASE.V2.HarnessCaller(key,runtime/f'worker-{n}',worker_id=f'r{round_number}-{n}',max_tokens=8000) as caller:
            for job in jobs[n::4]:
                jid=digest(job)[:24];dest=runtime/'results'/(jid+'.json')
                if dest.exists():
                    if read(dest)['job']!=job:raise ValueError('Resume identity mismatch')
                    continue
                c=contracts[jid];answer=None
                try:
                    answer=caller.call(f'r{round_number}-'+jid,c['role'],c['input'],c['output_schema'],c['skill'])
                    row={'job':job,'status':'completed','answer':answer,'input_hash':digest(c['input'])}
                    if job['kind']=='review':
                        row['gate']=review_gate(answer,c['input'])
                        if not row['gate']['protocol_valid']:row['status']='protocol_failure'
                    elif job['kind']=='scoring':validate_semantic_review(answer,c['input'])
                    else:
                        texts={t['context_id']:t['text'] for t in c['input']['contexts']}
                        for fact in answer['facts']:
                            for group in fact['support_groups']:
                                for q in group:
                                    if not q['quote'] or q['quote'] not in texts.get(q['context_id'],''):raise ValueError('Inventory citation outside actual contexts')
                except Exception as exc:
                    row={'job':job,'status':'protocol_failure' if answer is not None or 'Protocol failure' in str(exc) else 'technical_failure',
                         'error_type':type(exc).__name__,'message':str(exc).replace(key,'[REDACTED]')[:1000]}
                    if answer is not None:row['answer']=answer
                save(dest,row,key)
                print(json.dumps({'round':round_number,'finished':len(list((runtime/'results').glob('*.json'))),'job':job,'status':row['status']}),flush=True)
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:list(pool.map(worker,range(4)))


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('command',choices=['prepare','verify','run']);p.add_argument('--round',type=int,required=True);a=p.parse_args()
    if a.command=='prepare':print(json.dumps(prepare(a.round)))
    elif a.command=='verify':print({'cases':len(verify(a.round)['cases']),'verified':True})
    else:
        secret=os.environ.get('DEEPSEEK_API_KEY') or getpass.getpass('DeepSeek runtime credential (hidden): ').strip()
        if not secret:raise ValueError('Missing credential')
        run(a.round,secret)
