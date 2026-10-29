import './workspace-shim.mjs';
import assert from 'node:assert/strict';
import {chromium} from 'playwright';
const base=process.env.MBDYN_STUDIO_URL||'http://127.0.0.1:8768';
const browser=await chromium.launch({headless:true,args:['--enable-unsafe-swiftshader']}),page=await browser.newPage({viewport:{width:1440,height:960}}), errors=[];
page.on('pageerror',e=>errors.push(e.message));
try {
 await page.request.post(base+'/api/tour-preference',{data:{enabled:false}});await page.goto(base);await page.waitForFunction(()=>document.querySelector('#solverStatus')?.textContent.includes('MBDyn ready'));
 await page.locator('#examplesButton').click();await page.locator('.example-card').filter({has:page.getByRole('heading',{name:'Authored rigid pendulum',exact:true})}).getByRole('button',{name:/Open example/}).click();
 await page.getByText('Calculate mass and inertia from a uniform solid').click();
 await page.getByLabel('Solid shape').selectOption('brick');await page.getByLabel('Density (kg/m³)').fill('1200');
 await page.getByLabel('Width X (m)').fill('.03');await page.getByLabel('Width Y (m)').fill('.03');await page.getByLabel('Length Z (m)').fill('1');
 await page.getByRole('button',{name:'Apply mass and inertia'}).click();
 assert(Math.abs(Number(await page.locator('#graph-body-upper_link-mass').inputValue())-1.08)<1e-10);
 assert(Math.abs(Number(await page.locator('#graph-body-upper_link-inertia-yy').inputValue())-.090081)<1e-10);
 await page.waitForFunction(()=>document.querySelector('#validationBadge')?.textContent==='Ready');
 const evt=page.waitForResponse(r=>r.url().endsWith('/api/run')&&r.request().method()==='POST',{timeout:120000});await page.locator('#runButton').click();const result=await (await evt).json();assert(result.ok,JSON.stringify(result));
 await page.waitForFunction(()=>document.querySelector('#notice')?.textContent.includes('MBDyn completed successfully'));
 assert.equal(result.model.bodies[0].mass,1.08);
 await page.locator('#undoButton').click();assert.equal(await page.locator('#graph-body-upper_link-mass').inputValue(),'1.2');
 assert.deepEqual(errors,[]);console.log(JSON.stringify({ok:true,runId:result.runId,checks:['brick mass and inertia','real MBDyn solve','undo']}));
}catch(e){console.error(e);process.exitCode=1;}finally{await browser.close();}
