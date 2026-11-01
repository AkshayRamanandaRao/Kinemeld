import './workspace-shim.mjs';
import assert from 'node:assert/strict';
import {chromium} from 'playwright';
const base=process.env.MBDYN_STUDIO_URL || 'http://127.0.0.1:8768';
const browser=await chromium.launch({headless:true,args:['--enable-unsafe-swiftshader']});
const page=await browser.newPage({viewport:{width:1440,height:960}}),errors=[];page.on('pageerror',e=>errors.push(e.message));
await page.route('**/api/tour-preference',route=>route.fulfill({json:{enabled:false}}));
await page.addInitScript(()=>{
  const host=window.__ackHost={attempts:0,cleanAttempts:0,revision:0,mode:'finalize-loss',accepted:0,rollbacks:0,dirty:false,path:'C:/test/old.mbdyn-studio',saved:null,finalized:null};
  window.ipc={postMessage(raw){
    const request=JSON.parse(raw),respond=(ok,value)=>window.__mbdynNativeResolve(request.id,ok?{ok:true,value}:{ok:false,error:value});
    if(request.op==='dirty'){host.revision++;host.dirty=true;return;}
    if(request.op==='recovery'){respond(true,{});return;}
    if(request.op==='autosave'){respond(true,{skipped:true});return;}
    if(request.op==='open') {fetch('/api/examples').then(r=>r.json()).then(data=>respond(true,{project:{format:'mbdyn-studio/1',model:data.examples.find(x=>x.id==='mass-spring').model},path:'C:/test/candidate.mbdyn-studio'}));return;}
    if(request.op==='accept-open'){host.accepted++;host.path='C:/test/candidate.mbdyn-studio';host.revision++;host.dirty=true;respond(true,{token:'1'});return;}
    if(request.op==='finalize-open'){
      host.attempts++;if(request.payload.token!=='1'){respond(false,'wrong token');return;}
      if(host.finalized && host.finalized!==request.payload.token){respond(false,'different transaction');return;}
      host.finalized=request.payload.token;
      if(host.mode==='clean-loss'){respond(true,{token:host.finalized,dirtyRevision:String(host.revision)});return;}
      if(host.mode==='focus-wait'){setTimeout(()=>respond(true,{token:host.finalized,dirtyRevision:String(host.revision)}),1200);return;}
      if(host.attempts===1)return; // The host committed, but its first acknowledgement was lost.
      if(host.attempts===2){respond(true,{token:'wrong',dirtyRevision:String(host.revision)});return;}
      setTimeout(()=>respond(true,{token:host.finalized,dirtyRevision:String(host.revision)}),300);return;
    }
    if(request.op==='clean-open'){
      host.cleanAttempts++;
      const clean=request.payload.token===host.finalized && request.payload.dirtyRevision===String(host.revision);
      if(clean)host.dirty=false;
      if(host.mode==='clean-loss' && host.cleanAttempts===1)return;
      setTimeout(()=>respond(true,{token:request.payload.token,dirtyRevision:request.payload.dirtyRevision,clean}),300);return;
    }
    if(request.op==='rollback-open'){host.rollbacks++;respond(false,'already finalized');return;}
    if(request.op==='save'){host.saved=structuredClone(request.payload);host.dirty=false;respond(true,{path:host.path});return;}
    if(request.id)respond(false,'unexpected '+request.op);
  }};
});
await page.addInitScript({path:'native/crates/app/src/bridge.js'});
try {
 await page.goto(base);await page.waitForFunction(()=>document.querySelector('#solverStatus')?.textContent.includes('MBDyn ready'));
 await page.locator('#importButton').click();await page.waitForFunction(()=>window.__ackHost.attempts===1);
 assert.equal(await page.locator('#field-mass').inputValue(),'1');
 await page.locator('#field-mass').fill('2');await page.locator('#field-mass').press('Tab');
 await page.locator('#saveButton').click();assert.equal(await page.evaluate(()=>window.__ackHost.saved),null);
 await page.waitForFunction(()=>document.querySelector('#notice')?.textContent.includes('Edits made while confirmation was pending remain unsaved'),null,{timeout:20000});
 const host=await page.evaluate(()=>structuredClone(window.__ackHost));assert(host.attempts>=3);assert.equal(host.accepted,1);assert.equal(host.rollbacks,0);assert.equal(host.finalized,'1');assert.equal(host.dirty,true);assert.equal(await page.locator('#field-mass').inputValue(),'2');
 await page.locator('#saveButton').click();await page.waitForFunction(()=>window.__ackHost.saved!==null);const saved=await page.evaluate(()=>window.__ackHost.saved);
 assert.equal(saved.model.parameters.mass,2);assert.equal(await page.evaluate(()=>window.__ackHost.path),'C:/test/candidate.mbdyn-studio');
 await page.reload();await page.waitForFunction(()=>document.querySelector('#solverStatus')?.textContent.includes('MBDyn ready'));
 await page.evaluate(()=>{window.__ackHost.mode='clean-loss';});
 await page.locator('#importButton').click();await page.waitForFunction(()=>window.__ackHost.cleanAttempts===1);
 assert.equal(await page.evaluate(()=>document.querySelector('main').inert),true);
 const unchanged=await page.locator('#field-mass').inputValue();
 await page.evaluate(()=>document.querySelector('#field-mass').focus());await page.keyboard.type('99');
 assert.equal(await page.locator('#field-mass').inputValue(),unchanged,'Unconfirmed clean handshake must block typed edits');
 await page.waitForFunction(()=>document.querySelector('#notice')?.textContent.includes('Project opened and validated.'),null,{timeout:20000});
 assert(await page.evaluate(()=>window.__ackHost.cleanAttempts>=2));assert.equal(await page.evaluate(()=>document.querySelector('main').inert),false);assert.equal(await page.evaluate(()=>window.__ackHost.dirty),false);
 await page.reload();await page.waitForFunction(()=>document.querySelector('#solverStatus')?.textContent.includes('MBDyn ready'));
 await page.evaluate(()=>{window.__ackHost.mode='focus-wait';});await page.locator('#importButton').click();await page.waitForFunction(()=>window.__ackHost.attempts===1);
 await page.locator('#field-mass').fill('3');
 await page.waitForFunction(()=>document.querySelector('#notice')?.textContent.includes('Edits made while confirmation was pending remain unsaved'),null,{timeout:10000});
 assert.equal(await page.locator('#field-mass').inputValue(),'3');assert.equal(await page.evaluate(()=>window.__ackHost.dirty),true);assert.equal(await page.evaluate(()=>window.__ackHost.cleanAttempts),0);
 await page.locator('#field-mass').press('Tab');await page.waitForFunction(()=>document.querySelector('#notice')?.textContent.includes('Edits made while confirmation was pending remain unsaved'),null,{timeout:10000});
 assert.equal(await page.locator('#field-mass').inputValue(),'3');assert.equal(await page.evaluate(()=>window.__ackHost.dirty),true);
 assert.deepEqual(errors,[]);
 console.log('Lost, mismatched and delayed finalize/clean acknowledgements were retried; edits before confirmation stayed dirty and the clean handshake blocked further edits until acknowledged');
}catch(e){console.error(e);process.exitCode=1;await page.screenshot({path:'tests/evidence/native-open-ack-failure.png',fullPage:true}).catch(()=>{});}finally{await browser.close();}
