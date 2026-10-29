import * as THREE from "three";
import { OrbitControls } from "./vendor/OrbitControls.js";
import { buildIndustry, sampleIndustry } from "./industry-view.js";
import { buildSourceView, sampleSourceView } from "./source-view.js";
import { createStepView } from "./step-view.js";

const DEG = Math.PI / 180;
const BODY_COLORS = [0x5b8fd0, 0xd99a4e, 0x5aae8a, 0xa982c9, 0xcf6d6d, 0x8fa54e, 0x4fb0c6, 0xc7a64a];
const TRAIL_COLORS = [0x2f74d0, 0xe0821e, 0x13998f, 0xb04fc9, 0xd2453f, 0x6c8f1f, 0x8a6a3f, 0x3fa0d8];

/** Parameter-driven visualization only; motion samples always come from the selected run. */
export class MechanismView {
  constructor(mount, onSelect) {
    this.mount = mount;
    this.scene = new THREE.Scene();
    this.camera = new THREE.PerspectiveCamera(35, 1, 0.01, 100);
    this.camera.up.set(0, 0, 1);
    this.renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true });
    this.renderer.setPixelRatio(Math.min(devicePixelRatio, 2));
    this.renderer.setClearColor(0, 0);
    this.renderer.shadowMap.enabled = true;
    this.renderer.shadowMap.type = THREE.PCFShadowMap;
    this.renderer.outputColorSpace = THREE.SRGBColorSpace;
    mount.append(this.renderer.domElement);
    this.controls = new OrbitControls(this.camera, this.renderer.domElement);
    this.controls.enableDamping = true;
    this.controls.minDistance = 0.5;
    this.controls.maxDistance = 15;
    this.controls.maxPolarAngle = Math.PI * 0.85;
    this.scene.add(new THREE.HemisphereLight(0xdceaff, 0x6d778a, 2.8));
    const key = new THREE.DirectionalLight(0xffffff, 3.3);
    key.position.set(3, -4, 7);
    key.castShadow = true;
    key.shadow.mapSize.set(1024, 1024);
    key.shadow.camera.left = -3;
    key.shadow.camera.right = 3;
    key.shadow.camera.top = 3;
    key.shadow.camera.bottom = -3;
    key.shadow.normalBias = 0.015;
    this.scene.add(key);
    const fill = new THREE.DirectionalLight(0x91baff, 1.6);
    fill.position.set(-3, 2, 2);
    this.scene.add(fill);
    this.group = new THREE.Group();
    this.scene.add(this.group);
    this.referenceGroup = new THREE.Group();
    this.scene.add(this.referenceGroup);
    this.grid = new THREE.GridHelper(8, 40, 0xbdc9d8, 0xd4dde7);
    this.grid.rotation.x = Math.PI / 2;
    this.grid.position.z = -0.075;
    this.scene.add(this.grid);
    this.floor = new THREE.Mesh(
      new THREE.PlaneGeometry(20, 20),
      new THREE.ShadowMaterial({ opacity: 0.13 }),
    );
    this.floor.position.z = -0.08;
    this.floor.receiveShadow = true;
    this.scene.add(this.floor);
    this.labels = [];
    this.raycaster = new THREE.Raycaster();
    let down;
    this.renderer.domElement.addEventListener("pointerdown", (e) => {
      down = [e.clientX, e.clientY];
    });
    this.renderer.domElement.addEventListener("pointerup", (e) => {
      if (!down || Math.hypot(e.clientX - down[0], e.clientY - down[1]) > 5)
        return;
      const rect = this.renderer.domElement.getBoundingClientRect();
      this.raycaster.setFromCamera(
        new THREE.Vector2(
          ((e.clientX - rect.left) / rect.width) * 2 - 1,
          (-(e.clientY - rect.top) / rect.height) * 2 + 1,
        ),
        this.camera,
      );
      const hit = this.raycaster
        .intersectObjects(this.group.children, true)
        .find((item) => item.object.userData.entity);
      if (hit) onSelect(hit.object.userData.entity);
    });
    this.resizeObserver = new ResizeObserver(() => this.resize());
    this.resizeObserver.observe(mount);
    this.resize();
    this.renderer.setAnimationLoop(() => {
      this.controls.update();
      this.renderer.render(this.scene, this.camera);
      this.positionLabels();
    });
  }
  resize() {
    const { width, height } = this.mount.getBoundingClientRect();
    if (!width || !height) return;
    this.camera.aspect = width / height;
    this.camera.updateProjectionMatrix();
    this.renderer.setSize(width, height);
  }
  material(color, metalness = 0.15) {
    return new THREE.MeshStandardMaterial({
      color,
      roughness: 0.38,
      metalness,
    });
  }
  mesh(geometry, color, position, entity = null) {
    const mesh = new THREE.Mesh(geometry, this.material(color));
    mesh.position.copy(position);
    mesh.castShadow = true;
    mesh.receiveShadow = true;
    mesh.userData.entity = entity;
    mesh.userData.baseColor = color;
    this.group.add(mesh);
    return mesh;
  }
  link(a, b, radius, color, entity) {
    const delta = b.clone().sub(a);
    const mesh = this.mesh(
      new THREE.CylinderGeometry(radius, radius, delta.length(), 24),
      color,
      a.clone().add(b).multiplyScalar(0.5),
      entity,
    );
    mesh.quaternion.setFromUnitVectors(
      new THREE.Vector3(0, 1, 0),
      delta.normalize(),
    );
    return mesh;
  }
  label(text, anchor) {
    const element = document.createElement("div");
    element.className = "object-label";
    element.textContent = text;
    this.mount.append(element);
    this.labels.push({ element, anchor });
  }
  positionLabels() {
    const { width, height } = this.mount.getBoundingClientRect();
    const placed = [];
    for (const { element, anchor } of this.labels) {
      const pos = anchor().clone().project(this.camera);
      element.style.display = pos.z < 1 && pos.z > -1 ? "" : "none";
      let x = ((pos.x + 1) * width) / 2 + 15;
      let y = ((-pos.y + 1) * height) / 2 - 8;
      if (
        ["source-example", "planar-assembly", "spatial-assembly"].includes(this.model?.kind) &&
        element.style.display !== "none"
      ) {
        const w = element.offsetWidth,
          h = element.offsetHeight;
        x = Math.max(0, Math.min(x, width - w));
        for (const other of placed)
          if (
            x < other.x + other.w &&
            x + w > other.x &&
            y < other.y + other.h &&
            y + h > other.y
          )
            y = other.y + other.h + 3;
        y = Math.max(0, Math.min(y, height - h));
        placed.push({ x, y, w, h });
      }
      element.style.left = `${x}px`;
      element.style.top = `${y}px`;
    }
  }
  clear() {
    this.stepView?.dispose();
    this.stepView = null;
    for (const label of this.labels) label.element.remove();
    this.labels = [];
    this.group.traverse((obj) => {
      obj.geometry?.dispose();
      if (Array.isArray(obj.material)) obj.material.forEach((m) => m.dispose());
      else obj.material?.dispose();
    });
    this.group.clear();
  }
  setModel(model, reset = false, sourceExample = null) {
    this.model = structuredClone(model);
    this.sourceMetadata = sourceExample;
    this.setTrails(null);
    this.followLast = null;
    this.clear();
    if (["source-example", "planar-assembly", "spatial-assembly"].includes(model.kind)) buildSourceView(this, sourceExample);
    else if (model.kind === "double-pendulum") this.buildDoublePendulum();
    else if (model.kind === "pendulum") this.buildPendulum();
    else if (model.kind === "mass-spring") this.buildSpring();
    else buildIndustry(this);
    this.renderStep();
    this.placeGround();
    if (this.referenceMesh) this.placeReference();
    if (this.isolatedReference) this.showLabels(false);
    this.setSelection(this.selection || "body");
    if (reset) this.reset();
  }
  buildPendulum() {
    const length = this.model.parameters.length;
    this.scale = length;
    const s = length;
    this.pivot = new THREE.Vector3(0, 0, s * 1.05);
    this.mesh(
      new THREE.BoxGeometry(0.55 * s, 0.48 * s, 0.09 * s),
      0x909fb3,
      new THREE.Vector3(0, 0.18 * s, -0.025 * s),
      "ground",
    );
    this.mesh(
      new THREE.BoxGeometry(0.08 * s, 0.08 * s, 1.1 * s),
      0xa7b4c6,
      new THREE.Vector3(0, 0.23 * s, 0.55 * s),
      "ground",
    );
    this.mesh(
      new THREE.BoxGeometry(0.23 * s, 0.34 * s, 0.14 * s),
      0x52657f,
      new THREE.Vector3(0, 0.12 * s, 1.05 * s),
      "joint",
    );
    this.mesh(
      new THREE.CylinderGeometry(0.075 * s, 0.075 * s, 0.27 * s, 32),
      0x7d9fc4,
      this.pivot.clone(),
      "joint",
    );
    this.bob = this.mesh(
      new THREE.SphereGeometry(0.115 * s, 40, 28),
      0x2678da,
      new THREE.Vector3(),
      "body",
    );
    this.rod = this.mesh(
      new THREE.CylinderGeometry(0.022 * s, 0.022 * s, s, 24),
      0x4c8fdc,
      new THREE.Vector3(),
      "body",
    );
    const arcPoints = [];
    for (let i = 0; i <= 100; i++) {
      const a = ((-55 + i * 1.1) * Math.PI) / 180;
      arcPoints.push(
        new THREE.Vector3(s * Math.sin(a), 0, this.pivot.z - s * Math.cos(a)),
      );
    }
    const arc = new THREE.Line(
      new THREE.BufferGeometry().setFromPoints(arcPoints),
      new THREE.LineDashedMaterial({
        color: 0x8fa8c7,
        dashSize: 0.025 * s,
        gapSize: 0.02 * s,
      }),
    );
    arc.computeLineDistances();
    this.group.add(arc);
    this.label("Ground · fixed", () =>
      this.pivot.clone().add(new THREE.Vector3(-0.15 * s, 0.07 * s, 0.12 * s)),
    );
    this.label("Point mass", () => this.bob.position);
    this.setSample(null);
  }
  buildSpring() {
    const s = Math.max(1, Math.abs(this.model.parameters.displacement) * 3);
    this.scale = s;
    this.mesh(
      new THREE.BoxGeometry(1.8 * s, 0.5 * s, 0.07 * s),
      0x9baabe,
      new THREE.Vector3(0.2 * s, 0, -0.04 * s),
      "ground",
    );
    this.mesh(
      new THREE.BoxGeometry(0.09 * s, 0.42 * s, 0.48 * s),
      0x5f728c,
      new THREE.Vector3(-0.6 * s, 0, 0.2 * s),
      "ground",
    );
    for (const y of [-0.15 * s, 0.15 * s])
      this.link(
        new THREE.Vector3(-0.6 * s, y, 0.08 * s),
        new THREE.Vector3(0.95 * s, y, 0.08 * s),
        0.018 * s,
        0xa8bcd5,
        "joint",
      );
    this.bob = this.mesh(
      new THREE.BoxGeometry(0.31 * s, 0.34 * s, 0.28 * s),
      0x2678da,
      new THREE.Vector3(0.1, 0, 0.24 * s),
      "body",
    );
    this.label(
      "Ground · fixed",
      () => new THREE.Vector3(-0.62 * s, 0, 0.48 * s),
    );
    this.label("Translating mass", () =>
      this.bob.position.clone().add(new THREE.Vector3(0.12 * s, 0, 0.1 * s)),
    );
    this.spring = new THREE.Mesh(
      new THREE.BufferGeometry(),
      this.material(0x7196bd, 0.6),
    );
    this.spring.castShadow = true;
    this.spring.userData.entity = "joint";
    this.group.add(this.spring);
    this.setSample(null);
  }
  buildDoublePendulum() {
    const p = this.model.parameters,
      s = p.length1 + p.length2;
    this.scale = s;
    this.pivot = new THREE.Vector3(0, 0, s * 1.05);
    this.mesh(
      new THREE.BoxGeometry(0.32 * s, 0.3 * s, 0.05 * s),
      0x909fb3,
      new THREE.Vector3(0, 0.12 * s, -0.02 * s),
      "ground",
    );
    this.mesh(
      new THREE.BoxGeometry(0.045 * s, 0.045 * s, 1.07 * s),
      0xa7b4c6,
      new THREE.Vector3(0, 0.15 * s, 0.535 * s),
      "ground",
    );
    this.mesh(
      new THREE.BoxGeometry(0.16 * s, 0.22 * s, 0.09 * s),
      0x52657f,
      new THREE.Vector3(0, 0.075 * s, 1.05 * s),
      "joint",
    );
    this.mesh(
      new THREE.CylinderGeometry(0.04 * s, 0.04 * s, 0.14 * s, 24),
      0x7d9fc4,
      this.pivot.clone(),
      "joint",
    );
    this.bob = this.mesh(
      new THREE.SphereGeometry(0.055 * s, 32, 24),
      0x2678da,
      new THREE.Vector3(),
      "body",
    );
    this.bob2 = this.mesh(
      new THREE.SphereGeometry(0.055 * s, 32, 24),
      0x1ba9b1,
      new THREE.Vector3(),
      "body2",
    );
    this.pin2 = this.mesh(
      new THREE.CylinderGeometry(0.035 * s, 0.035 * s, 0.17 * s, 24),
      0x7d9fc4,
      new THREE.Vector3(),
      "joint2",
    );
    this.rod = this.mesh(
      new THREE.CylinderGeometry(0.014 * s, 0.014 * s, p.length1, 24),
      0x4c8fdc,
      new THREE.Vector3(),
      "body",
    );
    this.rod2 = this.mesh(
      new THREE.CylinderGeometry(0.014 * s, 0.014 * s, p.length2, 24),
      0x49b8bc,
      new THREE.Vector3(),
      "body2",
    );
    this.label("Ground · fixed", () =>
      this.pivot.clone().add(new THREE.Vector3(-0.1 * s, 0, 0.07 * s)),
    );
    this.label("Mass 1 · link 1", () => this.bob.position);
    this.label("Mass 2 · link 2", () => this.bob2.position);
    this.setSample(null);
  }
  setSample(sample) {
    this.applySample(sample);
    if (this.followEntity) this.applyFollow();
  }
  applySample(sample) {
    if (!this.model || !this.bob) return;
    if (["source-example", "planar-assembly", "spatial-assembly"].includes(this.model.kind)) {
      sampleSourceView(
        this,
        sample || { nodes: this.sourceMetadata.initialNodes },
      );
      if (this.stepView && ["planar-assembly", "spatial-assembly"].includes(this.model.kind)) {
        const nodes = sample?.nodes || this.sourceMetadata.initialNodes.filter(n => this.model.bodies.some(b => b.id === n.id));
        this.stepView.update(this.model.kind === "planar-assembly" && sample
          ? nodes.map(node => ({...node, ry: node.angleDeg}))
          : nodes);
      }
      return;
    }
    if (
      ["suspension", "landing-gear-drop", "gear-deployment"].includes(
        this.model.kind,
      )
    ) {
      sampleIndustry(this, sample);
      return;
    }
    if (this.model.kind === "double-pendulum") {
      const p = this.model.parameters;
      const a1 = ((sample?.angle ?? p.angle1) * Math.PI) / 180,
        a2 = ((sample?.angle2 ?? p.angle2) * Math.PI) / 180;
      this.bob.position.set(
        p.length1 * Math.sin(a1),
        0,
        this.pivot.z - p.length1 * Math.cos(a1),
      );
      this.bob2.position
        .copy(this.bob.position)
        .add(
          new THREE.Vector3(
            p.length2 * Math.sin(a2),
            0,
            -p.length2 * Math.cos(a2),
          ),
        );
      if (sample) {
        this.bob.position.set(sample.x, sample.y, this.pivot.z + sample.z);
        this.bob2.position.set(sample.x2, sample.y2, this.pivot.z + sample.z2);
      }
      this.pin2.position.copy(this.bob.position);
      for (const [rod, a, b] of [
        [this.rod, this.pivot, this.bob.position],
        [this.rod2, this.bob.position, this.bob2.position],
      ]) {
        rod.position.copy(a).add(b).multiplyScalar(0.5);
        rod.quaternion.setFromUnitVectors(
          new THREE.Vector3(0, 1, 0),
          b.clone().sub(a).normalize(),
        );
      }
    } else if (this.model.kind === "pendulum") {
      const angle =
        ((sample?.angle ?? this.model.parameters.angle) * Math.PI) / 180;
      const s = this.model.parameters.length;
      this.bob.position.set(
        s * Math.sin(angle),
        0,
        this.pivot.z - s * Math.cos(angle),
      );
      if (sample)
        this.bob.position.set(sample.x, sample.y, this.pivot.z + sample.z);
      const delta = this.bob.position.clone().sub(this.pivot);
      this.rod.position
        .copy(this.pivot)
        .add(this.bob.position)
        .multiplyScalar(0.5);
      this.rod.quaternion.setFromUnitVectors(
        new THREE.Vector3(0, 1, 0),
        delta.normalize(),
      );
    } else {
      const x = sample?.x ?? this.model.parameters.displacement;
      const s = this.scale;
      this.bob.position.x = x;
      const points = [];
      for (let i = 0; i <= 120; i++) {
        const f = i / 120;
        points.push(
          new THREE.Vector3(
            -0.54 * s + (x + 0.385 * s) * f,
            Math.sin(f * Math.PI * 18) * 0.07 * s,
            0.24 * s + Math.cos(f * Math.PI * 18) * 0.07 * s,
          ),
        );
      }
      this.spring.geometry.dispose();
      this.spring.geometry = new THREE.TubeGeometry(
        new THREE.CatmullRomCurve3(points),
        120,
        0.009 * s,
        7,
        false,
      );
    }
  }
  setStepAsset(asset) {
    this.stepAsset = asset;
    if (this.model) this.setModel(this.model, false, this.sourceMetadata);
    this.reset();
  }
  renderStep() {
    this.stepView?.dispose();
    this.stepView = null;
    if (!this.model || !this.stepAsset) {
      if (["planar-assembly", "spatial-assembly"].includes(this.model?.kind)) {
        for (const node of this.sourceParts.nodes.values()) node.visible = true;
        for (const link of this.sourceParts.links) link.line.visible = true;
        this.showLabels(true);
      }
      return;
    }
    const assembly = ["planar-assembly", "spatial-assembly"].includes(this.model.kind);
    const nodes = assembly ? this.sourceMetadata.initialNodes.filter(n => this.model.bodies.some(b => b.id === n.id)) : [];
    const ids = new Set(nodes.map(n => n.id));
    const bindings = Object.fromEntries(Object.entries(this.stepAsset.metadata.bindings).filter(([,binding]) => ids.has(binding.body)));
    const bodyOrder = (this.model.bodies || []).map(body => body.id);
    this.stepView = createStepView(this.stepAsset, {
      initialNodes: nodes, bindings,
      offset: assembly ? this.sourceParts.offset : [0, 0, 0],
      entityForBody: id => id === this.model.bodies[0]?.id ? "body" : `node-${id}`,
      colorForBody: id => BODY_COLORS[Math.max(0, bodyOrder.indexOf(id)) % BODY_COLORS.length],
    });
    this.group.add(this.stepView.group);
    if (assembly) {
      for (const node of this.sourceParts.nodes.values()) node.visible = false;
      for (const link of this.sourceParts.links) link.line.visible = false;
      this.showLabels(false);
    } else {
      for (const child of this.group.children) if (child !== this.stepView.group) child.visible = false;
      this.showLabels(false);
    }
  }
  setReference(reference) {
    this.isolatedReference = false;
    this.group.visible = true;
    this.showLabels(true);
    if (this.referenceMesh) {
      this.referenceGroup.remove(this.referenceMesh);
      this.referenceMesh.material.dispose();
      this.referenceMesh = null;
    }
    if (reference) {
      this.referenceMesh = new THREE.Mesh(reference.geometry, this.material(0xd29b50, 0.25));
      this.referenceMesh.castShadow = true;
      this.referenceMesh.receiveShadow = true;
      this.referenceGroup.add(this.referenceMesh);
      this.placeReference();
    }
    this.reset();
  }
  placeReference() {
    const box = this.referenceMesh.geometry.boundingBox;
    const center = box.getCenter(new THREE.Vector3()), size = box.getSize(new THREE.Vector3());
    const gap = (this.scale || 1) * 0.25;
    this.referenceMesh.position.set((this.scale || 1) * 0.75 + size.x / 2 + gap - center.x, -center.y, size.z / 2 + gap - center.z);
  }
  isolateReference(isolated) {
    this.isolatedReference = Boolean(isolated && this.referenceMesh);
    this.group.visible = !this.isolatedReference;
    this.showLabels(!this.isolatedReference);
    this.reset();
  }
  reset() {
    const s = this.scale || 1;
    const pendulum = this.model?.kind !== "mass-spring";
    this.camera.position.set(s * 2.4, -s * 4, s * 2.3);
    if (this.model?.kind === "gear-deployment")
      this.camera.position.x = s * 1.3;
    if (["source-example", "planar-assembly", "spatial-assembly"].includes(this.model?.kind))
      this.camera.position.set(
        s * 1.9,
        -s * 3,
        this.sourceParts.focus.z + s * 1.4,
      );
    this.camera.far = Math.max(100, s * 100);
    this.camera.updateProjectionMatrix();
    this.grid.scale.setScalar(s);
    this.floor.scale.setScalar(s);
    this.controls.target.set(
      pendulum ? 0.2 * s : 0.08 * s,
      0,
      pendulum ? 0.52 * s : 0.17 * s,
    );
    if (["source-example", "planar-assembly", "spatial-assembly"].includes(this.model?.kind))
      this.controls.target.copy(this.sourceParts.focus);
    if (this.referenceMesh || this.stepView) {
      const bounds = this.referenceMesh ? new THREE.Box3().setFromObject(this.referenceGroup) : new THREE.Box3();
      if (this.stepView) bounds.union(new THREE.Box3().setFromObject(this.stepView.group));
      else if (!this.isolatedReference) bounds.union(new THREE.Box3().setFromObject(this.group));
      const center = bounds.getCenter(new THREE.Vector3()), size = bounds.getSize(new THREE.Vector3());
      const fit = Math.max(size.x, size.y, size.z, 0.1);
      this.camera.position.copy(center).add(new THREE.Vector3(fit * 1.5, -fit * 2.8, fit * 1.5));
      this.camera.far = Math.max(100, fit * 100);
      this.camera.updateProjectionMatrix();
      this.controls.target.copy(center);
      this.controls.minDistance = fit * 0.1;
      this.controls.maxDistance = fit * 15;
      this.controls.update();
      return;
    }
    this.controls.minDistance = s * 0.6;
    this.controls.maxDistance = s * 15;
    this.controls.update();
  }
  setSelection(entity) {
    this.selection = entity;
    this.group.traverse((obj) => {
      if (!obj.isMesh || !obj.userData.entity) return;
      obj.material.color.set(obj.userData.baseColor ?? 0x7196bd);
      obj.material.emissive.set(
        obj.userData.entity === entity ? 0x183458 : 0x000000,
      );
      obj.material.emissiveIntensity = 0.3;
    });
  }
  setGrid(visible) {
    this.grid.visible = visible;
  }
  /** Put the grid and shadow floor at a contact plane, or just below the geometry or motion envelope. */
  placeGround(envelopeMinZ = null) {
    const s = this.scale || 1;
    let z = -0.075;
    if (["source-example", "planar-assembly", "spatial-assembly"].includes(this.model?.kind)) {
      const planes = (this.model.contacts || []).filter((c) => Math.abs(c.planeNormal.z) > 0.99).map((c) => c.planePoint.z + this.sourceParts.offset.z);
      if (planes.length) z = Math.min(...planes) - s * 0.012;
      else {
        const bounds = new THREE.Box3().setFromObject(this.stepView ? this.stepView.group : this.group);
        const lowest = Math.min(bounds.isEmpty() ? 0 : bounds.min.z, Number.isFinite(envelopeMinZ) ? envelopeMinZ : Infinity);
        z = Math.min(-0.075 * s, lowest - 0.03 * s);
      }
    }
    this.grid.position.z = z;
    this.floor.position.z = z - 0.001 * s;
  }
  /** Lowest display height reached by any body point during a result (origins and farthest geometry). */
  resultEnvelopeMinZ(result) {
    let lowest = Infinity;
    for (const track of this.bodyTracks(result)) {
      const reach = this.stepView?.farthestPoint?.(track.id)?.length() ?? 0;
      const node = (i) => result.samples[i].nodes?.find((item) => String(item.id) === track.id);
      for (let i = 0; i < result.samples.length; i++) {
        const n = node(i);
        if (n) lowest = Math.min(lowest, n.z + this.sourceParts.offset.z - reach);
      }
    }
    return lowest;
  }
  /** World-space display position of a body's characteristic point for each sample. */
  bodyTracks(result) {
    const samples = result?.samples;
    if (!samples?.length || !this.model) return [];
    const kind = this.model.kind;
    if (["source-example", "planar-assembly", "spatial-assembly"].includes(kind)) {
      const offset = this.sourceParts.offset;
      const bodies = this.model.bodies || [];
      const ids = (samples[0].nodes || []).map((node) => String(node.id));
      const scale = this.scale || 1;
      return ids.map((id, index) => {
        const body = bodies.find((item) => item.id === id);
        const centre = body?.centerOfMass ? new THREE.Vector3(body.centerOfMass.x, body.centerOfMass.y, body.centerOfMass.z) : new THREE.Vector3();
        const track = (local) => samples.map((sample) => {
          const node = sample.nodes?.find((item) => String(item.id) === id);
          if (!node) return null;
          const point = local.clone();
          if (kind === "spatial-assembly") point.applyEuler(new THREE.Euler(node.rx * DEG, node.ry * DEG, node.rz * DEG, "XYZ"));
          else if (kind === "planar-assembly") point.applyAxisAngle(new THREE.Vector3(0, 1, 0), (node.angleDeg ?? node.ry ?? 0) * DEG);
          return point.add(new THREE.Vector3(node.x, node.y, node.z)).add(offset);
        });
        let points = track(centre);
        // A body spinning about a fixed centre traces nothing useful; follow its farthest geometry point instead.
        const extent = new THREE.Box3().setFromPoints(points.filter(Boolean)).getSize(new THREE.Vector3()).length();
        const tip = this.stepView?.farthestPoint?.(id);
        if (extent < scale * 0.03 && tip) points = track(tip);
        return { id, entity: index ? `node-${id}` : "body", points };
      });
    }
    const pivot = this.pivot || new THREE.Vector3();
    if (kind === "pendulum") return [{ id: "body", entity: "body", points: samples.map((s) => new THREE.Vector3(s.x, s.y, pivot.z + s.z)) }];
    if (kind === "double-pendulum")
      return [
        { id: "body", entity: "body", points: samples.map((s) => new THREE.Vector3(s.x, s.y, pivot.z + s.z)) },
        { id: "body2", entity: "body2", points: samples.map((s) => new THREE.Vector3(s.x2, s.y2, pivot.z + s.z2)) },
      ];
    return [];
  }
  setTrails(result, options = {}) {
    if (this.trails) {
      for (const trail of this.trails) {
        this.scene.remove(trail.ghost, trail.tube);
        trail.ghost.geometry.dispose(); trail.ghost.material.dispose();
        trail.tube.geometry.dispose(); trail.tube.material.dispose();
      }
    }
    this.trails = null;
    this.trailTimes = null;
    if (!result) return;
    const radius = (this.scale || 1) * 0.0045;
    this.trailWindow = options.window || 0;
    this.trailTimes = result.samples.map((sample) => sample.time);
    const bodies = options.bodies ? new Set(options.bodies) : null;
    this.trails = this.bodyTracks(result).map((track, index) => {
      if (bodies && !bodies.has(track.id) && !bodies.has(track.entity)) return null;
      const color = TRAIL_COLORS[index % TRAIL_COLORS.length];
      const valid = track.points.map((point, frame) => [point, frame]).filter(([point]) => point && [point.x, point.y, point.z].every(Number.isFinite));
      if (valid.length < 2) return null;
      const ghost = new THREE.Line(new THREE.BufferGeometry().setFromPoints(valid.map(([point]) => point)), new THREE.LineBasicMaterial({ color, transparent: true, opacity: 0.28, depthWrite: false }));
      ghost.visible = !this.trailWindow;
      const stride = Math.max(1, Math.ceil(valid.length / 700));
      const kept = valid.filter((_, i) => i % stride === 0 || i === valid.length - 1);
      const radial = 6;
      const curve = new THREE.CatmullRomCurve3(kept.map(([point]) => point), false, "centripetal");
      const tube = new THREE.Mesh(new THREE.TubeGeometry(curve, kept.length - 1, radius, radial, false), new THREE.MeshBasicMaterial({ color, transparent: true, opacity: 0.92 }));
      tube.renderOrder = 2;
      this.scene.add(ghost, tube);
      // Map each result frame to the number of tube segments drawn up to it.
      const segmentsAt = new Int32Array(result.samples.length);
      let k = 0;
      for (let frame = 0; frame < segmentsAt.length; frame++) {
        while (k < kept.length - 1 && kept[k + 1][1] <= frame) k++;
        segmentsAt[frame] = k;
      }
      return { ghost, tube, segmentsAt, perSegment: radial * 6 };
    }).filter(Boolean);
    this.setTrailFrame(0);
  }
  setTrailFrame(frame) {
    if (!this.trails?.length) return;
    const last = this.trailTimes.length - 1, end = Math.max(0, Math.min(frame, last));
    let start = 0;
    if (this.trailWindow > 0) {
      // First sample inside the trailing time window.
      const from = this.trailTimes[end] - this.trailWindow;
      let lo = 0, hi = end;
      while (lo < hi) { const mid = (lo + hi) >> 1; if (this.trailTimes[mid] < from) lo = mid + 1; else hi = mid; }
      start = lo;
    }
    for (const trail of this.trails) {
      const first = trail.segmentsAt[start], segments = trail.segmentsAt[end];
      trail.tube.geometry.setDrawRange(first * trail.perSegment, Math.max(0, segments - first) * trail.perSegment);
    }
  }
  setFollow(entity) {
    this.followEntity = entity || null;
    this.followLast = null;
  }
  followPoint() {
    if (!this.followEntity || !this.model) return null;
    const meshes = [];
    this.group.traverse((obj) => { if (obj.isMesh && obj.userData.entity === this.followEntity) meshes.push(obj); });
    if (!meshes.length) return null;
    const box = new THREE.Box3();
    for (const mesh of meshes) box.expandByObject(mesh);
    return box.isEmpty() ? null : box.getCenter(new THREE.Vector3());
  }
  applyFollow() {
    const point = this.followPoint();
    if (!point) return;
    if (this.followLast) {
      const delta = point.clone().sub(this.followLast);
      this.camera.position.add(delta);
      this.controls.target.add(delta);
    }
    this.followLast = point;
  }
  setTheme(dark) {
    this.grid.material.color?.set(dark ? 0x596579 : 0xc2cedd);
  }
  showLabels(show) {
    for (const l of this.labels)
      l.element.style.visibility = show && !this.isolatedReference ? "visible" : "hidden";
  }
}
