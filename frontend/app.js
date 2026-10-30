import { MechanismView } from "./viewport.js";
import { industry, signalsFor, industryCsvUnits } from "./industry.js";
import { restoreReferenceGeometry } from "./reference-geometry.js";
import { setupAgent } from "./agent.js";
import { assemblyInfo, renderAssemblyEditor } from "./assembly-editor.js";
import { spatialInfo, renderSpatialEditor } from "./spatial-editor.js";
import { loadStepAsset, restoreStepAsset, stepPartLabel } from "./step-asset.js";
import { createStepView } from "./step-view.js";
import { setupTour } from "./tour.js";
import { setupStepMass } from "./step-mass.js";
import { setupKinematics } from "./kinematics.js";
import { setupPointProbe } from "./point-probe.js";
import { setupWheelKinematics } from "./wheel-kinematics.js";
import { parseSolverCsv, fullSeries, seriesStatistics, envelope } from "./full-resolution.js";
import { faceAt, cadPlacement, worldFeature, jointFromFeature, frameFromFeature, measureFeatures, worldFromBody, alongAxis, inPlane } from "./cad-features.js";
import { studyParameters as listStudyParameters, parameterValue, caseModel, parseValues, suggestValues, caseSummary, summaryCsv, caseColors, pathKey, MAX_CASES } from "./studies.js";
import { syncFrameLinks } from "./frame-editor.js";

const $ = (id) => document.getElementById(id);
const paths = {
  file: "M6 3h8l4 4v14H6z M14 3v5h5",
  save: "M4 3h14l3 3v15H3V3z M7 3v6h10V3 M7 21v-8h10v8",
  play: "M7 4l13 8-13 8z",
  pause: "M7 4v16 M17 4v16",
  rewind: "M5 4v16 M19 4L7 12l12 8z",
  cube: "M12 3l9 5v10l-9 5-9-5V8z M3 8l9 5 9-5 M12 13v10",
  folder: "M3 7V4h7l2 3h9v13H3z",
  grid: "M3 3h7v7H3z M14 3h7v7h-7z M3 14h7v7H3z M14 14h7v7h-7z",
  book: "M12 5C8 2 4 3 2 4v15c4-2 7-1 10 1 3-2 6-3 10-1V4c-2-1-6-2-10 1z M12 5v15",
  sun: "M12 2v2 M12 20v2 M2 12h2 M20 12h2 M5 5l2 2 M17 17l2 2 M19 5l-2 2 M7 17l-2 2 M16 12a4 4 0 1 1-8 0 4 4 0 0 1 8 0",
  undo: "M4 5v6h6 M4 11a8 8 0 1 1 2 8",
  redo: "M20 5v6h-6 M20 11a8 8 0 1 0-2 8",
  check: "M4 12l5 5L20 6",
  code: "M8 5l-6 7 6 7 M16 5l6 7-6 7 M14 3l-4 18",
  network: "M8 4H3v5h5z M21 4h-5v5h5z M14 16H9v5h5z M5 9v3h14V9 M12 12v4",
  fit: "M3 9V3h6 M15 3h6v6 M21 15v6h-6 M9 21H3v-6",
  wave: "M2 12c4-16 6 16 10 0s6 16 10 0",
  download: "M12 2v13 M6 10l6 6 6-6 M3 17v5h18v-5",
  sliders: "M5 3v18 M12 3v18 M19 3v18 M2 8h6 M9 16h6 M16 7h6",
  clock: "M21 12a9 9 0 1 1-18 0 9 9 0 0 1 18 0 M12 6v6l4 2",
  info: "M21 12a9 9 0 1 1-18 0 9 9 0 0 1 18 0 M12 11v6 M12 7v1",
  chat: "M4 4h16v12H9l-5 4z M8 8h8 M8 12h6",
  close: "M5 5l14 14 M19 5L5 19",
  ground: "M3 9h18 M5 9l-3 5 M11 9l-4 7 M17 9l-4 7 M22 10l-5 6",
  joint: "M15 12a3 3 0 1 1-6 0 3 3 0 0 1 6 0 M3 12h6 M15 12h6 M12 3v6 M12 15v6",
  gravity: "M12 2v16 M6 12l6 6 6-6 M4 22h16",
  chart: "M3 3v18h18 M5 15l5-5 4 3 6-8",
  saveas: "M4 3h11l3 3v6 M7 3v5h8V3 M3 3v18h8 M15 15l5 5 M20 15l-5 5 M14 22h8",
  compass: "M21 12a9 9 0 1 1-18 0 9 9 0 0 1 18 0 M15.5 8.5l-2 5-5 2 2-5z",
  layers: "M12 3l9 5-9 5-9-5z M3 13l9 5 9-5 M3 17l9 5 9-5",
  trail: "M4 19c3-1 4-6 7-8s6 1 9-6 M18 4h3v3 M4 19h.01 M8 14h.01 M12 10h.01",
  tag: "M3 12V3h9l9 9-9 9z M8 8h.01",
  stepback: "M6 5v14 M18 5l-9 7 9 7z",
  stepforward: "M18 5v14 M6 5l9 7-9 7z",
  loop: "M17 2l4 4-4 4 M3 11V9a3 3 0 0 1 3-3h15 M7 22l-4-4 4-4 M21 13v2a3 3 0 0 1-3 3H3",
  cpu: "M6 6h12v12H6z M9 9h6v6H9z M9 2v4 M15 2v4 M9 18v4 M15 18v4 M2 9h4 M2 15h4 M18 9h4 M18 15h4",
  ruler: "M3 17L17 3l4 4L7 21z M7 13l2 2 M10 10l2 2 M13 7l2 2",
  eye: "M2 12s4-7 10-7 10 7 10 7-4 7-10 7S2 12 2 12z M15 12a3 3 0 1 1-6 0 3 3 0 0 1 6 0",
  force: "M12 3v14 M7 12l5 5 5-5 M5 21h14",
  present: "M3 4h18v12H3z M8 20h8 M12 16v4 M10 8l4 2-4 2z",
  pin: "M9 3h6l-1 6 4 4H6l4-4z M12 13v8",
  compare: "M3 17l5-6 4 3 4-7 5 4 M3 20h18 M3 9l5 3 4-5 4 4 5-6",
  newfile: "M6 3h8l4 4v14H6z M14 3v4h4 M12 11v6 M9 14h6",
};
function icon(name) {
  return `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="${paths[name] || paths.cube}"/></svg>`;
}
function hydrateIcons(root = document) {
  root.querySelectorAll("[data-icon]").forEach((el) => {
    el.innerHTML = icon(el.dataset.icon);
  });
}
hydrateIcons();

const defaults = {
  kind: "pendulum",
  name: "Gravity pendulum",
  parameters: { mass: 1, length: 1, angle: 30, gravity: 9.81 },
  simulation: { duration: 5, step: 0.005 },
};
const fields = {
  "source-example": [],
  "planar-assembly": [["gravity", "Gravity", "m/s²", 0, 0.01]],
  "spatial-assembly": [],
  ...Object.fromEntries(
    Object.entries(industry).map(([kind, info]) => [kind, info.fields]),
  ),
  pendulum: [
    ["mass", "Point mass", "kg", 0.0001, 0.1],
    ["length", "Link length", "m", 0.01, 0.1],
    ["angle", "Release angle", "°", -170, 1],
    ["gravity", "Gravity", "m/s²", 0.01, 0.01],
  ],
  "double-pendulum": [
    ["mass1", "Mass 1", "kg", 0.01, 0.1],
    ["mass2", "Mass 2", "kg", 0.01, 0.1],
    ["length1", "Link 1 length", "m", 0.01, 0.1],
    ["length2", "Link 2 length", "m", 0.01, 0.1],
    ["angle1", "Link 1 release angle", "°", -170, 1],
    ["angle2", "Link 2 release angle", "°", -170, 1],
    ["gravity", "Gravity", "m/s²", 0.01, 0.01],
  ],
  "mass-spring": [
    ["mass", "Translating mass", "kg", 0.0001, 0.1],
    ["stiffness", "Spring stiffness", "N/m", 0.01, 10],
    ["damping", "Viscous damping", "N·s/m", 0, 0.1],
    ["displacement", "Initial displacement", "m", -10, 0.01],
  ],
};
const state = {
  model: structuredClone(defaults),
  selection: "body",
  history: [],
  future: [],
  result: null,
  resultSignature: null,
  validation: null,
  solver: null,
  examples: [],
  sourceExamples: [],
  selectedNode: null,
  selectedForce: null,
  selectedJoint: null,
  measureNode: null,
  reference: null,
  step: null,
  playing: false,
  frame: 0,
  speed: 1,
  loop: true,
  trails: false,
  overlays: [],
  compareRun: null,
  busy: false,
  saving: false,
  signal: 0,
};
let view,
  savedTheme,
  validationTimer,
  lastFrame = 0,
  playTime = 0,
  pendingDownload,
  referenceLoad = 0, stepLoad = 0;
let applyingNativeProject = false, projectRevision = 0, browserDirty = false, activeRunToken = null;
const nativeDesktop = window.mbdynNative;
const stepMass = setupStepMass({
  getState:()=>({asset:state.step,model:state.model,partId:$("stepPart").value,busy:state.busy || state.saving || state.opening}),
  validateModel:checkModel,
  applyCandidate:candidate=>{pushHistory();applyModel(candidate,false);},
  notify:notice,
});
function markNativeDirty() {
  if (!applyingNativeProject) { projectRevision++; browserDirty = true; }
  if (nativeDesktop && !applyingNativeProject) {
    nativeDesktop.notify("dirty");
    scheduleAutosave();
  }
}
const signature = () => JSON.stringify(state.model);
const sourceInfo = (model = state.model) =>
  state.sourceExamples.find((example) => example.id === model.sourceExampleId);
const visualInfo = (model = state.model) => model.kind === "planar-assembly" ? assemblyInfo(model) : model.kind === "spatial-assembly" ? spatialInfo(model) : sourceInfo(model);
const assemblyKind = model => ["planar-assembly","spatial-assembly"].includes(model?.kind);
const sourceModel = (source) => ({
  kind: "source-example",
  name: source.title,
  sourceExampleId: source.id,
  sourceRevision: source.source.revision,
  sourceHashes: source.files.map((file) => file.sha256),
  parameters: {},
  simulation: structuredClone(source.simulation),
});
const escapeHtml = (value) =>
  String(value).replace(
    /[&<>"']/g,
    (char) =>
      ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[
        char
      ],
  );
const stale = () => state.result && state.resultSignature !== signature();
const format = (n, d = 3) => (Number.isFinite(n) ? n.toFixed(d) : "—");
let noticeTimer;
const noticeText = $("noticeText"), noticeClose = $("noticeClose");
function notice(message, type = "") {
  clearTimeout(noticeTimer);
  noticeText.textContent = message;
  // Other code may have replaced the toast's content; restore the text and close button.
  $("notice").replaceChildren(noticeText, noticeClose);
  $("notice").className = `notice ${type}`;
  $("notice").hidden = !message;
  // Informational toasts fade; warnings and errors stay until replaced or dismissed.
  if (message && !type) noticeTimer = setTimeout(() => { $("notice").hidden = true; }, 6000);
}
noticeClose.onclick = () => { clearTimeout(noticeTimer); $("notice").hidden = true; };
function status(message) {
  $("statusText").textContent = message;
}
function replaceReference(reference, dirty = true, disposePrevious = true) {
  const previous = state.reference;
  state.reference = reference;
  view?.setReference(reference);
  if (disposePrevious && previous && previous !== reference) previous.dispose();
  $("referenceStatus").hidden = !reference;
  $("referenceRemoveButton").hidden = !reference;
  $("referenceIsolateButton").hidden = !reference;
  $("referenceIsolateButton").textContent = "Isolate STL";
  $("referenceStatus").textContent = reference ? `Saved STL reference: ${reference.metadata.name} (${reference.metadata.unit}) · visual only` : "";
  if (dirty) markNativeDirty();
}
function validateStepForModel(asset, model) {
  if (!asset) return;
  const nodes = assemblyKind(model) ? visualInfo(model).initialNodes.filter(n => model.bodies.some(b => b.id === n.id)) : [];
  const test = createStepView(asset, {initialNodes:nodes, bindings:asset.metadata.bindings});
  test.dispose();
}
function renderStepReview() {
  const asset=state.step, pending=asset?.metadata.unverifiedBindings || {};
  const candidate=$('stepReviewCandidate').value;
  const entries=Object.entries(pending);
  $('stepReview').hidden=!entries.length;
  $('stepReviewCandidate').replaceChildren(...entries.map(([id,binding])=>{const option=document.createElement('option');option.value=id;option.textContent=`Saved slot ${id} · body ${binding.body}`;return option;}));
  if (Object.hasOwn(pending,candidate)) $('stepReviewCandidate').value=candidate;
  const id=$('stepReviewCandidate').value, binding=pending[id], index=Number(id.split(':',1)[0]);
  $('stepReviewDetail').textContent=binding ? `Source: ${asset.metadata.files[index]?.name || 'unknown'} · body: ${binding.body} · original registration pose: ${JSON.stringify(binding.pose)}` : '';
  const placeholder=document.createElement('option');placeholder.value='';placeholder.textContent='Choose a current part after inspection';
  $('stepReviewTarget').replaceChildren(placeholder,...(asset?.parts || []).filter(part=>part.id.startsWith(`${index}:`)).map(part=>{const option=document.createElement('option');option.value=part.id;option.textContent=stepPartLabel(part);return option;}));
}
function renderStepControls() {
  const asset=state.step;
  $("stepRemove").hidden=!asset;
  $("stepBindings").hidden=!asset;
  $("stepMass").hidden=!asset;
  stepMass.clear();
  $("stepBodyLabel").hidden=!assemblyKind(state.model);
  $("stepBind").hidden=!assemblyKind(state.model);
  const pending=Object.keys(asset?.metadata.unverifiedBindings || {}).length;
  $("stepDetail").textContent=asset ? `${asset.metadata.files.length} STEP files · ${asset.parts.length} solid parts · ${Object.keys(asset.metadata.bindings).length} attached${pending ? ` · ${pending} awaiting review` : ''}. Source units converted to metres. Define mass, inertia and joints in the physical model.` : "No STEP geometry loaded. Import .step or .stp solids; define mass, inertia and joints separately.";
  renderStepReview();
  $("stepStatus").hidden=!asset;
  $("stepStatus").textContent=asset ? `STEP solids · ${Object.keys(asset.metadata.bindings).length} attached · visual geometry` : "";
  if (!asset) return;
  const selected=$("stepPart").value;
  $("stepPart").replaceChildren(...asset.parts.map(part=>{const option=document.createElement("option");option.value=part.id;option.textContent=stepPartLabel(part);return option;}));
  if (asset.parts.some(p=>p.id===selected)) $("stepPart").value=selected;
  $("stepBody").replaceChildren(...[{id:"",name:"Unattached (static)"},...(assemblyKind(state.model) ? state.model.bodies : [])].map(body=>{const option=document.createElement("option");option.value=body.id;option.textContent=body.name;return option;}));
  $("stepBody").value=asset.metadata.bindings[$("stepPart").value]?.body || "";
}
function replaceStep(asset, dirty=true) {
  validateStepForModel(asset,state.model);
  if (dirty) pushHistory();
  state.step=asset;
  view?.setStepAsset(asset);
  if (state.result && !stale()) setFrame(state.frame);
  renderStepControls();
  if (dirty) {markNativeDirty();updateHistoryButtons();}
}
async function createPrimitiveSolid(bodyId, spec) {
  if(state.busy || state.opening || state.saving)throw Error("Wait for the current operation before creating a solid.");
  const before=signature(), previous=state.step, token=++stepLoad, body=state.model.bodies.find(item=>item.id===bodyId);
  if(!body)throw Error("Select a valid assembly body first.");
  const pose=structuredClone(body.pose);
  const response=await fetch("/api/step/primitive",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({shape:spec.shape,dimensions:spec.dimensions,pose})});
  if(!response.ok){let detail;try{detail=await response.json();}catch{}throw Error(detail?.error || "STEP solid generation failed.");}
  const generated=await loadStepAsset([{name:`${bodyId}-${spec.shape}.step`,bytes:new Uint8Array(await response.arrayBuffer())}]);
  if(signature()!==before || state.step!==previous || state.busy || state.opening || state.saving || token!==stepLoad)throw Error("The model or CAD geometry changed during generation; nothing was applied.");
  if(generated.parts.length!==1)throw Error("The generated solid did not contain exactly one part.");
  const existing=previous?.metadata.files || [], sourceBytes=existing.reduce((sum,file)=>sum+file.byteLength,0)+generated.metadata.files[0].byteLength;
  const triangles=(previous?.parts || []).reduce((sum,part)=>sum+part.indices.length/3,0)+generated.parts[0].indices.length/3;
  if(existing.length>=24 || sourceBytes>12*1024*1024 || triangles>200000)throw Error("Adding this solid would exceed STEP file, size or triangle limits.");
  const part={...generated.parts[0],id:`${existing.length}:${generated.parts[0].id.split(":").slice(1).join(":")}`};
  const binding={body:bodyId,pose:state.model.kind === "spatial-assembly" ? {...pose} : {x:pose.x,y:0,z:pose.z,ry:pose.angleDeg}};
  const witness=generated.metadata.occurrenceWitnesses?.[generated.parts[0].id];
  const asset={units:"m",parts:[...(previous?.parts || []),part],metadata:{schemaVersion:1,format:"step",files:[...existing,...generated.metadata.files],bindings:{...(previous?.metadata.bindings || {}),[part.id]:binding},occurrenceWitnesses:{...(previous?.metadata.occurrenceWitnesses || {}),...(witness ? {[part.id]:witness} : {})},unverifiedBindings:{...(previous?.metadata.unverifiedBindings || {})}}};
  const draft=structuredClone(state.model), target=draft.bodies.find(item=>item.id===bodyId);
  target.mass=spec.properties.mass;target.inertia=structuredClone(spec.properties.inertia);
  if(draft.kind === 'spatial-assembly') target.centerOfMass={x:0,y:0,z:0};
  const validation=await checkModel(draft);
  if(signature()!==before || state.step!==previous || state.busy || state.opening || state.saving || token!==stepLoad)throw Error("The model or CAD geometry changed during generation; nothing was applied.");
  if(!validation.valid)throw Error((validation.issues || []).map(issue=>issue.message).join(" ") || "The updated physical model is invalid.");
  validateStepForModel(asset,draft);
  pushHistory();state.model=draft;state.step=asset;if(view)view.stepAsset=asset;
  changed();renderTree();renderProperties();renderStepControls();view?.setSelection(state.selection);
  if(!previous && state.model.kind==='spatial-assembly' && state.model.joints.length===0)view?.reset();
  notice(`Created and attached ${spec.shape} STEP solid with mass ${spec.properties.mass.toPrecision(6)} kg. Other attached geometry is not included in these physical properties.`,"");
}
function download(name, text, type = "text/plain") {
  const url = URL.createObjectURL(new Blob([text], { type }));
  const link = document.createElement("a");
  link.href = url;
  link.download = name;
  link.click();
  setTimeout(() => URL.revokeObjectURL(url), 2000);
}
function saveLocal() {
  try {
    localStorage.setItem(
      "mbdyn-studio-project",
      JSON.stringify({ format: "mbdyn-studio/1", model: state.model }),
    );
  } catch {
    status(
      "Browser storage unavailable. Use Save project to retain your work.",
    );
  }
}
async function api(path, model, runToken = null) {
  const response = await fetch(
    `/api/${path}`,
    model
      ? {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(runToken ? { model, runToken } : { model }),
        }
      : undefined,
  );
  let data;
  try {
    data = await response.json();
  } catch {
    throw new Error(
      "The local backend returned an unreadable response. Check the server log.",
    );
  }
  if (!response.ok) {
    const error = new Error(
      data.error || data.message || `Request failed (${response.status})`,
    );
    error.issues = data.issues;
    error.details = data;
    throw error;
  }
  return data;
}
async function checkModel(model) {
  if (model.kind !== "source-example") return api("validate", model);
  const source = sourceInfo(model);
  const valid = Boolean(
    source?.enabled &&
    model.name === source.title &&
    model.sourceRevision === source.source.revision &&
    JSON.stringify(model.sourceHashes) ===
      JSON.stringify(source.files.map((file) => file.sha256)) &&
    JSON.stringify(model.parameters) === "{}" &&
    model.simulation?.duration === source.simulation.duration &&
    model.simulation?.step === source.simulation.step,
  );
  return valid
    ? api("validate", model)
    : {
        valid: false,
        issues: [
          {
            level: "error",
            field: "model",
            message:
              "This source model is unavailable or its preserved study settings were changed.",
          },
        ],
      };
}
async function runSource(id, runToken = null) {
  const response = await fetch("/api/source-run", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(runToken ? { id, runToken } : { id }),
  });
  const data = await response.json();
  if (!response.ok) {
    const error = new Error(
      data.error || `Source run failed (${response.status})`,
    );
    error.details = data;
    throw error;
  }
  return data;
}
function snapshot() { return {model:structuredClone(state.model),step:state.step}; }
function pushHistory() {
  state.history.push(snapshot());
  if (state.history.length > 50) state.history.shift();
  state.future = [];
}
function updateHistoryButtons() {
  $("undoButton").disabled = !state.history.length || state.busy;
  $("redoButton").disabled = !state.future.length || state.busy;
}
function changed() {
  markNativeDirty();
  if (state.step && assemblyKind(state.model)) {
    const ids = new Set(state.model.bodies.map(body => body.id));
    if (Object.values(state.step.metadata.bindings).some(binding => !ids.has(binding.body))) {
      state.step = {...state.step,metadata:{...state.step.metadata,bindings:Object.fromEntries(Object.entries(state.step.metadata.bindings).filter(([,binding]) => ids.has(binding.body)))}};
      if (view) view.stepAsset=state.step;
      notice("A STEP attachment was removed with its body; check the remaining part bindings.", "warn");
      renderStepControls();
    }
  }
  state.playing = false;
  state.validation = null;
  saveLocal();
  updateHistoryButtons();
  renderMetadata();
  $("validationBadge").textContent = "Needs check";
  $("validationBadge").className = "badge";
  if (state.result) {
    renderResult();
    if (stale())
      notice(
        "Parameters changed. The plot belongs to the previous model; the 3D view shows the edited initial configuration. Run again to update the response.",
        "warn",
      );
    else
      notice(
        "Model restored. The displayed response matches these parameters.",
      );
  }
  const p = state.model.parameters;
  if (
    (state.model.kind === "spatial-assembly" ? Object.values(p.gravity || {}).every(Number.isFinite) : Object.values(p).every(Number.isFinite)) &&
    (["source-example", "planar-assembly", "spatial-assembly"].includes(state.model.kind)
      ? Boolean(visualInfo()) && (!assemblyKind(state.model) || (state.model.bodies.length > 0 && state.model.bodies.every(body => Object.values(body.pose).every(Number.isFinite) && Object.values(body.velocity).every(Number.isFinite)) && state.model.joints.every(joint => Object.values(joint.parentAnchor || joint.anchorA).every(Number.isFinite) && Object.values(joint.childAnchor || joint.anchorB).every(Number.isFinite)) && (state.model.forces || []).every(force => Object.values(force.anchorA).every(Number.isFinite) && Object.values(force.anchorB).every(Number.isFinite))))
      : industry[state.model.kind]
        ? Object.entries(p).every(
            ([key, value]) => !/mass|length|stiffness/i.test(key) || value > 0,
          )
        : state.model.kind === "double-pendulum"
          ? p.mass1 > 0 && p.mass2 > 0 && p.length1 > 0 && p.length2 > 0
          : p.mass > 0 && (state.model.kind !== "pendulum" || p.length > 0))
  )
    view?.setModel(state.model, false, visualInfo());
  if (state.result && !stale()) setFrame(state.frame);
  else {
    $("viewTime").textContent = "t = 0.000 s";
    $("viewSource").textContent = "Initial configuration";
  }
  clearTimeout(validationTimer);
  validationTimer = setTimeout(() => validate(false), 300);
}
function setNumber(section, key, raw) {
  pushHistory();
  state.model[section][key] = raw.trim() === "" ? null : Number(raw);
  changed();
}
function renderMetadata() {
  $("kinematicsButton").hidden = state.model.kind !== "spatial-assembly";
  const m = state.model;
  const source = sourceInfo(m);
  const industrial = industry[m.kind];
  const pendulum = m.kind !== "mass-spring";
  const double = m.kind === "double-pendulum";
  $("documentName").textContent = m.name;
  $("treeProjectName").textContent = m.name;
  $("viewportName").textContent = m.name;
  $("mechanismType").textContent = double
    ? "DOUBLE PENDULUM"
    : pendulum
      ? "PENDULUM"
      : "MASS–SPRING";
  $("viewportDescription").textContent = double
    ? "Two connected bodies. Coupled, nonlinear motion."
    : pendulum
      ? "Gravity, inertia and one rotational degree of freedom."
      : "A guided mass, an elastic spring and viscous damping.";
  $("signalTitle").textContent = double
    ? "Link angles · 1 / 2"
    : pendulum
      ? "Angular displacement"
      : "Linear displacement";
  if (!state.result) {
    $("durationMetric").innerHTML = `${format(m.simulation.duration, 2)} <span>s</span>`;
    $("stepMetric").innerHTML = `${Number.isFinite(m.simulation.step) ? String(m.simulation.step) : "—"} <span>s</span>`;
  }
  $("endTime").textContent = `${format(m.simulation.duration)} s`;
  $("modelKindBadge").textContent = double
    ? "2 moving bodies · 2 joints"
    : pendulum
      ? "1 moving body · 1 joint"
      : "1 moving body · 1 translation";
  $("assumptions").textContent = double
    ? "Two point masses on massless rigid links with planar revolute constraints. Both input angles are absolute from vertical down. Zero initial angular velocity; no damping. The visible geometry is illustrative."
    : pendulum
      ? "Ideal point mass on a massless rigid link, constrained to a vertical plane. No friction or aerodynamic drag. The visible sphere and support are illustrative."
      : "A mass constrained to horizontal translation with a linear spring and viscous damper. No gravity along the travel axis. The visible block and rail are illustrative.";
  if (industrial) {
    $("mechanismType").textContent = industrial.title;
    $("viewportDescription").textContent = industrial.description;
    $("modelKindBadge").textContent = industrial.badge;
    $("assumptions").textContent = industrial.assumptions;
    $("signalTitle").textContent = industrial.signals[0].title;
  }
  if (source) {
    $("mechanismType").textContent = `${source.category} · UPSTREAM MODEL`;
    $("viewportDescription").textContent = source.description;
    $("modelKindBadge").textContent =
      `${source.nodes.length} recorded nodes · ${source.license.spdx}`;
    $("assumptions").textContent =
      `${source.visualizationNote} Original upstream input is read-only in this viewer. Source: ${source.source.url}. ${source.license.evidence}`;
    $("signalTitle").textContent = "Node position · X / Y / Z";
  }
  if (m.kind === "planar-assembly") {
    $("mechanismType").textContent = "PLANAR RIGID-BODY ASSEMBLY";
    $("viewportDescription").textContent = "Author planar bodies, revolute hinges, sliders and loads in the X–Z plane.";
    $("modelKindBadge").textContent = `${m.bodies.length} bodies · ${m.joints.length} joints`;
    $("assumptions").textContent = "Planar rigid bodies in a rooted tree of revolute and prismatic joints, with optional axial spring-dampers and constant COM loads. Node-origin links are schematic. Closed loops, contact, flexible bodies and prescribed drives are not yet supported in this editor.";
    $("signalTitle").textContent = "Body position · X / Y / Z";
  }
  if (m.kind === "spatial-assembly") {
    $("mechanismType").textContent = "3D RIGID-BODY ASSEMBLY";
    $("viewportDescription").textContent = "Edit 3D bodies and local-frame joints; loop constraints are solved by MBDyn.";
    const dof = spatialMobility(m);
    $("modelKindBadge").textContent = `${m.bodies.length} bodies · ${m.joints.length} joints · ${dof} DOF (Grübler)`;
    $("assumptions").textContent = "3D rigid bodies may be free or joined with revolute, prismatic, cylindrical, universal, spherical or weld joints, with optional 3D spring-dampers. Loop solvability and nonredundant constraints must be verified by the solver. STEP mass properties can be calculated at an explicit density and applied when body-frame requirements are met.";
    $("signalTitle").textContent = "Body position · X / Y / Z";
  }
  $("treeProjectKind").textContent = m.kind === "spatial-assembly" ? "3D rigid-body assembly" : m.kind === "planar-assembly" ? "Planar rigid-body assembly" : m.kind === "source-example" ? "Upstream MBDyn deck" : industrial ? "Engineering template" : "Parametric mechanism";
  renderChecklist();
}
// Grübler–Kutzbach mobility estimate; redundant loop constraints make the true value larger.
const CONSTRAINED = { revolute: 5, prismatic: 5, cylindrical: 4, spherical: 3, universal: 4, weld: 6 };
function spatialMobility(model) {
  return 6 * model.bodies.length - model.joints.reduce((sum, joint) => sum + (CONSTRAINED[joint.type] || 0) + (joint.motion ? 1 : 0), 0);
}
function renderChecklist() {
  const m = state.model, items = [];
  const valid = state.validation?.valid;
  items.push([valid === true ? "ok" : valid === false ? "bad" : "", "Model inputs", valid === true ? "passed" : valid === false ? `${(state.validation.issues || []).length} issue(s)` : "not checked"]);
  const solverReady = state.solver?.available;
  items.push([solverReady ? "ok" : state.solver ? "bad" : "", "MBDyn solver", solverReady ? state.solver.version || "ready" : state.solver ? "not configured" : "checking"]);
  const steps = Number.isFinite(m.simulation?.duration / m.simulation?.step) ? Math.ceil(m.simulation.duration / m.simulation.step) : NaN;
  items.push([Number.isFinite(steps) ? (steps > 20000 ? "bad" : "ok") : "bad", "Time steps", Number.isFinite(steps) ? steps.toLocaleString() : "—"]);
  if (m.kind === "spatial-assembly") {
    const analysis = state.validation?.summary?.mobility;
    if (analysis) {
      const redundant = analysis.redundant.length;
      items.push([redundant ? "warn" : "ok", "Mobility (constraint rank)", `${analysis.dof} DOF${redundant ? ` · ${redundant} redundant` : ""}`]);
    } else {
      const dof = spatialMobility(m);
      items.push([dof >= 0 ? "ok" : "warn", "Mobility (Grübler)", `${dof} DOF`]);
    }
  }
  items.push([state.result ? (stale() ? "warn" : "ok") : "", "Result", state.result ? (stale() ? "stale · rerun" : "current") : "none"]);
  $("checklist").replaceChildren(...items.map(([cls, label, detail]) => {
    const li = document.createElement("li");
    li.className = cls;
    li.innerHTML = `<span class="mark">${cls === "ok" ? "✓" : cls === "bad" ? "!" : cls === "warn" ? "~" : "·"}</span><span>${escapeHtml(label)}</span><small>${escapeHtml(detail)}</small>`;
    return li;
  }));
  const redundant = m.kind === "spatial-assembly" ? state.validation?.summary?.mobility?.redundant || [] : [];
  if (redundant.length) {
    const li = document.createElement("li");
    li.className = "redundancy";
    li.innerHTML = `<p>Redundant constraints — MBDyn will reject this assembly. Make the loop exact, e.g. a spherical joint at one end of a link and a universal joint at the other.</p><ul>${redundant.map((item) => `<li><button type="button" data-joint="${escapeHtml(item.joint)}">${escapeHtml(item.joint)}</button> ${escapeHtml(item.component)}</li>`).join("")}</ul>`;
    li.querySelectorAll("[data-joint]").forEach((button) => { button.onclick = () => { switchStep("model"); select(`joint-${button.dataset.joint}`); }; });
    $("checklist").append(li);
  }
  const seconds = m.simulation?.duration, dt = m.simulation?.step;
  $("stepSummary").textContent = Number.isFinite(steps) ? `${steps.toLocaleString()} implicit steps of ${dt} s cover ${seconds} s. Smaller steps capture faster motion and take longer.` : "Enter a positive duration and time step.";
}
function renderTree() {
  const pendulum = state.model.kind !== "mass-spring";
  const double = state.model.kind === "double-pendulum";
  const entries = [
    [
      "BODIES",
      "2",
      [
        ["ground", "ground", "Ground", "Fixed"],
        ["body", "cube", pendulum ? "Point mass" : "Translating mass", ""],
      ],
    ],
    [
      "CONNECTIONS",
      "1",
      [
        [
          "joint",
          "joint",
          pendulum ? "Revolute joint" : "Prismatic guide",
          "1 DOF",
        ],
      ],
    ],
    [
      "EXCITATION",
      "1",
      [
        [
          pendulum ? "load" : "spring",
          pendulum ? "gravity" : "wave",
          pendulum ? "Gravity" : "Spring + damper",
          "",
        ],
      ],
    ],
    ["STUDIES", "1", [["study", "clock", "Transient response", ""]]],
  ];
  if (double) {
    entries[0][1] = "3";
    entries[0][2][1][2] = "Mass 1";
    entries[0][2].push(["body2", "cube", "Mass 2", ""]);
    entries[1][1] = "2";
    entries[1][2][0][2] = "Ground revolute";
    entries[1][2].push(["joint2", "joint", "Link revolute", "1 DOF"]);
  }
  const industrial = industry[state.model.kind];
  if (industrial) {
    entries[0] = [
      "BODIES",
      String(industrial.bodies.length),
      industrial.bodies,
    ];
    entries[1] = [
      "CONNECTIONS",
      String(industrial.connections.length),
      industrial.connections,
    ];
    entries[2] = [
      "EXCITATION",
      String(industrial.excitation.length),
      industrial.excitation,
    ];
  }
  const source = sourceInfo();
  if (source) {
    entries[0] = [
      "NODES",
      String(source.nodes.length),
      source.nodes.map((node, index) => [
        index ? `node-${node.id}` : "body",
        "cube",
        node.label,
        String(node.id),
      ]),
    ];
    entries[1] = [
      "CONNECTIONS",
      String(source.connections.length),
      source.connections.map((connection) => [
        "joint",
        "joint",
        connection.label,
        `${connection.from} ↔ ${connection.to}`,
      ]),
    ];
    entries[2] = [
      "PROVENANCE",
      "1",
      [["source", "book", "Upstream model", source.license.spdx]],
    ];
  }
  if (state.model.kind === "planar-assembly") {
    entries[0] = ["BODIES", String(state.model.bodies.length), state.model.bodies.map((body,index) => [index ? `node-${body.id}` : "body", "cube", body.name, body.id])];
    entries[1] = ["JOINTS", String(state.model.joints.length), state.model.joints.map(joint => [`joint-${joint.id}`, "joint", joint.id, `${joint.parent} ↔ ${joint.child}`])];
    entries[2] = ["FORCES", String(1+(state.model.forces || []).length+(state.model.loads || []).length+(state.model.rotationalElements || []).length+(state.model.jointTorques || []).length), [["load", "gravity", "Gravity", ""],...(state.model.forces || []).map(force=>[`force-${force.id}`,"spring",force.id,`${force.a} ↔ ${force.b}`]),...(state.model.loads || []).map(load=>[`applied-${load.id}`,"gravity",load.id,load.body]),...(state.model.rotationalElements || []).map(item=>[`rotary-${item.id}`,"spring",item.id,item.joint]),...(state.model.jointTorques || []).map(item=>[`torque-${item.id}`,"joint",item.id,item.joint])]];
  }
  if (state.model.kind === "spatial-assembly") {
    entries[0] = ["BODIES", String(state.model.bodies.length), state.model.bodies.map((body,index)=>[index?`node-${body.id}`:"body","cube",body.name,body.id])];
    entries[1] = ["JOINTS", String(state.model.joints.length), state.model.joints.map(joint=>[`joint-${joint.id}`,"joint",joint.id,`${joint.a} ↔ ${joint.b}`])];
    entries[2] = ["FORCES", String(1+(state.model.forces || []).length+(state.model.loads || []).length+(state.model.rotationalElements || []).length+(state.model.jointTorques || []).length+(state.model.jointForces || []).length+(state.model.contacts || []).length), [["load","gravity","Gravity",""],...(state.model.forces || []).map(item=>[`force-${item.id}`,"spring",item.id,`${item.a} ↔ ${item.b}`]),...(state.model.loads || []).map(item=>[`applied-${item.id}`,"gravity",item.id,item.body]),...(state.model.rotationalElements || []).map(item=>[`rotary-${item.id}`,"spring",item.id,item.joint]),...(state.model.jointTorques || []).map(item=>[`torque-${item.id}`,"joint",item.id,item.joint]),...(state.model.jointForces || []).map(item=>[`joint-force-${item.id}`,"joint",item.id,item.joint]),...(state.model.contacts || []).map(item=>[`contact-${item.id}`,"force",item.id,item.body])]];
  }
  const root = $("modelTree");
  root.replaceChildren();
  for (const [name, count, rows] of entries) {
    const group = document.createElement("div");
    group.className = "tree-group";
    group.innerHTML = `<span>${name}</span><span>${count}</span>`;
    root.append(group);
    for (const [id, symbol, label, badge] of rows) {
      const button = document.createElement("button");
      button.className = `tree-item ${state.selection === id ? "active" : ""}`;
      button.dataset.entity = id;
      button.setAttribute("aria-pressed", String(state.selection === id));
      button.innerHTML = `${icon(symbol)}<span>${escapeHtml(label)}</span><span class="tree-state">${escapeHtml(badge)}</span>`;
      button.onclick = () => select(id);
      root.append(button);
    }
  }
  renderTopology();
}
function select(entity) {
  state.selection = entity;
  const source = visualInfo();
  if (source && (entity === "body" || entity.startsWith("node-"))) {
    state.selectedNode =
      entity === "body"
        ? source.nodes[0]?.id
        : source.nodes.find((node) => `node-${node.id}` === entity)?.id;
    if (["source-example", "planar-assembly", "spatial-assembly"].includes(state.result?.model?.kind)) renderResult();
  }
  renderTree();
  renderProperties();
  view?.setSelection(entity);
  if ($("followToggle").checked) view?.setFollow(entity);
  if ($("trailBodies").value === "selected") refreshTrails();
  if (entity === "study") { switchStep("simulate"); $("durationInput").focus(); }
}
/** Name and short description of an entity for hover tooltips. */
function describeEntity(entity) {
  const model = state.model, id = entity.replace(/^(joint|force|node|contact|applied)-/, "");
  if (model.kind === "spatial-assembly") {
    const body = entity === "body" ? model.bodies[0] : entity.startsWith("node-") ? model.bodies.find((b) => b.id === id) : null;
    if (body) return [body.name, `Rigid body · ${format(body.mass, 4)} kg`];
    const joint = entity.startsWith("joint-") && model.joints.find((j) => j.id === id);
    if (joint) return [joint.id, `${joint.type[0].toUpperCase()}${joint.type.slice(1)} joint · ${joint.a} ↔ ${joint.b}`];
    const force = entity.startsWith("force-") && (model.forces || []).find((f) => f.id === id);
    if (force) return [force.id, `${force.type === "oleo-strut" ? "Oleo-pneumatic strut" : "Spring-damper"} · ${force.a} ↔ ${force.b}`];
    const contact = entity.startsWith("contact-") && (model.contacts || []).find((c) => c.id === id);
    if (contact) return [contact.id, `Sphere-plane contact · ${contact.body}`];
  }
  const item = document.querySelector(`#modelTree [data-entity="${CSS.escape(entity)}"]`);
  return item ? [item.children[1]?.textContent || entity, item.children[2]?.textContent || ""] : [entity, ""];
}
/** Hover from the 3D view: tooltip at the cursor and the matching tree row highlighted. */
function showHover(entity, x, y) {
  const tip = $("viewTooltip");
  document.querySelectorAll("#modelTree .tree-item.hovered").forEach((item) => item.classList.remove("hovered"));
  if (!entity || entity.startsWith("step-part-")) { tip.hidden = true; return; }
  document.querySelector(`#modelTree [data-entity="${CSS.escape(entity)}"]`)?.classList.add("hovered");
  const [name, detail] = describeEntity(entity);
  placeTooltip(name, jointDrag.accepts(entity) ? `${detail} · drag to move it, or onto a CAD feature to snap` : detail, x, y);
}
function placeTooltip(name, detail, x, y) {
  const tip = $("viewTooltip");
  tip.innerHTML = `<b>${escapeHtml(name)}</b>${detail ? `<span>${escapeHtml(detail)}</span>` : ""}`;
  const rect = $("canvasMount").getBoundingClientRect();
  tip.hidden = false;
  const left = Math.min(x - rect.left + 14, rect.width - tip.offsetWidth - 8);
  const top = y - rect.top + 18 + tip.offsetHeight > rect.height ? y - rect.top - tip.offsetHeight - 10 : y - rect.top + 18;
  tip.style.left = `${Math.max(8, left)}px`;
  tip.style.top = `${Math.max(8, top)}px`;
}
// ---------- Picking CAD features ----------
// Faces are evaluated at the initial configuration, so the view shows it while a pick is active.
function featureFromHit(hit) {
  if (!hit || !state.step) return null;
  const part = state.step.parts.find((item) => item.id === hit.partId);
  const face = Number.isInteger(hit.edge) ? part?.edges?.[hit.edge] || null : faceAt(part, hit.triangle);
  if (!face) return null;
  const binding = state.step.metadata.bindings[hit.partId];
  let body = binding && (state.model.bodies || []).find((item) => item.id === binding.body);
  // Measuring in Post-processing uses each body's pose in the displayed frame.
  if (body && pickAtFrame) {
    const node = state.result?.samples[state.frame]?.nodes?.find((item) => String(item.id) === body.id);
    if (node) body = { ...body, pose: node };
  }
  return { ...worldFeature(face, cadPlacement(binding, body), hit.point), part: part.name };
}
let picking = false, pickAtFrame = false;
/** Pick CAD features at the initial configuration, or with `atFrame` at the displayed result frame. */
function startPick(text, onFeature, atFrame = false) {
  if (state.model.kind !== "spatial-assembly" || !state.step || !view) return notice("Import STEP parts into a 3D assembly to pick CAD features.", "warn");
  stopPick();
  picking = true;
  pickAtFrame = atFrame;
  if (!atFrame) view.setSample(null);
  $("pickText").textContent = text;
  $("pickBar").hidden = false;
  view.setPickMode({
    hover: (hit, x, y) => {
      const feature = featureFromHit(hit);
      view.showFeature(feature);
      if (feature) placeTooltip(feature.label, feature.part, x, y);
      else $("viewTooltip").hidden = true;
    },
    select: (hit) => {
      const feature = featureFromHit(hit);
      if (!feature) return notice("Pick a cylindrical or planar face, or a circular edge, of a STEP part.", "warn");
      onFeature(feature);
    },
  });
}
function stopPick() {
  if (!picking) return;
  picking = false;
  pickAtFrame = false;
  view?.setPickMode(null);
  $("pickBar").hidden = true;
  $("viewTooltip").hidden = true;
  $("measureViewButton").setAttribute("aria-pressed", "false");
  if (state.result && !stale()) setFrame(state.frame);
}
$("pickCancel").onclick = stopPick;
/** Put both ends of a joint on one picked feature: the anchors coincide and the axes agree. */
function pickJointFromCad(jointId) {
  if ((state.model.frameLinks || []).some((link) => link.joint === jointId)) return notice("This joint follows a linked reference frame; unlink it before placing it from CAD.", "warn");
  startPick(`Joint ${jointId}: click a bore, shaft or pin (cylindrical face), a hole rim (circular edge) or a planar face.`, (feature) => {
    stopPick();
    placeJoint(jointId, feature);
  });
}
function placeJoint(jointId, feature) {
  const joint = state.model.joints.find((item) => item.id === jointId);
  if (!joint) return;
  const values = jointFromFeature(state.model, joint, feature);
  pushHistory();
  Object.assign(joint, values);
  changed();
  renderTree();
  renderProperties();
  view?.setSelection(state.selection);
  notice(feature.part
    ? `Joint ${jointId} placed on ${feature.part} · ${feature.label}. Both ends share the anchor${values.axisA ? " and axis" : ""}; Undo restores the previous placement.`
    : `Joint ${jointId} moved ${feature.label}. Both ends keep a shared anchor; Undo restores the previous placement.`);
}
/**
 * Where a dragged joint goes: the CAD feature under the pointer, or a constrained move from its
 * current anchor in 1 mm steps — along its axis (Shift ignores CAD), across it (Alt), or in the
 * view plane for joints without a single axis.
 */
function jointDragTarget(id, hit, input) {
  const joint = state.model.joints.find((item) => item.id === id);
  if (!joint || !input?.ray) return null;
  if (!input.shift && !input.alt) {
    const feature = featureFromHit(hit);
    if (feature) return feature;
  }
  const body = state.model.bodies.find((item) => item.id === joint.a);
  const axial = ["revolute", "cylindrical", "prismatic"].includes(joint.type) && joint.axisA;
  const start = worldFromBody(body, joint.anchorA, joint.axisA || { x: 0, y: 0, z: 1 });
  const [moved, how] = axial && !input.alt
    ? [alongAxis(start.point, start.direction, input.ray), "along its axis"]
    : [inPlane(start.point, axial ? start.direction : input.view, input.ray), axial ? "across its axis" : "in the view plane"];
  if (!moved) return null;
  return { type: "drag", point: moved.point, axis: start.direction, label: `${how} by ${(moved.offset * 1000).toFixed(0)} mm` };
}
/** Drag a joint symbol in Pre-processing: it snaps to a CAD feature, or moves along or across its axis. */
const jointDrag = {
  accepts(entity) {
    if (workspace !== "model" || state.busy || state.model.kind !== "spatial-assembly" || !entity.startsWith("joint-")) return false;
    const id = entity.slice("joint-".length);
    return state.model.joints.some((joint) => joint.id === id) && !(state.model.frameLinks || []).some((link) => link.joint === id);
  },
  id: null,
  start(entity) {
    jointDrag.id = entity.slice("joint-".length);
    view.setSample(null);
    $("viewTooltip").hidden = true;
    const cad = state.step?.parts?.some((part) => part.faces?.length || part.edges?.length);
    $("pickText").textContent = `Joint ${entity.slice("joint-".length)}: ${cad ? "drop on a bore, shaft, pin, hole rim or face, or away from the CAD to slide along the axis" : "drag to slide along the axis"}. Shift: along the axis only · Alt: across the axis · Esc cancels.`;
    $("pickBar").hidden = false;
  },
  move(hit, x, y, input) {
    const target = jointDragTarget(jointDrag.id, hit, input);
    view.showFeature(target);
    if (target) placeTooltip(target.part ? target.label : `Move ${target.label}`, target.part, x, y);
    else $("viewTooltip").hidden = true;
  },
  drop(entity, hit, input) {
    const id = entity.slice("joint-".length), target = jointDragTarget(id, hit, input);
    jointDrag.cancel();
    if (target) placeJoint(id, target);
    else notice(`Joint ${id} is unchanged: the drag ran parallel to its axis or plane.`, "warn");
  },
  cancel() {
    view.showFeature(null);
    $("pickBar").hidden = true;
    $("viewTooltip").hidden = true;
    if (state.result && !stale()) setFrame(state.frame);
  },
};
/** Put a named frame's origin on a picked feature with local +Z along its axis; linked joints follow. */
function pickFrameFromCad(frameId) {
  startPick(`Frame ${frameId}: click a cylindrical or planar face; local +Z follows its axis or normal.`, (feature) => {
    const frame = (state.model.frames || []).find((item) => item.id === frameId);
    if (!frame) return stopPick();
    // Linked joint ends follow the frame; check them on a copy before touching the model.
    const values = frameFromFeature(state.model, frame, feature), candidate = structuredClone(state.model);
    Object.assign(candidate.frames.find((item) => item.id === frameId), values);
    try {
      syncFrameLinks(candidate);
    } catch (error) {
      stopPick();
      return notice(error.message, "warn");
    }
    pushHistory();
    Object.assign(frame, values);
    syncFrameLinks(state.model);
    changed();
    renderTree();
    renderProperties();
    view?.setSelection(state.selection);
    stopPick();
    notice(`Reference frame ${frame.name} placed on ${feature.part} · ${feature.label}. Undo restores the previous placement.`);
  });
}
let measureFirst = null;
const millimetres = (value) => `${(value * 1000).toFixed(2)} mm`;
$("measureViewButton").onclick = () => {
  if (picking) return stopPick();
  measureFirst = null;
  // In Post-processing with a current result, measure the displayed frame.
  const atFrame = workspace === "results" && Boolean(state.result?.samples?.length) && !stale();
  if (atFrame) state.playing = false;
  const when = () => (atFrame ? ` at t = ${format(state.result.samples[state.frame].time, 4)} s` : "");
  startPick(`Measure${when()}: click the first CAD feature.`, (feature) => {
    if (!measureFirst) {
      measureFirst = feature;
      $("pickText").textContent = `From ${feature.label}${when()}. Click the second feature.`;
      return;
    }
    const result = measureFeatures(measureFirst, feature);
    const d = result.delta;
    $("pickText").textContent = `Distance ${millimetres(result.distance)} (Δx ${millimetres(d.x)}, Δy ${millimetres(d.y)}, Δz ${millimetres(d.z)})${result.angle === null ? "" : ` · axes ${result.angle.toFixed(2)}° apart`}${when()}. Click to measure again.`;
    measureFirst = null;
  }, atFrame);
  if (picking) $("measureViewButton").setAttribute("aria-pressed", "true");
};
// Hovering a tree row highlights the same entity in the 3D view.
$("modelTree").addEventListener("pointerover", (event) => view?.setHover(event.target.closest?.(".tree-item")?.dataset.entity || null));
$("modelTree").addEventListener("pointerleave", () => view?.setHover(null));
function setGlyphs(on) {
  state.glyphs = on;
  $("glyphsButton").setAttribute("aria-pressed", String(on));
  view?.setGlyphs(on);
}
function renderProperties() {
  const pendulum = state.model.kind !== "mass-spring";
  const double = state.model.kind === "double-pendulum";
  const titles = {
    body: double ? "Mass 1" : pendulum ? "Point mass" : "Translating mass",
    body2: "Mass 2",
    ground: "Ground reference",
    joint: pendulum ? "Revolute joint" : "Prismatic guide",
    joint2: "Link revolute joint",
    load: "Gravity field",
    spring: "Spring + damper",
    study: "Transient study",
  };
  const industrial = industry[state.model.kind];
  const source = sourceInfo();
  const assembly = state.model.kind === "planar-assembly";
  const spatial = state.model.kind === "spatial-assembly";
  const graph = assembly || spatial ? visualInfo() : source;
  if (industrial)
    for (const row of [
      ...industrial.bodies,
      ...industrial.connections,
      ...industrial.excitation,
    ])
      titles[row[0]] = row[2];
  if (source) {
    titles.body = source.nodes[0]?.label || "Source node";
    for (const node of source.nodes) titles[`node-${node.id}`] = node.label;
    titles.joint = "Schematic joint graph";
    titles.source = "Source and license";
  }
  if (assembly || spatial) {
    titles.body = graph.nodes[0]?.label || "Body";
    for (const node of graph.nodes) titles[`node-${node.id}`] = node.label;
    for (const joint of state.model.joints) titles[`joint-${joint.id}`] = `${spatial ? joint.type : joint.type === "prismatic" ? "Slider" : "Hinge"} · ${joint.id}`;
    for (const force of state.model.forces || []) titles[`force-${force.id}`] = `${force.type === "oleo-strut" ? "Oleo strut" : "Spring / damper"} · ${force.id}`;
    for (const load of state.model.loads || []) titles[`applied-${load.id}`] = `External load · ${load.id}`;
    for (const item of state.model.rotationalElements || []) titles[`rotary-${item.id}`] = `Rotational spring / damper · ${item.id}`;
    for (const item of state.model.jointTorques || []) titles[`torque-${item.id}`] = `Time-varying torque · ${item.id}`;
    for (const item of state.model.jointForces || []) titles[`joint-force-${item.id}`] = `Axial joint force · ${item.id}`;
    for (const item of state.model.contacts || []) titles[`contact-${item.id}`] = `Sphere-plane contact · ${item.id}`;
  }
  $("propertyMode").textContent = source ? "Read-only deck" : "Editable";
  $("selectionTitle").textContent = titles[state.selection] || "Mechanism";
  $("selectionSubtitle").textContent = source
    ? "Recorded upstream node / connection"
    : spatial ? "Editable 3D rigid body / joint" : assembly ? "Editable planar body / joint / load"
    : state.selection === "ground"
      ? state.model.kind === "suspension"
        ? "Prescribed vertical road motion"
        : "Fixed in the global frame"
      : state.selection === "joint"
        ? "Template-defined constraint"
        : "Physical parameters";
  const group = document.createElement("div");
  group.className = "property-group";
  const heading = document.createElement("h3");
  heading.textContent = source
    ? "Upstream model · read-only"
    : "Mechanism parameters";
  group.append(heading);
  if (source) {
    const detail = document.createElement("p");
    detail.textContent = `${source.description} ${source.visualizationNote} License: ${source.license.spdx}. Revision: ${source.source.revision}.`;
    group.append(detail);
  }
  if (graph) {
    const label = document.createElement("label");
    label.textContent = "Measure distance to node";
    const select = document.createElement("select");
    select.id = "measureNode";
    for (const node of graph.nodes) {
      const option = document.createElement("option");
      option.value = String(node.id);
      option.textContent = `${node.label} · ${node.id}`;
      select.append(option);
    }
    if (
      !graph.nodes.some(
        (node) => String(node.id) === String(state.measureNode),
      )
    )
      state.measureNode = graph.nodes.at(-1)?.id;
    select.value = String(state.measureNode);
    select.onchange = () => {
      state.measureNode = select.value;
      updateSourceProbe();
    };
    label.append(select);
    group.append(label);
    const probe = document.createElement("output");
    probe.id = "sourceProbe";
    probe.className = "source-probe";
    group.append(probe);
  }
  for (const [key, title, unit, min, step] of fields[state.model.kind]) {
    const label = document.createElement("label");
    label.textContent = title;
    const wrapper = document.createElement("span");
    wrapper.className = "number-field";
    const input = document.createElement("input");
    input.type = "number";
    input.id = `field-${key}`;
    input.value = state.model.parameters[key] ?? "";
    input.step = String(step);
    input.setAttribute("aria-label", title);
    input.dataset.field = `parameters.${key}`;
    if (min !== null) input.min = String(min);
    input.onchange = () => setNumber("parameters", key, input.value);
    const units = document.createElement("span");
    units.textContent = unit;
    wrapper.append(input, units);
    label.append(wrapper);
    group.append(label);
  }
  $("properties").replaceChildren(group);
  if (assembly) renderAssemblyEditor({
    container: $("properties"), model: state.model, selection: state.selection,
    notify: (message,type="warn") => notice(message, type),
    createSolid: createPrimitiveSolid,
    mutate: (change, selection) => {
      if (state.busy) {notice("Wait for the active simulation before editing the assembly.", "warn");return false;}
      pushHistory(); change(state.model);
      if (selection) state.selection = selection;
      changed(); renderTree(); renderProperties(); view?.setSelection(state.selection);
      return true;
    },
  });
  const cadFaces = state.step?.parts?.some((part) => part.faces?.length);
  if (spatial) renderSpatialEditor({container:$("properties"),model:state.model,selection:state.selection,createSolid:createPrimitiveSolid,pickFromCad:cadFaces ? pickJointFromCad : null,pickFrameFromCad:cadFaces ? pickFrameFromCad : null,notify:(message,type="warn")=>notice(message,type),mutate:(change,selection)=>{
    if(state.busy){notice("Wait for the active simulation before editing the assembly.","warn");return false;}
    pushHistory();change(state.model);if(selection)state.selection=selection;
    changed();renderTree();renderProperties();view?.setSelection(state.selection);return true;
  }});
  $("durationInput").value = state.model.simulation.duration ?? "";
  $("stepInput").value = state.model.simulation.step ?? "";
  $("inspectorNote").textContent = source
    ? "The upstream deck and its original study settings are preserved. The node graph is schematic; open the deck to inspect actual elements."
    : spatial ? "Edit 3D poses, velocities and local joint frames in SI units. Symbols in the 3D view mark joint anchors and axes and force elements." : assembly ? "Edit bodies, joint anchors and loads in SI units. Lines show body origins, not solid geometry."
    : industrial
      ? "Edit this engineering template in SI units. Open the example guide for its equations, parameter studies and modelling limits."
      : state.selection === "ground"
        ? `The ground is fixed. This template has ${double ? "two" : "one"} independent motion coordinate${double ? "s" : ""}; support geometry is illustrative.`
        : state.selection.startsWith("joint")
          ? "This template has fixed connections. Use a planar assembly example to add and edit revolute hinges."
          : "The visible mechanism is generated from these parameters. This release edits verified templates; the exported deck remains inspectable.";
  for (const input of document.querySelectorAll(".inspector input"))
    input.disabled = state.busy || Boolean(source);
  $("previewButton").disabled = state.busy || Boolean(graph);
  if (graph) updateSourceProbe();
}
function updateSourceProbe() {
  const source = visualInfo(),
    output = $("sourceProbe");
  if (!source || !output) return;
  const frame =
    ["source-example", "planar-assembly", "spatial-assembly"].includes(state.result?.model?.kind) && !stale()
      ? state.result.samples[state.frame]
      : { nodes: source.initialNodes };
  const node = frame?.nodes?.find(
    (item) => String(item.id) === String(state.selectedNode),
  );
  const other = frame?.nodes?.find(
    (item) => String(item.id) === String(state.measureNode),
  );
  if (!node) {
    output.textContent = "No coordinates for this node in the selected frame.";
    return;
  }
  const distance = other
    ? Math.hypot(node.x - other.x, node.y - other.y, node.z - other.z)
    : NaN;
  output.textContent = `Node ${node.id}: X ${format(node.x, 5)} m · Y ${format(node.y, 5)} m · Z ${format(node.z, 5)} m\nDistance ${format(distance, 5)} m`;
}
function renderTopology() {
  const source = visualInfo();
  if (source) {
    $("topology").innerHTML =
      `<span class="eyebrow">${state.model.kind === "planar-assembly" ? "PLANAR ASSEMBLY" : state.model.kind === "spatial-assembly" ? "3D ASSEMBLY" : "UPSTREAM SCHEMATIC"} · NODE ORIGINS</span><div class="industry-topology">${source.connections.map((connection) => `<div class="topology-node"><b>${escapeHtml(connection.from)} ↔ ${escapeHtml(connection.to)}</b><small>${escapeHtml(connection.label)}</small></div>`).join("")}</div><p class="topology-note">${escapeHtml(source.visualizationNote)}</p>`;
    return;
  }
  const industrial = industry[state.model.kind];
  if (industrial) {
    $("topology").innerHTML =
      `<span class="eyebrow">${industrial.badge}</span><div class="industry-topology">${industrial.topology.map(([name, role], index) => `${index ? '<span class="topology-arrow">↕</span>' : ""}<div class="topology-node"><b>${name}</b><small>${role}</small></div>`).join("")}</div><p class="topology-note">${industrial.assumptions}</p>`;
    return;
  }
  const p = state.model.kind !== "mass-spring",
    double = state.model.kind === "double-pendulum";
  $("topology").innerHTML =
    `<span class="eyebrow">${double ? "TWO INDEPENDENT MOTION COORDINATES" : "ONE INDEPENDENT MOTION COORDINATE"}</span><div class="topology-row"><div class="topology-node"><b>Ground</b><small>Fixed reference</small></div><span class="topology-arrow">↔</span><div class="topology-node selected"><b>${p ? "Revolute joint" : "Prismatic guide"}</b><small>${p ? "Rotation about Y" : "Translation along X"}</small></div></div><span class="topology-arrow">↕</span><div class="topology-row"><div class="topology-node"><b>${double ? "Mass 1" : p ? "Point mass" : "Translating mass"}</b><small>${p ? "Gravity force" : "Spring + viscous damper"}</small></div>${double ? '<span class="topology-arrow">↔</span><div class="topology-node selected"><b>Mass 2</b><small>Second revolute joint</small></div>' : ""}</div><p class="topology-note">Template topology. Select an entity in the model browser to inspect its role; edit physical parameters in the properties panel.</p>`;
}
function showIssues(issues) {
  const list = $("issuesList");
  list.replaceChildren();
  $("issuesSection").hidden = !issues.length;
  for (const issue of issues) {
    const li = document.createElement("li");
    li.className = issue.level;
    const button = document.createElement("button");
    const key = issue.field?.split(".").at(-1);
    const label =
      fields[state.model.kind].find((f) => f[0] === key)?.[1] ||
      { duration: "Duration", step: "Time step", name: "Project name" }[key] ||
      issue.field ||
      "Model";
    button.textContent = `${label}: ${issue.message}`;
    button.onclick = () => {
      switchStep(["duration", "step"].includes(key) ? "simulate" : "model");
      if (state.model.kind === "spatial-assembly") {
        const parts=(issue.field || "").split(".");
        if(parts[0] === "bodies" && state.model.bodies[Number(parts[1])]){const body=state.model.bodies[Number(parts[1])];select(Number(parts[1])===0?"body":`node-${body.id}`);$(`spatial-body-${body.id}-${parts.slice(2).join("-")}`)?.focus();return;}
        if(parts[0] === "joints" && state.model.joints[Number(parts[1])]){const joint=state.model.joints[Number(parts[1])];select(`joint-${joint.id}`);$(`spatial-joint-${joint.id}-${parts.slice(2).join("-")}`)?.focus();return;}
        if(parts[0] === "forces" && state.model.forces?.[Number(parts[1])]){const force=state.model.forces[Number(parts[1])];select(`force-${force.id}`);$(`spatial-force-${force.id}-${parts.slice(2).join("-")}`)?.focus();return;}
        if(["rotationalElements","jointTorques"].includes(parts[0]) && state.model[parts[0]]?.[Number(parts[1])]){const item=state.model[parts[0]][Number(parts[1])],prefix=parts[0] === "rotationalElements" ? "rotary" : "torque";select(`${prefix}-${item.id}`);$(`spatial-${prefix}-${item.id}-${parts.slice(2).join("-")}`)?.focus();return;}
        if(parts[0] === "jointForces" && state.model.jointForces?.[Number(parts[1])]){const item=state.model.jointForces[Number(parts[1])];select(`joint-force-${item.id}`);$(`spatial-joint-force-${item.id}-${parts.slice(2).join("-")}`)?.focus();return;}
        if(parts[0] === "contacts" && state.model.contacts?.[Number(parts[1])]){const item=state.model.contacts[Number(parts[1])];select(`contact-${item.id}`);$(`spatial-contact-${item.id}-${parts.slice(2).join("-")}`)?.focus();return;}
        if(parts[0] === "loads" && state.model.loads?.[Number(parts[1])]){const item=state.model.loads[Number(parts[1])];select(`applied-${item.id}`);$(`spatial-load-${item.id}-${parts.slice(2).join("-")}`)?.focus();return;}
        if(parts[0] === "parameters" && parts[1] === "gravity"){$(`spatial-gravity-${parts[2]}`)?.focus();return;}
      }
      if (state.model.kind === "planar-assembly") {
        const parts = (issue.field || "").split(".");
        if (parts[0] === "bodies" && state.model.bodies[Number(parts[1])]) {
          const body = state.model.bodies[Number(parts[1])];
          select(Number(parts[1]) === 0 ? "body" : `node-${body.id}`);
          $(`graph-body-${body.id}-${parts.slice(2).join("-")}`)?.focus();
          return;
        }
        if (parts[0] === "joints" && state.model.joints[Number(parts[1])]) {
          const joint = state.model.joints[Number(parts[1])];
          select(`joint-${joint.id}`);
          $(`graph-joint-${joint.id}-${parts.slice(2).join("-")}`)?.focus();
          return;
        }
        if (parts[0] === "forces" && state.model.forces?.[Number(parts[1])]) {
          const force=state.model.forces[Number(parts[1])];
          select(`force-${force.id}`);
          $(`graph-force-${force.id}-${parts.slice(2).join("-")}`)?.focus();
          return;
        }
        if (["rotationalElements", "jointTorques"].includes(parts[0]) && state.model[parts[0]]?.[Number(parts[1])]) {
          const item=state.model[parts[0]][Number(parts[1])], prefix=parts[0] === "rotationalElements" ? "rotary" : "torque";
          select(`${prefix}-${item.id}`);
          $(`graph-${prefix}-${item.id}-${parts.slice(2).join("-")}`)?.focus();
          return;
        }
        if (parts[0] === "loads" && state.model.loads?.[Number(parts[1])]) {
          const load=state.model.loads[Number(parts[1])];
          select(`applied-${load.id}`);
          $(`graph-load-${load.id}-${parts.slice(2).join("-")}`)?.focus();
          return;
        }
      }
      (
        $(`field-${key}`) ||
        $(
          key === "duration"
            ? "durationInput"
            : key === "step"
              ? "stepInput"
              : "properties",
        )
      )?.focus();
    };
    li.append(button);
    list.append(li);
  }
}
async function validate(show = true) {
  const request = signature();
  try {
    const result = await checkModel(state.model);
    if (request !== signature()) return result;
    state.validation = result;
    showIssues(result.issues || []);
    renderChecklist();
    const mobility = result.summary?.mobility;
    if (state.model.kind === "spatial-assembly" && mobility)
      $("modelKindBadge").textContent = `${state.model.bodies.length} bodies · ${state.model.joints.length} joints · ${mobility.dof} DOF${mobility.redundant.length ? ` · ${mobility.redundant.length} redundant` : ""}`;
    $("validationBadge").textContent = result.valid
      ? "Ready"
      : "Needs attention";
    $("validationBadge").className = `badge ${result.valid ? "green" : "red"}`;
    $("readinessText").textContent = result.valid
      ? sourceInfo()
        ? "Upstream deck selected; source hashes are checked before execution."
        : "Physical inputs and study settings passed the model checks."
      : "Resolve the highlighted inputs before running the solver.";
    if (show)
      notice(
        result.valid
          ? "Model checks passed. You can run the MBDyn simulation."
          : "Model validation found issues. Select an issue to find its field.",
        result.valid ? "" : "error",
      );
    return result;
  } catch (error) {
    if (show) notice(error.message, "error");
    return { valid: false, issues: [] };
  }
}
function applyModel(model, remember = true) {
  if (remember) pushHistory();
  clearStudy(false);
  state.model = structuredClone(model);
  if (state.step && Object.keys(state.step.metadata.bindings).length) {
    const allowed=new Set(assemblyKind(model) ? model.bodies.map(body=>body.id) : []);
    if (Object.values(state.step.metadata.bindings).some(binding=>!allowed.has(binding.body) || ((model.kind === "spatial-assembly") !== (Object.hasOwn(binding.pose,"rx") && Object.hasOwn(binding.pose,"rz"))))) {
      state.step={...state.step,metadata:{...state.step.metadata,bindings:{}}};
      if (view) view.stepAsset=state.step;
    }
  }
  state.selection = "body";
  state.selectedNode = visualInfo()?.nodes[0]?.id ?? null;
  state.measureNode = visualInfo()?.nodes.at(-1)?.id ?? null;
  state.signal = 0;
  state.playing = false;
  state.validation = null;
  renderMetadata();
  renderTree();
  renderProperties();
  view?.setModel(state.model, true, visualInfo());
  saveLocal();
  updateHistoryButtons();
  changed();
  renderStepControls();
}
let workspace = "model";
function switchStep(step) {
  const validating = step === "validate";
  if (validating) step = "simulate";
  workspace = step;
  document.body.classList.remove("ws-model", "ws-simulate", "ws-results");
  document.body.classList.add(`ws-${step}`);
  document
    .querySelectorAll("[data-step]")
    .forEach((b) => b.classList.toggle("active", b.dataset.step === step));
  if (step === "simulate") {
    renderChecklist();
    renderStudyControls();
    if (validating) validate();
  }
  if (step === "results" && state.result) requestAnimationFrame(drawPlot);
  refreshTrails();
}
// Switch to the workspace that owns a control, e.g. when following an issue to its field.
function revealElement(element) {
  const owner = element?.closest?.(".pane-model, .pane-simulate, .console-panel, .pane-results, .results-panel");
  if (!owner) return false;
  const step = owner.matches(".pane-model") ? "model" : owner.matches(".pane-simulate, .console-panel") ? "simulate" : "results";
  if (step !== workspace) switchStep(step);
  return true;
}
window.__kinemeldReveal = revealElement;
function setBusy(busy) {
  state.busy = busy;
  $("cancelRunButton").hidden = !busy || !activeRunToken;
  $("cancelRunButton").disabled = false;
  document.body.classList.toggle("busy", busy);
  for (const id of [
    "runButton",
    "solveRunButton",
    "previewButton",
    "examplesButton",
    "importButton",
    "saveButton",
    "saveAsButton",
    "validateButton",
    "deckButton",
    "studyRunButton",
  ])
    $(id).disabled = busy || (id === "previewButton" && Boolean(visualInfo())) || (state.saving && ["saveButton", "saveAsButton"].includes(id));
  document
    .querySelectorAll(".inspector input")
    .forEach((i) => (i.disabled = busy || Boolean(sourceInfo())));
  if (nativeDesktop) nativeDesktop.notify(busy ? "busy" : "idle");
  updateHistoryButtons();
  $("runButton").querySelector("span:last-child").textContent = busy
    ? "Solving…"
    : "Run simulation";
  $("runButton").setAttribute("aria-label", busy ? "Solving…" : "Run simulation");
  $("solveRunButton").lastChild.textContent = busy ? "Solving…" : "Run MBDyn";
}
async function run(preview = false) {
  if (state.busy || state.saving || state.opening) return;
  setBusy(true);
  const checked = await validate(false);
  if (!checked.valid) {
    setBusy(false);
    notice(
      "The model needs attention before it can run. Review the highlighted fields.",
      "error",
    );
    switchStep("simulate");
    return;
  }
  const snapshot = structuredClone(state.model);
  const key = signature();
  activeRunToken = preview ? null : [...crypto.getRandomValues(new Uint8Array(16))].map(value=>value.toString(16).padStart(2,"0")).join("");
  setBusy(true);
  state.playing = false;
  notice(
    preview
      ? "Computing an independent reference response…"
      : "MBDyn is solving the model. The log and response will appear when the process finishes.",
  );
  showConsole(preview ? "Reference preview" : "Solving…", preview ? "Computing an independent reference response (not MBDyn output)…" : `MBDyn job started ${new Date().toLocaleTimeString()}\n${snapshot.kind === "source-example" ? "Upstream deck" : `${Math.ceil(snapshot.simulation.duration / snapshot.simulation.step).toLocaleString()} steps · Δt ${snapshot.simulation.step} s · ${snapshot.simulation.duration} s`}\nWaiting for the solver process…`);
  status(preview ? "Reference calculation in progress" : "Solver job running");
  try {
    const result =
      snapshot.kind === "source-example"
        ? await runSource(snapshot.sourceExampleId, activeRunToken)
        : await api(preview ? "preview" : "run", snapshot, activeRunToken);
    if (result.ok === false)
      throw new Error(
        result.error || "The solver did not finish successfully.",
      );
    if (!Array.isArray(result.samples) || !result.samples.length)
      throw new Error("No response samples were returned.");
    if (["source-example", "planar-assembly", "spatial-assembly"].includes(snapshot.kind)) result.model = snapshot;
    clearStudy(false);
    state.result = result;
    state.lastFailure = null;
    state.resultSignature = key;
    markNativeDirty();
    state.frame = 0;
    playTime = 0;
    state.playing = false;
    renderResult();
    setFrame(0);
    switchStep("results");
    notice(
      result.metrics?.contactAssumptionViolated
        ? "Tire load became negative. The continuous-contact suspension assumption is invalid for this run; this model does not simulate wheel lift-off. Reduce the excitation or use a contact model before interpreting the response."
        : preview
          ? "Reference preview. This response is computed independently and is not MBDyn solver output."
          : `MBDyn completed successfully · ${result.samples.length.toLocaleString()} samples.`,
      preview || result.metrics?.contactAssumptionViolated ? "warn" : "",
    );
    status(
      preview ? "Reference preview · not MBDyn output" : "MBDyn run completed",
    );
    $("runId").textContent = result.runId || "Reference calculation";
    showConsole(preview ? "Reference preview complete" : `Completed · ${result.samples.length.toLocaleString()} samples`, result.log || "Reference preview computed independently; MBDyn was not launched.");
  } catch (error) {
    notice(error.message, "error");
    showIssues(error.issues || []);
    state.lastFailure = error.details;
    const cancelled=error.details?.cancelled === true;
    status(cancelled ? "Run cancelled · partial log retained" : "Run failed · inspect the reported error");
    if (error.details?.runId)
      $("runId").textContent = `${cancelled ? "Cancelled" : "Failed"} · ${error.details.runId}`;
    showConsole(cancelled ? "Cancelled" : "Failed", [error.message, error.details?.log].filter(Boolean).join("\n\n"));
    if (workspace !== "simulate") switchStep("simulate");
  } finally {
    activeRunToken = null;
    setBusy(false);
  }
}
function elementSignals(model, result) {
  return [
    ...((model?.forces || []).length ? [
      {type:"force",title:"Spring length / extension",unit:"m",channels:[["length","Length"],["extension","Extension"]]},
      {type:"force",title:(model.forces || []).some(force=>force.type==="oleo-strut") ? "Axial tension (native / reconstructed)" : "Spring tension (reconstructed)",unit:"N",channels:[["force","Tension"]]},
      {type:"force",title:"Spring length rate",unit:"m/s",channels:[["rate","Rate"]]},
    ] : []),
    ...((model?.joints || []).some(joint=>joint.type==="prismatic") ? [
      {type:"slider",title:"Slider position (reconstructed)",unit:"m",channels:[["position","Position"]]},
      {type:"slider",title:"Slider velocity (reconstructed)",unit:"m/s",channels:[["velocity","Velocity"]]},
    ] : []),
    ...((model?.joints || []).some(joint=>joint.type==="cylindrical") ? [
      {type:"cylinder",title:"Cylindrical position",unit:"m",channels:[["position","Position"]]},
      {type:"cylinder",title:"Cylindrical velocity",unit:"m/s",channels:[["velocity","Velocity"]]},
      {type:"cylinder",title:"Cylindrical rotation",unit:"rad",channels:[["angle","Angle"]]},
      {type:"cylinder",title:"Cylindrical angular velocity",unit:"rad/s",channels:[["angularVelocity","Angular velocity"]]},
    ] : []),
    ...((model?.rotationalElements || []).length ? [
      {type:"rotary",title:"Rotational deflection",unit:"rad",channels:[["angle","Deflection"]]},
      {type:"rotary",title:"Rotational velocity",unit:"rad/s",channels:[["velocity","Velocity"]]},
      {type:"rotary",title:"Rotational spring torque",unit:"N·m",channels:[["torque","Torque"]]},
    ] : []),
    ...((model?.jointTorques || []).length ? [
      {type:"torque",title:"Actuation torque",unit:"N·m",channels:[["torque","Torque"]]},
      {type:"torque",title:"Actuation power",unit:"W",channels:[["power","Power"]]},
      {type:"system",title:"Actuation work (reconstructed)",unit:"J",channels:[["actuationWork","Work"]]},
    ] : []),
    ...((model?.contacts || []).length ? [
      {type:"contact",title:"Contact gap / penetration",unit:"m",channels:[["gap","Gap"],["penetration","Penetration"]]},
      {type:"contact",title:"Contact normal force (reconstructed)",unit:"N",channels:[["force","Force"]]},
      {type:"contact",title:"Contact elastic energy",unit:"J",channels:[["energy","Energy"]]},
      ...((model?.contacts || []).some(contact=>contact.damping>0) ? [
        {type:"contact",title:"Contact damping power (reconstructed)",unit:"W",channels:[["dampingPower","Power"]]},
        {type:"contact",title:"Contact dissipated energy (reconstructed)",unit:"J",channels:[["dissipatedEnergy","Energy"]]},
      ] : []),
      ...((model?.contacts || []).some(contact=>contact.friction>0) ? [
        {type:"contact",title:"Contact friction force",unit:"N",channels:[["frictionForce","Friction"]]},
        {type:"contact",title:"Contact slip speed",unit:"m/s",channels:[["slip","Slip"]]},
        {type:"contact",title:"Friction dissipated energy",unit:"J",channels:[["frictionEnergy","Energy"]]},
      ] : []),
    ] : []),
    ...((model?.jointForces || []).length ? [
      {type:"joint-force",title:"Axial joint force",unit:"N",channels:[["force","Force"]]},
      {type:"joint-force",title:"Axial joint force power",unit:"W",channels:[["power","Power"]]},
      {type:"system",title:"Axial joint force work (reconstructed)",unit:"J",channels:[["jointForceWork","Work"]]},
    ] : []),
    ...(model?.kind === "spatial-assembly" && result?.source === "MBDyn" && result.samples?.[0]?.jointReactions?.length ? [
      {type:"reaction",title:"Joint reaction force on B · world X / Y / Z",unit:"N",channels:[["force.x","X"],["force.y","Y"],["force.z","Z"]]},
      {type:"reaction",title:"Joint reaction moment at B anchor · world X / Y / Z",unit:"N·m",channels:[["moment.x","X"],["moment.y","Y"],["moment.z","Z"]]},
    ] : []),
    ...(model?.kind === "spatial-assembly" && (model.loads || []).length ? [
      {type:"load",title:"Applied force · X / Y / Z",unit:"N",channels:[["force.x","X"],["force.y","Y"],["force.z","Z"]]},
      {type:"load",title:"Applied torque · X / Y / Z",unit:"N·m",channels:[["torque.x","X"],["torque.y","Y"],["torque.z","Z"]]},
      {type:"load",title:"Applied moment about COM · X / Y / Z",unit:"N·m",channels:[["moment.x","X"],["moment.y","Y"],["moment.z","Z"]]},
      {type:"load",title:"Load power",unit:"W",channels:[["power","Power"]]},
    ] : []),
    ...((model?.loads || []).length ? [
      {type:"system",title:"Applied power (reconstructed)",unit:"W",channels:[["loadPower","Power"]]},
      {type:"system",title:"Applied work (reconstructed)",unit:"J",channels:[["appliedWork","Work"]]},
    ] : []),
    ...((model?.forces || []).some(force=>force.type==="oleo-strut") ? [
      {type:"oleo",title:"Oleo gas pressure (native)",unit:"Pa",channels:[["gasPressure","Pressure"]]},
      {type:"oleo",title:"Oleo force components (native / derived)",unit:"N",channels:[["gasForce","Gas"],["hydraulicForce","Hydraulic"],["stopForce","Stop"]]},
    ] : []),
    ...((model?.joints || []).some(joint=>joint.type==="revolute" && joint.motion) ? [
      {type:"drive",title:"Rotary drive angle · measured / commanded",unit:"rad",channels:[["angle","Measured"],["commandedAngle","Commanded"]]},
      {type:"drive",title:"Rotary drive speed",unit:"rad/s",channels:[["speed","Speed"]]},
      {type:"drive",title:"Rotary drive torque (hinge reaction)",unit:"N·m",channels:[["torque","Torque"]]},
      {type:"drive",title:"Rotary drive power",unit:"W",channels:[["power","Power"]]},
      {type:"system",title:"Rotary drive work (all drives)",unit:"J",channels:[["rotaryDriveWork","Work"]]},
    ] : []),
  ];
}
function resultSignal() {
  if (["source-example", "planar-assembly", "spatial-assembly"].includes(state.result?.model?.kind)) {
    const extra=elementSignals(state.result.model,state.result)[state.signal-NODE_SIGNALS];
    if (extra) {
      if(extra.type==="system")return extra;
      const selected=["slider","cylinder","reaction","drive"].includes(extra.type) ? state.selectedJoint : state.selectedForce;
      return {...extra,channels:extra.channels.map(([key,label])=>[`${extra.type}:${selected}:${key}`,label])};
    }
    const node =
      state.selectedNode ?? visualInfo(state.result.model)?.nodes[0]?.id;
    const axes = ["x", "y", "z"];
    const signals = [
      { title: "Node position · X / Y / Z", unit: "m", prefix: "" },
      { title: "Node velocity · X / Y / Z", unit: "m/s", prefix: "v" },
      { title: "Node Euler 1–2–3 · X / Y / Z", unit: "deg", prefix: "r" },
      {
        title: "Node angular velocity · X / Y / Z",
        unit: "rad/s",
        prefix: "w",
      },
      { title: "Angular velocity in body axes · x / y / z", unit: "rad/s", prefix: "bw" },
    ];
    const signal = signals[state.signal] || signals[0];
    return {
      ...signal,
      channels: axes.map((axis) => [
        `node:${node}:${signal.prefix}${axis}`,
        axis.toUpperCase(),
      ]),
    };
  }
  const signals = signalsFor(state.result?.model?.kind || state.model.kind);
  return signals[state.signal] || signals[0];
}
function channelValue(sample, key) {
  if (key.startsWith("force:")) {const [,id,field]=key.split(":");return sample.forces?.find(item=>item.id===id)?.[field];}
  if (key.startsWith("oleo:")) {const [,id,field]=key.split(":");return sample.forces?.find(item=>item.id===id)?.[field];}
  if (key.startsWith("rotary:")) {const [,id,field]=key.split(":");return sample.rotationalStates?.find(item=>item.id===id)?.[field];}
  if (key.startsWith("torque:")) {const [,id,field]=key.split(":");return sample.actuationStates?.find(item=>item.id===id)?.[field];}
  if (key.startsWith("contact:")) {const [,id,field]=key.split(":");return sample.contactStates?.find(item=>item.id===id)?.[field];}
  if (key.startsWith("joint-force:")) {const [,id,field]=key.split(":");return sample.jointForceStates?.find(item=>item.id===id)?.[field];}
  if (key.startsWith("reaction:")) {const [,id,path]=key.split(":");const [field,axis]=path.split(".");return sample.jointReactions?.find(item=>item.id===id)?.[field]?.[axis];}
  if (key.startsWith("load:")) {const [,id,path]=key.split(":");const item=sample.loadStates?.find(entry=>entry.id===id);const [field,axis]=path.split(".");return axis ? item?.[field]?.[axis] : item?.[field];}
  if (key.startsWith("cylinder:")) {const [,id,field]=key.split(":");return sample.cylinders?.find(item=>item.id===id)?.[field];}
  if (key.startsWith("drive:")) {const [,id,field]=key.split(":");return sample.rotaryDrives?.find(item=>item.id===id)?.[field];}
  if (key.startsWith("slider:")) {const [,id,field]=key.split(":");return sample.sliders?.find(item=>item.id===id)?.[field];}
  if (!key.startsWith("node:")) return sample[key];
  const [, node, field] = key.split(":");
  const entry = sample.nodes?.find((item) => String(item.id) === node);
  if (field?.startsWith("bw") && entry) return bodyAngularVelocity(entry)["xyz".indexOf(field[2])];
  return entry?.[field];
}
const NODE_SIGNALS = 5;
// MBDyn reports world-frame angular velocity; rotate it into body axes with the Euler 1-2-3 orientation.
function bodyAngularVelocity(node) {
  const [a, b, c] = [node.rx, node.ry, node.rz].map((deg) => (deg * Math.PI) / 180);
  if (![a, b, c, node.wx, node.wy, node.wz].every(Number.isFinite)) return [NaN, NaN, NaN];
  const [ca, sa, cb, sb, cc, sc] = [Math.cos(a), Math.sin(a), Math.cos(b), Math.sin(b), Math.cos(c), Math.sin(c)];
  const R = [
    [cb * cc, -cb * sc, sb],
    [ca * sc + sa * sb * cc, ca * cc - sa * sb * sc, -sa * cb],
    [sa * sc - ca * sb * cc, sa * cc + ca * sb * sc, ca * cb],
  ];
  const w = [node.wx, node.wy, node.wz];
  return [0, 1, 2].map((i) => R[0][i] * w[0] + R[1][i] * w[1] + R[2][i] * w[2]);
}
function renderResult() {
  const result = state.result;
  if (!result) return;
  const isStale = stale();
  const real = result.source === "MBDyn";
  $("resultSource").textContent =
    `${isStale ? "Stale · " : ""}${result.restored ? `Saved result · recorded ${real ? "MBDyn" : "reference"}` : real ? "MBDyn solver" : "Reference preview"}`;
  $("resultSource").className =
    `source-badge ${isStale ? "stale" : real ? "real" : ""}`;
  $("viewSource").textContent = isStale
    ? "Initial configuration · edited model"
    : result.restored
      ? "Saved result · recorded source"
      : real
        ? "MBDyn solver response"
        : "Reference preview";
  $("samplesMetric").textContent = result.samples.length.toLocaleString();
  const kind = result.model?.kind || state.model.kind;
  const source = visualInfo(result.model);
  const forces=assemblyKind(result.model) ? result.model.forces || [] : [];
  const joints=assemblyKind(result.model) ? result.model.joints : [];
  const extraSignals=elementSignals(result.model,result);
  const signals = source
    ? [
        "Node position · X / Y / Z",
        "Node velocity · X / Y / Z",
        "Node Euler 1–2–3 · X / Y / Z",
        "Node angular velocity · X / Y / Z",
        "Angular velocity in body axes · x / y / z",
      ].concat(extraSignals.map(signal=>signal.title)).map((title) => ({ title }))
    : signalsFor(kind);
  if (
    source &&
    !source.nodes.some((node) => String(node.id) === String(state.selectedNode))
  )
    state.selectedNode = source.nodes[0]?.id;
  if (state.signal >= signals.length) state.signal = 0;
  const selectedExtra=extraSignals[state.signal-NODE_SIGNALS];
  const selectedElements=selectedExtra?.type === "rotary" ? result.model.rotationalElements || [] : selectedExtra?.type === "torque" ? result.model.jointTorques || [] : selectedExtra?.type === "joint-force" ? result.model.jointForces || [] : selectedExtra?.type === "contact" ? result.model.contacts || [] : selectedExtra?.type === "load" ? result.model.loads || [] : selectedExtra?.type === "oleo" ? forces.filter(force=>force.type==="oleo-strut") : forces;
  if (!selectedElements.some(item=>item.id===state.selectedForce)) state.selectedForce=selectedElements[0]?.id ?? null;
  const availableReactions=new Set((result.samples[0]?.jointReactions || []).map(item=>item.id));
  const selectedJoints=selectedExtra?.type === "reaction" ? joints.filter(joint=>availableReactions.has(joint.id)) : selectedExtra?.type === "drive" ? joints.filter(joint=>joint.type==="revolute" && joint.motion) : joints.filter(joint=>joint.type===(selectedExtra?.type === "cylinder" ? "cylindrical" : "prismatic"));
  if (!selectedJoints.some(joint=>joint.id===state.selectedJoint)) state.selectedJoint=selectedJoints[0]?.id ?? null;
  $("signalTitle").textContent = resultSignal().title;
  $("signalSelect").replaceChildren(
    ...signals.map((signal, index) => {
      const option = document.createElement("option");
      option.value = String(index);
      option.textContent = signal.title;
      return option;
    }),
  );
  $("signalSelect").value = String(state.signal);
  $("signalSelect").hidden = signals.length < 2;
  $("nodeSelect").hidden = !source || Boolean(selectedExtra);
  $("forceSelect").hidden = !["force","rotary","torque","joint-force","load","contact","oleo"].includes(selectedExtra?.type);
  $("forceSelect").setAttribute("aria-label",selectedExtra?.type === "load" ? "Result external load" : selectedExtra?.type === "rotary" ? "Result rotational spring" : selectedExtra?.type === "torque" ? "Result joint torque" : selectedExtra?.type === "joint-force" ? "Result axial joint force" : selectedExtra?.type === "contact" ? "Result contact" : selectedExtra?.type === "oleo" ? "Result oleo strut" : "Result spring or damper");
  $("jointSelect").hidden = !["slider","cylinder","reaction","drive"].includes(selectedExtra?.type);
  if(selectedElements.length){$("forceSelect").replaceChildren(...selectedElements.map(item=>{const option=document.createElement("option");option.value=item.id;option.textContent=item.id;return option;}));$("forceSelect").value=state.selectedForce;}
  if(selectedJoints.length){$("jointSelect").replaceChildren(...selectedJoints.map(joint=>{const option=document.createElement("option");option.value=joint.id;option.textContent=joint.id;return option;}));$("jointSelect").value=state.selectedJoint;}
  if (source) {
    $("nodeSelect").replaceChildren(
      ...source.nodes.map((node) => {
        const option = document.createElement("option");
        option.value = String(node.id);
        option.textContent = `${node.label} · ${node.id}`;
        return option;
      }),
    );
    $("nodeSelect").value = String(state.selectedNode);
  }
  for (const id of ["playButton", "rewindButton", "frameBackButton", "frameForwardButton", "timeSlider", "csvButton", "clearResultsButton", "pinTraceButton", "plotSvgButton", "plotPngButton", "compareButton"])
    $(id).disabled = false;
  $("playButton").disabled = Boolean(isStale);
  $("resultsBadge").textContent = isStale ? "Stale" : real ? "MBDyn" : "Preview";
  $("resultsBadge").className = `badge ${isStale ? "warn" : real ? "green" : "blue"}`;
  $("durationMetric").innerHTML = `${format(result.samples.at(-1).time, 3)} <span>s</span>`;
  const resultStep = result.model?.simulation?.step ?? state.model.simulation.step;
  $("stepMetric").innerHTML = `${Number.isFinite(resultStep) ? String(resultStep) : "—"} <span>s</span>`;
  refreshTrails();
  if (!isStale && view && assemblyKind(result.model)) view.placeGround(view.resultEnvelopeMinZ(result));
  $("timeSlider").max = String(result.samples.length - 1);
  $("endTime").textContent = `${format(result.samples.at(-1).time)} s`;
  drawPlot();
}
function showConsole(title, text) {
  $("consoleTitle").textContent = title;
  const lines = String(text || "").split(/\r?\n/);
  $("solverConsole").textContent = lines.length > 400 ? [`… ${lines.length - 400} earlier lines in the full log`, ...lines.slice(-400)].join("\n") : lines.join("\n");
  $("solverConsole").scrollTop = $("solverConsole").scrollHeight;
}
// Nice tick spacing (1, 2, 2.5, 5 × 10^n) for readable engineering axes.
function niceTicks(min, max, count) {
  const span = max - min;
  if (!(span > 0)) return [min];
  const raw = span / Math.max(1, count), power = 10 ** Math.floor(Math.log10(raw));
  const step = [1, 2, 2.5, 5, 10].map((m) => m * power).find((m) => m >= raw) || 10 * power;
  const ticks = [];
  for (let v = Math.ceil(min / step - 1e-9) * step; v <= max + step * 1e-9; v += step) ticks.push(Math.abs(v) < step * 1e-9 ? 0 : v);
  return ticks;
}
function formatTick(value, span) {
  if (value === 0) return "0";
  const magnitude = Math.abs(value);
  if (magnitude >= 1e5 || magnitude < 1e-3) return value.toExponential(2);
  const digits = Math.max(0, Math.min(5, 2 - Math.floor(Math.log10(span || 1))));
  return value.toFixed(digits);
}
function formatValue(value) {
  if (!Number.isFinite(value)) return "—";
  const magnitude = Math.abs(value);
  return magnitude !== 0 && (magnitude >= 1e5 || magnitude < 1e-3) ? value.toExponential(4) : value.toPrecision(5);
}
const PLOT_COLORS = ["var(--c1)", "var(--c2)", "var(--c3)", "var(--c4)", "#d2453f", "#6c8f1f", "#8a6a3f", "#3fa0d8"];
const DASHES = ["", "6 3", "2 3", "8 3 2 3"];
let plotGeometry = null;
// Parsed solver CSVs, keyed by result object so saving or cloning a result never copies them.
const fullResolution = new WeakMap();
const fullResolutionLoading = new WeakSet();
async function loadFullResolution(result) {
  if (!result || result.source !== "MBDyn" || fullResolution.has(result) || fullResolutionLoading.has(result)) return;
  const csv = result.files?.csv;
  if (!result.csvText && !(typeof csv === "string" && /^\/api\/runs\/[0-9a-f]{32}\/results\.csv$/.test(csv))) return;
  fullResolutionLoading.add(result);
  try {
    const text = result.csvText || (await (await fetch(csv)).text());
    fullResolution.set(result, parseSolverCsv(text));
    if (state.result === result || state.study?.cases.some((item) => item.result === result)) drawPlot();
  } catch (error) {
    console.warn("Full-resolution results unavailable:", error);
  } finally {
    fullResolutionLoading.delete(result);
  }
}
function seriesFor(result, key) {
  const full = fullResolution.get(result);
  const values = full ? fullSeries(full, key, bodyAngularVelocity) : null;
  if (values && values.length === full.times.length) return { times: full.times, values, full: true };
  return { times: result.samples.map((sample) => sample.time), values: result.samples.map((sample) => channelValue(sample, key)), full: false };
}
function nearestIndex(times, t) {
  let lo = 0, hi = times.length - 1;
  while (hi - lo > 1) { const mid = (lo + hi) >> 1; if (times[mid] < t) lo = mid; else hi = mid; }
  return Math.abs(times[lo] - t) <= Math.abs(times[hi] - t) ? lo : hi;
}
/** Current channels, pinned traces with the same unit, and the comparison run's matching channels. */
function plotSeries() {
  const signal = resultSignal();
  const study = activeStudy();
  if (study) {
    const [key] = signal.channels[studyChannel(signal)];
    return study.cases.map((item, i) => {
      loadFullResolution(item.result);
      return { key, label: studyValueLabel(item.value), color: study.colors[i], dash: "", shown: item.result === state.result, ...seriesFor(item.result, key) };
    }).filter((item) => item.values.some(Number.isFinite));
  }
  const series = signal.channels.map(([key, label], i) => ({ key, label, color: PLOT_COLORS[i], dash: DASHES[i] || "", ...seriesFor(state.result, key) }));
  let color = signal.channels.length;
  for (const overlay of state.overlays) {
    if (overlay.unit !== signal.unit) continue;
    for (const [key, label] of overlay.channels) {
      if (signal.channels.some(([own]) => own === key)) continue;
      const data = seriesFor(state.result, key);
      if (!data.values.some(Number.isFinite)) continue;
      series.push({ key, label: `${overlay.name} ${label}`, color: PLOT_COLORS[color++ % PLOT_COLORS.length], dash: "", overlay: true, ...data });
    }
  }
  const compare = state.compareRun;
  if (compare && compare.result !== state.result) {
    for (const [key, label] of signal.channels) {
      const data = seriesFor(compare.result, key);
      if (data.values.some(Number.isFinite)) series.push({ key, label: `${label} · ${compare.name}`, color: "var(--faint)", dash: "4 3", reference: true, ...data });
    }
  }
  return series;
}
function drawPlot() {
  const samples = state.result?.samples;
  if (!samples?.length) return;
  loadFullResolution(state.result);
  const w = Math.max($("plot").clientWidth, 300),
    h = Math.max($("plot").clientHeight, 110),
    left = 64,
    right = 14,
    top = 14,
    bottom = 28;
  const signal = resultSignal();
  const series = plotSeries();
  const values = series.flatMap((item) => item.values).filter(Number.isFinite);
  if (!values.length) {
    plotGeometry = null;
    $("plot").innerHTML = `<div class="empty-plot">${icon("wave")}<strong>No values for this quantity</strong><span>Choose another response or entity.</span></div>`;
    $("plotStats").replaceChildren();
    return;
  }
  let min = Infinity, max = -Infinity;
  for (const value of values) { if (value < min) min = value; if (value > max) max = value; }
  const padding = (max - min) * 0.08 || Math.max(Math.abs(max) * 0.1, 1e-6);
  min -= padding;
  max += padding;
  const first = samples[0].time, last = samples.at(-1).time;
  const duration = last - first || 1;
  const px = (t) => left + ((t - first) / duration) * (w - left - right),
    py = (y) => top + ((max - y) / (max - min)) * (h - top - bottom);
  plotGeometry = { left, right, top, bottom, w, h, first, duration, px, py, series };
  const buckets = Math.max(50, Math.round(w - left - right));
  const curves = series
    .map((item, index) => {
      // Min/max per pixel column keeps every peak of a long full-resolution series visible.
      const points = envelope(item.times, item.values, first, last, buckets);
      let path = "", pen = false;
      for (const point of points) {
        if (!point || point.t > last + 1e-12) { pen = false; continue; }
        path += `${pen ? "L" : "M"}${px(point.t).toFixed(1)},${py(point.v).toFixed(1)}`;
        pen = true;
      }
      const role = item.reference ? "plot-reference" : item.overlay ? "plot-overlay" : "plot-curve";
      return `<path class="${role}" d="${path}" fill="none" stroke="${item.color}" stroke-width="${item.reference ? 1.4 : item.shown ? 2.6 : 1.7}" ${item.dash ? `stroke-dasharray="${item.dash}"` : ""} stroke-linejoin="round" stroke-linecap="round"/>`;
    })
    .join("");
  let grid = "";
  const yTicks = niceTicks(min, max, Math.max(3, Math.floor((h - top - bottom) / 28)));
  for (const val of yTicks) {
    const y = py(val);
    grid += `<line x1="${left}" x2="${w - right}" y1="${y}" y2="${y}" stroke="var(--line)" ${val === 0 ? "" : 'stroke-dasharray="2 3"'}/><text x="${left - 7}" y="${y + 3}" text-anchor="end">${formatTick(val, max - min)}</text>`;
  }
  for (const t of niceTicks(first, last, Math.max(2, Math.floor((w - left - right) / 80)))) {
    const x = px(t);
    grid += `<line x1="${x}" x2="${x}" y1="${top}" y2="${h - bottom}" stroke="var(--line)" stroke-dasharray="2 3"/><text x="${x}" y="${h - bottom + 14}" text-anchor="middle">${formatTick(t, duration)}</text>`;
  }
  const axes = `<line x1="${left}" x2="${left}" y1="${top}" y2="${h - bottom}" stroke="var(--line-strong)"/><line x1="${left}" x2="${w - right}" y1="${h - bottom}" y2="${h - bottom}" stroke="var(--line-strong)"/><text x="${w - right}" y="${h - 4}" text-anchor="end">time · s</text><text transform="translate(12 ${(top + h - bottom) / 2}) rotate(-90)" text-anchor="middle">${escapeHtml(signal.unit)}</text>`;
  const step = Math.min(150, Math.max(78, ...series.map((item) => 30 + item.label.length * 6)));
  const legendWidth = Math.min(w - left - right - 8, series.length * step + 6);
  const legend = `<rect x="${left + 4}" y="${top - 6}" width="${legendWidth}" height="18" rx="4" fill="var(--surface)" opacity="0.88"/>` + series.map(({ label, color, dash }, i) => `<g transform="translate(${left + 10 + i * step} ${top + 4})"><line x1="0" x2="16" y1="0" y2="0" stroke="${color}" stroke-width="2" ${dash ? `stroke-dasharray="${dash}"` : ""}/><text x="21" y="3" fill="var(--text)">${escapeHtml(label)}</text></g>`).join("");
  const markers = series.map((item, i) => `<circle class="plot-marker" data-index="${i}" r="3.5" fill="var(--surface)" stroke="${item.color}" stroke-width="2" cx="-10" cy="-10"/>`).join("");
  $("plot").innerHTML =
    `<svg viewBox="0 0 ${w} ${h}" role="presentation" xmlns="http://www.w3.org/2000/svg"><g fill="var(--dim)" font-family="PlexMono" font-size="9.5">${grid}${axes}</g>${curves}<line id="plotHover" y1="${top}" y2="${h - bottom}" x1="-10" x2="-10" stroke="var(--faint)" stroke-width="1"/><line id="plotCursor" x1="${px(samples[state.frame]?.time ?? first)}" x2="${px(samples[state.frame]?.time ?? first)}" y1="${top}" y2="${h - bottom}" stroke="var(--accent)" stroke-width="1.2"/>${markers}<g font-family="Plex" font-size="10.5">${legend}</g></svg><div class="plot-readout" id="plotReadout" hidden></div>`;
  $("plot").setAttribute(
    "aria-label",
    `${signal.title} in ${signal.unit} versus time. ${signal.channels.map(([, label], i) => `${label} ${["solid blue", "dashed teal", "dashed gold"][i]}`).join("; ")}. ${state.result.source}. ${samples.length} samples. Range ${format(Math.min(...values), 3)} to ${format(Math.max(...values), 3)}.`,
  );
  renderPlotStats();
  renderStudyResults();
  placePlotCursor();
}
function renderPlotStats() {
  const geometry = plotGeometry;
  if (!geometry) return;
  const samples = state.result.samples, frame = Math.min(state.frame, samples.length - 1);
  const signal = resultSignal();
  const full = geometry.series.some((item) => item.full);
  const steps = full ? fullResolution.get(state.result).times.length : samples.length;
  const pinned = state.overlays.length || state.compareRun
    ? `<div class="stat-pins">${state.overlays.map((overlay, i) => `<button type="button" data-overlay="${i}" title="Remove pinned trace">${escapeHtml(overlay.name)} · ${escapeHtml(overlay.title)} ×</button>`).join("")}${state.compareRun ? `<button type="button" data-compare title="Stop comparing">vs ${escapeHtml(state.compareRun.name)} ×</button>` : ""}</div>`
    : "";
  $("plotStats").innerHTML = `<div class="stat-title">${escapeHtml(signal.unit)} · t = ${format(samples[frame].time)} s</div><div class="stat-source">${full ? `Full resolution · ${steps.toLocaleString()} steps` : `Displayed samples · ${steps.toLocaleString()}`}</div>${pinned}` + geometry.series.map((item, i) => {
    const stats = seriesStatistics(item.times, item.values);
    return `<div class="stat-channel"><b><i style="background:${item.color}"></i>${escapeHtml(item.label)}</b><dl><dt>value</dt><dd data-live="${i}">—</dd><dt>min</dt><dd title="at ${format(stats.minAt, 4)} s">${formatValue(stats.min)}</dd><dt>max</dt><dd title="at ${format(stats.maxAt, 4)} s">${formatValue(stats.max)}</dd><dt>peak at</dt><dd>${format(Math.abs(stats.max) >= Math.abs(stats.min) ? stats.maxAt : stats.minAt, 4)} s</dd><dt>range</dt><dd>${formatValue(stats.max - stats.min)}</dd><dt>rms</dt><dd>${formatValue(stats.rms)}</dd></dl></div>`;
  }).join("");
  $("plotStats").querySelectorAll("[data-overlay]").forEach((button) => { button.onclick = () => { state.overlays.splice(Number(button.dataset.overlay), 1); drawPlot(); }; });
  $("plotStats").querySelector("[data-compare]")?.addEventListener("click", () => { state.compareRun = null; renderCompareControls(); drawPlot(); });
}
function seriesValueAt(item, t) {
  return item.values[nearestIndex(item.times, t)];
}
function placePlotCursor() {
  const geometry = plotGeometry, samples = state.result?.samples;
  if (!geometry || !samples) return;
  const sample = samples[state.frame];
  const x = geometry.px(sample.time);
  $("plotCursor")?.setAttribute("x1", String(x));
  $("plotCursor")?.setAttribute("x2", String(x));
  document.querySelectorAll("#plot .plot-marker").forEach((marker) => {
    const value = seriesValueAt(geometry.series[Number(marker.dataset.index)], sample.time);
    marker.setAttribute("cx", Number.isFinite(value) ? String(x) : "-10");
    marker.setAttribute("cy", Number.isFinite(value) ? String(geometry.py(value)) : "-10");
  });
  document.querySelectorAll("#plotStats [data-live]").forEach((cell) => {
    cell.textContent = formatValue(seriesValueAt(geometry.series[Number(cell.dataset.live)], sample.time));
  });
  const title = document.querySelector("#plotStats .stat-title");
  if (title) title.textContent = `${resultSignal().unit} · t = ${format(sample.time)} s`;
}
function plotTimeAt(event) {
  const geometry = plotGeometry;
  if (!geometry) return null;
  const rect = $("plot").getBoundingClientRect();
  const x = ((event.clientX - rect.left) / rect.width) * geometry.w;
  if (x < geometry.left - 4 || x > geometry.w - geometry.right + 4) return null;
  return Math.max(geometry.first, Math.min(geometry.first + geometry.duration, geometry.first + ((x - geometry.left) / (geometry.w - geometry.left - geometry.right)) * geometry.duration));
}
function plotFrameAt(event) {
  const t = plotTimeAt(event), samples = state.result?.samples;
  return t === null || !samples ? null : nearestIndex(samples.map((sample) => sample.time), t);
}
let plotDragging = false;
$("plot").addEventListener("pointermove", (event) => {
  const t = plotTimeAt(event), geometry = plotGeometry;
  const hover = $("plotHover"), readout = $("plotReadout");
  if (t === null || !hover || !readout) { if (hover) hover.setAttribute("x1", "-10"), hover.setAttribute("x2", "-10"); if (readout) readout.hidden = true; return; }
  // The readout uses each series' own resolution, so it can show values between displayed samples.
  const x = geometry.px(t);
  hover.setAttribute("x1", String(x));
  hover.setAttribute("x2", String(x));
  readout.innerHTML = `t = ${format(t, 4)} s<br>${geometry.series.map((item) => `<i style="background:${item.color}"></i>${escapeHtml(item.label)} ${formatValue(seriesValueAt(item, t))}`).join("<br>")}`;
  readout.hidden = false;
  const rect = $("plot").getBoundingClientRect(), left = (x / geometry.w) * rect.width;
  readout.style.left = `${left + 12 + readout.offsetWidth > rect.width ? left - readout.offsetWidth - 12 : left + 12}px`;
  readout.style.top = "18px";
  if (plotDragging && !stale()) { state.playing = false; setFrame(plotFrameAt(event)); }
});
$("plot").addEventListener("pointerleave", () => {
  plotDragging = false;
  $("plotHover")?.setAttribute("x1", "-10");
  $("plotHover")?.setAttribute("x2", "-10");
  if ($("plotReadout")) $("plotReadout").hidden = true;
});
$("plot").addEventListener("pointerdown", (event) => {
  const index = plotFrameAt(event);
  if (index === null || stale()) return;
  plotDragging = true;
  state.playing = false;
  setFrame(index);
});
window.addEventListener("pointerup", () => { plotDragging = false; });
function entityName() {
  const signal = resultSignal(), key = signal.channels[0]?.[0] || "";
  const [kind, id] = key.split(":");
  if (kind === "node") return visualInfo(state.result.model)?.nodes.find((node) => String(node.id) === id)?.label || id;
  return id && kind !== key ? id : signal.title;
}
$("pinTraceButton").onclick = () => {
  if (!state.result) return;
  const signal = resultSignal();
  const name = entityName();
  if (state.overlays.some((overlay) => overlay.name === name && overlay.title === signal.title)) return notice("This trace is already pinned.");
  state.overlays.push({ name, title: signal.title, unit: signal.unit, channels: signal.channels.map(([key, label]) => [key, label]) });
  notice(`Pinned ${name} · ${signal.title}. Choose another body or element with the same unit to compare it on one plot.`);
  drawPlot();
};
function renderCompareControls() {
  const compare = state.compareRun;
  $("compareStatus").textContent = compare ? `Comparing with ${compare.name} (${compare.label}).` : "Pin this run, change the model and run again to overlay both responses.";
  $("compareButton").textContent = compare ? "Pin the current run instead" : "Pin run for comparison";
  $("compareClearButton").hidden = !compare;
}
$("compareButton").onclick = () => {
  if (!state.result) return;
  state.compareCount = (state.compareCount || 0) + 1;
  state.compareRun = { result: state.result, name: `Run ${state.compareCount}`, label: `${state.result.samples.at(-1).time.toFixed(3)} s, ${state.result.source}` };
  renderCompareControls();
  drawPlot();
  notice(`${state.compareRun.name} pinned. Edit the model and run again; the pinned response stays on the plot as a grey dashed line.`);
};
$("compareClearButton").onclick = () => { state.compareRun = null; renderCompareControls(); drawPlot(); };
// ---------- Parameter studies ----------
// One input is solved for several values plus its current (baseline) value. Cases live in memory
// for the session; projects keep the baseline result.
let studyInputs = [], studyRunning = false, studyCancelled = false, studySetupPending = false;
/** A study set-up from a project or the featured catalog: input path key, values and response quantity. */
function validStudySetup(value) {
  if (!value || typeof value.input !== "string" || value.input.length > 200 || !Array.isArray(value.values)) return null;
  const values = value.values.filter(Number.isFinite);
  if (values.length < 1 || values.length > MAX_CASES || values.length !== value.values.length) return null;
  const response = typeof value.response === "string" && value.response.length <= 200 ? value.response : null;
  return { input: value.input, values, ...(response ? { response } : {}) };
}
const ENTITY_COLLECTIONS = { node: "bodies", joint: "joints", force: "forces", contact: "contacts", applied: "loads" };
const selectedStudyInput = () => studyInputs.find((item) => pathKey(item.path) === $("studyParameter").value) || null;
// Trailing zeros of a decimal fraction only: 0.12300 → 0.123, 1.0000e+5 → 1e+5, 20000 stays.
const studyValueLabel = (value) => formatValue(value).replace(/(\.\d*?)0+(?=e|$)/, "$1").replace(/\.(?=e|$)/, "");
const activeStudy = () => (state.study?.cases.some((item) => item.result === state.result) ? state.study : null);
const studyChannel = (signal) => Math.min(state.study?.channel || 0, signal.channels.length - 1);
function savedResult() {
  return state.study?.cases.find((item) => item.baseline)?.result || state.result;
}
function renderStudyControls() {
  const select = $("studyParameter"), keep = select.value;
  studyInputs = state.model.kind === "source-example" ? [] : listStudyParameters(state.model, fields);
  const groups = new Map();
  for (const item of studyInputs) {
    if (!groups.has(item.group)) {
      const group = document.createElement("optgroup");
      group.label = item.group;
      groups.set(item.group, group);
    }
    const option = document.createElement("option");
    option.value = pathKey(item.path);
    option.textContent = `${item.label}${item.unit ? ` (${item.unit})` : ""}`;
    groups.get(item.group).append(option);
  }
  select.replaceChildren(...groups.values());
  // Prefer the input kept from before, then one of the entity selected in the model tree.
  const [kind, ...rest] = String(state.selection).split("-"), id = rest.join("-");
  // A set-up that came with the project wins once, then the user's own choice is kept.
  const setup = studySetupPending ? studyInputs.find((item) => pathKey(item.path) === state.studySetup?.input) : null;
  studySetupPending = false;
  if (setup) {
    select.value = pathKey(setup.path);
    $("studyValues").value = state.studySetup.values.join(", ");
    updateStudyInput();
    return;
  }
  const preferred = studyInputs.find((item) => pathKey(item.path) === keep)
    || studyInputs.find((item) => item.path[0] === ENTITY_COLLECTIONS[kind] && item.path[1] === id)
    || studyInputs[0];
  if (preferred) select.value = pathKey(preferred.path);
  if (pathKey(preferred?.path || []) !== keep) $("studyValues").value = "";
  updateStudyInput();
}
function updateStudyInput() {
  const item = selectedStudyInput();
  $("studyUnit").textContent = item?.unit || "";
  if (item && !$("studyValues").value.trim()) $("studyValues").value = suggestValues(item.value).join(", ");
  $("studyHint").textContent = item
    ? `Current value ${studyValueLabel(item.value)}${item.unit ? ` ${item.unit}` : ""}, always solved as the baseline. Up to ${MAX_CASES} cases.`
    : "This model has no inputs a study can vary.";
  $("studyRunButton").disabled = state.busy || !item;
}
$("studyParameter").onchange = () => { $("studyValues").value = ""; updateStudyInput(); };
async function runStudy() {
  if (state.busy || state.saving || state.opening) return;
  const input = selectedStudyInput();
  if (!input) return;
  let values;
  try {
    const baseline = parameterValue(state.model, input.path);
    values = [...new Set([...parseValues($("studyValues").value), baseline])].sort((a, b) => a - b);
    if (values.length > MAX_CASES) throw new Error(`A study runs at most ${MAX_CASES} cases, including the baseline.`);
  } catch (error) {
    notice(error.message, "error");
    return;
  }
  setBusy(true);
  const checked = await validate(false);
  if (!checked.valid) {
    setBusy(false);
    notice("The model needs attention before it can run. Review the highlighted fields.", "error");
    return;
  }
  const base = structuredClone(state.model), key = signature(), baseline = parameterValue(base, input.path);
  const name = `${input.label}${input.unit ? ` (${input.unit})` : ""}`, cases = [], log = [];
  let failure = null;
  studyRunning = true;
  studyCancelled = false;
  state.playing = false;
  $("studyProgress").hidden = false;
  try {
    for (const [index, value] of values.entries()) {
      if (studyCancelled) break;
      const caption = `Case ${index + 1} of ${values.length} · ${input.label} = ${studyValueLabel(value)}${input.unit ? ` ${input.unit}` : ""}`;
      $("studyProgressText").textContent = caption;
      $("studyProgressBar").value = index / values.length;
      status(`Parameter study · ${caption}`);
      showConsole("Parameter study", [...log, `${caption} · solving…`].join("\n"));
      const model = caseModel(base, input.path, value);
      activeRunToken = [...crypto.getRandomValues(new Uint8Array(16))].map((byte) => byte.toString(16).padStart(2, "0")).join("");
      setBusy(true);
      try {
        const result = await api("run", model, activeRunToken);
        if (result.ok === false) throw new Error(result.error || "The solver did not finish successfully.");
        if (!Array.isArray(result.samples) || !result.samples.length) throw new Error("No response samples were returned.");
        if (assemblyKind(model)) result.model = model;
        cases.push({ value, baseline: value === baseline, result });
        log.push(`${caption} · ${result.samples.length.toLocaleString()} samples · run ${result.runId}`);
      } catch (error) {
        if (error.details?.cancelled) studyCancelled = true;
        else failure = { caption, error };
        log.push(`${caption} · ${error.details?.cancelled ? "cancelled" : `failed: ${error.message}`}`);
        break;
      } finally {
        activeRunToken = null;
      }
    }
  } finally {
    studyRunning = false;
    setBusy(false);
    $("studyProgress").hidden = true;
    showConsole("Parameter study", log.join("\n"));
  }
  if (!cases.length) {
    notice(failure ? `${failure.caption} failed: ${failure.error.message}` : "The study was stopped before any case finished.", "error");
    status("Parameter study stopped");
    return;
  }
  state.study = { input: { ...input, name }, cases, signature: key, channel: 0, colors: caseColors(cases.length) };
  const response = state.studySetup?.input === pathKey(input.path) ? state.studySetup.response : null;
  state.studySetup = { input: pathKey(input.path), values: values.filter((value) => value !== baseline), ...(response ? { response } : {}) };
  showStudyCase(cases.find((item) => item.baseline) || cases[0]);
  const option = response && [...$("signalSelect").options].find((item) => item.textContent === response);
  if (option) { $("signalSelect").value = option.value; state.signal = Number(option.value); renderResult(); }
  markNativeDirty();
  switchStep("results");
  const solved = `${cases.length} of ${values.length} cases solved`;
  notice(failure ? `${failure.caption} failed: ${failure.error.message} ${solved}.` : studyCancelled ? `Study stopped · ${solved}.` : `Parameter study complete · ${solved}. Select a case to animate it.`, failure || studyCancelled ? "warn" : "");
  status(`Parameter study · ${solved}`);
}
$("studyRunButton").onclick = runStudy;
function showStudyCase(item) {
  state.result = item.result;
  state.resultSignature = state.study.signature;
  state.lastFailure = null;
  state.frame = 0;
  playTime = 0;
  state.playing = false;
  renderResult();
  setFrame(0);
  $("runId").textContent = item.result.runId || "Study case";
}
function renderStudyResults() {
  const study = activeStudy();
  $("studyResults").hidden = !study;
  if (!study) return;
  const signal = resultSignal(), channel = studyChannel(signal), [key, label] = signal.channels[channel];
  $("studyChannelField").hidden = signal.channels.length < 2;
  $("studyChannel").replaceChildren(...signal.channels.map(([, name], i) => Object.assign(document.createElement("option"), { value: String(i), textContent: name })));
  $("studyChannel").value = String(channel);
  const response = `${signal.title}${signal.channels.length > 1 ? ` · ${label}` : ""}`;
  $("studySummary").textContent = `${study.input.group} · ${study.input.name}, ${study.cases.length} cases. Response: ${response} (${signal.unit}) for ${entityName()}.`;
  study.rows = study.cases.map((item) => ({ value: item.value, summary: caseSummary(...Object.values((({ times, values }) => ({ times, values }))(seriesFor(item.result, key)))) }));
  const head = `<thead><tr><th scope="col">${escapeHtml(study.input.label)}${study.input.unit ? ` <small>${escapeHtml(study.input.unit)}</small>` : ""}</th><th scope="col">max</th><th scope="col">min</th><th scope="col">rms</th><th scope="col">final</th></tr></thead>`;
  const body = study.rows.map(({ value, summary }, i) => {
    const item = study.cases[i], shown = item.result === state.result;
    return `<tr class="${shown ? "shown" : ""}" data-case="${i}"><th scope="row"><button type="button" class="study-case" aria-label="Show case ${escapeHtml(studyValueLabel(value))}" aria-pressed="${shown}"><i style="background:${study.colors[i]}"></i></button>${escapeHtml(studyValueLabel(value))}${item.baseline ? ' <span class="study-baseline" title="The current value">base</span>' : ""}</th><td title="at ${format(summary.maxAt, 4)} s">${studyValueLabel(summary.max)}</td><td title="at ${format(summary.minAt, 4)} s">${studyValueLabel(summary.min)}</td><td>${studyValueLabel(summary.rms)}</td><td>${studyValueLabel(summary.final)}</td></tr>`;
  }).join("");
  $("studyTable").innerHTML = `${head}<tbody>${body}</tbody>`;
  $("studyTable").querySelectorAll("tr[data-case]").forEach((row) => {
    row.onclick = () => {
      const item = study.cases[Number(row.dataset.case)];
      if (item.result !== state.result) showStudyCase(item);
    };
  });
  study.response = { label: response, unit: signal.unit };
}
$("studyChannel").onchange = () => { if (state.study) { state.study.channel = Number($("studyChannel").value); drawPlot(); } };
$("studyCsvButton").onclick = () => {
  const study = activeStudy();
  if (!study?.rows) return;
  download("parameter-study.csv", summaryCsv({ group: study.input.group, label: study.input.label, unit: study.input.unit }, study.response, study.rows), "text/csv");
};
function clearStudy(redraw = true) {
  if (!state.study) return;
  const baseline = state.study.cases.find((item) => item.baseline)?.result;
  const showing = activeStudy();
  state.study = null;
  $("studyResults").hidden = true;
  if (redraw && showing && baseline && baseline !== state.result) {
    state.result = baseline;
    state.frame = 0;
    playTime = 0;
    state.playing = false;
    renderResult();
    setFrame(0);
    $("runId").textContent = baseline.runId || "MBDyn run";
  } else if (redraw && state.result) drawPlot();
}
$("studyClearButton").onclick = () => clearStudy();
function exportablePlot() {
  const svg = $("plot").querySelector("svg");
  if (!svg) return null;
  const clone = svg.cloneNode(true);
  const style = getComputedStyle(document.documentElement);
  const resolve = (text) => text.replace(/var\((--[a-z0-9-]+)\)/g, (_, name) => style.getPropertyValue(name).trim() || "#888");
  clone.querySelectorAll("*").forEach((element) => {
    for (const attribute of ["fill", "stroke"]) if (element.getAttribute(attribute)?.includes("var(")) element.setAttribute(attribute, resolve(element.getAttribute(attribute)));
  });
  clone.querySelectorAll("#plotHover, .plot-marker").forEach((element) => element.remove());
  const [, , w, h] = clone.getAttribute("viewBox").split(" ").map(Number);
  const background = document.createElementNS("http://www.w3.org/2000/svg", "rect");
  background.setAttribute("width", w); background.setAttribute("height", h); background.setAttribute("fill", resolve("var(--surface)"));
  clone.insertBefore(background, clone.firstChild);
  const title = document.createElementNS("http://www.w3.org/2000/svg", "title");
  title.textContent = `${state.model.name} · ${resultSignal().title} (${state.result.source})`;
  clone.insertBefore(title, clone.firstChild);
  clone.setAttribute("width", w); clone.setAttribute("height", h);
  clone.querySelectorAll("text").forEach((text) => text.setAttribute("font-family", "IBM Plex Sans, Helvetica, Arial, sans-serif"));
  return { text: new XMLSerializer().serializeToString(clone), w, h };
}
function plotFileName(extension) {
  return `${state.model.name}-${resultSignal().title}`.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "").slice(0, 80) + `.${extension}`;
}
$("plotSvgButton").onclick = () => {
  const plot = exportablePlot();
  if (plot) download(plotFileName("svg"), plot.text, "image/svg+xml");
};
$("plotPngButton").onclick = () => {
  const plot = exportablePlot();
  if (!plot) return;
  const image = new Image(), scale = 2;
  image.onload = () => {
    const canvas = document.createElement("canvas");
    canvas.width = plot.w * scale; canvas.height = plot.h * scale;
    const context = canvas.getContext("2d");
    context.scale(scale, scale);
    context.drawImage(image, 0, 0);
    canvas.toBlob((blob) => { if (blob) download(plotFileName("png"), blob, "image/png"); });
  };
  image.src = `data:image/svg+xml;charset=utf-8,${encodeURIComponent(plot.text)}`;
};
function setFrame(index) {
  const samples = state.result?.samples;
  if (!samples?.length) return;
  state.frame = Math.max(0, Math.min(index, samples.length - 1));
  const sample = samples[state.frame];
  $("timeSlider").value = String(state.frame);
  $("timeOutput").textContent = `${format(sample.time)} s`;
  $("viewTime").textContent = `t = ${format(sample.time)} s`;
  if (!stale()) {
    view?.setSample(sample);
    view?.setTrailFrame(state.frame);
  }
  updateSourceProbe();
  placePlotCursor();
}
function animate(time) {
  if (state.playing && state.result && !stale()) {
    playTime += ((time - lastFrame) / 1000) * state.speed;
    const samples = state.result.samples;
    const end = samples.at(-1).time;
    if (playTime > end) {
      if (state.loop) playTime = samples[0].time;
      else { playTime = end; state.playing = false; }
    }
    let index = state.frame;
    if (samples[index].time > playTime) index = 0;
    while (index < samples.length - 1 && samples[index + 1].time <= playTime)
      index++;
    setFrame(index);
  }
  lastFrame = time;
  $("playButton").innerHTML = icon(state.playing ? "pause" : "play");
  $("playButton").setAttribute(
    "aria-label",
    state.playing ? "Pause result animation" : "Play result animation",
  );
  requestAnimationFrame(animate);
}
function showDocument(title, text, filename) {
  $("documentTitle").textContent = title;
  $("documentEyebrow").textContent = "INSPECTABLE BY DESIGN";
  const pre = document.createElement("pre");
  pre.textContent = text;
  $("documentBody").replaceChildren(pre);
  pendingDownload = filename ? { name: filename, text } : null;
  $("documentDownload").hidden = !pendingDownload;
  $("documentDialog").showModal();
}
function showGuide() {
  $("documentTitle").textContent = "From a mechanism to a result";
  $("documentEyebrow").textContent = "QUICK START";
  $("documentBody").innerHTML = `<article>
    <p><strong>Kinemeld</strong> is an independent, open-source multibody workbench. Choose <strong>Tour</strong> for the interactive walkthrough or open <strong>docs/first-study.md</strong> in the application folder.</p>
    <h3>1. Start with a mechanism or STEP geometry</h3>
    <p>Choose <strong>STEP parts → Load moving STEP pendulum</strong> for a solid with a matching physical model. New geometry imports accept <strong>.step</strong> and <strong>.stp</strong> files. Imported solids are display geometry: define mass, inertia, body frames and connections separately, then attach each solid to an assembly body to follow its motion. Older saved projects may still contain visual STL references.</p>
    <p><strong>Examples</strong> includes editable planar and spatial assemblies, six parameterized mechanism families and verified upstream MBDyn studies. Upstream inputs retain their original definitions and source provenance.</p>
    <h3>2. Build a planar body and hinge graph</h3>
    <p>In a planar assembly, add a body with a revolute hinge or prismatic slider. Edit its mass, principal inertia, pose and velocity; assign linear axial spring-dampers or constant global force and torque. Select a joint to edit its frame and anchors, and validate the initial constraints. Undo and Redo retain edits and STEP attachments.</p>
    <p>The planar editor supports rooted trees. The spatial editor supports free bodies and disconnected graphs as well as closed loops, with revolute, prismatic, cylindrical, universal, spherical and weld joints. Constraints must have compatible initial states and non-redundant degrees of freedom; MBDyn decides whether a model is solvable. Elastic sphere-plane contact with optional damping and regularised Coulomb friction is available; general surface contact and flexible bodies are not. Units are metres, kilograms and seconds; body angles are entered in degrees.</p>
    <h3>3. Validate and run</h3>
    <p><strong>Validate model</strong> checks supported topology, physical inputs and time resolution. <strong>Inspect MBDyn deck</strong> shows the solver input. <strong>Run simulation</strong> uses the configured local MBDyn solver and retains errors and partial logs when a run fails. Validation alone is not engineering certification.</p>
    <h3>4. Explore the response</h3>
    <p>Play or scrub the timeline, select nodes and response quantities, and export CSV. Attached STEP solids follow the corresponding solver body. Existing templates also offer a separately labelled <strong>Reference preview</strong>; this is not available for authored graphs or pinned upstream studies. Editing physical inputs makes older results stale.</p>
    <h3>5. Save and reopen</h3>
    <p>The Windows desktop uses native <strong>Save project</strong>, <strong>Save as</strong> and <strong>Open project</strong> dialogs. Projects retain the physical model, available results and full CSV, viewing state, original STEP bytes and part bindings. Conflicting disk changes are reported before overwrite. The browser version exports and imports portable project files; browser recovery retains only the current physical model.</p>
    <p>See <a href="/docs/tutorials.md" target="_blank" rel="noreferrer">tutorials</a> for model assumptions and <a href="/docs/roadmap.md" target="_blank" rel="noreferrer">the roadmap</a> for remaining scope. Static, modal and buckling FEA belong to the separate Enigmiq CAD workflow. Official reference: <a href="https://www.mbdyn.org/Documentation.html" target="_blank" rel="noreferrer">MBDyn documentation</a>.</p>
  </article>`;
  pendingDownload = null;
  $("documentDownload").hidden = true;
  $("documentDialog").showModal();
}
const FEATURED_ART = {
  "quarter-car": '<svg viewBox="0 0 180 100" fill="none" stroke="currentColor" stroke-width="3" stroke-linecap="round"><path d="M20 30l55 6M20 70l55 4M78 30l4 46"/><circle cx="120" cy="54" r="34"/><circle cx="120" cy="54" r="20" stroke="#13998f"/><path d="M40 18l12 10-10 4 12 6-10 4 12 6" stroke="#d0821b"/></svg>',
  "gear-drop": '<svg viewBox="0 0 180 100" fill="none" stroke="currentColor" stroke-width="3" stroke-linecap="round"><rect x="55" y="8" width="70" height="18" rx="3"/><path d="M90 26v26M84 30h12v22H84z"/><circle cx="90" cy="70" r="18"/><path d="M30 92h120" stroke="#13998f"/><path d="M150 20v28m-6-6 6 6 6-6" stroke="#d0821b"/></svg>',
  "slider-crank": '<svg viewBox="0 0 180 100" fill="none" stroke="currentColor" stroke-width="3" stroke-linecap="round"><circle cx="60" cy="70" r="24"/><path d="M60 70l14-16 40-34"/><rect x="104" y="6" width="24" height="18" rx="2" stroke="#13998f"/><path d="M100 4v30M132 4v30" stroke-dasharray="3 4"/><path d="M28 70a32 32 0 0 1 8-22" stroke="#d0821b"/></svg>',
  "gyroscopic-top": '<svg viewBox="0 0 180 100" fill="none" stroke="currentColor" stroke-width="3" stroke-linecap="round"><path d="M90 92L112 24"/><ellipse cx="106" cy="40" rx="30" ry="9" transform="rotate(-18 106 40)"/><path d="M60 22c10-12 50-16 72-4" stroke="#d0821b" stroke-dasharray="4 4"/><path d="M60 92h60" stroke="#13998f"/></svg>',
  "tumbling-handle": '<svg viewBox="0 0 180 100" fill="none" stroke="currentColor" stroke-width="3" stroke-linecap="round"><path d="M58 40h64M90 40v34"/><circle cx="90" cy="80" r="6"/><path d="M40 70a50 30 0 0 0 100 0" stroke="#d0821b" stroke-dasharray="4 4"/><path d="M134 66l6 4-2 7" stroke="#d0821b"/></svg>',
  "chaotic-pendulums": '<svg viewBox="0 0 180 100" fill="none" stroke-width="3" stroke-linecap="round"><path d="M40 8h100" stroke="currentColor"/><path d="M80 8l-24 30-6 34" stroke="currentColor"/><circle cx="50" cy="72" r="7" fill="currentColor"/><path d="M100 8l24 30 10 32" stroke="#13998f"/><circle cx="134" cy="70" r="7" fill="#13998f"/><path d="M30 60c20 30 40-20 60 10s40 10 60-20" stroke="#d0821b" stroke-dasharray="3 4"/></svg>',
};
function exampleArt(kind) {
  if (FEATURED_ART[kind]) return FEATURED_ART[kind];
  if (["source-example", "planar-assembly", "spatial-assembly"].includes(kind))
    return '<svg viewBox="0 0 180 100" fill="none"><path d="M28 68L65 26l47 10 35 38H28M65 26l13 54m34-44-34 44" stroke="currentColor" stroke-width="3"/><circle cx="28" cy="68" r="6" fill="currentColor"/><circle cx="65" cy="26" r="6" fill="currentColor"/><circle cx="112" cy="36" r="6" fill="currentColor"/><circle cx="147" cy="74" r="6" fill="currentColor"/><circle cx="78" cy="80" r="6" fill="#159aa4"/></svg>';
  if (kind === "suspension")
    return '<svg viewBox="0 0 180 100" fill="none"><path d="M24 24h132v16H24zM58 40v7l-9 4 18 7-18 7 9 4v9M117 40v32M20 92h140" stroke="currentColor" stroke-width="3"/><circle cx="87" cy="76" r="15" fill="currentColor"/><circle cx="87" cy="76" r="7" fill="#b5c7dc"/></svg>';
  if (kind === "landing-gear-drop")
    return '<svg viewBox="0 0 180 100" fill="none"><path d="M51 12h78M90 13v23M80 36h20v28H80zM90 64v16M28 96h125M38 30v31m-5-5 5 5 5-5" stroke="currentColor" stroke-width="4"/><circle cx="78" cy="82" r="11" fill="currentColor"/><circle cx="103" cy="82" r="11" fill="currentColor"/></svg>';
  if (kind === "gear-deployment")
    return '<svg viewBox="0 0 180 100" fill="none"><path d="M23 15h130M46 15l62 60M76 45l-8 29 71-59" stroke="currentColor" stroke-width="4"/><circle cx="112" cy="80" r="13" fill="currentColor"/><circle cx="68" cy="74" r="5" fill="#159aa4"/></svg>';
  if (kind === "double-pendulum")
    return '<svg viewBox="0 0 180 100" fill="none"><path d="M35 9h90M76 9l23 36 34 34" stroke="currentColor" stroke-width="4" stroke-linecap="round"/><circle cx="99" cy="45" r="10" fill="currentColor"/><circle cx="133" cy="79" r="12" fill="#1ba9b1"/></svg>';
  return kind === "pendulum"
    ? '<svg viewBox="0 0 180 100" fill="none"><path d="M35 14h90M80 14l44 63" stroke="currentColor" stroke-width="5" stroke-linecap="round"/><circle cx="124" cy="77" r="13" fill="currentColor"/><path d="M38 76Q77 105 132 82" stroke="currentColor" stroke-dasharray="3 5" opacity=".3"/></svg>'
    : '<svg viewBox="0 0 180 100" fill="none"><path d="M23 25v55M23 52h12l6-14 12 28 12-28 12 28 12-28 6 14h12M20 83h145" stroke="currentColor" stroke-width="3"/><rect x="107" y="32" width="40" height="40" rx="5" fill="currentColor"/></svg>';
}
const EXAMPLE_GROUPS = [["featured", "Featured studies"], ["assembly", "3D & planar assemblies"], ["template", "Templates"], ["upstream", "Upstream MBDyn decks"]];
let exampleGroup = "featured";
function exampleCard(art, category, title, description, action, featured = false) {
  const card = document.createElement("article");
  card.className = "example-card";
  card.innerHTML = `<div class="example-art">${featured ? '<span class="featured">FEATURED</span>' : ""}${art}</div><div class="example-card-body"><span class="eyebrow"></span><h3></h3><p></p><button class="secondary">Open →</button></div>`;
  card.querySelector(".eyebrow").textContent = category;
  card.querySelector("h3").textContent = title;
  card.querySelector("p").textContent = description;
  const button = card.querySelector("button");
  if (action.label) button.textContent = action.label;
  button.onclick = action.run;
  return card;
}
function renderExamples() {
  const root = $("exampleCards");
  root.replaceChildren();
  const groups = EXAMPLE_GROUPS.filter(([id]) => id !== "featured" || state.featured?.length);
  if (!groups.some(([id]) => id === exampleGroup)) exampleGroup = groups[0][0];
  $("exampleFilters").replaceChildren(...groups.map(([id, label]) => {
    const button = document.createElement("button");
    button.type = "button";
    button.textContent = label;
    button.className = id === exampleGroup ? "active" : "";
    button.onclick = () => {
      exampleGroup = id;
      $("exampleFilters").querySelectorAll("button").forEach((item) => item.classList.toggle("active", item === button));
      root.querySelector(`[data-group="${id}"]`)?.scrollIntoView({ block: "start", behavior: "smooth" });
    };
    return button;
  }));
  const sections = Object.fromEntries(groups.map(([id, label]) => {
    const heading = document.createElement("h3");
    heading.className = "example-group";
    heading.dataset.group = id;
    heading.textContent = label;
    root.append(heading);
    return [id, heading];
  }));
  const place = (group, card) => {
    let anchor = sections[group];
    while (anchor.nextElementSibling && !anchor.nextElementSibling.classList.contains("example-group")) anchor = anchor.nextElementSibling;
    anchor.after(card);
  };
  for (const study of state.featured || []) {
    const card = exampleCard(exampleArt(study.id) || exampleArt("spatial-assembly"), study.category, study.title, study.description, { label: "Open study →", run: () => openFeatured(study) }, true);
    if (study.study?.label) {
      const note = document.createElement("p");
      note.className = "example-study";
      note.textContent = `Parameter study included · ${study.study.label}`;
      card.querySelector("p").after(note);
    }
    place("featured", card);
  }
  for (const ex of [
    ...state.examples,
    ...state.sourceExamples.map((source) => ({
      ...source,
      model: sourceModel(source),
    })),
  ]) {
    const group = assemblyKind(ex.model) ? "assembly" : ex.model.kind === "source-example" ? "upstream" : "template";
    const category =
      assemblyKind(ex.model) ? (ex.model.kind === "spatial-assembly" ? "3D RIGID BODIES · EDITABLE" : "PLANAR · EDITABLE") : ex.model.kind === "source-example"
        ? `${ex.category} · ${ex.license.spdx} · UPSTREAM`
        : industry[ex.model.kind]?.category ||
          (ex.model.kind === "double-pendulum"
            ? "COUPLED · TWO BODIES"
            : ex.model.kind === "pendulum"
              ? "RIGID BODY · GRAVITY"
              : "ELASTICITY · DAMPING");
    if (ex.model.kind === "source-example" && !ex.enabled) {
      place(group, exampleCard(exampleArt(ex.model.kind), category, ex.title, ex.description, { label: "Why unavailable?", run: () =>
        showDocument(
          ex.title,
          `${ex.description}\n\n${ex.validation.error}\n\n${ex.validation.remediation}\n\nSource: ${ex.source.url}\nLicense: ${ex.license.spdx}`,
        ) }));
      continue;
    }
    place(group, exampleCard(exampleArt(ex.model.kind), category, ex.title, ex.description, { label: "Open example →", run: () => {
      applyModel(ex.model);
      state.overlays = [];
      state.compareRun = null;
      renderCompareControls();
      $("examplesDialog").close();
      switchStep("model");
      notice(
        ex.model.kind === "source-example"
          ? "Original upstream example loaded. Its input is read-only; inspect the deck, run it, and explore native node trajectories."
          : "Example loaded. Edit its parameters, validate, and run. Undo restores your previous model.",
      );
    } }));
  }
}

$("referenceRemoveButton").onclick = () => {
  referenceLoad++;
  replaceReference(null);
  notice("Visual STL reference removed. Solver model and results are unchanged.");
};
$("referenceIsolateButton").onclick = () => {
  const next = !view?.isolatedReference;
  view?.isolateReference(next);
  $("referenceIsolateButton").textContent = next ? "Show model" : "Isolate STL";
};
$("stepButton").onclick = () => {renderStepControls(); $("stepDialog").showModal();};
$("stepClose").onclick = () => $("stepDialog").close();
$("stepImport").onclick = () => $("stepFile").click();
$("stepPart").onchange = () => { $("stepBody").value = state.step?.metadata.bindings[$("stepPart").value]?.body || ""; };
$("stepReviewCandidate").onchange = renderStepReview;
$("stepReviewApply").onclick = () => {
  const asset=state.step, oldId=$("stepReviewCandidate").value, target=$("stepReviewTarget").value;
  const pending=asset?.metadata.unverifiedBindings || {}, binding=pending[oldId];
  if (!binding || !target || !asset.parts.some(part=>part.id===target && part.id.split(':',1)[0]===oldId.split(':',1)[0])) return notice("Choose a saved attachment and a current part from its original STEP file.","error");
  if (!asset.metadata.occurrenceWitnesses?.[target]) return notice("This STEP occurrence has no verifiable identity. Keep the saved attachment for review or use a STEP source with identifiable occurrences.","error");
  if (Object.hasOwn(asset.metadata.bindings,target)) return notice("The selected STEP part already has an attachment.","error");
  if (!assemblyKind(state.model) || !state.model.bodies.some(body=>body.id===binding.body)) return notice("The saved attachment's simulation body is missing. Restore that body before confirming the attachment.","error");
  if (Object.hasOwn(binding.pose,'rx') !== (state.model.kind==='spatial-assembly')) return notice("The saved registration pose is incompatible with the current assembly type.","error");
  const unverifiedBindings={...pending};delete unverifiedBindings[oldId];
  try {
    replaceStep({...asset,metadata:{...asset.metadata,bindings:{...asset.metadata.bindings,[target]:structuredClone(binding)},unverifiedBindings}});
    notice("Saved STEP attachment confirmed with its original registration pose. Check the geometry alignment before solving.");
  } catch(error) {notice(error.message,"error");}
};
$("stepReviewDiscard").onclick = () => {
  const asset=state.step, id=$("stepReviewCandidate").value, pending=asset?.metadata.unverifiedBindings || {};
  if (!Object.hasOwn(pending,id) || !confirm(`Discard the saved attachment ${id} for body ${pending[id].body}? You can undo this change.`)) return;
  const unverifiedBindings={...pending};delete unverifiedBindings[id];
  try {replaceStep({...asset,metadata:{...asset.metadata,unverifiedBindings}});notice("Saved STEP attachment discarded. Undo restores it.");} catch(error) {notice(error.message,"error");}
};
$("stepExport").onclick = () => {
  const index=Number($("stepPart").value.split(":",1)[0]), file=state.step?.metadata.files[index];
  if(!file)return notice("Select a STEP part to export its original source.","warn");
  const raw=atob(file.data), bytes=Uint8Array.from(raw,character=>character.charCodeAt(0));
  download(file.name,bytes,"application/step");
};
$("stepBind").onclick = () => {
  if (!state.step || !assemblyKind(state.model)) return;
  const part=$("stepPart").value, body=$("stepBody").value;
  const bindings={...state.step.metadata.bindings};
  if (body) {
    const node=visualInfo(state.model).initialNodes.find(n=>n.id===body);
    if (!node) return notice("The selected body no longer exists.", "error");
    const pose={x:node.x,y:node.y,z:node.z,ry:node.ry};
    if (state.model.kind === "spatial-assembly") Object.assign(pose,{rx:node.rx,rz:node.rz});
    bindings[part]={body,pose};
  } else delete bindings[part];
  const asset={...state.step,metadata:{...state.step.metadata,bindings}};
  try {replaceStep(asset); notice(body ? "STEP part attached to the selected body. Check its alignment before solving." : "STEP part is unattached and remains static.");}
  catch(error){notice(error.message,"error");}
};
$("stepRemove").onclick = () => {stepLoad++;replaceStep(null);notice("STEP geometry removed; the physical model is unchanged.");};
$("stepPendulum").onclick = async () => {
  const token=++stepLoad, before=signature();
  try {
    $("stepDetail").textContent="Preparing a STEP solid and matching MBDyn pendulum…";
    const example=state.examples.find(item=>item.id==="assembly-single");
    if(!example)throw Error("The matching planar pendulum example is unavailable.");
    const response=await fetch("/api/step/pendulum");
    if(!response.ok)throw Error("STEP service is unavailable. Restart Kinemeld to load the updated backend.");
    const asset=await loadStepAsset([{name:"pendulum.step",bytes:new Uint8Array(await response.arrayBuffer()),sha256:"21d27f30d5cc9459f70d7d3cc66f61a6e7c6b1a7e4f69b4fd72e2837090d96ac"}]);
    if(token!==stepLoad)return;
    if(signature()!==before || state.busy)throw Error("The current project changed while the example loaded; no changes were applied.");
    if(asset.parts.length!==1)throw Error("The pendulum STEP source must contain one solid.");
    const model=structuredClone(example.model), node=assemblyInfo(model).initialNodes.find(n=>n.id==="upper_link");
    asset.metadata.bindings={[asset.parts[0].id]:{body:node.id,pose:{x:node.x,y:node.y,z:node.z,ry:node.ry}}};
    const validation=await checkModel(model);
    if(token!==stepLoad)return;
    if(!validation.valid || signature()!==before || state.busy)throw Error("The model changed or could not be validated; the example was not applied.");
    validateStepForModel(asset,model);
    pushHistory();applyModel(model,false);replaceStep(asset,false);markNativeDirty();updateHistoryButtons();
    $("stepDialog").close();notice("Matching STEP solid and rigid pendulum loaded. Run MBDyn to see the solid move.");
  } catch(error) {if(token===stepLoad){renderStepControls();notice(`STEP pendulum could not be loaded: ${error.message}`,"error");}}
};
$("stepFile").onchange = async event => {
  const files=[...event.target.files], token=++stepLoad;
  try {
    if (!files.length) return;
    if (files.some(file => !/\.(step|stp)$/i.test(file.name))) throw Error("Choose STEP geometry files (.step or .stp). Saved projects may retain older visual references.");
    if (files.length>24 || files.reduce((n,file)=>n+file.size,0)>12*1024*1024) throw Error("Select up to 24 STEP files totalling at most 12 MiB.");
    $("stepDetail").textContent="Converting STEP solids locally…";
    const inputs=[];for(const file of files) inputs.push({name:file.name,bytes:new Uint8Array(await file.arrayBuffer())});
    const asset=await loadStepAsset(inputs);
    if(token!==stepLoad)return;
    replaceStep(asset);notice("STEP solids loaded. Attach them to assembly bodies to follow motion; define mass, inertia and joints in the physical model.");
  } catch(error) {if(token===stepLoad){renderStepControls();notice(`STEP import failed: ${error.message}`,"error");}}
  finally {event.target.value="";}
};
/** Load original parts from the shipped suspension STEP set; `pattern` selects a subset by file name. */
async function loadSuspensionParts(pattern = null) {
  const token=++stepLoad;
  try {
    $("stepDetail").textContent="Loading and converting the original suspension STEP parts…";
    const responseCatalog=await fetch("/api/step/suspension");
    if(!responseCatalog.ok)throw Error("STEP service is unavailable. Restart Kinemeld to load the updated backend.");
    const catalog=await responseCatalog.json(), inputs=[];
    for (const [i,file] of catalog.files.entries()) {
      if (pattern && !pattern.test(file.name)) continue;
      const response=await fetch(`/api/step/suspension/${i}`);if(!response.ok)throw Error(`Cannot load ${file.name}.`);
      inputs.push({name:file.name,bytes:new Uint8Array(await response.arrayBuffer()),sha256:file.sha256});
    }
    if(!inputs.length)throw Error("No matching STEP parts were found.");
    const asset=await loadStepAsset(inputs);if(token!==stepLoad)return false;
    replaceStep(asset);
    return true;
  } catch(error) {if(token===stepLoad){renderStepControls();notice(`Suspension STEP import failed: ${error.message}`,"error");}return false;}
}
$("stepExample").onclick = async () => {
  if (await loadSuspensionParts()) notice("Original double-wishbone STEP parts loaded. Source alignment and all physical body attachments require verification.");
};

$("durationInput").onchange = (e) =>
  setNumber("simulation", "duration", e.target.value);
$("stepInput").onchange = (e) =>
  setNumber("simulation", "step", e.target.value);
async function cancelActiveRun() {
  const token=activeRunToken;
  if(!token || !state.busy)return;
  if(studyRunning)studyCancelled=true;
  $("cancelRunButton").disabled=true;
  try {
    const response=await fetch("/api/run/cancel",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({runToken:token})});
    const result=await response.json();
    if(!response.ok || !result.ok)throw Error(result.error || "Could not cancel the solver run.");
    if(activeRunToken===token){notice("Stopping the solver; partial output will be retained.","warn");status("Stopping simulation…");}
  } catch(error){if(activeRunToken===token){$("cancelRunButton").disabled=false;notice(error.message,"error");}}
}
$("cancelRunButton").onclick=cancelActiveRun;
window.addEventListener("pagehide",()=>{
  if(activeRunToken)navigator.sendBeacon("/api/run/cancel",new Blob([JSON.stringify({runToken:activeRunToken})],{type:"application/json"}));
});
$("runButton").onclick = () => run();
$("previewButton").onclick = () => run(true);
$("validateButton").onclick = () => {
  switchStep("validate");
};
// Undo and Redo keep the selected entity when it still exists, so editing continues in place.
function restoreHistory(entry) {
  const selection = state.selection;
  state.step=entry.step;if(view)view.stepAsset=entry.step;
  applyModel(entry.model, false);replaceStep(entry.step,false);
  if (selection !== state.selection && document.querySelector(`#modelTree [data-entity="${CSS.escape(selection)}"]`)) select(selection);
}
$("undoButton").onclick = () => {
  if (!state.history.length) return;
  state.future.push(snapshot());
  restoreHistory(state.history.pop());
};
$("redoButton").onclick = () => {
  if (!state.future.length) return;
  state.history.push(snapshot());
  restoreHistory(state.future.pop());
};
async function nativeSave(saveAs) {
  if (state.saving || state.busy || state.opening) return;
  state.saving = true;
  $("saveButton").disabled = true;
  $("saveAsButton").disabled = true;
  try {
    const modelSignature = signature();
    const originalResult = state.result;
    const originalReference = state.reference;
    const originalStep = state.step, stepJson = JSON.stringify(state.step?.metadata);
    const payload = { ...(await projectPayload()), saveAs };
    const saved = await nativeDesktop.call("save", payload);
    if (saved.cancelled) return;
    cancelAutosave();
    if (signature() !== modelSignature || state.result !== originalResult || state.reference !== originalReference || state.step !== originalStep || JSON.stringify(state.step?.metadata) !== stepJson) {
      markNativeDirty();
      notice(`Saved a snapshot to ${saved.path}; newer edits remain unsaved.`, "warn");
      return;
    }
    $("dirtyMark").title = "Saved project";
    status(`Project saved · ${saved.path}`);
    notice(
      `Project saved to ${saved.path}${saved.backup ? `. Previous version retained at ${saved.backup}.` : "."}`,
    );
  } catch (error) {
    notice(`Project was not saved: ${error.message}`, "error");
  } finally {
    state.saving = false;
    $("saveButton").disabled = state.busy;
    $("saveAsButton").disabled = state.busy;
  }
}
// The full solver CSV of a run, fetched once (and shared while in flight) for saves and autosaves.
const resultCsv = new WeakMap();
function fullCsv(source) {
  if (!resultCsv.has(source)) {
    const text = fetch(source.files.csv).then((response) => {
      if (!response.ok)
        throw new Error("The full solver CSV is unavailable. The project was not saved; preserve the run folder and retry.");
      return response.text();
    });
    resultCsv.set(source, text);
    text.catch(() => resultCsv.delete(source));
  }
  return resultCsv.get(source);
}
/** The project as the desktop saves it: model, result with its full CSV (unless left out), view and asset metadata. */
async function projectPayload(includeResult = true) {
  const model = structuredClone(state.model);
  const reference = state.reference, stepMetadata = state.step ? structuredClone(state.step.metadata) : null;
  const source = includeResult ? savedResult() : null, view = currentViewState();
  let result = source ? structuredClone(source) : null;
  if (result?.source === "MBDyn" && !result.csvText && result.files?.csv) {
    if (!/^\/api\/runs\/[0-9a-f]{32}\/results\.csv$/.test(result.files.csv))
      throw new Error("The saved result contains an unsupported CSV location.");
    result.csvText = await fullCsv(source);
  }
  const payload = {
    model,
    result,
    view,
    assets: reference || stepMetadata ? {...(reference ? {reference:reference.metadata} : {}), ...(stepMetadata ? {step:stepMetadata} : {})} : null,
  };
  if (new Blob([JSON.stringify(payload)]).size > 32 * 1024 * 1024)
    throw new Error("Project exceeds 32 MiB. Export the CSV, clear the loaded result, then save the model and geometry.");
  return payload;
}
// ---------- Desktop autosave and crash recovery ----------
// While the desktop project has unsaved edits, a snapshot goes to the user's data folder once
// editing pauses, and at least once a minute during continuous editing. Saving or closing
// normally removes it; a snapshot found at start-up is offered back.
const AUTOSAVE_QUIET_MS = 15000, AUTOSAVE_MAX_MS = 60000;
let autosaveTimer = null, autosaveDeadline = 0, autosaveEnabled = false, autosaveFailed = false;
function scheduleAutosave() {
  if (!nativeDesktop || !autosaveEnabled) return;
  const now = Date.now();
  if (!autosaveTimer) autosaveDeadline = now + AUTOSAVE_MAX_MS;
  clearTimeout(autosaveTimer);
  autosaveTimer = setTimeout(autosave, Math.max(0, Math.min(AUTOSAVE_QUIET_MS, autosaveDeadline - now)));
}
function cancelAutosave() {
  clearTimeout(autosaveTimer);
  autosaveTimer = null;
}
async function autosave() {
  autosaveTimer = null;
  if (!browserDirty) return;
  if (state.saving || state.opening || state.busy) return scheduleAutosave();
  try {
    let payload;
    try {
      payload = await projectPayload();
    } catch (error) {
      // A result too large for a project still leaves the model, geometry and view worth keeping.
      if (!/exceeds 32 MiB/.test(error.message)) throw error;
      payload = await projectPayload(false);
    }
    const saved = await nativeDesktop.call("autosave", payload, 30000);
    if (saved.savedAt) {
      $("dirtyMark").title = `Unsaved changes · autosaved for recovery at ${new Date(saved.savedAt).toLocaleTimeString()}`;
      autosaveFailed = false;
    }
  } catch (error) {
    // Report once per failure streak; editing continues and the next change retries.
    if (!autosaveFailed) notice(`Autosave for crash recovery failed: ${error.message}`, "warn");
    autosaveFailed = true;
  }
}
async function offerRecovery() {
  let pending;
  try {
    pending = await nativeDesktop.call("recovery", {}, 10000);
  } catch (error) {
    notice(`Could not check for autosaved work: ${error.message}`, "warn");
    return;
  }
  if (pending.damaged) notice(`An autosaved project could not be read and was kept at ${pending.setAside}.`, "warn");
  if (!pending.savedAt) {
    autosaveEnabled = true;
    return;
  }
  $("recoveryText").textContent = `Kinemeld closed without saving changes to ${pending.name ? `“${pending.name}”` : "a project"}${pending.path ? ` (${pending.path})` : ""}. They were autosaved at ${new Date(pending.savedAt).toLocaleString()}.`;
  $("recoveryDialog").showModal();
  const recover = await new Promise((resolve) => {
    $("recoveryOpen").onclick = () => resolve(true);
    $("recoveryDiscard").onclick = () => resolve(false);
    $("recoveryDialog").oncancel = (event) => { event.preventDefault(); };
  });
  $("recoveryDialog").close();
  if (recover) await nativeOpen("recovery-open");
  else await setRecoveryAside();
  autosaveEnabled = true;
  if (browserDirty) scheduleAutosave();
}
async function setRecoveryAside(reason = "") {
  try {
    const aside = await nativeDesktop.call("recovery-discard", {}, 10000);
    if (aside.setAside) notice(`${reason}The autosaved project was set aside at ${aside.setAside}.`, reason ? "warn" : "");
  } catch (error) {
    notice(`${reason}The autosaved project could not be set aside: ${error.message}`, "warn");
  }
}
function currentViewState() {
  return {
    selection: state.selection,
    selectedNode: state.selectedNode,
    selectedForce: state.selectedForce,
    selectedJoint: state.selectedJoint,
    measureNode: state.measureNode,
    signal: state.signal,
    frame: state.frame,
    camera: view?.camera.position.toArray(),
    target: view?.controls.target.toArray(),
    trails: Boolean(state.trails),
    trailWindow: Number($("trailWindow").value) || 0,
    trailPoint: $("trailPoint").value,
    glyphs: state.glyphs !== false,
    ...(state.studySetup ? { study: { ...state.studySetup, ...(activeStudy() ? { response: resultSignal().title } : {}) } } : {}),
    ...(state.trailPreset && $("trailBodies").value === "preset" ? { trailBodies: state.trailPreset } : {}),
  };
}
function validSavedResult(result) {
  if (
    !result ||
    !["MBDyn", "Reference preview"].includes(result.source) ||
    !fields[result.model?.kind] ||
    !Array.isArray(result.samples) ||
    !result.samples.length ||
    result.samples.length > 2001
  )
    return false;
  const source = ["source-example", "planar-assembly", "spatial-assembly"].includes(result.model.kind) ? visualInfo(result.model) : null;
  if (["source-example", "planar-assembly", "spatial-assembly"].includes(result.model.kind) && !source) return false;
  const firstReactions=result.samples[0]?.jointReactions;
  if(firstReactions!==undefined && (result.source!=="MBDyn" || result.model.kind!=="spatial-assembly" || !Array.isArray(firstReactions) || firstReactions.length>result.model.joints.length || new Set(firstReactions.map(item=>item?.id)).size!==firstReactions.length || !firstReactions.every(item=>result.model.joints.some(joint=>joint.id===item?.id)))) return false;
  let previous = -Infinity;
  return result.samples.every((sample) => {
    if (!Number.isFinite(sample.time) || sample.time <= previous) return false;
    previous = sample.time;
    if(firstReactions===undefined ? sample.jointReactions!==undefined : !Array.isArray(sample.jointReactions) || sample.jointReactions.length!==firstReactions.length || !firstReactions.every(expected=>{const matches=sample.jointReactions.filter(item=>item?.id===expected.id);return matches.length===1 && ["force","moment"].every(key=>matches[0][key] && ["x","y","z"].every(axis=>Number.isFinite(matches[0][key][axis])));} )) return false;
    if (source)
      return (
        Array.isArray(sample.nodes) &&
        sample.nodes.length === source.nodes.length &&
        source.nodes.every((expected) => {
          const node = sample.nodes.find((item) => item.id === expected.id);
          return (
            node &&
            [
              "x",
              "y",
              "z",
              "rx",
              "ry",
              "rz",
              "vx",
              "vy",
              "vz",
              "wx",
              "wy",
              "wz",
            ].every((key) => Number.isFinite(node[key])) &&
            (result.model.kind !== "planar-assembly" || Number.isFinite(node.angleDeg))
          );
        }) &&
        (!(result.model.forces || []).length || (
          Array.isArray(sample.forces) && sample.forces.length === result.model.forces.length &&
          result.model.forces.every(expected => {
            const force=sample.forces.find(item=>item.id===expected.id);
            return force && ["length","extension","rate","force",...(expected.type==="oleo-strut"?["gasPressure","gasForce","hydraulicForce","stopForce"]:[])].every(key=>Number.isFinite(force[key]));
          }) && ["elasticEnergy","dampingPower","dissipatedEnergy"].every(key=>Number.isFinite(sample[key]))
        )) &&
        (!(result.model.joints || []).some(joint=>joint.type==="prismatic") || (
          Array.isArray(sample.sliders) && sample.sliders.length === result.model.joints.filter(joint=>joint.type==="prismatic").length &&
          result.model.joints.filter(joint=>joint.type==="prismatic").every(expected=>{
            const slider=sample.sliders.find(item=>item.id===expected.id);
            return slider && ["position","velocity","transverse","transverseVelocity","angle","angularVelocity"].every(key=>Number.isFinite(slider[key]));
          }) && ["jointAngularError","jointAngularVelocityError"].every(key=>Number.isFinite(sample[key]))
        )) && (!(result.model.joints || []).some(joint=>joint.type==="cylindrical") || (
          Array.isArray(sample.cylinders) && sample.cylinders.length === result.model.joints.filter(joint=>joint.type==="cylindrical").length &&
          result.model.joints.filter(joint=>joint.type==="cylindrical").every(expected=>{const cylinder=sample.cylinders.find(item=>item.id===expected.id);return cylinder && ["position","velocity","angle","angularVelocity","transverse","transverseVelocity","angularError","angularVelocityError"].every(key=>Number.isFinite(cylinder[key]));})
        )) && (!(result.model.loads || []).length || (["loadPower","appliedWork"].every(key=>Number.isFinite(sample[key])) && (result.model.kind !== "spatial-assembly" || (Array.isArray(sample.loadStates) && sample.loadStates.length === result.model.loads.length && result.model.loads.every(expected=>{const item=sample.loadStates.find(item=>item.id===expected.id);return item && Number.isFinite(item.power) && ["force","torque","moment"].every(key=>item[key] && ["x","y","z"].every(axis=>Number.isFinite(item[key][axis])));}))))) &&
        (!(result.model.rotationalElements || []).length || (Array.isArray(sample.rotationalStates) && sample.rotationalStates.length === result.model.rotationalElements.length && result.model.rotationalElements.every(expected=>{const item=sample.rotationalStates.find(item=>item.id===expected.id);return item && ["angle","velocity","torque"].every(key=>Number.isFinite(item[key]));}))) &&
        (!(result.model.jointTorques || []).length || (Array.isArray(sample.actuationStates) && sample.actuationStates.length === result.model.jointTorques.length && result.model.jointTorques.every(expected=>{const item=sample.actuationStates.find(item=>item.id===expected.id);return item && ["torque","power"].every(key=>Number.isFinite(item[key]));}) && ["actuationPower","actuationWork"].every(key=>Number.isFinite(sample[key])))) &&
        (!(result.model.contacts || []).length || (Array.isArray(sample.contactStates) && sample.contactStates.length === result.model.contacts.length && result.model.contacts.every(expected=>{const item=sample.contactStates.find(item=>item.id===expected.id);return item && ["gap","penetration","force","power","energy",...(expected.damping>0?["dampingPower","dissipatedEnergy"]:[]),...(expected.friction>0?["frictionForce","slip","frictionPower","frictionEnergy"]:[])].every(key=>Number.isFinite(item[key])) && (!(expected.friction>0) || ["x","y","z"].every(axis=>Number.isFinite(item.frictionVector?.[axis])));}))) &&
        (!(result.model.jointForces || []).length || (Array.isArray(sample.jointForceStates) && sample.jointForceStates.length === result.model.jointForces.length && result.model.jointForces.every(expected=>{const item=sample.jointForceStates.find(item=>item.id===expected.id);return item && ["force","power"].every(key=>Number.isFinite(item[key]));}) && ["jointForcePower","jointForceWork"].every(key=>Number.isFinite(sample[key]))))
      );
    const keys = ["x", "y", "z", "angle", "velocity", "value"];
    if (result.model.kind === "double-pendulum")
      keys.push("x2", "y2", "z2", "angle2", "velocity2", "value2");
    return keys.every((key) => Number.isFinite(sample[key]));
  });
}
function clearResult() {
  state.result = null;
  state.resultSignature = null;
  state.playing = false;
  state.frame = 0;
  for (const id of ["playButton", "rewindButton", "frameBackButton", "frameForwardButton", "timeSlider", "csvButton", "clearResultsButton", "pinTraceButton", "plotSvgButton", "plotPngButton", "compareButton"])
    $(id).disabled = true;
  plotGeometry = null;
  $("plotStats").replaceChildren();
  $("resultsBadge").textContent = "Empty";
  $("resultsBadge").className = "badge";
  view?.setTrails(null);
  $("nodeSelect").hidden = true;
  $("forceSelect").hidden = true;
  $("jointSelect").hidden = true;
  $("signalSelect").hidden = true;
  $("resultSource").textContent = "No run yet";
  $("resultSource").className = "source-badge";
  $("samplesMetric").textContent = "—";
  $("timeOutput").textContent = "0.000 s";
  $("plot").innerHTML =
    `<div class="empty-plot">${icon("wave")}<strong>No results yet</strong><span>Run the model in the Solve workspace to plot its response.</span></div>`;
}
$("clearResultsButton").onclick = () => {
  clearResult(); markNativeDirty();
  notice("Loaded result cleared. Generated run files remain in the runs folder.");
};
function applyDisplayPreset(preset) {
  state.trailPreset = Array.isArray(preset?.trailBodies) && preset.trailBodies.every((id) => typeof id === "string") ? preset.trailBodies : null;
  $("trailBodies").querySelector('[value="preset"]').hidden = !state.trailPreset;
  $("trailBodies").value = state.trailPreset ? "preset" : "all";
  const window = Number(preset?.trailWindow);
  if (Number.isFinite(window) && window >= 0 && window <= 60) {
    if (![...$("trailWindow").options].some((option) => Number(option.value) === window)) {
      const option = document.createElement("option");
      option.value = String(window);
      option.textContent = `Last ${window} s`;
      $("trailWindow").append(option);
    }
    $("trailWindow").value = [...$("trailWindow").options].find((option) => Number(option.value) === window).value;
  } else $("trailWindow").value = "0";
  $("trailPoint").value = preset?.trailPoint === "tip" ? "tip" : "auto";
  if (typeof preset?.trails === "boolean") setTrails(preset.trails);
  setGlyphs(preset?.glyphs !== false);
  state.studySetup = validStudySetup(preset?.study);
  studySetupPending = Boolean(state.studySetup);
}
// Keep the previous document and its live reference geometry until the new view is complete.
function commitOpenedProject(project, reference, step) {
  const keys = ["model","selection","history","future","result","resultSignature","validation","selectedNode","selectedForce","selectedJoint","measureNode","reference","step","playing","frame","signal"];
  const previous = Object.fromEntries(keys.map(key=>[key,state[key]]));
  const previousRevision=projectRevision, previousDirty=browserDirty, previousApplying=applyingNativeProject;
  const camera=view ? {position:view.camera.position.clone(),target:view.controls.target.clone(),isolated:view.isolatedReference} : null;
  let stored, storageAvailable=false;
  try {stored=localStorage.getItem("mbdyn-studio-project");storageAvailable=true;} catch {}
  applyingNativeProject=true;
  try {
    // A binding from the old document may be invalid in the new body graph.
    state.step=null;
    state.result=null;
    if(view)view.stepAsset=null;
    applyModel(project.model,false);
    replaceReference(reference,false,false);
    replaceStep(step,false);
    if (project.result) {
      state.result={...project.result,restored:true};
      state.resultSignature=project.result.model ? JSON.stringify(project.result.model) : null;
      state.selectedNode=project.view?.selectedNode ?? state.selectedNode;
      state.selectedForce=project.view?.selectedForce ?? state.selectedForce;
      state.selectedJoint=project.view?.selectedJoint ?? state.selectedJoint;
      state.measureNode=project.view?.measureNode ?? state.measureNode;
      state.signal=Number.isInteger(project.view?.signal) ? Math.max(0,project.view.signal) : 0;
      state.frame=Number.isInteger(project.view?.frame) ? Math.max(0,Math.min(project.view.frame,project.result.samples.length-1)) : 0;
      renderResult();setFrame(state.frame);
    } else {
      clearResult();
      if (Number.isInteger(project.view?.signal)) state.signal = Math.max(0, project.view.signal);
      for (const key of ["selectedNode", "selectedForce", "selectedJoint"]) if (typeof project.view?.[key] === "string") state[key] = project.view[key];
    }
    applyDisplayPreset(project.view);
    state.overlays = [];
    state.compareRun = null;
    renderCompareControls();
    if(typeof project.view?.selection === "string" && document.querySelector(`[data-entity="${CSS.escape(project.view.selection)}"]`)) select(project.view.selection);
    if(view && [project.view?.camera,project.view?.target].every(point=>Array.isArray(point) && point.length===3 && point.every(value=>Number.isFinite(value) && Math.abs(value)<1e6))) {
      view.camera.position.fromArray(project.view.camera);view.controls.target.fromArray(project.view.target);view.controls.update();
    }
    state.history=[];state.future=[];updateHistoryButtons();
    projectRevision++;
    browserDirty=false;
  } catch (error) {
    clearTimeout(validationTimer);
    Object.assign(state,previous);
    projectRevision=previousRevision;browserDirty=previousDirty;
    if(storageAvailable)try {if(stored===null)localStorage.removeItem("mbdyn-studio-project");else localStorage.setItem("mbdyn-studio-project",stored);} catch {}
    let restoreError;
    try {
      if(view){view.stepAsset=previous.step;view.setModel(previous.model,false,visualInfo(previous.model));}
      replaceReference(previous.reference,false,false);
      if(view)view.isolateReference(camera.isolated);
      renderMetadata();renderTree();renderProperties();renderStepControls();updateHistoryButtons();
      if(previous.result){renderResult();setFrame(previous.frame);}else clearResult();
      if(view && camera){view.camera.position.copy(camera.position);view.controls.target.copy(camera.target);view.controls.update();view.setSelection(previous.selection);}
    } catch (failure) {restoreError=failure;}
    if(restoreError)throw new Error(`${error.message} The previous document is retained, but its view could not be fully restored: ${restoreError.message}`);
    throw error;
  } finally {applyingNativeProject=previousApplying;}
  if(previous.reference && previous.reference !== reference) {try {previous.reference.dispose();} catch(error) {console.error("Could not release the previous reference geometry:",error);}}
}
async function confirmNativeOpen(token) {
  for (;;) {
    try {
      const confirmation=await nativeDesktop.call("finalize-open",{token},2000);
      if (confirmation.token !== token || typeof confirmation.dirtyRevision !== "string" || !/^[0-9]+$/.test(confirmation.dirtyRevision)) throw new Error("The desktop returned an invalid project confirmation.");
      return confirmation.dirtyRevision;
    } catch (error) {
      notice(`The opened project is visible, but its save identity is not confirmed: ${error.message} Retrying; your edits are kept.`,"warn");
      status("Confirming project open · saving and running are paused");
      await new Promise(resolve=>setTimeout(resolve,1000));
    }
  }
}
async function confirmNativeClean(token, dirtyRevision, openedRevision) {
  for (;;) {
    if (projectRevision !== openedRevision) return false;
    const focus=document.activeElement;
    if (focus && (focus.matches("input, textarea, select") || focus.isContentEditable)) {
      notice("Finish editing the active field to confirm the opened project; your input is kept.","warn");
      await new Promise(resolve=>setTimeout(resolve,250));
      continue;
    }
    // Prevent a pending STEP conversion from applying while the clean request is in flight.
    stepLoad++;referenceLoad++;
    const elements=[...document.body.children].filter(element=>element.id!=="notice" && element.tagName!=="SCRIPT");
    const previous=elements.map(element=>element.inert);
    elements.forEach(element=>{element.inert=true;});
    try {
      if (projectRevision !== openedRevision) return false;
      for (;;) {
        try {
          const response=await nativeDesktop.call("clean-open",{token,dirtyRevision},2000);
          if (response.token !== token || response.dirtyRevision !== dirtyRevision || typeof response.clean !== "boolean") throw new Error("The desktop returned an invalid clean confirmation.");
          return response.clean;
        } catch(error) {
          notice(`The project is open, but its clean state is not confirmed: ${error.message} Retrying without discarding input.`,"warn");
          status("Confirming project open · editing and saving are paused");
          await new Promise(resolve=>setTimeout(resolve,1000));
        }
      }
    } finally {
      elements.forEach((element,index)=>{element.inert=previous[index];});
      if(focus?.isConnected && typeof focus.focus === "function")focus.focus({preventScroll:true});
    }
  }
}
/** Open a project chosen in a native dialog, or with op "recovery-open" the autosaved one. */
async function nativeOpen(op = "open") {
  if (state.opening || state.saving || state.busy) return;
  const recovering = op === "recovery-open";
  state.opening = true;
  const revision = projectRevision;
  let accepted = false;
  let acceptedToken;
  let candidate;
  let nextReference;
  let nextStep;
  try {
    candidate = await nativeDesktop.call(op);
    if (candidate.cancelled) {
      if (recovering) await setRecoveryAside();
      return;
    }
    const project = candidate.project;
    if (!project?.model || !fields[project.model.kind])
      throw new Error("This project uses a model family this app cannot open.");
    const check = await checkModel(project.model);
    if (!check.valid)
      throw new Error((check.issues || []).map((i) => i.message).join(" "));
    const result = project.result;
    if (result && !validSavedResult(result))
      throw new Error(
        "The saved result samples are incomplete, malformed or unsupported.",
      );
    if (project.assets && (typeof project.assets !== "object" || Object.keys(project.assets).some(key => !["reference","step"].includes(key)))) throw new Error("The project contains unsupported visual assets.");
    const token = ++referenceLoad;
    const stepToken = ++stepLoad;
    nextReference = project.assets?.reference ? await restoreReferenceGeometry(project.assets.reference) : null;
    nextStep = project.assets?.step ? await restoreStepAsset(project.assets.step) : null;
    validateStepForModel(nextStep,project.model);
    if (token !== referenceLoad || stepToken !== stepLoad) throw new Error("A newer geometry operation started; reopen the project to retry.");
    if (revision !== projectRevision) throw new Error("The current project changed while the file was loading; your edits were kept. Open it again to retry.");
    const acceptance=await nativeDesktop.call("accept-open");
    acceptedToken=acceptance.token;
    if (typeof acceptedToken !== "string" || !/^[1-9][0-9]*$/.test(acceptedToken)) throw new Error("The desktop did not return a valid project transaction identity.");
    accepted = true;
    if (revision !== projectRevision) {
      await nativeDesktop.call("rollback-open",{token:acceptedToken});
      accepted = false;
      throw new Error("The current project changed while the file was opening; your edits were kept. Open it again to retry.");
    }
    commitOpenedProject(project,nextReference,nextStep);
    nextReference = null;
    accepted = false;
    const openedRevision=projectRevision;
    status("Confirming project open · saving and running are paused");
    const dirtyRevision=await confirmNativeOpen(acceptedToken);
    if (recovering) {
      // Recovered work is unsaved by definition: skip the clean handshake and keep it dirty.
      try { await nativeDesktop.call("recovery-adopted", {}, 10000); }
      catch (error) { notice(`Recovered, but autosave stays paused for this session: ${error.message}`, "warn"); }
      markNativeDirty();
      $("dirtyMark").title = "Unsaved changes";
      notice(`Recovered the work autosaved at ${new Date(candidate.savedAt).toLocaleTimeString()}. It is unsaved: Save asks where to write it${candidate.path ? `, starting at ${candidate.path}` : ""}.`);
      status("Recovered autosaved project · unsaved");
      return;
    }
    const clean=projectRevision === openedRevision ? await confirmNativeClean(acceptedToken,dirtyRevision,openedRevision) : false;
    const edited=projectRevision !== openedRevision || !clean;
    $("dirtyMark").title = edited ? "Unsaved changes" : "Saved project";
    notice((edited
      ? "Project opened. Edits made while confirmation was pending remain unsaved."
      : result ? "Project opened. The saved response is labelled with its recorded source." : "Project opened and validated.") + (Object.keys(state.step?.metadata.unverifiedBindings || {}).length ? " Review saved STEP attachments before using them." : ""));
    status(`Project opened · ${candidate.path}${edited ? " · unsaved edits" : ""}`);
  } catch (error) {
    applyingNativeProject = false;
    nextReference?.dispose();
    if (accepted) {
      try { await nativeDesktop.call("rollback-open",{token:acceptedToken}); } catch { nativeDesktop.notify("dirty"); }
    } else if (candidate && !candidate.cancelled) nativeDesktop.notify("discard-open");
    if (recovering) await setRecoveryAside(`The autosaved project could not be opened: ${error.message} `);
    else notice(`Project was not opened: ${error.message}`, "error");
  } finally {
    state.opening = false;
  }
}
if (nativeDesktop) $("saveAsButton").hidden = false;
$("saveAsButton").onclick = () => nativeSave(true);
$("saveButton").onclick = async () => {
  if (nativeDesktop) return nativeSave(false);
  try {
  const revision = projectRevision;
  const model = structuredClone(state.model), result = savedResult() ? structuredClone(savedResult()) : null, reference = state.reference, step = state.step ? structuredClone(state.step.metadata) : null;
  if (result?.source === "MBDyn" && !result.csvText && result.files?.csv) {
    if (!/^\/api\/runs\/[0-9a-f]{32}\/results\.csv$/.test(result.files.csv)) throw new Error("The result contains an unsupported CSV location.");
    const response = await fetch(result.files.csv);
    if (!response.ok) throw new Error("The full solver CSV is unavailable; the project was not exported.");
    result.csvText = await response.text();
  }
  const contents = JSON.stringify({ format: "mbdyn-studio/1", model, result, view: currentViewState(), assets:reference || step ? {...(reference ? {reference:reference.metadata} : {}), ...(step ? {step} : {})} : null }, null, 2);
  if (new Blob([contents]).size > 32 * 1024 * 1024) throw new Error("Project exceeds 32 MiB; export large results or reference geometry separately.");
  download(`${model.kind}.mbdyn-studio`, contents, "application/json");
  if (revision === projectRevision) browserDirty = false;
  status("Project JSON exported");
  } catch(error) {notice(`Project was not exported: ${error.message}`,"error");}
};
$("importButton").onclick = () =>
  nativeDesktop ? nativeOpen() : $("projectFile").click();
async function openProjectText(readText, size) {
  const revision = projectRevision;
  let nextReference;
  let nextStep;
  try {
    if (browserDirty && !window.confirm("Opening this project replaces the current unsaved model, geometry and results. Export the current project first if you need to keep them. Continue?")) return false;
    if (size > 32 * 1024 * 1024) throw new Error("Project file exceeds 32 MiB.");
    const project = JSON.parse(await readText());
    if (project.format !== "mbdyn-studio/1" || !project.model)
      throw new Error("Unsupported project format. Expected mbdyn-studio/1.");
    const check = await checkModel(project.model);
    if (!check.valid)
      throw new Error((check.issues || []).map((i) => i.message).join(" "));
    if (project.result && !validSavedResult(project.result)) throw new Error("The saved result is incomplete or unsupported.");
    if (project.assets && (typeof project.assets !== "object" || Object.keys(project.assets).some(key => !["reference","step"].includes(key)))) throw new Error("The project contains unsupported visual assets.");
    const token = ++referenceLoad;
    const stepToken = ++stepLoad;
    nextReference = project.assets?.reference ? await restoreReferenceGeometry(project.assets.reference) : null;
    nextStep = project.assets?.step ? await restoreStepAsset(project.assets.step) : null;
    validateStepForModel(nextStep,project.model);
    if (token !== referenceLoad || stepToken !== stepLoad) throw new Error("A newer geometry operation started; reopen the project to retry.");
    if (revision !== projectRevision) throw new Error("The current project changed while the file was loading; your edits were kept. Open it again to retry.");
    commitOpenedProject(project,nextReference,nextStep);
    nextReference = null;
    switchStep(state.result ? "results" : "model");
    notice("Project imported and validated." + (Object.keys(state.step?.metadata.unverifiedBindings || {}).length ? " Review saved STEP attachments before using them." : ""));
    return true;
  } catch (error) {
    nextReference?.dispose();
    notice(`Project was not opened: ${error.message}`, "error");
    return false;
  }
}
$("projectFile").onchange = async (e) => {
  const file = e.target.files[0];
  try {
    if (file) await openProjectText(() => file.text(), file.size);
  } finally {
    e.target.value = "";
  }
};
// A new project starts as a 3D assembly with one body; STEP parts, bodies and joints are added from there.
const NEW_ASSEMBLY = {
  format: "mbdyn-studio/1",
  model: {
    kind: "spatial-assembly", name: "Untitled 3D assembly",
    parameters: { gravity: { x: 0, y: 0, z: -9.81 } }, simulation: { duration: 1, step: 0.001 },
    bodies: [{ id: "body1", name: "Body 1", mass: 1, inertia: { xx: 0.1, yy: 0.1, zz: 0.1 }, pose: { x: 0, y: 0, z: 0, rx: 0, ry: 0, rz: 0 }, velocity: { vx: 0, vy: 0, vz: 0, wx: 0, wy: 0, wz: 0 } }],
    joints: [],
  },
};
async function newAssembly() {
  if (state.busy || state.saving || state.opening) return;
  const text = JSON.stringify(NEW_ASSEMBLY);
  if (await openProjectText(async () => text, text.length)) {
    browserDirty = false;
    switchStep("model");
    notice("New 3D assembly. Import STEP parts, then add bodies, joints and loads in Pre-processing.");
  }
}
$("newButton").onclick = newAssembly;
async function openFeatured(study) {
  if (state.busy || state.saving || state.opening) return;
  notice(`Loading ${study.title} and converting its CAD geometry…`, "warn");
  const response = await fetch(`/api/featured/${encodeURIComponent(study.id)}`);
  if (!response.ok) return notice(`The featured study could not be loaded (${response.status}).`, "error");
  const text = await response.text();
  if (await openProjectText(async () => text, text.length)) {
    $("examplesDialog").close();
    browserDirty = false;
    notice(`${study.title} loaded. ${study.next || "Open Solve and run MBDyn, then explore the motion in Post-processing."}`);
  }
}
$("deckButton").onclick = async () => {
  try {
    const result = await api("deck", state.model);
    if (!result.valid) {
      showIssues(result.issues || []);
      throw new Error(
        "Correct model validation errors before exporting a solver deck.",
      );
    }
    showDocument("Generated MBDyn input", result.deck, result.filename);
  } catch (error) {
    notice(error.message, "error");
  }
};
$("logButton").onclick = () => {
  const record = state.lastFailure || state.result;
  showDocument(
    record?.source === "MBDyn" ? "MBDyn run log" : "Run information",
    record?.log ||
      record?.error ||
      "No MBDyn run log is loaded. Reference previews are independent calculations and do not launch MBDyn.",
    record?.log ? "solver.log" : null,
  );
};
$("documentDownload").onclick = () => {
  if (pendingDownload) download(pendingDownload.name, pendingDownload.text);
};
$("helpButton").onclick = async () => {
  const guide = sourceInfo()
    ? "open-source-examples.md"
    : state.model.kind === "spatial-assembly" ? "spatial-assembly.md"
    : state.model.kind === "planar-assembly" ? "planar-assembly.md"
    : industry[state.model.kind]?.tutorial;
  if (!guide) return showGuide();
  try {
    const response = await fetch(`/docs/${guide}`);
    if (!response.ok) throw new Error("The example guide could not be loaded.");
    showDocument(
      `${state.model.name} · engineering guide`,
      await response.text(),
      guide,
    );
  } catch (error) {
    notice(error.message, "error");
  }
};
$("examplesButton").onclick = () => $("examplesDialog").showModal();
document
  .querySelectorAll("[data-close]")
  .forEach((b) => (b.onclick = () => b.closest("dialog").close()));
document
  .querySelectorAll("[data-step]")
  .forEach((b) => (b.onclick = () => switchStep(b.dataset.step)));
document.querySelectorAll("[data-view]").forEach(
  (b) =>
    (b.onclick = () => {
      const scene = b.dataset.view === "scene";
      document
        .querySelectorAll("[data-view]")
        .forEach((x) => x.classList.toggle("active", x === b));
      $("topology").hidden = scene;
      $("canvasMount").style.visibility = scene ? "visible" : "hidden";
      view?.showLabels(scene);
    }),
);
$("resetViewButton").onclick = () => view?.reset();
$("solveRunButton").onclick = () => run();
function setPresentation(on) {
  document.body.classList.toggle("present", on);
  $("presentButton").setAttribute("aria-pressed", String(on));
  if (on && state.result && workspace !== "results") switchStep("results");
  requestAnimationFrame(() => { view?.resize(); if (state.result) drawPlot(); });
}
$("presentButton").onclick = () => setPresentation(!document.body.classList.contains("present"));
$("presentExit").onclick = () => setPresentation(false);
$("frameBackButton").onclick = () => { state.playing = false; setFrame(state.frame - 1); };
$("frameForwardButton").onclick = () => { state.playing = false; setFrame(state.frame + 1); };
$("loopButton").onclick = () => {
  state.loop = !state.loop;
  $("loopButton").setAttribute("aria-pressed", String(state.loop));
};
function trailOptions() {
  const choice = $("trailBodies").value;
  const bodies = choice === "preset" ? state.trailPreset : choice === "selected" ? [state.selection === "body" ? state.result?.model?.bodies?.[0]?.id : state.selection.replace(/^node-/, "")] : null;
  return { window: Number($("trailWindow").value) || 0, bodies, point: $("trailPoint").value };
}
function refreshTrails() {
  const show = state.trails && workspace === "results" && state.result && !stale();
  view?.setTrails(show ? state.result : null, trailOptions());
  if (show) view?.setTrailFrame(state.frame);
}
function setTrails(on) {
  state.trails = on;
  $("trailsButton").setAttribute("aria-pressed", String(on));
  $("trailsToggle").checked = on;
  if (on && workspace !== "results" && state.result) switchStep("results");
  refreshTrails();
}
$("trailWindow").onchange = refreshTrails;
$("trailBodies").onchange = refreshTrails;
$("trailPoint").onchange = refreshTrails;
$("trailsButton").onclick = () => setTrails(!state.trails);
$("trailsToggle").onchange = (event) => setTrails(event.target.checked);
$("followToggle").onchange = (event) => { view?.setFollow(event.target.checked ? state.selection : null); };
$("labelsButton").onclick = () => {
  const show = $("labelsButton").getAttribute("aria-pressed") !== "true";
  $("labelsButton").setAttribute("aria-pressed", String(show));
  $("viewport").classList.toggle("hide-labels", !show);
};
$("glyphsButton").onclick = () => setGlyphs(state.glyphs === false);
$("gridButton").onclick = () => {
  const next = $("gridButton").getAttribute("aria-pressed") !== "true";
  $("gridButton").setAttribute("aria-pressed", String(next));
  view?.setGrid(next);
};
$("themeButton").onclick = () => {
  const dark = document.documentElement.dataset.theme !== "dark";
  document.documentElement.dataset.theme = dark ? "dark" : "light";
  try {
    localStorage.setItem("mbdyn-studio-theme", dark ? "dark" : "light");
  } catch {}
  view?.setTheme(dark);
};
$("playButton").onclick = () => {
  if (stale()) {
    notice("Run the edited model again before playing its response.", "warn");
    return;
  }
  state.playing = !state.playing;
  playTime = state.result.samples[state.frame].time;
};
$("rewindButton").onclick = () => {
  state.playing = false;
  playTime = 0;
  setFrame(0);
};
$("timeSlider").oninput = (e) => {
  state.playing = false;
  setFrame(Number(e.target.value));
};
$("speedButton").onclick = () => {
  const speeds = [0.1, 0.25, 0.5, 1, 2];
  state.speed = speeds[(speeds.indexOf(state.speed) + 1) % speeds.length];
  $("speedButton").textContent = `${state.speed}×`;
};
$("signalSelect").onchange = (event) => {
  state.signal = Number(event.target.value);
  renderResult();
};
$("nodeSelect").onchange = (event) => {
  state.selectedNode = event.target.value;
  const source = visualInfo();
  if (source && !stale()) {
    const index = source.nodes.findIndex(
      (node) => String(node.id) === String(state.selectedNode),
    );
    if (index >= 0)
      return select(index ? `node-${source.nodes[index].id}` : "body");
  }
  renderResult();
};
$("forceSelect").onchange = event => {state.selectedForce=event.target.value;renderResult();};
$("jointSelect").onchange = event => {state.selectedJoint=event.target.value;renderResult();};
$("csvButton").onclick = async () => {
  if (!state.result) return;
  const r = state.result;
  const kind = r.model?.kind || state.model.kind;
  const angular = ["pendulum", "double-pendulum", "gear-deployment"].includes(
    kind,
  );
  const names = {
    ...industryCsvUnits,
    time: "time_s",
    id: "node_id",
    x: "x_m",
    y: "y_m",
    z: "z_m",
    rx: "euler123_x_deg",
    ry: "euler123_y_deg",
    rz: "euler123_z_deg",
    vx: "velocity_x_m_s",
    vy: "velocity_y_m_s",
    vz: "velocity_z_m_s",
    wx: "angular_velocity_x_rad_s",
    wy: "angular_velocity_y_rad_s",
    wz: "angular_velocity_z_rad_s",
    angle: "angle_deg",
    velocity: angular ? "angular_velocity_rad_s" : "velocity_m_s",
    value: angular ? "value_deg" : "value_m",
    x2: "x2_m",
    y2: "y2_m",
    z2: "z2_m",
    angle2: "angle2_deg",
    velocity2: "angular_velocity2_rad_s",
    value2: "value2_deg",
  };
  try {
    let rows, keys;
    if (r.source === "MBDyn" && (r.csvText || r.files?.csv)) {
      let text = r.csvText;
      if (!text) {
        if (!/^\/api\/runs\/[0-9a-f]{32}\/results\.csv$/.test(r.files.csv))
          throw new Error(
            "The saved result contains an unsupported CSV location.",
          );
        const response = await fetch(r.files.csv);
        if (!response.ok)
          throw new Error("Could not download the full solver CSV.");
        text = await response.text();
      }
      const lines = text.trim().split(/\r?\n/);
      keys = lines[0].split(",");
      rows = lines.slice(1);
    } else {
      keys = Object.keys(r.samples[0]);
      rows = r.samples.map((s) =>
        keys.map((key) => (Number.isFinite(s[key]) ? s[key] : "")).join(","),
      );
    }
    const data = [
      `# source: ${r.source}`,
      `# model: ${JSON.stringify(r.model || {})}`,
      keys.map((key) => names[key] || key).join(","),
      ...rows,
    ].join("\n");
    download(
      `${kind}-${r.source === "MBDyn" ? "mbdyn" : "reference"}.csv`,
      data,
      "text/csv",
    );
  } catch (error) {
    notice(error.message, "error");
  }
};
document.addEventListener("keydown", (e) => {
  if (
    e.target.closest("input,textarea") ||
    document.querySelector("dialog[open]")
  )
    return;
  if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "z") {
    e.preventDefault();
    $(e.shiftKey ? "redoButton" : "undoButton").click();
    return;
  }
  if ((e.ctrlKey || e.metaKey) && ["s", "o"].includes(e.key.toLowerCase())) {
    e.preventDefault();
    $(e.key.toLowerCase() === "s" ? "saveButton" : "importButton").click();
    return;
  }
  if (e.target.closest("select,button") && [" ", "Enter"].includes(e.key)) return;
  if (e.ctrlKey || e.metaKey || e.altKey) return;
  if (e.key === "F5") { e.preventDefault(); if (!state.busy) run(); return; }
  if (["1", "2", "3"].includes(e.key)) { switchStep(["model", "simulate", "results"][Number(e.key) - 1]); return; }
  if (e.key.toLowerCase() === "f") { view?.reset(); return; }
  if (e.key.toLowerCase() === "p") { $("presentButton").click(); return; }
  if (e.key === "Escape" && picking) { stopPick(); return; }
  if (e.key === "Escape" && view?.dragging) { view.cancelDrag(); return; }
  if (e.key.toLowerCase() === "m" && state.step) { $("measureViewButton").click(); return; }
  if (e.key === "Escape" && document.body.classList.contains("present")) { setPresentation(false); return; }
  if (!state.result || workspace !== "results") return;
  if (e.key === " ") { e.preventDefault(); $("playButton").click(); }
  else if (e.key === "ArrowLeft") { e.preventDefault(); $("frameBackButton").click(); }
  else if (e.key === "ArrowRight") { e.preventDefault(); $("frameForwardButton").click(); }
  else if (e.key === "Home") { e.preventDefault(); $("rewindButton").click(); }
  else if (e.key === "End") { e.preventDefault(); state.playing = false; setFrame(state.result.samples.length - 1); }
});
new ResizeObserver(() => {
  if (state.result) drawPlot();
}).observe($("plot"));

async function init() {
  try {
    savedTheme = localStorage.getItem("mbdyn-studio-theme");
    if (savedTheme) document.documentElement.dataset.theme = savedTheme;
  } catch {}
  try {
    view = new MechanismView($("canvasMount"), entity => {
      if (entity.startsWith("step-part-")) {
        renderStepControls();
        $("stepPart").value = entity.slice("step-part-".length);
        $("stepPart").dispatchEvent(new Event("change"));
        $("stepDialog").showModal();
      } else select(entity);
    }, showHover);
    view.setDragMode(jointDrag);
  } catch (error) {
    const box = document.createElement("div");
    box.className = "error-box";
    box.textContent = `3D rendering is unavailable: ${error.message}. The model editor, deck export and result charts remain usable.`;
    $("canvasMount").append(box);
  }
  renderMetadata();
  renderTree();
  renderProperties();
  view?.setModel(state.model, true);
  try {
    const [solver, examples, sourceExamples, featured] = await Promise.all([
      api("status"),
      api("examples"),
      api("source-examples").catch(() => ({ examples: [] })),
      api("featured").catch(() => ({ studies: [] })),
    ]);
    state.featured = featured.studies;
    state.solver = solver.solver;
    state.examples = examples.examples;
    state.sourceExamples = sourceExamples.examples;
    renderExamples();
    $("solverStatus").textContent = solver.solver.available
      ? "MBDyn ready"
      : "MBDyn not configured";
    $("solverDot").className =
      `status-dot ${solver.solver.available ? "green" : ""}`;
    $("solverDetail").textContent = solver.solver.available
      ? solver.solver.version || "Local solver"
      : "Reference previews and deck export available";
    $("solverChip").textContent = solver.solver.available ? `MBDyn ${solver.solver.version || "ready"}` : "MBDyn not configured";
    $("solverChip").className = `status-chip ${solver.solver.available ? "ok" : ""}`;
    renderChecklist();
    if (!solver.solver.available)
      notice(
        "MBDyn is unavailable. You can edit models, export decks and use Reference preview. Run simulation will report the solver configuration error.",
        "warn",
      );
    let recovered;
    try {
      const saved = JSON.parse(
        localStorage.getItem("mbdyn-studio-project") || "null",
      );
      if (saved?.format === "mbdyn-studio/1") {
        const check = await checkModel(saved.model);
        if (check.valid) recovered = saved.model;
      }
    } catch {}
    if (recovered) applyModel(recovered, false);
    else await validate(false);
    if (nativeDesktop) await offerRecovery();
  } catch (error) {
    notice(
      `Cannot connect to the local workspace: ${error.message}. Start backend/server.py, then reload.`,
      "error",
    );
    $("solverStatus").textContent = "Backend unavailable";
    $("solverDetail").textContent = "Start the local server";
  }
  requestAnimationFrame(animate);
  try {
    await setupTour({
      newAssembly,
      importWheelEnd: async () => {
        if (await loadSuspensionParts(/(Knuckle_Left Knuckle|Hub|Front Tyre)\.step$/)) notice("Knuckle, hub and tyre STEP parts loaded. Attach each part to its body in STEP parts.");
      },
      openStudy: (id) => { const study = state.featured?.find((item) => item.id === id); if (study) openFeatured(study); },
      openFeaturedStudies: () => { $("examplesButton").click(); },
    });
  } catch (error) {
    notice(`The guided tour could not start: ${error.message}. The model workspace remains available.`, "warn");
  }
}
setupAgent({getModel:()=>state.model, getSignature:signature, getBindings:()=>state.step?.metadata.bindings || {}, checkModel, applyModel, run, isBusy:()=>state.busy || state.saving || state.opening, nativeDesktop});
const kinematics=setupKinematics({getModel:()=>state.model,getBindings:()=>state.step?.metadata.bindings || {},isBusy:()=>state.busy || state.saving || state.opening,applyModel,notify:notice});
setupPointProbe({getResult:()=>state.result,getModel:()=>state.model,getBindings:()=>state.step?.metadata.bindings || {},getFrame:()=>state.frame,isStale:()=>Boolean(stale()),notify:notice});
setupWheelKinematics({getResult:()=>state.result,getModel:()=>state.model,getBindings:()=>state.step?.metadata.bindings || {},getFrame:()=>state.frame,isStale:()=>Boolean(stale()),notify:notice});
$("kinematicsButton").onclick=kinematics.open;
init();
