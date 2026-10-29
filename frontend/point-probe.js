import * as THREE from 'three';

const AXES=['x','y','z'], RAD=Math.PI/180;
const value=(vector,key)=>{const n=vector?.[key];if(typeof n!=='number'||!Number.isFinite(n))throw Error(`Missing finite ${key} in solver output.`);return n;};

/** Resolve a body-local point from an actual solver sample into world position and velocity. */
export function pointState(sample, endpoint) {
  if(!endpoint || typeof endpoint.body!=='string' || !endpoint.point || !AXES.every(k=>typeof endpoint.point[k]==='number'&&Number.isFinite(endpoint.point[k])&&Math.abs(endpoint.point[k])<=1000))throw Error('A point needs a valid body and finite coordinates within ±1000 m.');
  const local=new THREE.Vector3(...AXES.map(k=>endpoint.point[k]));
  if(endpoint.body==='ground')return {position:local.toArray(),velocity:[0,0,0]};
  const node=sample?.nodes?.find(n=>n.id===endpoint.body);if(!node)throw Error(`Solver sample is missing body ${endpoint.body}.`);
  const rotation=new THREE.Euler(...['rx','ry','rz'].map(k=>value(node,k)*RAD),'XYZ');
  const offset=local.applyEuler(rotation),position=new THREE.Vector3(...AXES.map(k=>value(node,k))).add(offset);
  const omega=new THREE.Vector3(...['wx','wy','wz'].map(k=>value(node,k)));
  const velocity=new THREE.Vector3(...['vx','vy','vz'].map(k=>value(node,k))).add(omega.cross(offset));
  return {position:position.toArray(),velocity:velocity.toArray()};
}

/** Calculate distance, relative distance rate, and both point states at displayed samples. */
export function pointHistory(samples,a,b) {
  if(!Array.isArray(samples)||!samples.length||samples.length>2001)throw Error('A spatial result needs 1–2001 displayed solver samples.');
  let previous=-Infinity;
  return samples.map(sample=>{
    const time=value(sample,'time');if(time<=previous)throw Error('Solver sample times must increase.');previous=time;
    const A=pointState(sample,a),B=pointState(sample,b),delta=B.position.map((x,i)=>x-A.position[i]),speed=B.velocity.map((x,i)=>x-A.velocity[i]);
    const distance=Math.hypot(...delta),rate=distance===0?null:delta.reduce((sum,x,i)=>sum+x*speed[i],0)/distance;
    if(!Number.isFinite(distance)||(rate!==null&&!Number.isFinite(rate)))throw Error('The calculated separation is not finite.');
    return {time,pointA:A,pointB:B,distance,rate};
  });
}

/** Export displayed samples with point IDs and local offsets; no formulas or human text are embedded. */
export function pointCsv(history,a,b) {
  const cols=['time_s','a_body','a_local_x_m','a_local_y_m','a_local_z_m','b_body','b_local_x_m','b_local_y_m','b_local_z_m','a_world_x_m','a_world_y_m','a_world_z_m','a_velocity_x_m_s','a_velocity_y_m_s','a_velocity_z_m_s','b_world_x_m','b_world_y_m','b_world_z_m','b_velocity_x_m_s','b_velocity_y_m_s','b_velocity_z_m_s','separation_m','separation_rate_m_s'];
  if(![a.body,b.body].every(id=>id==='ground'||/^[A-Za-z][A-Za-z0-9_-]{0,31}$/.test(id)))throw Error('Invalid body identity for CSV export.');
  return cols.join(',')+'\n'+history.map(s=>[s.time,a.body,...AXES.map(k=>a.point[k]),b.body,...AXES.map(k=>b.point[k]),...s.pointA.position,...s.pointA.velocity,...s.pointB.position,...s.pointB.velocity,s.distance,s.rate??''].join(',')).join('\n')+'\n';
}

/** Add an on-demand probe that does not mutate the project or its solver results. */
export function setupPointProbe({getResult,getModel,getBindings=()=>({}),getFrame=()=>0,isStale=()=>false,notify}) {
  const button=document.createElement('button');button.id='pointProbeButton';button.type='button';button.className='text-button';button.textContent='Point probe';button.title='Measure separation and point motion';(document.querySelector('#measureTools') || document.querySelector('#csvButton').parentElement).append(button);
  const dialog=document.createElement('dialog');dialog.id='pointProbeDialog';dialog.setAttribute('aria-labelledby','pointProbeTitle');
  const head=document.createElement('div');head.className='dialog-heading';head.innerHTML='<h2 id="pointProbeTitle">Measure two points</h2>';
  const close=document.createElement('button');close.type='button';close.className='icon-button';close.setAttribute('aria-label','Close point probe');close.textContent='×';close.onclick=()=>dialog.close();head.append(close);dialog.append(head);
  const intro=document.createElement('p');intro.textContent='Points are in their body’s local axes, or world axes for ground. Named frames use their origins. The plot and CSV use displayed MBDyn samples, which may be downsampled.';dialog.append(intro);
  const grid=document.createElement('div');grid.style.display='grid';grid.style.gridTemplateColumns='repeat(auto-fit,minmax(225px,1fr))';grid.style.gap='14px';dialog.append(grid);
  const action=document.createElement('div');action.className='step-actions';const calculate=document.createElement('button');calculate.type='button';calculate.className='primary';calculate.id='pointProbeCalculate';calculate.textContent='Calculate separation';const exportButton=document.createElement('button');exportButton.type='button';exportButton.className='secondary';exportButton.id='pointProbeExport';exportButton.textContent='Export displayed samples CSV';exportButton.disabled=true;action.append(calculate,exportButton);dialog.append(action);
  const status=document.createElement('p');status.id='pointProbeStatus';status.setAttribute('role','status');status.style.whiteSpace='pre-line';dialog.append(status);const plot=document.createElement('div');plot.id='pointProbePlot';plot.setAttribute('role','img');plot.setAttribute('aria-label','Separation plot. Calculate to show data.');dialog.append(plot);document.body.append(dialog);
  let snapshot=null,bindings=null,source=null,history=null,endpoints=null;
  function current(){return source===getResult() && JSON.stringify(getModel())===snapshot && JSON.stringify(getBindings())===bindings && !isStale();}
  function clear(){history=null;endpoints=null;exportButton.disabled=true;plot.replaceChildren();plot.setAttribute('aria-label','Separation plot. Calculate to show data.');status.textContent='Inputs changed; calculate again.';}
  function endpointField(side,model) {
    const group=document.createElement('fieldset');group.className='solid-calculator';group.style.padding='10px';group.innerHTML=`<legend>Point ${side}</legend>`;
    const label=document.createElement('label');label.textContent=`Point ${side} reference`;const select=document.createElement('select');select.id=`pointProbe${side}Reference`;select.setAttribute('aria-label',label.textContent);
    const choices=[{key:'ground',label:'Ground · world coordinates',body:'ground'},...model.bodies.map(body=>({key:`body:${body.id}`,label:`${body.name} · body local`,body:body.id})),...(model.frames||[]).map(frame=>({key:`frame:${frame.id}`,label:`${frame.name} · frame origin`,body:frame.body,point:frame.translation}))];
    for(const entry of choices){const option=document.createElement('option');option.value=entry.key;option.textContent=entry.label;select.append(option);}select.value=side==='B'&&model.bodies.length?`body:${model.bodies[0].id}`:'ground';label.append(select);group.append(label);
    const inputs={};for(const axis of AXES){const wrapper=document.createElement('label');wrapper.textContent=`Point ${side} ${axis.toUpperCase()} (m)`;const input=document.createElement('input');input.type='number';input.step='any';input.value='0';input.id=`pointProbe${side}${axis.toUpperCase()}`;input.setAttribute('aria-label',wrapper.textContent);input.addEventListener('input',clear);wrapper.append(input);group.append(wrapper);inputs[axis]=input;}
    select.onchange=()=>{const choice=choices.find(item=>item.key===select.value);for(const axis of AXES){inputs[axis].readOnly=Boolean(choice.point);if(choice.point)inputs[axis].value=String(choice.point[axis]);}clear();};grid.append(group);
    return ()=>{const choice=choices.find(item=>item.key===select.value);if(!choice)throw Error('Choose a valid point reference.');const point=Object.fromEntries(AXES.map(k=>[k,inputs[k].value.trim()===''?NaN:Number(inputs[k].value)]));return {body:choice.body,point};};
  }
  let readA,readB;
  button.onclick=()=>{
    const result=getResult(),model=getModel();if(!result||result.source!=='MBDyn'||result.model?.kind!=='spatial-assembly'||model?.kind!=='spatial-assembly'||isStale()){notify('Run or reopen a current spatial MBDyn result before using the point probe.','warn');return;}
    source=result;snapshot=JSON.stringify(model);bindings=JSON.stringify(getBindings());grid.replaceChildren();readA=endpointField('A',model);readB=endpointField('B',model);history=null;endpoints=null;exportButton.disabled=true;status.textContent='Choose points and calculate.';plot.replaceChildren();dialog.showModal();
  };
  calculate.onclick=()=>{try{
    if(!current())throw Error('The model, STEP bindings, or result changed; close and reopen the point probe.');
    const a=readA(),b=readB(),rows=pointHistory(source.samples,a,b),selected=rows[Math.max(0,Math.min(getFrame(),rows.length-1))];history=rows;endpoints={a,b};exportButton.disabled=false;
    const vec=values=>values.map(n=>n.toPrecision(5)).join(', ');
    status.textContent=`At ${selected.time.toPrecision(5)} s: separation ${selected.distance.toPrecision(6)} m; separation rate ${selected.rate===null?'undefined at zero separation':selected.rate.toPrecision(6)+' m/s'}. ${rows.length} displayed samples.\nPoint A world position: (${vec(selected.pointA.position)}) m; velocity: (${vec(selected.pointA.velocity)}) m/s.\nPoint B world position: (${vec(selected.pointB.position)}) m; velocity: (${vec(selected.pointB.velocity)}) m/s.`;
    const distances=rows.map(item=>item.distance),lo=Math.min(...distances),hi=Math.max(...distances),minTime=rows[0].time,maxTime=rows.at(-1).time,scale=Math.max(Math.abs(lo),Math.abs(hi),1),pad=Math.max((hi-lo)*.05,scale*5e-7),bottom=lo-pad,top=hi+pad;
    const points=rows.map(item=>`${40+620*(item.time-minTime)/(maxTime-minTime||1)},${120-95*(item.distance-bottom)/(top-bottom)}`).join(' ');
    plot.innerHTML=`<svg viewBox="0 0 680 155" aria-hidden="true"><path d="M40 20V120H660" fill="none" stroke="currentColor"/><polyline points="${points}" fill="none" stroke="#2678da" stroke-width="2"/><text x="40" y="145" font-size="12">${minTime.toPrecision(4)} s</text><text x="600" y="145" font-size="12">${maxTime.toPrecision(4)} s</text><text x="46" y="18" font-size="12">${top.toPrecision(8)} m</text><text x="46" y="115" font-size="12">${bottom.toPrecision(8)} m</text></svg>`;
    plot.setAttribute('aria-label',`Point separation over time: ${lo.toPrecision(6)} to ${hi.toPrecision(6)} metres, ${rows.length} displayed samples.`);
  }catch(error){clear();status.textContent=error.message;}};
  exportButton.onclick=()=>{try{if(!history||!current())throw Error('The model, STEP bindings, or result changed; calculate again.');const text=pointCsv(history,endpoints.a,endpoints.b),url=URL.createObjectURL(new Blob([text],{type:'text/csv'})),link=document.createElement('a');link.href=url;link.download='point-probe-displayed-samples.csv';link.click();setTimeout(()=>URL.revokeObjectURL(url),1000);}catch(error){clear();status.textContent=error.message;}};
  return {open:()=>button.click()};
}
