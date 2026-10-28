import assert from 'node:assert/strict';
import {chromium} from 'playwright';
import {mkdir,readFile} from 'node:fs/promises';
const base=process.env.MBDYN_STUDIO_URL||'http://127.0.0.1:8788';
const browser=await chromium.launch({headless:true,args:['--enable-unsafe-swiftshader']});const page=await browser.newPage({viewport:{width:1440,height:1200},acceptDownloads:true}),errors=[];
page.on('pageerror',e=>errors.push(e.message));page.on('dialog',d=>d.accept());await page.route('**/api/tour-preference',r=>r.fulfill({json:{enabled:false}}));
try {
 await page.goto(base);await page.waitForFunction(()=>document.querySelector('#solverStatus')?.textContent.includes('MBDyn ready'));
 await page.locator('#projectFile').setInputFiles('examples/open-wheel-end/wheel-end.mbdyn-studio');await page.waitForFunction(()=>document.querySelector('#notice')?.textContent.includes('Project imported and validated'),null,{timeout:240000});assert.match(await page.locator('#stepStatus').textContent(),/3 attached/);
 const response=page.waitForResponse(r=>r.url().endsWith('/api/run')&&r.request().method()==='POST',{timeout:120000});await page.locator('#runButton').click();const result=await (await response).json();assert(result.ok,JSON.stringify(result));assert(result.metrics.maxConstraintError<1e-7);assert(result.samples.at(-1).nodes.find(n=>n.id==='wheel').wx>2);await page.waitForFunction(()=>document.querySelector('#notice')?.textContent.includes('MBDyn completed successfully'));
 await page.locator('#nodeSelect').selectOption('wheel');await page.locator('#signalSelect').selectOption({label:'Node angular velocity · X / Y / Z'});await page.locator('#timeSlider').fill(String(Math.floor(result.samples.length/2)));await page.locator('#timeSlider').dispatchEvent('input');await page.locator('[data-entity="torque-drive"]').click();
 if(process.env.MBDYN_SKIP_DOC_SCREENSHOTS!=='1'){await mkdir('docs/images',{recursive:true});await page.screenshot({path:'docs/images/open-wheel-end.png'});}
 const download=page.waitForEvent('download');await page.locator('#saveButton').click();const file=await download;const project=JSON.parse(await readFile(await file.path(),'utf8'));assert.equal(project.result.source,'MBDyn');assert.equal(project.assets.step.files.length,3);assert.equal(Object.keys(project.assets.step.bindings).length,3);
 await page.locator('#projectFile').setInputFiles(await file.path());await page.waitForFunction(()=>document.querySelector('#notice')?.textContent.includes('Project imported and validated'),null,{timeout:240000});assert.match(await page.locator('#stepStatus').textContent(),/3 attached/);assert.deepEqual(errors,[]);console.log('Original open CAD wheel end: STEP registration, real MBDyn, save/reopen passed.');
}finally{await browser.close();}
