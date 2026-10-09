// [Review verification](../specs/08_临时人工审查.md). No production records are written.
const {chromium}=require('playwright');
const {DatabaseSync}=require('node:sqlite');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const {pathToFileURL}=require('node:url');
const root=path.resolve(__dirname,'../..'),out=path.resolve(root,process.env.BRIDGEQA_CHECK_DIR||'workspace/explorer');
fs.mkdirSync(out,{recursive:true});
const base=process.env.BRIDGEQA_URL||'http://127.0.0.1:8766';
const db=new DatabaseSync(':memory:');
db.exec('CREATE TABLE review_entries (round TEXT NOT NULL,kind TEXT NOT NULL,id TEXT NOT NULL,value TEXT NOT NULL,revision INTEGER NOT NULL,updated_at TEXT NOT NULL,PRIMARY KEY(round,kind,id))');
const DB={prepare(sql){return {bind(...args){const stmt=db.prepare(sql);return {async first(){return stmt.get(...args)||null;},async all(){return {results:stmt.all(...args)};},async run(){const result=stmt.run(...args);return {meta:{changes:Number(result.changes)}};}};}};}};
const checks=[],errors=[];
(async()=>{
  const worker=(await import(pathToFileURL(path.join(root,'explorer/review-service/worker.js')).href)).default;
  const {ROUND,PLAN}=await import(pathToFileURL(path.join(root,'explorer/review-service/plan.js')).href);
  const model=await import(pathToFileURL(path.join(root,'explorer/web/review-model.js')).href);
  const rows=fs.readFileSync(path.join(root,'data/pilot_literature_history_v0/benchmark.jsonl'),'utf8').trim().split(/\r?\n/).map(JSON.parse);
  const browser=await chromium.launch({headless:true,downloadsPath:path.join(out,'review-downloads')});
  let failSave=false;
  const mock=async route=>{
    const r=route.request();
    if(failSave&&r.method()==='PUT'&&r.url().includes('/records/')){failSave=false;return route.fulfill({status:503,headers:{'Content-Type':'application/json','Access-Control-Allow-Origin':base},body:JSON.stringify({error:'模拟存储故障'})});}
    const response=await worker.fetch(new Request(r.url(),{method:r.method(),headers:r.headers(),...(r.postData()?{body:r.postData()}: {})}),{DB});
    await route.fulfill({status:response.status,headers:Object.fromEntries(response.headers),body:await response.text()});
  };
  const c1=await browser.newContext({viewport:{width:1440,height:1050}}),c2=await browser.newContext({viewport:{width:1440,height:1050}});
  const staticFiles=async route=>{
    const relative=decodeURIComponent(new URL(route.request().url()).pathname).replace(/^\//,'')||'index.html';
    const filename=path.resolve(root,'workspace/pages',relative);
    if(!filename.startsWith(path.join(root,'workspace/pages')+path.sep)||!fs.existsSync(filename))return route.fulfill({status:404,body:'Not found'});
    const types={'.html':'text/html','.js':'text/javascript','.json':'application/json','.css':'text/css','.md':'text/plain'};
    return route.fulfill({status:200,contentType:types[path.extname(filename)]||'application/octet-stream',body:fs.readFileSync(filename)});
  };
  for(const context of [c1,c2])await context.route(base+'/**',staticFiles);
  await c1.route('https://bridgeqa-human-review.spryox2.chatgpt.site/api/review**',mock);
  await c2.route('https://bridgeqa-human-review.spryox2.chatgpt.site/api/review**',mock);
  const p1=await c1.newPage(),p2=await c2.newPage();
  for(const p of [p1,p2])p.on('pageerror',e=>errors.push(e.message));
  const check=async(name,fn)=>{await fn();checks.push(name);console.log('PASS '+name);};
  const home=async p=>{await p.goto(base+'/#/review');await p.waitForSelector('.review-person-card');await p.waitForFunction(()=>document.querySelector('#review-toolbar')?.innerText.includes('已同步'));};
  const detail=async(p,row)=>{await p.goto(base+'/#/review-question/'+row.id);await p.waitForSelector('.review-form');};
  const unitSelect=p=>p.locator('select[data-review-field=accuracy]');
  const saveMember=async(p,person,name)=>{await p.locator('#initials-'+person).fill(name);await p.locator('[data-act=review-name][data-person='+person+']').click();await p.waitForFunction(({person,name})=>document.querySelector('#initials-'+person)?.value===name&&document.querySelector('#review-toolbar')?.innerText.includes('已同步'),{person,name});};
  try{
    await check('server rejects wrong version, unknown IDs, malformed evaluations and missing storage',async()=>{
      const request=(suffix,body,round=ROUND)=>new Request('https://service.test/api/review'+suffix+'?round='+encodeURIComponent(round),{method:'PUT',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
      assert.equal((await worker.fetch(request('/members/A',{expectedRevision:0,value:{initials:'abc'}},'old'),{DB})).status,409);
      assert.equal((await worker.fetch(request('/records/not-a-task',{expectedRevision:0,value:{}}),{DB})).status,400);
      assert.equal((await worker.fetch(request('/members/A',{expectedRevision:0,value:{initials:'<x>'}}),{DB})).status,400);
      assert.equal((await worker.fetch(new Request('https://service.test/api/review?round='+encodeURIComponent(ROUND)),{})).status,503);
    });
    await check('server conditional writes reject a concurrent update without changing original',async()=>{
      const row=rows[0],value=model.blankReview(row,PLAN[row.id].owner);
      const requests=['one','two'].map(comment=>new Request('https://service.test/api/review/records/'+row.id+'?round='+encodeURIComponent(ROUND),{method:'PUT',body:JSON.stringify({expectedRevision:0,value:{...value,comment}})}));
      const results=await Promise.all(requests.map(r=>worker.fetch(r,{DB})));assert.deepEqual(results.map(r=>r.status).sort(),[200,409]);
      db.prepare('DELETE FROM review_entries').run();
    });
    await check('four-person records retain comments, status, signatures and revisions under two-person allocation',async()=>{
      const sorted=[...rows].sort((a,b)=>a.family_id.localeCompare(b.family_id,'en')||a.id.localeCompare(b.id,'en'));
      const insert=db.prepare('INSERT INTO review_entries VALUES (?,?,?,?,?,?)');
      for(let i=0;i<4;i++){
        const value=model.blankReview(sorted[i],['A','B','C','D'][i]);value.initials='old';value.comment='旧评价'+i;
        for(const step of Object.values(value.steps))step.accuracy='correct';value.verdict='accept';value.status=i%2?'draft':'complete';
        insert.run(ROUND,'records',sorted[i].id,JSON.stringify(value),7,'2026-10-08');
      }
      insert.run(ROUND,'members','C',JSON.stringify({initials:'oldname'}),2,'2026-10-08');
      const get=()=>worker.fetch(new Request('https://service.test/api/review?round='+encodeURIComponent(ROUND)),{DB}).then(r=>r.json());
      let data=await get();assert.equal(data.members.A.value.initials,'oldname');
      for(let i=0;i<4;i++){const r=data.records[sorted[i].id];assert.equal(r.value.owner,i%2?'B':'A');assert.equal(r.value.comment,'旧评价'+i);assert.equal(r.value.initials,'old');assert.equal(r.revision,7);assert.equal(r.value.status,i%2?'draft':'complete');}
      const put=await worker.fetch(new Request('https://service.test/api/review/members/A?round='+encodeURIComponent(ROUND),{method:'PUT',body:JSON.stringify({expectedRevision:0,value:{initials:'newname'}})}),{DB});assert.equal(put.status,200);
      data=await get();assert.equal(data.members.A.value.initials,'newname');assert.equal(db.prepare("SELECT value FROM review_entries WHERE kind='members' AND id='C'").get().value,JSON.stringify({initials:'oldname'}));
      const old=data.records[sorted[2].id];const save=await worker.fetch(new Request('https://service.test/api/review/records/'+sorted[2].id+'?round='+encodeURIComponent(ROUND),{method:'PUT',body:JSON.stringify({expectedRevision:7,value:old.value})}),{DB});assert.equal(save.status,200);
      db.prepare('DELETE FROM review_entries').run();
    });
    await check('05 homepage shows complete 43/43 assignment and initials sync across browsers',async()=>{
      await home(p1);await home(p2);assert.deepEqual(await p1.locator('.review-progress-text').allTextContents(),['0 / 43 题 · 0%','0 / 43 题 · 0%']);
      await saveMember(p1,'B','abc');await p2.waitForFunction(()=>document.querySelector('#initials-B')?.value==='abc');
      await p1.screenshot({path:path.join(out,'12-review-home-desktop.png'),fullPage:true});
    });
    const row=rows.find(r=>PLAN[r.id].owner==='A'&&r.gold.proofs.length===1);
    await check('review catalog scopes assignments, searches and returns with filters',async()=>{
      await p1.locator('.review-person-card[data-person=A] .primary').click();await p1.waitForSelector('#result-count');assert.equal(await p1.locator('#result-count b').innerText(),'43');
      await p1.locator('#search').fill(row.id);await p1.waitForFunction(()=>document.querySelector('#result-count b')?.innerText==='1');
      await p1.locator('.question-link').click();await p1.waitForSelector('.review-form');
      await p1.getByRole('link',{name:'← 返回筛选结果',exact:true}).click();await p1.waitForSelector('#result-count');assert.equal(await p1.locator('#result-count b').innerText(),'1');
    });
    await check('all materials and facts visible, reference support highlighted, proof graph still interactive',async()=>{
      await detail(p1,row);assert.equal(await p1.locator('.review-document').count(),row.input.documents.length);assert.equal(await p1.locator('.review-fact').count(),row.facts.length);
      assert.ok(await p1.locator('.review-fact.current').count()>0);assert.equal(await unitSelect(p1).count(),model.units(row).length);
      await p1.locator('.proof-connection').last().click();assert.match(await p1.locator('.node-analysis h3').innerText(),/选中跳跃/);
      await p1.screenshot({path:path.join(out,'13-review-detail-desktop.png'),fullPage:true});
    });
    await check('incomplete review cannot finish, comments theme works, drafts survive reload',async()=>{
      await p1.locator('[data-act=review-complete]').click();assert.match(await p1.locator('#review-feedback').innerText(),/尚未评价|请选择/);await p1.waitForTimeout(5200);assert.match(await p1.locator('#review-feedback').innerText(),/尚未评价|请选择/);
      await unitSelect(p1).first().selectOption('incorrect');await p1.locator('[data-act=review-complete]').click();
      await p1.waitForTimeout(900);assert.match(await p1.locator('#review-feedback').innerText(),/需要填写原因/);
      await p1.locator('.review-topic-buttons button').first().click();
      assert.match(await p1.locator('textarea[data-review-field=step-comment]').first().inputValue(),/问题的可读性/);
      await p1.locator('textarea[data-review-field=step-comment]').first().fill('需核对该跳的证据');await p1.locator('[data-act=review-draft]').click();await p1.waitForFunction(()=>document.querySelector('#review-feedback')?.innerText.includes('草稿已保存'));
      await p1.waitForFunction(()=>document.querySelector('#review-toolbar')?.innerText.includes('已保存'));
      await p1.reload();await p1.waitForFunction(()=>document.querySelector('textarea[data-review-field=step-comment]')?.value==='需核对该跳的证据');
    });
    await check('shared completed count updates and a changed completed record returns to draft',async()=>{
      for(const select of await unitSelect(p1).all())await select.selectOption('correct');await p1.locator('select[data-review-field=verdict]').selectOption('accept');
      assert.equal(await p1.locator('.review-form .badge').innerText().then(t=>t.includes('未署名')),true);
      assert.equal(await p1.locator('.review-rating-guide li').count(),25);
      await p1.locator('[data-act=review-complete]').click();await p1.waitForFunction(()=>document.querySelector('.review-form .badge')?.innerText.includes('已完成'));
      await p1.waitForFunction(()=>document.querySelector('#review-feedback')?.innerText.includes('审查已完成'));await p1.waitForTimeout(5200);assert.match(await p1.locator('#review-feedback').innerText(),/审查已完成/);
      await p1.reload();await p1.waitForFunction(()=>document.querySelector('.review-form .badge')?.innerText.includes('已完成'));
      await p2.waitForFunction(()=>document.querySelector('.review-person-card[data-person=A] .review-progress-text')?.innerText.includes('1 / 43'));
      await p1.locator('[data-act=review-draft]').click();await p1.waitForFunction(()=>document.querySelector('#review-feedback')?.innerText.includes('草稿已保存'));await p1.reload();await p1.waitForFunction(()=>document.querySelector('.review-form .badge')?.innerText.includes('草稿'));
      await p2.waitForFunction(()=>document.querySelector('.review-person-card[data-person=A] .review-progress-text')?.innerText.includes('0 / 43'));
    });
    await check('storage failure preserves input and explicit retry completes shared save',async()=>{
      failSave=true;await p1.locator('textarea[data-review-field=comment]').fill('保存故障仍保留此意见');
      await p1.waitForFunction(()=>document.querySelector('#review-toolbar')?.innerText.includes('保存失败'));
      assert.equal(await p1.locator('textarea[data-review-field=comment]').inputValue(),'保存故障仍保留此意见');assert.match(await p1.locator('#review-feedback').innerText(),/保存失败/);await p1.locator('#review-feedback [data-act=review-retry]').click();
      await p1.waitForFunction(()=>document.querySelector('#review-toolbar')?.innerText.includes('已同步'));
    });
    await check('failed complete and draft actions show local errors, retry persists intended status',async()=>{
      failSave=true;await p1.locator('[data-act=review-complete]').click();
      await p1.waitForFunction(()=>document.querySelector('#review-feedback')?.innerText.includes('保存失败'));
      assert.match(await p1.locator('.review-form .badge').innerText(),/草稿/);
      await p1.locator('#review-feedback [data-act=review-retry]').click();
      await p1.waitForFunction(()=>document.querySelector('.review-form .badge')?.innerText.includes('已完成'));
      failSave=true;await p1.locator('[data-act=review-draft]').click();
      await p1.waitForFunction(()=>document.querySelector('#review-feedback')?.innerText.includes('保存失败'));
      await p1.locator('#review-feedback [data-act=review-retry]').click();
      await p1.waitForFunction(()=>document.querySelector('#review-feedback')?.innerText.includes('草稿已保存'));
      await p1.reload();await p1.waitForFunction(()=>document.querySelector('.review-form .badge')?.innerText.includes('草稿'));
    });
    await check('multi-proof tasks require every branch; insufficient tasks have only boundary review',async()=>{
      const multiple=rows.find(r=>r.gold.proofs.length>1);await detail(p1,multiple);assert.equal(await unitSelect(p1).count(),model.units(multiple).length);
      const first=await p1.locator('.review-fact.current .fact-line .mono').allTextContents();await p1.locator('#proof-choice').selectOption('1');const second=await p1.locator('.review-fact.current .fact-line .mono').allTextContents();assert.notDeepEqual(first,second);
      const noProof=rows.find(r=>!r.gold.proofs.length);await detail(p1,noProof);assert.equal(await unitSelect(p1).count(),1);assert.equal(await p1.locator('.review-fact.current').count(),0);assert.match(await p1.locator('.review-step h3').innerText(),/不可作答/);
    });
    await check('same-task conflict keeps local input and permits choosing remote version',async()=>{
      await detail(p1,row);await detail(p2,row);await p1.waitForTimeout(400);await p2.waitForTimeout(400);
      await p1.locator('textarea[data-review-field=comment]').fill('设备一的版本');await p2.locator('textarea[data-review-field=comment]').fill('设备二的版本');
      await Promise.race([p1.waitForSelector('.review-conflict'),p2.waitForSelector('.review-conflict')]);
      const loser=await p1.locator('.review-conflict').count()?p1:p2;await loser.locator('#review-feedback [data-act=review-remote]').click();await loser.waitForFunction(()=>!document.querySelector('.review-conflict'));
    });
    await check('export yields structured shared records; 02 remains separate from 05',async()=>{
      const download=await Promise.all([p1.waitForEvent('download'),p1.locator('[data-act=review-export]').click()]);const file=await download[0].path();const result=JSON.parse(fs.readFileSync(file,'utf8'));
      assert.equal(result.format,'bridgeqa-human-review-v1');assert.equal(Object.keys(result.assignments).length,86);assert.equal(result.round,ROUND);
      await p1.getByRole('link',{name:'02题目与证据'}).click();await p1.waitForSelector('#result-count');assert.equal(await p1.locator('.review-form').count(),0);assert.equal(await p1.locator('#review-toolbar').count(),0);
    });
    await check('390px review home and detail have no page overflow',async()=>{
      await p1.setViewportSize({width:390,height:844});await home(p1);assert.ok(await p1.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1));await p1.screenshot({path:path.join(out,'14-review-home-mobile.png'),fullPage:true});
      await detail(p1,row);assert.ok(await p1.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1));await p1.screenshot({path:path.join(out,'15-review-detail-mobile.png'),fullPage:true});
    });
    assert.deepEqual(errors,[]);fs.writeFileSync(path.join(out,'review_checks.json'),JSON.stringify({status:'passed',checks,unexpected_browser_errors:errors,storage:'In-memory SQLite through actual Worker API; no production writes'},null,2)+'\n');
    console.log('ALL '+checks.length+' review checks passed');
  }catch(e){await p1.screenshot({path:path.join(out,'review-failure.png'),fullPage:true});fs.writeFileSync(path.join(out,'review_checks.json'),JSON.stringify({status:'failed',checks,error:String(e),errors},null,2));throw e;}
  finally{await browser.close();db.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
