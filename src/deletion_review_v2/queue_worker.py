"""Hidden, task-owned execution queue; no credentials in files or arguments."""
import concurrent.futures
import getpass
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import msvcrt

from experiment import ROOT, HarnessCaller, read, save_new_or_same

QUEUE=ROOT/'workspace/deletion-review-v2/queue'


def execute(command,key):
    manifest=(ROOT/command['manifest']).resolve()
    if not manifest.is_relative_to(ROOT):raise ValueError('Manifest outside task')
    task=read(manifest);out=(ROOT/task['output']).resolve()
    if not out.is_relative_to(ROOT):raise ValueError('Output outside task')
    workers=command.get('workers',3)
    if command['command']=='reviews':
        from experiment import run_reviews
        return run_reviews(manifest.parent,out,key,workers=workers)
    if command['command']=='blind':
        from experiment import run_blind
        from review_cases import verify_reference_gate
        verify_reference_gate(manifest.parent)
        return run_blind(read(ROOT/task['families']),out,key,workers=workers)
    jobs=task['jobs']
    def worker(index):
        rows=[]
        with HarnessCaller(key,out,worker_id='worker-'+str(index),max_tokens=task.get('max_tokens',10000)) as caller:
            for job in jobs[index::workers]:
                try:
                    caller.call(job['name'],job['role'],job['payload'],job['schema'],job['prompt'])
                    row={'name':job['name'],'status':'completed'}
                except Exception as exc:
                    row={'name':job['name'],'status':'failed','error_type':type(exc).__name__,
                         'message':str(exc).replace(key,'[REDACTED]')[:1000]}
                print(json.dumps(row,ensure_ascii=True),flush=True);rows.append(row)
        return rows
    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as pool:
        return [r for rows in pool.map(worker,range(workers)) for r in rows]


def main():
    QUEUE.mkdir(parents=True,exist_ok=True)
    if '--launch' in sys.argv:
        key=getpass.getpass('DeepSeek runtime credential (hidden): ').strip()
        if not key:raise ValueError('Missing credential')
        log=QUEUE/'worker.log'
        with log.open('ab') as handle:
            process=subprocess.Popen([sys.executable,str(Path(__file__).resolve()),'--worker'],
                                     env=dict(os.environ,DEEPSEEK_API_KEY=key),stdin=subprocess.DEVNULL,
                                     stdout=handle,stderr=handle,creationflags=subprocess.CREATE_NO_WINDOW)
        save_new_or_same(QUEUE/('worker-'+str(process.pid)+'.json'),{'pid':process.pid,'role':'task_local_model_execution'})
        print(json.dumps({'worker_started':process.pid,'credential_persisted':False}),flush=True)
        return
    key=(getpass.getpass('DeepSeek runtime credential (hidden): ').strip() if '--foreground' in sys.argv
         else os.environ.pop('DEEPSEEK_API_KEY',''))
    if not key:raise ValueError('Missing worker credential')
    lease=(QUEUE/'worker.lease').open('a+b')
    lease.seek(0)
    if not lease.read(1):lease.write(b'0');lease.flush()
    lease.seek(0)
    try:msvcrt.locking(lease.fileno(),msvcrt.LK_NBLCK,1)
    except OSError:
        raise RuntimeError('Another task worker holds the queue lease; refusing duplicate model calls')
    while not (QUEUE/'STOP').exists():
        pending=[p for p in sorted(QUEUE.glob('job-*.json')) if not p.with_suffix('.done.json').exists() and not p.with_suffix('.failed.json').exists()]
        for path in pending:
            if path.name.endswith(('.done.json','.failed.json')):continue
            try:
                result=execute(read(path),key)
                save_new_or_same(path.with_suffix('.done.json'),{'jobs':len(result),'result':result},key)
            except Exception as exc:
                save_new_or_same(path.with_suffix('.failed.json'),{'error_type':type(exc).__name__,'message':str(exc).replace(key,'[REDACTED]')[:1600]},key)
        time.sleep(2)


if __name__=='__main__':main()
