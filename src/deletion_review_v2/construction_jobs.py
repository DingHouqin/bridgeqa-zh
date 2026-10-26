"""Constrained role proposals and independent protocol debug jobs.

Run this file to build manifests; no network requests are performed here.
"""
import copy
from experiment import ROOT, read, save_new_or_same, REVIEW_PROMPT, SCHEMAS, digest
from review_cases import project_review

WORK = ROOT / 'workspace/deletion-review-v2'
RUNTIME = 'workspace/harness-prototype/runs/deletion-review-v2-20261022'


def object_schema(properties):
    return {'type':'object','properties':properties,'required':list(properties),'additionalProperties':False}


STR = {'type':'string'}
STRINGS = {'type':'array','items':STR}
COMPOSER_SCHEMA = object_schema({'question':STR,'rationale':STR,'issues':STRINGS})
DIFFICULT_SCHEMA = object_schema({'mechanism':STR,'reason':STR,'risks':STRINGS,'issues':STRINGS})


def construction_jobs():
    families = read(WORK / 'source-families.draft-v4.json')
    packets = {p['family_id']:p for p in read(WORK / 'source-packets.draft-v4.json')}
    jobs = []
    for family in families:
        fid=family['family_id'];packet=packets[fid]
        base=next(v for v in family['variants'] if v['condition']=='base')
        material=lambda rows:[{'unit_id':u['unit_id'],'text':u['text']} for u in rows]
        jobs.append({'name':'composer-'+fid,'role':'composer','schema':COMPOSER_SCHEMA,
            'prompt':'你是Composer。本轮是受约束来源构题：只能使用给定材料、已核验父母事实、固定query和两步proof，不改变事实、答案、scope或删证蓝图。为query拟定清楚的现代汉语问题及为什么必须两步的说明。问句须说明组合给定材料各自明确的关系，不借作品常识，不虚构或补回缺失事实。若有直接答案捷径或不能严格两步，在issues指出，不自行修材料。输出JSON。',
            'payload':{'family_id':fid,'materials':material(base['materials']),
                       'origin':family['origin'],'fixed_query':family['query'],
                       'fixed_proof':base['gold'],'question_seed':family['question'],
                       'construction_constraint':'原始来源和事实已由程序/GPT根代理固定，本角色只提议问法与解释。'}})
        variants={v['condition']:v for v in family['variants']}
        jobs.append({'name':'difficult-'+fid,'role':'difficult','schema':DIFFICULT_SCHEMA,
            'prompt':'你是Difficult。本轮机制范围限角色/实体混淆与假桥接，材料及变换已固定。分析所给主干扰与基础题的实际差别，选适用机制并解释潜在错误连接、为什么合法答案保持，以及风险。若只能称一般相关性干扰、没有明确混淆机制，应如实写出，不把无难度材料包装为有效攻击。不能增加事实、关系或干扰句，不能把干扰中的父母事实跨人物拼接。另检查固定删证/无关对照的风险，不能用引文失配替代语义判断。输出JSON。',
            'payload':{'family_id':fid,'question':family['question'],'fixed_query':family['query'],
                       'base_materials':material(base['materials']),
                       'main_distractor_materials':material(variants['main_distractor']['materials']),
                       'fixed_deletions':packet['deletions'],
                       'allowed_mechanisms':['entity_confusion','false_bridge','relatedness_distraction'],
                       'target_coverage':'本批删证与审查验证；不要求每题强行具备实体混淆。'}})
    task={'output':RUNTIME+'/construction-stage2','max_tokens':6500,'jobs':jobs,
          'source_families_sha256':digest(families),'notes':'GPT/program blueprints constrain Flash proposals; no claim of autonomous end-to-end generation.'}
    save_new_or_same(WORK/'construction-stage2-jobs-v2.json',task)
    return task


def debug_cases():
    old=ROOT/'workspace/harness-prototype/runs/milestone-007'
    family=copy.deepcopy(read(old/'family.internal.json'))
    family['family_version']='0.1'
    family['origin']=read(old/'facts.gpt-adjudicated.json')
    cases=[{'case_id':'DEBUG-OLD007','family_id':'DEBUG-OLD007','track':'source',
            'candidate':family,'rationale':'仅供协议调试，旧开发家族，不计入新批。','external_relation_hints':{}}]
    for number,kind in enumerate(('valid','missing','redundant','scope'),1):
        # Separate names, wording, identifiers and construction from locked SYN pairs.
        root,mid,leaf=f'周甲调{number}',f'钱乙调{number}',f'孙丙调{number}'
        s1=f'档案说明：{leaf}的生父是{mid}。'
        s2=f'另页记载：{mid}的生父是{root}。'
        text=s1+s2+'窗外有一棵松树。'
        facts=[{'id':'D1','parent':mid,'child':leaf,'parent_role':'father','scope':'调试档案','expression':'direct','evidence_sets':[[{'unit_id':'DEBUG-T','quote':s1}]]},
               {'id':'D2','parent':root,'child':mid,'parent_role':'father','scope':'调试档案','expression':'direct','evidence_sets':[[{'unit_id':'DEBUG-T','quote':s2}]]}]
        question=f'只根据调试档案的现实记载，{leaf}的生父的生父叫什么？'
        proof=[{'from':leaf,'relation':'father','to':mid,'quote':s1},{'from':mid,'relation':'father','to':root,'quote':s2}]
        answer=[root];status='answerable'
        declared={'review_scope':'single_item','task_requires_two_steps':True,'query_scope':'调试档案现实记载，不采用梦境'}
        if kind=='missing':
            text=text.replace(s1,'');facts=facts[1:];answer=[];status='insufficient_evidence';proof=[]
        elif kind=='redundant':
            dup=f'户籍复核还写着，{mid}是{leaf}的父亲。'
            text=text.replace(s1,'')+dup;facts[0]['evidence_sets']=[[{'unit_id':'DEBUG-T','quote':dup}]];proof[0]['quote']=dup
            declared['deleted_original_support']=s1
        elif kind=='scope':
            text=s1+f'梦中有人自称：“{s2}”';facts[1]['scope']='梦境'
            answer=[];status='insufficient_evidence';proof=[]
        cases.append({'case_id':'DEBUG-INDEPENDENT-'+str(number),'family_id':'DEBUG-SYN-'+str(number),'track':'synthetic',
            'candidate':{'question':question,'materials':[{'unit_id':'DEBUG-T','text':text}],
                         'facts':facts,'proposed_answer':answer,'proposed_status':status,'proof':proof,'declared_conditions':declared},
            'rationale':'独立构造的协议调试材料，不属于锁定挑战集。','external_relation_hints':{}})
    return cases


def debug_jobs():
    cases=debug_cases()
    jobs=[{'name':case['case_id'].lower(),'role':'supervisor','payload':project_review(case,'A'),
           'schema':SCHEMAS['supervisor'],'prompt':REVIEW_PROMPT} for case in cases]
    task={'output':RUNTIME+'/prompt-debug','max_tokens':8500,'jobs':jobs,
          'prompt_sha256':digest(REVIEW_PROMPT),'debug_only':True,
          'case_count':len(cases),'cases':cases,'not_in_locked_batch':True}
    save_new_or_same(WORK/'prompt-debug-jobs.json',task)
    return task


if __name__=='__main__':
    print({'construction_jobs':len(construction_jobs()['jobs']),
           'debug_jobs':len(debug_jobs()['jobs']),
           'manifests':[str(WORK/'construction-stage2-jobs-v2.json'),str(WORK/'prompt-debug-jobs.json')]})
