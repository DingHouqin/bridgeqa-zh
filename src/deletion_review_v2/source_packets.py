"""Source-grounded construction drafts, explicitly retaining GPT corrections."""
import copy
import hashlib

from experiment import ROOT, read, save_new_or_same, digest
from family import build_family, graph_core, remove_quotes_v2

WORK=ROOT/'workspace/deletion-review-v2'
RUNTIME=ROOT/'workspace/harness-prototype/runs/deletion-review-v2-20261022'


def modern_materials():
    rows=read(WORK/'materials.gpt-draft-v2.json')
    for row in rows:
        row['text']=row['text'].replace('只只顾寻欢作乐','只顾寻欢作乐').replace('荣府的后辈','荣府的孙辈').replace('满一个月才到家','过了这个月才到家')
        row['modern_sha256']=hashlib.sha256(row['text'].encode()).hexdigest()
        row['review_status']='pending_independent_gpt'
    units={u['unit_id']:u for u in rows}
    parent=units['SRC-GENEALOGY'];text=parent['text'];cut=text.index('再说荣府你听')
    intro_start=text.index('当年宁国公');intro_end=text.index('。',intro_start)+1
    opening=text.index('“')+1
    for uid,ranges in [('SRC-NING',[(0,cut),(len(text)-1,len(text))]),
                       ('SRC-RONG',[(0,opening),(intro_start,intro_end),(cut,len(text))])]:
        fragment=''.join(text[a:b] for a,b in ranges)
        units[uid]={**parent,'unit_id':uid,'text':fragment,'parent_unit_id':parent['unit_id'],
                    'parent_modern_sha256':parent['modern_sha256'],'composition_ranges':ranges,
                    'modern_sha256':hashlib.sha256(fragment.encode()).hexdigest()}
    # Reuse an already modernized source distractor, never reuse the old base question.
    prior=read(ROOT/'workspace/hongloumeng-modernization-trial/resolved-validation/P02.modern.json')[0]
    source_index=[__import__('json').loads(line) for line in (ROOT/'data/source-candidates/hongloumeng_archive_org/20210205_20210205_1123/prepared/source_units.jsonl').read_text(encoding='utf-8').splitlines()]
    meta=next(u for u in source_index if u['unit_id']==prior['unit_id'])
    raw=(ROOT/'data/source-candidates/hongloumeng_archive_org/20210205_20210205_1123/hongloumeng_original_120.txt').read_bytes().decode('utf-8-sig')
    units['SRC-XUE-MOTHER']={**meta,'unit_id':'SRC-XUE-MOTHER','parent_unit_id':prior['unit_id'],
                           'original_text':raw[meta['start_character']:meta['end_character_exclusive']],
                           'text':prior['modern_text'],'modern_sha256':prior['modern_sha256'],
                           'assertion_scope':'叙述者','reuse':'previous_modernization_snapshot_pending_new_independent_review'}
    save_new_or_same(WORK/'materials.gpt-draft-v4.json',list(units.values()))
    parent=units['SRC-DAUGHTERS'];body=parent['text']
    start=body.index('因史老夫人');end=body.index('。',start)+1
    selected=body[:start]+body[end:]
    units['SRC-DAUGHTERS-TASK']={**parent,'unit_id':'SRC-DAUGHTERS-TASK','text':selected,
        'parent_unit_id':parent['unit_id'],'parent_modern_sha256':parent['modern_sha256'],
        'selection_ranges':[[0,start],[end,len(body)]], 'excluded_ranges':[[start,end]],
        'excluded_text':body[start:end],'selection_reason':'排除直接祖母结论以测试必要两步推理；非翻译修订',
        'modern_sha256':hashlib.sha256(selected.encode()).hexdigest()}
    save_new_or_same(WORK/'materials.task-selected-v1.json',list(units.values()))
    return units


def make_fact(fid,parent,child,role,scope,groups):
    return {'id':fid,'parent':parent,'child':child,'parent_role':role,'scope':scope,
            'expression':'coreference' if len(groups[0])>1 else 'direct','evidence_sets':groups}


def construct():
    units=modern_materials();source=read(WORK/'source-discovery.json')
    ning=units['SRC-NING']['text'];rong=units['SRC-RONG']['text'];daughters=units['SRC-DAUGHTERS-TASK']['text']
    q=lambda uid,quote:{'unit_id':uid,'quote':quote}
    # Whole source contexts retain the antecedents; short context-free model quotes are not accepted.
    facts=[
        make_fact('DAIHUA-JING','贾代化','贾敬','father','冷子兴转述',[[q('SRC-NING',ning[:ning.index('幸而早年')])]]),
        make_fact('JING-ZHEN','贾敬','贾珍','father','冷子兴转述',[[q('SRC-NING',ning[:ning.index('因他父亲')])]]),
        make_fact('DAISHAN-SHE','贾代善','贾赦','father','冷子兴转述',[[q('SRC-RONG',rong[rong.index('如今代善'):rong.index('这政老爹的夫人')])]]),
        make_fact('DAISHAN-ZHENG','贾代善','贾政','father','冷子兴转述',[[q('SRC-RONG',rong[rong.index('如今代善'):rong.index('这政老爹的夫人')])]]),
        make_fact('MU-SHE','贾母','贾赦','mother','叙述者',[[q('SRC-MOTHER-IDENTITY',units['SRC-MOTHER-IDENTITY']['text'])]]),
        make_fact('MU-ZHENG','贾母','贾政','mother','叙述者',[[q('SRC-MOTHER-IDENTITY',units['SRC-MOTHER-IDENTITY']['text'])]]),
        make_fact('SHE-LIAN','贾赦','贾琏','father','黛玉回忆母亲的说明',[[q('SRC-JIA-LIAN-PARENT',units['SRC-JIA-LIAN-PARENT']['text'])]]),
        make_fact('ZHENG-YUAN','贾政','元春','father','冷子兴转述',[[q('SRC-RONG',rong),q('SRC-DAUGHTERS-TASK',daughters[:daughters.index('二小姐')])]]),
        make_fact('ZHENG-TAN','贾政','探春','father','冷子兴转述',[[q('SRC-RONG',rong),q('SRC-DAUGHTERS-TASK',daughters[daughters.index('三小姐'):daughters.index('四小姐')])]]),
        make_fact('RONG-DAISHAN','荣国公','贾代善','father','冷子兴转述',[[q('SRC-RONG',rong)]]),
        make_fact('WANG-ZHU','王氏','贾珠','mother','冷子兴转述',[[q('SRC-RONG',rong)]]),
        make_fact('ZHU-LAN','贾珠','贾兰','father','叙述者',[[q('SRC-JIA-LAN-PARENT',units['SRC-JIA-LAN-PARENT']['text'])]]),
        make_fact('WANG-XUE','王氏（薛蟠之母）','薛蟠','mother','叙述者',[[q('SRC-XUE-MOTHER',units['SRC-XUE-MOTHER']['text'])]]),
    ]
    next(f for f in facts if f['id']=='JING-ZHEN')['expression']='coreference'
    aliases={'贾母':['史氏太君'],'贾敬':['敬老爹'],'贾珍':['珍爷'],'贾代善':['代善'],
             '贾赦':['赦老爹'],'贾政':['政老爹'],'荣国公':['荣公'],'王氏':['王夫人'],
             '王氏（薛蟠之母）':['王氏','薛姨妈']}
    all_names={f[k] for f in facts for k in ('parent','child')}
    entities=[{'id':n,'name':n,'aliases':aliases.get(n,[])} for n in sorted(all_names)]
    def pair_fact(p,c):return next(f for f in facts if f['parent']==p and f['child']==c)
    drafts=[];rejections=[]
    for proposal in source['families']:
        chain=proposal['proposed_chain'];fid=proposal['family_id']
        if chain[0]=='迎春':
            rejections.append({'family_id':fid,'reason':'前妻所出未在本轮严格直接关系合同下确认丈夫父亲身份；不靠婚姻补父边','status':'rejected_source_ambiguity'})
            continue
        first=pair_fact(chain[1],chain[0]);second=pair_fact(chain[2],chain[1])
        ids=[u.replace('SRC-DAUGHTERS','SRC-DAUGHTERS-TASK').replace('SRC-GENEALOGY','SRC-NING' if chain[0]=='贾珍' else 'SRC-RONG') for u in proposal['base_unit_ids']]
        if chain[0]=='贾珍':
            noise='SRC-RONG';noise_facts=[pair_fact('贾代善','贾政')]
        elif first['parent_role']=='father' and second['parent_role']=='mother':
            if 'SRC-RONG' not in ids:
                noise='SRC-RONG';noise_facts=[pair_fact('王氏','贾珠')]
            elif chain[0]=='贾兰':
                noise='SRC-MOTHER-IDENTITY';noise_facts=[pair_fact('贾母','贾政')]
            else:
                noise='SRC-XUE-MOTHER';noise_facts=[pair_fact('王氏（薛蟠之母）','薛蟠')]
        else:
            noise='SRC-NING';noise_facts=[pair_fact('贾代化','贾敬'),pair_fact('贾敬','贾珍')]
        unrelated=next(u for u in ['SRC-NAME-YINGCHUN','SRC-NAME-YUANCHUN','SRC-NAME-TANCHUN'] if u not in ids and u!=noise)
        if chain[0]=='贾珍':
            end=ning.index('这珍爷哪里')
            delete=[q('SRC-NING',ning[ning.index('幸而早年'):end])]
        elif chain[0] in ('贾赦','贾政'):
            start=rong.index('自荣公死后');end=rong.index('。',start)+1
            delete=[q('SRC-RONG',rong[start:end])]
        else:
            first_uid='SRC-DAUGHTERS-TASK' if chain[0] in ('元春','探春') else 'SRC-JIA-LIAN-PARENT' if chain[0]=='贾琏' else 'SRC-JIA-LAN-PARENT'
            delete=[q(first_uid,units[first_uid]['text'])]
        chosen={f['id']:f for f in [first,second]+noise_facts}
        packet={'family_id':fid,'track':'source',
                'question':f'结合给定材料中各自明确说明的亲属关系，{chain[0]}的父亲的'+('母亲' if proposal['roles'][1]=='mother' else '父亲')+'是谁？',
                'origin':{'entities':[e for e in entities if e['id'] in {f[k] for f in chosen.values() for k in ('parent','child')}],
                          'facts':list(chosen.values()),'warnings':['每条事实保留原陈述scope；问题明确组合给定材料，不声称所有信息都出自同一说话者。']},
                'query':{'operation':'parent_chain','start':chain[0],'steps':proposal['roles'],'scope':'explicit_given_source_composition',
                         'scope_by_step':[first['scope'],second['scope']]},
                'base_unit_ids':ids,'materials':[units[u] for u in dict.fromkeys(ids+[noise,unrelated])],
                'additions':{'main_distractor':[noise],'irrelevant_addition':[unrelated]},
                'deletions':{'necessary_support_deleted_name_retained':delete,
                             'irrelevant_deleted':[q('SRC-SCENERY',units['SRC-SCENERY']['text'].split('。')[0]+'。')]},
                'optional_not_applicable':{'name_absent_deleted':'无法在不另改其他相关支持的情况下消除所有起点称谓；本轮不强凑。',
                                           'redundant_support_deleted':'未登记经独立核实的重复支持组；不以文本相似冒充。',
                                           'alternative_proof_preserved':'本来源查询未发现同答案的独立完整替代链。'},
                'provenance':{'construction':'Flash Origin draft plus explicitly recorded root GPT source corrections',
                              'source_proposal':proposal,'independent_review':'pending'}}
        graph_core().validate_origin(packet['origin'],packet['materials'])
        drafts.append(packet)
    for packet in drafts:
        firstcut=packet['deletions']['necessary_support_deleted_name_retained']
        original=next(f for f in source['families'] if f['family_id']==packet['family_id'])
        retention=original['retention_unit_id']
        candidate=copy.deepcopy(packet)
        candidate['deletions']['name_absent_deleted']=firstcut+[q(retention,units[retention]['text'])]
        del candidate['optional_not_applicable']['name_absent_deleted']
        try:
            tentative=build_family(candidate)
            by={v['condition']:v for v in tentative['variants']}
            if by['name_absent_deleted']['active_fact_ids']==by['necessary_support_deleted_name_retained']['active_fact_ids']:
                packet.update(deletions=candidate['deletions'],optional_not_applicable=candidate['optional_not_applicable'])
        except ValueError:pass
    save_new_or_same(WORK/'source-packets.draft-v4.json',drafts)
    save_new_or_same(WORK/'source-rejections.json',rejections)
    families=[build_family(p) for p in drafts]
    save_new_or_same(WORK/'source-families.draft-v4.json',families)
    save_new_or_same(WORK/'origin-gpt-corrections-v3.json',{'original_flash_origin':str((RUNTIME/'construction/calls/origin-all-source.parsed.json').relative_to(ROOT)),
                          'changes':['去掉未充分支持的贾政→贾珠父边及迎春父边','贾母母边改用叙述者明确说明','指代证据纳入先行词与身份映射','补登记明确的荣公长子贾代善','删去过宽通用别名','按角色独立限定同名王氏'],
                          'facts':facts,'new_source_facts_invented':False,'human_review':'not_run'})
    return drafts,families


if __name__=='__main__':
    packets,families=construct();print({'source_families':len(families),'members':sum(len(f['variants']) for f in families)})
