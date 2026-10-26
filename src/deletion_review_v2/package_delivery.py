"""Freeze machine delivery without asserting independent post-audit approval.

Usage: package_delivery.py --batch DIR --reviews DIR --blind DIR --analysis DIR --out DIR
Raw runtime requests/responses remain in place and are bound by a SHA-256 index.
"""
from __future__ import annotations
import argparse
import collections
import hashlib
from pathlib import Path

from experiment import CORE, ROOT, SCHEMAS, digest, make_jobs, read, save_new_or_same
from review_cases import project_review, verify_reference_gate
from analyze_batch import load_rows


def checked_path(path, *, exists=True):
    path = Path(path).resolve()
    if not path.is_relative_to(ROOT.resolve()):
        raise ValueError('Delivery path must remain inside project: ' + str(path))
    if exists and not path.is_dir():
        raise ValueError('Missing input directory: ' + str(path))
    return path


def file_record(path):
    path = Path(path).resolve()
    if not path.is_relative_to(ROOT.resolve()):
        raise ValueError('Indexed file resolves outside project')
    raw = path.read_bytes()
    return {'path': path.relative_to(ROOT).as_posix(),
            'sha256': hashlib.sha256(raw).hexdigest(), 'bytes': len(raw)}


def blind_jobs(families):
    return ([{'family_id': f['family_id'], 'variant_index': i}
             for f in families for i in range(len(f['variants']))] +
            [{'family_id': f['family_id'], 'variant_index': None} for f in families])


def complete_rows(folder, expected):
    rows = load_rows(folder)
    wanted = {digest(job) for job in expected}
    actual = {digest(row['job']) for row in rows}
    if len(wanted) != len(expected):
        raise ValueError('Duplicate scheduled jobs')
    if actual != wanted:
        raise ValueError('Incomplete or unexpected result jobs: missing=%d unexpected=%d' %
                         (len(wanted-actual), len(actual-wanted)))
    if read(Path(folder)/'jobs.frozen.json') != expected:
        raise ValueError('Persisted schedule differs from the frozen expected schedule')
    for row in rows:
        if row.get('status') not in ('completed', 'technical_failure', 'protocol_failure'):
            raise ValueError('Result has no final machine disposition')
    return rows


def verify_family_binding(batch, cases, refs, families):
    binding = read(batch/'family-binding.json')
    if binding.get('families_sha256') != digest(families):
        raise ValueError('Family-binding family digest mismatch')
    if binding.get('all_families_equal_approved_correct_case') is not True:
        raise ValueError('Family binding does not attest approved-candidate equality')
    if read(batch/'reference_review.json').get('family_content_sha256') != digest(families):
        raise ValueError('Independent reference review does not bind these families')
    correct = [case for case in cases if case['track']=='source' and
               refs[case['case_id']]['expected_verdict']=='pass']
    indexed = {case['family_id']: case['candidate'] for case in correct}
    if len(indexed) != len(correct) or len(indexed) != len(families):
        raise ValueError('Correct source candidate / family coverage mismatch')
    for family in families:
        if family != indexed.get(family['family_id']):
            raise ValueError('Blind family differs from an approved correct candidate')
    if binding.get('cases_sha256', digest(cases)) != digest(cases):
        raise ValueError('Family-binding case digest mismatch')
    return binding


def validate_input_hashes(cases, families, review_rows, blind_rows):
    indexed = {c['case_id']: c for c in cases}
    for row in review_rows:
        if row['status']=='completed':
            job = row['job']
            expected = project_review(indexed[job['case_id']], job['condition'])
            if row.get('input_hash') != digest(expected):
                raise ValueError('Review result input hash mismatch')
    by_family = {f['family_id']: f for f in families}
    for row in blind_rows:
        if row['status']=='completed':
            job = row['job']; family = by_family[job['family_id']]
            variant = (family['variants'][job['variant_index']] if job['variant_index'] is not None
                       else {'materials': [], 'gold': CORE.solve(family['query'], [])})
            expected = CORE.project(variant, family['question'], SCHEMAS['blind-solver'])
            if row.get('input_hash') != digest(expected):
                raise ValueError('Blind result input hash mismatch')


def package(batch, reviews, blind, analysis, out):
    batch, reviews, blind, analysis = [checked_path(p) for p in (batch, reviews, blind, analysis)]
    out = checked_path(out, exists=False)
    relative_out = out.relative_to(ROOT)
    if not relative_out.parts or not (ROOT/relative_out.parts[0]).is_dir():
        raise ValueError('Output may not create an unapproved first-level directory')
    for source in (batch, reviews, blind, analysis):
        if out.is_relative_to(source) or source.is_relative_to(out):
            raise ValueError('Output must be disjoint from all source directories')
    cases, refs = verify_reference_gate(batch)
    families = read(batch/'families.frozen.json')
    binding = verify_family_binding(batch, cases, refs, families)
    review_plan, blind_plan = make_jobs(cases), blind_jobs(families)
    review_rows = complete_rows(reviews, review_plan)
    blind_rows = complete_rows(blind, blind_plan)
    review_contract = read(reviews/'experiment.frozen.json')
    if (review_contract.get('cases_sha256') != digest(cases) or
            review_contract.get('jobs_sha256') != digest(review_plan)):
        raise ValueError('Review runtime experiment bindings differ from the approved batch')
    if read(blind/'families.frozen.json') != families:
        raise ValueError('Blind runtime family snapshot differs from approved families')
    validate_input_hashes(cases, families, review_rows, blind_rows)
    analysis_manifest = read(analysis/'analysis-manifest.json')
    expected_analysis = {'cases_sha256': digest(cases), 'references_sha256': digest(refs),
                         'families_sha256': digest(families),
                         'review_results_sha256': digest(review_rows),
                         'blind_results_sha256': digest(blind_rows)}
    if any(analysis_manifest.get(k) != v for k, v in expected_analysis.items()):
        raise ValueError('Analysis input bindings differ from actual frozen inputs/results')
    if analysis_manifest.get('formal_release') is not False:
        raise ValueError('Analysis must keep formal release disabled')
    # Require both reports, even when every model output was a recorded failure.
    read(analysis/'review-summary.json'); read(analysis/'blind-summary.json')
    runtime_files = []
    for kind, folder in [('reviews', reviews), ('blind', blind)]:
        for pattern in ('*.request.json', '*.response.json', '*.technical-failure.json', '*.format-error.json'):
            for path in sorted(folder.rglob(pattern)):
                runtime_files.append({'role': kind, **file_record(path)})
    inputs = []
    copies = []
    sources = {'batch': batch, 'reviews': reviews, 'blind': blind, 'analysis': analysis}
    for group, folder in sources.items():
        candidates = list(sorted(folder.glob('*.json')))
        if group in ('reviews', 'blind'):
            candidates += list(sorted((folder/'results').glob('*.json')))
        for source in candidates:
            # Runtime requests and responses are represented only by the external index.
            if source.name.endswith(('.request.json', '.response.json')):
                continue
            relative = source.relative_to(folder)
            target = out/group/relative
            inputs.append({'group': group, **file_record(source)})
            save_new_or_same(target, read(source))
            copies.append({'source': source.relative_to(ROOT).as_posix(),
                           'delivery_path': target.relative_to(out).as_posix(),
                           'source_sha256': file_record(source)['sha256'],
                           'delivery_sha256': file_record(target)['sha256']})
    save_new_or_same(out/'runtime-file-index.json', runtime_files)
    chain = {'version': 'delivery-hash-chain-v0.2',
             'source_files': inputs, 'frozen_copies': copies,
             'runtime_file_index_sha256': file_record(out/'runtime-file-index.json')['sha256'],
             'analysis_bindings': expected_analysis,
             'family_binding_sha256': digest(binding)}
    save_new_or_same(out/'file-hash-chain.json', chain)
    counts = lambda rows: dict(collections.Counter(row['status'] for row in rows))
    manifest = {'version': 'deletion-review-development-delivery-v0.2',
                'status': 'machine_complete_pending_independent_post_audit',
                'formal_release': False, 'independent_post_audit': 'not_asserted_by_packager',
                'reference_review': 'verified_independent_gpt_pre_audit',
                'source_locations': {k: p.relative_to(ROOT).as_posix() for k, p in sources.items()},
                'cases': len(cases), 'source_families': len(families),
                'source_members': sum(len(f['variants']) for f in families),
                'review_jobs': len(review_plan), 'blind_jobs': len(blind_plan),
                'review_dispositions': counts(review_rows), 'blind_dispositions': counts(blind_rows),
                'bindings': expected_analysis,
                'hash_chain_sha256': file_record(out/'file-hash-chain.json')['sha256'],
                'runtime_file_index_sha256': file_record(out/'runtime-file-index.json')['sha256'],
                'runtime_requests_and_responses_copied': False,
                'post_review_policy': 'Independent reviewer may add a separately versioned post_review file; this immutable manifest does not sign or imply post-audit approval.'}
    save_new_or_same(out/'delivery-manifest.json', manifest)
    return manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('batch', 'reviews', 'blind', 'analysis', 'out'):
        parser.add_argument('--'+name, type=Path, required=True)
    args = parser.parse_args()
    result = package(args.batch, args.reviews, args.blind, args.analysis, args.out)
    print({k: result[k] for k in ('status','cases','review_jobs','blind_jobs','formal_release')})


if __name__=='__main__':
    main()
