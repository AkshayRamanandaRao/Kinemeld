import test from 'node:test';
import assert from 'node:assert/strict';
import {frameAxis,applyReferenceFrame,linkReferenceFrame,syncFrameLinks,jointFrameLink} from '../frontend/frame-editor.js';

const close=(value,expected)=>assert(Math.abs(value-expected)<1e-12,`${value} != ${expected}`);
const frame={id:'pivot',name:'Pivot',body:'arm',translation:{x:.1,y:.2,z:.3},rotation:{rx:90,ry:90,rz:0}};

test('noncommuting Euler123 basis produces the expected parent-local axes',()=>{
 const x=frameAxis(frame,'x'),y=frameAxis(frame,'y'),z=frameAxis(frame,'z');
 for(const [actual,expected] of [[x,{x:0,y:1,z:0}],[y,{x:0,y:0,z:1}],[z,{x:1,y:0,z:0}]])for(const k of ['x','y','z'])close(actual[k],expected[k]);
});
test('applying a body frame snapshots its origin and axis, preserving unrelated joint fields',()=>{
 const model={frames:[structuredClone(frame)],joints:[{id:'hinge',type:'revolute',a:'ground',b:'arm',anchorA:{x:0,y:0,z:0},anchorB:{x:0,y:0,z:0},axisA:{x:0,y:1,z:0},axisB:{x:0,y:1,z:0}}]};
 applyReferenceFrame(model,'hinge','b','pivot','z');
 assert.deepEqual(model.joints[0].anchorB,{x:.1,y:.2,z:.3});close(model.joints[0].axisB.x,1);
 assert.deepEqual(model.joints[0].anchorA,{x:0,y:0,z:0});model.frames[0].translation.x=.9;assert.equal(model.joints[0].anchorB.x,.1);
 const before=structuredClone(model);assert.throws(()=>applyReferenceFrame(model,'hinge','a','pivot','x'),/belonging/);assert.deepEqual(model,before);
});
test('ground frames use world coordinates and spherical ends only copy position',()=>{
 const global={...structuredClone(frame),id:'worldFrame',body:'ground'},model={frames:[global],joints:[{id:'ball',type:'spherical',a:'ground',b:'arm',anchorA:{x:0,y:0,z:0},anchorB:{x:0,y:0,z:0}}]};
 applyReferenceFrame(model,'ball','a','worldFrame','y');assert.deepEqual(model.joints[0].anchorA,{x:.1,y:.2,z:.3});assert.equal(Object.hasOwn(model.joints[0],'axisA'),false);
});
test('invalid rotations cannot partly overwrite a joint anchor',()=>{
 const bad=structuredClone(frame);bad.rotation.rz=Infinity;const model={frames:[bad],joints:[{id:'hinge',a:'ground',b:'arm',anchorB:{x:3,y:4,z:5},axisB:{x:0,y:1,z:0}}]},before=structuredClone(model);
 assert.throws(()=>applyReferenceFrame(model,'hinge','b','pivot','y'),/valid frame rotation/);assert.deepEqual(model,before);
});
test('live links update snapshots and unlink keeps the last physical fields',()=>{
 const model={frames:[structuredClone(frame)],joints:[{id:'hinge',a:'ground',b:'arm',anchorB:{x:0,y:0,z:0},axisB:{x:0,y:1,z:0}}]};
 linkReferenceFrame(model,'hinge','b','pivot','x');assert.equal(jointFrameLink(model,'hinge','b').frame,'pivot');
 model.frames[0].translation.x=.4;model.frames[0].rotation={rx:0,ry:0,rz:90};syncFrameLinks(model);close(model.joints[0].anchorB.x,.4);close(model.joints[0].axisB.y,1);
 model.frameLinks=[];model.frames[0].translation.x=.7;syncFrameLinks(model);close(model.joints[0].anchorB.x,.4);
});
test('linking a frame to another body cannot modify a joint',()=>{
 const model={frames:[structuredClone(frame)],joints:[{id:'hinge',a:'ground',b:'arm',anchorA:{x:0,y:0,z:0}}]},before=structuredClone(model);
 assert.throws(()=>linkReferenceFrame(model,'hinge','a','pivot','x'),/belonging/);assert.deepEqual(model,before);
});
