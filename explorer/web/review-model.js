// [Human review contract](../specs/08_临时人工审查.md).
export const PEOPLE=['A','B'];
export const TOPICS={readability:'问题的可读性',logic:'逻辑的紧密性',complexity:'关联的复杂性',evidence:'证据的充分性',distraction:'干扰的合理性'};
export const RATING_GUIDES={
  readability:['难以理解题意，条件或指代不清','需较大改写才能理解，有多处歧义','基本可理解，个别措辞或指代需澄清','题意清楚，仅需少量润色','条件、指代与作答要求清楚，阅读顺畅'],
  logic:['推理链不成立，无法推出标注答案','缺少关键依赖，需补证据或重构步骤','主要链条成立，部分条件或衔接需说明','依赖完整，只有少量隐含条件需写明','每步依赖清楚，结论严密，未发现绕过必要步骤的捷径'],
  complexity:['直接查找即可，关系连接很少','少量串联关系，条件简单','多步连接，或需额外处理一个条件','需汇合多条线索，结合时间、筛选或表格信息','多分支与多个条件交织，需综合规则或聚合判断'],
  evidence:['材料不支持或直接反驳标注结论','缺少关键证据，现有材料不足以支撑结论','主要判断有依据，部分证据定位或适用条件需核实','关键判断均有可追溯支持，个别引用可更精确','各步证据准确且易定位，充分支持相应结论或不可作答边界'],
  distraction:['干扰破坏可作答性，或设置明显不成立','干扰牵强，几乎无需判断就能排除','干扰有一定可信度，可按题目条件排除','相近线索容易混淆，需要核对正确关系或条件','干扰自然且可信，仍能依据材料公平地区分正确与错误路径']
};
export const ACCURACY={correct:'准确',incorrect:'不准确',uncertain:'待核实'};
export const VERDICTS={accept:'可保留',revise:'需修改',reject:'不宜使用',uncertain:'待核实'};
export function assignment(rows){
  // New A combines old A+C; new B combines old B+D, 43 tasks each.
  return Object.fromEntries([...rows].sort((a,b)=>a.family_id.localeCompare(b.family_id,'en')||a.id.localeCompare(b.id,'en')).map((r,i)=>[r.id,PEOPLE[i%2]]));
}
export function units(row){
  return row.gold.proofs.length?row.gold.proofs.flatMap((proof,p)=>proof.map(n=>({key:`p${p}:${n.node_id}`,proof:p,node:n,label:`证明 ${p+1} · ${n.node_id}`}))):
    [{key:'boundary',proof:null,node:null,label:'材料不足：不可作答边界'}];
}
export function datasetKey(bundle){
  return bundle.id+':'+bundle.version+':'+bundle.review_fingerprint;
}
export function blankReview(row,owner){
  return {owner,initials:'',status:'draft',steps:Object.fromEntries(units(row).map(u=>[u.key,{accuracy:'',comment:''}])),verdict:'',ratings:Object.fromEntries(Object.keys(TOPICS).map(k=>[k,''])),comment:''};
}
export function completionErrors(review,unitKeys){
  const errors=[];
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
