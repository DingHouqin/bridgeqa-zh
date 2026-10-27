"""Execute exactly one initial completion per frozen slot; no format resampling."""
import argparse,base64,concurrent.futures,hashlib,importlib.metadata,json,re,subprocess,sys,time
from contextlib import contextmanager
from pathlib import Path
from scorer import ROOT,read,require,file_sha,digest,validate_plan,bind_completion
from prepare_trial import frozen,SRC
sys.path.insert(0,str(SRC))
import luna_runtime_r2 as luna

def ref(path):return {'path':path.relative_to(ROOT).as_posix(),'sha256':file_sha(path)}
def safe(message,key=None):
    text=str(message)
    if key:text=text.replace(key,'[REDACTED]')
    return re.sub(r'sk-[A-Za-z0-9_-]{16,}','[REDACTED]',text)[:1200]

@contextmanager
def exclusive_plan(plan_path):
    path=Path(plan_path).resolve();require(path.is_relative_to(ROOT/'workspace/hop-audit-v15/initial-trials'),'Plan lock outside the initial-trial workspace')
    # OS-level locks release on a crash; a stale metadata file cannot cause
    # resampling. A second live runner is refused before any inference starts.
    with (path.parent/'.execution.lock').open('a+b') as handle:
        handle.seek(0,2)
        if handle.tell()==0:handle.write(b'0');handle.flush()
        handle.seek(0);locked=False
        try:
            if sys.platform=='win32':
                import msvcrt
                try:msvcrt.locking(handle.fileno(),msvcrt.LK_NBLCK,1)
                except OSError as exc:raise ValueError('Another runner already owns this frozen plan') from exc
            else:
                import fcntl
                try:fcntl.flock(handle.fileno(),fcntl.LOCK_EX|fcntl.LOCK_NB)
                except OSError as exc:raise ValueError('Another runner already owns this frozen plan') from exc
            locked=True;yield
        finally:
            if locked:
                handle.seek(0)
                if sys.platform=='win32':msvcrt.locking(handle.fileno(),msvcrt.LK_UNLCK,1)
                else:fcntl.flock(handle.fileno(),fcntl.LOCK_UN)

def run(plan_path,credential_file=None):
    with exclusive_plan(plan_path):return _run_locked(plan_path,credential_file)

def _run_locked(plan_path,credential_file=None):
    plan_path=Path(plan_path).resolve();require(plan_path.is_relative_to(ROOT/'workspace/hop-audit-v15/initial-trials'),'Plan outside the initial-trial workspace')
    plan=read(plan_path);slots=validate_plan(plan);plan_sha=file_sha(plan_path);model=plan['configuration']['model'];directory=plan_path.parent
    order=read(directory/'execution-order.json');require(order['plan_sha256']==plan_sha and set(order['trial_ids'])==set(slots) and len(order['trial_ids'])==len(slots),'Execution order differs from the frozen complete grid')
    runtime=plan['configuration']['runtime_contract'];key=None;cli=None
    # Validate every cached/new slot before any worker can launch inference.
    for tid,(case,slot) in slots.items():
        req_path=ROOT/slot['request_path'];resp_path=ROOT/slot['response_path'];req=read(req_path)
        require(file_sha(req_path)==slot['request_sha256'] and digest(req.get('input'))==case['input_sha256'] and digest({k:v for k,v in req.items() if k!='input'})==case['request_contract_sha256'],'Frozen request differs before startup')
        receipt=Path(str(resp_path).replace('.response.json','.receipt.json'))
        expected={'trial_id':tid,'plan_sha256':plan_sha,'request_sha256':file_sha(req_path),'format_retries':0}
        if receipt.exists():require(digest(read(receipt))==digest(expected),'Corrupt or cross-slot receipt')
        if resp_path.exists():
            require(receipt.exists(),'Unreceipted cached raw is not a valid trial')
            response=read(resp_path)
            require(response.get('request_hash')==digest(req) and response.get('selected_model')==model and isinstance(response.get('session_id'),str) and bool(response['session_id']) and isinstance(response.get('final_response'),str),'Cached raw provenance differs')
            if response.get('finish_reason')=='completed':
                cached={'request':ref(req_path),'response':ref(resp_path),'initial_attempt':True,'attempt_ordinal':0}
                if req.get('runtime_contract',{}).get('transport','').startswith('codex_cli'):
                    cached['process']=ref(Path(str(resp_path).replace('.response.json','.process.json')))
                bind_completion(cached,case,plan,ROOT)
    if model=='gpt-6-luna':
        executable,catalog,version=luna.establish();require(runtime['effort']==luna.EFFORT and runtime['cli_version']==version,'Local CLI configuration changed; prepare a new plan')
        require(runtime['base_instructions_sha256']==hashlib.sha256((luna.BASE+'\n').encode()).hexdigest() and runtime['disabled_features']==luna.DISABLED,'CLI base/tool mask changed')
        actual_runtime={'transport':'codex_cli_no_daemon_ephemeral_r2','effort':luna.EFFORT,'cli_version':version,
          'base_instructions_sha256':hashlib.sha256((luna.BASE+'\n').encode()).hexdigest(),
          'tools':'code_mode_only catalog + code_mode_host disabled (fail closed); zero action events required','disabled_features':luna.DISABLED,
          'project_doc_max_bytes':0,'skip_host_skill_discovery':True,'ignore_user_config':True,'ignore_rules':True,'empty_cwd':luna.EMPTY.relative_to(ROOT).as_posix(),
          'max_output_tokens':'provider/CLI default; no CLI override supported','temperature':'provider default','seed':None,
          'shared_schema_enforcement':'same schema supplied in prompt; offline validation, no strict-provider schema rewrite'}
        require(digest(runtime)==digest(actual_runtime),'The full actual CLI runtime differs from the declared configuration')
        cli=(executable,catalog,version)
    else:
        require(model=='deepseek-flash' and credential_file,'DeepSeek requires the authorized local credential file')
        sys.path.insert(0,str(ROOT/'src/multidomain_v13'));import runtime as harness_runtime
        key=harness_runtime.credential(credential_file)
        from experiment import HarnessCaller,V0
        require(runtime['sdk_version']==importlib.metadata.version('deepseek-harness-sdk'),'SDK version changed')
        require(runtime['base_patch_hash']==digest((V0/'harness.patch.yml').read_text(encoding='utf-8')) and runtime['tool_mask_hash']==digest((V0/'solver.patch.yml').read_text(encoding='utf-8')),'Harness base/tool patch changed')
        require(type(runtime['max_tokens']) is int and runtime['max_tokens']>0,'Invalid output budget')
        actual_runtime={'transport':'official_harness_anthropic_messages','effort':'off','max_tokens':runtime['max_tokens'],
          'temperature':'provider_default','seed':None,'base_patch_hash':digest((V0/'harness.patch.yml').read_text(encoding='utf-8')),
          'tool_mask_hash':digest((V0/'solver.patch.yml').read_text(encoding='utf-8')),'tools':'all_model_tools_disabled','sdk_version':importlib.metadata.version('deepseek-harness-sdk')}
        require(digest(runtime)==digest(actual_runtime),'The full actual Harness runtime differs from the declared configuration')
    def worker(worker_id):
        caller=None;results=[]
        try:
            if not cli:caller=HarnessCaller(key,directory,worker_id='v15-initial-solver-'+str(worker_id),max_tokens=runtime['max_tokens'])
            for tid in order['trial_ids'][worker_id::3]:
                case,slot=slots[tid];request_path=ROOT/slot['request_path'];response_path=ROOT/slot['response_path'];request=read(request_path)
                require(digest({k:v for k,v in request.items() if k!='input'})==case['request_contract_sha256'] and digest(request['input'])==case['input_sha256'],'Frozen request changed before execution')
                receipt=Path(str(response_path).replace('.response.json','.receipt.json'));failure_path=Path(str(response_path).replace('.response.json','.technical-failure.json'))
                process_path=Path(str(response_path).replace('.response.json','.process.json'))
                record={'trial_id':tid,'case_id':case['id'],'input_sha256':case['input_sha256'],'configuration_sha256':plan['configuration_sha256'],'rubric_sha256':plan['rubric_sha256'],'plan_sha256':plan_sha,
                  'initial_attempt':True,'attempt_ordinal':0,'request':ref(request_path)}
                if process_path.exists():record['process']=ref(process_path)
                if response_path.exists():
                    response=read(response_path);record['response']=ref(response_path)
                    if cli:record['process']=ref(Path(str(response_path).replace('.response.json','.process.json')))
                    if response.get('finish_reason')!='completed' or failure_path.exists():
                        if not failure_path.exists():frozen(failure_path,{'trial_id':tid,'plan_sha256':plan_sha,'reason':'Retained initial response incomplete; not resampled'})
                        record.update(status='technical_failure',failure=ref(failure_path))
                    else:record.update(status='completed')
                    results.append(record);continue
                if failure_path.exists():
                    record.update(status='technical_failure',failure=ref(failure_path));results.append(record);continue
                # The receipt is frozen before inference. A missing reply never
                # triggers a new generation in this slot on a resumed execution.
                if receipt.exists():
                    frozen(failure_path,{'trial_id':tid,'plan_sha256':plan_sha,'reason':'Previously started initial attempt has no retained response; not resampled'})
                    record.update(status='technical_failure',failure=ref(failure_path));results.append(record);continue
                frozen(receipt,{'trial_id':tid,'plan_sha256':plan_sha,'request_sha256':file_sha(request_path),'format_retries':0})
                try:
                    content={k:request[k] for k in ['role','skill','input','output_schema']}
                    if cli:
                        args=luna.command(cli[0]);start=time.monotonic()
                        process_path=Path(str(response_path).replace('.response.json','.process.json'))
                        try:
                            proc=subprocess.run(args,input=json.dumps(content,ensure_ascii=False),capture_output=True,text=True,encoding='utf-8',errors='replace',cwd=luna.EMPTY,env=luna.safe_env(),timeout=300,
                              creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
                        except subprocess.TimeoutExpired as exc:
                            stdout=exc.stdout or '';stderr=exc.stderr or ''
                            def decoded(value):return value.decode('utf-8',errors='replace') if isinstance(value,bytes) else value
                            partial={'argv':args,'exit_code':None,'timeout':True,'stdout':decoded(stdout),'stderr':decoded(stderr),'elapsed_seconds':time.monotonic()-start}
                            if isinstance(stdout,bytes):partial['stdout_base64']=base64.b64encode(stdout).decode('ascii')
                            if isinstance(stderr,bytes):partial['stderr_base64']=base64.b64encode(stderr).decode('ascii')
                            frozen(process_path,partial);record['process']=ref(process_path);raise
                        frozen(process_path,{'argv':args,'exit_code':proc.returncode,'stdout':proc.stdout,'stderr':proc.stderr,'elapsed_seconds':time.monotonic()-start})
                        record['process']=ref(process_path)
                        require(proc.returncode==0,'CLI failed before a retained completion');info=luna.parse_events(proc.stdout)
                        response={**info,'request_hash':digest(request),'finish_reason':'completed','selected_model':model,'model_identity_limit':'Requested CLI alias, no provider-signed snapshot'}
                        record['process']=ref(process_path)
                    else:
                        sid='bridgeqa-v15-first-'+digest({'plan':plan_sha,'trial':tid})[:28]
                        # Deliberately bypass HarnessCaller.call's JSON-repair
                        # loop: one SDK root run, no closing repair or re-prompt.
                        result=caller._pool().run(json.dumps(content,ensure_ascii=False),session_id=sid)
                        response={'session_id':result.session_id,'finish_reason':result.finish_reason,'final_response':result.final_response,'events':result.events,'notifications':result.notifications,
                          'request_hash':digest(request),'selected_model':model,'model_identity_limit':'Explicit configured SDK alias, no provider-signed snapshot'}
                    # Persist every obtained first output, including truncated
                    # output, before classifying execution or parsing its JSON.
                    try:frozen(response_path,response)
                    except (TypeError,ValueError) as exc:
                        # Even an unexpected SDK metadata type must not erase
                        # the already paid-for initial model text.
                        essential={k:response[k] for k in ['session_id','finish_reason','final_response','request_hash','selected_model']}
                        essential['metadata_serialization_error']=safe(exc,key)
                        frozen(response_path,essential);record['response']=ref(response_path);raise
                    record['response']=ref(response_path)
                    require(response['finish_reason']=='completed','Initial response incomplete')
                    record.update(status='completed')
                except Exception as exc:
                    frozen(failure_path,{'trial_id':tid,'plan_sha256':plan_sha,'reason':safe(exc,key)})
                    record.update(status='technical_failure',failure=ref(failure_path))
                results.append(record);print(json.dumps({'trial_id':tid,'status':record['status']},ensure_ascii=False),flush=True)
        finally:
            if caller:caller.close()
        return results
    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:records=[r for rs in pool.map(worker,range(3)) for r in rs]
    require(len(records)==len(slots),'Initial trial grid is incomplete')
    out=directory/'records-initial.json';frozen(out,records)
    print(json.dumps({'records':str(out),'completed':sum(r['status']=='completed' for r in records),'technical_failure':sum(r['status']=='technical_failure' for r in records),'semantic_adjudications':0},ensure_ascii=False));return records

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--plan',required=True);p.add_argument('--credential-file');a=p.parse_args();run(a.plan,a.credential_file)
