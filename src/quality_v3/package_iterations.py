"""Package completed, independently audited iterations without editing old runs.

Raw request/event files remain at their indexed workspace paths. Compact model
results and file-byte hashes are copied into a new immutable delivery directory.
The program does not declare skills mature or authorize automatic release.
"""
from __future__ import annotations
import argparse
import collections
import hashlib
import json
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[2]
ROUNDS = [
    ('run-002', 'quality-v3-20261022-r2', 'round-1-review.json'),
    ('round-2', 'quality-v3-round-2', 'round-2-review.json'),
    ('round-3', 'quality-v3-round-3', 'round-3-review.json'),
]


def read(path):
    return json.loads(path.read_text(encoding='utf-8'))


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def save(path, value):
    text = json.dumps(value, ensure_ascii=False, indent=2) + '\n'
    if re.search(r'sk-[A-Za-z0-9]{24,}', text):
        raise ValueError('Potential credential in delivery; no content printed')
    if path.exists() and path.read_text(encoding='utf-8') != text:
        raise ValueError('Refusing to overwrite delivery: ' + str(path))
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding='utf-8')


def main(destination, report):
    destination, report = destination.resolve(), report.resolve()
    if not destination.is_relative_to(ROOT/'artifacts/quality-v3'):
        raise ValueError('Delivery destination outside quality artifacts')
    audit_path = ROOT/'artifacts/quality-v3/final-report-review.json'
    report_audit = read(audit_path)
    if (report_audit.get('status') != 'approved'
            or report_audit.get('reviewer_kind') != 'independent_gpt_subagent'
            or report_audit.get('report_sha256') != sha(report)):
        raise ValueError('Final report requires independent approval of exact bytes')
    validation_records = []
    for name in ('program-validation-three-rounds.json', 'skill-validation-three-rounds.json',
                 'independent-origin-subsets-review.json', 'independent-defect-localization-summary.json'):
        path = ROOT/'workspace/quality-v3'/name
        save(destination/'checks'/name, read(path))
        validation_records.append({'source':path.relative_to(ROOT).as_posix(), 'sha256':sha(path)})
    delivered = []
    for number, (batch_name, runtime_name, audit_name) in enumerate(ROUNDS, 1):
        batch = ROOT/'artifacts/quality-v3'/batch_name
        runtime = ROOT/'workspace/harness-prototype/runs'/runtime_name
        summary, integrity = (read(batch/'analysis'/name) for name in ('summary.json', 'integrity.json'))
        post = read(batch/'post-audit'/audit_name)
        if (post.get('reviewer_kind') != 'independent_gpt_subagent'
                or not post.get('status', '').startswith('approved')):
            raise ValueError('Missing independent post-audit for round ' + str(number))
        if not integrity['all_observed_checks_pass'] or integrity['counts']['not_run']:
            raise ValueError('Incomplete or invalid actual request chain')
        rows = [read(p) for p in sorted((runtime/'results').glob('*.json'))]
        if len(rows) != summary['scheduled_jobs'] or len(rows) != summary['result_rows']:
            raise ValueError('Incomplete round results')
        expected = {json.dumps(j, sort_keys=True) for j in read(batch/'jobs.frozen.json')}
        observed = [json.dumps(row['job'], sort_keys=True) for row in rows]
        if len(set(observed)) != len(observed) or set(observed) != expected:
            raise ValueError('Duplicate, missing or unexpected result identity')
        out = destination/f'round-{number}'
        save(out/'results.json', rows)
        save(out/'summary.json', summary)
        save(out/'integrity.json', integrity)
        for name in ('cases.frozen.json', 'references.frozen.json', 'jobs.frozen.json',
                     'protocol.frozen.json', 'manifest.json', 'reference_review.json'):
            save(out/name, read(batch/name))
        for path in sorted((batch/'post-audit').glob('*.json')):
            save(out/'post-audit'/path.name, read(path))
        sources = list(batch.rglob('*.json')) + list(runtime.glob('worker-*/calls/*'))
        sources += list((runtime/'results').glob('*.json'))
        sources = sorted({p for p in sources if p.is_file()})
        index = [{'path': p.relative_to(ROOT).as_posix(), 'bytes': p.stat().st_size,
                  'sha256': sha(p)} for p in sources]
        save(out/'source-files.json', index)
        delivered.append({'round': number, 'batch': batch.relative_to(ROOT).as_posix(),
            'runtime': runtime.relative_to(ROOT).as_posix(), 'logical_calls': len(rows),
            'status_counts': dict(collections.Counter(r['status'] for r in rows)),
            'actual_session_counts': integrity['counts'], 'indexed_files': len(index),
            'source_files_sha256': sha(out/'source-files.json'),
            'results_sha256': sha(out/'results.json'),
            'independent_post_audit': (batch/'post-audit'/audit_name).relative_to(ROOT).as_posix(),
            'independent_post_audit_sha256': sha(batch/'post-audit'/audit_name)})
    save(destination/'manifest.json', {'version': 'quality-v3-three-iteration-delivery-v1',
        'rounds': delivered, 'logical_calls': sum(r['logical_calls'] for r in delivered),
        'report': report.relative_to(ROOT).as_posix(), 'report_sha256': sha(report),
        'report_review': audit_path.relative_to(ROOT).as_posix(), 'report_review_sha256': sha(audit_path),
        'validation_records':validation_records,
        'reference_state': 'GPT独立审核', 'human_review_performed': False,
        'skills_maturity': 'development_candidates_after_three_iterations', 'formal_release': False})
    print(json.dumps({'rounds': 3, 'logical_calls': sum(r['logical_calls'] for r in delivered),
                      'formal_release': False}))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', required=True, type=Path)
    parser.add_argument('--report', required=True, type=Path)
    args = parser.parse_args()
    main(args.out, args.report)
