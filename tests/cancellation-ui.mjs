import assert from 'node:assert/strict';
import {chromium} from 'playwright';
const base=process.env.MBDYN_STUDIO_URL||'http://127.0.0.1:8768',browser=await chromium.launch({headless:true,args:['--enable-unsafe-swiftshader']}),page=await browser.newPage({viewport:{width:1440,height:960}}),errors=[];
page.on('pageerror',error=>errors.push(error.message));
let requests=[],cancels=[],release=null;
await page.route('**/api/tour-preference',route=>route.fulfill({json:{enabled:false}}));
for(const path of ['**/api/run','**/api/source-run'])await page.route(path,async route=>{const body=route.request().postDataJSON();requests.push(body);await new Promise(resolve=>{release=resolve});await route.fulfill({status:409,json:{ok:false,cancelled:true,error:'Simulation cancelled. Partial output and the solver log are retained.',runId:'a'.repeat(32),log:'partial'}})});
await page.route('**/api/run/cancel',async route=>{cancels.push(route.request().postDataJSON());await route.fulfill({status:200,json:{ok:true,state:'stopping'}});release?.()});
try {
 await page.goto(base);await page.waitForFunction(()=>document.querySelector('#solverStatus')?.textContent.includes('MBDyn ready'));
 await page.evaluate(()=>{document.querySelector('#runButton').click();document.querySelector('#runButton').click();});
 await page.waitForFunction(()=>!document.querySelector('#cancelRunButton').hidden);await page.waitForTimeout(200);
 assert.equal(requests.length,1);assert.match(requests[0].runToken,/^[0-9a-f]{32}$/);await page.locator('#cancelRunButton').click();
 await page.waitForFunction(()=>document.querySelector('#statusText')?.textContent.includes('Run cancelled'));assert.equal(cancels[0].runToken,requests[0].runToken);assert(await page.locator('#cancelRunButton').isHidden());assert.match(await page.locator('#runId').textContent(),/Cancelled/);await page.locator('#logButton').click();assert.match(await page.locator('#documentBody').textContent(),/partial/);
 await page.getByRole('button',{name:/Close.*document/i}).click().catch(()=>{});
 await page.locator('#examplesButton').click();await page.locator('.example-card').filter({has:page.getByRole('heading',{name:'Parallel manipulator — triangle',exact:true})}).getByRole('button',{name:/Open example/}).click();
 await page.locator('#runButton').click();await page.waitForFunction(()=>!document.querySelector('#cancelRunButton').hidden);await page.waitForTimeout(200);assert.equal(requests.length,2);assert.notEqual(requests[1].runToken,requests[0].runToken);
 await page.evaluate(()=>window.dispatchEvent(new Event('pagehide')));await page.waitForFunction(()=>document.querySelector('#statusText')?.textContent.includes('Run cancelled'));assert.equal(cancels[1].runToken,requests[1].runToken);assert.deepEqual(errors,[]);
 console.log('Cancellation UI token, pending run, log, source run and pagehide workflows passed');
}catch(error){console.error(error,errors,await page.locator('#solverStatus').textContent().catch(()=>'unknown'));process.exitCode=1;await page.screenshot({path:'tests/evidence/cancellation-ui-failure.png',fullPage:true}).catch(()=>{});}finally{release?.();await browser.close();}

