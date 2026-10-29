import './workspace-shim.mjs';
import assert from 'node:assert/strict';
import {chromium} from 'playwright';
import {writeFile} from 'node:fs/promises';
const base=process.env.MBDYN_STUDIO_URL || 'http://127.0.0.1:8768';
const b=await chromium.launch({headless:true,args:['--enable-unsafe-swiftshader']}),p=await b.newPage({viewport:{width:1440,height:960}}), errors=[];
p.on('pageerror',e=>errors.push(e.message));
try {
 await p.goto(base);await p.waitForFunction(()=>document.querySelector('#solverStatus')?.textContent.includes('MBDyn ready'));
 await p.evaluate(async()=>{const {MechanismView}=await import('/viewport.js');for(const name of ['renderStep','setSample']){const original=MechanismView.prototype[name];MechanismView.prototype[name]=function(...args){original.apply(this,args);if(this.stepView){this.stepView.group.updateMatrixWorld(true);window.__matrix=[...this.stepView.partMeshes.values()][0].matrixWorld.toArray();}}}});
 await p.locator('#stepButton').click();await p.locator('#stepPendulum').click();
 await p.waitForFunction(()=>document.querySelector('#notice')?.textContent.includes('Matching STEP solid and rigid pendulum loaded'),null,{timeout:60000});
 assert.match(await p.locator('#stepStatus').textContent(),/1 attached/);
 assert.equal(await p.locator('#graph-body-upper_link-mass').inputValue(),'1.2');
 const initial=await p.evaluate(()=>window.__matrix);
 const ev=p.waitForResponse(r=>r.url().endsWith('/api/run')&&r.request().method()==='POST',{timeout:120000});await p.locator('#runButton').click();const result=await (await ev).json();assert(result.ok);
 await p.waitForFunction(()=>document.querySelector('#notice')?.textContent.includes('MBDyn completed successfully'));
 await p.locator('#timeSlider').fill(String(result.samples.length-1));await p.locator('#timeSlider').dispatchEvent('input');
 assert.notDeepEqual(await p.evaluate(()=>window.__matrix),initial);assert.deepEqual(errors,[]);
 await p.screenshot({path:'tests/evidence/step-pendulum.png'});
 await writeFile('tests/evidence/step-pendulum-ui.json',JSON.stringify({ok:true,runId:result.runId,samples:result.samples.length},null,2));
} catch(e) {console.error(e);process.exitCode=1;} finally {await b.close();}
