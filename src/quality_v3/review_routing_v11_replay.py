"""Re-route the existing real v10 batch; make no new provider calls.

Only actual, operator-attested independent audits can supply review receipts.
Runtime routing is in [review_gate_v11.py](review_gate_v11.py); no case whitelist
is a routing policy. The old raw deliveries and audits are never edited.
"""
from __future__ import annotations

import argparse
from collections import Counter
import copy
import hashlib
import json
from pathlib import Path

import contracts_v10_experiment as E
import review_gate_v11 as G

ROOT = Path(__file__).resolve().parents[2]
WORK = ROOT / 'workspace/quality-v3/evidence-contract-v11'
OUT = ROOT / 'artifacts/quality-v3/review-routing-v11-001'
AUTHORITY = WORK / 'review-authorities.json'


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def _receipt(request, draft, contract, artifact, artifact_sha, record_index, authority):
    return {'version': G.VERSION, 'scope': G.CORE_SCOPE,
        'request_sha256': request['request_sha256'], 'source_sha256': request['source_sha256'],
        'draft_bytes_sha256': request['draft_bytes_sha256'], 'decision': 'confirmed',
        'unresolved_facets': [], 'reviewer_identity': authority['reviewer_identity'],
        'reviewer_kind': 'independent_strong_agent', 'source_artifact_sha256': artifact_sha,
        'source_record_index': record_index,
        'confirmed_facets': request['required_facets'], 'reviewed_coverage': request['required_coverage'],
        'confirmed_core': G.core_projection(contract, draft),
        'evidence_scope_note': 'Migrated from the actual independent source review of this exact '
            'v10 draft. Coverage identifiers are regenerated read-scope targets, not invented '
            'per-unit semantic labels. No raw auxiliary dimension or free reason is certified.',
        'source_review_kind': artifact['reviewer_task']}


def evaluate_batch(contracts, raw_results, audit_bytes, authorities):
    """Pure replay with explicit trusted operator inputs, suitable for audit."""
    if set(raw_results) != set(contracts) or len(contracts) != 54:
        raise ValueError('Replay requires every one of the 54 actual task deliveries')
    audits = {}
    by_kind = {'scoring': {}, 'inventory': {}}
    for kind in ('scoring', 'inventory'):
        authority = authorities['artifacts'][kind]
        raw = audit_bytes[kind]
        if (sha(raw) != authority['sha256']
                or authority.get('actual_independent_source_review_verified') is not True
                or authority.get('permitted_scope') != G.CORE_SCOPE):
            raise ValueError('Independent audit is not attested for this exact scope/byte artifact')
        artifact = G._load(raw)
        if artifact['reviewer_task'] != authority['reviewer_identity']:
            raise ValueError('Actual reviewer identity differs from the operator attestation')
        audits[kind] = artifact
        for index, record in enumerate(artifact['records']):
            jid = record['job_id']
            if jid in by_kind[kind]:
                raise ValueError('Duplicate independent review record')
            by_kind[kind][jid] = (index, record)
        expected = {jid for jid, c in contracts.items() if c['job']['kind'] == kind}
        if set(by_kind[kind]) != expected:
            raise ValueError('Independent audit must retain every task, including failed or disputed ones')

    receipts, registry, baseline, routed, records = {}, {}, {}, {}, []
    source_counts = Counter()
    for jid, contract in contracts.items():
        raw = raw_results[jid]
        draft = G._load(raw)
        kind = contract['job']['kind']
        if draft['job'] != contract['job'] or draft['split'] != contract['split']:
            raise ValueError('Original delivery identity/split mismatch')
        if draft['status'] not in ('completed', 'protocol_failure', 'technical_failure'):
            raise ValueError('Original delivery is nonterminal')
        source_counts[draft['status']] += 1
        baseline[jid] = G.route(contract, raw, closed_world=True)
        request = G.review_request(contract, raw, closed_world=True)
        index, record = by_kind[kind][jid]
        if record['case_id'] != contract['job']['case_id']:
            raise ValueError('Review record refers to another case')
        if kind == 'scoring':
            if (record['result_sha256'] != sha(raw)
                    or record['source_expectation_before_model_output']['v10_native_package_sha256']
                    != G.digest(contract['package'])):
                raise ValueError('Scoring review input or original-result byte binding differs')
            accepted = record['independent_audit']['whole_report_semantic_success'] is True
        else:
            if (record['original_result_sha256'] != sha(raw)
                    or record['source_expectations']['canonical_request'] != contract['canonical_request']):
                raise ValueError('Inventory review source or original-result byte binding differs')
            accepted = record['strict_delivered_semantic_success'] is True
        if accepted:
            if draft['status'] != 'completed':
                raise ValueError('A failed historical draft cannot be migrated as a confirmed core')
            authority = authorities['artifacts'][kind]
            receipt = _receipt(request, draft, contract, audits[kind],
                               authority['sha256'], index, authority)
            receipts[jid] = receipt
            registry[G.digest(receipt)] = {key: receipt[key] for key in (
                'source_artifact_sha256', 'reviewer_identity')}
            registry[G.digest(receipt)]['actual_independent_source_review_verified'] = True
        routed[jid] = G.route(contract, raw, closed_world=True,
            receipt=receipts.get(jid), trusted_registry=registry)
        if accepted and not routed[jid]['can_use_as_determinate_core']:
            raise ValueError('An attested minimal-core migration failed validation; do not silently drop it')
        if not accepted and routed[jid]['status'] == 'independently_reviewed_core':
            raise ValueError('No review artifact confirms this draft')
        records.append({'job_id': jid, 'case_id': contract['job']['case_id'], 'kind': kind,
            'original_delivery_status': draft['status'], 'original_raw_sha256': sha(raw),
            'before_review_status': baseline[jid]['status'],
            'status': routed[jid]['status'], 'label': routed[jid]['label'],
            'original_draft_certified': False, 'conclusion': routed[jid]['conclusion'],
            'receipt_sha256': G.digest(receipts[jid]) if jid in receipts else None})

    before = Counter(x['status'] for x in baseline.values())
    after = Counter(x['status'] for x in routed.values())
    observed_core_disagreements = []
    for jid, result in routed.items():
        if not result['can_use_as_determinate_core']:
            if result['conclusion'] is not None:
                raise ValueError('Review-pending result exposed a determinate conclusion')
            continue
        # This counts disagreement with actual audited cores, not universal error.
        if jid not in receipts or result['conclusion'] != receipts[jid]['confirmed_core']:
            observed_core_disagreements.append(jid)
    summary = {'version': G.VERSION, 'execution_kind': 'offline_routing_replay_of_existing_real_model_data',
        'new_provider_calls': 0, 'original_real_model_batch': 'artifacts/quality-v3/contracts-v10-run-001',
        'logical_jobs': len(contracts), 'original_status_counts': dict(source_counts),
        'before_independent_review': dict(before), 'after_existing_independent_review': dict(after),
        'actual_independent_receipts_migrated': len(receipts),
        'automatic_and_migrated_review_overlap': sum(jid in receipts and
            baseline[jid]['status'] == 'automatically_determined_core' for jid in baseline),
        'determinate_core_union': sum(x['can_use_as_determinate_core'] for x in routed.values()),
        'pending_review': sum(x['status'] == 'requires_review' for x in routed.values()),
        'published_core_receipt_mismatches': observed_core_disagreements,
        'new_independent_semantic_zero_error_trial_performed': False,
        'original_model_repair_successes_added': 0, 'pending_counted_as_correct_semantics': 0,
        'certified_scope': G.CORE_SCOPE, 'formal_release': False,
        'limits': ['No new DeepSeek or strong-agent model trial was run by this replay.',
            'The original 40 completed and 14 failed deliveries remain unchanged; reviewed routing is a separate layer.',
            'Trusted receipts originate in already executed independent source audits, not automatic case-name rules.',
            'Read-scope coverage is not a mathematical proof of semantic completeness; actual review quality remains a trust boundary.',
            'No known error in these finite checked cores is not a guarantee for new natural-language sources.',
            'Raw reasons, auxiliary dimensions and natural-language question intent are not certified by a minimal-core receipt.',
            'All-defer can be safe abstention but does not establish useful automatic coverage or a repaired model.']}
    return {'summary': summary, 'records': records, 'baseline_routes': baseline,
            'routes': routed, 'receipts': receipts, 'trusted_receipt_registry': registry}


def load_snapshot():
    startup_sources = [Path(__file__), Path(G.__file__), E.BATCH / 'manifest.json']
    startup_hashes = {p.relative_to(ROOT).as_posix(): sha(p.read_bytes()) for p in startup_sources}
    objects = E.verify()
    contracts = objects['request-contracts']
    result_paths = {jid: E.RUNTIME / 'results' / (jid + '.json') for jid in contracts}
    raw_results = {jid: path.read_bytes() for jid, path in result_paths.items()}
    authority_bytes = AUTHORITY.read_bytes()
    authorities = G._load(authority_bytes)
    audit_bytes = {kind: (ROOT / entry['path']).read_bytes()
                   for kind, entry in authorities['artifacts'].items()}
    sources = [Path(__file__), Path(G.__file__), E.BATCH / 'manifest.json',
        E.BATCH / 'cases.frozen.json', E.BATCH / 'references.frozen.json',
        E.BATCH / 'jobs.frozen.json', E.BATCH / 'protocol.frozen.json',
        E.BATCH / 'request-contracts.frozen.json']
    sources += [ROOT / p for p in objects['protocol']['code_sha256']]
    captured = {p.relative_to(ROOT).as_posix(): p.read_bytes() for p in sources}
    bindings = {relative: sha(raw) for relative, raw in captured.items()}
    for relative, expected in startup_hashes.items():
        if bindings[relative] != expected:
            raise ValueError('Manifest/gate/adapter changed during verified snapshot: ' + relative)
    for key in ('cases', 'references', 'jobs', 'protocol', 'request-contracts'):
        path = E.BATCH / (key + '.frozen.json')
        if G._load(captured[path.relative_to(ROOT).as_posix()]) != objects[key]:
            raise ValueError('Captured frozen input differs from verified object: ' + key)
    for relative, expected in objects['protocol']['code_sha256'].items():
        if bindings[relative] != expected:
            raise ValueError('Captured dependency differs from frozen protocol: ' + relative)
    bindings[AUTHORITY.relative_to(ROOT).as_posix()] = sha(authority_bytes)
    for kind, entry in authorities['artifacts'].items():
        bindings[entry['path']] = sha(audit_bytes[kind])
    for jid, path in result_paths.items():
        bindings[path.relative_to(ROOT).as_posix()] = sha(raw_results[jid])
    assert_sources_unchanged(bindings)
    if E.verify() != objects:
        raise ValueError('Verified frozen objects changed during input snapshot')
    assert_sources_unchanged(bindings)
    return (contracts, raw_results, audit_bytes, authorities), bindings


def load_inputs():
    return load_snapshot()[0]


def assert_sources_unchanged(bindings):
    for relative, expected in bindings.items():
        if sha((ROOT / relative).read_bytes()) != expected:
            raise ValueError('Input/code changed since replay snapshot: ' + relative)


def main(write=False):
    inputs, bindings = load_snapshot()
    output = evaluate_batch(*inputs)
    if write:
        assert_sources_unchanged(bindings)
        if OUT.exists():
            raise ValueError('Preserve existing routing artifact; do not overwrite it')
        OUT.mkdir(parents=True)
        def save(path, value):
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
        save(OUT / 'summary.json', output['summary'])
        save(OUT / 'cases.json', output['records'])
        save(OUT / 'review-receipts.json', output['receipts'])
        save(OUT / 'operator-trusted-registry.json', output['trusted_receipt_registry'])
        for jid, route in output['routes'].items():
            save(OUT / 'routes' / (jid + '.json'), route)
        save(OUT / 'source-bindings.json', bindings)
        assert_sources_unchanged(bindings)
        save(OUT / 'complete.json', {'status': 'complete', 'new_provider_calls': 0,
            'file_sha256': {p.relative_to(OUT).as_posix(): sha(p.read_bytes())
                            for p in OUT.rglob('*.json')}})
    print(json.dumps(output['summary'], ensure_ascii=False))
    return output


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--write', action='store_true')
    main(parser.parse_args().write)
