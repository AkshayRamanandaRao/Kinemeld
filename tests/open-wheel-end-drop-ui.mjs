import './workspace-shim.mjs';
import assert from 'node:assert/strict';
import {chromium} from 'playwright';
import {mkdir,readFile} from 'node:fs/promises';
const base=process.env.MBDYN_STUDIO_URL||'http://127.0.0.1:8789';
const browser=await chromium.launch({headless:true,args:['--enable-unsafe-swiftshader']});
const page=await browser.newPage({viewport:{width:1440,height:1200},acceptDownloads:true}),errors=[];
page.on('pageerror',e=>errors.push(e.message));page.on('dialog',d=>d.accept());await page.route('**/api/tour-preference',r=>r.fulfill({json:{enabled:false}}));
try {
 await page.goto(base);await page.waitForFunction(()=>document.querySelector('#solverStatus')?.textContent.includes('MBDyn ready'));
 await page.locator('#projectFile').setInputFiles('examples/open-wheel-end/wheel-end-drop.mbdyn-studio');await page.waitForFunction(()=>document.querySelector('#notice')?.textContent.includes('Project imported and validated'),null,{timeout:240000});assert.match(await page.locator('#stepStatus').textContent(),/3 attached/);
 const ev=page.waitForResponse(r=>r.url().endsWith('/api/run')&&r.request().method()==='POST',{timeout:120000});await page.locator('#runButton').click();const result=await (await ev).json();assert(result.ok,JSON.stringify(result));assert(result.samples.some(s=>s.contactStates[0].force>100));assert(result.samples.at(-1).contactStates[0].dissipatedEnergy>0);assert(result.metrics.maxConstraintError<1e-6);await page.waitForFunction(()=>document.querySelector('#notice')?.textContent.includes('MBDyn completed successfully'));
 await page.locator('#signalSelect').selectOption({label:'Contact normal force (reconstructed)'});assert.equal(await page.locator('#forceSelect').inputValue(),'tire_plane');const i=result.samples.findIndex(s=>s.contactStates[0].force>400);await page.locator('#timeSlider').fill(String(i));await page.locator('#timeSlider').dispatchEvent('input');await page.locator('[data-entity="contact-tire_plane"]').click();
 await page.mouse.move(700,600);await page.mouse.wheel(0,400);await page.waitForTimeout(300);
 await page.locator('.inspector').evaluate(element=>{const group=element.querySelector('#spatial-contact-tire_plane-radius').closest('.property-group');element.scrollTop+=group.getBoundingClientRect().top-element.getBoundingClientRect().top-20;});
 if(process.env.MBDYN_SKIP_DOC_SCREENSHOTS!=='1'){await mkdir('docs/images',{recursive:true});await page.screenshot({path:'docs/images/open-wheel-end-drop.png'});}
 const evsave=page.waitForEvent('download');await page.locator('#saveButton').click();const saved=await evsave;const project=JSON.parse(await readFile(await saved.path(),'utf8'));const original=JSON.parse(await readFile('examples/open-wheel-end/wheel-end-drop.mbdyn-studio','utf8'));assert.deepEqual(project.assets.step.files,original.assets.step.files);assert(project.result.samples[0].contactStates);await page.locator('#projectFile').setInputFiles(await saved.path());await page.waitForFunction(()=>document.querySelector('#notice')?.textContent.includes('Project imported and validated'),null,{timeout:240000});assert.match(await page.locator('#stepStatus').textContent(),/3 attached/);assert.deepEqual(errors,[]);console.log('Open CAD wheel drop: actual STEP, MBDyn contact results, save/reopen passed');
}finally{await browser.close();}
