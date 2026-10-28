import assert from 'node:assert/strict';
import {chromium} from 'playwright';
import {mkdir,readFile} from 'node:fs/promises';
const base=process.env.MBDYN_STUDIO_URL||'http://127.0.0.1:8778';
const browser=await chromium.launch({headless:true,args:['--enable-unsafe-swiftshader']});
const page=await browser.newPage({viewport:{width:1440,height:1200},acceptDownloads:true}),errors=[];
page.on('pageerror',e=>errors.push(e.message));page.on('dialog',d=>d.accept());await page.route('**/api/tour-preference',r=>r.fulfill({json:{enabled:false}}));
async function configure(){await page.getByText('Calculate mass and inertia from a uniform solid').click();await page.getByLabel('Solid shape').selectOption('polygon-extrusion');await page.getByLabel('Density (kg/m³)').fill('1000');await page.getByLabel('Length Z (m)').fill('.4');}
try {
 await page.goto(base);await page.waitForFunction(()=>document.querySelector('#solverStatus')?.textContent.includes('MBDyn ready'));
 await page.locator('#examplesButton').click();await page.locator('.example-card').filter({has:page.getByRole('heading',{name:'3D spherical pendulum',exact:true})}).getByRole('button',{name:/Open example/}).click();await configure();
 const vertices=page.getByLabel('Profile vertices x,y (m), one per line');await vertices.fill('0,0\n1,1\n0,1\n1,0');await page.getByRole('button',{name:'Create STEP solid and apply mass'}).click();await page.waitForFunction(()=>document.querySelector('#notice')?.textContent.includes('must not intersect'));
 await vertices.fill('0,0\n0.3,0\n0.3,0.1\n0.1,0.1\n0.1,0.3\n0,0.3');await page.getByRole('button',{name:'Create STEP solid and apply mass'}).click();await page.waitForFunction(()=>document.querySelector('#notice')?.textContent.includes('Created and attached polygon-extrusion STEP solid'),null,{timeout:120000});
 assert(Math.abs(Number(await page.locator('#spatial-body-bob-mass').inputValue())-20)<1e-8);assert(Math.abs(Number(await page.locator('#spatial-body-bob-inertia-xy').inputValue())-.072)<1e-8);assert.match(await page.locator('#stepStatus').textContent(),/1 attached/);
 const response=page.waitForResponse(r=>r.url().endsWith('/api/run')&&r.request().method()==='POST',{timeout:120000});await page.locator('#runButton').click();const result=await (await response).json();assert(result.ok,JSON.stringify(result));await page.waitForFunction(()=>document.querySelector('#notice')?.textContent.includes('MBDyn completed successfully'));
 await configure();await page.getByRole('button',{name:'Create STEP solid and apply mass'}).scrollIntoViewIfNeeded();if(process.env.MBDYN_SKIP_DOC_SCREENSHOTS!=='1'){await mkdir('docs/images',{recursive:true});await page.screenshot({path:'docs/images/polygon-extrusion.png'});}
 const download=page.waitForEvent('download');await page.locator('#saveButton').click();const file=await download;const project=JSON.parse(await readFile(await file.path(),'utf8'));assert.equal(project.result.source,'MBDyn');assert.match(project.assets.step.files[0].name,/polygon-extrusion\.step$/);assert(Math.abs(project.model.bodies[0].inertia.xy-.072)<1e-8);
 await page.locator('#projectFile').setInputFiles(await file.path());await page.waitForFunction(()=>document.querySelector('#notice')?.textContent.includes('Project imported and validated'),null,{timeout:120000});assert.match(await page.locator('#stepStatus').textContent(),/1 attached/);assert.deepEqual(errors,[]);console.log('Concave profile STEP extrusion, invalid profile rejection, MBDyn, and save/reopen passed.');
} finally {await browser.close();}
