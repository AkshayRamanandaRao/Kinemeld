import assert from 'node:assert/strict';
import {chromium} from 'playwright';
import {mkdir,readFile} from 'node:fs/promises';

const base=process.env.MBDYN_STUDIO_URL||'http://127.0.0.1:18991';
const browser=await chromium.launch({headless:true,args:['--enable-unsafe-swiftshader']});
const page=await browser.newPage({viewport:{width:1440,height:1200},acceptDownloads:true}),errors=[];
page.on('pageerror',e=>errors.push(e.message));page.on('dialog',d=>d.accept());await page.route('**/api/tour-preference',r=>r.fulfill({json:{enabled:false}}));
try {
 await page.goto(base);await page.waitForFunction(()=>document.querySelector('#solverStatus')?.textContent.includes('MBDyn ready'));
 const project=JSON.parse(await readFile('examples/prescribed-wheel-bump/wheel-bump.mbdyn-studio','utf8'));project.model.parameters.gravity.z=-9.81;
 const upload=async project=>{await page.evaluate(()=>{document.querySelector('#notice').textContent='Waiting for import';});await page.locator('#projectFile').setInputFiles({name:'reaction-study.mbdyn-studio',mimeType:'application/json',buffer:Buffer.from(JSON.stringify(project))});};
 await upload(project);await page.waitForFunction(()=>document.querySelector('#notice')?.textContent.includes('Project imported and validated'),null,{timeout:180000});
 const response=page.waitForResponse(r=>r.url().endsWith('/api/run')&&r.request().method()==='POST',{timeout:120000});await page.locator('#runButton').click();const result=await (await response).json();assert(result.ok,JSON.stringify(result));await page.waitForFunction(()=>document.querySelector('#notice')?.textContent.includes('MBDyn completed successfully'));
 assert.match(result.files.jointOutput,/\/result\.jnt$/);const native=await page.request.get(base+result.files.jointOutput);assert(native.ok());assert((await native.body()).length>100);
 const index=250,sample=result.samples[index],reaction=sample.jointReactions.find(v=>v.id==='fixture'),totalMass=project.model.bodies.reduce((sum,b)=>sum+b.mass,0);assert(reaction);assert(Math.abs(reaction.force.z-totalMass*9.81)<.001,JSON.stringify(reaction));
 await page.locator('#signalSelect').selectOption({label:'Joint reaction force on B · world X / Y / Z'});await page.locator('#jointSelect').selectOption('fixture');await page.locator('#timeSlider').fill(String(index));await page.locator('#timeSlider').dispatchEvent('input');assert.match(await page.locator('#plot').getAttribute('aria-label'),/Joint reaction force on B/);
 if(process.env.MBDYN_SKIP_DOC_SCREENSHOTS!=='1'){await mkdir('docs/images',{recursive:true});await page.screenshot({path:'docs/images/joint-reactions.png'});}
 const csvEvent=page.waitForEvent('download');await page.locator('#csvButton').click();const csv=await csvEvent,lines=(await readFile(await csv.path(),'utf8')).trim().split(/\r?\n/),columns=lines[2].split(','),column=columns.indexOf('jointReaction:fixture:force_z_N'),timeColumn=columns.indexOf('time_s');assert(column>=0&&timeColumn>=0,columns.join(','));
 const row=lines.slice(3).map(line=>line.split(',')).find(values=>Math.abs(Number(values[timeColumn])-sample.time)<1e-10);assert(row);assert(Math.abs(Number(row[column])-reaction.force.z)<1e-8);
 const saveEvent=page.waitForEvent('download');await page.locator('#saveButton').click();const saved=JSON.parse(await readFile(await (await saveEvent).path(),'utf8'));assert.equal(saved.result.samples[index].jointReactions.length,2);
 await upload(saved);await page.waitForFunction(()=>document.querySelector('#notice')?.textContent.includes('Project imported and validated'),null,{timeout:180000});await page.locator('#signalSelect').selectOption({label:'Joint reaction moment at B anchor · world X / Y / Z'});await page.locator('#jointSelect').selectOption('fixture');assert.match(await page.locator('#plot').getAttribute('aria-label'),/Joint reaction moment at B anchor/);
 const corrupt=structuredClone(saved);corrupt.result.samples[1].jointReactions[0].force.x='invalid';await upload(corrupt);await page.waitForFunction(()=>document.querySelector('#notice')?.textContent.includes('saved result is incomplete or unsupported'),null,{timeout:180000});
 const legacy=structuredClone(saved);for(const s of legacy.result.samples)delete s.jointReactions;delete legacy.result.reactionInfo;await upload(legacy);await page.waitForFunction(()=>document.querySelector('#notice')?.textContent.includes('Project imported and validated'),null,{timeout:180000});assert.equal(await page.locator('#signalSelect option').filter({hasText:'Joint reaction force on B'}).count(),0);
 assert.deepEqual(errors,[]);console.log('Joint reactions: STEP, real solver, independent force, CSV, save/reopen, malformed and legacy results passed.');
}finally{await browser.close();}
