import './workspace-shim.mjs';
import assert from 'node:assert/strict';
import {spawn} from 'node:child_process';
import {createInterface} from 'node:readline';
import {once} from 'node:events';
import {mkdir} from 'node:fs/promises';
import {chromium} from 'playwright';

const service=spawn('python',['tests/spatial-agent-server.py'],{cwd:process.cwd(),windowsHide:true,stdio:['ignore','pipe','pipe']});
let diagnostics='';service.stderr.on('data',chunk=>{diagnostics+=chunk.toString();});const lines=createInterface({input:service.stdout});let browser;
try{
 let timeout;const deadline=new Promise((_,reject)=>{timeout=setTimeout(()=>reject(Error('Owned test server did not start')),15000);});let line;
 try{line=await Promise.race([once(lines,'line').then(([value])=>value),once(service,'exit').then(()=>{throw Error(`Owned test server exited: ${diagnostics}`);}),deadline]);}finally{clearTimeout(timeout);}
 browser=await chromium.launch({headless:true,args:['--enable-unsafe-swiftshader']});const page=await browser.newPage({viewport:{width:1440,height:1200}}),errors=[],runs=[];
 page.on('pageerror',error=>errors.push(error.message));await page.route('**/api/tour-preference',route=>route.fulfill({json:{enabled:false}}));await page.route('**/api/run',route=>{runs.push(route.request().postData());return route.fulfill({status:503,json:{ok:false,error:'Unexpected solver run'}});});
 await page.goto(`http://127.0.0.1:${JSON.parse(line).port}`);await page.waitForFunction(()=>document.querySelector('#solverStatus')?.textContent.includes('MBDyn ready'));
 await page.locator('#projectFile').setInputFiles('examples/oleo-strut/wheel-oleo.mbdyn-studio');await page.waitForFunction(()=>document.querySelector('#notice')?.textContent.includes('Project imported and validated'),null,{timeout:180000});
 await page.locator('[data-entity="force-oleo"]').click();await page.locator('#agentButton').click();await page.waitForFunction(()=>!document.querySelector('#agentSend').disabled);
 await page.locator('#agentInput').fill('Oleo: set the reference gas pressure to 1.2 MPa. Do not run.');await page.locator('#agentSend').click();const review=page.locator('.agent-review').last();await review.waitFor();
 const snapshots=(await review.locator('pre').textContent()).split('\n\nPROPOSED MODEL\n'),before=JSON.parse(snapshots[0].replace(/^CURRENT MODEL\n/,'')),after=JSON.parse(snapshots[1]);
 assert.equal(before.forces.find(f=>f.id==='oleo').pressure,1000000);assert.equal(after.forces.find(f=>f.id==='oleo').pressure,1200000);assert.equal(runs.length,0);
 await review.locator('pre').evaluate(pre=>{const index=pre.textContent.indexOf('"pressure"',pre.textContent.indexOf('PROPOSED MODEL'));const count=pre.textContent.slice(0,index).split('\n').length;pre.scrollTop=(count-2)*parseFloat(getComputedStyle(pre).lineHeight);});
 if(process.env.MBDYN_SKIP_DOC_SCREENSHOTS!=='1'){await mkdir('docs/images',{recursive:true});await page.screenshot({path:'docs/images/spatial-ai-oleo.png'});}
 await review.getByRole('button',{name:'Apply proposal'}).click();await page.waitForFunction(()=>document.querySelector('#agentMessages')?.textContent.includes('Use Undo to restore the previous model.'));await page.locator('[data-entity="force-oleo"]').click();await page.waitForFunction(()=>Number(document.querySelector('#spatial-force-oleo-pressure')?.value)===1200000);
 assert.equal(runs.length,0);assert.deepEqual(errors,[]);console.log('AI oleo: controlled proposal, review, apply and no solver run passed.');
}finally{if(browser)await browser.close();service.kill();lines.close();}
