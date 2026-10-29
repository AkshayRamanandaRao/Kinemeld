import * as THREE from "three";

/** Display native node origins and a schematic connection graph, never a CAD solid. */
export function buildSourceView(view, example) {
  const nodes = example?.initialNodes || [];
  if (!nodes.length)
    throw new Error(
      "This source model has no verified initial node coordinates.",
    );
  const bounds = new THREE.Box3();
  for (const node of nodes)
    bounds.expandByPoint(new THREE.Vector3(node.x, node.y, node.z));
  const center = bounds.getCenter(new THREE.Vector3());
  const size = bounds.getSize(new THREE.Vector3());
  const scale = Math.max(size.x, size.y, size.z, 0.1);
  const offset = new THREE.Vector3(
    -center.x,
    -center.y,
    -bounds.min.z + scale * 0.1,
  );
  view.scale = scale;
  view.sourceParts = {
    offset,
    focus: new THREE.Vector3(0, 0, size.z / 2 + scale * 0.1),
    nodes: new Map(),
    links: [],
  };
  for (const [index, node] of nodes.entries()) {
    const entity = index === 0 ? "body" : `node-${node.id}`;
    const point = new THREE.Vector3(node.x, node.y, node.z).add(offset);
    const mesh = view.mesh(
      new THREE.SphereGeometry(scale * 0.035, 20, 14),
      index ? 0x159aa4 : 0x2678da,
      point,
      entity,
    );
    view.sourceParts.nodes.set(String(node.id), mesh);
    if (!index) view.bob = mesh;
    if (nodes.length <= 12) {
      const description = example.nodes.find(
        (item) => String(item.id) === String(node.id),
      );
      view.label(description?.label || node.label || `Node ${node.id}`, () => mesh.position);
    }
  }
  for (const connection of example.connections || []) {
    const a = view.sourceParts.nodes.get(String(connection.from));
    const b = view.sourceParts.nodes.get(String(connection.to));
    if (!a || !b || a.position.distanceTo(b.position) < 1e-9) continue;
    const line = view.mesh(
      new THREE.CylinderGeometry(scale * 0.012, scale * 0.012, 1, 12),
      0x7299b6,
      new THREE.Vector3(),
      connection.entity || (connection.id ? `joint-${connection.id}` : "joint"),
    );
    view.sourceParts.links.push({ line, a, b });
  }
  // Contact planes are part of the solver model, so draw them where MBDyn places them.
  const drawnPlanes = new Set();
  for (const contact of view.model?.contacts || []) {
    const key = JSON.stringify([contact.planePoint, contact.planeNormal]);
    if (drawnPlanes.has(key)) continue;
    drawnPlanes.add(key);
    const normal = new THREE.Vector3(contact.planeNormal.x, contact.planeNormal.y, contact.planeNormal.z).normalize();
    const size = scale * 2.2;
    const plane = new THREE.Mesh(
      new THREE.BoxGeometry(size, size, scale * 0.012),
      new THREE.MeshStandardMaterial({ color: 0x8a96a8, roughness: 0.85, metalness: 0, transparent: true, opacity: 0.55 }),
    );
    plane.receiveShadow = true;
    plane.quaternion.setFromUnitVectors(new THREE.Vector3(0, 0, 1), normal);
    plane.position.set(contact.planePoint.x, contact.planePoint.y, contact.planePoint.z).add(offset).addScaledVector(normal, -scale * 0.006);
    plane.userData.entity = `contact-${contact.id}`;
    plane.userData.baseColor = 0x8a96a8;
    view.group.add(plane);
  }
  sampleSourceView(view, { nodes });
}

export function sampleSourceView(view, sample) {
  const parts = view.sourceParts;
  for (const node of sample?.nodes || []) {
    const mesh = parts.nodes.get(String(node.id));
    if (mesh) mesh.position.set(node.x, node.y, node.z).add(parts.offset);
  }
  for (const { line, a, b } of parts.links) {
    const delta = b.position.clone().sub(a.position);
    line.position.copy(a.position).add(b.position).multiplyScalar(0.5);
    line.scale.y = delta.length();
    if (delta.lengthSq() > 1e-16)
      line.quaternion.setFromUnitVectors(
        new THREE.Vector3(0, 1, 0),
        delta.normalize(),
      );
  }
}
