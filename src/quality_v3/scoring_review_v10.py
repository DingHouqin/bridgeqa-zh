"""Display-name query binding around the frozen flat traversal contract.

Mechanical materialization is an explicit copy of [v9](scoring_review_v9.py).
Final semantic gates use the narrow, auditable [v10 policy fork](scoring_semantics_v10.py)
of frozen [v7](scoring_review_v7.py); no old module or global is patched.
First-hop constraints express the query subject, never a parentage assertion.
"""
from __future__ import annotations

import copy
import json

import jsonschema

import scoring_review_v9 as FLAT
import scoring_semantics_v10 as POLICY


PREVIOUS = FLAT.PREVIOUS
CORE = POLICY
VERSION = 'quality-v0.10-display-name-flat-scoring-review'
digest = FLAT.digest
build_scoring_package = FLAT.build_scoring_package
step_evidence_inputs = FLAT.step_evidence_inputs
validate_evidence_review = FLAT.validate_evidence_review
combine_evidence_reviews = FLAT.combine_evidence_reviews
EVIDENCE_SCHEMA = copy.deepcopy(FLAT.EVIDENCE_SCHEMA)
EVIDENCE_PROMPT = FLAT.EVIDENCE_PROMPT
ANSWER_SCHEMA = copy.deepcopy(FLAT.ANSWER_SCHEMA)
ANSWER_PROMPT = (
    '所有frontier/child/parent都写当前原文姓名或已给唯一纯姓名别名，不写后台实体ID。'
    'query只公开start_surface作为查询起点；它已经是第一hop的child，不能改成语法主语。'
    '例如“甲是乙的父亲”：child=乙,parent=甲；第一hop查询乙时frontier=["乙"]，'
    'child_findings/context_reviews/edge_groups的child均为乙，绝不能填甲。'
    'child_findings始终审本hop frontier的child；后hop只能从上一hop真实parent继续。'
    '第一hop格式锁定查询姓名只说明审谁，不证明该姓名有任何父母边；缺证或未决仍照实输出。'
    + FLAT.ANSWER_PROMPT.replace('从原query.start遍历', '从query.start_surface遍历'))


def build_answer_payload(package, evidence_review):
    payload = FLAT.build_answer_payload(package, evidence_review)
    payload['version'] = VERSION
    # The original identifier remains in the sealed native package for audit,
    # but is absent from the model-facing query and every model-facing note.
    payload['query'].pop('start', None)
    payload['flat_input_sha256'] = digest({k: v for k, v in payload.items() if k != 'flat_input_sha256'})
    return payload


def _internal_flat_payload(payload):
    """Translate protocol bindings only, without restoring hidden query.start."""
    if (payload.get('version') != VERSION or 'start' in payload.get('query', {}) or
            payload.get('flat_input_sha256') != digest({k: v for k, v in payload.items()
                                                       if k != 'flat_input_sha256'})):
        raise ValueError('v10 public flat input integrity or query display boundary mismatch')
    internal = copy.deepcopy(payload)
    internal['version'] = FLAT.VERSION
    internal['flat_input_sha256'] = digest({k: v for k, v in internal.items() if k != 'flat_input_sha256'})
    FLAT._validate_input(internal)
    return internal


def answer_schema(payload):
    schema = FLAT.answer_schema(_internal_flat_payload(payload))
    props = schema['properties']
    props['flat_input_sha256'] = {'const': payload['flat_input_sha256']}
    first_hop = payload['query_plan'][0]['hop_id']
    start = payload['query']['start_surface']
    ordered_hops = []
    for index, hop in enumerate(payload['query_plan']):
        frontier = copy.deepcopy(props['hop_frontiers']['items'])
        frontier['properties']['hop_id'] = {'const': hop['hop_id']}
        if index == 0:
            frontier['properties']['frontier'] = {'const': [start]}
        ordered_hops.append(frontier)
    props['hop_frontiers']['prefixItems'] = ordered_hops
    for table in ('child_findings', 'context_reviews', 'edge_groups'):
        props[table]['items']['allOf'] = [{
            'if': {'properties': {'hop_id': {'const': first_hop}}, 'required': ['hop_id']},
            'then': {'properties': {'child': {'const': start}}}}]
    first_subject = {'type': 'object', 'properties': {
        'hop_id': {'const': first_hop}, 'child': {'const': start}}, 'required': ['hop_id', 'child']}
    props['child_findings']['allOf'] = [
        {'contains': first_subject, 'minContains': 1, 'maxContains': 1}]
    context_coverage = []
    for context in payload['contexts']:
        required_context = copy.deepcopy(first_subject)
        required_context['properties']['context_id'] = {'const': context['context_id']}
        required_context['required'].append('context_id')
        context_coverage.append({'contains': required_context, 'minContains': 1, 'maxContains': 1})
    if context_coverage:
        props['context_reviews']['allOf'] = context_coverage
    # These implications check the model's own empty-frontier declaration.
    # They never infer later parents or fill an omitted semantic finding.
    schema['allOf'] = []
    for hop in payload['query_plan']:
        empty_hop = {'type': 'object', 'properties': {
            'hop_id': {'const': hop['hop_id']}, 'frontier': {'const': []}},
            'required': ['hop_id', 'frontier']}
        same_hop = {'type': 'object', 'properties': {'hop_id': {'const': hop['hop_id']}},
                    'required': ['hop_id']}
        schema['allOf'].append({
            'if': {'properties': {'hop_frontiers': {'contains': empty_hop}}, 'required': ['hop_frontiers']},
            'then': {'properties': {table: {'not': {'contains': copy.deepcopy(same_hop)}}
                                   for table in ('child_findings', 'context_reviews', 'edge_groups')}}})
    return schema


def build_answer_contract(package, evidence_review):
    payload = build_answer_payload(package, evidence_review)
    notes = (' 第一hop固定审查询主体=' + json.dumps(payload['query']['start_surface'], ensure_ascii=False)
             + '；原step IDs=' + json.dumps([s['step_id'] for s in payload['submitted_steps']], ensure_ascii=False)
             + '；当前context IDs=' + json.dumps([c['context_id'] for c in payload['contexts']], ensure_ascii=False)
             + '。后续parent只能由当前原文证据确定，schema没有预设任何parent。')
    return {'input': payload, 'output_schema': answer_schema(payload), 'skill': ANSWER_PROMPT + notes}


def materialize_answer_review(review, payload):
    """Expand each selected whole unit, and use every model row exactly once.

    The caller-supplied payload is self-consistency checked; trusted source
    authentication additionally occurs in merge by regenerating it from the
    sealed package. No row, parent, finding or check is inferred or discarded.
    """
    jsonschema.validate(review, answer_schema(payload))
    units = {u['unit_id']: u for u in payload['unit_catalog']}
    aliases = payload['identity_aliases']
    canonical = lambda surface: CORE._canonical(surface, aliases)
    key = lambda row: (row['hop_id'], canonical(row['child']))
    plan_ids = [h['hop_id'] for h in payload['query_plan']]
    if [h['hop_id'] for h in review['hop_frontiers']] != plan_ids:
        raise ValueError('Flat hop frontiers must retain every query hop in order')
    children = {}
    for row in review['child_findings']:
        row_key = key(row)
        if row_key in children:
            raise ValueError('Duplicate flat child finding')
        children[row_key] = row
    context_rows, grouped = {}, {}
    for row in review['context_reviews']:
        row_key = key(row)
        if row_key not in children:
            raise ValueError('Orphan flat context review')
        context_key = (*row_key, row['context_id'])
        if context_key in context_rows:
            raise ValueError('Duplicate flat child/context review')
        if any(units[uid]['context_id'] != row['context_id'] for uid in row['considered_unit_ids']):
            raise ValueError('Considered unit belongs to another context')
        context_rows[context_key] = row
    footprints = set()
    for row in review['edge_groups']:
        row_key = key(row)
        if row_key not in children:
            raise ValueError('Orphan flat edge group')
        if any(row[k + '_unit_id'] not in row['group_unit_ids'] for k in CORE.ANCHOR_KEYS):
            raise ValueError('Flat edge anchor must be selected inside its own support group')
        parent = canonical(row['parent'])
        footprint = (*row_key, parent, row['parent_role'], tuple(sorted(row['group_unit_ids'])))
        if footprint in footprints:
            raise ValueError('Duplicate flat support footprint')
        footprints.add(footprint)
        grouped.setdefault(row_key, {}).setdefault(parent, []).append(row)
    citation = lambda uid: {k: units[uid][k] for k in ('context_id', 'quote')}
    hops, used_children, used_contexts, used_groups = [], set(), set(), 0
    for hop in review['hop_frontiers']:
        canonical_frontier = [canonical(n) for n in hop['frontier']]
        CORE._coverage(canonical_frontier, set(canonical_frontier), 'Unique flat frontier')
        expected = {(hop['hop_id'], child) for child in canonical_frontier}
        actual = {k for k in children if k[0] == hop['hop_id']}
        if actual != expected:
            raise ValueError('Every flat frontier child requires exactly one finding; no orphan children')
        child_reviews = []
        for row_key in (key({'hop_id': hop['hop_id'], 'child': child}) for child in hop['frontier']):
            child = children[row_key]
            used_children.add(row_key)
            contexts = []
            expected_contexts = {(row_key[0], row_key[1], c['context_id']) for c in payload['contexts']}
            actual_contexts = {k for k in context_rows if k[:2] == row_key}
            if actual_contexts != expected_contexts:
                raise ValueError('Every flat child must review every current context exactly once')
            for context in payload['contexts']:
                ck = (*row_key, context['context_id']); cr = context_rows[ck]
                used_contexts.add(ck)
                contexts.append({'context_id': cr['context_id'], 'finding': cr['finding'],
                    'considered_quotes': [units[u]['quote'] for u in cr['considered_unit_ids']],
                    'missing_requirements': copy.deepcopy(cr['missing_requirements']), 'reason': cr['reason']})
            edges = []
            for parent_rows in grouped.get(row_key, {}).values():
                roles = {r['parent_role'] for r in parent_rows}
                if len(roles) != 1:
                    raise ValueError('One canonical parent edge cannot have conflicting declared roles')
                support_groups = []
                for row in parent_rows:
                    used_groups += 1
                    support_groups.append({'citations': [citation(u) for u in row['group_unit_ids']],
                        'anchors': {k: citation(row[k + '_unit_id']) for k in CORE.ANCHOR_KEYS},
                        'checks': {k: row['check_' + k] for k in CORE.CHECK_KEYS}, 'reason': row['reason']})
                # Edge reason is mechanical provenance, not a new semantic judgment.
                edges.append({'parent': parent_rows[0]['parent'], 'parent_role': parent_rows[0]['parent_role'],
                    'support_groups': support_groups,
                    'reason': 'Program grouping of flat rows for one canonical parent; group reasons preserved separately.'})
            child_reviews.append({'child': child['child'], 'finding': child['finding'],
                'context_reviews': contexts, 'edges': edges, 'reason': child['reason']})
        hops.append({'hop_id': hop['hop_id'], 'frontier': copy.deepcopy(hop['frontier']),
                     'child_reviews': child_reviews})
    if (used_children != set(children) or used_contexts != set(context_rows)
            or used_groups != len(review['edge_groups'])):
        raise ValueError('Every original flat row must be materialized exactly once')
    native = {'input_sha256': payload['native_input_sha256'],
              'evidence_review_sha256': payload['evidence_review_sha256'],
              'context_checks': copy.deepcopy(review['context_checks']), 'hop_reviews': hops,
              'issues': copy.deepcopy(review.get('issues', [])), 'reason': review['reason']}
    validation_payload = {**payload, 'input_sha256': payload['native_input_sha256']}
    POLICY.validate_answer_review(native, validation_payload)
    return native


def validate_answer_review(review, answer_payload):
    materialize_answer_review(review, answer_payload)
    return True


def merge_scoring_results(package, evidence_review, answer_review):
    # Do not call FLAT.merge: it regenerates the older public input, whose
    # hash intentionally differs because that query still contains start ID.
    payload = build_answer_payload(package, evidence_review)
    native = materialize_answer_review(answer_review, payload)
    result = POLICY.merge_scoring_results(package, evidence_review, native)
    result.update(scorer_version=VERSION, semantic_core_version=POLICY.VERSION,
        semantic_policy_version=POLICY.SEMANTIC_POLICY_VERSION,
        answer_review_sha256=digest(answer_review),
        flat_input_sha256=payload['flat_input_sha256'], native_answer_review_sha256=digest(native),
        model_authored_answer_representation='flat_unit_selectors_and_explicit_findings',
        native_answer_representation='program_materialized_whole_source_units_and_row_grouping',
        flat_rows_materialized={key: len(answer_review[key]) for key in (
            'hop_frontiers', 'child_findings', 'context_reviews', 'edge_groups', 'context_checks')},
        optional_issues_defaulted='issues' not in answer_review,
        public_query_backend_start_omitted=True,
        protocol_binding_translation='v10_public_flat_binding_to_native_binding_mechanical_only',
        protocol_adapter_repairs_semantic_content=False)
    return result
