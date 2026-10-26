"""Fresh fictional R2/R3 fixtures; no skills, revisions or result files are read.

Outputs and independent references: [R2](../../workspace/quality-v3/round-2/)
and [R3](../../workspace/quality-v3/round-3/). Only the current checkout's
projection API is imported. See [repository rules](../../AGENTS.md).
"""
from __future__ import annotations

import copy
import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location('iteration_projection', ROOT/'src/multi_agent_v0/core.py')
CORE = importlib.util.module_from_spec(spec)
spec.loader.exec_module(CORE)

EVIDENCE = {'type':'object', 'properties':{'context_id':{'type':'string','minLength':1},
    'quote':{'type':'string','minLength':1}}, 'required':['context_id','quote'], 'additionalProperties':False}
ANSWER_SCHEMA = {'type':'object','properties':{
    'status':{'enum':['answerable','insufficient_evidence','ambiguous','conflicting']},
    'answers':{'type':'array','items':{'type':'string','minLength':1}},
    'evidence':{'type':'array','items':EVIDENCE},
    'steps':{'type':'array','items':{'type':'object','properties':{
        'from':{'type':'string','minLength':1}, 'to':{'type':'string','minLength':1},
        'relation':{'enum':['father','mother','parent']},
        'evidence':{'type':'array','items':EVIDENCE,'minItems':1}},
        'required':['from','relation','to','evidence'],'additionalProperties':False}},
    'brief_reason':{'type':'string','minLength':1}},
    'required':['status','answers','evidence','steps','brief_reason'],'additionalProperties':False}


def cid(uid):
    return 'P' + CORE.digest(uid)[:10]


def world(key, names, roles, texts, supports, question, scope='登记事实', aliases=None):
    """supports[i] contains independent (unit index, exact quote) expressions."""
    aliases = aliases or {}
    units = [{'unit_id':f'{key}-u{i}', 'text':text} for i,text in enumerate(texts)]
    facts = []
    for i,(role,expressions) in enumerate(zip(roles,supports)):
        facts.append({'id':f'{key}-f{i}', 'child':names[i], 'parent':names[i+1],
            'parent_role':role, 'scope':scope,
            'evidence_sets':[[{'unit_id':units[n]['unit_id'],'quote':q}] for n,q in expressions]})
    return {'key':key,'names':names,'roles':roles,'materials':units,'facts':facts,
        'question':question,'query':{'operation':'parents','start':names[0],'steps':roles,'scope':scope},
        'entities':[{'id':n,'name':n,'aliases':aliases.get(n,[])} for n in names]}


def projected_facts(w):
    facts = copy.deepcopy(w['facts'])
    for f in facts:
        for bundle in f['evidence_sets']:
            for q in bundle:
                q['unit_id'] = cid(q['unit_id'])
    return facts


def refs(w, *indices, alternative=False):
    result = []
    for i in indices:
        sets = w['facts'][i]['evidence_sets']
        for q in sets[-1 if alternative else 0]:
            result.append({'context_id':cid(q['unit_id']),'quote':q['quote']})
    return result


def proof(w):
    return {'entities':w['names'][:], 'facts':[f['id'] for f in w['facts']]}


def review_case(w, suffix, *, status='answerable', bad_order=False):
    p = proof(w)
    if bad_order:
        p['facts'].reverse()
    return {'case_id':w['key']+'-'+suffix, 'candidate':{
        'question':w['question'], 'query':copy.deepcopy(w['query']),
        'materials':[{'unit_id':cid(u['unit_id']),'text':u['text']} for u in w['materials']],
        'facts':projected_facts(w), 'proposed_status':status,
        'proposed_answer':[w['names'][-1]] if status=='answerable' else [],
        'proof':[p] if status=='answerable' else [],
        'declared_conditions':{'fictional':True,'requested_hops':2,'scope':w['query']['scope']}}}


def review_ref(w, verdict='pass', *, answer=True, supported=True, necessary='necessary', reason='', evidence=None):
    return {'expected_valid':verdict=='pass','expected_verdict':verdict,'expected_candidate_status_supported':answer,
        'expected_answer_supported':answer,'expected_proof_supported':supported,
        'expected_two_hop':necessary,'evidence':refs(w,0,1) if evidence is None else evidence,
        'reason':reason, 'author_gpt_checks':{
            'question_start':w['names'][0], 'requested_roles':w['roles'],
            'target':w['names'][-1], 'requested_scope':w['query']['scope'],
            'fictional':True,'positive_support_quotes_do_not_use_negated_or_wrong_scope_sentences':True}}


def score_case(w, suffix, *, status='answerable', missing=False, final=None, cites=None):
    row = {'materials':copy.deepcopy(w['materials']), 'gold':{
        'status':'insufficient_evidence' if missing else 'answerable',
        'answer_ids':[] if missing else [w['names'][-1]],
        'proofs':[] if missing else [proof(w)]}}
    origin = {'entities':copy.deepcopy(w['entities']), 'facts':copy.deepcopy(w['facts']),
        'warnings':['所有人物、档案和关系均为本轮独立合成的虚构设定。']}
    payload = CORE.project(row,w['question'],ANSWER_SCHEMA)
    steps = []
    if status=='answerable' and not missing:
        for i,role in enumerate(w['roles']):
            steps.append({'from':w['names'][i], 'to':w['names'][i+1], 'relation':role,
                'evidence':cites[i] if cites else refs(w,i)})
    answer = {'status':status,'answers':([final or w['names'][-1]] if status=='answerable' else []),
        'steps':steps,'evidence':[], 'brief_reason':('材料未给出所需完整链。' if status=='insufficient_evidence'
            else '按所提交的两步关系定位目标。')}
    return {'case_id':w['key']+'-'+suffix,'answer':answer,'payload':payload,'row':row,'origin':origin,
        'query':copy.deepcopy(w['query'])}


def score_ref(w, *, verdict='supported', status=True, answer=True, support='supported', reason='', evidence=None):
    return {'expected_valid':verdict=='supported',
        'status_correct':status,'final_answer_correct':answer,
        'proof_supported_by_actual_member':support in ('supported','not_applicable'),
        'expected_semantic_verdict':verdict, 'expected_status_correct':status,
        'expected_answer_correct':answer,'expected_proof_support':support,
        'evidence':refs(w,0,1) if evidence is None else evidence, 'reason':reason,
        'author_gpt_checks':{'start':w['names'][0], 'requested_roles':w['roles'],
            'target':w['names'][-1], 'scope':w['query']['scope'], 'fictional':True,
            'dimensions_scored_independently':True}}


def inventory_case(w, extra_facts=None):
    facts = copy.deepcopy(w['facts']) + copy.deepcopy(extra_facts or [])
    payload = {'question':w['question'],'query':copy.deepcopy(w['query']),
        'contexts':[{'context_id':cid(u['unit_id']),'text':u['text']} for u in w['materials']],
        'candidate_edges':[{k:f[k] for k in ('id','parent','child','parent_role','scope')} for f in facts],
        'entity_bindings':copy.deepcopy(w['entities'])}
    return {'case_id':w['key'],'payload':payload}


def inventory_ref(w, extra_facts=None, paths=None):
    facts = w['facts'] + (extra_facts or [])
    groups = []
    for f in facts:
        groups.append({'fact_id':f['id'],'parent':f['parent'],'child':f['child'],
            'parent_role':f['parent_role'],'scope':f['scope'],
            'independent_support_groups':[[{'context_id':cid(q['unit_id']),'quote':q['quote']} for q in b]
                for b in f['evidence_sets']]})
    return {'expected_support_inventory':groups,
        'expected_complete_paths':paths or [proof(w)], 'expected_answer_ids':[w['names'][-1]],
        'reason':'每个独立表达分别登记；完整路径按起点、角色和登记事实范围连接。梦境、演出及否定语句不进入正支持。',
        'author_gpt_checks':{'fictional':True,'start':w['names'][0],'roles':w['roles'],
            'target':w['names'][-1],'scope':w['query']['scope'],
            'all_positive_supports_are_exact_located_and_affirmative':True}}


def new_round(round_no):
    return {'metadata':{'version':'fresh-iteration-fixtures-v1','round':round_no,
        'source':'independently authored fictional microarchives; not external literary or historical facts',
        'isolation':{'read_skills':False,'read_skill_revisions':False,'read_new_model_results':False,
            'read_old_case_text':False,'read_other_branches':False,
            'allowed_reads':['current-checkout AGENTS.md','review/scoring API and schemas',
                'CORE.project/digest API','old fixture JSON key/schema structure only']},
        'references_are_separate':True}, 'review_cases':[],'score_cases':[],'inventory_cases':[]}, {
        'metadata':{'round':round_no,'independent_reference_only':True,
            'reference_author':'fixture-author GPT',
            'independent_gpt_pre_audit':'pending separate reviewer',
            'human_review_performed':False},
        'review_references':{},'score_references':{},'inventory_references':{}}


def add_pair(data, reference, kind, cases, labels):
    key = {'review':'review_cases','score':'score_cases','inventory':'inventory_cases'}[kind]
    rkey = {'review':'review_references','score':'score_references','inventory':'inventory_references'}[kind]
    data[key].extend(cases)
    reference[rkey].update({c['case_id']:r for c,r in zip(cases,labels)})


def round_two():
    d,r = new_round(2)
    w = world('R2-RV-A',['苇岚','弦浦','砂遥'],['mother','father'],[
        '虚构的苔桥登记簿把两条亲属消息写在同一段：苇岚由母亲弦浦抚养；弦浦的父亲名为砂遥。墙上的砂遥画像与亲属登记无关。'],
        [[(0,'苇岚由母亲弦浦抚养')],[(0,'弦浦的父亲名为砂遥')]],
        '仅按这份虚构登记簿，苇岚的母亲的父亲是谁？')
    direct = copy.deepcopy(w)
    direct['materials'][0]['text'] += '旁注直写：苇岚的外公是砂遥；“灰帆”是砂遥的别称，此处外公也可写作灰帆。'
    add_pair(d,r,'review',[review_case(w,'01'),review_case(direct,'02')],[
        review_ref(w,reason='同段包含两条相连父母关系，仍须从苇岚经弦浦查到砂遥。'),
        review_ref(direct,'revise',necessary='shortcut',reason='外公的直接结论及明确别称已在材料中给出。',
            evidence=[{'context_id':cid(w['materials'][0]['unit_id']),'quote':'苇岚的外公是砂遥'}])])

    w = world('R2-RV-B',['檐禾','石汀','藤晗'],['father','mother'],[
        '虚构的河闸户册记载：檐禾的父亲是石汀。',
        '同一本户册的登记事实写道：石汀的母亲是藤晗。另页戏词不作为户册事实。'],
        [[(0,'檐禾的父亲是石汀')],[(1,'石汀的母亲是藤晗')]],
        '按这份虚构户册的登记事实，檐禾的父亲的母亲是谁？')
    scoped = copy.deepcopy(w)
    scoped['materials'][1]['text'] = '虚构的木偶戏台词写道：“石汀的母亲是藤晗。”户册没有登记石汀的母亲。'
    scoped['facts'][1]['scope'] = '木偶戏台词'
    add_pair(d,r,'review',[review_case(w,'03'),review_case(scoped,'04')],[
        review_ref(w,reason='两条都属于户册登记事实。'),
        review_ref(scoped,'revise',answer=False,supported=False,necessary='not_applicable',
            reason='第二条仅为戏词，无法连接登记事实中的第二步。',
            evidence=[{'context_id':cid(scoped['materials'][1]['unit_id']),'quote':scoped['materials'][1]['text']}])])

    w = world('R2-RV-C',['露砚','舟芮','岩绫'],['mother','mother'],[
        '虚构的纸船村入户表写着：露砚的母亲是舟芮。',
        '另一格由舟芮亲笔填入：我的母亲叫岩绫。该格的填表人一栏写的是舟芮。'],
        [[(0,'露砚的母亲是舟芮')],[(1,'另一格由舟芮亲笔填入：我的母亲叫岩绫。该格的填表人一栏写的是舟芮。')]],
        '在这个虚构入户表的登记事实中，露砚的母亲的母亲是谁？')
    add_pair(d,r,'review',[review_case(w,'05'),review_case(w,'06',bad_order=True)],[
        review_ref(w,reason='有序事实分别连接露砚→舟芮→岩绫。'),
        review_ref(w,'revise',supported=False,reason='两条关系本身为真，但提交 facts 顺序与 entities 各步相反。')])

    w = world('R2-RV-D',['绒策','栎苏','池珞'],['father','father'],[
        '虚构的舟棚账页保留了绒策的父亲登记：栎苏。',
        '栎苏的父亲叫池珞，这是账页正文的登记事实。',
        '独立的重抄卡说，绒策是栎苏之子，栎苏为其父亲；栎苏本人则是池珞的儿子，池珞的身份是父亲。卡片中的亲属关系也经账页登记者确认。'],
        [[(0,'绒策的父亲登记：栎苏'),(2,'绒策是栎苏之子，栎苏为其父亲')],
         [(1,'栎苏的父亲叫池珞'),(2,'栎苏本人则是池珞的儿子，池珞的身份是父亲')]],
        '按此虚构舟棚档案的登记事实，绒策的父亲的父亲是谁？')
    add_pair(d,r,'review',[review_case(w,'07'),review_case(w,'08',status='insufficient_evidence')],[
        review_ref(w,reason='原登记与独立重抄都保留同一完整链，重复支持不影响可答。'),
        review_ref(w,'revise',answer=False,supported=False,reason='缺证声明为伪：两步各有独立肯定表达。')])

    w = world('R2-SC-A',['麦沄','铜鹭','雪棠'],['father','mother'],[
        '虚构的苔钟所登记事实只载：麦沄的父亲是铜鹭。雪棠为此页校字员。',
        '铜鹭的母亲一栏留白；“铜鹭的母亲是雪棠”一说已被记录员否认，不能当作登记事实。'],
        [[(0,'麦沄的父亲是铜鹭')],[]],
        '按虚构苔钟所的登记事实，麦沄的父亲的母亲是谁？')
    add_pair(d,r,'score',[score_case(w,'01',status='insufficient_evidence',missing=True),
        score_case(w,'02',missing=True)],[
        score_ref(w,support='not_applicable',reason='第二步没有肯定支持，空答案和空步骤合适。',evidence=refs(w,0)),
        score_ref(w,verdict='incorrect',status=False,answer=False,support='unsupported',
            reason='第二步缺失却猜雪棠；否认不能作为正支持。',evidence=refs(w,0))])

    w = world('R2-SC-B',['荷绡','岚笛','木澄'],['mother','father'],[
        '虚构的风窑籍册说，荷绡的母亲是岚笛。',
        '岚笛的父亲是木澄。木澄另名“青瓦客”；校图人梧灯另名“赤页”。'],
        [[(0,'荷绡的母亲是岚笛')],[(1,'岚笛的父亲是木澄')]],
        '依据虚构风窑籍册的登记事实，荷绡的母亲的父亲是谁？',aliases={'木澄':['青瓦客']})
    w['entities'].append({'id':'梧灯','name':'梧灯','aliases':['赤页']})
    add_pair(d,r,'score',[score_case(w,'03',final='木澄（青瓦客）'),score_case(w,'04',final='木澄（赤页）')],[
        score_ref(w,reason='组合中的本名与别名明示属于同一目标。'),
        score_ref(w,verdict='incorrect',answer=False,reason='顶层名称将木澄与另一人的别名赤页混合；路径正确不能修复冒名。')])

    w = world('R2-SC-C',['萤褚','砾悠','棉岑'],['father','father'],[
        '虚构的瓷港登记事实记载：萤褚的父亲是砾悠。',
        '登记事实另记：砾悠的父亲是棉岑。',
        '另一份独立核录写道，萤褚是砾悠的儿子，砾悠的亲属身份标为父亲。',
        '核录又记，棉岑育有儿子砾悠，且亲属角色标为父亲。'],
        [[(0,'萤褚的父亲是砾悠')],[(1,'砾悠的父亲是棉岑')]],
        '只按这套虚构瓷港登记事实，萤褚的父亲的父亲是谁？')
    alt = [[{'context_id':cid(w['materials'][2]['unit_id']),'quote':'萤褚是砾悠的儿子，砾悠的亲属身份标为父亲'}],
           [{'context_id':cid(w['materials'][3]['unit_id']),'quote':'棉岑育有儿子砾悠，且亲属角色标为父亲'}]]
    thin = [[{'context_id':cid(w['materials'][0]['unit_id']),'quote':'砾悠'}],
            [{'context_id':cid(w['materials'][1]['unit_id']),'quote':'棉岑'}]]
    add_pair(d,r,'score',[score_case(w,'05',cites=alt),score_case(w,'06',cites=thin)],[
        score_ref(w,reason='提交的是另一份独立肯定表达，虽与原标注不重叠仍逐步支持。',evidence=alt[0]+alt[1]),
        score_ref(w,verdict='incorrect',support='unsupported',reason='引文仅为人名，未提交父子关系的证据。')])

    w = world('R2-SC-D',['篷芷','汐衡','榆盏'],['mother','mother'],[
        '虚构的藤环村登记事实有三人：篷芷、汐衡、榆盏。篷芷认汐衡为生母。',
        '汐衡的生母登记为榆盏。纸鹤只是传信人的称呼。'],
        [[(0,'篷芷认汐衡为生母')],[(1,'汐衡的生母登记为榆盏')]],
        '按这份虚构藤环村登记事实，篷芷的母亲的母亲是谁？')
    add_pair(d,r,'score',[score_case(w,'07',final='汐衡'),score_case(w,'08')],[
        score_ref(w,verdict='incorrect',answer=False,reason='步骤与引文正确，但最终填的是桥接人汐衡。'),
        score_ref(w,reason='最终目标、顺序与逐步引文全部符合材料。')])

    w = world('R2-IN-01',['笺瑚','灰芦','沐陶'],['father','mother'],[
        '虚构的灯屿登记事实写：笺瑚的父亲是灰芦。',
        '第二页写：灰芦的母亲是沐陶。',
        '一份独立复核载，灰芦是笺瑚的生父。',
        '另一份独立复核载，沐陶生下灰芦，亲属身份是灰芦的母亲。',
        '戏中把笺瑚的父亲演作沐陶，这不是登记事实。复核明确否定“沐陶是笺瑚的父亲”。'],
        [[(0,'笺瑚的父亲是灰芦'),(2,'灰芦是笺瑚的生父')],
         [(1,'灰芦的母亲是沐陶'),(3,'沐陶生下灰芦，亲属身份是灰芦的母亲')]],
        '依据虚构灯屿的登记事实，笺瑚的父亲的母亲是谁？')
    add_pair(d,r,'inventory',[inventory_case(w)],[inventory_ref(w)])
    w = world('R2-IN-02',['墨棱','涧澜','暮柏'],['parent','father'],[
        '虚构的铜湾登记事实：墨棱的母亲叫涧澜。',
        '涧澜的父亲叫暮柏。',
        '墨棱的父亲叫舟栖。',
        '舟栖的父亲也叫暮柏。',
        '梦境里，墨棱的母亲变成暮柏；登记员否定“暮柏是墨棱的父亲”。'],
        [[(0,'墨棱的母亲叫涧澜')],[(1,'涧澜的父亲叫暮柏')]],
        '根据虚构铜湾的登记事实，墨棱的父母中任一人的父亲是谁？列出所有符合的人，去掉重复。')
    w['facts'][0]['parent_role']='mother'
    w['entities'].append({'id':'舟栖','name':'舟栖','aliases':[]})
    extra = [{'id':'R2-IN-02-f2','child':'墨棱','parent':'舟栖','parent_role':'father','scope':'登记事实',
        'evidence_sets':[[{'unit_id':w['materials'][2]['unit_id'],'quote':'墨棱的父亲叫舟栖'}]]},
        {'id':'R2-IN-02-f3','child':'舟栖','parent':'暮柏','parent_role':'father','scope':'登记事实',
        'evidence_sets':[[{'unit_id':w['materials'][3]['unit_id'],'quote':'舟栖的父亲也叫暮柏'}]]}]
    add_pair(d,r,'inventory',[inventory_case(w,extra)],[inventory_ref(w,extra,
        [proof(w),{'entities':['墨棱','舟栖','暮柏'],'facts':['R2-IN-02-f2','R2-IN-02-f3']}])])
    return d,r


def round_three():
    d,r = new_round(3)
    w = world('R3-RV-A',['釉宁','杉弈','汀罗'],['father','mother'],[
        '虚构的浮市户籍用问答记事：“釉宁的父亲是谁？”答：“杉弈。”接着问：“杉弈的母亲是谁？”答：“汀罗。”本段两答均为登记事实。'],
        [[(0,'“釉宁的父亲是谁？”答：“杉弈。”')],[(0,'“杉弈的母亲是谁？”答：“汀罗。”')]],
        '按虚构浮市户籍的登记事实，釉宁的父亲的母亲是谁？')
    direct=copy.deepcopy(w)
    direct['materials'][0]['text']+='补写一行：“釉宁的奶奶”指汀罗，而非杉弈；此处“她”仍指这位奶奶。'
    add_pair(d,r,'review',[review_case(w,'01'),review_case(direct,'02')],[
        review_ref(w,reason='同一段问答分别给出第一步和第二步，未直写奶奶目标。'),
        review_ref(direct,'revise',necessary='shortcut',reason='补写对釉宁的奶奶作了显式目标绑定；她的指代也明确。',
            evidence=[{'context_id':cid(w['materials'][0]['unit_id']),'quote':'“釉宁的奶奶”指汀罗'}])])

    w = world('R3-RV-B',['棠瑜','烛川','青绮'],['mother','father'],[
        '虚构的沼岸登记事实以箭头标注亲属：棠瑜——母亲→烛川。',
        '登记员解释下一格：烛川的父亲是青绮。蓝色格不代表梦境。'],
        [[(0,'棠瑜——母亲→烛川')],[(1,'烛川的父亲是青绮')]],
        '按虚构沼岸的登记事实，棠瑜的母亲的父亲是谁？')
    scoped=copy.deepcopy(w)
    scoped['materials'][1]['text']='梦话采录格写着“烛川的父亲是青绮”；采录人说明这只存在于梦中，登记事实中烛川父亲尚未查明。'
    scoped['facts'][1]['scope']='梦话采录'
    add_pair(d,r,'review',[review_case(w,'03'),review_case(scoped,'04')],[
        review_ref(w,reason='图例明确角色方向，第二条也为登记事实。'),
        review_ref(scoped,'revise',answer=False,supported=False,necessary='not_applicable',
            reason='梦话中的第二步不能充当登记事实。',
            evidence=[{'context_id':cid(scoped['materials'][1]['unit_id']),'quote':scoped['materials'][1]['text']}])])

    w = world('R3-RV-C',['琥盈','松溯','霭纹'],['father','father'],[
        '虚构的绸井登记事实分列卡片：子女栏琥盈，父亲栏松溯。',
        '第二张卡片的子女栏为松溯，父亲栏为霭纹。两张卡片都已经确认。'],
        [[(0,'子女栏琥盈，父亲栏松溯')],[(1,'子女栏为松溯，父亲栏为霭纹')]],
        '按这套虚构卡片的登记事实，琥盈的父亲的父亲是谁？')
    add_pair(d,r,'review',[review_case(w,'05'),review_case(w,'06',bad_order=True)],[
        review_ref(w,reason='卡片角色与有序提交相符。'),
        review_ref(w,'revise',supported=False,reason='卡片都属实，提交却把支持松溯→霭纹的事实放到第一步。')])

    w = world('R3-RV-D',['漆悠','雾苓','银笺'],['parent','mother'],[
        '虚构的萤台登记事实称漆悠的母亲为雾苓。',
        '雾苓说：“我的母亲是银笺。”书记确认这段话记入登记事实。',
        '另一名登记员独立核对，雾苓是漆悠的生母。',
        '核对表的另一栏写着：银笺为雾苓之母。',
        '另一页独立登记父系：漆悠的父亲是夕缗；夕缗的母亲也是银笺。',
        '戏曲里将漆悠的母亲唱成银笺；此唱词已被否定为现实亲属登记。'],
        [[(0,'漆悠的母亲为雾苓'),(2,'雾苓是漆悠的生母')],
         [(1,'雾苓说：“我的母亲是银笺。”书记确认这段话记入登记事实。'),(3,'银笺为雾苓之母')]],
        '根据虚构萤台的登记事实，漆悠的父母中任一人的母亲是谁？列全且去重。')
    w['facts'][0]['parent_role']='mother'
    add_pair(d,r,'review',[review_case(w,'07'),review_case(w,'08',status='insufficient_evidence')],[
        review_ref(w,reason='母系有重复记录，父系另有独立完整路径且同终点；戏曲假近路不消除真链。'),
        review_ref(w,'revise',answer=False,supported=False,reason='独立复核、母系原链与父系替代链均保留，不能宣称缺证。')])
    for case in d['review_cases'][-2:]:
        r['review_references'][case['case_id']]['preserved_alternative_complete_path']={
            'entities':['漆悠','夕缗','银笺'],'roles':['father','mother'],
            'scope':'登记事实','evidence':[{'context_id':cid(w['materials'][4]['unit_id']),
                'quote':'漆悠的父亲是夕缗；夕缗的母亲也是银笺'}]}

    w = world('R3-SC-A',['瓷岫','隅婉','帛辛'],['mother','father'],[
        '虚构的松帆岛登记事实载，瓷岫的母亲是隅婉。帛辛负责海图绘制。',
        '隅婉的父亲没有登记。旧传单称“隅婉的父亲是帛辛”，但传单作者已经撤回此说。'],
        [[(0,'瓷岫的母亲是隅婉')],[]],
        '按虚构松帆岛的登记事实，瓷岫的母亲的父亲是谁？')
    add_pair(d,r,'score',[score_case(w,'01',status='insufficient_evidence',missing=True),score_case(w,'02',missing=True)],[
        score_ref(w,support='not_applicable',reason='没有可支持第二步的登记；空答与空证明符合。',evidence=refs(w,0)),
        score_ref(w,verdict='incorrect',status=False,answer=False,support='unsupported',
            reason='把撤回的传单当作依据猜帛辛，当前材料不支持。',evidence=refs(w,0))])

    w = world('R3-SC-B',['芽络','岫棋','陶泓'],['father','mother'],[
        '虚构的篷塔登记事实说明，芽络的父亲是岫棋。',
        '岫棋的母亲叫陶泓。陶泓另用名“墨瓮”。抄录员纪筝是一名白篷书吏；“白篷书吏”只描述纪筝的工作，从未用作陶泓的名号。'],
        [[(0,'芽络的父亲是岫棋')],[(1,'岫棋的母亲叫陶泓')]],
        '根据虚构篷塔的登记事实，芽络的父亲的母亲是谁？',aliases={'陶泓':['墨瓮']})
    w['entities'].append({'id':'纪筝','name':'纪筝','aliases':[]})
    add_pair(d,r,'score',[score_case(w,'03',final='陶泓（墨瓮）'),score_case(w,'04',final='陶泓（白篷书吏）')],[
        score_ref(w,reason='陶泓及墨瓮是材料明确登记的同人名号。'),
        score_ref(w,verdict='incorrect',answer=False,reason='括注冒用另一人的职业描述；该描述被明确排除为陶泓名号。')])

    w = world('R3-SC-C',['苔若','简陌','砚洄'],['mother','mother'],[
        '虚构的柚丘登记事实载：苔若的母亲是简陌。',
        '简陌的母亲是砚洄，这是另一页登记事实。',
        '复核问答记录：“苔若由谁生下？”答：“简陌，她是苔若的母亲。”',
        '独立问答再记：“简陌的生母姓名？”答：“砚洄。”'],
        [[(0,'苔若的母亲是简陌')],[(1,'简陌的母亲是砚洄')]],
        '按虚构柚丘的登记事实，苔若的母亲的母亲是谁？')
    alt = [[{'context_id':cid(w['materials'][2]['unit_id']),'quote':'“苔若由谁生下？”答：“简陌，她是苔若的母亲。”'}],
        [{'context_id':cid(w['materials'][3]['unit_id']),'quote':'“简陌的生母姓名？”答：“砚洄。”'}]]
    thin = [[{'context_id':cid(w['materials'][0]['unit_id']),'quote':'苔若'}],
        [{'context_id':cid(w['materials'][1]['unit_id']),'quote':'简陌'}]]
    add_pair(d,r,'score',[score_case(w,'05',cites=alt),score_case(w,'06',cites=thin)],[
        score_ref(w,reason='复核问答是独立表达，完整指明各自母女关系。',evidence=alt[0]+alt[1]),
        score_ref(w,verdict='incorrect',support='unsupported',reason='只提交姓名片段，没有母女关系。')])

    w = world('R3-SC-D',['穗湛','绢霏','槐聆'],['father','father'],[
        '虚构的橙渡家系登记事实采用短笺：穗湛称绢霏为生父，书记予以核定。',
        '绢霏称槐聆为生父，也已核定为登记事实。'],
        [[(0,'穗湛称绢霏为生父，书记予以核定')],[(1,'绢霏称槐聆为生父，也已核定为登记事实')]],
        '在虚构橙渡的登记事实范围内，穗湛的父亲的父亲是谁？')
    add_pair(d,r,'score',[score_case(w,'07',final='绢霏'),score_case(w,'08')],[
        score_ref(w,verdict='incorrect',answer=False,reason='所提交链及引文正确，最终答案却是中间父亲。'),
        score_ref(w,reason='顶层目标与提交链终点相同，逐步引用充分。')])

    w = world('R3-IN-01',['霞序','陶芩','竹晞'],['mother','father'],[
        '虚构的浅礁登记事实确认，霞序的母亲叫陶芩。',
        '陶芩的父亲叫竹晞。',
        '一封独立查验回函写道：“霞序由陶芩所生，陶芩为其母亲。”',
        '另一张查验表把陶芩列在子女栏，把竹晞列在父亲栏。',
        '诗社演出让竹晞扮霞序之母，不属于登记事实。登记员否定“霞序的母亲是竹晞”。'],
        [[(0,'霞序的母亲叫陶芩'),(2,'霞序由陶芩所生，陶芩为其母亲')],
         [(1,'陶芩的父亲叫竹晞'),(3,'把陶芩列在子女栏，把竹晞列在父亲栏')]],
        '依虚构浅礁的登记事实，霞序的母亲的父亲是谁？')
    add_pair(d,r,'inventory',[inventory_case(w)],[inventory_ref(w)])
    w = world('R3-IN-02',['舫吟','苇淮','澄樾'],['parent','mother'],[
        '虚构的杉潮登记事实确认：舫吟的父亲是苇淮。',
        '苇淮的母亲是澄樾。',
        '同册也确认：舫吟的母亲是柳缈。',
        '柳缈的母亲仍是澄樾。',
        '梦中舫吟说澄樾是其母亲，但梦境不属于登记事实；登记员否定“舫吟的母亲是澄樾”。'],
        [[(0,'舫吟的父亲是苇淮')],[(1,'苇淮的母亲是澄樾')]],
        '按虚构杉潮的登记事实，舫吟的父母中任一人的母亲是谁？列全且去重。')
    w['facts'][0]['parent_role']='father'
    w['entities'].append({'id':'柳缈','name':'柳缈','aliases':[]})
    extra = [{'id':'R3-IN-02-f2','child':'舫吟','parent':'柳缈','parent_role':'mother','scope':'登记事实',
        'evidence_sets':[[{'unit_id':w['materials'][2]['unit_id'],'quote':'舫吟的母亲是柳缈'}]]},
        {'id':'R3-IN-02-f3','child':'柳缈','parent':'澄樾','parent_role':'mother','scope':'登记事实',
        'evidence_sets':[[{'unit_id':w['materials'][3]['unit_id'],'quote':'柳缈的母亲仍是澄樾'}]]}]
    add_pair(d,r,'inventory',[inventory_case(w,extra)],[inventory_ref(w,extra,
        [proof(w),{'entities':['舫吟','柳缈','澄樾'],'facts':['R3-IN-02-f2','R3-IN-02-f3']}])])
    return d,r


def validate(data, reference):
    """Local mechanical QA; the reference semantic claims require independent review."""
    assert [len(data[k]) for k in ('review_cases','score_cases','inventory_cases')]==[8,8,2]
    all_ids=[]
    for kind,key,rkey in [('review','review_cases','review_references'),
                          ('score','score_cases','score_references'),
                          ('inventory','inventory_cases','inventory_references')]:
        assert set(reference[rkey])=={c['case_id'] for c in data[key]}
        for c in data[key]:
            all_ids.append(c['case_id'])
            if kind=='review':
                p=c['candidate']; texts={u['unit_id']:u['text'] for u in p['materials']}
                facts=p['facts']
            elif kind=='score':
                CORE.validate_projection(c['payload'])
                assert c['payload']==CORE.project(c['row'],c['payload']['question'],ANSWER_SCHEMA)
                texts={u['context_id']:u['text'] for u in c['payload']['contexts']}
                facts=copy.deepcopy(c['origin']['facts'])
                for f in facts:
                    for bundle in f['evidence_sets']:
                        for e in bundle:e['unit_id']=cid(e['unit_id'])
            else:
                texts={u['context_id']:u['text'] for u in c['payload']['contexts']}; facts=[]
            def located(obj):
                if isinstance(obj,dict):
                    if 'quote' in obj and ('context_id' in obj or 'unit_id' in obj):
                        uid=obj.get('context_id',obj.get('unit_id'))
                        assert obj['quote'] and obj['quote'] in texts[uid], (c['case_id'],obj)
                    for v in obj.values():located(v)
                elif isinstance(obj,list):
                    for v in obj:located(v)
            located(facts)
            if kind=='score':located(c['answer'])
            located(reference[rkey][c['case_id']])
            # No independent expectations may appear in objects sent to a model.
            serialized=json.dumps(c,ensure_ascii=False)
            assert 'expected_verdict' not in serialized and 'author_gpt_checks' not in serialized
            assert '虚构' in (c['candidate']['question'] if kind=='review' else c['payload']['question'])
    assert len(all_ids)==len(set(all_ids))
    assert sum(x['expected_verdict']=='pass' for x in reference['review_references'].values())==4
    assert sum(x['expected_semantic_verdict']=='supported' for x in reference['score_references'].values())==4
    return {'case_counts':{'review':8,'scoring':8,'inventory':2},
        'all_submitted_and_reference_quotes_exactly_located':True,
        'blind_scoring_projection_matches_CORE_project':True,
        'reference_labels_excluded_from_model_case_objects':True,
        'review_balance':{'pass':4,'revise':4},'score_balance':{'supported':4,'incorrect':4},
        'semantic_reference_review':'pending independent pre-audit'}


def main():
    rounds=[]
    for n,build in [(2,round_two),(3,round_three)]:
        data,reference=build()
        data['metadata']['selfcheck']=validate(data,reference)
        out=ROOT/f'workspace/quality-v3/round-{n}'
        out.mkdir(parents=True,exist_ok=True)
        for name,obj in [('new-cases.json',data),('new-references.json',reference)]:
            (out/name).write_text(json.dumps(obj,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
        rounds.append(data)
        print(f'round-{n}: 8 review + 8 score + 2 inventory; all quotes located')
    names=[]
    for data in rounds:
        values=set()
        for c in data['review_cases']:values.add(c['candidate']['query']['start'])
        for c in data['score_cases']:values.update(e['name'] for e in c['origin']['entities'])
        for c in data['review_cases']:
            for f in c['candidate']['facts']:values.update([f['parent'],f['child']])
        for c in data['inventory_cases']:values.update(e['name'] for e in c['payload']['entity_bindings'])
        names.append(values)
    assert not names[0]&names[1], names[0]&names[1]
    print('round-2/3 entity sets disjoint; no skill/result/old-text files were read by this builder')


if __name__=='__main__':
    main()
