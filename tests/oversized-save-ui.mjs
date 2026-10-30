/** Oversized full solver CSV must fail locally before desktop IPC, with export preserved. */
import './workspace-shim.mjs';
import assert from 'node:assert/strict';
import { chromium } from 'playwright';
import { mkdir, open, stat, unlink, writeFile } from 'node:fs/promises';
import { randomUUID } from 'node:crypto';

const base=process.env.MBDYN_STUDIO_URL || 'http://127.0.0.1:8768';
const browser=await chromium.launch({headless:true,args:['--enable-unsafe-swiftshader']});
const page=await browser.newPage({viewport:{width:1440,height:960},acceptDownloads:true});
const errors=[], report={checks:[],started:new Date().toISOString()};
page.on('pageerror',error=>errors.push(error.message));
await page.route('**/api/tour-preference',route=>route.fulfill({json:{enabled:false}}));
await page.route('**/api/run',async route=>{
  const model=route.request().postDataJSON().model;
  await route.fulfill({json:{ok:true,source:'MBDyn',model,runId:'a'.repeat(32),files:{csv:`/api/runs/${'a'.repeat(32)}/results.csv`},metrics:{sampleCount:2,duration:.1},samples:[
    {time:0,x:0,y:0,z:-1,angle:0,velocity:0,value:0},
    {time:.1,x:.1,y:0,z:-.99,angle:5,velocity:1,value:5}
  ]}});
});
await page.addInitScript(()=>{
  window.__nativeTest={saveCalls:0,notifications:[],csvFetches:0};
  window.mbdynNative={notify(op){window.__nativeTest.notifications.push(op)},async call(op){if(op==='recovery')return {};if(op==='autosave')return {skipped:true};if(op==='save'){window.__nativeTest.saveCalls++;return {path:'C:/fixture/project.mbdyn-studio'};}throw Error(`Unexpected native operation ${op}`)}};
  const fetchOriginal=window.fetch.bind(window);
  window.fetch=async(input,init)=>{
    const url=typeof input==='string'?input:input.url;
    if(url==='/api/runs/'+ 'a'.repeat(32) +'/results.csv'){
      window.__nativeTest.csvFetches++;
      const row='123.456,'.repeat(160)+'1\n';
      return new Response(new Blob(['time,id,force\n',row.repeat(26200)],{type:'text/csv'}),{status:200,headers:{'Content-Type':'text/csv'}});
    }
    return fetchOriginal(input,init);
  };
});
const downloadPath=`tests/evidence/oversized-export-${randomUUID()}.csv`;
try {
  await page.goto(base);
  await page.waitForFunction(()=>document.querySelector('#solverStatus')?.textContent.includes('MBDyn ready'));
  await page.locator('#field-length').fill('1.2');await page.locator('#field-length').press('Tab');
  await page.waitForFunction(()=>document.querySelector('#validationBadge')?.textContent==='Ready');
  const response=page.waitForResponse(r=>r.url().endsWith('/api/run')&&r.request().method()==='POST');
  await page.locator('#runButton').click();assert((await response).ok());
  await page.waitForFunction(()=>document.querySelector('#resultSource')?.textContent==='MBDyn solver');
  await page.locator('#saveButton').click();
  await page.waitForFunction(()=>document.querySelector('#notice')?.textContent.includes('Project exceeds 32 MiB'),null,{timeout:30000});
  assert.match(await page.locator('#notice').textContent(),/Export the CSV, clear the loaded result, then save the model and geometry/);
  assert.equal(await page.evaluate(()=>window.__nativeTest.saveCalls),0,'The oversized payload must never cross the native IPC boundary');
  assert.equal(await page.locator('#field-length').inputValue(),'1.2');
  assert.equal(await page.locator('#resultSource').textContent(),'MBDyn solver');
  assert.equal(await page.locator('#saveButton').isEnabled(),true);
  assert((await page.evaluate(()=>window.__nativeTest.notifications)).includes('dirty'));
  report.checks.push('Oversized project reports recovery instructions, retains unsaved model and result, and never calls native save');
  const event=page.waitForEvent('download',{timeout:60000});await page.locator('#csvButton').click();const download=await event;
  await mkdir('tests/evidence',{recursive:true});await download.saveAs(downloadPath);
  const info=await stat(downloadPath);assert(info.size>32*1024*1024);
  const file=await open(downloadPath,'r');
  try {
    const first=Buffer.alloc(64),last=Buffer.alloc(64);await file.read(first,0,64,0);await file.read(last,0,64,info.size-64);
    assert.match(first.toString('utf8'),/^# source: MBDyn/);assert.match(last.toString('utf8'),/123\.456,.*1$/);
  } finally {await file.close();}
  // Full-resolution plot data, the rejected save and the CSV export each read the run's CSV once.
  assert.equal(await page.evaluate(()=>window.__nativeTest.csvFetches),3);
  report.checks.push('Full oversized CSV remains downloadable after the rejected save');
  assert.deepEqual(errors,[]);report.ok=true;
}catch(error){report.ok=false;report.failure=error.stack;process.exitCode=1;console.error(error);}
finally {
  await unlink(downloadPath).catch(error=>{if(error.code!=='ENOENT')throw error;});
  report.errors=errors;report.completed=new Date().toISOString();await mkdir('tests/evidence',{recursive:true});
  await writeFile('tests/evidence/oversized-save-verification.json',JSON.stringify(report,null,2));await browser.close();
}
