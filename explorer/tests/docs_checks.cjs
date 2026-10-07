// [Online documentation acceptance](../specs/06_静态发布与文档.md).
const {chromium}=require('playwright');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const base=(process.env.BRIDGEQA_URL||'http://127.0.0.1:8766/pages').replace(/\/$/,'');
const out=path.resolve(__dirname,'../../workspace/explorer');
(async()=>{
  const browser=await chromium.launch({headless:true});
  const page=await browser.newPage({viewport:{width:1440,height:1000}});
  const errors=[],bundles=[],checks=[];
  page.on('pageerror',e=>errors.push(e.message));
  page.on('request',r=>{if(r.url().includes('/bundle'))bundles.push(r.url());});
  const catalog=await (await page.request.get(base+'/documents.json')).json();
  const open=async slug=>{
    await page.goto(base+'/#/docs/'+slug+'?dataset=not_registered');
    const expected=catalog.documents.find(d=>d.slug===slug).title;
    await page.waitForFunction(title=>document.title===title+' · BridgeQA',expected);
    await page.waitForSelector('.markdown-body');
  };
  try{
    await open('benchmark-survey/07-scenes');
    assert.ok(await page.locator('.markdown-body table').count());
    assert.equal(await page.locator('#dataset').count(),0);
    assert.equal(await page.locator('.sidebar nav a[aria-current=page]').count(),1);
    assert.deepEqual(bundles,[]);
    await page.reload();await page.waitForSelector('.markdown-body');
    await page.locator('.docs-toc a').first().click();
    await page.waitForFunction(()=>location.hash.includes('section='));
    await page.goBack();await page.waitForSelector('.markdown-body');
    checks.push('nested hash, unknown dataset independence, reload, anchors and history');
    await page.screenshot({path:path.join(out,'09-docs-desktop.png')});
    const fileLinks=new Set();
    for(const d of catalog.documents){
      await open(d.slug);
      assert.ok((await page.locator('.markdown-body').innerText()).length>20,d.slug);
      for(const href of await page.locator('.docs-content a').evaluateAll(as=>as.map(a=>a.href))){
        if(href.startsWith(base+'/files/'))fileLinks.add(href);
      }
      assert.equal(await page.locator('.markdown-body script').count(),0);
    }
    for(const href of fileLinks)assert.equal((await page.request.get(href)).status(),200,href);
    checks.push('all '+catalog.documents.length+' chapters render; '+fileLinks.size+' local file links resolve');
    await open('index');
    await page.locator('.markdown-body a[href="#/docs/data/pilot"]').first().click();
    await page.waitForFunction(()=>location.hash.startsWith('#/docs/data/pilot'));
    await page.waitForFunction(()=>document.querySelector('.markdown-body h1')?.textContent.includes('首轮候选集'));
    assert.match(await page.locator('.markdown-body h1').innerText(),/首轮候选集/);
    await page.goto(base+'/#/docs/absent');await page.getByRole('heading',{name:'章节未找到'}).waitFor();
    await page.getByRole('link',{name:'返回文档首页'}).click();await page.waitForSelector('.markdown-body');
    checks.push('source-relative Markdown links and missing chapter recovery');
    await page.setViewportSize({width:390,height:844});
    await open('benchmark-survey/07-scenes');
    assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1));
    await page.screenshot({path:path.join(out,'10-docs-mobile.png')});
    await page.goto(base+'/#/guide');await page.waitForSelector('#testing-guide');
    assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1));
    assert.deepEqual(bundles,[]);
    assert.deepEqual(errors,[]);
    checks.push('mobile documentation/guide and no bundle requests or browser errors');
    fs.writeFileSync(path.join(out,'docs_checks.json'),JSON.stringify({status:'passed',base,checks,chapters:catalog.documents.length,file_links:fileLinks.size,errors,report_link:'[检查说明](README.md)'},null,2)+'\n');
    console.log('PASS '+checks.join('\nPASS '));
  }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
