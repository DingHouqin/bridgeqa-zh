// [Catalog rendering contract](../specs/11_全量题库与最新关系题发布.md).
import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';
import {fileURLToPath} from 'node:url';
import path from 'node:path';
const root=path.resolve(path.dirname(fileURLToPath(import.meta.url)),'../..');
globalThis.location={href:'http://127.0.0.1:8768/'};
globalThis.document={addEventListener(){}};
globalThis.fetch=async url=>({ok:true,json:async()=>JSON.parse(await readFile(path.join(root,new URL(url).pathname.replace('/files/','')),'utf8'))});
const {renderCatalog,filterCatalog}=await import('../web/catalog.js');
const catalog=JSON.parse(await readFile(path.join(root,'explorer/publication_v25/catalog.json'),'utf8'));
const results=JSON.parse(await readFile(path.join(root,'explorer/publication_v25/luna.json'),'utf8'));
const escape=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const home=await renderCatalog('overview','',new URLSearchParams());
assert.match(home.html,/570/);assert.equal(home.title,'全部题目');
let materialBlocks=0;
for(const q of catalog.cases){
 const v=await renderCatalog('overview',q.key,new URLSearchParams());
 assert.ok(v.html.includes(escape(q.input.question)),q.key);
 for(const d of q.input.documents||q.input.contexts||q.input.materials||[]){assert.ok(v.html.includes(escape(typeof d==='string'?d:d.text??JSON.stringify(d,null,2))),q.key);materialBlocks++;}
 assert.ok(v.html.includes(escape(JSON.stringify(q.input,null,2))),q.key);
}
for(const cohort of catalog.cohorts)assert.equal(filterCatalog(catalog.cases,new URLSearchParams({cohort:cohort.id})).length,cohort.count);
assert.equal(filterCatalog(catalog.cases,new URLSearchParams({cohort:'v24',kind:'mother'})).length,8);
assert.equal(filterCatalog(catalog.cases,new URLSearchParams({cohort:'v24',condition:'rename_A'})).length,8);
assert.equal(filterCatalog(catalog.cases,new URLSearchParams({cohort:'v23',kind:'local'})).length,24);
assert.ok(filterCatalog(catalog.cases,new URLSearchParams({search:'惜春'})).length>0);
assert.equal(filterCatalog(catalog.cases,new URLSearchParams({search:'NoSuchTask_xyz'})).length,0);
for(const r of results.records){
 const v=await renderCatalog('results',r.key,new URLSearchParams());
 if(r.raw_response!==null)assert.ok(v.html.includes(escape(r.raw_response)),r.case_id);
 else assert.match(v.html,/没有模型答复/);
}
for(const [verdict,count] of [['正确',17],['错误',4],['语义未决',2],['技术缺失',1]]){
 const v=await renderCatalog('results','',new URLSearchParams({verdict}));assert.ok(v.html.includes(`<b>${count}</b> / 24`));
}
console.log(JSON.stringify({status:'pass',all_details:570,complete_material_blocks:materialBlocks,exact_model_answers:23,explicit_missing:1,cohorts:7}));
