"""All-case successor to the failed v7 contract, with occurrence windows.

The prior trial remains frozen: [v7 runner](contracts_v7_experiment.py).
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

import contracts_v7_experiment as PARENT
import inventory_occurrences_v8 as INVENTORY
import scoring_review_v8 as SCORE

ROOT = PARENT.ROOT
WORK = ROOT / 'workspace/quality-v3/evidence-contract-v8'
BATCH = ROOT / 'artifacts/quality-v3/contracts-v8-run-001'
RUNTIME = ROOT / 'workspace/harness-prototype/runs/contracts-v8-run-001'
read, save, digest = PARENT.read, PARENT.save, PARENT.digest


def code_hashes():
    names = ('contracts_v8_experiment.py', 'contracts_v8_analysis.py', 'inventory_occurrences_v8.py',
             'scoring_review_v8.py', 'scoring_review_v7.py', 'inventory_coverage.py',
             'inventory_catalog.py', 'support_contract.py', 'scoring_isolation.py',
             'evidence_contract_experiment.py', 'experiment.py', 'scoring.py',
             'contracts_v7_experiment.py', 'contracts_v7_analysis.py')
    paths = [Path(__file__).parent / name for name in names]
    paths.extend(ROOT / name for name in (
        'src/deletion_review_v2/experiment.py', 'src/multi_agent_v0/core.py',
        'src/multi_agent_v0/formatting.py', 'src/multi_agent_v0/install_plugin.py',
        'src/multi_agent_v0/harness.patch.yml', 'src/multi_agent_v0/solver.patch.yml'))
    return {p.relative_to(ROOT).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}


def prepare():
    parent = PARENT.verify()
    cases = copy.deepcopy(parent['cases'])
    references = copy.deepcopy(parent['references'])
    for case in cases:
        case['split'] = 'disclosed_regression'
    fresh = read(WORK / 'heldout-cases.json')
    fresh_refs = read(WORK / 'heldout-reference.json')
    for case in fresh['scoring_cases']:
        ref = fresh_refs['scoring_references'][case['case_id']]
        arguments = {k: copy.deepcopy(case[k]) for k in ('answer', 'payload', 'query')}
        arguments.update({k: copy.deepcopy(ref[k]) for k in ('row', 'origin')})
        cases.append({'case_id': case['case_id'], 'kind': 'scoring',
                      'split': 'independent_forward_v8', 'arguments': arguments})
        references[case['case_id']] = copy.deepcopy(ref)
    for case in fresh['inventory_cases']:
        cases.append({'case_id': case['case_id'], 'kind': 'inventory',
                      'split': 'independent_forward_v8', 'payload': copy.deepcopy(case['payload'])})
        references[case['case_id']] = copy.deepcopy(fresh_refs['inventory_references'][case['case_id']])
    if len({c['case_id'] for c in cases}) != len(cases):
        raise ValueError('Repeated case IDs')
    contracts = {}
    for case in cases:
        if case['kind'] == 'scoring':
            package = SCORE.build_scoring_package(**case['arguments'])
            job = {'case_id': case['case_id'], 'kind': 'scoring', 'arm': 'candidate_v8'}
            contracts[digest(job)[:24]] = {'job': job, 'split': case['split'],
                'package': package, 'evidence_inputs': SCORE.step_evidence_inputs(package),
                'output_schema': SCORE.EVIDENCE_SCHEMA, 'skill': SCORE.EVIDENCE_PROMPT}
        else:
            canonical = PARENT.BASE.inventory_request(case['payload'])
            job = {'case_id': case['case_id'], 'kind': 'inventory', 'arm': 'occurrences_v8'}
            contracts[digest(job)[:24]] = {'job': job, 'split': case['split'],
                'canonical_request': canonical,
                'window_requests': INVENTORY.build_occurrence_requests(canonical, max_anchor_units=8)}
    jobs = sorted(contracts, key=lambda jid: digest({'jid': jid, 'seed': 2026102208}))
    protocol = {'version': 'contracts-v8-experiment-v0.8', 'model': 'deepseek-flash',
        'workers': 4, 'max_tokens': 12000, 'max_anchor_units': 8,
        'max_group_reviews_per_inventory': 40, 'code_sha256': code_hashes(),
        'scoring_semantics': 'v7 verdict core with pure identity display projection; optional hop audit reason accepted and preserved; case-specific ID/cardinality schema.',
        'comparison': 'Every v7 case rerun, plus independent additions. Earlier v7/v5 results kept; no selective failure rerun or causal gain claim.',
        'inventory_review': 'Every fact/unit must be assessed as a distinct relation-completion occurrence in a small window; review every positive occurrence separately.',
        'path_construction': 'Explicitly program-derived from original occurrence proposals; no model-authored path is repaired.',
        'failure_policy': 'Every window attempted; all partial failures and raw responses retained. Unknown never counted corrected.',
        'formal_release': False}
    base_calls = sum(len(c['evidence_inputs']) + 1 if c['job']['kind'] == 'scoring'
                     else len(c['window_requests']) for c in contracts.values())
    manifest = {'version': protocol['version'], 'cases': len(cases), 'logical_jobs': len(jobs),
        'planned_base_stage_calls': base_calls,
        'additional_group_review_calls': 'Response-dependent and separately counted.', 'formal_release': False}
    for name, obj in (('cases', cases), ('references', references), ('jobs', jobs),
                      ('protocol', protocol), ('request-contracts', contracts)):
        save(BATCH / (name + '.frozen.json'), obj)
        manifest[name + '_sha256'] = digest(obj)
    save(BATCH / 'manifest.json', manifest)
    return manifest


def verify(require_audit=True):
    objects = {name: read(BATCH / (name + '.frozen.json')) for name in (
        'cases', 'references', 'jobs', 'protocol', 'request-contracts')}
    manifest = read(BATCH / 'manifest.json')
    for name, value in objects.items():
        if digest(value) != manifest[name + '_sha256']:
            raise ValueError('Changed frozen object: ' + name)
    if objects['protocol']['code_sha256'] != code_hashes():
        raise ValueError('Changed frozen code')
    if require_audit:
        gate = read(BATCH / 'pre-audit.json')
        if gate.get('status') != 'approved' or gate.get('reviewer_kind') != 'independent_gpt_subagent':
            raise ValueError('Independent pre-audit required')
        for name in objects:
            if gate.get(name + '_sha256') != manifest[name + '_sha256']:
                raise ValueError('Pre-audit hash mismatch')
    return objects


def _failure(exc, secret, response):
    return {'status': 'protocol_failure' if response is not None or 'Protocol failure' in str(exc)
            else 'technical_failure', 'error_type': type(exc).__name__,
            'message': str(exc).replace(secret, '[REDACTED]')[:1500]}


def run(secret):
    objects = verify()
    contracts, protocol = objects['request-contracts'], objects['protocol']

    def worker(number):
        with PARENT.BASE.LEGACY.V2.HarnessCaller(secret, RUNTIME / f'worker-{number}',
                worker_id=f'contracts-v8-{number}', max_tokens=protocol['max_tokens']) as caller:
            for jid in objects['jobs'][number::protocol['workers']]:
                contract = contracts[jid]
                dest = RUNTIME / 'results' / (jid + '.json')
                if dest.exists():
                    if read(dest)['job'] != contract['job']:
                        raise ValueError('Resume identity mismatch')
                    continue
                result = {'job': contract['job'], 'split': contract['split']}
                response = None
                try:
                    if contract['job']['kind'] == 'scoring':
                        reviews = result['single_step_reviews'] = []
                        for index, item in enumerate(contract['evidence_inputs']):
                            response = None
                            response = caller.call(f'score-v8-{jid}-step-{index}', 'quote_review',
                                item, contract['output_schema'], contract['skill'])
                            SCORE.validate_evidence_review(response, item)
                            reviews.append(response)
                        result['evidence_review'] = SCORE.combine_evidence_reviews(contract['package'], reviews)
                        exact = SCORE.build_answer_contract(contract['package'], result['evidence_review'])
                        save(RUNTIME / 'derived-contracts' / (jid + '-answer.json'), exact, secret)
                        response = None
                        response = caller.call(f'answer-v8-{jid}', 'answer_review',
                            exact['input'], exact['output_schema'], exact['skill'])
                        result['answer_review'] = response
                        result['merged'] = SCORE.merge_scoring_results(contract['package'], result['evidence_review'], response)
                    else:
                        windows = result['window_results'] = []
                        raw_responses = []
                        for index, window in enumerate(contract['window_requests']):
                            response = None
                            item = {'window_id': window['window_id']}
                            try:
                                response = caller.call(f'occurrence-v8-{jid}-{index}', 'occurrence_review',
                                    window['input'], window['output_schema'], window['skill'])
                                item['answer'] = response
                                item['validation'] = INVENTORY.validate_occurrence_response(response, window['input'])
                                item['status'] = 'completed'
                                raw_responses.append(response)
                            except Exception as exc:
                                item.update(_failure(exc, secret, response))
                                if response is not None:
                                    item['failed_stage_response'] = response
                            windows.append(item)
                        if any(w['status'] != 'completed' for w in windows):
                            result['status'] = ('technical_failure' if any(w['status'] == 'technical_failure' for w in windows)
                                                else 'protocol_failure')
                            result['message'] = 'One or more occurrence windows failed; every window result retained.'
                        else:
                            assembly = INVENTORY.assemble_inventory(contract['canonical_request'], raw_responses)
                            result['assembly'] = assembly
                            group_requests = INVENTORY.build_group_review_requests(assembly)
                            if len(group_requests) > protocol['max_group_reviews_per_inventory']:
                                response = assembly
                                raise ValueError('Per-job group review budget exceeded; proposal not accepted')
                            reviews = result['group_reviews'] = []
                            for index, group in enumerate(group_requests):
                                exact = {k: group[k] for k in ('input', 'output_schema', 'skill')}
                                save(RUNTIME / 'derived-contracts' / (jid + f'-group-{index}.json'), exact, secret)
                                response = None
                                response = caller.call(f'group-v8-{jid}-{index}', 'group_review',
                                    exact['input'], exact['output_schema'], exact['skill'])
                                reviews.append(response)
                            result['group_validation'] = INVENTORY.validate_group_reviews(assembly, reviews)
                    result.setdefault('status', 'completed')
                except Exception as exc:
                    result.update(_failure(exc, secret, response))
                    if response is not None:
                        result['failed_stage_response'] = response
                save(dest, result, secret)
                print(json.dumps({'job': contract['job'], 'status': result['status']}, ensure_ascii=False), flush=True)

    with concurrent.futures.ThreadPoolExecutor(max_workers=protocol['workers']) as pool:
        list(pool.map(worker, range(protocol['workers'])))


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('command', choices=('prepare', 'verify', 'run'))
    args = parser.parse_args()
    if args.command == 'prepare':
        print(json.dumps(prepare(), ensure_ascii=False))
    elif args.command == 'verify':
        print({'verified': True, 'cases': len(verify()['cases'])})
    else:
        verify()
        key = os.environ.get('DEEPSEEK_API_KEY') or getpass.getpass('DeepSeek credential (hidden): ').strip()
        if not key:
            raise ValueError('Missing credential')
        run(key)
