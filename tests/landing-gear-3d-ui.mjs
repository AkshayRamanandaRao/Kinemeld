import './workspace-shim.mjs';
import assert from 'node:assert/strict';
import {chromium} from 'playwright';
import {mkdir,readFile} from 'node:fs/promises';
const base=process.env.MBDYN_STUDIO_URL||'http://127.0.0.1:8786';
const browser=await chromium.launch({headless:true,args:['--enable-unsafe-swiftshader']});
const page=await browser.newPage({viewport:{width:1440,height:1200},acceptDownloads:true}),errors=[];
page.on('pageerror',e=>errors.push(e.message));page.on('dialog',d=>d.accept());await page.route('**/api/tour-preference',r=>r.fulfill({json:{enabled:false}}));
try{
 await page.goto(base);await page.waitForFunction(()=>document.querySelector('#solverStatus')?.textContent.includes('MBDyn ready'));
 await page.locator('#projectFile').setInputFiles('examples/landing-gear-3d/landing-gear-drop.mbdyn-studio');await page.waitForFunction(()=>document.querySelector('#notice')?.textContent.includes('Project imported and validated'),null,{timeout:180000});assert.match(await page.locator('#stepStatus').textContent(),/2 attached/);
 const response=page.waitForResponse(r=>r.url().endsWith('/api/run')&&r.request().method()==='POST',{timeout:120000});await page.locator('#runButton').click();const result=await (await response).json();assert(result.ok,JSON.stringify(result));assert(result.metrics.maxConstraintError<1e-7);assert(result.samples.some(s=>s.contactStates[0].force>3000));assert(result.samples.some(s=>s.contactStates[0].force===0));
 await page.waitForFunction(()=>document.querySelector('#notice')?.textContent.includes('MBDyn completed successfully'));await page.locator('[data-entity="contact-tire"]').click();await page.locator('#signalSelect').selectOption({label:'Contact normal force (reconstructed)'});assert.equal(await page.locator('#forceSelect').inputValue(),'tire');const i=result.samples.findIndex(s=>s.contactStates[0].force>2500);await page.locator('#timeSlider').fill(String(i));await page.locator('#timeSlider').dispatchEvent('input');
 await page.locator('.inspector').evaluate(el=>{const group=el.querySelector('#spatial-contact-tire-radius').closest('.property-group');el.scrollTop+=group.getBoundingClientRect().top-el.getBoundingClientRect().top-20;});
 if(process.env.MBDYN_SKIP_DOC_SCREENSHOTS!=='1'){await mkdir('docs/images',{recursive:true});await page.screenshot({path:'docs/images/landing-gear-3d.png'});}
 const down=page.waitForEvent('download');await page.locator('#saveButton').click();const file=await down;const saved=JSON.parse(await readFile(await file.path(),'utf8'));assert.equal(saved.result.source,'MBDyn');assert.equal(saved.model.joints.length,1);assert.equal(Object.keys(saved.assets.step.bindings).length,2);
 await page.locator('#projectFile').setInputFiles(await file.path());await page.waitForFunction(()=>document.querySelector('#notice')?.textContent.includes('Project imported and validated'),null,{timeout:180000});assert.match(await page.locator('#stepStatus').textContent(),/2 attached/);assert.deepEqual(errors,[]);console.log('STEP landing-gear drop: two bodies, real MBDyn, contact plot and save/reopen passed.');
}finally{await browser.close();}
