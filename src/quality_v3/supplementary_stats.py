"""Disclosed origin and historical false-block subsets, without pooling rounds."""
import argparse
import collections
import json
from pathlib import Path
try:
    from .analyze import read, digest, model_decision, program_decision, write_once
except ImportError:
    from analyze import read, digest, model_decision, program_decision, write_once


def partitions(case, ref):
    cid, kind = case['case_id'], case['kind']
    if kind == 'review':
        if cid.startswith('DEV-HLM-'):
            return ['review/source_historical_20']
        if cid.startswith('DEV-'):
            return ['review/synthetic_historical_4']
        return ['review/synthetic_forward_first_round_' + str(case.get('first_seen_round', 1))]
    if kind == 'inventory':
        return ['inventory/real_source' if cid.startswith('INVENTORY-') else 'inventory/synthetic']
    if not cid.startswith('SCORE-DEV-'):
        return ['scoring/synthetic_forward_first_round_' + str(case.get('first_seen_round', 1))]
    label = 'scoring/historical_no_material' if not case['payload']['contexts'] else 'scoring/historical_source_member'
    legacy = case['structural']['legacy'].get('strict_structural_success') is True
    if ref['expected_valid'] is True:
        return [label, 'scoring/historical_valid_legacy_accepted' if legacy else 'scoring/historical_valid_legacy_false_block']
    return [label, 'scoring/historical_semantically_invalid']


def build(batch, runtime, out):
    cases = read(batch/'cases.frozen.json')
    refs = read(batch/'references.frozen.json')
    rows = {digest(r['job']): r for r in map(read, sorted((runtime/'results').glob('*.json')))}
    counts, identities = collections.defaultdict(collections.Counter), collections.defaultdict(set)
    for case in cases:
        for arm in ('generic', 'skills'):
            for label in partitions(case, refs[case['case_id']]):
                key = label+'/'+arm
                identities[key].add(case['case_id'])
                for repeat in range(1, 4) if case['kind'] == 'review' else (1,):
                    job = {'case_id':case['case_id'], 'kind':case['kind'], 'arm':arm, 'repeat':repeat}
                    row = rows.get(digest(job), {'status':'not_run'})
                    c = counts[key]
                    c['scheduled'] += 1
                    c[row['status']] += 1
                    valid = refs[case['case_id']].get('expected_valid')
                    if case['kind'] == 'inventory':
                        continue
                    c['valid_trials' if valid else 'invalid_trials'] += 1
                    if row['status'] != 'completed':
                        continue
                    raw = model_decision(case['kind'], row['answer'])
                    program, _ = program_decision(case['kind'], case, row)
                    for prefix, decision in [('raw',raw),('program',program)]:
                        if decision is None:
                            c[prefix+'_undecided'] += 1
                        else:
                            c[prefix+('_accept' if decision else '_reject')] += 1
                            c[prefix+('_correct' if decision == valid else '_false_block' if valid else '_unsafe_accept')] += 1
    result = {'version':'quality-origin-subsets-v1', 'groups':{
        key:{'unique_cases':len(identities[key]),'counts':dict(counts[key])} for key in sorted(counts)},
        'limits':['Origin/subset groups overlap; do not sum them as independent samples.',
            'Three review trials per case are repeated measurements.',
            'The inventory split name exploratory_source in frozen trials includes explicitly fictional probes; these are separated here.',
            'No cross-round pooling, new gold labels, or inventory accuracy is asserted.'], 'formal_release':False}
    write_once(out, result)
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for flag in ('batch','runtime','out'):
        parser.add_argument('--'+flag,type=Path,required=True)
    args = parser.parse_args()
    result = build(args.batch,args.runtime,args.out)
    print(json.dumps({'groups':len(result['groups']),'formal_release':False}))
