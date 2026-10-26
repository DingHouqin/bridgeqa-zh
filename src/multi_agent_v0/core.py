"""Deterministic evidence, parent-path, family and projection contracts.

Natural language entailment remains a separate review; see README.md.
"""
import copy
import hashlib
import json


def digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode('utf-8')).hexdigest()


def unique(rows, field):
    ids = [r[field] for r in rows]
    if len(ids) != len(set(ids)):
        raise ValueError('Duplicate ' + field)


def validate_origin(origin, materials):
    unique(origin['entities'], 'id')
    unique(origin['facts'], 'id')
    entities = {e['id'] for e in origin['entities']}
    entity_rows = {e['id']: e for e in origin['entities']}
    units = {u['unit_id']: u['text'] for u in materials}
    defects = []
    for f in origin['facts']:
        if f['parent'] not in entities or f['child'] not in entities or f['parent'] == f['child']:
            defects.append(f['id'] + ': invalid parent endpoints')
        for bundle in f['evidence_sets']:
            combined = ''.join(q['quote'] for q in bundle)
            for endpoint in ('parent', 'child'):
                if f[endpoint] in entity_rows:
                    entity = entity_rows[f[endpoint]]
                    if not any(alias in combined for alias in [entity['name']] + entity['aliases']):
                        defects.append(f['id'] + ': one evidence bundle omits the named ' + endpoint + ' endpoint; include its antecedent quote')
            for q in bundle:
                if q['unit_id'] not in units or q['quote'] not in units[q['unit_id']]:
                    defects.append(f['id'] + ': quote is not an exact substring: ' + q['quote'])
    if defects:
        raise ValueError('All located evidence defects: ' + json.dumps(defects, ensure_ascii=False))
    # Identical surface names are allowed; they are not merged automatically.
    return {'entities': len(entities), 'facts': len(origin['facts']), 'quotes_located': True}


def query_options(origin, materials):
    facts = active_facts(origin, materials)
    options = []
    for first in facts:
        for second in facts:
            if first['parent'] != second['child'] or first['scope'] != second['scope']:
                continue
            query = {'operation': 'parent_chain', 'start': first['child'],
                     'steps': [first['parent_role'], second['parent_role']], 'scope': first['scope']}
            result = solve(query, facts)
            if result['status'] == 'answerable' and [first['id'], second['id']] in [p['facts'] for p in result['proofs']]:
                option = {'query': query, 'answer_ids': result['answer_ids'], 'proof_fact_ids': [first['id'], second['id']]}
                if option not in options:
                    options.append(option)
    return options


def validate_origin_for_composition(origin, materials):
    result = validate_origin(origin, materials)
    result['query_options'] = query_options(origin, materials)
    if not result['query_options']:
        raise ValueError('Extracted subset has no complete two-step parent path. Select connected supported facts (prioritize the continuous Ning-household narrative), or reject if source truly lacks them; do not invent husband-to-child edges.')
    return result


def active_facts(origin, materials):
    units = {u['unit_id']: u['text'] for u in materials}
    return [f for f in origin['facts'] if any(all(q['unit_id'] in units and q['quote'] in units[q['unit_id']] for q in bundle) for bundle in f['evidence_sets'])]


def solve(query, facts):
    # Each step is a child -> parent lookup; no generic transitivity or closed-world negation.
    paths = [{'entities': [query['start']], 'facts': []}]
    for role in query['steps']:
        paths = [
            {'entities': p['entities'] + [f['parent']], 'facts': p['facts'] + [f['id']]}
            for p in paths for f in facts
            if f['child'] == p['entities'][-1] and f['scope'] == query['scope']
            and (role == 'parent' or f['parent_role'] == role)
            and f['parent'] not in p['entities'] and f['id'] not in p['facts']
        ]
    answers = sorted({p['entities'][-1] for p in paths})
    return {'status': 'insufficient_evidence' if not answers else ('answerable' if len(answers) == 1 else 'ambiguous'),
            'answer_ids': answers, 'proofs': paths, 'proof_depth': len(query['steps']) if paths else None,
            'world_semantics': 'positive_evidence_only_within_frozen_extracted_graph'}


def validate_composer(composer, origin, materials):
    query = composer['query']
    units = {u['unit_id']: u for u in materials}
    if len(composer['base_unit_ids']) != len(set(composer['base_unit_ids'])) or any(i not in units for i in composer['base_unit_ids']):
        raise ValueError('Invalid base units')
    if query['start'] not in {e['id'] for e in origin['entities']}:
        raise ValueError('Unknown query start')
    selected = {'query': query, 'answer_ids': composer['proposed_answer_ids'], 'proof_fact_ids': composer['proof_fact_ids']}
    if selected not in query_options(origin, materials):
        raise ValueError('Select an unchanged validated query option; do not substitute mother/father roles or invent edges')
    base = [units[i] for i in composer['base_unit_ids']]
    result = solve(query, active_facts(origin, base))
    if result['status'] != 'answerable' or sorted(composer['proposed_answer_ids']) != result['answer_ids']:
        raise ValueError('Proposed answer disagrees with graph solve')
    if composer['proof_fact_ids'] not in [p['facts'] for p in result['proofs']]:
        raise ValueError('Proposed proof is not a complete permitted path')
    if len(set(composer['proof_fact_ids'])) != 2:
        raise ValueError('Two distinct dependency operations are required')
    return result


def remove_quotes(base, deletions):
    result = copy.deepcopy(base)
    units = {u['unit_id']: u for u in result}
    logs = []
    # Offsets always refer to the pre-deletion version; merge overlaps then remove right-to-left.
    per_unit = {}
    for d in deletions:
        if d['unit_id'] not in units:
            raise ValueError('Deletion targets a non-base unit')
        body = units[d['unit_id']]['text']
        if body.count(d['quote']) != 1:
            raise ValueError('Deletion quote must occur exactly once')
        start = body.index(d['quote'])
        per_unit.setdefault(d['unit_id'], []).append((start, start + len(d['quote'])))
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
            logs.append({'unit_id': uid, 'start': start, 'end_exclusive': end, 'removed_text': before[start:end]})
        if not after.strip():
            raise ValueError('Cannot export an empty passage')
        units[uid]['text'] = after
        if 'modern_sha256' in units[uid]:
            units[uid]['source_modern_sha256'] = units[uid]['modern_sha256']
            units[uid]['modern_sha256'] = hashlib.sha256(after.encode('utf-8')).hexdigest()
    return result, logs


def build_family(composer, difficult, origin, materials):
    validate_composer(composer, origin, materials)
    units = {u['unit_id']: u for u in materials}
    base_ids = composer['base_unit_ids']
    for key in ('distractor_unit_ids', 'irrelevant_unit_ids'):
        ids = difficult[key]
        if len(ids) != len(set(ids)) or any(i not in units or i in base_ids for i in ids):
            raise ValueError('Additions must be distinct acquired source units outside base')
    if set(difficult['distractor_unit_ids']) & set(difficult['irrelevant_unit_ids']):
        raise ValueError('Main distractor and unrelated addition must be distinct for this pilot')
    if any(i not in {e['id'] for e in origin['entities']} for i in difficult['expected_trap_answer_ids']):
        raise ValueError('Unknown lure entity')
    base = [copy.deepcopy(units[i]) for i in base_ids]
    deleted, deletion_log = remove_quotes(base, difficult['deletions'])
    contexts = {'base': base,
                'main_distractor': base + [copy.deepcopy(units[i]) for i in difficult['distractor_unit_ids']],
                'irrelevant_control': base + [copy.deepcopy(units[i]) for i in difficult['irrelevant_unit_ids']],
                'necessary_support_deleted': deleted}
    rows = []
    for condition, context in contexts.items():
        facts = active_facts(origin, context)
        gold = solve(composer['query'], facts)
        rows.append({'condition': condition, 'materials': context, 'active_fact_ids': [f['id'] for f in facts], 'gold': gold})
    baseline = rows[0]['gold']
    for row in rows[1:3]:
        if row['gold']['status'] != baseline['status'] or row['gold']['answer_ids'] != baseline['answer_ids']:
            raise ValueError('Answer-preserving variant changed the graph answer')
        if not all(p in row['gold']['proofs'] for p in baseline['proofs']):
            raise ValueError('Answer-preserving variant damaged a base proof')
    if rows[3]['gold']['status'] != 'insufficient_evidence':
        raise ValueError('Necessary-support deletion leaves an alternative proof')
    if set(difficult['expected_trap_answer_ids']) & set(baseline['answer_ids']):
        raise ValueError('Lure equals correct answer')
    return {'schema_version': 'bridgeqa-family-v0.1', 'candidate_id': composer['candidate_id'],
            'question': composer['question'], 'query': composer['query'], 'mechanism': difficult['mechanism'],
            'wrong_path_explanation': difficult['wrong_path_explanation'], 'deletion_log': deletion_log,
            'variants': rows, 'source_track': 'literary_source_modernized_with_source_deletions',
            'split_group': composer['candidate_id'], 'human_review': 'not_run', 'release_status': 'development_candidate'}


def project(row, question, output_schema):
    # Only this allowlisted object reaches Blind Solver. IDs are content-opaque, condition-independent.
    contexts = [{'context_id': 'P' + digest(u['unit_id'])[:10], 'text': u['text']} for u in row['materials']]
    item_id = 'Q' + digest({'question': question, 'context': contexts})[:12]
    return {'item_id': item_id, 'question': question, 'contexts': contexts,
            'answer_policy': '仅依据本次提供材料。按问题指定角色和转述范围作答；无完整证据则insufficient_evidence，不凭作品常识补足。steps只写可核验的简短关系记录，不写长篇思维过程。每个quote必须是对应context中逐字、连续的原句子串，不加省略号、不改字或标点；非连续的依据分成多个evidence对象。此逐字引用规则同样适用于steps内的evidence。',
            'output_schema': output_schema}


def validate_projection(payload):
    if set(payload) != {'item_id', 'question', 'contexts', 'answer_policy', 'output_schema'}:
        raise ValueError('Model input contains non-allowlisted fields')
    if any(set(c) != {'context_id', 'text'} for c in payload['contexts']):
        raise ValueError('Context leaks internal metadata')
    return True


def quote_spans_overlap(left, right, text):
    """Both exact quotes may extend past different sides of one shared span."""
    def spans(quote):
        start = 0
        result = []
        while True:
            index = text.find(quote, start)
            if index < 0:
                return result
            result.append((index, index + len(quote)))
            start = index + 1
    if not left or not right:
        return False
    return any(max(a, c) < min(b, d) for a, b in spans(left) for c, d in spans(right))


def check_solver(answer, payload, row, origin, query):
    validate_projection(payload)
    texts = {c['context_id']: c['text'] for c in payload['contexts']}
    quotes_valid = True
    for evidence in answer['evidence'] + [e for step in answer['steps'] for e in step['evidence']]:
        quotes_valid &= evidence['context_id'] in texts and evidence['quote'] in texts.get(evidence['context_id'], '')
    entities = {e['id']: e for e in origin['entities']}

    def matches(surface, eid):
        return surface in [entities[eid]['name']] + entities[eid]['aliases']

    gold = row['gold']
    answer_correct = answer['status'] == gold['status'] and (
        (not gold['answer_ids'] and not answer['answers']) or
        (len(answer['answers']) == len(gold['answer_ids']) and all(any(matches(a, eid) for a in answer['answers']) for eid in gold['answer_ids'])))
    path_correct = False
    reference_coverage = False
    if answer['status'] == 'insufficient_evidence':
        path_correct = gold['status'] == 'insufficient_evidence' and not answer['steps'] and not answer['answers']
        reference_coverage = path_correct
    elif len(answer['steps']) == len(query['steps']):
        for proof in gold['proofs']:
            if all(matches(step['from'], proof['entities'][i]) and matches(step['to'], proof['entities'][i + 1]) and step['relation'] == query['steps'][i] for i, step in enumerate(answer['steps'])):
                path_correct = True
                by_id = {f['id']: f for f in origin['facts']}
                coverage = all(any(all(any(e['context_id'] == 'P' + digest(q['unit_id'])[:10]
                    and quote_spans_overlap(q['quote'], e['quote'], texts.get(e['context_id'], '')) for e in step['evidence'])
                    for q in bundle) for bundle in by_id[fid]['evidence_sets'])
                    for fid, step in zip(proof['facts'], answer['steps']))
                reference_coverage |= coverage
    return {'answer_and_status_correct': answer_correct, 'path_matches_permitted_proof': path_correct,
            'evidence_quotes_located': bool(quotes_valid), 'evidence_overlaps_reference_spans': reference_coverage,
            'strict_structural_success': bool(answer_correct and path_correct and quotes_valid and reference_coverage),
            'limit': 'Quote location and graph-path agreement do not independently establish natural-language entailment.'}


def supervisor_gate(review, required):
    names = [c['name'] for c in review['checks']]
    if len(names) != len(set(names)) or not set(required) <= set(names):
        raise ValueError('Supervisor omitted required checks or duplicated check names')
    if review['verdict'] == 'pass' and (any(not c['passed'] for c in review['checks']) or any(i['severity'] == 'major' for i in review['issues']) or review['required_changes']):
        raise ValueError('Supervisor pass contradicts its recorded defects')
    return review['verdict'] == 'pass'
