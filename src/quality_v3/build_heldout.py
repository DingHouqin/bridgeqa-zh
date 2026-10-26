"""Independent fictional forward-test fixtures; no v3 skills/implementation used.

This generator intentionally imports only legacy core/schema definitions. The
separate references are never part of a model payload. See the parent module's
README for the eventual experiment protocol; this file does not run models.
"""
from __future__ import annotations

import copy
import hashlib
import importlib.util
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / 'workspace/quality-v3'


def legacy_core():
    spec = importlib.util.spec_from_file_location('_heldout_legacy_core', ROOT / 'src/multi_agent_v0/core.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def write_once(path, value):
    content = json.dumps(value, ensure_ascii=False, indent=2) + '\n'
    if path.exists():
        if path.read_text(encoding='utf-8') != content:
            raise ValueError('Forward-test artifact already frozen: ' + str(path))
    else:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding='utf-8')


def fact(fid, parent, child, quote, role='father', scope='虚构现实档案', uid='H'):
    return {'id': fid, 'parent': parent, 'child': child, 'parent_role': role,
            'scope': scope, 'expression': 'direct',
            'evidence_sets': [[{'unit_id': uid, 'quote': quote}]]}


def entities(names, aliases=None):
    aliases = aliases or {}
    return [{'id': n, 'name': n, 'aliases': aliases.get(n, [])} for n in names]


def query(leaf, roles=None):
    return {'operation': 'parent_chain', 'start': leaf,
            'steps': roles or ['father', 'father'], 'scope': '虚构现实档案'}


def review_seed(leaf, mid, root, first=None, second=None):
    first = first or f'{leaf}的父亲是{mid}。'
    second = second or f'{mid}的父亲是{root}。'
    fs = [fact('R1', mid, leaf, first), fact('R2', root, mid, second)]
    return {'question': f'只根据虚构现实档案，{leaf}的父亲的父亲是谁？',
            'materials': [{'unit_id': 'H', 'text': first + second + '窗台上放着一只蓝杯。'}],
            'facts': fs, 'query': query(leaf),
            'proposed_answer': [root], 'proposed_status': 'answerable',
            'proof': [{'from': leaf, 'relation': 'father', 'to': mid, 'quote': first},
                      {'from': mid, 'relation': 'father', 'to': root, 'quote': second}],
            'declared_conditions': {'review_scope': 'single_item', 'task_requires_two_steps': True,
                                    'proof_steps_are_ordered': True, 'fictional': True}}


def build_review():
    cases, refs = [], {}

    def add_pair(number, category, good, bad, evidence, rationale):
        for offset, candidate in enumerate((good, bad)):
            cid = f'HVR-{number:02}-{offset}'
            cases.append({'case_id': cid, 'family_id': f'HVR-{number:02}', 'track': 'synthetic',
                          'candidate': copy.deepcopy(candidate),
                          'rationale': '独立虚构材料，候选结论须以本次实际文本为准。',
                          'external_relation_hints': {}})
            refs[cid] = {'expected_valid': offset == 0, 'expected_verdict': 'pass' if offset == 0 else 'revise',
                         'major_defect': offset == 1, 'defect_category': 'none' if offset == 0 else category,
                         'expected_two_hop': ('shortcut' if offset == 1 and category == 'direct_answer_shortcut'
                                              else 'not_applicable' if good['proposed_status'] == 'insufficient_evidence' else 'necessary'),
                         'evidence': ''.join(m['text'] for m in candidate['materials']) if offset == 0 else evidence, 'rationale': rationale,
                         'reference_state': 'GPT独立制例与核验', 'human_review': 'not_run'}

    # Pair 1: adjacency is not itself a shortcut; an explicit grandfather clause is.
    good = review_seed('苏岚', '方原', '陶嵩')
    bad = copy.deepcopy(good)
    shortcut = '苏岚的祖父就是陶嵩。'
    bad['materials'][0]['text'] += shortcut
    add_pair(1, 'direct_answer_shortcut', good, bad, shortcut,
             '相邻两个直接父子事实仍须组合；坏例额外给出祖父目标关系，已不需要两步。')

    # Pair 2: an alias/coreference shortcut, not simply repeating the question.
    good = review_seed('孟禾', '沈圭', '石庭', '孟禾的父亲叫沈圭。', '沈圭的父亲名叫石庭。')
    alias = '石庭在村里又被叫作老石。'
    good['materials'][0]['text'] += alias
    bad = copy.deepcopy(good)
    shortcut = '老石进门时，大家向孟禾介绍：“这就是你的爷爷。”'
    bad['materials'][0]['text'] += shortcut
    add_pair(2, 'direct_answer_shortcut', good, bad, shortcut,
             '坏例以老石身份映射及爷爷称谓直接给祖父目标；正例别名本身不构成目标结论。')

    # Pair 3: preserving scope makes the correct claim insufficient, not a refusal error.
    good = review_seed('陆澄', '邵闻', '祁岑')
    q1, q2 = '陆澄的父亲是邵闻。', '祁岑是邵闻的父亲。'
    good['materials'][0]['text'] = f'现实档案记载：{q1}邵闻昨夜梦见有人说：“{q2}”'
    good['facts'] = [fact('R1', '邵闻', '陆澄', q1), fact('R2', '祁岑', '邵闻', q2, scope='梦境')]
    good['question'] = '只根据现实档案、不采用梦境，陆澄的父亲的父亲是谁？'
    good.update(proposed_answer=[], proposed_status='insufficient_evidence', proof=[])
    bad = copy.deepcopy(good)
    bad.update(proposed_answer=['祁岑'], proposed_status='answerable',
               proof=[{'from': '陆澄', 'relation': 'father', 'to': '邵闻', 'quote': q1},
                      {'from': '邵闻', 'relation': 'father', 'to': '祁岑', 'quote': q2}])
    add_pair(3, 'scope_mixing', good, bad, q2, '唯一第二跳只是梦境内容；现实范围没有完整证明。')

    # Pair 4: no prior-version material is delivered. The bad claim quotes a missing premise.
    good = review_seed('白芮', '乔川', '郁青')
    absent = '白芮的父亲是乔川。'
    remaining = '乔川的父亲是郁青。白芮今天参加了合唱排练。'
    good['materials'][0]['text'] = remaining
    good['facts'] = [fact('R2', '郁青', '乔川', '乔川的父亲是郁青。')]
    good.update(proposed_answer=[], proposed_status='insufficient_evidence', proof=[])
    bad = copy.deepcopy(good)
    bad.update(proposed_answer=['郁青'], proposed_status='answerable',
               proof=[{'from': '白芮', 'relation': 'father', 'to': '乔川', 'quote': absent},
                      {'from': '乔川', 'relation': 'father', 'to': '郁青', 'quote': '乔川的父亲是郁青。'}])
    add_pair(4, 'member_evidence_leakage', good, bad, {'absent_quote': absent, 'actual_text': remaining},
             '候选第一跳引文不在当前材料；即使它可能来自别的版本也不能补回。')

    # Pair 5: an over-wide annotation disappears while the actual supporting sentences remain.
    good = review_seed('温莱', '许端', '崔朗')
    body = good['materials'][0]['text']
    good['materials'][0]['text'] = body.replace('窗台上放着一只蓝杯。', '')
    good['declared_conditions']['removed_annotation_sha256'] = hashlib.sha256(body.encode()).hexdigest()
    bad = copy.deepcopy(good)
    bad.update(proposed_answer=[], proposed_status='insufficient_evidence', proof=[])
    add_pair(5, 'quote_only_failure', good, bad, good['materials'][0]['text'],
             '旧整段标注不再逐字存在，但两条关系原句完整存在，不能据失配拒答。')

    # Pair 6: a concrete unrelated deletion, with complete evidence left.
    good = review_seed('夏临', '江衡', '任泽')
    good['materials'][0]['text'] = '夏临的父亲是江衡。江衡的父亲是任泽。'
    good['declared_conditions']['deleted_text'] = '门口挂着一顶红帽子。'
    bad = copy.deepcopy(good)
    bad.update(proposed_answer=[], proposed_status='insufficient_evidence', proof=[])
    add_pair(6, 'irrelevant_deletion', good, bad, good['materials'][0]['text'],
             '删去帽子描述没有移除亲属事实；坏例证据不足状态为伪缺证。')

    # Pair 7: genuinely distinct father and mother branches, not duplicate wording.
    good = review_seed('林枝', '唐微', '季明')
    father_link = '林枝的父亲是周实。'
    father_top = '周实的父亲是季明。'
    mother_link, mother_top = '林枝的母亲是唐微。', '唐微的父亲是季明。'
    good['question'] = '只根据剩余虚构档案，沿“父母之一→父亲”两步能确定林枝的哪位长辈？'
    good['query'] = query('林枝', ['parent', 'father'])
    good['materials'][0]['text'] = father_top + mother_link + mother_top
    good['facts'] = [fact('R2', '季明', '周实', father_top),
                     fact('R3', '唐微', '林枝', mother_link, role='mother'),
                     fact('R4', '季明', '唐微', mother_top)]
    good['proof'] = [{'from': '林枝', 'relation': 'parent', 'to': '唐微', 'quote': mother_link},
                     {'from': '唐微', 'relation': 'father', 'to': '季明', 'quote': mother_top}]
    good['declared_conditions'].update(deleted_original_support_sha256=hashlib.sha256(father_link.encode()).hexdigest(),
                                      original_material_sha256=hashlib.sha256((father_link + father_top + mother_link + mother_top).encode()).hexdigest())
    bad = copy.deepcopy(good)
    bad.update(proposed_answer=[], proposed_status='insufficient_evidence', proof=[])
    add_pair(7, 'alternative_proof', good, bad, mother_link + mother_top,
             '父系首跳被删，但母系完整独立链仍到同一祖辈；这不是同一事实的重复措辞。')

    # Pair 8: explicit step-order failure while the endpoint answer stays correct.
    good = review_seed('池悠', '袁庭', '宁岳')
    bad = copy.deepcopy(good)
    bad['proof'] = list(reversed(bad['proof']))
    add_pair(8, 'ordered_proof', good, bad, {'correct_order': good['proof'], 'wrong_order': bad['proof']},
             '协议声明proof按起点依次排序；坏例先从袁庭走，不能与池悠起点对齐。')
    return cases, refs


def score_seed(cid, leaf, mid, root, *, aliases=None, extra_names=None):
    first, second = f'{leaf}的父亲是{mid}。', f'{mid}的父亲是{root}。'
    fs = [fact('S1', mid, leaf, first), fact('S2', root, mid, second)]
    origin = {'entities': entities([leaf, mid, root] + (extra_names or []), aliases), 'facts': fs, 'warnings': []}
    materials = [{'unit_id': 'H', 'text': first + second}]
    row = {'materials': materials, 'gold': {'status': 'answerable', 'answer_ids': [root],
                                          'proofs': [{'entities': [leaf, mid, root], 'facts': ['S1', 'S2']}]}}
    q = query(leaf)
    schema = json.loads((ROOT / 'src/multi_agent_v0/schemas.json').read_text(encoding='utf-8'))['blind-solver']
    payload = legacy_core().project(row, f'只根据虚构现实档案，{leaf}的父亲的父亲是谁？', schema)
    context_id = payload['contexts'][0]['context_id']
    ev = lambda quote: {'context_id': context_id, 'quote': quote}
    answer = {'status': 'answerable', 'answers': [root], 'evidence': [ev(first), ev(second)],
              'steps': [{'from': leaf, 'relation': 'father', 'to': mid, 'evidence': [ev(first)]},
                        {'from': mid, 'relation': 'father', 'to': root, 'evidence': [ev(second)]}],
              'brief_reason': '依次核对两条亲属记录。'}
    return {'case_id': cid, 'track': 'synthetic', 'answer': answer, 'payload': payload,
            'row': row, 'origin': origin, 'query': q}


def rebuild_payload(case, text=None, question=None):
    if text is not None:
        case['row']['materials'][0]['text'] = text
    schema = case['payload']['output_schema']
    question = question or case['payload']['question']
    case['payload'] = legacy_core().project(case['row'], question, schema)


def build_scoring():
    cases, refs = [], {}

    def add_pair(number, category, good, bad, evidence, rationale, bad_status=True, bad_answer=False, bad_proof=False):
        for offset, candidate in enumerate((good, bad)):
            candidate['case_id'] = f'HVS-{number:02}-{offset}'
            cases.append(copy.deepcopy(candidate))
            refs[candidate['case_id']] = {
                'expected_valid': offset == 0,
                'status_correct': True if offset == 0 else bad_status,
                'final_answer_correct': True if offset == 0 else bad_answer,
                'proof_supported_by_actual_member': True if offset == 0 else bad_proof,
                'all_quotes_located': all(e['quote'] in next(c['text'] for c in candidate['payload']['contexts']
                    if c['context_id'] == e['context_id']) for e in candidate['answer']['evidence'] +
                    [e for step in candidate['answer']['steps'] for e in step['evidence']]),
                'defect_category': 'none' if offset == 0 else category,
                'evidence': copy.deepcopy(candidate['answer']['evidence']) if offset == 0 and number in (5, 7) else evidence, 'rationale': rationale,
                'reference_state': 'GPT独立制例与核验', 'human_review': 'not_run'}

    good = score_seed('', '闻初', '贺南', '严朔')
    bad = copy.deepcopy(good)
    bad['answer']['answers'] = ['贺南']
    add_pair(1, 'final_answer_wrong_steps_right', good, bad, '闻初→贺南→严朔',
             '坏例步骤完整正确，但顶层最终答案是父亲而非祖父，不能据steps救回。', bad_proof=True)

    good = score_seed('', '顾霁', '罗斐', '赵清', aliases={'赵清': ['阿清']}, extra_names=['陈端'])
    text = good['row']['materials'][0]['text'] + '赵清在本村常被叫作阿清；陈端是另一个人。'
    rebuild_payload(good, text)
    good['answer']['answers'] = ['赵清（阿清）']
    bad = copy.deepcopy(good)
    bad['answer']['answers'] = ['赵清（陈端）']
    add_pair(2, 'conflicting_compound_alias', good, bad, '赵清在本村常被叫作阿清；陈端是另一个人。',
             '同一身份的组合称谓有效；组合两个不同人物不是可接受别称。', bad_proof=True)

    good = score_seed('', '江知', '傅远', '秦晏', aliases={'秦晏': ['晏伯']})
    rebuild_payload(good, good['row']['materials'][0]['text'] + '秦晏也被邻里称作晏伯。')
    good['answer']['answers'] = ['晏伯']
    bad = copy.deepcopy(good)
    bad['answer']['answers'] = ['秦晏的兄长']
    add_pair(3, 'descriptive_phrase_not_entity', good, bad, '秦晏也被邻里称作晏伯。',
             '秦晏的兄长不是秦晏本人的名字或别称，包含目标字串不能当匹配。', bad_proof=True)

    good = score_seed('', '叶满', '程安', '潘岳')
    early = '潘岳是程安的父亲。'
    name_only = '合唱名单依次写着潘岳、程安和叶满。'
    body = early + name_only + '叶满的父亲是程安。程安的父亲是潘岳。'
    rebuild_payload(good, body)
    ev = {'context_id': good['payload']['contexts'][0]['context_id'], 'quote': early}
    good['answer']['steps'][1]['evidence'] = [ev]
    good['answer']['evidence'][1] = ev
    bad = copy.deepcopy(good)
    bad_ev = {'context_id': good['payload']['contexts'][0]['context_id'], 'quote': name_only}
    bad['answer']['steps'][1]['evidence'] = [bad_ev]
    bad['answer']['evidence'][1] = bad_ev
    add_pair(4, 'name_cooccurrence_not_support', good, bad, {'alternative': early, 'non_support': name_only},
             '前段明确父子句虽不与登记后段重叠仍支持；名单同现不支持引用所声称的亲属关系。', bad_answer=True)

    good = score_seed('', '明绮', '邵路', '唐礼', extra_names=['许实'])
    denied = '许实不是邵路的父亲。'
    real = '唐礼是邵路的父亲。'
    body = '明绮的父亲是邵路。' + denied + real
    rebuild_payload(good, body)
    good['origin']['facts'][1]['evidence_sets'] = [[{'unit_id': 'H', 'quote': real}]]
    ev = {'context_id': good['payload']['contexts'][0]['context_id'], 'quote': real}
    good['answer']['evidence'][1] = ev
    good['answer']['steps'][1]['evidence'] = [ev]
    bad = copy.deepcopy(good)
    bad['answer']['answers'] = ['许实']
    bad['answer']['steps'][1]['to'] = '许实'
    bad_ev = {'context_id': good['payload']['contexts'][0]['context_id'], 'quote': denied}
    bad['answer']['evidence'][1] = bad_ev
    bad['answer']['steps'][1]['evidence'] = [bad_ev]
    add_pair(5, 'negation_ignored', good, bad, denied, '逐字引用正确不等于支持成立；明确否定不能当父子肯定事实。')

    good = score_seed('', '石宁', '卢冬', '陈荻')
    q1, dream = '石宁的父亲是卢冬。', '陈荻是卢冬的父亲。'
    rebuild_payload(good, q1 + f'卢冬在梦中听见有人说：“{dream}”',
                    '只根据现实档案、不采用梦境，石宁的父亲的父亲是谁？')
    good['row']['gold'] = {'status': 'insufficient_evidence', 'answer_ids': [], 'proofs': []}
    good['origin']['facts'][1]['scope'] = '梦境'
    good['origin']['facts'][1]['evidence_sets'] = [[{'unit_id': 'H', 'quote': dream}]]
    good['answer'].update(status='insufficient_evidence', answers=[], steps=[], evidence=[],
                          brief_reason='现实范围缺少卢冬父亲的记录，不能以梦境补足。')
    bad = copy.deepcopy(good)
    context_id = bad['payload']['contexts'][0]['context_id']
    ev = lambda quote: {'context_id': context_id, 'quote': quote}
    bad['answer'].update(status='answerable', answers=['陈荻'], evidence=[ev(q1), ev(dream)],
                         steps=[{'from': '石宁', 'relation': 'father', 'to': '卢冬', 'evidence': [ev(q1)]},
                                {'from': '卢冬', 'relation': 'father', 'to': '陈荻', 'evidence': [ev(dream)]}],
                         brief_reason='合并了现实与梦境记录。')
    add_pair(6, 'dream_scope_ignored', good, bad, dream, '问句排除梦境，坏例无现实完整证据却作答。', bad_status=False)

    good = score_seed('', '高予', '黎远', '何乔')
    bad = copy.deepcopy(good)
    bad['answer']['evidence'] = []
    for step in bad['answer']['steps']:
        step['evidence'] = []
    add_pair(7, 'missing_required_citation', good, bad, '所有evidence数组均为空。',
             '答案与路径可对，但明确要求每步可定位依据时，空引用不能算证明交付合格。', bad_answer=True)

    good = score_seed('', '林阿', '陈析', '姚白', extra_names=['庄序'])
    anaphor = '他是林阿的父亲。'
    full = '陈析推门进入。他是林阿的父亲。'
    wrong = '庄序坐在书桌旁看信。'
    rebuild_payload(good, full + '陈析的父亲叫姚白。' + wrong)
    good['origin']['facts'][0]['expression'] = 'coreference'
    good['origin']['facts'][0]['evidence_sets'] = [[{'unit_id': 'H', 'quote': full}]]
    good['origin']['facts'][1]['evidence_sets'] = [[{'unit_id': 'H', 'quote': '陈析的父亲叫姚白。'}]]
    context_id = good['payload']['contexts'][0]['context_id']
    ev = lambda quote: {'context_id': context_id, 'quote': quote}
    good['answer']['evidence'] = [ev(anaphor), ev('陈析的父亲叫姚白。')]
    good['answer']['steps'][0]['evidence'] = [ev(anaphor)]
    good['answer']['steps'][1]['evidence'] = [ev('陈析的父亲叫姚白。')]
    bad = copy.deepcopy(good)
    bad['answer']['evidence'][0] = ev(wrong)
    bad['answer']['steps'][0]['evidence'] = [ev(wrong)]
    add_pair(8, 'unrelated_citation', good, bad, {'resolved_quote': anaphor, 'antecedent': '陈析推门进入。', 'unrelated': wrong},
             '当前上下文有明确先行词时短引文可合法消解；无关看信句不能支持父亲身份。', bad_answer=True)
    return cases, refs


def selfcheck(review_cases, review_refs, score_cases, score_refs):
    assert len(review_cases) == len(review_refs) == len(score_cases) == len(score_refs) == 16
    assert sum(r['expected_valid'] for r in review_refs.values()) == 8
    assert sum(r['expected_valid'] for r in score_refs.values()) == 8
    assert set(review_refs) == {c['case_id'] for c in review_cases}
    assert set(score_refs) == {c['case_id'] for c in score_cases}
    located, intentionally_absent = 0, []
    for c in review_cases:
        material = {m['unit_id']: m['text'] for m in c['candidate']['materials']}
        joined = ''.join(material.values())
        for step in c['candidate']['proof']:
            if step['quote'] in joined:
                located += 1
            else:
                intentionally_absent.append({'case_id': c['case_id'], 'quote': step['quote']})
        for f in c['candidate']['facts']:
            for bundle in f['evidence_sets']:
                assert all(q['quote'] in material[q['unit_id']] for q in bundle)
    assert [r['case_id'] for r in intentionally_absent] == ['HVR-04-1']
    core = legacy_core()
    for c in score_cases:
        core.validate_projection(c['payload'])
        texts = {x['context_id']: x['text'] for x in c['payload']['contexts']}
        all_ev = c['answer']['evidence'] + [e for s in c['answer']['steps'] for e in s['evidence']]
        assert all(e['quote'] and e['quote'] in texts[e['context_id']] for e in all_ev)
    return {'review_cases': 16, 'review_pairs': 8, 'score_cases': 16, 'score_pairs': 8,
            'positive_negative_each_track': [8, 8], 'review_proof_quotes_located': located,
            'intentional_current_member_quote_absence': intentionally_absent,
            'score_nonempty_quote_substrings_all_located': True,
            'missing_citation_case_retained': 'HVS-07-1',
            'real_model_calls': 0}


def main():
    rc, rr = build_review()
    sc, sr = build_scoring()
    checks = selfcheck(rc, rr, sc, sr)
    cases = {'version': 'quality-v3-independent-forward-cases-v1', 'track': 'synthetic',
             'author_task': '/root/v3_heldout',
             'isolation': {'read_new_skills': False, 'read_new_implementation': False,
                           'read_new_flash_outputs': False, 'read_old_synthetic_case_texts': False},
             'review_cases': rc, 'score_cases': sc, 'selfcheck': checks}
    references = {'version': 'quality-v3-independent-forward-references-v3',
                  'reviewer_kind': 'independent_gpt_subagent', 'reference_state': 'GPT独立制例与核验',
                  'human_review': 'not_run', 'cases_sha256': digest(cases),
                  'review_references': rr, 'score_references': sr,
                  'freeze_policy': 'Do not revise cases/references based on treatment success; any reference correction creates a separately reported version.',
                  'formal_release': False}
    write_once(OUT / 'heldout-cases.json', cases)
    write_once(OUT / 'heldout-references-v3.json', references)
    print(json.dumps({'cases_sha256': digest(cases), 'references_sha256': digest(references), **checks}, ensure_ascii=False))


if __name__ == '__main__':
    main()
