const KEY = "mbdyn-studio.guided-tour.auto";

const steps = [
  {
    title: "Welcome to Kinemeld",
    text: "This tour introduces a STEP-based planar mechanism: geometry, bodies, revolute hinges, a solver run and results. You can use the app while this guide is open; choose Next when you are ready.",
    target: () => "#stepButton",
  },
  {
    title: "Start with STEP geometry",
    text: "Choose STEP parts, then Load moving STEP pendulum. Wait for it to finish. This example loads a solid and its matching planar body model. You can instead import your own STEP files, but their physical properties and connections must be entered separately.",
    target: () => document.querySelector("#stepDialog")?.open ? "#stepPendulum" : "#stepButton",
    hint: "Open STEP parts and load the moving STEP pendulum to follow the remaining steps.",
  },
  {
    title: "Inspect the body",
    text: "Select Upper Link in the model browser. Properties include mass, inertia, initial position, angle and velocity. You can calculate mass and principal inertia from uniform brick, cylinder, sphere or ellipsoid dimensions and density. This does not create CAD geometry.",
    target: () => "#properties",
    hint: "The body editor appears after the planar STEP pendulum example is loaded.",
  },
  {
    title: "Add a body and hinge",
    text: "In Properties, find Build assembly. Choose a parent and a joint type, then add a body with a revolute hinge or prismatic slider. The body and joint appear in the model browser. The editor supports rooted planar trees.",
    target: () => "#properties",
    hint: "Select a planar body in the model browser to show Build assembly.",
  },
  {
    title: "Set joint anchors",
    text: "Under JOINTS, select a hinge to edit its anchors. Body anchors are local; ground anchors use world coordinates. Their initial positions and velocities must agree. The Properties panel also lets you add a linear spring and damper between ground or bodies.",
    target: () => "#modelTree",
    hint: "Select a hinge such as ground_pin or the new hinge to see its anchor fields.",
  },
  {
    title: "Attach a STEP solid",
    text: "Open STEP parts. Select a STEP part and a planar body, then choose Apply attachment. Check the CAD and body-frame alignment. This links the display to body motion; it does not calculate mass, inertia, joints or contact from the CAD.",
    target: () => document.querySelector("#stepDialog")?.open ? "#stepBindings" : "#stepButton",
    hint: "The attachment controls appear when STEP parts and a planar assembly are loaded.",
  },
  {
    title: "Validate and run",
    text: "Select Validate model and follow any issue back to its field. Check the study duration and time step, then select Run simulation. The configured local MBDyn solver must be available; a validation pass alone does not prove the design is physically correct.",
    target: () => "#validateButton",
  },
  {
    title: "Explore and save",
    text: "After the run, scrub the timeline or press Play to see attached solids move. Choose a response quantity and export CSV if needed. Save project retains the model, results, original STEP files and attachments. Reopen the tour from the Tour button whenever you need it.",
    target: () => "#timeSlider",
  },
];

const element = id => document.getElementById(id);
function preference() { try { return localStorage.getItem(KEY); } catch { return null; } }
function setPreference(value) { try { localStorage.setItem(KEY, value); } catch { /* Storage can be unavailable in private contexts. */ } }

/** Start the optional, non-blocking first-run guide and expose it through Tour. */
export async function setupTour() {
  const panel=element("guidedTour"), button=element("tourButton"), disable=element("tourDisable");
  let index=0, highlighted=null, autoEnabled=preference()!=="off", interacted=false;
  let pendingWrite=Promise.resolve();
  function persist(enabled) {
    autoEnabled=enabled;
    setPreference(enabled ? "on" : "off");
    pendingWrite=pendingWrite.then(async()=>{
      const response=await fetch("/api/tour-preference",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({enabled})});
      if(!response.ok) throw new Error("Tour preference unavailable.");
      element("tourPreferenceStatus").textContent="";
    }).catch(()=>{
      const message="The tour preference could not be saved. It may be reset when you restart the app.";
      element("tourPreferenceStatus").textContent=message;
      const banner=element("notice");
      banner.textContent=message;banner.className="notice warn";banner.hidden=false;
    });
  }
  function relocate() {
    const dialog=[...document.querySelectorAll("dialog[open]")].at(-1);
    const target=dialog || document.body;
    if(panel.parentElement!==target) target.append(panel);
  }
  function update() {
    if (panel.hidden) return;
    relocate();
    if(highlighted) highlighted.classList.remove("guided-tour-target");
    const step=steps[index], target=document.querySelector(step.target());
    highlighted=target && target.getClientRects().length ? target : null;
    if(highlighted) highlighted.classList.add("guided-tour-target");
    element("tourProgress").textContent=`GUIDED TOUR · ${index+1} / ${steps.length}`;
    element("tourTitle").textContent=step.title;
    element("tourText").textContent=step.text;
    element("tourHint").textContent=step.hint || "";
    element("tourBack").disabled=index===0;
    element("tourNext").textContent=index===steps.length-1 ? "Finish" : "Next";
    const rect=highlighted?.getBoundingClientRect();
    panel.classList.toggle("tour-left", Boolean(rect && rect.left+rect.width/2 > innerWidth/2));
  }
  function start() {
    index=0;
    disable.checked=!autoEnabled;
    panel.hidden=false; button.setAttribute("aria-expanded","true");
    update();
    element("tourTitle").focus();
  }
  function close() {
    if(panel.hidden) return;
    const dialog=panel.closest("dialog[open]");
    persist(!disable.checked);
    panel.hidden=true; button.setAttribute("aria-expanded","false");
    if(highlighted) highlighted.classList.remove("guided-tour-target");
    highlighted=null;
    if(panel.parentElement!==document.body) document.body.append(panel);
    (dialog?.querySelector("[data-close], #stepClose") || button).focus();
  }
  button.addEventListener("click",()=>{interacted=true;start();});
  element("tourClose").addEventListener("click",close);
  element("tourBack").addEventListener("click",()=>{if(index){index--;update();element("tourTitle").focus();}});
  element("tourNext").addEventListener("click",()=>{if(index===steps.length-1){close();return;}index++;update();element("tourTitle").focus();});
  disable.addEventListener("change",()=>{interacted=true;persist(!disable.checked);});
  const observer=new MutationObserver(update);
  for(const dialog of document.querySelectorAll("dialog")) observer.observe(dialog,{attributes:true,attributeFilter:["open"]});
  window.addEventListener("resize",update);
  panel.addEventListener("keydown",event=>{if(event.key==="Escape" && !panel.closest("dialog[open]")){event.preventDefault();close();}});
  try {
    const response=await fetch("/api/tour-preference");
    if(!response.ok)throw new Error("Tour preference unavailable.");
    const settings=await response.json();
    if(typeof settings.enabled!=="boolean")throw new Error("Invalid tour preference.");
    if(!interacted)autoEnabled=settings.enabled;
  } catch { /* Local browser preference is the fallback when the service is unavailable. */ }
  if(!interacted && autoEnabled) start();
  return {start,close};
}
