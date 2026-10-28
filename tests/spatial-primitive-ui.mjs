import assert from 'node:assert/strict';
import {chromium} from 'playwright';
import * as THREE from 'three';
import {readFile,writeFile} from 'node:fs/promises';
const base=process.env.MBDYN_STUDIO_URL || 'http://127.0.0.1:8768';
const browser=await chromium.launch({headless:true,args:['--enable-unsafe-swiftshader']});
const page=await browser.newPage({viewport:{width:1440,height:960},acceptDownloads:true}),errors=[];
page.on('pageerror',e=>errors.push(e.message));page.on('dialog',d=>d.accept());
await page.route('**/api/tour-preference',route=>route.fulfill({json:{enabled:false}}));
try{
 await page.goto(base);await page.waitForFunction(()=>document.querySelector('#solverStatus')?.textContent.includes('MBDyn ready'));
 const examples=await (await page.request.get(base+'/api/examples')).json(),model=structuredClone(examples.examples.find(item=>item.id==='spatial-spherical').model);
 const body=model.bodies[0],joint=model.joints[0];Object.assign(body.pose,{rx:20,ry:30,rz:-10});body.centerOfMass={x:.05,y:0,z:0};model.simulation.duration=.3;
 const q=new THREE.Quaternion().setFromEuler(new THREE.Euler(20*Math.PI/180,30*Math.PI/180,-10*Math.PI/180,'XYZ'));
 const a=joint.anchorA,offset=new THREE.Vector3(a.x-body.pose.x,a.y-body.pose.y,a.z-body.pose.z).applyQuaternion(q.invert());
 joint.anchorB={x:offset.x,y:offset.y,z:offset.z};
 await page.locator('#projectFile').setInputFiles({name:'spatial-primitive.mbdyn-studio',mimeType:'application/json',buffer:Buffer.from(JSON.stringify({format:'mbdyn-studio/1',model}))});
 await page.waitForFunction(()=>document.querySelector('#notice')?.textContent.includes('Project imported and validated'));
 await page.getByText('Calculate mass and inertia from a uniform solid').click();await page.getByLabel('Density (kg/m³)',{exact:true}).fill('1000');for(const label of ['Width X (m)','Width Y (m)','Length Z (m)'])await page.getByLabel(label).fill('.1');
 await page.getByRole('button',{name:'Create STEP solid and apply mass'}).click();await page.waitForFunction(()=>document.querySelector('#notice')?.textContent.includes('Created and attached brick STEP solid'),null,{timeout:90000});
 assert(Math.abs(Number(await page.locator('#spatial-body-bob-mass').inputValue())-1)<1e-8);assert.equal(Number(await page.locator('#spatial-body-bob-centerOfMass-x').inputValue()),0);assert.match(await page.locator('#stepStatus').textContent(),/1 attached/);
 await page.locator('#undoButton').click();assert.equal(Number(await page.locator('#spatial-body-bob-centerOfMass-x').inputValue()),.05);await page.locator('#redoButton').click();assert.equal(Number(await page.locator('#spatial-body-bob-centerOfMass-x').inputValue()),0);
 const run=page.waitForResponse(r=>r.url().endsWith('/api/run')&&r.request().method()==='POST',{timeout:120000});await page.locator('#runButton').click();const result=await (await run).json();assert(result.ok,JSON.stringify(result));await page.waitForFunction(()=>document.querySelector('#notice')?.textContent.includes('MBDyn completed successfully'));
 const event=page.waitForEvent('download');await page.locator('#saveButton').click();const file=await event;const saved=JSON.parse(await readFile(await file.path(),'utf8'));const binding=Object.values(saved.assets.step.bindings)[0];assert.deepEqual(binding.pose,body.pose);assert.deepEqual(saved.model.bodies[0].centerOfMass,{x:0,y:0,z:0});assert.equal(saved.result.source,'MBDyn');
 await page.locator('#projectFile').setInputFiles(await file.path());await page.waitForFunction(()=>document.querySelector('#notice')?.textContent.includes('Project imported and validated'),null,{timeout:120000});assert.match(await page.locator('#stepStatus').textContent(),/1 attached/);
 assert.deepEqual(errors,[]);await writeFile('tests/evidence/spatial-primitive-ui-verification.json',JSON.stringify({ok:true,runId:result.runId,checks:['noncommuting 3D pose','generated STEP','uniform mass','real MBDyn','save/reopen']}));console.log('Spatial primitive STEP and MBDyn workflow passed');
}finally{await browser.close();}
