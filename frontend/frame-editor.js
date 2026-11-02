import * as THREE from 'three';

const RAD=Math.PI/180;
let activeFrame=null, framesOpen=false;
const jointFrameSelections=new Map(), jointAxisSelections=new Map();

/** Express a frame's positive local axis in its parent body's axes (Euler123). */
export function frameAxis(frame, axis) {
  if(!['x','y','z'].includes(axis) || !frame?.rotation || !['rx','ry','rz'].every(key=>Number.isFinite(frame.rotation[key]) && Math.abs(frame.rotation[key])<=360))throw Error('Choose a valid frame rotation and axis.');
  const {rx,ry,rz}=frame.rotation, vector=new THREE.Vector3(axis==='x'?1:0,axis==='y'?1:0,axis==='z'?1:0);
  vector.applyEuler(new THREE.Euler(rx*RAD,ry*RAD,rz*RAD,'XYZ'));
  vector.normalize();return {x:Math.max(-1,Math.min(1,vector.x)),y:Math.max(-1,Math.min(1,vector.y)),z:Math.max(-1,Math.min(1,vector.z))};
}

/** Copy a named frame into one joint end; later frame edits do not change the joint. */
export function applyReferenceFrame(model, jointId, side, frameId, axis) {
  if(!['a','b'].includes(side))throw Error('Choose joint side A or B.');
  const frame=model.frames?.find(item=>item.id===frameId),joint=model.joints?.find(item=>item.id===jointId);
  if(!frame || !joint || frame.body!==joint[side])throw Error('Choose a reference frame belonging to this joint body.');
  if(!frame.translation || !['x','y','z'].every(key=>Number.isFinite(frame.translation[key]) && Math.abs(frame.translation[key])<=1000))throw Error('Enter a valid frame translation first.');
  const direction=frameAxis(frame,axis), suffix=side.toUpperCase();
  joint[`anchor${suffix}`]={...frame.translation};
  if(Object.hasOwn(joint,`axis${suffix}`))joint[`axis${suffix}`]=direction;
}

/** Find an explicit live link without changing legacy snapshot behavior. */
export function jointFrameLink(model,joint,side){return (model.frameLinks||[]).find(link=>link.joint===joint&&link.side===side);}

/** Synchronize linked joint fields after a frame edit. */
export function syncFrameLinks(model){for(const link of model.frameLinks||[])applyReferenceFrame(model,link.joint,link.side,link.frame,link.axis);}

/** Link one joint end and immediately set its physical snapshot. */
export function linkReferenceFrame(model,joint,side,frame,axis){
  applyReferenceFrame(model,joint,side,frame,axis);
  model.frameLinks??=[];model.frameLinks=model.frameLinks.filter(item=>item.joint!==joint||item.side!==side);
  model.frameLinks.push({joint,side,frame,axis});
}

function label(parent,title,input){const wrapper=document.createElement('label');wrapper.textContent=title;input.setAttribute('aria-label',title);wrapper.append(input);parent.append(wrapper);return input;}
function button(title,action){const result=document.createElement('button');result.type='button';result.className='secondary full-width';result.textContent=title;result.onclick=action;return result;}
function options(select,items,selected){select.replaceChildren(...items.map(item=>{const option=document.createElement('option');option.value=item.id;option.textContent=item.name;return option;}));select.value=selected;}

/** Manage project-local named frames; all coordinates use the selected parent's axes. */
export function renderFrameEditor({container,model,mutate,notify,pickFromCad}) {
  const list=model.frames||[],details=document.createElement('details');details.className='property-group solid-calculator';details.open=framesOpen;
  details.addEventListener('toggle',()=>{framesOpen=details.open;});
  const title=document.createElement('summary');title.textContent=`Named reference frames (${list.length})`;details.append(title);
  const info=document.createElement('p');info.textContent='Frames belong to a body or ground. A joint end can copy a frame or stay linked to it.';details.append(info);
  const content=document.createElement('div');details.append(content);container.append(details);
  const draw=()=>{
    content.replaceChildren();const frames=model.frames||[];
    if(!frames.some(item=>item.id===activeFrame))activeFrame=frames[0]?.id||null;
    const select=document.createElement('select');select.id='reference-frame-select';options(select,frames,activeFrame||'');select.disabled=!frames.length;
    label(content,'Reference frame',select);select.onchange=()=>{activeFrame=select.value;draw();};
    const frame=frames.find(item=>item.id===activeFrame);
    if(frame){
      const name=document.createElement('input');name.type='text';name.maxLength=120;name.value=frame.name;name.id='reference-frame-name';label(content,'Frame name',name);
      name.onchange=()=>mutate(next=>{next.frames.find(item=>item.id===frame.id).name=name.value;});
      const parent=document.createElement('select');parent.id='reference-frame-parent';options(parent,[{id:'ground',name:'Ground (world)'},...model.bodies],frame.body);label(content,'Frame parent',parent);
      parent.onchange=()=>{if((model.frameLinks||[]).some(link=>link.frame===frame.id)){parent.value=frame.body;return notify('Unlink this frame from its joints before changing its parent.');}mutate(next=>{next.frames.find(item=>item.id===frame.id).body=parent.value;});};
      for(const [category,components,unit] of [['translation',['x','y','z'],'m'],['rotation',['rx','ry','rz'],'°']])for(const component of components){
        const input=document.createElement('input');input.type='number';input.step='any';input.value=String(frame[category][component]);input.id=`reference-frame-${category}-${component}`;
        label(content,`Frame ${category} ${component.toUpperCase()} (${unit})`,input);
        input.onchange=()=>{const value=input.value.trim()===''?null:Number(input.value),linked=(model.frameLinks||[]).some(link=>link.frame===frame.id);try{if(linked){const candidate=structuredClone(model);candidate.frames.find(item=>item.id===frame.id)[category][component]=value;syncFrameLinks(candidate);}mutate(next=>{next.frames.find(item=>item.id===frame.id)[category][component]=value;if(linked)syncFrameLinks(next);});}catch(error){input.value=String(frame[category][component]);notify(error.message);}};
      }
      if(pickFromCad){const pick=button('Place from CAD feature…',()=>pickFromCad(frame.id));pick.id='reference-frame-pick';pick.title='Click an analytic face or circular rim. Cones use their apex, tori their centre; local +Z follows the feature axis or plane normal.';content.append(pick);}
      content.append(button('Remove reference frame',()=>{if((model.frameLinks||[]).some(link=>link.frame===frame.id))return notify('Unlink this frame from its joints before removing it.');activeFrame=null;mutate(next=>{next.frames=next.frames.filter(item=>item.id!==frame.id);});}));
    }
    const add=button('Add reference frame',()=>{
      if((model.frames||[]).length>=64)return notify('A project supports at most 64 reference frames.');
      let n=1;const ids=new Set((model.frames||[]).map(item=>item.id));while(ids.has(`frame${n}`))n++;
      const id=`frame${n}`;activeFrame=id;
      mutate(next=>{next.frames??=[];next.frames.push({id,name:`Frame ${n}`,body:next.bodies[0].id,translation:{x:0,y:0,z:0},rotation:{rx:0,ry:0,rz:0}});});
    });add.disabled=frames.length>=64;content.append(add);
  };
  draw();
}

/** Offer only frames owned by each joint side; copy frame origin and axis on Apply. */
export function renderJointFrameControls({container,model,joint,mutate,notify}) {
  const group=document.createElement('div');group.className='property-group solid-calculator';const title=document.createElement('h3');title.textContent='Apply named reference frame';group.append(title);
  const description=document.createElement('p');description.textContent='Copy a frame once, or link it so frame edits update this joint end. Unlink preserves its current anchor and axis.';group.append(description);
  for(const side of ['a','b']){
    const frames=(model.frames||[]).filter(frame=>frame.body===joint[side]);
    if(!frames.length)continue;
    const suffix=side.toUpperCase(),selectionKey=`${joint.id}:${side}`,select=document.createElement('select');select.id=`joint-frame-${side}`;
    const existing=jointFrameLink(model,joint.id,side);
    const selectedFrame=frames.some(frame=>frame.id===jointFrameSelections.get(selectionKey))?jointFrameSelections.get(selectionKey):(existing?.frame||frames[0].id);
    options(select,frames,selectedFrame);select.onchange=()=>jointFrameSelections.set(selectionKey,select.value);label(group,`Joint ${suffix} reference frame`,select);
    const axis=document.createElement('select');axis.id=`joint-frame-axis-${side}`;options(axis,['x','y','z'].map(key=>({id:key,name:`+${key.toUpperCase()}`})),jointAxisSelections.get(selectionKey)||existing?.axis||'y');axis.onchange=()=>jointAxisSelections.set(selectionKey,axis.value);
    if(Object.hasOwn(joint,`axis${suffix}`))label(group,`Joint ${suffix} frame axis`,axis);
    group.append(button(`Apply frame to joint ${suffix}`,()=>{if(existing)return notify('Unlink this joint end before applying a one-time frame snapshot.');try{applyReferenceFrame(structuredClone(model),joint.id,side,select.value,axis.value);mutate(next=>applyReferenceFrame(next,joint.id,side,select.value,axis.value));}catch(error){notify(error.message);}}));
    group.append(button(existing?`Update frame link on joint ${suffix}`:`Link frame to joint ${suffix}`,()=>{try{linkReferenceFrame(structuredClone(model),joint.id,side,select.value,axis.value);mutate(next=>linkReferenceFrame(next,joint.id,side,select.value,axis.value));}catch(error){notify(error.message);}}));
    if(existing){const current=document.createElement('p');current.textContent=`Linked to ${existing.frame} (+${existing.axis.toUpperCase()}).`;group.append(current);group.append(button(`Unlink frame from joint ${suffix}`,()=>mutate(next=>{next.frameLinks=next.frameLinks.filter(link=>link.joint!==joint.id||link.side!==side);})));}
  }
  if(!(model.frames||[]).some(frame=>frame.body===joint.a||frame.body===joint.b)){const empty=document.createElement('p');empty.textContent='Create a named frame on a connected body or ground first.';group.append(empty);}
  container.append(group);
}
