import assert from 'node:assert/strict';
import {chromium} from 'playwright';
import {readFile,writeFile} from 'node:fs/promises';
const base=process.env.MBDYN_STUDIO_URL||'http://127.0.0.1:8768';
const browser=await chromium.launch({headless:true,args:['--enable-unsafe-swiftshader']}),page=await browser.newPage({viewport:{width:1440,height:960},acceptDownloads:true}),errors=[];
page.on('pageerror',e=>errors.push(e.message));
try {
 await page.request.post(base+'/api/tour-preference',{data:{enabled:false}});await page.goto(base);await page.waitForFunction(()=>document.querySelector('#solverStatus')?.textContent.includes('MBDyn ready'));
 await page.locator('#examplesButton').click();await page.locator('.example-card').filter({has:page.getByRole('heading',{name:'Authored rigid pendulum',exact:true})}).getByRole('button',{name:/Open example/}).click();
 await page.getByRole('button',{name:'Add spring / damper',exact:true}).click();
 assert(await page.locator('[data-entity="force-spring1"]').isVisible());
 await page.locator('#graph-force-spring1-restLength').fill('0.45');await page.locator('#graph-force-spring1-restLength').press('Tab');
 await page.locator('#graph-force-spring1-damping').fill('2');await page.locator('#graph-force-spring1-damping').press('Tab');
 await page.waitForFunction(()=>document.querySelector('#validationBadge')?.textContent==='Ready');
 const ev=page.waitForResponse(r=>r.url().endsWith('/api/run')&&r.request().method()==='POST',{timeout:120000});await page.locator('#runButton').click();const result=await (await ev).json();
 assert(result.ok,JSON.stringify(result));assert.equal(result.model.forces[0].restLength,.45);assert(result.samples.some(x=>Math.abs(x.forces[0].force)>1e-5));
 await page.waitForFunction(()=>document.querySelector('#notice')?.textContent.includes('MBDyn completed successfully'));
 await page.locator('#signalSelect').selectOption({label:'Spring tension (reconstructed)'});assert.equal(await page.locator('#forceSelect').inputValue(),'spring1');assert.match(await page.locator('#signalTitle').textContent(),/Spring tension/);
 const dlEvent=page.waitForEvent('download');await page.locator('#csvButton').click();const dl=await dlEvent;await dl.saveAs('tests/evidence/spring-ui.csv');const csv=await readFile('tests/evidence/spring-ui.csv','utf8');assert.match(csv,/spring:spring1:force_N/);
 const projectEvent=page.waitForEvent('download');await page.locator('#saveButton').click();const project=await projectEvent;await project.saveAs('tests/evidence/spring-ui.mbdyn-studio');
 await page.locator('#projectFile').setInputFiles('tests/evidence/spring-ui.mbdyn-studio');await page.waitForFunction(()=>document.querySelector('#notice')?.textContent.includes('Project imported and validated'));
 assert.match(await page.locator('#resultSource').textContent(),/Saved result/);assert(await page.locator('[data-entity="force-spring1"]').isVisible());assert.deepEqual(errors,[]);
 await writeFile('tests/evidence/spring-ui-verification.json',JSON.stringify({ok:true,runId:result.runId,samples:result.samples.length,checks:['editor validation','real solver','force plot','full CSV','save and reopen']}));console.log('Spring UI and MBDyn result passed');
}catch(e){console.error(e);process.exitCode=1;await page.screenshot({path:'tests/evidence/spring-ui-failure.png',fullPage:true}).catch(()=>{});}finally{await browser.close();}
