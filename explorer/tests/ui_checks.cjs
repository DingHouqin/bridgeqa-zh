// [Browser acceptance](../specs/05_验收与测试.md). Uses an existing local Playwright runtime.
const {chromium}=require('playwright');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const root=path.resolve(__dirname,'../..');
const out=path.join(root,'workspace/explorer');
const base=process.env.BRIDGEQA_URL||'http://127.0.0.1:8765';
const rows=fs.readFileSync(path.join(root,'data/pilot_literature_history_v0/benchmark.jsonl'),'utf8').trim().split(/\r?\n/).map(JSON.parse);
const find=(c,v='challenge',d='history')=>rows.find(r=>r.combination_id===c&&r.variant===v&&r.domain===d);
(async()=>{
  const browser=await chromium.launch({headless:true});
  const page=await browser.newPage({viewport:{width:1440,height:1050},deviceScaleFactor:1});
  const errors=[],checks=[],failedRequests=[];
  page.on('pageerror',e=>errors.push(e.message));
  page.on('console',m=>{if(m.type()==='error')errors.push(m.text());});
  page.on('response',r=>{if(r.status()>=400)failedRequests.push({url:r.url(),status:r.status()});});
  fs.mkdirSync(out,{recursive:true});
  const check=async(name,fn)=>{await fn();checks.push(name);console.log('PASS '+name);};
  const overview=async()=>{await page.goto(base+'/#overview?dataset=pilot_literature_history_v0');await page.waitForSelector('.hero');};
  const catalog=async()=>{await page.goto(base+'/#questions?dataset=pilot_literature_history_v0');await page.waitForSelector('#result-count');};
  const count=async expected=>{await page.waitForFunction(n=>document.querySelector('#result-count b')?.textContent===String(n),expected);};
  const detail=async row=>{
    await page.goto(base+'/#question/'+row.id+'?dataset=pilot_literature_history_v0');
    await page.waitForFunction(id=>document.title.startsWith(id),row.id);
  };
  const screenshot=async name=>{
    await page.evaluate(()=>scrollTo(0,0));
    await page.screenshot({path:path.join(out,name),fullPage:true});
  };
  try{
    await check('overview: topic, scale, sources, combinations and diagram',async()=>{
      await overview();
      assert.match(await page.locator('h1').innerText(),/文学与历史/);
      assert.equal(await page.locator('.stat strong').first().innerText(),'128');
      assert.equal(await page.locator('.combination-table tbody tr').count(),10);
      assert.equal(await page.locator('.scene-cell').count(),32);
      assert.equal(await page.locator('#dataset option').count(),1);
      await screenshot('01-overview-desktop.png');
    });
    await check('catalog: all rows, search, label visibility and zero result',async()=>{
      await catalog();await count(128);
      assert.equal(await page.locator('.question-card').count(),12);
      await page.locator('.card-all-tags').first().locator('summary').click();
      assert.ok(await page.locator('.card-all-tags').first().locator('.tag').count()>=18);
      await page.locator('#search').fill('F-C08-H');await count(9);
      await page.locator('#search').fill('不存在的独立测试问题');await count(0);
      assert.ok(await page.locator('.empty-state').isVisible());
      await page.locator('.filter-heading [data-act=clear]').click();await count(128);
    });
    await check('cross-facet AND and scene ALL, reload and return preservation',async()=>{
      await page.locator('.facet-value[data-key=scene][data-value=S01]').click();
      await page.locator('.facet-value[data-key=scene][data-value=S28]').click();
      await page.locator('#scene-mode').selectOption('all');await count(2);
      await page.reload();await count(2);
      await page.locator('.question-link').first().click();
      await page.waitForSelector('.prototype');
      assert.match(await page.locator('.proof-panel h2').innerText(),/原型/);
      assert.ok(await page.locator('.missing-support').isVisible());
      await page.getByRole('link',{name:'← 返回筛选结果',exact:true}).click();await count(2);
      await page.locator('.filter-heading [data-act=clear]').click();await count(128);
      await page.locator('.facet-value[data-key=scene][data-value=S15]').click();await count(12);
      await page.locator('.facet-value[data-key=domain][data-value=history]').click();await count(6);
      await screenshot('02-catalog-filtered.png');
    });
    await check('C01 correct chain, role diversion and evidence navigation',async()=>{
      const row=find('C01','challenge','literature');
      await detail(row);
      assert.equal(await page.locator('.proof-node').count(),3);
      assert.ok(await page.locator('.potential-fact').count()>0);
      await page.locator('.proof-node[data-node=n2]').click();
      assert.match(await page.locator('.node-analysis h3').innerText(),/n2/);
      await page.locator('.evidence-jumps button').first().click();
      assert.ok(await page.locator('.document.focused').count()>0);
      await page.locator('.source-record').first().locator('blockquote').first().scrollIntoViewIfNeeded();
      assert.ok(await page.locator('.source-record').count()>0);
      await screenshot('03-chain-detail.png');
    });
    await check('C04 alternative proofs and material role switching',async()=>{
      const row=find('C04');await detail(row);
      assert.equal(await page.locator('#proof-choice option').count(),2);
      const second=row.fact_to_evidence.b2,first=row.fact_to_evidence.b;
      assert.ok(await page.locator('#doc-'+second+'.alternative').count());
      await page.locator('#proof-choice').selectOption('1');
      assert.ok(await page.locator('#doc-'+second+'.current').count());
      assert.ok(await page.locator('#doc-'+first+'.alternative').count());
    });
    await check('C03 ambiguity, alias proof and source-independent settings',async()=>{
      const row=find('C03');await detail(row);
      assert.equal(await page.locator('.interpretations>div').count(),2);
      assert.equal(await page.locator('.proof-node').count(),4);
      assert.ok(await page.locator('.proof-node[data-node=alias]').count());
    });
    await check('C06 table/text aggregation displays DAG and 25 pages',async()=>{
      const row=find('C06');await detail(row);
      assert.equal(await page.locator('.proof-node').count(),row.gold.proofs[0].length);
      assert.equal(await page.locator('.source-table tbody tr').count(),3);
      assert.equal(await page.locator('.answer-box strong').innerText(),'25');
      await page.locator('.proof-node[data-node=sum]').click();
      assert.match(await page.locator('.node-analysis').innerText(),/合计求和/);
      assert.ok(await page.locator('.proof-canvas').evaluate(el=>el.scrollLeft>0));
      assert.match(await page.locator('.node-analysis .potential-fact').innerText(),/75/);
      await screenshot('04-aggregation-detail.png');
    });
    await check('C09 unknown is answerable, no-context has no current documents',async()=>{
      await detail(find('C09'));
      assert.match(await page.locator('.intro-labels .status').innerText(),/可作答.*逻辑未知/);
      assert.equal(await page.locator('.answer-box strong').innerText(),'不确定');
      await detail(find('C01','no_context'));
      assert.equal(await page.locator('.document').count(),0);
      assert.ok(await page.locator('.prototype').count());
      assert.match(await page.locator('#materials').innerText(),/当前材料为空/);
    });
    await check('C08 updated world, bridge differences and original quotation',async()=>{
      const row=find('C08');await detail(row);
      assert.equal(await page.locator('.answer-box strong').innerText(),'庞崖');
      assert.equal(await page.locator('.change-item').count(),2);
      await page.locator('.proof-node[data-node=n2]').click();
      assert.ok(await page.locator('.old-bridge').count());
      assert.match(await page.locator('.old-bridge').innerText(),/项燕/);
      const anon=find('C08','anonymous_challenge');await detail(anon);
      assert.ok(await page.getByText('实体命名映射',{exact:false}).count());
    });
    await check('long background is expandable and raw source preserved',async()=>{
      const row=find('C07','noise_12000');await detail(row);
      assert.equal(await page.locator('.document.background').count(),2);
      await page.locator('.document.background details summary').first().click();
      assert.ok(await page.locator('.full-background').first().isVisible());
      assert.equal((await page.locator('.full-background').first().innerText()).length,6000);
    });
    await check('reverse access, conditional time ambiguity and explicit abduction',async()=>{
      await detail(find('C05'));
      assert.match(await page.locator('.proof-node').first().textContent(),/逆查/);
      await detail(find('C10','time_unspecified'));
      assert.equal(await page.locator('.interpretations>div').count(),2);
      await detail(find('C09','bounded_abduction'));
      await page.locator('.proof-node[data-node=assume]').click();
      assert.match(await page.locator('.node-analysis').innerText(),/待补假设/);
    });
    await check('mobile overview and detail fit 390px without page overflow',async()=>{
      await page.setViewportSize({width:390,height:844});
      await overview();
      assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1));
      await screenshot('05-overview-mobile.png');
      await detail(find('C08'));
      assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1));
      await screenshot('06-detail-mobile.png');
      await page.locator('.proof-node[data-node=n2]').focus();
      await page.keyboard.press('Enter');
      assert.match(await page.locator('.node-analysis h3').innerText(),/n2/);
      await catalog();await count(128);
      await page.locator('.filter-shell-title').click();
      assert.equal(await page.locator('.filter-shell').getAttribute('open'),null);
      assert.ok(await page.locator('.question-results').isVisible());
      assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1));
    });
    await check('fixed testing guide is dataset-independent, linked and mobile-readable',async()=>{
      const guide=await browser.newPage({viewport:{width:1440,height:1050}});
      const bundleRequests=[];
      guide.on('request',r=>{if(r.url().includes('/bundle'))bundleRequests.push(r.url());});
      guide.on('pageerror',e=>errors.push(e.message));
      await guide.goto(base+'/#guide?dataset=not_registered');
      await guide.waitForSelector('#testing-guide');
      assert.equal(await guide.locator('#dataset').count(),0);
      assert.match(await guide.locator('[aria-current=page]').innerText(),/03.*测试指引/);
      const content=await guide.locator('#testing-guide').innerHTML();
      for(const filename of ['README.md','combinations.json','sources.json','seeds.json',
          'benchmark.jsonl','inputs.jsonl','oracle_inputs.jsonl','oracle_gold.jsonl','题目审阅册.md']){
        assert.ok(content.includes(filename),filename);
      }
      const links=await guide.locator('#testing-guide a[href*="/files/"]').evaluateAll(nodes=>nodes.map(n=>n.getAttribute('href')));
      for(const href of new Set(links))assert.equal((await guide.request.get(new URL(href,base).href)).status(),200,href);
      await guide.goto(base+'/#guide?dataset=pilot_literature_history_v0');
      await guide.waitForSelector('#testing-guide');
      assert.equal(await guide.locator('#testing-guide').innerHTML(),content);
      await guide.reload();await guide.waitForSelector('#testing-guide');
      assert.deepEqual(bundleRequests,[]);
      await guide.screenshot({path:path.join(out,'07-testing-guide-desktop.png'),fullPage:true});
      await guide.setViewportSize({width:390,height:844});
      assert.ok(await guide.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1));
      await guide.screenshot({path:path.join(out,'08-testing-guide-mobile.png'),fullPage:true});
      await guide.locator('.guide-toc a').last().click();
      await guide.waitForFunction(()=>location.hash.includes('section='));
      assert.match(await guide.title(),/03 测试指引/);
      await guide.close();
    });
    await check('invalid dataset and question offer recovery',async()=>{
      await page.goto(base+'/#question/absent?dataset=pilot_literature_history_v0');
      await page.waitForSelector('#page-title');
      assert.equal(await page.locator('#page-title').innerText(),'题号未找到');
      await page.goto(base+'/#overview?dataset=not_registered');
      await page.getByRole('heading',{name:'暂时无法打开数据集'}).waitFor();
      await page.getByRole('link',{name:'返回已登记的数据集'}).click();
      await page.waitForSelector('.hero');
    });
    // The intentionally invalid dataset yields an expected HTTP 404 console diagnostic.
    const unexpected=errors.filter(e=>!e.includes('404'));
    assert.deepEqual(unexpected,[]);
    assert.deepEqual(failedRequests.filter(r=>r.url!==base+'/api/datasets/not_registered/bundle.json'),[]);
    fs.writeFileSync(path.join(out,'browser_checks.json'),JSON.stringify({
      status:'passed',base,checks,unexpected_browser_errors:unexpected,
      expected_error_route_test:true,failed_requests:failedRequests,viewports:['1440x1050','390x844'],
      report_link:'[检查说明](README.md)'
    },null,2)+'\n');
    console.log('ALL '+checks.length+' browser checks passed');
  }catch(error){
    await page.screenshot({path:path.join(out,'failure.png'),fullPage:true});
    fs.writeFileSync(path.join(out,'browser_checks.json'),JSON.stringify({status:'failed',checks,error:String(error),errors},null,2));
    throw error;
  }finally{await browser.close();}
})().catch(error=>{console.error(error);process.exitCode=1;});

