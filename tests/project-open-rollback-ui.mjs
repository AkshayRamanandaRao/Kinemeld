import './workspace-shim.mjs';
import assert from 'node:assert/strict';
import {chromium} from 'playwright';
import {createHash} from 'node:crypto';
import {readFile} from 'node:fs/promises';

const base=process.env.MBDYN_STUDIO_URL || 'http://127.0.0.1:8768';
const browser=await chromium.launch({headless:true,args:['--enable-unsafe-swiftshader']});
const page=await browser.newPage({viewport:{width:1440,height:960}});
const errors=[];page.on('pageerror',e=>errors.push(e.message));
await page.route('**/api/tour-preference',route=>route.fulfill({json:{enabled:false}}));
await page.addInitScript(()=>{
  window.__nativeTest={current:null,pending:null,previous:null,candidate:null,rollbacks:0};
  window.mbdynNative={
    notify(op){const s=window.__nativeTest;if(op==='finalize-open')s.previous=null;if(op==='discard-open')s.pending=null;},
    async call(op,payload={}){if(op==='recovery')return {};if(op==='autosave')return {skipped:true};
      const s=window.__nativeTest;
      if(op==='new-project'){s.pending={project:structuredClone(payload.project)};return structuredClone(s.pending);}
      if(op==='save') {s.current={path:s.current?.path||'C:/test/current.mbdyn-studio',project:structuredClone({format:'mbdyn-studio/1',schemaVersion:1,model:payload.model,result:payload.result,view:payload.view,assets:payload.assets})};return {path:s.current.path};}
      if(op==='open'){s.pending=structuredClone(s.candidate);return structuredClone(s.pending);}
      if(op==='accept-open'){if(!s.pending)throw Error('No pending open');s.previous=s.current;s.current=s.pending;s.pending=null;return {token:'1'};}
      if(op==='finalize-open'){s.previous=null;return {token:payload.token,dirtyRevision:'1'};}
      if(op==='clean-open')return {token:payload.token,dirtyRevision:payload.dirtyRevision,clean:true};
      if(op==='rollback-open'){s.current=s.previous;s.previous=null;s.rollbacks++;return {};}
      throw Error(`Unexpected native operation: ${op}`);
    },
  };
});
const mesh=Buffer.from('solid sample\nfacet normal 0 0 1\nouter loop\nvertex 0 0 0\nvertex 10 0 0\nvertex 0 10 0\nendloop\nendfacet\nendsolid sample\n');
const reference={schemaVersion:1,format:'stl',name:'old-reference.stl',unit:'mm',data:mesh.toString('base64'),sha256:createHash('sha256').update(mesh).digest('hex'),byteLength:mesh.length,triangleCount:1};
async function save(){await page.locator('#saveButton').click();await page.waitForFunction(()=>document.querySelector('#notice')?.textContent.includes('Project saved to'));return page.evaluate(()=>structuredClone(window.__nativeTest.current));}
async function open(){await page.locator('#importButton').click();}
try {
  await page.goto(base);await page.waitForFunction(()=>document.querySelector('#solverStatus')?.textContent.includes('MBDyn ready'));
  await page.locator('#examplesButton').click();await page.locator('.example-card').filter({has:page.getByRole('heading',{name:'Authored rigid pendulum',exact:true})}).getByRole('button',{name:/Open example/}).click();
  await page.locator('#stepButton').click();await page.locator('#stepFile').setInputFiles('examples/step-pendulum/pendulum.step');await page.waitForFunction(()=>document.querySelector('#stepDetail')?.textContent.includes('1 STEP files'),null,{timeout:180000});
  await page.locator('#stepBody').selectOption('upper_link');await page.locator('#stepBind').click();await page.locator('#stepClose').click();
  const response=page.waitForResponse(r=>r.url().endsWith('/api/run')&&r.request().method()==='POST',{timeout:120000});await page.locator('#runButton').click();const result=await (await response).json();assert(result.ok,JSON.stringify(result));
  await page.waitForFunction(()=>document.querySelector('#notice')?.textContent.includes('MBDyn completed successfully'));
  await page.locator('#timeSlider').fill('30');await page.locator('#timeSlider').dispatchEvent('input');
  const initial=await save();initial.project.assets.reference=reference;
  await page.evaluate(value=>{window.__nativeTest.candidate={path:'C:/test/reference-project.mbdyn-studio',project:value};},initial.project);
  await open();await page.waitForFunction(()=>document.querySelector('#notice')?.textContent.includes('Project opened'));
  assert.match(await page.locator('#referenceStatus').textContent(),/old-reference.stl/);
  await page.evaluate(async()=>{
    const {MechanismView}=await import('/viewport.js');
    for(const name of ['setModel','setReference','setStepAsset','setSample']){
      const original=MechanismView.prototype[name];
      MechanismView.prototype[name]=function(...args){window.__testView=this;const value=original.apply(this,args);if(window.__throwMethod===name){window.__throwMethod=null;throw Error(`Injected ${name} failure`);}return value;};
    }
  });
  await page.locator('#graph-body-upper_link-mass').fill('1.7');await page.locator('#graph-body-upper_link-mass').press('Tab');
  await page.waitForFunction(()=>window.__testView?.referenceMesh);
  await page.evaluate(()=>{window.__testView.controls.enableDamping=false;window.__oldReference=window.__testView.referenceMesh.geometry;window.__oldDisposals=0;window.__oldReference.addEventListener('dispose',()=>window.__oldDisposals++);});
  const baseline=await save();
  const uiBefore={frame:await page.locator('#timeOutput').textContent(),undo:await page.locator('#undoButton').isDisabled(),redo:await page.locator('#redoButton').isDisabled(),camera:await page.evaluate(()=>({position:window.__testView.camera.position.toArray(),target:window.__testView.controls.target.toArray()}))};
  const candidate=structuredClone(baseline.project);candidate.model.name='Candidate after rollback';candidate.model.bodies[0].mass=1.4;candidate.result.model=structuredClone(candidate.model);candidate.assets.reference.name='new-reference.stl';
  await page.evaluate(value=>{window.__nativeTest.candidate={path:'C:/test/candidate.mbdyn-studio',project:value};},candidate);
  for(const method of ['setModel','setReference','setStepAsset','setSample']){
    await page.evaluate(method=>{window.__throwMethod=method;},method);
    await open();await page.waitForFunction(name=>document.querySelector('#notice')?.textContent.includes(`Injected ${name} failure`),method,{timeout:180000});
    assert.match(await page.locator('#notice').textContent(),new RegExp(`Injected ${method} failure`));
    assert.equal(await page.locator('#graph-body-upper_link-mass').inputValue(),'1.7',method);
    assert.match(await page.locator('#referenceStatus').textContent(),/old-reference.stl/);assert.match(await page.locator('#stepStatus').textContent(),/1 attached/);
    assert.equal(await page.locator('#timeOutput').textContent(),uiBefore.frame);assert.equal(await page.locator('#undoButton').isDisabled(),uiBefore.undo);assert.equal(await page.locator('#redoButton').isDisabled(),uiBefore.redo);
    const native=await page.evaluate(()=>({path:window.__nativeTest.current.path,rollbacks:window.__nativeTest.rollbacks,disposed:window.__oldDisposals,camera:{position:window.__testView.camera.position.toArray(),target:window.__testView.controls.target.toArray()}}));
    assert.equal(native.path,baseline.path);assert.equal(native.disposed,0,`previous reference disposed during ${method} rollback`);assert.deepEqual(native.camera,uiBefore.camera);
    const saved=await save();assert.deepEqual(saved.project.model,baseline.project.model);assert.deepEqual(saved.project.assets,baseline.project.assets);assert.deepEqual(saved.project.result,baseline.project.result);assert.equal(saved.project.view.frame,baseline.project.view.frame);
  }
  await open();await page.waitForFunction(()=>document.querySelector('#notice')?.textContent.includes('Project opened'),null,{timeout:180000});
  assert.equal(await page.locator('#graph-body-upper_link-mass').inputValue(),'1.4');assert.equal(await page.evaluate(()=>window.__oldDisposals),1);
  assert.equal(await page.evaluate(()=>window.__nativeTest.current.path),'C:/test/candidate.mbdyn-studio');assert.deepEqual(errors,[]);
  const web=await browser.newPage({viewport:{width:1440,height:960},acceptDownloads:true});
  try {
    web.on('dialog',dialog=>dialog.accept());web.on('pageerror',e=>errors.push(e.message));await web.route('**/api/tour-preference',route=>route.fulfill({json:{enabled:false}}));
    await web.goto(base);await web.waitForFunction(()=>document.querySelector('#solverStatus')?.textContent.includes('MBDyn ready'));
    const importProject=async value=>web.locator('#projectFile').setInputFiles({name:'project.mbdyn-studio',mimeType:'application/json',buffer:Buffer.from(JSON.stringify(value))});
    await importProject(baseline.project);await web.waitForFunction(()=>document.querySelector('#notice')?.textContent.includes('Project imported and validated'),null,{timeout:180000});
    await web.evaluate(async()=>{const {MechanismView}=await import('/viewport.js');for(const name of ['setModel','setReference','setStepAsset','setSample']){const original=MechanismView.prototype[name];MechanismView.prototype[name]=function(...args){window.__testView=this;const result=original.apply(this,args);if(window.__throwMethod===name){window.__throwMethod=null;throw Error(`Injected ${name} failure`);}return result;};}});
    await web.locator('#graph-body-upper_link-mass').fill('1.8');await web.locator('#graph-body-upper_link-mass').press('Tab');await web.waitForFunction(()=>window.__testView?.referenceMesh);
    await web.evaluate(()=>{window.__oldReference=window.__testView.referenceMesh.geometry;window.__oldDisposals=0;window.__oldReference.addEventListener('dispose',()=>window.__oldDisposals++);});
    const webSave=async()=>{const event=web.waitForEvent('download');await web.locator('#saveButton').click();return JSON.parse(await readFile(await (await event).path(),'utf8'));};
    const webBaseline=await webSave(), webUndo=await web.locator('#undoButton').isDisabled(), webRedo=await web.locator('#redoButton').isDisabled(), webFrame=await web.locator('#timeOutput').textContent();
    const webCandidate=structuredClone(webBaseline);webCandidate.model.name='Browser candidate';webCandidate.model.bodies[0].mass=1.9;webCandidate.result.model=structuredClone(webCandidate.model);webCandidate.assets.reference.name='browser-new.stl';
    for(const method of ['setModel','setReference','setStepAsset','setSample']) {
      await web.evaluate(name=>{window.__throwMethod=name;},method);await importProject(webCandidate);
      await web.waitForFunction(name=>document.querySelector('#notice')?.textContent.includes(`Injected ${name} failure`),method,{timeout:180000});
      assert.equal(await web.locator('#graph-body-upper_link-mass').inputValue(),'1.8',method);assert.match(await web.locator('#referenceStatus').textContent(),/old-reference.stl/);assert.match(await web.locator('#stepStatus').textContent(),/1 attached/);
      assert.equal(await web.locator('#timeOutput').textContent(),webFrame);assert.equal(await web.locator('#undoButton').isDisabled(),webUndo);assert.equal(await web.locator('#redoButton').isDisabled(),webRedo);assert.equal(await web.evaluate(()=>window.__oldDisposals),0);
      const saved=await webSave();assert.deepEqual(saved.model,webBaseline.model);assert.deepEqual(saved.assets,webBaseline.assets);assert.deepEqual(saved.result,webBaseline.result);
    }
  } finally {await web.close();}
  assert.deepEqual(errors,[]);
  console.log('Native open and browser import rollback preserve model, STEP, reference, result and history across four injected viewer failures; native save identity and camera also retained');
}catch(e){console.error(e);process.exitCode=1;await page.screenshot({path:'tests/evidence/project-open-rollback-failure.png',fullPage:true}).catch(()=>{});}finally{await browser.close();}
