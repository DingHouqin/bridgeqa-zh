// [Data and inference contract](../specs/03_数据映射与干扰语义.md).
export const FACETS = [
  ['domain', '取材领域'], ['language', '材料文体'], ['combination', '设计组合'], ['scene', '实际场景单元'],
  ['variant', '题目变体'], ['status', '作答状态'], ['family', '题目家族'],
  ['naming', '命名方式'], ['provenance', '事实出处类型'], ['source', '来源组'],
  ['query', '查询类型'], ['depth', '证明依赖深度'], ['proofs', '参考证明数'],
  ['noise', '追加背景长度'], ['split', '数据划分'], ['review', '复核状态'],
  ['source_read', '助手来源阅读'], ['human', '独立人工复核'], ['model', '模型运行'],
  ['truth', '规则真值']
];
export const VARIANTS = {
  control:'基础对照', challenge:'组合挑战', anonymous_challenge:'匿名挑战',
  unfamiliar_challenge:'陌生名挑战', no_context:'无材料诊断',
  clarify_second:'消歧：另一身份', delete_one_support:'删除一处支持',
  delete_all_bridge_supports:'删除全部桥接支持', delete_irrelevant:'删除无关资料',
  noise_1000:'背景 1,000 字符', noise_12000:'背景 12,000 字符',
  reorder_same_noise:'同材料重排', anonymous_control:'匿名基础对照',
  switch_question_start:'同材料切换起点', same_answer_other_proof:'同答案：另一证明',
  same_answer_original_start:'同答案：原起点', bounded_abduction:'受限溯因',
  time_2:'时间切换：馆年 2', time_unspecified:'未指定馆年'
};
export const STATUS = {answerable:'可作答', ambiguous:'多解释歧义', insufficient:'材料不足'};
export const PROVENANCE = {source_annotation:'古籍原文事实标注', source_paraphrase:'原文关系改写', synthetic_editor_setting:'原创合成设定',
  counterfactual_editor_override:'反事实编者改写', none:'无当前事实'};
export const OPERATIONS = {lookup:'关系查找', resolve_alias:'别名消解', earlier_than:'早晚比较',
  enumerate_scope:'枚举统计范围', read_complete_roster:'读取完整名录', member_test:'成员筛选',
  read_pages:'读取页数', sum:'合计求和', open_world_entailment:'开放世界规则判断',
  hypothesis:'补充假设', forward_rule_application:'正向规则推导'};

export function makeIndex(bundle) {
  return {rows:new Map(bundle.records.map(r=>[r.id,r])),
    scenarios:new Map(bundle.scenarios.map(s=>[s.id,s])),
    combinations:new Map(bundle.combinations.map(c=>[c.combination_id,c])),
    quotes:new Map(bundle.sources.flatMap(s=>s.quotes.map(q=>[q.quote_id,{...q,source:s}]))),
    sources:new Map(bundle.sources.map(s=>[s.source_id,s]))};
}
export function tagsFor(row) {
  return {
    domain:[row.domain], language:[row.material_style], combination:[row.combination_id], scene:row.scenario_ids,
    variant:[row.variant], status:[row.gold.status], family:[row.family_id],
    naming:[row.construction.naming], provenance:[...new Set(row.facts.map(f=>f.provenance))].length ?
      [...new Set(row.facts.map(f=>f.provenance))] : ['none'],
    source:[row.source_cluster_id], query:[row.query.kind], depth:[String(row.minimum_proof_depth)],
    proofs:[String(row.gold.proofs.length)], noise:[String(row.construction.noise_characters)],
    split:[row.split], review:[row.review.status], source_read:[String(row.review.assistant_source_read)],
    human:[String(row.review.independent_human_review)], model:[String(row.review.model_run)],
    truth:[row.gold.logical_truth || 'not_applicable']
  };
}
export function tagLabel(key,value,index) {
  if (key==='scene') return value+' · '+(index.scenarios.get(value)?.title || '未登记单元');
  if (key==='combination') return value+' · '+(index.combinations.get(value)?.title || '');
  const dicts={
    domain:{literature:'文学',history:'历史'}, language:{classical:'古文（历史标签）',vernacular:'现代文',mixed:'混合文体（历史标签）'}, variant:VARIANTS,status:STATUS,provenance:PROVENANCE,
    naming:{named:'自然/设定名称',anonymous:'匿名代号',unfamiliar:'陌生名称'},
    query:{walk:'串行关系',ambiguous:'多解释查询',compare:'桥接比较',sum_join:'表文筛选与聚合',
      entailment:'规则判断',abduction:'受限溯因'},
    review:{candidate:'候选 · 待复核'}, split:{pilot_development_only:'开发候选集'},
    truth:{not_applicable:'未设规则真值',unknown:'逻辑未知',true:'逻辑可证真',false:'逻辑可证假'}
  };
  if (dicts[key]) return dicts[key][value] || value;
  if (['human','model','source_read'].includes(key)) return value==='true'?'是':'否';
  if (key==='noise') return Number(value).toLocaleString()+' 字符';
  if (key==='depth') return value==='0'?'无完整证明':value+' 层';
  if (key==='proofs') return value+' 个图';
  return value;
}
export function filterRows(rows,filters={},search='',sceneMode='any') {
  const term=search.trim().toLocaleLowerCase();
  return rows.filter(row=>{
    const tags=tagsFor(row);
    if (term && ![row.id,row.family_id,row.input.question,JSON.stringify(row.gold.answers)]
      .join(' ').toLocaleLowerCase().includes(term)) return false;
    return Object.entries(filters).every(([key,values])=>{
      if (!Array.isArray(values) || !values.length) return true;
      const present=tags[key]||[];
      return key==='scene' && sceneMode==='all' ? values.every(v=>present.includes(v)) :
        values.some(v=>present.includes(v));
    });
  });
}
export function facetCounts(rows) {
  const counts=Object.fromEntries(FACETS.map(([key])=>[key,new Map()]));
  for (const row of rows) for (const [key,values] of Object.entries(tagsFor(row))) {
    for (const value of values) counts[key].set(value,(counts[key].get(value)||0)+1);
  }
  return counts;
}
export function evidenceRoles(row,proof) {
  const current=new Set(proof.flatMap(n=>n.support_evidence_ids));
  const all=new Set(row.gold.proofs.flatMap(p=>p.flatMap(n=>n.support_evidence_ids)));
  const structured=new Set(Object.values(row.fact_to_evidence));
  return Object.fromEntries(row.input.documents.map(d=>[d.id,current.has(d.id)?'current':
    all.has(d.id)?'alternative':!structured.has(d.id)&&row.construction.noise_characters>0?'background':'unreferenced']));
}
export function candidatesFor(row,node) {
  const legal=new Set(row.gold.proofs.flatMap(p=>p.flatMap(n=>n.support_fact_ids)));
  if(row.query.kind==='sum_join'&&node.operation==='sum'){
    return row.facts.filter(f=>f.relation==='统计页数'&&!legal.has(f.fact_id)).map(fact=>({
      fact,reason:'该卷本没有通过作者成员筛选；其页数不能纳入当前求和。',kind:'operation'}));
  }
  if(row.query.kind==='sum_join'&&node.operation==='member_test'){
    const proof=row.gold.proofs.find(p=>p.some(n=>n.node_id===node.node_id))||[];
    const previous=proof.find(n=>node.dependencies.includes(n.node_id)&&n.node_id.startsWith('author'));
    const work=row.facts.find(f=>previous?.support_fact_ids.includes(f.fact_id))?.subject;
    return row.facts.filter(f=>f.subject===work&&f.relation==='评奖组关联'&&f.object===row.query.group&&!legal.has(f.fact_id))
      .map(fact=>({fact,reason:'作品与该组的评奖关联，不能替代作者属于该组的成员关系。',kind:'operation'}));
  }
  if(row.query.kind==='compare'&&node.operation==='earlier_than'){
    return row.facts.filter(f=>f.datatype==='number'&&f.relation==='试行就任月份'&&!legal.has(f.fact_id))
      .map(fact=>({fact,reason:'这是试行阶段的日期，不是两条正式负责人分支取出的月份。',kind:'operation'}));
  }
  if(!node.relation&&['lookup','read_pages'].includes(node.operation)&&node.support_fact_ids.length===1){
    const anchor=row.facts.find(f=>f.fact_id===node.support_fact_ids[0]);
    if(anchor) node={...node,relation:anchor.relation,upstream:anchor.subject,direction:'out'};
  }
  if (!node.relation || node.upstream===undefined) return [];
  const inputKey=node.direction==='in'?'object':'subject';
  const outputKey=node.direction==='in'?'subject':'object';
  const found=[];
  for (const fact of row.facts) {
    if (legal.has(fact.fact_id)) continue;
    let reason='';
    if (fact[inputKey]===node.upstream && fact.relation!==node.relation)
      reason='共享当前上游，但关系/角色不是这一跳要求的「'+node.relation+'」。';
    else if (fact.relation===node.relation && fact[inputKey]!==node.upstream)
      reason='关系相似，但该事实的起点不是当前上游，不能直接接入本链。';
    else if (fact.relation===node.relation && fact[inputKey]===node.upstream && fact.period &&
      row.query.time!=null && !(fact.period[0]<=row.query.time&&row.query.time<=fact.period[1]))
      reason='关系与主体相同，但有效任期不包含题目指定馆年。';
    if (reason) found.push({fact,reason,kind:'adjacent'});
  }
  const seen=new Set(found.map(c=>c.fact.fact_id));
  let frontier=found.filter(c=>c.fact.datatype==='entity').map(c=>c.fact[outputKey]);
  for(let level=0;level<2;level++){
    const next=[];
    for(const fact of row.facts){
      if(legal.has(fact.fact_id)||seen.has(fact.fact_id)||!frontier.includes(fact[inputKey])) continue;
      found.push({fact,reason:'该候选分支的后续关系；结构连通不代表满足原问题。',kind:'continuation'});
      seen.add(fact.fact_id);
      if(fact.datatype==='entity') next.push(fact[outputKey]);
    }
    frontier=next;
  }
  return found;
}
export function proofWithStart(row,proof){
  if(!proof.length)return [];
  const start={node_id:'n0',operation:'question_start',expected_value:row.query.start??row.query.subject??proof[0].upstream??'题目给定条件',support_fact_ids:[],support_evidence_ids:[],dependencies:[]};
  return [start,...proof.map(n=>({...n,dependencies:n.dependencies.length?[...n.dependencies]:['n0']}))];
}
export function layoutProof(proof) {
  const layers=new Map();
  for(const node of proof) layers.set(node.node_id,1+Math.max(0,...node.dependencies.map(id=>layers.get(id)||0)));
  const groups=new Map();
  for(const node of proof){
    const layer=layers.get(node.node_id);
    if(!groups.has(layer)) groups.set(layer,[]);
    groups.get(layer).push(node);
  }
  const maxRows=Math.max(1,...[...groups.values()].map(g=>g.length));
  const positions=new Map();
  for(const [layer,nodes] of groups) nodes.forEach((node,i)=>{
    positions.set(node.node_id,{x:24+(layer-1)*304,y:30+i*112+(maxRows-nodes.length)*56});
  });
  return {positions,width:Math.max(460,groups.size*304+20),height:Math.max(170,maxRows*112+50),
    edges:proof.flatMap(node=>node.dependencies.map(from=>({from,to:node.node_id})))};
}
export function missingFacts(row,index) {
  const parent=index.rows.get(row.paired_changes?.parent_id||row.control_id);
  if(!parent || parent.id===row.id) return [];
  const ids=new Set(row.facts.map(f=>f.fact_id));
  return parent.facts.filter(f=>!ids.has(f.fact_id));
}

