import './workspace-shim.mjs';
import assert from 'node:assert/strict';
import {chromium} from 'playwright';
import {mkdir,readFile} from 'node:fs/promises';
const base=process.env.MBDYN_STUDIO_URL||'http://127.0.0.1:8768';
const browser=await chromium.launch({headless:true,args:['--enable-unsafe-swiftshader']});const page=await browser.newPage({viewport:{width:1440,height:960},acceptDownloads:true}),errors=[];
page.on('pageerror',e=>errors.push(e.message));page.on('dialog',d=>d.accept());await page.route('**/api/tour-preference',route=>route.fulfill({json:{enabled:false}}));
const change=async(id,value)=>{await page.locator(id).fill(String(value));await page.locator(id).dispatchEvent('change');};
try{
 await page.goto(base);await page.waitForFunction(()=>document.querySelector('#solverStatus')?.textContent.includes('MBDyn ready'));
 await page.locator('#examplesButton').click();await page.locator('.example-card').filter({has:page.getByRole('heading',{name:'3D full-inertia pendulum',exact:true})}).getByRole('button',{name:/Open example/}).click();
 await change('#spatial-body-bob-inertia-xy',.11);await page.locator('#validateButton').click();await page.waitForFunction(()=>document.querySelector('#validationBadge')?.textContent==='Needs attention');assert(await page.locator('#issuesList').getByText(/positive definite/i).count());
 await change('#spatial-body-bob-inertia-xy',.02);await page.locator('#validateButton').click();await page.waitForFunction(()=>document.querySelector('#validationBadge')?.textContent==='Ready');
 await page.locator('#stepButton').click();await page.locator('#stepFile').setInputFiles('examples/step-pendulum/pendulum.step');await page.waitForFunction(()=>document.querySelector('#stepDetail')?.textContent.includes('1 STEP files'),null,{timeout:180000});await page.locator('#stepBody').selectOption('bob');await page.locator('#stepBind').click();await page.locator('#stepClose').click();
 const response=page.waitForResponse(r=>r.url().endsWith('/api/run')&&r.request().method()==='POST',{timeout:120000});await page.locator('#runButton').click();const result=await (await response).json();assert(result.ok,JSON.stringify(result));assert.equal(result.model.bodies[0].inertia.xy,.02);assert(result.samples.every(sample=>sample.nodes.every(node=>Number.isFinite(node.wx))));
 await page.waitForFunction(()=>document.querySelector('#notice')?.textContent.includes('MBDyn completed successfully'));
 await page.locator('#timeSlider').fill(String(Math.floor((result.samples.length-1)/2)));await page.locator('#timeSlider').dispatchEvent('input');
 await page.setViewportSize({width:1440,height:1200});
 await page.locator('.inspector').evaluate(element=>{const group=element.querySelector('#spatial-body-bob-inertia-xy').closest('.property-group');element.scrollTop+=group.getBoundingClientRect().top-element.getBoundingClientRect().top-20;});
 if(process.env.MBDYN_SKIP_DOC_SCREENSHOTS!=='1'){await mkdir('docs/images',{recursive:true});await page.screenshot({path:'docs/images/spatial-full-inertia.png'});}
 const event=page.waitForEvent('download');await page.locator('#saveButton').click();const saved=await event;const project=JSON.parse(await readFile(await saved.path(),'utf8'));assert.equal(project.model.bodies[0].inertia.xy,.02);assert(project.assets.step);assert.equal(project.result.source,'MBDyn');
 await page.locator('#projectFile').setInputFiles(await saved.path());await page.waitForFunction(()=>document.querySelector('#notice')?.textContent.includes('Project imported and validated'),null,{timeout:120000});assert.equal(Number(await page.locator('#spatial-body-bob-inertia-xy').inputValue()),.02);assert.match(await page.locator('#stepStatus').textContent(),/1 attached/);assert.deepEqual(errors,[]);console.log('Full 3D inertia, invalid-tensor diagnostics, STEP, MBDyn and project reopen passed');
}finally{await browser.close();}
