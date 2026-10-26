"""Build deletion families from frozen modern-text packets without editing sources.

See contracts.py for the packet interface. Exact substring survival is a registered
support check, never a natural-language completeness proof. v0.1 is loaded under
private module aliases so its bare module names do not collide with v0.2.
"""
import copy
import hashlib
import importlib.util
from pathlib import Path

import jsonschema

try:
    from .contracts import VERSION, MANDATORY, OPTIONAL, PACKET_SCHEMA, FAMILY_SCHEMA
except ImportError:
    from contracts import VERSION, MANDATORY, OPTIONAL, PACKET_SCHEMA, FAMILY_SCHEMA


def _legacy(name):
    path = Path(__file__).resolve().parents[1] / 'multi_agent_v0' / (name + '.py')
    spec = importlib.util.spec_from_file_location('_bridgeqa_v01_' + name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


_CORE = _legacy('core')
_V01_CONTRACTS = _legacy('contracts')


def graph_core():
    return _CORE


def solve_scoped(query, facts):
    """Compose only explicitly declared per-operation source scopes.

    Legacy queries retain exactly the v0.1 single-scope behavior. A compound
    query never changes a fact's source scope or makes arbitrary scope mixing
    available to the solver.
    """
    if 'scope_by_step' not in query:
        return _CORE.solve(query, facts)
    scopes = query['scope_by_step']
    jsonschema.validate(scopes, {'type': 'array', 'items': {'type': 'string', 'minLength': 1},
                                 'minItems': 2, 'maxItems': 2})
    if len(scopes) != len(query['steps']):
        raise ValueError('Each query operation requires exactly one explicit source scope')
    paths = [{'entities': [query['start']], 'facts': []}]
    for index, role in enumerate(query['steps']):
        paths = [
            {'entities': p['entities'] + [f['parent']], 'facts': p['facts'] + [f['id']]}
            for p in paths for f in facts
            if f['child'] == p['entities'][-1] and f['scope'] == scopes[index]
            and (role == 'parent' or f['parent_role'] == role)
            and f['parent'] not in p['entities'] and f['id'] not in p['facts']
        ]
    answers = sorted({p['entities'][-1] for p in paths})
    return {'status': 'insufficient_evidence' if not answers else ('answerable' if len(answers) == 1 else 'ambiguous'),
            'answer_ids': answers, 'proofs': paths, 'proof_depth': len(query['steps']) if paths else None,
            'world_semantics': 'positive_evidence_only_within_frozen_extracted_graph_explicit_step_scopes'}


def _sha(text):
    return hashlib.sha256(text.encode('utf-8')).hexdigest()


def _positions(materials, names):
    result = []
    for unit in materials:
        for surface in dict.fromkeys(names):
            start = 0
            while surface and (found := unit['text'].find(surface, start)) >= 0:
                result.append({'unit_id': unit['unit_id'], 'surface': surface,
                               'start': found, 'end_exclusive': found + len(surface)})
                start = found + 1
    return result


def _support_counts(origin, materials):
    texts = {u['unit_id']: u['text'] for u in materials}
    return {f['id']: sum(all(q['unit_id'] in texts and q['quote'] in texts[q['unit_id']]
                             for q in group) for group in f['evidence_sets'])
            for f in origin['facts']}


def _same_answer(base, row):
    return row['status'] == base['status'] and row['answer_ids'] == base['answer_ids']


def _residual(packet, condition):
    value = packet.get('semantic_residual', False)
    return value if isinstance(value, bool) else value.get(condition, False)


def remove_quotes_v2(base, deletions):
    """Apply literal original-coordinate cuts, allowing complete source-unit removal.

    A removed unit is omitted from the context rather than represented by an
    empty placeholder. The operation still cannot remove the entire passage
    collection. Partial cuts retain exactly the surviving text and hashes.
    """
    result = copy.deepcopy(base)
    units = {u['unit_id']: u for u in result}
    per_unit = {}
    for deletion in deletions:
        uid = deletion['unit_id']
        if uid not in units:
            raise ValueError('Deletion targets a non-base unit')
        body, quote = units[uid]['text'], deletion['quote']
        if not quote or body.count(quote) != 1:
            raise ValueError('Deletion quote must occur exactly once')
        start = body.index(quote)
        per_unit.setdefault(uid, []).append((start, start + len(quote)))
    logs, removed = [], set()
    for uid, intervals in per_unit.items():
        merged = []
        for start, end in sorted(intervals):
            if merged and start <= merged[-1][1]:
                merged[-1] = merged[-1][0], max(end, merged[-1][1])
            else:
                merged.append((start, end))
        before = units[uid]['text']
        after = before
        for start, end in reversed(merged):
            after = after[:start] + after[end:]
        unit_removed = after == ''
        if not after.strip() and not unit_removed:
            raise ValueError('Cannot export a whitespace-only passage; delete its full original unit instead')
        for start, end in reversed(merged):
            logs.append({'unit_id': uid, 'start': start, 'end_exclusive': end,
                         'removed_text': before[start:end], 'unit_removed': unit_removed,
                         'source_modern_sha256': units[uid].get('modern_sha256', _sha(before))})
        if unit_removed:
            removed.add(uid)
        else:
            units[uid]['text'] = after
            units[uid]['source_modern_sha256'] = units[uid].get('modern_sha256', _sha(before))
            units[uid]['modern_sha256'] = _sha(after)
    result = [u for u in result if u['unit_id'] not in removed]
    if not result:
        raise ValueError('Cannot remove all base units (empty passage collection)')
    return result, logs


def build_family(packet):
    """Return a graph-checked draft; independent text/reference audit is still required.

    Deletions only remove exact source substrings. semantic_residual flags preserve
    graph results separately but make semantic gold unresolved, never insufficient.
    """
    jsonschema.validate(packet, PACKET_SCHEMA)
    origin = packet['origin']
    jsonschema.validate(origin, _V01_CONTRACTS.SCHEMAS['origin'])
    legacy_query = copy.deepcopy(packet['query'])
    scopes = legacy_query.pop('scope_by_step', None)
    jsonschema.validate(legacy_query, _V01_CONTRACTS.QUERY)
    if 'scope_by_step' in packet['query']:
        jsonschema.validate(scopes, {'type': 'array', 'items': {'type': 'string', 'minLength': 1},
                                     'minItems': 2, 'maxItems': 2})
    materials = copy.deepcopy(packet['materials'])
    _CORE.unique(materials, 'unit_id')
    units = {u['unit_id']: u for u in materials}
    for unit in materials:
        calculated = _sha(unit['text'])
        if unit.get('modern_sha256', calculated) != calculated:
            raise ValueError('Frozen modern text hash mismatch: ' + unit['unit_id'])
        unit['modern_sha256'] = calculated
    _CORE.validate_origin(origin, materials)
    entities = {e['id']: e for e in origin['entities']}
    start = packet['query']['start']
    if start not in entities:
        raise ValueError('Unknown query start')
    if any(uid not in units for uid in packet['base_unit_ids']):
        raise ValueError('Unknown base material')
    base = [copy.deepcopy(units[uid]) for uid in packet['base_unit_ids']]
    start_name = entities[start]['name']
    start_aliases = [start_name] + entities[start]['aliases']
    if not _positions(base, [start_name]):
        raise ValueError('Base must contain the canonical query-start name')
    contexts = {'base': base}
    logs = {'base': []}
    addition_ids = packet['additions']
    if set(addition_ids['main_distractor']) & set(addition_ids['irrelevant_addition']):
        raise ValueError('Main distractor and irrelevant addition must be distinct')
    for condition in MANDATORY[1:3]:
        ids = addition_ids[condition]
        if any(uid not in units or uid in packet['base_unit_ids'] for uid in ids):
            raise ValueError('Additions must be acquired non-base materials')
        contexts[condition] = copy.deepcopy(base) + [copy.deepcopy(units[uid]) for uid in ids]
        logs[condition] = []
    applicability = {}
    for condition in OPTIONAL:
        present = condition in packet['deletions']
        reason = packet['optional_not_applicable'].get(condition)
        if present and reason:
            raise ValueError('Optional condition both applicable and not applicable: ' + condition)
        if not present and not reason:
            raise ValueError('Missing explicit optional applicability reason: ' + condition)
        applicability[condition] = {'applicable': present, 'reason': 'provided_source_deletion' if present else reason}
    for condition, deletions in packet['deletions'].items():
        contexts[condition], logs[condition] = remove_quotes_v2(base, deletions)
    rows = []
    for condition in MANDATORY + OPTIONAL:
        if condition not in contexts:
            continue
        context = contexts[condition]
        facts = _CORE.active_facts(origin, context)
        graph_gold = solve_scoped(packet['query'], facts)
        semantic_gold = copy.deepcopy(graph_gold)
        if _residual(packet, condition):
            semantic_gold = {'status': 'unresolved', 'answer_ids': [], 'proofs': [], 'proof_depth': None,
                             'world_semantics': 'registered_quote_changed_semantic_support_requires_independent_review'}
        rows.append({'condition': condition, 'materials': context, 'gold': semantic_gold,
                     'registered_graph_gold': graph_gold, 'active_fact_ids': [f['id'] for f in facts],
                     'deletion_log': logs[condition], 'name_positions': _positions(context, start_aliases),
                     'requires_text_review': True, 'support_counts': _support_counts(origin, context),
                     'evidence_completeness': 'registered_graph_only'})
    by_condition = {r['condition']: r for r in rows}
    baseline = by_condition['base']['registered_graph_gold']
    if baseline['status'] != 'answerable' or baseline['proof_depth'] != 2:
        raise ValueError('Base must have a unique answer and a two-step proof')
    for condition in ('main_distractor', 'irrelevant_addition', 'irrelevant_deleted'):
        gold = by_condition[condition]['registered_graph_gold']
        if not _same_answer(baseline, gold) or not all(p in gold['proofs'] for p in baseline['proofs']):
            raise ValueError('Answer/proof-preserving condition changed the base: ' + condition)
    cut = by_condition['necessary_support_deleted_name_retained']
    if not any(p['surface'] == start_name for p in cut['name_positions']):
        raise ValueError('Necessary deletion must retain the canonical query-start name')
    if not _residual(packet, cut['condition']) and cut['registered_graph_gold']['status'] != 'insufficient_evidence':
        raise ValueError('Necessary deletion leaves a registered proof')
    if 'name_absent_deleted' in by_condition:
        row = by_condition['name_absent_deleted']
        if row['name_positions']:
            raise ValueError('Name-absent deletion retains a start name or alias')
        if not _residual(packet, row['condition']) and row['registered_graph_gold']['status'] != 'insufficient_evidence':
            raise ValueError('Name-absent deletion leaves a registered proof')
    if 'redundant_support_deleted' in by_condition:
        row = by_condition['redundant_support_deleted']
        if not _same_answer(baseline, row['registered_graph_gold']):
            raise ValueError('Repeated-support deletion changed the answer')
        proof_facts = {f for p in baseline['proofs'] for f in p['facts']}
        before, after = by_condition['base']['support_counts'], row['support_counts']
        if not any(before[f] > after[f] > 0 for f in proof_facts):
            raise ValueError('Repeated-support condition must remove one support but retain another for a proof fact')
    if 'alternative_proof_preserved' in by_condition:
        row = by_condition['alternative_proof_preserved']
        gold = row['registered_graph_gold']
        if not _same_answer(baseline, gold) or not any(p not in gold['proofs'] for p in baseline['proofs']):
            raise ValueError('Alternative-proof condition must remove a proof while preserving the answer')
    unresolved = any(r['gold']['status'] == 'unresolved' for r in rows)
    result = {'schema_version': VERSION, 'family_version': 'family-v0.2',
              'family_id': packet['family_id'], 'candidate_id': packet['family_id'],
              'track': packet['track'], 'question': packet['question'], 'query': copy.deepcopy(packet['query']),
              'origin': copy.deepcopy(origin), 'variants': rows, 'optional_applicability': applicability,
              'provenance': {'packet_sha256': _CORE.digest(packet),
                             'material_hashes': {u['unit_id']: u['modern_sha256'] for u in materials},
                             'source_metadata': copy.deepcopy(packet.get('provenance', {})),
                             'transform': 'literal_source_substring_deletion_only'},
              'validation_status': 'pending_semantic_review' if unresolved else 'graph_checked_pending_text_audit',
              'eligible_for_locked_experiment': False,
              'reference_review': 'pending_independent_gpt', 'human_review': 'not_run', 'formal_release': False}
    jsonschema.validate(result, FAMILY_SCHEMA)
    return result


def validate_family(family, packet):
    """Rebuild exactly, preventing unlogged text/gold/condition edits after construction."""
    expected = build_family(packet)
    if family != expected:
        raise ValueError('Family differs from its frozen packet reconstruction')
    return {'reconstruction': 'pass', 'packet_sha256': expected['provenance']['packet_sha256'],
            'registered_graph_only': True, 'requires_independent_text_audit': True}
