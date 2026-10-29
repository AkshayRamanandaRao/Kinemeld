import './workspace-shim.mjs';
import assert from 'node:assert/strict';
import {chromium} from 'playwright';
import {mkdir,readFile} from 'node:fs/promises';

const base=process.env.MBDYN_STUDIO_URL||'http://127.0.0.1:19005';
const browser=await chromium.launch({headless:true,args:['--enable-unsafe-swiftshader']});
const page=await browser.newPage({viewport:{width:1440,height:1200},acceptDownloads:true}),errors=[];
page.on('pageerror',e=>errors.push(e.message));page.on('dialog',d=>d.accept());await page.route('**/api/tour-preference',r=>r.fulfill({json:{enabled:false}}));
try {
 await page.goto(base);await page.waitForFunction(()=>document.querySelector('#solverStatus')?.textContent.includes('MBDyn ready'));
 await page.locator('#projectFile').setInputFiles('examples/oleo-strut/wheel-oleo.mbdyn-studio');await page.waitForFunction(()=>document.querySelector('#notice')?.textContent.includes('Project imported and validated'),null,{timeout:180000});assert.match(await page.locator('#stepStatus').textContent(),/3 attached/);
 await page.locator('[data-entity="force-oleo"]').click();assert.equal(Number(await page.locator('#spatial-force-oleo-pressure').inputValue()),1e6);
 const response=page.waitForResponse(r=>r.url().endsWith('/api/run')&&r.request().method()==='POST',{timeout:120000});await page.locator('#runButton').click();const result=await (await response).json();assert(result.ok,JSON.stringify(result));await page.waitForFunction(()=>document.querySelector('#notice')?.textContent.includes('MBDyn completed successfully'));
 const sample=result.samples.reduce((best,s)=>Math.abs(s.time-.25)<Math.abs(best.time-.25)?s:best),index=result.samples.indexOf(sample),state=sample.forces.find(x=>x.id==='oleo');assert(state.gasPressure>1e6&&state.gasForce<0&&state.hydraulicForce<0);assert(result.samples.some(s=>s.forces[0].stopForce<0));assert(result.samples.some(s=>s.forces[0].hydraulicForce>0));
 await page.locator('#signalSelect').selectOption({label:'Oleo gas pressure (native)'});await page.locator('#forceSelect').selectOption('oleo');await page.locator('#timeSlider').fill(String(index));await page.locator('#timeSlider').dispatchEvent('input');assert.match(await page.locator('#plot').getAttribute('aria-label'),/Oleo gas pressure/);
 assert.match(await page.locator('#plot').textContent(),/\d\.\d+e\+6/);assert(await page.locator('#plot svg').evaluate(svg=>[...svg.querySelectorAll('text[text-anchor="end"]')].every(label=>label.getBoundingClientRect().left>=svg.getBoundingClientRect().left-1)));
 const cursor=Number(await page.locator('#plotCursor').getAttribute('x1')),width=await page.locator('#plot').evaluate(node=>Math.max(node.clientWidth,300));assert(Math.abs(cursor-(80+sample.time/result.samples.at(-1).time*(width-92)))<1e-8);
 await page.locator('.inspector').evaluate(element=>{const field=element.querySelector('#spatial-force-oleo-pressure');element.scrollTop+=field.getBoundingClientRect().top-element.getBoundingClientRect().top-90;});
 if(process.env.MBDYN_SKIP_DOC_SCREENSHOTS!=='1'){await mkdir('docs/images',{recursive:true});await page.screenshot({path:'docs/images/oleo-strut.png'});}
 await page.locator('#signalSelect').selectOption({label:'Oleo force components (native / derived)'});assert.match(await page.locator('#plot').getAttribute('aria-label'),/Gas.*Hydraulic.*Stop/);
 await page.locator('#signalSelect').selectOption({label:'Axial tension (native / reconstructed)'});assert.match(await page.locator('#plot').getAttribute('aria-label'),/Axial tension/);
 const csvEvent=page.waitForEvent('download');await page.locator('#csvButton').click();const csv=await csvEvent,lines=(await readFile(await csv.path(),'utf8')).trim().split(/\r?\n/),headers=lines[2].split(','),column=headers.indexOf('force:oleo:gasPressure_Pa'),time=headers.indexOf('time_s');assert(column>=0&&time>=0);const row=lines.slice(3).map(line=>line.split(',')).find(values=>Math.abs(Number(values[time])-sample.time)<1e-10);assert(row);assert(Math.abs(Number(row[column])-state.gasPressure)<1e-5);
 const saveEvent=page.waitForEvent('download');await page.locator('#saveButton').click();const saved=await saveEvent,project=JSON.parse(await readFile(await saved.path(),'utf8'));assert.equal(project.model.forces[0].type,'oleo-strut');assert.equal(project.assets.step.files.length,3);assert(project.result.samples.some(s=>Number.isFinite(s.forces[0].gasPressure)));
 await page.evaluate(()=>{document.querySelector('#notice').textContent='Waiting for import';});await page.locator('#projectFile').setInputFiles(await saved.path());await page.waitForFunction(()=>document.querySelector('#notice')?.textContent.includes('Project imported and validated'),null,{timeout:180000});await page.locator('[data-entity="force-oleo"]').click();assert.equal(Number(await page.locator('#spatial-force-oleo-gasVolume').inputValue()),.001);
 await page.getByRole('button',{name:'Add oleo strut'}).click();assert(await page.locator('#spatial-force-oleo1-pressure').isVisible());await page.locator('#spatial-force-oleo1-gasVolume').fill('.00001');await page.locator('#spatial-force-oleo1-gasVolume').dispatchEvent('change');await page.waitForFunction(()=>document.querySelector('#validationBadge')?.textContent!=='Ready');assert.deepEqual(errors,[]);
 console.log('Oleo strut: sourced STEP, real MBDyn, pressure/forces, CSV, add, invalid gas volume and save/reopen passed.');
}finally{await browser.close();}
