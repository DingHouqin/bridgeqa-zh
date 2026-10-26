"""Second inventory trial: exact source-span IDs replace model-computed indices.

The failed offset trial remains at the parent batch. Instructions: [README.md](README.md).
"""
import argparse
import concurrent.futures
import getpass
import hashlib
import json
import os
from pathlib import Path

import evidence_contract_experiment as BASE
import inventory_catalog as CATALOG

ROOT, WORK = BASE.ROOT, BASE.WORK
BATCH = ROOT / 'artifacts/quality-v3/inventory-catalog-v6'
RUNTIME = ROOT / 'workspace/harness-prototype/runs/inventory-catalog-v6'
read, save, digest = BASE.read, BASE.save, BASE.digest


def code_hashes():
    paths = [Path(__file__).parent / n for n in (
        'inventory_catalog_experiment.py', 'inventory_catalog.py', 'support_contract.py')]
    paths += [ROOT / 'src/deletion_review_v2/experiment.py', ROOT / 'src/multi_agent_v0/install_plugin.py',
              ROOT / 'src/multi_agent_v0/harness.patch.yml', ROOT / 'src/multi_agent_v0/solver.patch.yml']
    return {p.relative_to(ROOT).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}


def prepare():
    parent = BASE.verify()
    cases = [c for c in parent['cases'] if c['kind'] == 'inventory']
    refs = {c['case_id']: parent['references'][c['case_id']] for c in cases}
    contracts = {}
    for c in cases:
        canonical = BASE.inventory_request(c['payload'])
        job = {'case_id': c['case_id'], 'kind': 'inventory', 'arm': 'span_catalog'}
        contracts[digest(job)[:24]] = {'job': job, 'split': c['split'], 'canonical_request': canonical,
            'input': CATALOG.build_catalog_request(canonical), 'output_schema': CATALOG.CATALOG_SCHEMA,
            'skill': CATALOG.CATALOG_PROMPT}
    jobs = sorted(contracts, key=lambda j: digest({'jid': j, 'seed': 2026102206}))
    protocol = {'version': 'inventory-catalog-experiment-v0.6', 'model': 'deepseek-flash',
        'workers': 2, 'max_tokens': 4500, 'code_sha256': code_hashes(),
        'parent_batch': BASE.BATCH.relative_to(ROOT).as_posix(),
        'comparison': 'Same 10 source requests. New source-span selection contract; all are disclosed regressions, not held-out.',
        'automatic_repairs': 'Only exact expansion of preassigned span IDs. Never add support groups or repair paths.',
        'formal_release': False}
    manifest = {'version': protocol['version'], 'cases': len(cases), 'logical_jobs': len(jobs),
                'planned_model_calls': len(jobs), 'formal_release': False}
    for name, obj in [('cases', cases), ('references', refs), ('jobs', jobs),
                      ('protocol', protocol), ('request-contracts', contracts)]:
        save(BATCH / (name + '.frozen.json'), obj); manifest[name + '_sha256'] = digest(obj)
    save(BATCH / 'manifest.json', manifest)
    return manifest


def verify(require_audit=True):
    objects = {n: read(BATCH / (n + '.frozen.json')) for n in (
        'cases', 'references', 'jobs', 'protocol', 'request-contracts')}
    manifest = read(BATCH / 'manifest.json')
    for n, obj in objects.items():
        if manifest[n + '_sha256'] != digest(obj):
            raise ValueError('Changed frozen object: ' + n)
    if objects['protocol']['code_sha256'] != code_hashes():
        raise ValueError('Changed frozen code')
    if require_audit:
        gate = read(BATCH / 'pre-audit.json')
        if gate.get('status') != 'approved' or gate.get('reviewer_kind') != 'independent_gpt_subagent':
            raise ValueError('Independent pre-audit required')
        for n in objects:
            if gate.get(n + '_sha256') != manifest[n + '_sha256']:
                raise ValueError('Pre-audit binding mismatch')
    return objects


def run(secret):
    objects = verify(); protocol = objects['protocol']; contracts = objects['request-contracts']
    def worker(n):
        with BASE.LEGACY.V2.HarnessCaller(secret, RUNTIME / f'worker-{n}',
                worker_id=f'catalog-v6-{n}', max_tokens=protocol['max_tokens']) as caller:
            for jid in objects['jobs'][n::protocol['workers']]:
                c = contracts[jid]; dest = RUNTIME / 'results' / (jid + '.json')
                if dest.exists():
                    if read(dest)['job'] != c['job']:
                        raise ValueError('Resume identity changed')
                    continue
                result = {'job': c['job'], 'split': c['split']}; response = None
                try:
                    response = caller.call('catalog-v6-' + jid, 'inventory',
                        c['input'], c['output_schema'], c['skill'])
                    result['answer'] = response
                    result['materialized'] = CATALOG.materialize_inventory(response, c['input'])
                    result['validation'] = BASE.INVENTORY.validate_inventory(result['materialized'], c['canonical_request'])
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
    parser = argparse.ArgumentParser(); parser.add_argument('command', choices=['prepare', 'verify', 'run'])
    args = parser.parse_args()
    if args.command == 'prepare':
        print(json.dumps(prepare(), ensure_ascii=False))
    elif args.command == 'verify':
        print({'verified': True, 'cases': len(verify()['cases'])})
    else:
        verify()
        credential = os.environ.get('DEEPSEEK_API_KEY') or getpass.getpass('DeepSeek credential (hidden): ').strip()
        if not credential:
            raise ValueError('Missing credential')
        run(credential)
