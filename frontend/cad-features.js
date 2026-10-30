import * as THREE from "three";

/**
 * Analytic STEP faces (cylinders and planes reported by the converter) turned into joint anchors
 * and axes. Geometry is evaluated at the model's initial configuration: an attached part follows
 * its body's initial pose, an unattached part stays at its CAD position.
 */
const DEG = Math.PI / 180;
const vector = (v) => (Array.isArray(v) ? new THREE.Vector3(v[0], v[1], v[2]) : new THREE.Vector3(v.x, v.y, v.z));
const plain = (v) => ({ x: round(v.x), y: round(v.y), z: round(v.z) });
const round = (n) => (Math.abs(n) < 1e-12 ? 0 : Number(n.toPrecision(10)));

function rotation(pose, spatial = true) {
  return spatial
    ? new THREE.Quaternion().setFromEuler(new THREE.Euler((pose.rx || 0) * DEG, (pose.ry || 0) * DEG, (pose.rz || 0) * DEG, "XYZ"))
    : new THREE.Quaternion().setFromAxisAngle(new THREE.Vector3(0, 1, 0), (pose.ry || 0) * DEG);
}

/** The analytic face containing a triangle of a converted part, if the converter described it.
 *  Full circular edges are listed separately in `part.edges` and picked by line, not triangle. */
export function faceAt(part, triangle) {
  return (part?.faces || []).find((face) => triangle >= face.triangles[0] && triangle < face.triangles[0] + face.triangles[1]) || null;
}

/** Map CAD coordinates of a part into model world coordinates at the initial configuration. */
export function cadPlacement(binding, body) {
  if (!binding || !body) return { point: (p) => vector(p), direction: (d) => vector(d).normalize() };
  const bindRotation = rotation(binding.pose, Object.hasOwn(binding.pose, "rx"));
  const bodyRotation = rotation(body.pose);
  const bind = vector(binding.pose), origin = vector(body.pose);
  const turn = bodyRotation.clone().multiply(bindRotation.clone().invert());
  return {
    point: (p) => vector(p).sub(bind).applyQuaternion(turn).add(origin),
    direction: (d) => vector(d).applyQuaternion(turn).normalize(),
  };
}

/** A face in model world coordinates: an anchor point, an axis (cylinder axis or plane normal) and a label. */
export function worldFeature(face, placement, hitPoint = null) {
  if (face.type === "circle") {
    const axis = placement.direction(face.axis);
    return { type: "circle", point: placement.point(face.centre), axis, radius: face.radius,
      label: `Circle Ø${(face.radius * 2000).toFixed(1)} mm · axis ${describe(axis)}` };
  }
  if (face.type === "cylinder") {
    const axis = placement.direction(face.axis);
    return { type: "cylinder", point: placement.point(face.centre), axis, radius: face.radius, length: face.length,
      label: `Cylinder Ø${(face.radius * 2000).toFixed(1)} mm · axis ${describe(axis)}` };
  }
  const normal = placement.direction(face.normal);
  // On a plane the clicked point is the natural anchor; project it onto the plane exactly.
  const onPlane = placement.point(face.point);
  const point = hitPoint ? hitPoint.clone().sub(normal.clone().multiplyScalar(hitPoint.clone().sub(onPlane).dot(normal))) : onPlane;
  return { type: "plane", point, axis: normal, label: `Plane · normal ${describe(normal)}` };
}

function describe(direction) {
  const names = ["x", "y", "z"], values = direction.toArray();
  const index = values.findIndex((value) => Math.abs(Math.abs(value) - 1) < 1e-6);
  return index >= 0 ? `${values[index] < 0 ? "−" : "+"}${names[index]}` : `(${values.map((v) => v.toFixed(3)).join(", ")})`;
}

/** Express a world point and direction in a body's frame at the initial configuration; ground keeps world axes. */
export function inBodyFrame(body, point, direction) {
  if (!body) return { point: plain(point), direction: plain(direction) };
  const inverse = rotation(body.pose).invert();
  return {
    point: plain(point.clone().sub(vector(body.pose)).applyQuaternion(inverse)),
    direction: plain(direction.clone().applyQuaternion(inverse).normalize()),
  };
}

/**
 * Joint fields that place both ends at one picked feature, so the anchors coincide and the axes
 * agree by construction. Universal joints keep their perpendicular cross axes.
 */
export function jointFromFeature(model, joint, feature) {
  const bodies = new Map(model.bodies.map((body) => [body.id, body]));
  const values = {};
  for (const side of ["A", "B"]) {
    const local = inBodyFrame(bodies.get(joint[side.toLowerCase()]), feature.point, feature.axis);
    values[`anchor${side}`] = local.point;
    if (["revolute", "cylindrical"].includes(joint.type) || (joint.type === "prismatic" && side === "A")) values[`axis${side}`] = local.direction;
  }
  return values;
}

/**
 * A named frame placed on a picked feature, in its parent's axes: the origin at the feature point
 * and local +Z along the cylinder axis or plane normal. Rotation is Euler123 in degrees.
 */
export function frameFromFeature(model, frame, feature) {
  const body = model.bodies.find((item) => item.id === frame.body);
  const local = inBodyFrame(body, feature.point, feature.axis);
  const turn = new THREE.Quaternion().setFromUnitVectors(new THREE.Vector3(0, 0, 1), vector(local.direction).normalize());
  const euler = new THREE.Euler().setFromQuaternion(turn, "XYZ");
  // Near ry = ±90° the extraction amplifies the CAD axis tolerance; 1e-5° is far below modelling significance.
  const degrees = (angle) => Number((angle / DEG).toFixed(5)) || 0;
  return { translation: local.point, rotation: { rx: degrees(euler.x), ry: degrees(euler.y), rz: degrees(euler.z) } };
}

/** A body-frame point and direction in model world coordinates at the initial configuration. */
export function worldFromBody(body, point, direction) {
  if (!body) return { point: vector(point), direction: vector(direction).normalize() };
  const turn = rotation(body.pose);
  return { point: vector(point).applyQuaternion(turn).add(vector(body.pose)), direction: vector(direction).applyQuaternion(turn).normalize() };
}

const snap = (value, step) => (step > 0 ? Math.round(value / step) * step : value);

/**
 * The point on the line through `origin` along `axis` closest to `ray`, moved in `step`
 * increments from `origin`. Null when the ray runs along the line.
 */
export function alongAxis(origin, axis, ray, step = 0.001) {
  const u = axis.clone().normalize(), d = ray.direction.clone().normalize(), w = origin.clone().sub(ray.origin);
  const b = u.dot(d), denominator = 1 - b * b;
  if (denominator < 1e-9) return null;
  const offset = snap((b * d.dot(w) - u.dot(w)) / denominator, step);
  return { point: origin.clone().addScaledVector(u, offset), offset };
}

/**
 * Where `ray` meets the plane through `origin` with `normal`, moved in `step` increments along
 * two in-plane directions. Null when the ray runs parallel to the plane.
 */
export function inPlane(origin, normal, ray, step = 0.001) {
  const n = normal.clone().normalize(), along = ray.direction.dot(n);
  if (Math.abs(along) < 1e-9) return null;
  const hit = ray.origin.clone().addScaledVector(ray.direction, origin.clone().sub(ray.origin).dot(n) / along);
  const u = new THREE.Vector3().crossVectors(n, Math.abs(n.x) < 0.9 ? new THREE.Vector3(1, 0, 0) : new THREE.Vector3(0, 1, 0)).normalize();
  const v = new THREE.Vector3().crossVectors(n, u);
  const offset = hit.sub(origin), a = snap(offset.dot(u), step), c = snap(offset.dot(v), step);
  return { point: origin.clone().addScaledVector(u, a).addScaledVector(v, c), offset: Math.hypot(a, c) };
}

/** Distance between two picked features' points and, when both have axes, the angle between them. */
export function measureFeatures(first, second) {
  const distance = first.point.distanceTo(second.point);
  const angle = first.axis && second.axis ? Math.acos(Math.min(1, Math.abs(first.axis.dot(second.axis)))) / DEG : null;
  return { distance, angle, delta: second.point.clone().sub(first.point) };
}
