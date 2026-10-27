"""Public, answer-free task projection. [Contract](specs/11_全量题库与最新关系题发布.md)."""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
from site_data import PROJECT, load_bundle

OUT = PROJECT / 'explorer/publication_v25'
SOURCES = []
def read(path):
    p = PROJECT / path
    SOURCES.append({'path':path,'sha256':hashlib.sha256(p.read_bytes()).hexdigest()})
    return json.loads(p.read_text(encoding='utf-8'))
def lines(path):
    p = PROJECT / path
    SOURCES.append({'path':path,'sha256':hashlib.sha256(p.read_bytes()).hexdigest()})
    return [json.loads(x) for x in p.read_text(encoding='utf-8').splitlines() if x.strip()]
def digest(value):
    return hashlib.sha256(json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode()).hexdigest()
def save(name,value):
    (OUT/name).write_text(json.dumps(value,ensure_ascii=False,separators=(',',':'))+'\n',encoding='utf-8')

def build():
    OUT.mkdir(exist_ok=True)
    cases=[]
    cohorts=[
        {'id':'v24','title':'最新 · 复杂嵌套与一致换名','count':24,'new_mothers':8,'variants':16,'note':'8个新增母题、16个部分换名变体。四个串行母题，其余为汇合、比较或双分支结构。'},
        {'id':'v23','title':'五类对抗与独立单跳','count':49,'new_mothers':1,'variants':18,'note':'主19＝1新增母题原题＋18变体；另诊断6、独立正确上游单跳24。主任务覆盖4个语义母题组。'},
        {'id':'v21','title':'自然目标与材料控跳','count':16,'new_mothers':3,'variants':13,'note':'3个新增母题原题＋13变体；覆盖5个语义母题组，部分复用既有母题。'},
        {'id':'v20','title':'来源关系图与多种结构','count':18,'new_mothers':9,'variants':9,'note':'9个新增母题、9个来源干扰／重排变体。'},
        {'id':'v18','title':'多领域合成开发题库','count':252,'note':'142主任务、48节点、12状态对照；另16修订、30新算子、4边界。历史结构声明不等于必要跳数认证。'},
        {'id':'v2','title':'第二版 · 红楼梦','count':57,'note':'10个来源家族、57个成员。支持合同需复核的开发展示版。'},
        {'id':'v0','title':'第一版 · 文学与历史','count':86,'note':'历史文学／历史对抗候选集；家族数量不作为独立母题数。'},
    ]
    def add(cohort,identity,inp,**meta):
        cases.append(dict(key=cohort+':'+identity,case_id=identity,cohort=cohort,input=inp,input_sha256=digest(inp),**meta))
    for cohort,ds in [('v0','pilot_literature_history_v0'),('v2','multi_agent_hongloumeng_v2')]:
        for r in load_bundle(ds)['records']:
            add(cohort,r['id'],r['input'],kind='historical',mother=r['family_id'],condition=r['variant'],structure='historical',domain=r['domain'],legacy_dataset=ds)
    for q in read('explorer/publication_v18/questions.public.json')['cases']:
        add('v18',q['question_key'],q['input'],kind=q['partition'],mother=q['metadata']['family_id'],condition=q['metadata'].get('condition',''),structure='synthetic',domain=q['metadata']['domain'],legacy_key=q['question_key'],phase=q['phase'],relation_dependencies=q['metadata'].get('declared_hops'))
    refs={r['case_id']:r for r in lines('data/graph_pilot_v20/final-r1/references.jsonl')}
    for r in lines('data/graph_pilot_v20/final-r1/public_inputs.jsonl'):
        ref=refs[r['case_id']]
        add('v20',r['case_id'],r,kind='variant' if ref['variant_of'] else 'mother',mother=ref['mother_candidate_id'],condition=ref['condition'],structure=ref['structure'],domain='文学',relation_dependencies=ref['draft_relation_dependencies'],serial_depth=ref['draft_path_depth'])
    for cohort,inp,reg in [
        ('v21','data/natural_goal_v21/draft-r3/public_inputs.jsonl','data/natural_goal_v21/mother_registry-r1.json'),
        ('v23','data/adversarial_axes_v23/draft-r2/public_all_inputs.jsonl','data/adversarial_axes_v23/mother_registry-r2.json'),
        ('v24','data/nested_relations_v24/final-r2/public_inputs.jsonl','data/nested_relations_v24/final-r2/mother_registry.json')]:
        registry=read(reg); members={x['case_id']:x for x in registry['members']}
        mothers={m['mother_id']:m for m in registry.get('mothers',[])}
        for r in lines(inp):
            m=members[r['id']]; partition=m.get('partition','')
            kind=('local' if partition in ['local_probe','independent_correct_upstream_probe','local'] or m.get('hop_index') is not None else 'diagnostic' if 'diagnostic' in partition else 'mother' if m['record_kind'] in ['new_mother_original','new_mother_seed','new_mother'] else 'variant')
            mother=m.get('mother_id',m.get('semantic_mother_id',''))
            shape=m.get('structure',mothers.get(mother,{}).get('shape','natural_goal'))
            add(cohort,r['id'],r,kind=kind,mother=mother,condition=m.get('condition',m.get('material_condition','')),structure=shape,domain='文学',relation_dependencies=m.get('relation_dependencies',m.get('minimum_relation_dependencies')),serial_depth=m.get('serial_depth',m.get('maximum_serial_depth')),axes=m.get('axes',[]))
    # Latest first answers: copy only visible final text and adopted, explicit diagnostics.
    selection=read('workspace/nested-relations-v24/luna-final-r2/selection.json')
    review=read('workspace/nested-relations-v24/post-review-r2/review.json')
    by_id={x['case_id']:x for x in review['records']}; results=[]
    for s in selection['records']:
        r=by_id[s['case_id']]
        raw=None if s['status']!='completed' else read(s['response']['path'])['final_response']
        results.append({'key':'v24:'+s['case_id'],'case_id':s['case_id'],'model':'gpt-6-luna','status':s['status'],'raw_response':raw,'raw_text_sha256':hashlib.sha256(raw.encode()).hexdigest() if raw is not None else None,'endpoint_success':r['endpoint_success'],'rationale':r['endpoint_rationale'],'progress':r['observed_progress'],'contract':r['contract_diagnostics'],'proof_diagnostics':r['proof_diagnostics']})
    catalog={'format_version':1,'date':'2026-10-27','cohorts':cohorts,'cases':cases,'counting_note':'502条历史与当前输入记录，含变体和诊断；不代表502个独立母题。批次间母题共享，全库独立母题总数未认证。'}
    result={'format_version':1,'records':results,'counts':{'planned':24,'completed':23,'correct':17,'incorrect':4,'semantic_unknown':2,'technical_missing':1}}
    verify(catalog,result)
    save('catalog.json',catalog);save('luna.json',result)
    save('manifest.json',{'format_version':1,'sources':SOURCES,'outputs':{name:hashlib.sha256((OUT/name).read_bytes()).hexdigest() for name in ['catalog.json','luna.json']},'private_reference_files_published':False})
    print(json.dumps({'records':len(cases),'cohorts':{c['id']:c['count'] for c in cohorts},'luna':result['counts']},ensure_ascii=False))

def verify(catalog,result):
    cases=catalog['cases']; assert len(cases)==502
    assert len({q['key'] for q in cases})==502
    allowed={'key','case_id','cohort','input','input_sha256','kind','mother','condition','structure','domain','legacy_dataset','legacy_key','phase','relation_dependencies','serial_depth','axes'}
    for q in cases:
        assert set(q)<=allowed and digest(q['input'])==q['input_sha256']
        assert q['input']['question']
    for cohort in catalog['cohorts']:
        assert sum(q['cohort']==cohort['id'] for q in cases)==cohort['count']
    rs=result['records']; assert len(rs)==24
    assert sum(r['endpoint_success'] is True for r in rs)==17
    assert sum(r['endpoint_success'] is False for r in rs)==4
    assert sum(r['status']=='technical_failure' for r in rs)==1
    assert sum(r['status']=='completed' and r['endpoint_success'] is None for r in rs)==2
    for r in rs:
        assert r['key'] in {q['key'] for q in cases}
        if r['raw_response'] is not None:assert hashlib.sha256(r['raw_response'].encode()).hexdigest()==r['raw_text_sha256']
    assert not any(q['case_id'] in ['q-274cc1fa0b119eff','q-00799e1ec021','q-89fe0f975a93'] for q in cases)

if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('--verify-existing',action='store_true');args=ap.parse_args()
    if args.verify_existing:
        verify(json.loads((OUT/'catalog.json').read_text(encoding='utf-8')),json.loads((OUT/'luna.json').read_text(encoding='utf-8')))
        print('502 public inputs and 24 Luna slots verified')
    else:build()
