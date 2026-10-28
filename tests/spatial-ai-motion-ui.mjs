import assert from 'node:assert/strict';
import {spawn} from 'node:child_process';
import {createInterface} from 'node:readline';
import {once} from 'node:events';
import {mkdir} from 'node:fs/promises';
import {chromium} from 'playwright';

const service=spawn('python',['tests/spatial-agent-server.py'],{cwd:process.cwd(),windowsHide:true,stdio:['ignore','pipe','pipe']});
let diagnostics='';service.stderr.on('data',chunk=>{diagnostics+=chunk.toString();});
const lines=createInterface({input:service.stdout});let browser;
try{
 let timeout;const deadline=new Promise((_,reject)=>{timeout=setTimeout(()=>reject(Error('Owned test server did not start')),15000);});
 let line;try{line=await Promise.race([once(lines,'line').then(([value])=>value),once(service,'exit').then(()=>{throw Error(`Owned test server exited: ${diagnostics}`);}),deadline]);}finally{clearTimeout(timeout);}
 browser=await chromium.launch({headless:true,args:['--enable-unsafe-swiftshader']});
 const page=await browser.newPage({viewport:{width:1440,height:1200}}),errors=[],runs=[];
 page.on('pageerror',error=>errors.push(error.message));await page.route('**/api/tour-preference',route=>route.fulfill({json:{enabled:false}}));
 await page.route('**/api/run',route=>{runs.push(route.request().postData());return route.fulfill({status:503,json:{ok:false,error:'Unexpected solver run'}});});
 await page.goto(`http://127.0.0.1:${JSON.parse(line).port}`);await page.waitForFunction(()=>document.querySelector('#solverStatus')?.textContent.includes('MBDyn ready'));
 await page.locator('#projectFile').setInputFiles('examples/prescribed-wheel-bump/wheel-bump.mbdyn-studio');
 await page.waitForFunction(()=>document.querySelector('#notice')?.textContent.includes('Project imported and validated'),null,{timeout:180000});
 await page.locator('[data-entity="joint-fixture"]').click();await page.getByRole('button',{name:'Remove prescribed motion'}).click();
 await page.locator('#agentButton').click();await page.waitForFunction(()=>!document.querySelector('#agentSend').disabled);
 await page.locator('#agentInput').fill('Motion: prescribe the fixture slider with amplitude 0.025 m and frequency 1 Hz. Do not run.');await page.locator('#agentSend').click();
 const review=page.locator('.agent-review').last();await review.waitFor();const snapshots=(await review.locator('pre').textContent()).split('\n\nPROPOSED MODEL\n');
 const before=JSON.parse(snapshots[0].replace(/^CURRENT MODEL\n/,'')),after=JSON.parse(snapshots[1]);
 assert.equal(before.joints[0].motion,undefined);assert.deepEqual(after.joints[0].motion,{amplitude:.025,frequencyHz:1});assert.equal(runs.length,0);
 await review.locator('pre').evaluate(pre=>{const index=pre.textContent.indexOf('"motion"',pre.textContent.indexOf('PROPOSED MODEL'));const count=pre.textContent.slice(0,index).split('\n').length;pre.scrollTop=(count-2)*parseFloat(getComputedStyle(pre).lineHeight);});
 if(process.env.MBDYN_SKIP_DOC_SCREENSHOTS!=='1'){await mkdir('docs/images',{recursive:true});await page.screenshot({path:'docs/images/spatial-ai-prescribed-motion.png'});}
 await review.getByRole('button',{name:'Apply proposal'}).click();await page.waitForFunction(()=>document.querySelector('#agentMessages')?.textContent.includes('Use Undo to restore the previous model.'));await page.locator('[data-entity="joint-fixture"]').click();await page.waitForFunction(()=>Number(document.querySelector('#spatial-joint-fixture-motion-amplitude')?.value)===.025);
 assert.equal(Number(await page.locator('#spatial-joint-fixture-motion-frequencyHz').inputValue()),1);assert.equal(runs.length,0);assert.deepEqual(errors,[]);
 console.log('AI prescribed motion: controlled proposal, manual review, apply and no solver run passed.');
}finally{if(browser)await browser.close();service.kill();lines.close();}
