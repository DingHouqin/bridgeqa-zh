"""Freeze the next coverage/scoring trial; preserve all earlier failures.

Context: [v5/v6 report](../../QA_Generator/validation/2026-10-22_评分证据隔离与支持登记合同修复.md).
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

import evidence_contract_experiment as BASE
import inventory_coverage as INVENTORY
import scoring_review_v7 as SCORE

ROOT = BASE.ROOT
WORK = ROOT / 'workspace/quality-v3/evidence-contract-v7'
BATCH = ROOT / 'artifacts/quality-v3/contracts-v7-run-001'
RUNTIME = ROOT / 'workspace/harness-prototype/runs/contracts-v7-run-001'
read, save, digest = BASE.read, BASE.save, BASE.digest


def scorer(arm):
    return SCORE if arm == 'candidate_v7' else BASE.SCORE


def code_hashes():
    names = ('contracts_v7_experiment.py', 'contracts_v7_analysis.py', 'inventory_coverage.py', 'inventory_catalog.py',
             'support_contract.py', 'scoring_review_v7.py', 'scoring_isolation.py',
             'evidence_contract_experiment.py', 'experiment.py', 'scoring.py')
    paths = [Path(__file__).parent / name for name in names]
    paths.extend(ROOT / name for name in (
        'src/deletion_review_v2/experiment.py', 'src/multi_agent_v0/core.py',
        'src/multi_agent_v0/formatting.py', 'src/multi_agent_v0/install_plugin.py',
        'src/multi_agent_v0/harness.patch.yml', 'src/multi_agent_v0/solver.patch.yml'))
    return {p.relative_to(ROOT).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}


def prepare():
    parent = BASE.verify()
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
                      'split': 'independent_forward_v7', 'arguments': arguments})
        references[case['case_id']] = copy.deepcopy(ref)
    for case in fresh['inventory_cases']:
        cases.append({'case_id': case['case_id'], 'kind': 'inventory',
                      'split': 'independent_forward_v7', 'payload': copy.deepcopy(case['payload'])})
        references[case['case_id']] = copy.deepcopy(fresh_refs['inventory_references'][case['case_id']])
    if len({c['case_id'] for c in cases}) != len(cases):
        raise ValueError('Repeated case IDs')
    contracts = {}
    for case in cases:
        if case['kind'] == 'scoring':
            for arm in ('baseline_v5', 'candidate_v7'):
                module = scorer(arm)
                package = module.build_scoring_package(**case['arguments'])
                job = {'case_id': case['case_id'], 'kind': 'scoring', 'arm': arm}
                contracts[digest(job)[:24]] = {'job': job, 'split': case['split'],
                    'package': package, 'evidence_inputs': module.step_evidence_inputs(package),
                    'output_schema': module.EVIDENCE_SCHEMA, 'skill': module.EVIDENCE_PROMPT}
        else:
            canonical = BASE.inventory_request(case['payload'])
            job = {'case_id': case['case_id'], 'kind': 'inventory', 'arm': 'coverage_v7'}
            contracts[digest(job)[:24]] = {'job': job, 'split': case['split'],
                'canonical_request': canonical, 'input': INVENTORY.build_coverage_request(canonical),
                'output_schema': INVENTORY.COVERAGE_SCHEMA, 'skill': INVENTORY.COVERAGE_PROMPT}
    jobs = sorted(contracts, key=lambda jid: digest({'jid': jid, 'seed': 2026102207}))
    protocol = {'version': 'contracts-v7-experiment-v0.7', 'model': 'deepseek-flash',
        'workers': 4, 'max_tokens': 12000, 'max_group_reviews_per_inventory': 40,
        'code_sha256': code_hashes(),
        'score_arms': {arm: {'answer_schema': scorer(arm).ANSWER_SCHEMA,
                           'answer_prompt': scorer(arm).ANSWER_PROMPT}
                       for arm in ('baseline_v5', 'candidate_v7')},
        'comparison': 'Concurrent v5 versus v7 full scoring contracts; not a single-factor isolation experiment.',
        'inventory_review': 'Every proposed group reviewed in a fresh quote-only session; exact derived request saved before call.',
        'failure_policy': 'Preserve every terminal failure; no selective success reruns. Unknown is never counted corrected.',
        'formal_release': False}
    base_calls = sum(len(c['evidence_inputs']) + 1 if c['job']['kind'] == 'scoring' else 1
                     for c in contracts.values())
    manifest = {'version': protocol['version'], 'cases': len(cases), 'logical_jobs': len(jobs),
                'planned_base_stage_calls': base_calls,
                'additional_group_review_calls': 'Response-dependent; bounded by protocol and counted separately.',
                'formal_release': False}
    for name, obj in (('cases', cases), ('references', references), ('jobs', jobs),
                      ('protocol', protocol), ('request-contracts', contracts)):
        save(BATCH / (name + '.frozen.json'), obj)
        manifest[name + '_sha256'] = digest(obj)
    save(BATCH / 'manifest.json', manifest)
    return manifest


def verify(require_audit=True):
    objects = {n: read(BATCH / (n + '.frozen.json')) for n in (
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


def run(secret):
    objects = verify()
    contracts, protocol = objects['request-contracts'], objects['protocol']

    def worker(number):
        with BASE.LEGACY.V2.HarnessCaller(secret, RUNTIME / f'worker-{number}',
                worker_id=f'contracts-v7-{number}', max_tokens=protocol['max_tokens']) as caller:
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
                        module = scorer(contract['job']['arm'])
                        reviews = []
                        result['single_step_reviews'] = reviews
                        for index, step_input in enumerate(contract['evidence_inputs']):
                            response = None
                            response = caller.call(f'score-v7-{jid}-step-{index}', 'quote_review',
                                step_input, contract['output_schema'], contract['skill'])
                            module.validate_evidence_review(response, step_input)
                            reviews.append(response)
                        result['single_step_reviews'] = reviews
                        result['evidence_review'] = module.combine_evidence_reviews(contract['package'], reviews)
                        exact = {'input': module.build_answer_payload(contract['package'], result['evidence_review']),
                                 'output_schema': protocol['score_arms'][contract['job']['arm']]['answer_schema'],
                                 'skill': protocol['score_arms'][contract['job']['arm']]['answer_prompt']}
                        save(RUNTIME / 'derived-contracts' / (jid + '-answer.json'), exact, secret)
                        response = None
                        response = caller.call(f'answer-v7-{jid}', 'answer_review',
                            exact['input'], exact['output_schema'], exact['skill'])
                        result['answer_review'] = response
                        result['merged'] = module.merge_scoring_results(
                            contract['package'], result['evidence_review'], response)
                    else:
                        response = caller.call(f'inventory-v7-{jid}', 'inventory',
                            contract['input'], contract['output_schema'], contract['skill'])
                        result['answer'] = response
                        result['coverage_validation'] = INVENTORY.validate_coverage(response, contract['input'])
                        result['materialized'] = INVENTORY.materialize_inventory(response, contract['input'])
                        group_requests = INVENTORY.build_group_review_requests(response, contract['input'])
                        if len(group_requests) > protocol['max_group_reviews_per_inventory']:
                            raise ValueError('Per-job group review budget exceeded; proposal not accepted')
                        reviews = []
                        result['group_reviews'] = reviews
                        for index, group in enumerate(group_requests):
                            exact = {k: group[k] for k in ('input', 'output_schema', 'skill')}
                            save(RUNTIME / 'derived-contracts' / (jid + f'-group-{index}.json'), exact, secret)
                            response = None
                            review = caller.call(f'group-v7-{jid}-{index}', 'group_review',
                                exact['input'], exact['output_schema'], exact['skill'])
                            response = review
                            reviews.append(review)
                        result['group_reviews'] = reviews
                        result['group_validation'] = INVENTORY.validate_group_reviews(
                            result['answer'], contract['input'], reviews)
                    result['status'] = 'completed'
                except Exception as exc:
                    result.update(status='protocol_failure' if response is not None or
                        'Protocol failure' in str(exc) else 'technical_failure',
                        error_type=type(exc).__name__, message=str(exc).replace(secret, '[REDACTED]')[:1500])
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
