const $ = id => document.getElementById(id);

export function explicitRunRequest(text) {
  const negated = /\b(?:do\s+not|don't|dont|never|without|avoid|not)\s+(?:\w+\s+){0,4}(?:run|solve|simulate|execute)\b/i;
  const requested = /(?:^\s*(?:please\s+)?|\b(?:and|then|also|please|can you|could you|go ahead and)\s+)(?:run|solve|simulate|execute)\b/i;
  return requested.test(text) && !negated.test(text);
}

/** UI for a local model connection; all changes pass the existing validator and history. */
export function setupAgent({getModel, getSignature, getBindings=()=>({}), checkModel, applyModel, run, isBusy, nativeDesktop}) {
  const panel = $("agentPanel"), messages = $("agentMessages"), modelSelect = $("agentModel");
  const history = [];
  let pending = false, reviewOutstanding = false;
  function message(text, role = "assistant") {
    const element = document.createElement("div");
    element.className = `agent-message ${role}`;
    element.textContent = text;
    messages.append(element);
    messages.scrollTop = messages.scrollHeight;
    return element;
  }
  function reviewSpatial({before, original, proposed, bindings, descriptions, runAfter}) {
    reviewOutstanding = true;
    const item=message("Review the complete model before applying. Validation checks consistency; it cannot determine whether the agent interpreted your request correctly.");
    item.classList.add("agent-review");
    const details=document.createElement("details"), summary=document.createElement("summary"), pre=document.createElement("pre");
    details.open=true;summary.textContent="Compare current and proposed model";pre.textContent=`CURRENT MODEL\n${JSON.stringify(original,null,2)}\n\nPROPOSED MODEL\n${JSON.stringify(proposed,null,2)}`;
    details.append(summary,pre);item.append(details);
    const allowed=new Set(["planar-assembly","spatial-assembly"].includes(proposed.kind) ? (proposed.bodies || []).map(body=>body.id) : []);
    const detached=Object.entries(bindings).filter(([,binding])=>!allowed.has(binding.body) || ((proposed.kind === "spatial-assembly") !== (Object.hasOwn(binding.pose || {},"rx") && Object.hasOwn(binding.pose || {},"rz"))));
    if(detached.length){const warning=document.createElement("p");warning.textContent=`Applying will detach STEP parts: ${detached.map(([part,binding])=>`${part} from ${binding.body}`).join(", ")}.`;item.append(warning);}
    const controls=document.createElement("div"), apply=document.createElement("button"), reject=document.createElement("button");
    controls.className="agent-review-actions";apply.type=reject.type="button";apply.className="primary";reject.className="secondary";apply.textContent=runAfter ? "Apply and run" : "Apply proposal";reject.textContent="Discard proposal";controls.append(apply,reject);item.append(controls);
    reject.onclick=()=>{reviewOutstanding=false;apply.disabled=reject.disabled=true;message("Proposal discarded. The current model was not changed.");};
    apply.onclick=async()=>{
      if(getSignature()!==before || JSON.stringify(getBindings())!==JSON.stringify(bindings) || isBusy()){message("The model, STEP attachments or another operation changed since this proposal. Ask the agent again.","error");reviewOutstanding=false;apply.disabled=reject.disabled=true;return;}
      apply.disabled=reject.disabled=true;
      let applied=false;
      try {
        const validation=await checkModel(proposed);
        if(!validation.valid)throw Error((validation.issues || []).map(issue=>issue.message).join(" ") || "The proposal is no longer valid.");
        if(getSignature()!==before || JSON.stringify(getBindings())!==JSON.stringify(bindings) || isBusy())throw Error("The model, STEP attachments or another operation changed during validation. Ask the agent again.");
        applyModel(proposed);applied=true;message(`${descriptions.join(" · ") || "Updated the model"}. Use Undo to restore the previous model.`);
        if(runAfter){message("Running the reviewed model as requested.");await run(false);}
      } catch(error){message(`${applied ? "The model was applied, but the run could not finish" : "The proposal could not be applied"}: ${error.message}`,"error");}
      finally {reviewOutstanding=false;}
    };
    messages.scrollTop=messages.scrollHeight;
  }
  async function request(path, body) {
    const response = await fetch(`/api/agent/${path}`, body ? {method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(body)} : undefined);
    let data;
    try { data = await response.json(); } catch { throw new Error("The AI service returned an unreadable response."); }
    if (!response.ok || data.ok === false) throw new Error(data.error || `AI request failed (${response.status}).`);
    return data;
  }
  async function refresh() {
    $("agentStatus").textContent = "Checking local AI service…";
    $("agentSend").disabled = true;
    try {
      const status = await request("status");
      modelSelect.replaceChildren();
      for (const item of status.models || []) {
        const option = document.createElement("option");
        option.value = item.name; option.textContent = item.name; modelSelect.append(option);
      }
      if (status.defaultModel) modelSelect.value = status.defaultModel;
      $("agentStatus").textContent = status.detail || (status.available ? "Local model service ready." : "Local model service unavailable.");
      $("agentSend").disabled = !status.available || !modelSelect.value;
    } catch (error) {
      $("agentStatus").textContent = `AI connection unavailable: ${error.message}`;
      $("agentSend").disabled = true;
    }
  }
  $("agentButton").onclick = () => {
    const open = panel.hidden;
    panel.hidden = !open;
    $("agentButton").setAttribute("aria-expanded", String(open));
    if (open) { if (!messages.childElementCount) message("Describe the mechanism, parameters and study you need. I can set up supported models and explain their limits."); refresh(); }
  };
  $("agentClose").onclick = () => { panel.hidden = true; $("agentButton").setAttribute("aria-expanded", "false"); };
  $("agentRefresh").onclick = () => { if (!pending) refresh(); };
  $("agentForm").onsubmit = async event => {
    event.preventDefault();
    const text = $("agentInput").value.trim();
    if (!text || pending || !modelSelect.value) return;
    if (reviewOutstanding) {message("Apply or discard the pending spatial proposal before sending another request.","error");return;}
    if (text.length > 4000) {message("The request exceeds 4,000 characters.","error");return;}
    const before = getSignature();
    const model = structuredClone(getModel());
    const bindings = structuredClone(getBindings());
    const prior = history.slice(-8);
    message(text,"user"); $("agentInput").value = "";
    pending = true; $("agentSend").disabled = true; $("agentStatus").textContent = "Thinking locally…";
    nativeDesktop?.notify("agent-busy");
    try {
      const response = await request("chat", {message:text,model,chatModel:modelSelect.value,history:prior});
      const answer = typeof response.answer === "string" ? response.answer : "The model returned no explanation.";
      const spatialProposal=Boolean(response.proposedModel && (model.kind === "spatial-assembly" || response.proposedModel.kind === "spatial-assembly"));
      message(`${spatialProposal ? "Agent explanation (unverified; proposal not yet applied)" : "Agent explanation (unverified; check the model and run status)"}:\n${answer}`);
      history.push({role:"user",content:text},{role:"assistant",content:answer});
      let ready = getSignature() === before && JSON.stringify(getBindings()) === JSON.stringify(bindings) && !isBusy();
      let reviewPending = false;
      if (response.proposedModel) {
        if (!ready) message("The model, STEP attachments or another operation changed while the agent was working. No proposed changes were applied.","error");
        else {
          const validation = await checkModel(response.proposedModel);
          ready = validation.valid && getSignature() === before && JSON.stringify(getBindings()) === JSON.stringify(bindings) && !isBusy();
          if (!ready) message(`The proposed changes were not applied. ${(validation.issues || []).map(issue=>issue.message).join(" ")}`,"error");
          else {
            const descriptions = (response.actions || []).map(action => {
              if (action.type === "load_example") return `Loaded example ${action.id}`;
              if (action.type === "set_parameters") return `Set parameters: ${Object.keys(action.values || {}).join(", ")}`;
              if (action.type === "set_simulation") return `Set study: ${Object.keys(action.values || {}).join(", ")}`;
              if (action.type === "set_spatial_gravity") return `Set gravity (m/s²): ${Object.entries(action.values || {}).map(([key,value])=>`${key}=${value}`).join(", ")}`;
              if (action.type === "edit_spatial_assembly") return (action.edits || []).map(edit=>`${edit.operation === "copy" ? "Copied" : edit.operation === "add" ? "Added" : "Updated"} ${edit.collection} ${edit.id}${edit.operation === "copy" ? ` from ${edit.sourceId}` : ""} (${Object.keys(edit.values || {}).join(", ")})`).join(" · ");
              return "Updated supported model";
            });
            if (model.kind === "spatial-assembly" || response.proposedModel.kind === "spatial-assembly") {
              const runAfter=response.runRequested && response.requiresUserRun === false && explicitRunRequest(text);
              reviewSpatial({before,original:model,proposed:structuredClone(response.proposedModel),bindings,descriptions,runAfter});
              reviewPending=true;
            } else {
              applyModel(response.proposedModel);
              message(`${descriptions.join(" · ") || "Updated the model"}. Use Undo to restore the previous model.`);
            }
          }
        }
      }
      if (!reviewPending && response.runRequested && response.requiresUserRun === false && explicitRunRequest(text) && ready) {
        message("Running the validated model as requested.");
        await run(false);
      } else if (response.runRequested && !explicitRunRequest(text)) {
        message("The agent requested a run, but your message did not explicitly ask to run it. Use Run simulation when ready.");
      }
      for (const tool of response.toolResults || []) if (tool.ok === false) message(`${tool.name}: ${tool.error || "Action could not be completed."}`,"error");
      $("agentStatus").textContent = "Local model service ready.";
    } catch (error) {
      message(error.message,"error");
      $("agentStatus").textContent = "Request failed. The current model was not changed.";
    } finally {
      nativeDesktop?.notify("agent-idle");
      pending = false; $("agentSend").disabled = !modelSelect.value;
    }
  };
}
