const COMPONENTS=[['x','X','m'],['y','Y','m'],['z','Z','m'],['rx','Euler X','°'],['ry','Euler Y','°'],['rz','Euler Z','°']];

const VELOCITIES=[['vx','Linear X','m/s'],['vy','Linear Y','m/s'],['vz','Linear Z','m/s'],['wx','Angular X','rad/s'],['wy','Angular Y','rad/s'],['wz','Angular Z','rad/s']];


/** Build a kinematics dialog; integration provides project state and mutation. */

export function setupKinematics({getModel,getBindings=()=>({}),isBusy=()=>false,applyModel,notify}) {

  const dialog=document.createElement('dialog');dialog.id='kinematicsDialog';dialog.setAttribute('aria-labelledby','kinematicsTitle');

  const heading=document.createElement('div');heading.className='dialog-heading';

  const title=document.createElement('h2');title.id='kinematicsTitle';title.textContent='Solve assembly position';

  const close=document.createElement('button');close.type='button';close.className='icon-button';close.setAttribute('aria-label','Close kinematics');close.textContent='×';close.onclick=()=>dialog.close();heading.append(title,close);dialog.append(heading);

  const modeLabel=document.createElement('label');modeLabel.textContent='Calculation ';const modeSelect=document.createElement('select');modeSelect.id='kinematicsMode';modeSelect.setAttribute('aria-label','Kinematics calculation');for(const [value,label] of [['position','Position'],['velocity','Velocity']]){const option=document.createElement('option');option.value=value;option.textContent=label;modeSelect.append(option);}modeLabel.append(modeSelect);dialog.append(modeLabel);

  const intro=document.createElement('p');dialog.append(intro);

  const fields=document.createElement('div');fields.id='kinematicsFields';dialog.append(fields);

  const actions=document.createElement('div');actions.className='step-actions';

  const solveButton=document.createElement('button');solveButton.type='button';solveButton.className='primary';solveButton.textContent='Solve positions';solveButton.id='kinematicsSolve';

  const applyButton=document.createElement('button');applyButton.type='button';applyButton.className='secondary';applyButton.textContent='Apply solved pose';applyButton.id='kinematicsApply';applyButton.disabled=true;actions.append(solveButton,applyButton);dialog.append(actions);

  const output=document.createElement('p');output.id='kinematicsResult';output.setAttribute('role','status');dialog.append(output);document.body.append(dialog);

  let snapshot=null,bindSnapshot=null,solution=null,revision=0;

  const clear=()=>{revision++;solution=null;applyButton.disabled=true;output.textContent='Inputs changed; solve again.';};

  function renderFields() {

    const velocity=modeSelect.value==='velocity',components=velocity ? VELOCITIES : COMPONENTS,field=velocity ? 'velocity' : 'pose';

    title.textContent=velocity ? 'Solve assembly velocity' : 'Solve assembly position';

    intro.textContent=velocity ? 'Choose body-origin world-frame velocities to solve and set targets. Poses and unselected velocities stay fixed. Angular velocity is in rad/s, not Euler-angle rate. This does not run MBDyn.' : 'Choose body coordinates to solve, adjust initial guesses, and set targets. Other coordinates and velocities stay fixed. This is an independent position calculation, not a dynamics simulation.';

    solveButton.textContent=velocity ? 'Solve velocities' : 'Solve positions';applyButton.textContent=velocity ? 'Apply solved velocities' : 'Apply solved pose';

    clear();fields.replaceChildren();output.textContent=`No ${modeSelect.value} calculation yet.`;

    for(const body of snapshot.bodies){

      const container=document.createElement('details'),summary=document.createElement('summary');summary.textContent=`${body.name} · ${body.id}`;container.append(summary);

      const group=document.createElement('fieldset');group.setAttribute('aria-label',`${body.name} ${velocity ? 'velocities' : 'coordinates'}`);container.append(group);

      for(const [key,label,unit] of components){

        const row=document.createElement('div');row.className='kinematics-row';row.dataset.body=body.id;row.dataset.component=key;

        const unknownLabel=document.createElement('label'),unknown=document.createElement('input');unknown.type='checkbox';unknown.dataset.role='unknown';unknown.setAttribute('aria-label',`${body.name} ${label} unknown`);unknownLabel.append(unknown,document.createTextNode(` ${label} unknown`));

        const guessLabel=document.createElement('label'),guess=document.createElement('input');guess.type='number';guess.step='any';guess.value=String(body[field][key]);guess.dataset.role='initial';guess.setAttribute('aria-label',`${body.name} ${label} initial guess (${unit})`);guessLabel.append(document.createTextNode(`Initial (${unit}) `),guess);

        const targetLabel=document.createElement('label'),target=document.createElement('input');target.type='checkbox';target.dataset.role='target';target.setAttribute('aria-label',`${body.name} ${label} target`);targetLabel.append(target,document.createTextNode(' Target'));

        const valueLabel=document.createElement('label'),value=document.createElement('input');value.type='number';value.step='any';value.value=String(body[field][key]);value.dataset.role='value';value.setAttribute('aria-label',`${body.name} ${label} target value (${unit})`);valueLabel.append(document.createTextNode(`Value (${unit}) `),value);

        for(const input of [unknown,guess,target,value])input.addEventListener('input',clear);

        row.append(unknownLabel,guessLabel,targetLabel,valueLabel);group.append(row);

      }fields.append(container);

    }

  }

  modeSelect.addEventListener('change',renderFields);

  function open() {

    if(isBusy())return notify('Wait for the current operation before solving kinematics.','warn');

    const model=getModel();if(model?.kind!=='spatial-assembly')return notify('Select a 3D assembly to solve kinematics.','warn');

    snapshot=structuredClone(model);bindSnapshot=structuredClone(getBindings());modeSelect.value='position';renderFields();dialog.showModal();

  }

  solveButton.onclick=async()=>{

    const before=JSON.stringify(snapshot),bindings=JSON.stringify(bindSnapshot),mode=modeSelect.value,field=mode==='velocity' ? 'velocity' : 'pose';

    if(isBusy() || JSON.stringify(getModel())!==before || JSON.stringify(getBindings())!==bindings){output.textContent='The model or STEP attachments changed. Close and reopen the kinematics solver.';clear();return;}

    const variables=[],targets=[];

    for(const row of fields.querySelectorAll('.kinematics-row')){

      const {body,component}=row.dataset,unknown=row.querySelector('[data-role=unknown]'),guess=row.querySelector('[data-role=initial]'),target=row.querySelector('[data-role=target]'),value=row.querySelector('[data-role=value]');

      if(unknown.checked){if(guess.value.trim()==='' || !Number.isFinite(Number(guess.value))){output.textContent=`Enter a finite initial guess for ${body} ${component}.`;return;}variables.push({body,component,initial:Number(guess.value)});}

      if(target.checked){if(value.value.trim()==='' || !Number.isFinite(Number(value.value))){output.textContent=`Enter a finite target for ${body} ${component}.`;return;}targets.push({body,component,value:Number(value.value)});}

    }

    if(!variables.length){output.textContent='Select at least one unknown component.';return;}

    clear();const request=revision;solveButton.disabled=true;output.textContent=`Solving ${mode} constraints…`;

    try {

      const response=await fetch('/api/kinematics',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(mode==='velocity' ? {mode,model:snapshot,variables,targets} : {model:snapshot,variables,targets})});

      const result=await response.json();if(!response.ok)throw Error(result.error || 'The kinematic calculation failed.');

      if(request!==revision)return;

      if(isBusy() || JSON.stringify(getModel())!==before || JSON.stringify(getBindings())!==bindings)throw Error('The model or STEP attachments changed; no solution was applied.');

      if(typeof result.ok!=='boolean' || !Number.isFinite(result.maxResidual) || !(result.jacobianRank===null || Number.isInteger(result.jacobianRank)) || !Number.isInteger(result.unknownCount))throw Error('The kinematic solver returned an invalid result.');

      output.textContent=`${result.message} Maximum residual: ${result.maxResidual.toExponential(3)}; Jacobian rank ${result.jacobianRank===null ? 'not evaluated' : `${result.jacobianRank}/${result.unknownCount}` }.`;

      if(result.ok){

        if(!result.model || !Array.isArray(result.model.bodies))throw Error('The solution has no valid candidate model.');

        const candidate=structuredClone(snapshot);

        for(const variable of variables){const original=candidate.bodies.find(item=>item.id===variable.body),solved=result.model.bodies.find(item=>item.id===variable.body),number=solved?.[field]?.[variable.component];if(!original || !Number.isFinite(number))throw Error('The solution contains an invalid coordinate.');original[field][variable.component]=number;}

        if(JSON.stringify(candidate)!==JSON.stringify(result.model))throw Error('The solution unexpectedly changed values outside the selected coordinates.');

        const units=Object.fromEntries((mode==='velocity' ? VELOCITIES : COMPONENTS).map(([key,,unit])=>[key,unit]));
        output.textContent+=` Proposed: ${variables.map(({body,component})=>`${body} ${component} = ${Number(candidate.bodies.find(item=>item.id===body)[field][component].toPrecision(7))} ${units[component]}`).join('; ')}.`;
        const validation=result.dynamicsValidation;

        if(!validation || typeof validation.valid!=='boolean' || !Array.isArray(validation.issues))throw Error('The solution did not include dynamics validation.');

        output.textContent+=validation.valid ? ' The current MBDyn input checks pass; a solver run is still required.' : ` The ${mode} is solved, but MBDyn input checks still need attention: ${validation.issues.map(issue=>`${issue.field}: ${issue.message}`).join(' ')}`;

        solution=candidate;applyButton.disabled=false;

      }

    } catch(error){if(request===revision){output.textContent=error.message;notify(error.message,'warn');}} finally {solveButton.disabled=false;}

  };

  applyButton.onclick=()=>{

    if(!solution)return;

    if(isBusy() || JSON.stringify(getModel())!==JSON.stringify(snapshot) || JSON.stringify(getBindings())!==JSON.stringify(bindSnapshot)){output.textContent='The model or STEP attachments changed; no solution was applied.';clear();return;}

    applyModel(solution);clear();dialog.close();notify(`Applied the solved ${modeSelect.value}. Check model validation before running MBDyn.`,'');

  };

  return {open};

}

