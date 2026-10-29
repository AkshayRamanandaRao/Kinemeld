import './workspace-shim.mjs';
import assert from 'node:assert/strict';
import {chromium} from 'playwright';
import {mkdir,readFile} from 'node:fs/promises';
const base=process.env.MBDYN_STUDIO_URL||'http://127.0.0.1:8785';
const browser=await chromium.launch({headless:true,args:['--enable-unsafe-swiftshader']});
const page=await browser.newPage({viewport:{width:1440,height:1200},acceptDownloads:true}),errors=[];
page.on('pageerror',e=>errors.push(e.message));page.on('dialog',d=>d.accept());await page.route('**/api/tour-preference',r=>r.fulfill({json:{enabled:false}}));
try{
 await page.goto(base);await page.waitForFunction(()=>document.querySelector('#solverStatus')?.textContent.includes('MBDyn ready'));
 await page.locator('#projectFile').setInputFiles('examples/wishbone-3d/wishbone.mbdyn-studio');await page.waitForFunction(()=>document.querySelector('#notice')?.textContent.includes('Project imported and validated'),null,{timeout:180000});assert.match(await page.locator('#stepStatus').textContent(),/3 attached/);
 const response=page.waitForResponse(r=>r.url().endsWith('/api/run')&&r.request().method()==='POST',{timeout:120000});await page.locator('#runButton').click();const result=await (await response).json();assert(result.ok,JSON.stringify(result));assert(result.metrics.maxConstraintError<1e-7);assert(result.samples.some(s=>Math.abs(s.nodes.find(n=>n.id==='upright').z-.175)>.02));
 await page.waitForFunction(()=>document.querySelector('#notice')?.textContent.includes('MBDyn completed successfully'));await page.locator('#nodeSelect').selectOption('upright');await page.locator('#timeSlider').fill(String(Math.floor(result.samples.length/2)));await page.locator('#timeSlider').dispatchEvent('input');
 if(process.env.MBDYN_SKIP_DOC_SCREENSHOTS!=='1'){await mkdir('docs/images',{recursive:true});await page.screenshot({path:'docs/images/wishbone-3d.png'});}
 const download=page.waitForEvent('download');await page.locator('#saveButton').click();const file=await download;const saved=JSON.parse(await readFile(await file.path(),'utf8'));assert.equal(saved.result.source,'MBDyn');assert.equal(saved.model.joints.length,4);assert.equal(Object.keys(saved.assets.step.bindings).length,3);
 await page.locator('#projectFile').setInputFiles(await file.path());await page.waitForFunction(()=>document.querySelector('#notice')?.textContent.includes('Project imported and validated'),null,{timeout:180000});assert.match(await page.locator('#stepStatus').textContent(),/3 attached/);assert.deepEqual(errors,[]);console.log('Three STEP parts, closed-loop 3D suspension, real MBDyn and save/reopen passed.');
}finally{await browser.close();}
