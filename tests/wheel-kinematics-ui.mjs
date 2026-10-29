import './workspace-shim.mjs';
import assert from 'node:assert/strict';
import {chromium} from 'playwright';
import {mkdir,readFile} from 'node:fs/promises';

const base=process.env.MBDYN_STUDIO_URL||'http://127.0.0.1:8789';
const browser=await chromium.launch({headless:true,args:['--enable-unsafe-swiftshader']});
const page=await browser.newPage({viewport:{width:1440,height:1200},acceptDownloads:true}),errors=[];
page.on('pageerror',e=>errors.push(e.message));page.on('dialog',d=>d.accept());await page.route('**/api/tour-preference',r=>r.fulfill({json:{enabled:false}}));
try {
 await page.goto(base);await page.waitForFunction(()=>document.querySelector('#solverStatus')?.textContent.includes('MBDyn ready'));
 const project=JSON.parse(await readFile('examples/open-wheel-end/wheel-end-drop.mbdyn-studio','utf8'));
 project.model.frames=[{id:'vehicle',name:'Vehicle axes',body:'ground',translation:{x:0,y:0,z:0},rotation:{rx:0,ry:0,rz:-90}}];
 await page.locator('#projectFile').setInputFiles({name:'wheel-kinematics.mbdyn-studio',mimeType:'application/json',buffer:Buffer.from(JSON.stringify(project))});await page.waitForFunction(()=>document.querySelector('#notice')?.textContent.includes('Project imported and validated'),null,{timeout:240000});
 const event=page.waitForResponse(r=>r.url().endsWith('/api/run')&&r.request().method()==='POST',{timeout:120000});await page.locator('#runButton').click();const result=await (await event).json();assert(result.ok,JSON.stringify(result));await page.waitForFunction(()=>document.querySelector('#notice')?.textContent.includes('MBDyn completed successfully'));
 const index=Math.floor(result.samples.length/2);await page.locator('#timeSlider').fill(String(index));await page.locator('#timeSlider').dispatchEvent('input');await page.locator('#wheelKinematicsButton').click();
 await page.locator('#wheelKinematicsBody').selectOption('wheel');await page.locator('#wheelKinematicsReference').selectOption('frame:vehicle');await page.locator('#wheelKinematics-axis-x').fill('1');await page.locator('#wheelKinematics-axis-y').fill('0');await page.locator('#wheelKinematicsCalculate').click();
 assert.match(await page.locator('#wheelKinematicsStatus').textContent(),/vertical travel .* m; camber .*°; toe .*°/);assert.match(await page.locator('#wheelKinematicsPlot').getAttribute('aria-label'),/travel from/);
 if(process.env.MBDYN_SKIP_DOC_SCREENSHOTS!=='1'){await mkdir('docs/images',{recursive:true});await page.screenshot({path:'docs/images/wheel-kinematics.png'});}
 const download=page.waitForEvent('download');await page.locator('#wheelKinematicsExport').click();const file=await download,lines=(await readFile(await file.path(),'utf8')).trim().split('\n'),headers=lines[0].split(','),row=Object.fromEntries(headers.map((h,i)=>[h,lines[index+1].split(',')[i]]));
 assert.equal(row.reference,'frame:vehicle');assert.equal(row.reference_parent,'ground');assert.equal(Number(row.reference_rz_deg),-90);const first=result.samples[0].nodes.find(n=>n.id==='wheel'),selected=result.samples[index].nodes.find(n=>n.id==='wheel');assert(Math.abs(Number(row.vertical_travel_m)-(selected.z-first.z))<1e-9);
 const rx=selected.rx*Math.PI/180,ry=selected.ry*Math.PI/180,rz=selected.rz*Math.PI/180;const worldX=Math.cos(ry)*Math.cos(rz),worldY=Math.cos(rx)*Math.sin(rz)+Math.sin(rx)*Math.sin(ry)*Math.cos(rz);assert(Math.abs(Number(row.toe_deg)-Math.atan2(worldY,worldX)*180/Math.PI)<1e-8);
 await page.locator('#wheelKinematics-axis-x').fill('0');await page.locator('#wheelKinematicsCalculate').click();assert.match(await page.locator('#wheelKinematicsStatus').textContent(),/nonzero axle/);assert(await page.locator('#wheelKinematicsExport').isDisabled());
 await page.getByRole('button',{name:'Close wheel kinematics'}).click();const save=page.waitForEvent('download');await page.locator('#saveButton').click();const saved=await save;await page.locator('#projectFile').setInputFiles(await saved.path());await page.waitForFunction(()=>document.querySelector('#notice')?.textContent.includes('Project imported and validated'),null,{timeout:240000});await page.locator('#wheelKinematicsButton').click();await page.locator('#wheelKinematicsBody').selectOption('wheel');await page.locator('#wheelKinematicsReference').selectOption('frame:vehicle');await page.locator('#wheelKinematics-axis-x').fill('1');await page.locator('#wheelKinematics-axis-y').fill('0');await page.locator('#wheelKinematicsCalculate').click();assert.match(await page.locator('#wheelKinematicsStatus').textContent(),/displayed samples/);
 await page.getByRole('button',{name:'Close wheel kinematics'}).click();await page.locator('[data-entity="node-wheel"]').click();await page.locator('#spatial-body-wheel-mass').fill('4');await page.locator('#spatial-body-wheel-mass').dispatchEvent('change');await page.locator('#wheelKinematicsButton').click();await page.waitForFunction(()=>document.querySelector('#notice')?.textContent.includes('current spatial MBDyn result'));assert.deepEqual(errors,[]);console.log('Wheel kinematics: real STEP and MBDyn, frame, CSV, save/reopen and stale gate passed.');
}finally{await browser.close();}
