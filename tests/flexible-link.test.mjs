import test from 'node:test';
import assert from 'node:assert/strict';
import * as THREE from 'three';
import {buildFlexibleLink,sampleFlexibleLink} from '../frontend/flexible-link.js';
import {parseSolverCsv,fullSeries} from '../frontend/full-resolution.js';

test('flexible renderer places every FE node directly and preserves native curvature',()=>{
  const group=new THREE.Group(),view={group,model:{parameters:{nodes:3,length:1}},mesh(geometry,color,position,entity){const mesh=new THREE.Mesh(geometry,new THREE.MeshBasicMaterial({color}));mesh.position.copy(position);mesh.userData.entity=entity;group.add(mesh);return mesh;}};
  buildFlexibleLink(view);assert.equal(view.flexibleParts.nodes.length,3);assert.equal(view.flexibleParts.segments.length,2);
  sampleFlexibleLink(view,{nodes:[{id:'flex1',x:0,y:0,z:0},{id:'flex2',x:.5,y:.02,z:-.01},{id:'flex3',x:.99,y:.04,z:-.03}]});
  assert.deepEqual(view.flexibleParts.nodes[1].position.toArray(),[.5,.02,-.01]);assert.deepEqual(view.flexibleParts.nodes[2].position.toArray(),[.99,.04,-.03]);
  assert(Math.abs(view.flexibleParts.segments[1].scale.y-Math.hypot(.49,.02,-.02))<1e-12);
  group.traverse(o=>{o.geometry?.dispose();o.material?.dispose();});
});

test('full-resolution flexible channels retain physical scalar units and every node',()=>{
  const csv='time,id,label,x,z,tipDeflection_m,rootMoment_Nm\n0,flex1,Root,0,0,0,0\n0,flex3,Tip,1,0,0,0\n1,flex1,Root,0,0,-.01,.5\n1,flex3,Tip,.999,-.01,-.01,.5';
  const data=parseSolverCsv(csv);assert.deepEqual(fullSeries(data,'tipDeflection'),[0,-.01]);assert.deepEqual(fullSeries(data,'rootMoment'),[0,.5]);assert.deepEqual(fullSeries(data,'node:flex3:z'),[0,-.01]);
});
