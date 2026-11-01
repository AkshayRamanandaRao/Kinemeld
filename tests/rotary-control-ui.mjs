/** Real browser and native MBDyn/controller processes; no desktop automation. */
import './workspace-shim.mjs';
import assert from 'node:assert/strict';
import {spawn} from 'node:child_process';
import {createInterface} from 'node:readline';
import {once} from 'node:events';
import {mkdir,readFile,writeFile} from 'node:fs/promises';
import {chromium} from 'playwright';

const binary=process.env.MBDYN_CONTROL_TEST_SOLVER||'verification/dependency-audit/ci-audit2-windows/solver/bin/mbdyn.exe';
const service=spawn('python',['tests/rotary-control-server.py',binary],{windowsHide:true,stdio:['ignore','pipe','pipe']});
const lines=createInterface({input:service.stdout});let diagnostics='',browser,page;
service.stderr.on('data',data=>diagnostics+=data);
const report={scope:'Actual browser, backend validators, native MBDyn and separate trusted Python feedback controller; no external AI or desktop automation.',checks:[],errors:[]};
const record=text=>{report.checks.push(text);console.log(text);};
try{
 let timer;const ready=await Promise.race([once(lines,'line').then(([line])=>JSON.parse(line)),once(service,'exit').then(()=>{throw Error(diagnostics);}),new Promise((_,reject)=>timer=setTimeout(()=>reject(Error('Owned servo server did not start')),15000))]).finally(()=>clearTimeout(timer));
 const base=`http://127.0.0.1:${ready.port}`;
 browser=await chromium.launch({headless:true,args:['--enable-unsafe-swiftshader']});page=await browser.newPage({viewport:{width:1540,height:1100},acceptDownloads:true});
 page.on('pageerror',error=>report.errors.push(error.message));page.on('dialog',dialog=>dialog.accept());
 await page.route('**/api/tour-preference',route=>route.fulfill({json:{enabled:false}}));
 await page.goto(base);await page.waitForFunction(()=>document.querySelector('#solverStatus')?.textContent.includes('MBDyn ready'));
 const open=async project=>{await page.locator('#projectFile').setInputFiles({name:'robot-servo.mbdyn-studio',mimeType:'application/json',buffer:Buffer.from(JSON.stringify(project))});await page.waitForFunction(name=>document.querySelector('#documentName')?.textContent===name&&document.querySelector('#notice')?.textContent.includes('Project imported and validated'),project.model.name);};
 const exported=async()=>{const pending=page.waitForEvent('download');await page.locator('#saveButton').click();const file=await pending;return JSON.parse(await readFile(await file.path(),'utf8'));};
 const change=async(id,value)=>{await page.locator(id).fill(String(value));await page.locator(id).blur();};
 await open({format:'mbdyn-studio/1',model:ready.model});await page.locator('[data-step="model"]').click();
 await page.locator('#modelTree [data-entity="torque-shoulderMotor"]').click();
 assert.match(await page.locator('#properties').textContent(),/separate local PD controller/i);
 await change('#spatial-torque-shoulderMotor-torqueLimit',1.5);await page.locator('#undoButton').click();assert.equal(await page.locator('#spatial-torque-shoulderMotor-torqueLimit').inputValue(),'2');await page.locator('#redoButton').click();assert.equal(await page.locator('#spatial-torque-shoulderMotor-torqueLimit').inputValue(),'1.5');
 const setup=await exported();assert.equal(setup.model.jointTorques[0].type,'servo');assert.equal(setup.model.jointTorques[0].torqueLimit,1.5);
 record('Servo gains, target ramp and torque limit edit through normal Undo/Redo and project save');
 const deck=await page.request.post(`${base}/api/deck`,{data:{model:setup.model}});assert.equal(deck.status(),422);assert.match((await deck.json()).error,/managed local peer/);
 await page.locator('[data-step="simulate"]').click();const response=page.waitForResponse(r=>r.url().endsWith('/api/run')&&r.request().method()==='POST',{timeout:120000});await page.locator('#runButton').click();const result=await(await response).json();assert(result.ok,result.error);await page.waitForFunction(()=>!document.querySelector('#runButton').disabled);
 assert.equal(result.coSimulation.actuatorCount,2);assert(result.coSimulation.exchangeCount>5000);assert.match(await page.locator('#controllerSummary').textContent(),/one-step/i);
 const traceLink=page.locator('#controllerSummary a').filter({hasText:/trace/i});const trace=await page.request.get(`${base}${await traceLink.getAttribute('href')}`);assert.equal(trace.status(),200);assert((await trace.text()).includes('"commandTorque"'));
 for(const label of ['Servo angle · measured / commanded','Servo speed · measured / commanded','Servo tracking error','Servo held torque','Servo saturation']){await page.locator('#signalSelect').selectOption({label});await page.waitForFunction(()=>document.querySelector('#plotStats')?.textContent.includes('Full resolution'));assert(!await page.locator('#forceSelect').isHidden());}
 await page.locator('#signalSelect').selectOption({label:'Servo angle · measured / commanded'});await page.locator('#forceSelect').selectOption('elbowMotor');
 const csv=await(await page.request.get(`${base}${result.files.csv}`)).text();assert.match(csv,/servo:elbowMotor:desiredAngle_rad/);assert.match(csv,/servo:shoulderMotor:saturated/);assert(csv.split('\n').length>10000);
 await mkdir('tests/evidence',{recursive:true});await page.screenshot({path:'tests/evidence/rotary-control-ui.png'});
 record('Managed Run solves two actuators with actual native feedback, inspectable trace and full-resolution servo plots/CSV');
 const saved=await exported();assert.equal(saved.result.coSimulation.exchangeCount,result.coSimulation.exchangeCount);assert(saved.result.csvText.includes('servo:elbowMotor:desiredAngle_rad'));
 await open(saved);await page.locator('[data-step="results"]').click();await page.waitForFunction(()=>!document.querySelector('#controllerSummary').hidden);await page.locator('#signalSelect').selectOption({label:'Servo tracking error'});await page.waitForFunction(()=>document.querySelector('#plotStats')?.textContent.includes('Full resolution'));
 await page.locator('[data-step="model"]').click();await page.locator('#modelTree [data-entity="torque-elbowMotor"]').click();await change('#spatial-torque-elbowMotor-targetAngleDeg',-40);await page.waitForFunction(()=>document.querySelector('#resultSource')?.textContent.includes('Stale'));assert(await page.locator('#playButton').isDisabled());
 record('Saved servo results and full CSV reopen; changing target angle invalidates the retained result');
 await page.locator('#undoButton').click();await page.getByRole('button',{name:'Remove joint torque',exact:true}).click();await page.getByRole('button',{name:'Add controlled rotary actuator',exact:true}).click();assert.equal(await page.locator('#spatial-torque-servo1-kp').inputValue(),'1');
 record('Existing servo removal and controlled actuator creation use the standard editor');
 const cancellable=structuredClone(ready.model);cancellable.name='Robot servo cancellation';cancellable.simulation={duration:2,step:.0001};await open({format:'mbdyn-studio/1',model:cancellable});await page.locator('[data-step="simulate"]').click();const cancellation=page.waitForResponse(r=>r.url().endsWith('/api/run')&&r.request().method()==='POST',{timeout:30000});await page.locator('#runButton').click();
 let active;const deadline=Date.now()+15000;while(Date.now()<deadline){active=await(await page.request.get(`${base}/fixture/active-controller`)).json();if(active.runId&&active.bytes>1000)break;await new Promise(resolve=>setTimeout(resolve,20));}report.activeRunId=active.runId;assert(active.runId&&active.bytes>1000);
 await page.locator('#cancelRunButton').click();const cancelled=await(await cancellation).json();report.cancelled=cancelled;assert.equal(cancelled.runId,active.runId);assert.equal(cancelled.cancelled,true);await page.waitForFunction(()=>document.querySelector('#statusText')?.textContent.includes('Run cancelled'));assert(await page.locator('#cancelRunButton').isHidden());const partial=await page.request.get(`${base}${cancelled.files.controllerTrace}`);assert.equal(partial.status(),200,JSON.stringify({files:cancelled.files,active:await(await page.request.get(`${base}/fixture/active-controller`)).json(),error:await partial.text()}));assert((await partial.text()).length>1000);
 record('GUI Cancel stops an actual native feedback run and retains its partial controller trace');
 assert.deepEqual(report.errors,[]);report.ok=true;report.actualMBDynRuns=2;console.log(JSON.stringify({ok:true,checks:report.checks.length,actualMBDynRuns:2}));
}catch(error){report.ok=false;report.failure=error.stack;if(page)await page.screenshot({path:'tests/evidence/rotary-control-ui-failure.png',fullPage:true}).catch(()=>{});console.error(error);process.exitCode=1;}
finally{await mkdir('tests/evidence',{recursive:true});await writeFile('tests/evidence/rotary-control-ui.json',JSON.stringify(report,null,2));await browser?.close();service.kill();}
