import './workspace-shim.mjs';
import assert from 'node:assert/strict';
import {chromium} from 'playwright';
import {mkdir,readFile} from 'node:fs/promises';
const base=process.env.MBDYN_STUDIO_URL || 'http://127.0.0.1:8768';
const browser=await chromium.launch({headless:true,args:['--enable-unsafe-swiftshader']});
const page=await browser.newPage({viewport:{width:1440,height:1050},acceptDownloads:true}),errors=[];
page.on('pageerror',e=>errors.push(e.message));page.on('dialog',d=>d.accept());await page.route('**/api/tour-preference',route=>route.fulfill({json:{enabled:false}}));
try {
 await page.goto(base);await page.waitForFunction(()=>document.querySelector('#solverStatus')?.textContent.includes('MBDyn ready'));
 await page.locator('#projectFile').setInputFiles('examples/step-composite/composite-body.mbdyn-studio');await page.waitForFunction(()=>document.querySelector('#notice')?.textContent.includes('Project imported and validated'));
 await page.locator('#stepButton').click();await page.locator('#stepFile').setInputFiles(['examples/step-composite/brick-left.step','examples/step-composite/brick-right.step']);await page.waitForFunction(()=>document.querySelector('#stepDetail')?.textContent.includes('2 STEP files'),null,{timeout:180000});
 for(const part of ['0:part-1','1:part-1']){await page.locator('#stepPart').selectOption(part);await page.locator('#stepBody').selectOption('bob');await page.locator('#stepBind').click();}
 assert.match(await page.locator('#stepDetail').textContent(),/2 attached/);await page.locator('#stepMassDensity').fill('1000');await page.locator('#stepMassCalculateBody').click();
 await page.waitForFunction(()=>document.querySelector('#stepMassResult')?.textContent.includes('Combined occurrences: 2'),null,{timeout:180000});
 const result=await page.locator('#stepMassResult').textContent();assert.match(result,/Mass: 12\.00000/);assert.match(result,/body axes/);assert(await page.locator('#stepMassApply').isEnabled());
 if(process.env.MBDYN_SKIP_DOC_SCREENSHOTS!=='1'){await mkdir('docs/images',{recursive:true});await page.screenshot({path:'docs/images/step-composite-mass.png'});}
 await page.locator('#stepMassApply').click();await page.waitForFunction(()=>document.querySelector('#notice')?.textContent.includes('Applied the STEP mass and inertia'));await page.locator('#stepClose').click();
 assert(Math.abs(Number(await page.locator('#spatial-body-bob-mass').inputValue())-12)<1e-7);assert(Math.abs(Number(await page.locator('#spatial-body-bob-inertia-xy').inputValue()))>.01);
 const ev=page.waitForResponse(r=>r.url().endsWith('/api/run')&&r.request().method()==='POST',{timeout:120000});await page.locator('#runButton').click();const run=await (await ev).json();assert(run.ok,JSON.stringify(run));assert.equal(run.model.bodies[0].inertia.xy!==0,true);
 await page.waitForFunction(()=>document.querySelector('#notice')?.textContent.includes('MBDyn completed successfully'));const download=page.waitForEvent('download');await page.locator('#saveButton').click();const saved=await download;const project=JSON.parse(await readFile(await saved.path(),'utf8'));assert.equal(Object.keys(project.assets.step.bindings).length,2);assert(Math.abs(project.model.bodies[0].inertia.xy)>.01);
 await page.locator('#projectFile').setInputFiles(await saved.path());await page.waitForFunction(()=>document.querySelector('#notice')?.textContent.includes('Project imported and validated'),null,{timeout:180000});assert.match(await page.locator('#stepStatus').textContent(),/2 attached/);assert.deepEqual(errors,[]);
 console.log('Two real STEP parts: combined inertia, explicit apply, MBDyn and project reopen passed.');
}finally{await browser.close();}
