import * as THREE from "three";

const DEG = Math.PI / 180;
const MAX_PARTS = 512;
const MAX_COORDINATES = 3_000_000;
const MAX_INDICES = 6_000_000;

function point(value, context, spatial = false) {
  if (!value || ![value.x, value.y, value.z, value.ry].every(Number.isFinite) ||
      (spatial && ![value.rx, value.rz].every(Number.isFinite)) ||
      [value.x, value.y, value.z].some(n => Math.abs(n) > 1e6))
    throw new Error(`Invalid ${spatial ? "spatial" : "planar"} body pose for ${context}.`);
  return value;
}
function rotation(value, spatial) {
  return spatial
    ? new THREE.Quaternion().setFromEuler(new THREE.Euler(value.rx * DEG, value.ry * DEG, value.rz * DEG, "XYZ"))
    : new THREE.Quaternion().setFromAxisAngle(new THREE.Vector3(0, 1, 0), value.ry * DEG);
}
function normalizeOffset(value) {
  const xyz = Array.isArray(value) ? value : [value?.x, value?.y, value?.z];
  if (xyz.length !== 3 || !xyz.every(Number.isFinite) || xyz.some(n => Math.abs(n) > 1e6))
    throw new Error("Invalid STEP display offset.");
  return new THREE.Vector3(...xyz);
}
function validateGeometry(converted) {
  if (!converted || converted.units !== "m" || !Array.isArray(converted.parts) || !converted.parts.length || converted.parts.length > MAX_PARTS)
    throw new Error("STEP conversion must contain a bounded list of parts in metres.");
  const seen = new Set(); let coordinates = 0, indices = 0;
  for (const part of converted.parts) {
    if (!part || typeof part.id !== "string" || !part.id.length || part.id.length > 256 || seen.has(part.id))
      throw new Error("STEP part IDs must be unique nonempty strings.");
    seen.add(part.id);
    if (!Array.isArray(part.positions) || part.positions.length < 9 || part.positions.length % 3 ||
        !Array.isArray(part.indices) || part.indices.length < 3 || part.indices.length % 3)
      throw new Error(`STEP part ${part.id} has invalid triangles.`);
    coordinates += part.positions.length; indices += part.indices.length;
    if (coordinates > MAX_COORDINATES || indices > MAX_INDICES ||
        !part.positions.every(n => Number.isFinite(n) && Math.abs(n) <= 1e6) ||
        !part.indices.every(n => Number.isInteger(n) && n >= 0 && n < part.positions.length / 3))
      throw new Error(`STEP part ${part.id} exceeds geometry limits or has invalid coordinates or indices.`);
  }
  return seen;
}

/** Attach STEP solids using planar +Y or spatial Euler123 (Rx Ry Rz) body poses. */
export function createStepView(converted, {initialNodes = [], bindings = {}, offset = [0, 0, 0], entityForBody = id => `node-${id}`, entityForPart = id => `step-part-${id}`, colorForBody = null} = {}) {
  const partIds = validateGeometry(converted);
  if (!bindings || typeof bindings !== "object" || Array.isArray(bindings) || !Array.isArray(initialNodes))
    throw new Error("Invalid STEP body bindings.");
  const initial = new Map();
  for (const node of initialNodes) {
    if (!node || typeof node.id !== "string" || initial.has(node.id)) throw new Error("Invalid or duplicate initial body ID.");
    initial.set(node.id, point(node, node.id));
  }
  const displayOffset = normalizeOffset(offset);
  for (const [part, binding] of Object.entries(bindings)) {
    if (!partIds.has(part) || !binding || typeof binding !== "object" || Array.isArray(binding) ||
        Object.keys(binding).some(key => !["body", "pose"].includes(key)) ||
        typeof binding.body !== "string" || !initial.has(binding.body))
      throw new Error(`STEP binding ${part} refers to an unknown part or body.`);
    if (!binding.pose || typeof binding.pose !== "object" || Array.isArray(binding.pose) ||
        Object.keys(binding.pose).some(key => !["x", "y", "z", "rx", "ry", "rz"].includes(key)) ||
        Object.hasOwn(binding.pose, "rx") !== Object.hasOwn(binding.pose, "rz"))
      throw new Error(`STEP binding ${part} has an invalid registration pose.`);
    const spatial = Object.hasOwn(binding.pose, "rx");
    point(binding.pose, part, spatial);
    point(initial.get(binding.body), binding.body, spatial);
  }
  const group = new THREE.Group(), partMeshes = new Map(), attached = [];
  let disposed = false;
  try {
    for (const part of converted.parts) {
      const geometry = new THREE.BufferGeometry();
      geometry.setAttribute("position", new THREE.Float32BufferAttribute(part.positions, 3));
      geometry.setIndex(part.indices);
      geometry.computeVertexNormals(); geometry.computeBoundingBox();
      const name = String(part.name || "").toLowerCase();
      const boundBody = Object.hasOwn(bindings, part.id) ? bindings[part.id]?.body : null;
      const color = /tyre|tire/.test(name) ? 0x323b46 : /control arm/.test(name) ? 0x4b8ab1 : /knuckle/.test(name) ? 0xb38b59 : /rim/.test(name) ? 0xb9c2cc : boundBody && colorForBody ? colorForBody(boundBody) : 0xa5b6c6;
      const mesh = new THREE.Mesh(geometry, new THREE.MeshStandardMaterial({color, roughness:0.4, metalness:0.24}));
      mesh.castShadow = true; mesh.receiveShadow = true;
      mesh.name = typeof part.name === "string" ? part.name : part.id;
      mesh.userData.partId = part.id; mesh.userData.baseColor = color;
      const binding = Object.hasOwn(bindings, part.id) ? bindings[part.id] : null;
      const body = binding?.body;
      mesh.userData.entity = body ? entityForBody(body) : entityForPart(part.id);
      if (body) {
        const bind = binding.pose, spatial = Object.hasOwn(bind, "rx"), inverse = rotation(bind, spatial).invert();
        mesh.position.set(-bind.x, -bind.y, -bind.z).applyQuaternion(inverse);
        mesh.quaternion.copy(inverse);
        const frame = new THREE.Group(); frame.add(mesh); group.add(frame);
        attached.push({body, frame, spatial});
      } else {
        mesh.position.copy(displayOffset); group.add(mesh);
      }
      partMeshes.set(part.id, mesh);
    }
  } catch (error) {
    for (const mesh of partMeshes.values()) { mesh.geometry.dispose(); mesh.material.dispose(); }
    throw error;
  }
  function update(nodes) {
    if (disposed) throw new Error("STEP view has been disposed.");
    if (!Array.isArray(nodes)) throw new Error("STEP body poses must be an array.");
    const poses = new Map();
    for (const node of nodes) {
      if (!node || typeof node.id !== "string" || poses.has(node.id)) throw new Error("Invalid or duplicate STEP body pose ID.");
      poses.set(node.id, node);
    }
    for (const {body, spatial} of attached) point(poses.get(body), body, spatial);
    for (const {body, frame, spatial} of attached) {
      const pose = poses.get(body);
      frame.position.set(pose.x + displayOffset.x, pose.y + displayOffset.y, pose.z + displayOffset.z);
      frame.quaternion.copy(rotation(pose, spatial));
    }
    group.updateMatrixWorld(true);
  }
  function dispose() {
    if (disposed) return;
    disposed = true;
    group.removeFromParent();
    for (const mesh of partMeshes.values()) { mesh.geometry.dispose(); mesh.material.dispose(); }
    group.clear();
  }
  /** Farthest attached vertex from a body's origin, in body-local coordinates. */
  function farthestPoint(bodyId) {
    let best = null, distance = -1;
    for (const {body, frame} of attached) {
      if (body !== bodyId) continue;
      const mesh = frame.children[0], positions = mesh.geometry.getAttribute("position");
      const local = new THREE.Vector3();
      for (let i = 0; i < positions.count; i += Math.max(1, Math.floor(positions.count / 4000))) {
        local.fromBufferAttribute(positions, i).applyQuaternion(mesh.quaternion).add(mesh.position);
        const d = local.lengthSq();
        if (d > distance) { distance = d; best = local.clone(); }
      }
    }
    return best;
  }
  update(initialNodes);
  return {group, partMeshes, update, dispose, farthestPoint};
}
