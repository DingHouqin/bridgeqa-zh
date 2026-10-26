"""Conservative scoring repair; original scores remain independent historical data.

The structural layer resolves only registered identities. Citation location,
reference overlap and semantic entailment are deliberately separate outcomes.
"""
from __future__ import annotations

import copy
import importlib.util
import re
import unicodedata
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
_SPEC = importlib.util.spec_from_file_location('_quality_v3_legacy_core', ROOT/'src/multi_agent_v0/core.py')
CORE = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(CORE)


def _surface(value):
    """Normalize width/outer whitespace only; never remove arbitrary content."""
    return unicodedata.normalize('NFKC', value).strip() if isinstance(value, str) else ''


def identity_index(origin):
    index = {}
    for entity in origin.get('entities', []):
        for value in [entity['name']] + entity.get('aliases', []):
            surface = _surface(value)
            if surface:
                index.setdefault(surface, set()).add(entity['id'])
    return index


def resolve_entity(surface, origin_or_index):
    """Resolve an exact registered name or unambiguous composed aliases.

    Whole registered names are checked before splitting: parentheses may belong
    to a real disambiguated identity, e.g. 王氏（薛蟠之母）.
    """
    index = identity_index(origin_or_index) if 'entities' in origin_or_index else origin_or_index
    value = _surface(surface)
    if not value:
        return {'status': 'unresolved', 'entity_id': None, 'reason': 'empty_or_nonstring_surface'}
    if value in index:
        ids = index[value]
        return {'status': 'resolved' if len(ids) == 1 else 'ambiguous',
                'entity_id': next(iter(ids)) if len(ids) == 1 else None,
                'reason': 'exact_registered_surface', 'candidate_ids': sorted(ids)}
    composed = re.fullmatch(r'([^()]+)\(([^()]+)\)', value)
    if not composed:
        return {'status': 'unresolved', 'entity_id': None, 'reason': 'not_an_exact_registered_surface'}
    parts = [_surface(p) for p in composed.groups()]
    resolutions = [index.get(p, set()) for p in parts]
    if not all(len(ids) == 1 for ids in resolutions):
        return {'status': 'ambiguous' if any(len(ids) > 1 for ids in resolutions) else 'unresolved',
                'entity_id': None, 'reason': 'composed_alias_has_unknown_or_ambiguous_part', 'parts': parts}
    ids = {next(iter(s)) for s in resolutions}
    if len(ids) != 1:
        return {'status': 'conflicting', 'entity_id': None, 'reason': 'composed_alias_names_different_entities', 'parts': parts}
    return {'status': 'resolved', 'entity_id': next(iter(ids)), 'reason': 'composed_registered_equivalent_aliases', 'parts': parts}


def _compare_surfaces(surfaces, targets, index):
    resolutions = [resolve_entity(value, index) for value in surfaces]
    if len(surfaces) != len(targets):
        return 'incorrect', resolutions
    if any(r['status'] == 'conflicting' for r in resolutions):
        return 'incorrect', resolutions
    if any(r['status'] == 'ambiguous' for r in resolutions):
        return 'needs_semantic_review', resolutions
    if any(r['status'] != 'resolved' for r in resolutions):
        return 'needs_semantic_review', resolutions
    ids = [r['entity_id'] for r in resolutions]
    return ('correct' if len(set(ids)) == len(ids) and set(ids) == set(targets) else 'incorrect'), resolutions


def _located(evidence, texts):
    return (isinstance(evidence, dict) and isinstance(evidence.get('quote'), str)
            and bool(evidence['quote']) and evidence.get('context_id') in texts
            and evidence['quote'] in texts[evidence['context_id']])


def _validate_member_payload(payload):
    CORE.validate_projection(payload)
    contexts = payload['contexts']
    ids = [c['context_id'] for c in contexts]
    if len(ids) != len(set(ids)) or any(not isinstance(c['text'], str) for c in contexts):
        raise ValueError('Current-member contexts must have unique IDs and string text')


def _role_satisfies(actual, requested):
    return actual == requested or requested == 'parent' and actual in ('father', 'mother')


def _path_shape(steps, query, allowed_targets, index):
    """Check mechanics without treating the registered proof list as exhaustive."""
    if len(steps) != len(query.get('steps', [])) or not steps:
        return 'incorrect'
    endpoints = [(resolve_entity(s.get('from'), index), resolve_entity(s.get('to'), index)) for s in steps]
    if any(not _role_satisfies(s.get('relation'), role) for s, role in zip(steps, query['steps'])):
        return 'incorrect'
    if any(r['status'] == 'conflicting' for pair in endpoints for r in pair):
        return 'incorrect'
    first, last = endpoints[0][0], endpoints[-1][1]
    if first['status'] == 'resolved' and first['entity_id'] != query.get('start'):
        return 'incorrect'
    if last['status'] == 'resolved' and allowed_targets and last['entity_id'] not in allowed_targets:
        return 'incorrect'
    for (_, previous), (following, _) in zip(endpoints, endpoints[1:]):
        if previous['status'] == following['status'] == 'resolved' and previous['entity_id'] != following['entity_id']:
            return 'incorrect'
    if any(r['status'] != 'resolved' for pair in endpoints for r in pair):
        return 'needs_semantic_review'
    return 'correct'


def assess_structural(answer, payload, row, origin, query):
    """Return separate structural dimensions and a conservative review route.

    ``payload`` is the unchanged blind-solver allowlist projection. Missing span
    overlap is a review trigger, never a natural-language unsupported verdict.
    Even positive overlap remains only a proxy, not semantic acceptance.
    """
    _validate_member_payload(payload)
    index = identity_index(origin)
    gold = row['gold']
    statuses_match = answer.get('status') == gold['status']
    answers = answer.get('answers', [])
    steps = answer.get('steps', [])
    answer_match, resolutions = _compare_surfaces(answers, gold.get('answer_ids', []), index)
    if not statuses_match:
        answer_match = 'incorrect'
    texts = {c['context_id']: c['text'] for c in payload['contexts']}
    evidence = answer.get('evidence', []) + [e for s in steps for e in s.get('evidence', [])]
    quotes_located = all(_located(e, texts) for e in evidence)
    step_citations_present = all(bool(s.get('evidence')) for s in steps)
    path_state = ('needs_semantic_review' if statuses_match and answer.get('status') not in ('answerable', 'insufficient_evidence')
                  else 'incorrect')
    span_proxy = False
    matched_proof = None
    path_shape = None
    if answer.get('status') == 'insufficient_evidence':
        path_state = 'correct' if statuses_match and not steps and not answers else 'incorrect'
        span_proxy = path_state == 'correct'
    elif answer.get('status') == 'answerable':
        path_shape = _path_shape(steps, query, gold.get('answer_ids', []), index)
        path_state = 'incorrect' if path_shape == 'incorrect' else 'needs_semantic_review'
        by_id = {f['id']: f for f in origin.get('facts', [])}
        for proof in gold.get('proofs', []):
            if path_shape != 'correct':
                continue
            expected = proof.get('entities', [])
            fact_ids = proof.get('facts', [])
            if len(expected) != len(steps) + 1 or len(fact_ids) != len(steps):
                continue
            checks = []
            for i, step in enumerate(steps):
                left = resolve_entity(step.get('from'), index)
                right = resolve_entity(step.get('to'), index)
                fact = by_id.get(fact_ids[i], {})
                role_ok = (_role_satisfies(step.get('relation'), query['steps'][i])
                           and _role_satisfies(fact.get('parent_role'), step.get('relation'))
                           and fact.get('child') == expected[i] and fact.get('parent') == expected[i+1])
                if not role_ok:
                    checks.append('incorrect')
                elif left['status'] == 'conflicting' or right['status'] == 'conflicting':
                    checks.append('incorrect')
                elif left['status'] != 'resolved' or right['status'] != 'resolved':
                    checks.append('needs_semantic_review')
                else:
                    checks.append('correct' if left['entity_id'] == expected[i] and right['entity_id'] == expected[i+1] else 'incorrect')
            if all(c == 'correct' for c in checks):
                path_state = 'correct'
                matched_proof = proof
                coverage = []
                for fact_id, step in zip(proof.get('facts', []), steps):
                    fact = by_id.get(fact_id, {})
                    coverage.append(any(all(any(
                        e.get('context_id') == 'P' + CORE.digest(q['unit_id'])[:10]
                        and CORE.quote_spans_overlap(q.get('quote', ''), e.get('quote', ''), texts.get(e.get('context_id'), ''))
                        for e in step.get('evidence', [])) for q in bundle)
                        for bundle in fact.get('evidence_sets', [])))
                span_proxy |= bool(len(coverage) == len(steps) and all(coverage))
    if answer.get('status') == 'answerable' and not steps:
        path_state = 'incorrect'
    contradiction = None
    if answer.get('status') == 'answerable' and matched_proof and answer_match == 'incorrect':
        contradiction = 'top_level_answer_does_not_identify_the_permitted_target_even_though_steps_match'
    structural_success = bool(statuses_match and answer_match == 'correct' and path_state == 'correct'
                              and quotes_located and step_citations_present and span_proxy)
    hard_defect = (not statuses_match or answer_match == 'incorrect' or path_state == 'incorrect'
                   or not quotes_located or not step_citations_present)
    try:
        legacy = CORE.check_solver(answer, payload, row, origin, query)
    except (KeyError, TypeError, IndexError) as exc:
        legacy = {'legacy_error': type(exc).__name__}
    return {'scorer_version': 'quality-v0.3-structural',
            'status_correct': statuses_match,
            'final_answer_match': answer_match,
            'answer_resolutions': resolutions,
            'path_match': path_state,
            'path_shape': path_shape,
            'evidence_quotes_located': quotes_located,
            'step_citations_present': step_citations_present,
            'reference_span_coverage_proxy': span_proxy,
            'structural_proxy_success': structural_success,
            'evidence_semantic_status': 'needs_semantic_review',
            'provisional_outcome': 'incorrect' if hard_defect else 'needs_semantic_review',
            'top_level_answer_contradiction': contradiction,
            'legacy': legacy,
            'automatic_release_eligible': False,
            'limits': ['Identity matching uses registered aliases only; unresolved is not an automatic incorrect answer.',
                       'Reference overlap is neither necessary nor sufficient for textual entailment.',
                       'A mechanically valid unregistered path requires semantic review; registered proofs are not assumed exhaustive.',
                       'A correct path never repairs an incorrect top-level final answer.']}


_EVIDENCE = {'type': 'object', 'properties': {'context_id': {'type': 'string'}, 'quote': {'type': 'string', 'minLength': 1}},
             'required': ['context_id', 'quote'], 'additionalProperties': False}
_TRI = {'enum': ['correct', 'incorrect', 'undetermined']}
SEMANTIC_SCHEMA = {'type': 'object', 'properties': {
    'verdict': {'enum': ['supported', 'incorrect', 'needs_adjudication']},
    'status_correct': _TRI, 'answer_correct': _TRI,
    'proof_support': {'enum': ['supported', 'unsupported', 'undetermined', 'not_applicable']},
    'evidence': {'type': 'array', 'items': _EVIDENCE},
    'issues': {'type': 'array', 'items': {'type': 'string'}}, 'reason': {'type': 'string'}},
    'required': ['verdict', 'status_correct', 'answer_correct', 'proof_support', 'evidence', 'issues', 'reason'],
    'additionalProperties': False}
SEMANTIC_BASELINE_PROMPT = ('你是问答评分审查员。仅依实际材料，分别核对候选作答的状态、顶层答案及证明是否成立。'
    '参考声明也须由材料支持，不能作为裁定权威。输出给定schema的JSON，判断不能确定时保留未裁定。')


def semantic_payload(answer, payload, row, origin, query):
    """Only current-member text plus scoring claims; no independent audit labels.

    This is a grader input, not a blind solver input. Reference statements are
    deliberately labeled claims. Evidence absent from this member is removed.
    """
    _validate_member_payload(payload)
    texts = {c['context_id']: c['text'] for c in payload['contexts']}
    whole_text = '\n'.join(texts.values())
    bindings = []
    for entity in origin.get('entities', []):
        visible = [v for v in [entity['name']] + entity.get('aliases', []) if v and v in whole_text]
        if visible:
            bindings.append({'entity_id': entity['id'], 'visible_registered_surfaces': visible,
                             'identity_binding_is_reference_claim': True})
    facts = []
    for fact in origin.get('facts', []):
        sets = []
        for bundle in fact.get('evidence_sets', []):
            converted = [{'context_id': 'P' + CORE.digest(q['unit_id'])[:10], 'quote': q['quote']} for q in bundle]
            if converted and all(_located(q, texts) for q in converted):
                sets.append(converted)
        if sets:
            facts.append({k: copy.deepcopy(fact[k]) for k in ('id', 'parent', 'child', 'parent_role', 'scope') if k in fact})
            facts[-1]['located_evidence_sets'] = sets
    return {'task': 'semantic_scoring_review', 'question': payload['question'], 'query': copy.deepcopy(query),
            'contexts': copy.deepcopy(payload['contexts']), 'candidate_response': copy.deepcopy(answer),
            'visible_entity_bindings': bindings,
            'reference_claims': {'status': row['gold']['status'], 'answer_ids': copy.deepcopy(row['gold'].get('answer_ids', [])),
                                 'proofs': copy.deepcopy(row['gold'].get('proofs', [])), 'facts': facts},
            'contract': '只用当前成员实际材料。参考是待核验声明，不是独立裁定。别称、证据表达不必逐字等于参考；逐字引文必须位于所给context。最终答案与步骤分开，不能用正确步骤救回错答案。不确定标needs_adjudication。'}


def validate_semantic_review(review, payload):
    """Reject invalid citations and inconsistent supported verdicts, never repair."""
    import jsonschema
    jsonschema.validate(review, SEMANTIC_SCHEMA)
    texts = {c['context_id']: c['text'] for c in payload['contexts']}
    if not all(_located(e, texts) for e in review['evidence']):
        raise ValueError('Semantic reviewer citation is absent from this actual member')
    if review['verdict'] == 'incorrect' and not (
            review['status_correct'] == 'incorrect' or review['answer_correct'] == 'incorrect'
            or review['proof_support'] == 'unsupported'):
        raise ValueError('Incorrect verdict requires an explicit incorrect status/answer or unsupported proof; uncertainty is not incorrectness')
    if review['verdict'] == 'supported':
        if review['status_correct'] != 'correct' or review['answer_correct'] != 'correct':
            raise ValueError('Supported verdict contradicts answer or status findings')
        status = payload['candidate_response'].get('status')
        if status == 'answerable' and (review['proof_support'] != 'supported' or not review['evidence']):
            raise ValueError('Answerable supported verdict requires located proof evidence')
        if status == 'insufficient_evidence':
            response = payload['candidate_response']
            if response.get('answers') or response.get('steps') or review['proof_support'] not in ('supported', 'not_applicable'):
                raise ValueError('Insufficient-evidence success contradicts nonempty answer/path or proof finding')
    return True
