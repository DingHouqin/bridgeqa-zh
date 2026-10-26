"""Freeze the explicit quote contract and re-run every condition once.

Earlier behavior is archived, never selected away; facts/questions are unchanged.
See the development delivery report linked from README.md.
"""
import argparse
import getpass
import json
import os
import shutil

from contracts import SCHEMAS
from core import check_solver, digest, project, solve, supervisor_gate
from runner import ROOT, CODE, Pipeline, load


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--run-id', default='milestone-007')
    args = parser.parse_args()
    out = ROOT / 'workspace/harness-prototype/runs' / args.run_id
    family = load(out / 'family.internal.json')
    origin = load(out / 'facts.gpt-adjudicated.json')
    previous_completion = load(out / 'completion.json')
    prior = out / 'protocol-v1'
    prior.mkdir(exist_ok=True)
    for name in ('model-inputs.json', 'gold.json', 'solver-results.json', 'no-material-diagnostic.json', 'completion.json'):
        if not (prior / name).exists():
            shutil.copyfile(out / name, prior / name)
    inputs = [project(row, family['question'], SCHEMAS['blind-solver']) for row in family['variants']]
    snapshot = {'protocol_version': 'evidence-quotes-v0.2', 'purpose': 'Make literal quote matching explicit before re-running all conditions',
                'question_and_materials_changed': False, 'gold_changed': False, 'all_conditions_rerun_once': True,
                'inputs': inputs, 'input_hashes': [digest(p) for p in inputs],
                'blind_skill_hash': digest((CODE / 'skills/bridgeqa-blind-solver/SKILL.md').read_text(encoding='utf-8'))}
    path = out / 'protocol-v2.frozen.json'
    if path.exists():
        assert load(path) == snapshot
    else:
        path.write_text(json.dumps(snapshot, ensure_ascii=False, indent=2), encoding='utf-8')
    key = os.environ.get('DEEPSEEK_API_KEY') or getpass.getpass('DeepSeek runtime credential (hidden): ').strip()
    pipeline = Pipeline(key, args.run_id)
    try:
        results = []
        golds = []
        for i, (row, payload) in enumerate(zip(family['variants'], inputs), 1):
            answer = pipeline.role(f'blind-v2-item-{i}', 'blind-solver', payload)
            results.append({'item_id': payload['item_id'], 'condition': row['condition'], 'answer': answer,
                            'checks': check_solver(answer, payload, row, origin, family['query'])})
            golds.append({'item_id': payload['item_id'], 'condition': row['condition'], 'gold': row['gold'], 'group': family['split_group']})
        row = {'materials': [], 'gold': solve(family['query'], [])}
        payload = project(row, family['question'], SCHEMAS['blind-solver'])
        answer = pipeline.role('blind-v2-no-material-diagnostic', 'blind-solver', payload)
        pipeline.save('no-material-diagnostic.json', {'input': payload, 'answer': answer,
            'checks': check_solver(answer, payload, row, origin, family['query']), 'separate_from_four_member_family': True})
        required = ['final_text_no_shortcut', 'all_proofs_cut', 'family_invariants', 'solver_comparison', 'isolation']
        review = pipeline.role('final-family-review-v2', 'supervisor', {'stage': 'final-protocol-v2',
            'materials': pipeline.materials, 'family': family, 'reviewed_facts': origin, 'model_inputs': inputs,
            'solver_results': results, 'required_checks': required,
            'instruction': '来源、问题、四变体和gold不变；输出协议现在明确要求逐字连续引用，已冻结后统一重跑全部条件。检查实际答案及证据，模型错误不决定题目保留。原v1结果保留为协议调试，不替换成正式测试。所有布尔字段须与说明一致。',
            'isolation_contract': '四个新会话，solver独立home；关闭全部图、Shell、文件、目录工具；输入无gold、配方或其他答案。'})
        if not supervisor_gate(review, required):
            raise RuntimeError('Frozen quote protocol final review needs adjudication; no further sampling')
        pipeline.save('model-inputs.json', inputs)
        pipeline.save('gold.json', golds)
        pipeline.save('solver-results.json', results)
        for name, rows in [('model-inputs', inputs), ('gold', golds), ('solver-results', results)]:
            (out / (name + '.jsonl')).write_text(''.join(json.dumps(r, ensure_ascii=False) + '\n' for r in rows), encoding='utf-8')
        previous_completion['answer_protocol_version'] = 'evidence-quotes-v0.2'
        previous_completion['structured_solver_successes'] = sum(r['checks']['strict_structural_success'] for r in results)
        previous_completion['protocol_v2_calls'] = pipeline.calls
        previous_completion['final_review_stage'] = 'final-family-review-v2'
        pipeline.save('completion.json', previous_completion)
        print(json.dumps({'protocol': 'evidence-quotes-v0.2', 'answer_status_correct': sum(r['checks']['answer_and_status_correct'] for r in results),
                          'strict_success': sum(r['checks']['strict_structural_success'] for r in results), 'further_sampling': False}, ensure_ascii=False), flush=True)
    finally:
        pipeline.close()


if __name__ == '__main__':
    main()
