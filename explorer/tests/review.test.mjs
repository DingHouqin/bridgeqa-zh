// [Human review acceptance](../specs/08_临时人工审查.md).
import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {assignment,units,blankReview,completionErrors,validateReview,TOPICS,RATING_GUIDES} from '../web/review-model.js';
const rows=readFileSync(new URL('../../data/pilot_literature_history_v0/benchmark.jsonl',import.meta.url),'utf8').trim().split(/\r?\n/).map(JSON.parse);
test('all 86 tasks assigned once, balanced and independent of input order',()=>{
  const plan=assignment(rows);assert.equal(Object.keys(plan).length,86);
  assert.deepEqual(assignment([...rows].reverse()),plan);
  assert.deepEqual(['A','B'].map(p=>Object.values(plan).filter(v=>v===p).length),[43,43]);
  const sorted=[...rows].sort((a,b)=>a.family_id.localeCompare(b.family_id,'en')||a.id.localeCompare(b.id,'en'));
  sorted.forEach((row,i)=>assert.equal(plan[row.id],['A','B','A','B'][i%4]));
});
test('five specific score anchors for every topic, initials optional for completion',()=>{
  assert.deepEqual(Object.keys(RATING_GUIDES),Object.keys(TOPICS));
  for(const anchors of Object.values(RATING_GUIDES)){assert.equal(anchors.length,5);assert.equal(new Set(anchors).size,5);}
  const row=rows[0],review=blankReview(row,'A');
  review.verdict='accept';for(const step of Object.values(review.steps))step.accuracy='correct';review.status='complete';
  assert.equal(validateReview(review,'A',units(row).map(u=>u.key)).initials,'');
});
test('every legal proof operation is required, incomplete tasks cannot be completed',()=>{
  const row=rows.find(r=>r.gold.proofs.length>1),review=blankReview(row,'A');
  assert.equal(units(row).length,row.gold.proofs.reduce((n,p)=>n+p.length,0));
  review.initials='abc';review.verdict='accept';for(const s of Object.values(review.steps))s.accuracy='correct';
  assert.deepEqual(completionErrors(review,units(row).map(u=>u.key)),[]);
  Object.values(review.steps).at(-1).accuracy='';assert.equal(completionErrors(review,units(row).map(u=>u.key)).length,1);
  review.status='complete';assert.throws(()=>validateReview(review,'A',units(row).map(u=>u.key)));
});
test('insufficient tasks review only current answerability, not prototype steps',()=>{
  const row=rows.find(r=>!r.gold.proofs.length),review=blankReview(row,'B');assert.deepEqual(Object.keys(review.steps),['boundary']);
  review.initials='def';review.verdict='revise';review.steps.boundary={accuracy:'incorrect',comment:''};
  assert.equal(completionErrors(review,['boundary']).length,2);
  review.steps.boundary.comment='缺失的是另一条必要桥接';review.comment='需要重写问题';review.status='complete';
  assert.equal(validateReview(review,'B',['boundary']).status,'complete');
});
test('reject wrong owners, unknown fields, invalid ratings and prototype-property enum attacks',()=>{
  const row=rows[0],keys=units(row).map(u=>u.key),review=blankReview(row,'A');
  assert.throws(()=>validateReview(review,'B',keys));
  review.ratings.logic=7;assert.throws(()=>validateReview(review,'A',keys));review.ratings.logic='';
  review.steps[keys[0]].accuracy='__proto__';assert.throws(()=>validateReview(review,'A',keys));
  review.steps[keys[0]].accuracy='';review.steps.unregistered={accuracy:'correct',comment:''};assert.throws(()=>validateReview(review,'A',keys));
});
