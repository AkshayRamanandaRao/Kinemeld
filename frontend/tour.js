const KEY = "mbdyn-studio.guided-tour.auto";

// An industry walkthrough: build a wheel-end drop test from original STEP parts, solve it and read the results.
const steps = [
  {
    title: "Welcome to Kinemeld",
    text: "This tour builds an automotive wheel-end drop test from original STEP parts: import the CAD, define bodies and links, add contact and initial conditions, solve with MBDyn and review the results. You can use the app while the guide is open. To see finished industry studies first, open Featured studies.",
    target: () => "#examplesButton",
    action: { label: "Open featured studies", run: (actions) => actions.openFeaturedStudies?.() },
  },
  {
    title: "1 · Start a 3D assembly",
    text: "Pre-processing (key 1) holds the model tree on the left and the properties of the selection on the right. Start a new 3D assembly; it contains one body to build from.",
    target: () => "#newButton",
    action: { label: "New 3D assembly", run: (actions) => actions.newAssembly?.() },
  },
  {
    title: "2 · Import the CAD",
    text: "Open STEP parts and import the knuckle, hub and tyre from the original wheel-end assembly. Parts keep their CAD units and coordinates; they are display geometry until you attach them to bodies.",
    target: () => document.querySelector("#stepDialog")?.open ? "#stepImport" : "#stepButton",
    action: { label: "Import wheel-end STEP parts", run: (actions) => actions.importWheelEnd?.() },
  },
  {
    title: "3 · Bodies and links",
    text: "Rename Body 1 to Knuckle and place its frame at the bearing centre (x −0.04 m, y −0.0875 m). Under Add 3D body and joint, add the Hub to the Knuckle with a Revolute joint, then the Tyre to the Hub with a Weld. Select each joint to set anchors and the bearing axis (x). Joint symbols in the 3D view show each anchor and axis.",
    target: () => "#properties",
    hint: "Select a body in the model tree to show its properties and the Add 3D body and joint tools.",
  },
  {
    title: "4 · Attach CAD and compute mass",
    text: "In STEP parts, attach each solid to its body; the solid then follows that body. Calculate the mass from the solid with a material density (steel 7850, rubber 1100 kg/m³) and apply it: mass, centre of mass and inertia come from the CAD.",
    target: () => document.querySelector("#stepDialog")?.open ? "#stepBindings" : "#stepButton",
    hint: "Attachment and mass controls appear in STEP parts once parts are imported.",
  },
  {
    title: "5 · Contact and initial conditions",
    text: "Add a sphere-plane contact to the Tyre (radius 0.208 m, floor through the origin, 20 kN/m, 100 N·s/m), then raise all three bodies to z = 0.6 m with a downward velocity of 1 m/s. The AI assistant can propose these edits for you to review and apply.",
    target: () => "#agentButton",
  },
  {
    title: "6 · Solve",
    text: "Solve (key 2) holds the study settings, pre-run checks and the solver console. Set 1.5 s at 0.5 ms, check the mobility and any linked issues, inspect the MBDyn deck if you wish, then Run simulation (F5).",
    target: () => '[data-step="simulate"]',
  },
  {
    title: "7 · Post-processing",
    text: "Post-processing (key 3) plays the motion with frame stepping and speed control. Plot Contact normal force, hover or drag on the plot to scrub, and read min, max and RMS. Trails, follow camera and presentation mode (P) help reviews; CSV export keeps every solver step.",
    target: () => '[data-step="results"]',
  },
  {
    title: "Compare with the finished study",
    text: "The Wheel-end drop test featured study is this model, built and verified: free fall, first contact time and the contact energy balance are checked against independent calculations. Save your project to keep the model, CAD, attachments and results together.",
    target: () => "#examplesButton",
    action: { label: "Open the finished study", run: (actions) => actions.openStudy?.("wheel-end-drop") },
  },
];

const element = id => document.getElementById(id);
function preference() { try { return localStorage.getItem(KEY); } catch { return null; } }
function setPreference(value) { try { localStorage.setItem(KEY, value); } catch { /* Storage can be unavailable in private contexts. */ } }

/** Start the optional, non-blocking first-run guide and expose it through Tour. */
export async function setupTour(actions = {}) {
  const panel=element("guidedTour"), button=element("tourButton"), disable=element("tourDisable");
  let index=0, highlighted=null, autoEnabled=preference()==="on", interacted=false;
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
    const action=element("tourAction");
    action.hidden=!step.action;
    action.textContent=step.action?.label || "";
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
  element("tourAction").addEventListener("click",()=>{interacted=true;steps[index].action?.run(actions);});
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
