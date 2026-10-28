import assert from 'node:assert/strict';
import {chromium} from 'playwright';
import {mkdir,writeFile} from 'node:fs/promises';
const base=process.env.MBDYN_STUDIO_URL || 'http://127.0.0.1:8768';
const browser=await chromium.launch({headless:true,args:['--enable-unsafe-swiftshader']});
const page=await browser.newPage({viewport:{width:1440,height:960}}), errors=[];
const report={checks:[],started:new Date().toISOString()};page.on('pageerror',e=>errors.push(e.message));
try {
 assert((await page.request.post(`${base}/api/tour-preference`,{data:{enabled:true}})).ok());
 await page.goto(base);await page.waitForFunction(()=>document.querySelector('#solverStatus')?.textContent.includes('MBDyn ready'));
 await page.locator('#guidedTour').waitFor({state:'visible'});await page.locator('#tourNext').click();
 await page.locator('#stepButton').click();await page.locator('#stepPendulum').click();
 await page.waitForFunction(()=>document.querySelector('#notice')?.textContent.includes('Matching STEP solid and rigid pendulum loaded'),null,{timeout:90000});
 assert.match(await page.locator('#stepStatus').textContent(),/1 attached/);await page.locator('#tourNext').click();
 assert.match(await page.locator('#tourTitle').textContent(),/Inspect the body/);
 await page.locator('#tourNext').click();assert.match(await page.locator('#tourTitle').textContent(),/Add a body and hinge/);
 await page.getByRole('button',{name:'Add body + revolute hinge'}).click();
 assert(await page.locator('[data-entity="node-body1"]').isVisible());
 await page.locator('#graph-body-body1-mass').fill('1.1');await page.locator('#graph-body-body1-mass').press('Tab');
 await page.locator('#tourNext').click();await page.locator('[data-entity="joint-hinge1"]').click();
 assert(await page.locator('#graph-joint-hinge1-parentAnchor-x').isVisible());
 await page.locator('#tourNext').click();assert.match(await page.locator('#tourText').textContent(),/does not calculate mass/);
 await page.locator('#tourNext').click();await page.locator('#validateButton').click();
 await page.waitForFunction(()=>document.querySelector('#validationBadge')?.textContent==='Ready');
 const ev=page.waitForResponse(r=>r.url().endsWith('/api/run')&&r.request().method()==='POST',{timeout:120000});
 await page.locator('#runButton').click();const result=await (await ev).json();assert.equal(result.ok,true,JSON.stringify(result));
 await page.waitForFunction(()=>document.querySelector('#notice')?.textContent.includes('MBDyn completed successfully'));
 assert.equal(result.model.bodies.length,2);assert.equal(result.model.bodies[1].mass,1.1);assert(result.samples.length>1);
 await page.locator('#tourNext').click();assert.match(await page.locator('#tourTitle').textContent(),/Explore and save/);
 await page.locator('#tourDisable').check();await page.locator('#tourNext').click();
 await page.waitForFunction(async()=>!(await (await fetch('/api/tour-preference')).json()).enabled);
 assert.deepEqual(errors,[]);report.ok=true;report.runId=result.runId;report.checks.push('Tour, STEP pendulum, body mass, new revolute joint, validation, and real solver run');
} catch(e){report.ok=false;report.failure=e.stack;process.exitCode=1;console.error(e);await page.screenshot({path:'tests/evidence/guided-workflow-failure.png',fullPage:true}).catch(()=>{});}
finally {report.errors=errors;await mkdir('tests/evidence',{recursive:true});await writeFile('tests/evidence/guided-workflow-verification.json',JSON.stringify(report,null,2));await browser.close();}
