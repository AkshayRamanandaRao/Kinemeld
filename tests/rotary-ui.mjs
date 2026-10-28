import assert from 'node:assert/strict';
import {chromium} from 'playwright';
import {readFile,writeFile} from 'node:fs/promises';
const base=process.env.MBDYN_STUDIO_URL||'http://127.0.0.1:8768';
const browser=await chromium.launch({headless:true,args:['--enable-unsafe-swiftshader']});
const page=await browser.newPage({viewport:{width:1440,height:960},acceptDownloads:true}),errors=[];
page.on('pageerror',e=>errors.push(e.message));
try {
 await page.request.post(base+'/api/tour-preference',{data:{enabled:false}});
 await page.goto(base);await page.waitForFunction(()=>document.querySelector('#solverStatus')?.textContent.includes('MBDyn ready'));
 await page.locator('#examplesButton').click();await page.locator('.example-card').filter({has:page.getByRole('heading',{name:'Authored rigid pendulum',exact:true})}).getByRole('button',{name:/Open example/}).click();
 await page.getByText('Calculate mass and inertia from a uniform solid').click();
 await page.getByRole('button',{name:'Create STEP solid and apply mass'}).click();
 await page.waitForFunction(()=>document.querySelector('#notice')?.textContent.includes('Created and attached brick STEP solid'),null,{timeout:90000});
 await page.getByRole('button',{name:'Add rotational spring / damper'}).click();
 await page.locator('#graph-rotary-rotary1-stiffness').fill('20');await page.locator('#graph-rotary-rotary1-stiffness').press('Tab');
 await page.getByRole('button',{name:'Add sinusoidal joint torque'}).click();
 await page.locator('#graph-torque-torque1-amplitude').fill('2');await page.locator('#graph-torque-torque1-amplitude').press('Tab');
 await page.waitForFunction(()=>document.querySelector('#validationBadge')?.textContent==='Ready');
 const response=page.waitForResponse(r=>r.url().endsWith('/api/run')&&r.request().method()==='POST',{timeout:120000});await page.locator('#runButton').click();const result=await (await response).json();assert(result.ok,JSON.stringify(result));
 assert.equal(result.model.rotationalElements[0].stiffness,20);assert.equal(result.model.jointTorques[0].amplitude,2);
 assert(result.samples.every(s=>Number.isFinite(s.rotationalStates[0].torque)&&Number.isFinite(s.actuationStates[0].torque)&&Number.isFinite(s.actuationWork)));
 await page.waitForFunction(()=>document.querySelector('#notice')?.textContent.includes('MBDyn completed successfully'));
 for(const label of ['Rotational spring torque','Actuation torque','Actuation power','Actuation work (reconstructed)']){await page.locator('#signalSelect').selectOption({label});assert.equal(await page.locator('#signalTitle').textContent(),label);}
 const download=page.waitForEvent('download');await page.locator('#saveButton').click();await (await download).saveAs('tests/evidence/rotary-project.mbdyn-studio');
 const project=JSON.parse(await readFile('tests/evidence/rotary-project.mbdyn-studio','utf8'));assert(project.assets.step);assert(project.result.samples[0].rotationalStates);
 await page.locator('#projectFile').setInputFiles('tests/evidence/rotary-project.mbdyn-studio');await page.waitForFunction(()=>document.querySelector('#notice')?.textContent.includes('Project imported and validated'),null,{timeout:180000});
 assert.match(await page.locator('#stepStatus').textContent(),/1 attached/);await page.locator('#signalSelect').selectOption({label:'Rotational spring torque'});
 assert.deepEqual(errors,[]);await writeFile('tests/evidence/rotary-ui-verification.json',JSON.stringify({ok:true,runId:result.runId,checks:['STEP body','rotational spring editing','sinusoidal torque editing','real MBDyn','plots','saved result reopen']}));console.log('Rotational spring and torque UI workflow passed');
}catch(e){console.error(e);process.exitCode=1;await page.screenshot({path:'tests/evidence/rotary-ui-failure.png',fullPage:true}).catch(()=>{});}finally{await browser.close();}
