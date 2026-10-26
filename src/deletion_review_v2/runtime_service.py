"""Task-local stdin job service; credential remains in process memory only."""
import concurrent.futures
import getpass
import json
import re
import sys
from pathlib import Path

from experiment import HarnessCaller, ROOT, read, save_new_or_same


def main():
    key = getpass.getpass('DeepSeek runtime credential (hidden): ').strip()
    if not key:
        raise ValueError('Missing credential')
    print('SERVICE_READY', flush=True)
    for line in sys.stdin:
        if not line.strip():
            continue
        command = json.loads(line)
        if command['command'] == 'close':
            break
        manifest = (ROOT / command['manifest']).resolve()
        if not manifest.is_relative_to(ROOT):
            raise ValueError('Task manifest outside project')
        task = read(manifest)
        out = (ROOT / task['output']).resolve()
        if not out.is_relative_to(ROOT):
            raise ValueError('Task output outside project')
        if command['command'] == 'reviews':
            from experiment import run_reviews
            batch = manifest.parent
            results = run_reviews(batch, out, key, workers=command.get('workers', 3))
            print(json.dumps({'command_complete': 'reviews', 'jobs': len(results)}), flush=True)
            continue
        if command['command'] == 'blind':
            from experiment import run_blind
            from review_cases import verify_reference_gate
            verify_reference_gate(manifest.parent)
            family_path = (ROOT / task['families']).resolve()
            if not family_path.is_relative_to(ROOT):
                raise ValueError('Families outside project')
            results = run_blind(read(family_path), out, key, workers=command.get('workers', 3))
            print(json.dumps({'command_complete': 'blind', 'jobs': len(results)}), flush=True)
            continue
        jobs = list(task['jobs'])
        workers = max(1, min(4, command.get('workers', 3)))
        def worker(index):
            results=[]
            with HarnessCaller(key, out, worker_id='worker-'+str(index), max_tokens=task.get('max_tokens',10000)) as caller:
                for job in jobs[index::workers]:
                    try:
                        value=caller.call(job['name'],job['role'],job['payload'],job['schema'],job['prompt'])
                        status={'name':job['name'],'status':'completed'}
                    except Exception as error:
                        safe=re.sub(r'sk-[A-Za-z0-9]{20,}','[REDACTED]',str(error).replace(key,'[REDACTED]'))
                        status={'name':job['name'],'status':'failed','error':safe[:1500]}
                    results.append(status)
                    print(json.dumps(status,ensure_ascii=True),flush=True)
            return results
        with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as pool:
            combined=[row for group in pool.map(worker,range(workers)) for row in group]
        save_new_or_same(out/'service-status.json',combined,key)
        print(json.dumps({'command_complete':'run','completed':sum(r['status']=='completed' for r in combined),'total':len(combined)}),flush=True)
    key=''


if __name__=='__main__':main()
