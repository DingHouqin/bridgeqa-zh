"""Independently recheck the saved run and export the development milestone.

No model calls or credentials. This script never edits existing human reviews.
"""
import argparse
import ast
import hashlib
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

import jsonschema
from contracts import SCHEMAS
from core import (active_facts, build_family, check_solver, digest, project, solve,
                  supervisor_gate, validate_origin, validate_projection)
from runner import ROOT, CODE, MATERIAL_DIR, load


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding='utf-8')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--run-id', default='milestone-007')
    args = parser.parse_args()
    if not re.fullmatch(r'[a-z0-9-]+', args.run_id):
        raise ValueError('Invalid run id')
    out = ROOT / 'workspace/harness-prototype/runs' / args.run_id
    package = ROOT / 'artifacts/multi-agent-v0' / args.run_id
    package.mkdir(parents=True, exist_ok=True)
    completion = load(out / 'completion.json')
    assert completion['status'] in ('completed_pending_gpt_review', 'development_milestone_complete')
    protocol_v2 = completion.get('answer_protocol_version') == 'evidence-quotes-v0.2'
    materials = load(out / 'materials.frozen.json')
    origin = load(out / 'facts.gpt-adjudicated.json')
    composer = load(out / 'base.reviewed.json')
    difficult = load(out / 'difficulty.gpt-adjudicated.json')
    for name, value in [('origin', origin), ('composer', composer), ('difficult', difficult)]:
        jsonschema.validate(value, SCHEMAS[name])
    validate_origin(origin, materials)
    family = build_family(composer, difficult, origin, materials)
    saved_family = load(out / 'family.internal.json')
    for key in family:
        if key == 'release_status':
            continue
        assert family[key] == saved_family[key], key
    # Speaker-frame reuse is checked character-for-character against the approved modern parent.
    parent_units = {u['unit_id']: u for p in ('P01', 'P02') for u in load(MATERIAL_DIR / (p + '.modern.json'))}
    raw_path = ROOT / 'data/source-candidates/hongloumeng_archive_org/20210205_20210205_1123/hongloumeng_original_120.txt'
    raw_hash = hashlib.sha256(raw_path.read_bytes()).hexdigest()
    for u in materials:
        assert raw_hash == u['source_sha256']
        assert hashlib.sha256(u['text'].encode('utf-8')).hexdigest() == u['modern_sha256']
        if 'parent_unit_id' in u:
            parent = parent_units[u['parent_unit_id']]
            assert parent['modern_sha256'] == u['parent_modern_sha256']
            assert ''.join(parent['modern_text'][a:b] for a, b in u['modern_source_ranges']) == u['text']
        else:
            assert parent_units[u['unit_id']]['modern_text'] == u['text']
    # Recompute the committed four inputs and all external behavior checks.
    inputs = load(out / 'model-inputs.json')
    results = load(out / 'solver-results.json')
    isolation = []
    for i, (row, payload, result) in enumerate(zip(family['variants'], inputs, results), 1):
        assert payload == project(row, family['question'], SCHEMAS['blind-solver'])
        validate_projection(payload)
        jsonschema.validate(result['answer'], SCHEMAS['blind-solver'])
        assert check_solver(result['answer'], payload, row, origin, family['query']) == result['checks']
        prefix = 'blind-v2-item-' if protocol_v2 else 'blind-item-'
        stage = next(p for p in (out / 'stages').glob(f'{prefix}{i}.format-*.input.json') if load(p)['input'] == payload)
        record = load(stage.with_name(stage.name.replace('.input.json', '.runtime.json')))
        runtime = load(stage.with_name(stage.name.replace('.input.json', '.runtime-events.json')))
        messages = [e for e in runtime['events'] if e['type'] == 'user/message' and e['data'].get('source', {}).get('kind') == 'user']
        assert len(messages) == 1, 'Blind solver inherited extra user history'
        actual_request = json.loads(''.join(b['text'] for b in messages[0]['data']['content'] if b.get('type') == 'text'))
        assert actual_request == load(stage)
        assert actual_request['input'] == payload
        assert not any(e['type'].startswith('tool/') for e in runtime['events'])
        isolation.append({'item_id': payload['item_id'], 'session_id': record['session_id'], 'one_fresh_task_message': True,
                          'actual_runtime_input_matches_projection': True, 'gold_or_other_answers_in_input': False})
    assert len({r['session_id'] for r in isolation}) == 4
    required = ['final_text_no_shortcut', 'all_proofs_cut', 'family_invariants', 'solver_comparison', 'isolation']
    final_stage = completion.get('final_review_stage', 'final-family-review')
    final_review = load(out / f'stages/{final_stage}.format-0.parsed.json')
    assert supervisor_gate(final_review, required)
    plugin_check = load(out / 'harness-plugin-verification.json')
    assert plugin_check['status'] == 'passed' and plugin_check['harness_tool_execution']
    assert plugin_check['python_and_harness_results_equal']
    smoke = load(out / 'fixed-profile-smoke.json')
    assert len(smoke) == 2 and all(r['startup'] == 'passed' and r['model_turns'] == 0 for r in smoke)
    base_facts = active_facts(origin, family['variants'][0]['materials'])
    assert plugin_check['result'] == solve(family['query'], base_facts)
    plugin_check['payload_hash'] = digest({'facts': base_facts, 'query': family['query']})
    write(out / 'harness-plugin-verification.json', plugin_check)
    # Run the local behavioral suite and save a durable result.
    test = subprocess.run([sys.executable, '-m', 'unittest', 'discover', '-s', str(CODE), '-p', 'test_core.py', '-v'],
                          capture_output=True, text=True, encoding='utf-8')
    (package / 'tests.txt').write_text(test.stdout + test.stderr, encoding='utf-8')
    assert test.returncode == 0
    count = int(re.search(r'Ran (\d+) tests', test.stderr).group(1))
    for path in CODE.glob('*.py'):
        ast.parse(path.read_text(encoding='utf-8'))
    # Actual SDK requests are counted by root request/header events, not cached role calls.
    ledger = []
    all_roles = set()
    for run in sorted((ROOT / 'workspace/harness-prototype/runs').glob('milestone-*')):
        for p in sorted((run / 'stages').glob('*.runtime-events.json')):
            value = load(p)
            runtime_path = p.with_name(p.name.replace('.runtime-events.json', '.runtime.json'))
            record = load(runtime_path)
            all_roles.add(record['role'])
            headers = [e for e in value['events'] if e['type'] == 'request/header']
            usages = [e['data']['usage'] for e in value['events'] if isinstance(e.get('data', {}).get('usage'), dict)]
            usage = {k: sum(u.get(k, 0) for u in usages) for k in ('inputTokens', 'outputTokens', 'cacheReadTokens', 'cacheWriteTokens', 'totalTokens')}
            ledger.append({'run': run.name, 'stage': record['stage'], 'role': record['role'], 'session_id': record['session_id'],
                           'requests': len(headers), 'finish_reason': record['finish_reason'], 'usage_observed': bool(usages), 'usage': usage,
                           'runtime_record': str(p.relative_to(ROOT)).replace('\\', '/')})
    role_set = {load(p)['role'] for p in (out / 'stages').glob('*.runtime.json')}
    assert role_set == {'origin', 'composer', 'difficult', 'supervisor', 'blind-solver'}
    current_ledger = [r for r in ledger if r['run'] == args.run_id]
    stats = {'all_development_requests': sum(r['requests'] for r in ledger),
             'all_development_observed_total_tokens': sum(r['usage']['totalTokens'] for r in ledger),
             'requests_without_usage': sum(r['requests'] for r in ledger if not r['usage_observed']),
             'final_run_requests_including_rejected_drafts': sum(r['requests'] for r in current_ledger),
             'final_run_observed_total_tokens': sum(r['usage']['totalTokens'] for r in current_ledger),
             'billing_amount': 'not_retrieved', 'counting': 'Saved root request/header and top-level usage once per stage within each isolated run; notifications/stream duplicates excluded.'}
    write(package / 'run_ledger.json', ledger)
    # Current GPT reviewed the source, graph, actual variants, solver results and contradictory review.
    family.update({'machine_review': 'passed', 'gpt_review': 'passed_for_development',
                   'release_status': 'development_milestone_only', 'human_review': 'not_run', 'gpt_adjudication_used': True})
    family['answer_protocol_version'] = completion.get('answer_protocol_version', 'implicit-v1')
    family['target_conclusion_type'] = 'implicit_two_parent_composition'
    family['fact_expression_counts'] = {kind: sum(f['expression'] == kind for f in origin['facts']) for kind in ('direct', 'coreference')}
    family['evidence_distribution'] = 'same_selected_passage_for_base_proof'
    family['visibility_judgement_basis'] = 'Final text inspected by Supervisor and GPT; graph depth alone is not the basis for absence of a direct conclusion.'
    gpt_review = {'reviewer': 'GPT in current Codex session', 'date': '2026-10-21', 'decision': 'pass_for_development_milestone',
        'family_hash': digest(family), 'question': family['question'], 'material_hashes': [u['modern_sha256'] for u in materials],
        'actual_blind_input_hashes': [digest(p) for p in inputs],
        'answer_protocol_version': completion.get('answer_protocol_version', 'implicit-v1'),
        'behavioral_findings': {'answer_status_correct': sum(r['checks']['answer_and_status_correct'] for r in results),
            'out_of': len(results), 'necessary_support_deleted_response': results[-1]['answer'],
            'no_material_diagnostic_response': load(out / 'no-material-diagnostic.json')['answer'],
            'interpretation': 'Partial-context completion can fail evidence sufficiency despite an empty-context refusal; this does not identify the model internal cause or demonstrate entity-confusion success.'},
        'checks': {'source_fragment_reconstruction': True, 'base_two_necessary_parent_lookups': True,
                   'no_direct_target_statement_found_in_selected_text': True, 'entity_confusion_first_error_explicit': True,
                   'unrelated_change_does_not_support_target': True, 'deletion_cuts_F4_preserves_F3': True,
                   'no_alternative_textual_proof_found_in_selected_context': True, 'actual_blind_inputs_audited': True},
        'intervention': 'One explicit GPT source-grounded entity/fact supplement and difficulty correction after finite Flash revisions; independently re-reviewed before blind solves.',
        'limits': ['Necessary-support deletion also removes the question-start name; a solver could detect lexical absence. Do not use this alone as proof of relational dependence.',
                   'The archived protocol-v1 main distractor answer/path was correct, but a non-verbatim quote failed literal matching. The rule was then made explicit and all conditions re-run under a frozen protocol-v2, not selected by outcome.',
                   'This verifies one development family, not broad coverage or independently held-out model performance.',
                   'This run generated roles before the local-patch peer-resolution defect was fixed; the real plugin gate was subsequently executed through the installed official bundle. No model tool call is claimed.'],
        'user_confirmation_of_material_AI_review': True, 'line_by_line_human_review': 'not_claimed', 'new_family_human_review': 'not_run',
        'formal_test_release': False}
    write(package / 'gpt_review.json', gpt_review)
    family.update({'machine_review': 'passed', 'gpt_review': 'passed_for_development',
                   'release_status': 'development_milestone_only', 'human_review': 'not_run', 'gpt_adjudication_used': True})
    write(package / 'family.internal.json', family)
    for name in ['materials.frozen.json', 'facts.gpt-adjudicated.json', 'base.reviewed.json', 'difficulty.gpt-adjudicated.json',
                 'gpt-adjudication.json', 'model-inputs.json', 'model-inputs.jsonl', 'gold.json', 'gold.jsonl',
                 'solver-results.json', 'solver-results.jsonl', 'no-material-diagnostic.json',
                 'harness-plugin-execution.json', 'harness-plugin-verification.json', 'fixed-profile-smoke.json']:
        shutil.copyfile(out / name, package / name)
    if protocol_v2:
        shutil.copyfile(out / 'protocol-v2.frozen.json', package / 'protocol-v2.frozen.json')
        (package / 'protocol-v1').mkdir(exist_ok=True)
        for name in ('model-inputs.json', 'gold.json', 'solver-results.json', 'no-material-diagnostic.json', 'completion.json'):
            shutil.copyfile(out / 'protocol-v1' / name, package / 'protocol-v1' / name)
        for name in ('protocol-v2-before-overlap-fix.json', 'evidence-overlap-correction.json'):
            shutil.copyfile(out / name, package / name)
    review_dir = package / 'reviews'
    review_dir.mkdir(exist_ok=True)
    for name in ('adjudicated-origin-review', 'adjudicated-family-review', final_stage):
        shutil.copyfile(out / f'stages/{name}.format-0.parsed.json', review_dir / (name + '.json'))
    current_roles = sorted(role_set)
    report = {'status': 'development_milestone_complete', 'question': family['question'], 'family_count': 1, 'variants': 4, 'diagnostics': 1,
        'roles_actually_executed': current_roles, 'gpt_adjudications': 1,
        'answer_and_status_correct': sum(r['checks']['answer_and_status_correct'] for r in results),
        'path_records_correct': sum(r['checks']['path_matches_permitted_proof'] for r in results),
        'strict_structure_and_quotes_correct': sum(r['checks']['strict_structural_success'] for r in results),
        'tests_passed': count, 'runtime_plugin_check': 'passed', 'isolation_checks': isolation, 'usage': stats,
        'raw_source_hash_rechecked': True, 'answer_protocol_version': completion.get('answer_protocol_version', 'implicit-v1'),
        'structural_score_version': completion.get('structural_score_version', 'containment-v0.1'),
        'decoding_parameters': {'model_alias': 'deepseek-flash', 'effort': 'off', 'max_tokens': 18000,
                                'temperature': 'provider_default_not_explicitly_fixed', 'seed': 'not_set'},
        'fixed_builder_and_solver_startup': 'passed_without_model_turns',
        'sdk_version': completion['sdk_version'], 'runtime_version': completion['runtime_version'],
        'first_success_is_not_fully_automatic': True, 'human_review': 'not_run', 'formal_release': False}
    write(package / 'verification.json', report)
    state = [
        {'state': 'source_materials_confirmed_for_development', 'evidence': 'material-user-confirmation.json'},
        {'state': 'origin_and_base_reviewed', 'evidence': 'facts.reviewed.json + base.reviewed.json'},
        {'state': 'automatic_difficulty_revisions_exhausted', 'evidence': 'stages/difficult-review-2.format-0.parsed.json'},
        {'state': 'gpt_targeted_adjudication', 'evidence': 'gpt-adjudication.json'},
        {'state': 'adjudicated_facts_and_family_independently_reviewed', 'evidence': 'stages/adjudicated-family-review.format-0.parsed.json'},
        {'state': 'four_blind_solves_and_no_material_probe_complete', 'evidence': 'solver-results.json + no-material-diagnostic.json'},
        {'state': 'final_supervisor_review_passed', 'evidence': 'stages/final-family-review.format-0.parsed.json'},
        {'state': 'real_harness_plugin_gate_passed', 'evidence': 'harness-plugin-verification.json'},
        {'state': 'gpt_and_independent_program_audit_passed', 'evidence': 'gpt_review.json + verification.json'},
        {'state': 'development_package_exported_human_review_not_claimed', 'evidence': 'family.internal.json'}]
    write(package / 'workflow_states.json', {'reconstructed_from_saved_artifacts': True, 'ordering': 'logical gate order, not an invented wall-clock trace',
        'answer_protocol_version': completion.get('answer_protocol_version', 'implicit-v1'), 'states': state})
    write(package / 'human_review_queue.json', {'status': 'pending', 'reason': 'important GPT adjudication requires human dispute review under the agreed policy',
        'family_id': family['candidate_id'], 'family_hash': digest(family), 'material_user_confirmation': 'confirmation_of_AI_conclusions_only',
        'human_line_by_line_review': 'not_run', 'review_book': '题目家族审阅册.md'})
    book = ['# 首个四成员家族审阅册\n\n状态：机器与GPT开发复核已完成，新家族人工审查待进行。此册含gold与条件标签，不能作为被测输入。\n\n',
            '问题：' + family['question'] + '\n\n正确链：贾蓉→父贾珍→父贾敬。主干扰的错误路径是假把贾珍识别为贾政，再取贾政之父贾代善。\n\n',
            '人工重点：父子指代是否成立；荣府是否形成近名干扰但不改变答案；删证是否确无替代证明；删证同时删去贾蓉名称的局限是否可以接受为开发例。引用协议v1及v2均留存，不能混为独立测试。\n\n']
    for row, payload, result in zip(family['variants'], inputs, results):
        book.append('## ' + row['condition'] + '\n\n')
        book.append('题号：`' + payload['item_id'] + '`。标准状态：`' + row['gold']['status'] + '`；标准实体ID：`' + ', '.join(row['gold']['answer_ids']) + '`。\n\n')
        for context in payload['contexts']:
            book.append('### ' + context['context_id'] + '\n\n' + context['text'] + '\n\n')
        book.append('Flash状态：`' + result['answer']['status'] + '`；答案：' + ('、'.join(result['answer']['answers']) or '无') + '。\n\n')
    (package / '题目家族审阅册.md').write_text(''.join(book), encoding='utf-8')
    manifest = {str(p.relative_to(ROOT)).replace('\\', '/'): hashlib.sha256(p.read_bytes()).hexdigest()
                for p in CODE.rglob('*') if p.is_file() and p.suffix in ('.py', '.json', '.md', '.js', '.mjs', '.yml', '.txt') and '__pycache__' not in p.parts}
    write(package / 'implementation_manifest.json', {'packaged_source_hashes': manifest, 'original_per_request_skill_schema_patch_hashes': 'retained in workspace stage runtime records'})
    # First-party artifacts/session transcripts only; do not scan dependency payloads.
    scanned = list(CODE.rglob('*.py')) + list(CODE.rglob('*.md')) + list(package.rglob('*.json')) + list(package.rglob('*.jsonl')) + list(package.rglob('*.md'))
    scanned += list((out / 'stages').glob('*.json'))
    for session_dir in (out / 'harness-homes').glob('*/sessions'):
        scanned += list(session_dir.rglob('*.jsonl'))
    assert not any(re.search(r'sk-[A-Za-z0-9]{20,}', p.read_text(encoding='utf-8')) for p in scanned)
    report['credential_pattern_scan'] = {'files': len(scanned), 'matches': 0}
    write(package / 'verification.json', report)
    # Repair the resumed-run summary's role count without erasing its historical call list.
    completion['roles_executed'] = current_roles
    completion['status'] = 'development_milestone_complete'
    completion['gpt_review'] = 'passed_for_development'
    completion['prior_failure_records_retained'] = True
    completion['roles_count_source'] = 'all actual stage runtime records, including the pre-adjudication Difficult calls'
    write(out / 'completion.json', completion)
    print(json.dumps(report, ensure_ascii=False))


if __name__ == '__main__':
    main()
