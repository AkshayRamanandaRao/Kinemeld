import * as THREE from 'three';
import {pointState} from './point-probe.js';

const keys=['x','y','z'], rad=Math.PI/180;
const vec=v=>new THREE.Vector3(...keys.map(k=>v[k]));
function rotation(sample,body) {
  if(body==='ground')return new THREE.Quaternion();
  const node=sample.nodes?.find(n=>n.id===body);
  if(!node||!['rx','ry','rz'].every(k=>Number.isFinite(node[k])))throw Error(`Missing orientation for body ${body}.`);
  return new THREE.Quaternion().setFromEuler(new THREE.Euler(node.rx*rad,node.ry*rad,node.rz*rad,'XYZ'));
}
function finiteVector(v,max){return v&&keys.every(k=>Number.isFinite(v[k])&&Math.abs(v[k])<=max);}

/** Express a wheel centre and oriented axle in a ground- or body-fixed vehicle frame. */
export function wheelHistory(samples,wheel,reference) {
  if(!Array.isArray(samples)||!samples.length||samples.length>2001)throw Error('A spatial result needs 1–2001 displayed samples.');
  if(!wheel||wheel.body==='ground'||typeof wheel.body!=='string'||!finiteVector(wheel.center,1000)||!finiteVector(wheel.axis,1e6)||vec(wheel.axis).length()<1e-12)throw Error('Choose a wheel body, finite centre and nonzero axle direction.');
  if(!reference||typeof reference.body!=='string'||!finiteVector(reference.origin,1000)||!reference.rotation||!['rx','ry','rz'].every(k=>Number.isFinite(reference.rotation[k])&&Math.abs(reference.rotation[k])<=360))throw Error('Choose a valid vehicle reference frame.');
  const relativeFrame=new THREE.Quaternion().setFromEuler(new THREE.Euler(reference.rotation.rx*rad,reference.rotation.ry*rad,reference.rotation.rz*rad,'XYZ'));
  let last=-Infinity,initialZ;
  return samples.map(sample=>{
    if(!Number.isFinite(sample.time)||sample.time<=last)throw Error('Solver sample times must increase.');last=sample.time;
    const wheelPosition=new THREE.Vector3(...pointState(sample,{body:wheel.body,point:wheel.center}).position);
    const origin=new THREE.Vector3(...pointState(sample,{body:reference.body,point:reference.origin}).position);
    const inverse=rotation(sample,reference.body).multiply(relativeFrame).invert();
    const position=wheelPosition.sub(origin).applyQuaternion(inverse);
    const axle=vec(wheel.axis).normalize().applyQuaternion(rotation(sample,wheel.body)).applyQuaternion(inverse).normalize();
    const horizontal=Math.hypot(axle.x,axle.y);
    if(initialZ===undefined)initialZ=position.z;
    // shortcut: near a vertical axle toe is undefined, use another orientation representation if this configuration matters.
    const toe=horizontal<1e-10?null:Math.atan2(-axle.x,axle.y)/rad;
    const travel=position.z-initialZ,camber=Math.atan2(axle.z,horizontal)/rad;
    if(![...position.toArray(),...axle.toArray(),travel,camber,...(toe===null?[]:[toe])].every(Number.isFinite))throw Error('Calculated wheel kinematics are not finite.');
    return {time:sample.time,position:position.toArray(),axle:axle.toArray(),travel,camber,toe};
  });
}

/** Export calculated displayed samples without spreadsheet formulas or text from the model. */
export function wheelCsv(rows,wheel,reference,referenceId) {
  if(!/^[A-Za-z][A-Za-z0-9_-]{0,31}$/.test(wheel.body)||!(/^(body|frame):[A-Za-z][A-Za-z0-9_-]{0,31}$/.test(referenceId)||referenceId==='ground'))throw Error('Invalid body or reference identity.');
  if(!/^[A-Za-z][A-Za-z0-9_-]{0,31}$/.test(reference.body))throw Error('Invalid reference parent.');
  return 'time_s,wheel_body,reference,reference_parent,reference_origin_x_m,reference_origin_y_m,reference_origin_z_m,reference_rx_deg,reference_ry_deg,reference_rz_deg,center_local_x_m,center_local_y_m,center_local_z_m,axle_local_x,axle_local_y,axle_local_z,center_frame_x_m,center_frame_y_m,center_frame_z_m,axle_frame_x,axle_frame_y,axle_frame_z,vertical_travel_m,camber_deg,toe_deg\n'+rows.map(r=>[r.time,wheel.body,referenceId,reference.body,...keys.map(k=>reference.origin[k]),...['rx','ry','rz'].map(k=>reference.rotation[k]),...keys.map(k=>wheel.center[k]),...keys.map(k=>wheel.axis[k]),...r.position,...r.axle,r.travel,r.camber,r.toe??''].join(',')).join('\n')+'\n';
}

/** Identify discontinuities where a principal toe angle crosses the ±180° boundary. */
export function wheelPlotBreak(previous,current,quantity){return previous===null||current===null||(quantity==='toe'&&Math.abs(current-previous)>180);}

/** Install a non-mutating suspension measurement for current spatial MBDyn results. */
export function setupWheelKinematics({getResult,getModel,getBindings=()=>({}),getFrame=()=>0,isStale=()=>false,notify}) {
  const button=document.createElement('button');button.id='wheelKinematicsButton';button.type='button';button.className='text-button';button.textContent='Wheel kinematics';document.querySelector('#csvButton').before(button);
  const dialog=document.createElement('dialog');dialog.id='wheelKinematicsDialog';dialog.setAttribute('aria-labelledby','wheelKinematicsTitle');
  const head=document.createElement('div');head.className='dialog-heading';head.innerHTML='<h2 id="wheelKinematicsTitle">Wheel kinematics</h2>';
  const close=document.createElement('button');close.type='button';close.className='icon-button';close.setAttribute('aria-label','Close wheel kinematics');close.textContent='×';close.onclick=()=>dialog.close();head.append(close);dialog.append(head);
  const intro=document.createElement('p');intro.textContent='Vehicle frame: X forward, Y left, Z up. Enter the wheel centre and an axle direction pointing toward vehicle +Y, in wheel-body axes. Travel is relative to the first displayed sample. Results use displayed samples and are not a tire or K&C rig model.';dialog.append(intro);
  const grid=document.createElement('div');grid.style.display='grid';grid.style.gridTemplateColumns='repeat(auto-fit,minmax(225px,1fr))';grid.style.gap='14px';dialog.append(grid);
  const actions=document.createElement('div');actions.className='step-actions';const calculate=document.createElement('button');calculate.type='button';calculate.className='primary';calculate.id='wheelKinematicsCalculate';calculate.textContent='Calculate wheel kinematics';const exportButton=document.createElement('button');exportButton.type='button';exportButton.className='secondary';exportButton.id='wheelKinematicsExport';exportButton.textContent='Export displayed samples CSV';exportButton.disabled=true;actions.append(calculate,exportButton);dialog.append(actions);
  const status=document.createElement('p');status.id='wheelKinematicsStatus';status.setAttribute('role','status');status.style.whiteSpace='pre-line';dialog.append(status);
  const signal=document.createElement('select');signal.id='wheelKinematicsSignal';signal.setAttribute('aria-label','Wheel kinematics plot quantity');for(const [value,label] of [['travel','Vertical travel (m)'],['camber','Camber (°)'],['toe','Toe (°)']]){const option=document.createElement('option');option.value=value;option.textContent=label;signal.append(option);}dialog.append(signal);
  const plot=document.createElement('div');plot.id='wheelKinematicsPlot';plot.setAttribute('role','img');plot.setAttribute('aria-label','Wheel kinematics plot. Calculate to show data.');dialog.append(plot);document.body.append(dialog);
  let source,snapshot,bindings,rows,wheel,reference,referenceId,read;
  const current=()=>source===getResult()&&JSON.stringify(getModel())===snapshot&&JSON.stringify(getBindings())===bindings&&!isStale();
  function clear(){rows=null;exportButton.disabled=true;plot.replaceChildren();plot.setAttribute('aria-label','Wheel kinematics plot. Calculate to show data.');status.textContent='Inputs changed; calculate again.';}
  function field(parent,title,control){const label=document.createElement('label');label.textContent=title;control.setAttribute('aria-label',title);label.append(control);parent.append(label);}
  function draw(){
    plot.replaceChildren();if(!rows)return;const valid=rows.filter(r=>r[signal.value]!==null);if(!valid.length){plot.setAttribute('aria-label','Quantity undefined for all displayed samples.');return;}
    const values=valid.map(r=>r[signal.value]),lo=Math.min(...values),hi=Math.max(...values),pad=Math.max((hi-lo)*.05,Math.max(Math.abs(lo),Math.abs(hi),1)*5e-7),bottom=lo-pad,top=hi+pad,start=rows[0].time,end=rows.at(-1).time;
    let previous=null;const path=rows.map(r=>{const value=r[signal.value];if(value===null){previous=null;return '';}const x=40+620*(r.time-start)/(end-start||1),y=120-95*(value-bottom)/(top-bottom),p=`${wheelPlotBreak(previous,value,signal.value)?'M':'L'}${x},${y}`;previous=value;return p;}).join(' ');
    const unit=signal.value==='travel'?'m':'°';plot.innerHTML=`<svg viewBox="0 0 680 160" aria-hidden="true"><path d="M40 20V120H660" fill="none" stroke="currentColor"/><path d="${path}" fill="none" stroke="#2678da" stroke-width="2"/><text x="40" y="155" font-size="12">${start.toPrecision(4)} s</text><text x="600" y="155" font-size="12">${end.toPrecision(4)} s</text><text x="46" y="18" font-size="12">${top.toPrecision(6)} ${unit}</text><text x="46" y="136" font-size="12">${bottom.toPrecision(6)} ${unit}</text></svg>`;plot.setAttribute('aria-label',`${signal.value} from ${lo.toPrecision(6)} to ${hi.toPrecision(6)} ${unit}; ${valid.length} defined samples.`);
  }
  signal.onchange=draw;
  button.onclick=()=>{
    const model=getModel(),result=getResult();if(!result||result.source!=='MBDyn'||result.model?.kind!=='spatial-assembly'||model?.kind!=='spatial-assembly'||isStale()){notify('Run or reopen a current spatial MBDyn result before measuring wheel kinematics.','warn');return;}
    source=result;snapshot=JSON.stringify(model);bindings=JSON.stringify(getBindings());grid.replaceChildren();clear();
    const inputs=document.createElement('fieldset');inputs.className='solid-calculator';inputs.style.padding='10px';inputs.innerHTML='<legend>Wheel body</legend>';grid.append(inputs);
    const body=document.createElement('select');body.id='wheelKinematicsBody';for(const b of model.bodies){const o=document.createElement('option');o.value=b.id;o.textContent=b.name;body.append(o);}field(inputs,'Wheel body',body);body.onchange=clear;
    const coords={};for(const [kind,defaults] of [['center',[0,0,0]],['axis',[0,1,0]]]){coords[kind]={};keys.forEach((k,i)=>{const input=document.createElement('input');input.type='number';input.step='any';input.value=String(defaults[i]);input.id=`wheelKinematics-${kind}-${k}`;input.oninput=clear;field(inputs,`${kind==='center'?'Wheel centre':'Axle direction'} ${k.toUpperCase()}${kind==='center'?' (m)':''}`,input);coords[kind][k]=input;});}
    const frameBox=document.createElement('fieldset');frameBox.className='solid-calculator';frameBox.style.padding='10px';frameBox.innerHTML='<legend>Vehicle reference frame</legend>';grid.append(frameBox);
    const reference=document.createElement('select');reference.id='wheelKinematicsReference';const choices=[{id:'ground',name:'Ground · world axes',body:'ground',translation:{x:0,y:0,z:0},rotation:{rx:0,ry:0,rz:0}},...model.bodies.map(b=>({id:`body:${b.id}`,name:`${b.name} · body axes`,body:b.id,translation:{x:0,y:0,z:0},rotation:{rx:0,ry:0,rz:0}})),...(model.frames||[]).map(f=>({...f,id:`frame:${f.id}`}))];for(const f of choices){const o=document.createElement('option');o.value=f.id;o.textContent=f.name;reference.append(o);}field(frameBox,'Reference frame',reference);reference.onchange=clear;
    const info=document.createElement('p');info.textContent='Select a chassis-fixed body or named frame to remove chassis translation and rotation. For a named frame, its origin and orientation are used.';frameBox.append(info);
    read=()=>{const selected=choices.find(f=>f.id===reference.value);if(!selected)throw Error('Choose a reference frame.');return {wheel:{body:body.value,...Object.fromEntries(['center','axis'].map(kind=>[kind,Object.fromEntries(keys.map(k=>[k,coords[kind][k].value.trim()===''?NaN:Number(coords[kind][k].value)]))]))},reference:{body:selected.body,origin:selected.translation,rotation:selected.rotation},id:selected.id};};
    status.textContent='Choose the wheel and vehicle frame, then calculate.';dialog.showModal();
  };
  calculate.onclick=()=>{try{if(!current())throw Error('The model, STEP bindings, or result changed; close and reopen this tool.');const selection=read();wheel=selection.wheel;reference=selection.reference;referenceId=selection.id;rows=wheelHistory(source.samples,wheel,reference);const row=rows[Math.max(0,Math.min(getFrame(),rows.length-1))],format=n=>n===null?'undefined':n.toPrecision(6);status.textContent=`At ${format(row.time)} s: vertical travel ${format(row.travel)} m; camber ${format(row.camber)}°; toe ${format(row.toe)}°. ${rows.length} displayed samples.\nCentre in vehicle frame: (${row.position.map(format).join(', ')}) m. Axle: (${row.axle.map(format).join(', ')}).`;exportButton.disabled=false;draw();}catch(error){clear();status.textContent=error.message;}};
  exportButton.onclick=()=>{try{if(!rows||!current())throw Error('The model, STEP bindings, or result changed; calculate again.');const url=URL.createObjectURL(new Blob([wheelCsv(rows,wheel,reference,referenceId)],{type:'text/csv'})),a=document.createElement('a');a.href=url;a.download='wheel-kinematics-displayed-samples.csv';a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);}catch(error){clear();status.textContent=error.message;}};
}
