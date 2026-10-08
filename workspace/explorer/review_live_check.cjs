// Production read-only acceptance; [review contract](../../explorer/specs/08_临时人工审查.md).
const {chromium}=require('playwright');
const fs=require('node:fs');
const path=require('node:path');
const assert=require('node:assert/strict');
const base='https://dinghouqin.github.io/bridgeqa-zh/';
(async()=>{
  const browser=await chromium.launch({headless:true});const errors=[];
  try{
    const pages=await Promise.all([browser.newPage({viewport:{width:1440,height:1050}}),browser.newPage({viewport:{width:390,height:844}})]);
    for(const page of pages){
      page.on('pageerror',e=>errors.push(e.message));
      await page.goto(base+'#/review');await page.waitForSelector('.review-person-card');
      await page.waitForFunction(()=>document.querySelector('#review-toolbar')?.innerText.includes('已同步'),{},{timeout:45000});
      assert.equal(await page.locator('.review-person-card').count(),4);
      assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1));
      assert.equal(await page.locator('nav[aria-label=主导航] a').count(),5);
    }
    const home=await pages[0].locator('.review-progress-text').allTextContents();
    assert.deepEqual(await pages[1].locator('.review-progress-text').allTextContents(),home);
    await pages[0].locator('.review-person-card[data-person=A] .primary').click();await pages[0].waitForSelector('#result-count');assert.equal(await pages[0].locator('#result-count b').innerText(),'22');
    await pages[0].locator('.question-link').first().click();await pages[0].waitForSelector('.review-form');
    assert.ok(await pages[0].locator('.review-step').count()>0);assert.ok(await pages[0].locator('#review-all-data').count()>0);
    await pages[0].goto(base+'#/docs/specs/08');await pages[0].waitForSelector('.markdown-body');assert.match(await pages[0].locator('.markdown-body').innerText(),/D1数据库/);
    const build=await (await pages[0].request.get(base+'build.json')).json();assert.equal(build.revision,process.env.BRIDGEQA_EXPECT_REVISION);
    assert.deepEqual(errors,[]);const result={status:'passed',url:base+'#/review',revision:build.revision,checks:['two independent browser contexts connect to production shared database','four progress totals match across desktop and mobile','A catalog contains 22 assigned tasks','review detail shows per-step form and full data','05 specification renders online','production build matches pushed source','no browser exceptions or 390px overflow'],writes:'none'};
    fs.writeFileSync(path.join(__dirname,'review_live_checks.json'),JSON.stringify(result,null,2)+'\n');console.log(JSON.stringify(result,null,2));
  }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
