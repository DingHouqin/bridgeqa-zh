"""Separate contract checks, semantic outcomes and real-call accounting.

Protocol and limitations: [evidence-contracts-v0.5.md](../../QA_Generator/specs/evidence-contracts-v0.5.md).
"""
from __future__ import annotations

import argparse
import collections
import copy
import hashlib
import json

import evidence_contract_experiment as E


def locate_unique(q, contexts):
    text = next(c['text'] for c in contexts if c['context_id'] == q['context_id'])
    start = text.find(q['quote'])
    if start < 0 or text.find(q['quote'], start + 1) >= 0:
        raise ValueError('Offline field adapter requires a unique original quote occurrence')
    return dict(q, start=start, end=start + len(q['quote']))


def adapt_candidate_inventory(c):
    """Translate old public field names without repairing an altered edge."""
    request = E.inventory_request(c['payload'])
    by_id = {e['fact_id']: e for e in request['requested_edges']}
    response = {'contract_version': E.INVENTORY.VERSION, 'request_digest': request['request_digest'],
                'facts': [], 'proof_paths': copy.deepcopy(c['candidate_inventory']['proof_paths']),
                'reason': c['candidate_inventory']['reason']}
    for f in c['candidate_inventory']['facts']:
        expected = by_id.get(f['id'])
        if expected is None or any(f[k] != expected['parent_role' if k == 'role' else k]
                                   for k in ('parent', 'child', 'role', 'scope')):
            raise ValueError('Candidate changes the edge denoted by its stable fact ID')
        response['facts'].append({'fact_id': f['id'], 'status': 'support_proposed',
            'support_groups': [[locate_unique(q, request['contexts']) for q in group]
                               for group in f['support_groups']], 'reason': '独立候选原样字段适配。'})
    return request, response


def offline():
    fresh = E.read(E.WORK / 'heldout-cases.json')
    refs = E.read(E.WORK / 'heldout-reference.json')['inventory_references']
    records = []
    for c in fresh['inventory_cases']:
        record = {'case_id': c['case_id']}
        try:
            request, response = adapt_candidate_inventory(c)
            record['report'] = E.INVENTORY.validate_inventory(response, request)
            record['protocol_valid'] = True
            if c.get('deletion_check'):
                d = c['deletion_check']
                spans = [locate_unique(q, request['contexts']) for q in d['removed_evidence']]
                after = E.INVENTORY.retained_inventory(response, request, spans, d['actual_contexts'])
                record['retained_graph_paths'] = after['inventory']['proof_paths']
                record['registered_path_remains'] = bool(after['inventory']['proof_paths'])
                record['deletion_claim_automatically_approved'] = after['report']['deletion_validity_established']
        except (ValueError, KeyError, TypeError) as exc:
            record.update(protocol_valid=False, error=str(exc))
        record['matches_independent_reference'] = record['protocol_valid'] == refs[c['case_id']]['expected_valid']
        if 'retained_graph_paths' in record:
            record['matches_independent_deletion_paths'] = (
                record['retained_graph_paths'] == refs[c['case_id']]['remaining_complete_paths'])
        records.append(record)
    result = {'candidate_checks': len(records), 'model_calls': 0,
              'mismatches': sum(not r['matches_independent_reference'] or
                                r.get('matches_independent_deletion_paths') is False for r in records),
              'records': records}
    E.save(E.WORK / 'independent-candidate-contract-checks.json', result)
    return {k: v for k, v in result.items() if k != 'records'}


def summarize():
    objects = E.verify(); refs = objects['references']; contracts = objects['request-contracts']
    results = {p.stem: E.read(p) for p in (E.RUNTIME / 'results').glob('*.json')}
    if set(results) - set(contracts):
        raise ValueError('Results contain unknown jobs')
    groups, rows = {}, []
    for jid in objects['jobs']:
        contract = contracts[jid]; job = contract['job']; r = results.get(jid)
        split = contract['split']; arm = job['arm']; kind = job['kind']
        key = '|'.join((kind, split, arm))
        g = groups.setdefault(key, collections.Counter())
        g['planned_jobs'] += 1
        ref = refs[job['case_id']]
        eligible = ref.get('analysis_eligible', True)
        if kind == 'scoring' and eligible:
            g['valid_case_planned' if ref['expected_valid'] else 'invalid_case_planned'] += 1
        row = {'job': job, 'split': split, 'analysis_eligible': eligible,
               'status': r['status'] if r else 'not_run'}
        g[row['status']] += 1
        if r and r['status'] == 'completed' and kind == 'scoring':
            m = r['merged']; verdict = m['verdict']
            row.update(verdict=verdict, raw_model_verdict=m.get('raw_model_verdict'),
                proof_support=m['proof_support'], reference_disagreement=m['private_reference_disagreement'])
            g['verdict_' + verdict] += 1
            if eligible:
                raw = m.get('raw_model_verdict')
                g['raw_false_block'] += bool(ref['expected_valid'] and raw == 'incorrect')
                g['raw_false_accept'] += bool(not ref['expected_valid'] and raw == 'supported')
                g['raw_undetermined'] += raw == 'needs_adjudication'
                g['false_block'] += bool(ref['expected_valid'] and verdict == 'incorrect')
                g['false_accept'] += bool(not ref['expected_valid'] and verdict == 'supported')
                g['correct_accept'] += bool(ref['expected_valid'] and verdict == 'supported')
                g['correct_reject'] += bool(not ref['expected_valid'] and verdict == 'incorrect')
                g['eligible_undetermined'] += verdict == 'needs_adjudication'
            else:
                g['reference_disputed'] += 1
        if r and r['status'] == 'completed' and kind == 'inventory':
            row['protocol_valid_only'] = r['validation']['protocol_valid']
            row['semantic_validity_established'] = r['validation']['semantic_validity_established']
        rows.append(row)
    calls, violations, sessions = [], [], []
    for path in sorted(E.RUNTIME.glob('worker-*/calls/*.input.json')):
        request = E.read(path); stage = path.name.removesuffix('.input.json')
        jid = stage.split('-step-')[0].removeprefix('evidence-v5-') if stage.startswith('evidence-v5-') else (
            stage.removeprefix('answer-v5-') if stage.startswith('answer-v5-') else stage.removeprefix('inventory-v5-'))
        contract = contracts[jid]
        if stage.startswith('evidence-v5-'):
            step = int(stage.split('-step-')[1]); expected = contract['evidence_inputs'][step]
            if request['input'] != expected or len(expected['steps']) != 1:
                violations.append({'stage': stage, 'error': 'incorrect_step_projection'})
            if contract['job']['arm'] == 'isolated' and 'unisolated_context' in request['input']:
                violations.append({'stage': stage, 'error': 'isolation_leak'})
        elif stage.startswith('answer-v5-'):
            expected = E.read(E.RUNTIME / 'derived-contracts' / (jid + '.json'))
            if any(request[k] != expected[k] for k in ('input', 'output_schema', 'skill')):
                violations.append({'stage': stage, 'error': 'derived_request_differs'})
        elif request['input'] != contract['input']:
            violations.append({'stage': stage, 'error': 'inventory_request_differs'})
        if request['model'] != 'deepseek-flash' or request['runtime_contract']['tools'] != 'all_model_tools_disabled':
            violations.append({'stage': stage, 'error': 'model_or_tools_changed'})
        calls.append({'stage': stage, 'sha256': hashlib.sha256(path.read_bytes()).hexdigest()})
    responses = sorted(E.RUNTIME.glob('worker-*/calls/*.attempt-*.response.json'))
    for p in responses:
        sessions.append(E.read(p)['session_id'])
    if len(set(sessions)) != len(sessions):
        violations.append({'error': 'duplicate_session_id'})
    summary = {'groups': {k: dict(v) for k, v in groups.items()}, 'logical_jobs': len(contracts),
        'recorded_jobs': len(results), 'planned_model_calls': E.read(E.BATCH / 'manifest.json')['planned_model_calls'],
        'persisted_logical_call_requests': len(calls), 'actual_response_sessions': len(responses),
        'request_violations': violations, 'formal_release': False,
        'limits': ['Targeted diagnostic selection; not overall accuracy.',
                   'Empty-step arms have identical inputs; their differences reflect repeated sampling.',
                   'Inventory protocol validity does not establish semantics or complete support coverage.',
                   'EH-S09 remains outside determinate denominators.']}
    E.save(E.BATCH / 'analysis/summary.json', summary)
    E.save(E.BATCH / 'analysis/cases.json', rows)
    E.save(E.BATCH / 'analysis/actual-request-audit.json', {'calls': calls, 'violations': violations})
    return summary


if __name__ == '__main__':
    parser = argparse.ArgumentParser(); parser.add_argument('command', choices=['offline', 'summarize'])
    args = parser.parse_args()
    print(json.dumps(offline() if args.command == 'offline' else summarize(), ensure_ascii=False))
