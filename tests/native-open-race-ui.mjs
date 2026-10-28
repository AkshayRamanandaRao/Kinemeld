import assert from 'node:assert/strict';
import {chromium} from 'playwright';
const base=process.env.MBDYN_STUDIO_URL || 'http://127.0.0.1:8768';
const browser=await chromium.launch({headless:true,args:['--enable-unsafe-swiftshader']});
const page=await browser.newPage({viewport:{width:1440,height:960}}),errors=[];
page.on('pageerror',e=>errors.push(e.message));
await page.route('**/api/tour-preference',route=>route.fulfill({json:{enabled:false}}));
await page.addInitScript(()=>{
 window.guard={mode:'',waiting:'',release:null,accepted:0,rollbacks:0,notifications:[]};
 window.mbdynNative={notify(op){window.guard.notifications.push(op);},async call(op,payload={}){
  if(op==='open'){const examples=await (await fetch('/api/examples')).json();const model=examples.examples.find(x=>x.id==='mass-spring').model;if(window.guard.mode==='open'){window.guard.waiting='open';await new Promise(resolve=>window.guard.release=resolve);}return {project:{format:'mbdyn-studio/1',model},path:'C:/test/other.mbdyn-studio'};}
  if(op==='accept-open'){window.guard.accepted++;if(window.guard.mode==='accept'){window.guard.waiting='accept';await new Promise(resolve=>window.guard.release=resolve);}return {token:'1'};}
  if(op==='finalize-open')return {token:payload.token,dirtyRevision:'1'};
  if(op==='clean-open')return {token:payload.token,dirtyRevision:payload.dirtyRevision,clean:true};
  if(op==='rollback-open'){window.guard.rollbacks++;return {};}
  throw Error('Unexpected native operation '+op);
 }};
});
try{
 await page.goto(base);await page.waitForFunction(()=>document.querySelector('#validationBadge')?.textContent==='Ready');
 for(const [mode,value] of [['open','31'],['accept','32']]){
  await page.evaluate(mode=>{window.guard.mode=mode;window.guard.waiting='';},mode);
  await page.locator('#importButton').click();await page.waitForFunction(mode=>window.guard.waiting===mode,mode);
  await page.locator('#field-angle').fill(value);await page.locator('#field-angle').press('Tab');
  await page.evaluate(()=>window.guard.release());await page.waitForFunction(()=>document.querySelector('#notice')?.textContent.includes('your edits were kept'));
  assert.equal(await page.locator('#field-angle').inputValue(),value);
 }
 const guard=await page.evaluate(()=>window.guard);assert.equal(guard.accepted,1);assert.equal(guard.rollbacks,1);assert(guard.notifications.includes('discard-open'));assert.deepEqual(errors,[]);console.log('Native open race preserves edits before and during commit');
}finally{await browser.close();}
