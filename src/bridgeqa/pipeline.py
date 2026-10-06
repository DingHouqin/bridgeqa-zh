"""Actual standard-library runs, diagnostic isolation and reproducible demo state."""
import copy
import json
import math
import platform
import shutil
import subprocess
import sys
from collections import defaultdict
from datetime import datetime,timezone
from pathlib import Path

from .baseline import predict, ALGORITHM
from .io import read_jsonl
from .pilot import ROOT, audit_pilot, sha_bytes, write_json, write_jsonl
from .protocol import export_inputs, evaluate_v02, score_sample, stable_hash, normalize, average, validate_input, refs, texts, nonempty
from .validation import require


def code_hash(root=ROOT):
    files=sorted((root/'src/bridgeqa').rglob('*.py'))+sorted((root/'scripts').glob('*.py'))
    return stable_hash({p.relative_to(root).as_posix():sha_bytes(p.read_bytes()) for p in files})


def oracle_inputs(samples,inputs):
    public_by_id={i['sample_id']:i for i in inputs}
    output,reference=[],[]
    for sample in samples:
        conditions=defaultdict(list)
        for proof in sample['proofs']:
            for step in proof['steps']:
                key=(step['hop'],normalize(step['head']),step['relation'],step['qualifier'])
                conditions[key].append(step)
        for (hop,_,relation,qualifier),steps in conditions.items():
            public=copy.deepcopy(public_by_id[sample['sample_id']])
            head=steps[0]['head']
            public['question']=f'独立单跳诊断（正确上游）：实体「{head}」的「{relation}」是什么？限定：{qualifier or "无额外限定"}。只提交一跳；只用给定片段。'
            public['sample_id']='q_'+stable_hash([sample['sample_id'],public['question'],hop])[:24]
            validate_input(public);output.append(public)
            tails=[]
            for step in steps:
                for tail in [step['tail'],*sample['entity_aliases'].get(step['tail'],[])]:
                    if tail not in tails:tails.append(tail)
            proofs=[]
            for step in steps:
                single=copy.deepcopy(step);single['hop']=1
                p={'steps':[single]}
                if p not in proofs:proofs.append(p)
            reference.append({'schema_version':'oracle-reference-1','oracle_id':public['sample_id'],'parent_sample_id':sample['sample_id'],'seed_id':sample['seed_id'],'source_cluster':sample['source_cluster'],
                              'hop':hop,'variant':sample['variant'],'pair_id':sample['pair_id'],'mechanism':sample['attack']['primary_type'] if sample['attack'] else None,
                              'reference':{'sample_id':public['sample_id'],'seed_id':sample['seed_id'],'source_cluster':sample['source_cluster'],'hop_count':1,'documents':public['documents'],
                                           'answer':{'text':tails[0],'aliases':tails[1:]},'entity_aliases':sample['entity_aliases'],'proofs':proofs}})
    return output,reference


def score_oracle_node(reference,prediction):
    """Target and explicit support must match the SAME alternative; steps are diagnostic."""
    diagnostic=score_sample(reference,prediction)
    errors=[];core_valid=False;support=set();em=0;cs=0;proof_metrics=[]
    try:
        require(isinstance(prediction,dict),'missing or invalid Oracle prediction')
        required={'schema_version','sample_id','run_id','status','answer','support'}
        allowed=required|{'submitted_steps','raw_output','error_message','latency_ms'}
        require(required<=set(prediction)<=allowed,'Oracle core fields')
        require(prediction['schema_version']=='0.2' and prediction['sample_id']==reference['sample_id'],'Oracle version/ID')
        require(nonempty(prediction['run_id']) and prediction['status'] in ('ok','error','abstain'),'Oracle run/status')
        for field in ('raw_output','error_message'):
            require(prediction.get(field) is None or isinstance(prediction[field],str),'Oracle optional log type')
        latency=prediction.get('latency_ms')
        require(latency is None or (type(latency) in (float,int) and math.isfinite(latency) and latency>=0),'Oracle latency')
        answer=prediction['answer']
        require((answer is None and prediction['status']!='ok') or (isinstance(answer,dict) and set(answer)=={'text'} and isinstance(answer['text'],str)),'Oracle answer format')
        support=refs(prediction['support'])
        require(support<=set(texts(reference)),'Oracle unknown support')
        core_valid=True
        if prediction['status']=='ok':
            for proof in reference['proofs']:
                tail=proof['steps'][-1]['tail']
                target_match=normalize(answer['text']) in {normalize(t) for t in [tail,*reference['entity_aliases'].get(tail,[])]}
                gold=set().union(*(refs(s['evidence']) for s in proof['steps']))
                hits=len(support&gold);p=hits/len(support) if support else 0.;r=hits/len(gold)
                f=2*p*r/(p+r) if p+r else 0.
                proof_metrics.append({'answer_em':int(target_match),'support_precision':p,'support_recall':r,'support_f1':f})
                em=max(em,int(target_match));cs=max(cs,int(target_match and bool(support) and support==gold))
        else:errors.append('oracle_non_ok_status')
    except (ValueError,TypeError,KeyError) as exc:errors.append(str(exc))
    best=max(proof_metrics,key=lambda p:p['support_f1']) if proof_metrics else {'support_precision':0.,'support_recall':0.,'support_f1':0.}
    if core_valid and em and best['support_f1']==1 and not cs:errors.append('oracle_target_support_alternative_mismatch')
    return {'oracle_cs':cs,'answer_em':em,'support_precision':best['support_precision'],'support_recall':best['support_recall'],'support_f1':best['support_f1'],
            'core_valid':core_valid,'core_diagnostics':errors,'step_diagnostic_only':diagnostic,'raw_prediction':copy.deepcopy(prediction)}


def evaluate_oracle(reference,predictions,samples):
    known={r['oracle_id']:r for r in reference};indexed={}
    for pred in predictions:
        require(isinstance(pred,dict) and isinstance(pred.get('sample_id'),str) and pred['sample_id'] in known,'unknown oracle ID')
        require(pred['sample_id'] not in indexed,'duplicate oracle ID');indexed[pred['sample_id']]=pred
    scored=[]
    for ref in reference:
        item=score_oracle_node(ref['reference'],indexed.get(ref['oracle_id']))
        scored.append({**{k:v for k,v in ref.items() if k!='reference'},'oracle_cs':item['oracle_cs'],'answer_em':item['answer_em'],'support_f1':item['support_f1'],'diagnostic':item})
    sample_by_id={s['sample_id']:s for s in samples}
    mechanism_by_pair={s['pair_id']:s['attack']['primary_type'] for s in samples if s['attack']}
    parent_nodes=defaultdict(lambda:defaultdict(list))
    for row in scored:parent_nodes[row['parent_sample_id']][row['hop']].append(row['oracle_cs'])
    parents=[]
    for sid,hops in parent_nodes.items():
        sample=sample_by_id[sid]
        parents.append({'sample_id':sid,'seed_id':sample['seed_id'],'source_cluster':sample['source_cluster'],'variant':sample['variant'],'mechanism':mechanism_by_pair.get(sample['pair_id']),
                        'oracle_cs':average([average(hops.get(h,[0])) for h in range(1,sample['hop_count']+1)])})
    def summary(items):
        seed_values=defaultdict(list)
        for item in items:seed_values[item['seed_id']].append(item['oracle_cs'])
        ids={r['sample_id'] for r in items};nodes=[r for r in scored if r['parent_sample_id'] in ids]
        return {'samples':len(items),'seeds':len(seed_values),'source_clusters':len({r['source_cluster'] for r in items}),'nodes':len(nodes),'node_successes':sum(r['oracle_cs'] for r in nodes),
                'raw_node_rate':average([r['oracle_cs'] for r in nodes]),'seed_macro_oracle_cs':average([average(v) for v in seed_values.values()])}
    return {'condition':'independent_correct_upstream_rules; unverified_candidate_reference','success_definition':'target EM and exact explicit support for the same single-hop alternative; submitted_steps diagnostic only','counts':{'nodes':len(reference),'predictions':len(predictions),'missing':len(reference)-len(predictions),'parent_samples':len(parents),'seeds':len({r['seed_id'] for r in parents})},
            'by_variant':{v:summary([p for p in parents if p['variant']==v]) for v in ('gold_only','clean_control','adversarial')},
            'by_mechanism_condition':{m:{v:summary([p for p in parents if p['mechanism']==m and p['variant']==v]) for v in ('clean_control','adversarial')} for m in sorted(mechanism_by_pair.values())},
            'per_sample':parents,'per_node':scored,'note':'correct upstream is intentionally provided; no internal causal error attribution; nodes are dependent'}


def run_manifest(output,inputs,predictions,root=ROOT):
    try:
        if not (root/'.git').exists():raise OSError('this directory has no own Git metadata')
        revision=subprocess.run(['git','rev-parse','HEAD'],cwd=root,capture_output=True,text=True,check=True).stdout.strip()
        dirty=bool(subprocess.run(['git','status','--porcelain'],cwd=root,capture_output=True,text=True,check=True).stdout.strip())
    except (OSError,subprocess.CalledProcessError):revision=None;dirty=None
    return {'algorithm':ALGORITHM,'kind':'actual_rule_baseline_not_llm','developed_on_this_pilot':True,'run_at':datetime.now(timezone.utc).isoformat(),
            'python':sys.version.split()[0],'platform':platform.platform(),'git_commit':revision,'git_worktree_dirty':dirty,'code_sha256':code_hash(root),
            'input_sha256':sha_bytes((output/'inputs.jsonl').read_bytes()),'prediction_sha256':sha_bytes((output/'predictions.jsonl').read_bytes()),
            'samples_sha256':sha_bytes((root/'data/pilot/samples.jsonl').read_bytes()),'schema_sha256':sha_bytes((root/'schemas/v0.2/model-input.schema.json').read_bytes()),
            'records':len(inputs),'complete_answers':sum(p['status']=='ok' and bool(p['answer']['text']) for p in predictions),'abstentions':sum(p['status']=='abstain' for p in predictions),
            'status_counts':{s:sum(p['status']==s for p in predictions) for s in ('ok','abstain','error')},'total_latency_ms':sum(p['latency_ms'] for p in predictions),
            'model':None,'token_counts':None,'scope_policy':'visible synthetic appendix identity is excluded in both pair conditions','human_review':'pending','official_samples':0}


def build_run(output,root=ROOT):
    from .run_paths import check_build_output
    output=check_build_output(output,root)
    audit=audit_pilot(root)
    output.mkdir(parents=True,exist_ok=True)
    samples=read_jsonl(root/'data/pilot/samples.jsonl')
    require(all(s['split']!='test_hidden' for s in samples),'demo refuses hidden data')
    inputs=export_inputs(samples);write_jsonl(output/'inputs.jsonl',inputs)
    predictions=[predict(i) for i in inputs];write_jsonl(output/'predictions.jsonl',predictions)
    score=evaluate_v02(samples,predictions)
    score['submission']={'path':'predictions.jsonl','path_kind':'run_directory_relative','sha256':sha_bytes((output/'predictions.jsonl').read_bytes())}
    write_json(output/'score.json',score)
    oi,ref=oracle_inputs(samples,inputs);write_jsonl(output/'oracle-inputs.jsonl',oi);write_json(output/'oracle-reference.json',ref)
    op=[predict(i,ALGORITHM+'-oracle') for i in oi];write_jsonl(output/'oracle-predictions.jsonl',op)
    os=evaluate_oracle(ref,op,samples);write_json(output/'oracle-score.json',os)
    from .controlled import run_controlled
    controlled=run_controlled(output/'controlled',root)
    manifest=run_manifest(output,inputs,predictions,root)
    manifest['oracle']={'nodes':len(oi),'input_sha256':sha_bytes((output/'oracle-inputs.jsonl').read_bytes()),'prediction_sha256':sha_bytes((output/'oracle-predictions.jsonl').read_bytes()),'score_sha256':sha_bytes((output/'oracle-score.json').read_bytes()),'separate_from_main':True}
    manifest['controlled']={'cases':46,'roots':6,'source_topology_clusters':3,'separate_from_main_fixture_oracle':True,'run_manifest_sha256':sha_bytes((output/'controlled/run-manifest.json').read_bytes()),'score_sha256':sha_bytes((output/'controlled/score.json').read_bytes())}
    write_json(output/'run-manifest.json',manifest)
    state={'samples':samples,'inputs':inputs,'predictions':predictions,'score':score,'oracle_score':os,'manifest':manifest,'audit':audit,
           'sources':json.loads((root/'data/pilot/source-manifest.json').read_text(encoding='utf-8')),
           'spans':json.loads((root/'data/pilot/derived-spans.json').read_text(encoding='utf-8')),
           'original_spans':json.loads((root/'data/pilot/spans.json').read_text(encoding='utf-8')),
           'derivation_ledger':json.loads((root/'data/pilot/derivation-ledger.json').read_text(encoding='utf-8')),
           'review_ledger':json.loads((root/'data/pilot/review-ledger.json').read_text(encoding='utf-8'))}
    fixtures=read_jsonl(root/'examples/v0.2/demo.jsonl')
    require(all(s['origin']=='fictional_fixture' and s['split']=='example' for s in fixtures),'demo fixture isolation')
    state['fixtures']={'samples':fixtures,'inputs':export_inputs(fixtures),'predictions':[predict(i) for i in export_inputs(fixtures)]}
    state['controlled']=controlled
    write_json(output/'state.json',state)
    web=output/'web';web.mkdir(exist_ok=True)
    for name in ('index.html','app.js','styles.css','framework.svg'):
        source=root/'web'/name
        if source.exists():shutil.copyfile(source,web/name)
    (web/'state.js').write_bytes(('window.BRIDGEQA_STATE='+json.dumps(state,ensure_ascii=False).replace('<','\\u003c')+';\n').encode('utf-8'))
    return {'output':str(output),'records':len(inputs),'oracle_nodes':len(oi),'controlled_cases':46,'candidate_metrics':score['partitions']['candidate']['metrics'],'official_samples':0,'manifest':str(output/'run-manifest.json')}
