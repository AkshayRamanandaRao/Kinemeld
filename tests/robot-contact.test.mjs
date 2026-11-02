import test from 'node:test';
import assert from 'node:assert/strict';
import * as THREE from 'three';
import { buildGlyphs,updateGlyphs,disposeGlyphs } from '../frontend/glyphs.js';
import { columnFor,parseSolverCsv,fullSeries } from '../frontend/full-resolution.js';

test('moving sphere-pair glyphs retain each radius and transformed body-local center',()=>{
  const model={bodies:[{id:'a'},{id:'b'}],joints:[],contacts:[{id:'pair',type:'sphere-sphere',body:'a',otherBody:'b',center:{x:1,y:0,z:0},otherCenter:{x:0,y:1,z:0},radius:.1,otherRadius:.2}]};
  const glyphs=buildGlyphs(model,1,new THREE.Vector3(2,0,0));
  const spheres=glyphs.items.filter(i=>i.object.userData.entity==='contact-pair');assert.equal(spheres.length,2);
  assert.deepEqual(spheres.map(i=>i.object.geometry.parameters.radius),[.1,.2]);
  updateGlyphs(glyphs,[{id:'a',x:1,y:2,z:0,rx:0,ry:0,rz:90},{id:'b',x:3,y:0,z:1,rx:0,ry:0,rz:0}]);
  assert(spheres[0].object.position.distanceTo(new THREE.Vector3(3,3,0))<1e-12);
  assert(spheres[1].object.position.distanceTo(new THREE.Vector3(5,1,1))<1e-12);disposeGlyphs(glyphs);
});

test('brake channels resolve signed native CSV and full-resolution dissipation',()=>{
  const csv='time,id,label,jointFriction:h:torque_Nm,jointFriction:h:speed_rad_s,jointFriction:h:power_W,jointFriction:h:dissipatedEnergy_J\n0,a,A,-1,0,0,0\n1,a,A,-1,2,2,1';
  const data=parseSolverCsv(csv);
  assert.deepEqual(columnFor('brake:h:torque'),{column:'jointFriction:h:torque_Nm'});
  assert.deepEqual(fullSeries(data,'brake:h:torque'),[-1,-1]);
  assert.deepEqual(fullSeries(data,'brake:h:dissipatedEnergy'),[0,1]);
});
