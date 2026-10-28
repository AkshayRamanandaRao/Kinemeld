import assert from 'node:assert/strict';
import test from 'node:test';
import {createHash} from 'node:crypto';
import * as THREE from 'three';
import {captureStepMass,calculateStepMass,stepMassCurrent,proposeStepMass,captureBodyStepMass,bodyStepMassCurrent,combineBodyStepMass,proposeBodyStepMass,setupStepMass} from '../frontend/step-mass.js';
const bytes=Buffer.from('ISO-10303-21; mock');const sha256=createHash('sha256').update(bytes).digest('hex');
function fixture(pose={x:1,y:2,z:3,rx:20,ry:30,rz:-10}) {
 const asset={parts:[{id:'0:part-1'}],metadata:{files:[{name:'test.step',data:bytes.toString('base64'),byteLength:bytes.length,sha256}],bindings:{'0:part-1':{body:'bob',pose}}}};
 const model={kind:'spatial-assembly',bodies:[{id:'bob',mass:2,inertia:{xx:1,yy:2,zz:3}}]};
 const r=new THREE.Matrix3().setFromMatrix4(new THREE.Matrix4().makeRotationFromEuler(new THREE.Euler((pose.rx||0)*Math.PI/180,pose.ry*Math.PI/180,(pose.rz||0)*Math.PI/180,'XYZ')));
 const world=r.clone().multiply(new THREE.Matrix3().set(1,0,0,0,2,0,0,0,3)).multiply(r.clone().transpose()).elements;
 const result={ok:true,format:'step-mass/1',sha256,partId:'part-1',density:1000,units:{length:'m',volume:'m^3',mass:'kg',inertia:'kg*m^2'},reference:'world axes, inertia about centre of mass',volume:.002,mass:2,centerOfMass:{x:pose.x,y:pose.y,z:pose.z},inertia:[[world[0],world[3],world[6]],[world[1],world[4],world[7]],[world[2],world[5],world[8]]]};
 return {asset,model,result,snapshot:captureStepMass(asset,model,'0:part-1',1000)};
}
const propose=f=>proposeStepMass(f.snapshot,f.asset,f.model,'0:part-1',1000,f.result);
test('noncommuting registered orientation transforms world inertia back into local principal axes',()=>{const f=fixture();const x=propose(f);assert.equal(x.bodyId,'bob');assert.equal(x.mass,2);for(const [key,want] of Object.entries({xx:1,yy:2,zz:3}))assert(Math.abs(x.inertia[key]-want)<1e-10);});
test('planar registration uses +Y rotation',()=>{const f=fixture({x:1,y:2,z:3,ry:37});f.model.kind='planar-assembly';f.snapshot=captureStepMass(f.asset,f.model,'0:part-1',1000);const x=propose(f);assert(Math.abs(x.inertia.yy-2)<1e-10);});
test('spatial bodies accept an offset COM; planar bodies and single parts in multi-part bodies remain guarded',()=>{let f=fixture();f.result.centerOfMass.x+=.001;const expected=new THREE.Vector3(.001,0,0).applyMatrix3(new THREE.Matrix3().setFromMatrix4(new THREE.Matrix4().makeRotationFromEuler(new THREE.Euler(...['rx','ry','rz'].map(k=>f.snapshot.binding.pose[k]*Math.PI/180),'XYZ'))).transpose());const center=propose(f).centerOfMass;assert(Math.hypot(center.x-expected.x,center.y-expected.y,center.z-expected.z)<1e-12);f.model.kind='planar-assembly';f.snapshot=captureStepMass(f.asset,f.model,'0:part-1',1000);assert.throws(()=>propose(f),/centre of mass/);f=fixture();f.asset.metadata.bindings['1:part-1']={body:'bob',pose:f.snapshot.binding.pose};assert.throws(()=>propose(f),/multiple STEP parts/);});
test('spatial inertia keeps products while planar bodies reject non-diagonal inertia',()=>{let f=fixture({x:1,y:2,z:3,rx:0,ry:0,rz:0});f.result.inertia=[[2,.1,0],[.1,2,0],[0,0,2]];assert(Math.abs(propose(f).inertia.xy-.1)<1e-12);f=fixture({x:1,y:2,z:3,ry:0});f.model.kind='planar-assembly';f.snapshot=captureStepMass(f.asset,f.model,'0:part-1',1000);f.result.inertia=[[2,.1,0],[.1,2,0],[0,0,2]];assert.throws(()=>propose(f),/not diagonal/);});
test('source, binding, body, part and density edits invalidate the snapshot',()=>{for(const change of [f=>f.asset.metadata.files[0].data+='A',f=>f.asset.metadata.bindings['0:part-1'].pose.x++,f=>f.model.bodies[0].mass++,f=>f.asset.parts=[],f=>f.model.kind='planar-assembly']){const f=fixture();change(f);assert.equal(stepMassCurrent(f.snapshot,f.asset,f.model,'0:part-1',1000),false);assert.throws(()=>propose(f),/changed/);}const f=fixture();assert.equal(stepMassCurrent(f.snapshot,f.asset,f.model,'0:part-1',1),false);});
test('backend mismatch, invalid physics and malformed input never produce a proposal',()=>{for(const change of [f=>f.result.sha256='0'.repeat(64),f=>f.result.mass=-1,f=>f.result.inertia[0][0]=-1,f=>f.result.inertia[1][0]+=1,f=>f.result.centerOfMass.x=NaN]){const f=fixture();change(f);assert.throws(()=>propose(f));}const f=fixture();assert.throws(()=>captureStepMass(f.asset,f.model,'0:part-1',Infinity),/density/);});
test('request sends exact source and rejects mismatched backend identity',async()=>{const f=fixture();let seen;const data=await calculateStepMass(f.snapshot,async(url,options)=>{seen={url,options};return {ok:true,json:async()=>f.result};});assert.equal(data.mass,2);assert.equal(seen.url,'/api/step/mass');assert.equal(seen.options.headers['X-Step-Part'],'part-1');assert.deepEqual(Buffer.from(seen.options.body),bytes);await assert.rejects(calculateStepMass(f.snapshot,async()=>({ok:true,json:async()=>({...f.result,sha256:'bad'})})),/mismatched/);});

test('multi-occurrence mass requires a unique witnessed selection and checks the service witness',async()=>{
 const f=fixture(), first={scheme:'step-nauo-id-path/1',path:['组装','left']}, second={scheme:'step-nauo-id-path/1',path:['组装','right']};
 f.asset.parts=[{id:'0:part-1',occurrenceWitness:first},{id:'0:part-2',occurrenceWitness:second}];
 f.snapshot=captureStepMass(f.asset,f.model,'0:part-1',1000);f.result.occurrenceWitness=first;
 let header;await calculateStepMass(f.snapshot,async(_url,options)=>{header=options.headers['X-Step-Witness'];return {ok:true,json:async()=>f.result};});
 assert.deepEqual(JSON.parse(Buffer.from(header,'base64').toString('utf8')),first);
 await assert.rejects(calculateStepMass(f.snapshot,async()=>({ok:true,json:async()=>({...f.result,occurrenceWitness:second})})),/occurrence identity/);
 f.asset.parts[1].occurrenceWitness=first;assert.throws(()=>captureStepMass(f.asset,f.model,'0:part-1',1000),/ambiguous/);
 f.asset.parts[1].occurrenceWitness=second;f.asset.parts[0].occurrenceWitness=null;assert.throws(()=>captureStepMass(f.asset,f.model,'0:part-1',1000),/missing or ambiguous/);
});

test('pending attachments prevent partial or combined mass being applied to their body',()=>{
 const f=fixture();f.asset.metadata.unverifiedBindings={'0:part-2':{body:'bob',pose:f.snapshot.binding.pose}};
 assert.throws(()=>propose(f),/unverified/);
 assert.throws(()=>captureBodyStepMass(f.asset,f.model,'0:part-1',1000),/unverified/);
});

test('tiny planar inertia is not accepted when off-diagonal terms are physically significant',()=>{const f=fixture({x:1,y:2,z:3,ry:0});f.model.kind='planar-assembly';f.snapshot=captureStepMass(f.asset,f.model,'0:part-1',1000);f.result.inertia=[[1e-16,1e-17,0],[1e-17,2e-16,0],[0,0,3e-16]];assert.throws(()=>propose(f),/not diagonal/);});
test('validation failures can be retried, and changed density discards a pending calculation',async()=>{
 const f=fixture(),elements=Object.fromEntries(['stepPart','stepMassDensity','stepMassApply','stepMassCalculate','stepMassCalculateBody','stepMassResult'].map(id=>[id,{disabled:false,textContent:'',value:id==='stepMassDensity'?'1000':'0:part-1',listeners:{},addEventListener(name,fn){this.listeners[name]=fn;}}]));
 const oldDocument=globalThis.document,oldFetch=globalThis.fetch;let valid=false,applied=0;
 try{
  globalThis.document={getElementById:id=>elements[id]};globalThis.fetch=async()=>({ok:true,json:async()=>f.result});
  setupStepMass({getState:()=>({asset:f.asset,model:f.model,partId:elements.stepPart.value,busy:false}),validateModel:async()=>({valid,issues:[{message:'test failure'}]}),applyCandidate:()=>{applied++},notify:()=>{}});
  await elements.stepMassCalculate.onclick();assert.equal(elements.stepMassApply.disabled,false);
  await elements.stepMassApply.onclick();assert.equal(elements.stepMassApply.disabled,false);assert.match(elements.stepMassResult.textContent,/test failure/);assert.equal(applied,0);
  valid=true;await elements.stepMassApply.onclick();assert.equal(applied,1);
  let finish;globalThis.fetch=()=>new Promise(resolve=>{finish=resolve;});const waiting=elements.stepMassCalculate.onclick();await new Promise(resolve=>setTimeout(resolve,10));
  elements.stepMassDensity.value='1200';elements.stepMassDensity.listeners.input();finish({ok:true,json:async()=>f.result});await waiting;assert.equal(elements.stepMassResult.textContent,'No calculation yet.');assert.equal(elements.stepMassApply.disabled,true);
 }finally{globalThis.document=oldDocument;globalThis.fetch=oldFetch;}
});

test('combined STEP occurrences use mass-weighted centers and the parallel-axis theorem',()=>{
 const f=fixture({x:0,y:0,z:0,rx:0,ry:0,rz:0});f.asset.parts.push({id:'1:part-1'});f.asset.metadata.files.push(structuredClone(f.asset.metadata.files[0]));f.asset.metadata.bindings['1:part-1']=structuredClone(f.asset.metadata.bindings['0:part-1']);
 const left=structuredClone(f.result),right=structuredClone(f.result);left.centerOfMass.x=-.2;right.centerOfMass.x=.2;
 const snap=captureBodyStepMass(f.asset,f.model,'0:part-1',1000),combined=combineBodyStepMass(snap,[left,right]);
 assert.equal(combined.mass,4);assert.deepEqual(combined.center,[0,0,0]);assert(Math.abs(combined.inertia[0][0]-2)<1e-12);assert(Math.abs(combined.inertia[1][1]-4.16)<1e-12);assert(Math.abs(combined.inertia[2][2]-6.16)<1e-12);
 const proposal=proposeBodyStepMass(snap,f.asset,f.model,'0:part-1',1000,[left,right]);assert.equal(proposal.mass,4);
 f.asset.metadata.bindings['1:part-1'].pose.x=.1;assert.equal(bodyStepMassCurrent(snap,f.asset,f.model,'0:part-1',1000),false);assert.throws(()=>proposeBodyStepMass(snap,f.asset,f.model,'0:part-1',1000,[left,right]),/changed/);
});
test('combined STEP bodies preserve off-center resultant COM in body axes',()=>{const f=fixture({x:0,y:0,z:0,rx:0,ry:0,rz:0}),snap=captureBodyStepMass(f.asset,f.model,'0:part-1',1000);f.result.centerOfMass.x=.2;const proposal=proposeBodyStepMass(snap,f.asset,f.model,'0:part-1',1000,[f.result]);assert.deepEqual(proposal.centerOfMass,{x:.2,y:0,z:0});});

test('combination respects each occurrence registration frame and off-diagonal parallel-axis terms',()=>{
 const f=fixture(), poseA=f.snapshot.binding.pose, poseB={x:-2,y:1,z:.5,rx:-15,ry:10,rz:35};
 f.asset.parts.push({id:'1:part-1'});f.asset.metadata.files.push(structuredClone(f.asset.metadata.files[0]));f.asset.metadata.bindings['1:part-1']={body:'bob',pose:poseB};
 const make=(pose,point)=>{const r=new THREE.Matrix3().setFromMatrix4(new THREE.Matrix4().makeRotationFromEuler(new THREE.Euler(pose.rx*Math.PI/180,pose.ry*Math.PI/180,pose.rz*Math.PI/180,'XYZ')));const v=new THREE.Vector3(...point).applyMatrix3(r).add(new THREE.Vector3(pose.x,pose.y,pose.z));const e=r.clone().multiply(new THREE.Matrix3().set(1,0,0,0,2,0,0,0,3)).multiply(r.clone().transpose()).elements;return {...structuredClone(f.result),centerOfMass:{x:v.x,y:v.y,z:v.z},inertia:[[e[0],e[3],e[6]],[e[1],e[4],e[7]],[e[2],e[5],e[8]]]};};
 const a=[.1,.2,0],b=[-.1,-.2,0],results=[make(poseA,a),make(poseB,b)],snap=captureBodyStepMass(f.asset,f.model,'0:part-1',1000),combined=combineBodyStepMass(snap,results);
 assert(Math.hypot(...combined.center)<1e-12);assert(Math.abs(combined.inertia[0][0]-2.16)<1e-10);assert(Math.abs(combined.inertia[1][1]-4.04)<1e-10);assert(Math.abs(combined.inertia[2][2]-6.20)<1e-10);assert(Math.abs(combined.inertia[0][1]+.08)<1e-10);
 const proposal=proposeBodyStepMass(snap,f.asset,f.model,'0:part-1',1000,results);assert(Math.abs(proposal.inertia.xy+.08)<1e-10);
});
