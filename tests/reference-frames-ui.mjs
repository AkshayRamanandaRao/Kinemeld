import './workspace-shim.mjs';
import assert from 'node:assert/strict';
import {chromium} from 'playwright';
import {mkdir,readFile} from 'node:fs/promises';

const base=process.env.MBDYN_STUDIO_URL||'http://127.0.0.1:8776';
const browser=await chromium.launch({headless:true,args:['--enable-unsafe-swiftshader']});
const page=await browser.newPage({viewport:{width:1440,height:1200},acceptDownloads:true}),errors=[];
page.on('pageerror',error=>errors.push(error.message));page.on('dialog',dialog=>dialog.accept());
await page.route('**/api/tour-preference',route=>route.fulfill({json:{enabled:false}}));
const change=async(id,value)=>{await page.locator(id).fill(String(value));await page.locator(id).dispatchEvent('change');};
try{
 await page.goto(base);await page.waitForFunction(()=>document.querySelector('#solverStatus')?.textContent.includes('MBDyn ready'));
 await page.locator('#examplesButton').click();await page.locator('.example-card').filter({has:page.getByRole('heading',{name:'3D revolute pendulum',exact:true})}).getByRole('button',{name:/Open example/}).click();
 await page.locator('#stepButton').click();await page.locator('#stepFile').setInputFiles('examples/step-pendulum/pendulum.step');await page.waitForFunction(()=>document.querySelector('#stepDetail')?.textContent.includes('1 STEP files'),null,{timeout:180000});await page.locator('#stepBody').selectOption('arm');await page.locator('#stepBind').click();await page.locator('#stepClose').click();
 await page.locator('summary').filter({hasText:'Named reference frames'}).click();await page.getByRole('button',{name:'Add reference frame'}).click();
 await change('#reference-frame-name','Pendulum pivot');await change('#reference-frame-translation-x',-.5);await change('#reference-frame-translation-z',Math.sqrt(3)/2);await change('#reference-frame-rotation-rz',90);
 await page.locator('.inspector').evaluate(element=>{const group=element.querySelector('#reference-frame-select').closest('.property-group');element.scrollTop+=group.getBoundingClientRect().top-element.getBoundingClientRect().top-20;});
 if(process.env.MBDYN_SKIP_DOC_SCREENSHOTS!=='1'){await mkdir('docs/images',{recursive:true});await page.screenshot({path:'docs/images/reference-frame-edit.png'});}
 await page.locator('[data-entity="joint-hinge"]').click();await change('#spatial-joint-hinge-anchorB-x',-.4);await page.locator('#joint-frame-axis-b').selectOption('x');await page.getByRole('button',{name:'Apply frame to joint B'}).click();
 assert(Math.abs(Number(await page.locator('#spatial-joint-hinge-anchorB-x').inputValue())+.5)<1e-12);assert(Math.abs(Number(await page.locator('#spatial-joint-hinge-axisB-y').inputValue())-1)<1e-12);
 await page.waitForFunction(()=>document.querySelector('#validationBadge')?.textContent==='Ready');
 const response=page.waitForResponse(r=>r.url().endsWith('/api/run')&&r.request().method()==='POST',{timeout:120000});await page.locator('#runButton').click();const result=await (await response).json();assert(result.ok,JSON.stringify(result));assert.equal(result.model.frames[0].name,'Pendulum pivot');
 await page.waitForFunction(()=>document.querySelector('#notice')?.textContent.includes('MBDyn completed successfully'));assert.equal(await page.locator('#joint-frame-axis-b').inputValue(),'x');
 await page.locator('.inspector').evaluate(element=>{const group=element.querySelector('#joint-frame-b').closest('.property-group');element.scrollTop+=group.getBoundingClientRect().top-element.getBoundingClientRect().top-20;});
 if(process.env.MBDYN_SKIP_DOC_SCREENSHOTS!=='1'){await mkdir('docs/images',{recursive:true});await page.screenshot({path:'docs/images/reference-frame-joint.png'});}
 const event=page.waitForEvent('download');await page.locator('#saveButton').click();const file=await event;const saved=JSON.parse(await readFile(await file.path(),'utf8'));assert.equal(saved.model.frames[0].name,'Pendulum pivot');assert.equal(saved.result.source,'MBDyn');assert(saved.assets.step);
 const bad=structuredClone(saved.model);bad.frames[0].body='missing';const check=await (await page.request.post(base+'/api/validate',{data:{model:bad}})).json();assert.equal(check.valid,false);assert(check.issues.some(issue=>issue.field==='frames.0.body'));
 await page.locator('#projectFile').setInputFiles(await file.path());await page.waitForFunction(()=>document.querySelector('#notice')?.textContent.includes('Project imported and validated'),null,{timeout:120000});assert.match(await page.locator('#stepStatus').textContent(),/1 attached/);
 await page.locator('[data-entity="joint-hinge"]').click();await page.locator('summary').filter({hasText:'Named reference frames'}).click().catch(()=>{});
 if(!await page.locator('#reference-frame-translation-x').isVisible())await page.locator('summary').filter({hasText:'Named reference frames'}).click();
 await change('#reference-frame-translation-x',-.3);assert(Math.abs(Number(await page.locator('#spatial-joint-hinge-anchorB-x').inputValue())+.5)<1e-12);
 assert.deepEqual(errors,[]);console.log('Named frame, rotated local joint axis, STEP, real MBDyn, save/reopen and snapshot semantics passed.');
}finally{await browser.close();}
