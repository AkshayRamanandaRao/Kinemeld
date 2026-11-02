import './workspace-shim.mjs';
import assert from 'node:assert/strict';
import {chromium} from 'playwright';
import {mkdir,readFile} from 'node:fs/promises';
import {createHash} from 'node:crypto';

const base=process.env.MBDYN_STUDIO_URL||'http://127.0.0.1:18996';
const browser=await chromium.launch({headless:true,args:['--enable-unsafe-swiftshader']});
const page=await browser.newPage({viewport:{width:1440,height:1200},acceptDownloads:true}),errors=[];
page.on('pageerror',error=>errors.push(error.message));page.on('dialog',dialog=>dialog.accept());await page.route('**/api/tour-preference',route=>route.fulfill({json:{enabled:false}}));
try {
 await page.goto(base);await page.waitForFunction(()=>document.querySelector('#solverStatus')?.textContent.includes('MBDyn ready'));
 await page.locator('#projectFile').setInputFiles('examples/open-aircraft-nose-kinematics/nose-gear-kinematics.mbdyn-studio');await page.waitForFunction(()=>document.querySelector('#notice')?.textContent.includes('Project imported and validated'),null,{timeout:180000});
 assert.match(await page.locator('#stepStatus').textContent(),/11 attached/);assert.match(await page.locator('body').innerText(),/Aircraft nose-gear kinematics/);assert.doesNotMatch(await page.locator('body').innerText(),/KINEMATIC ONLY|loads invalid|source overlaps/);
 await page.locator('#stepButton').click();assert.match(await page.locator('#stepDetail').textContent(),/11 attached/);assert(await page.locator('#stepReview').isHidden());await page.locator('#stepClose').click();
 const event=page.waitForResponse(r=>r.url().endsWith('/api/run')&&r.request().method()==='POST',{timeout:120000});await page.locator('#runButton').click();const run=await (await event).json();assert(run.ok,JSON.stringify(run));await page.waitForFunction(()=>document.querySelector('#notice')?.textContent.includes('MBDyn completed successfully'));
 const first=run.samples[0].sliders.find(s=>s.id==='oleo'),last=run.samples.at(-1).sliders.find(s=>s.id==='oleo');assert(Math.abs((last.position-first.position)-.01)<1e-9);assert(run.metrics.maxConstraintError<1e-8);
 const upper0=run.samples[0].nodes.find(n=>n.id==='upper_link'),upper1=run.samples.at(-1).nodes.find(n=>n.id==='upper_link');assert(Math.abs(upper1.rx-upper0.rx)>.1);
 await page.locator('[data-entity="joint-oleo"]').click();await page.locator('#signalSelect').selectOption({label:'Slider position (reconstructed)'});await page.locator('#jointSelect').selectOption('oleo');await page.locator('#timeSlider').fill('250');await page.locator('#timeSlider').dispatchEvent('input');
 await page.locator('.inspector').evaluate(element=>{const group=element.querySelector('#spatial-joint-oleo-motion-amplitude').closest('.property-group');element.scrollTop+=group.getBoundingClientRect().top-element.getBoundingClientRect().top-20;});
 if(process.env.MBDYN_SKIP_DOC_SCREENSHOTS!=='1'){await mkdir('docs/images',{recursive:true});await page.screenshot({path:'docs/images/aircraft-nose-kinematics.png'});}
 const save=page.waitForEvent('download');await page.locator('#saveButton').click();const file=await save,saved=JSON.parse(await readFile(await file.path(),'utf8'));assert.equal(Object.keys(saved.assets.step.bindings).length,11);assert.equal(Object.keys(saved.assets.step.occurrenceWitnesses).length,11);assert.equal(saved.result.source,'MBDyn');assert.equal(createHash('sha256').update(Buffer.from(saved.assets.step.files[0].data,'base64')).digest('hex'),'b53205b3356f9b98b0edf6d2ba4f8b04f46cc61607cad263857192c1aeb7a575');
 await page.evaluate(()=>{document.querySelector('#notice').textContent='Waiting for import';});await page.locator('#projectFile').setInputFiles(await file.path());await page.waitForFunction(()=>document.querySelector('#notice')?.textContent.includes('Project imported and validated'),null,{timeout:180000});assert.match(await page.locator('#stepStatus').textContent(),/11 attached/);assert.deepEqual(errors,[]);
 console.log('Source STEP nose gear: inferred 10 mm sweep, solver motion, 11 bindings and save/reopen passed. Loads are not valid aircraft predictions.');
}finally{await browser.close();}
