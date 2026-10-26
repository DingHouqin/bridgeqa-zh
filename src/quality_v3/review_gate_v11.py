"""Publish a narrow checked decision, or explicitly require independent review.

No case-name rules, private references, model confidence or risk keywords clear
natural-language evidence. Original model deliveries stay unchanged. Review
receipts are accepted only through a separately trusted operator registry.
See [contract](../../QA_Generator/specs/review-routing-v0.11.md).
"""
from __future__ import annotations

import copy
import hashlib
import json
import re

import inventory_occurrences_v10 as INVENTORY
import scoring_review_v10 as SCORING

VERSION = 'quality-v0.11-independent-review-gate'
CORE_SCOPE = 'structured_core_only_no_raw_auxiliary_checks_or_free_reasons'
REVIEW_LABEL = '需【人工/强智能体复核】'
SCORING_FACETS = ('proof_verdict', 'source_status_answers_paths',
                  'independent_submitted_step_support', 'actual_occurrence_scope')
INVENTORY_FACETS = ('all_source_support_occurrences', 'same_occurrence_deduplication',
                    'group_local_subject_role_scope', 'complete_proof_paths')
BASE_KEYS = {'version', 'task', 'question', 'query', 'query_plan', 'contexts',
             'candidate_final', 'submitted_steps', 'identity_aliases', 'relation_definition'}


def digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
        separators=(',', ':'), allow_nan=False).encode('utf-8')).hexdigest()


def _load(raw):
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError('Duplicate JSON member')
            result[key] = value
        return result
    def invalid_constant(value):
        raise ValueError('Non-finite JSON value: ' + value)
    return json.loads(raw.decode('utf-8-sig'), object_pairs_hook=unique,
                      parse_constant=invalid_constant)


def _source(contract):
    if contract['job']['kind'] == 'scoring':
        # No package.private_checks, source gold, or reference disagreement.
        base = contract['package']['answer_input_base']
        return {key: copy.deepcopy(base[key]) for key in BASE_KEYS}
    if contract['job']['kind'] == 'inventory':
        return copy.deepcopy(contract['canonical_request'])
    raise ValueError('Unsupported task kind')


def _coverage(contract, source):
    result = ['context:' + c['context_id'] for c in source['contexts']]
    if contract['job']['kind'] == 'scoring':
        result += ['unit:' + u['unit_id'] for u in SCORING.FLAT._source_units(source['contexts'])]
        result += ['step:' + s['step_id'] for s in source['submitted_steps']]
        result += ['citation:' + s['step_id'] + ':' + c['citation_id']
                   for s in source['submitted_steps'] for c in s['submitted_citations']]
        result += ['hop:' + h['hop_id'] for h in source['query_plan']]
    else:
        windows = INVENTORY.build_occurrence_requests(source)
        if contract['window_requests'] != windows:
            raise ValueError('Inventory windows differ from canonical full-source regeneration')
        for envelope in windows:
            window = envelope['input']
            result += ['cell:' + window['fact']['fact_id'] + ':' + uid
                       for uid in window['anchor_unit_ids']]
    if len(result) != len(set(result)):
        raise ValueError('Duplicate source review targets')
    return sorted(result)


def core_projection(contract, draft):
    """Select only declared fields; do not publish model reasons or raw checks."""
    if draft['status'] != 'completed':
        raise ValueError('An uncompleted draft has no confirmed core projection')
    if contract['job']['kind'] == 'scoring':
        merged = draft['merged']
        member = merged['member_findings']
        if (merged['verdict'] not in ('supported', 'incorrect')
                or type(member['uncertainty_encountered']) is not bool
                or member['uncertainty_encountered'] is not False):
            raise ValueError('Undetermined core')
        if member['status'] not in ('answerable', 'insufficient_evidence'):
            raise ValueError('Undetermined or invalid member status')
        def string_list(value):
            return isinstance(value, list) and all(isinstance(s, str) and bool(s.strip()) for s in value)
        if (not string_list(member['answers']) or not isinstance(member['paths'], list)
                or any(not string_list(path) or not path for path in member['paths'])
                or member['status'] == 'insufficient_evidence' and (member['answers'] or member['paths'])
                or member['status'] == 'answerable' and (not member['answers'] or not member['paths'])):
            raise ValueError('Invalid status/answer/path structure')
        steps = [{'step_id': s['step_id'], 'support': s['effective_support']}
                 for s in merged['step_results']]
        if (any(s['support'] not in ('supported', 'unsupported') for s in steps)
                or [s['step_id'] for s in steps] != [s['step_id'] for s in
                    contract['package']['answer_input_base']['submitted_steps']]):
            raise ValueError('Undetermined submitted step')
        return {'kind': 'scoring', 'proof_verdict': merged['verdict'],
                'source_status': member['status'], 'answers': copy.deepcopy(member['answers']),
                'paths': copy.deepcopy(member['paths']), 'steps': steps}
    inventory = draft['assembly']['inventory']
    source = contract['canonical_request']
    texts = {c['context_id']: c['text'] for c in source['contexts']}
    requested = {f['fact_id'] for f in source['requested_edges']}
    facts = []
    for fact in inventory['facts']:
        if fact['fact_id'] not in requested or fact['status'] not in ('support_proposed', 'not_found'):
            raise ValueError('Unknown or unconfirmed inventory fact')
        if not isinstance(fact['support_groups'], list):
            raise ValueError('Invalid support-group list')
        if fact['status'] == 'not_found' and fact['support_groups'] != []:
            raise ValueError('No-support finding has a contradictory positive group')
        groups = []
        for group in fact['support_groups']:
            if not isinstance(group, list) or not group:
                raise ValueError('Empty or invalid support group')
            citations = []
            for citation in group:
                item = {key: copy.deepcopy(citation[key]) for key in ('context_id', 'start', 'end', 'quote')}
                if (item['context_id'] not in texts or type(item['start']) is not int
                        or type(item['end']) is not int or item['start'] < 0
                        or item['end'] <= item['start'] or item['end'] > len(texts[item['context_id']])
                        or not isinstance(item['quote'], str)
                        or texts[item['context_id']][item['start']:item['end']] != item['quote']):
                    raise ValueError('Inventory citation does not locate the exact source')
                citations.append(item)
            groups.append(citations)
        if fact['status'] == 'support_proposed' and not groups:
            raise ValueError('No confirmed support groups')
        facts.append({'fact_id': fact['fact_id'], 'status': fact['status'], 'support_groups': groups})
    if len(facts) != len(requested) or {f['fact_id'] for f in facts} != requested:
        raise ValueError('Every requested fact must be present exactly once')
    paths = []
    positive_ids = {f['fact_id'] for f in facts if f['status'] == 'support_proposed'}
    for path in inventory['proof_paths']:
        item = {key: copy.deepcopy(path[key]) for key in ('fact_ids', 'entity_ids')}
        if (not isinstance(item['fact_ids'], list) or not item['fact_ids']
                or any(fid not in positive_ids for fid in item['fact_ids'])
                or not isinstance(item['entity_ids'], list)
                or len(item['entity_ids']) != len(item['fact_ids']) + 1
                or any(not isinstance(e, str) or not e.strip() for e in item['entity_ids'])):
            raise ValueError('Invalid inventory proof path')
        paths.append(item)
    return {'kind': 'inventory', 'facts': facts, 'proof_paths': paths}


def review_request(contract, draft_bytes, *, closed_world=False):
    """closed_world is a trusted caller policy, never inferred from prose."""
    draft = _load(draft_bytes)
    if draft['job'] != contract['job'] or draft['split'] != contract['split']:
        raise ValueError('Draft belongs to another task/split')
    source = _source(contract)
    expected_coverage = _coverage(contract, source)
    facets = SCORING_FACETS if contract['job']['kind'] == 'scoring' else INVENTORY_FACETS
    untrusted = {key: copy.deepcopy(draft[key]) for key in (
        'single_step_reviews', 'evidence_review', 'answer_review', 'window_results',
        'group_reviews', 'group_validation', 'failed_stage_response', 'message') if key in draft}
    if contract['job']['kind'] == 'inventory' and 'assembly' in draft:
        untrusted['proposed_inventory'] = copy.deepcopy(draft['assembly']['inventory'])
    try:
        proposed_core = core_projection(contract, draft)
    except (KeyError, TypeError, ValueError):
        proposed_core = None
    task = {'version': VERSION, 'scope': CORE_SCOPE, 'kind': contract['job']['kind'],
        'source': source, 'source_sha256': digest(source),
        'contract_sha256': digest(contract),
        'draft_bytes_sha256': hashlib.sha256(draft_bytes).hexdigest(),
        'original_delivery_status': draft['status'], 'closed_world': closed_world is True,
        'required_coverage': expected_coverage, 'required_facets': list(facets),
        'untrusted_draft_for_comparison': untrusted, 'proposed_core_for_comparison': proposed_core,
        'draft_author_identity': 'original_deepseek_flash_delivery',
        'review_instructions': 'Read and judge the whole source before comparing the untrusted draft. '
            'Review all actual source material independently. Preserve raw output; '
            'do not use model pass or confidence as truth. Confirm only the declared structured core, '
            'or leave review pending. Raw auxiliary fields and free reasons are outside this certificate.'}
    task['request_sha256'] = digest(task)
    return task


def _empty_source_core(contract, draft, request):
    """A closed parent-chain with literally no material proves only insufficiency."""
    if request['kind'] != 'scoring' or not request['closed_world'] or draft['status'] != 'completed':
        return None
    source = request['source']
    base = contract['package']['answer_input_base']
    query = source['query']
    if (set(base) != BASE_KEYS or source['contexts'] != [] or source['submitted_steps'] != []
            or source['candidate_final'] != {'status': 'insufficient_evidence', 'answers': []}
            or query.get('operation') != 'parent_chain'
            or not isinstance(query.get('start'), str) or not query['start'].strip()
            or not isinstance(query.get('start_surface'), str) or not query['start_surface'].strip()
            or not isinstance(query.get('steps'), list) or not query['steps']
            or any(role not in ('parent', 'mother', 'father') for role in query['steps'])):
        return None
    if source['query_plan'] != [
            {'hop_id': 'hop-' + str(i), 'requested_role': role,
             'scope': query.get('scope_by_step', [query.get('scope')] * len(query['steps']))[i]}
            for i, role in enumerate(query['steps'])]:
        return None
    if any(e.get('steps') for e in contract.get('evidence_inputs', [])):
        return None
    if draft.get('evidence_review', {}).get('steps') != []:
        return None
    # "completed" alone is not trusted. Re-run the actual frozen semantic and
    # wire validator, without using its private-reference diagnostics as truth.
    rebuilt = SCORING.merge_scoring_results(contract['package'], draft['evidence_review'],
                                            draft['answer_review'])
    public_fields = ('scorer_version', 'semantic_policy_version', 'verdict', 'raw_model_verdict',
        'status_correct', 'answer_correct', 'proof_support', 'member_findings', 'step_results',
        'evidence_input_sha256', 'evidence_review_sha256', 'answer_input_sha256',
        'answer_review_sha256', 'flat_input_sha256', 'native_answer_review_sha256')
    if any(draft['merged'].get(key) != rebuilt[key] for key in public_fields):
        return None
    expected = {'kind': 'scoring', 'proof_verdict': 'supported',
        'source_status': 'insufficient_evidence', 'answers': [], 'paths': [], 'steps': []}
    try:
        return expected if core_projection(contract, draft) == expected else None
    except (KeyError, TypeError, ValueError):
        return None


def _approved_core(receipt, registry, request, contract, draft):
    """The registry is a caller-owned trust boundary, not model-supplied data."""
    approved = registry.get(digest(receipt)) if isinstance(registry, dict) else None
    if not isinstance(approved, dict):
        raise ValueError('No trusted operator attestation for this exact receipt')
    if not isinstance(receipt.get('source_artifact_sha256'), str) or not re.fullmatch(
            r'[0-9a-f]{64}', receipt['source_artifact_sha256']):
        raise ValueError('A full SHA256 of an actual reviewed source artifact is required')
    for key in ('source_artifact_sha256', 'reviewer_identity'):
        if approved.get(key) != receipt.get(key):
            raise ValueError('Receipt authority mismatch')
    if (receipt.get('version') != VERSION or receipt.get('scope') != CORE_SCOPE
            or receipt.get('request_sha256') != request['request_sha256']
            or receipt.get('source_sha256') != request['source_sha256']
            or receipt.get('draft_bytes_sha256') != request['draft_bytes_sha256']
            or receipt.get('decision') != 'confirmed'
            or receipt.get('unresolved_facets') != []
            or receipt.get('reviewer_kind') not in ('independent_strong_agent', 'human')
            or not isinstance(receipt.get('reviewer_identity'), str)
            or not receipt['reviewer_identity'].strip()
            or receipt['reviewer_identity'] == request['draft_author_identity']
            or approved.get('actual_independent_source_review_verified') is not True
            or receipt.get('reviewed_coverage') != request['required_coverage']
            or receipt.get('confirmed_facets') != request['required_facets']):
        raise ValueError('Review scope, independence, source, coverage or unresolved fields mismatch')
    core = core_projection(contract, draft)
    if receipt.get('confirmed_core') != core:
        raise ValueError('A correction requires a separately versioned revised delivery, not relabeling')
    return core


def route(contract, draft_bytes, *, closed_world=False, receipt=None, trusted_registry=None):
    """Pending is a delivered routing outcome, never a semantic fix or score."""
    result = {'version': VERSION, 'status': 'requires_review', 'label': REVIEW_LABEL,
        'scope': CORE_SCOPE, 'conclusion': None, 'can_use_as_determinate_core': False,
        'original_draft_certified': False, 'formal_release': False,
        'original_delivery_status': None, 'reasons': [], 'review_request': None,
        'receipt_sha256': None}
    try:
        request = review_request(contract, draft_bytes, closed_world=closed_world)
        draft = _load(draft_bytes)
        result['original_delivery_status'] = draft['status']
        result['review_request'] = request
        empty = _empty_source_core(contract, draft, request)
        if empty is not None:
            result.update(status='automatically_determined_core', label='无材料：仅确认缺证拒答',
                          conclusion=empty, can_use_as_determinate_core=True)
            return result
        if receipt is not None:
            core = _approved_core(receipt, trusted_registry, request, contract, draft)
            result.update(status='independently_reviewed_core', label='核心结论已独立复核',
                conclusion=core, can_use_as_determinate_core=True, receipt_sha256=digest(receipt))
            return result
        if draft['status'] != 'completed':
            result['reasons'].append('original_delivery_not_completed')
        elif request['kind'] == 'inventory':
            result['reasons'].append('full_source_coverage_and_group_semantics_require_independent_review')
        else:
            result['reasons'].append('natural_language_semantics_require_independent_review')
    except (KeyError, TypeError, ValueError, UnicodeError, IndexError, AttributeError,
            SCORING.jsonschema.ValidationError) as error:
        result['reasons'].append('invalid_or_unconfirmed_review_contract:' + str(error))
    return result
