import { renderSolidEditor } from "./solid-editor.js";

const RAD = Math.PI / 180;

function rotate(point, angle) {
  const c = Math.cos(angle * RAD), s = Math.sin(angle * RAD);
  return {x:c * point.x + s * point.z, z:-s * point.x + c * point.z};
}
function world(body, local) {
  if (!body) return {...local};
  const r = rotate(local,body.pose.angleDeg);
  return {x:body.pose.x+r.x,z:body.pose.z+r.z};
}
function inverse(body, point) {
  if (!body) return {...point};
  return rotate({x:point.x-body.pose.x,z:point.z-body.pose.z},-body.pose.angleDeg);
}

/** Create display-only origin/joint metadata; solver geometry remains in the graph. */
export function assemblyInfo(model) {
  const nodes = model.bodies.map(body => ({id:body.id,label:body.name}));
  const initialNodes = model.bodies.map(body => ({id:body.id,x:body.pose.x,y:0,z:body.pose.z,rx:0,ry:body.pose.angleDeg,rz:0,
    vx:body.velocity.vx,vy:0,vz:body.velocity.vz,wx:0,wy:body.velocity.omega,wz:0}));
  const connections = [];
  for (const joint of model.joints) {
    if (joint.parent === "ground") {
      const id = `fixed-${joint.id}`;
      initialNodes.push({id,label:`Ground · ${joint.id}`,x:joint.parentAnchor.x,y:0,z:joint.parentAnchor.z,rx:0,ry:0,rz:0,vx:0,vy:0,vz:0,wx:0,wy:0,wz:0});
      connections.push({id:joint.id,from:id,to:joint.child,label:joint.type === "prismatic" ? "Prismatic slider" : "Revolute hinge"});
    } else connections.push({id:joint.id,from:joint.parent,to:joint.child,label:joint.type === "prismatic" ? "Prismatic slider" : "Revolute hinge"});
  }
  for (const force of model.forces || []) {
    const endpoint=(id,anchor,side)=>{
      if (id !== "ground") return id;
      const marker=`fixed-force-${force.id}-${side}`;
      initialNodes.push({id:marker,label:`Ground · ${force.id}`,x:anchor.x,y:0,z:anchor.z,rx:0,ry:0,rz:0,vx:0,vy:0,vz:0,wx:0,wy:0,wz:0});
      return marker;
    };
    connections.push({id:force.id,entity:`force-${force.id}`,from:endpoint(force.a,force.anchorA,"a"),to:endpoint(force.b,force.anchorB,"b"),label:"Spring / damper · schematic"});
  }
  return {nodes,initialNodes,connections,visualizationNote:"Lines join body origins and ground anchors as a schematic; they are not exact solid geometry."};
}

function entityBody(model,selection) {
  if (selection === "body") return model.bodies[0];
  if (selection.startsWith("node-")) return model.bodies.find(body => `node-${body.id}` === selection);
  return null;
}
function entityJoint(model,selection) {
  return model.joints.find(joint => `joint-${joint.id}` === selection) || null;
}
function entityForce(model,selection) {
  return (model.forces || []).find(force => `force-${force.id}` === selection) || null;
}
function entityLoad(model,selection) {
  return (model.loads || []).find(load => `applied-${load.id}` === selection) || null;
}
function jointChoice(section, model, current, label, change) {
  const wrapper=document.createElement("label");wrapper.textContent=label;
  const select=document.createElement("select");select.setAttribute("aria-label",label);
  for(const joint of model.joints.filter(item=>item.type==="revolute")) {
    const option=document.createElement("option");option.value=joint.id;option.textContent=`${joint.id} · ${joint.parent} → ${joint.child}`;select.append(option);
  }
  select.value=current;select.onchange=()=>change(select.value);wrapper.append(select);section.append(wrapper);
  return select;
}
function descendants(model,id) {
  const found = new Set([id]);
  let size;
  do { size=found.size; for (const joint of model.joints) if (found.has(joint.parent)) found.add(joint.child); } while (size !== found.size);
  return found;
}
function inputRow(container,label,unit,value,change,step="0.01", id="") {
  const row=document.createElement("label"); row.textContent=label;
  const wrapper=document.createElement("span"); wrapper.className="number-field";
  const input=document.createElement("input"); input.type="number"; input.step=step;
  input.value=value ?? ""; input.setAttribute("aria-label",label);
  if (id) input.id=id;
  input.onchange=()=>change(input.value.trim()==="" ? null : Number(input.value));
  const suffix=document.createElement("span"); suffix.textContent=unit;
  wrapper.append(input,suffix); row.append(wrapper); container.append(row);
}
function group(container,title) {
  const section=document.createElement("div"); section.className="property-group";
  const heading=document.createElement("h3"); heading.textContent=title; section.append(heading); container.append(section); return section;
}

/** Build body and hinge controls for the supported rooted-tree assembly. */
export function renderAssemblyEditor({container,model,selection,mutate,notify,createSolid}) {
  const body=entityBody(model,selection), joint=entityJoint(model,selection), force=entityForce(model,selection), appliedLoad=entityLoad(model,selection);
  const rotary=(model.rotationalElements || []).find(item=>`rotary-${item.id}`===selection);
  const torque=(model.jointTorques || []).find(item=>`torque-${item.id}`===selection);
  if (body) {
    const section=group(container,`Body · ${body.id}`);
    const nameLabel=document.createElement("label"); nameLabel.textContent="Body name";
    const name=document.createElement("input"); name.type="text"; name.maxLength=80; name.value=body.name;
    name.setAttribute("aria-label","Body name"); name.onchange=()=>mutate(next=>{next.bodies.find(item=>item.id===body.id).name=name.value;});
    nameLabel.append(name);section.append(nameLabel);
    const fields=[
      ["Mass","kg",["mass"],"0.1"],["Inertia Ixx","kg·m²",["inertia","xx"],"0.001"],
      ["Inertia Iyy","kg·m²",["inertia","yy"],"0.001"],["Inertia Izz","kg·m²",["inertia","zz"],"0.001"],
      ["Initial X","m",["pose","x"],"0.01"],["Initial Z","m",["pose","z"],"0.01"],["Initial angle about Y","°",["pose","angleDeg"],"1"],
      ["Initial velocity X","m/s",["velocity","vx"],"0.01"],["Initial velocity Z","m/s",["velocity","vz"],"0.01"],
      ["Initial angular velocity Y","rad/s",["velocity","omega"],"0.01"],
    ];
    for (const [title,unit,path,step] of fields) {
      const value=path.length===1 ? body[path[0]] : body[path[0]][path[1]];
      inputRow(section,title,unit,value,number=>mutate(next=>{
        const selected=next.bodies.find(item=>item.id===body.id);
        if (path.length===1) selected[path[0]]=number; else selected[path[0]][path[1]]=number;
      }),step,`graph-body-${body.id}-${path.join("-")}`);
    }
    const remove=document.createElement("button"); remove.className="secondary full-width";remove.type="button";remove.textContent="Remove selected body";
    remove.onclick=()=>{
      if (model.bodies.length<=1) return notify("Keep at least one body in this assembly.");
      if (model.joints.some(item=>item.parent===body.id)) return notify("Remove this body's child links first so their connections are not lost.");
      if ((model.forces || []).some(item=>item.a===body.id||item.b===body.id)) return notify("Remove spring-dampers attached to this body first.");
      if ((model.loads || []).some(item=>item.body===body.id)) return notify("Remove external loads attached to this body first.");
      const incoming=model.joints.find(item=>item.child===body.id);
      if (incoming && ((model.rotationalElements || []).some(item=>item.joint===incoming.id) || (model.jointTorques || []).some(item=>item.joint===incoming.id))) return notify("Remove the rotational springs and joint torques on this body's joint first.");
      mutate(next=>{next.bodies=next.bodies.filter(item=>item.id!==body.id);next.joints=next.joints.filter(item=>item.child!==body.id);},"body");
    };
    section.append(remove);
    renderSolidEditor({container:section,body,mutate,notify,createSolid});
  } else if (joint) {
    const section=group(container,`${joint.type === "prismatic" ? "Prismatic slider" : "Revolute hinge"} · ${joint.id}`);
    const child=model.bodies.find(item=>item.id===joint.child);
    const label=document.createElement("label");label.textContent="Parent body";
    const parent=document.createElement("select");parent.setAttribute("aria-label","Hinge parent body");
    const forbidden=descendants(model,joint.child);
    for (const item of [{id:"ground",name:"Ground"},...model.bodies.filter(item=>!forbidden.has(item.id))]) {
      const option=document.createElement("option");option.value=item.id;option.textContent=item.name;parent.append(option);
    }
    parent.value=joint.parent;
    parent.onchange=()=>mutate(next=>{
      const changed=next.joints.find(item=>item.id===joint.id), childBody=next.bodies.find(item=>item.id===joint.child);
      const newParent=next.bodies.find(item=>item.id===parent.value);
      const pin=world(childBody,changed.childAnchor);
      changed.parent=parent.value;changed.parentAnchor=inverse(newParent,pin);
      if(changed.type === "prismatic") {
        changed.referenceAngleDeg=((childBody.pose.angleDeg-(newParent?.pose.angleDeg || 0)+540)%360)-180;
        childBody.velocity.omega=newParent?.velocity.omega || 0;
      }
      const parentOffset=newParent ? rotate(changed.parentAnchor,newParent.pose.angleDeg) : {x:0,z:0};
      const parentVelocity=newParent ? {x:newParent.velocity.vx+newParent.velocity.omega*parentOffset.z,z:newParent.velocity.vz-newParent.velocity.omega*parentOffset.x} : {x:0,z:0};
      const childOffset=rotate(changed.childAnchor,childBody.pose.angleDeg);
      childBody.velocity.vx=parentVelocity.x-childBody.velocity.omega*childOffset.z;
      childBody.velocity.vz=parentVelocity.z+childBody.velocity.omega*childOffset.x;
    });
    label.append(parent);section.append(label);
    const note=document.createElement("p");note.textContent=`Child: ${child?.name || joint.child}. Anchor coordinates are local to each body; ground uses world coordinates.${joint.type === "prismatic" ? " The guide angle rotates parent-local +X about +Y; the reference angle is child minus parent." : ""}`;section.append(note);
    for (const side of ["parentAnchor","childAnchor"]) for (const axis of ["x","z"]) {
      inputRow(section,`${side === "parentAnchor" ? "Parent" : "Child"} anchor ${axis.toUpperCase()}`,"m",joint[side][axis],
        number=>mutate(next=>{next.joints.find(item=>item.id===joint.id)[side][axis]=number;}),"0.01",`graph-joint-${joint.id}-${side}-${axis}`);
    }
    if (joint.type === "prismatic") for (const [key,title] of [["axisAngleDeg","Guide angle from +X about +Y"],["referenceAngleDeg","Child minus parent angle"]]) inputRow(section,title,"°",joint[key],number=>mutate(next=>{next.joints.find(item=>item.id===joint.id)[key]=number;}),"1",`graph-joint-${joint.id}-${key}`);
  } else if (force) {
    const section=group(container,`Spring / damper · ${force.id}`);
    const note=document.createElement("p");note.textContent="Forces act along the line between the two body-local anchors. Ground anchors use world coordinates; zero-length attachments are invalid.";section.append(note);
    for(const side of ["a","b"]) {
      const label=document.createElement("label");label.textContent=`Endpoint ${side.toUpperCase()}`;
      const select=document.createElement("select");select.setAttribute("aria-label",`Spring endpoint ${side.toUpperCase()}`);select.id=`graph-force-${force.id}-${side}`;
      for(const item of [{id:"ground",name:"Ground"},...model.bodies]){const option=document.createElement("option");option.value=item.id;option.textContent=item.name;select.append(option);}
      select.value=force[side];select.onchange=()=>mutate(next=>{next.forces.find(item=>item.id===force.id)[side]=select.value;});label.append(select);section.append(label);
    }
    for(const side of ["anchorA","anchorB"])for(const axis of ["x","z"])inputRow(section,`${side === "anchorA" ? "A" : "B"} anchor ${axis.toUpperCase()}`,"m",force[side][axis],value=>mutate(next=>{next.forces.find(item=>item.id===force.id)[side][axis]=value;}),"0.01",`graph-force-${force.id}-${side}-${axis}`);
    for(const [key,title,unit,step] of [["stiffness","Stiffness","N/m","10"],["damping","Damping","N·s/m","0.1"],["restLength","Rest length","m","0.01"]])inputRow(section,title,unit,force[key],value=>mutate(next=>{next.forces.find(item=>item.id===force.id)[key]=value;}),step,`graph-force-${force.id}-${key}`);
    const remove=document.createElement("button");remove.className="secondary full-width";remove.type="button";remove.textContent="Remove spring / damper";remove.onclick=()=>mutate(next=>{next.forces=next.forces.filter(item=>item.id!==force.id);},"body");section.append(remove);
  } else if (rotary) {
    const section=group(container,`Rotational spring / damper · ${rotary.id}`);
    const note=document.createElement("p");note.textContent="Torque resists child-minus-parent angle and relative velocity about +Y. Spring travel must remain within ±180° of its rest angle; multiple turns are unsupported.";section.append(note);
    jointChoice(section,model,rotary.joint,"Rotational element joint",value=>mutate(next=>{next.rotationalElements.find(item=>item.id===rotary.id).joint=value;}));
    for(const [key,title,unit,step] of [["stiffness","Rotational stiffness","N·m/rad","1"],["damping","Rotational damping","N·m·s/rad","0.1"],["restAngleDeg","Rest angle","°","1"]])inputRow(section,title,unit,rotary[key],value=>mutate(next=>{next.rotationalElements.find(item=>item.id===rotary.id)[key]=value;}),step,`graph-rotary-${rotary.id}-${key}`);
    const remove=document.createElement("button");remove.className="secondary full-width";remove.type="button";remove.textContent="Remove rotational spring / damper";remove.onclick=()=>mutate(next=>{next.rotationalElements=next.rotationalElements.filter(item=>item.id!==rotary.id);},"body");section.append(remove);
  } else if (torque) {
    const section=group(container,`Sinusoidal joint torque · ${torque.id}`);
    const note=document.createElement("p");note.textContent="Torque = offset + amplitude × sin(2π × frequency × time), applied to the child about +Y with an equal opposite reaction on the parent. Use at least 20 time steps per cycle.";section.append(note);
    jointChoice(section,model,torque.joint,"Torque joint",value=>mutate(next=>{next.jointTorques.find(item=>item.id===torque.id).joint=value;}));
    for(const [key,title,unit,step] of [["amplitude","Torque amplitude","N·m","0.1"],["frequencyHz","Frequency","Hz","0.1"],["offset","Torque offset","N·m","0.1"]])inputRow(section,title,unit,torque[key],value=>mutate(next=>{next.jointTorques.find(item=>item.id===torque.id)[key]=value;}),step,`graph-torque-${torque.id}-${key}`);
    const remove=document.createElement("button");remove.className="secondary full-width";remove.type="button";remove.textContent="Remove joint torque";remove.onclick=()=>mutate(next=>{next.jointTorques=next.jointTorques.filter(item=>item.id!==torque.id);},"body");section.append(remove);
  } else if (appliedLoad) {
    const section=group(container,`External load · ${appliedLoad.id}`);
    const note=document.createElement("p");note.textContent="Constant force is applied at the body center of mass in global X/Z. Torque acts about global +Y. These values are not a time-varying actuator.";section.append(note);
    const label=document.createElement("label");label.textContent="Loaded body";const select=document.createElement("select");select.id=`graph-load-${appliedLoad.id}-body`;select.setAttribute("aria-label","Loaded body");
    for(const item of model.bodies){const option=document.createElement("option");option.value=item.id;option.textContent=item.name;select.append(option);}select.value=appliedLoad.body;select.onchange=()=>mutate(next=>{next.loads.find(item=>item.id===appliedLoad.id).body=select.value;});label.append(select);section.append(label);
    for(const [key,title,unit] of [["fx","Force X","N"],["fz","Force Z","N"],["torque","Torque Y","N·m"]])inputRow(section,title,unit,appliedLoad[key],value=>mutate(next=>{next.loads.find(item=>item.id===appliedLoad.id)[key]=value;}),"1",`graph-load-${appliedLoad.id}-${key}`);
    const remove=document.createElement("button");remove.className="secondary full-width";remove.type="button";remove.textContent="Remove external load";remove.onclick=()=>mutate(next=>{next.loads=next.loads.filter(item=>item.id!==appliedLoad.id);},"body");section.append(remove);
  }
  const section=group(container,"Build assembly");
  const note=document.createElement("p");note.textContent="Add a body and joint to a rooted planar tree. Closed loops, contact and flexible bodies are not supported.";section.append(note);
  const label=document.createElement("label");label.textContent="Attach next body to";
  const parent=document.createElement("select");parent.setAttribute("aria-label","Attach next body to");
  for (const item of [{id:"ground",name:"Ground"},...model.bodies]) {
    const option=document.createElement("option");option.value=item.id;option.textContent=item.name;parent.append(option);
  }
  parent.value=body?.id || "ground";label.append(parent);section.append(label);
  const jointLabel=document.createElement("label");jointLabel.textContent="Joint type";const jointType=document.createElement("select");jointType.setAttribute("aria-label","New joint type");
  for(const [value,title] of [["revolute","Revolute hinge"],["prismatic","Prismatic slider"]]){const option=document.createElement("option");option.value=value;option.textContent=title;jointType.append(option);}jointLabel.append(jointType);section.append(jointLabel);
  const add=document.createElement("button");add.className="secondary full-width";add.type="button";add.textContent="Add body + revolute hinge";
  jointType.onchange=()=>{add.textContent=jointType.value==="prismatic"?"Add body + prismatic slider":"Add body + revolute hinge";};
  add.disabled=model.bodies.length>=16;
  add.onclick=()=>mutate(next=>{
    const used=new Set(next.bodies.map(item=>item.id));let index=1;while(used.has(`body${index}`))index++;
    const id=`body${index}`;
    let hingeIndex=index; const usedJoints=new Set(next.joints.map(item=>item.id));
    while (usedJoints.has(`hinge${hingeIndex}`)) hingeIndex++;
    const hinge=`hinge${hingeIndex}`, parentBody=next.bodies.find(item=>item.id===parent.value);
    const parentAnchor=parentBody ? {x:0,z:-.5} : {x:(next.bodies.length-1)*1.5,z:0};
    const pin=world(parentBody,parentAnchor), angleDeg=parentBody?.pose.angleDeg || 0, childAnchor={x:0,z:.5}, offset=rotate(childAnchor,angleDeg);
    const position={x:pin.x-offset.x,z:pin.z-offset.z};
    const omega=parentBody?.velocity.omega || 0;
    const delta=parentBody ? {x:position.x-parentBody.pose.x,z:position.z-parentBody.pose.z} : {x:0,z:0};
    next.bodies.push({id,name:`Body ${index}`,mass:1,inertia:{xx:.0834083,yy:.0834083,zz:.00015},pose:{...position,angleDeg},
      velocity:{vx:(parentBody?.velocity.vx || 0)+omega*delta.z,vz:(parentBody?.velocity.vz || 0)-omega*delta.x,omega}});
    const joint={id:hinge,type:jointType.value,parent:parent.value,child:id,parentAnchor,childAnchor};
    if(jointType.value==="prismatic"){joint.axisAngleDeg=0;joint.referenceAngleDeg=0;}
    next.joints.push(joint);
  },`node-body${(()=>{const used=new Set(model.bodies.map(item=>item.id));let n=1;while(used.has(`body${n}`))n++;return n;})()}`);
  section.append(add);
  const load=group(container,"Add spring / damper");
  const loadNote=document.createElement("p");loadNote.textContent="Connect the selected body to a ground point with a linear spring and damper. Edit both endpoints and attachment coordinates after adding.";load.append(loadNote);
  const targetLabel=document.createElement("label");targetLabel.textContent="Body for new spring";const target=document.createElement("select");target.setAttribute("aria-label","Body for new spring");
  for(const item of model.bodies){const option=document.createElement("option");option.value=item.id;option.textContent=item.name;target.append(option);}target.value=body?.id || model.bodies[0].id;targetLabel.append(target);load.append(targetLabel);
  const addForce=document.createElement("button");addForce.className="secondary full-width";addForce.type="button";addForce.textContent="Add spring / damper";
  addForce.disabled=(model.forces || []).length>=32;
  addForce.onclick=()=>{const used=new Set((model.forces || []).map(item=>item.id));let index=1;while(used.has(`spring${index}`))index++;const id=`spring${index}`;const selected=model.bodies.find(item=>item.id===target.value);mutate(next=>{next.forces ??= [];next.forces.push({id,type:"linear-spring-damper",a:"ground",b:selected.id,anchorA:{x:selected.pose.x-0.5,z:selected.pose.z},anchorB:{x:0,z:0},stiffness:100,damping:1,restLength:0.5});},`force-${id}`);};
  load.append(addForce);
  const external=group(container,"Add external load");const externalNote=document.createElement("p");externalNote.textContent="Add a constant global force and/or torque at a body's center of mass.";external.append(externalNote);
  const externalTargetLabel=document.createElement("label");externalTargetLabel.textContent="Body for external load";const externalTarget=document.createElement("select");externalTarget.setAttribute("aria-label","Body for external load");
  for(const item of model.bodies){const option=document.createElement("option");option.value=item.id;option.textContent=item.name;externalTarget.append(option);}externalTarget.value=body?.id || model.bodies[0].id;externalTargetLabel.append(externalTarget);external.append(externalTargetLabel);
  const addLoad=document.createElement("button");addLoad.className="secondary full-width";addLoad.type="button";addLoad.textContent="Add external force / torque";
  addLoad.disabled=(model.loads || []).length>=32;
  addLoad.onclick=()=>{const used=new Set((model.loads || []).map(item=>item.id));let index=1;while(used.has(`load${index}`))index++;const id=`load${index}`;mutate(next=>{next.loads ??= [];next.loads.push({id,body:externalTarget.value,fx:1,fz:0,torque:0});},`applied-${id}`);};external.append(addLoad);
  const revolute=model.joints.filter(item=>item.type==="revolute");
  const rotational=group(container,"Add rotational element");
  const rotationalNote=document.createElement("p");rotationalNote.textContent="Add a torsional spring or damper, or a sinusoidal torque to a revolute joint.";rotational.append(rotationalNote);
  const targetJoint=jointChoice(rotational,model,joint?.type==="revolute" ? joint.id : revolute[0]?.id,"Joint for rotational element",()=>{});
  const addRotary=document.createElement("button");addRotary.className="secondary full-width";addRotary.type="button";addRotary.textContent="Add rotational spring / damper";addRotary.disabled=!revolute.length || (model.rotationalElements || []).length>=32;
  addRotary.onclick=()=>{const used=new Set((model.rotationalElements || []).map(item=>item.id));let index=1;while(used.has(`rotary${index}`))index++;const id=`rotary${index}`;const chosen=model.joints.find(item=>item.id===targetJoint.value);const child=model.bodies.find(item=>item.id===chosen.child),parent=model.bodies.find(item=>item.id===chosen.parent);const rest=Math.max(-179,Math.min(179,child.pose.angleDeg-(parent?.pose.angleDeg || 0)));mutate(next=>{next.rotationalElements ??= [];next.rotationalElements.push({id,joint:chosen.id,stiffness:10,damping:0.5,restAngleDeg:rest});},`rotary-${id}`);};rotational.append(addRotary);
  const addTorque=document.createElement("button");addTorque.className="secondary full-width";addTorque.type="button";addTorque.textContent="Add sinusoidal joint torque";addTorque.disabled=!revolute.length || (model.jointTorques || []).length>=32;
  addTorque.onclick=()=>{const used=new Set((model.jointTorques || []).map(item=>item.id));let index=1;while(used.has(`torque${index}`))index++;const id=`torque${index}`;mutate(next=>{next.jointTorques ??= [];next.jointTorques.push({id,joint:targetJoint.value,amplitude:1,frequencyHz:1,offset:0});},`torque-${id}`);};rotational.append(addTorque);
}
