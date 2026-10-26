"""Separate explicit correction, uncertainty, protocol validity and model reviews.

Definitions: [v7 protocol](../../QA_Generator/specs/evidence-contracts-v0.7.md).
"""
import argparse
import collections
import hashlib
import json

import contracts_v7_experiment as E


def summarize(final=False):
    objects = E.verify()
    results = {p.stem: E.read(p) for p in (E.RUNTIME / 'results').glob('*.json')}
    if set(results) - set(objects['jobs']):
        raise ValueError('Unknown result job')
    if final and set(results) != set(objects['jobs']):
        raise ValueError('Final analysis requires every terminal job')
    groups, records = {}, []
    for jid in objects['jobs']:
        contract = objects['request-contracts'][jid]
        job = contract['job']
        result = results.get(jid)
        ref = objects['references'][job['case_id']]
        key = '|'.join((job['kind'], contract['split'], job['arm']))
        count = groups.setdefault(key, collections.Counter())
        count['planned'] += 1
        status = result['status'] if result else 'not_run'
        count[status] += 1
        row = {'job_id': jid, 'job': job, 'split': contract['split'], 'status': status}
        eligible = ref.get('analysis_eligible', True) and not ref.get('disputed', False)
        row['analysis_eligible'] = eligible
        if job['kind'] == 'scoring':
            if eligible:
                count['planned_valid' if ref['expected_valid'] else 'planned_invalid'] += 1
            else:
                count['reference_disputed_excluded'] += 1
            if status == 'completed':
                merged = result['merged']
                verdict = merged['verdict']
                row.update(verdict=verdict, raw_model_verdict=merged.get('raw_model_verdict'),
                    reference_disagreement=merged['private_reference_disagreement'])
                count['verdict_' + verdict] += 1
                if eligible:
                    valid = ref['expected_valid']
                    count['correct_accept'] += valid and verdict == 'supported'
                    count['correct_reject'] += not valid and verdict == 'incorrect'
                    count['false_block'] += valid and verdict == 'incorrect'
                    count['false_accept'] += not valid and verdict == 'supported'
                    count['undetermined'] += verdict == 'needs_adjudication'
                    raw = merged.get('raw_model_verdict')
                    count['raw_false_block'] += valid and raw == 'incorrect'
                    count['raw_false_accept'] += not valid and raw == 'supported'
                    count['raw_undetermined'] += raw == 'needs_adjudication'
        elif status == 'completed':
            review = result['group_validation']
            row.update(structural_protocol_valid=True, model_group_review_outcome=review['outcome'],
                       independent_semantic_success=None)
            count['model_outcome_' + review['outcome']] += 1
        records.append(row)
    requests = sorted(E.RUNTIME.glob('worker-*/calls/*.input.json'))
    response_paths = sorted(E.RUNTIME.glob('worker-*/calls/*.attempt-*.response.json'))
    sessions = [E.read(p)['session_id'] for p in response_paths]
    if len(set(sessions)) != len(sessions):
        raise ValueError('Duplicate returned sessions')
    request_counts = collections.Counter()
    for path in requests:
        request_counts[path.name.split('-v7-', 1)[0]] += 1
    summary = {'logical_jobs_planned': len(objects['jobs']), 'recorded_jobs': len(results),
        'planned_base_stage_calls': E.read(E.BATCH / 'manifest.json')['planned_base_stage_calls'],
        'persisted_stage_requests': len(requests), 'actual_response_sessions': len(response_paths),
        'unique_returned_sessions': len(set(sessions)), 'request_stage_counts': dict(request_counts),
        'groups': {key: dict(value) for key, value in groups.items()},
        'formal_release': False,
        'limits': ['Unknown and protocol/technical failure are never counted corrected.',
                   'Model group reviews and structural validity do not establish support coverage.',
                   'Concurrent scoring arms change the whole contract, not a single factor.',
                   'EH-S09 stays outside determinate denominators; earlier new cases are disclosed regressions.']}
    if final:
        E.save(E.BATCH / 'analysis/summary.json', summary)
        E.save(E.BATCH / 'analysis/cases.json', records)
        E.save(E.BATCH / 'analysis/evidence-files.json', {
            'requests': {p.relative_to(E.ROOT).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest() for p in requests},
            'responses': {p.relative_to(E.ROOT).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest() for p in response_paths}})
    return summary


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--final', action='store_true')
    args = parser.parse_args()
    print(json.dumps(summarize(args.final), ensure_ascii=False))
