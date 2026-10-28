import assert from 'node:assert/strict';
import test from 'node:test';
import {readFile} from 'node:fs/promises';
import vm from 'node:vm';

const source=await readFile(new URL('../native/crates/app/src/bridge.js',import.meta.url),'utf8');
function bridge(){const messages=[],window={ipc:{postMessage(text){messages.push(JSON.parse(text));}}};vm.runInNewContext(source,{window,setTimeout,clearTimeout});return {window,messages};}

test('timed native calls remove callbacks, ignore late replies and preserve unrelated requests',async()=>{
 const {window,messages}=bridge();
 const abandoned=window.mbdynNative.call('finalize-open',{token:'1'},20);const live=window.mbdynNative.call('status',{},200);
 const first=messages[0],second=messages[1];assert.equal(first.payload.token,'1');
 await assert.rejects(abandoned,/acknowledgement timed out/);
 window.__mbdynNativeResolve(first.id,{ok:true,value:{unexpected:true}});
 window.__mbdynNativeResolve(second.id,{ok:true,value:{state:'live'}});
 assert.equal((await live).state,'live');
 const retry=window.mbdynNative.call('finalize-open',{token:'1'},200);const retryMessage=messages[2];
 window.__mbdynNativeResolve(retryMessage.id,{ok:true,value:{token:'1'}});
 assert.equal((await retry).token,'1');
});

test('synchronous transport failures reject cleanly and later requests work',async()=>{
 const {window,messages}=bridge();window.ipc.postMessage=()=>{throw Error('transport unavailable');};
 await assert.rejects(window.mbdynNative.call('finalize-open',{token:'2'},20),/transport unavailable/);
 window.ipc.postMessage=text=>messages.push(JSON.parse(text));
 const next=window.mbdynNative.call('finalize-open',{token:'2'},200);
 window.__mbdynNativeResolve(messages[0].id,{ok:false,error:'different transaction'});
 await assert.rejects(next,/different transaction/);
});
