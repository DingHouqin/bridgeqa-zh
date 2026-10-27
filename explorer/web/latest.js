// [Publication contract](../specs/10_最新题库与模型评测发布.md).
// This viewer consumes reviewed publication snapshots and never grades answers.
import {siteURL} from './urls.js';
const esc=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const base='files/explorer/publication_v18/';
const phases={current_r2:'现有题库',novel_r1:'新算子30题',revised_r1:'旧题修订16题',bounds_r1:'部分信息边界4题'};
const partitions={primary:'主任务',node:'节点诊断',control:'状态对照'};
const dimensions={answer:'A 答案',logical_proof:'L 推导',output_contract:'C 完整合同'};
const models=['gpt-6-luna','gpt-6.1-sol'];
const hopStatus={local_dependency_only:'仅有局部依赖资格',not_applicable:'不适用必要跳数主张',parent_only:'依赖证书仅限父题',requires_review:'逐跳依赖需复核'};
const cache=new Map();
async function get(name){
  if(!cache.has(name))cache.set(name,fetch(siteURL(base+name+'.json')).then(async r=>{if(!r.ok)throw Error('发布数据读取失败：'+name);return r.json();}).catch(e=>{cache.delete(name);throw e;}));
  return cache.get(name);
}
function link(page,key='',params=new URLSearchParams()){
  const p=new URLSearchParams(params);if(page==='results')p.set('cohort','v18');
  return '#/'+page+(key?'/'+encodeURIComponent(key):'')+(p.size?'?'+p:'');
}
function heading(k,t,d){return `<div class="page-heading"><div><p class="eyebrow">${esc(k)}</p><h1 id="page-title" tabindex="-1">${esc(t)}</h1><p class="lead">${esc(d)}</p></div></div>`;}
function badge(v){return `<span class="verdict verdict-${esc(v)}">${esc(v)} ${esc({P:'通过',F:'失败',U:'需复核'}[v]||'未登记')}</span>`;}
function download(name,label){return `<a href="${siteURL(base+name)}" download>${esc(label)} ↧</a>`;}
function policy(){return '<section class="notice warning"><b>合成开发与回归验证</b><span>每题每模型仅1次首答，五次指标未计算。U需人工／强智能体复核，保留原分母。全局无捷径认证为0，声明关系段数不等于必要跳数。</span></section>';}
const json=v=>JSON.stringify(v,null,2);
function counts(rows,dim){const n={P:0,F:0,U:0};for(const r of rows)n[r.labels[dim]]++;return n;}
function summaryTable(rows,questions){
  const qmap=new Map(questions.map(q=>[q.question_key,q]));
  const groups=[['current_r2','primary'],['current_r2','node'],['current_r2','control'],['revised_r1','primary'],['novel_r1','primary'],['bounds_r1','primary']];
  return `<div class="table-wrap"><table class="latest-summary"><caption>分层首答结果，各格为P / F / U（份）。每层独立保留分母。</caption><thead><tr><th>阶段／任务</th><th>模型</th><th>份数</th>${Object.values(dimensions).map(d=>'<th>'+esc(d)+'</th>').join('')}</tr></thead><tbody>${groups.flatMap(([phase,part])=>models.map(model=>{
    const rs=rows.filter(r=>r.phase===phase&&r.model===model&&qmap.get(r.question_key)?.partition===part);
    return `<tr><th>${esc(phases[phase])}<small>${esc(partitions[part]||part)}</small></th><td class="mono">${esc(model)}</td><td>${rs.length}</td>${Object.keys(dimensions).map(d=>{const c=counts(rs,d);return `<td>${c.P} / ${c.F} / ${c.U}</td>`;}).join('')}</tr>`;
  })).join('')}</tbody></table></div>`;
}
function options(items,value){return '<option value="">全部</option>'+items.map(([v,label])=>`<option value="${esc(v)}" ${v===value?'selected':''}>${esc(label)}</option>`).join('');}
function filters(page,params,cases){
  const fields=[['phase','阶段',Object.entries(phases)],['partition','任务分区',Object.entries(partitions)],['domain','领域',[...new Set(cases.map(q=>q.metadata?.domain).filter(Boolean))].sort().map(x=>[x,x])]];
  if(page==='results')fields.push(['model','被测模型',models.map(m=>[m,m])],...Object.entries(dimensions).map(([d,label])=>[d,label,[['P','P 通过'],['F','F 失败'],['U','U 需复核']]]));
  else fields.push(['hops','声明关系段数',[['3','3段（非必要跳数认证）'],['4','4段（非必要跳数认证）']]]);
  return `<form class="latest-filters" data-latest-form="${page}"><label class="latest-search">搜索题号、问题或材料<input name="search" id="latest-search" value="${esc(params.get('search')||'')}" placeholder="例如 稳定匹配、SCI、challenge3"></label>${fields.map(([name,label,items])=>`<label>${esc(label)}<select name="${name}">${options(items,params.get(name)||'')}</select></label>`).join('')}<button type="submit">应用筛选</button><a href="${link(page)}">重置</a></form>`;
}
function filterCases(cases,params){
  const term=(params.get('search')||'').toLowerCase();
  return cases.filter(q=>['phase','partition'].every(k=>!params.get(k)||q[k]===params.get(k))&&(!params.get('domain')||q.metadata?.domain===params.get('domain'))&&(!params.get('hops')||String(q.metadata?.declared_hops)===params.get('hops'))&&(!term||[q.case_id,q.public_id,q.input.question,json(q.input.contexts)].join(' ').toLowerCase().includes(term)));
}
function pager(page,params,total,size=12){
  const max=Math.max(1,Math.ceil(total/size)),current=Math.min(max,Math.max(1,Number(params.get('page'))||1));
  const pg=n=>{const p=new URLSearchParams(params);p.set('page',String(n));return link(page,'',p);};
  return {start:(current-1)*size,html:`<nav class="pagination" aria-label="结果分页">${current>1?`<a href="${pg(current-1)}">上一页</a>`:''}<span>第 ${current} / ${max} 页</span>${current<max?`<a href="${pg(current+1)}">下一页</a>`:''}</nav>`};
}
function taskFacts(q){return `<span>${esc(phases[q.phase]||q.phase)}</span><span>${esc(partitions[q.partition]||q.partition)}</span><span>${esc(q.metadata?.domain||'未声明领域')}</span><span>${q.metadata?.declared_hops?esc(q.metadata.declared_hops)+'段声明结构':'段数未声明'}</span>`;}
function resultLabels(r){return `<div class="result-labels">${Object.entries(dimensions).map(([d,label])=>`<span>${esc(label)} ${badge(r.labels[d])}</span>`).join('')}</div>`;}
function observation(r,compact=false){
  return `<article class="model-result"><h3>${esc(r.model)}</h3>${resultLabels(r)}<div class="review-rationale"><b>实际裁决理由</b><p>${esc(typeof r.rationale==='string'?r.rationale:json(r.rationale))}</p></div>${compact?'':`<p class="caption">JSON：${r.json_valid?'有效':'无效，首次原文保留'}。n=1，pass@5与pass^5为空。</p><details class="raw-answer" open><summary>首次原答，逐字保留</summary><pre>${esc(r.raw_response)}</pre></details><details><summary>哈希与验收来源</summary><dl class="hash-list"><dt>原答文本SHA256</dt><dd>${esc(r.raw_text_sha256)}</dd><dt>原答源文件SHA256</dt><dd>${esc(r.response_file_sha256)}</dd><dt>本题输入SHA256</dt><dd>${esc(r.input_sha256)}</dd><dt>审查者</dt><dd>${esc(r.reviewers?.join('、'))}</dd><dt>批准记录</dt><dd>${esc(json(r.approval))}</dd><dt>原始相对来源，仅作审计定位</dt><dd>${esc(json(r.source))}</dd></dl></details>`}</article>`;
}
async function detail(page,key,cases,records){
  const q=cases.find(q=>q.question_key===key);
  if(!q)return heading('未找到任务','该题号未在本次发布中登记','请返回题库选择已登记任务。')+`<a href="${link('latest')}">返回最新题库</a>`;
  const paired=records.filter(r=>r.question_key===key).sort((a,b)=>models.indexOf(a.model)-models.indexOf(b.model));
  return heading(page==='latest'?'05 / LATEST TASK':'05 / HISTORICAL RESULTS',q.case_id,'同一公共输入的两模型首次作答。先看当前材料，再查看资格边界与逐维裁决。')+policy()+
    `<p class="latest-links"><a href="${link('latest')}">返回题库</a><a href="${link('results')}">返回全部实测</a><a href="${link(page==='latest'?'results':'latest',key)}">${page==='latest'?'查看本题原答对照':'查看本题清洁输入'}</a><button data-latest-jump="latest-model-comparison">跳到两模型原答</button><button data-latest-download="${esc(key)}">下载本题清洁输入</button></p><div class="task-meta">${taskFacts(q)}</div><section class="panel"><h2>问题</h2><p class="latest-question">${esc(q.input.question)}</p>${q.input.instruction?`<p>${esc(q.input.instruction)}</p>`:''}<h3>当前题面全部材料</h3>${(q.input.contexts||[]).map(c=>`<article class="latest-context"><b>${esc(c.context_id||c.id||c.document_id||'材料')}</b><p>${esc(typeof c==='string'?c:c.text??json(c))}</p></article>`).join('')}<details><summary>完整清洁输入及作答合同</summary><pre>${esc(json(q.input))}</pre></details><details><summary>本题资格与跳数边界</summary><pre>${esc(json({metadata:q.metadata,qualification:q.qualification}))}</pre></details></section>`+
    `<details class="panel reference-review"><summary>题意与资格边界</summary><p class="caption">本次不公开独立标准答案与证明包。下方只说明本题的资格状态；模型原答及已验收裁决理由单列。</p>${q.qualification.target_ambiguity?'<section class="notice warning"><b>题意需复核</b><span>此旧题对目标集合存在不同自然读法，两模型答案维度均保留U，不以历史参考指定唯一正确答案。</span></section>':''}<pre>${esc(json(q.qualification))}</pre></details>`+
    `<h2 class="comparison-title" id="latest-model-comparison" tabindex="-1">两模型逐题表现</h2><div class="model-comparison">${paired.map(r=>observation(r)).join('')}</div>`;
}
function scoringPage(){
  return heading('07 / SCORING','评分器与过程评价','冻结v15聚合器读取已独立验收的裁决，程序门禁、语义审核与指标聚合各有明确职责。')+
  `<section class="notice"><b>评分对象是可核验的外显依据</b><span>不把模型解释当成真实内部思维，不要求机械复述标准路径。正确的短证明、上下界和合法剪枝均可接受。</span></section>`+
  `<section class="panel scoring-dimensions"><h2>每份作答分三维判断</h2><dl><dt>A　答案</dt><dd>最终状态正确，目标集合完整，数值、单位及全部并列方案正确。</dd><dt>L　推导</dt><dd>A通过，并提供充分、真实且一致的可核对依据。保留明确错误操作时，末尾正确答案不能抵消它。</dd><dt>C　完整输出合同</dt><dd>A、L都通过，再核原始直接JSON、Schema、实际事实ID、候选路径全集及连续引文。C不是单纯格式率。</dd></dl><p>每维分别记录 ${badge('P')} ${badge('F')} ${badge('U')}。确定的语义错误仍为F，不能大范围改成U提高成绩。</p></section>`+
  `<section class="panel"><h2>过程评价如何实现</h2><ol class="scoring-steps"><li><b>冻结题材与协议</b><p>登记输入、参考、rubric、配置、计划槽和哈希。题材或采样资格不合格时，不开放正式点估计。</p></li><li><b>绑定实际首次原答</b><p>程序核对输入、请求、原答与裁决哈希，检查实际模型和运行配置，保留失败、缺槽及非法JSON，不用修复答案补采成功槽。</p></li><li><b>独立语义审查</b><p>审查者核对目标、每个实际推导操作、引文与完整性。主智能体验收分歧，无法裁清保留U，不能由字符串相同或结构通过自动认定证明成立。</p></li><li><b>执行合同门与聚合</b><p>程序校验裁决归属、批准状态与三维依赖，再按同题采样槽及任务分区聚合。哈希能发现混用与陈旧，不能证明语义裁决绝对正确。</p></li></ol><p>判例：先将15时误当满足16时门槛，末尾给22时正确答案，可以A通过而L失败。仅事实ID误写或连续引文失误，在语义已充分成立时可只导致C失败。</p></section>`+
  `<section class="panel"><h2>pass@1、pass@5与pass^5</h2><p>同一道题预登记n个有效首次采样槽，其中c个成功。每个维度分别计算，先逐题再宏平均。</p><div class="table-wrap"><table><thead><tr><th>指标</th><th>精确估计式</th><th>含义</th></tr></thead><tbody><tr><td>pass@1</td><td class="mono">c / n</td><td>单次成功率</td></tr><tr><td>pass@5</td><td class="mono">1 − C(n−c,5) / C(n,5)</td><td>五次至少一次成功</td></tr><tr><td>pass^5</td><td class="mono">C(c,5) / C(n,5)</td><td>五次全部成功</td></tr></tbody></table></div><p>例如n=5、c=4时，三项是0.8、1、0，最后一项不能用0.8⁵代替。n&lt;5，五次指标留空。本轮每题每模型n=1，全部五次指标为空。</p><p>有u个未决，用c与c+u分别代入公式形成标签上下界，U保留原分母，正式点值为空。此界限不是置信区间。不能将不同题或不同提示凑成五次，也不能将全库平均准确率代入五次公式。</p></section>`+
  `<section class="panel"><h2>源码、详细协议与复算</h2><div class="latest-links"><a href="#/docs/evaluation/scoring-guide">详细评测指标及过程评分说明</a><a href="#/docs/model-testing/luna-sol-latest">Luna/Sol完整说明</a><a href="${siteURL('files/evaluation/pass_metrics_v15/scorer.py')}">冻结评分器源码</a><a href="${siteURL('files/evaluation/pass_metrics_v15/test_scorer.py')}">评分器测试</a><a href="${siteURL('files/src/luna_sol_v16/analyze_delivery.py')}">v16证据绑定与汇总实现</a></div><p>下载源码可查看实现或运行独立算术测试。完整证据门禁复算依赖原有完整审计快照，网页JSON不能代替全部进程和采样资格证据。采样结论仍依赖已声明的稳定provider及条件IID假设。</p></section>`;
}
export async function renderLatest(page,key,params){
  if(page==='scoring')return {title:'评分器与过程评价',html:scoringPage()};
  const [qs,rs]=await Promise.all([get('questions.public'),get('results')]);
  const cases=qs.cases,records=rs.records;
  if(key)return {title:key,html:await detail(page,key,cases,records)};
  const matched=filterCases(cases,params),qmap=new Map(cases.map(q=>[q.question_key,q]));
  const downloadLinks=`<p class="latest-links">${download('inputs.jsonl','252项清洁输入')}${download('questions.public.json','任务与审阅元数据索引')}${download('results.json','504份原答及裁决')}${download('results.csv','逐槽评分CSV')}${download('manifest.json','来源与哈希清单')}<a href="#/scoring">评分规则与实现</a></p>`;
  if(page==='latest'){
    const pg=pager(page,params,matched.length);
    return {title:'最新开发题库',html:heading('05 / LATEST TASKS','最新开发题库','252项任务：现有142主任务、48节点诊断、12状态对照，及50条开发扩展。材料均为合成闭世界，历史两版题库仍保留原入口。')+policy()+downloadLinks+filters(page,params,cases)+`<p class="result-count" id="latest-count">匹配 <b>${matched.length}</b> / ${cases.length} 项任务</p><section class="latest-task-list">${matched.slice(pg.start,pg.start+12).map(q=>`<article class="panel latest-task"><div class="task-meta">${taskFacts(q)}</div><h2><a href="${link('latest',q.question_key)}">${esc(q.case_id)}</a></h2><p>${esc(q.input.question)}</p><p class="caption">${q.input.contexts.length}段材料，${esc(hopStatus[q.metadata?.hop_claim_status]||'局部资格范围见详情')}</p><div class="latest-links"><a href="${link('latest',q.question_key)}">问题与全部材料</a><a href="${link('results',q.question_key)}">两模型原答与裁决</a></div></article>`).join('')||'<p>没有匹配任务。请调整筛选。</p>'}</section>`+pg.html};
  }
  const selected=new Set(matched.map(q=>q.question_key));
  const shown=records.filter(r=>selected.has(r.question_key)&&(!params.get('model')||r.model===params.get('model'))&&Object.keys(dimensions).every(d=>!params.get(d)||r.labels[d]===params.get(d)));
  const pg=pager(page,params,shown.length);
  return {title:'Luna / Sol逐题实测',html:'<p class="latest-links"><a href="#/results">返回最新嵌套／换名Luna实测</a><a href="#/overview?cohort=v18">本批全部题目</a></p>'+heading('05 / HISTORICAL LUNA & SOL','Luna / Sol逐题实测','504份真实首次作答，技术失败0。两模型每题公共输入一致，无工具、无重采和格式修复。20份非法JSON原样保留。')+policy()+downloadLinks+`<details class="panel" open><summary>按阶段与任务分区查看汇总</summary>${summaryTable(records,cases)}<p class="caption">此汇总固定展示全量分层口径，不随下方逐槽筛选变化。有U时，正式点值留空。</p></details>`+filters(page,params,cases)+`<p class="result-count" id="latest-count">匹配 <b>${shown.length}</b> / ${records.length} 份原答</p><section class="latest-task-list">${shown.slice(pg.start,pg.start+12).map(r=>{const q=qmap.get(r.question_key);return `<article class="panel latest-task"><div class="task-meta">${taskFacts(q)}</div><h2><a href="${link('results',r.question_key)}">${esc(r.case_id)}</a></h2><p>${esc(q.input.question)}</p>${observation(r,true)}<a href="${link('results',r.question_key)}">查看两模型完整原答、材料及哈希</a></article>`;}).join('')||'<p>没有匹配原答。请调整筛选。</p>'}</section>`+pg.html};
}
export async function downloadLatestInput(key){
  const q=(await get('questions.public')).cases.find(q=>q.question_key===key);if(!q)return;
  const url=URL.createObjectURL(new Blob([json(q.input)+'\n'],{type:'application/json;charset=utf-8'}));
  const a=document.createElement('a');a.href=url;a.download=q.case_id+'.public.json';a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);
}
document.addEventListener('submit',e=>{
  const form=e.target.closest('[data-latest-form]');if(!form)return;e.preventDefault();
  const params=new URLSearchParams();for(const [k,v] of new FormData(form))if(String(v).trim())params.set(k,String(v).trim());
  location.hash=link(form.dataset.latestForm,'',params);
});
document.addEventListener('click',e=>{
  const el=e.target.closest('[data-latest-download]');if(el)downloadLatestInput(el.dataset.latestDownload);
  const jump=e.target.closest('[data-latest-jump]');if(jump){const target=document.getElementById(jump.dataset.latestJump);target?.focus({preventScroll:true});target?.scrollIntoView({block:'start'});}
});
