import './workspace-shim.mjs';
import assert from 'node:assert/strict';
import {chromium} from 'playwright';
import {readFile,writeFile} from 'node:fs/promises';
const base=process.env.MBDYN_STUDIO_URL||'http://127.0.0.1:8768';
const browser=await chromium.launch({headless:true,args:['--enable-unsafe-swiftshader']}),page=await browser.newPage({viewport:{width:1440,height:960},acceptDownloads:true}),errors=[];
page.on('pageerror',e=>errors.push(e.message));
try{
 await page.route('**/api/tour-preference',route=>route.fulfill({json:{enabled:false}}));
 await page.goto(base);await page.waitForFunction(()=>document.querySelector('#solverStatus')?.textContent.includes('MBDyn ready'));
 await page.locator('#examplesButton').click();await page.locator('.example-card').filter({has:page.getByRole('heading',{name:'Authored rigid pendulum',exact:true})}).getByRole('button',{name:/Open example/}).click();
 await page.getByText('Calculate mass and inertia from a uniform solid').click();
 await page.getByLabel('Density (kg/m³)').fill('1000');for(const field of ['Width X (m)','Width Y (m)','Length Z (m)'])await page.getByLabel(field).fill('.1');
 await page.getByRole('button',{name:'Create STEP solid and apply mass'}).click();await page.waitForFunction(()=>document.querySelector('#notice')?.textContent.includes('Created and attached brick STEP solid'),null,{timeout:90000});
 assert(Math.abs(Number(await page.locator('#graph-body-upper_link-mass').inputValue())-1)<1e-8);
 await page.locator('#stepButton').click();await page.locator('#stepMassDensity').fill('2000');
 const response=page.waitForResponse(r=>r.url().endsWith('/api/step/mass')&&r.request().method()==='POST',{timeout:120000});await page.locator('#stepMassCalculate').click();const result=await (await response).json();assert(result.ok,JSON.stringify(result));assert(Math.abs(result.mass-2)<1e-8);
 await page.waitForFunction(()=>document.querySelector('#stepMassResult')?.textContent.includes('Mass: 2.'));await page.locator('#stepMassApply').click();
 await page.waitForFunction(()=>document.querySelector('#notice')?.textContent.includes('Applied the STEP mass and inertia'));await page.locator('#stepClose').click();
 assert(Math.abs(Number(await page.locator('#graph-body-upper_link-mass').inputValue())-2)<1e-8);
 const save=page.waitForEvent('download');await page.locator('#saveButton').click();const download=await save;await download.saveAs('tests/evidence/step-mass-project.mbdyn-studio');const project=JSON.parse(await readFile('tests/evidence/step-mass-project.mbdyn-studio','utf8'));assert(Math.abs(project.model.bodies[0].mass-2)<1e-8);assert.equal(Object.keys(project.assets.step.bindings).length,1);
 await page.locator('#undoButton').click();assert(Math.abs(Number(await page.locator('#graph-body-upper_link-mass').inputValue())-1)<1e-8);
 await page.locator('#redoButton').click();assert(Math.abs(Number(await page.locator('#graph-body-upper_link-mass').inputValue())-2)<1e-8);
 page.once('dialog',dialog=>dialog.accept());
 await page.locator('#projectFile').setInputFiles('tests/evidence/step-mass-project.mbdyn-studio');await page.waitForFunction(()=>document.querySelector('#notice')?.textContent.includes('Project imported and validated'),null,{timeout:120000});assert(Math.abs(Number(await page.locator('#graph-body-upper_link-mass').inputValue())-2)<1e-8);
 assert.deepEqual(errors,[]);await writeFile('tests/evidence/step-mass-ui-verification.json',JSON.stringify({ok:true,checks:['generated and bound STEP','actual OpenCascade mass','explicit density','validated apply','undo/redo','save and reopen']}));console.log('STEP mass calculator and safe apply UI passed');
}catch(error){console.error(error);process.exitCode=1;await page.screenshot({path:'tests/evidence/step-mass-ui-failure.png',fullPage:true}).catch(()=>{});}finally{await browser.close();}
