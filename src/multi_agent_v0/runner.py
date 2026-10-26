"""Run five isolated roles on the official Harness SDK. See README.md.

Secrets stay in runtime memory/child environment. No direct chat-API fallback.
"""
import argparse
import dataclasses
import getpass
import hashlib
import importlib.metadata
import json
import os
import re
import traceback
from pathlib import Path

import jsonschema
from deepseek_harness import DeepSeekHarness

from contracts import SCHEMAS, VERSION
from formatting import parse_with_closing_repair, normalize_origin_annotations
from install_plugin import install
from external_relations import load_approved_libraries, compare_origin
from core import (active_facts, build_family, check_solver, digest, project, solve,
                  supervisor_gate, validate_composer, validate_origin, validate_projection)
from core import validate_origin_for_composition, query_options

ROOT = Path(__file__).resolve().parents[2]
CODE = Path(__file__).resolve().parent
MATERIAL_DIR = ROOT / 'workspace/hongloumeng-modernization-trial/resolved-validation'


def load(path):
    return json.loads(path.read_text(encoding='utf-8'))


def load_materials():
    review = load(MATERIAL_DIR / 'gpt_review.json')
    approved = {u['unit_id']: u for u in review['reviewed_snapshots']}
    result = []
    for packet in ('P01', 'P02'):
        for u in load(MATERIAL_DIR / (packet + '.modern.json')):
            if u['modern_sha256'] != approved[u['unit_id']]['modern_sha256']:
                raise ValueError('Material differs from reviewed snapshot')
            if hashlib.sha256(u['modern_text'].encode('utf-8')).hexdigest() != u['modern_sha256']:
                raise ValueError('Material text/hash mismatch')
            result.append({'unit_id': u['unit_id'], 'text': u['modern_text'], 'modern_sha256': u['modern_sha256'],
                           'source_sha256': approved[u['unit_id']]['source_sha256'], 'source_span': approved[u['unit_id']]['source_span']})
    selected = []
    for unit in result:
        if not unit['unit_id'].endswith('C002-U0014'):
            selected.append(unit)
            continue
        body = unit['text']
        boundary = body.index('再说荣府')
        opening_end = body.index('“') + 1
        assert body.endswith('”')
        # Reuse only the already-reviewed speaker frame and its closing quote.
        # Each fragment is reconstructed from explicitly recorded parent-text regions.
        for suffix, ranges in [('NING', [[0, boundary], [len(body)-1, len(body)]]),
                               ('RONG', [[0, opening_end], [boundary, len(body)]])]:
            fragment = ''.join(body[start:end] for start, end in ranges)
            selected.append(dict(unit, unit_id=unit['unit_id'] + '-' + suffix, text=fragment,
                modern_sha256=hashlib.sha256(fragment.encode('utf-8')).hexdigest(),
                parent_unit_id=unit['unit_id'], parent_modern_sha256=unit['modern_sha256'],
                modern_source_ranges=ranges, selection_transform='source_excerpt_with_reused_speaker_frame',
                source_span_scope='raw span covers the reviewed parent unit, not an exact raw subspan'))
    return selected


def json_default(value):
    if dataclasses.is_dataclass(value):
        return dataclasses.asdict(value)
    if hasattr(value, 'model_dump'):
        return value.model_dump(mode='json')
    return str(value)


class Pipeline:
    def __init__(self, key, run_id, adjudication=None):
        if not re.fullmatch(r'[a-z0-9-]+', run_id):
            raise ValueError('Invalid run id')
        self.key = key
        self.out = ROOT / 'workspace/harness-prototype/runs' / run_id
        self.out.mkdir(parents=True, exist_ok=True)
        self.presets = load(CODE / 'role-presets.json')
        self.calls = []
        self.model = 'deepseek-flash'
        self.adjudication = Path(adjudication).resolve() if adjudication else None
        self.pools = {}
        self.external_libraries = load_approved_libraries(ROOT)
        self.materials = load_materials()
        self.save('materials.frozen.json', self.materials)
        self.save('material-user-confirmation.json', {'date': '2026-10-21', 'type': 'user_confirmation_of_ai_conclusions',
            'instruction': '赞同AI的结论；同意执行到下一个交付点', 'line_by_line_human_review': 'not_claimed',
            'purpose': 'authorized development prototype, not hidden formal test release'})

    def save(self, name, value):
        encoded = json.dumps(value, ensure_ascii=False, indent=2, default=json_default)
        if self.key and self.key in encoded:
            raise RuntimeError('Credential detected in artifact; refusing output')
        path = self.out / name
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.exists() and name.endswith(('.input.json', '.parsed.json', '.frozen.json')) and path.read_text(encoding='utf-8') != encoded:
            raise RuntimeError('Immutable stage changed; start a new run or stage version')
        path.write_text(encoded, encoding='utf-8')

    def pool(self, role):
        pool = 'solver' if role == 'blind-solver' else 'builder'
        if pool not in self.pools:
            patches = [str(CODE / 'harness.patch.yml')]
            if pool == 'solver':
                patches.append(str(CODE / 'solver.patch.yml'))
            cwd = self.out / 'runtime-workspaces' / pool
            cwd.mkdir(parents=True, exist_ok=True)
            home = self.out / 'harness-homes' / pool
            home.mkdir(parents=True, exist_ok=True)
            manifest_path = home / 'profiles/sdk-minimal/package.json'
            manifest = load(manifest_path) if manifest_path.exists() else {}
            if 'bridgeqa-harness-tools' not in manifest.get('dsh', {}).get('profile', {}).get('bundles', []):
                manifest = install(home)
            self.save('runtime-' + pool + '-profile.json', manifest)
            self.pools[pool] = DeepSeekHarness(provider='deepseek-official', model=self.model,
                reasoning_effort='off', max_tokens=18000, cwd=str(cwd), runtime_cwd=str(cwd), dsh_home=str(home),
                profile='sdk-minimal', patches=tuple(patches), api_key=self.key, base_url='https://api.deepseek.com/anthropic',
                initialize_timeout_seconds=90, request_timeout_seconds=300, shutdown_timeout_seconds=10)
            self.pools[pool].start()
            diagnostics = self.pools[pool].client._runtime_diagnostics()
            if 'did not activate' in diagnostics or 'failed to import' in diagnostics:
                raise RuntimeError('Harness plugin activation failed; inference withheld: ' + diagnostics[-2000:])
        return self.pools[pool]

    def role(self, stage, role, payload):
        skill = (CODE / self.presets[role]['skill']).read_text(encoding='utf-8')
        original = {'role': role, 'skill': skill, 'input': payload, 'output_schema': SCHEMAS[role],
                    'model': self.model, 'schema_version': VERSION,
                    'runtime_contract': {'sdk_version': importlib.metadata.version('deepseek-harness-sdk'),
                       'transport': 'official_anthropic_messages', 'effort': 'off', 'max_tokens': 18000,
                       'base_patch_hash': digest((CODE / 'harness.patch.yml').read_text(encoding='utf-8')),
                       'solver_patch_hash': digest((CODE / 'solver.patch.yml').read_text(encoding='utf-8')) if role == 'blind-solver' else None}}
        for attempt in range(3):
            name = f'stages/{stage}.format-{attempt}'
            request = dict(original)
            if attempt:
                request['format_repair'] = '上次输出不满足JSON合同。只修复格式和字段；不要扩展任务。错误：' + format_error
            sid = 'bridgeqa-' + digest({'stage': name, 'request': request})[:24]
            self.save(name + '.input.json', request)
            parsed_path = self.out / (name + '.parsed.json')
            if parsed_path.exists():
                parsed = load(parsed_path)
                jsonschema.validate(parsed, SCHEMAS[role])
                record = load(self.out / (name + '.runtime.json'))
                record['reused'] = True
                self.calls.append(record)
                print(json.dumps({'stage': stage, 'role': role, 'cached': True}, ensure_ascii=True), flush=True)
                return parsed
            print(json.dumps({'started': stage, 'role': role, 'format_attempt': attempt}, ensure_ascii=True), flush=True)
            response_path = self.out / (name + '.response.json')
            if response_path.exists():
                runtime_record = load(self.out / (name + '.runtime.json'))
                if runtime_record['finish_reason'] != 'completed':
                    raise RuntimeError('Prior incomplete Harness turn must use a new batch')
                content_response = load(response_path)['final_response']
                from types import SimpleNamespace
                prior_events = load(self.out / (name + '.runtime-events.json'))
                result = SimpleNamespace(session_id=sid, finish_reason='completed', final_response=content_response,
                                         events=prior_events['events'], notifications=prior_events['notifications'])
                from_cache = True
            else:
                result = self.pool(role).run(json.dumps(request, ensure_ascii=False), session_id=sid)
                from_cache = False
            runtime = {'session_id': result.session_id, 'finish_reason': result.finish_reason, 'events': result.events, 'notifications': result.notifications}
            self.save(name + '.runtime-events.json', runtime)
            self.save(name + '.response.json', {'final_response': result.final_response})
            record = {'stage': stage, 'role': role, 'session_id': result.session_id, 'finish_reason': result.finish_reason,
                      'input_hash': digest(request), 'skill_hash': digest(skill), 'schema_hash': digest(SCHEMAS[role]),
                      'tool_policy': self.presets[role]['tool_policy'], 'reused': from_cache}
            self.save(name + '.runtime.json', record)
            self.calls.append(record)
            self.save('progress.json', {'status': 'running', 'calls': self.calls})
            if result.finish_reason != 'completed':
                raise RuntimeError('Harness turn did not complete: ' + str(result.finish_reason))
            content = result.final_response.strip()
            if content.startswith('```'):
                content = re.sub(r'^```(?:json)?\s*|\s*```$', '', content)
            try:
                parsed, punctuation_repairs = parse_with_closing_repair(content)
                if punctuation_repairs:
                    self.save(name + '.syntax-repair.json', {'method': 'closing_delimiters_only', 'edits': punctuation_repairs,
                        'string_contents_and_values_unchanged': True, 'semantic_validation_still_required': True})
                if role == 'origin':
                    parsed, annotations = normalize_origin_annotations(parsed)
                    if annotations:
                        self.save(name + '.annotation-normalization.json', {'method': 'move_known_commentary_to_root_warnings', 'edits': annotations,
                            'parent_child_role_scope_and_evidence_unchanged': True})
                jsonschema.validate(parsed, SCHEMAS[role])
                self.save(name + '.parsed.json', parsed)
                print(json.dumps({'completed': stage, 'role': role}, ensure_ascii=True), flush=True)
                return parsed
            except (ValueError, jsonschema.ValidationError) as exc:
                format_error = (str(exc.message) + ' at ' + '/'.join(map(str, exc.absolute_path))) if isinstance(exc, jsonschema.ValidationError) else str(exc)
                self.save(name + '.format-error.json', {'error': format_error})
        raise RuntimeError('Format repair limit reached for ' + stage)

    def reviewed(self, kind, role, payload, validate, required):
        previous = None
        for revision in range(3):
            data = dict(payload)
            if previous:
                data['revision_request'] = previous
            draft = self.role(f'{kind}-{revision}', role, data)
            try:
                checked = validate(draft)
            except ValueError as exc:
                previous = {'program_defect': str(exc), 'previous_output': draft}
                self.save(f'revisions/{kind}-{revision}.json', previous)
                continue
            review_payload = {'stage': kind, 'materials': self.materials, 'generator_input': payload, 'candidate': draft,
                              'program_checks': checked, 'required_checks': required}
            if kind == 'origin':
                hints = compare_origin(draft, self.external_libraries)
                self.save(f'external-relations/{kind}-{revision}.frozen.json', hints)
                review_payload['external_relation_hints'] = hints
                review_payload['external_relation_policy'] = '仅来源核验线索，不是事实或裁判；未覆盖不表示错误。对照实际材料，不能从库中补事实或凭一致自动放行。已知库错忽略并留痕，时间与scope均未获库验证。'
            review = self.role(f'{kind}-review-{revision}', 'supervisor', review_payload)
            if supervisor_gate(review, required):
                return draft, checked, review
            if review['verdict'] == 'reject':
                raise RuntimeError(kind + ' rejected by Supervisor; no source fabrication permitted')
            previous = {'review': review, 'previous_output': draft}
            self.save(f'revisions/{kind}-{revision}.json', previous)
        raise RuntimeError(kind + ' content revision limit reached')

    def run(self):
        material_view = [{'unit_id': u['unit_id'], 'text': u['text']} for u in self.materials]
        primary_id = next(u['unit_id'] for u in self.materials if u['unit_id'].endswith('-NING'))
        distractor_id = next(u['unit_id'] for u in self.materials if u['unit_id'].endswith('-RONG'))
        origin, origin_checks, origin_review = self.reviewed('origin', 'origin',
            {'materials': material_view, 'allowed_predicates': ['parent'], 'allowed_scopes': ['冷子兴转述', '叙述者'],
             'extraction_budget': '只选4—8条最明确、端点具名的直接父母事实。不要为了穷尽抽取而加入继官、妻生子或常识推测的关系；复杂无名人物可不选。',
             'selection_hint': '优先选同一段宁国府连续父子叙事中的连通事实，至少形成一个child→parent→parent链。荣府和薛家可提供干扰候选。不需要抽全部人物。每个替代evidence_set独立含父母及子女的名字或可核验别名，不能把只有父母称呼的一句当独立支持。',
             'primary_unit_id': primary_id, 'parallel_household_distractor_unit_id': distractor_id,
             'exclude_for_question_targets': ['内囊耗尽程度', '承局精确职名', '亲名达部具体执行方式', '能著细义']},
            lambda draft: validate_origin_for_composition(draft, self.materials),
            ['identity', 'direction', 'scope', 'evidence_support', 'alternative_supports'])
        self.save('facts.reviewed.json', origin)

        def validate_base(draft):
            if draft['base_unit_ids'] != [primary_id]:
                raise ValueError('For this controlled pilot, base must use only the selected Ning-household excerpt')
            return validate_composer(draft, origin, self.materials)

        composer, base_checks, base_review = self.reviewed('composer', 'composer',
            {'materials': material_view, 'reviewed_facts': origin,
             'validated_query_options': query_options(origin, [u for u in self.materials if u['unit_id'] == primary_id]),
             'base_unit_whitelist': [primary_id],
             'goal': '优先选择两次father查找，最少一个完整来源单元足以支持，留出至少两个其他来源单元用于不同添加条件。只生成一个候选；按来源事实构题，不要求模型答错。'},
            validate_base,
            ['query_alignment', 'answer_unique', 'two_necessary_steps', 'no_direct_answer', 'alternative_proofs'])
        self.save('base.reviewed.json', composer)
        if self.adjudication:
            decision = load(self.adjudication)
            if decision['parent_origin_hash'] != digest(origin) or decision['parent_composer_hash'] != digest(composer):
                raise ValueError('GPT adjudication parent version mismatch')
            original_origin = origin
            origin = decision['origin']
            assert all(f in origin['facts'] for f in original_origin['facts'])
            validate_origin(origin, self.materials)
            validate_composer(composer, origin, self.materials)
            self.save('facts.gpt-adjudicated.json', origin)
            adjudicated_hints = compare_origin(origin, self.external_libraries)
            self.save('external-relations/adjudicated-origin.frozen.json', adjudicated_hints)
            review = self.role('adjudicated-origin-review', 'supervisor',
                {'stage': 'source-grounded noise-fact supplement', 'materials': material_view, 'candidate': origin,
                 'external_relation_hints': adjudicated_hints,
                 'required_checks': ['identity', 'direction', 'scope', 'evidence_support', 'alternative_supports'],
                 'review_instruction': '原抽取基础链不变；新登记荣府来源中直接出现的贾代善、贾政及父子关系。独立核对引文，不凭裁定者身份放行；确保passed布尔值、说明和verdict相互一致。'})
            if not supervisor_gate(review, ['identity', 'direction', 'scope', 'evidence_support', 'alternative_supports']):
                raise RuntimeError('Adjudicated extraction did not pass independent review')
            difficult = decision['difficulty']
            jsonschema.validate(difficult, SCHEMAS['difficult'])
            family = build_family(composer, difficult, origin, self.materials)
            self.save('difficulty.gpt-adjudicated.json', difficult)
            family_review = self.role('adjudicated-family-review', 'supervisor',
                {'stage': 'adjudicated-family', 'materials': material_view, 'reviewed_facts': origin, 'base': composer,
                 'candidate': difficult, 'program_checks': family,
                 'required_checks': ['distractor_applicable', 'unrelated_control', 'family_invariants', 'all_proofs_cut', 'final_text_no_shortcut'],
                 'review_instruction': '独立对照实际材料。基础同段两次父亲查找是已允许的多跳形式。删证只切断第一步F4的完整句，F3保留；切断全部证明不要求删除每条边。不要把小样本未诱错当题目无效。确保布尔字段与说明一致。'})
            if not supervisor_gate(family_review, ['distractor_applicable', 'unrelated_control', 'family_invariants', 'all_proofs_cut', 'final_text_no_shortcut']):
                raise RuntimeError('Adjudicated family did not pass independent review')
        else:
            difficult, family, family_review = self.reviewed('difficult', 'difficult',
                {'materials': material_view, 'reviewed_facts': origin, 'base': composer, 'base_program_checks': base_checks,
                 'allowed_mechanisms': ['entity_confusion'], 'source_track_only': True,
                 'required_distractor_unit_ids': [distractor_id],
                 'instruction': '主干扰必须添加RONG选段，即另一房的同姓世系；错接路径明确指出把宁府目标人物误对应到荣府哪一个具体人物。无关对照从其他来源单元选择，与主干扰不同。删证优先只删一条必要边的完整支持句（含其句末标点），保持其他人物和叙事；若该边有重复支持则一并删去。不删除无关世系句、不留下双句号、孤立分号或明显截断标记。'},
                lambda draft: build_family(composer, draft, origin, self.materials),
                ['distractor_applicable', 'unrelated_control', 'family_invariants', 'all_proofs_cut', 'final_text_no_shortcut'])
        self.save('family.internal.json', family)
        inputs, golds, results = [], [], []
        for i, row in enumerate(family['variants']):
            payload = project(row, family['question'], SCHEMAS['blind-solver'])
            validate_projection(payload)
            self.save(f'blind-inputs/item-{i + 1}.json', payload)
            answer = self.role(f'blind-item-{i + 1}', 'blind-solver', payload)
            judgement = check_solver(answer, payload, row, origin, family['query'])
            inputs.append(payload)
            golds.append({'item_id': payload['item_id'], 'condition': row['condition'], 'gold': row['gold'], 'group': family['split_group']})
            results.append({'item_id': payload['item_id'], 'condition': row['condition'], 'answer': answer, 'checks': judgement})
        diagnostic_row = {'materials': [], 'gold': solve(family['query'], [])}
        diagnostic_input = project(diagnostic_row, family['question'], SCHEMAS['blind-solver'])
        diagnostic = self.role('blind-no-material-diagnostic', 'blind-solver', diagnostic_input)
        self.save('no-material-diagnostic.json', {'input': diagnostic_input, 'answer': diagnostic,
            'checks': check_solver(diagnostic, diagnostic_input, diagnostic_row, origin, family['query']), 'separate_from_four_member_family': True})
        final_review = self.role('final-family-review', 'supervisor',
            {'stage': 'final', 'materials': material_view, 'reviewed_facts': origin, 'base': composer, 'difficulty': difficult,
             'family': family, 'solver_results': results, 'model_inputs': inputs,
             'required_checks': ['final_text_no_shortcut', 'all_proofs_cut', 'family_invariants', 'solver_comparison', 'isolation'],
             'isolation_contract': '每条盲解是独立全新会话，不见gold、事实图、家族标签或其他答案；独立home，所有工具禁用。问题与当前材料投影见model_inputs。',
             'instruction': '模型答错不自动代表题目无效。核查gold和文本是否正确，若确为盲解错误可作为表现记录；仅在候选、删证或gold有问题时打回。'})
        if not supervisor_gate(final_review, ['final_text_no_shortcut', 'all_proofs_cut', 'family_invariants', 'solver_comparison', 'isolation']):
            self.save('final-review-dispute.json', final_review)
            raise RuntimeError('Final family needs GPT adjudication; outputs preserved, export withheld')
        family['machine_review'] = 'passed'
        family['gpt_review'] = 'pending'
        family['release_status'] = 'machine_checked_development_family_pending_gpt'
        self.save('family.internal.json', family)
        self.save('model-inputs.json', inputs)
        self.save('gold.json', golds)
        self.save('solver-results.json', results)
        for name, rows in [('model-inputs', inputs), ('gold', golds), ('solver-results', results)]:
            (self.out / (name + '.jsonl')).write_text(''.join(json.dumps(row, ensure_ascii=False) + '\n' for row in rows), encoding='utf-8')
        self.save('completion.json', {'status': 'completed_pending_gpt_review', 'schema_version': VERSION,
            'roles_executed': sorted({load(p)['role'] for p in (self.out / 'stages').glob('*.runtime.json')}), 'variants': 4, 'diagnostics': 1,
            'structured_solver_successes': sum(r['checks']['strict_structural_success'] for r in results),
            'model_failures_do_not_determine_retention': True, 'calls': self.calls,
            'sdk_version': importlib.metadata.version('deepseek-harness-sdk'),
            'runtime_version': importlib.metadata.version('deepseek-harness-runtime-bin'),
            'human_review': 'not_run', 'split': 'development_only'})

    def close(self):
        for harness in self.pools.values():
            harness.close()
        self.key = ''


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--run-id', default='milestone-001')
    parser.add_argument('--adjudication')
    args = parser.parse_args()
    key = os.environ.get('DEEPSEEK_API_KEY') or getpass.getpass('DeepSeek runtime credential (hidden): ').strip()
    if not key:
        raise RuntimeError('No credential')
    pipeline = Pipeline(key, args.run_id, args.adjudication)
    try:
        pipeline.run()
        print('Milestone pipeline completed; GPT review remains separate.', flush=True)
    except Exception as exc:
        # Runtime diagnostics may include request details; never persist unredacted exceptions.
        safe = str(exc).replace(key, '[REDACTED]')
        safe = re.sub(r'sk-[A-Za-z0-9]{20,}', '[REDACTED]', safe)
        pipeline.save('failure.json', {'type': type(exc).__name__, 'message': safe[:6000], 'calls': pipeline.calls})
        print(json.dumps({'status': 'failed', 'type': type(exc).__name__, 'message': safe[:1200]}, ensure_ascii=True), flush=True)
    finally:
        pipeline.close()


if __name__ == '__main__':
    main()
