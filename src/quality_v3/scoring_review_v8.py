"""Pure identity projection and explicit protocol around the v7 semantic core.

Accepts optional hop audit explanations and binds array coverage dynamically.
It never repairs a ledger or changes a semantic verdict. See
[v7 core](scoring_review_v7.py) and [development protocol](../../QA_Generator/specs/evidence-contracts-v0.7.md).
"""
import copy
import json

import jsonschema

import scoring_review_v7 as CORE
import inventory_coverage as PURE_IDENTITIES

VERSION = 'quality-v0.8-scoring-protocol'
digest = CORE.digest
step_evidence_inputs = CORE.step_evidence_inputs
validate_evidence_review = CORE.validate_evidence_review
combine_evidence_reviews = CORE.combine_evidence_reviews
build_answer_payload = CORE.build_answer_payload
EVIDENCE_SCHEMA = copy.deepcopy(CORE.EVIDENCE_SCHEMA)
EVIDENCE_PROMPT = CORE.EVIDENCE_PROMPT + (
    '任何非空anchor的citation_id必须同时列在used_citation_ids中；'
    '不能确定时可以把相应anchor两字段留空，不可借用邻步引用。')
ANSWER_SCHEMA = copy.deepcopy(CORE.ANSWER_SCHEMA)
# Free audit text is accepted and preserved, but never consulted by the core.
ANSWER_SCHEMA['properties']['hop_reviews']['items']['properties']['reason'] = {'type': 'string'}
ANSWER_PROMPT = CORE.ANSWER_PROMPT + (
    '注意context_checks只对应submitted_steps，不对应query_plan/hop_reviews。'
    'submitted_steps为空时context_checks必须是[]，绝不自造step-0。'
    '每hop可另附reason审计说明，该说明不决定结果。每child必须列全当前context IDs。'
    'finding=missing必须是确定缺边；指代/冲突/角色尚不能裁定应写undetermined而非missing。'
    '当context标support_component时，considered_quotes必须原样包含本context全部正组citations'
    '或其更长原文，不能只列谓词而让正组引用无法溯回。'
    '每edge和每support_group也分别需要reason，不能遗漏；hop的reason才是可选。'
    '父母角色anchor应指向所问parent本人的父母角色或原文性别依据，'
    '子辈的儿子/女儿词不自动证明parent为父或母，必要时将parent的明确原文依据一起引用。'
    '原提交引文的context_consistency独立核该步原位置，不因另一跳坏而连带否定合法步骤。')


def build_scoring_package(answer, payload, row, origin, query):
    """Choose only pure registered identity surfaces, including query.start.

    The v7 core's direct ID lookup otherwise exposes an unfiltered canonical
    entity.name. Unresolved display identity remains unresolved, never missing.
    Shared negative identity guards: [inventory_coverage.py](inventory_coverage.py).
    """
    projected = copy.deepcopy(origin)
    bindings = {'entity_bindings': [{'id': e['id'], 'name': e['name'],
                                    'aliases': e.get('aliases', [])}
                                   for e in origin.get('entities', [])]}
    forms = PURE_IDENTITIES._identity_forms(bindings)
    unresolved, changed = [], []
    opaque = set()
    for entity in projected.get('entities', []):
        options = [surface for surface in [entity['name'], *entity.get('aliases', [])]
                   if surface in forms[entity['id']]]
        if options:
            chosen = options[0]
            entity['aliases'] = list(dict.fromkeys(s for s in options[1:] if s != chosen))
        else:
            chosen = 'UNRESOLVED_ENTITY_' + digest({'entity_id': entity['id']})[:20]
            entity['aliases'] = []
            unresolved.append(entity['id'])
            opaque.add(chosen)
        if chosen != entity['name']:
            changed.append(entity['id'])
        entity['name'] = chosen
    package = CORE.build_scoring_package(answer, payload, row, projected, query)
    if package['answer_input_base']['query']['start_surface'] in opaque:
        package['answer_input_base']['query']['start_resolution'] = 'unresolved'
    package['private_checks']['identity_display_projection'] = {
        'changed_entity_ids': changed, 'unresolved_entity_ids': unresolved,
        'source': 'Unique pure registered identity surfaces; per-stage projections retain only locally visible aliases.'}
    return CORE._seal(package)


def answer_schema(payload):
    """Narrow IDs/cardinalities without changing any semantic acceptance rule."""
    schema = copy.deepcopy(ANSWER_SCHEMA)
    properties = schema['properties']
    steps = payload['submitted_steps']
    checks = properties['context_checks']
    checks.update(minItems=len(steps), maxItems=len(steps))
    if not steps:
        checks['items'] = False
    else:
        variants = []
        for step in steps:
            item = copy.deepcopy(checks['items'])
            item['properties']['step_id'] = {'const': step['step_id']}
            ids = [c['citation_id'] for c in step['submitted_citations']]
            item['properties']['checked_citation_ids'].update(minItems=len(ids), maxItems=len(ids))
            item['properties']['checked_citation_ids']['items'] = {'enum': ids} if ids else False
            variants.append(item)
        checks['items'] = {'oneOf': variants}
    hops = properties['hop_reviews']
    hops.update(minItems=len(payload['query_plan']), maxItems=len(payload['query_plan']))
    hops['items']['properties']['hop_id'] = {'enum': [h['hop_id'] for h in payload['query_plan']]}
    contexts = [c['context_id'] for c in payload['contexts']]
    context_reviews = hops['items']['properties']['child_reviews']['items']['properties']['context_reviews']
    context_reviews.update(minItems=len(contexts), maxItems=len(contexts))
    context_reviews['items']['properties']['context_id'] = {'enum': contexts} if contexts else False
    return schema


def build_answer_contract(package, evidence_review):
    payload = build_answer_payload(package, evidence_review)
    step_ids = [s['step_id'] for s in payload['submitted_steps']]
    context_ids = [c['context_id'] for c in payload['contexts']]
    notes = ('本次允许的原提交step IDs=' + json.dumps(step_ids, ensure_ascii=False) + '；'
             '每child必须逐一核的context IDs=' + json.dumps(context_ids, ensure_ascii=False) + '。'
             '两类ID不可混用。空原步骤只令context_checks=[]，仍须从query.start核全文各hop。')
    return {'input': payload, 'output_schema': answer_schema(payload), 'skill': ANSWER_PROMPT + notes}


def _core_review(review, payload):
    jsonschema.validate(review, answer_schema(payload))
    result = copy.deepcopy(review)
    for hop in result['hop_reviews']:
        hop.pop('reason', None)
    return result


def validate_answer_review(review, answer_payload):
    return CORE.validate_answer_review(_core_review(review, answer_payload), answer_payload)


def merge_scoring_results(package, evidence_review, answer_review):
    payload = build_answer_payload(package, evidence_review)
    compatible = _core_review(answer_review, payload)
    result = CORE.merge_scoring_results(package, evidence_review, compatible)
    result.update(scorer_version=VERSION, semantic_core_version=CORE.VERSION,
        answer_review_sha256=digest(answer_review),
        optional_hop_reasons_preserved=sum('reason' in h for h in answer_review['hop_reviews']),
        protocol_adapter_repairs_semantic_content=False)
    return result
