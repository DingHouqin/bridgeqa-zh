// [Human review contract](../specs/08_临时人工审查.md).
export const PEOPLE=['A','B','C','D'];
export const TOPICS={readability:'问题的可读性',logic:'逻辑的紧密性',complexity:'关联的复杂性',evidence:'证据的充分性',distraction:'干扰的合理性'};
export const ACCURACY={correct:'准确',incorrect:'不准确',uncertain:'待核实'};
export const VERDICTS={accept:'可保留',revise:'需修改',reject:'不宜使用',uncertain:'待核实'};
export function assignment(rows){
  return Object.fromEntries([...rows].sort((a,b)=>a.family_id.localeCompare(b.family_id,'en')||a.id.localeCompare(b.id,'en')).map((r,i)=>[r.id,PEOPLE[i%4]]));
}
export function units(row){
  return row.gold.proofs.length?row.gold.proofs.flatMap((proof,p)=>proof.map(n=>({key:`p${p}:${n.node_id}`,proof:p,node:n,label:`证明 ${p+1} · ${n.node_id}`}))):
    [{key:'boundary',proof:null,node:null,label:'材料不足：不可作答边界'}];
}
export function datasetKey(bundle){
  return bundle.id+':'+bundle.version+':'+bundle.fingerprint;
}
export function blankReview(row,owner){
  return {owner,initials:'',status:'draft',steps:Object.fromEntries(units(row).map(u=>[u.key,{accuracy:'',comment:''}])),verdict:'',ratings:Object.fromEntries(Object.keys(TOPICS).map(k=>[k,''])),comment:''};
}
export function completionErrors(review,unitKeys){
  const errors=[];
  if(!/^[a-zA-Z]{1,12}$/.test(review.initials||''))errors.push('请在负责人后填写1–12位姓名首字母');
  for(const key of unitKeys){const step=review.steps?.[key];
    if(!Object.hasOwn(ACCURACY,step?.accuracy||''))errors.push(key+' 尚未评价准确性');
    else if(step.accuracy!=='correct'&&!step.comment?.trim())errors.push(key+' 需要填写原因');
  }
  if(!Object.hasOwn(VERDICTS,review.verdict||''))errors.push('请选择整题审查结论');
  if(review.verdict&&review.verdict!=='accept'&&!review.comment?.trim())errors.push('整题需修改/不宜使用/待核实时，请填写综合意见');
  return errors;
}
export function validateReview(value,owner,unitKeys){
  const fail=()=>{throw new Error('审查字段不合法，请检查题号、负责人和步骤');};
  if(!value||value.owner!==owner||!['draft','complete'].includes(value.status)||typeof value.initials!=='string'||value.initials.length>12||
    (value.initials&&!/^[a-zA-Z]+$/.test(value.initials))||typeof value.comment!=='string'||value.comment.length>10000||
    (value.verdict!==''&&!Object.hasOwn(VERDICTS,value.verdict))||!value.steps||!value.ratings)fail();
  if(Object.keys(value.steps).length!==unitKeys.length||Object.keys(value.ratings).length!==Object.keys(TOPICS).length)fail();
  const clean={owner,initials:value.initials,status:value.status,steps:{},verdict:value.verdict,ratings:{},comment:value.comment};
  for(const key of unitKeys){const s=value.steps[key];if(!s||typeof s.comment!=='string'||s.comment.length>10000||(s.accuracy!==''&&!Object.hasOwn(ACCURACY,s.accuracy)))fail();clean.steps[key]={accuracy:s.accuracy,comment:s.comment};}
  for(const key of Object.keys(TOPICS)){const v=value.ratings[key];if(v!==''&&![1,2,3,4,5].includes(v))fail();clean.ratings[key]=v;}
  if(clean.status==='complete'&&completionErrors(clean,unitKeys).length)fail();
  return clean;
}
