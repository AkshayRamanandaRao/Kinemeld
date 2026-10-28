// Actual MBDyn 1.7.3 solver samples from run ed5ae4b7c6c44534beeb215b3e62ed13.
const fixture = {"format":"mbdyn-studio/1","model":{"kind":"planar-assembly","name":"Authored rigid pendulum","parameters":{"gravity":0.0},"simulation":{"duration":2.0,"step":0.001},"bodies":[{"id":"upper_link","name":"Upper Link","mass":1.2,"inertia":{"xx":0.10009,"yy":0.10009,"zz":0.00018},"pose":{"x":0.06958655048003272,"z":-0.4951340343707852,"angleDeg":-8.0},"velocity":{"vx":-4.951340343707852,"vz":-0.6958655048003272,"omega":10.0}}],"joints":[{"id":"ground_pin","type":"revolute","parent":"ground","child":"upper_link","parentAnchor":{"x":0.0,"z":0.0},"childAnchor":{"x":0.0,"z":0.5}}],"loads":[{"id":"spin","body":"upper_link","fx":0.0,"fz":0.0,"torque":0.7}]},"result":{"ok":true,"source":"MBDyn","runId":"ed5ae4b7c6c44534beeb215b3e62ed13","model":{"kind":"planar-assembly","name":"Authored rigid pendulum","parameters":{"gravity":0.0},"simulation":{"duration":2.0,"step":0.001},"bodies":[{"id":"upper_link","name":"Upper Link","mass":1.2,"inertia":{"xx":0.10009,"yy":0.10009,"zz":0.00018},"pose":{"x":0.06958655048003272,"z":-0.4951340343707852,"angleDeg":-8.0},"velocity":{"vx":-4.951340343707852,"vz":-0.6958655048003272,"omega":10.0}}],"joints":[{"id":"ground_pin","type":"revolute","parent":"ground","child":"upper_link","parentAnchor":{"x":0.0,"z":0.0},"childAnchor":{"x":0.0,"z":0.5}}],"loads":[{"id":"spin","body":"upper_link","fx":0.0,"fz":0.0,"torque":0.7}]},"samples":[{"time":0.0,"nodes":[{"id":"upper_link","x":0.06958655048003,"y":0.0,"z":-0.4951340343708,"rx":-0.0,"ry":-8.0,"rz":0.0,"vx":-4.951340343708,"vy":0.0,"vz":-0.6958655048003,"wx":0.0,"wy":10.0,"wz":0.0,"label":1,"angleDeg":-8.0}],"loadStates":[{"id":"spin","power":7.0}],"loadPower":7.0,"appliedWork":0.0,"energy":20.004500000000856,"jointError":1.506900275940756e-14,"jointVelocityError":1.5079922756149846e-13},{"time":0.22,"nodes":[{"id":"upper_link","x":-0.4309649815835,"y":0.0,"z":0.2535136774392,"rx":-180.0,"ry":59.53397458799,"rz":180.0,"vx":2.632572486565,"vy":0.0,"vz":4.475308119948,"wx":0.0,"wy":10.38381743937,"wz":0.0,"label":1,"angleDeg":120.46602541201001}],"loadStates":[{"id":"spin","power":7.268672207559}],"loadPower":7.268672207559,"appliedWork":1.5694814534771573,"energy":21.571327694910785,"jointError":5.712345611112561e-14,"jointVelocityError":0.0002799059028200328}],"metrics":{"sampleCount":2,"duration":0.22}}};
import assert from 'node:assert/strict';
import {chromium} from 'playwright';
import {readFile,writeFile,mkdir} from 'node:fs/promises';
import {createHash} from 'node:crypto';
const base=process.env.MBDYN_STUDIO_URL || 'http://127.0.0.1:8768';
const browser=await chromium.launch({headless:true,args:['--enable-unsafe-swiftshader']});
const page=await browser.newPage({viewport:{width:1440,height:960}}),errors=[];
const report={checks:[],started:new Date().toISOString(),recordedRunId:fixture.result.runId};
page.on('pageerror',e=>errors.push(e.message));
try {
  await page.route('**/api/tour-preference',route=>route.fulfill({json:{enabled:false}}));
  await page.goto(base);await page.waitForFunction(()=>document.querySelector('#solverStatus')?.textContent.includes('MBDyn ready'));
  await page.evaluate(async()=>{
    const THREE=await import('three');const {MechanismView}=await import('/viewport.js');
    const original=MechanismView.prototype.setSample;
    MechanismView.prototype.setSample=function(sample){
      original.call(this,sample);
      if(this.stepView && sample){this.stepView.group.updateMatrixWorld(true);const mesh=[...this.stepView.partMeshes.values()][0];const q=new THREE.Quaternion();mesh.getWorldQuaternion(q);window.__rotationBranch={quaternion:q.toArray(),sample};}
    };
  });
  const bytes=await readFile('examples/step-pendulum/pendulum.step');
  const pose=fixture.model.bodies[0].pose;
  fixture.assets={step:{schemaVersion:1,format:'step',files:[{name:'pendulum.step',data:bytes.toString('base64'),sha256:createHash('sha256').update(bytes).digest('hex'),byteLength:bytes.length}],bindings:{'0:part-1':{body:'upper_link',pose:{x:pose.x,y:0,z:pose.z,ry:pose.angleDeg}}}}};
  const project=Buffer.from(JSON.stringify(fixture));
  page.on('dialog', dialog=>dialog.accept());await page.locator('#projectFile').setInputFiles({name:'actual-branch.mbdyn-studio',mimeType:'application/json',buffer:project});
  await page.waitForFunction(()=>document.querySelector('#notice')?.textContent.includes('Project imported and validated'),null,{timeout:60000});
  await page.locator('#timeSlider').fill('1');await page.locator('#timeSlider').dispatchEvent('input');
  const poseState=await page.evaluate(()=>window.__rotationBranch);
  const node=poseState.sample.nodes[0],actual=poseState.quaternion;
  assert(Math.abs(node.angleDeg-node.ry)>60,'Fixture must cross the Euler123 branch');
  const quat=angle=>[0,Math.sin(angle*Math.PI/360),0,Math.cos(angle*Math.PI/360)];
  const dot=(a,b)=>Math.abs(a.reduce((sum,value,index)=>sum+value*b[index],0));
  assert(dot(actual,quat(node.angleDeg-pose.angleDeg))>1-1e-9,'The STEP solid must use reconstructed planar angle');
  assert(dot(actual,quat(node.ry-pose.angleDeg))<0.95,'The STEP solid must not use ambiguous native Euler ry');
  report.checks.push('Real multi-turn MBDyn Euler branch drives the STEP world quaternion from angleDeg, not native ry');
  const invalid=structuredClone(fixture);delete invalid.result.samples[1].nodes[0].angleDeg;
  await page.locator('#projectFile').setInputFiles({name:'missing-angle.mbdyn-studio',mimeType:'application/json',buffer:Buffer.from(JSON.stringify(invalid))});
  await page.waitForFunction(()=>document.querySelector('#notice')?.textContent.includes('saved result is incomplete or unsupported'));
  assert.match(await page.locator('#resultSource').textContent(),/Saved result/);
  assert.equal(await page.locator('#timeSlider').inputValue(),'1');
  report.checks.push('A saved planar result missing angleDeg is rejected without replacing the open project');
  assert.deepEqual(errors,[]);report.ok=true;
}catch(e){report.ok=false;report.failure=e.stack;process.exitCode=1;console.error(e);await page.screenshot({path:'tests/evidence/step-rotation-branch-failure.png',fullPage:true}).catch(()=>{});}
finally{report.errors=errors;report.completed=new Date().toISOString();await mkdir('tests/evidence',{recursive:true});await writeFile('tests/evidence/step-rotation-branch-verification.json',JSON.stringify(report,null,2));await browser.close();}
