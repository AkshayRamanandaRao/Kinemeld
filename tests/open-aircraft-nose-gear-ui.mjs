import './workspace-shim.mjs';
import assert from 'node:assert/strict';
import {chromium} from 'playwright';
import {mkdir,readFile} from 'node:fs/promises';
import {createHash} from 'node:crypto';

const base=process.env.MBDYN_STUDIO_URL||'http://127.0.0.1:18892';
const browser=await chromium.launch({headless:true,args:['--enable-unsafe-swiftshader']});
const page=await browser.newPage({viewport:{width:1440,height:1100},acceptDownloads:true}),errors=[];
page.on('pageerror',e=>errors.push(e.message));page.on('dialog',d=>d.accept());await page.route('**/api/tour-preference',r=>r.fulfill({json:{enabled:false}}));
try{
 await page.goto(base);const catalog=await (await page.request.get(base+'/api/examples')).json();const model=structuredClone(catalog.examples.find(e=>e.id==='spatial-revolute').model);model.name='Aircraft nose gear · CAD inspection only';model.bodies[0].name='Unattached placeholder';
 await page.locator('#projectFile').setInputFiles({name:'cad-inspection.mbdyn-studio',mimeType:'application/json',buffer:Buffer.from(JSON.stringify({format:'mbdyn-studio/1',model}))});await page.waitForFunction(()=>document.querySelector('#notice')?.textContent.includes('Project imported and validated'));
 await page.locator('#stepButton').click();await page.locator('#stepFile').setInputFiles('examples/open-aircraft-nose-gear/source-assembly.step');
 await page.waitForFunction(()=>document.querySelector('#stepDetail')?.textContent.includes('1 STEP files'),null,{timeout:180000});
 assert.equal(await page.locator('#stepPart option').count(),11);assert.match(await page.locator('#stepDetail').textContent(),/0 attached/);
 const labels=await page.locator('#stepPart option').allTextContents();assert.equal(labels[0],'Piston · NAUO1');assert.equal(labels[2],'Strut · NAUO3');assert.equal(labels[9],'Wheel · NAUO10');assert.equal(labels[10],'Wheel · NAUO11');
 if(process.env.MBDYN_SKIP_DOC_SCREENSHOTS!=='1'){await mkdir('docs/images',{recursive:true});await page.screenshot({path:'docs/images/step-product-names.png'});}
 await page.locator('#stepClose').click();await page.locator('#resetViewButton').click();await page.waitForTimeout(300);
 if(process.env.MBDYN_SKIP_DOC_SCREENSHOTS!=='1'){await mkdir('docs/images',{recursive:true});await page.screenshot({path:'docs/images/open-aircraft-nose-gear.png'});}
 const event=page.waitForEvent('download');await page.locator('#saveButton').click();const file=await event;const project=JSON.parse(await readFile(await file.path(),'utf8'));const asset=project.assets.step.files[0];
 assert.equal(createHash('sha256').update(Buffer.from(asset.data,'base64')).digest('hex'),'b53205b3356f9b98b0edf6d2ba4f8b04f46cc61607cad263857192c1aeb7a575');assert.equal(Object.keys(project.assets.step.bindings).length,0);
 await page.locator('#projectFile').setInputFiles(await file.path());await page.waitForFunction(()=>document.querySelector('#notice')?.textContent.includes('Project imported and validated'),null,{timeout:180000});await page.locator('#stepButton').click();assert.equal(await page.locator('#stepPart option').count(),11);assert.equal(await page.locator('#stepPart option').first().textContent(),'Piston · NAUO1');assert.deepEqual(errors,[]);console.log('Original aircraft STEP assembly: named CAD occurrences, untouched bytes and project save/reopen passed. CAD only; no dynamics run.');
}finally{await browser.close();}
