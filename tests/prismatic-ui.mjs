import './workspace-shim.mjs';
import assert from 'node:assert/strict';
import {chromium} from 'playwright';
import {readFile,writeFile} from 'node:fs/promises';
const base=process.env.MBDYN_STUDIO_URL||'http://127.0.0.1:8768';const browser=await chromium.launch({headless:true,args:['--enable-unsafe-swiftshader']}),page=await browser.newPage({viewport:{width:1440,height:960},acceptDownloads:true}),errors=[];page.on('pageerror',e=>errors.push(e.message));
try{
 await page.request.post(base+'/api/tour-preference',{data:{enabled:false}});await page.goto(base);await page.waitForFunction(()=>document.querySelector('#solverStatus')?.textContent.includes('MBDyn ready'));
 await page.locator('#examplesButton').click();await page.locator('.example-card').filter({has:page.getByRole('heading',{name:'Authored rigid pendulum',exact:true})}).getByRole('button',{name:/Open example/}).click();
 await page.getByLabel('New joint type').selectOption('prismatic');await page.getByRole('button',{name:'Add body + prismatic slider'}).click();
 await page.locator('[data-entity="joint-hinge1"]').click();assert(await page.locator('#graph-joint-hinge1-axisAngleDeg').isVisible());
 await page.locator('[data-entity="node-body1"]').click();await page.getByRole('button',{name:'Add spring / damper',exact:true}).click();
 await page.locator('#durationInput').fill('0.5');await page.locator('#durationInput').press('Tab');
 await page.waitForFunction(()=>document.querySelector('#validationBadge')?.textContent==='Ready');
 const ev=page.waitForResponse(r=>r.url().endsWith('/api/run')&&r.request().method()==='POST',{timeout:120000});await page.locator('#runButton').click();const result=await (await ev).json();assert(result.ok,JSON.stringify(result));assert.equal(result.model.joints[1].type,'prismatic');assert.equal(result.model.forces.length,1);assert(result.samples.every(s=>Number.isFinite(s.sliders[0].position) && Number.isFinite(s.forces[0].force)));
 await page.waitForFunction(()=>document.querySelector('#notice')?.textContent.includes('MBDyn completed successfully'));await page.locator('#signalSelect').selectOption({label:'Slider position (reconstructed)'});assert.equal(await page.locator('#jointSelect').inputValue(),'hinge1');
 const download=page.waitForEvent('download');await page.locator('#csvButton').click();const csv=await download;await csv.saveAs('tests/evidence/slider-ui.csv');assert.match(await readFile('tests/evidence/slider-ui.csv','utf8'),/slider:hinge1:position_m/);
 const save=page.waitForEvent('download');await page.locator('#saveButton').click();const project=await save;await project.saveAs('tests/evidence/slider-ui.mbdyn-studio');await page.locator('#projectFile').setInputFiles('tests/evidence/slider-ui.mbdyn-studio');await page.waitForFunction(()=>document.querySelector('#notice')?.textContent.includes('Project imported and validated'));assert.match(await page.locator('#resultSource').textContent(),/Saved result/);assert.deepEqual(errors,[]);
 await writeFile('tests/evidence/prismatic-ui-verification.json',JSON.stringify({ok:true,runId:result.runId,checks:['create slider','add spring','real solve','slider plot','full CSV','save and reopen']}));console.log('Prismatic plus spring UI workflow passed');
}catch(e){console.error(e);process.exitCode=1;await page.screenshot({path:'tests/evidence/prismatic-ui-failure.png',fullPage:true}).catch(()=>{});}finally{await browser.close();}
