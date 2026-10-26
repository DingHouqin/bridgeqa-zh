"""Offline accounting and projection checks for a sealed deletion/review batch.

Usage: python analyze_batch.py --batch DIR --reviews DIR --blind DIR --out DIR
This script writes analysis only; it never changes frozen inputs or model results.
"""
from __future__ import annotations
import argparse
import collections
import json
import re
from pathlib import Path

from experiment import CORE, SCHEMAS, digest, read, save_new_or_same, make_jobs, summarize, REVIEW_PROMPT, V0
from review_cases import project_review

CHECK_FIELDS = ('answer_and_status_correct', 'path_matches_permitted_proof',
                'evidence_quotes_located', 'evidence_overlaps_reference_spans',
                'strict_structural_success')
UNADJUDICATED = {'pending', 'unresolved', 'disputed', 'pending_independent_gpt'}


def load_rows(folder):
    rows = [read(p) for p in sorted((Path(folder)/'results').glob('*.json'))]
    seen=set()
    for row in rows:
        identity=digest(row['job'])
        if identity in seen: raise ValueError('Duplicate result job identity')
        seen.add(identity)
    return rows


def frac(n,d):
    return {'numerator':n,'denominator':d,'value':n/d if d else None}


def references_by_case(references):
    return ({r['case_id']:r for r in references} if isinstance(references,list) else references)


def family_macro(cases,references,rows):
    """Equal-weight family means; repetitions remain within family measurements."""
    refs=references_by_case(references);indexed={c['case_id']:c for c in cases}
    actual={digest(r['job']):r for r in rows};groups={}
    for job in make_jobs(cases):
        case=indexed[job['case_id']];ref=refs[job['case_id']]
        key=(case['track'],job['condition'],case['family_id'])
        c=groups.setdefault(key,collections.Counter());c['scheduled']+=1
        if ref.get('status') in UNADJUDICATED:
            c['unadjudicated']+=1;continue
        valid=ref['expected_verdict']=='pass';major=ref.get('major_defect',not valid)
        c['valid_trials' if valid else 'defective_trials']+=1
        c['major_defect_trials']+=int(major)
        row=actual.get(digest(job),{'status':'not_run'})
        if row['status']!='completed':c[row['status']]+=1;continue
        passed=row['answer']['verdict']=='pass';c['completed']+=1
        c['false_block']+=int(valid and not passed)
        c['unsafe_accept']+=int(major and passed)
        c['correct_disposition']+=int(passed==valid)
    per_family=[];aggregated={}
    for (track,condition,fid),c in sorted(groups.items()):
        rates={'unsafe_accept':frac(c['unsafe_accept'],c['major_defect_trials']),
               'false_block':frac(c['false_block'],c['valid_trials']),
               'correct_disposition_among_completed':frac(c['correct_disposition'],c['completed']),
               'decision_coverage':frac(c['completed'],c['scheduled']-c['unadjudicated'])}
        per_family.append({'track':track,'condition':condition,'family_id':fid,'counts':dict(c),'rates':rates})
        m=aggregated.setdefault(track+'/'+condition,collections.defaultdict(list))
        for metric,rate in rates.items():
            if rate['value'] is not None:m[metric].append(rate['value'])
    return {'per_family':per_family,'macro':{key:{metric:{'mean':sum(values)/len(values),
              'family_denominator':len(values)} for metric,values in metrics.items()} for key,metrics in aggregated.items()},
            'limit':'Descriptive equal-family means; shared sources/edges and repeated measurements are not independent observations.'}


def source_clusters(families):
    edges=collections.defaultdict(set);units=collections.defaultdict(set)
    for family in families:
        fid=family['family_id'];facts={f['id']:f for f in family['origin']['facts']}
        base=next(v for v in family['variants'] if v['condition']=='base')
        for proof in base['gold'].get('proofs',[]):
            for factid in proof['facts']:
                fact=facts[factid];edges[factid].add(fid)
                for bundle in fact['evidence_sets']:
                    for q in bundle:units[q['unit_id']].add(fid)
    return {'proof_edges':{k:sorted(v) for k,v in edges.items()},
            'proof_materials':{k:sorted(v) for k,v in units.items()},
            'shared_edge_count':sum(len(v)>1 for v in edges.values()),
            'shared_material_count':sum(len(v)>1 for v in units.values()),
            'independence_claim':False}


def blind_summary(families,rows):
    indexed={f['family_id']:f for f in families};actual={digest(r['job']):r for r in rows}
    jobs=[{'family_id':f['family_id'],'variant_index':i} for f in families for i in range(len(f['variants']))]
    jobs += [{'family_id':f['family_id'],'variant_index':None} for f in families]
    if set(actual)-{digest(j) for j in jobs}:raise ValueError('Unexpected blind job')
    counters={};items=[]
    for job in jobs:
        f=indexed[job['family_id']];idx=job['variant_index']
        condition=f['variants'][idx]['condition'] if idx is not None else 'no_material_diagnostic'
        gold=f['variants'][idx]['gold'] if idx is not None else CORE.solve(f['query'],[])
        c=counters.setdefault(condition,collections.Counter());c['scheduled']+=1
        row=actual.get(digest(job),{'status':'not_run'});c[row['status']]+=1
        detail={'job':job,'condition':condition,'status':row['status'],'reference_status':gold['status']}
        if row['status']=='completed':
            answer=row['answer'];checks=row.get('checks',{})
            c['answer_status:'+answer['status']]+=1
            for field in CHECK_FIELDS:c[field]+=int(bool(checks.get(field)))
            c['status_correct']+=int(answer['status']==gold['status'])
            detail.update(answer_status=answer['status'],checks={k:checks.get(k) for k in CHECK_FIELDS})
        items.append(detail)
    by_condition={}
    for condition,c in counters.items():
        by_condition[condition]={'counts':dict(c),'rates_among_completed':{field:frac(c[field],c['completed'])
            for field in ('status_correct',)+CHECK_FIELDS},'decision_coverage':frac(c['completed'],c['scheduled'])}
    return {'scheduled':len(jobs),'conditions':by_condition,'items':items,
            'limitations':['A refusal after deletion does not establish deletion validity; independent reference audit and retained-support controls are required.',
                           'Graph path and exact quotation checks do not independently establish natural-language entailment.',
                           'No-material diagnostics are separate from the source-member analysis.']}


def legacy_effective_hints(value):
    if isinstance(value,dict):
        return any((k in ('matches','conflict_hints','potential_omissions','known_library_issues') and bool(v))
                   or legacy_effective_hints(v) for k,v in value.items())
    if isinstance(value,list):return any(legacy_effective_hints(v) for v in value)
    return False


def effective_hints(value):
    """Strict fact-hint presence; library warnings are not factual hints."""
    if isinstance(value,dict):
        for key,child in value.items():
            if key in ('known_library_issues','known_issue_rows'):
                continue
            if key in ('matches','conflict_hints','potential_omissions'):
                if isinstance(child,list) and any(isinstance(row,dict) and not row.get('known_issue')
                    and not row.get('excluded_from_comparison') for row in child):return True
            elif effective_hints(child):return True
    elif isinstance(value,list):return any(effective_hints(child) for child in value)
    return False


def library_hint_coverage(cases,families):
    """Count actual C01/C02 records and their relevance to canonical base proofs.

    Relevance means a comparison is attached to a base-proof fact ID; it does
    not mean the hint is correct, independently sourced, or causally useful.
    Omissions without a fact ID are associated by exact canonical endpoint
    names and compatible explicit parent role, otherwise remain unassigned.
    """
    family_index={f['family_id']:f for f in families};records=[];library_totals={}
    for case in cases:
        if case['track']!='source':continue
        family=family_index.get(case['family_id'])
        if family is None:raise ValueError('Missing canonical family for library hint relevance')
        base=next(v for v in family['variants'] if v['condition']=='base')
        proof_ids={fid for proof in base['gold'].get('proofs',[]) for fid in proof.get('facts',[])}
        fact_index={f['id']:f for f in family['origin']['facts']}
        entity_index={e['id']:e for e in family['origin']['entities']}
        hints=case.get('external_relation_hints',{});by_library={key:collections.Counter() for key in ('C01','C02')}
        for lib in hints.get('libraries',[]):by_library.setdefault(lib['id'],collections.Counter())
        locators=collections.defaultdict(list);warnings=collections.defaultdict(set)
        def count_record(library,kind,row,fact_ids):
            counter=by_library.setdefault(library,collections.Counter())
            if row.get('known_issue') or row.get('excluded_from_comparison'):
                counter['excluded_known_issue_records']+=1;return
            relevant=bool(proof_ids & set(fact_ids))
            known=bool(set(fact_ids)&set(fact_index))
            relevance='base_proof' if relevant else 'noise_fact' if known else 'unassigned'
            counter[kind]+=1;counter[kind+':'+relevance]+=1
            counter['usable_fact_hint_rows']+=1
            counter['base_proof_hint_rows' if relevant else 'nonproof_hint_rows']+=1
            locators[library].append({'kind':kind,'fact_ids':sorted(fact_ids),'relevance':relevance,
                                      'source_row':row.get('source_row')})
        for item in hints.get('facts',[]):
            fid=item.get('fact_id');fact_ids=[fid] if fid else []
            for comparison in item.get('comparisons',[]):
                library=comparison.get('library','unknown')
                by_library.setdefault(library,collections.Counter())
                for kind in ('matches','conflict_hints'):
                    for row in comparison.get(kind,[]):count_record(library,kind,row,fact_ids)
                for number in comparison.get('known_issue_rows',[]):warnings[library].add(str(number))
        for row in hints.get('potential_omissions',[]):
            library=row.get('library','unknown');ids=[]
            if row.get('fact_id'):ids=[row['fact_id']]
            else:
                for fid,fact in fact_index.items():
                    parent=entity_index[fact['parent']]['name'];child=entity_index[fact['child']]['name']
                    role_compatible=row.get('parent_role') in (fact['parent_role'],'parent')
                    if (parent,child)==(row.get('parent'),row.get('child')) and role_compatible:ids.append(fid)
            count_record(library,'omissions',row,ids)
        for row in hints.get('known_library_issues',[]):
            warnings[row.get('library','unknown')].add(str(row.get('source_row','unlocated')))
        per_library={}
        for library,counter in by_library.items():
            for field in ('matches','conflict_hints','omissions','usable_fact_hint_rows',
                          'base_proof_hint_rows','nonproof_hint_rows','excluded_known_issue_records'):
                counter.setdefault(field,0)
            counter['known_issue_warning_rows']=len(warnings[library])
            stratum=('base_proof_related' if counter['base_proof_hint_rows'] else
                     'noise_only' if counter['usable_fact_hint_rows'] and
                         all(x['relevance']=='noise_fact' for x in locators[library]) else
                     'nonproof_or_unassigned_only' if counter['usable_fact_hint_rows'] else
                     'empty_fact_hints')
            per_library[library]={'counts':dict(counter),'stratum':stratum,
                'any_usable_fact_hint':bool(counter['usable_fact_hint_rows']),
                'base_proof_related_fact_hint':bool(counter['base_proof_hint_rows']),
                'warning_only':bool(warnings[library]) and not counter['usable_fact_hint_rows'],
                'row_locators':locators[library]}
            total=library_totals.setdefault(library,collections.Counter());total.update(counter)
            total['source_cases']+=1;total['cases_with_any_fact_hint']+=bool(counter['usable_fact_hint_rows'])
            total['cases_with_base_proof_hint']+=bool(counter['base_proof_hint_rows'])
            total['cases_with_conflict_hint']+=bool(counter['conflict_hints'])
            total['cases:'+stratum]+=1
        any_hint=any(x['any_usable_fact_hint'] for x in per_library.values())
        proof_hint=any(x['base_proof_related_fact_hint'] for x in per_library.values())
        all_locators=[row for value in per_library.values() for row in value['row_locators']]
        stratum=('base_proof_related' if proof_hint else 'noise_only' if any_hint and
            all(row['relevance']=='noise_fact' for row in all_locators) else
            'nonproof_or_unassigned_only' if any_hint else 'empty_fact_hints')
        records.append({'case_id':case['case_id'],'family_id':case['family_id'],
            'canonical_base_proof_fact_ids':sorted(proof_ids),'libraries':per_library,
            'stratum':stratum,'any_usable_fact_hint':any_hint,'base_proof_related_fact_hint':proof_hint})
    claims={}
    for library,total in library_totals.items():
        total['source_families']=len({row['family_id'] for row in records})
        total['families_with_any_fact_hint']=len({row['family_id'] for row in records if row['libraries'].get(library,{}).get('any_usable_fact_hint')})
        total['families_with_base_proof_hint']=len({row['family_id'] for row in records if row['libraries'].get(library,{}).get('base_proof_related_fact_hint')})
        total['families_with_conflict_hint']=len({row['family_id'] for row in records if row['libraries'].get(library,{}).get('counts',{}).get('conflict_hints',0)})

        claims[library]={'actual_conflict_hint_cases':total['cases_with_conflict_hint'],
                        'nonempty_conflict_exposure_present':bool(total['cases_with_conflict_hint']),
                        'conflict_correctness_or_benefit_established':False,
                        'may_claim_tested_nonempty_conflict_hints':bool(total['cases_with_conflict_hint'])}
    return {'per_source_case':records,'library_totals':{key:dict(value) for key,value in library_totals.items()},
            'conflict_exposure':claims,
            'definitions':{'any_hint':'Nonexcluded matches, conflict_hints or omissions; warnings alone do not count.',
              'base_proof_related':'Actual comparison attached to a fact ID in the canonical correct family base proof, not the corrupted candidate proof.',
              'omission_mapping':'Exact canonical endpoint names and compatible parent role; unmatched omissions are unassigned.',
              'counts':'Record rows per candidate; GOOD/BAD share library input, so rows and candidates are not independent library facts.'},
            'limitations':['Nonempty factual hints are exposure, not proven benefit or correctness.',
                'C02 cannot be described as an effective conflict-hint test when actual conflict exposure is zero.',
                'Warnings about known library errors are retained separately and never counted as effective factual hints.']}


def strict_hint_changes(summary,coverage,cases):
    indexed={row['case_id']:row for row in coverage['per_source_case']};case_index={c['case_id']:c for c in cases}
    result={}
    for row in summary['paired_changes']:
        case=case_index[row['case_id']]
        exposure=indexed.get(row['case_id'])
        stratum=exposure['stratum'] if exposure else 'not_applicable_synthetic'
        group=case['track']+'/'+row['pair']+'/'+stratum
        count=result.setdefault(group,collections.Counter());count['paired_completed_trials']+=1
        count['corrections']+=int(row['correction']);count['introduced_errors']+=int(row['introduced_error'])
    return {key:dict(value) for key,value in result.items()}


def hint_changes(summary,cases):
    cases={c['case_id']:c for c in cases};out={}
    for row in summary['paired_changes']:
        effective=row['track']=='source' and legacy_effective_hints(cases[row['case_id']].get('external_relation_hints',{}))
        group=row['track']+'/'+row['pair']+'/'+('effective' if effective else 'empty_or_not_applicable')
        c=out.setdefault(group,collections.Counter());c['paired_completed_trials']+=1
        c['corrections']+=int(row['correction']);c['introduced_errors']+=int(row['introduced_error'])
    return {k:dict(v) for k,v in out.items()}


def request_projection_audit(cases,families,reviews_folder,blind_folder):
    """Compare persisted raw-request inputs to exact allowlisted projections.

    This inspects requests, not only reconstructed result hashes. Equality is a
    stronger field-isolation check than searching answer names in natural text.
    """
    expected_reviews={}
    for job in make_jobs(cases):
        case=next(c for c in cases if c['case_id']==job['case_id'])
        expected_reviews['review-'+digest(job)[:24]]=(project_review(case,job['condition']),job)
    expected_blind={}
    for f in families:
        for idx in list(range(len(f['variants'])))+[None]:
            job={'family_id':f['family_id'],'variant_index':idx}
            row=f['variants'][idx] if idx is not None else {'materials':[],'gold':CORE.solve(f['query'],[])}
            expected_blind['blind-'+digest(job)[:24]]=(CORE.project(row,f['question'],SCHEMAS['blind-solver']),job)
    reports={}
    for role,folder,expected in [('review',Path(reviews_folder),expected_reviews),('blind',Path(blind_folder),expected_blind)]:
        files=sorted(folder.rglob('*.request.json'));violations=[];checked=0;sids=set()
        found_stages=set()
        for path in files:
            match=re.fullmatch(r'(.+)\.attempt-([0-2])\.request\.json',path.name)
            if not match:
                violations.append({'file':str(path.relative_to(folder)),'issue':'unrecognized_request_filename'});continue
            stage=match.group(1);found_stages.add(stage)
            if stage not in expected:
                violations.append({'file':str(path.relative_to(folder)),'issue':'unexpected_request_stage'});continue
            request=read(path);payload,job=expected[stage];checked+=1
            allowed_request_keys={'role','skill','input','output_schema','model','runtime_contract','format_repair'}
            if set(request)-allowed_request_keys:
                violations.append({'file':str(path.relative_to(folder)),'issue':'unexpected_top_level_request_fields'})
            expected_prompt=REVIEW_PROMPT if role=='review' else (V0/'skills/bridgeqa-blind-solver/SKILL.md').read_text(encoding='utf-8')
            expected_schema=SCHEMAS['supervisor' if role=='review' else 'blind-solver']
            if request.get('skill')!=expected_prompt or digest(request.get('output_schema'))!=digest(expected_schema):
                violations.append({'file':str(path.relative_to(folder)),'issue':'prompt_or_schema_differs_from_frozen_contract'})
            if digest(request.get('input'))!=digest(payload):
                violations.append({'file':str(path.relative_to(folder)),'issue':'input_differs_from_exact_allowlisted_projection','job':job})
            if role=='review':
                actual=request.get('input',{})
                if job['condition']=='A' and 'generator_explanation' in actual:
                    violations.append({'file':str(path.relative_to(folder)),'issue':'A_contains_generator_explanation'})
                if job['condition'] in ('A','B') and 'external_relation_hints' in actual:
                    violations.append({'file':str(path.relative_to(folder)),'issue':'AB_contains_external_hints'})
            else:
                try:CORE.validate_projection(request.get('input',{}))
                except (ValueError,KeyError,TypeError):
                    violations.append({'file':str(path.relative_to(folder)),'issue':'blind_projection_allowlist_failure'})
            response_path=path.with_name(path.name.replace('.request.json','.response.json'))
            if response_path.exists():
                sid=read(response_path).get('session_id')
                if sid in sids:violations.append({'file':str(path.relative_to(folder)),'issue':'duplicate_session_id_within_role'})
                if sid:sids.add(sid)
        reports[role]={'request_attempts_checked':checked,'scheduled_stages':len(expected),
                       'persisted_request_stages':len(found_stages),'stages_without_request':len(set(expected)-found_stages),
                       'unique_response_sessions':len(sids),'violations':violations,
                       'all_observed_projections_match':not violations,
                       'scope':'Persisted initial and format-repair raw request input objects; hidden references/program conclusions are excluded by exact allowlist equality.'}
    return reports


def runtime_accounting(folder):
    folder=Path(folder);responses=sorted(folder.rglob('*.response.json'))
    requests=sorted(folder.rglob('*.request.json'));sessions=[];observations=[]
    allowed=('input_tokens','output_tokens','prompt_tokens','completion_tokens','total_tokens',
             'cache_read_input_tokens','cache_creation_input_tokens','cached_tokens')
    sdk_versions=set();models=set()
    for path in requests:
        obj=read(path);contract=obj.get('runtime_contract',{})
        if contract.get('sdk_version'):sdk_versions.add(contract['sdk_version'])
        if obj.get('model'):models.add(obj['model'])
    def inspect(value,path,location=''):
        if isinstance(value,dict):
            numeric={k:v for k,v in value.items() if k in allowed and isinstance(v,(int,float))}
            if numeric:observations.append({'file':path,'location':location,'token_fields':numeric})
            for key,child in value.items():inspect(child,path,location+'/'+key)
        elif isinstance(value,list):
            for i,child in enumerate(value):inspect(child,path,location+'/'+str(i))
    for path in responses:
        obj=read(path)
        if obj.get('session_id'):sessions.append(obj['session_id'])
        # Only structured telemetry is inspected; never parse or export final text.
        inspect(obj.get('events',[]),str(path.relative_to(folder)),'events')
        inspect(obj.get('notifications',[]),str(path.relative_to(folder)),'notifications')
    return {'request_attempt_files':len(requests),'response_attempt_files':len(responses),
            'unique_response_sessions':len(set(sessions)),'duplicate_response_session_ids':len(sessions)-len(set(sessions)),
            'technical_failure_files':len(list(folder.rglob('*.technical-failure.json'))),
            'format_error_files':len(list(folder.rglob('*.format-error.json'))),
            'sdk_versions':sorted(sdk_versions),'models':sorted(models),
            'usage_observations':observations,'usage_available':bool(observations),
            'cost_rmb':None,'usage_limit':'Raw structured token observations can include repeated cumulative/delta telemetry; do not sum them into billable tokens without provider reconciliation.'}


def selfcheck_hint_coverage():
    """Minimal offline assertions for the strict exposure definition."""
    assert not effective_hints({'known_library_issues':[{'library':'C02','source_row':1}]})
    assert not effective_hints({'facts':[{'comparisons':[{'known_issue_rows':[1]}]}]})
    assert not effective_hints({'matches':[{'known_issue':True}]})
    assert effective_hints({'matches':[{'source_row':2}]})
    family={'family_id':'CHECK','origin':{'entities':[], 'facts':[{'id':'P'},{'id':'N'}]},
            'variants':[{'condition':'base','gold':{'proofs':[{'facts':['P']} ]}}]}
    case={'case_id':'CHECK-CASE','family_id':'CHECK','track':'source',
          'external_relation_hints':{'facts':[{'fact_id':'N','comparisons':[{'library':'C01',
            'matches':[{'source_row':2}],'conflict_hints':[]}]}],
            'known_library_issues':[{'library':'C02','source_row':1}]}}
    coverage=library_hint_coverage([case],[family]);row=coverage['per_source_case'][0]
    assert row['stratum']=='noise_only'
    assert row['libraries']['C02']['warning_only'] and not row['libraries']['C02']['any_usable_fact_hint']
    assert not coverage['conflict_exposure']['C02']['may_claim_tested_nonempty_conflict_hints']
    case['external_relation_hints']['facts'][0]['fact_id']='P'
    assert library_hint_coverage([case],[family])['per_source_case'][0]['stratum']=='base_proof_related'
    return {'hint_coverage_selfcheck':'passed'}


def analyze(batch,reviews,blind,out):
    batch=Path(batch);out=Path(out)
    cases=read(batch/'cases.frozen.json');refs=read(batch/'references.frozen.json')
    families=read(batch/'families.frozen.json')
    review_rows=load_rows(reviews);blind_rows=load_rows(blind)
    normalized_refs={key:dict(value) for key,value in references_by_case(refs).items()}
    for ref in normalized_refs.values():
        if ref.get('status') in UNADJUDICATED:ref['status']='pending'
    summary=summarize(cases,normalized_refs,review_rows)
    for counts in summary['metrics'].values():
        for field in ('technical_failure','protocol_failure','not_run','unadjudicated'):
            counts.setdefault(field,0)
    refsmap=references_by_case(refs)
    summary['reference_status_counts']=dict(collections.Counter(r.get('status','missing') for r in refsmap.values()))
    summary['family_macro']=family_macro(cases,refs,review_rows)
    summary['source_clusters']=source_clusters(families)
    summary['hint_effect_strata']=hint_changes(summary,cases)
    summary['hint_effect_strata_algorithm']='legacy recursive exposure algorithm retained for comparison; may count known-library warnings and does not distinguish base-proof relevance.'
    summary['library_hint_coverage']=library_hint_coverage(cases,families)
    summary['strict_hint_effect_strata']=strict_hint_changes(summary,summary['library_hint_coverage'],cases)
    summary['stability_distributions']=[{**s,'verdict_counts':dict(collections.Counter(v if v is not None else 'technical_or_not_run' for v in s['decisions']))} for s in summary['stability']]
    summary['input_projection_audit']=request_projection_audit(cases,families,reviews,blind)
    summary['runtime_accounting']={'reviews':runtime_accounting(reviews),'blind':runtime_accounting(blind)}
    summary['semantic_localization']={'status':'pending_independent_gpt_post_audit',
        'exact_code_match_is_semantic_localization':False,
        'required_adjudication_fields':['case_id','condition','repeat','correct_defect_identified','correct_material_location','reviewer_kind','rationale'],
        'audit_file':None,'main_result_includes_semantic_localization':False}
    summary['formal_release']=False
    blind_report=blind_summary(families,blind_rows)
    save_new_or_same(out/'review-summary.json',summary)
    save_new_or_same(out/'blind-summary.json',blind_report)
    save_new_or_same(out/'analysis-manifest.json',{'cases_sha256':digest(cases),'references_sha256':digest(refs),
        'families_sha256':digest(families),'review_results_sha256':digest(review_rows),'blind_results_sha256':digest(blind_rows),
        'formal_release':False,'analysis_status':'machine_accounting_pending_independent_post_audit'})
    return summary,blind_report


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ('batch','reviews','blind','out'):parser.add_argument('--'+name,type=Path)
    parser.add_argument('--selfcheck',action='store_true')
    args=parser.parse_args()
    if args.selfcheck:print(json.dumps(selfcheck_hint_coverage()))
    else:
        if any(getattr(args,name) is None for name in ('batch','reviews','blind','out')):
            parser.error('--batch, --reviews, --blind and --out are required for analysis')
        a,b=analyze(args.batch,args.reviews,args.blind,args.out)
        print(json.dumps({'cases':a['case_count'],'blind_scheduled':b['scheduled'],'formal_release':False}))
