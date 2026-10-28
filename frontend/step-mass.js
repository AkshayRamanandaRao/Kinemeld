import * as THREE from 'three';

const same = (a,b) => JSON.stringify(a) === JSON.stringify(b);
const finite = Number.isFinite;
const hashBytes = async bytes => [...new Uint8Array(await crypto.subtle.digest('SHA-256',bytes))].map(n=>n.toString(16).padStart(2,'0')).join('');
const validWitness = witness => witness && typeof witness==='object' && !Array.isArray(witness) && (witness.scheme==='single-part/1' && Object.keys(witness).length===1 || witness.scheme==='step-nauo-id-path/1' && Object.keys(witness).length===2 && Array.isArray(witness.path) && witness.path.length>0 && witness.path.length<=32 && witness.path.every(id=>typeof id==='string' && id.length>0) && new TextEncoder().encode(JSON.stringify(witness)).length<=4096);
const sameWitness = (a,b) => !!a && !!b && a.scheme===b.scheme && (a.scheme==='single-part/1' || Array.isArray(a.path) && Array.isArray(b.path) && a.path.length===b.path.length && a.path.every((id,i)=>id===b.path[i]));

/** Capture the source, body registration and input density used for one calculation. */
export function captureStepMass(asset,model,partId,density) {
  if (!asset || !Array.isArray(asset.parts) || !asset.parts.some(part=>part.id===partId)) throw Error('Select an imported STEP part.');
  const match=/^(\d+):(part-[1-9]\d{0,2})$/.exec(partId);
  if(!match)throw Error('The selected STEP occurrence ID is invalid.');
  const file=asset.metadata?.files?.[Number(match[1])];
  if(!file || typeof file.data!=='string' || !/^[0-9a-f]{64}$/.test(file.sha256||'') || !Number.isInteger(file.byteLength) || file.byteLength<1 || file.byteLength>12*1024*1024) throw Error('The selected STEP source is invalid.');
  if(!finite(density)||density<=0||density>1e9)throw Error('Enter a density greater than zero and at most 1e9 kg/m³.');
  const sourceParts=asset.parts.filter(part=>part.id.startsWith(`${match[1]}:`));
  const witness=sourceParts.find(part=>part.id===partId)?.occurrenceWitness ?? null;
  if(sourceParts.length>1 && (!validWitness(witness) || witness.scheme==='single-part/1' || sourceParts.filter(part=>sameWitness(part.occurrenceWitness,witness)).length!==1)) throw Error('The STEP occurrence identity is missing or ambiguous; mass properties cannot be safely assigned.');
  if(witness && !validWitness(witness))throw Error('The STEP occurrence identity is invalid.');
  const binding=asset.metadata.bindings?.[partId] ?? null;
  const body=binding && model?.bodies?.find(item=>item.id===binding.body);
  return {partId, occurrence:match[2], witness:structuredClone(witness), density, file:structuredClone(file), binding:structuredClone(binding), body:body ? structuredClone(body) : null, kind:model?.kind};
}

/** Confirm a calculation still refers to the same source, registration, body and density. */
export function stepMassCurrent(snapshot,asset,model,partId,density) {
  try {
    const current=captureStepMass(asset,model,partId,density);
    return same(snapshot,current);
  } catch {return false;}
}

function validateResult(result,snapshot) {
  const tensor=result?.inertia, com=result?.centerOfMass;
  if(snapshot.witness && !sameWitness(snapshot.witness,result?.occurrenceWitness))throw Error('The STEP service returned a mismatched occurrence identity.');
  if(!result?.ok || result.format!=='step-mass/1' || result.sha256!==snapshot.file.sha256 || result.partId!==snapshot.occurrence || result.density!==snapshot.density || result.units?.length!=='m' || result.units?.volume!=='m^3' || result.units?.mass!=='kg' || result.units?.inertia!=='kg*m^2' || result.reference!=='world axes, inertia about centre of mass' || !finite(result.volume) || result.volume<=0 || !finite(result.mass) || result.mass<=0 || Math.abs(result.mass-result.volume*result.density)>Math.max(Number.MIN_VALUE,result.mass*1e-9) || ![com?.x,com?.y,com?.z].every(finite) || !Array.isArray(tensor) || tensor.length!==3 || tensor.some(row=>!Array.isArray(row)||row.length!==3||!row.every(finite))) throw Error('The STEP service returned invalid or mismatched mass properties.');
  const scale=Math.max(...tensor.flat().map(Math.abs));
  if(scale<=0 || tensor.some((row,i)=>row.some((value,j)=>Math.abs(value-tensor[j][i])>Math.max(Number.MIN_VALUE,scale*1e-9))))throw Error('The STEP inertia tensor is invalid or asymmetric.');
  const [a,b,c]=[tensor[0][0]/scale,tensor[1][1]/scale,tensor[2][2]/scale], x=tensor[0][1]/scale,y=tensor[0][2]/scale,z=tensor[1][2]/scale;
  if(a<=0||b<=0||c<=0||a*b-x*x<=0||a*b*c+2*x*y*z-a*z*z-b*y*y-c*x*x<=0)throw Error('The STEP inertia tensor is not positive definite.');
  return result;
}

/** Calculate one occurrence against the exact original STEP source. */
export async function calculateStepMass(snapshot, request=fetch) {
  let bytes;
  try {const raw=atob(snapshot.file.data);bytes=Uint8Array.from(raw,c=>c.charCodeAt(0));} catch {throw Error('The saved STEP source is not valid base64.');}
  if(bytes.length!==snapshot.file.byteLength || await hashBytes(bytes)!==snapshot.file.sha256)throw Error('The saved STEP source failed its integrity check.');
  const headers={'Content-Type':'application/step','X-Step-Density':String(snapshot.density),'X-Step-Part':snapshot.occurrence};
  if(snapshot.witness)headers['X-Step-Witness']=btoa(String.fromCharCode(...new TextEncoder().encode(JSON.stringify(snapshot.witness))));
  const response=await request('/api/step/mass',{method:'POST',headers,body:bytes});
  let result;try{result=await response.json();}catch{throw Error('The STEP mass service returned an unreadable response.');}
  if(!response.ok || !result.ok)throw Error(result.error || 'STEP mass calculation failed.');
  return validateResult(result,snapshot);
}

/** Transform one occurrence's center and COM inertia into the registered body frame. */
function localStepProperties(snapshot,result) {
  validateResult(result,snapshot);
  const p=snapshot.binding?.pose;
  if(!p || ![p.x,p.y,p.z,p.ry].every(finite) || Object.hasOwn(p,'rx')!==Object.hasOwn(p,'rz') || (Object.hasOwn(p,'rx') && ![p.rx,p.rz].every(finite)))throw Error('The STEP body registration pose is invalid.');
  const rad=Math.PI/180, r=new THREE.Matrix3().setFromMatrix4(new THREE.Matrix4().makeRotationFromEuler(new THREE.Euler((p.rx||0)*rad,p.ry*rad,(p.rz||0)*rad,'XYZ'))), rt=r.clone().transpose();
  const com=new THREE.Vector3(result.centerOfMass.x-p.x,result.centerOfMass.y-p.y,result.centerOfMass.z-p.z).applyMatrix3(rt);
  const tensor=new THREE.Matrix3().set(...result.inertia.flat()).premultiply(rt).multiply(r).elements;
  return {mass:result.mass,center:[com.x,com.y,com.z],inertia:[[tensor[0],tensor[3],tensor[6]],[tensor[1],tensor[4],tensor[7]],[tensor[2],tensor[5],tensor[8]]]};
}

function proposalFromLocal(bodyId,kind,properties) {
  if(!properties.center.every(finite))throw Error('The STEP centre of mass is invalid.');
  if(kind==='planar-assembly' && Math.hypot(...properties.center)>1e-8)throw Error('The STEP centre of mass does not coincide with the planar body origin (tolerance 1e-8 m).');
  const m=properties.inertia, diagonal=[m[0][0],m[1][1],m[2][2]], scale=Math.max(...diagonal.map(Math.abs));
  if(!finite(properties.mass) || properties.mass<=0 || !diagonal.every(value=>finite(value)&&value>0) || !finite(scale))throw Error('The STEP mass or inertia is invalid.');
  const off=[(m[0][1]+m[1][0])/2,(m[0][2]+m[2][0])/2,(m[1][2]+m[2][1])/2];
  if(!off.every(finite))throw Error('The STEP inertia tensor is invalid.');
  const tolerance=scale*1e-8;
  if(kind==='planar-assembly' && off.some(value=>Math.abs(value)>tolerance))throw Error('The STEP inertia tensor is not diagonal in the body axes; use a spatial body or reorient the body.');
  const inertia={xx:diagonal[0],yy:diagonal[1],zz:diagonal[2]};
  if(kind==='spatial-assembly')for(const [index,key] of ['xy','xz','yz'].entries())inertia[key]=off[index];
  return {bodyId,mass:properties.mass,inertia,...(kind==='spatial-assembly'?{centerOfMass:Object.fromEntries(['x','y','z'].map((key,i)=>[key,properties.center[i]]))}:{})};
}

/** Convert a calculated world tensor to an eligible attached body's local axes. */
export function proposeStepMass(snapshot,asset,model,partId,density,result) {
  if(!stepMassCurrent(snapshot,asset,model,partId,density))throw Error('The selected source, binding, body or density changed; calculate again.');
  if(!['planar-assembly','spatial-assembly'].includes(model?.kind)||!snapshot.binding||!snapshot.body)throw Error('Attach this STEP part to an editable body before applying.');
  if(Object.values(asset.metadata.unverifiedBindings || {}).some(item=>item?.body===snapshot.binding.body))throw Error('Review this body’s unverified STEP attachments before applying mass properties.');
  if(Object.values(asset.metadata.bindings).filter(item=>item?.body===snapshot.binding.body).length!==1)throw Error('This body has multiple STEP parts attached; calculate their combined properties before applying.');
  return proposalFromLocal(snapshot.binding.body,model.kind,localStepProperties(snapshot,result));
}

/** Capture every occurrence attached to the selected body, using one explicit density. */
export function captureBodyStepMass(asset,model,partId,density) {
  const selected=captureStepMass(asset,model,partId,density);
  if(!['planar-assembly','spatial-assembly'].includes(model?.kind)||!selected.binding||!selected.body)throw Error('Attach the selected STEP part to an editable body first.');
  if(Object.values(asset.metadata.unverifiedBindings || {}).some(item=>item?.body===selected.binding.body))throw Error('Review this body’s unverified STEP attachments before calculating combined mass.');
  const ids=Object.entries(asset.metadata.bindings).filter(([,binding])=>binding?.body===selected.binding.body).map(([id])=>id).sort();
  if(!ids.length || ids.length>256)throw Error('The attached body must have between 1 and 256 STEP occurrences.');
  return {bodyId:selected.binding.body,kind:model.kind,partId,density,items:ids.map(id=>captureStepMass(asset,model,id,density))};
}

/** Check that neither the attachment set nor its registered frames have changed. */
export function bodyStepMassCurrent(snapshot,asset,model,partId,density) {
  try{return same(snapshot,captureBodyStepMass(asset,model,partId,density));}catch{return false;}
}

/** Combine per-occurrence properties in body coordinates, using the parallel-axis theorem. */
export function combineBodyStepMass(snapshot,results) {
  if(!Array.isArray(results)||results.length!==snapshot.items.length)throw Error('Every attached STEP occurrence must have a mass result.');
  const parts=snapshot.items.map((item,index)=>localStepProperties(item,results[index]));
  const mass=parts.reduce((sum,item)=>sum+item.mass,0);
  if(!finite(mass)||mass<=0)throw Error('The combined STEP mass is invalid.');
  const center=[0,1,2].map(axis=>parts.reduce((sum,item)=>sum+item.mass*item.center[axis],0)/mass);
  const inertia=Array.from({length:3},()=>[0,0,0]);
  for(const part of parts){
    const d=part.center.map((value,index)=>value-center[index]),distance=d.reduce((sum,value)=>sum+value*value,0);
    for(let i=0;i<3;i++)for(let j=0;j<3;j++)inertia[i][j]+=part.inertia[i][j]+part.mass*((i===j?distance:0)-d[i]*d[j]);
  }
  if(!center.every(finite)||inertia.some(row=>!row.every(finite)))throw Error('The combined STEP properties are not finite.');
  return {mass,center,inertia};
}

/** Validate the composite against the current body and derive its editable properties. */
export function proposeBodyStepMass(snapshot,asset,model,partId,density,results) {
  if(!bodyStepMassCurrent(snapshot,asset,model,partId,density))throw Error('The attached sources, registration, body or density changed; calculate again.');
  return proposalFromLocal(snapshot.bodyId,snapshot.kind,combineBodyStepMass(snapshot,results));
}

/** Bind calculator controls; the owner supplies state, validation and atomic commit. */
export function setupStepMass({getState,validateModel,applyCandidate,notify}) {
  const byId=id=>document.getElementById(id), density=()=>{const raw=byId('stepMassDensity').value.trim();return raw?Number(raw):NaN;};
  let calculated=null, serial=0;
  const clear=()=>{serial++;calculated=null;byId('stepMassApply').disabled=true;byId('stepMassResult').textContent='No calculation yet.';};
  byId('stepPart').addEventListener('change',clear);byId('stepMassDensity').addEventListener('input',clear);
  byId('stepMassCalculate').onclick=async()=>{
    const current=getState();if(current.busy)return notify('Wait for the active simulation before calculating mass.','warn');
    const token=++serial;calculated=null;byId('stepMassApply').disabled=true;
    try {
      const snapshot=captureStepMass(current.asset,current.model,current.partId,density());
      byId('stepMassResult').textContent='Calculating STEP mass properties…';
      const result=await calculateStepMass(snapshot);const next=getState();
      if(token!==serial)return;
      if(!stepMassCurrent(snapshot,next.asset,next.model,next.partId,density()))throw Error('The selected source, binding, body or density changed; calculate again.');
      calculated={mode:"part",snapshot,result};const number=x=>Number(x).toPrecision(7);
      byId('stepMassResult').textContent=`Volume: ${number(result.volume)} m³\nMass: ${number(result.mass)} kg\nCentre of mass, STEP world (m): ${[result.centerOfMass.x,result.centerOfMass.y,result.centerOfMass.z].map(number).join(', ')}\nInertia about COM, STEP world (kg·m²):\n${result.inertia.map(row=>row.map(number).join('  ')).join('\n')}`;
      try{proposeStepMass(snapshot,next.asset,next.model,next.partId,density(),result);byId('stepMassApply').disabled=false;}catch(error){byId('stepMassResult').textContent+=`\n\nCannot apply: ${error.message}`;}
    } catch(error){if(token===serial){byId('stepMassResult').textContent=error.message;notify(error.message,'warn');}}
  };
  byId('stepMassCalculateBody').onclick=async()=>{
    const current=getState();if(current.busy)return notify('Wait for the active simulation before calculating mass.','warn');
    const token=++serial;calculated=null;byId('stepMassApply').disabled=true;
    try {
      const snapshot=captureBodyStepMass(current.asset,current.model,current.partId,density()),results=[];
      byId('stepMassResult').textContent=`Calculating ${snapshot.items.length} attached STEP occurrences…`;
      for(const item of snapshot.items){
        results.push(await calculateStepMass(item));
        const next=getState();if(token!==serial)return;
        if(!bodyStepMassCurrent(snapshot,next.asset,next.model,next.partId,density()))throw Error('The attached sources, registration, body or density changed; calculate again.');
      }
      const next=getState(),combined=combineBodyStepMass(snapshot,results),number=x=>Number(x).toPrecision(7);
      calculated={mode:'body',snapshot,result:results};
      byId('stepMassResult').textContent=`Combined occurrences: ${results.length}\nMass: ${number(combined.mass)} kg\nCentre of mass, body axes (m): ${combined.center.map(number).join(', ')}\nInertia about COM, body axes (kg·m²):\n${combined.inertia.map(row=>row.map(number).join('  ')).join('\n')}\n\nA single density is used for all parts. Overlapping solids are counted more than once.`;
      try{proposeBodyStepMass(snapshot,next.asset,next.model,next.partId,density(),results);byId('stepMassApply').disabled=false;}catch(error){byId('stepMassResult').textContent+=`\n\nCannot apply: ${error.message}`;}
    } catch(error){if(token===serial){byId('stepMassResult').textContent=error.message;notify(error.message,'warn');}}
  };
  byId('stepMassApply').onclick=async()=>{
    if(!calculated)return;
    const {mode,snapshot,result}=calculated, token=serial;
    const currentProposal=next=>mode === "body" ? proposeBodyStepMass(snapshot,next.asset,next.model,next.partId,density(),result) : proposeStepMass(snapshot,next.asset,next.model,next.partId,density(),result);
    const isCurrent=next=>mode === "body" ? bodyStepMassCurrent(snapshot,next.asset,next.model,next.partId,density()) : stepMassCurrent(snapshot,next.asset,next.model,next.partId,density());
    try {
      const current=getState();if(current.busy)throw Error('Wait for the active simulation before editing the model.');
      const proposal=currentProposal(current), before=JSON.stringify(current.model);
      const candidate=structuredClone(current.model), body=candidate.bodies.find(item=>item.id===proposal.bodyId);body.mass=proposal.mass;body.inertia=proposal.inertia;if(proposal.centerOfMass)body.centerOfMass=proposal.centerOfMass;
      byId('stepMassApply').disabled=true;
      const check=await validateModel(candidate);const after=getState();
      if(!check.valid)throw Error((check.issues||[]).map(issue=>issue.message).join(' ') || 'The calculated body properties are invalid.');
      if(token!==serial || after.busy || JSON.stringify(after.model)!==before || !isCurrent(after))throw Error('The model or STEP selection changed during validation; no mass properties were applied.');
      if(applyCandidate(candidate)===false)throw Error('The model could not be updated.');
      clear();notify('Applied the STEP mass and inertia to the attached body.');
    }catch(error){if(token===serial){const next=getState();try{currentProposal(next);byId('stepMassApply').disabled=Boolean(next.busy);}catch{byId('stepMassApply').disabled=true;}byId('stepMassResult').textContent+=`\n\n${error.message}`;notify(error.message,'warn');}}
  };
  return {clear};
}
