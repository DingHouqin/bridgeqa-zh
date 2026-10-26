"""Freeze and evaluate the successor evidence contracts without editing history.

Run instructions and limits: [README.md](README.md).
This runner compares the same quote-review schema/prompt with versus without
additional unisolated information. The inventory trial is a contract probe.
"""
from __future__ import annotations

import argparse
import concurrent.futures
import copy
import getpass
import hashlib
import json
import os
from pathlib import Path

import experiment as LEGACY
import scoring_isolation as SCORE
import support_contract as INVENTORY

ROOT = Path(__file__).resolve().parents[2]
WORK = ROOT / 'workspace/quality-v3/evidence-contract-v5'
BATCH = ROOT / 'artifacts/quality-v3/evidence-contract-v5-run-002'
RUNTIME = ROOT / 'workspace/harness-prototype/runs/evidence-contract-v5-run-002'
OLD = ROOT / 'artifacts/quality-v3/round-3'
read, save, digest = LEGACY.read, LEGACY.save, LEGACY.digest
VERSION = 'evidence-contract-experiment-v0.5.1'


def legacy_score_arguments(case):
    """Adapt the frozen public v3 scoring input, preserving text and response."""
    p = case['payload']
    entities = []
    for e in p['visible_entity_bindings']:
        surfaces = e['visible_registered_surfaces']
        entities.append({'id': e['entity_id'], 'name': surfaces[0], 'aliases': surfaces[1:]})
    payload = {'item_id': case['case_id'], 'question': p['question'],
               'contexts': copy.deepcopy(p['contexts']),
               'answer_policy': '仅依据本次材料；提交引文必须逐字定位。', 'output_schema': {}}
    return {'answer': copy.deepcopy(p['candidate_response']), 'payload': payload,
            'row': {'gold': copy.deepcopy(p['reference_claims'])},
            'origin': {'entities': entities, 'facts': []}, 'query': copy.deepcopy(p['query'])}


def inventory_request(payload):
    args = {k: copy.deepcopy(payload.get(k, []))
            for k in ('question', 'query', 'contexts', 'requested_edges', 'entity_bindings')}
    args['entity_bindings'] = [{'id': e.get('id', e.get('entity_id')), 'name': e['name'],
                               'aliases': e.get('aliases', [])} for e in args['entity_bindings']]
    return INVENTORY.make_inventory_request(**args)


def selected_regressions(cases, refs):
    """A disclosed targeted diagnostic, never an overall ability estimate."""
    scores = [c for c in cases if c['kind'] == 'scoring']
    prior = ROOT / 'workspace/harness-prototype/runs/quality-v3-round-3/results'
    false_blocks = set()
    for path in sorted(prior.glob('*.json')):
        r = read(path); job = r['job']
        if (job['kind'] == 'scoring' and job['arm'] == 'skills'
                and refs[job['case_id']].get('expected_valid')
                and r.get('answer', {}).get('verdict') == 'incorrect'):
            false_blocks.add(job['case_id'])
    if len(false_blocks) != 8:
        raise ValueError('Historical eight-error diagnostic changed')
    selected = set(false_blocks) | {'R2-SC-C-05', 'R2-SC-C-06', 'R3-SC-C-05', 'R3-SC-C-06'}
    for strict in (False, True):
        group = sorted(c['case_id'] for c in scores
            if c['case_id'].startswith('SCORE-DEV-')
            and c['payload']['candidate_response']['status'] == 'answerable'
            and refs[c['case_id']].get('expected_valid')
            and c['structural']['legacy'].get('strict_structural_success') is strict)
        selected.update(group[:4])
    return [c for c in scores if c['case_id'] in selected]


def _code_hashes():
    names = ['evidence_contract_experiment.py', 'scoring_isolation.py', 'support_contract.py',
             'scoring.py', 'experiment.py']
    paths = [Path(__file__).parent / n for n in names]
    paths += [ROOT / 'src/deletion_review_v2/experiment.py', ROOT / 'src/multi_agent_v0/core.py',
              ROOT / 'src/multi_agent_v0/formatting.py', ROOT / 'src/multi_agent_v0/harness.patch.yml',
              ROOT / 'src/multi_agent_v0/solver.patch.yml']
    return {p.relative_to(ROOT).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}


def prepare():
    old_cases = read(OLD / 'cases.frozen.json'); old_refs = read(OLD / 'references.frozen.json')
    fresh = read(WORK / 'heldout-cases.json'); fresh_refs = read(WORK / 'heldout-reference.json')
    cases, refs = [], {}
    for c in selected_regressions(old_cases, old_refs):
        cases.append({'case_id': c['case_id'], 'kind': 'scoring', 'split': 'targeted_regression',
                      'arguments': legacy_score_arguments(c), 'exposed_payload': c['payload']})
        refs[c['case_id']] = old_refs[c['case_id']]
    for c in old_cases:
        if c['kind'] == 'inventory':
            cases.append({'case_id': c['case_id'], 'kind': 'inventory', 'split': 'regression_probe',
                          'payload': c['payload']})
            refs[c['case_id']] = old_refs[c['case_id']]
    # Fresh author uses old public APIs. Only field adaptation is performed here.
    for c in fresh['scoring_cases']:
        ref = copy.deepcopy(fresh_refs['scoring_references'][c['case_id']])
        if c['case_id'] == 'EH-S09':
            ref['analysis_eligible'] = False
            ref['reference_state'] = 'disputed_parent_role_not_specified'
            ref['dispute_reason'] = '有一女 establishes parenthood but not fatherhood; original reference is retained separately.'
        args = {k: copy.deepcopy(c[k]) for k in ('answer', 'payload', 'query')}
        args.update({k: copy.deepcopy(ref[k]) for k in ('row', 'origin')})
        exposed = LEGACY.semantic_payload(**args)
        cases.append({'case_id': c['case_id'], 'kind': 'scoring', 'split': 'independent_forward',
                      'arguments': args, 'exposed_payload': exposed})
        refs[c['case_id']] = ref
    seen_inventory_inputs = set()
    for c in fresh['inventory_cases']:
        identity = digest(inventory_request(c['payload']))
        if identity in seen_inventory_inputs:
            continue  # Candidate corruptions sharing one source are offline checks, not new generation inputs.
        seen_inventory_inputs.add(identity)
        cases.append({'case_id': c['case_id'], 'kind': 'inventory', 'split': 'independent_forward',
                      'payload': c['payload']})
        refs[c['case_id']] = fresh_refs['inventory_references'][c['case_id']]
    if len({c['case_id'] for c in cases}) != len(cases):
        raise ValueError('Duplicate case ID')
    contracts = {}
    for c in cases:
        if c['kind'] == 'scoring':
            package = SCORE.build_scoring_package(**c['arguments'])
            for arm in ('isolated', 'exposed_control'):
                job = {'case_id': c['case_id'], 'kind': 'scoring', 'arm': arm}
                contracts[digest(job)[:24]] = {'job': job, 'split': c['split'], 'package': package,
                    'evidence_inputs': [dict(p, **({'unisolated_context': copy.deepcopy(c['exposed_payload'])}
                        if arm == 'exposed_control' else {})) for p in SCORE.step_evidence_inputs(package)],
                    'output_schema': SCORE.EVIDENCE_SCHEMA,
                    'skill': SCORE.EVIDENCE_PROMPT}
        else:
            job = {'case_id': c['case_id'], 'kind': 'inventory', 'arm': 'new_contract'}
            contracts[digest(job)[:24]] = {'job': job, 'split': c['split'],
                'input': inventory_request(c['payload']), 'output_schema': INVENTORY.INVENTORY_SCHEMA,
                'skill': INVENTORY.INVENTORY_PROMPT}
    protocol = {'version': VERSION, 'model': 'deepseek-flash', 'workers': 4,
        'previous_startup_only_attempt': 'artifacts/quality-v3/evidence-contract-v5',
        'startup_repair': 'Install the same local plugin in isolated workspace homes with filesystem-link permission before running; no model output existed in attempt one.',
        'max_tokens': 4500, 'formal_release': False, 'code_sha256': _code_hashes(),
        'answer_schema': SCORE.ANSWER_SCHEMA, 'answer_prompt': SCORE.ANSWER_PROMPT,
        'comparison': 'Same stage-one schema/prompt and stage-two rule; only added unisolated_context differs.',
        'stage_one_policy': 'One independent model session per submitted step; empty refusal has a deterministic empty review and no stage-one call.',
        'stage_two_policy': 'Always run for every schema-valid stage one; freeze exact derived request before call. Empty-step arms have identical inputs and are repeated diagnostics, not an information-exposure contrast.',
        'selection': 'Eight R3 false blocks; R2/R3 C05/C06; first four sorted legacy answerable valid cases per strict-score group; all six inventory regressions; all fresh scoring cases; deduplicated fresh inventory source inputs (all candidate corruptions checked offline).',
        'fresh_case_sha256': hashlib.sha256((WORK / 'heldout-cases.json').read_bytes()).hexdigest(),
        'fresh_reference_sha256': hashlib.sha256((WORK / 'heldout-reference.json').read_bytes()).hexdigest(),
        'old_case_sha256': hashlib.sha256((OLD / 'cases.frozen.json').read_bytes()).hexdigest()}
    jobs = sorted(contracts, key=lambda jid: digest({'jid': jid, 'seed': 2026102205}))
    manifest = {'version': VERSION, 'cases': len(cases), 'logical_jobs': len(jobs),
                'planned_model_calls': sum(len(v['evidence_inputs']) + 1 if v['job']['kind'] == 'scoring' else 1 for v in contracts.values()),
                'formal_release': False}
    for name, obj in [('cases', cases), ('references', refs), ('jobs', jobs),
                      ('protocol', protocol), ('request-contracts', contracts)]:
        save(BATCH / (name + '.frozen.json'), obj); manifest[name + '_sha256'] = digest(obj)
    save(BATCH / 'manifest.json', manifest)
    return manifest


def verify(require_pre_audit=True):
    manifest = read(BATCH / 'manifest.json')
    objects = {n: read(BATCH / (n + '.frozen.json'))
               for n in ('cases', 'references', 'jobs', 'protocol', 'request-contracts')}
    for n, obj in objects.items():
        if digest(obj) != manifest[n + '_sha256']:
            raise ValueError('Frozen object changed: ' + n)
    if _code_hashes() != objects['protocol']['code_sha256']:
        raise ValueError('Frozen code changed; prepare another version')
    if require_pre_audit:
        audit = read(BATCH / 'pre-audit.json')
        if audit.get('status') != 'approved' or audit.get('reviewer_kind') != 'independent_gpt_subagent':
            raise ValueError('Independent pre-audit required')
        for n in objects:
            if audit.get(n + '_sha256') != manifest[n + '_sha256']:
                raise ValueError('Pre-audit digest mismatch: ' + n)
    return objects


def check():
    """All 99 old score projections, not just the selected model subset."""
    records = []
    for c in read(OLD / 'cases.frozen.json'):
        if c['kind'] != 'scoring':
            continue
        args = legacy_score_arguments(c); package = SCORE.build_scoring_package(**args)
        changed = copy.deepcopy(args)
        changed['answer']['brief_reason'] = 'POISON_RATIONALE_断言丢失关系仍成立'
        changed['answer']['answers'] = ['POISON_TOP_LEVEL_ANSWER']
        changed['row']['gold']['answer_ids'] = ['POISON_GOLD']
        changed['row']['gold']['proofs'] = [{'POISON_PROOF': True}]
        changed['origin']['facts'] = [{'POISON_FACT': True}]
        changed['payload']['contexts'].append({'context_id': 'NEW', 'text': 'POISON_OUTSIDE_CITATION'})
        other = SCORE.build_scoring_package(**changed)
        invariant = package['evidence_input'] == other['evidence_input']
        if not invariant:
            raise ValueError('Stage-one isolation regression: ' + c['case_id'])
        single_inputs = SCORE.step_evidence_inputs(package)
        if single_inputs != SCORE.step_evidence_inputs(other):
            raise ValueError('Single-step isolation regression: ' + c['case_id'])
        for i, expected in enumerate(single_inputs):
            adjacent = copy.deepcopy(args)
            for j, step in enumerate(adjacent['answer']['steps']):
                if j != i:
                    step['evidence'] = [{'context_id': 'POISON_NEIGHBOR', 'quote': 'POISON_NEIGHBOR_QUOTE'}]
            revised = SCORE.build_scoring_package(**adjacent)
            if SCORE.step_evidence_inputs(revised)[i] != expected:
                raise ValueError('Adjacent step crossed isolation boundary: ' + c['case_id'])
        records.append({'case_id': c['case_id'], 'stage_one_invariant': invariant,
                        'single_step_requests': len(single_inputs), 'adjacent_step_invariant': True,
                        'evidence_input_sha256': package['evidence_input']['input_sha256']})
    result = {'version': VERSION, 'regressions': len(records), 'violations': 0,
              'model_calls': 0, 'records': records, 'historical_code_sha256': _code_hashes()}
    save(WORK / 'isolation-regression-v2.json', result)
    return {'regressions': len(records), 'violations': 0, 'model_calls': 0}


def run(secret):
    objects = verify(); contracts = objects['request-contracts']
    jobs = objects['jobs']; protocol = objects['protocol']
    def worker(n):
        with LEGACY.V2.HarnessCaller(secret, RUNTIME / f'worker-{n}',
                worker_id=f'evidence-v5-{n}', max_tokens=protocol['max_tokens']) as caller:
            for jid in jobs[n::protocol['workers']]:
                dest = RUNTIME / 'results' / (jid + '.json')
                c = contracts[jid]
                if dest.exists():
                    if read(dest)['job'] != c['job']:
                        raise ValueError('Resume identity mismatch')
                    continue
                result = {'job': c['job'], 'split': c['split']}; response = None
                try:
                    if c['job']['kind'] == 'scoring':
                        reviews = []
                        canonical = SCORE.step_evidence_inputs(c['package'])
                        for step_number, (step_input, expected) in enumerate(zip(c['evidence_inputs'], canonical)):
                            response = None
                            response = caller.call('evidence-v5-' + jid + '-step-' + str(step_number), 'quote_review',
                                step_input, c['output_schema'], c['skill'])
                            SCORE.validate_evidence_review(response, expected)
                            reviews.append(response)
                        response = SCORE.combine_evidence_reviews(c['package'], reviews)
                        result['single_step_reviews'] = reviews
                        result['evidence_review'] = response
                        derived = SCORE.build_answer_payload(c['package'], response)
                        exact = {'input': derived, 'output_schema': protocol['answer_schema'],
                                 'skill': protocol['answer_prompt']}
                        save(RUNTIME / 'derived-contracts' / (jid + '.json'), exact, secret)
                        response = None
                        response = caller.call('answer-v5-' + jid, 'answer_review',
                            derived, exact['output_schema'], exact['skill'])
                        result['answer_review'] = response
                        result['merged'] = SCORE.merge_scoring_results(
                            c['package'], result['evidence_review'], response)
                    else:
                        response = caller.call('inventory-v5-' + jid, 'inventory',
                            c['input'], c['output_schema'], c['skill'])
                        result['answer'] = response
                        result['validation'] = INVENTORY.validate_inventory(response, c['input'])
                    result['status'] = 'completed'
                except Exception as exc:
                    result.update(status='protocol_failure' if response is not None or
                        'Protocol failure' in str(exc) else 'technical_failure',
                        error_type=type(exc).__name__, message=str(exc).replace(secret, '[REDACTED]')[:1000])
                    if response is not None:
                        result['failed_stage_response'] = response
                save(dest, result, secret)
                print(json.dumps({'job': c['job'], 'status': result['status']}, ensure_ascii=False), flush=True)
    with concurrent.futures.ThreadPoolExecutor(max_workers=protocol['workers']) as pool:
        list(pool.map(worker, range(protocol['workers'])))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(); parser.add_argument('command', choices=['check', 'prepare', 'verify', 'run'])
    args = parser.parse_args()
    if args.command == 'check':
        print(json.dumps(check(), ensure_ascii=False))
    elif args.command == 'prepare':
        print(json.dumps(prepare(), ensure_ascii=False))
    elif args.command == 'verify':
        print(json.dumps({'verified': True, 'cases': len(verify()['cases'])}))
    else:
        verify()  # Do not request credentials before the pre-audit passes.
        credential = os.environ.get('DEEPSEEK_API_KEY') or getpass.getpass('DeepSeek credential (hidden): ').strip()
        if not credential:
            raise ValueError('Missing credential')
        run(credential)
