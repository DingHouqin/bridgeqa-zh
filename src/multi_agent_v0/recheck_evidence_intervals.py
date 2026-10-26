"""Correct the structural span-overlap bug without re-running any model.

Original responses and original scores are preserved as an explicit version.
"""
import argparse
import json
import shutil
from core import check_solver
from runner import ROOT, load


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--run-id', default='milestone-007')
    args = parser.parse_args()
    out = ROOT / 'workspace/harness-prototype/runs' / args.run_id
    prior = out / 'protocol-v2-before-overlap-fix.json'
    if not prior.exists():
        shutil.copyfile(out / 'solver-results.json', prior)
    family = load(out / 'family.internal.json')
    inputs = load(out / 'model-inputs.json')
    origin = load(out / 'facts.gpt-adjudicated.json')
    results = load(prior)
    diffs = []
    for row, payload, result in zip(family['variants'], inputs, results):
        before = result['checks']
        after = check_solver(result['answer'], payload, row, origin, family['query'])
        if before != after:
            diffs.append({'condition': row['condition'], 'before': before, 'after': after})
        result['checks'] = after
    (out / 'solver-results.json').write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding='utf-8')
    (out / 'solver-results.jsonl').write_text(''.join(json.dumps(r, ensure_ascii=False) + '\n' for r in results), encoding='utf-8')
    completion = load(out / 'completion.json')
    completion['structural_score_version'] = 'interval-overlap-v0.2'
    completion['structured_solver_successes'] = sum(r['checks']['strict_structural_success'] for r in results)
    (out / 'completion.json').write_text(json.dumps(completion, ensure_ascii=False, indent=2), encoding='utf-8')
    record = {'bug': 'Quoted evidence and reference both locate in the same context and overlap, but neither contains the other; the old containment shortcut falsely rejected this.',
              'fix': 'Locate all exact source intervals and test nonempty interval intersection; unrelated quotes still fail.',
              'model_calls': 0, 'response_answers_and_evidence_changed': False, 'score_version': 'interval-overlap-v0.2', 'diffs': diffs}
    (out / 'evidence-overlap-correction.json').write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({'corrected_cases':len(diffs),'strict_success':completion['structured_solver_successes'],'model_calls':0}))


if __name__ == '__main__':
    main()
