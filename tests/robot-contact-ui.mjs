/** Browser GUI against a real local server and native solver; no desktop automation. */
import './workspace-shim.mjs';
import assert from 'node:assert/strict';
import {readFile,mkdir} from 'node:fs/promises';
import {chromium} from 'playwright';
const base=process.env.MBDYN_STUDIO_URL||'http://127.0.0.1:8791';
const browser=await chromium.launch({headless:true,args:['--enable-unsafe-swiftshader']});
const page=await browser.newPage({viewport:{width:1440,height:1060},acceptDownloads:true});
const errors=[];page.on('pageerror',e=>errors.push(e.message));page.on('dialog',d=>d.accept());
await page.route('**/api/tour-preference',r=>r.fulfill({json:{enabled:false}}));
async function open(title){await page.locator('#examplesButton').click();await page.locator('.example-card').filter({has:page.getByRole('heading',{name:title,exact:true})}).getByRole('button').click();await page.locator('[data-step="model"]').click();}
async function solve(){await page.locator('[data-step="simulate"]').click();const response=page.waitForResponse(r=>r.url().endsWith('/api/run')&&r.request().method()==='POST',{timeout:120000});await page.locator('#runButton').click();const result=await(await response).json();assert(result.ok,JSON.stringify(result.error));await page.waitForFunction(()=>document.querySelector('#notice')?.textContent.includes('MBDyn completed successfully'));return result;}
async function change(id,value){await page.locator(`#${id}`).evaluate((input,next)=>{input.value=String(next);input.dispatchEvent(new Event('change'));},value);}
async function csv(){const download=page.waitForEvent('download');await page.locator('#csvButton').click();return readFile(await(await download).path(),'utf8');}
try{
  await page.goto(base);await page.waitForFunction(()=>document.querySelector('#solverStatus')?.textContent.includes('MBDyn ready'));
  await open('Robot joint brake');await page.locator('#modelTree [data-entity="joint-hinge"]').click();
  assert.equal(await page.locator('#spatial-joint-hinge-brake').inputValue(),'coulomb');
  await page.locator('#spatial-joint-hinge-brake').selectOption('none');assert.equal(await page.locator('#spatial-joint-hinge-friction-preload').count(),0);
  await page.locator('#spatial-joint-hinge-brake').selectOption('coulomb');assert.equal(Number(await page.locator('#spatial-joint-hinge-friction-preload').inputValue()),20);
  await change('spatial-joint-hinge-friction-preload',25);await page.locator('#undoButton').click();
  await page.locator('#modelTree [data-entity="joint-hinge"]').click();assert.equal(Number(await page.locator('#spatial-joint-hinge-friction-preload').inputValue()),20);
  const brake=await solve();assert(brake.samples.filter(s=>s.time<.11).every(s=>Math.abs(s.nodes[0].wz)<1e-12));assert(brake.samples.at(-1).jointFrictionStates[0].dissipatedEnergy>.1);
  await page.locator('#signalSelect').selectOption({label:'Joint friction torque (native)'});
  await page.waitForFunction(()=>document.querySelector('#plotStats')?.textContent.includes('Full resolution'));
  assert.match(await csv(),/jointFriction:hinge:torque_Nm/);
  await page.locator('[data-step="model"]').click();await page.locator('#modelTree [data-entity="torque-motor"]').click();
  await change('spatial-torque-motor-amplitude',0);await change('spatial-torque-motor-offset',1.5);
  await page.locator('[data-step="simulate"]').click();const rejectedResponse=page.waitForResponse(r=>r.url().endsWith('/api/run')&&r.request().method()==='POST');await page.locator('#runButton').click();
  const rejected=await(await rejectedResponse).json();assert.equal(rejected.ok,false);assert.match(JSON.stringify(rejected),/brake hinge produces energy at t=0\.001/);
  await page.waitForFunction(()=>document.querySelector('#notice')?.textContent.includes('produces energy'));
  await open('Robot bumper collision');await page.locator('#modelTree [data-entity="contact-bumper"]').click();
  assert.equal(await page.locator('#spatial-contact-bumper-otherBody').inputValue(),'b');assert.equal(await page.locator('#spatial-contact-bumper-friction').count(),0);
  await page.getByRole('button',{name:'Add sphere-sphere contact',exact:true}).click();assert.equal(await page.locator('#modelTree [data-entity="contact-contact1"]').count(),1);
  await page.getByRole('button',{name:'Remove sphere-sphere contact',exact:true}).click();assert.equal(await page.locator('#modelTree [data-entity="contact-contact1"]').count(),0);
  await page.locator('#modelTree [data-entity="node-b"]').click();await page.getByRole('button',{name:'Remove selected body',exact:true}).click();assert.match(await page.locator('#notice').textContent(),/Remove all contacts/);assert.equal(await page.locator('#modelTree [data-entity="node-b"]').count(),1);
  await page.locator('#modelTree [data-entity="contact-bumper"]').click();
  await change('spatial-contact-bumper-otherCenter-y',.02);await page.locator('#undoButton').click();
  const pair=await solve();assert(pair.samples.some(s=>s.contactStates[0].force>20));
  for(const sample of pair.samples)assert(Math.abs(sample.nodes[0].vx+2*sample.nodes[1].vx)<1e-7);
  await page.locator('#signalSelect').selectOption({label:'Contact normal force (native)'});
  await page.waitForFunction(()=>document.querySelector('#plotStats')?.textContent.includes('Full resolution'));
  assert.match(await csv(),/contact:bumper:force_N/);
  if(process.env.KINEMELD_SCREENSHOT){await mkdir('verification/robot-contact',{recursive:true});const peak=pair.samples.findIndex(s=>s.contactStates[0].force===Math.max(...pair.samples.map(s=>s.contactStates[0].force)));await page.locator('#timeSlider').evaluate((input,value)=>{input.value=String(value);input.dispatchEvent(new Event('input'));},peak);await page.screenshot({path:process.env.KINEMELD_SCREENSHOT});}
  const download=page.waitForEvent('download');await page.locator('#saveButton').click();const file=await download;const project=JSON.parse(await readFile(await file.path(),'utf8'));assert.equal(project.model.contacts[0].type,'sphere-sphere');
  await page.locator('#projectFile').setInputFiles(await file.path());await page.waitForFunction(()=>document.querySelector('#notice')?.textContent.includes('Project imported and validated'));
  await page.locator('[data-step="model"]').click();await page.locator('#modelTree [data-entity="contact-bumper"]').click();await change('spatial-contact-bumper-otherRadius',.11);
  await page.waitForFunction(()=>document.querySelector('#resultSource')?.textContent.includes('Stale'));assert(await page.locator('#playButton').isDisabled());
  assert.deepEqual(errors,[]);console.log('Native robot brake and sphere pair: add/remove/edit/undo, native solves and expected startup rejection, full-resolution plots/CSV, save/reopen and stale gates passed.');
}finally{await browser.close();}
