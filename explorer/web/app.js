// [Interaction spec](../specs/02_标签筛选与交互.md), [semantic spec](../specs/03_数据映射与干扰语义.md).
import {FACETS,VARIANTS,STATUS,PROVENANCE,OPERATIONS,makeIndex,tagsFor,tagLabel,
  filterRows,facetCounts,evidenceRoles,candidatesFor,layoutProof,missingFacts} from './model.js';
const app=document.querySelector('#app');
const h=value=>String(value??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const valueText=value=>Array.isArray(value)?value.map(valueText).join('、'):
  typeof value==='object'&&value!==null?JSON.stringify(value):typeof value==='boolean'?(value?'是':'否'):String(value??'—');
const external=value=>{try {const url=new URL(value,location.origin);return ['http:','https:'].includes(url.protocol)?url.href:'#';}catch{return '#';}};
let registry=[],bundle,index,counts,dataset='pilot_literature_history_v0',token=0;
let listState={filters:{},search:'',sceneMode:'any',page:1,size:12};
let pageName='overview',currentId='',proofIndex=0,selectedNode='',lastDetail='';
let filterExpanded=window.innerWidth>760;
let guideMarkup;
const sortedRows=()=>[...bundle.records].sort((a,b)=>a.family_id.localeCompare(b.family_id)||a.id.localeCompare(b.id));
function route(name,id='',state=listState,ds=dataset){
  if(name==='guide') return '#guide';
  const params=new URLSearchParams({dataset:ds});
  if(name!=='overview') params.set('state',JSON.stringify(state));
  return '#'+name+(id?'/'+id:'')+'?'+params;
}
function navigate(name,id='',state=listState){
  // Keep rapid consecutive filter clicks consistent before the hashchange event is delivered.
  listState=structuredClone(state);
  location.hash=route(name,id,listState);
}
function normalizedState(raw){
  try {
    const s=JSON.parse(raw||'{}');
    return {filters:Object.fromEntries(Object.entries(s.filters||{}).filter(([key,v])=>
      FACETS.some(([f])=>f===key)&&Array.isArray(v)).map(([k,v])=>[k,v.map(String)])),
      search:String(s.search||''),sceneMode:s.sceneMode==='all'?'all':'any',
      page:Math.max(1,parseInt(s.page)||1),size:s.size===24?24:12};
  }catch{return {filters:{},search:'',sceneMode:'any',page:1,size:12};}
}
function tag(key,value,extra=''){
  const facet=FACETS.find(([k])=>k===key)?.[1]||key;
  return '<button class="tag '+(key==='scene'?'scene-tag ':'')+extra+'" data-act="filter" data-key="'+h(key)+
    '" data-value="'+h(value)+'" title="'+h(facet+'：'+tagLabel(key,value,index)+'；点击筛选')+'">'+
    (key==='scene'?'': '<span class="tag-key">'+h(facet)+' · </span>')+h(tagLabel(key,value,index))+'</button>';
}
function allTags(row){return Object.entries(tagsFor(row)).flatMap(([key,values])=>values.map(v=>tag(key,v))).join('');}
function mainTitle(kicker,title,desc=''){
  return '<div class="page-heading"><div><p class="eyebrow">'+h(kicker)+'</p><h1 id="page-title" tabindex="-1">'+h(title)+
    '</h1>'+(desc?'<p class="lead">'+h(desc)+'</p>':'')+'</div></div>';
}
function shell(content,active=pageName){
  const focus=document.activeElement?.id;
  const selection=focus==='search'?document.activeElement.selectionStart:null;
  const graphScroll=pageName==='question'&&document.title.startsWith(currentId)?
    document.querySelector('.proof-canvas')?.scrollLeft:undefined;
  app.innerHTML='<div class="layout"><aside class="sidebar"><a class="brand" href="'+route('overview')+'">'+
    '<svg viewBox="0 0 40 40" aria-hidden="true"><path d="M7 30V17Q20 1 33 17V30M7 21H33M20 9V30"/></svg>'+
    '<span>BridgeQA<small>中文多跳 · 研究审查</small></span></a><div class="nav-label">BENCHMARK ATLAS</div><nav aria-label="主导航">'+
    '<a '+(active==='overview'?'aria-current="page"':'')+' href="'+route('overview')+'"><span>01</span>选题概览</a>'+
    '<a '+(active==='questions'||active==='question'?'aria-current="page"':'')+' href="'+route('questions')+'"><span>02</span>题目与证据</a>'+
    '<a '+(active==='guide'?'aria-current="page"':'')+' href="'+route('guide')+'"><span>03</span>测试指引</a>'+
    '</nav><div class="side-note"><span class="signal"></span>本地 · 只读审查<p>看清每条关系，<br>以及偏离发生在哪里。</p>'+
    '<a href="/specs/README.md" target="_blank" rel="noopener">查看设计规格 ↗</a></div></aside><div class="workspace">'+
    '<header class="topbar"><span class="workbench-label">证据与推理工作台</span>'+(active==='guide'?
    '<span class="global-page-label">全项目固定指引 · 新增数据集时增补</span>':'<label class="dataset-picker">数据集<select id="dataset" aria-label="选择数据集">'+
    registry.map(d=>'<option value="'+h(d.id)+'" '+(d.id===dataset?'selected':'')+'>'+h(d.id)+'</option>').join('')+
    '</select></label><span class="version">'+h(bundle?.version||'')+'</span>')+'</header>'+
    '<main id="main" aria-live="polite">'+content+'</main><footer class="app-footer">BridgeQA · 候选数据审查'+
    '<span>干扰推定 ≠ 人工逐跳标注 ≠ 模型实测</span></footer></div></div>';
  if(focus&&document.getElementById(focus)){
    document.getElementById(focus).focus();
    if(selection!==null) document.getElementById(focus).setSelectionRange(selection,selection);
  }
  if(graphScroll!==undefined&&document.querySelector('.proof-canvas')){
    document.querySelector('.proof-canvas').scrollLeft=graphScroll;
  }
}
function stat(n,label,sub){return '<div class="stat"><strong>'+h(n)+'</strong><span>'+h(label)+'</span><small>'+h(sub)+'</small></div>';}
function statusBadge(row){return '<span class="status '+h(row.gold.status)+'">'+h(STATUS[row.gold.status])+
  (row.gold.logical_truth==='unknown'?' · 逻辑未知':'')+'</span>';}
function renderOverview(){
  const s=bundle.summary;
  const sourceCards=['literature','history'].map(domain=>{
    const srcs=bundle.sources.filter(src=>src.domain===domain);
    return '<article class="topic-card"><p class="eyebrow">'+(domain==='literature'?'LITERATURE / 文学叙事':'HISTORY / 史书记载')+
      '</p><h2>'+(domain==='literature'?'人物、叙事与文学目录':'家系、官署与历史档案')+'</h2><p>'+
      (domain==='literature'?'从熟悉故事中抽取关系，再用匿名、改接和目录规则检查证据依赖。':
        '按所给记载连接人物、时间与机构，区分史料锚点和合成实验设定。')+'</p><div class="source-pills">'+
      srcs.map(src=>'<a href="'+h(external(src.revision_url))+'" target="_blank" rel="noopener">'+h(src.title)+' ↗</a>').join('')+
      '</div><button class="text-button" data-act="open-domain" data-value="'+domain+'">查看'+
      (domain==='literature'?'文学':'历史')+'题目 · '+s.domains[domain]+' 条 →</button></article>';
  }).join('');
  const combinationRows=bundle.combinations.map(c=>{
    const rows=bundle.records.filter(r=>r.combination_id===c.combination_id);
    return '<tr><td><strong>'+h(c.combination_id)+'</strong></td><td><button class="link-button" data-act="open-combo" data-value="'+
      h(c.combination_id)+'">'+h(c.title)+' →</button><small>'+h(c.material_plan)+'</small></td><td class="planned-tags">'+
      c.planned_scene_ids.map(id=>'<a href="'+h(bundle.links.catalog)+'" target="_blank" rel="noopener" title="'+
        h(index.scenarios.get(id)?.title)+'">'+h(id)+'</a>').join(' ')+'</td><td>'+rows.length+
      ' <small>/ '+new Set(rows.map(r=>r.family_id)).size+' 家族</small></td><td class="goal">'+h(c.validation_goal)+'</td></tr>';
  }).join('');
  const sceneGrid=bundle.scenarios.map(sce=>{
    const n=counts.scene.get(sce.id)||0;
    return n?'<button class="scene-cell" data-act="open-scene" data-value="'+h(sce.id)+'"><b>'+h(sce.id)+
      '</b><span>'+h(sce.title)+'</span><small>'+n+' 条</small></button>':
      '<div class="scene-cell inactive"><b>'+h(sce.id)+'</b><span>'+h(sce.title)+'</span><small>本批未单列</small></div>';
  }).join('');
  shell(mainTitle('01 / TOPIC & DESIGN','文学与历史，作为推理的试验场',bundle.topic)+
    '<section class="hero"><div><span class="hero-badge">首轮候选 · '+h(bundle.version)+'</span><h2>从问题出发，<br>把每一次跳跃摊开。</h2>'+
    '<p>一条相似线索是否接得上？一个熟悉答案是否真的有证据？在这里逐题审查。</p>'+
    '<a class="primary" href="'+route('questions')+'">进入题目库 <span>→</span></a></div><div class="hero-map" aria-label="结构示意">'+
    '<span class="map-start">问题起点</span><div class="map-line"></div><span class="map-mid">必要桥接</span>'+
    '<div class="map-line"></div><span class="map-end">有据答案</span><span class="map-decoy">相似角色 / 旧知识</span>'+
    '<small>相似不代表关系成立</small></div></section>'+
    '<section class="stats" aria-label="数据规模">'+stat(s.records,'主任务记录',s.families+' 个题目家族，含配对变体')+
    stat(s.scenarios,'实际场景单元',s.catalog_scenarios+' 个候选单元中的本批覆盖')+
    stat(s.combinations,'设计组合','每组文学、历史各一母题')+stat(s.sources,'原文资料页',s.oracle_tasks+' 条 Oracle 诊断另列')+'</section>'+
    '<div class="section-heading"><h2>选题与取材</h2><a href="'+h(bundle.links.readme)+'" target="_blank" rel="noopener">数据设计说明 ↗</a></div>'+
    '<section class="topic-grid">'+sourceCards+'</section><section class="notice"><b>本批口径</b><span>'+
    s.statuses.answerable+' 条可答 · '+s.statuses.ambiguous+' 条歧义 · '+s.statuses.insufficient+' 条材料不足。'+
    '独立人工复核 '+s.human_reviewed+' 条，模型实跑 '+s.model_run+' 条；多个家族共享来源与模板。</span></section>'+
    '<div class="section-heading"><h2>先组合，再构题</h2><a href="'+h(bundle.links.combinations)+'" target="_blank" rel="noopener">组合登记 ↗</a></div>'+
    '<div class="table-wrap"><table class="combination-table"><thead><tr><th>组合</th><th>设计配方</th><th>计划单元</th><th>记录</th><th>验收关注</th></tr></thead><tbody>'+
    combinationRows+'</tbody></table></div><p class="caption">这里列计划配方；每条题目使用自己的实际标签，删桥/换年等变体并不套用整组标签。</p>'+
    '<div class="section-heading"><h2>场景覆盖图</h2><small>标签非互斥，点击进入对应题目</small></div><section class="scene-grid">'+sceneGrid+'</section>'+
    '<section class="protocol-strip"><div><p class="eyebrow">KNOWLEDGE & PROTOCOL</p><h2>背景知识干扰，靠对照检查</h2><p>'+
    '自然名 / 匿名 / 陌生名 / 无材料 · 保度数改接 · 删一处与删全部 · 换起点 · 同答案不同证明</p></div>'+
    '<a href="'+h(bundle.links.protocol)+'" target="_blank" rel="noopener">多步骤评判设计 ↗</a></section>');
}
function filterPanel(){
  return '<aside class="filter-panel"><div class="filter-heading"><h2>标签筛选</h2><button class="text-button" data-act="clear">清空</button></div>'+
    '<p class="caption">跨维度同时满足；同维度任一满足。计数为数据集全量。</p>'+
    '<label class="field-label" for="facet-search">查找标签</label><input id="facet-search" placeholder="例如：角色、C08、匿名" autocomplete="off">'+
    '<label class="field-label" for="scene-mode">多场景匹配方式</label><select id="scene-mode"><option value="any" '+(listState.sceneMode==='any'?'selected':'')+
    '>包含任一选中场景</option><option value="all" '+(listState.sceneMode==='all'?'selected':'')+'>同时包含全部选中场景</option></select>'+
    FACETS.map(([key,title],i)=>'<details class="facet-group" '+(i<4||listState.filters[key]?.length?'open':'')+'><summary>'+h(title)+
      '<span>'+ (listState.filters[key]?.length||'')+'</span></summary><div class="facet-values">'+
      [...counts[key].entries()].sort((a,b)=>a[0].localeCompare(b[0],undefined,{numeric:true})).map(([value,n])=>{
        const checked=listState.filters[key]?.includes(value);
        return '<button class="facet-value '+(checked?'checked':'')+'" data-act="filter" data-key="'+h(key)+
          '" data-value="'+h(value)+'" data-facetlabel="'+h((title+' '+tagLabel(key,value,index)+' '+value).toLowerCase())+
          '" aria-pressed="'+!!checked+'"><span class="check">'+(checked?'✓':'')+'</span><span>'+h(tagLabel(key,value,index))+
          '</span><small>'+n+'</small></button>';
      }).join('')+'</div></details>').join('')+'</aside>';
}
function questionCard(row){
  const tags=tagsFor(row);
  const otherTags=Object.entries(tags).filter(([key])=>key!=='scene').flatMap(([key,values])=>values.map(v=>tag(key,v))).join('');
  return '<article class="question-card"><div class="card-top"><span class="mono">'+h(row.id)+'</span>'+statusBadge(row)+
    '</div><a class="question-link" href="'+route('question',row.id)+'">'+h(row.input.question)+'</a>'+
    '<div class="card-meta">'+h(row.family_id)+' <span>·</span> '+h(VARIANTS[row.variant]||row.variant)+' <span>·</span> '+
    (row.domain==='history'?'历史':'文学')+' <span>·</span> '+(row.minimum_proof_depth?row.minimum_proof_depth+' 层依赖':'无完整证明')+'</div>'+
    '<div class="tag-list">'+row.scenario_ids.map(s=>tag('scene',s)).join('')+'</div>'+
    '<details class="card-all-tags"><summary>全部标签 <span>'+Object.values(tags).reduce((a,v)=>a+v.length,0)+' 项</span></summary>'+
    '<div class="tag-list">'+otherTags+'</div></details><div class="card-answer"><span>标准答案</span><strong>'+
    h(row.gold.answers.length?valueText(row.gold.answers):'材料不足，不补齐缺失关系')+'</strong>'+
    '<a href="'+route('question',row.id)+'">剖析证据 →</a></div></article>';
}
function renderQuestions(){
  const results=filterRows(sortedRows(),listState.filters,listState.search,listState.sceneMode);
  const pages=Math.max(1,Math.ceil(results.length/listState.size));
  listState.page=Math.min(listState.page,pages);
  const start=(listState.page-1)*listState.size;
  const active=Object.entries(listState.filters).flatMap(([key,values])=>values.map(value=>tag(key,value,'active-filter')));
  shell(mainTitle('02 / QUESTIONS & EVIDENCE','题目与证据','按实际标签选题，沿正确依赖查证，也看见可能的偏离。')+
    '<div class="catalog-layout"><details class="filter-shell" '+(window.innerWidth>760||filterExpanded?'open':'')+'>'+
    '<summary class="filter-shell-title">标签筛选 · 点击展开 / 收起</summary>'+filterPanel()+'</details><section class="question-results"><div class="search-row">'+
    '<label class="search-box"><span>⌕</span><input id="search" value="'+h(listState.search)+'" placeholder="搜索问句、题号、家族或标准答案" aria-label="搜索题目"></label>'+
    '<select id="page-size" aria-label="每页数量"><option value="12" '+(listState.size===12?'selected':'')+'>每页 12 条</option>'+
    '<option value="24" '+(listState.size===24?'selected':'')+'>每页 24 条</option></select></div>'+
    '<div class="results-heading"><p id="result-count"><b>'+results.length+'</b> 条记录 <span>/ '+new Set(results.map(r=>r.family_id)).size+
    ' 个家族</span></p><small>家族 / 题号稳定排序</small></div>'+
    (active.length?'<div class="active-filters"><span>已选 · 点击移除</span>'+active.join('')+'</div>':'')+
    (results.length?results.slice(start,start+listState.size).map(questionCard).join(''):'<div class="empty-state"><h2>没有同时满足这些条件的题目</h2>'+
      '<p>可以移除一项标签、改用“任一场景”，或清空筛选。</p><button class="primary" data-act="clear">清空条件</button></div>')+
    '<div class="pagination"><button data-act="page" data-page="'+(listState.page-1)+'" '+(listState.page===1?'disabled':'')+
    '>← 上一页</button><span>第 '+listState.page+' / '+pages+' 页</span><button data-act="page" data-page="'+(listState.page+1)+'" '+
    (listState.page===pages?'disabled':'')+'>下一页 →</button></div></section></div>');
}
function proofGraphic(proof){
  const {positions,width,height,edges}=layoutProof(proof);
  const lines=edges.map(e=>{
    const a=positions.get(e.from),b=positions.get(e.to),x1=a.x+202,y1=a.y+40,x2=b.x,y2=b.y+40;
    return '<path class="proof-edge" d="M '+x1+' '+y1+' C '+(x1+26)+' '+y1+', '+(x2-26)+' '+y2+', '+x2+' '+y2+'" marker-end="url(#arrow)"/>';
  }).join('');
  const nodes=proof.map(n=>{
    const pos=positions.get(n.node_id);
    const value=valueText(n.expected_value);
    const label=n.relation?(n.direction==='in'?'逆查 · ':'')+n.relation:OPERATIONS[n.operation]||n.operation;
    return '<g class="proof-node '+(n.node_id===selectedNode?'selected':'')+'" tabindex="0" role="button" aria-label="'+
      h(n.node_id+' '+label+' '+value)+'" data-act="node" data-node="'+h(n.node_id)+'" transform="translate('+pos.x+','+pos.y+')">'+
      '<title>'+h(label+' → '+value)+'</title><rect width="202" height="80" rx="12"/><text x="14" y="21" class="node-id">'+h(n.node_id)+
      '</text><text x="14" y="42" class="node-operation">'+h(label.length>19?label.slice(0,18)+'…':label)+
      '</text><text x="14" y="64" class="node-value">'+h(value.length>19?value.slice(0,18)+'…':value)+'</text></g>';
  }).join('');
  return '<div class="proof-canvas"><svg width="'+width+'" height="'+height+'" viewBox="0 0 '+width+' '+height+'" aria-label="参考证明依赖图">'+
    '<defs><marker id="arrow" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="6" markerHeight="6" orient="auto">'+
    '<path d="M0 0L10 5L0 10Z"/></marker></defs>'+lines+nodes+'</svg></div>';
}
function quoteButtons(fact){
  const refs=[...(fact.quote_ids||[]),...(fact.parent_quote_ids||[])];
  return refs.map(q=>'<button class="quote-link" data-act="scroll" data-target="quote-'+h(q)+'">'+h(q)+
    (fact.parent_quote_ids?.includes(q)?' · 改写前锚点':'')+' ↗</button>').join('');
}
function factView(fact,extra=''){
  return '<div class="fact '+extra+'"><div class="fact-line"><span class="mono">'+h(fact.fact_id)+'</span><strong>'+h(fact.subject)+
    '</strong><span class="relation">— '+h(fact.relation)+' →</span><strong>'+h(valueText(fact.object))+'</strong></div>'+
    '<div class="fact-foot"><span>'+h(PROVENANCE[fact.provenance]||fact.provenance)+
    (fact.period?' · 馆年 '+fact.period[0]+'–'+fact.period[1]+'（含端点）':'')+'</span>'+quoteButtons(fact)+'</div></div>';
}
function nodeAnalysis(row,displayRow,proof,isPrototype){
  const node=proof.find(n=>n.node_id===selectedNode)||proof[0];
  if(!node) return '';
  const supportFacts=node.support_fact_ids.map(id=>displayRow.facts.find(f=>f.fact_id===id)).filter(Boolean);
  const potential=isPrototype?[]:candidatesFor(row,node);
  const old=index.rows.get(row.control_id);
  const changed=isPrototype?[]:supportFacts.filter(f=>row.construction.changed_fact_ids.includes(f.fact_id))
    .map(f=>old?.facts.find(of=>of.fact_id===f.fact_id)).filter(Boolean);
  const docs=new Set(row.input.documents.map(d=>d.id));
  return '<section class="node-analysis"><div class="section-heading"><h3>选中步骤 · '+h(node.node_id)+'</h3><span class="badge">'+
    h(OPERATIONS[node.operation]||node.operation)+'</span></div><div class="node-summary"><span>上游 '+h(valueText(node.upstream??node.dependencies))+
    '</span><strong>→ '+h(valueText(node.expected_value))+'</strong></div><p class="caption">依赖：'+h(node.dependencies.join('、')||'问题起点 / 题面条件')+
    (node.direction==='in'?'；这是合法逆向查前驱，不把谓词当对称关系。':'')+'</p>'+
    '<h4>'+(isPrototype?'原型支持（不代表当前完整证据）':'本步骤的合法支持')+'</h4>'+
    (supportFacts.length?supportFacts.map(f=>factView(f,'support-fact')).join(''):
      '<p class="caption">'+(node.operation==='hypothesis'?'这是待补假设，不是材料中已为真的事实。':
        '这是比较、筛选或聚合等操作节点，依据来自前置步骤，不能捏造独立证据。')+'</p>')+
    '<div class="evidence-jumps">'+node.support_evidence_ids.map(id=>'<button class="text-button" data-act="scroll" data-target="doc-'+h(id)+
      '" '+(!docs.has(id)?'disabled':'')+'>定位材料 '+h(id)+' ↓</button>').join('')+'</div>'+
    '<div class="potential-heading"><h4>这一跳可能如何偏离</h4><span>结构规则推定</span></div>'+
    (potential.length?potential.map(c=>'<div class="potential-fact"><p>'+h(c.reason)+'</p>'+factView(c.fact)+'</div>').join(''):
      '<p class="caption">'+(isPrototype?'当前没有完整证明；这里只解释原型。请在缺失支持区查看被删除的关系。':
        '未找到符合当前结构规则的非支持分支；这不表示没有语义或知识干扰。')+'</p>')+
    (changed.length?'<div class="old-bridge"><h4>改接前的旧关系 · 仅作记忆干扰对照</h4>'+changed.map(f=>factView(f)).join('')+
      '<p class="caption">这条旧关系不属于当前世界的有效桥。引文只能支撑改写前内容。</p></div>':'')+
    '<details class="operation-fields"><summary>查看操作完整标注</summary><pre>'+h(JSON.stringify(node,null,2))+'</pre></details></section>';
}
function documentText(text){
  const lines=text.split('\n');
  const tableLines=lines.filter(l=>l.trim().startsWith('|'));
  if(tableLines.length>=3){
    const cells=line=>line.split('|').slice(1,-1).map(c=>c.trim());
    return '<p>'+h(lines.filter(l=>!l.trim().startsWith('|')).join('\n'))+'</p><div class="table-wrap"><table class="source-table"><thead><tr>'+
      cells(tableLines[0]).map(c=>'<th>'+h(c)+'</th>').join('')+'</tr></thead><tbody>'+
      tableLines.slice(2).map(l=>'<tr>'+cells(l).map(c=>'<td>'+h(c)+'</td>').join('')+'</tr>').join('')+
      '</tbody></table></div><details><summary>查看原始表格文本</summary><pre>'+h(text)+'</pre></details>';
  }
  if(text.length>700) return '<p class="background-preview">'+h(text.slice(0,260))+'…</p><details><summary>展开全文 · '+
    text.length.toLocaleString()+' 字符</summary><pre class="full-background">'+h(text)+'</pre></details>';
  return '<p class="document-text">'+h(text)+'</p>';
}
function materials(row,proof,isPrototype){
  const roles=evidenceRoles(row,isPrototype?[]:proof);
  const currentFacts=new Set((isPrototype?[]:proof).flatMap(n=>n.support_fact_ids));
  const allFacts=new Set(row.gold.proofs.flatMap(p=>p.flatMap(n=>n.support_fact_ids)));
  const partial=new Set(isPrototype?proof.flatMap(n=>n.support_fact_ids):[]);
  const selected=proof.find(n=>n.node_id===selectedNode);
  const focused=new Set(isPrototype?[]:selected?.support_evidence_ids||[]);
  const labels={current:'当前证明支持',alternative:'其他合法证明支持',background:'构造背景',unreferenced:'非参考支持 · 不等于干扰'};
  return '<section id="materials" class="panel materials"><div class="section-heading"><h2>当前题面材料</h2><small>'+
    row.input.documents.length+' 份 · '+row.context_characters.toLocaleString()+' 字符 · 原顺序</small></div>'+
    '<p class="caption">这里只有当前实际输入；来源引文和原型缺失证据另列，不会补进题面。</p>'+
    (row.input.documents.length?row.input.documents.map(d=>{
      const facts=row.facts.filter(f=>row.fact_to_evidence[f.fact_id]===d.id);
      const hasPartial=isPrototype&&facts.some(f=>partial.has(f.fact_id));
      return '<article id="doc-'+h(d.id)+'" class="document '+h(roles[d.id])+' '+(focused.has(d.id)?'focused':'')+'">'+
        '<div class="document-heading"><span class="mono">'+h(d.id)+'</span><span class="badge">'+
        (hasPartial?'仍在材料中的部分原型支持':labels[roles[d.id]])+'</span></div>'+documentText(d.text)+
        (facts.length?'<details class="document-facts" open><summary>结构化事实与溯源 · '+facts.length+' 项</summary>'+
          facts.map(f=>factView(f,currentFacts.has(f.fact_id)?'support-fact':allFacts.has(f.fact_id)?'alternative-fact':'')).join('')+
          '</details>':'')+'</article>';
    }).join(''):'<div class="empty-state compact"><h3>当前材料为空</h3><p>这是无材料诊断。不能从熟悉剧情或原型资料补齐当前答案。</p></div>')+'</section>';
}
function sourceSection(row,missing,displayRow){
  const facts=[...row.facts,...missing];
  if(!row.gold.proofs.length) facts.push(...displayRow.facts);
  const quotes=new Set(facts.flatMap(f=>[...f.quote_ids,...(f.parent_quote_ids||[])]));
  const sources=bundle.sources.filter(s=>s.quotes.some(q=>quotes.has(q.quote_id)));
  return '<section class="panel" id="source-materials"><div class="section-heading"><h2>溯源资料与原文</h2><small>不是额外题面证据</small></div>'+
    '<p class="caption">原文锚点用于审查改写；合成事实没有古籍依据。反事实只保留改写前出处，匿名题须用映射回溯。</p>'+
    (sources.length?sources.map(s=>'<article class="source-record"><div class="section-heading"><h3>'+h(s.title)+'</h3>'+
      '<a href="'+h(external(s.revision_url))+'" target="_blank" rel="noopener">固定修订网页 ↗</a></div><p class="caption">'+h(s.author_attribution)+
      ' · 采集 '+h(s.retrieved_at)+' · 助手阅读，未独立人工复核</p>'+
      '<a class="license-link" href="https://creativecommons.org/licenses/by-sa/4.0/" target="_blank" rel="noopener">'+h(s.license_displayed)+' ↗</a>'+
      s.quotes.filter(q=>quotes.has(q.quote_id)).map(q=>'<blockquote id="quote-'+h(q.quote_id)+'"><div><b>'+h(q.quote_id)+'</b> · '+h(q.locator)+
        '</div><p>'+h(q.text)+'</p>'+(q.capture_note?'<small>'+h(q.capture_note)+'</small>':'')+'</blockquote>').join('')+'</article>').join(''):
      '<p>本题使用原创合成设定，没有外部原文引文。完整事实出处仍在材料标注中保留。</p>')+'</section>';
}
function pairSection(row){
  const parent=index.rows.get(row.paired_changes?.parent_id);
  const family=sortedRows().filter(r=>r.family_id===row.family_id);
  let comparison='<p class="caption">这是基础对照。其他条件的变换从本家族的实际配对记录追溯。</p>';
  if(parent){
    const dif=row.paired_changes;
    const changes=[
      ...dif.added_fact_ids.map(id=>({title:'新增',after:row.facts.find(f=>f.fact_id===id)})),
      ...dif.removed_fact_ids.map(id=>({title:'删除',before:parent.facts.find(f=>f.fact_id===id)})),
      ...dif.rewritten_fact_ids.map(id=>({title:'改写',before:parent.facts.find(f=>f.fact_id===id),after:row.facts.find(f=>f.fact_id===id)}))
    ];
    comparison='<p>比较对象：<a href="'+route('question',parent.id)+'">'+h(VARIANTS[parent.variant])+' · '+h(parent.id)+'</a></p>'+
      '<div class="pair-summary"><div><small>比较对象答案</small><b>'+h(valueText(parent.gold.answers)||'材料不足')+'</b></div>'+
      '<span>→</span><div><small>当前答案</small><b>'+h(valueText(row.gold.answers)||'材料不足')+'</b></div></div>'+
      '<p class="caption">问题 '+(dif.question_changed?'变化':'保持')+' · 答案 '+(dif.answer_changed?'变化':'保持')+
      ' · 状态 '+(dif.status_changed?'变化':'保持')+'。答案相同不等于证明相同。</p>'+
      '<details '+(changes.length<=6?'open':'')+'><summary>事实变化 · '+changes.length+' 项</summary>'+
      (changes.length?changes.map(c=>'<div class="change-item"><span class="badge">'+c.title+'</span>'+
        (c.before?'<div class="before"><small>原型 / 比较对象</small>'+factView(c.before)+'</div>':'')+
        (c.after?'<div><small>当前题</small>'+factView(c.after)+'</div>':'')+'</div>').join(''):'<p class="caption">没有事实变更；可能只改变问题、材料顺序或背景长度。</p>')+'</details>';
  }
  return '<section class="panel" id="comparison"><div class="section-heading"><h2>配对差异与家族</h2><small>'+h(row.family_id)+'</small></div>'+comparison+
    (Object.keys(row.entity_mapping).length?'<details><summary>实体命名映射 · '+Object.keys(row.entity_mapping).length+' 项</summary>'+
      '<table class="mapping-table"><thead><tr><th>原实体</th><th>当前名称</th></tr></thead><tbody>'+
      Object.entries(row.entity_mapping).map(([a,b])=>'<tr><td>'+h(a)+'</td><td>'+h(b)+'</td></tr>').join('')+'</tbody></table></details>':'')+
    '<h3>同家族其他版本</h3><div class="family-links">'+family.map(r=>'<a class="'+(r.id===row.id?'current':'')+'" href="'+route('question',r.id)+'">'+
      '<strong>'+h(VARIANTS[r.variant]||r.variant)+'</strong><small>'+h(valueText(r.gold.answers)||'材料不足')+'</small></a>').join('')+'</div></section>';
}
function renderDetail(){
  const row=index.rows.get(currentId);
  if(!row){shell(mainTitle('问题定位','题号未找到','该题号不属于当前登记的数据集。')+
    '<a class="primary" href="'+route('questions')+'">返回题目库</a>');return;}
  const isPrototype=!row.gold.proofs.length;
  const displayRow=isPrototype?index.rows.get(row.control_id)||row:row;
  const available=displayRow.gold.proofs;
  proofIndex=Math.min(proofIndex,Math.max(0,available.length-1));
  const proof=available[proofIndex]||[];
  if(!proof.some(n=>n.node_id===selectedNode)) selectedNode=proof[0]?.node_id||'';
  const missing=missingFacts(row,index);
  const resultRows=filterRows(sortedRows(),listState.filters,listState.search,listState.sceneMode);
  const position=resultRows.findIndex(r=>r.id===row.id);
  const operationCount=proof.length;
  const combo=index.combinations.get(row.combination_id);
  const explanations=row.gold.interpretations?.length?'<div class="interpretations">'+row.gold.interpretations.map(i=>'<div><b>'+
    h(i.label)+'</b><span>→ '+h(valueText(i.answers))+'</span></div>').join('')+'</div>':'';
  const proofControls=available.length>1?'<label>选择完整证明<select id="proof-choice">'+available.map((p,i)=>{
    const meaning=!isPrototype&&row.gold.status==='ambiguous'&&row.gold.interpretations[i]?
      ' · '+row.gold.interpretations[i].label:'';
    return '<option value="'+i+'" '+(i===proofIndex?'selected':'')+'>证明 '+(i+1)+meaning+'</option>';
  }).join('')+'</select></label>':'<span class="badge">'+(isPrototype?'原型参考图':'1 个完整参考证明')+'</span>';
  const trap=row.attack_design;
  shell('<div class="breadcrumbs"><a href="'+route('questions')+'">← 返回筛选结果</a><span>/</span><span>'+h(row.family_id)+'</span>'+
    '<div class="detail-prev-next">'+(position>0?'<a href="'+route('question',resultRows[position-1].id)+'">← 前一题</a>':'')+
    (position>=0&&position<resultRows.length-1?'<a href="'+route('question',resultRows[position+1].id)+'">后一题 →</a>':'')+'</div></div>'+
    mainTitle('QUESTION ANATOMY / '+row.id,'逐题剖析')+
    '<section class="question-intro"><div class="intro-labels">'+statusBadge(row)+'<span class="badge">'+h(VARIANTS[row.variant]||row.variant)+
    '</span><span class="mono">'+h(row.combination_id)+' · '+h(combo?.title)+'</span></div><h2>'+h(row.input.question)+'</h2>'+
    '<div class="answer-box"><span>当前标准答案</span><strong>'+h(row.gold.answers.length?valueText(row.gold.answers):'材料不足 · 不补事实')+
    '</strong></div>'+explanations+'<div class="detail-tags tag-list">'+allTags(row)+'</div>'+
    '<div class="intro-actions"><button class="text-button" data-act="scroll" data-target="materials">查看全部材料 ↓</button>'+
    '<button class="text-button" data-act="scroll" data-target="comparison">比较家族变体 ↓</button>'+
    '<button class="text-button" data-act="download">下载本题完整标注 ↧</button></div>'+
    '<details><summary>统一作答指令与输出约定</summary><p>'+h(row.input.instruction)+'</p><pre>'+h(JSON.stringify(row.input.output_contract,null,2))+
    '</pre></details></section><div class="detail-grid"><div class="detail-main"><section class="panel proof-panel '+(isPrototype?'prototype':'')+'">'+
    '<div class="section-heading"><h2>'+(isPrototype?'原型链：当前无完整支持':'正确跳跃与操作依赖')+'</h2>'+proofControls+'</div>'+
    (isPrototype?'<div class="notice warning"><b>不可作答</b><span>下图来自基础原型，仅用于解释缺失；它不是当前题目的合法证明，不能据此回答。</span></div>':'')+
    '<p class="caption">'+(isPrototype?'原型操作图':'当前完整证明')+' · '+operationCount+' 个操作 · 依赖深度 '+
    (isPrototype?displayRow.minimum_proof_depth:row.minimum_proof_depth)+' 层。点击节点查看支持与潜在偏离。</p>'+
    proofGraphic(proof)+nodeAnalysis(row,displayRow,proof,isPrototype)+'</section>'+
    (missing.length?'<section class="panel missing-support"><h2>当前缺失的原型事实</h2><p class="caption">来自实际比较对象；以下内容不在当前材料中。</p>'+
      missing.map(f=>factView(f)).join('')+'</section>':'')+
    materials(row,proof,isPrototype)+sourceSection(row,missing,displayRow)+pairSection(row)+'</div>'+
    '<aside class="analysis-rail"><section class="rail-card"><p class="eyebrow">DESIGN INTENT</p><h3>干扰设计预期</h3><p>'+h(trap.target_failure)+
    '</p><ol>'+trap.predicted_error_path.map(p=>'<li>'+h(p)+'</li>').join('')+'</ol><div class="rail-rule"><b>验收条件</b><p>'+
    h(trap.acceptance)+'</p></div><small>这是组合层面的设计预期，不代表该变体仍含全部干扰，也不是模型观察。</small></section>'+
    '<section class="rail-card"><h3>预设错误候选</h3><p class="wrong-values">'+h(valueText(row.expected_wrong_answers)||'未单独指定')+
    '</p><small>仅供审查假设。当前答案可能被错误路径碰巧得到，应同时查证明。</small></section>'+
    '<section class="rail-card"><h3>知识与材料边界</h3>'+row.knowledge_risks.map(r=>'<p class="risk-line">'+h(r)+'</p>').join('')+
    '<p class="caption">匿名化不自动消除剧情、关系或分词差异。没有人工逐跳干扰标注或模型实测。</p>'+
    (row.construction.degree_preserving_claim?'<span class="badge">双边改接 · 保持逐关系入出度</span>':'')+'</section>'+
    '<section class="rail-card"><h3>实际场景说明</h3>'+Object.entries(row.scenario_annotations).map(([id,desc])=>'<div class="scene-note"><b>'+
    h(id)+' · '+h(index.scenarios.get(id)?.title)+'</b><p>'+h(desc)+'</p></div>').join('')+
    '<a href="'+h(bundle.links.catalog)+'" target="_blank" rel="noopener">打开场景定义 ↗</a></section>'+
    '<section class="rail-card"><h3>审查状态</h3><p>候选数据 · 开发划分</p><p>独立人工复核：'+
    (row.review.independent_human_review?'是':'否')+'<br>模型实跑：'+(row.review.model_run?'是':'否')+'</p>'+
    '<a href="'+h(bundle.links.readme)+'" target="_blank" rel="noopener">数据说明 ↗</a></section></aside></div>');
}
async function onRoute(){
  const request=++token;
  const [path,query='']=location.hash.slice(1).split('?');
  const params=new URLSearchParams(query);
  const wanted=params.get('dataset')||registry[0]?.id||dataset;
  pageName=(path||'overview').split('/')[0];
  currentId=(path||'').split('/')[1]||'';
  if(!['overview','questions','question','guide'].includes(pageName)) pageName='overview';
  if(pageName!=='guide') listState=normalizedState(params.get('state'));
  if(currentId!==lastDetail){proofIndex=0;selectedNode='';lastDetail=currentId;}
  try {
    if(pageName==='guide'){
      if(!guideMarkup){
        const response=await fetch('/testing-guide.html');
        if(!response.ok) throw new Error('固定指引内容读取失败，请刷新或检查页面文件。');
        guideMarkup=await response.text();
      }
      if(request!==token) return;
      if(!registry.some(d=>d.id===dataset)) dataset=registry[0]?.id||'pilot_literature_history_v0';
      shell(mainTitle('03 / TESTING GUIDE','测试指引','全项目固定说明，按数据集分章维护。')+guideMarkup,'guide');
      document.title='03 测试指引 · BridgeQA';
      const section=params.get('section');
      if(section) document.getElementById(section)?.scrollIntoView({block:'start'});
      return;
    }
    if(!bundle||dataset!==wanted){
      dataset=wanted;
      app.innerHTML='<main class="boot" aria-live="polite">正在读取数据集与证据索引…</main>';
      const response=await fetch('/api/datasets/'+encodeURIComponent(wanted)+'/bundle');
      const loaded=await response.json();
      if(!response.ok) throw new Error(loaded.error||'数据集加载失败');
      if(request!==token) return;
      bundle=loaded;index=makeIndex(bundle);counts=facetCounts(bundle.records);
    }
    if(request!==token) return;
    if(pageName==='overview') renderOverview();
    else if(pageName==='questions') renderQuestions();
    else renderDetail();
    document.title=(pageName==='overview'?'选题概览':pageName==='questions'?'题目与证据':currentId)+' · BridgeQA';
  }catch(error){
    if(request!==token) return;
    bundle=null;
    app.innerHTML=pageName==='guide'?'<main class="boot"><h1>暂时无法打开测试指引</h1><p>'+h(error.message)+
      '</p><a href="#overview?dataset=pilot_literature_history_v0">返回概览</a></main>':
      '<main class="boot"><h1>暂时无法打开数据集</h1><p>'+h(error.message)+'</p><a href="#overview?dataset=pilot_literature_history_v0">返回已登记的数据集</a></main>';
  }
}
function changeFilters(key,value,single=false){
  const state=structuredClone(listState);
  const current=state.filters[key]||[];
  state.filters[key]=single?[value]:current.includes(value)?current.filter(v=>v!==value):[...current,value];
  if(!state.filters[key].length) delete state.filters[key];
  state.page=1;
  navigate('questions','',state);
}
function jump(target){
  const el=document.getElementById(target);
  if(!el) return;
  const parent=el.closest('details');
  if(parent) parent.open=true;
  el.scrollIntoView({behavior:'smooth',block:'center'});
  el.classList.add('jump-highlight');
  setTimeout(()=>el.classList.remove('jump-highlight'),2000);
}
app.addEventListener('click',event=>{
  const el=event.target.closest('[data-act]');
  if(!el) return;
  const act=el.dataset.act;
  if(act==='filter') changeFilters(el.dataset.key,el.dataset.value);
  else if(act==='open-domain') navigate('questions','',{...normalizedState(),filters:{domain:[el.dataset.value]}});
  else if(act==='open-combo') navigate('questions','',{...normalizedState(),filters:{combination:[el.dataset.value]}});
  else if(act==='open-scene') navigate('questions','',{...normalizedState(),filters:{scene:[el.dataset.value]}});
  else if(act==='clear') navigate('questions','',normalizedState());
  else if(act==='page') navigate('questions','',{...listState,page:Number(el.dataset.page)});
  else if(act==='scroll') jump(el.dataset.target);
  else if(act==='node'){selectedNode=el.dataset.node;renderDetail();}
  else if(act==='download'){
    const row=index.rows.get(currentId);
    const url=URL.createObjectURL(new Blob([JSON.stringify(row,null,2)],{type:'application/json;charset=utf-8'}));
    const a=document.createElement('a');a.href=url;a.download=row.id+'.json';a.click();
    setTimeout(()=>URL.revokeObjectURL(url),1000);
  }
});
app.addEventListener('keydown',event=>{
  if(event.target.matches('.proof-node')&&['Enter',' '].includes(event.key)){
    event.preventDefault();event.target.dispatchEvent(new MouseEvent('click',{bubbles:true}));
    const selected=document.querySelector('.proof-node.selected');selected?.focus();
  }
});
let searchTimer;
app.addEventListener('input',event=>{
  if(event.target.id==='search'){
    clearTimeout(searchTimer);
    const search=event.target.value;
    searchTimer=setTimeout(()=>navigate('questions','',{...listState,search,page:1}),250);
  }else if(event.target.id==='facet-search'){
    const term=event.target.value.toLowerCase().trim();
    for(const button of document.querySelectorAll('.facet-value')){
      button.hidden=!button.dataset.facetlabel.includes(term);
    }
    for(const group of document.querySelectorAll('.facet-group')){
      group.hidden=![...group.querySelectorAll('.facet-value')].some(b=>!b.hidden);
      if(term&&!group.hidden) group.open=true;
    }
  }
});
app.addEventListener('change',event=>{
  if(event.target.id==='dataset'){
    bundle=null;location.hash=route('overview','',normalizedState(),event.target.value);
  }else if(event.target.id==='scene-mode') navigate('questions','',{...listState,sceneMode:event.target.value,page:1});
  else if(event.target.id==='page-size') navigate('questions','',{...listState,size:Number(event.target.value),page:1});
  else if(event.target.id==='proof-choice'){proofIndex=Number(event.target.value);selectedNode='';renderDetail();}
});
app.addEventListener('toggle',event=>{
  if(event.target.classList.contains('filter-shell')) filterExpanded=event.target.open;
},true);
window.addEventListener('hashchange',onRoute);
try {
  const response=await fetch('/api/datasets');
  if(!response.ok) throw new Error('数据集登记读取失败');
  registry=await response.json();
  if(!location.hash) history.replaceState(null,'',route('overview'));
  await onRoute();
}catch(error){app.innerHTML='<main class="boot"><h1>服务暂不可用</h1><p>'+h(error.message)+'</p><p>请确认本地服务仍在运行，然后刷新。</p></main>';}

