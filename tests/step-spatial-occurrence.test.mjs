import assert from 'node:assert/strict';
import {spawnSync} from 'node:child_process';
import {test} from 'node:test';
import * as THREE from 'three';
import {createStepView} from '../frontend/step-view.js';

const marker='KINEMELD_STEP_JSON=';
const python=`import json,sys\nsys.path.insert(0,'backend')\nimport test_step_geometry,step_geometry\nif not test_step_geometry.HAS_OCP: print('MISSING_OCP'); sys.exit(77)\ntest_step_geometry.StepGeometryTest.setUpClass()\nprint('${marker}'+json.dumps(step_geometry.convert_step(test_step_geometry.StepGeometryTest.data,'assembly.step'),separators=(',',':')))\n`;
const near=(a,b)=>assert(Math.abs(a-b)<1e-6,`${a} != ${b}`);

test('actual repeated STEP occurrences retain CAD placement and follow a spatial body',t=>{
  const run=spawnSync('python',['-c',python],{encoding:'utf8',maxBuffer:32*1024*1024});
  if(run.status===77){t.skip('optional OpenCascade runtime is unavailable');return;}
  assert.equal(run.status,0,run.stderr);
  // OCP 8 can emit an ANSI reset after Python's final line; frame the fixture explicitly.
  const payload=run.stdout.split(/\r?\n/).find(line=>line.includes(marker));assert(payload,'STEP fixture did not emit its JSON record.');
  const data=JSON.parse(payload.slice(payload.indexOf(marker)+marker.length));assert.equal(data.parts.length,2);
  const [a,b]=data.parts, initial={id:'body',x:0,y:0,z:0,rx:0,ry:0,rz:0};
  const view=createStepView(data,{initialNodes:[initial],bindings:{[b.id]:{body:'body',pose:{x:0,y:0,z:0,rx:0,ry:0,rz:0}}}});
  const originalA=view.partMeshes.get(a.id),attached=view.partMeshes.get(b.id), point=mesh=>mesh.localToWorld(new THREE.Vector3().fromBufferAttribute(mesh.geometry.getAttribute('position'),0));
  const a0=point(originalA).clone(),b0=point(attached).clone();
  // Independent Rz(90) for the selected body, then translation; occurrence rotation is already in source vertex data.
  view.update([{id:'body',x:1,y:2,z:3,rx:0,ry:0,rz:90}]);
  const moved=point(attached);near(moved.x,1-b0.y);near(moved.y,2+b0.x);near(moved.z,3+b0.z);
  const fixed=point(originalA);near(fixed.x,a0.x);near(fixed.y,a0.y);near(fixed.z,a0.z);
  view.dispose();
});
