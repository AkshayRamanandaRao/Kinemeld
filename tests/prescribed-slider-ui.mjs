import assert from 'node:assert/strict';
import {chromium} from 'playwright';
import {mkdir,readFile} from 'node:fs/promises';

const base=process.env.MBDYN_STUDIO_URL||'http://127.0.0.1:8786';
const browser=await chromium.launch({headless:true,args:['--enable-unsafe-swiftshader']});
const page=await browser.newPage({viewport:{width:1440,height:1200},acceptDownloads:true}),errors=[];
page.on('pageerror',error=>errors.push(error.message));page.on('dialog',dialog=>dialog.accept());
await page.route('**/api/tour-preference',route=>route.fulfill({json:{enabled:false}}));
try{
 await page.goto(base);await page.waitForFunction(()=>document.querySelector('#solverStatus')?.textContent.includes('MBDyn ready'));
 await page.locator('#projectFile').setInputFiles('examples/prescribed-wheel-bump/wheel-bump.mbdyn-studio');
 await page.waitForFunction(()=>document.querySelector('#notice')?.textContent.includes('Project imported and validated'),null,{timeout:180000});
 await page.locator('[data-entity="joint-fixture"]').click();
 await page.getByRole('button',{name:'Remove prescribed motion'}).click();
 await page.getByRole('button',{name:'Add prescribed slider motion'}).click();
 await page.locator('#spatial-joint-fixture-motion-amplitude').fill('0.025');await page.locator('#spatial-joint-fixture-motion-amplitude').dispatchEvent('change');
 await page.waitForFunction(()=>document.querySelector('#validationBadge')?.textContent==='Ready');
 const response=page.waitForResponse(r=>r.url().endsWith('/api/run')&&r.request().method()==='POST',{timeout:120000});await page.locator('#runButton').click();const result=await (await response).json();assert(result.ok,JSON.stringify(result));
 assert.equal(result.model.joints[0].motion.amplitude,.025);assert(Math.abs(result.samples.at(-1).sliders[0].position-.05)<1e-7);
 await page.waitForFunction(()=>document.querySelector('#notice')?.textContent.includes('MBDyn completed successfully'));
 await page.locator('#signalSelect').selectOption({label:'Slider position (reconstructed)'});await page.locator('#jointSelect').selectOption('fixture');
 await page.locator('#timeSlider').fill(String(Math.floor((result.samples.length-1)/2)));await page.locator('#timeSlider').dispatchEvent('input');
 await page.locator('.inspector').evaluate(element=>{const group=element.querySelector('#spatial-joint-fixture-motion-amplitude').closest('.property-group');element.scrollTop+=group.getBoundingClientRect().top-element.getBoundingClientRect().top-20;});
 if(process.env.MBDYN_SKIP_DOC_SCREENSHOTS!=='1'){await mkdir('docs/images',{recursive:true});await page.screenshot({path:'docs/images/prescribed-wheel-travel.png'});}
 const event=page.waitForEvent('download');await page.locator('#saveButton').click();const file=await event;const saved=JSON.parse(await readFile(await file.path(),'utf8'));
 assert(saved.assets.step);assert.equal(saved.model.joints[0].motion.amplitude,.025);assert.equal(saved.result.source,'MBDyn');
 await page.locator('#projectFile').setInputFiles(await file.path());await page.waitForFunction(()=>document.querySelector('#notice')?.textContent.includes('Project imported and validated'),null,{timeout:180000});
 await page.locator('[data-entity="joint-fixture"]').click();await page.locator('#spatial-joint-fixture-motion-amplitude').fill('0.03');await page.locator('#spatial-joint-fixture-motion-amplitude').dispatchEvent('change');
 await page.waitForFunction(()=>document.querySelector('#resultSource')?.textContent.includes('Stale'));assert(await page.locator('#playButton').isDisabled());assert.deepEqual(errors,[]);
 console.log('Prescribed slider: sourced STEP wheel, MBDyn, trajectory, save/reopen and stale-result checks passed.');
}finally{await browser.close();}
