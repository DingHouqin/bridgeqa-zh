"""Allowlisted review projections and immutable batch sealing; see module README."""
import copy
import hashlib
import json
from pathlib import Path


def digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def write_frozen(path, value):
    path=Path(path)
    text=json.dumps(value,ensure_ascii=False,indent=2)+'\n'
    if path.exists():
        if path.read_text(encoding='utf-8')!=text:raise ValueError('Frozen artifact changed: '+str(path))
    else:
        path.parent.mkdir(parents=True,exist_ok=True)
        path.write_text(text,encoding='utf-8')


def project_candidate(candidate):
    # Claims and gold here are assertions under review, not hidden adjudication.
    result={k:copy.deepcopy(candidate[k]) for k in ('family_version','question','query') if k in candidate}
    if 'origin' in candidate:
        result['origin']={k:copy.deepcopy(candidate['origin'][k]) for k in ('entities','facts') if k in candidate['origin']}
    result['variants']=[]
    for variant in candidate.get('variants',[]):
        row={k:copy.deepcopy(variant[k]) for k in ('condition','gold','deletion_log') if k in variant}
        row['materials']=[{'context_id':u['unit_id'],'text':u['text']} for u in variant['materials']]
        # Gold solve objects contain program conclusions; only retain candidate claims/proofs.
        if 'gold' in row:
            row['gold']={k:row['gold'][k] for k in ('status','answer_ids','proofs') if k in row['gold']}
        result['variants'].append(row)
    if not result['variants']:
        # Single item challenge cases use the same explicit source-and-claims format.
        for key in ('materials','facts','proposed_answer','proposed_status','proof','declared_conditions'):
            if key in candidate:result[key]=copy.deepcopy(candidate[key])
    return result


def project_review(case,condition):
    if condition not in ('A','B','C'):raise ValueError('Unknown review condition')
    payload={'candidate':project_candidate(case['candidate']),
             'required_checks':['source_support','query_alignment','proof_validity','deletion_validity','family_invariants'],
             'review_contract':'逐个成员仅用该成员实际材料判断可答性。基准只用于核对变换，不补回已删证据。候选答案和证明是待核对声明，不是权威。未覆盖不代表错误；引文失配不等于语义支持消失。用输出schema逐项举证。'}
    if condition in ('B','C'):payload['generator_explanation']=copy.deepcopy(case.get('rationale',''))
    if condition=='C':
        payload['external_relation_hints']=copy.deepcopy(case.get('external_relation_hints',{})) if case['track']=='source' else {'status':'not_applicable_synthetic','facts':[]}
        payload['external_hint_policy']='仅已批准的C01/C02静态提示；不是裁判，不补事实或gold，不能验证时间或scope。'
    return payload


def freeze_batch(cases,references,out):
    if len({c['case_id'] for c in cases})!=len(cases):raise ValueError('Duplicate case IDs')
    refs={r['case_id']:r for r in references} if isinstance(references,list) else references
    if set(refs)!={c['case_id'] for c in cases}:raise ValueError('Reference coverage mismatch')
    for case in cases:
        for condition in ('A','B','C'):project_review(case,condition)
    out=Path(out)
    write_frozen(out/'cases.frozen.json',cases)
    write_frozen(out/'references.frozen.json',refs)
    manifest={'version':'review-batch-v0.2','cases_sha256':digest(cases),'references_sha256':digest(refs),
              'case_count':len(cases),'source_cases':sum(c['track']=='source' for c in cases),
              'synthetic_cases':sum(c['track']=='synthetic' for c in cases),'formal_release':False}
    write_frozen(out/'manifest.json',manifest)
    return manifest


def verify_reference_gate(out,review=None):
    out=Path(out)
    cases=json.loads((out/'cases.frozen.json').read_text(encoding='utf-8'))
    refs=json.loads((out/'references.frozen.json').read_text(encoding='utf-8'))
    manifest=json.loads((out/'manifest.json').read_text(encoding='utf-8'))
    review=review or json.loads((out/'reference_review.json').read_text(encoding='utf-8'))
    if digest(cases)!=manifest['cases_sha256'] or digest(refs)!=manifest['references_sha256']:raise ValueError('Frozen content digest mismatch')
    if review.get('status')!='approved' or review.get('reviewer_kind')!='independent_gpt_subagent':raise ValueError('Independent GPT pre-review required')
    if review.get('cases_sha256')!=digest(cases) or review.get('references_sha256')!=digest(refs):raise ValueError('Reference review version mismatch')
    return cases,refs
