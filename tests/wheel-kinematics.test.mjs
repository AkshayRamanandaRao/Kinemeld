import test from 'node:test';
import assert from 'node:assert/strict';
import {wheelHistory,wheelCsv,wheelPlotBreak} from '../frontend/wheel-kinematics.js';

const node=(id,values={})=>({id,x:0,y:0,z:0,rx:0,ry:0,rz:0,vx:0,vy:0,vz:0,wx:0,wy:0,wz:0,...values});
const wheel={body:'wheel',center:{x:0,y:0,z:0},axis:{x:0,y:1,z:0}};
const world={body:'ground',origin:{x:0,y:0,z:0},rotation:{rx:0,ry:0,rz:0}};
const close=(a,b)=>assert(Math.abs(a-b)<1e-9,`${a} != ${b}`);

test('travel, toe and camber use the oriented axle and wheel centre',()=>{
 const rows=wheelHistory([{time:0,nodes:[node('wheel')]},{time:1,nodes:[node('wheel',{z:.1,rx:10})]},{time:2,nodes:[node('wheel',{z:.2,rz:5})]}],wheel,world);
 close(rows[1].travel,.1);close(rows[1].camber,10);close(rows[1].toe,0);close(rows[2].toe,5);close(rows[2].camber,0);
});
test('remove chassis motion and honor a rotated named frame',()=>{
 const samples=[{time:0,nodes:[node('chassis'),node('wheel',{x:1,y:0,z:1})]},{time:1,nodes:[node('chassis',{x:4,y:3,z:2,rz:90}),node('wheel',{x:4,y:4,z:3,rz:90})]}];
 const reference={body:'chassis',origin:{x:0,y:0,z:0},rotation:{rx:0,ry:0,rz:0}};
 const rows=wheelHistory(samples,wheel,reference);close(rows[1].travel,0);rows[1].position.forEach((v,i)=>close(v,rows[0].position[i]));close(rows[1].toe,0);
 const rotated=wheelHistory([samples[0]],{...wheel,axis:{x:1,y:0,z:0}},{...world,rotation:{rx:0,ry:0,rz:-90}})[0];close(rotated.toe,0);
});
test('vertical axle has undefined toe and is blank in CSV',()=>{
 const rows=wheelHistory([{time:0,nodes:[node('wheel',{rx:90})]}],wheel,world);assert.equal(rows[0].toe,null);close(rows[0].camber,90);assert(wheelCsv(rows,wheel,world,'body:chassis').trimEnd().endsWith(','));
 assert(wheelPlotBreak(179,-179,'toe'));assert(!wheelPlotBreak(179,-179,'camber'));assert(wheelPlotBreak(null,0,'toe'));
});
test('reject invalid axis, missing samples and unsafe CSV identity',()=>{
 assert.throws(()=>wheelHistory([{time:0,nodes:[node('wheel')]}],{...wheel,axis:{x:0,y:0,z:0}},world));
 assert.throws(()=>wheelHistory([{time:0,nodes:[]}],wheel,world));
 assert.throws(()=>wheelHistory([{time:0,nodes:[node('wheel')]},{time:0,nodes:[node('wheel')]}],wheel,world));
 assert.throws(()=>wheelCsv([],{...wheel,body:'=bad'},world,'ground'));
 assert.throws(()=>wheelHistory([{time:0,nodes:[node('wheel',{x:1e308}),node('chassis',{x:-1e308})]}],wheel,{...world,body:'chassis'}),/not finite/);
});
