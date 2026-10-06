"""Loopback snapshot demo with separate candidate and controlled scorers."""
import hashlib
import os
import re
import stat
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from .baseline import predict
from .pipeline import build_run
from .pilot import ROOT
from .protocol import score_sample, validate_input
from .controlled import score_case, strict_json_loads, strict_json_bytes
from .validation import require


def export_target(output, track, name):
    """Fixed server-generated path; reject links/aliases before writing."""
    target=Path(os.path.abspath(output))/'user-submissions'/track/name
    for item in (target,*target.parents):
        try:info=item.lstat()
        except FileNotFoundError:continue
        require(not (stat.S_ISLNK(info.st_mode) or getattr(info,'st_file_attributes',0)&getattr(stat,'FILE_ATTRIBUTE_REPARSE_POINT',1024)), 'export link/reparse point rejected')
        if item==target:
            require(stat.S_ISREG(info.st_mode) and info.st_nlink==1,'export target must be an independent regular file')
        else:require(stat.S_ISDIR(info.st_mode),'export parent must be a directory')
    target.resolve().relative_to(Path(output).resolve()/'user-submissions'/track)
    return target


def handler_for(output):
    output=Path(output)
    state=strict_json_loads((output/'state.json').read_text(encoding='utf-8'))
    require(all(s['split']=='dev_public' for s in state['samples']), 'demo only serves public development candidates')
    samples={s['sample_id']:s for s in state['samples']}
    inputs={s['sample_id']:s for s in state['inputs']}
    for sample in state.get('fixtures',{}).get('samples',[]):
        require(sample['origin']=='fictional_fixture' and sample['split']=='example','invalid fixture')
        samples[sample['sample_id']]=sample
    inputs.update({i['sample_id']:i for i in state.get('fixtures',{}).get('inputs',[])})
    controlled=state['controlled']
    controlled_cases={c['sample_id']:c for c in controlled['reference']['cases']}
    controlled_inputs={i['sample_id']:i for i in controlled['inputs']}
    require(not set(samples)&set(controlled_cases),'tracks must have distinct IDs')
    for row in [*inputs.values(),*controlled_inputs.values()]:validate_input(row)
    files={'/':('index.html','text/html'),'/index.html':('index.html','text/html'),'/app.js':('app.js','text/javascript'),'/styles.css':('styles.css','text/css'),'/state.js':('state.js','text/javascript'),'/framework.svg':('framework.svg','image/svg+xml')}
    snapshot={name:(output/'web'/name).read_bytes() for name,_ in files.values()}
    # Match pipeline's literal wrapper while also checking strict JSON above.
    import json
    expected=('window.BRIDGEQA_STATE='+json.dumps(state,ensure_ascii=False,allow_nan=False).replace('<','\\u003c')+';\n').encode('utf-8')
    require(snapshot['state.js']==expected,'state.js must wrap this session state.json; rebuild consistently before starting')
    exports={}
    results={'scope':'separate_actual_rule_tracks_not_llm','candidate':{'score':state['score'],'oracle_score':state['oracle_score']},
             'controlled':{'score':controlled['score'],'manifest':controlled['manifest'],'audit':controlled['audit']},'manifest':state['manifest'],
             'score':state['score'],'oracle_score':state['oracle_score']}
    class Handler(BaseHTTPRequestHandler):
        def reply(self,code,body,kind='application/json'):
            if not isinstance(body,bytes):body=strict_json_bytes(body)
            self.send_response(code);self.send_header('Content-Type',kind+'; charset=utf-8')
            self.send_header('Content-Length',str(len(body)));self.send_header('Cache-Control','no-store')
            self.send_header('X-Content-Type-Options','nosniff');self.end_headers();self.wfile.write(body)
        def do_GET(self):
            if self.path=='/results.json':return self.reply(200,results)
            if self.path=='/controlled-results.json':return self.reply(200,{'scope':'controlled_only_not_candidate_fixture_or_oracle',**results['controlled']})
            if self.path in exports:return self.reply(200,exports[self.path])
            if self.path not in files:return self.reply(404,{'error':'not found'})
            name,kind=files[self.path];self.reply(200,snapshot[name],kind)
        def do_POST(self):
            paths=('/api/score','/api/baseline','/api/export','/api/controlled/score','/api/controlled/baseline','/api/controlled/export')
            if self.path not in paths:return self.reply(404,{'error':'not found'})
            origin=self.headers.get('Origin')
            if origin and origin!=f'http://{self.headers.get("Host")}':return self.reply(403,{'error':'origin rejected'})
            try:
                size=int(self.headers.get('Content-Length','0'));require(0<size<=262144,'body length must be 1..262144 bytes')
                raw=self.rfile.read(size)
                try:data=strict_json_loads(raw.decode('utf-8-sig'))
                except (ValueError,UnicodeError) as exc:
                    error={'error':str(exc),'status':'submission_parse_error','sha256':hashlib.sha256(raw).hexdigest(),
                           'raw_submission_hex':raw.hex(),'identity_inferred':False}
                    try:error['raw_submission']=raw.decode('utf-8')
                    except UnicodeError:pass
                    return self.reply(400,error)
                is_controlled=self.path.startswith('/api/controlled/');track='controlled' if is_controlled else 'candidate-fixture'
                known=controlled_cases if is_controlled else samples
                require(isinstance(data,dict) and isinstance(data.get('sample_id'),str) and data['sample_id'] in known,'unknown public sample ID for this track')
                sid=data['sample_id'];action=self.path.rsplit('/',1)[1]
                require(set(data)==({'sample_id'} if action=='baseline' else {'sample_id','prediction'}),'request fields')
                public=controlled_inputs[sid] if is_controlled else inputs[sid]
                if action=='baseline':return self.reply(200,predict(public))
                prediction=data['prediction'];require(isinstance(prediction,dict) and prediction.get('sample_id')==sid,'submission sample ID mismatch')
                score=score_case(known[sid],prediction,public) if is_controlled else score_sample(known[sid],prediction)
                if action=='export':
                    export={'scope':'edited_user_demo_not_model_result','track':track,'input_sha256':hashlib.sha256(strict_json_bytes(public)).hexdigest(),'prediction':prediction,'score':score}
                    body=strict_json_bytes(export);name=hashlib.sha256(body).hexdigest()[:32]+'.json'
                    target=export_target(output,track,name);target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(body)
                    url=f'/exports/{track}/{name}';exports[url]=body
                    return self.reply(200,{'saved':f'user-submissions/{track}/{name}','url':url,'export':export})
                self.reply(200,score)
            except (ValueError,TypeError,KeyError,OverflowError,UnicodeError,OSError) as exc:self.reply(400,{'error':str(exc)})
        def log_message(self,*args):pass
    return Handler


def serve(output,port=8768):
    build_run(Path(output))
    server=ThreadingHTTPServer(('127.0.0.1',port),handler_for(output))
    print(f'BridgeQA separate-track demo: http://127.0.0.1:{port} (Ctrl+C to stop)',flush=True)
    try:server.serve_forever()
    except KeyboardInterrupt:pass
    finally:server.server_close()
