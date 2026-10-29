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

/** The analytic face containing a triangle of a converted part, if the converter described it. */
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

/** Distance between two picked features' points and, when both have axes, the angle between them. */
export function measureFeatures(first, second) {
  const distance = first.point.distanceTo(second.point);
  const angle = first.axis && second.axis ? Math.acos(Math.min(1, Math.abs(first.axis.dot(second.axis)))) / DEG : null;
  return { distance, angle, delta: second.point.clone().sub(first.point) };
}
