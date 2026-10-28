import test from 'node:test';
import assert from 'node:assert/strict';
import { webcrypto } from 'node:crypto';
import {loadStepAsset,restoreStepAsset} from '../frontend/step-asset.js';

globalThis.crypto ??= webcrypto;
const source=new TextEncoder().encode('ISO-10303-21; fictional fixture');
const w=id=>({scheme:'step-nauo-id-path/1',path:[id]});
const pose={x:1,y:2,z:3,ry:0.5};
const binding={body:'wheel',pose};
let current;
globalThis.fetch=async (_url,options)=>({ok:true,status:200,json:async()=>({ok:true,sha256:Buffer.from(await crypto.subtle.digest('SHA-256',options.body)).toString('hex'),parts:current})});
const p=(id,witness)=>({id,name:id,positions:[0,0,0],indices:[0,0,0],occurrenceWitness:witness});
const sourceFile={name:'fixture.step',bytes:source};

test('witness follows source occurrence when traversal indices change',async()=>{
  current=[p('part-1',w('A')),p('part-2',w('B'))];
  const original=await loadStepAsset([sourceFile],{'0:part-1':binding});
  current=[p('part-1',w('B')),p('part-2',w('A'))];
  const restored=await restoreStepAsset(original.metadata);
  assert.deepEqual(restored.metadata.bindings,{'0:part-2':binding});
  assert.deepEqual(restored.metadata.unverifiedBindings,{});
});

test('legacy binding is quarantined and stays there through repeated save and reopen',async()=>{
  current=[p('part-1',w('A')),p('part-2',w('B'))];
  const original=await loadStepAsset([sourceFile],{'0:part-1':binding});
  delete original.metadata.occurrenceWitnesses;
  delete original.metadata.unverifiedBindings;
  const first=await restoreStepAsset(original.metadata);
  assert.deepEqual(first.metadata.bindings,{});
  assert.deepEqual(first.metadata.unverifiedBindings,{'0:part-1':binding});
  const second=await restoreStepAsset(JSON.parse(JSON.stringify(first.metadata)));
  assert.deepEqual(second.metadata.unverifiedBindings,{'0:part-1':binding});
  assert.deepEqual(second.metadata.files,original.metadata.files);
});

test('a witnessed mismatch or duplicate occurrence cannot silently rebind',async()=>{
  current=[p('part-1',w('A')),p('part-2',w('B'))];
  const original=await loadStepAsset([sourceFile],{'0:part-1':binding});
  current=[p('part-1',w('B')),p('part-2',w('C'))];
  await assert.rejects(restoreStepAsset(original.metadata),/no longer matches/);
  current=[p('part-1',w('A')),p('part-2',w('A'))];
  await assert.rejects(restoreStepAsset(original.metadata),/no longer matches/);
});

test('a newly bound occurrence without source identity is quarantined after reopen',async()=>{
  current=[p('part-1',null),p('part-2',null)];
  const original=await loadStepAsset([sourceFile],{'0:part-2':binding});
  const restored=await restoreStepAsset(original.metadata);
  assert.deepEqual(restored.metadata.bindings,{});
  assert.deepEqual(restored.metadata.unverifiedBindings,{'0:part-2':binding});
});

test('two saved bindings cannot resolve to one witness',async()=>{
  current=[p('part-1',w('A')),p('part-2',w('B'))];
  const original=await loadStepAsset([sourceFile],{'0:part-1':binding,'0:part-2':binding});
  original.metadata.occurrenceWitnesses['0:part-2']=w('A');
  await assert.rejects(restoreStepAsset(original.metadata),/same occurrence/);
});
