import { test } from "node:test";
import assert from "node:assert/strict";
import * as THREE from "three";
import { createStepView } from "../frontend/step-view.js";

const part = (id, positions=[2,0,2, 3,0,2, 2,1,2]) => ({id,name:id,path:id,positions,indices:[0,1,2]});
const model = () => ({units:"m",parts:[part("hashA:arm"),part("hashB:upright")]});
const initial = [{id:"upper",x:1,y:0,z:2,ry:90}];
const bound = {body:"upper",pose:{x:1,y:0,z:2,ry:90}};
const near = (actual, expected) => assert.ok(Math.abs(actual-expected)<1e-5, `${actual} != ${expected}`);
const worldVertex = mesh => mesh.localToWorld(new THREE.Vector3().fromBufferAttribute(mesh.geometry.getAttribute("position"),0));

test("bound solids preserve assembled STEP pose and follow actual translated and rotated body; unbound solids stay fixed",()=>{
  const view=createStepView(model(),{initialNodes:initial,bindings:{"hashA:arm":bound},offset:[0,0,1],entityForBody:()=>"body"});
  let point=worldVertex(view.partMeshes.get("hashA:arm"));
  near(point.x,2);near(point.z,3);
  const selected=view.partMeshes.get("hashA:arm");assert.equal(selected.userData.entity,"body");
  view.update([{id:"upper",x:4,y:0,z:5,ry:180}]);
  point=worldVertex(selected);near(point.x,4);near(point.z,5);
  point=worldVertex(view.partMeshes.get("hashB:upright"));near(point.x,2);near(point.z,3);
  view.dispose();
});

test("failed updates are atomic and duplicate or stale bindings are rejected",()=>{
  const view=createStepView(model(),{initialNodes:initial,bindings:{"hashA:arm":bound}});
  const before=worldVertex(view.partMeshes.get("hashA:arm")).clone();
  assert.throws(()=>view.update([{id:"upper",x:7,y:0,z:0,ry:NaN}]),/pose/);
  assert.deepEqual(worldVertex(view.partMeshes.get("hashA:arm")).toArray(),before.toArray());
  assert.throws(()=>createStepView(model(),{initialNodes:initial,bindings:{"absent":bound}}),/unknown/);
  assert.throws(()=>createStepView(model(),{initialNodes:initial,bindings:{"hashA:arm":{...bound,body:"absent"}}}),/unknown/);
  assert.throws(()=>createStepView(model(),{initialNodes:initial,bindings:{"hashA:arm":{...bound,pose:{...bound.pose,ry:NaN}}}}),/pose/);
  assert.throws(()=>createStepView(model(),{initialNodes:initial,bindings:{"hashA:arm":{...bound,pose:{...bound.pose,scale:2}}}}),/registration pose/);
  assert.throws(()=>createStepView({units:"mm",parts:[part("x")]}),/metres/);
  assert.throws(()=>createStepView({units:"m",parts:[part("x"),part("x")]}),/unique/);
  assert.throws(()=>createStepView({units:"m",parts:[{...part("x"),indices:[0,1,99]}]}),/indices/);
  const named = createStepView({units:"m",parts:[part("__proto__")]});
  assert.equal(named.partMeshes.get("__proto__").userData.entity, "step-part-__proto__");
  named.dispose();
  view.dispose();
});

test("changing the initial body pose retains the original CAD binding frame",()=>{
  const changed=[{id:"upper",x:4,y:0,z:5,ry:180}];
  const view=createStepView(model(),{initialNodes:changed,bindings:{"hashA:arm":bound}});
  const point=worldVertex(view.partMeshes.get("hashA:arm"));
  near(point.x,4);near(point.z,4);
  view.dispose();
});

test("disposal releases every part exactly once and removes its group",()=>{
  const view=createStepView(model());let geometries=0, materials=0;
  const parent=new THREE.Group();parent.add(view.group);
  for(const mesh of view.partMeshes.values()) {mesh.geometry.addEventListener("dispose",()=>geometries++);mesh.material.addEventListener("dispose",()=>materials++);}
  view.dispose();view.dispose();assert.equal(geometries,2);assert.equal(materials,2);assert.equal(parent.children.length,0);
  assert.throws(()=>view.update([]),/disposed/);
});

// Explicit row-major Rx*Ry*Rz checks the MBDyn Euler123 convention independently of Three.js Euler.
const mul=(a,b)=>Array.from({length:9},(_,i)=>{const row=Math.floor(i/3),col=i%3;return [0,1,2].reduce((sum,k)=>sum+a[row*3+k]*b[k*3+col],0)});
function r123(p){const r=Math.PI/180,[a,b,c]=[p.rx,p.ry,p.rz].map(v=>v*r);return mul(mul([1,0,0,0,Math.cos(a),-Math.sin(a),0,Math.sin(a),Math.cos(a)],[Math.cos(b),0,Math.sin(b),0,1,0,-Math.sin(b),0,Math.cos(b)]),[Math.cos(c),-Math.sin(c),0,Math.sin(c),Math.cos(c),0,0,0,1]);}
const apply=(m,v)=>[0,1,2].map(i=>m[3*i]*v[0]+m[3*i+1]*v[1]+m[3*i+2]*v[2]);
const transpose=m=>[m[0],m[3],m[6],m[1],m[4],m[7],m[2],m[5],m[8]];
function expectedSpatial(vertex,bind,now,offset){const local=apply(transpose(r123(bind)),vertex.map((v,i)=>v-[bind.x,bind.y,bind.z][i]));return apply(r123(now),local).map((v,i)=>v+[now.x,now.y,now.z][i]+offset[i]);}

test("spatial STEP occurrence follows noncommuting Euler123 rotations in world coordinates",()=>{
  const start={id:"body3d",x:1,y:-2,z:3,rx:25,ry:-40,rz:70};
  const registration={body:"body3d",pose:{x:start.x,y:start.y,z:start.z,rx:start.rx,ry:start.ry,rz:start.rz}};
  const display=[.2,-.3,.4], vertex=[2,0,2], view=createStepView(model(),{initialNodes:[start],bindings:{"hashA:arm":registration},offset:display});
  let result=worldVertex(view.partMeshes.get("hashA:arm")).toArray();expectedSpatial(vertex,registration.pose,start,display).forEach((v,i)=>near(result[i],v));
  const current={id:"body3d",x:-4,y:3,z:7,rx:-80,ry:55,rz:15};view.update([current]);
  result=worldVertex(view.partMeshes.get("hashA:arm")).toArray();expectedSpatial(vertex,registration.pose,current,display).forEach((v,i)=>near(result[i],v));
  const fixed=worldVertex(view.partMeshes.get("hashB:upright")).toArray();vertex.map((v,i)=>v+display[i]).forEach((v,i)=>near(fixed[i],v));
  view.dispose();
});

test("equivalent Euler123 branch representations produce identical STEP transforms",()=>{
  const registration={body:"body3d",pose:{x:0,y:0,z:0,rx:0,ry:0,rz:0}};
  const first={id:"body3d",x:1,y:2,z:3,rx:30,ry:60,rz:-20}, equivalent={...first,rx:210,ry:120,rz:160};
  const view=createStepView(model(),{initialNodes:[first],bindings:{"hashA:arm":registration}}), mesh=view.partMeshes.get("hashA:arm");
  const a=worldVertex(mesh).toArray();view.update([equivalent]);const b=worldVertex(mesh).toArray();a.forEach((v,i)=>near(v,b[i]));view.dispose();
});

test("spatial binding requires complete finite 3D orientation and rejects partial updates atomically",()=>{
  const binding={body:"body3d",pose:{x:0,y:0,z:0,rx:5,ry:10,rz:20}}, first={id:"body3d",x:1,y:2,z:3,rx:20,ry:30,rz:40};
  assert.throws(()=>createStepView(model(),{initialNodes:[first],bindings:{"hashA:arm":{...binding,pose:{x:0,y:0,z:0,rx:5,ry:10}}}}),/registration pose/);
  assert.throws(()=>createStepView(model(),{initialNodes:[{...first,rz:undefined}],bindings:{"hashA:arm":binding}}),/spatial body pose/);
  const view=createStepView(model(),{initialNodes:[first],bindings:{"hashA:arm":binding}}),before=worldVertex(view.partMeshes.get("hashA:arm")).toArray();
  assert.throws(()=>view.update([{...first,rx:NaN}]),/spatial body pose/);
  assert.deepEqual(worldVertex(view.partMeshes.get("hashA:arm")).toArray(),before);view.dispose();
});
