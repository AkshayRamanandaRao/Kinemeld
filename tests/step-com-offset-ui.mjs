import './workspace-shim.mjs';
import assert from 'node:assert/strict';
import {chromium} from 'playwright';
import {mkdir,readFile} from 'node:fs/promises';
const base=process.env.MBDYN_STUDIO_URL||'http://127.0.0.1:8770';
const browser=await chromium.launch({headless:true,args:['--enable-unsafe-swiftshader']});
const page=await browser.newPage({viewport:{width:1440,height:1200},acceptDownloads:true}),errors=[];
page.on('pageerror',error=>errors.push(error.message));page.on('dialog',dialog=>dialog.accept());await page.route('**/api/tour-preference',route=>route.fulfill({json:{enabled:false}}));
try{
 await page.goto(base);await page.waitForFunction(()=>document.querySelector('#solverStatus')?.textContent.includes('MBDyn ready'));
 await page.locator('#projectFile').setInputFiles('examples/step-composite/composite-body.mbdyn-studio');await page.waitForFunction(()=>document.querySelector('#notice')?.textContent.includes('Project imported and validated'));
 await page.locator('#spatial-gravity-z').fill('-9.81');await page.locator('#spatial-gravity-z').dispatchEvent('change');
 await page.locator('#stepButton').click();await page.locator('#stepFile').setInputFiles('examples/step-composite/brick-left.step');await page.waitForFunction(()=>document.querySelector('#stepDetail')?.textContent.includes('1 STEP files'),null,{timeout:180000});
 await page.locator('#stepBody').selectOption('bob');await page.locator('#stepBind').click();await page.locator('#stepMassDensity').fill('1000');await page.locator('#stepMassCalculate').click();await page.waitForFunction(()=>document.querySelector('#stepMassResult')?.textContent.includes('Mass: 6.00000'),null,{timeout:180000});assert(await page.locator('#stepMassApply').isEnabled());
 await page.locator('#stepMassApply').click();await page.waitForFunction(()=>document.querySelector('#notice')?.textContent.includes('Applied the STEP mass and inertia'));await page.locator('#stepClose').click();
 assert(Math.abs(Number(await page.locator('#spatial-body-bob-centerOfMass-x').inputValue())+.15)<1e-8);assert(Math.abs(Number(await page.locator('#spatial-body-bob-centerOfMass-y').inputValue()))<1e-8);assert(Math.abs(Number(await page.locator('#spatial-body-bob-mass').inputValue())-6)<1e-8);
 const response=page.waitForResponse(r=>r.url().endsWith('/api/run')&&r.request().method()==='POST',{timeout:120000});await page.locator('#runButton').click();const result=await (await response).json();assert(result.ok,JSON.stringify(result));assert(Math.abs(result.model.bodies[0].centerOfMass.x+.15)<1e-8);assert(Math.abs(result.samples.at(-1).nodes[0].ry)>.01);
 await page.waitForFunction(()=>document.querySelector('#notice')?.textContent.includes('MBDyn completed successfully'));
 await page.locator('#signalSelect').selectOption('2');await page.locator('#timeSlider').fill(String(result.samples.length-1));await page.locator('#timeSlider').dispatchEvent('input');
 await page.locator('.inspector').evaluate(element=>{const input=element.querySelector('#spatial-body-bob-centerOfMass-x');element.scrollTop+=input.getBoundingClientRect().top-element.getBoundingClientRect().top-350;});
 if(process.env.MBDYN_SKIP_DOC_SCREENSHOTS!=='1'){await mkdir('docs/images',{recursive:true});await page.screenshot({path:'docs/images/step-offset-com.png'});}
 const event=page.waitForEvent('download');await page.locator('#saveButton').click();const saved=await event;const project=JSON.parse(await readFile(await saved.path(),'utf8'));assert(Math.abs(project.model.bodies[0].centerOfMass.x+.15)<1e-8);assert(project.assets.step);assert.equal(project.result.source,'MBDyn');
 await page.locator('#projectFile').setInputFiles(await saved.path());await page.waitForFunction(()=>document.querySelector('#notice')?.textContent.includes('Project imported and validated'),null,{timeout:180000});assert(Math.abs(Number(await page.locator('#spatial-body-bob-centerOfMass-x').inputValue())+.15)<1e-8);assert.match(await page.locator('#stepStatus').textContent(),/1 attached/);assert.deepEqual(errors,[]);
 console.log('Offset STEP COM: measured, applied, real gravity-driven MBDyn motion, project save and reopen passed.');
}finally{await browser.close();}
