// [GitHub storage contract](../../data/human-review/README.md).
import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {createGithubStore,encodeJSON,decodeJSON} from '../web/github-review-store.js';
import {assignment,blankReview,datasetKey} from '../web/review-model.js';
const rows=readFileSync(new URL('../../data/pilot_literature_history_v0/benchmark.jsonl',import.meta.url),'utf8').trim().split(/\r?\n/).map(JSON.parse);
const bundle={id:'pilot',version:'v1',review_fingerprint:'test',records:rows},plan=assignment(rows),row=rows.find(r=>plan[r.id]==='A');
function fixture(){
  const files=Object.fromEntries(['A','B'].map(person=>[person,{version:1,value:{format:'bridgeqa-github-review-v1',round:datasetKey(bundle),person,member:null,records:{}}}]));
  const calls=[];
  const fetcher=async(url,options)=>{
    calls.push({url,options});const person=new URL(url).pathname.split('/').at(-1).replace('.json',''),file=files[person];
    if(options.method==='PUT'){
      if(options.headers.Authorization!=='Bearer own-token')return Response.json({message:'Bad credentials'},{status:401});
      const body=JSON.parse(options.body);if(body.sha!==String(file.version))return Response.json({message:'stale sha'},{status:409});
      file.value=decodeJSON(body.content);file.version++;return Response.json({content:{sha:String(file.version)}});
    }
    return Response.json({sha:String(file.version),content:encodeJSON(file.value)});
  };
  return {files,calls,fetcher};
}
test('UTF-8 JSON round trip handles long Chinese comments',()=>{const value={comment:'中文评论'.repeat(50000)};assert.deepEqual(decodeJSON(encodeJSON(value)),value);});
test('public reads need no token and saving without authorization never writes',async()=>{
  const f=fixture(),store=createGithubStore(bundle,{fetcher:f.fetcher});assert.deepEqual((await store.read()).records,{});
  assert.ok(f.calls.every(c=>!c.options.headers.Authorization));
  await assert.rejects(store.write('/records/'+row.id,{expectedRevision:0,value:blankReview(row,'A')}),/连接GitHub/);
  assert.ok(!f.calls.some(c=>c.options.method==='PUT'));
});
test('two browsers save different A questions without overwriting each other',async()=>{
  const f=fixture(),a=createGithubStore(bundle,{fetcher:f.fetcher,getToken:()=> 'own-token'}),b=createGithubStore(bundle,{fetcher:f.fetcher,getToken:()=> 'own-token'});
  const other=rows.find(r=>plan[r.id]==='A'&&r.id!==row.id);
  await Promise.all([a.write('/records/'+row.id,{expectedRevision:0,value:blankReview(row,'A')}),b.write('/records/'+other.id,{expectedRevision:0,value:blankReview(other,'A')})]);
  assert.deepEqual(Object.keys(f.files.A.value.records).sort(),[row.id,other.id].sort());assert.equal(f.files.A.value.records[row.id].revision,1);
  assert.ok(f.calls.filter(c=>c.options.method==='PUT').every(c=>!c.options.body.includes('own-token')));
});
test('stale same-question writes return the remote record without overwriting',async()=>{
  const f=fixture(),store=createGithubStore(bundle,{fetcher:f.fetcher,getToken:()=> 'own-token'}),value=blankReview(row,'A');
  const first=await store.write('/records/'+row.id,{expectedRevision:0,value:{...value,comment:'first'}});
  await assert.rejects(store.write('/records/'+row.id,{expectedRevision:0,value:{...value,comment:'second'}}),e=>e.conflict&&e.current.value.comment==='first');
  assert.deepEqual(f.files.A.value.records[row.id],first);
});
test('A/B files stay separate and member changes preserve evaluations',async()=>{
  const f=fixture(),store=createGithubStore(bundle,{fetcher:f.fetcher,getToken:()=> 'own-token'});
  await store.write('/records/'+row.id,{expectedRevision:0,value:blankReview(row,'A')});await store.write('/members/A',{expectedRevision:0,value:{initials:'abc'}});
  assert.equal(f.files.A.value.records[row.id].revision,1);assert.equal(f.files.A.value.member.value.initials,'abc');assert.deepEqual(f.files.B.value.records,{});
});
