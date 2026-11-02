/** Full-resolution access to a solver run's CSV: every integration step, not only displayed samples. */

// Displayed-sample channel keys map onto the column names written by the backend CSV writers.
const ELEMENT_COLUMNS = {
  servo: { angle: "angle_rad", speed: "speed_rad_s", desiredAngle: "desiredAngle_rad", desiredSpeed: "desiredSpeed_rad_s", error: "error_rad", torque: "torque_Nm", saturated: "saturated", power: "power_W" },
  force: { length: "length_m", extension: "extension_m", rate: "rate_m_s", force: "tension_N" },
  oleo: { gasPressure: "gasPressure_Pa", gasForce: "gasForce_N", hydraulicForce: "hydraulicForce_N", stopForce: "stopForce_N" },
  slider: { position: "position_m", velocity: "velocity_m_s" },
  cylinder: { position: "position_m", velocity: "velocity_m_s", angle: "angle_rad", angularVelocity: "angularVelocity_rad_s" },
  rotary: { angle: "angle_rad", velocity: "velocity_rad_s", torque: "torque_Nm" },
  torque: { torque: "torque_Nm", power: "power_W" },
  contact: { gap: "gap_m", penetration: "penetration_m", force: "force_N", power: "power_W", energy: "energy_J", dampingPower: "dampingPower_W", dissipatedEnergy: "dissipatedEnergy_J", frictionForce: "frictionForce_N", slip: "slip_m_s", frictionPower: "frictionPower_W", frictionEnergy: "frictionEnergy_J" },
  "joint-force": { force: "force_N", power: "power_W" },
  drive: { angle: "angle_rad", speed: "speed_rad_s", torque: "torque_Nm", power: "power_W" },
  brake: { torque: "torque_Nm", speed: "speed_rad_s", power: "power_W", dissipatedEnergy: "dissipatedEnergy_J" },
};
const ELEMENT_PREFIX = { servo: "servo", force: "force", oleo: "force", slider: "slider", cylinder: "cylindrical", rotary: "rotational", torque: "actuation", contact: "contact", "joint-force": "jointForce", drive: "rotaryDrive", brake: "jointFriction" };
const SYSTEM_COLUMNS = {
  tipDeflection: "tipDeflection_m", tipVelocity: "tipVelocity_m_s", tipSlope: "tipSlope_rad", appliedForce: "appliedForce_N", rootForce: "rootForce_N", rootMoment: "rootMoment_Nm",
  loadPower: "loadPower_W", appliedWork: "appliedWork_J", actuationPower: "actuationPower_W", actuationWork: "actuationWork_J",
  jointForcePower: "jointForcePower_W", jointForceWork: "jointForceWork_J", elasticEnergy: "elasticEnergy_J", dampingPower: "dampingPower_W", dissipatedEnergy: "dissipatedEnergy_J",
  rotaryDrivePower: "rotaryDrivePower_W", rotaryDriveWork: "rotaryDriveWork_J",
};
const NODE_FIELDS = new Set(["x", "y", "z", "rx", "ry", "rz", "vx", "vy", "vz", "wx", "wy", "wz"]);

/** Translate a plotted channel key to a CSV column and, for body values, the row id. */
export function columnFor(key) {
  const parts = key.split(":");
  if (parts[0] === "node") {
    const field = parts[2];
    if (field.startsWith("bw")) return { node: parts[1], derived: field };
    return NODE_FIELDS.has(field) ? { node: parts[1], column: field } : null;
  }
  if (parts.length === 1) return SYSTEM_COLUMNS[key] ? { column: SYSTEM_COLUMNS[key] } : null;
  const [kind, id, path] = parts;
  if (kind === "reaction") {
    const [field, axis] = path.split(".");
    return { column: `jointReaction:${id}:${field}_${axis}_${field === "force" ? "N" : "Nm"}` };
  }
  if (kind === "load") {
    if (path === "power") return { column: `load:${id}:power_W` };
    const [field, axis] = path.split(".");
    return { column: `load:${id}:${field}_${axis}_${field === "force" ? "N" : "Nm"}` };
  }
  const column = ELEMENT_COLUMNS[kind]?.[path];
  return column ? { column: `${ELEMENT_PREFIX[kind]}:${id}:${column}` } : null;
}

/** Parse the solver CSV once into per-time columns; body columns are keyed by node id. */
export function parseSolverCsv(text) {
  const lines = text.trim().split(/\r?\n/);
  const header = lines[0].split(",");
  const index = Object.fromEntries(header.map((name, i) => [name, i]));
  if (index.time === undefined) throw new Error("The solver CSV has no time column.");
  const times = [], global = Object.create(null), nodes = Object.create(null);
  let lastTime = null;
  for (let row = 1; row < lines.length; row++) {
    const cells = lines[row].split(",");
    const time = Number(cells[index.time]);
    const fresh = time !== lastTime;
    if (fresh) {
      times.push(time);
      lastTime = time;
      for (const [name, i] of Object.entries(index)) {
        if (name === "time" || name === "id" || name === "label" || (index.id !== undefined && NODE_FIELDS.has(name))) continue;
        (global[name] ||= []).push(cells[i] === "" ? NaN : Number(cells[i]));
      }
    }
    if (index.id !== undefined) {
      const id = cells[index.id];
      const columns = (nodes[id] ||= Object.create(null));
      for (const field of NODE_FIELDS) {
        if (index[field] !== undefined) (columns[field] ||= []).push(Number(cells[index[field]]));
      }
    }
  }
  return { times, global, nodes };
}

/** Values of a channel at every solver step, or null when the CSV does not contain it. */
export function fullSeries(data, key, bodyAngularVelocity) {
  const target = columnFor(key);
  if (!target) return Object.hasOwn(data.global, key) ? data.global[key] : null;
  if (target.node !== undefined) {
    const columns = data.nodes[target.node];
    if (!columns) return null;
    if (target.derived) {
      const axis = "xyz".indexOf(target.derived[2]);
      return data.times.map((_, i) => bodyAngularVelocity({ rx: columns.rx[i], ry: columns.ry[i], rz: columns.rz[i], wx: columns.wx[i], wy: columns.wy[i], wz: columns.wz[i] })[axis]);
    }
    return columns[target.column] || null;
  }
  return data.global[target.column] || null;
}

/** Min, max, time of extremes and time-weighted RMS using trapezoidal integration. */
export function seriesStatistics(times, values) {
  let min = Infinity, max = -Infinity, minAt = NaN, maxAt = NaN, integral = 0, span = 0;
  for (let i = 0; i < values.length; i++) {
    const v = values[i];
    if (!Number.isFinite(v)) continue;
    if (v < min) { min = v; minAt = times[i]; }
    if (v > max) { max = v; maxAt = times[i]; }
    if (i && Number.isFinite(values[i - 1])) {
      const dt = times[i] - times[i - 1];
      integral += 0.5 * (v * v + values[i - 1] * values[i - 1]) * dt;
      span += dt;
    }
  }
  return { min, max, minAt, maxAt, rms: span > 0 ? Math.sqrt(integral / span) : Math.abs(values.find(Number.isFinite) ?? NaN) };
}

/** Reduce a long series to min/max pairs per pixel bucket so no peak disappears from the plot. */
export function envelope(times, values, first, last, buckets) {
  const points = [];
  const width = (last - first) / buckets || 1;
  let bucket = -1, lo = null, hi = null;
  const flush = () => {
    if (!lo) return;
    if (lo.t <= hi.t) points.push(lo, hi); else points.push(hi, lo);
    if (lo === hi) points.pop();
  };
  for (let i = 0; i < times.length; i++) {
    const v = values[i];
    if (!Number.isFinite(v)) { flush(); lo = hi = null; points.push(null); bucket = -1; continue; }
    const b = Math.min(buckets - 1, Math.floor((times[i] - first) / width));
    if (b !== bucket) { flush(); bucket = b; lo = hi = { t: times[i], v }; continue; }
    if (v < lo.v) lo = { t: times[i], v };
    if (v > hi.v) hi = { t: times[i], v };
  }
  flush();
  return points;
}
