import * as THREE from "three";

/**
 * Engineering glyphs for 3D assemblies: joint symbols at their anchors and along their axes,
 * spring and strut symbols between force anchors, and axis triads for named frames. Glyphs are
 * drawn over the geometry so joints buried inside CAD solids remain visible and selectable.
 */
const DEG = Math.PI / 180;
const UP = new THREE.Vector3(0, 1, 0);
export const JOINT_COLOR = 0xe08a1e;
export const FORCE_COLOR = 0x12a3a0;
const AXIS_COLORS = [0xd8434c, 0x3aa35a, 0x3a72d8];

const vector = (p) => new THREE.Vector3(p?.x || 0, p?.y || 0, p?.z || 0);
const eulerQuaternion = (p) => new THREE.Quaternion().setFromEuler(new THREE.Euler((p?.rx || 0) * DEG, (p?.ry || 0) * DEG, (p?.rz || 0) * DEG, "XYZ"));
const alongY = (axis) => {
  const direction = vector(axis);
  return direction.lengthSq() > 1e-12 ? new THREE.Quaternion().setFromUnitVectors(UP, direction.normalize()) : new THREE.Quaternion();
};

function material(color) {
  return new THREE.MeshStandardMaterial({ color, roughness: 0.45, metalness: 0.1, depthTest: false, depthWrite: false, transparent: true, opacity: 0.95 });
}
function part(group, geometry, color, entity, transform) {
  const mesh = new THREE.Mesh(geometry, material(color));
  mesh.renderOrder = 20;
  mesh.userData.entity = entity;
  mesh.userData.baseColor = color;
  mesh.userData.glyph = true;
  transform?.(mesh);
  group.add(mesh);
  return mesh;
}
const shaft = (g, length) => new THREE.CylinderGeometry(g * 0.07, g * 0.07, length, 10);
const ring = (g, radius) => new THREE.TorusGeometry(radius, g * 0.075, 8, 32);
const flat = (mesh) => mesh.rotation.set(Math.PI / 2, 0, 0); // torus axis from Z to Y

/** Symbol for one joint type, built along +Y in the joint frame. */
function jointSymbol(type, g, entity) {
  const group = new THREE.Group();
  if (type === "revolute") {
    part(group, shaft(g, g * 2.6), JOINT_COLOR, entity);
    part(group, ring(g, g * 0.55), JOINT_COLOR, entity, flat);
  } else if (type === "cylindrical") {
    part(group, shaft(g, g * 2.8), JOINT_COLOR, entity);
    for (const y of [-0.45, 0.45]) part(group, ring(g, g * 0.5), JOINT_COLOR, entity, (m) => { flat(m); m.position.y = y * g; });
  } else if (type === "prismatic") {
    part(group, shaft(g, g * 2.4), JOINT_COLOR, entity);
    for (const sign of [-1, 1])
      part(group, new THREE.ConeGeometry(g * 0.22, g * 0.5, 14), JOINT_COLOR, entity, (m) => { m.position.y = sign * g * 1.3; if (sign < 0) m.rotation.z = Math.PI; });
    part(group, new THREE.BoxGeometry(g * 0.55, g * 0.7, g * 0.55), JOINT_COLOR, entity);
  } else if (type === "spherical") {
    part(group, new THREE.SphereGeometry(g * 0.42, 20, 14), JOINT_COLOR, entity);
    part(group, ring(g, g * 0.62), JOINT_COLOR, entity, flat);
  } else if (type === "weld") {
    part(group, new THREE.BoxGeometry(g * 0.7, g * 0.7, g * 0.7), JOINT_COLOR, entity);
  } else {
    part(group, new THREE.SphereGeometry(g * 0.3, 16, 12), JOINT_COLOR, entity);
  }
  return group;
}

/** Coil of unit length along +Y; scaled to the current anchor distance every frame. */
function coilGeometry(g) {
  const turns = 7, points = [];
  for (let i = 0; i <= turns * 24; i++) {
    const t = i / (turns * 24), angle = t * turns * Math.PI * 2;
    const r = t < 0.1 || t > 0.9 ? 0 : g * 0.38;
    points.push(new THREE.Vector3(r * Math.cos(angle), t - 0.5, r * Math.sin(angle)));
  }
  return new THREE.TubeGeometry(new THREE.CatmullRomCurve3(points), 220, g * 0.045, 6, false);
}

/** Build glyphs for a spatial model. `offset` is the view offset applied to all world points. */
export function buildGlyphs(model, scale, offset) {
  const g = Math.max(scale, 0.05) * 0.045;
  const group = new THREE.Group();
  group.name = "glyphs";
  const items = [];
  const bodies = new Map((model.bodies || []).map((body) => [body.id, body]));
  for (const joint of model.joints || []) {
    const entity = `joint-${joint.id}`;
    // Follow the moving side; a joint grounded on side B is drawn on side A.
    const side = joint.b !== "ground" && bodies.has(joint.b) ? "B" : "A";
    const body = joint[side.toLowerCase()];
    const anchor = vector(joint[`anchor${side}`]);
    if (joint.type === "universal") {
      // One bar on each body: the two cross arms of the spider.
      for (const end of ["A", "B"]) {
        const owner = joint[end.toLowerCase()];
        const arm = new THREE.Group();
        part(arm, shaft(g, g * 2.2), JOINT_COLOR, entity);
        for (const sign of [-1, 1]) part(arm, new THREE.SphereGeometry(g * 0.16, 12, 8), JOINT_COLOR, entity, (m) => { m.position.y = sign * g * 1.1; });
        group.add(arm);
        items.push({ object: arm, body: owner, anchor: vector(joint[`anchor${end}`]), axis: alongY(joint[`axis${end}`]) });
      }
      const hub = new THREE.Group();
      part(hub, new THREE.SphereGeometry(g * 0.26, 16, 12), JOINT_COLOR, entity);
      group.add(hub);
      items.push({ object: hub, body, anchor, axis: new THREE.Quaternion() });
      continue;
    }
    const symbol = jointSymbol(joint.type, g, entity);
    group.add(symbol);
    items.push({ object: symbol, body, anchor, axis: alongY(joint[`axis${side}`] || { x: 0, y: 0, z: 1 }) });
  }
  const links = [];
  for (const force of model.forces || []) {
    const entity = `force-${force.id}`;
    const object = new THREE.Group();
    if (force.type === "oleo-strut") {
      part(object, new THREE.CylinderGeometry(g * 0.32, g * 0.32, 0.55, 18), FORCE_COLOR, entity, (m) => { m.position.y = -0.225; });
      part(object, new THREE.CylinderGeometry(g * 0.17, g * 0.17, 0.6, 14), FORCE_COLOR, entity, (m) => { m.position.y = 0.2; });
    } else {
      part(object, coilGeometry(g), FORCE_COLOR, entity);
    }
    const ends = ["a", "b"].map((key) => {
      const ball = part(group, new THREE.SphereGeometry(g * 0.2, 12, 8), FORCE_COLOR, entity);
      return { ball, body: force[key], anchor: vector(force[`anchor${key.toUpperCase()}`]) };
    });
    group.add(object);
    links.push({ object, ends, g });
  }
  const frames = [];
  for (const frame of model.frames || []) {
    if (frame.body !== "ground" && !bodies.has(frame.body)) continue;
    const triad = new THREE.Group();
    for (const [index, axis] of [new THREE.Vector3(1, 0, 0), new THREE.Vector3(0, 1, 0), new THREE.Vector3(0, 0, 1)].entries()) {
      const arrow = new THREE.Group();
      part(arrow, shaft(g * 0.7, g * 1.6), AXIS_COLORS[index], null, (m) => { m.position.y = g * 0.8; });
      part(arrow, new THREE.ConeGeometry(g * 0.14, g * 0.36, 12), AXIS_COLORS[index], null, (m) => { m.position.y = g * 1.75; });
      arrow.quaternion.setFromUnitVectors(UP, axis);
      triad.add(arrow);
    }
    group.add(triad);
    items.push({ object: triad, body: frame.body, anchor: vector(frame.translation), axis: eulerQuaternion(frame.rotation) });
    frames.push(triad);
  }
  return { group, items, links, offset: offset.clone(), size: g };
}

/** Place every glyph for body poses `nodes` (id, x, y, z, rx, ry, rz in degrees, Euler123). */
export function updateGlyphs(glyphs, nodes) {
  if (!glyphs) return;
  const poses = new Map();
  for (const node of nodes || []) poses.set(String(node.id), { position: vector(node), quaternion: eulerQuaternion(node) });
  const ground = { position: new THREE.Vector3(), quaternion: new THREE.Quaternion() };
  const world = (body, anchor) => {
    const pose = poses.get(String(body)) || ground;
    return anchor.clone().applyQuaternion(pose.quaternion).add(pose.position).add(glyphs.offset);
  };
  for (const item of glyphs.items) {
    const pose = poses.get(String(item.body)) || ground;
    item.object.position.copy(world(item.body, item.anchor));
    item.object.quaternion.copy(pose.quaternion).multiply(item.axis);
  }
  for (const { object, ends } of glyphs.links) {
    const [a, b] = ends.map(({ ball, body, anchor }) => {
      const point = world(body, anchor);
      ball.position.copy(point);
      return point;
    });
    const delta = b.clone().sub(a), length = delta.length();
    object.visible = length > 1e-9;
    if (!object.visible) continue;
    object.position.copy(a).add(b).multiplyScalar(0.5);
    object.quaternion.setFromUnitVectors(UP, delta.normalize());
    object.scale.set(1, length, 1);
  }
}

export function disposeGlyphs(glyphs) {
  glyphs?.group.traverse((object) => {
    object.geometry?.dispose();
    object.material?.dispose();
  });
}
