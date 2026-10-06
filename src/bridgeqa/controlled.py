"""Independent S1.3 diagnostic contract, scorer and actual rule runner.

Input: safe v0.2 inputs + separate controlled reference; output: independent
score/raw predictions/manifest. Standard-library runtime; full schemas are a
separate development check. Owner: S1.3. Never part of candidate/Oracle scores.
"""
import copy
import json
import math
import re
import os
import stat
import hashlib
from itertools import combinations
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

from .protocol import (validate_input, validate_v02, stable_hash, refs, texts,
                       nonempty, normalize, score_sample, average, RELATION_QUALIFIERS)
from .validation import require

PROFILE='controlled-temporary-world-1'
CONDITIONS=('full','order-shuffle','internal-reroute','delete-hop','no-context')
COUNTS={'full':6,'order-shuffle':6,'internal-reroute':11,'delete-hop':17,'no-context':6}
CODE=re.compile(r'N[0-9a-f]{8}')
RUN_FILES=('inputs.jsonl','reference.json','predictions.jsonl','score.json','audit.json','run-manifest.json')
CASE_COMMON={'sample_id','root_id','source_cluster','condition','intervention_hop','hop_count','expected_answerable','input_sha256','presentation','available_fact_support','changed_slots'}
WORLD_FIELDS={'root_id','parent_sample_id','parent_seed_id','source_cluster','hop_count','a_nodes','b_nodes','source_mapping','source_provenance','base_facts','roster_codes','roster_text','base_order'}


def validate_reference(inputs, reference):
    """Strict standard-library shape + matched intervention invariants.

    Source replay and frozen file byte checks live in audit_controlled. This
    function also validates user-supplied paired input/reference contracts.
    """
    require(isinstance(reference,dict) and set(reference)=={'schema_version','profile','generator','salt','visibility','method','worlds','cases'},'controlled reference fields')
    require(reference['schema_version']=='controlled-reference-1' and reference['profile']==PROFILE,'controlled reference version/profile')
    require(reference['generator']=='parallel-chain-sha256-v1' and nonempty(reference['salt']),'controlled generator/salt')
    require(reference['visibility']=='public-diagnostic_reference_never_model_input' and nonempty(reference['method']),'controlled disclosure')
    require(isinstance(inputs,list) and len(inputs)==46,'controlled input count')
    public={}
    for row in inputs:
        validate_input(row);require(row['sample_id'] not in public,'duplicate controlled input');public[row['sample_id']]=row
    worlds=reference['worlds'];cases=reference['cases']
    require(isinstance(worlds,list) and len(worlds)==6 and isinstance(cases,list) and len(cases)==46,'controlled six worlds/46 cases')
    by_world={};all_codes=set()
    for world in worlds:
        require(isinstance(world,dict) and set(world)==WORLD_FIELDS,'controlled world fields')
        root=world['root_id'];h=world['hop_count']
        require(nonempty(root) and root not in by_world and type(h) is int and h in (2,3,4),'controlled root/hops')
        require(all(nonempty(world[k]) for k in ('parent_sample_id','parent_seed_id','source_cluster','roster_text')) and re.fullmatch(r'q_[0-9a-f]{24}',world['parent_sample_id']),'controlled world metadata')
        for branch in ('a_nodes','b_nodes'):
            nodes=world[branch];require(isinstance(nodes,list) and len(nodes)==h+1 and all(isinstance(c,str) and CODE.fullmatch(c) for c in nodes),'opaque node format')
        nodes=world['a_nodes']+world['b_nodes']
        require(len(set(map(normalize,nodes)))==len(nodes) and not set(nodes)&all_codes,'opaque nodes must be globally unique');all_codes.update(nodes)
        require(isinstance(world['roster_codes'],list) and set(world['roster_codes'])==set(nodes) and len(world['roster_codes'])==len(nodes),'roster exactly all nodes once')
        from .controlled_generation import roster_codes
        require(world['roster_codes']==roster_codes(nodes),'roster order must depend only on code and fixed salt')
        require(world['roster_text']=='本临时世界代号名册：'+'、'.join(world['roster_codes'])+'。本句只列代号，不陈述任何关系。','roster text')
        mapping=world['source_mapping']
        require(isinstance(mapping,list) and len(mapping)==h+1 and all(isinstance(m,dict) and set(m)=={'source_entity','code'} and nonempty(m['source_entity']) and m['code']==world['a_nodes'][i] for i,m in enumerate(mapping)),'source mapping')
        require(isinstance(world['source_provenance'],dict) and set(world['source_provenance'])=={'construction_method','sources'} and nonempty(world['source_provenance']['construction_method']) and isinstance(world['source_provenance']['sources'],list),'source provenance')
        for source in world['source_provenance']['sources']:
            require(isinstance(source,dict) and set(source)=={'source_id','url','citation','version','accessed_at','license','text_sha256'} and all(nonempty(v) for v in source.values()),'source metadata')
            require(re.fullmatch(r'[a-f0-9]{64}',source['text_sha256']),'source hash')
        facts=world['base_facts'];require(isinstance(facts,list) and len(facts)==2*h,'parallel edge count')
        for n,fact in enumerate(facts):
            require(isinstance(fact,dict) and set(fact)=={'slot_id','kind','head','relation','qualifier','tail'},'fact fields')
            branch='A' if n<h else 'B';k=n%h+1;path=world['a_nodes'] if branch=='A' else world['b_nodes']
            require(fact['slot_id']==f'{branch}{k}' and fact['kind']=='fact' and fact['head']==path[k-1] and fact['tail']==path[k],'parallel fact topology')
            require(fact['relation'] in RELATION_QUALIFIERS and fact['qualifier']==RELATION_QUALIFIERS[fact['relation']],'public fact vocabulary')
            if n>=h:require((fact['relation'],fact['qualifier'])==(facts[n-h]['relation'],facts[n-h]['qualifier']),'parallel relation/qualifier')
        order=world['base_order'];require(isinstance(order,list) and len(order)==2*h+1 and set(order)=={f['slot_id'] for f in facts}|{'roster'},'world presentation slots')
        by_world[root]=world
    require([w['hop_count'] for w in worlds]==[2,3,3,4,2,3] and len({w['source_cluster'] for w in worlds})==3,'controlled six topology/three cluster contract')
    seen=set();grouped=defaultdict(list);answerable=[]
    for case in cases:
        require(isinstance(case,dict) and type(case.get('expected_answerable')) is bool,'controlled answerability')
        expected=case['expected_answerable'];require(set(case)==CASE_COMMON|({'reference'} if expected else {'expected_refusal'}),'controlled case branch fields')
        sid=case['sample_id'];require(sid in public and sid not in seen,'unknown/duplicate controlled case');seen.add(sid)
        root=case['root_id'];require(root in by_world,'unknown root');world=by_world[root];h=world['hop_count'];row=public[sid]
        require(case['hop_count']==h and type(case['hop_count']) is int and case['source_cluster']==world['source_cluster'],'case topology metadata')
        condition=case['condition'];k=case['intervention_hop'];require(condition in CONDITIONS,'controlled condition')
        require(expected==(condition in CONDITIONS[:3]),'condition answerability')
        require((type(k) is int and 1<=k<=(h-1 if condition=='internal-reroute' else h)) if condition in ('internal-reroute','delete-hop') else k is None,'intervention hop')
        require(case['input_sha256']==stable_hash(row),'controlled safe input hash')
        presentation=case['presentation'];require(isinstance(presentation,list) and len(presentation)==len(row['documents']),'case presentation')
        require(all(isinstance(p,dict) and set(p)=={'slot_id','doc_id','sent_id'} and nonempty(p['slot_id']) and p['doc_id']==f'd{n}' and type(p['sent_id']) is int and p['sent_id']==0 for n,p in enumerate(presentation,1)),'presentation mapping fields')
        order=[p['slot_id'] for p in presentation]
        require(len(set(order))==len(order),'duplicate fact slots')
        if condition=='no-context':require(order==['no-context'],'no-context slot')
        else:require(set(order)==set(world['base_order']),'case fact slots')
        if condition in ('full','internal-reroute','delete-hop'):require(order==world['base_order'],'matched presentation changed')
        if condition=='order-shuffle':require(order!=world['base_order'],'shuffle must be nonidentity')
        require(case['changed_slots']==([f'A{k}'] if condition in ('internal-reroute','delete-hop') else []),'registered changed slot')
        by_slot={p['slot_id']:(p['doc_id'],p['sent_id']) for p in presentation}
        row_text=texts(row);facts=copy.deepcopy(world['base_facts'])
        if condition=='internal-reroute':next(f for f in facts if f['slot_id']==f'A{k}')['tail']=world['b_nodes'][k]
        from .controlled_generation import fact_text, MISSING, NO_CONTEXT
        expected_text={f['slot_id']:fact_text(f) for f in facts};expected_text['roster']=world['roster_text']
        if condition=='delete-hop':expected_text[f'A{k}']=MISSING
        if condition=='no-context':expected_text={'no-context':NO_CONTEXT}
        require(row_text=={by_slot[s]:expected_text[s] for s in order},'unregistered changed statement/roster/marker')
        available={by_slot[f['slot_id']] for f in facts if f['slot_id'] in by_slot and not (condition=='delete-hop' and f['slot_id']==f'A{k}')}
        require(refs(case['available_fact_support'])==available,'available evidence excludes roster/markers')
        if expected:
            sample=case['reference'];validate_v02([sample])
            require(sample['sample_id']==sid and sample['question']==row['question'] and sample['documents']==row['documents'] and sample['hop_count']==h,'reference/current input mismatch')
            require(sample['origin']=='fictional_fixture' and sample['split']=='example' and sample['qc']=={'status':'fixture_only','human_verified':False,'review_ids':[]} and sample['entity_aliases']=={} and sample['answer']['aliases']==[],'controlled reference must be unverified fiction without aliases')
            require(sample['seed_id']==sid and sample['source_cluster']==world['source_cluster'] and sample['domain']=='synthetic_temporary_world' and sample['variant']=='gold_only' and sample['pair_id'] is None and sample['attack'] is None and sample['answer']['type']=='entity','controlled fixture reference metadata')
            require(sample['provenance']['sources']==world['source_provenance']['sources'] and sample['provenance']['construction_method']=='source-derived topology; all temporary-world statements and B branch are synthetic; not source quotations or human gold','controlled synthetic source attribution')
            expected_steps=[]
            for hop in range(1,h+1):
                branch='B' if condition=='internal-reroute' and hop>k else 'A'
                fact=next(f for f in facts if f['slot_id']==f'{branch}{hop}')
                did,si=by_slot[fact['slot_id']]
                expected_steps.append({'hop':hop,**{key:fact[key] for key in ('head','relation','tail','qualifier')},'evidence':[{'doc_id':did,'sent_id':si}]})
            require(sample['proofs']==[{'steps':expected_steps}],'reference must follow changed graph')
            require(sample['answer']['text']==expected_steps[-1]['tail'],'changed target reference');answerable.append(sample)
        else:require(case['expected_refusal'] is True,'insufficient case expects refusal')
        # Require a unique answer path iff answerable, using available facts only.
        current=world['a_nodes'][0];walk=[]
        for hop in range(h):
            relation=world['base_facts'][hop]['relation'];qualifier=world['base_facts'][hop]['qualifier']
            choices=[f for f in facts if f['slot_id'] in by_slot and by_slot[f['slot_id']] in available and f['head']==current and f['relation']==relation and f['qualifier']==qualifier]
            if len(choices)!=1:break
            walk.append(choices[0]);current=choices[0]['tail']
        require((len(walk)==h)==expected,'answerability must follow available facts')
        if condition!='no-context':
            joined='\n'.join(row_text.values());require(world['a_nodes'][-1] in joined and world['b_nodes'][-1] in joined,'both terminal codes remain visible')
        codes_in_question=CODE.findall(row['question']);require(codes_in_question==[world['a_nodes'][0]],'question leaks bridge/branch codes')
        require(all(m['source_entity'] not in row['question'] and all(m['source_entity'] not in t for t in row_text.values()) for m in world['source_mapping']),'original names leaked into safe input')
        grouped[root].append(case)
    require(Counter(c['condition'] for c in cases)==COUNTS and sum(c['expected_answerable'] for c in cases)==23,'controlled condition/answerability totals')
    for root,members in grouped.items():
        h=by_world[root]['hop_count']
        require(Counter(c['condition'] for c in members)=={'full':1,'order-shuffle':1,'internal-reroute':h-1,'delete-hop':h,'no-context':1},'per root intervention counts')
        for condition,maximum in (('internal-reroute',h-1),('delete-hop',h)):
            require(sorted(c['intervention_hop'] for c in members if c['condition']==condition)==list(range(1,maximum+1)),'all intervention hops exactly once')
        require(len({public[c['sample_id']]['question'] for c in members})==1,'question must be fixed in world')
    return {'profile':PROFILE,'cases':46,'roots':6,'source_topology_clusters':3,'answerable':23,'insufficient':23,'by_condition':dict(COUNTS),'schema_validation':'runtime_contract_checks','human_review':'pending','official_samples':0}


def prediction_shape(case, prediction):
    """Exact v0.2 fields + continuous connected path and finite optional latency."""
    require(isinstance(prediction,dict),'missing_or_malformed_prediction')
    require(not nonfinite_paths(prediction),'nested_nonfinite_prediction')
    required={'schema_version','sample_id','run_id','status','answer','support','submitted_steps'}
    require(required<=set(prediction)<=required|{'raw_output','error_message','latency_ms'},'prediction_fields')
    require(prediction['schema_version']=='0.2' and prediction['sample_id']==case['sample_id'],'prediction_version_or_id')
    require(nonempty(prediction['run_id']) and prediction['status'] in ('ok','abstain','error'),'prediction_run_or_status')
    for field in ('raw_output','error_message'):require(prediction.get(field) is None or isinstance(prediction[field],str),'prediction_log_type')
    latency=prediction.get('latency_ms');require(latency is None or (type(latency) in (float,int) and math.isfinite(latency) and latency>=0),'prediction_latency')
    answer=prediction['answer'];require(answer is None or (isinstance(answer,dict) and set(answer)=={'text'} and isinstance(answer['text'],str)),'prediction_answer_shape')
    if prediction['status']=='ok':require(isinstance(answer,dict),'ok_requires_answer')
    if prediction['status']=='abstain':require(answer is None,'abstain_requires_null')
    steps=prediction['submitted_steps'];require(isinstance(steps,list),'prediction_steps')
    available=refs(case['available_fact_support']);support=refs(prediction['support']);union=set()
    require(support<=available,'unknown_or_nonfact_support')
    for hop,step in enumerate(steps,1):
        require(isinstance(step,dict) and set(step)=={'hop','head','relation','tail','qualifier','evidence'},'step_fields')
        require(type(step['hop']) is int and step['hop']==hop and 1<=hop<=4,'step_hop')
        require(all(nonempty(step[field]) for field in ('head','relation','tail')) and isinstance(step['qualifier'],str),'step_text')
        evidence=refs(step['evidence']);require(bool(evidence) and evidence<=available,'unknown_empty_or_nonfact_evidence');union|=evidence
        if hop>1:require(normalize(steps[hop-2]['tail'])==normalize(step['head']),'disconnected_steps')
    require(support==union,'support_not_exact_step_union')
    return True


def nonfinite_paths(value,path=()):
    """Find non-finite Python floats at any nesting depth without mutation."""
    if isinstance(value,float) and not math.isfinite(value):return [list(path)]
    if isinstance(value,dict):return [p for key,item in value.items() for p in nonfinite_paths(item,(*path,key))]
    if isinstance(value,(list,tuple)):return [p for index,item in enumerate(value) for p in nonfinite_paths(item,(*path,index))]
    return []


def raw_diagnostic(value):
    """Finite raw remains unchanged; non-finite raw gets unambiguous typed nodes.

    The wrapper encodes every original node type, so a user-supplied dict that
    resembles a float marker remains a dict node, never a substituted value.
    The diagnostic is never passed back into scoring.
    """
    paths=nonfinite_paths(value)
    if not paths:return copy.deepcopy(value)
    def typed(item):
        if isinstance(item,float) and not math.isfinite(item):
            return {'type':'python-float-nonfinite','value':'nan' if math.isnan(item) else ('+inf' if item>0 else '-inf')}
        if isinstance(item,dict):return {'type':'dict','items':[[typed(key),typed(val)] for key,val in item.items()]}
        if isinstance(item,list):return {'type':'list','items':[typed(val) for val in item]}
        if isinstance(item,tuple):return {'type':'tuple','items':[typed(val) for val in item]}
        return {'type':type(item).__name__,'value':copy.deepcopy(item)}
    return {'representation':'python-nonfinite-tagged-v1','nonfinite_paths':paths,'structure':typed(value)}


def strict_json_bytes(value,jsonl=False):
    """Encode completely before touching any filesystem output."""
    if jsonl:
        return ''.join(json.dumps(row,ensure_ascii=False,allow_nan=False)+'\n' for row in value).encode('utf-8')
    return (json.dumps(value,ensure_ascii=False,allow_nan=False,indent=2)+'\n').encode('utf-8')


def write_strict_json(path,value):
    encoded=strict_json_bytes(value)
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(encoded)


def submission_evidence(path):
    raw=Path(path).read_bytes()
    return {'raw_submission':raw.decode('utf-8'),'sha256':hashlib.sha256(raw).hexdigest()}


def parse_error_record(path,error):
    return {'schema_version':'controlled-submission-error-1','status':'submission_parse_error','error':str(error),**submission_evidence(path)}


def score_case(case, prediction, model_input=None):
    valid=False;errors=[]
    try:prediction_shape(case,prediction);valid=True
    except (ValueError,KeyError,TypeError,OverflowError) as exc:errors.append(str(exc))
    result={'sample_id':case['sample_id'],'root_id':case['root_id'],'source_cluster':case['source_cluster'],'condition':case['condition'],
            'intervention_hop':case['intervention_hop'],'expected_answerable':case['expected_answerable'],'prediction_status':prediction.get('status','malformed') if isinstance(prediction,dict) else 'missing',
            'prediction_valid':valid,'answer_em':None,'support_f1':None,'strict_sr':None,'path_cfs':None,'correct_refusal':None,'contract_success':0,'diagnostics':errors,'partial_fact_semantics':None,'raw_prediction':raw_diagnostic(prediction)}
    if not isinstance(result['prediction_status'],str):result['prediction_status']='malformed'
    if case['expected_answerable']:
        metric=score_sample(case['reference'],prediction if valid else None)
        result.update({key:metric[key] if valid else 0 for key in ('answer_em','support_f1','strict_sr','path_cfs')})
        result['contract_success']=result['strict_sr'];result['diagnostics']+=metric['diagnostics']
    else:
        correct=int(valid and prediction['status']=='abstain' and prediction['answer'] is None and len(prediction['submitted_steps'])<case['hop_count'])
        result['correct_refusal']=correct;result['contract_success']=correct
        if valid and not correct:result['diagnostics'].append('requires_abstain_null_and_short_prefix')
        # Semantic truth of a partial claim is diagnostic, not refusal condition.
        # Avoid treating the original complete-world graph as a missing-case gold.
        if valid and model_input is not None:
            from .baseline import extract
            facts=extract(model_input['documents'])
            matched=[]
            for step in prediction['submitted_steps']:
                relevant=[f for f in facts if all((normalize(f[k])==normalize(step[k]) if k in ('head','tail') else f[k]==step[k]) for k in ('head','relation','tail','qualifier'))]
                supported=set().union(*(refs(f['evidence']) for f in relevant)) if relevant else set()
                matched.append(refs(step['evidence'])<=supported)
            result['partial_fact_semantics']={'steps_supported_by_current_facts':matched,'all_steps_supported':all(matched),'complete_proof_scored':False}
    return result


def strict_json_loads(text):
    """Shared CLI/HTTP JSON boundary: unique keys and finite numeric tokens."""
    def pairs(values):
        result={}
        for key,value in values:
            require(key not in result,'duplicate JSON object key');result[key]=value
        return result
    def constant(value):raise ValueError('non-finite JSON constant: '+value)
    def finite_float(value):
        parsed=float(value)
        require(math.isfinite(parsed),'non-finite JSON float: '+value)
        return parsed
    return json.loads(text,object_pairs_hook=pairs,parse_constant=constant,parse_float=finite_float)


def read_submission(path):
    """Strict JSONL: never infer an identity for unparseable records."""
    rows=[]
    for number,line in enumerate(Path(path).read_bytes().decode('utf-8-sig').splitlines(),1):
        if not line.strip():continue
        try:row=strict_json_loads(line)
        except (ValueError,json.JSONDecodeError) as exc:raise ValueError(f'controlled submission line {number}: {exc}') from exc
        require(isinstance(row,dict),'controlled submission record must be an object');rows.append(row)
    return rows


def check_output(output,root,submission=None):
    """Freeze every lexical target and identity before any output mkdir/write.

    Reject all existing links/reparse ancestors, pairwise output aliases, and
    aliases of necessary inputs. Does not claim protection against a concurrent
    process intentionally changing the filesystem after this preflight.
    """
    root=Path(root).resolve();lexical=Path(os.path.abspath(output))
    target_files=[lexical] if submission is not None else [lexical/name for name in RUN_FILES]
    for target in target_files:
        for ancestor in (target,*target.parents):
            try:info=ancestor.lstat()
            except FileNotFoundError:continue
            require(not (stat.S_ISLNK(info.st_mode) or getattr(info,'st_file_attributes',0)&getattr(stat,'FILE_ATTRIBUTE_REPARSE_POINT',1024)),'controlled target or ancestor is a link/reparse point')
            if ancestor==target:require(stat.S_ISREG(info.st_mode),'controlled output member must be a regular file')
            else:require(stat.S_ISDIR(info.st_mode),'controlled target ancestor must be a directory')
    output=lexical.resolve()
    try:relative=output.relative_to(root)
    except ValueError:relative=None
    if relative is not None:
        require(not any(part in ('.git','.venv','__pycache__','.pytest_cache','.ruff_cache','private') for part in relative.parts),'controlled output inside project private/runtime cache')
    protected=[root/folder for folder in ('data','src','scripts','schemas','resources','examples','docs/plan/draft/source-snapshots')]
    require(output!=root and output not in root.parents and not any(output==p.resolve() or p.resolve() in output.parents for p in protected),'controlled output overlaps frozen source/code/schema or project ancestor')
    if submission is not None:require(output!=Path(submission).resolve(),'controlled output overlaps original submission')
    # Existing aliases can be hardlinks even when resolved paths differ.
    targets=[p.resolve() for p in target_files]
    for a,b in combinations(targets,2):
        require(a!=b and a not in b.parents and b not in a.parents,'controlled output targets conflict')
        if a.exists() and b.exists():require(not a.samefile(b),'controlled output targets alias the same file')
    existing=[p for p in targets if p.exists()]
    if existing:
        source_files=[p for folder in protected if folder.exists() for p in folder.rglob('*') if p.is_file()]
        source_files += [root/name for name in ('README.md','AGENTS.md','pyproject.toml','uv.lock','.gitattributes') if (root/name).exists()]
        if submission is not None:source_files.append(Path(submission))
        for target in existing:
            require(not any(target.samefile(source) for source in source_files),'controlled output member aliases protected input')
    return output


def evaluate_controlled(inputs,reference,predictions):
    validate_reference(inputs,reference)
    require(isinstance(predictions,list),'controlled predictions must be a list')
    known={c['sample_id'] for c in reference['cases']};indexed={}
    for prediction in predictions:
        require(isinstance(prediction,dict) and isinstance(prediction.get('sample_id'),str) and prediction['sample_id'] in known,'unknown_or_unidentifiable_controlled_prediction')
        require(prediction['sample_id'] not in indexed,'duplicate_controlled_prediction');indexed[prediction['sample_id']]=prediction
    public={i['sample_id']:i for i in inputs}
    scored=[score_case(case,indexed.get(case['sample_id']),public[case['sample_id']]) for case in reference['cases']]
    def summary(items):
        roots=defaultdict(list)
        for item in items:roots[item['root_id']].append(item)
        fields=['contract_success']+(['answer_em','support_f1','strict_sr','path_cfs'] if items and items[0]['expected_answerable'] else ['correct_refusal'])
        return {'cases':len(items),'roots':len(roots),'successes':sum(i['contract_success'] for i in items),
                'raw_micro':{f:average([i[f] for i in items]) for f in fields},
                'root_macro':{f:average([average([i[f] for i in members]) for members in roots.values()]) for f in fields}}
    by_condition={condition:summary([r for r in scored if r['condition']==condition]) for condition in CONDITIONS}
    root_contract=[];bridge=[]
    for world in reference['worlds']:
        root=world['root_id'];members=[s for s in scored if s['root_id']==root]
        condition_means={c:average([s['contract_success'] for s in members if s['condition']==c]) for c in CONDITIONS}
        root_contract.append({'root_id':root,'condition_means':condition_means,'contract_success':average(list(condition_means.values()))})
        full=next(s for s in members if s['condition']=='full');fullcase=next(c for c in reference['cases'] if c['sample_id']==full['sample_id'])
        for reroute in (s for s in members if s['condition']=='internal-reroute'):
            reroutecase=next(c for c in reference['cases'] if c['sample_id']==reroute['sample_id'])
            targets_differ=fullcase['reference']['answer']['text']!=reroutecase['reference']['answer']['text']
            bridge.append({'root_id':root,'full_id':full['sample_id'],'reroute_id':reroute['sample_id'],'intervention_hop':reroute['intervention_hop'],
                           'targets_differ':targets_differ,'success':int(full['strict_sr']==1 and reroute['strict_sr']==1 and targets_differ)})
    bridge_roots=defaultdict(list)
    for pair in bridge:bridge_roots[pair['root_id']].append(pair['success'])
    return {'schema_version':'controlled-score-1','profile':PROFILE,'kind':'controlled_diagnostic_not_benchmark_or_llm_accuracy',
            'counts':{'cases':46,'predictions':len(predictions),'missing':46-len(predictions),'roots':6,'source_topology_clusters':3,'answerable':23,'insufficient':23},
            'by_condition':by_condition,'answerable':summary([s for s in scored if s['expected_answerable']]),'insufficient':summary([s for s in scored if not s['expected_answerable']]),
            'contract_success':{'definition':'within each root: full, shuffle, reroute k mean, delete k mean, no-context equally weighted; then macro over six roots',
                                'root_macro':average([r['contract_success'] for r in root_contract]),'raw_micro':average([s['contract_success'] for s in scored]),'successes':sum(s['contract_success'] for s in scored),'per_root':root_contract},
            'bridge_sensitivity':{'definition':'both full and each reroute StrictSR=1 and reference targets differ; all eleven pairs kept; mean k then root',
                                  'pairs':11,'successes':sum(p['success'] for p in bridge),'raw_micro':average([p['success'] for p in bridge]),
                                  'root_macro':average([average(v) for v in bridge_roots.values()]),'per_pair':bridge},
            'model_metrics':None,'human_semantic_review':'pending','official_samples':0,'per_case':scored,'raw_predictions':[raw_diagnostic(p) for p in predictions]}


def build_controlled(root,output=None):
    from .controlled_generation import construct
    from .io import read_jsonl
    from .pilot import write_json,write_jsonl,sha_bytes
    root=Path(root);destination=Path(output) if output else root/'data/controlled'
    require(destination.resolve()!=root.resolve() and destination.resolve()!= (root/'data/pilot').resolve(),'unsafe controlled construction destination')
    inputs,reference=construct(read_jsonl(root/'data/pilot/samples.jsonl'))
    validate_reference(inputs,reference)
    encoded={'inputs.jsonl':strict_json_bytes(inputs,jsonl=True),'reference.json':strict_json_bytes(reference)}
    manifest={'schema_version':'controlled-construction-1','profile':PROFILE,'generator':reference['generator'],'salt':reference['salt'],
              'source_samples_sha256':sha_bytes((root/'data/pilot/samples.jsonl').read_bytes()),'files':{name:sha_bytes(encoded[name]) for name in ('inputs.jsonl','reference.json')},
              'generator_code_sha256':sha_bytes((root/'src/bridgeqa/controlled_generation.py').read_bytes()),'schema_validation':'runtime_contract_checks','counts':COUNTS,
              'disclosure':'all facts synthetic; source mapping/reference excluded from predictor; six families, three source topology clusters; no human certification'}
    encoded['construction-manifest.json']=strict_json_bytes(manifest)
    destination.mkdir(parents=True,exist_ok=True)
    for name,body in encoded.items():(destination/name).write_bytes(body)
    return {'inputs':inputs,'reference':reference,'manifest':manifest}


def audit_controlled(root):
    from .controlled_generation import construct
    from .io import read_jsonl
    from .pilot import sha_bytes,audit_pilot
    root=Path(root);directory=root/'data/controlled'
    source_audit=audit_pilot(root)
    inputs=read_jsonl(directory/'inputs.jsonl');reference=json.loads((directory/'reference.json').read_text(encoding='utf-8'))
    manifest=json.loads((directory/'construction-manifest.json').read_text(encoding='utf-8'))
    result=validate_reference(inputs,reference)
    require(manifest['schema_version']=='controlled-construction-1' and manifest['profile']==PROFILE,'controlled construction manifest version')
    require(set(manifest['files'])=={'inputs.jsonl','reference.json'},'controlled manifest file set')
    for name,hash_value in manifest['files'].items():require(sha_bytes((directory/name).read_bytes())==hash_value,'controlled frozen file hash mismatch')
    require(manifest['source_samples_sha256']==sha_bytes((root/'data/pilot/samples.jsonl').read_bytes()),'controlled parent source hash mismatch')
    require(manifest['generator_code_sha256']==sha_bytes((root/'src/bridgeqa/controlled_generation.py').read_bytes()),'controlled generator code hash mismatch')
    replay_inputs,replay_reference=construct(read_jsonl(root/'data/pilot/samples.jsonl'))
    require(inputs==replay_inputs and reference==replay_reference,'controlled source-derived construction replay mismatch')
    return {**result,'source_replay':'exact','source_replay_scope':'validated current pilot parents to synthetic construction; not access-event or semantic certification',
            'source_audit':source_audit,'source_integrity':'verified against fixed original/derived/access/resource anchors; no file-operation history claim','frozen_file_hashes':manifest['files']}


def run_controlled(output,root):
    from .baseline import predict,ALGORITHM
    from .io import read_jsonl
    from .pilot import write_json,write_jsonl,sha_bytes
    root=Path(root);output=check_output(output,root);source=(root/'data/controlled').resolve()
    audit=audit_controlled(root)
    inputs=read_jsonl(source/'inputs.jsonl');reference=json.loads((source/'reference.json').read_text(encoding='utf-8'))
    # Only safe inputs cross this prediction boundary.
    predictions=[predict(row,ALGORITHM+'-controlled') for row in inputs]
    score=evaluate_controlled(inputs,reference,predictions)
    encoded={'inputs.jsonl':strict_json_bytes(inputs,jsonl=True),'reference.json':strict_json_bytes(reference),'predictions.jsonl':strict_json_bytes(predictions,jsonl=True),
             'score.json':strict_json_bytes(score),'audit.json':strict_json_bytes(audit)}
    code_files=sorted((root/'src/bridgeqa').glob('*.py'))+sorted((root/'scripts').glob('*.py'))
    schema_files=sorted((root/'schemas/controlled').glob('*.json'))+[root/'schemas/v0.2/model-input.schema.json',root/'schemas/v0.2/prediction.schema.json',root/'schemas/v0.2/sample.schema.json']
    manifest={'schema_version':'controlled-run-1','profile':PROFILE,'algorithm':ALGORITHM,'kind':'actual_public_rule_not_llm',
              'run_at':datetime.now(timezone.utc).isoformat(),'model':None,'records':46,'roots':6,'source_topology_clusters':3,'status_counts':dict(Counter(p['status'] for p in predictions)),
              'source_files':{p.relative_to(root).as_posix():sha_bytes(p.read_bytes()) for p in [source/'inputs.jsonl',source/'reference.json',source/'construction-manifest.json',root/'data/pilot/samples.jsonl']},
              'code_sha256':stable_hash({p.relative_to(root).as_posix():sha_bytes(p.read_bytes()) for p in code_files}),
              'schema_files':{p.relative_to(root).as_posix():sha_bytes(p.read_bytes()) for p in schema_files},
              'files':{name:sha_bytes(encoded[name]) for name in ('inputs.jsonl','reference.json','predictions.jsonl','score.json','audit.json')},
              'separate_from_candidate_fixture_oracle':True,'human_review':'pending','official_samples':0}
    encoded['run-manifest.json']=strict_json_bytes(manifest)
    output.mkdir(parents=True,exist_ok=True)
    for name in RUN_FILES:(output/name).write_bytes(encoded[name])
    return {'inputs':inputs,'reference':reference,'predictions':predictions,'score':score,'manifest':manifest,'audit':audit}
