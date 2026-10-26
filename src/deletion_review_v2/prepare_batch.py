"""Versioned material jobs and explicitly synthetic audit challenges; see README."""
import copy
import hashlib
import json
from pathlib import Path

from experiment import ROOT, read, save_new_or_same, digest

WORK=ROOT/'workspace/deletion-review-v2'
RUNTIME=ROOT/'workspace/harness-prototype/runs/deletion-review-v2-20261022'
MATERIAL_PROMPT='''你是古白话材料现代化译写员。只根据输入原文完整译写，不概述，不改成事实清单。保留人物说话者、指代、关系、条件、否定、数量和叙事细节，不用红楼梦百科，不补父母或派生亲属称谓，不提供解题解释。每个原文单元恰好一条且同ID。别名若原文没有明确对应就保留原称，不猜补全名。口语与一般句法须现代化，保留专名。只输出符合schema的JSON。'''
MATERIAL_SCHEMA={'type':'object','properties':{'units':{'type':'array','items':{'type':'object','properties':{'unit_id':{'type':'string'},'text':{'type':'string'},'issues':{'type':'array','items':{'type':'string'}}},'required':['unit_id','text','issues'],'additionalProperties':False}}},'required':['units'],'additionalProperties':False}


def material_jobs(discovery):
    units=discovery['materials']
    jobs=[]
    for offset in range(0,len(units),3):
        group=units[offset:offset+3]
        jobs.append({'name':'modernize-'+str(offset//3+1),'role':'modernizer',
                     'payload':{'units':[{'unit_id':u['unit_id'],'original_text':u['text']} for u in group]},
                     'schema':MATERIAL_SCHEMA,'prompt':MATERIAL_PROMPT})
    task={'output':RUNTIME.relative_to(ROOT).as_posix()+'/materials','max_tokens':10000,'jobs':jobs}
    save_new_or_same(WORK/'material-jobs.json',task)
    return task


def material_review_jobs():
    discovery=read(WORK/'source-discovery.json')
    modern={u['unit_id']:u for p in (RUNTIME/'materials/calls').glob('*.parsed.json') for u in read(p)['units']}
    schema={'type':'object','properties':{'verdict':{'enum':['pass','revise','needs_context']},'issues':{'type':'array','items':{'type':'object','properties':{'unit_id':{'type':'string'},'problem':{'type':'string'},'source_quote':{'type':'string'},'modern_quote':{'type':'string'}},'required':['unit_id','problem','source_quote','modern_quote'],'additionalProperties':False}}},'required':['verdict','issues'],'additionalProperties':False}
    prompt='独立对照原文与译文，只核验事实保持、现代汉语程度、完整性、说话者和引号归属。不要凭作品知识。不能把妻子生子扩为丈夫亲生，不补姓名或派生关系。保留古白话短语、说话者引号错位、新增原文没有的关系均应指出。输出JSON，pass必须无实质问题，机器通过不代表人工。'
    jobs=[]
    for i in range(0,len(discovery['materials']),3):
        group=discovery['materials'][i:i+3]
        jobs.append({'name':'material-review-'+str(i//3+1),'role':'material-supervisor','schema':schema,'prompt':prompt,
                     'payload':{'units':[{'unit_id':u['unit_id'],'original_text':u['text'],'modern_text':modern[u['unit_id']]['text']} for u in group]}})
    task={'output':RUNTIME.relative_to(ROOT).as_posix()+'/material-reviews','max_tokens':6500,'jobs':jobs}
    save_new_or_same(WORK/'material-review-jobs.json',task)
    return task


def freeze_material_draft():
    discovery=read(WORK/'source-discovery.json')
    modern={u['unit_id']:u for p in (RUNTIME/'materials-revision1/calls').glob('*.parsed.json') for u in read(p)['units']}
    replacements={'一味好道':'一心修道','一味高乐个没完':'只顾寻欢作乐',
                  '十四岁进学':'十四岁就取得了生员资格','一落胎胞':'刚一出生',
                  '递上遗本':'递上临终奏章','即时令长子袭官之外':'除了立即让长子承袭官职以外',
                  '其余的才从了‘春’字':'其余的人才跟着用了‘春’字',
                  '将来之东床如何呢':'将来的女婿会怎么样呢',
                  '怎么贾府也乐意套这俗套':'为什么贾府也喜欢用这个俗套',
                  '也都从男子之名命字':'也都按照男子名字所用的字来取名',
                  '赦老爹前妻所出':'赦老爹的前妻生的','政老爹的庶出':'政老爹的妾生的女儿',
                  '侥幸留下一个儿子':'幸好留下一个儿子',
                  '太监传出去到外厢':'太监传到外面的厢房',
                  '你说这是不是新奇事':'你说这是不是新奇怪异的事'}
    records=[]
    for source in discovery['materials']:
        u=copy.deepcopy(source);body=modern[u['unit_id']]['text'];edits=[]
        for old,new in replacements.items():
            if old in body:
                body=body.replace(old,new);edits.append({'before':old,'after':new})
        u.update(original_text=u.pop('text'),text=body,modern_sha256=hashlib.sha256(body.encode()).hexdigest(),
                 translation_authorship={'initial':'DeepSeek Flash via Harness','revision1':'DeepSeek Flash via Harness',
                                        'revision2':'root GPT targeted modernization edits','edits':edits},
                 review_status='pending_independent_material_review')
        records.append(u)
    save_new_or_same(WORK/'materials.gpt-draft-v2.json',records)
    groups=[records[i:i+3] for i in range(0,len(records),3)]
    schema={'type':'object','properties':{'verdict':{'enum':['pass','revise','needs_context']},'issues':{'type':'array','items':{'type':'object','properties':{'unit_id':{'type':'string'},'problem':{'type':'string'},'source_quote':{'type':'string'},'modern_quote':{'type':'string'}},'required':['unit_id','problem','source_quote','modern_quote'],'additionalProperties':False}}},'required':['verdict','issues'],'additionalProperties':False}
    jobs=[{'name':'frozen-material-review-'+str(i+1),'role':'material-supervisor','schema':schema,
           'prompt':'对照原文与现代文，独立检查事实、范围、说话者、数量、现代化及完整性。术语可保留，语体替换不是新增事实；不得凭作品常识补关系。不要因作者是谁放行或误拒。问题必须指出实际差异；pass时issues为空。',
           'payload':{'units':[{'unit_id':u['unit_id'],'original_text':u['original_text'],'modern_text':u['text']} for u in group]}} for i,group in enumerate(groups)]
    save_new_or_same(WORK/'frozen-material-review-jobs.json',{'output':RUNTIME.relative_to(ROOT).as_posix()+'/frozen-material-reviews','jobs':jobs,'max_tokens':6500})
    target_pairs=[f['proposed_chain'] for f in discovery['families']]
    origins=[{'name':'origin-all-source','role':'origin','schema':__import__('experiment').SCHEMAS['origin'],
              'prompt':'你是Origin，只从冻结现代文提取明确的直接父母事实。人物ID稳定，实体别名只能由给定文本消解。每条事实保留单元的原始assertion_scope，不能将叙述者/黛玉回忆重标为子兴发言。不得从丈夫与妻生子推断父亲。每个证据组需共同含父母与孩子的具名或可核验别名及先行词，可用多段引文共同支持；不能把仅含代词的一句作为独立支持组。优先找desired_chains直接涉及的父母边。不要提取派生祖父母关系，不借百科补人物。输出正式Origin JSON。',
              'payload':{'materials':[{'unit_id':u['unit_id'],'text':u['text'],'assertion_scope':u['assertion_scope']} for u in records],
                         'desired_chains':target_pairs,'budget':'最多16条父母事实，支持不明确就放warnings，不凑数。'}}]
    save_new_or_same(WORK/'origin-jobs.json',{'output':RUNTIME.relative_to(ROOT).as_posix()+'/construction','jobs':origins,'max_tokens':16000})
    return records


def fictional_fact(fid,p,c,quote,role='father',scope='虚构档案'):
    return {'id':fid,'parent':p,'child':c,'parent_role':role,'scope':scope,'expression':'direct',
            'evidence_sets':[[{'unit_id':'T','quote':quote}]]}


def synthetic_challenges():
    """Twelve controlled pairs; expected labels live only in separate references."""
    cases=[];refs={}
    categories=['missing_support','redundant_support','alternative_proof','quote_only_failure',
                'scope_mixing','direction','coreference','direct_answer_shortcut',
                'wrong_answer','wrong_status','wrong_evidence','irrelevant_deletion']
    for number,category in enumerate(categories,1):
        suffix=str(number)
        a,b,c,d='甲'+suffix,'乙'+suffix,'丙'+suffix,'丁'+suffix
        q1=f'{b}是{c}的父亲。';q2=f'{a}是{b}的父亲。'
        neutral=f'{c}正在读书。';weather='院墙旁开着白花。'
        text=q1+q2+neutral+weather
        facts=[fictional_fact('F1',b,c,q1),fictional_fact('F2',a,b,q2)]
        good={'question':f'根据虚构档案，{c}的父亲的父亲是谁？',
              'materials':[{'unit_id':'T','text':text}], 'facts':facts,
              'proposed_answer':[a],'proposed_status':'answerable',
              'proof':[{'from':c,'relation':'father','to':b,'quote':q1},
                       {'from':b,'relation':'father','to':a,'quote':q2}],
              'declared_conditions':{'review_scope':'single_item','task_requires_two_steps':True}}
        bad=copy.deepcopy(good)
        evidence=q1
        if category=='missing_support':
            good['materials'][0]['text']=text.replace(q1,'');good['facts']=facts[1:]
            good.update(proposed_answer=[],proposed_status='insufficient_evidence',proof=[])
            bad['materials'][0]['text']=good['materials'][0]['text']
        elif category=='redundant_support':
            duplicate=f'{c}的父亲名叫{b}。'
            for item in (good,bad):
                item['materials'][0]['text']=text.replace(q1,'')+duplicate
                item['facts'][0]['evidence_sets']=[[{'unit_id':'T','quote':duplicate}]]
                item['proof'][0]['quote']=duplicate
                item['declared_conditions']['deleted_original_support']=q1
            bad.update(proposed_answer=[],proposed_status='insufficient_evidence',proof=[])
            evidence=duplicate
        elif category=='alternative_proof':
            # Distinct parent chains, not merely duplicate wording of one fact.
            alt=f'{d}是{c}的母亲。';alt2=f'{a}是{d}的父亲。'
            for item in (good,bad):
                item['question']=f'根据虚构档案，{c}的父母之一的父亲是谁？'
                item['materials'][0]['text']=q2+alt+alt2+neutral+weather
                item['facts']=[facts[1],fictional_fact('F3',d,c,alt,'mother'),fictional_fact('F4',a,d,alt2)]
                item['proof']=[{'from':c,'relation':'mother','to':d,'quote':alt},{'from':d,'relation':'father','to':a,'quote':alt2}]
                item['declared_conditions'].update(deleted_original_support=q1,original_material=text+alt+alt2)
            bad.update(proposed_answer=[],proposed_status='insufficient_evidence',proof=[])
            evidence=alt+alt2
        elif category=='quote_only_failure':
            # Removal breaks an over-wide annotation, not the relation sentence.
            for item in (good,bad):
                item['materials'][0]['text']=text.replace(weather,'')
                item['declared_conditions'].update(deleted_text=weather,old_annotation=q1+q2+neutral+weather)
            bad.update(proposed_answer=[],proposed_status='insufficient_evidence',proof=[])
        elif category=='scope_mixing':
            for item in (good,bad):
                item['materials'][0]['text']=f'叙述者确认：{q1}{b}的梦中有人说：“{q2}”'+neutral
                item['facts'][1]['scope']='梦境'
                item['declared_conditions']['query_scope']='现实叙述，不采用梦境'
                item['question']=f'只根据现实叙述、不采用梦境，{c}的父亲的父亲是谁？'
            good.update(proposed_answer=[],proposed_status='insufficient_evidence',proof=[])
        elif category=='direction':
            bad['facts'][0]['parent'],bad['facts'][0]['child']=c,b
            bad['proof'][0].update(to=c,**{'from':b})
        elif category=='coreference':
            bad['materials'][0]['text']=f'{d}来到屋内。他是{c}的父亲。'+q2+neutral
            good['materials'][0]['text']=f'{b}来到屋内。他是{c}的父亲。'+q2+neutral
            good['facts'][0]['evidence_sets']=[[{'unit_id':'T','quote':f'{b}来到屋内。他是{c}的父亲。'}]]
            good['proof'][0]['quote']=f'{b}来到屋内。他是{c}的父亲。'
            good['facts'][0]['expression']='coreference'
            evidence=f'{d}来到屋内。'
        elif category=='direct_answer_shortcut':
            bad['materials'][0]['text']+=f'{c}的父亲的父亲就是{a}。'
            evidence=f'{c}的父亲的父亲就是{a}。'
        elif category=='wrong_answer':bad['proposed_answer']=[d]
        elif category=='wrong_status':bad.update(proposed_answer=[],proposed_status='insufficient_evidence',proof=[])
        elif category=='wrong_evidence':bad['proof'][0]['quote']=weather
        elif category=='irrelevant_deletion':
            for item in (good,bad):
                item['materials'][0]['text']=text.replace(weather,'')
                item['declared_conditions']['deleted_text']=weather
            bad.update(proposed_answer=[],proposed_status='insufficient_evidence',proof=[])
        for offset,candidate in enumerate((good,bad)):
            cid='K'+str(1000+number*2+offset)
            cases.append({'case_id':cid,'family_id':'SYN-'+str(number),'track':'synthetic',
                          'candidate':candidate,'rationale':'构造者声明：所列答案、证据与多跳要求均已核对，变换不会带来非预期支持。请仍独立核验。',
                          'external_relation_hints':{}})
            positive_evidence=(candidate['materials'][0]['text'] if category=='missing_support' else
                               f'{b}来到屋内。他是{c}的父亲。' if category=='coreference' else q1 if category=='direct_answer_shortcut' else evidence)
            refs[cid]={'expected_verdict':'pass' if offset==0 else 'revise','status':'pending',
                       'major_defect':bool(offset),'defect_category':'none' if offset==0 else category,
                       'evidence':positive_evidence if offset==0 else evidence,'track':'synthetic','reference_author':'root_GPT_draft_pending_independent_audit'}
    return cases,refs


if __name__=='__main__':
    import argparse
    p=argparse.ArgumentParser();p.add_argument('action',choices=['materials','material-review','freeze-material-draft','synthetic']);args=p.parse_args()
    if args.action=='materials':print(len(material_jobs(read(WORK/'source-discovery.json'))['jobs']))
    elif args.action=='material-review':print(len(material_review_jobs()['jobs']))
    elif args.action=='freeze-material-draft':print(len(freeze_material_draft()))
    else:
        cases,refs=synthetic_challenges()
        save_new_or_same(WORK/'synthetic-cases.draft-v3.json',cases)
        save_new_or_same(WORK/'synthetic-references.draft-v3.json',refs)
        print(len(cases))
