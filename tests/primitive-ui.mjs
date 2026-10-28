import assert from 'node:assert/strict';
import {chromium} from 'playwright';
import {readFile,writeFile} from 'node:fs/promises';
import {createHash} from 'node:crypto';
const base=process.env.MBDYN_STUDIO_URL||'http://127.0.0.1:8768';
const browser=await chromium.launch({headless:true,args:['--enable-unsafe-swiftshader']}),page=await browser.newPage({viewport:{width:1440,height:960},acceptDownloads:true}),errors=[];
page.on('pageerror',e=>errors.push(e.message));
try{
 await page.request.post(base+'/api/tour-preference',{data:{enabled:false}});await page.goto(base);await page.waitForFunction(()=>document.querySelector('#solverStatus')?.textContent.includes('MBDyn ready'));
 await page.locator('#stepButton').click();await page.locator('#stepPendulum').click();await page.waitForFunction(()=>document.querySelector('#notice')?.textContent.includes('Matching STEP solid and rigid pendulum loaded'),null,{timeout:60000});
 await page.getByText('Calculate mass and inertia from a uniform solid').click();
 await page.getByLabel('Density (kg/m³)').fill('1200');await page.getByLabel('Width X (m)').fill('.03');await page.getByLabel('Width Y (m)').fill('.03');await page.getByLabel('Length Z (m)').fill('1');
 await page.getByRole('button',{name:'Create STEP solid and apply mass'}).click();
 await page.waitForFunction(()=>document.querySelector('#notice')?.textContent.includes('Created and attached brick STEP solid'),null,{timeout:90000});
 assert.match(await page.locator('#stepStatus').textContent(),/2 attached/);assert(Math.abs(Number(await page.locator('#graph-body-upper_link-mass').inputValue())-1.08)<1e-10);
 const down=page.waitForEvent('download');await page.locator('#saveButton').click();const file=await down;await file.saveAs('tests/evidence/generated-solid-project.mbdyn-studio');const project=JSON.parse(await readFile('tests/evidence/generated-solid-project.mbdyn-studio','utf8'));
 assert.equal(project.assets.step.files.length,2);assert.equal(Object.keys(project.assets.step.bindings).length,2);assert.equal(project.model.bodies[0].mass,1.08);
 await page.locator('#stepButton').click();await page.locator('#stepPart').selectOption('1:part-1');const sourceEvent=page.waitForEvent('download');await page.locator('#stepExport').click();const source=await sourceEvent;await source.saveAs('tests/evidence/generated-solid.step');assert.equal(createHash('sha256').update(await readFile('tests/evidence/generated-solid.step')).digest('hex'),project.assets.step.files[1].sha256);await page.locator('#stepClose').click();
 await page.locator('#undoButton').click();assert.equal(await page.locator('#graph-body-upper_link-mass').inputValue(),'1.2');assert.match(await page.locator('#stepStatus').textContent(),/1 attached/);
 await page.locator('#redoButton').click();assert.match(await page.locator('#stepStatus').textContent(),/2 attached/);
 const ev=page.waitForResponse(r=>r.url().endsWith('/api/run')&&r.request().method()==='POST',{timeout:120000});await page.locator('#runButton').click();const result=await (await ev).json();assert(result.ok,JSON.stringify(result));assert.equal(result.model.bodies[0].mass,1.08);
 await page.waitForFunction(()=>document.querySelector('#notice')?.textContent.includes('MBDyn completed successfully'));page.on('dialog', dialog=>dialog.accept());await page.locator('#projectFile').setInputFiles('tests/evidence/generated-solid-project.mbdyn-studio');await page.waitForFunction(()=>document.querySelector('#notice')?.textContent.includes('Project imported and validated'),null,{timeout:90000});assert.match(await page.locator('#stepStatus').textContent(),/2 attached/);assert.deepEqual(errors,[]);
 await writeFile('tests/evidence/primitive-ui-verification.json',JSON.stringify({ok:true,runId:result.runId,checks:['generated STEP solid','preserved previous solid','mass applied','undo and redo','real solve','save and reopen']}));console.log('Primitive STEP UI workflow passed');
}catch(e){console.error(e);process.exitCode=1;await page.screenshot({path:'tests/evidence/primitive-ui-failure.png',fullPage:true}).catch(()=>{});}finally{await browser.close();}
