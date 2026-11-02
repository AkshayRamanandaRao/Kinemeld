/** Real cone/torus face picking, transformed attachment, Undo and project round trip. */
import './workspace-shim.mjs';
import assert from 'node:assert/strict';
import { execFileSync } from 'node:child_process';
import { mkdir, readFile, writeFile } from 'node:fs/promises';
import { resolve } from 'node:path';
import { chromium } from 'playwright';

const base = process.env.MBDYN_STUDIO_URL || 'http://127.0.0.1:8768';
const evidence = resolve(process.env.KINEMELD_CAD_EVIDENCE || 'tests/evidence/cad-curved');
await mkdir(evidence, { recursive: true });
const fixture = resolve(evidence, 'cones-tori.step');
execFileSync(process.env.MBDYN_STUDIO_PYTHON || 'python', ['-B', 'backend/test_step_curved_features.py', '--fixture', fixture], { stdio: 'pipe' });
const browser = await chromium.launch({ headless: true, args: ['--enable-unsafe-swiftshader'], ...(process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH ? { executablePath: process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH } : {}) });
const page = await browser.newPage({ viewport: { width: 1440, height: 1000 }, acceptDownloads: true });
const errors = [];
page.on('pageerror', error => errors.push(error.message));
page.on('dialog', dialog => dialog.accept());
await page.route('**/api/tour-preference', route => route.fulfill({ json: { enabled: false } }));
const close = (actual, expected, tolerance = 1e-7) => {
  for (const key of ['x', 'y', 'z']) assert(Math.abs(actual[key] - expected[key]) < tolerance, `${key}: ${actual[key]} != ${expected[key]}`);
};
async function save() {
  const event = page.waitForEvent('download');
  await page.locator('#saveButton').click();
  const download = await event;
  return { project: JSON.parse(await readFile(await download.path(), 'utf8')), path: await download.path() };
}
async function input(id, value) {
  await page.locator(id).fill(String(value));
  await page.locator(id).dispatchEvent('change');
}
async function aim(name, type) {
  return page.evaluate(async ({ name, type }) => {
    const { Box3, Vector3 } = await import('/vendor/three.module.js');
    const view = window.__view;
    const part = view.stepAsset.parts.find(part => part.name.includes(name));
    if (!part) throw Error(`Missing actual STEP occurrence ${name}`);
    const mesh = view.stepView.partMeshes.get(part.id);
    view.scene.updateMatrixWorld(true);
    const box = new Box3().setFromObject(mesh), centre = box.getCenter(new Vector3());
    const distance = Math.max(box.getSize(new Vector3()).length() * 3, .12);
    const rect = view.renderer.domElement.getBoundingClientRect();
    view.controls.enableDamping = false;
    for (const direction of [[1, -1, 1], [-1, -1, 1], [1, 1, 1], [-1, 1, 1]]) {
      view.controls.target.copy(centre);
      view.camera.position.copy(centre).addScaledVector(new Vector3(...direction).normalize(), distance);
      view.controls.update();
      view.renderer.render(view.scene, view.camera);
      for (const face of part.faces.filter(face => face.type === type)) {
        const [start, count] = face.triangles;
        for (let triangle = start; triangle < start + count; triangle += Math.max(1, Math.floor(count / 80))) {
          const point = new Vector3();
          for (let corner = 0; corner < 3; corner++) point.add(new Vector3().fromBufferAttribute(mesh.geometry.attributes.position, part.indices[triangle * 3 + corner]));
          point.multiplyScalar(1 / 3).applyMatrix4(mesh.matrixWorld).project(view.camera);
          const x = rect.left + (point.x + 1) * rect.width / 2, y = rect.top + (1 - point.y) * rect.height / 2;
          if (x < rect.left + 20 || x > rect.right - 20 || y < rect.top + 30 || y > rect.bottom - 20) continue;
          const hit = view.pickPart(x, y);
          if (hit?.partId === part.id && Number.isInteger(hit.triangle) && part.faces.some(face => face.type === type && hit.triangle >= face.triangles[0] && hit.triangle < face.triangles[0] + face.triangles[1])) return { x, y };
        }
      }
    }
    throw Error(`No visible ${type} face on ${name}`);
  }, { name, type });
}
async function pick(name, type, image) {
  const target = await aim(name, type);
  await page.mouse.move(target.x, target.y);
  await page.waitForFunction(type => document.querySelector('#viewTooltip')?.textContent.startsWith(type === 'cone' ? 'Cone apex' : 'Torus centre'), type);
  if (image) await page.screenshot({ path: resolve(evidence, image) });
  await page.mouse.click(target.x, target.y);
}
try {
  await page.goto(base);
  await page.waitForFunction(() => document.querySelector('#solverStatus')?.textContent.includes('MBDyn ready'));
  await page.evaluate(async () => {
    const { MechanismView } = await import('/viewport.js');
    const setModel = MechanismView.prototype.setModel;
    MechanismView.prototype.setModel = function (...args) { window.__view = this; return setModel.apply(this, args); };
  });
  const project = JSON.parse(await readFile('examples/prescribed-wheel-bump/wheel-bump.mbdyn-studio', 'utf8'));
  project.model.name = 'Cone and torus CAD picking';
  delete project.assets;
  await page.locator('#projectFile').setInputFiles({ name: 'curved-features.mbdyn-studio', mimeType: 'application/json', buffer: Buffer.from(JSON.stringify(project)) });
  await page.waitForFunction(() => document.querySelector('#notice')?.textContent.includes('Project imported and validated'));
  await page.locator('[data-step="model"]').click();
  await page.locator('#stepButton').click();
  await page.locator('#stepFile').setInputFiles(fixture);
  await page.waitForFunction(() => window.__view?.stepAsset?.parts?.length === 4);
  const partId = await page.locator('#stepPart option').filter({ hasText: 'Cone placed' }).getAttribute('value');
  await page.locator('#stepPart').selectOption(partId);
  await page.locator('#stepBody').selectOption('knuckle');
  await page.locator('#stepBind').click();
  await page.locator('#stepClose').click();
  await page.locator('#modelTree [data-entity="body"]').click();
  await input('#spatial-body-knuckle-pose-rz', 90);
  await page.locator('#modelTree [data-entity="joint-hub_axis"]').click();
  const values = async () => Object.fromEntries(await Promise.all(['anchorA', 'anchorB', 'axisA', 'axisB'].flatMap(field => ['x', 'y', 'z'].map(async axis => [`${field}-${axis}`, Number(await page.locator(`#spatial-joint-hub_axis-${field}-${axis}`).inputValue())]))));
  const before = await values();
  await page.locator('#spatial-joint-hub_axis-pick').click();
  await pick('Cone placed', 'cone', 'cone-pick.png');
  await page.waitForFunction(() => document.querySelector('#notice')?.textContent.includes('Joint hub_axis placed on'));
  let actual = await values();
  const expected = { anchorA: { x: .14, y: .1975, z: 0 }, anchorB: { x: -.1975, y: .14, z: 0 }, axisA: { x: 1, y: 0, z: 0 }, axisB: { x: 0, y: 1, z: 0 } };
  for (const [field, vector] of Object.entries(expected)) close(Object.fromEntries(['x', 'y', 'z'].map(axis => [axis, actual[`${field}-${axis}`]])), vector);
  await page.locator('#undoButton').click();
  assert.deepEqual(await values(), before);
  await page.locator('#redoButton').click();
  assert.deepEqual(await values(), actual);

  await page.locator('summary', { hasText: 'Named reference frames' }).click();
  await page.getByRole('button', { name: 'Add reference frame' }).click();
  await page.locator('#reference-frame-parent').selectOption('ground');
  await page.locator('#reference-frame-pick').click();
  await pick('Torus placed', 'torus', 'torus-pick.png');
  await page.waitForFunction(() => document.querySelector('#notice')?.textContent.includes('Reference frame Frame 1 placed on'));
  close(Object.fromEntries(await Promise.all(['x', 'y', 'z'].map(async axis => [axis, Number(await page.locator(`#reference-frame-translation-${axis}`).inputValue())]))), { x: .16, y: .16, z: 0 });
  assert(Math.abs(Number(await page.locator('#reference-frame-rotation-rx').inputValue()) + 90) < 1e-6);
  const saved = await save();
  assert.equal(saved.project.format, 'mbdyn-studio/1');
  assert.equal(saved.project.assets.step.schemaVersion, 1);
  assert.equal(saved.project.assets.step.bindings[partId].body, 'knuckle');
  assert.equal(saved.project.model.frames[0].body, 'ground');
  await page.locator('#projectFile').setInputFiles(saved.path);
  await page.waitForFunction(() => document.querySelector('#notice')?.textContent.includes('Project imported and validated'));
  const reopened = await save();
  assert.deepEqual(reopened.project.model, saved.project.model);
  assert.deepEqual(reopened.project.assets, saved.project.assets);
  await page.locator('#measureViewButton').click();
  await pick('Cone placed', 'cone');
  await pick('Torus placed', 'torus');
  const measured = await page.locator('#pickText').textContent();
  const distance = Math.hypot(.3975, .1075) * 1000;
  assert(measured.includes(`Distance ${distance.toFixed(2)} mm`), measured);
  assert(measured.includes('axes 0.00° apart'), measured);
  await page.screenshot({ path: resolve(evidence, 'project-reopened.png') });
  assert.deepEqual(errors, []);
  await writeFile(resolve(evidence, 'report.json'), JSON.stringify({ ok: true, checks: ['Real transformed cone/torus face raycasting', 'Attached-body rotation', 'Joint placement and Undo/Redo', 'Named frame placement', 'Original STEP/model/binding save and reopen', 'Regenerated-feature measurement'], distanceMm: distance, pageErrors: errors }, null, 2));
  console.log(`Cone/torus picking: transformed joint and frame placement, Undo/Redo, source-preserving project round trip, measurement ${distance.toFixed(2)} mm.`);
} finally {
  await browser.close();
}
