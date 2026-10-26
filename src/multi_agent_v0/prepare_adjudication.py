"""Record the current GPT session's narrow, source-located correction.

This is a disclosed review intervention, never presented as a Flash output.
See README.md and the generated adjudication record.
"""
import copy
import json
from pathlib import Path

from core import active_facts, build_family, digest, validate_origin, validate_composer
from runner import ROOT, load


def main():
    out = ROOT / 'workspace/harness-prototype/runs/milestone-007'
    origin = load(out / 'facts.reviewed.json')
    composer = load(out / 'base.reviewed.json')
    materials = load(out / 'materials.frozen.json')
    rong = next(u for u in materials if u['unit_id'].endswith('-RONG'))
    ning = next(u for u in materials if u['unit_id'].endswith('-NING'))
    revised_origin = copy.deepcopy(origin)
    # These identities and one direct father edge occur verbatim in the new distractor.
    for eid, name, aliases in [('JIA-DAISHAN', '贾代善', ['代善']), ('JIA-ZHENG', '贾政', ['政老爹'])]:
        assert name in rong['text']
        existing = [e for e in revised_origin['entities'] if e['id'] == eid]
        if not existing:
            revised_origin['entities'].append({'id': eid, 'name': name, 'aliases': aliases})
    quote = '长子贾代善承袭了官爵，娶的也是金陵世代勋贵的史侯家的小姐为妻，生了两个儿子：长子贾赦，次子贾政。'
    assert quote in rong['text']
    revised_origin['facts'].append({'id': 'F-RONG-DAISHAN-ZHENG', 'parent': 'JIA-DAISHAN', 'child': 'JIA-ZHENG',
        'parent_role': 'father', 'scope': '冷子兴转述', 'expression': 'direct', 'evidence_sets': [[{'unit_id': rong['unit_id'], 'quote': quote}]]})
    deletion = '这位珍爷倒生了一个儿子，今年才十六岁，名叫贾蓉。'
    assert deletion in ning['text']
    revised_difficulty = {
        'mechanism': 'entity_confusion', 'distractor_unit_ids': [rong['unit_id']],
        'irrelevant_unit_ids': [next(u['unit_id'] for u in materials if u['unit_id'].endswith('C004-U0020'))],
        'deletions': [{'unit_id': ning['unit_id'], 'quote': deletion}],
        'expected_trap_answer_ids': ['JIA-DAISHAN'],
        'wrong_path_explanation': '正确链为贾蓉→父贾珍→父贾敬。主干扰新引入近名的贾政及明确的贾代善→贾政父子关系。首次错误是把宁府的中间人物“贾珍”误配为荣府“贾政”（珍／政近名，均姓贾）；随后沿来源中真实的贾政之父关系走向贾代善，得到错误答案。贾蓉→贾政不是合法关系，明确作为诱导的错误连接，不进入gold事实图。无关对照为薛家进京住处商议，不含上述近名中间人物的父系替代分支。',
        'invariants': ['基础问题及父系两步查询保持不变。',
                       '主干扰与无关对照分别添加完整来源选段，三种可答条件的答案均为贾敬且原证明保持。',
                       '必要支持删除仅删去贾珍→贾蓉的整句支持，保留贾敬→贾珍、其他人物及完整句法；不加缺失标记。',
                       '删证条件必须为insufficient_evidence，不能以作品记忆补出贾蓉的父亲；贾蓉名称在该条件中一并消失，作为本例诊断局限单独记录。',
                       '不要求Flash答错才保留；近名混淆是机制假设，实际诱错效果单独报告。']}
    validate_origin(revised_origin, materials)
    validate_composer(composer, revised_origin, materials)
    revised_family = build_family(composer, revised_difficulty, revised_origin, materials)
    base = revised_family['variants'][0]
    deleted = revised_family['variants'][-1]
    removed = set(base['active_fact_ids']) - set(deleted['active_fact_ids'])
    assert removed == {'F4'}, removed
    record = {'reviewer': 'GPT in the current Codex session', 'type': 'important_dispute_targeted_adjudication',
        'parent_origin_hash': digest(origin), 'parent_composer_hash': digest(composer),
        'reasons': ['Supervisor文字与布尔字段矛盾，不能按结构化false无限修订。',
                   '初轮抽取仅覆盖基础链，缺少主干扰中的实体与直接父子边；补登记已有来源，不补写事实。',
                   '把干扰首次错接明确为贾珍/贾政近名混淆，诱饵ID与解释一致。',
                   '采用第一步单边整句删除，避免删除多条边后出现悬空指代。'],
        'origin': revised_origin, 'difficulty': revised_difficulty, 'material_or_question_changed': False,
        'new_source_facts_invented': False, 'human_review': 'not_run',
        'next_gate': 'independent Flash Supervisor review, fresh Blind Solver for all four actual inputs, final Supervisor and GPT check',
        'revision_policy': 'normal content revisions exhausted and retained; one explicit GPT adjudication, no unbounded generator loop'}
    (out / 'gpt-adjudication.json').write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({'adjudication_prepared': True, 'removed_fact_ids': sorted(removed), 'family_answers': [v['gold']['answer_ids'] for v in revised_family['variants']]}, ensure_ascii=False))


if __name__ == '__main__':
    main()
