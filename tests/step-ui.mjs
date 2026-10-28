import assert from 'node:assert/strict';
import {chromium} from 'playwright';
import {mkdir,writeFile,readFile} from 'node:fs/promises';
const base=process.env.MBDYN_STUDIO_URL || 'http://127.0.0.1:8768';
const browser=await chromium.launch({headless:true,args:['--enable-unsafe-swiftshader']});
const page=await browser.newPage({viewport:{width:1440,height:960},acceptDownloads:true}), errors=[], report={checks:[],started:new Date().toISOString()};
page.on('pageerror',e=>errors.push(e.message));
try {
 await page.goto(base); await page.waitForFunction(()=>document.querySelector('#solverStatus')?.textContent.includes('MBDyn ready'));
 await page.locator('#examplesButton').click();
 await page.locator('.example-card').filter({has:page.getByRole('heading',{name:'Authored rigid pendulum',exact:true})}).getByRole('button',{name:/Open example/}).click();
 await page.evaluate(async()=>{const {MechanismView}=await import('/viewport.js'); for (const name of ['renderStep','setSample']) {const original=MechanismView.prototype[name];MechanismView.prototype[name]=function(...args){original.apply(this,args);if(this.stepView){this.stepView.group.updateMatrixWorld(true);window.__stepPose=[...this.stepView.partMeshes].map(([id,mesh])=>({id,visible:mesh.visible,matrix:mesh.matrixWorld.toArray()}));}};}});
 await page.locator('#stepButton').click(); await page.locator('#stepExample').click();
 await page.waitForFunction(()=>document.querySelector('#stepDetail')?.textContent.includes('12 STEP files'),null,{timeout:180000});
 assert((await page.locator('#stepPart option').count())>=12); assert.match(await page.locator('#stepDetail').textContent(),/0 attached/);
 await page.locator('#stepBody').selectOption('upper_link');await page.locator('#stepBind').click();
 assert.match(await page.locator('#stepDetail').textContent(),/1 attached/);await page.locator('#stepClose').click();
 await page.screenshot({path:'tests/evidence/step-suspension-assembly.png'});
 await page.locator('#undoButton').click();assert.match(await page.locator('#stepStatus').textContent(),/0 attached/);
 await page.locator('#redoButton').click();assert.match(await page.locator('#stepStatus').textContent(),/1 attached/);
 report.checks.push('STEP attachment Undo and Redo preserve the part binding');
 const download=page.waitForEvent('download'); await page.locator('#saveButton').click(); const file=await download;await file.saveAs('tests/evidence/step-project.mbdyn-studio');
 const project=JSON.parse(await readFile('tests/evidence/step-project.mbdyn-studio','utf8'));
 assert.equal(project.assets.step.files.length,12);assert.equal(Object.values(project.assets.step.bindings)[0].body,'upper_link');
 await page.locator('#stepButton').click(); await page.locator('#stepRemove').click();await page.locator('#stepClose').click();
 page.on('dialog', dialog=>dialog.accept());await page.locator('#projectFile').setInputFiles('tests/evidence/step-project.mbdyn-studio');
 await page.waitForFunction(()=>document.querySelector('#notice')?.textContent.includes('Project imported and validated'),null,{timeout:180000});
 assert.match(await page.locator('#stepStatus').textContent(),/1 attached/);
 report.checks.push('12 original STEP files converted locally; source files and body binding saved and reopened');
 const initial=await page.evaluate(()=>window.__stepPose); assert(initial?.length>=12);
 const response=page.waitForResponse(r=>r.url().endsWith('/api/run')&&r.request().method()==='POST',{timeout:120000});
 await page.locator('#runButton').click();const result=await (await response).json();assert(result.ok,JSON.stringify(result));
 await page.waitForFunction(()=>document.querySelector('#notice')?.textContent.includes('MBDyn completed successfully'));
 await page.locator('#timeSlider').fill(String(result.samples.length-1));await page.locator('#timeSlider').dispatchEvent('input');
 const last=await page.evaluate(()=>window.__stepPose);assert.notDeepEqual(last[0].matrix,initial[0].matrix);assert.deepEqual(last[1].matrix,initial[1].matrix);
 report.checks.push('Attached solid follows real MBDyn body rotation; an unbound solid stays fixed');
 assert.deepEqual(errors,[]); report.ok=true;
} catch(e) {report.ok=false;report.failure=e.stack;process.exitCode=1;console.error(e);await page.screenshot({path:'tests/evidence/step-ui-failure.png',fullPage:true}).catch(()=>{});}
finally {report.errors=errors;report.completed=new Date().toISOString();await mkdir('tests/evidence',{recursive:true});await writeFile('tests/evidence/step-ui-verification.json',JSON.stringify(report,null,2));await browser.close();}
