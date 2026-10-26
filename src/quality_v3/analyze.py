"""Offline accounting for the pinned quality-skills pilot; never changes inputs.

Usage: python analyze.py --batch DIR --runtime DIR --out DIR
The independent case/reference records remain separate from actual requests.
"""
from __future__ import annotations

import argparse
import collections
import hashlib
import json
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[2]


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
        separators=(',', ':')).encode()).hexdigest()


def write_once(path, value):
    path = Path(path)
    text = json.dumps(value, ensure_ascii=False, indent=2) + '\n'
    if path.exists():
        if path.read_text(encoding='utf-8') != text:
            raise ValueError('Analysis output changed; choose a new version: ' + str(path))
    else:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding='utf-8')


def fraction(numerator, denominator):
    return {'numerator': numerator, 'denominator': denominator,
            'value': numerator / denominator if denominator else None}


def indexed_references(value):
    return {r['case_id']: r for r in value} if isinstance(value, list) else value


def validity(reference):
    value = reference.get('expected_valid')
    return value if isinstance(value, bool) else None


def model_decision(kind, answer):
    verdict = answer.get('verdict')
    if kind == 'review':
        return True if verdict == 'pass' else False if verdict == 'revise' else None
    if kind == 'scoring':
        return True if verdict == 'supported' else False if verdict == 'incorrect' else None
    return None


def program_decision(kind, case, row):
    if kind == 'review':
        disposition = row.get('gate', {}).get('program_disposition')
        if disposition == 'pass': return True, disposition
        if disposition in ('revise', 'needs_revision_structural'): return False, disposition
        return None, disposition or 'unavailable'
    if kind == 'scoring':
        structural = case.get('structural', {}).get('provisional_outcome')
        raw = model_decision(kind, row.get('answer', {}))
        if structural == 'incorrect': return False, 'incorrect_structural'
        if raw is True: return True, 'supported_semantic_review'
        if raw is False: return False, 'incorrect_semantic_review'
        return None, 'needs_semantic_review'
    return None, 'exploratory_not_scored'


def update_decision(counter, prefix, decision, expected):
    if expected is None:
        counter[prefix + 'unadjudicated_reference'] += 1
        return
    if decision is None:
        counter[prefix + 'needs_adjudication'] += 1
        return
    counter[prefix + 'decided'] += 1
    counter[prefix + ('valid_decided' if expected else 'invalid_decided')] += 1
    if expected == decision:
        counter[prefix + 'correct_disposition'] += 1
    elif expected:
        counter[prefix + 'false_block'] += 1
    else:
        counter[prefix + 'unsafe_accept'] += 1


def dimension_value(field, value, payload):
    if field in ('status_correct', 'answer_correct'):
        return True if value == 'correct' else False if value == 'incorrect' else None
    if field == 'proof_support':
        if value == 'supported': return True
        if value == 'unsupported': return False
        if value == 'not_applicable' and payload.get('candidate_response', {}).get('status') == 'insufficient_evidence':
            return True
    return None


def summarize(cases, references, jobs, rows):
    refs = indexed_references(references)
    case_map = {c['case_id']: c for c in cases}
    actual = {digest(r['job']): r for r in rows}
    counts, dims, distributions, inventory = {}, {}, {}, []
    grouped_case_ids = collections.defaultdict(set)
    program_conflicts = []
    scheduled = {digest(j): j for j in jobs}
    if len(scheduled) != len(jobs): raise ValueError('Duplicate scheduled jobs')
    if len(actual) != len(rows): raise ValueError('Duplicate result jobs')
    if set(actual) - set(scheduled): raise ValueError('Unexpected result jobs')
    for job in jobs:
        case = case_map[job['case_id']]
        if case['kind'] != job['kind']: raise ValueError('Job/case kind mismatch')
        kind, split, arm = case['kind'], case['split'], job['arm']
        key = '/'.join((kind, split, arm))
        c = counts.setdefault(key, collections.Counter())
        grouped_case_ids[key].add(case['case_id'])
        c['scheduled'] += 1
        ref = refs[case['case_id']]
        expected = validity(ref)
        if kind != 'inventory':
            c['valid_trials' if expected is True else 'invalid_trials' if expected is False else 'unadjudicated_reference_trials'] += 1
        row = actual.get(digest(job), {'job': job, 'status': 'not_run'})
        status = row['status']; c[status] += 1
        if kind == 'review':
            distributions.setdefault((case['case_id'], split, arm), []).append({
                'repeat': job['repeat'], 'status': status,
                'raw_verdict': row.get('answer', {}).get('verdict')})
        if kind == 'inventory':
            inventory.append({'job': job, 'split': split, 'status': status,
                'proposal': row.get('answer'), 'independently_verified': False,
                'accuracy_eligible': False})
            continue
        if status != 'completed':
            if row.get('answer', {}).get('verdict') is not None:
                c['protocol_invalid_raw_verdict:' + str(row['answer']['verdict'])] += 1
            continue
        answer = row['answer']
        c['raw_verdict:' + str(answer.get('verdict'))] += 1
        raw = model_decision(kind, answer)
        update_decision(c, 'raw_model_', raw, expected)
        program, disposition = program_decision(kind, case, row)
        c['program_disposition:' + disposition] += 1
        update_decision(c, 'program_', program, expected)
        if kind == 'review' and raw is True and disposition == 'needs_revision_structural':
            program_conflicts.append({'job': job, 'split': split,
                'conflict': 'raw_model_pass_overridden_by_deterministic_structural_defect',
                'raw_verdict_preserved': answer.get('verdict'), 'program_disposition': disposition,
                'structural': row.get('gate', {}).get('structural'),
                'not_a_skill_only_gain': True})
        if kind == 'scoring':
            if raw is True and case.get('structural', {}).get('provisional_outcome') == 'incorrect':
                program_conflicts.append({'job': job, 'split': split,
                    'conflict': 'semantic_grader_supports_structurally_incorrect_response',
                    'raw_verdict_preserved': answer.get('verdict'),
                    'program_disposition': disposition, 'structural': case['structural'],
                    'not_a_skill_only_gain': True})
            mapping = {'status_correct': 'status_correct', 'answer_correct': 'final_answer_correct',
                       'proof_support': 'proof_supported_by_actual_member'}
            for field, ref_field in mapping.items():
                d = dims.setdefault(key + '/' + field, collections.Counter())
                reference_value = ref.get(ref_field)
                if not isinstance(reference_value, bool):
                    d['reference_unadjudicated'] += 1; continue
                d['completed_reference_trials'] += 1
                d['expected_true' if reference_value else 'expected_false'] += 1
                value = dimension_value(field, answer.get(field), case['payload'])
                if value is None: d['model_undetermined'] += 1
                else:
                    d['model_decided'] += 1
                    d['agreement' if value == reference_value else 'error'] += 1
    groups = {}
    for key, c in sorted(counts.items()):
        for field in ('completed', 'protocol_failure', 'technical_failure', 'not_run',
                      'valid_trials', 'invalid_trials', 'unadjudicated_reference_trials'):
            c.setdefault(field, 0)
        rates = {}
        if not key.startswith('inventory/'):
            for prefix in ('raw_model_', 'program_'):
                for metric in ('unsafe_accept','false_block','correct_disposition','needs_adjudication','decided','valid_decided','invalid_decided','unadjudicated_reference'):
                    c.setdefault(prefix+metric, 0)
            for prefix in ('raw_model_', 'program_'):
                rates[prefix.rstrip('_')] = {
                    'unsafe_accept_per_scheduled_invalid': fraction(c[prefix+'unsafe_accept'], c['invalid_trials']),
                    'false_block_per_scheduled_valid': fraction(c[prefix+'false_block'], c['valid_trials']),
                    'unsafe_accept_among_decided_invalid': fraction(c[prefix+'unsafe_accept'], c[prefix+'invalid_decided']),
                    'false_block_among_decided_valid': fraction(c[prefix+'false_block'], c[prefix+'valid_decided']),
                    'decision_coverage': fraction(c[prefix+'decided'], c['scheduled']-c['unadjudicated_reference_trials'])}
        groups[key] = {'unique_cases':len(grouped_case_ids[key]), 'counts': dict(c), 'rates': rates}
    dimensions = {key: {'counts': dict(c),
        'agreement_among_decided': fraction(c['agreement'], c['model_decided']),
        'agreement_per_completed_reference': fraction(c['agreement'], c['completed_reference_trials'])}
        for key, c in sorted(dims.items())}
    paired, paired_groups = [], {}
    for case in cases:
        if case['kind'] == 'inventory': continue
        repeats = sorted({j['repeat'] for j in jobs if j['case_id'] == case['case_id']})
        for repeat in repeats:
            pair = {}
            for arm in ('generic', 'skills'):
                j = {'case_id': case['case_id'], 'kind': case['kind'], 'arm': arm, 'repeat': repeat}
                pair[arm] = actual.get(digest(j), {'status': 'not_run'})
            key = case['kind'] + '/' + case['split']
            c = paired_groups.setdefault(key, collections.Counter()); c['scheduled_pairs'] += 1
            ref = validity(refs[case['case_id']])
            if ref is None: c['unadjudicated_reference_pairs'] += 1; continue
            if any(r['status'] != 'completed' for r in pair.values()):
                c['excluded_technical_protocol_or_not_run'] += 1; continue
            before = model_decision(case['kind'], pair['generic']['answer'])
            after = model_decision(case['kind'], pair['skills']['answer'])
            if before is None or after is None:
                c['excluded_needs_adjudication'] += 1; continue
            c['paired_decisive_completed'] += 1
            correction = before != ref and after == ref
            introduced = before == ref and after != ref
            c['corrections'] += correction; c['introduced_errors'] += introduced
            paired.append({'case_id': case['case_id'], 'kind': case['kind'], 'split': case['split'],
                'repeat': repeat, 'generic_correct': before == ref, 'skills_correct': after == ref,
                'correction': correction, 'introduced_error': introduced,
                'comparison_layer': 'raw_contract_valid_model_disposition'})
    stability = []
    for (cid, split, arm), observations in sorted(distributions.items()):
        observations.sort(key=lambda r:r['repeat'])
        all_completed = len(observations) == 3 and all(r['status'] == 'completed' for r in observations)
        verdicts = [r['raw_verdict'] if r['status'] == 'completed' else r['status'] for r in observations]
        stability.append({'case_id': cid, 'split': split, 'arm': arm, 'observations': observations,
            'distribution': dict(collections.Counter(verdicts)),
            'all_three_contract_valid': all_completed,
            'all_three_decisive': all_completed and all(r['raw_verdict'] in ('pass','revise') for r in observations),
            'all_three_same_valid_verdict': all_completed and len(set(verdicts)) == 1,
            'repeat_calls_are_independent_items': False})
    structural_cases = []
    for case in cases:
        if case['kind'] == 'scoring':
            structural_cases.append({'case_id': case['case_id'], 'split': case['split'],
                'expected_valid': validity(refs[case['case_id']]), 'structural': case.get('structural'),
                'per_case_not_replicated_per_arm': True})
    return {'version':'quality-v3-summary-v1', 'scheduled_jobs':len(jobs), 'result_rows':len(rows),
        'groups':groups, 'reference_case_status_counts':dict(collections.Counter(str(r.get('reference_state','unrecorded')) for r in refs.values())), 'scoring_dimensions':dimensions,
        'paired_raw_model_changes':paired, 'paired_counts':{k:dict(c) for k,c in paired_groups.items()},
        'review_repeat_distributions':stability, 'program_conflicts':program_conflicts,
        'scoring_structural_layer_per_case':structural_cases,
        'inventory_proposals':inventory,
        'inventory_accuracy_policy':'Exploratory proposals only; independent fact/support verification is still required.',
        'limitations':['Historical diagnostics were already used to design the repair; they are not held-out tests.',
            'Independent forward fixtures are synthetic and small; no broad generalization is established.',
            'Generic and skills arms share the same changed contract and deterministic gates; program improvements are not skill-only gains.',
            'Failed and undecided calls are not reclassified as rejections or incorrect answers.',
            'Paired repeat indices describe independent stochastic sessions, not stable causal effects.',
            'Three review calls are repeated measurements of one case, not three independent cases.',
            'needs_semantic_review is an unresolved route, not a claim that the answer is wrong.'],
        'formal_release':False}


def _selected_prompt(kind, arm, protocol, violations):
    generic = protocol['generic_prompts'][kind]
    if arm == 'generic': return generic, {}
    parts = []; files = protocol['skills'][kind]
    for relative, sha in files.items():
        path = (Path(__file__).parent/'skills'/relative).resolve()
        if not path.is_relative_to((Path(__file__).parent/'skills').resolve()):
            violations.append({'issue':'selected_skill_path_escapes_project','file':relative});continue
        data = path.read_bytes()
        if hashlib.sha256(data).hexdigest() != sha:
            violations.append({'issue':'selected_skill_content_hash_changed','file':relative})
        parts.append('项目技能 ' + relative + '\n' + data.decode('utf-8'))
    return generic + '\n\n' + '\n\n'.join(parts), files


def _forbidden_reference_fields(value, at=''):
    found = []
    forbidden = {'expected_valid','expected_verdict','reference_state','reviewer_kind','defect_category',
                 'semantic_task_success','independent_review_status','human_review'}
    if isinstance(value, dict):
        for k, v in value.items():
            if k in forbidden: found.append(at+'/'+k)
            found.extend(_forbidden_reference_fields(v, at+'/'+k))
    elif isinstance(value, list):
        for i, v in enumerate(value): found.extend(_forbidden_reference_fields(v, at+'/'+str(i)))
    return found


def integrity(batch, runtime, cases, references, jobs, protocol, rows):
    batch, runtime = Path(batch), Path(runtime)
    violations, warnings = [], []
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
        expected_requests['quality-'+jid]=exp
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
        seen.add(jid);stage='quality-'+jid[:24];exp=expected_requests[stage]
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


def analyze(batch, runtime, out):
    batch,runtime,out=Path(batch),Path(runtime),Path(out)
    cases,refs,jobs,protocol=(read(batch/name) for name in ('cases.frozen.json','references.frozen.json','jobs.frozen.json','protocol.frozen.json'))
    rows=[read(path) for path in sorted((runtime/'results').glob('*.json'))]
    report=summarize(cases,refs,jobs,rows)
    check=integrity(batch,runtime,cases,refs,jobs,protocol,rows)
    report['integrity_all_observed_checks_pass']=check['all_observed_checks_pass']
    write_once(out/'summary.json',report);write_once(out/'integrity.json',check)
    manifest={'version':'quality-v3-analysis-v1','cases_sha256':digest(cases),'references_sha256':digest(refs),
        'jobs_sha256':digest(jobs),'protocol_sha256':digest(protocol),'results_sha256':digest(rows),
        'summary_sha256':digest(report),'integrity_sha256':digest(check),
        'analysis_code_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        'complete_scheduled_result_coverage':len(rows)==len(jobs),
        'independent_post_audit_status':'not_asserted_by_analyzer','formal_release':False}
    contracts=batch/'request-contracts.frozen.json'
    if contracts.exists():manifest['request_contracts_sha256']=digest(read(contracts))
    write_once(out/'analysis-manifest.json',manifest)
    return report,check


def selfcheck():
    """Small synthetic fixture tests statistics without touching real references."""
    cases=[{'case_id':'V','kind':'review','split':'independent_forward','payload':{}},
           {'case_id':'I','kind':'review','split':'independent_forward','payload':{}},
           {'case_id':'SV','kind':'scoring','split':'diagnostic_development','payload':{'candidate_response':{'status':'answerable'}},'structural':{'provisional_outcome':'needs_semantic_review'}},
           {'case_id':'SI','kind':'scoring','split':'diagnostic_development','payload':{'candidate_response':{'status':'answerable'}},'structural':{'provisional_outcome':'incorrect'}},
           {'case_id':'INV','kind':'inventory','split':'exploratory_source','payload':{}}]
    refs={c['case_id']:{'expected_valid':c['case_id'] in ('V','SV'),'status_correct':True,
          'final_answer_correct':c['case_id']!='SI','proof_supported_by_actual_member':True} for c in cases}
    refs['INV']={'status':'exploratory_not_in_accuracy_denominators'}
    jobs=[];rows=[]
    for case in cases:
        for arm in ('generic','skills'):
            for repeat in (1,2,3) if case['kind']=='review' else (1,):
                job={'case_id':case['case_id'],'kind':case['kind'],'arm':arm,'repeat':repeat};jobs.append(job)
                row={'job':job,'status':'completed'}
                if case['kind']=='review':
                    verdict='pass' if case['case_id']=='V' or arm=='generic' else 'revise'
                    if case['case_id']=='V' and arm=='generic' and repeat==2:verdict='needs_adjudication'
                    if case['case_id']=='V' and arm=='generic' and repeat==3:row['status']='protocol_failure'
                    row['answer']={'verdict':verdict}
                    row['gate']={'program_disposition':'needs_revision_structural' if case['case_id']=='I' else verdict}
                elif case['kind']=='scoring':
                    verdict=('needs_adjudication' if case['case_id']=='SV' and arm=='generic' else
                             'incorrect' if case['case_id']=='SI' and arm=='skills' else 'supported')
                    row['answer']={'verdict':verdict,'status_correct':'correct',
                                  'answer_correct':'incorrect' if verdict=='incorrect' else 'undetermined' if verdict=='needs_adjudication' else 'correct',
                                  'proof_support':'supported'}
                else:row['answer']={'facts':[],'reason':'Only an unverified exploratory proposal.'}
                rows.append(row)
    summary=summarize(cases,refs,jobs,rows)
    group=summary['groups']['review/independent_forward/generic']['counts']
    assert group['valid_trials']==3 and group['invalid_trials']==3
    assert group['protocol_failure']==1 and group['raw_model_needs_adjudication']==1
    assert group['raw_model_unsafe_accept']==3 and group['program_unsafe_accept']==0
    assert summary['paired_counts']['review/independent_forward']['corrections']==3
    assert summary['paired_counts']['review/independent_forward']['excluded_technical_protocol_or_not_run']==1
    assert summary['paired_counts']['review/independent_forward']['excluded_needs_adjudication']==1
    assert len(summary['program_conflicts'])==4
    assert len(summary['inventory_proposals'])==2 and all(not x['accuracy_eligible'] for x in summary['inventory_proposals'])
    assert len(summary['review_repeat_distributions'])==4
    missing=summarize(cases,refs,jobs,rows[:-1])
    assert missing['groups']['inventory/exploratory_source/skills']['counts']['not_run']==1
    return {'selfcheck':'passed','scheduled_fixture_jobs':len(jobs),
        'tested':['failed-not-rejected','undecided-not-incorrect','raw-vs-program-separation',
                  'structural-overrides-recorded','paired-exclusions','review-only-repeats','inventory-not-accuracy','not-run-coverage']}


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--batch',type=Path);parser.add_argument('--runtime',type=Path);parser.add_argument('--out',type=Path)
    parser.add_argument('--selfcheck',action='store_true');args=parser.parse_args()
    if args.selfcheck:print(json.dumps(selfcheck()))
    else:
        if not all((args.batch,args.runtime,args.out)):parser.error('--batch --runtime --out are required')
        a,b=analyze(args.batch,args.runtime,args.out)
        print(json.dumps({'jobs':a['scheduled_jobs'],'results':a['result_rows'],
                          'integrity_violations':len(b['violations']),'formal_release':False}))
