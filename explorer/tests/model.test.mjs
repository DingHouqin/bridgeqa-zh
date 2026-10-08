// [Acceptance spec](../specs/05_验收与测试.md).
import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {FACETS,filterRows,tagsFor,evidenceRoles,candidatesFor,layoutProof,proofWithStart} from '../web/model.js';
const rows=readFileSync(new URL('../../data/pilot_literature_history_v0/benchmark.jsonl',import.meta.url),'utf8')
  .trim().split(/\r?\n/).map(JSON.parse);
const row=(combo,variant='challenge',domain='history')=>rows.find(r=>r.combination_id===combo&&r.domain===domain&&(variant==='challenge'?['challenge','anonymous_challenge','unfamiliar_challenge'].includes(r.variant):r.variant===variant));

test('facet AND, within-facet OR, scene ANY/ALL, text and impossible combinations',()=>{
  assert.equal(filterRows(rows).length,86);
  const both=filterRows(rows,{scene:['S01','S28']},'','all');
  assert.equal(both.length,2);
  assert.ok(both.every(r=>r.variant==='delete_all_bridge_supports'));
  const any=filterRows(rows,{scene:['S01','S28']},'','any');
  assert.equal(any.length,rows.filter(r=>r.scenario_ids.includes('S01')||r.scenario_ids.includes('S28')).length);
  const compound=filterRows(rows,{scene:['S15','S30'],domain:['history'],variant:['challenge','anonymous_challenge']},'','all');
  assert.equal(compound.length,1);
  assert.equal(filterRows(rows,{},'F-C08-H').length,6);
  assert.equal(filterRows(rows,{domain:['history'],family:['F-C08-L']}).length,0);
});
test('every label group is available, planned scenes are not inherited',()=>{
  for(const r of rows) assert.deepEqual(Object.keys(tagsFor(r)),FACETS.map(([k])=>k));
  assert.deepEqual(tagsFor(row('C04','delete_one_support')).scene,['S01']);
  assert.equal(tagsFor(row('C09')).status[0],'answerable');
  assert.equal(tagsFor(row('C09')).truth[0],'unknown');
});

test('all current model inputs are modern Chinese; old register filters match none',()=>{
  assert.equal(filterRows(rows,{language:['classical']}).length,0);
  assert.equal(filterRows(rows,{language:['vernacular']}).length,86);
  assert.equal(filterRows(rows,{language:['mixed']}).length,0);
  assert.equal(tagsFor(row('C01','no_context')).language[0],'vernacular');
});
test('alternative support stays legal, never becomes a distractor',()=>{
  const r=row('C04');
  assert.equal(r.gold.proofs.length,2);
  const roles0=evidenceRoles(r,r.gold.proofs[0]);
  const roles1=evidenceRoles(r,r.gold.proofs[1]);
  assert.equal(roles0[r.fact_to_evidence.b],'current');
  assert.equal(roles0[r.fact_to_evidence.b2],'alternative');
  assert.equal(roles1[r.fact_to_evidence.b2],'current');
  const candidates=candidatesFor(r,r.gold.proofs[0][1]);
  assert.ok(candidates.every(c=>!['b','b2'].includes(c.fact.fact_id)));
});
test('role diversion, adjacent continuation and wrong time are classified conservatively',()=>{
  const r=row('C01','challenge','literature');
  const candidates=candidatesFor(r,r.gold.proofs[0][0]);
  assert.ok(candidates.some(c=>c.fact.fact_id==='x'&&c.kind==='adjacent'));
  assert.ok(candidates.some(c=>c.fact.fact_id==='y'&&c.kind==='continuation'));
  const time=row('C10','challenge','literature');
  assert.ok(candidatesFor(time,time.gold.proofs[0][0]).some(c=>c.fact.fact_id==='a'&&c.reason.includes('任期')));
});
test('all proof layouts preserve DAG nodes, directions and dependencies',()=>{
  for(const r of rows) for(const proof of r.gold.proofs){
    const layout=layoutProof(proof);
    assert.equal(layout.positions.size,proof.length);
    for(const edge of layout.edges) assert.ok(layout.positions.get(edge.from).x<layout.positions.get(edge.to).x);
    for(const pos of layout.positions.values()){
      assert.ok(pos.x>=0&&pos.y>=0&&pos.x+202<=layout.width&&pos.y+80<=layout.height);
    }
  }
});
test('comparison, member filtering and sums only flag the relevant non-support operation inputs',()=>{
  const compare=row('C02');
  const last=compare.gold.proofs[0].at(-1);
  assert.equal(candidatesFor(compare,last).length,2);
  const aggregate=row('C06');
  const sum=aggregate.gold.proofs[0].find(n=>n.operation==='sum');
  const candidates=candidatesFor(aggregate,sum);
  assert.equal(candidates.length,1);
  assert.equal(candidates[0].fact.object,75);
  const filter=aggregate.gold.proofs[0].find(n=>n.node_id==='filter2');
  assert.equal(candidatesFor(aggregate,filter)[0].fact.relation,'评奖组关联');
});


test('display start adds root connections and preserves every original dependency',()=>{
  for(const row of rows)for(const proof of row.gold.proofs){
    const before=JSON.stringify(proof),visual=proofWithStart(row,proof);
    assert.equal(visual.length,proof.length+1);
    assert.equal(visual[0].node_id,'n0');
    for(const n of proof){
      const v=visual.find(x=>x.node_id===n.node_id);
      assert.deepEqual(v.dependencies,n.dependencies.length?n.dependencies:['n0']);
    }
    assert.equal(JSON.stringify(proof),before);
    const graph=layoutProof(visual);
    assert.ok(graph.edges.some(e=>e.from==='n0'));
    assert.equal(graph.positions.size,proof.length+1);
  }
});
