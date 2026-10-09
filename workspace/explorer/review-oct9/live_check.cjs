// Read-only production verification; [review specification](../../../explorer/specs/08_临时人工审查.md).
const {chromium}=require('playwright');
const fs=require('node:fs');
const path=require('node:path');
const assert=require('node:assert/strict');
const base='https://dinghouqin.github.io/bridgeqa-zh/';
(async()=>{
  const browser=await chromium.launch({headless:true});
  const errors=[],writes=[],checks=[];
  try{
    const desktop=await browser.newPage({viewport:{width:1440,height:1050}});
    const mobile=await browser.newPage({viewport:{width:390,height:844}});
    for(const page of [desktop,mobile]){
      page.on('pageerror',e=>errors.push(e.message));
      page.on('request',r=>{if(!['GET','OPTIONS'].includes(r.method()))writes.push(r.method()+' '+r.url());});
      await page.goto(base+'#/review');await page.waitForSelector('.review-person-card');
      await page.waitForFunction(()=>document.querySelector('#review-toolbar')?.innerText.includes('已同步'),{},{timeout:45000});
      assert.equal(await page.locator('.review-person-card').count(),2);
      for(const progress of await page.locator('.review-progress-text').allTextContents())assert.match(progress,/\/ 43 题/);
      assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1));
    }
    assert.deepEqual(await desktop.locator('.review-progress-text').allTextContents(),await mobile.locator('.review-progress-text').allTextContents());
    checks.push('two browsers connect to shared storage and display A/B 43/43');
    for(const person of ['A','B']){
      await desktop.goto(base+'#/review');await desktop.waitForSelector('.review-person-card');
      await desktop.locator('.review-person-card[data-person='+person+'] .primary').click();
      await desktop.waitForSelector('#result-count');assert.equal(await desktop.locator('#result-count b').innerText(),'43');
    }
    checks.push('both assigned catalogs contain exactly 43 questions');
    for(const page of [desktop,mobile]){
      await page.goto(base+'#/review-question/Q1e7d33f27419');await page.waitForSelector('.review-form');
      assert.equal(await page.locator('.review-rating-guide li').count(),25);
      assert.equal(await page.locator('#review-feedback').count(),1);
      assert.equal(await page.locator('[data-act=review-complete]').count(),1);
      assert.equal(await page.locator('[data-act=review-draft]').count(),1);
      assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1));
    }
    checks.push('rating anchors and action feedback render on desktop and 390px mobile');
    for(const slug of ['evaluation/index','model-testing/index']){
      await desktop.goto(base+'#/docs/'+slug);await desktop.waitForSelector('.markdown-body');
      assert.match(await desktop.locator('.markdown-body').innerText(),/怎样算完成/);
    }
    checks.push('both role READMEs render as online documents');
    const build=await (await desktop.request.get(base+'build.json')).json();
    assert.equal(build.revision,process.env.BRIDGEQA_EXPECT_REVISION);
    assert.deepEqual(errors,[]);assert.deepEqual(writes,[]);
    const result={status:'passed',url:base+'#/review',revision:build.revision,checks,unexpected_browser_errors:errors,writes:'none'};
    fs.writeFileSync(path.join(__dirname,'live_checks.json'),JSON.stringify(result,null,2)+'\n');console.log(JSON.stringify(result,null,2));
  }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
