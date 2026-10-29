import './workspace-shim.mjs';
import assert from 'node:assert/strict';
import { chromium } from 'playwright';
import { readFile } from 'node:fs/promises';

const base=process.env.MBDYN_STUDIO_URL || 'http://127.0.0.1:8768';
const browser=await chromium.launch({headless:true,args:['--enable-unsafe-swiftshader']});
const page=await browser.newPage({viewport:{width:1440,height:960},acceptDownloads:true});
await page.route('**/api/tour-preference', route=>route.fulfill({json:{enabled:false}}));
const errors=[]; page.on('pageerror',e=>errors.push(e.message));
try {
  await page.goto(base);
  await page.waitForFunction(()=>document.querySelector('#solverStatus')?.textContent.includes('MBDyn ready'));
  await page.locator('#examplesButton').click();
  await page.locator('.example-card').filter({has:page.getByRole('heading',{name:'3D spherical pendulum',exact:true})}).getByRole('button',{name:/Open example/}).click();
  for(const [id,value] of [['#spatial-body-bob-velocity-vy','0.25'],['#spatial-body-bob-velocity-wz','0.5']]) {await page.locator(id).fill(value);await page.locator(id).dispatchEvent('change');}
  await page.evaluate(async()=>{const {MechanismView}=await import('/viewport.js'); for (const name of ['renderStep','setSample']) {const original=MechanismView.prototype[name];MechanismView.prototype[name]=function(...args){original.apply(this,args);if(this.stepView){this.stepView.group.updateMatrixWorld(true);window.__stepPose=[...this.stepView.partMeshes].map(([id,mesh])=>({id,matrix:mesh.matrixWorld.toArray()}));}};}});
  await page.locator('#stepButton').click();
  await page.locator('#stepFile').setInputFiles('examples/step-pendulum/pendulum.step');
  await page.waitForFunction(()=>document.querySelector('#stepDetail')?.textContent.includes('1 STEP files'),null,{timeout:180000});
  await page.locator('#stepBody').selectOption('bob');await page.locator('#stepBind').click();
  assert.match(await page.locator('#stepDetail').textContent(),/1 attached/);
  await page.locator('#stepClose').click();
  const download=page.waitForEvent('download');await page.locator('#saveButton').click();const saved=await download;const project=JSON.parse(await readFile(await saved.path(),'utf8'));
  const binding=Object.values(project.assets.step.bindings)[0];assert.equal(binding.body,'bob');assert.deepEqual(Object.keys(binding.pose).sort(),['rx','ry','rz','x','y','z']);
  await page.locator('#stepButton').click();await page.locator('#stepRemove').click();await page.locator('#stepClose').click();
  page.on('dialog', dialog=>dialog.accept());await page.locator('#projectFile').setInputFiles(await saved.path());
  await page.waitForFunction(()=>document.querySelector('#notice')?.textContent.includes('Project imported and validated'),null,{timeout:180000});
  assert.match(await page.locator('#stepStatus').textContent(),/1 attached/);
  const initial=await page.evaluate(()=>window.__stepPose);
  const response=page.waitForResponse(r=>r.url().endsWith('/api/run')&&r.request().method()==='POST',{timeout:120000});
  await page.locator('#runButton').click();const result=await (await response).json();assert(result.ok,JSON.stringify(result));
  await page.waitForFunction(()=>document.querySelector('#notice')?.textContent.includes('MBDyn completed successfully'));
  await page.locator('#timeSlider').fill(String(result.samples.length-1));await page.locator('#timeSlider').dispatchEvent('input');
  const actual=await page.evaluate(()=>window.__stepPose);assert.notDeepEqual(actual[0].matrix,initial[0].matrix);
  const sample=result.samples.at(-1).nodes.find(n=>n.id==='bob');assert(Math.abs(sample.rx)>.01 && Math.abs(sample.rz)>.01,JSON.stringify(sample));
  const delta=await page.evaluate(async({actual,initial,first,last})=>{
    const THREE=await import('/vendor/three.module.js');
    const q=p=>new THREE.Quaternion().setFromEuler(new THREE.Euler(p.rx*Math.PI/180,p.ry*Math.PI/180,p.rz*Math.PI/180,'XYZ'));
    const t=(v)=>new THREE.Matrix4().makeTranslation(v.x,v.y,v.z), r=p=>new THREE.Matrix4().makeRotationFromQuaternion(q(p));
    // Display offset cancels when comparing world transforms by conjugation.
    const initialM=new THREE.Matrix4().fromArray(initial), actualM=new THREE.Matrix4().fromArray(actual);
    const offset=initialM.elements.slice(12,15); const display=new THREE.Matrix4().makeTranslation(...offset);
    const expected=display.clone().multiply(t(last)).multiply(r(last)).multiply(r(first).invert()).multiply(t({x:-first.x,y:-first.y,z:-first.z}));
    return Math.max(...actualM.elements.map((v,i)=>Math.abs(v-expected.elements[i])));
  },{actual:actual[0].matrix,initial:initial[0].matrix,first:binding.pose,last:sample});
  assert(delta<1e-5,`STEP matrix differs from native Euler123 pose: ${delta}`);
  assert.deepEqual(errors,[]);
  console.log('Spatial STEP attachment, save/reopen and real 3D MBDyn pose playback passed. Max matrix error:',delta);
} finally {await browser.close();}
