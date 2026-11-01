import './workspace-shim.mjs';
import assert from 'node:assert/strict';
import {readFile,mkdir} from 'node:fs/promises';
import {chromium} from 'playwright';
const base=process.env.MBDYN_STUDIO_URL||'http://127.0.0.1:8792',browser=await chromium.launch({headless:true,args:['--enable-unsafe-swiftshader']});
const page=await browser.newPage({viewport:{width:1440,height:1060},acceptDownloads:true}),errors=[];
page.on('pageerror',e=>errors.push(e.message));page.on('dialog',d=>d.accept());await page.route('**/api/tour-preference',r=>r.fulfill({json:{enabled:false}}));
async function field(key,value){await page.locator(`#field-${key}`).evaluate((input,value)=>{input.value=String(value);input.dispatchEvent(new Event('change'));},value);}
async function solve(){await page.locator('[data-step="simulate"]').click();const response=page.waitForResponse(r=>r.url().endsWith('/api/run')&&r.request().method()==='POST',{timeout:120000});await page.locator('#runButton').click();const result=await(await response).json();assert(result.ok,JSON.stringify(result.error));await page.waitForFunction(()=>document.querySelector('#notice')?.textContent.includes('MBDyn completed successfully'));return result;}
try{
  await page.goto(base);await page.waitForFunction(()=>document.querySelector('#solverStatus')?.textContent.includes('MBDyn ready'));
  await page.locator('#examplesButton').click();await page.locator('.example-card').filter({has:page.getByRole('heading',{name:'Flexible robot link',exact:true})}).getByRole('button').click();
  await page.locator('[data-step="model"]').click();assert.deepEqual(await page.locator('#field-nodes option').evaluateAll(options=>options.map(o=>o.value)),['3','5','9']);
  await page.locator('#field-nodes').selectOption('9');await page.locator('#undoButton').click();assert.equal(await page.locator('#field-nodes').inputValue(),'5');
  await field('bendingStiffness',10);await page.locator('#undoButton').click();assert.equal(Number(await page.locator('#field-bendingStiffness').inputValue()),5);
  assert(await page.locator('#previewButton').isDisabled());const result=await solve();
  assert.equal(result.model.kind,'flexible-link');assert(result.samples.every(s=>s.nodes.length===5));const final=result.samples.at(-1);
  for(const key of ['deck','motion','beamOutput','jointOutput']){const response=await page.request.get(base+result.files[key]);assert.equal(response.status(),200,`${key} artifact is downloadable`);assert((await response.body()).length>0);}
  assert(Math.abs(final.tipDeflection+.0083433333)<3e-6);assert(Math.abs(final.nodes[2].z-final.nodes[4].z/2)>.001);assert(result.samples.every(s=>Math.abs(s.nodes[0].z)<1e-8));
  await page.locator('#signalSelect').selectOption({label:'Tip deflection (native)'});await page.waitForFunction(()=>document.querySelector('#plotStats')?.textContent.includes('Full resolution'));
  const csvDownload=page.waitForEvent('download');await page.locator('#csvButton').click();const csv=await readFile(await(await csvDownload).path(),'utf8');assert.match(csv,/tipDeflection_m/);assert.match(csv,/rootMoment_Nm/);assert.match(csv,/flex5/);
  if(process.env.KINEMELD_SCREENSHOT){await mkdir('verification/flexible-link',{recursive:true});await page.locator('#timeSlider').evaluate((input,value)=>{input.value=String(value);input.dispatchEvent(new Event('input'));},result.samples.length-1);await page.screenshot({path:process.env.KINEMELD_SCREENSHOT});}
  const download=page.waitForEvent('download');await page.locator('#saveButton').click();const saved=await download;const project=JSON.parse(await readFile(await saved.path(),'utf8'));assert.equal(project.model.kind,'flexible-link');assert(project.result.samples[0].nodes.some(n=>n.id==='flex5'));
  await page.locator('#projectFile').setInputFiles(await saved.path());await page.waitForFunction(()=>document.querySelector('#notice')?.textContent.includes('Project imported and validated'));
  await page.locator('[data-step="model"]').click();await field('tipLoad',-.5);await page.waitForFunction(()=>document.querySelector('#resultSource')?.textContent.includes('Stale'));assert(await page.locator('#playButton').isDisabled());
  await field('tipLoad',-1);await page.locator('#field-nodes').selectOption('9');await page.locator('#durationInput').evaluate(input=>{input.value='15';input.dispatchEvent(new Event('change'));});
  await page.locator('[data-step="simulate"]').click();let finished=false;const pending=page.waitForResponse(r=>r.url().endsWith('/api/run')&&r.request().method()==='POST',{timeout:120000});pending.then(()=>{finished=true;});await page.locator('#runButton').click();await page.waitForFunction(()=>!document.querySelector('#cancelRunButton').hidden);await page.waitForTimeout(600);assert.equal(finished,false,'native beam run must still be active before cancellation');await page.locator('#cancelRunButton').click();
  const cancelled=await(await pending).json();assert.equal(cancelled.ok,false);assert.equal(cancelled.cancelled,true);assert.match(cancelled.log,/MBDyn|Reading Beam/);await page.waitForFunction(()=>document.querySelector('#statusText')?.textContent.includes('Run cancelled'));
  const log=await page.request.get(base+cancelled.files.log);assert.equal(log.status(),200);assert.match(await log.text(),/Reading Beam/);
  assert.deepEqual(errors,[]);console.log('Flexible link GUI: mesh/material edits and undo, native bending playback, full-resolution CSV, save/reopen/stale and actual native cancellation passed.');
}finally{await browser.close();}
