import * as THREE from "three";

const vector = (x = 0, y = 0, z = 0) => new THREE.Vector3(x, y, z);

function wheel(view, radius, width, entity) {
  const group = new THREE.Group();
  view.group.add(group);
  for (const [r, w, color] of [
    [radius, width, 0x263343],
    [radius * 0.59, width * 1.03, 0xa8bacb],
    [radius * 0.2, width * 1.1, 0x426b90],
  ]) {
    const part = view.mesh(
      new THREE.CylinderGeometry(r, r, w, 40),
      color,
      vector(),
      entity,
    );
    group.add(part);
  }
  return group;
}

function movingLink(view, radius, color, entity) {
  return view.mesh(
    new THREE.CylinderGeometry(radius, radius, 1, 24),
    color,
    vector(),
    entity,
  );
}

function poseLink(mesh, a, b) {
  const delta = b.clone().sub(a);
  mesh.position.copy(a).add(b).multiplyScalar(0.5);
  mesh.scale.y = delta.length();
  if (delta.lengthSq() > 1e-16)
    mesh.quaternion.setFromUnitVectors(vector(0, 1, 0), delta.normalize());
}

export function buildIndustry(view) {
  if (view.model.kind === "gear-deployment") return buildDeployment(view);
  const drop = view.model.kind === "landing-gear-drop";
  const p = view.model.parameters;
  const radius = drop ? 0.22 : 0.28;
  view.scale = drop
    ? Math.max(1.25, p.strutLength + radius + p.dropHeight)
    : 1.25;
  view.industryParts = { radius, drop };
  const parts = view.industryParts;
  parts.road = view.mesh(
    new THREE.BoxGeometry(2, 1.05, 0.07),
    0x7c8da2,
    vector(0, 0, -0.035),
    "ground",
  );
  for (const x of [-0.72, 0.72]) {
    const stripe = view.mesh(
      new THREE.BoxGeometry(0.02, 0.6, 0.003),
      0xc9d2dd,
      vector(x, 0, 0.002),
      "ground",
    );
    parts.road.attach(stripe);
  }
  view.bob = view.mesh(
    new THREE.BoxGeometry(drop ? 0.78 : 1.08, 0.66, 0.2),
    0x317bd1,
    vector(),
    "body",
  );
  parts.mount = view.mesh(
    new THREE.BoxGeometry(0.23, 0.29, 0.14),
    0x516c86,
    vector(0, 0, -0.15),
    "body",
  );
  view.bob.add(parts.mount);
  // The drop rig's second visible tire shares the one modelled unsprung coordinate.
  view.bob2 = new THREE.Group();
  view.group.add(view.bob2);
  for (const y of drop ? [-0.2, 0.2] : [0]) {
    const tire = wheel(view, radius, drop ? 0.17 : 0.26, "body2");
    tire.position.y = y;
    view.bob2.add(tire);
  }
  parts.axle = movingLink(view, 0.045, 0x8fa7bc, "body2");
  parts.barrel = movingLink(view, drop ? 0.075 : 0.048, 0x7493ac, "spring");
  parts.piston = movingLink(view, 0.029, 0xc5d7e6, "spring");
  parts.coil = view.mesh(
    new THREE.BufferGeometry(),
    0x16a0a5,
    vector(),
    "spring",
  );
  parts.coil.visible = !drop;
  if (drop) {
    // Stationary lab guides are context geometry; only two vertical translations are solved.
    for (const x of [-0.56, 0.56])
      view.link(
        vector(x, 0.36, 0.05),
        vector(x, 0.36, view.scale * 1.2),
        0.024,
        0x9eafbf,
        "joint",
      );
  }
  view.label(drop ? "Airframe mass" : "Sprung body", () =>
    view.bob.position.clone().add(vector(0.2, 0, 0.18)),
  );
  view.label(drop ? "Shock strut" : "Spring + damper", () =>
    view.bob.position
      .clone()
      .add(view.bob2.position)
      .multiplyScalar(0.5)
      .add(vector(0.1, 0, 0)),
  );
  view.label(drop ? "Wheel pair · one mass" : "Wheel assembly", () =>
    view.bob2.position.clone().add(vector(0.1, 0, -radius * 0.2)),
  );
  view.label(drop ? "Runway · contact" : "Road input", () =>
    vector(-0.75, -0.3, parts.road.position.z),
  );
  sampleIndustry(view, null);
}

export function sampleIndustry(view, sample) {
  if (view.model.kind === "gear-deployment")
    return sampleDeployment(view, sample);
  const p = view.model.parameters,
    parts = view.industryParts;
  const { drop, radius } = parts;
  const wheelZ = radius + (sample?.zUnsprung ?? (drop ? p.dropHeight : 0));
  const bodyZ =
    (drop ? radius : 1.15) +
    (sample?.zSprung ?? (drop ? p.dropHeight + p.strutLength : 0));
  view.bob.position.set(0, 0, bodyZ);
  view.bob2.position.set(0, 0, wheelZ);
  parts.road.position.z = (sample?.road ?? 0) - 0.035;
  poseLink(parts.axle, vector(0, -0.33, wheelZ), vector(0, 0.33, wheelZ));
  const lower = vector(0, 0, wheelZ),
    upper = vector(0, 0, bodyZ - 0.1);
  poseLink(parts.barrel, upper, upper.clone().lerp(lower, 0.57));
  poseLink(parts.piston, lower, upper.clone().lerp(lower, 0.3));
  if (!drop) {
    const points = [];
    for (let i = 0; i <= 100; i++) {
      const fraction = i / 100,
        a = fraction * Math.PI * 16;
      points.push(
        vector(
          Math.sin(a) * 0.095,
          Math.cos(a) * 0.095,
          wheelZ + 0.07 + fraction * (bodyZ - wheelZ - 0.24),
        ),
      );
    }
    parts.coil.geometry.dispose();
    parts.coil.geometry = new THREE.TubeGeometry(
      new THREE.CatmullRomCurve3(points),
      100,
      0.012,
      8,
      false,
    );
  }
}

function initialDeployment(p) {
  const a = (p.initialAngle * Math.PI) / 180;
  const bx = p.braceAttachment * Math.sin(a),
    bz = -p.braceAttachment * Math.cos(a);
  const dx = p.groundX - bx,
    dz = p.groundZ - bz,
    d = Math.hypot(dx, dz);
  if (
    d < 1e-9 ||
    d >= p.upperBraceLength + p.lowerBraceLength ||
    d <= Math.abs(p.upperBraceLength - p.lowerBraceLength)
  )
    return null;
  const along =
    (p.upperBraceLength ** 2 - p.lowerBraceLength ** 2 + d ** 2) / (2 * d);
  const height = Math.sqrt(Math.max(0, p.upperBraceLength ** 2 - along ** 2));
  return {
    bx,
    bz,
    cx: bx + (along * dx) / d - (height * dz) / d,
    cz: bz + (along * dz) / d + (height * dx) / d,
    wheelX: p.mainLength * Math.sin(a),
    wheelZ: -p.mainLength * Math.cos(a),
  };
}

function buildDeployment(view) {
  const p = view.model.parameters;
  view.scale = p.mainLength * 1.3;
  const lift = p.mainLength + 0.34;
  view.industryParts = { lift };
  const parts = view.industryParts;
  const anchor = (x, z) => vector(x, 0, z + lift);
  parts.a = anchor(0, 0);
  parts.d = anchor(p.groundX, p.groundZ);
  parts.actuatorAnchor = anchor(p.actuatorAnchorX, p.actuatorAnchorZ);
  // Open bay frame supplies context without implying a dimensioned Orbiter airframe.
  for (const y of [-0.42, 0.42]) {
    view.link(
      vector(-p.mainLength, y, lift + 0.2),
      vector(p.groundX + 0.2, y, lift + 0.2),
      0.025,
      0x8395ab,
      "ground",
    );
    for (const x of [0, p.groundX])
      view.link(
        vector(x, y, lift + 0.2),
        vector(x, y, lift - 0.1),
        0.04,
        0x8395ab,
        "ground",
      );
  }
  for (const position of [parts.a, parts.d, parts.actuatorAnchor])
    view.mesh(
      new THREE.CylinderGeometry(0.065, 0.065, 0.33, 24),
      0x4d6683,
      position.clone(),
      "ground",
    );
  view.bob = movingLink(view, 0.055, 0x317bd1, "body");
  parts.upper = movingLink(view, 0.032, 0x13a2a6, "body2");
  parts.lower = movingLink(view, 0.032, 0x13a2a6, "body3");
  parts.actuator = movingLink(view, 0.042, 0x8299b3, "drive");
  parts.piston = movingLink(view, 0.023, 0xc1d7e8, "drive");
  parts.wheels = new THREE.Group();
  view.group.add(parts.wheels);
  for (const y of [-0.2, 0.2]) {
    const tire = wheel(view, 0.2, 0.16, "body");
    tire.position.y = y;
    parts.wheels.add(tire);
  }
  parts.b = view.mesh(
    new THREE.CylinderGeometry(0.065, 0.065, 0.15, 24),
    0xd3e4eb,
    vector(),
    "joint",
  );
  parts.c = view.mesh(
    new THREE.CylinderGeometry(0.06, 0.06, 0.15, 24),
    0xd3e4eb,
    vector(),
    "joint",
  );
  view.label("Trunnion · A", () =>
    parts.a.clone().add(vector(-0.4, -0.15, 0.3)),
  );
  view.label("Folding brace · C", () =>
    parts.c.position.clone().add(vector(0.15, 0, -0.12)),
  );
  view.label("Gear + wheel pair", () =>
    parts.wheels.position.clone().add(vector(0.16, 0, 0)),
  );
  sampleDeployment(view, null);
}

function sampleDeployment(view, sample) {
  const parts = view.industryParts,
    pose = sample || initialDeployment(view.model.parameters);
  if (!pose) return;
  const b = vector(pose.bx, 0, pose.bz + parts.lift),
    c = vector(pose.cx, 0, pose.cz + parts.lift);
  const w = vector(pose.wheelX, 0, pose.wheelZ + parts.lift);
  poseLink(view.bob, parts.a, w);
  poseLink(parts.upper, b, c);
  poseLink(parts.lower, c, parts.d);
  poseLink(
    parts.actuator,
    parts.actuatorAnchor,
    parts.actuatorAnchor.clone().lerp(b, 0.6),
  );
  poseLink(parts.piston, parts.actuatorAnchor.clone().lerp(b, 0.45), b);
  parts.b.position.copy(b);
  parts.c.position.copy(c);
  parts.wheels.position.copy(w);
}
