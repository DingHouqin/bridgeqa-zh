"""Member-isolated review and mechanical gates; see quality_v3/README.md.

Registered graph contracts are checked here. Natural-language necessity and
support remain explicit review judgments, never inferred from regex hits.
"""
from __future__ import annotations

import copy
import hashlib
import json
import re


def digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
        separators=(',', ':')).encode()).hexdigest()


def _uid(row):
    return row.get('unit_id', row.get('context_id'))


def _quote(q, contexts):
    uid = q.get('unit_id', q.get('context_id'))
    quote = q.get('quote', '')
    if uid in contexts and isinstance(quote, str) and quote and quote in contexts[uid]:
        return {'context_id': uid, 'quote': quote}
    return None


def _clean_proof(proof, contexts):
    if not isinstance(proof, dict):
        raise ValueError('Proof must be an object')
    result = {k:copy.deepcopy(proof[k]) for k in ('entities', 'facts', 'from', 'to', 'relation') if k in proof}
    citations = proof.get('evidence', [])
    if 'quote' in proof:
        uid = proof.get('unit_id', proof.get('context_id'))
        if uid is not None:
            citations = list(citations) + [{'context_id':uid, 'quote':proof['quote']}]
        else:
            # A single-item legacy proof sometimes omits a unit. Locate only a
            # unique actual context; never send an absent historical quotation.
            located = [uid for uid, text in contexts.items() if proof['quote'] and proof['quote'] in text]
            if len(located) == 1:
                citations = list(citations) + [{'context_id':located[0], 'quote':proof['quote']}]
    if citations or 'quote' in proof or 'evidence' in proof:
        result['evidence'] = [item for q in citations if (item := _quote(q, contexts))]
    return result


def project_member(candidate, variant_index=None):
    """Project exactly one member; do not copy generic candidate dictionaries.

    Missing/unlocated citation text is intentionally not forwarded. A candidate
    relation remains a claim, not evidence. Internal member labels and prior
    materials are absent from this object.
    """
    if 'variants' in candidate and candidate['variants']:
        if variant_index is None:
            raise ValueError('A family requires an explicit member index')
        if not isinstance(variant_index, int) or variant_index < 0 or variant_index >= len(candidate['variants']):
            raise ValueError('Invalid member index')
        row = candidate['variants'][variant_index]
        materials = row['materials']; gold = row['gold']
        claim = {'status': gold['status'], 'answer_ids':copy.deepcopy(gold.get('answer_ids', [])),
                 'proofs':copy.deepcopy(gold.get('proofs', []))}
        facts = candidate.get('origin', {}).get('facts', [])
        wanted = {fid for p in claim['proofs'] for fid in p.get('facts', [])}
        facts = [f for f in facts if f['id'] in wanted]
    else:
        if variant_index is not None:
            raise ValueError('Single-item candidate does not take a member index')
        materials = candidate.get('materials', [])
        claim = {'status':candidate.get('proposed_status', candidate.get('status')),
                 'answer_ids':copy.deepcopy(candidate.get('proposed_answer', candidate.get('answer_ids', []))),
                 'proofs':copy.deepcopy(candidate.get('proofs', candidate.get('proof', [])))}
        facts = candidate.get('facts', candidate.get('origin', {}).get('facts', []))
    contexts = {}
    for unit in materials:
        uid = _uid(unit)
        if not uid or uid in contexts or not isinstance(unit.get('text'), str):
            raise ValueError('Duplicate/invalid actual context')
        contexts[uid] = unit['text']
    clean_facts = []
    for f in facts:
        item = {k:copy.deepcopy(f[k]) for k in ('id', 'parent', 'child', 'parent_role', 'scope', 'expression') if k in f}
        groups = []
        for bundle in f.get('evidence_sets', []):
            cleaned = [_quote(q, contexts) for q in bundle]
            # A conjunctive bundle is retained only as a complete bundle.
            if bundle and all(cleaned):
                groups.append(cleaned)
        item['evidence_sets'] = groups
        clean_facts.append(item)
    claim['proofs'] = [_clean_proof(p, contexts) for p in claim['proofs']]
    claim['facts'] = clean_facts
    payload = {'question':candidate['question'],
               'query':copy.deepcopy(candidate.get('query', {})),
               'contexts':[{'context_id':uid, 'text':text} for uid, text in contexts.items()],
               'candidate':claim,
               'review_contract':'仅使用本次contexts。candidate是待核声明，不是参考答案。各proof事实按entities路径逐步对应。每步合法且存在不等于两步必要；查直接结论及更短合法路径。缺少当前材料支持时不能从其他成员、先前译文、事实记忆或引文残片补回。只核对当前候选，不虚构它已修订。'}
    validate_member_projection(payload)
    return payload


def validate_member_projection(payload):
    if set(payload) != {'question', 'query', 'contexts', 'candidate', 'review_contract'}:
        raise ValueError('Unexpected member payload field')
    if any(set(c) != {'context_id', 'text'} for c in payload['contexts']):
        raise ValueError('Context metadata leak')
    if set(payload['candidate']) != {'status', 'answer_ids', 'proofs', 'facts'}:
        raise ValueError('Unexpected candidate claim field')
    if len({c['context_id'] for c in payload['contexts']}) != len(payload['contexts']):
        raise ValueError('Duplicate contexts')
    return True


def ordered_proof_check(payload):
    """Verify supplied proof syntax/direction/scope; never establish entailment."""
    query = payload.get('query', {}); candidate = payload['candidate']
    defects = []; review = []
    def fail(code, detail):
        defects.append({'code':code, 'detail':detail})
    status = candidate.get('status'); answers = candidate.get('answer_ids', [])
    proofs = candidate.get('proofs', []); facts = {f['id']:f for f in candidate.get('facts', [])}
    if status == 'insufficient_evidence':
        if answers or proofs:
            fail('insufficient_claim_has_answer_or_proof', '证据不足声明须为空答案及空完整证明。')
        return {'structural_valid':not defects, 'defects':defects, 'review_required':review,
                'semantic_validity_established':False}
    if status not in ('answerable', 'ambiguous', 'conflict'):
        fail('unknown_claim_status', str(status))
    if status == 'answerable' and len(answers) != 1:
        fail('answer_cardinality', '可答声明必须有一个候选目标。')
    if status in ('answerable', 'ambiguous') and not proofs:
        fail('missing_proof', '候选可答声明没有证明。')
    expected_steps = query.get('steps')
    if not expected_steps or query.get('start') is None:
        review.append({'code':'query_not_structurally_specified',
                       'detail':'缺少显式起点／步骤，须语义核对问句，不能从待审证明反推并当作已核查询。'})
    # Legacy single-item proofs are ordered step records instead of graph paths.
    if proofs and all('from' in p and 'to' in p for p in proofs):
        entities = [proofs[0]['from']] + [p['to'] for p in proofs]
        if len(set(entities)) != len(entities):
            fail('proof_cycle_or_repeat', '不能用循环关系冒充必要两步。')
        if any(proofs[i]['to'] != proofs[i+1]['from'] for i in range(len(proofs)-1)):
            fail('disconnected_proof', '相邻步骤没有共用桥接实体。')
        if expected_steps:
            if len(proofs) != len(expected_steps):fail('proof_length', '步骤数不符合query。')
            if entities[0] != query['start']:fail('proof_start', '证明没有从query起点开始。')
            for i, step in enumerate(proofs[:len(expected_steps)]):
                if step.get('relation') not in ('parent','father','mother') or (expected_steps[i] != 'parent' and step.get('relation') != expected_steps[i]):
                    fail('proof_role', '步骤角色不符合query。')
        if answers and entities[-1] not in answers:fail('proof_answer', '证明终点不是候选答案。')
    else:
        for proof in proofs:
            entities = proof.get('entities', []); fids = proof.get('facts', [])
            if len(entities) != len(fids)+1 or not fids:
                fail('proof_shape', 'entities必须比有序facts多一项，且proof不能为空。');continue
            if len(set(entities)) != len(entities) or len(set(fids)) != len(fids):
                fail('proof_cycle_or_repeat', '不能用循环或重复事实冒充两次必要查找。')
            if expected_steps:
                if len(fids) != len(expected_steps):fail('proof_length', '事实数不符合query步骤数。')
                if entities[0] != query['start']:fail('proof_start', '证明没有从query起点开始。')
            if answers and entities[-1] not in answers:fail('proof_answer', '证明终点不是候选答案。')
            for i, fid in enumerate(fids):
                fact = facts.get(fid)
                if not fact:
                    fail('unknown_proof_fact', str(fid));continue
                if fact.get('child') != entities[i] or fact.get('parent') != entities[i+1]:
                    fail('ordered_fact_endpoint_mismatch', f'{fid}不支持第{i}步的child→parent方向。')
                if expected_steps and i < len(expected_steps):
                    role = expected_steps[i]
                    if fact.get('parent_role') not in ('parent','father','mother') or (role != 'parent' and fact.get('parent_role') != role):
                        fail('proof_role', f'{fid}角色不符合query第{i}步。')
                    scopes = query.get('scope_by_step')
                    wanted_scope = scopes[i] if scopes and i < len(scopes) else query.get('scope')
                    if wanted_scope is not None and fact.get('scope') != wanted_scope:
                        fail('proof_scope', f'{fid}陈述范围不符合query第{i}步。')
    return {'structural_valid':not defects, 'defects':defects, 'review_required':review,
            'semantic_validity_established':False}


def literal_shortcut_scan(payload):
    """Locate literal target expressions. All matches need semantic confirmation.

    A negation, dream quotation, rejected allegation or different scope can
    contain the same lexical pattern. Therefore no automatic defect verdict.
    """
    query=payload.get('query', {}); start=query.get('start'); roles=query.get('steps', [])
    terms={('father','father'):['祖父','爷爷','父亲的父亲'],
           ('father','mother'):['祖母','奶奶','父亲的母亲'],
           ('mother','father'):['外祖父','外公','母亲的父亲'],
           ('mother','mother'):['外祖母','外婆','母亲的母亲']}.get(tuple(roles), [])
    if not start or not terms:return {'review_required':False,'candidates':[], 'automatic_defect':False}
    found=[]
    for context in payload['contexts']:
        for match in re.finditer(r'[^。！？\n]+[。！？]?', context['text']):
            sentence=match.group()
            if any(re.search(re.escape(start)+r'.{0,6}'+re.escape(term), sentence) for term in terms):
                found.append({'context_id':context['context_id'],'quote':sentence,
                              'start':match.start(),'end':match.end()})
    return {'review_required':bool(found),'candidates':found,'automatic_defect':False}


EVIDENCE_SCHEMA={'type':'object','properties':{'context_id':{'type':'string'},'quote':{'type':'string','minLength':1}},
                 'required':['context_id','quote'],'additionalProperties':False}
REVIEW_SCHEMA={'type':'object','properties':{
    'verdict':{'enum':['pass','revise','needs_adjudication']},
    'candidate_status_supported':{'type':'boolean'},'answer_supported':{'type':'boolean'},'proof_supported':{'type':'boolean'},
    'two_hop':{'type':'object','properties':{'verdict':{'enum':['necessary','shortcut','not_applicable','undetermined']},
                'evidence':{'type':'array','items':EVIDENCE_SCHEMA},'reason':{'type':'string'}},
                'required':['verdict','evidence','reason'],'additionalProperties':False},
    'step_reviews':{'type':'array','items':{'type':'object','properties':{'step':{'type':'integer','minimum':0},
                'supported':{'type':'boolean'},'evidence':{'type':'array','items':EVIDENCE_SCHEMA},'reason':{'type':'string'}},
                'required':['step','supported','evidence','reason'],'additionalProperties':False}},
    'findings':{'type':'array','items':{'type':'object','properties':{'code':{'type':'string'},
                'severity':{'enum':['major','minor','uncertain']},'explanation':{'type':'string'},
                'evidence':{'type':'array','items':EVIDENCE_SCHEMA}},
                'required':['code','severity','explanation','evidence'],'additionalProperties':False}},
    'reason':{'type':'string'}},
    'required':['verdict','candidate_status_supported','answer_supported','proof_supported','two_hop','step_reviews','findings','reason'],
    'additionalProperties':False}

GENERIC_REVIEW_PROMPT='''你是独立的题目质量审查员，只依据当前输入contexts审查candidate声明，不使用作品记忆。candidate不是权威答案，不得默认已经修订。query限定每一步关系、陈述范围及起点；candidate proofs中的facts按entities路径有序对应。按schema输出JSON，判定候选状态、答案和证明是否受到本成员材料支持，并判断任务两步是否必要。无法确定时needs_adjudication。证据必须逐字引用当前contexts；不要引用输入之外材料或另一成员。findings指出具体缺陷，不必为每个候选找错。step_reviews为所审的两步给出定位；证据不足候选可用空step_reviews。两步必要性、支持充分性与最终裁定必须一致。'''


def review_gate(answer, payload, structural=None):
    """Gate model output without rewriting its raw verdict or findings.

    ``local_decision`` is the usable model disposition. Program structural
    rejection is separate so an improvement due to deterministic checks is not
    misreported as a skill gain.
    """
    contexts={c['context_id']:c['text'] for c in payload['contexts']}
    errors=[]
    citations=[]
    citations.extend(answer.get('two_hop', {}).get('evidence', []))
    for step in answer.get('step_reviews', []):citations.extend(step.get('evidence', []))
    for finding in answer.get('findings', []):citations.extend(finding.get('evidence', []))
    if any(not q.get('quote') or q.get('context_id') not in contexts or q['quote'] not in contexts[q['context_id']] for q in citations):
        errors.append('review_evidence_not_in_current_member')
    if answer.get('verdict') == 'pass':
        if not all(answer.get(k) is True for k in ('candidate_status_supported','answer_supported','proof_supported')):
            errors.append('pass_contradicts_support_flags')
        if any(f.get('severity') in ('major','uncertain') for f in answer.get('findings', [])):
            errors.append('pass_contradicts_findings')
        status=payload['candidate']['status'];two_hop=answer.get('two_hop', {}).get('verdict')
        if status in ('answerable','ambiguous'):
            if two_hop != 'necessary':errors.append('pass_without_two_hop_necessity')
            count=len(payload.get('query',{}).get('steps',[])) or 2
            steps=answer.get('step_reviews',[])
            if sorted(s.get('step') for s in steps) != list(range(count)):
                errors.append('step_review_coverage')
            elif any(not s.get('supported') or not s.get('evidence') for s in steps):
                errors.append('step_review_missing_support')
        elif status == 'insufficient_evidence' and two_hop != 'not_applicable':
            errors.append('insufficient_claim_necessity_not_applicable')
    if answer.get('two_hop',{}).get('verdict') == 'shortcut' and not answer['two_hop'].get('evidence'):
        errors.append('shortcut_claim_without_location')
    structural=structural or ordered_proof_check(payload)
    local=answer.get('verdict') if not errors else 'protocol_failure'
    disposition=('needs_revision_structural' if not structural['structural_valid'] else
                 'needs_adjudication' if errors or structural.get('review_required') else local)
    return {'protocol_valid':not errors,'protocol_errors':errors,'local_decision':local,
            'program_disposition':disposition,'structural':structural,
            'raw_verdict':answer.get('verdict'),'automatic_release_eligible':False,
            'semantic_validity_established_by_program':False}
