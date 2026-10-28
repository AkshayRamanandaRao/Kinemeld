import assert from 'node:assert/strict';
import {chromium} from 'playwright';
import {readFile} from 'node:fs/promises';
const base=process.env.MBDYN_STUDIO_URL||'http://127.0.0.1:8768';
const browser=await chromium.launch({headless:true,args:['--enable-unsafe-swiftshader']});const page=await browser.newPage({viewport:{width:1440,height:960},acceptDownloads:true}),errors=[];page.on('pageerror',e=>errors.push(e.message));await page.route('**/api/tour-preference',route=>route.fulfill({json:{enabled:false}}));
const change=async(id,value)=>{await page.locator(id).fill(String(value));await page.locator(id).dispatchEvent('change');};
try {
 await page.goto(base);await page.waitForFunction(()=>document.querySelector('#solverStatus')?.textContent.includes('MBDyn ready'));
 await page.locator('#examplesButton').click();await page.locator('.example-card').filter({has:page.getByRole('heading',{name:'3D oblique slider',exact:true})}).getByRole('button',{name:/Open example/}).click();
 for(const id of ['#spatial-gravity-x','#spatial-gravity-y'])await change(id,0);
 await page.getByRole('button',{name:'Add spring / damper',exact:true}).click();assert(await page.locator('[data-entity="force-spring1"]').count());
 for(const [key,value] of [['anchorA-x',-.6],['anchorA-y',-.8],['anchorA-z',0],['stiffness',10],['damping',1],['restLength',1]])await change(`#spatial-force-spring1-${key}`,value);
 await page.waitForFunction(()=>document.querySelector('#validationBadge')?.textContent==='Ready');
 await page.locator('#stepButton').click();await page.locator('#stepFile').setInputFiles('examples/step-pendulum/pendulum.step');await page.waitForFunction(()=>document.querySelector('#stepDetail')?.textContent.includes('1 STEP files'),null,{timeout:180000});await page.locator('#stepBody').selectOption('block');await page.locator('#stepBind').click();await page.locator('#stepClose').click();
 const response=page.waitForResponse(r=>r.url().endsWith('/api/run')&&r.request().method()==='POST',{timeout:120000});await page.locator('#runButton').click();const result=await (await response).json();assert(result.ok,JSON.stringify(result));assert(Math.abs(result.samples[0].forces[0].length-1.3)<1e-9);assert(Math.abs(result.samples[0].forces[0].force-3.2)<1e-9);assert(result.samples.at(-1).dissipatedEnergy>0);
 await page.waitForFunction(()=>document.querySelector('#notice')?.textContent.includes('MBDyn completed successfully'));await page.locator('#signalSelect').selectOption({label:'Spring tension (reconstructed)'});assert.equal(await page.locator('#forceSelect').inputValue(),'spring1');
 const download=page.waitForEvent('download');await page.locator('#saveButton').click();const saved=await download;const project=JSON.parse(await readFile(await saved.path(),'utf8'));assert(project.assets.step);assert.equal(project.result.samples[0].forces[0].force,result.samples[0].forces[0].force);
 await page.locator('#projectFile').setInputFiles(await saved.path());await page.waitForFunction(()=>document.querySelector('#notice')?.textContent.includes('Project imported and validated'),null,{timeout:180000});await page.locator('#signalSelect').selectOption({label:'Spring length / extension'});assert.match(await page.locator('#stepStatus').textContent(),/1 attached/);assert.deepEqual(errors,[]);console.log('Spatial spring creation, STEP, real MBDyn, plots and saved result reopening passed.');
}catch(e){console.error(e);process.exitCode=1;await page.screenshot({path:'tests/evidence/spatial-spring-ui-failure.png',fullPage:true}).catch(()=>{});}finally{await browser.close();}
