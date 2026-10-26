"""Pinned round-specific skill accounting, reusing the original pilot analyzer.

The R1 analyzer is not modified. Cross-round tables include only shared case IDs
with unchanged binary references; newly added cases are never pooled as gains.
"""
from __future__ import annotations

import argparse
import collections
import hashlib
import json
import re
from pathlib import Path

try:
    from . import analyze as BASE
except ImportError:
    import analyze as BASE

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
read, digest, write_once = BASE.read, BASE.digest, BASE.write_once
indexed_references = BASE.indexed_references
_forbidden_reference_fields = BASE._forbidden_reference_fields


def _selected_prompt(kind, arm, protocol, violations):
    """Resolve only the frozen role files inside an allowed project skill root."""
    generic = protocol['generic_prompts'][kind]
    if arm == 'generic':
        return generic, {}
    selected = protocol['skills'][kind]
    configured = protocol.get('skill_root', 'src/quality_v3/skills')
    if not isinstance(configured, str):
        violations.append({'issue': 'invalid_protocol_skill_root'})
        return generic, selected
    root = (ROOT / configured).resolve()
    original = (HERE / 'skills').resolve()
    revisions = (HERE / 'skill-revisions').resolve()
    if root != original and not root.is_relative_to(revisions):
        violations.append({'issue': 'protocol_skill_root_outside_allowed_directories',
                           'configured': configured})
        return generic, selected
    parts = []
    for relative, expected in selected.items():
        path = (root / relative).resolve()
        if not path.is_relative_to(root):
            violations.append({'issue': 'selected_skill_path_escapes_round_root', 'file': relative})
            continue
        if not path.is_file():
            violations.append({'issue': 'selected_skill_file_missing', 'file': relative,
                               'skill_root': configured})
            continue
        data = path.read_bytes()
        if hashlib.sha256(data).hexdigest() != expected:
            violations.append({'issue': 'selected_skill_content_hash_changed', 'file': relative,
                               'skill_root': configured})
        parts.append('项目技能 ' + relative + '\n' + data.decode('utf-8'))
    return generic + '\n\n' + '\n\n'.join(parts), selected


def _integrity(batch, runtime, cases, references, jobs, protocol, rows):
    batch, runtime = Path(batch), Path(runtime)
    violations, warnings = [], []
    stage_prefix = protocol.get('request_stage_prefix', 'quality-')
    if not isinstance(stage_prefix, str) or not re.fullmatch(r'[A-Za-z0-9_-]+', stage_prefix):
        violations.append({'issue': 'invalid_frozen_request_stage_prefix'})
        stage_prefix = 'INVALID-'
    manifest = read(batch/'manifest.json')
    for key, value in [('cases_sha256',cases),('references_sha256',references),('jobs_sha256',jobs),('protocol_sha256',protocol)]:
        if manifest.get(key) != digest(value): violations.append({'issue':'frozen_manifest_hash_mismatch','field':key})
    gate_path = batch/'reference_review.json'
    if gate_path.exists():
        gate = read(gate_path)
        if gate.get('status') != 'approved' or gate.get('reviewer_kind') != 'independent_gpt_subagent':
            violations.append({'issue':'independent_reference_gate_not_approved'})
        for field in ('cases_sha256','references_sha256','jobs_sha256','protocol_sha256','request_contracts_sha256'):
            if gate.get(field) != manifest.get(field):violations.append({'issue':'independent_gate_hash_mismatch','field':field})
    else: violations.append({'issue':'independent_reference_gate_missing'})
    case_map = {c['case_id']:c for c in cases}; refs=indexed_references(references)
    if len(case_map)!=len(cases):violations.append({'issue':'duplicate_case_ids'})
    if set(refs)!=set(case_map):violations.append({'issue':'reference_case_coverage_mismatch'})
    for c in cases:
        leaks=_forbidden_reference_fields(c['payload'])
        if leaks:violations.append({'issue':'hidden_reference_field_in_frozen_payload','case_id':c['case_id'],'fields':leaks})
        if c['kind']=='review': expected={'question','query','contexts','candidate','review_contract'}
        elif c['kind']=='scoring': expected={'task','question','query','contexts','candidate_response','visible_entity_bindings','reference_claims','contract'}
        else: expected={'question','query','contexts'}
        if set(c['payload'])!=expected:violations.append({'issue':'unexpected_frozen_payload_fields','case_id':c['case_id']})
    payload_splits=collections.defaultdict(set)
    for c in cases:payload_splits[(c['kind'],digest(c['payload']))].add(c['split'])
    overlaps=[{'kind':k[0],'payload_sha256':k[1],'splits':sorted(v)} for k,v in payload_splits.items() if len(v)>1]
    if overlaps:violations.append({'issue':'identical_payload_crosses_diagnostic_and_forward_split','items':overlaps})
    contracts_path = batch/'request-contracts.frozen.json'
    pinned = read(contracts_path) if contracts_path.exists() else None
    if pinned is not None and manifest.get('request_contracts_sha256') != digest(pinned):
        violations.append({'issue':'frozen_manifest_hash_mismatch','field':'request_contracts_sha256'})
    if pinned is not None and isinstance(pinned, dict) and 'contracts' in pinned: pinned=pinned['contracts']
    if isinstance(pinned, list):pinned={digest(x['job'])[:24]:x for x in pinned}
    if pinned is None:warnings.append('No per-job request-contract snapshot: expected requests additionally checked against frozen case/protocol and hash-pinned skills; this is weaker than a resolved pre-run contract.')
    expected_requests={}
    for job in jobs:
        cid=job['case_id'];jid=digest(job)[:24];c=case_map[cid]
        if c['kind']!=job['kind']:violations.append({'issue':'job_kind_mismatch','job':job})
        prompt,selected=_selected_prompt(c['kind'],job['arm'],protocol,violations)
        exp={'job':job,'split':c['split'],'role':c['kind'],'payload':c['payload'],
             'schema':protocol['schemas'][c['kind']],'prompt':prompt,'selected_skill_files':selected}
        if pinned is not None:
            snap=pinned.get(jid,pinned.get(digest(job),{}))
            if not snap:violations.append({'issue':'frozen_request_contract_missing_job','job':job})
            else:
                pairs=[('job',job),('split',c['split']),('role',c['kind']),('payload',c['payload']),
                       ('schema',protocol['schemas'][c['kind']]),('prompt',prompt),('selected_skill_files',selected)]
                for name,value in pairs:
                    aliases={'payload':('payload','input'),'schema':('schema','output_schema'),'prompt':('prompt','resolved_prompt','skill')}
                    names=aliases.get(name,(name,));present=next((n for n in names if n in snap),None)
                    hnames={'payload':('payload_sha256','input_sha256'),'schema':('schema_sha256',),'prompt':('prompt_sha256','resolved_prompt_sha256')}.get(name,())
                    hfield=next((n for n in hnames if n in snap),None)
                    if present is not None:
                        if snap[present]!=value:violations.append({'issue':'frozen_request_contract_differs','job':job,'field':name})
                        if name in ('payload','schema','prompt'):exp[name]=snap[present]
                    elif hfield is not None:
                        if snap[hfield]!=digest(value):violations.append({'issue':'frozen_request_contract_hash_differs','job':job,'field':name})
                    elif name not in ('split','role'):
                        violations.append({'issue':'frozen_request_contract_field_missing','job':job,'field':name})
        expected_requests[stage_prefix+jid]=exp
    observed=set();sessions={};counts=collections.Counter();models=collections.Counter();sdk=collections.Counter()
    by_kind=collections.defaultdict(collections.Counter);event_types=collections.Counter()
    for path in sorted(runtime.rglob('*.request.json')):
        m=re.fullmatch(r'(.+)\.attempt-([0-2])\.request\.json',path.name)
        if not m or m[1] not in expected_requests:
            violations.append({'issue':'unexpected_runtime_request','file':str(path.relative_to(runtime))});continue
        stage,attempt=m[1],int(m[2]);exp=expected_requests[stage];kind=exp['job']['kind'];observed.add(stage)
        req=read(path);counts['request_attempts']+=1;by_kind[kind]['request_attempts']+=1
        for field,value in [('role',exp['role']),('input',exp['payload']),('output_schema',exp['schema']),('skill',exp['prompt'])]:
            if req.get(field)!=value:violations.append({'issue':'runtime_request_differs_from_frozen_contract','file':str(path.relative_to(runtime)),'field':field})
        if set(req)-{'role','skill','input','output_schema','model','runtime_contract','format_repair'}:
            violations.append({'issue':'unexpected_runtime_request_fields','file':str(path.relative_to(runtime))})
        models[str(req.get('model'))]+=1;sdk[str(req.get('runtime_contract',{}).get('sdk_version','unavailable'))]+=1
        if req.get('runtime_contract',{}).get('tools')!='all_model_tools_disabled':violations.append({'issue':'tools_not_recorded_disabled','file':str(path.relative_to(runtime))})
        response_path=path.with_name(path.name.replace('.request.json','.response.json'))
        if not response_path.exists():counts['request_without_response']+=1;continue
        response=read(response_path);counts['response_attempts']+=1;by_kind[kind]['response_attempts']+=1
        sid=response.get('session_id')
        expected_sid='bridgeqa-v2-'+digest({'stage':stage,'request':req,'attempt':attempt})[:28]
        if sid!=expected_sid:violations.append({'issue':'response_session_not_new_request_identity','file':str(path.relative_to(runtime))})
        if sid in sessions:violations.append({'issue':'session_reused_across_attempts_or_cases','session_id':sid})
        if sid:sessions[sid]=str(path.relative_to(runtime))
        if response.get('request_hash')!=digest(req):violations.append({'issue':'response_request_hash_mismatch','file':str(path.relative_to(runtime))})
        inbox=[]
        for event in response.get('events',[]):
            event_types[event.get('type','unknown')]+=1
            if event.get('type')=='agent/inbox/spliced':
                for item in event.get('data',{}).get('inserted',[]):
                    for content in item.get('content',[]):
                        if content.get('type')=='text':inbox.append(content.get('text'))
        if len(inbox)!=1:violations.append({'issue':'runtime_inbox_not_exactly_one_request','file':str(path.relative_to(runtime)),'count':len(inbox)})
        else:
            try:same=json.loads(inbox[0])==req
            except (ValueError,TypeError):same=False
            if not same:violations.append({'issue':'runtime_inbox_differs_from_persisted_request','file':str(path.relative_to(runtime))})
    known={digest(j):j for j in jobs};seen=set()
    for row in rows:
        jid=digest(row['job'])
        if jid not in known or jid in seen:violations.append({'issue':'unexpected_or_duplicate_result_job','job':row['job']});continue
        seen.add(jid);stage=stage_prefix+jid[:24];exp=expected_requests[stage]
        if row['status']=='completed':
            if row.get('input_hash')!=digest(exp['payload']):violations.append({'issue':'completed_result_input_hash_mismatch','job':row['job']})
            parsed=list(runtime.glob('worker-*/calls/'+stage+'.parsed.json'))
            if len(parsed)!=1 or read(parsed[0])!=row.get('answer'):violations.append({'issue':'completed_result_differs_from_parsed_response','job':row['job']})
        if row['status'] not in ('completed','protocol_failure','technical_failure'):
            violations.append({'issue':'unexpected_result_status','job':row['job'],'status':row['status']})
    counts['scheduled_jobs']=len(jobs);counts['scheduled_stages_with_request']=len(observed)
    counts['result_rows']=len(rows);counts['not_run']=len(jobs)-len(seen);counts['unique_response_sessions']=len(sessions)
    for field in ('technical_failure_files','format_error_files'):
        suffix='*.technical-failure.json' if field.startswith('technical') else '*.format-error.json'
        counts[field]=len(list(runtime.rglob(suffix)))
    counts['extra_request_attempts_over_started_stages']=counts['request_attempts']-len(observed)
    code_changes=[]
    for name,expected in protocol.get('code_sha256',{}).items():
        path=ROOT/name
        actual=hashlib.sha256(path.read_bytes()).hexdigest() if path.exists() else None
        if actual!=expected:code_changes.append({'file':name,'frozen_sha256':expected,'current_sha256':actual})
    if code_changes:violations.append({'issue':'code_changed_since_protocol_freeze','files':code_changes})
    return {'version':'quality-v3-integrity-v1','counts':dict(counts),'by_kind':{k:dict(v) for k,v in by_kind.items()},
        'model_alias_attempt_counts':dict(models),'sdk_version_attempt_counts':dict(sdk),'runtime_event_types':dict(event_types),
        'per_job_resolved_request_contract_available':pinned is not None,
        'violations':violations,'warnings':warnings,'all_observed_checks_pass':not violations,
        'case_split_counts':dict(collections.Counter(c['kind']+'/'+c['split'] for c in cases)),
        'formal_release':False,
        'limits':['This audit covers persisted requests, actual runtime inbox events and response identities; provider internals are not inspectable.',
                  'Only independently adjudicated references support accuracy denominators; inventory proposals are not reference facts.']}



def _accept_inventory_extensions(check, cases):
    # Later inventory tasks explicitly declare pending edges and literal focus
    # windows. This adapter recognizes exactly that frozen input contract; the
    # base audit still verifies every request byte and hidden-reference field.
    allowed = {'question', 'query', 'contexts', 'requested_edges',
               'entity_bindings', 'focus_windows', 'task_state'}
    extended = {c['case_id']: c for c in cases if c['kind'] == 'inventory'
                and set(c['payload']) == allowed}
    kept, acknowledged = [], []
    for violation in check['violations']:
        if (violation.get('issue') == 'unexpected_frozen_payload_fields'
                and violation.get('case_id') in extended):
            acknowledged.append({'case_id': violation['case_id'],
                'recognized_contract': 'inventory_pending_claims_and_literal_focus_windows',
                'fields': sorted(allowed), 'independent_reference_labels': False})
        else:
            kept.append(violation)
    check['violations'] = kept
    check['recognized_frozen_inventory_extensions'] = acknowledged
    check['all_observed_checks_pass'] = not kept
    return check


def load_snapshot(batch, runtime):
    batch, runtime = Path(batch), Path(runtime)
    cases, references, jobs, protocol = (read(batch / name) for name in
        ('cases.frozen.json', 'references.frozen.json', 'jobs.frozen.json', 'protocol.frozen.json'))
    rows = [read(p) for p in sorted((runtime / 'results').glob('*.json'))]
    return {'cases': cases, 'references': references, 'jobs': jobs,
            'protocol': protocol, 'rows': rows}


def _subset_counts(snapshot, eligible):
    """Count common case measurements by kind/arm, without merging new cases."""
    cases = {c['case_id']: c for c in snapshot['cases']}
    refs = BASE.indexed_references(snapshot['references'])
    actual = {digest(r['job']): r for r in snapshot['rows']}
    groups = {}
    case_sets = collections.defaultdict(set)
    for job in snapshot['jobs']:
        case = cases[job['case_id']]
        identity = (case['kind'], case['case_id'])
        if identity not in eligible:
            continue
        key = case['kind'] + '/' + job['arm']
        c = groups.setdefault(key, collections.Counter())
        case_sets[key].add(case['case_id'])
        c['scheduled'] += 1
        expected = BASE.validity(refs[case['case_id']])
        c['valid_trials' if expected else 'invalid_trials'] += 1
        row = actual.get(digest(job), {'status': 'not_run'})
        c[row['status']] += 1
        if row['status'] != 'completed':
            continue
        decision = BASE.model_decision(case['kind'], row['answer'])
        BASE.update_decision(c, 'raw_model_', decision, expected)
        program, disposition = BASE.program_decision(case['kind'], case, row)
        c['program_disposition:' + disposition] += 1
        BASE.update_decision(c, 'program_', program, expected)
    result = {}
    for key, c in sorted(groups.items()):
        for prefix in ('raw_model_', 'program_'):
            for metric in ('unsafe_accept', 'false_block', 'correct_disposition',
                           'needs_adjudication', 'decided', 'valid_decided', 'invalid_decided'):
                c.setdefault(prefix + metric, 0)
        for field in ('completed', 'protocol_failure', 'technical_failure', 'not_run'):
            c.setdefault(field, 0)
        result[key] = {'shared_unique_cases': len(case_sets[key]), 'counts': dict(c)}
    return result


def _validate_snapshot_jobs(snapshot):
    cases = {c['case_id']: c for c in snapshot['cases']}
    if len(cases) != len(snapshot['cases']):
        raise ValueError('Duplicate case IDs in round comparison')
    jobs = {digest(j): j for j in snapshot['jobs']}
    if len(jobs) != len(snapshot['jobs']):
        raise ValueError('Duplicate scheduled job in round comparison')
    actual = [digest(r['job']) for r in snapshot['rows']]
    if len(set(actual)) != len(actual) or set(actual) - set(jobs):
        raise ValueError('Unexpected or duplicate result job in round comparison')
    if set(BASE.indexed_references(snapshot['references'])) != set(cases):
        raise ValueError('Reference coverage mismatch in round comparison')
    for j in snapshot['jobs']:
        if j['case_id'] not in cases or j['kind'] != cases[j['case_id']]['kind']:
            raise ValueError('Job/case mismatch in round comparison')


def round_to_round(previous, current):
    """Descriptive shared-case accounting; never treats changed case mix as gain."""
    _validate_snapshot_jobs(previous)
    _validate_snapshot_jobs(current)
    p_cases = {(c['kind'], c['case_id']): c for c in previous['cases']}
    c_cases = {(c['kind'], c['case_id']): c for c in current['cases']}
    p_refs = BASE.indexed_references(previous['references'])
    c_refs = BASE.indexed_references(current['references'])
    common = set(p_cases) & set(c_cases)
    eligible = set()
    excluded, shared = [], []
    for kind, cid in sorted(common):
        if kind == 'inventory':
            excluded.append({'kind': kind, 'case_id': cid,
                             'reason': 'inventory_is_exploratory_not_accuracy'})
            continue
        p_ref = BASE.validity(p_refs[cid])
        c_ref = BASE.validity(c_refs[cid])
        if p_ref is None or c_ref is None or p_ref != c_ref:
            excluded.append({'kind': kind, 'case_id': cid,
                             'reason': 'reference_unadjudicated_or_changed',
                             'previous_reference': p_ref, 'current_reference': c_ref})
            continue
        eligible.add((kind, cid))
        shared.append({'kind': kind, 'case_id': cid,
            'previous_split': p_cases[(kind, cid)]['split'],
            'current_split': c_cases[(kind, cid)]['split'],
            'expected_valid': c_ref,
            'identical_payload': p_cases[(kind, cid)]['payload'] == c_cases[(kind, cid)]['payload'],
            'identical_output_schema': previous['protocol']['schemas'][kind] == current['protocol']['schemas'][kind],
            'identical_generic_prompt': previous['protocol']['generic_prompts'][kind] == current['protocol']['generic_prompts'][kind]})
    schemas_equal = {kind: previous['protocol']['schemas'].get(kind) == current['protocol']['schemas'].get(kind)
                     for kind in sorted({k for k, _ in eligible})}
    previous_counts = _subset_counts(previous, eligible)
    current_counts = _subset_counts(current, eligible)
    return {'comparison_scope': 'same_kind_and_case_id_with_unchanged_adjudicated_reference_only',
        'previous_round': previous['protocol'].get('round', previous['protocol'].get('version')),
        'current_round': current['protocol'].get('round', current['protocol'].get('version')),
        'shared_eligible_cases': shared,
        'excluded_shared_cases': excluded,
        'new_current_cases_not_pooled': [{'kind': k, 'case_id': cid} for k, cid in sorted(set(c_cases) - set(p_cases))],
        'previous_only_cases_not_pooled': [{'kind': k, 'case_id': cid} for k, cid in sorted(set(p_cases) - set(c_cases))],
        'previous_shared_subset': previous_counts,
        'current_shared_subset': current_counts,
        'output_schema_equal_by_kind': schemas_equal,
        'all_shared_payloads_identical': all(row['identical_payload'] for row in shared),
        'limits': [
            'Only the listed common cases enter these tables; newly added cases have separate within-round results.',
            'Shared case IDs are not enough to establish identical protocols: payload, schema and generic-prompt equality are shown explicitly.',
            'R1 and later rounds may use different output fields or contracts; changed-contract comparisons are descriptive regressions, not skill-only causal effects.',
            'Repeated review calls are repeated measurements of a case, not independent new questions.',
            'Do not compare different new-case mixtures as an overall improvement rate.',
            'The generic-versus-skills contrast remains the within-round comparison with shared contracts and program gates.'],
        'formal_release': False}


def analyze(batch, runtime, out, previous_batch=None, previous_runtime=None):
    current = load_snapshot(batch, runtime)
    cases, refs, jobs, protocol, rows = (current[k] for k in
        ('cases', 'references', 'jobs', 'protocol', 'rows'))
    summary = BASE.summarize(cases, refs, jobs, rows)
    check = _integrity(batch, runtime, cases, refs, jobs, protocol, rows)
    check = _accept_inventory_extensions(check, cases)
    summary['analysis_round'] = protocol.get('round', protocol.get('version'))
    summary['frozen_skill_root'] = protocol.get('skill_root', 'src/quality_v3/skills')
    summary['integrity_all_observed_checks_pass'] = check['all_observed_checks_pass']
    summary['iteration_policy'] = {
        'round_results_stored_separately': True,
        'regression_splits_are_independent_forward_tests': False,
        'review_repeats_are_independent_new_cases': False,
        'inventory_requires_independent_verification': True}
    previous = None
    if previous_batch is not None or previous_runtime is not None:
        if previous_batch is None or previous_runtime is None:
            raise ValueError('Both previous-batch and previous-runtime are required')
        previous = load_snapshot(previous_batch, previous_runtime)
        previous_manifest = read(Path(previous_batch)/'manifest.json')
        for key, field in [('cases_sha256','cases'),('references_sha256','references'),('jobs_sha256','jobs'),('protocol_sha256','protocol')]:
            if previous_manifest.get(key) != digest(previous[field]):
                raise ValueError('Previous round frozen manifest mismatch: '+key)
        summary['round_to_round_shared_cases'] = round_to_round(previous, current)
    else:
        summary['round_to_round_shared_cases'] = {'status': 'not_requested',
            'note': 'Within-round generic/skills counts remain separate by kind and split.'}
    check['resolved_skill_root'] = summary['frozen_skill_root']
    out = Path(out)
    write_once(out/'summary.json', summary)
    write_once(out/'integrity.json', check)
    manifest = {'version': 'quality-v3-iteration-analysis-v1',
        'cases_sha256': digest(cases), 'references_sha256': digest(refs),
        'jobs_sha256': digest(jobs), 'protocol_sha256': digest(protocol),
        'results_sha256': digest(rows), 'summary_sha256': digest(summary),
        'integrity_sha256': digest(check),
        'analysis_code_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        'base_analysis_code_sha256': hashlib.sha256(Path(BASE.__file__).read_bytes()).hexdigest(),
        'complete_scheduled_result_coverage': len(rows) == len(jobs),
        'independent_post_audit_status': 'not_asserted_by_analyzer', 'formal_release': False}
    contracts = Path(batch)/'request-contracts.frozen.json'
    if contracts.exists():
        manifest['request_contracts_sha256'] = digest(read(contracts))
    if previous is not None:
        manifest['previous_snapshot'] = {
            'cases_sha256': digest(previous['cases']),
            'references_sha256': digest(previous['references']),
            'jobs_sha256': digest(previous['jobs']),
            'protocol_sha256': digest(previous['protocol']),
            'results_sha256': digest(previous['rows'])}
    write_once(out/'analysis-manifest.json', manifest)
    return summary, check


def selfcheck():
    base = BASE.selfcheck()
    valid = {'case_id': 'COMMON', 'kind': 'review', 'split': 'independent_forward',
             'payload': {'question': '虚构同一问题'}}
    previous_cases = [valid, {'case_id': 'OLD', 'kind': 'review', 'split': 'independent_forward', 'payload': {}}]
    current_cases = [{'case_id': 'COMMON', 'kind': 'review', 'split': 'regression_r1',
                      'payload': valid['payload']},
                     {'case_id': 'NEW', 'kind': 'review', 'split': 'independent_forward', 'payload': {}}]
    def snapshot(cases, correct, schema):
        jobs, rows = [], []
        for case in cases:
            for arm in ('generic', 'skills'):
                for repeat in (1, 2, 3):
                    job = {'case_id': case['case_id'], 'kind': 'review', 'arm': arm, 'repeat': repeat}
                    jobs.append(job)
                    verdict = 'pass' if correct or case['case_id'] != 'COMMON' else 'revise'
                    rows.append({'job': job, 'status': 'completed', 'answer': {'verdict': verdict},
                                 'gate': {'program_disposition': verdict}})
        return {'cases': cases, 'references': {c['case_id']: {'expected_valid': True} for c in cases},
                'jobs': jobs, 'rows': rows,
                'protocol': {'schemas': {'review': schema}, 'generic_prompts': {'review': '同轮基线'}, 'round': 'fixture'}}
    previous = snapshot(previous_cases, False, {'v': 1})
    current = snapshot(current_cases, True, {'v': 2})
    comparison = round_to_round(previous, current)
    assert len(comparison['shared_eligible_cases']) == 1
    assert comparison['new_current_cases_not_pooled'] == [{'kind': 'review', 'case_id': 'NEW'}]
    assert comparison['previous_only_cases_not_pooled'] == [{'kind': 'review', 'case_id': 'OLD'}]
    assert comparison['previous_shared_subset']['review/skills']['shared_unique_cases'] == 1
    assert comparison['previous_shared_subset']['review/skills']['counts']['scheduled'] == 3
    assert comparison['current_shared_subset']['review/skills']['counts']['raw_model_correct_disposition'] == 3
    assert comparison['output_schema_equal_by_kind']['review'] is False
    changed = snapshot(current_cases, True, {'v': 2})
    changed['references']['COMMON']['expected_valid'] = False
    rejected = round_to_round(previous, changed)
    assert not rejected['shared_eligible_cases']
    assert rejected['excluded_shared_cases'][0]['reason'] == 'reference_unadjudicated_or_changed'
    violations = []
    _selected_prompt('review', 'skills', {'generic_prompts': {'review': 'generic'},
        'skills': {'review': {}}, 'skill_root': '../outside-skills'}, violations)
    assert violations[0]['issue'] == 'protocol_skill_root_outside_allowed_directories'
    assert BASE._selected_prompt is not _selected_prompt
    return {'selfcheck': 'passed', 'base_selfcheck': base,
        'additional_checks': ['shared-case-only-comparison', 'new-cases-not-pooled',
            'reference-changes-excluded', 'changed-contract-warning',
            'skill-root-boundary', 'r1-resolver-left-unchanged'], 'real_model_calls': 0}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('batch', 'runtime', 'out', 'previous-batch', 'previous-runtime'):
        parser.add_argument('--'+name, type=Path)
    parser.add_argument('--selfcheck', action='store_true')
    args = parser.parse_args()
    if args.selfcheck:
        print(json.dumps(selfcheck()))
    else:
        if not all((args.batch, args.runtime, args.out)):
            parser.error('--batch --runtime --out are required')
        if bool(args.previous_batch) != bool(args.previous_runtime):
            parser.error('--previous-batch and --previous-runtime must be provided together')
        summary, check = analyze(args.batch, args.runtime, args.out,
                                 args.previous_batch, args.previous_runtime)
        print(json.dumps({'jobs': summary['scheduled_jobs'], 'results': summary['result_rows'],
                          'integrity_violations': len(check['violations']), 'formal_release': False}))
