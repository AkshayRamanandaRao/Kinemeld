import { designGrid, rankDesigns, designCsv, csvResponses, responseSeries } from "./design-search.js";
import { pathKey, parseValues, suggestValues } from "./studies.js";

const defaults = () => ({ input0: "", values0: "", input1: "", values1: "", objective: "", metric: "rms", sense: "min", target: "0", constraint: "", constraintMetric: "peakAbs", lower: "", upper: "" });
const label = item => `${item.label}${item.unit ? ` (${item.unit})` : ""}`;
const option = (value, text) => Object.assign(document.createElement("option"), { value, textContent: text });

export function setupDesignSearch(host) {
  const card = document.createElement("section"); card.className = "card study-card"; card.id = "designSearchCard";
  card.innerHTML = `<details><summary>Design search</summary><p class="field-help">Evaluate up to 25 combinations of one or two inputs. The best feasible sampled design is reported; no global optimum is assumed.</p>
    <label>First input<select data-config="input0" aria-label="First design input"></select></label><label>First values<input data-config="values0" aria-label="First design values" maxlength="300"></label>
    <label>Second input (optional)<select data-config="input1" aria-label="Second design input"></select></label><label>Second values<input data-config="values1" aria-label="Second design values" maxlength="300"></label>
    <button class="text-button" id="designRefresh" type="button">Refresh responses from current run</button><p class="field-help" id="designContext"></p>
    <label>Objective response<select data-config="objective" aria-label="Design objective"></select></label>
    <div class="field-row"><label>Statistic<select data-config="metric"><option value="rms">RMS</option><option value="peakAbs">Peak magnitude</option><option value="final">Final value</option></select></label>
    <label>Direction<select data-config="sense"><option value="min">Minimize</option><option value="max">Maximize</option><option value="target">Match target</option></select></label></div>
    <label id="designTargetField" hidden>Target value<input data-config="target" inputmode="decimal" maxlength="40"></label>
    <label>Constraint response (optional)<select data-config="constraint" aria-label="Design constraint"></select></label>
    <label>Constraint statistic<select data-config="constraintMetric"><option value="peakAbs">Peak magnitude</option><option value="rms">RMS</option><option value="final">Final value</option></select></label>
    <div class="field-row"><label>Lower bound<input data-config="lower" inputmode="decimal" maxlength="40"></label><label>Upper bound<input data-config="upper" inputmode="decimal" maxlength="40"></label></div>
    <button id="designRun" class="secondary full-width" type="button">Run design search</button><button id="designCancel" class="text-button full-width" type="button" hidden>Stop design search</button>
    <p id="designProgress" class="field-help" role="status" aria-live="polite"></p>
    <div id="designResults" hidden><p id="designSummary" class="field-help"></p><div class="study-table-wrap"><table id="designTable" class="study-table"></table></div>
    <button id="designApply" class="secondary full-width" type="button">Apply best evaluated inputs</button><button id="designCsv" class="text-button full-width" type="button">Export design table</button></div></details>`;
  document.getElementById("studyCard").after(card);
  for (const input of card.querySelectorAll("input")) { const wrapper = document.createElement("span"); wrapper.className = "number-field"; input.before(wrapper); wrapper.append(input); }
  const find = id => card.querySelector(`#${id}`), controls = [...card.querySelectorAll("[data-config]")];
  let draft = defaults(), inputs = [], responses = [], running = false, starting = false, cancelled = false, runRevision = null, last = null;
  const best = () => last?.rows.filter(row => row.feasible).sort((a, b) => a.score - b.score || a.index - b.index)[0];
  const setControls = () => {
    for (const control of controls) control.value = draft[control.dataset.config];
    find("designTargetField").hidden = draft.sense !== "target";
  };
  const renderInputs = () => {
    inputs = host.inputs();
    for (let i = 0; i < 2; i++) {
      const select = card.querySelector(`[data-config="input${i}"]`);
      select.replaceChildren(option("", i ? "No second input" : "Choose an input"), ...inputs.map(item => option(pathKey(item.path), `${item.group} · ${label(item)}`)));
    }
    setControls();
  };
  const renderResponses = () => {
    for (const key of ["objective", "constraint"]) card.querySelector(`[data-config="${key}"]`).replaceChildren(option("", key === "objective" ? "Choose a response" : "No constraint"), ...responses.map(item => option(item.key, label(item))));
    setControls();
  };
  function renderRows() {
    find("designResults").hidden = !last;
    if (!last) return;
    const chosen = best();
    find("designSummary").textContent = chosen ? `Best feasible sampled design: case ${chosen.index + 1}, objective ${chosen.objectiveValue.toPrecision(6)}${last.objective.unit ? ` ${last.objective.unit}` : ""}. ${last.rows.filter(row => row.feasible).length} of ${last.rows.length} evaluated cases are feasible.` : "No evaluated case satisfies the response constraints.";
    const table = find("designTable"); table.replaceChildren();
    const header = table.createTHead().insertRow();
    const headings = ["Case", ...last.variables.map((item,i) => `Input ${i+1}${item.unit ? ` (${item.unit})` : ""}`), `${last.objective.metric}${last.objective.unit ? ` (${last.objective.unit})` : ""}`, "Status"];
    for (const [i,text] of headings.entries()) { const th = document.createElement("th"); th.scope = "col"; th.textContent = text; if(i>0 && i<=last.variables.length)th.title=label(last.variables[i-1]); header.append(th); }
    const body = table.createTBody();
    for (const item of last.rows) {
      const row = body.insertRow();
      for (const text of [item.index + 1, ...item.values, item.objectiveValue?.toPrecision(6) ?? "—", item.error || (item.feasible ? "Feasible" : "Constraint not met")]) row.insertCell().textContent = String(text);
      if (item === chosen) row.className = "shown";
    }
    find("designApply").disabled = running || host.busy() || !chosen || runRevision !== host.revision();
  }
  async function refresh() {
    if (running || starting) return;
    renderInputs();
    const revision = host.revision();
    try {
      const baseline = await host.baseline();
      if (revision !== host.revision()) return;
      responses = csvResponses(baseline.data, baseline.model);
      find("designContext").textContent = `Responses from MBDyn run ${baseline.runId}. Bounds use the displayed units.`;
    } catch (error) { responses = []; find("designContext").textContent = error.message; }
    renderResponses(); renderRows();
  }
  card.addEventListener("input", event => {
    const key = event.target.dataset.config;
    if (!key || running || starting) return;
    draft[key] = event.target.value;
    host.changed(); renderRows();
  });
  card.addEventListener("change", event => {
    const key = event.target.dataset.config;
    if (!key || running || starting) return;
    draft[key] = event.target.value;
    if (key.startsWith("input")) {
      const i = key.at(-1), selected = inputs.find(item => pathKey(item.path) === draft[key]);
      if (selected) draft[`values${i}`] = suggestValues(selected.value).join(", ");
    }
    setControls(); host.changed(); renderRows();
  });
  find("designRefresh").onclick = refresh;
  card.querySelector("details").addEventListener("toggle", event => { if (event.target.open) refresh(); });
  const stop = () => { cancelled = true; };
  find("designCancel").onclick = () => { stop(); host.cancel(); };
  find("designRun").onclick = async () => {
    if (running || starting || host.busy()) return;
    starting = true;
    const revision = host.revision();
    controls.forEach(control => { control.disabled = true; }); find("designRun").disabled = true;
    let plan, variables, objective, constraints;
    try {
      const baseline = await host.baseline();
      if (revision !== host.revision() || host.busy()) throw Error("The project changed while preparing the search. Refresh the current run and try again.");
      inputs = host.inputs();
      responses = csvResponses(baseline.data, baseline.model);
      variables = [0, 1].filter(i => draft[`input${i}`]).map(i => ({ ...inputs.find(item => pathKey(item.path) === draft[`input${i}`]), values: parseValues(draft[`values${i}`]) }));
      plan = designGrid(baseline.model, variables, host.fields);
      const response = responses.find(item => item.key === draft.objective);
      if (!response) throw Error("Select an objective from a current MBDyn run.");
      objective = { signal: response.key, metric: draft.metric, sense: draft.sense, target: draft.target.trim() ? Number(draft.target) : NaN, label: response.label, unit: response.unit };
      constraints = draft.constraint ? [{ signal: draft.constraint, metric: draft.constraintMetric, ...(draft.lower.trim() ? { lower: Number(draft.lower) } : {}), ...(draft.upper.trim() ? { upper: Number(draft.upper) } : {}) }] : [];
      if (constraints.some(item => !responses.some(response => response.key === item.signal))) throw Error("Select a current constraint response.");
      rankDesigns([], objective, constraints);
    } catch (error) { host.notice(error.message, "error"); return; }
    finally { starting = false; controls.forEach(control => { control.disabled = false; }); find("designRun").disabled = false; }
    running = true; cancelled = false; runRevision = host.revision(); last = { variables, objective, rows: [], models: plan.map(item => item.model) };
    controls.forEach(control => { control.disabled = true; }); find("designRun").disabled = true; find("designRefresh").disabled = true; find("designCancel").hidden = false;
    host.begin();
    try {
      find("designProgress").textContent = "Checking every candidate before solving…";
      for (const item of plan) {
        if (cancelled) break;
        const check = await host.check(item.model);
        if (!check.valid) throw Error(`Case ${item.index + 1} is invalid: ${(check.issues || []).map(issue => issue.message).join(" ")}`);
      }
      for (const item of plan) {
        if (cancelled || runRevision !== host.revision()) break;
        find("designProgress").textContent = `Solving case ${item.index + 1} of ${plan.length}…`;
        let row;
        try {
          const solved = await host.solve(item.model);
          const series = Object.fromEntries([...new Set([objective.signal, ...constraints.map(c => c.signal)])].map(key => [key, responseSeries(solved.data, key)]));
          row = rankDesigns([{ values: item.values, series, runId: solved.runId }], objective, constraints).rows[0];
          delete row.series;
        } catch (error) { row = { values: item.values, error: error.message, feasible: false, objectiveValue: null, score: null }; if (error.details?.cancelled) cancelled = true; }
        last.rows.push({ ...row, index: item.index }); renderRows();
      }
      find("designProgress").textContent = runRevision !== host.revision() ? "The project changed. Evaluated cases are retained; current edits were kept." : cancelled ? "Search stopped. Only completed feasible cases are ranked." : "Design search complete. Apply the best inputs explicitly, then run the model to inspect that design.";
    } catch (error) { find("designProgress").textContent = error.message; host.notice(error.message, "error"); }
    finally {
      running = false; host.end(); controls.forEach(control => { control.disabled = false; }); find("designRun").disabled = false; find("designRefresh").disabled = false; find("designCancel").hidden = true; renderRows();
    }
  };
  find("designApply").onclick = () => {
    const chosen = best();
    if (!chosen || running || host.busy() || runRevision !== host.revision()) { host.notice("The project changed after this search. Run it again before applying inputs.", "error"); return; }
    host.apply(last.models[chosen.index]); renderRows();
  };
  find("designCsv").onclick = () => { if (last) host.download("design-search.csv", designCsv(last.variables, last.objective, last), "text/csv"); };
  return {
    snapshot: () => structuredClone(draft),
    checkpoint: () => ({ draft: structuredClone(draft), last, runRevision }),
    rollback(value) {
      if (!value) return;
      draft = value.draft; last = value.last; runRevision = value.runRevision;
      renderInputs(); renderResponses(); renderRows();
    },
    restore(value) {
      draft = defaults();
      if (value && typeof value === "object") for (const key of Object.keys(draft)) if (typeof value[key] === "string" && value[key].length <= 512) draft[key] = value[key];
      last = null; renderInputs(); renderResponses(); renderRows();
    },
    refresh, stop,
  };
}
