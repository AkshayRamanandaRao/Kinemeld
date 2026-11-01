import { studyParameters, pathKey, caseModel, caseSummary } from "./studies.js";
import { industryCsvUnits } from "./industry.js";

export const MAX_DESIGNS = 25;
const METRICS = new Set(["rms", "peakAbs", "final"]);
const overlaps = (a, b) => a.length === b.length && a.every((part, i) => part === b[i] || part === "*" || b[i] === "*");

const UNITS = { m_s2: "m/s²", m_s: "m/s", rad_s: "rad/s", Nm: "N·m", rad: "rad", deg: "°", N: "N", m: "m", J: "J", W: "W", Pa: "Pa" };
const words = text => text.replace(/([a-z])([A-Z])/g, "$1 $2").replace(/_/g, " ");
export function csvResponses(data, model) {
  if (!Array.isArray(data?.times) || data.times.length < 2) return [];
  const names = new Map(["bodies", "joints", "forces", "contacts", "jointTorques", "jointForces", "loads"].flatMap(key => (model?.[key] || []).map(item => [item.id, item.name || item.id])));
  const valid = values => Array.isArray(values) && values.length === data.times.length && values.every(Number.isFinite);
  const result = Object.entries(data.global || {}).filter(([, values]) => valid(values)).map(([column]) => {
    const named = industryCsvUnits[column] || column;
    const suffix = Object.keys(UNITS).find(unit => named.endsWith(`_${unit}`));
    const angular = ["pendulum", "double-pendulum", "gear-deployment"].includes(model?.kind);
    const linear = ["mass-spring", "suspension", "landing-gear-drop", "flexible-link"].includes(model?.kind);
    const unit = suffix ? UNITS[suffix] : ({ x: "m", y: "m", z: "m", v: "m/s", angle: "°", angle2: "°", velocity: angular ? "rad/s" : linear ? "m/s" : "", velocity2: "rad/s", value: angular ? "°" : linear ? "m" : "" }[column] || "");
    const title = (suffix ? named.slice(0, -suffix.length - 1) : named).split(":").map(part => names.get(part) || words(part)).join(" · ");
    return { key: JSON.stringify(["global", column]), label: title, unit };
  });
  for (const [id, columns] of Object.entries(data.nodes || {})) for (const [field, values] of Object.entries(columns)) {
    if (!valid(values)) continue;
    const axis = field.at(-1).toUpperCase(), kind = field.length === 1 ? "position" : ({ v: "velocity", r: "Euler angle", w: "angular velocity" }[field[0]]);
    if (kind) result.push({ key: JSON.stringify(["node", id, field]), label: `${names.get(id) || id} · ${kind} ${axis}`, unit: field.length === 1 ? "m" : ({ v: "m/s", r: "°", w: "rad/s" }[field[0]]) });
  }
  return result;
}

export function responseSeries(data, key) {
  const parts = JSON.parse(key);
  if (!Array.isArray(parts)) throw Error("Invalid response identifier.");
  const columns = parts.length === 2 && parts[0] === "global" ? data.global : parts.length === 3 && parts[0] === "node" && Object.hasOwn(data.nodes || {}, parts[1]) ? data.nodes[parts[1]] : null;
  const field = parts[0] === "global" ? parts[1] : parts[2];
  if (!columns || !Object.hasOwn(columns, field)) throw Error("The response is absent from the full solver CSV.");
  return { times: data.times, values: columns[field] };
}

/** A bounded, deterministic grid. Each candidate still needs normal model validation. */
export function designGrid(model, variables, fields = {}) {
  if (!Array.isArray(variables) || variables.length < 1 || variables.length > 2) throw Error("Choose one or two design inputs.");
  const allowed = new Set(studyParameters(model, fields).map(item => pathKey(item.path)));
  const inputs = variables.map((item, index) => {
    if (!Array.isArray(item.path) || !allowed.has(pathKey(item.path))) throw Error("A design input is unavailable in the current model.");
    if (variables.slice(0, index).some(previous => overlaps(previous.path, item.path))) throw Error("Design inputs must not change the same property.");
    if (!Array.isArray(item.values) || item.values.some(value => typeof value !== "number" || !Number.isFinite(value))) throw Error("Design values must be finite numbers.");
    const values = [...new Set(item.values)];
    if (values.length < 2 || values.length > 9) throw Error("Supply two to nine distinct values for each design input.");
    return { path: [...item.path], values };
  });
  if (inputs.reduce((count, item) => count * item.values.length, 1) > MAX_DESIGNS) throw Error(`A design search evaluates at most ${MAX_DESIGNS} candidates.`);
  let cases = [{ values: [], model: structuredClone(model) }];
  for (const input of inputs) cases = cases.flatMap(item => input.values.map(value => ({ values: [...item.values, value], model: caseModel(item.model, input.path, value) })));
  return cases.map((item, index) => ({ ...item, index }));
}

function measure(series, signal, metric) {
  const item = Object.hasOwn(series || {}, signal) ? series[signal] : null;
  if (!METRICS.has(metric) || !Array.isArray(item?.times) || !Array.isArray(item?.values) || item.times.length < 2 || item.times.length !== item.values.length
    || item.times.some((time, i) => !Number.isFinite(time) || (i && time <= item.times[i - 1])) || item.values.some(value => !Number.isFinite(value)))
    throw Error(`A complete finite response is required for ${signal}.`);
  const stats = caseSummary(item.times, item.values);
  const value = metric === "peakAbs" ? Math.max(Math.abs(stats.min), Math.abs(stats.max)) : stats[metric];
  if (!Number.isFinite(value)) throw Error(`The computed ${metric} is not finite for ${signal}.`);
  return value;
}

/** Rank only successfully solved, feasible candidates; this is not a global optimum claim. */
export function rankDesigns(rows, objective, constraints = []) {
  if (!Array.isArray(rows) || rows.length > MAX_DESIGNS) throw Error("Invalid design result count.");
  if (!objective || typeof objective.signal !== "string" || !objective.signal || !METRICS.has(objective.metric)
    || !["min", "max", "target"].includes(objective.sense) || (objective.sense === "target" && !Number.isFinite(objective.target)))
    throw Error("Choose an objective response, statistic and direction.");
  if (!Array.isArray(constraints) || constraints.length > 4) throw Error("Use at most four response constraints.");
  for (const constraint of constraints) {
    if (!constraint || typeof constraint.signal !== "string" || !constraint.signal || !METRICS.has(constraint.metric)
      || (constraint.lower === undefined && constraint.upper === undefined)
      || [constraint.lower, constraint.upper].some(value => value !== undefined && !Number.isFinite(value))
      || (constraint.lower !== undefined && constraint.upper !== undefined && constraint.lower > constraint.upper))
      throw Error("Each response constraint needs finite, ordered bounds.");
  }
  const evaluated = rows.map((row, index) => {
    if (row.error) return { ...row, index, feasible: false, score: null, objectiveValue: null };
    try {
      const objectiveValue = measure(row.series, objective.signal, objective.metric);
      const checks = constraints.map(constraint => {
        const value = measure(row.series, constraint.signal, constraint.metric);
        return { ...constraint, value, satisfied: (constraint.lower === undefined || value >= constraint.lower) && (constraint.upper === undefined || value <= constraint.upper) };
      });
      const score = objective.sense === "target" ? Math.abs(objectiveValue - objective.target) : objective.sense === "max" ? -objectiveValue : objectiveValue;
      if (!Number.isFinite(score)) throw Error("The objective score is not finite.");
      return { ...row, index, objectiveValue, checks, feasible: checks.every(check => check.satisfied), score };
    } catch (error) { return { ...row, index, error: error.message, feasible: false, score: null, objectiveValue: null }; }
  });
  const feasible = evaluated.filter(row => row.feasible).sort((a, b) => a.score - b.score || a.index - b.index);
  return { rows: evaluated, bestIndex: feasible[0]?.index ?? null, feasibleCount: feasible.length };
}

export function designCsv(variables, objective, ranked) {
  const quote = value => `"${(typeof value === "string" && /^[=+\-@\t\r]/.test(value) ? "'" + value : String(value)).replace(/"/g, '""')}"`;
  const header = ["candidate", ...variables.map(item => `${item.label}${item.unit ? ` (${item.unit})` : ""}`), `${objective.label || objective.signal} ${objective.metric}`, "feasible", "error"];
  return [header, ...ranked.rows.map(row => [row.index + 1, ...row.values, row.objectiveValue ?? "", row.feasible, row.error || ""])].map(row => row.map(quote).join(",")).join("\n") + "\n";
}
