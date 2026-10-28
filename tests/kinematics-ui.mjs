import assert from 'node:assert/strict';
import {chromium} from 'playwright';
import {mkdir,readFile} from 'node:fs/promises';
const base=process.env.MBDYN_STUDIO_URL || 'http://127.0.0.1:8768';
const browser=await chromium.launch({headless:true,args:['--enable-unsafe-swiftshader']});
const page=await browser.newPage({viewport:{width:1440,height:960},acceptDownloads:true}),errors=[];
page.on('pageerror',error=>errors.push(error.message));page.on('dialog',dialog=>dialog.accept());
await page.route('**/api/tour-preference',route=>route.fulfill({json:{enabled:false}}));
try {
 await page.goto(base);await page.waitForFunction(()=>document.querySelector('#solverStatus')?.textContent.includes('MBDyn ready'));
 await page.locator('#examplesButton').click();await page.locator('.example-card').filter({has:page.getByRole('heading',{name:'3D closed-loop axle',exact:true})}).getByRole('button',{name:/Open example/}).click();
 await page.locator('#stepButton').click();await page.locator('#stepFile').setInputFiles('examples/step-pendulum/pendulum.step');await page.waitForFunction(()=>document.querySelector('#stepDetail')?.textContent.includes('1 STEP files'),null,{timeout:180000});await page.locator('#stepBody').selectOption('axle');await page.locator('#stepBind').click();await page.locator('#stepClose').click();
 await page.locator('#kinematicsButton').click();await page.locator('#kinematicsDialog summary').filter({hasText:'Axle · axle'}).click();
 for(const label of ['Axle Euler X unknown','Axle Euler Y unknown','Axle Euler Z unknown'])await page.getByLabel(label,{exact:true}).check();
 await page.getByLabel('Axle Euler Y target',{exact:true}).check();await page.getByLabel('Axle Euler Y target value (°)',{exact:true}).fill('10');
 let release,seen;const blocked=new Promise(resolve=>{release=resolve;}),started=new Promise(resolve=>{seen=resolve;});let delayOnce=true;
 await page.route('**/api/kinematics',async route=>{if(delayOnce){delayOnce=false;seen();await blocked;}await route.continue();});
 const delayed=page.waitForResponse(r=>r.url().endsWith('/api/kinematics')&&r.request().method()==='POST');await page.locator('#kinematicsSolve').click();await started;await page.getByLabel('Axle Euler Y target value (°)',{exact:true}).fill('11');release();await delayed;
 await page.waitForFunction(()=>document.querySelector('#kinematicsResult')?.textContent.includes('Inputs changed; solve again.'));assert(await page.locator('#kinematicsApply').isDisabled());
 await page.getByLabel('Axle Euler Y target value (°)',{exact:true}).fill('10');
 const response=page.waitForResponse(r=>r.url().endsWith('/api/kinematics') && r.request().method()==='POST');await page.locator('#kinematicsSolve').click();const result=await (await response).json();assert(result.ok,JSON.stringify(result));assert.equal(result.jacobianRank,3);assert(result.maxResidual<1e-7);assert.equal(result.dynamicsValidation.valid,true);
 await page.waitForFunction(()=>document.querySelector('#kinematicsResult')?.textContent.includes('position solution was found'));assert(await page.locator('#kinematicsApply').isEnabled());
 await mkdir('tests/evidence',{recursive:true});await page.locator('#kinematicsResult').scrollIntoViewIfNeeded();await page.screenshot({path:'tests/evidence/kinematics-ui.png'});
 await page.locator('#kinematicsApply').click();await page.locator('[data-entity="node-axle"]').click();assert(Math.abs(Number(await page.locator('#spatial-body-axle-pose-ry').inputValue())-10)<1e-6);assert.match(await page.locator('#stepStatus').textContent(),/1 attached/);
 const run=page.waitForResponse(r=>r.url().endsWith('/api/run')&&r.request().method()==='POST',{timeout:120000});await page.locator('#runButton').click();const execution=await (await run).json();assert(execution.ok,JSON.stringify(execution));await page.waitForFunction(()=>document.querySelector('#notice')?.textContent.includes('MBDyn completed successfully'));
 const download=page.waitForEvent('download');await page.locator('#saveButton').click();const file=await download;const project=JSON.parse(await readFile(await file.path(),'utf8'));assert(project.assets.step);assert.equal(project.result.source,'MBDyn');assert(Math.abs(project.model.bodies.find(item=>item.id==='axle').pose.ry-10)<1e-6);
 await page.locator('#projectFile').setInputFiles(await file.path());await page.waitForFunction(()=>document.querySelector('#notice')?.textContent.includes('Project imported and validated'),null,{timeout:180000});assert.match(await page.locator('#stepStatus').textContent(),/1 attached/);assert.deepEqual(errors,[]);
 console.log('Position solve, STEP binding, MBDyn run and saved project reopening passed');
} finally {await browser.close();}
