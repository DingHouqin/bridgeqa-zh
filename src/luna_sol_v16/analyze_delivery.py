"""Mechanical final-grade delivery, without semantic regrading; see [usage](README.md).

Only Root's independently approved grade map supplies labels/reviewer names.
Explicit frozen run plans define the denominator. Case counts are never trials
of the same task: every pass@5/pass^5 delivery field remains null.
"""
from __future__ import annotations
import argparse
import collections
import copy
import hashlib
import json
import os
from pathlib import Path
import sys
from fractions import Fraction

ROOT = Path(__file__).resolve().parents[2]
WORK = ROOT / 'workspace/luna-sol-v16'
sys.path.insert(0, str(ROOT / 'evaluation/pass_metrics_v15'))
import scorer as S

DEFAULT_PHASES = ('current_r2', 'novel_r1', 'revised_r1')
MODELS = ('gpt-6-luna', 'gpt-6.1-sol')
DIMENSIONS = S.DIMENSIONS
LABELS = {'P': 'pass', 'F': 'fail', 'U': 'needs_review',
          'pass': 'pass', 'fail': 'fail', 'needs_review': 'needs_review'}
SHORT = {'pass': 'P', 'fail': 'F', 'needs_review': 'U'}
GROUP_AXES = ('phase', 'model', 'partition', 'hops', 'domain', 'condition', 'family_id')
DESCRIPTION = ('Fixed development cohort, one first completion per case/model. '
               'Comparisons are descriptive, not iid significance tests or held-out capability estimates. '
               'Identification bounds are not confidence intervals. Global no-shortcut remains not_proven.')


def require(condition, message):
    S.require(condition, message)


def file_ref(path, root=ROOT):
    path = Path(path).resolve()
    return {'path': path.relative_to(root.resolve()).as_posix(), 'sha256': S.file_sha(path)}


def metric_counts(verdicts):
    """A fixed case denominator; do not turn >=5 distinct cases into n=5 trials."""
    m = S.metric(verdicts, 1, 'any')
    return {'planned_slots': len(verdicts), 'P': verdicts.count('pass'),
            'F': verdicts.count('fail'), 'U': verdicts.count('needs_review'),
            'pass@1': m, 'pass@5': None, 'pass^5': None,
            'higher_order_unavailable': 'Each case/model has n=1; pooling cases cannot create five same-task trials.'}


def tri_metrics(rows):
    return {d: metric_counts([r['verdicts'][d] for r in rows]) for d in DIMENSIONS}


def check_grade(grade, slot):
    """Validate declared provenance, never invent or change a semantic verdict."""
    required = {'phase', 'model', 'case_id', 'trial_id', 'response_sha256',
                'verdicts', 'rationale', 'reviewers', 'approval'}
    require(isinstance(grade, dict) and required <= set(grade), 'Incomplete grade-map row')
    for key in ('phase', 'model', 'case_id', 'trial_id'):
        require(grade[key] == slot[key], 'Grade identity differs from frozen slot: ' + key)
    require(grade['response_sha256'] == slot['response_sha256'], 'Stale/cross-slot response SHA in grade')
    values = grade['verdicts']
    require(isinstance(values, dict) and set(values) == set(DIMENSIONS), 'Exactly three verdict dimensions required')
    require(all(isinstance(v, str) and v in LABELS for v in values.values()), 'Unknown verdict label')
    verdicts = {d: LABELS[values[d]] for d in DIMENSIONS}
    require(isinstance(grade['rationale'], str) and bool(grade['rationale'].strip()), 'Review rationale missing')
    reviewers = grade['reviewers']; approval = grade['approval']
    require(isinstance(reviewers, list) and all(isinstance(v, str) and v for v in reviewers)
            and len(reviewers) == len(set(reviewers)) and len(reviewers) >= 2, 'Distinct actual reviewers required')
    require(set(reviewers) <= set(slot['trusted_reviewers']), 'Reviewer is outside frozen registry')
    require(isinstance(approval, dict) and approval.get('status') == 'accepted'
            and approval.get('approved_by') == slot['approver']
            and approval.get('approved_by') in reviewers
            and approval.get('independent_review') is True, 'Explicit independent Root approval required')
    # These dependencies are frozen in the plan rubric, not a new semantic test.
    require(verdicts['logical_proof'] != 'pass' or verdicts['answer'] == 'pass', 'Logical-proof P requires answer P')
    require(verdicts['output_contract'] != 'pass' or all(verdicts[d] == 'pass' for d in ('answer', 'logical_proof')),
            'Frozen full-contract P requires answer/proof P')
    require(slot['execution_status'] == 'completed' or set(verdicts.values()) == {'needs_review'},
            'Noncompleted slot cannot acquire a semantic P/F outcome')
    return verdicts


def run_plan_specs(values=None, root=ROOT):
    """No directory glob: obsolete runs and not-yet-approved phases stay out."""
    if not values:
        return [(phase, Path(root) / 'workspace/luna-sol-v16/runs' / (phase + '-' + model) / 'plan.json')
                for phase in DEFAULT_PHASES for model in MODELS]
    specs = []
    for value in values:
        if '=' in value:
            phase, path = value.split('=', 1)
            require(bool(phase.strip()), 'Explicit phase alias is empty')
        else:
            path = value; phase = S.read(Path(path))['label']
        specs.append((phase, Path(path)))
    return specs


def load_grid(specs=None, root=ROOT):
    """Read metadata and validate retained runtime evidence, not answer semantics."""
    root = Path(root).resolve(); grid = []; bindings = []; sessions = set()
    seen_runs = set()
    for phase, pp in (specs if specs is not None else run_plan_specs(root=root)):
            pp = Path(pp).resolve(); require(pp.is_relative_to(root), 'Plan escapes workspace')
            folder = pp.parent; plan = S.read(pp); planned = S.validate_plan(plan)
            model = plan['configuration']['model']; size = len(planned)
            require(model in MODELS, 'Unsupported requested model alias')
            require((phase, model) not in seen_runs, 'Duplicate phase/model run')
            seen_runs.add((phase, model))
            require(size > 0 and all(len(c['slots']) == 1 for c in plan['cases']), 'Only n=1 per case is supported')
            require(plan['configuration']['runtime_contract'].get('effort') == 'medium', 'Unexpected frozen effort')
            dataset, _ = S.read_ref(plan['dataset'], root)
            require(isinstance(dataset, list), 'Dataset must be case records')
            meta = {r['id']: r for r in dataset}
            require(len(meta) == len(dataset) and set(meta) == {c['id'] for c in plan['cases']}, 'Dataset/plan cases differ')
            records_path = folder / 'records-initial.json'; records = S.read(records_path)
            require(isinstance(records, list), 'records-initial must be a list')
            observed = {r['trial_id']: r for r in records}
            require(len(observed) == len(records) and set(observed) == set(planned), 'records-initial grid incomplete/extra/duplicated')
            plan_sha = S.file_sha(pp)
            for tid, (case, declared) in planned.items():
                r = observed[tid]; private = meta[case['id']]
                expected = {'case_id': case['id'], 'input_sha256': case['input_sha256'],
                            'configuration_sha256': plan['configuration_sha256'],
                            'rubric_sha256': plan['rubric_sha256'], 'plan_sha256': plan_sha,
                            'initial_attempt': True, 'attempt_ordinal': 0}
                require(all(type(r.get(k)) is type(v) and r.get(k) == v for k, v in expected.items()), 'Record binding differs from frozen plan')
                require(r['request'] == {'path': declared['request_path'], 'sha256': declared['request_sha256']}, 'Unplanned request')
                request, _ = S.read_ref(r['request'], root)
                require(S.digest(private['clean_input']) == private['input_sha256'] == case['input_sha256']
                        and S.digest(request['input']) == case['input_sha256'], 'Dataset/request input SHA differs')
                require(private['family_id'] == case['family_id'] and private['partition'] == case['partition'], 'Case grouping metadata differs')
                require(r.get('stdin') == declared['stdin'], 'Record stdin differs from frozen slot')
                stdin_path = (root / declared['stdin']['path']).resolve()
                require(stdin_path.is_relative_to(root) and S.file_sha(stdin_path) == declared['stdin']['sha256'], 'Frozen stdin bytes changed')
                projection = {k: request[k] for k in ('role', 'skill', 'input', 'output_schema')}
                require(stdin_path.read_bytes() == json.dumps(projection, ensure_ascii=False).encode('utf-8'), 'stdin is not the public projection')
                status = r.get('status'); require(status in {'completed', 'technical_failure'}, 'Unexpected execution status')
                response_sha = None; response_ref = None
                if 'response' in r:
                    require(r['response']['path'] == declared['response_path'], 'Unplanned response path')
                    _, response_path = S.read_ref(r['response'], root)
                    response_sha = S.file_sha(response_path); response_ref = r['response']
                if status == 'completed':
                    bound = S.bind_completion(r, case, plan, root)
                    require(bound['session_id'] not in sessions, 'CLI session reused across slots')
                    sessions.add(bound['session_id'])
                else:
                    require('failure' in r, 'Technical failure evidence missing')
                    S.read_ref(r['failure'], root)
                parent = private.get('parent')
                parent_ref = parent if isinstance(parent, dict) and 'id' in parent and 'input_sha256' in parent else None
                grid.append({'phase': phase, 'run_label': plan['label'], 'model': model, 'case_id': case['id'], 'trial_id': tid,
                             'response_sha256': response_sha, 'response': response_ref,
                             'input_sha256': case['input_sha256'], 'partition': case['partition'],
                             'hops': private.get('hops'), 'domain': private.get('domain'),
                             'hop_metadata': 'declared_structural_depth' if private.get('hops') is not None else 'not_declared',
                             'condition': private.get('condition'), 'family_id': case['family_id'],
                             'parent': parent_ref, 'execution_status': status,
                             'hop_certified': private.get('hop_certified', False),
                             'global_no_shortcut_status': private.get('global_no_shortcut_status', 'not_proven'),
                             'trusted_reviewers': plan['rubric']['trusted_reviewers'], 'approver': plan['rubric']['approver'],
                             'plan_sha256': plan_sha, 'records_sha256': S.file_sha(records_path)})
            bindings.append({'phase': phase, 'run_label': plan['label'], 'model': model, 'plan': file_ref(pp, root),
                             'records': file_ref(records_path, root), 'dataset': plan['dataset'], 'slots': size})
    require(len({r['trial_id'] for r in grid}) == len(grid), 'Duplicate trial across selected plans')
    require(len(grid) == sum(b['slots'] for b in bindings), 'Fixed denominator differs from selected run plans')
    for model in MODELS:
        counts = collections.Counter(r['partition'] for r in grid if r['run_label'] == 'current_r2' and r['model'] == model)
        if counts:
            require(counts == {'primary': 142, 'node': 48, 'control': 12}, 'Current primary/node/control denominators changed')
    require(all(r[a] is not None for r in grid for a in GROUP_AXES if a != 'hops'), 'Grouping metadata missing')
    return grid, bindings


def attach_grades(grid, payload):
    grades = payload['records'] if isinstance(payload, dict) and 'records' in payload else payload
    require(isinstance(grades, list), 'Grade map must be a list or an object with records')
    lookup = {r['trial_id']: r for r in grid}; supplied = {}
    for grade in grades:
        require(isinstance(grade, dict) and isinstance(grade.get('trial_id'), str), 'Grade trial ID missing')
        tid = grade['trial_id']; require(tid in lookup and tid not in supplied, 'Extra/duplicate grade trial')
        check_grade(grade, lookup[tid]); supplied[tid] = grade
    out = []
    for frozen in grid:
        row = copy.deepcopy(frozen); grade = supplied.get(row['trial_id'])
        row['verdicts'] = check_grade(grade, row) if grade else {d: 'needs_review' for d in DIMENSIONS}
        row['grade'] = grade  # Retain actual rationale/reviewer/approval verbatim.
        row['grade_source'] = 'approved_grade_map' if grade else 'no_approved_grade_map_row'
        out.append(row)
    return out


def group_rows(rows, axes):
    buckets = collections.defaultdict(list)
    for row in rows: buckets[tuple(row[a] for a in axes)].append(row)
    return [{**dict(zip(axes, key)), 'metrics': tri_metrics(rs)}
            for key, rs in sorted(buckets.items(), key=lambda kv: S.canonical(kv[0]))]


def comparison(left, right, kind):
    return {'kind': kind, 'left': {k: left[k] for k in ('phase', 'model', 'case_id', 'trial_id', 'response_sha256', 'input_sha256')},
            'right': {k: right[k] for k in ('phase', 'model', 'case_id', 'trial_id', 'response_sha256', 'input_sha256')},
            'transitions': {d: SHORT[left['verdicts'][d]] + '->' + SHORT[right['verdicts'][d]] for d in DIMENSIONS}}


def comparisons(rows):
    paired = []; bases = []; parents = []; unavailable = []
    by_case = collections.defaultdict(dict)
    for r in rows: by_case[r['phase'], r['case_id']][r['model']] = r
    for key, models in sorted(by_case.items()):
        require(set(models) == set(MODELS), 'Model pair missing a planned slot')
        a, b = [models[m] for m in MODELS]
        require(a['input_sha256'] == b['input_sha256'], 'Model-pair inputs differ')
        paired.append(comparison(a, b, 'same_input_model_pair'))
    families = collections.defaultdict(list)
    for r in rows: families[tuple(r[k] for k in ('phase', 'model', 'partition', 'family_id', 'hops'))].append(r)
    for _, members in sorted(families.items(), key=lambda kv: S.canonical(kv[0])):
        base = [r for r in members if r['condition'] in {'base', 'base3', 'base4'}]
        if len(base) != 1:
            if any(not r['run_label'].startswith('revised') for r in members):
                unavailable.append({'kind': 'base_condition', 'case_ids': [r['case_id'] for r in members], 'reason': 'No unique same-phase/partition/family/hops base'})
            continue
        for r in members:
            if r is not base[0]: bases.append(comparison(base[0], r, 'base_to_condition'))
    current = {(r['model'], r['case_id']): r for r in rows if r['run_label'] == 'current_r2'}
    for r in rows:
        if not r['run_label'].startswith('revised'): continue
        parent = r['parent']; require(parent is not None, 'Revision parent mapping missing')
        source = current.get((r['model'], parent['id']))
        if source is None:
            unavailable.append({'kind': 'revision_parent', 'phase': r['phase'], 'model': r['model'], 'case_id': r['case_id'],
                                'parent': parent, 'reason': ('Parent excluded from current202; no observed baseline may be invented'
                                                           if current else 'Current baseline run not selected; no observed baseline may be invented')})
        else:
            require(source['input_sha256'] == parent['input_sha256'], 'Revision parent input SHA differs from observed current case')
            parents.append(comparison(source, r, 'current_parent_to_revision'))
    def summarize(pairs):
        return {'pairs': len(pairs), 'transitions': {d: dict(sorted(collections.Counter(p['transitions'][d] for p in pairs).items())) for d in DIMENSIONS}, 'records': pairs}
    return {'scope': DESCRIPTION, 'same_input_model_pair': summarize(paired),
            'base_to_condition': summarize(bases), 'revision_parent': summarize(parents), 'unavailable': unavailable}


def outputs(rows, bindings, grade_ref):
    errors = []
    for r in rows:
        if all(v == 'pass' for v in r['verdicts'].values()): continue
        errors.append({k: r[k] for k in GROUP_AXES + ('case_id', 'trial_id', 'input_sha256', 'response_sha256',
                                                    'response', 'execution_status', 'hop_certified',
                                                    'global_no_shortcut_status', 'verdicts', 'grade_source', 'grade')})
    summary = {'version': 'luna-sol-v16-final-mechanical-summary-r1', 'scope': DESCRIPTION,
               'label_source': 'Only supplied approved grade-map rows; missing rows remain U, no automated semantic scoring.',
               'planned_all_partitions_slots': len(rows), 'approved_grade_rows': sum(r['grade'] is not None for r in rows),
               'grade_map': grade_ref, 'bindings': bindings,
               'phase_metadata': {phase: {'slots': sum(r['phase'] == phase for r in rows),
                                         'certified_hop_slots': sum(r['phase'] == phase and r['hop_certified'] is True for r in rows),
                                         'scope': 'Separate development phase; no causal difficulty claim across phases.'}
                                  for phase in sorted({r['phase'] for r in rows})},
               'main_task_cohort_policy': 'Current primary142 per model only; node48 and control12 are separate. No pooled202 main-task rate.',
               'hop_grouping_policy': 'Use dataset-declared structural hops; null means not declared (including existing node metadata), never an inferred hop count or certified lower bound.',
               'cohorts': group_rows(rows, ('phase', 'model', 'partition')),
               'by_axis': {a: group_rows(rows, ('phase', 'model', 'partition', a)) for a in ('hops', 'domain', 'condition', 'family_id')},
               'joint_groups': group_rows(rows, GROUP_AXES), 'comparisons': comparisons(rows),
               'semantic_regrading_performed': False, 'reviewer_identities_authenticated_by_script': False,
               'population_significance_test': None, 'global_no_shortcut_status': 'not_proven'}
    return summary, {'version': 'luna-sol-v16-final-error-index-r1', 'scope': DESCRIPTION,
                     'index_policy': 'Include any F or U dimension; absence is not an independent semantic review.',
                     'grade_map': grade_ref, 'records': errors}


def markdown_index(index, out_dir, root=ROOT):
    def escape(s): return str(s).replace('|', '\\|').replace('\n', ' ')
    lines = ['# 三维 F/U 机械索引', '', index['scope'], '',
             '仅转录已批准grade-map的判断与理由；没有复判语义，也不补造审查者。', '',
             '|phase/model/case|A/L/C|原始答卷|批准理由及审查者|', '|---|---|---|---|']
    for r in index['records']:
        ref = r['response']; label = r['phase'] + '/' + r['model'] + '/' + r['case_id']
        link = '无已完成答卷' if ref is None else '[raw](' + Path(os.path.relpath(Path(root) / ref['path'], out_dir)).as_posix() + ')'
        grade = r['grade']; reason = grade['rationale'] if grade else r['grade_source']
        reviewers = ', '.join(grade['reviewers']) if grade else '无已批准审查行'
        lines.append('|' + escape(label) + '|' + '/'.join(SHORT[r['verdicts'][d]] for d in DIMENSIONS) + '|' + link + '|' + escape(reason + '；' + reviewers) + '|')
    return '\n'.join(lines) + '\n'


def self_test():
    """Hand-calculated uncertainty/budget fixtures, with no real artifact reads."""
    tests = 0
    m = metric_counts(['pass', 'pass', 'fail', 'needs_review', 'needs_review'])
    assert (m['planned_slots'], m['P'], m['F'], m['U']) == (5, 2, 1, 2)
    assert m['pass@1']['point_estimate'] is None
    assert m['pass@1']['identification_bounds']['lower'] == S.number(Fraction(2, 5))
    assert m['pass@1']['identification_bounds']['upper'] == S.number(Fraction(4, 5))
    assert m['pass@5'] is None and m['pass^5'] is None; tests += 1
    for v, lo, hi in [('pass', 1, 1), ('fail', 0, 0), ('needs_review', 0, 1)]:
        z = metric_counts([v]); b = z['pass@1']['identification_bounds']
        assert b['lower'] == S.number(Fraction(lo)) and b['upper'] == S.number(Fraction(hi))
        assert z['pass@5'] is z['pass^5'] is None; tests += 1
    five_different_cases = metric_counts(['pass'] * 3 + ['fail'] * 2)
    assert five_different_cases['pass@1']['point_estimate'] == S.number(Fraction(3, 5))
    assert five_different_cases['pass@5'] is None; tests += 1
    under = S.task_metrics(['pass'] * 4)
    assert under['pass@5']['status'] == under['pass^5']['status'] == 'insufficient_planned_trials'
    assert under['pass@5']['point_estimate'] is under['pass^5']['point_estimate'] is None; tests += 1
    five_same_task = S.task_metrics(['pass', 'pass', 'pass', 'fail', 'needs_review'])
    assert five_same_task['pass@5']['point_estimate'] is None
    assert five_same_task['pass@5']['identification_bounds']['lower'] == S.number(Fraction(1))
    assert five_same_task['pass@5']['identification_bounds']['upper'] == S.number(Fraction(1))
    assert five_same_task['pass^5']['identification_bounds']['lower'] == five_same_task['pass^5']['identification_bounds']['upper'] == S.number(Fraction(0)); tests += 1
    slot = {'phase': 'synthetic', 'model': 'synthetic', 'case_id': 'C', 'trial_id': 'T',
            'response_sha256': 'a' * 64, 'trusted_reviewers': ['root', 'reviewer'], 'approver': 'root', 'execution_status': 'completed'}
    grade = {k: slot[k] for k in ('phase', 'model', 'case_id', 'trial_id', 'response_sha256')}
    grade.update(verdicts={d: 'U' for d in DIMENSIONS}, rationale='Synthetic handcomputed fixture only',
                 reviewers=['root', 'reviewer'], approval={'status': 'accepted', 'approved_by': 'root', 'independent_review': True})
    assert set(check_grade(grade, slot).values()) == {'needs_review'}; tests += 1
    for field, value in [('response_sha256', 'b' * 64), ('reviewers', ['root']), ('approval', {'status': 'pending'})]:
        bad = copy.deepcopy(grade); bad[field] = value
        try: check_grade(bad, slot)
        except S.ContractError: tests += 1
        else: raise AssertionError('Bad binding/provenance accepted')
    missing = attach_grades([slot], [])
    assert set(missing[0]['verdicts'].values()) == {'needs_review'}; tests += 1
    synthetic_rows = []
    for partition, hops, label in [('primary', 3, 'pass'), ('node', None, 'needs_review'), ('control', None, 'fail')]:
        synthetic_rows.append({'phase': 'bounds-synthetic', 'model': 'synthetic', 'partition': partition, 'hops': hops,
                               'verdicts': {d: label for d in DIMENSIONS}})
    grouped = group_rows(synthetic_rows, ('phase', 'model', 'partition', 'hops'))
    assert len(grouped) == 3 and sum(g['metrics']['answer']['planned_slots'] for g in grouped) == 3
    assert next(g for g in grouped if g['partition'] == 'node')['hops'] is None; tests += 1
    specs = run_plan_specs(['bounds=not-read-until-approved/plan.json'])
    assert specs == [('bounds', Path('not-read-until-approved/plan.json'))]; tests += 1
    pair_rows = []
    for model in MODELS:
        for phase, run, cid, condition, label, parent in [
                ('current', 'current_r2', 'base-case', 'base', 'pass', None),
                ('current', 'current_r2', 'condition-case', 'compound', 'fail', None),
                ('revised', 'revised_r1', 'revised-case', 'revision', 'needs_review', {'id': 'base-case', 'input_sha256': 'b' * 64}),
                ('bounds', 'bounds_r1', 'bounds-case', 'bounds', 'needs_review', None)]:
            pair_rows.append({'phase': phase, 'run_label': run, 'model': model, 'case_id': cid,
                              'condition': condition, 'family_id': 'synthetic-family', 'hops': 3,
                              'partition': 'primary', 'trial_id': phase + '/' + model + '/' + cid,
                              'input_sha256': 'b' * 64, 'response_sha256': 'c' * 64,
                              'parent': parent, 'verdicts': {d: label for d in DIMENSIONS}})
    paired = comparisons(pair_rows)
    assert paired['same_input_model_pair']['pairs'] == 4
    assert paired['base_to_condition']['pairs'] == 2 and paired['revision_parent']['pairs'] == 2
    assert paired['base_to_condition']['transitions']['answer'] == {'P->F': 2}
    assert paired['revision_parent']['transitions']['answer'] == {'P->U': 2}; tests += 1
    stale = copy.deepcopy(pair_rows); next(r for r in stale if r['phase'] == 'revised')['parent']['input_sha256'] = 'd' * 64
    try: comparisons(stale)
    except S.ContractError: tests += 1
    else: raise AssertionError('Stale parent SHA accepted')
    print(json.dumps({'self_tests_passed': tests, 'real_artifacts_read': 0, 'model_calls': 0,
                      'source_sha256': S.file_sha(__file__)}, ensure_ascii=False))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--self-test', action='store_true')
    parser.add_argument('--grade-map', type=Path)
    parser.add_argument('--out-dir', type=Path)
    parser.add_argument('--run-plan', action='append', metavar='[PHASE=]PLAN',
                        help='Repeat for every selected run; optional explicit phase alias. Without any, use the six existing current/novel/revised plans.')
    args = parser.parse_args()
    if args.self_test:
        require(args.grade_map is None and args.out_dir is None and args.run_plan is None, 'Self-test does not consume real grade maps/plans'); self_test(); return
    require(args.grade_map is not None and args.out_dir is not None, 'Supply final approved --grade-map and a new --out-dir')
    out = args.out_dir.resolve()
    require(out.is_relative_to(WORK.resolve()) and out != WORK.resolve(), 'Output must be a new subdirectory under v16 workspace')
    require(not out.exists(), 'Output directory already exists; preserve earlier deliveries')
    # Complete all validation before writing any delivery artifact.
    grid, bindings = load_grid(run_plan_specs(args.run_plan)); rows = attach_grades(grid, S.read(args.grade_map))
    summary, index = outputs(rows, bindings, file_ref(args.grade_map))
    summary['analyzer_source_sha256'] = S.file_sha(__file__)
    md = markdown_index(index, out)
    out.mkdir(parents=True)
    for name, data in [('summary.json', summary), ('error-index.json', index)]:
        (out / name).write_text(json.dumps(data, ensure_ascii=False, indent=2, allow_nan=False) + '\n', encoding='utf-8')
    (out / 'error-index.md').write_text(md, encoding='utf-8')
    print(json.dumps({'slots': len(rows), 'approved_grade_rows': summary['approved_grade_rows'],
                      'indexed_F_or_U': len(index['records']), 'output': str(out), 'semantic_regrading': False}, ensure_ascii=False))


if __name__ == '__main__':
    main()
