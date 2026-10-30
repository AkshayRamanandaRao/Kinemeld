import { seriesStatistics } from "./full-resolution.js";

/**
 * Parameter studies: which model inputs a study can sweep, the model solved for each case, the
 * key results tabulated per case, and the colours that order the cases on a plot.
 */
export const MAX_CASES = 12;

const COLLECTIONS = {
  bodies: "Body",
  joints: "Joint",
  forces: "Force",
  contacts: "Contact",
  loads: "Load",
  jointTorques: "Joint torque",
  rotationalElements: "Rotational element",
  jointForces: "Axial force",
};
// Geometry, orientation and vectors are left out: changing one component alone rarely means
// anything physically, and anchors must stay consistent between the two ends of a joint.
const SKIP = /^(anchor|axis|center$|center\.|centerOfMass|planePoint|planeNormal|point\.|force\.|torque\.|inertia|pose\.r|translation|rotation)/;
const NAMES = {
  mass: ["mass", "kg"],
  stiffness: ["stiffness", "N/m"],
  damping: ["damping", "N·s/m"],
  restLength: ["free length", "m"],
  minLength: ["minimum length", "m"],
  maxLength: ["maximum length", "m"],
  pressure: ["gas pre-charge pressure", "Pa"],
  gasArea: ["gas piston area", "m²"],
  gasVolume: ["gas volume", "m³"],
  gamma: ["polytropic exponent", ""],
  stopStiffness: ["end-stop stiffness", "N/m"],
  stopDamping: ["end-stop damping", "N·s/m"],
  fluidArea: ["hydraulic area", "m²"],
  fluidDensity: ["fluid density", "kg/m³"],
  dischargeCoefficient: ["discharge coefficient", ""],
  compressionMeteringArea: ["compression orifice area", "m²"],
  reboundMeteringArea: ["rebound orifice area", "m²"],
  radius: ["radius", "m"],
  friction: ["friction coefficient", ""],
  slipVelocity: ["friction slip velocity", "m/s"],
  amplitude: ["amplitude", ""],
  offset: ["offset", ""],
  frequencyHz: ["frequency", "Hz"],
  "pose.x": ["initial position x", "m"],
  "pose.y": ["initial position y", "m"],
  "pose.z": ["initial position z", "m"],
  "velocity.vx": ["initial velocity vx", "m/s"],
  "velocity.vy": ["initial velocity vy", "m/s"],
  "velocity.vz": ["initial velocity vz", "m/s"],
  "velocity.wx": ["initial angular velocity wx", "rad/s"],
  "velocity.wy": ["initial angular velocity wy", "rad/s"],
  "velocity.wz": ["initial angular velocity wz", "rad/s"],
  "motion.speedDegPerS": ["drive target speed", "°/s"],
  "motion.rampTime": ["drive ramp time", "s"],
  "motion.amplitudeDeg": ["drive amplitude", "°"],
  "motion.amplitude": ["drive amplitude", "m"],
  "motion.frequencyHz": ["drive frequency", "Hz"],
};
const ROTATIONAL_UNITS = { stiffness: "N·m/rad", damping: "N·m·s/rad", amplitude: "N·m", offset: "N·m" };

function words(key) {
  return key.replace(/\./g, " ").replace(/([a-z])([A-Z])/g, "$1 $2").toLowerCase();
}
function describe(collection, key) {
  const [name, unit] = NAMES[key] || [key.startsWith("motion.") ? `drive ${words(key.slice(7))}` : words(key), ""];
  return [name, (["rotationalElements", "jointTorques"].includes(collection) && ROTATIONAL_UNITS[key]) || unit];
}
function numericLeaves(value, prefix = "", depth = 0) {
  if (typeof value === "number" && Number.isFinite(value)) return [prefix];
  if (!value || typeof value !== "object" || Array.isArray(value) || depth > 1) return [];
  return Object.entries(value).flatMap(([key, child]) => numericLeaves(child, prefix ? `${prefix}.${key}` : key, depth + 1));
}

/**
 * The inputs of `model` a study can sweep: template parameters from `fields`, or the numeric
 * properties of assembly bodies and elements. Each has a path, a label, a unit and its value.
 */
export function studyParameters(model, fields = {}) {
  if (!["planar-assembly", "spatial-assembly"].includes(model?.kind)) {
    return (fields[model?.kind] || [])
      .filter(([key]) => Number.isFinite(model.parameters?.[key]))
      .map(([key, label, unit]) => ({ path: ["parameters", key], group: "Parameters", label, unit, value: model.parameters[key] }));
  }
  const parameters = [];
  // A drop or launch speed shared by every body is one input; sweeping one body alone would
  // break the joints' initial velocity consistency.
  const bodies = model.bodies || [];
  if (bodies.length > 1) {
    for (const key of ["velocity.vx", "velocity.vy", "velocity.vz"]) {
      const path = ["bodies", "*", ...key.split(".")];
      const values = bodies.map((body) => body.velocity?.[key.split(".")[1]]);
      if (values.every((value) => Number.isFinite(value) && value === values[0]) && values[0] !== 0)
        parameters.push({ path, group: "All bodies", label: NAMES[key][0], unit: NAMES[key][1], value: values[0] });
    }
  }
  for (const [collection, title] of Object.entries(COLLECTIONS)) {
    for (const item of model[collection] || []) {
      if (typeof item?.id !== "string") continue;
      // The order of NAMES puts the usual design inputs (mass, stiffness, damping) first.
      const rank = (key) => (key in NAMES ? Object.keys(NAMES).indexOf(key) : Infinity);
      for (const key of numericLeaves(item).sort((a, b) => rank(a) - rank(b))) {
        if (SKIP.test(key)) continue;
        const [label, unit] = describe(collection, key);
        parameters.push({ path: [collection, item.id, ...key.split(".")], group: `${title} ${item.name || item.id}`, label, unit, value: parameterValue(model, [collection, item.id, ...key.split(".")]) });
      }
    }
  }
  return parameters;
}

export const pathKey = (path) => path.join("/");

/** Every [container, key] an input addresses; an item id of "*" addresses each item of the collection. */
function locate(model, path) {
  const items = path[0] === "parameters" ? [model.parameters] : (model[path[0]] || []).filter((item) => path[1] === "*" || item.id === path[1]);
  const keys = path[0] === "parameters" ? path.slice(1) : path.slice(2);
  return items.map((item) => {
    let container = item;
    for (const key of keys.slice(0, -1)) container = container?.[key];
    return [container, keys.at(-1)];
  });
}

export function parameterValue(model, path) {
  const [container, key] = locate(model, path)[0] || [];
  return container?.[key];
}

/** A copy of `model` with the input at `path` set to `value`; the original is not changed. */
export function caseModel(model, path, value) {
  const copy = structuredClone(model);
  const targets = locate(copy, path);
  if (!targets.length || targets.some(([container, key]) => typeof container?.[key] !== "number")) throw new Error("The swept input no longer exists in this model.");
  for (const [container, key] of targets) container[key] = value;
  return copy;
}

/** Parse "1e4, 2e4; 4e4" into distinct finite values in the order given. */
export function parseValues(text) {
  const tokens = String(text).split(/[\s,;]+/).filter(Boolean);
  const values = tokens.map(Number);
  const bad = tokens.find((token, i) => !Number.isFinite(values[i]));
  if (bad !== undefined) throw new Error(`“${bad}” is not a number.`);
  const distinct = [...new Set(values)];
  if (distinct.length < 2) throw new Error("Enter at least two different values.");
  if (distinct.length > MAX_CASES) throw new Error(`A study runs at most ${MAX_CASES} cases.`);
  return distinct;
}

const significant = (value) => Number(value.toPrecision(3));
/** Five values around the current one, half to double; none for zero, whose scale is unknown. */
export function suggestValues(value) {
  if (!Number.isFinite(value) || value === 0) return [];
  return [0.5, 0.75, 1, 1.5, 2].map((factor) => significant(value * factor));
}

/** Extremes, their times, RMS and final value of one response series. */
export function caseSummary(times, values) {
  const stats = seriesStatistics(times, values);
  let final = NaN;
  for (let i = values.length - 1; i >= 0; i--) if (Number.isFinite(values[i])) { final = values[i]; break; }
  return { ...stats, final };
}

/** One row per case for a CSV of the study table. */
export function summaryCsv(parameter, response, rows) {
  const quote = (text) => `"${String(text).replace(/"/g, '""')}"`;
  const unit = (u) => (u ? ` (${u})` : "");
  const header = [`${parameter.group} ${parameter.label}${unit(parameter.unit)}`, ...["max", "time of max (s)", "min", "time of min (s)", "rms", "final"].map((name) => `${response.label} ${name}${name.includes("time") ? "" : unit(response.unit)}`)];
  return [header.map(quote).join(","), ...rows.map(({ value, summary: s }) => [value, s.max, s.maxAt, s.min, s.minAt, s.rms, s.final].map((x) => (Number.isFinite(x) ? String(x) : "")).join(","))].join("\n") + "\n";
}

// Mid-luminance stops from blue through magenta to orange read on light and dark backgrounds.
const RAMP = [[42, 120, 214], [90, 95, 208], [138, 79, 192], [184, 69, 159], [217, 79, 115], [232, 105, 63], [232, 144, 42]];
/** Ordered colours for `count` cases, from the first value to the last. */
export function caseColors(count) {
  return Array.from({ length: count }, (_, i) => {
    const position = count === 1 ? 0 : (i / (count - 1)) * (RAMP.length - 1);
    const lo = Math.floor(position), hi = Math.min(lo + 1, RAMP.length - 1), f = position - lo;
    const rgb = RAMP[lo].map((c, k) => Math.round(c + (RAMP[hi][k] - c) * f));
    return `#${rgb.map((c) => c.toString(16).padStart(2, "0")).join("")}`;
  });
}
