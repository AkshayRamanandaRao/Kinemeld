/** Place a joint and measure in the 3D view by picking analytic STEP faces (cylinder and plane). */
import './workspace-shim.mjs';
import assert from 'node:assert/strict';
import { chromium } from 'playwright';

const base = process.env.MBDYN_STUDIO_URL || 'http://127.0.0.1:8768';
const browser = await chromium.launch({ headless: true, args: ['--enable-unsafe-swiftshader'] });
const page = await browser.newPage({ viewport: { width: 1440, height: 960 } });
const errors = [];
page.on('pageerror', (error) => errors.push(error.message));
page.on('dialog', (dialog) => dialog.accept());
await page.route('**/api/tour-preference', (route) => route.fulfill({ json: { enabled: false } }));
try {
  await page.goto(base);
  await page.waitForFunction(() => document.querySelector('#solverStatus')?.textContent.includes('MBDyn ready'));
  // Keep a handle on the view to aim the camera and find screen positions of known CAD points.
  await page.evaluate(async () => {
    const { MechanismView } = await import('/viewport.js');
    const original = MechanismView.prototype.setModel;
    MechanismView.prototype.setModel = function (...args) { window.__view = this; return original.apply(this, args); };
  });
  await page.locator('#examplesButton').click();
  await page.locator('.example-card').filter({ has: page.getByRole('heading', { name: 'Wheel-end drop test', exact: true }) }).getByRole('button').click();
  await page.waitForFunction(() => document.querySelector('#notice')?.textContent.includes('Wheel-end drop test loaded'), null, { timeout: 240000 });
  await page.locator('[data-step="model"]').click();

  // Misplace the hub bearing, then restore it by picking the hub's outer cylinder.
  await page.locator('#modelTree [data-entity="joint-hub_axis"]').click();
  for (const [field, value] of [['anchorA-x', 0.03], ['anchorB-x', 0.03], ['axisA-x', 0], ['axisA-y', 1], ['axisB-x', 0], ['axisB-y', 1]]) {
    await page.locator(`#spatial-joint-hub_axis-${field}`).fill(String(value));
    await page.locator(`#spatial-joint-hub_axis-${field}`).dispatchEvent('change');
  }
  await page.locator('#spatial-joint-hub_axis-pick').click();
  assert(await page.locator('#pickBar').isVisible());
  // Look from the hub's open end so its outer cylinder is visible inside the tyre, and aim at it.
  const aim = () => page.evaluate(() => {
    const view = window.__view, offset = view.sourceParts.offset;
    const hub = { x: -0.04, y: -0.0875, z: 0.6 };
    view.controls.target.set(hub.x + offset.x, hub.y + offset.y, hub.z + offset.z);
    view.camera.position.set(hub.x + offset.x - 0.42, hub.y + offset.y - 0.22, hub.z + offset.z + 0.26);
    view.controls.update();
    view.renderer.render(view.scene, view.camera);
    const point = view.camera.position.clone().set(hub.x + offset.x - 0.028, hub.y + offset.y - 0.012, hub.z + offset.z + 0.025);
    point.project(view.camera);
    const rect = view.renderer.domElement.getBoundingClientRect();
    return { x: rect.left + (point.x + 1) / 2 * rect.width, y: rect.top + (1 - point.y) / 2 * rect.height };
  });
  let target = await aim();
  await page.mouse.move(target.x, target.y);
  await page.waitForFunction(() => /Cylinder Ø55\.0 mm · axis [−+]x/.test(document.querySelector('#viewTooltip')?.textContent || ''), null, { timeout: 10000 });
  await page.mouse.click(target.x, target.y);
  await page.waitForFunction(() => document.querySelector('#notice')?.textContent.includes('Joint hub_axis placed on'));
  assert(await page.locator('#pickBar').isHidden());
  const value = async (field) => Number(await page.locator(`#spatial-joint-hub_axis-${field}`).inputValue());
  for (const field of ['anchorA-x', 'anchorA-y', 'anchorA-z', 'anchorB-x', 'anchorB-y', 'anchorB-z']) assert(Math.abs(await value(field)) < 1e-9, `${field} = ${await value(field)}`);
  assert(Math.abs(Math.abs(await value('axisA-x')) - 1) < 1e-9 && Math.abs(await value('axisA-y')) < 1e-9);
  assert.equal(await value('axisA-x'), await value('axisB-x'));
  await page.locator('#validateButton').click();
  await page.waitForFunction(() => document.querySelector('#validationBadge')?.textContent === 'Ready');

  // Undo restores the misplaced joint in one step.
  await page.locator('#undoButton').click();
  assert.equal(await value('anchorA-x'), 0.03);
  await page.locator('#redoButton').click();

  // Measure from the hub's outer cylinder to its end face. Undo and Redo re-fit the view, so aim again.
  await page.locator('#measureViewButton').click();
  target = await aim();
  await page.mouse.click(target.x, target.y);
  const face = await page.evaluate(() => {
    const view = window.__view, offset = view.sourceParts.offset;
    const point = view.camera.position.clone().set(-0.04 - 0.035 + offset.x, -0.0875 - 0.026 + offset.y, 0.6 + offset.z);
    point.project(view.camera);
    const rect = view.renderer.domElement.getBoundingClientRect();
    return { x: rect.left + (point.x + 1) / 2 * rect.width, y: rect.top + (1 - point.y) / 2 * rect.height };
  });
  await page.mouse.click(face.x, face.y);
  const text = await page.locator('#pickText').textContent();
  assert.match(text, /Distance \d+\.\d+ mm/);
  assert.match(text, /axes 0\.00° apart/);
  await page.keyboard.press('Escape');
  assert(await page.locator('#pickBar').isHidden());
  assert.deepEqual(errors, []);
  console.log(`CAD picking: hub bearing placed from the hub cylinder, validated, undone and redone; measurement "${text}".`);
} finally {
  await browser.close();
}
