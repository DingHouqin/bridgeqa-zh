"""Build the v18 public, read-only Luna/Sol projection.

See [the publication contract](specs/10_最新题库与模型评测发布.md).
The retained v16 files are read only. This is projection and arithmetic,
not semantic regrading, resampling, or a new benchmark release.
"""
from __future__ import annotations

import argparse
import collections
import csv
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'explorer/publication_v18'
VERSION = 'bridgeqa-publication-v18'
MODELS = ('gpt-6-luna', 'gpt-6.1-sol')
PHASES = ('current_r2', 'revised_r1', 'novel_r1', 'bounds_r1')
DIMENSIONS = ('answer', 'logical_proof', 'output_contract')
SHORT = {'pass': 'P', 'fail': 'F', 'needs_review': 'U', 'P': 'P', 'F': 'F', 'U': 'U'}
COUNTS = {'current_r2': 202, 'revised_r1': 16, 'novel_r1': 30, 'bounds_r1': 4}
PUBLIC_FILES = {'questions.public.json', 'inputs.jsonl', 'results.json', 'summary.json', 'results.csv', 'README.md'}
SCOPE = {
    'as_of': '2026-10-27',
    'formal_benchmark_release': False,
    'evaluation_split': 'adaptive_development',
    'source_track': 'synthetic_closed_world',
    'first_completions_only': True,
    'trials_per_question_model': 1,
    'global_no_shortcut_certified': 0,
    'standard_references_public': False,
    'reference_disclosure': '本轮不公开独立标准答案或证明包，不以改名投影替代公开。题目、实际原答、逐维裁决与理由可查。',
    'interpretation': '适应性合成开发与回归记录，非独立测试。声明关系段数、局部依赖和全局无捷径是不同主张。',
    'uncertainty': 'P通过，F失败，U需人工／强智能体复核。U保留固定分母，不计成功；正式点值留空，标签界不是置信区间。',
    'higher_order': '每题每模型仅一次首答，pass@5和pass^5均为空。不同题不能拼成同题五次。',
    'raw_response': '仅公开原始final_response文字，逐字保留非法JSON。未公开事件、会话身份、进程、环境、用量或本机路径。',
    'csv_safety': 'CSV为表格安全投影，潜在公式开头的文本增加单引号前缀；raw_response_spreadsheet_safe不是新的原答。raw_text_sha256始终对应JSON中逐字原答UTF-8。',
    'source_paths': '原始来源路径只作仓库相对审计标识；不代表该原始文件已公开可下载。',
}


def require(ok, message):
    if not ok:
        raise ValueError(message)


def sha_bytes(data):
    return hashlib.sha256(data).hexdigest()


def file_sha(path):
    return sha_bytes(Path(path).read_bytes())


def digest(value):
    return sha_bytes(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode('utf-8'))


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def dumps(value):
    return json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + '\n'


def metric(labels):
    require(labels and all(v in {'P', 'F', 'U'} for v in labels), 'Unknown or empty label set')
    count = collections.Counter(labels)
    n, p, f, u = len(labels), count['P'], count['F'], count['U']
    return {'planned_slots': n, 'P': p, 'F': f, 'U': u,
            'pass@1': {'point_estimate': None if u else p / n,
                       'identification_bounds': {'lower': p / n, 'upper': (p + u) / n},
                       'bounds_are_confidence_intervals': False},
            'pass@5': None, 'pass^5': None}


def aggregate(rows, axes):
    groups = collections.defaultdict(list)
    for row in rows:
        groups[tuple(row[a] for a in axes)].append(row)
    return [{**dict(zip(axes, key)), 'metrics': {
        d: metric([r['labels'][d] for r in group]) for d in DIMENSIONS}}
        for key, group in sorted(groups.items(), key=lambda kv: json.dumps(kv[0], ensure_ascii=False))]


def source_ref(path):
    path = Path(path).resolve()
    require(path.is_relative_to(ROOT), 'Source outside checkout')
    return {'path': path.relative_to(ROOT).as_posix(), 'sha256': file_sha(path)}


def reject_private_reference_fields(value):
    """Reject independent answer/proof packages in the public structured data.

    The actual model's raw response is a string and is not reparsed as a
    reference object. Qualification status is metadata, not a gold answer.
    """
    forbidden = {'gold_answers', 'gold_paths', 'historical_reference', 'gold', 'world',
                 'reference_answers', 'reference_proof', 'expected_status', 'reading_1', 'reading_2',
                 'countermodel_certificates', 'completion_certificate', 'standard_answer', 'standard_proof'}
    if isinstance(value, dict):
        require(not (set(value) & forbidden), 'Independent standard reference fields are not public')
        for item in value.values():
            reject_private_reference_fields(item)
    elif isinstance(value, list):
        for item in value:
            reject_private_reference_fields(item)


def verify_snapshot(questions, results, summary):
    """Standalone validation of exported data, requiring no private evidence."""
    reject_private_reference_fields([questions, results, summary])
    qs, rs = questions['cases'], results['records']
    require(len(qs) == 252 and len(rs) == 504, 'Wrong public grid size')
    by_question = {q['question_key']: q for q in qs}
    require(len(by_question) == 252, 'Duplicate question key')
    require({q['phase'] for q in qs} == set(PHASES), 'Unexpected phase')
    require(collections.Counter(q['phase'] for q in qs) == COUNTS, 'Phase counts changed')
    current = [q for q in qs if q['phase'] == 'current_r2']
    require(collections.Counter(q['partition'] for q in current) == {'primary': 142, 'node': 48, 'control': 12},
            'Current primary/node/control denominator changed')
    public_keys = {'id', 'instruction', 'question', 'contexts', 'output_contract'}
    for q in qs:
        require(set(q['input']) <= public_keys and 'question' in q['input'] and 'contexts' in q['input'],
                'Public input contains undeclared fields')
        require(digest(q['input']) == q['input_sha256'], 'Public input SHA differs')
        require(q['metadata']['global_no_shortcut_status'] == 'not_proven', 'Global certification invented')
        require(q['metadata'].get('declared_hops') in {None, 1, 2, 3, 4}, 'Unexpected declared structural depth')
    pairs = collections.defaultdict(dict)
    for row in rs:
        key, model = row['question_key'], row['model']
        require(key in by_question and model in MODELS and model not in pairs[key], 'Extra/duplicate model slot')
        pairs[key][model] = row
        require(row['input_sha256'] == by_question[key]['input_sha256'], 'Cross-question response')
        require(sha_bytes(row['raw_response'].encode('utf-8')) == row['raw_text_sha256'], 'Raw text changed')
        require(set(row['labels']) == set(DIMENSIONS) and all(v in {'P', 'F', 'U'} for v in row['labels'].values()),
                'Invalid three-dimensional label')
        require(row['labels']['logical_proof'] != 'P' or row['labels']['answer'] == 'P', 'L P without A P')
        require(row['labels']['output_contract'] != 'P' or row['labels']['answer'] == row['labels']['logical_proof'] == 'P',
                'C P without A/L P')
        require(row['n'] == 1 and row['pass@5'] is None and row['pass^5'] is None, 'Invented repeated trials')
        require(row['execution_status'] == 'completed', 'Unexpected execution status')
        require(row['approval'] == {'status': 'accepted', 'approved_by': 'root', 'independent_review': True},
                'Unapproved published grade')
        require(len(row['reviewers']) >= 2 and len(set(row['reviewers'])) == len(row['reviewers']) and
                'root' in row['reviewers'] and bool(row['rationale'].strip()), 'Review provenance missing')
        try:
            json.loads(row['raw_response'])
            parsed = True
        except (json.JSONDecodeError, ValueError):
            parsed = False
        require(row['json_valid'] is parsed, 'JSON validity flag changed')
    require(set(pairs) == set(by_question) and all(set(v) == set(MODELS) for v in pairs.values()), 'Incomplete two-model grid')
    require(sum(not r['json_valid'] for r in rs) == 20 and
            all(r['model'] == 'gpt-6-luna' for r in rs if not r['json_valid']), 'Raw invalid JSON count changed')
    ambiguous = [q for q in qs if q['qualification']['target_ambiguity']]
    require({q['case_id'] for q in ambiguous} == {
        'GOV-3A-necessary_missing', 'GOV-4A-necessary_missing',
        'SCI-3B-necessary_missing', 'SCI-4B-necessary_missing'}, 'Target ambiguity overlay missing')
    for q in ambiguous:
        require(q['qualification']['gold_status'] == 'requires_review', 'Historical gold shown as unique accepted truth')
        require(all(r['labels']['answer'] == 'U' for r in pairs[q['question_key']].values()), 'Ambiguous target became A P/F')
    require(summary['cohorts'] == aggregate(rs, ('phase', 'model', 'partition')), 'Summary does not match published rows')
    require(summary['totals'] == {'questions': 252, 'responses': 504, 'models': 2, 'technical_failures': 0,
                                  'invalid_json': 20, 'trials_per_question_model': 1}, 'Totals changed')
    for q in qs:
        require(not any(k.startswith('gold') or k in {'world', 'expected_status', 'reviewers', 'rationale'}
                        for k in q['input']), 'Reference leaked into clean input')
    return {'questions': len(qs), 'responses': len(rs), 'invalid_json_preserved': 20,
            'paired_questions': len(pairs), 'target_ambiguities': len(ambiguous), 'status': 'pass'}


def scan_public_text(text):
    """Fail publication rather than silently redact or rewrite an answer."""
    patterns = [r'\bsk-[A-Za-z0-9_-]{12,}', r'(?i)Bearer\s+[A-Za-z0-9_.-]{16,}',
                r'(?i)[A-Z]:[\\/](?:Users|Program\sFiles|个人经历)', r'(?i)C:\\\\Users\\\\',
                r'gh[pousr]_[A-Za-z0-9]{20,}', r'github_pat_[A-Za-z0-9_]{20,}']
    require(not any(re.search(pattern, text) for pattern in patterns), 'Potential credential or local path in public projection')


def spreadsheet_safe(value):
    """Do not let a CSV consumer execute model text as a spreadsheet formula."""
    if isinstance(value, str) and value.lstrip(' \t\r\n').startswith(('=', '+', '-', '@')):
        return "'" + value
    return value


def load_analyzer():
    # Reuse frozen binding checks. No execution or semantic grading is invoked.
    sys.dont_write_bytecode = True
    path = ROOT / 'src/luna_sol_v16/analyze_delivery.py'
    spec = importlib.util.spec_from_file_location('publication_v18_frozen_analyzer', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def build(out=OUT):
    out = Path(out).resolve()
    require(out == OUT.resolve(), 'Output must be the dedicated explorer/publication_v18 directory')
    if out.exists() and any(out.iterdir()):
        require((out / 'manifest.json').is_file(), 'Refuse a non-publication output directory')
    work = ROOT / 'workspace/luna-sol-v16'
    acceptance_path = work / 'root-final-acceptance-r1.json'
    acceptance = read(acceptance_path)
    grade_path = ROOT / acceptance['grade_map']['path']
    require(file_sha(grade_path) == acceptance['grade_map']['sha256'], 'Root-accepted grade-map changed')
    A = load_analyzer()
    specs = [(phase, work / 'runs' / (phase + '-' + model) / 'plan.json') for phase in PHASES for model in MODELS]
    grid, bindings = A.load_grid(specs, root=ROOT)
    bound = A.attach_grades(grid, read(grade_path))
    require(len(bound) == 504 and all(r['grade'] for r in bound), 'Not all slots have approved grades')
    sources = {source_ref(p)['path']: source_ref(p) for p in [acceptance_path, grade_path,
               work / 'analysis-r1/summary.json', work / 'target-ambiguity-qualification-r1.json']}
    ambiguous = {r['id']: r for r in read(work / 'target-ambiguity-qualification-r1.json')['records']}
    case_lookup, qualification, file_lookup = {}, {}, {}
    for phase, plan_path in specs:
        plan = read(plan_path)
        dataset_path = ROOT / plan['dataset']['path']
        qual_path = ROOT / plan['input_qualification']['path']
        require(file_sha(qual_path) == plan['input_qualification']['sha256'], 'Frozen qualification changed')
        model = plan['configuration']['model']
        file_lookup[(phase, model)] = plan_path
        for path_ in [plan_path, plan_path.parent / 'records-initial.json', dataset_path, qual_path]:
            ref = source_ref(path_); sources[ref['path']] = ref
        qs = {q['id']: q for q in read(qual_path)['records']}
        for c in read(dataset_path):
            key = phase + ':' + c['id']
            require(c['id'] in qs, 'No input qualification')
            q = qs[c['id']]
            require(c['input_sha256'] == q['input_sha256'] == digest(c['clean_input']), 'Qualification input changed')
            require(q['gold_sha256'] == digest({'status': c['expected_status'], 'answers': c['gold_answers']}),
                    'Reference differs from frozen gold')
            if key in case_lookup:
                require(case_lookup[key] == c, 'Two-model case data differs')
            case_lookup[key], qualification[key] = c, q
    questions = []
    for key, c in sorted(case_lookup.items()):
        phase = key.split(':', 1)[0]
        q = qualification[key]
        amb = ambiguous.get(c['id']) if phase == 'current_r2' else None
        qual = {k: q.get(k) for k in ('gold_status', 'hop_claim_status', 'declared_hops', 'global_no_shortcut_status', 'scope')}
        qual['target_ambiguity'] = bool(amb)
        if amb:
            require(amb['input_sha256'] == c['input_sha256'], 'Ambiguity overlay refers to stale input')
            qual['historical_gold_status'] = qual['gold_status']
            qual['gold_status'] = 'requires_review'
            qual['reason'] = '题意可解释为当前确认集合或未知补全后的真实集合，历史engine gold不能当作唯一正确答案。'
        metadata = {k: c.get(k) for k in ('family_id', 'domain', 'condition', 'source_track', 'split')}
        metadata.update(declared_hops=c.get('hops'), hop_claim_status=q.get('hop_claim_status'),
                        global_no_shortcut_status='not_proven')
        questions.append({'question_key': key, 'case_id': c['id'], 'public_id': c['clean_input']['id'],
                          'phase': phase, 'partition': c['partition'], 'metadata': metadata,
                          'input_sha256': c['input_sha256'], 'input': c['clean_input'], 'qualification': qual})
    results = []
    for row in sorted(bound, key=lambda r: (r['phase'], r['case_id'], r['model'])):
        response_path = ROOT / row['response']['path']
        response = read(response_path)
        raw = response['final_response']
        require(isinstance(raw, str), 'Final response must be original text')
        try:
            json.loads(raw); valid_json = True
        except (json.JSONDecodeError, ValueError):
            valid_json = False
        key = row['phase'] + ':' + row['case_id']
        g = row['grade']
        result = {k: row[k] for k in ('phase', 'case_id', 'model', 'trial_id', 'input_sha256', 'execution_status', 'partition', 'domain', 'family_id', 'hops', 'condition')}
        result.update(question_key=key, labels={d: SHORT[row['verdicts'][d]] for d in DIMENSIONS},
                      rationale=g['rationale'], reviewers=g['reviewers'], approval=g['approval'],
                      raw_response=raw, raw_text_sha256=sha_bytes(raw.encode('utf-8')),
                      response_file_sha256=row['response_sha256'], json_valid=valid_json,
                      n=1, **{'pass@5': None, 'pass^5': None},
                      source={'response_path': row['response']['path'], 'grade_map_path': source_ref(grade_path)['path'],
                              'plan_path': source_ref(file_lookup[row['phase'], row['model']])['path']})
        results.append(result)
    frozen_summary = read(work / 'analysis-r1/summary.json')
    cohorts = aggregate(results, ('phase', 'model', 'partition'))
    by_frozen = {(r['phase'], r['model'], r['partition']): r['metrics'] for r in frozen_summary['cohorts']}
    for cohort in cohorts:
        original = by_frozen[cohort['phase'], cohort['model'], cohort['partition']]
        for d in DIMENSIONS:
            for label in ('planned_slots', 'P', 'F', 'U'):
                require(cohort['metrics'][d][label] == original[d][label], 'Cohort counts differ from frozen accepted analysis')
            fmetric, m = original[d]['pass@1'], cohort['metrics'][d]['pass@1']
            pnt = fmetric['point_estimate']
            require(m['point_estimate'] == (None if pnt is None else pnt['value']), 'Point estimate policy changed')
            require(all(m['identification_bounds'][k] == fmetric['identification_bounds'][k]['value'] for k in ('lower', 'upper')),
                    'Label bounds differ from frozen summary')
    qpayload = {'version': VERSION, 'scope': SCOPE, 'cases': questions}
    rpayload = {'version': VERSION, 'scope': SCOPE, 'records': results}
    summary = {'version': VERSION, 'scope': SCOPE,
               'totals': {'questions': 252, 'responses': 504, 'models': 2, 'technical_failures': 0,
                          'invalid_json': sum(not r['json_valid'] for r in results), 'trials_per_question_model': 1},
               'phase_counts': dict(collections.Counter(q['phase'] for q in questions)),
               'cohorts': cohorts, 'by_model': aggregate(results, ('model',)),
               'by_domain': aggregate(results, ('phase', 'model', 'partition', 'domain')),
               'by_declared_hops': aggregate(results, ('phase', 'model', 'partition', 'hops')),
               'by_family': aggregate(results, ('phase', 'model', 'partition', 'family_id')),
               'by_condition': aggregate(results, ('phase', 'model', 'partition', 'condition'))}
    verification = verify_snapshot(qpayload, rpayload, summary)
    exported = {'questions.public.json': dumps(qpayload),
                'inputs.jsonl': ''.join(json.dumps(q['input'], ensure_ascii=False, separators=(',', ':'), allow_nan=False) + '\n'
                                        for q in questions),
                'results.json': dumps(rpayload), 'summary.json': dumps(summary)}
    stream = io.StringIO(newline='')
    columns = ['question_key', 'phase', 'partition', 'case_id', 'model', 'domain', 'family_id', 'hops', 'condition',
               'answer', 'logical_proof', 'output_contract', 'rationale', 'raw_text_sha256', 'response_file_sha256', 'json_valid',
               'raw_response_spreadsheet_safe', 'raw_response_csv_prefix_applied']
    writer = csv.DictWriter(stream, columns, lineterminator='\n'); writer.writeheader()
    for r in results:
        csv_row = {k: r['labels'][k] if k in DIMENSIONS else r[k] for k in columns if not k.startswith('raw_response_')}
        csv_row['raw_response_spreadsheet_safe'] = spreadsheet_safe(r['raw_response'])
        csv_row['raw_response_csv_prefix_applied'] = csv_row['raw_response_spreadsheet_safe'] != r['raw_response']
        writer.writerow({k: spreadsheet_safe(v) for k, v in csv_row.items()})
    exported['results.csv'] = '\ufeff' + stream.getvalue()
    exported['README.md'] = '''# 最新题目与Luna/Sol逐题表现（v18公开投影）

本目录是2026-10-27冻结v16开发记录的只读公开投影。252项任务、两个模型各一次首答，共504份原始作答。当前142道主问题、48道节点诊断及12道状态对照分开，另有16条修订、30条新算子与4条部分信息边界题。

- [清洁盲解输入](inputs.jsonl)：252行，每行严格为实际单题clean_input，不含元数据、资格、参考或评分标签。被测模型每次只接收本次选定的一行，不能把全文件一次输入。
- [公开审阅索引](questions.public.json)：`cases[].input`逐字保持实际clean_input，SHA按排序键紧凑UTF-8 JSON计算。索引另含资格与审阅元数据，因此整个索引不能作为盲解输入包。
- [逐槽首答与裁决](results.json)：每条原始`final_response`保留在`raw_response`字符串，不修复20份非法JSON。`raw_text_sha256`只覆盖该字符串UTF-8字节；`response_file_sha256`覆盖原始完整response文件，两者不是同一种哈希。
- [逐题下载表](results.csv)：UTF-8 BOM CSV，504行。所有潜在公式开头（忽略前导空白后为`=+-@`）的文本增加单引号前缀，防止表格软件执行模型文字。列`raw_response_spreadsheet_safe`是原答的表格安全投影，`raw_response_csv_prefix_applied`说明是否加前缀，JSON原答始终不改，`raw_text_sha256`始终对应JSON原答的UTF-8字节。
- [分层汇总](summary.json)：按固定分母复算并对照冻结汇总，不重新语义判分。主问题、节点、状态对照及开发阶段分别列出。
- [来源与输出哈希](manifest.json)：原始来源路径仅作仓库相对审计标识，不代表未公开的workspace文件可下载。

本轮不公开独立标准答案或证明包，也不将私有参考改名投影发布。公开内容仅含题目、实际模型原答、逐维裁决及理由、资格状态和统计。四道旧缺证题的资格标记说明题意有歧义，两个模型的A均为U，历史engine答案没有被提升为唯一正确答案。公开快照不能独立重做语义判题；语义裁决仍来自已经独立审核并由Root接收的本地记录。

A为最终答案及状态，L在A通过后要求充分、真实且一致的外显证明，C在A/L通过后要求完整输出合同。P通过，F失败，U需人工／强智能体复核。U保留分母且不计成功；有U的正式点值为空，标签上下界不是置信区间。所有同题模型组合n=1，pass@5与pass^5均为空，不能用不同题拼凑五次。

这是适应性合成开发回归，不是held-out测试。关系段数为声明结构，不是已认证的最短推理步数，全局无捷径认证为0。仅公开最终可见答卷，不公开模型内部推理、原生事件、session、进程、本机环境或凭证。

[导出器](../build_latest_publication.py)只读取已验收的本地冻结证据并做白名单投影；运行完整构建需要私有工作记录，公开CI可使用`--verify-existing`离线核对该快照，无需读取任何独立标准答案文件。发布合同见[规格10](../specs/10_最新题库与模型评测发布.md)，本轮公开结果说明见[逐题表现说明](../../model-testing/luna_sol_v18_publication.md)，评分指标与过程见[评分指南](../../evaluation/SCORING_GUIDE.md)，评分实现见[评分器](../../evaluation/pass_metrics_v15/scorer.py)。
'''
    for value in exported.values():
        scan_public_text(value)
    require(set(exported) == PUBLIC_FILES, 'Unexpected file in public export')
    out.mkdir(parents=True, exist_ok=True)
    for name, value in exported.items():
        (out / name).write_text(value, encoding='utf-8', newline='\n')
    manifest = {'version': VERSION, 'as_of': '2026-10-27', 'scope': SCOPE,
                'sources': sorted(sources.values(), key=lambda r: r['path']),
                'response_sources': [{'question_key': r['question_key'], 'model': r['model'],
                                      'path': r['source']['response_path'], 'sha256': r['response_file_sha256'],
                                      'raw_text_sha256': r['raw_text_sha256']} for r in results],
                'builder': source_ref(Path(__file__)), 'verification': verification,
                'files': {name: file_sha(out / name) for name in sorted(exported)}}
    scan_public_text(dumps(manifest))
    (out / 'manifest.json').write_text(dumps(manifest), encoding='utf-8', newline='\n')
    print(json.dumps({'output': str(out.relative_to(ROOT)), **verification,
                      'bytes': {n: (out / n).stat().st_size for n in sorted(exported)}}, ensure_ascii=False))


def verify_existing(out=OUT):
    out = Path(out)
    m = read(out / 'manifest.json')
    require(set(m['files']) == PUBLIC_FILES, 'Public manifest must exclude independent reference packages')
    for name, sha in m['files'].items():
        require(file_sha(out / name) == sha, 'Published file hash mismatch: ' + name)
        scan_public_text((out / name).read_text(encoding='utf-8'))
    verification = verify_snapshot(read(out / 'questions.public.json'), read(out / 'results.json'), read(out / 'summary.json'))
    inputs = [json.loads(line) for line in (out / 'inputs.jsonl').read_text(encoding='utf-8').splitlines()]
    require(inputs == [q['input'] for q in read(out / 'questions.public.json')['cases']], 'Clean JSONL differs from actual per-question inputs')
    require(m['verification'] == verification, 'Manifest verification differs')
    require(m['builder']['sha256'] == file_sha(Path(__file__)), 'Builder changed after snapshot generation')
    print(json.dumps(verification, ensure_ascii=False))
    return verification


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--verify-existing', action='store_true', help='Validate only checked-in projections without private inputs')
    args = parser.parse_args()
    verify_existing() if args.verify_existing else build()
