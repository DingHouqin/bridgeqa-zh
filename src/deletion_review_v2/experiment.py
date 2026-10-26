"""Frozen A/B/C review experiments and isolated Harness calls; see module README.

No direct API fallback; reference labels never enter model projections.
"""
from __future__ import annotations

import argparse
import collections
import concurrent.futures
import dataclasses
import getpass
import hashlib
import importlib.metadata
import importlib.util
import json
import os
import random
import re
import threading
from pathlib import Path

import jsonschema

try:
    from .review_cases import project_review, verify_reference_gate
except ImportError:
    from review_cases import project_review, verify_reference_gate

ROOT = Path(__file__).resolve().parents[2]
V0 = ROOT / 'src/multi_agent_v0'
RUNTIME_WORK = ROOT / 'workspace/harness-prototype'
STARTUP_LOCK = threading.Lock()


def load_v0(name):
    spec = importlib.util.spec_from_file_location('_bridgeqa_v0_' + name, V0 / (name + '.py'))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


CORE = load_v0('core')
SCHEMAS = load_v0('contracts').SCHEMAS
FORMAT = load_v0('formatting')


def digest(value):
    return CORE.digest(value)


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def append_suffix(path, suffix):
    return Path(str(path) + suffix)


def _json_default(value):
    if dataclasses.is_dataclass(value):
        return dataclasses.asdict(value)
    if hasattr(value, 'model_dump'):
        return value.model_dump(mode='json')
    return str(value)


def save_new_or_same(path, value, secret=''):
    path = Path(path)
    encoded = json.dumps(value, ensure_ascii=False, indent=2, default=_json_default) + '\n'
    if secret and secret in encoded:
        raise ValueError('Credential in output refused')
    if path.exists():
        if path.read_text(encoding='utf-8') != encoded:
            raise ValueError('Frozen artifact differs: ' + str(path))
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(encoded, encoding='utf-8')


class HarnessCaller:
    """Generic JSON role calls. Fresh root session per attempt; a pool per worker.

    ``transport`` is an offline test double; live callers use official SDK only.
    Runtime profile stays in the previously authorized Harness workspace even
    when call outputs live in a separate artifact directory.
    """
    def __init__(self, key, out, *, worker_id='main', transport=None, max_tokens=10000):
        self.key = key
        self.out = Path(out).resolve()
        self.worker_id = worker_id
        self.transport = transport
        self.max_tokens = max_tokens
        self.harness = None
        self.calls = []
        self.out.mkdir(parents=True, exist_ok=True)

    def _pool(self):
        # Profile installation/runtime startup can touch shared package-manager state.
        # Serialize startup only; model requests still use independent concurrent roots.
        with STARTUP_LOCK:
            return self._initialize_pool()

    def _initialize_pool(self):
        if self.harness is None:
            from deepseek_harness import DeepSeekHarness
            home = RUNTIME_WORK / 'v2-runtime' / digest(str(self.out))[:16] / self.worker_id
            manifest = home / 'profiles/sdk-minimal/package.json'
            if not manifest.exists() or 'bridgeqa-harness-tools' not in read(manifest).get('dsh', {}).get('profile', {}).get('bundles', []):
                load_v0('install_plugin').install(home)
            cwd = home / 'empty-working-directory'
            cwd.mkdir(parents=True, exist_ok=True)
            self.harness = DeepSeekHarness(provider='deepseek-official', model='deepseek-flash',
                reasoning_effort='off', max_tokens=self.max_tokens, cwd=str(cwd), runtime_cwd=str(cwd),
                dsh_home=str(home), profile='sdk-minimal',
                patches=(str(V0/'harness.patch.yml'), str(V0/'solver.patch.yml')),
                api_key=self.key, base_url='https://api.deepseek.com/anthropic',
                initialize_timeout_seconds=90, request_timeout_seconds=300, shutdown_timeout_seconds=10)
            self.harness.start()
            diagnostic = self.harness.client._runtime_diagnostics()
            if 'did not activate' in diagnostic or 'failed to import' in diagnostic:
                self.close()
                raise RuntimeError('Harness startup module failure; inference withheld')
        return self.harness

    def call(self, name, role, payload, schema, prompt):
        if not re.fullmatch(r'[A-Za-z0-9_./-]+', name) or '..' in Path(name).parts or Path(name).anchor or name.startswith('/'):
            raise ValueError('Unsafe stage name')
        stage = self.out / 'calls' / name
        request = {'role': role, 'skill': prompt, 'input': payload, 'output_schema': schema,
                   'model': 'deepseek-flash', 'runtime_contract': {
                       'transport': 'official_harness_anthropic_messages', 'effort': 'off',
                       'max_tokens': self.max_tokens, 'temperature': 'provider_default', 'seed': None,
                       'base_patch_hash': digest((V0/'harness.patch.yml').read_text(encoding='utf-8')),
                       'tool_mask_hash': digest((V0/'solver.patch.yml').read_text(encoding='utf-8')),
                       'tools': 'all_model_tools_disabled'}}
        if self.transport is None:
            request['runtime_contract']['sdk_version'] = importlib.metadata.version('deepseek-harness-sdk')
        request_hash = digest(request)
        save_new_or_same(append_suffix(stage, '.input.json'), request, self.key)
        parsed_path = append_suffix(stage, '.parsed.json')
        if parsed_path.exists():
            result = read(parsed_path)
            jsonschema.validate(result, schema)
            self.calls.append({'stage': name, 'request_hash': request_hash, 'reused': True})
            return result
        format_error = None
        for attempt in range(3):
            current = dict(request)
            if format_error:
                current['format_repair'] = '仅修复JSON格式及合同，不据运行结果改变立场：' + format_error
            prefix = stage.parent / (stage.name + '.attempt-' + str(attempt))
            save_new_or_same(append_suffix(prefix, '.request.json'), current, self.key)
            response_path = append_suffix(prefix, '.response.json')
            sid = 'bridgeqa-v2-' + digest({'stage': name, 'request': current, 'attempt': attempt})[:28]
            if response_path.exists():
                response = read(response_path)
            else:
                try:
                    result = (self.transport(current, sid) if self.transport else
                              self._pool().run(json.dumps(current, ensure_ascii=False), session_id=sid))
                    response = {'session_id': result.session_id, 'finish_reason': result.finish_reason,
                                'final_response': result.final_response, 'events': result.events,
                                'notifications': result.notifications, 'request_hash': digest(current)}
                    save_new_or_same(response_path, response, self.key)
                except Exception as exc:
                    safe = str(exc).replace(self.key, '[REDACTED]') if self.key else str(exc)
                    safe = re.sub(r'sk-[A-Za-z0-9]{20,}', '[REDACTED]', safe)
                    save_new_or_same(append_suffix(prefix, '.technical-failure.json'), {'type': type(exc).__name__, 'message': safe[:1200]}, self.key)
                    raise
            if response['request_hash'] != digest(current):
                raise ValueError('Cached response input hash mismatch')
            self.calls.append({'stage': name, 'attempt': attempt, 'session_id': sid,
                               'request_hash': digest(current), 'reused': False})
            if response['finish_reason'] != 'completed':
                raise RuntimeError('Harness turn incomplete; preserve and diagnose before retry')
            content = re.sub(r'^```(?:json)?\s*|\s*```$', '', response['final_response'].strip())
            try:
                parsed, repairs = FORMAT.parse_with_closing_repair(content)
                jsonschema.validate(parsed, schema)
                if repairs:
                    save_new_or_same(append_suffix(prefix, '.syntax-repair.json'), repairs, self.key)
                save_new_or_same(parsed_path, parsed, self.key)
                return parsed
            except (ValueError, jsonschema.ValidationError) as exc:
                format_error = str(exc)[:1600]
                save_new_or_same(append_suffix(prefix, '.format-error.json'), {'error': format_error}, self.key)
        raise ValueError('Protocol failure after initial call and two format repairs')

    def close(self):
        if self.harness is not None:
            self.harness.close()
            self.harness = None

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()


REVIEW_PROMPT = '''你是独立题目质量审查员，只依据输入的实际材料核对候选声明，不使用作品记忆。每个成员的证据只能来自该成员；基准材料不能补回删证。可以接受合法替代证明。生成说明和外部提示均可能不可靠，不能取代原文核对。单题案例declared_conditions.review_scope为single_item时，不要求它具备五成员；不适用的检查应写明不适用并passed=true，而不是无故拒收。家族只检查其版本声明的必备成员，条件名是声明，仍须对照文本验证。scope_by_step明确许可的逐步来源组合不是无条件合并所有发言；核对每边是否在对应scope成立。proofs中的entities是按查询起点到答案排序的路径，facts[i]必须逐项支持entities[i]到entities[i+1]的查询步骤，不能把facts视作无序引用集合。别名必须由给定材料消解。检查required_checks，逐项返回passed和具体定位证据；问题分类major/minor，给出pass/revise/reject，不要静默修题。issues.code优先用missing_support、redundant_support、alternative_proof、quote_only_failure、scope_mixing、direction、coreference、direct_answer_shortcut、wrong_answer、wrong_status、wrong_evidence、irrelevant_deletion或other描述具体缺陷，不必为每个案例找错。pass不得含失败check、major issue或required_changes。严格按输出schema返回JSON。'''


class ProtocolError(ValueError):
    pass


def make_jobs(cases,seed=20261022):
    jobs=[{'case_id':c['case_id'],'condition':condition,'repeat':repeat}
          for c in cases for condition in ('A','B','C') for repeat in range(1,4)]
    random.Random(seed).shuffle(jobs)
    return jobs


def _execute_jobs(jobs,output,key,handler,workers=3,caller_factory=HarnessCaller):
    if not 1<=workers<=4:raise ValueError('workers must be 1..4')
    output=Path(output)
    save_new_or_same(output/'worker-plan.frozen.json',{'workers':workers,'jobs_sha256':digest(jobs)},key)
    def work(number):
        caller=caller_factory(key,output/('worker-'+str(number)),worker_id='worker-'+str(number))
        rows=[]
        try:
            for job in jobs[number::workers]:
                jid=digest(job)[:24]
                destination=output/'results'/(jid+'.json')
                if destination.exists():
                    prior=read(destination)
                    if prior['job']!=job:raise ValueError('Job identity mismatch')
                    rows.append(prior);continue
                try:
                    row={'job':job,'status':'completed',**handler(job,caller)}
                except Exception as exc:
                    safe=re.sub(r'sk-[A-Za-z0-9]{20,}','[REDACTED]',str(exc))
                    if key:safe=safe.replace(key,'[REDACTED]')
                    row={'job':job,'status':'protocol_failure' if isinstance(exc,ProtocolError) or 'Protocol failure' in safe else 'technical_failure',
                         'error_type':type(exc).__name__,'message':safe[:1000]}
                save_new_or_same(destination,row,key)
                rows.append(row)
                print(json.dumps({'finished':len(list((output/'results').glob('*.json'))),'job':job,'status':row['status']},ensure_ascii=True),flush=True)
        finally:caller.close()
        return rows
    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as pool:
        groups=list(pool.map(work,range(workers)))
    return [row for group in groups for row in group]


def run_reviews(cases,output,key,workers=3,reference_review=None,caller_factory=HarnessCaller):
    output=Path(output)
    # Accept a frozen batch folder or caller-provided cases with explicit matching review.
    if isinstance(cases,(str,Path)):
        cases,_=verify_reference_gate(cases,reference_review)
    elif not reference_review or reference_review.get('status')!='approved' or reference_review.get('reviewer_kind')!='independent_gpt_subagent' or reference_review.get('cases_sha256')!=digest(cases):
        raise ValueError('Explicit case-bound independent review required')
    indexed={c['case_id']:c for c in cases}
    jobs=make_jobs(cases)
    save_new_or_same(output/'jobs.frozen.json',jobs,key)
    save_new_or_same(output/'experiment.frozen.json',{'cases_sha256':digest(cases),'prompt_sha256':digest(REVIEW_PROMPT),'jobs_sha256':digest(jobs),'schema_sha256':digest(SCHEMAS['supervisor'])},key)
    def handler(job,caller):
        payload=project_review(indexed[job['case_id']],job['condition'])
        name='review-'+digest(job)[:24]
        answer=caller.call(name,'supervisor',payload,SCHEMAS['supervisor'],REVIEW_PROMPT)
        try:CORE.supervisor_gate(answer,payload['required_checks'])
        except ValueError as exc:raise ProtocolError('Inconsistent review contract: '+str(exc)) from exc
        return {'answer':answer,'input_hash':digest(payload)}
    return _execute_jobs(jobs,output,key,handler,workers,caller_factory)


def run_blind(families,output,key,workers=3,caller_factory=HarnessCaller):
    indexed={f['family_id']:f for f in families}
    jobs=[{'family_id':f['family_id'],'variant_index':i} for f in families for i in range(len(f['variants']))]
    jobs += [{'family_id':f['family_id'],'variant_index':None} for f in families]
    save_new_or_same(Path(output)/'jobs.frozen.json',jobs,key)
    save_new_or_same(Path(output)/'families.frozen.json',families,key)
    def handler(job,caller):
        family=indexed[job['family_id']]
        if job['variant_index'] is None:
            row={'materials':[],'gold':CORE.solve(family['query'],[])}
        else:row=family['variants'][job['variant_index']]
        if row['gold']['status']=='unresolved':raise ValueError('Unresolved semantic gold cannot be scored')
        payload=CORE.project(row,family['question'],SCHEMAS['blind-solver'])
        CORE.validate_projection(payload)
        answer=caller.call('blind-'+digest(job)[:24],'blind-solver',payload,SCHEMAS['blind-solver'],
                           (V0/'skills/bridgeqa-blind-solver/SKILL.md').read_text(encoding='utf-8'))
        return {'answer':answer,'input_hash':digest(payload),
                'checks':CORE.check_solver(answer,payload,row,family['origin'],family['query']),
                'condition':row.get('condition','no_material_diagnostic')}
    return _execute_jobs(jobs,output,key,handler,workers,caller_factory)


def summarize(cases,references,results):
    refs={r['case_id']:r for r in references} if isinstance(references,list) else references
    indexed={c['case_id']:c for c in cases}
    metrics={}; by_job={}
    actual={}
    for row in results:
        identity=digest(row['job'])
        if identity in actual:raise ValueError('Duplicate experiment result')
        actual[identity]=row
    scheduled=make_jobs(cases)
    if set(actual)-{digest(j) for j in scheduled}:raise ValueError('Unexpected experiment result')
    for job in scheduled:
        row=actual.get(digest(job),{'job':job,'status':'not_run'})
        job=row['job'];case=indexed[job['case_id']];ref=refs[job['case_id']]
        by_job[(job['case_id'],job['condition'],job['repeat'])]=row
        key=case['track']+'/'+job['condition']
        m=metrics.setdefault(key,collections.Counter())
        m['scheduled']+=1
        if ref.get('status') in ('disputed','unresolved','pending'):
            m['unadjudicated']+=1;continue
        valid=ref.get('expected_verdict')=='pass'
        major=ref.get('major_defect',not valid)
        m['valid_trials' if valid else 'defective_trials']+=1
        m['major_defect_trials']+=int(major)
        if row['status']!='completed':m[row['status']]+=1;continue
        passed=row['answer']['verdict']=='pass'
        m['decided']+=1
        m['false_block' if valid and not passed else 'unsafe_accept' if major and passed else 'incorrect_minor_disposition' if not valid and passed else 'correct_disposition']+=1
        expected=ref.get('defect_category')
        if not valid and expected:
            m['defect_localization_trials']+=1
            # Literal defect-code matching is a structural proxy, not semantic judging.
            m['defect_code_match']+=any(issue['code']==expected for issue in row['answer']['issues'])
    changes=[];stability=[]
    for case in cases:
        cid=case['case_id'];ref=refs[cid]
        if ref.get('status') in ('disputed','unresolved','pending'):continue
        expected=ref.get('expected_verdict')=='pass'
        for condition in ('A','B','C'):
            decisions=[by_job[(cid,condition,r)]['answer']['verdict'] if by_job.get((cid,condition,r),{}).get('status')=='completed' else None for r in (1,2,3)]
            stability.append({'case_id':cid,'track':case['track'],'condition':condition,'decisions':decisions,'all_three_decided':all(x is not None for x in decisions),'all_three_same':None not in decisions and len(set(decisions))==1})
        for left,right in (('A','B'),('B','C')):
            for repeat in (1,2,3):
                x=by_job.get((cid,left,repeat));y=by_job.get((cid,right,repeat))
                if not x or not y or x['status']!='completed' or y['status']!='completed':continue
                before=(x['answer']['verdict']=='pass')==expected;after=(y['answer']['verdict']=='pass')==expected
                def effective(value):
                    if isinstance(value,dict):
                        return any(bool(v) and k in ('matches','conflict_hints','potential_omissions','known_library_issues') or effective(v) for k,v in value.items())
                    if isinstance(value,list):return any(effective(v) for v in value)
                    return False
                changes.append({'case_id':cid,'track':case['track'],'pair':left+'-'+right,'repeat':repeat,'correction':not before and after,'introduced_error':before and not after,'effective_external_hints':case['track']=='source' and effective(case.get('external_relation_hints',{}))})
    rates={}
    for key,m in metrics.items():
        rates[key]={'unsafe_accept':{'numerator':m['unsafe_accept'],'denominator':m['major_defect_trials']},
                    'false_block':{'numerator':m['false_block'],'denominator':m['valid_trials']},
                    'decision_coverage':{'numerator':m['decided'],'denominator':m['scheduled']-m['unadjudicated']}}
    return {'version':'review-summary-v0.2','case_count':len(cases),'family_clusters':len({c['family_id'] for c in cases}),
            'metrics':{k:dict(v) for k,v in metrics.items()},'rates':rates,'paired_changes':changes,'stability':stability,
            'limitations':['Rates require their explicit denominators; failures and undecided references are separate.','Repeated calls are not independent questions.','Defect code matching is only a structural localization proxy.'], 'formal_release':False}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command',choices=['reviews','blind','summarize'])
    parser.add_argument('--batch',type=Path,required=True)
    parser.add_argument('--out',type=Path,required=True)
    parser.add_argument('--workers',type=int,default=3)
    args=parser.parse_args()
    if args.command=='summarize':
        rows=[read(p) for p in (args.out/'results').glob('*.json')]
        value=summarize(read(args.batch/'cases.frozen.json'),read(args.batch/'references.frozen.json'),rows)
        save_new_or_same(args.out/'summary.json',value)
        return
    key=os.environ.get('DEEPSEEK_API_KEY') or getpass.getpass('DeepSeek runtime credential (hidden): ').strip()
    if not key:raise ValueError('Missing runtime credential')
    if args.command=='reviews':run_reviews(args.batch,args.out,key,args.workers)
    else:
        verify_reference_gate(args.batch)
        run_blind(read(args.batch/'families.frozen.json'),args.out,key,args.workers)


if __name__=='__main__':main()
