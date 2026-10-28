import assert from 'node:assert/strict';
import {chromium} from 'playwright';
import {mkdir,readFile} from 'node:fs/promises';
const base=process.env.MBDYN_STUDIO_URL||'http://127.0.0.1:8791';
const browser=await chromium.launch({headless:true,args:['--enable-unsafe-swiftshader']});
const page=await browser.newPage({viewport:{width:1440,height:1200},acceptDownloads:true}),errors=[];
page.on('pageerror',e=>errors.push(e.message));page.on('dialog',d=>d.accept());await page.route('**/api/tour-preference',r=>r.fulfill({json:{enabled:false}}));
try{
 await page.goto(base);await page.waitForFunction(()=>document.querySelector('#solverStatus')?.textContent.includes('MBDyn ready'));
 await page.locator('#projectFile').setInputFiles('examples/open-suspension/suspension.mbdyn-studio');await page.waitForFunction(()=>document.querySelector('#notice')?.textContent.includes('Project imported and validated'),null,{timeout:180000});assert.match(await page.locator('#stepStatus').textContent(),/5 attached/);
 const response=page.waitForResponse(r=>r.url().endsWith('/api/run')&&r.request().method()==='POST',{timeout:120000});await page.locator('#runButton').click();const result=await (await response).json();assert(result.ok,JSON.stringify(result));assert(result.metrics.maxConstraintError<1e-7);assert(result.samples.some(s=>Math.abs(s.nodes.find(n=>n.id==='wheel').z+.0875)>.01));
 await page.waitForFunction(()=>document.querySelector('#notice')?.textContent.includes('MBDyn completed successfully'));await page.locator('#nodeSelect').selectOption('wheel');await page.locator('#timeSlider').fill(String(Math.floor(result.samples.length/4)));await page.locator('#timeSlider').dispatchEvent('input');
 const canvas=page.locator('canvas').first(),box=await canvas.boundingBox();if(box){await page.mouse.move(box.x+box.width*.5,box.y+box.height*.5);await page.mouse.down();await page.mouse.move(box.x+box.width*.5+220,box.y+box.height*.5,{steps:15});await page.mouse.up();await page.waitForTimeout(300);}
 if(process.env.MBDYN_SKIP_DOC_SCREENSHOTS!=='1'){await mkdir('docs/images',{recursive:true});await page.screenshot({path:'docs/images/open-suspension.png'});}
 await page.locator('#wheelKinematicsButton').click();await page.locator('#wheelKinematicsBody').selectOption('wheel');await page.locator('#wheelKinematicsReference').selectOption('frame:vehicle');await page.locator('#wheelKinematics-axis-x').fill('1');await page.locator('#wheelKinematics-axis-y').fill('0');await page.locator('#wheelKinematicsCalculate').click();assert.match(await page.locator('#wheelKinematicsStatus').textContent(),/vertical travel .* m; camber .*°; toe .*°/);await page.locator('#wheelKinematicsSignal').selectOption('camber');assert.match(await page.locator('#wheelKinematicsPlot').getAttribute('aria-label'),/camber from/);
 if(process.env.MBDYN_SKIP_DOC_SCREENSHOTS!=='1')await page.screenshot({path:'docs/images/open-suspension-kinematics.png'});await page.getByRole('button',{name:'Close wheel kinematics'}).click();
 const download=page.waitForEvent('download');await page.locator('#saveButton').click();const file=await download;const saved=JSON.parse(await readFile(await file.path(),'utf8'));assert.equal(saved.result.source,'MBDyn');assert.equal(saved.model.joints.length,5);assert.equal(Object.keys(saved.assets.step.bindings).length,5);
 await page.locator('#projectFile').setInputFiles(await file.path());await page.waitForFunction(()=>document.querySelector('#notice')?.textContent.includes('Project imported and validated'),null,{timeout:180000});assert.match(await page.locator('#stepStatus').textContent(),/5 attached/);assert.deepEqual(errors,[]);console.log('Open CAD 5-part closed-loop suspension: real MBDyn and project save/reopen passed.');
}finally{await browser.close();}
