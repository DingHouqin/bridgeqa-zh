// Browser acceptance for [the latest publication](../specs/10_最新题库与模型评测发布.md).
const {chromium}=require('playwright');
const fs=require('node:fs');const path=require('node:path');const assert=require('node:assert/strict');
const root=path.resolve(__dirname,'../..');
const source=process.env.BRIDGEQA_ASSET_DIR||path.join(root,'workspace/github-publication-v18/pages');
const out=path.join(root,'workspace/github-publication-v18/ui');fs.mkdirSync(out,{recursive:true});
const base=process.env.BRIDGEQA_URL||'https://publication.test/bridgeqa-zh/';
const online=process.env.BRIDGEQA_LIVE==='1';
const qs=JSON.parse(fs.readFileSync(path.join(root,'explorer/publication_v18/questions.public.json'),'utf8')).cases;
const rs=JSON.parse(fs.readFileSync(path.join(root,'explorer/publication_v18/results.json'),'utf8')).records;
const types={'.html':'text/html','.js':'text/javascript','.css':'text/css','.json':'application/json','.jsonl':'application/x-ndjson','.md':'text/plain','.py':'text/plain','.csv':'text/csv'};
async function mock(page,overrides={}){
 if(online)return;
 await page.route('**/*',async route=>{
  const url=new URL(route.request().url());
  if(!url.href.startsWith(base))return route.abort();
  const rel=decodeURIComponent(url.pathname.slice(new URL(base).pathname.length))||'index.html';
  const filename=path.resolve(source,rel);
  if(!filename.startsWith(path.resolve(source)+path.sep)||!fs.existsSync(filename))return route.fulfill({status:404,body:'Not found'});
  const body=overrides[rel]??fs.readFileSync(filename);
  await route.fulfill({status:200,contentType:types[path.extname(filename)]||'application/octet-stream',body});
 });
}
(async()=>{
 const browser=await chromium.launch({headless:true,downloadsPath:out,...(process.env.BRIDGEQA_CHROMIUM_PATH?{executablePath:process.env.BRIDGEQA_CHROMIUM_PATH}:{})});
 const page=await browser.newPage({viewport:{width:1440,height:1024}});await mock(page);
 const errors=[],failed=[],checks=[];
 page.on('pageerror',e=>errors.push(e.message));page.on('response',r=>{if(r.status()>=400)failed.push({url:r.url(),status:r.status()});});
 async function check(name,fn){await fn();checks.push(name);console.log('PASS '+name);}
 async function hash(value,title){await page.evaluate(h=>location.hash=h,value);await page.waitForFunction(t=>document.title===t+' · BridgeQA',title);}
 try{
  await check('new homepage, seven navigation entries and 252 tasks',async()=>{
   await page.goto(base);await page.waitForSelector('#latest-count');
   assert.match(await page.locator('#latest-count').textContent(),/252.*252/);
   assert.equal(await page.locator('.sidebar nav>a').count(),7);
   assert.equal(await page.locator('a[href*="references.review"],a[href*="references.private"]').count(),0);
   await page.screenshot({path:path.join(out,'01-latest-desktop.png'),fullPage:false});
  });
  await check('phase filtering returns 30 new-operator tasks',async()=>{
   await page.locator('select[name=phase]').selectOption('novel_r1');
   await page.locator('[data-latest-form] button[type=submit]').click();
   await page.waitForFunction(()=>document.querySelector('#latest-count')?.textContent.includes('30 / 252'));
  });
  await check('main, node, control and extension denominators',async()=>{
   await hash('#/results','Luna / Sol逐题实测');
   assert.equal(await page.locator('.latest-summary tbody tr').count(),12);
   const rows=await page.locator('.latest-summary tbody tr').allTextContents();
   assert.match(rows[0],/142.*85 \/ 53 \/ 4.*62 \/ 78 \/ 2.*40 \/ 91 \/ 11/);
   assert.match(rows[1],/142.*138 \/ 0 \/ 4/);
   await page.screenshot({path:path.join(out,'02-results-desktop.png'),fullPage:false});
  });
  await check('all 252 details preserve 504 complete raw answers and labels',async()=>{
   for(const q of qs){
    await hash('#/results/'+encodeURIComponent(q.question_key),q.question_key);
    const actual=await page.locator('.raw-answer pre').allTextContents();
    const expected=rs.filter(r=>r.question_key===q.question_key).sort((a,b)=>a.model.localeCompare(b.model));
    assert.equal(actual.length,2,q.question_key);
    const cards=page.locator('.model-comparison>.model-result');
    for(let i=0;i<2;i++){
     const model=await cards.nth(i).locator('h3').textContent();const r=expected.find(x=>x.model===model);
     assert.equal(actual[i],r.raw_response,q.question_key+' '+model+' raw');
     assert.deepEqual(await cards.nth(i).locator('.result-labels .verdict').allTextContents(),Object.values(r.labels).map(v=>v+' '+({P:'通过',F:'失败',U:'需复核'}[v])));
     assert((await cards.nth(i).locator('.review-rationale p').textContent()).length>0);
    }
    if(q.qualification.target_ambiguity)assert.equal(await page.locator('.reference-review .notice.warning').count(),1);
   }
  });
  const stable=qs.find(q=>q.case_id==='NEW-STABLE-challenge3');
  await check('stable-matching counterexample and raw comparison',async()=>{
   await hash('#/results/'+encodeURIComponent(stable.question_key),stable.question_key);
   assert.equal(await page.locator('.model-comparison .verdict-F').count(),6);
   await page.locator('[data-latest-jump]').click();
   assert.equal(await page.evaluate(()=>document.activeElement.id),'latest-model-comparison');
   await page.screenshot({path:path.join(out,'03-stable-detail-desktop.png'),fullPage:false});
  });
  await check('single-question download contains only exact clean input',async()=>{
   const [download]=await Promise.all([page.waitForEvent('download'),page.locator('[data-latest-download]').click()]);
   const target=path.join(out,'single-clean-input.json');await download.saveAs(target);
   assert.deepEqual(JSON.parse(fs.readFileSync(target,'utf8')),stable.input);
  });
  await check('scoring page and source links',async()=>{
   await hash('#/scoring','评分器与过程评价');
   assert.match(await page.locator('main').textContent(),/C\(c,5\).*C\(n,5\)/);
   assert.match(await page.locator('main').textContent(),/本轮每题每模型n=1/);
   const links=await page.locator('main a[href*="/files/"]').evaluateAll(els=>els.map(e=>e.href));
   for(const url of links){if(online){const response=await page.request.get(url);assert(response.ok(),url);}else {const rel=decodeURIComponent(new URL(url).pathname.slice(new URL(base).pathname.length));assert(fs.existsSync(path.join(source,rel)),url);}}
   await page.screenshot({path:path.join(out,'04-scoring-desktop.png'),fullPage:false});
  });
  await check('both historical dataset views still work',async()=>{
   for(const [id,n] of [['pilot_literature_history_v0',86],['multi_agent_hongloumeng_v2',57]]){
    await hash('#/questions?dataset='+id,'题目与证据');
    await page.waitForFunction(n=>document.querySelector('#result-count b')?.textContent===String(n),n);
   }
  });
  await check('new documentation routes resolve',async()=>{
   for(const [slug,title] of [['evaluation/scoring-guide','评分器与过程评价详解'],['model-testing/luna-sol-latest','Luna／Sol逐题表现与边界'],['data/latest-publication','最新252任务与504份首答公开投影']]){
    await hash('#/docs/'+slug,title);assert(await page.locator('.markdown-body').textContent());
   }
  });
  await check('mobile layout has no viewport overflow',async()=>{
   await page.setViewportSize({width:390,height:844});
   for(const [url,title] of [['#/latest','最新开发题库'],['#/results','Luna / Sol逐题实测'],['#/scoring','评分器与过程评价']]){
    await hash(url,title);
    assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1),url);
    await page.screenshot({path:path.join(out,'mobile-'+title.replace(/[^a-z0-9]/gi,'_')+'.png'),fullPage:false});
   }
  });
  if(!online)await check('model and question markup is escaped as text',async()=>{
   const injected=structuredClone(JSON.parse(fs.readFileSync(path.join(root,'explorer/publication_v18/questions.public.json'),'utf8')));
   const injectedR=structuredClone(JSON.parse(fs.readFileSync(path.join(root,'explorer/publication_v18/results.json'),'utf8')));
   injected.cases[0].input.question='<img src=x onerror="window.PWNED=1">';
   injectedR.records.filter(r=>r.question_key===injected.cases[0].question_key)[0].raw_response='<svg onload="window.PWNED=2"></svg>';
   const other=await browser.newPage();await mock(other,{'files/explorer/publication_v18/questions.public.json':JSON.stringify(injected),'files/explorer/publication_v18/results.json':JSON.stringify(injectedR)});
   await other.goto(base+'#/results/'+encodeURIComponent(injected.cases[0].question_key));await other.waitForSelector('.raw-answer');
   assert.equal(await other.evaluate(()=>window.PWNED),undefined);assert.equal(await other.locator('.latest-question img,.raw-answer svg').count(),0);await other.close();
  });
  assert.deepEqual(errors,[]);assert.deepEqual(failed,[]);
  fs.writeFileSync(path.join(out,online?'live-acceptance.json':'acceptance.json'),JSON.stringify({checks,questions:qs.length,responses:rs.length,pageErrors:errors,failedResponses:failed,base,live:online},null,2));
 }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
