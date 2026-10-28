import assert from 'node:assert/strict';
import {chromium} from 'playwright';
import {mkdir,readFile} from 'node:fs/promises';
const base=process.env.MBDYN_STUDIO_URL||'http://127.0.0.1:8775';
const browser=await chromium.launch({headless:true,args:['--enable-unsafe-swiftshader']});
const page=await browser.newPage({viewport:{width:1440,height:1200},acceptDownloads:true}),errors=[];
page.on('pageerror',e=>errors.push(e.message));page.on('dialog',d=>d.accept());
await page.route('**/api/tour-preference',r=>r.fulfill({json:{enabled:false}}));
async function setShape(){await page.getByText('Calculate mass and inertia from a uniform solid').click();await page.getByLabel('Solid shape').selectOption('regular-extrusion');await page.getByLabel('Density (kg/m³)').fill('1000');await page.getByLabel('Circumradius (m)').fill('.1');await page.getByLabel('Length Z (m)').fill('.4');await page.getByLabel('Number of sides').fill('6');}
try{
 await page.goto(base);await page.waitForFunction(()=>document.querySelector('#solverStatus')?.textContent.includes('MBDyn ready'));
 await page.locator('#examplesButton').click();await page.locator('.example-card').filter({has:page.getByRole('heading',{name:'3D spherical pendulum',exact:true})}).getByRole('button',{name:/Open example/}).click();
 await setShape();await page.getByRole('button',{name:'Create STEP solid and apply mass'}).click();await page.waitForFunction(()=>document.querySelector('#notice')?.textContent.includes('Created and attached regular-extrusion STEP solid'),null,{timeout:120000});
 assert(Math.abs(Number(await page.locator('#spatial-body-bob-mass').inputValue())-6*Math.sqrt(3))<1e-8);assert.match(await page.locator('#stepStatus').textContent(),/1 attached/);
 const runEvent=page.waitForResponse(r=>r.url().endsWith('/api/run')&&r.request().method()==='POST',{timeout:120000});await page.locator('#runButton').click();const run=await (await runEvent).json();assert(run.ok,JSON.stringify(run));await page.waitForFunction(()=>document.querySelector('#notice')?.textContent.includes('MBDyn completed successfully'));
 await setShape();await page.getByRole('button',{name:'Create STEP solid and apply mass'}).scrollIntoViewIfNeeded();if(process.env.MBDYN_SKIP_DOC_SCREENSHOTS!=='1'){await mkdir('docs/images',{recursive:true});await page.screenshot({path:'docs/images/regular-extrusion.png'});}
 const download=page.waitForEvent('download');await page.locator('#saveButton').click();const file=await download;const saved=JSON.parse(await readFile(await file.path(),'utf8'));assert.equal(saved.result.source,'MBDyn');assert.equal(saved.assets.step.files.length,1);assert.match(saved.assets.step.files[0].name,/regular-extrusion\.step$/);assert(Math.abs(saved.model.bodies[0].mass-6*Math.sqrt(3))<1e-8);
 await page.locator('#projectFile').setInputFiles(await file.path());await page.waitForFunction(()=>document.querySelector('#notice')?.textContent.includes('Project imported and validated'),null,{timeout:120000});assert.match(await page.locator('#stepStatus').textContent(),/1 attached/);assert.deepEqual(errors,[]);
 console.log('Regular hexagonal STEP extrusion, analytic mass, real MBDyn run and save/reopen passed.');
}finally{await browser.close();}
